"""Speech-to-text abstraction: same-language transcription, native script preserved.

Contract every provider must honour
-----------------------------------
* ``transcribe`` returns text **in the language that was spoken**, in that language's own script.
  It must never translate. (The Whisper provider passes ``task="transcribe"`` explicitly; the Bhashini
  provider only ever requests an ASR task, never a translation task.)
* A provider declares what it really supports via ``capabilities()``. Callers must not offer or accept a
  language (or auto-detection) that the provider did not declare.
* ``translated`` is always ``False``; translation, when wanted, is a separate step producing a separate field.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.exceptions import DependencyUnavailable, NotConfigured, ValidationFailed


@dataclass(frozen=True)
class SttCapabilities:
    languages: frozenset[str]
    auto_detect: bool


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str  # language the text was transcribed as
    provider: str
    detected_language: str | None = None  # provider's own detection, when it has one
    confidence: float | None = None
    translated: bool = False  # invariant: providers never translate
    extra: dict[str, Any] = field(default_factory=dict)


class SpeechToTextProvider(Protocol):
    name: str

    def capabilities(self) -> SttCapabilities: ...
    def transcribe(self, audio: bytes, mime: str, language: str | None) -> Transcript:
        """``language=None`` means auto-detect (only valid if ``capabilities().auto_detect``)."""
        ...


class TranslationProvider(Protocol):
    name: str

    def translate(self, text: str, source: str, target: str) -> str: ...


# Whisper's documented multilingual support covers these codes (verified by name in its language table).
WHISPER_LANGUAGES = frozenset({"en", "hi", "mr", "bn", "gu", "pa", "ta", "te", "kn", "ml"})


class WhisperProvider:
    """Self-hosted multilingual STT via ``faster-whisper`` (CTranslate2). Runs on the server; no external API.

    ``task="transcribe"`` is passed explicitly so non-English speech is NOT translated to English.
    Accuracy varies by language and model size (larger models are markedly better for Dravidian languages);
    choose ``WHISPER_MODEL`` accordingly. Not executed in the build sandbox (package/model absent).
    """

    name = "whisper"

    def __init__(self, model_name: str, *, device: str = "auto", compute_type: str = "int8", model: Any | None = None) -> None:
        if not model_name and model is None:
            raise NotConfigured("WHISPER_MODEL is not set.")
        if model is not None:  # injected (tests)
            self._model = model
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise NotConfigured("Install faster-whisper to use the self-hosted speech provider.") from exc
        self._model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def capabilities(self) -> SttCapabilities:
        return SttCapabilities(WHISPER_LANGUAGES, auto_detect=True)

    def transcribe(self, audio: bytes, mime: str, language: str | None) -> Transcript:
        if language is not None and language not in WHISPER_LANGUAGES:
            raise ValidationFailed("Unsupported language for this speech engine.", details={"supported": sorted(WHISPER_LANGUAGES)})
        try:
            segments, info = self._model.transcribe(io.BytesIO(audio), language=language, task="transcribe", vad_filter=True, beam_size=5)
            text = " ".join(s.text.strip() for s in segments).strip()
        except Exception as exc:
            raise DependencyUnavailable(f"Speech recognition failed ({type(exc).__name__}).") from exc
        if not text:
            raise ValidationFailed("No speech could be recognised in the recording.")
        detected = getattr(info, "language", None)
        return Transcript(text, language or detected or "", self.name, detected, getattr(info, "language_probability", None))


# Groq's transcription endpoint always transcribes (never translates) - that's a separate endpoint
# entirely, so there's no task= param to pass. It also returns the detected language as an English
# name ("English", "Hindi", ...), not the ISO 639-1 code the rest of this app uses everywhere else.
_GROQ_LANGUAGE_NAME_TO_CODE = {
    "english": "en", "hindi": "hi", "marathi": "mr", "bengali": "bn", "gujarati": "gu",
    "punjabi": "pa", "tamil": "ta", "telugu": "te", "kannada": "kn", "malayalam": "ml",
}


class GroqWhisperProvider:
    """Whisper large-v3 (or the -turbo variant), hosted on Groq's LPUs - same transcription
    contract as WhisperProvider (never translates) but cloud-hosted, so it doesn't compete with
    this machine's own limited CPU/RAM for a self-hosted model."""

    name = "groq_whisper"

    def __init__(self, api_key: str, model: str, *, base_url: str = "https://api.groq.com/openai/v1", timeout: float = 60.0) -> None:
        if not api_key:
            raise NotConfigured("GROQ_API_KEY is not set.")
        if not model:
            raise NotConfigured("GROQ_WHISPER_MODEL is not set.")
        self._api_key, self._model, self._base_url, self._timeout = api_key, model, base_url.rstrip("/"), timeout

    def capabilities(self) -> SttCapabilities:
        return SttCapabilities(WHISPER_LANGUAGES, auto_detect=True)

    def transcribe(self, audio: bytes, mime: str, language: str | None) -> Transcript:
        if language is not None and language not in WHISPER_LANGUAGES:
            raise ValidationFailed("Unsupported language for this speech engine.", details={"supported": sorted(WHISPER_LANGUAGES)})
        boundary = uuid.uuid4().hex
        ext = (mime.rsplit("/", 1)[-1] or "m4a").split(";")[0]
        fields: list[tuple[str, str]] = [("model", self._model), ("response_format", "verbose_json")]
        if language:
            fields.append(("language", language))
        parts: list[bytes] = []
        for k, v in fields:
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8"))
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.{ext}"\r\nContent-Type: {mime}\r\n\r\n'.encode("utf-8")
            + audio + b"\r\n"
        )  # fmt: skip
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(parts)
        req = urllib.request.Request(  # noqa: S310 - fixed https base URL
            f"{self._base_url}/audio/transcriptions", data=body, method="POST",
            # See app.rag.groq: Cloudflare 403s urllib's default User-Agent regardless of the request.
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "CivicLens/1.0"},
        )  # fmt: skip
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise DependencyUnavailable(f"Groq returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DependencyUnavailable("Groq is unreachable.") from exc
        try:
            parsed = json.loads(raw)
            text = str(parsed["text"]).strip()
        except (ValueError, KeyError, TypeError) as exc:
            raise DependencyUnavailable("Groq returned an unexpected transcription response.") from exc
        if not text:
            raise ValidationFailed("No speech could be recognised in the recording.")
        raw_detected = parsed.get("language")
        detected = _GROQ_LANGUAGE_NAME_TO_CODE.get(str(raw_detected).strip().lower()) if raw_detected else None
        return Transcript(text, language or detected or "", self.name, detected)
