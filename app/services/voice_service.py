"""Voice input service: audio -> same-language transcript (native script) -> stored with its metadata.

Rules enforced here (each has a test):
* the transcript is never translated; ``translated`` providers are rejected by contract;
* ``auto`` (language auto-detection) is accepted only if the configured engine declares it;
* a language is accepted only if the configured engine declares it - the UI lists what the engine declares;
* if the returned text is not in the expected script (a sign the engine romanised or translated it) the
  record carries ``script_ok=False`` and a warning; the text is *not* altered or silently replaced;
* with no provider configured the result is ``NOT_CONFIGURED`` and there is no transcript.
"""

from __future__ import annotations

import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from app.core.authorization import AuthContext, Permission, require
from app.core.exceptions import CivicLensError, NotConfigured, NotFound, ValidationFailed
from app.i18n.languages import LANGUAGES, detect_language, script_matches
from app.providers.speech import MAX_AUDIO_BYTES, sniff_audio
from app.providers.stt import SpeechToTextProvider, TranslationProvider

AUTO = "auto"
NO_SPEECH_MESSAGE = "No clear speech was recognised. Please speak a little closer to the microphone and try again."
# Whisper's well-known inventions for silence/noise; a real civic question is never just one of these.
_SILENCE_HALLUCINATIONS = frozenset({"thank you", "thanks", "thank you for watching", "thanks for watching", "you", "bye", "please subscribe", "subtitles by the amara.org community"})


def looks_like_noise(text: str, avg_logprob: float | None = None) -> bool:
    """True when a transcript is almost certainly the engine hallucinating on silence or noise rather than
    real speech: no real letters, one character repeated (a tone read as 'ಠಠಠ'), a stock silence phrase, or
    very low decoder confidence on a very short result. Real sentences pass untouched."""
    letters = [ch for ch in text if unicodedata.category(ch)[0] in ("L", "M")]
    if len(letters) < 2 or len(set(letters)) <= 2:
        return True
    if text.strip().strip(".!?,।").strip().lower() in _SILENCE_HALLUCINATIONS:
        return True
    return avg_logprob is not None and avg_logprob < -0.55 and len(text.split()) <= 3


@dataclass
class VoiceRecord:
    id: str
    user_id: str
    mime: str
    size: int
    language_requested: str  # a language code or "auto"
    status: str  # OK | NOT_CONFIGURED | FAILED
    created_at: datetime
    transcript: str | None = None  # the engine's output, exactly as returned
    language_detected: str | None = None
    detected_by: str | None = None  # "provider" | "script"
    provider: str | None = None
    error: str | None = None
    script_ok: bool = True
    warnings: list[str] = field(default_factory=list)
    confidence: float | None = None


class VoiceRepository(Protocol):
    def add(self, v: VoiceRecord) -> None: ...
    def get(self, voice_id: str) -> VoiceRecord | None: ...


class VoiceService:
    def __init__(self, uow_factory: Callable[[], Any], provider: SpeechToTextProvider | None, clock: Callable[[], datetime] | None = None) -> None:
        self._uow, self._provider, self._clock = uow_factory, provider, clock or (lambda: datetime.now(UTC))

    def capabilities(self) -> dict[str, Any]:
        """What the *configured* engine actually supports (drives the language picker in every client)."""
        if self._provider is None:
            return {"state": "NOT_CONFIGURED", "provider": None, "auto_detect": False, "languages": []}
        caps = self._provider.capabilities()
        return {"state": "CONFIGURED", "provider": self._provider.name, "auto_detect": caps.auto_detect,
                "languages": [{"code": c, "name": LANGUAGES[c].name, "native": LANGUAGES[c].native, "script": LANGUAGES[c].script} for c in sorted(caps.languages) if c in LANGUAGES]}  # fmt: skip

    def transcribe(self, ctx: AuthContext, audio: bytes, declared_mime: str | None, language: str = AUTO) -> VoiceRecord:
        require(ctx, Permission.COMPLAINT_CREATE)
        if not audio or len(audio) > MAX_AUDIO_BYTES:
            raise ValidationFailed(f"Recording must be 1 byte to {MAX_AUDIO_BYTES // (1024 * 1024)} MB.")
        mime = sniff_audio(audio)
        if mime is None:
            raise ValidationFailed("Unsupported or corrupt audio format.")
        language = (language or AUTO).lower()
        if language != AUTO and language not in LANGUAGES:
            raise ValidationFailed("Unsupported language.", details={"allowed": [AUTO, *sorted(LANGUAGES)]})
        rec = VoiceRecord(str(uuid.uuid4()), ctx.user_id, mime, len(audio), language, "OK", self._clock())
        if self._provider is None:
            rec.status, rec.error = "NOT_CONFIGURED", "No speech-to-text engine is configured; no transcript was produced."
        else:
            caps = self._provider.capabilities()
            if language == AUTO and not caps.auto_detect:
                raise ValidationFailed(f"The '{self._provider.name}' speech engine cannot auto-detect the language; please select it.", details={"supported": sorted(caps.languages)})
            if language != AUTO and language not in caps.languages:
                raise ValidationFailed(f"The '{self._provider.name}' speech engine does not support this language.", details={"supported": sorted(caps.languages)})
            rec.provider = self._provider.name
            try:
                t = self._provider.transcribe(audio, mime, None if language == AUTO else language)
            except CivicLensError as exc:
                rec.status, rec.error = "FAILED", exc.message
            else:
                if looks_like_noise(t.text, t.extra.get("avg_logprob")):
                    rec.status, rec.error = "FAILED", NO_SPEECH_MESSAGE
                else:
                    self._apply(rec, t.text, t.language, t.detected_language, t.confidence, t.translated)
        with self._uow() as uow:
            uow.voice.add(rec)
            uow.commit()
        return rec

    @staticmethod
    def _apply(rec: VoiceRecord, text: str, transcribed_as: str, provider_detected: str | None, confidence: float | None, translated: bool) -> None:
        if translated:  # contract violation: an engine that translates must not be used for citizen input
            rec.status, rec.error = "FAILED", "The speech engine returned a translation instead of a transcription; the result was discarded."
            return
        rec.transcript, rec.confidence = text, confidence
        if provider_detected:
            rec.language_detected, rec.detected_by = provider_detected, "provider"
        else:
            rec.language_detected, rec.detected_by = detect_language(text)[0], "script"
        expected = transcribed_as if transcribed_as in LANGUAGES else rec.language_detected
        if expected and not script_matches(expected, text):
            rec.script_ok = False
            rec.warnings.append(f"The text is not written in the expected script for '{expected}'. The engine may have romanised or translated it. Please review and correct it before using it.")

    def get_for_user(self, ctx: AuthContext, voice_id: str) -> VoiceRecord:
        with self._uow() as uow:
            v = uow.voice.get(voice_id)
        if v is None or v.user_id != ctx.user_id:
            raise NotFound("Voice recording not found.")
        return v


class TranslationService:
    """Optional, *derived* translation. Never used to replace citizen input."""

    def __init__(self, provider: TranslationProvider | None) -> None:
        self._provider = provider

    @property
    def available(self) -> bool:
        return self._provider is not None

    @property
    def provider_name(self) -> str | None:
        return getattr(self._provider, "name", None)

    def translate(self, text: str, source: str, target: str) -> str:
        if not (text or "").strip() or len(text) > 5000:
            raise ValidationFailed("Text must be 1-5000 characters.")
        if source == target:
            return text
        if self._provider is None:
            raise NotConfigured("No translation provider is configured.")
        return self._provider.translate(text, source, target)
