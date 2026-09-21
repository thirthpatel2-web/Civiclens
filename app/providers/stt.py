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
