"""Ollama HTTP client and provider wrappers (standard library only).

Nothing here hard-codes a model name: models come from configuration and an empty
model name yields ``NotConfigured`` instead of a guess. Failures surface as
``DependencyUnavailable`` so callers can degrade honestly.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any, Protocol
from urllib.parse import urlparse

from app.core.exceptions import DependencyUnavailable, NotConfigured

# Ollama's default keep_alive (5m) unloads the model between the kind of request gaps this app
# sees in normal use (an officer reading a report, a citizen typing a complaint), so a cold load
# - which alone took 52s for llama3.1:8b on this machine - hits nearly every request. Asking Ollama
# to hold the model resident for longer trades idle RAM for avoiding that repeated penalty.
OLLAMA_KEEP_ALIVE = "30m"


def validate_base_url(url: str, *, allow_private: bool = True) -> str:
    """Only http(s) URLs without embedded credentials (SSRF/credential-leak hygiene)."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base URL must be http(s) with a host")
    if parsed.username or parsed.password:
        raise ValueError("base URL must not embed credentials")
    return url.rstrip("/")


class OllamaClient:
    def __init__(self, base_url: str, *, timeout: float = 60.0) -> None:
        self.base_url = validate_base_url(base_url)
        self.timeout = timeout

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(  # noqa: S310 - scheme validated in __init__
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                body = resp.read()
        except urllib.error.HTTPError as exc:
            raise DependencyUnavailable(f"Ollama returned HTTP {exc.code} for {path}.") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DependencyUnavailable("Ollama is unreachable.") from exc
        try:
            parsed = json.loads(body)
        except ValueError as exc:
            raise DependencyUnavailable("Ollama returned a non-JSON response.") from exc
        if not isinstance(parsed, dict):
            raise DependencyUnavailable("Ollama returned an unexpected response shape.")
        return parsed

    def list_models(self) -> list[str]:
        data = self._request("/api/tags")
        return [m.get("name", "") for m in data.get("models", []) if isinstance(m, dict)]

    def embed(self, model: str, inputs: Sequence[str]) -> list[list[float]]:
        data = self._request("/api/embed", {"model": model, "input": list(inputs), "keep_alive": OLLAMA_KEEP_ALIVE})
        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(inputs):
            raise DependencyUnavailable("Ollama returned an unexpected embedding payload.")
        return [[float(x) for x in v] for v in vectors]

    def chat(self, model: str, messages: list[dict[str, str]], *, temperature: float = 0.0, json_mode: bool = False, images: list[str] | None = None) -> str:
        if images:  # base64 images attach to the last (user) message, as Ollama's chat API expects
            messages = [*messages[:-1], {**messages[-1], "images": images}]  # type: ignore[dict-item]
        # think=False is a no-op on models without a "thinking" capability, but on ones that have it
        # (e.g. gemma4) it skips an internal reasoning trace we never surface anyway - one measured
        # test dropped a trivial reply from 165 generated tokens to 3 for the same visible answer.
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False, "options": {"temperature": temperature}, "keep_alive": OLLAMA_KEEP_ALIVE, "think": False}
        if json_mode:
            payload["format"] = "json"
        data = self._request("/api/chat", payload)
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise DependencyUnavailable("Ollama returned no message content.")
        return content


class EmbeddingProvider(Protocol):
    @property
    def dimensions(self) -> int: ...
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OllamaEmbeddingProvider:
    def __init__(self, client: OllamaClient, model: str, dimensions: int = 0) -> None:
        if not model:
            raise NotConfigured("OLLAMA_EMBEDDING_MODEL is not set.")
        self._client, self._model, self._dimensions = client, model, dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._client.embed(self._model, texts)
        for v in vectors:
            if self._dimensions and len(v) != self._dimensions:
                raise DependencyUnavailable(
                    f"Embedding model returned {len(v)} dimensions but EMBEDDING_DIMENSIONS={self._dimensions}."
                )
        if vectors and not self._dimensions:
            self._dimensions = len(vectors[0])
        return vectors


class OllamaChatProvider:
    def __init__(self, client: OllamaClient, model: str) -> None:
        if not model:
            raise NotConfigured("OLLAMA_MODEL is not set.")
        self._client, self._model = client, model

    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.0) -> str:
        return self._client.chat(self._model, messages, temperature=temperature)


def probe(client: OllamaClient, required_models: Sequence[str]) -> tuple[bool, str, float]:
    """Health probe: (ok, detail, latency_seconds). Used by verify_environment and health."""
    start = time.monotonic()
    try:
        models = client.list_models()
    except DependencyUnavailable as exc:
        return False, exc.message, time.monotonic() - start
    missing = [m for m in required_models if m and m not in models and f"{m}:latest" not in models]
    latency = time.monotonic() - start
    if missing:
        return False, f"reachable, but model(s) not pulled: {', '.join(missing)}", latency
    return True, "reachable", latency
