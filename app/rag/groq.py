"""Groq Cloud chat provider (OpenAI-compatible /chat/completions, LPU-hosted).

Standard library only, matching app.rag.ollama. Implements the same ``ChatProvider`` protocol
(``chat(messages, *, temperature) -> str``) that GroundedGenerator/ClassificationService/reranker
already depend on, so swapping this in for OllamaChatProvider needs no changes anywhere else -
only which one ``container.py`` constructs as ``self.llm``. Embeddings and OCR vision stay on
Ollama; Groq's API is chat-completion only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.core.exceptions import DependencyUnavailable, NotConfigured


class GroqChatProvider:
    def __init__(self, api_key: str, model: str, *, base_url: str = "https://api.groq.com/openai/v1", timeout: float = 60.0) -> None:
        if not api_key:
            raise NotConfigured("GROQ_API_KEY is not set.")
        if not model:
            raise NotConfigured("GROQ_MODEL is not set.")
        self._api_key, self._model, self._base_url, self._timeout = api_key, model, base_url.rstrip("/"), timeout

    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.0) -> str:
        payload: dict[str, Any] = {"model": self._model, "messages": messages, "temperature": temperature}
        req = urllib.request.Request(  # noqa: S310 - fixed https base URL, no user-controlled scheme
            f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            # Cloudflare (fronting Groq's API) returns a bare 403 "error code: 1010" for urllib's
            # default User-Agent - it's a well-known bot-fingerprinting signature, not anything
            # about the request itself. Any non-default UA clears it.
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}", "User-Agent": "CivicLens/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
                body = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise DependencyUnavailable(f"Groq returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DependencyUnavailable("Groq is unreachable.") from exc
        try:
            parsed = json.loads(body)
            return str(parsed["choices"][0]["message"]["content"])
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise DependencyUnavailable("Groq returned an unexpected response shape.") from exc
