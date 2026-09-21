"""Image-evidence analysis through a configurable vision model. Never fabricates a result:
without a provider the evidence is marked IMAGE_ANALYSIS_UNAVAILABLE; a provider error is stored as FAILED."""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Protocol

from app.core.exceptions import CivicLensError
from app.rag.ollama import OllamaClient
from app.services.classification_service import CATEGORIES, SEVERITIES
from app.services.document_service import Storage
from app.services.ports import EvidenceRecord

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")
_PROMPT = ("Describe this photo submitted with a civic complaint. Reply with ONLY JSON: "
           '{"summary": short string, "issue_category": one of %s or "unknown", "severity_hint": one of %s or "unknown", '
           '"visible_text": string or "", "confidence": number 0-1}. Describe only what is visible; do not guess.') % (list(CATEGORIES), list(SEVERITIES))  # fmt: skip


class VisionProvider(Protocol):
    name: str

    def analyze(self, image: bytes, mime: str) -> dict[str, Any]: ...


class OllamaVisionProvider:
    name = "ollama"

    def __init__(self, client: OllamaClient, model: str) -> None:
        from app.core.exceptions import NotConfigured

        if not model:
            raise NotConfigured("OLLAMA_VISION_MODEL is not set.")
        self._client, self._model = client, model

    def analyze(self, image: bytes, mime: str) -> dict[str, Any]:
        raw = self._client.chat(self._model, [{"role": "user", "content": _PROMPT}], images=[base64.b64encode(image).decode("ascii")])
        try:
            data = json.loads(_FENCE.sub("", raw.strip()))
        except ValueError as exc:
            raise ValueError("vision model did not return JSON") from exc
        cat, sev = data.get("issue_category", "unknown"), data.get("severity_hint", "unknown")
        return {"summary": str(data.get("summary", ""))[:500], "issue_category": cat if cat in CATEGORIES else "unknown", "severity_hint": sev if sev in SEVERITIES else "unknown",
                "visible_text": str(data.get("visible_text", ""))[:1000], "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.0))))}  # fmt: skip


def analyze_evidence(ev: EvidenceRecord, storage: Storage, provider: VisionProvider | None) -> EvidenceRecord:
    """Mutates and returns ``ev`` with the truthful outcome."""
    if not ev.mime.startswith("image/"):
        ev.analysis_status = "NOT_APPLICABLE"
        return ev
    if provider is None:
        ev.analysis_status, ev.analysis_provider, ev.analysis_result, ev.analysis_error = "IMAGE_ANALYSIS_UNAVAILABLE", None, None, "No vision provider is configured."
        return ev
    ev.analysis_provider = provider.name
    try:
        ev.analysis_result, ev.analysis_status, ev.analysis_error = provider.analyze(storage.read(ev.storage_name), ev.mime), "OK", None
    except (CivicLensError, ValueError, KeyError, TypeError) as exc:
        ev.analysis_result, ev.analysis_status, ev.analysis_error = None, "FAILED", getattr(exc, "message", str(exc))[:300]
    return ev
