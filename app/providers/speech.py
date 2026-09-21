"""Speech-to-text and translation providers (Bhashini) + the voice service.

Bhashini access follows its two-step "pipeline" flow (obtain a pipeline config with user id +
ULCA key, then call the returned inference endpoint). The request/response shapes here are
written from Bhashini's published pipeline documentation and have NOT been verified against the
live service (no credentials/network were available); every URL/ID is configuration, nothing
is defaulted for the pipeline id. Without credentials the provider is ``NOT_CONFIGURED`` and no
transcript or translation is ever produced.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import DependencyUnavailable, NotConfigured, ValidationFailed
from app.integrations.base import Transport, TransportError, UrllibTransport, assert_safe_url
from app.providers.stt import SttCapabilities, Transcript

DEFAULT_PIPELINE_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
MAX_AUDIO_BYTES = 10 * 1024 * 1024
BHASHINI_DEFAULT_LANGUAGES = frozenset({"en", "hi", "mr", "bn", "gu", "pa", "ta", "te", "kn", "ml"})  # declared per Bhashini docs; override with BHASHINI_ASR_LANGUAGES
_MAGIC = (("audio/wav", lambda b: b[:4] == b"RIFF" and b[8:12] == b"WAVE"), ("audio/webm", lambda b: b[:4] == b"\x1a\x45\xdf\xa3"), ("audio/ogg", lambda b: b[:4] == b"OggS"),
          ("audio/mpeg", lambda b: b[:3] == b"ID3" or b[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")), ("audio/mp4", lambda b: b[4:8] == b"ftyp"))  # fmt: skip


def sniff_audio(data: bytes) -> str | None:
    return next((m for m, test in _MAGIC if len(data) > 12 and test(data)), None)


@dataclass(frozen=True)
class BhashiniConfig:
    user_id: str = ""
    api_key: str = field(default="", repr=False)
    pipeline_id: str = ""
    pipeline_url: str = DEFAULT_PIPELINE_URL
    timeout: float = 30.0
    allow_private_hosts: bool = False  # tests only; production keeps the SSRF guard on
    asr_languages: frozenset[str] = BHASHINI_DEFAULT_LANGUAGES

    def configured(self) -> bool:
        return bool(self.user_id and self.api_key and self.pipeline_id)


class BhashiniProvider:
    name = "bhashini"

    def __init__(self, config: BhashiniConfig, transport: Transport | None = None) -> None:
        if not config.configured():
            raise NotConfigured("Bhashini requires BHASHINI_USER_ID, BHASHINI_API_KEY and BHASHINI_PIPELINE_ID.")
        self._cfg, self._t = config, transport or UrllibTransport()

    def _post(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> Any:
        try:
            assert_safe_url(url, allow_private=self._cfg.allow_private_hosts, allow_http=False)
            resp = self._t.request("POST", url, headers, body, self._cfg.timeout)
        except TransportError as exc:
            raise DependencyUnavailable(f"Bhashini is unreachable ({exc}).") from exc
        if not 200 <= resp.status < 300 or not isinstance(resp.body, dict):
            raise DependencyUnavailable(f"Bhashini returned HTTP {resp.status}.")
        return resp.body

    def _pipeline(self, task: str, config: dict[str, Any]) -> tuple[str, dict[str, str], str]:
        data = self._post(self._cfg.pipeline_url, {"userID": self._cfg.user_id, "ulcaApiKey": self._cfg.api_key},
                          {"pipelineTasks": [{"taskType": task, "config": config}], "pipelineRequestConfig": {"pipelineId": self._cfg.pipeline_id}})  # fmt: skip
        try:
            endpoint = data["pipelineInferenceAPIEndPoint"]
            key = endpoint["inferenceApiKey"]
            service_id = data["pipelineResponseConfig"][0]["config"][0]["serviceId"]
            return endpoint["callbackUrl"], {key["name"]: key["value"]}, service_id
        except (KeyError, IndexError, TypeError) as exc:
            raise DependencyUnavailable("Bhashini returned an unexpected pipeline response.") from exc

    def capabilities(self) -> SttCapabilities:
        return SttCapabilities(self._cfg.asr_languages, auto_detect=False)  # the ASR pipeline needs the source language

    def transcribe(self, audio: bytes, mime: str, language: str | None) -> Transcript:
        """ASR task only (never a translation task): output is in the spoken language's own script."""
        if language is None:
            raise ValidationFailed("This speech engine cannot auto-detect the language; please select it.")
        if language not in self._cfg.asr_languages:
            raise ValidationFailed("Unsupported language for speech recognition.", details={"supported": sorted(self._cfg.asr_languages)})
        url, headers, sid = self._pipeline("asr", {"language": {"sourceLanguage": language}})
        data = self._post(url, headers, {"pipelineTasks": [{"taskType": "asr", "config": {"language": {"sourceLanguage": language}, "serviceId": sid}}],
                                         "inputData": {"audio": [{"audioContent": base64.b64encode(audio).decode("ascii")}]}})  # fmt: skip
        try:
            text = str(data["pipelineResponse"][0]["output"][0]["source"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise DependencyUnavailable("Bhashini returned an unexpected transcription response.") from exc
        if not text:
            raise ValidationFailed("No speech could be recognised in the recording.")
        return Transcript(text, language, self.name)

    def translate(self, text: str, source: str, target: str) -> str:
        if source not in BHASHINI_DEFAULT_LANGUAGES or target not in BHASHINI_DEFAULT_LANGUAGES:
            raise ValidationFailed("Unsupported language pair.")
        cfg = {"language": {"sourceLanguage": source, "targetLanguage": target}}
        url, headers, sid = self._pipeline("translation", cfg)
        data = self._post(url, headers, {"pipelineTasks": [{"taskType": "translation", "config": {**cfg, "serviceId": sid}}], "inputData": {"input": [{"source": text}]}})
        try:
            return str(data["pipelineResponse"][0]["output"][0]["target"])
        except (KeyError, IndexError, TypeError) as exc:
            raise DependencyUnavailable("Bhashini returned an unexpected translation response.") from exc
