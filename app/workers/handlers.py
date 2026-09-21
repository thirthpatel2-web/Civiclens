"""Job handlers (run inside worker processes): AI enrichment, e-mail, document ingestion."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.core.exceptions import CivicLensError
from app.providers.vision import VisionProvider, analyze_evidence
from app.realtime.events import COMPLAINT_PROCESSED
from app.services.classification_service import SEVERITIES, ClassificationService, compute_priority
from app.services.complaint_common import ComplaintEffects, Outbox
from app.services.complaint_service import ComplaintService
from app.services.document_service import DocumentIngestor, Storage
from app.services.notification_service import NotificationService
from app.services.sla_service import SlaCalculator
from app.services.uow import UowFactory
from app.services.voice_service import TranslationService
from app.workers.queue import Handler, PermanentJobError

LOW_CONFIDENCE = 0.6


class GrievanceWorker:
    def __init__(self, uow_factory: UowFactory, complaints: ComplaintService, ai_classifier: ClassificationService | None, vision: VisionProvider | None, storage: Storage,
                 effects: ComplaintEffects, notifications: NotificationService, ingestor_factory: Callable[[Any], DocumentIngestor] | None = None,
                 consent_check: Callable[[str, str], bool] | None = None, translation: TranslationService | None = None, push_sender: Any | None = None, government: Any | None = None) -> None:  # fmt: skip
        self._uow, self._complaints, self._ai, self._vision, self._storage = uow_factory, complaints, ai_classifier, vision, storage
        self._fx, self._notifications, self._ingestor_factory = effects, notifications, ingestor_factory
        self._consent = consent_check or (lambda user_id, purpose: False)
        self._translation = translation
        self._push = push_sender
        self._gov = government

    def handlers(self) -> dict[str, Handler]:
        return {"complaint.enrich": self.enrich_complaint, "notification.email": self.send_email, "notification.push": self.send_push, "gov.submit": self.submit_government, "evidence.analyze": self.analyze_evidence_job, "document.ingest": self.ingest_document}

    # ------------------------------------------------------------------ complaint.enrich
    def enrich_complaint(self, payload: dict[str, Any], job: Any) -> dict[str, Any]:
        cid = payload.get("complaint_id")
        out = Outbox()
        result: dict[str, Any] = {}
        with self._uow() as uow:
            c = uow.complaints.get(cid) if cid else None
            if c is None:
                raise PermanentJobError("complaint not found")
            if not self._consent(c.citizen_id, "ai_processing"):
                c.ai_status = "consent_required"
                uow.complaints.update(c)
                self._fx.event(uow, c, "ai_enriched", None, details={"status": "consent_required"}, internal=True, actor_label="AI")
                uow.commit()
                return {"ai_status": "consent_required"}
            if c.ai_status == "consent_required":
                c.ai_status = "ok"
            analysed = 0
            for ev in uow.complaints.list_evidence(c.id):
                if ev.analysis_status == "PENDING":
                    analyze_evidence(ev, self._storage, self._vision)
                    uow.complaints.update_evidence(ev)
                    analysed += 1
            result["evidence_analysed"] = analysed

            # Derived translation (separate field). The original text is never modified.
            translated_note = None
            if c.language != "en" and c.translated_text is None and self._translation is not None and self._translation.available:
                try:
                    c.translated_text = self._translation.translate(c.description, c.language, "en")
                    c.translated_language, c.translation_provider = "en", self._translation.provider_name
                    translated_note = "translated"
                except CivicLensError as exc:
                    translated_note = f"translation_failed: {exc.message}"[:120]
            result["translation"] = translated_note or ("not_needed" if c.language == "en" else "not_configured")
            text_for_ai = c.translated_text or c.description
            needs_model = bool(c.classification.get("ambiguous")) or float(c.classification.get("confidence") or 0.0) < LOW_CONFIDENCE
            if needs_model and self._ai is not None:
                r = self._ai.classify(c.title, text_for_ai)
                c.ai_status = r.ai_status if r.source != "llm" else "ok"
                if r.source == "llm":
                    c.classification = {**c.classification, "category": r.category, "severity": r.severity, "confidence": r.confidence, "source": "llm", "explanation": r.explanation, "ambiguous": False}
                    c.category = r.category
                    if SEVERITIES.index(r.severity) > SEVERITIES.index(c.severity):
                        c.severity = r.severity
                    c.priority = compute_priority(c.severity, affects_safety=bool(r.affects_safety), near_sensitive_site=bool(r.near_sensitive_site), duplicate_count=len(c.duplicates))["priority"]
                    if c.department_code is None:
                        decision = self._complaints.decide_route(uow, r, f"{c.title} {text_for_ai}", c.ward)
                        c.routing = {"source": decision.source, "rule_id": decision.rule_id, "confidence": decision.confidence, "explanation": decision.explanation, "ai_disagreement": decision.ai_disagreement, "manual_triage": decision.needs_manual_triage}
                        self._complaints.apply_routing(uow, c, decision)
                        c.sla_due_at = SlaCalculator(list(uow.config.sla_policies())).due_at(c.created_at, c.priority, c.department_code)
            elif needs_model:
                c.ai_status = "not_configured"
            c.updated_at = self._fx.clock()
            uow.complaints.update(c)
            self._fx.event(uow, c, "ai_enriched", None, details={"ai_status": c.ai_status, **result}, internal=True, actor_label="AI")
            out.events.append(self._fx.complaint_event(COMPLAINT_PROCESSED, c, {"ai_status": c.ai_status}, result))
            result["ai_status"] = c.ai_status
            self._fx.audit(uow).record("complaint.ai_enriched", actor_id=None, resource_type="complaint", resource_id=c.id, metadata={"ai_status": c.ai_status})
            uow.commit()
        self._fx.flush(out)
        return result

    # ------------------------------------------------------------------ notification.email
    def send_email(self, payload: dict[str, Any], job: Any) -> dict[str, Any]:
        with self._uow() as uow:  # phase 1: queued -> sending, persisted before the external call
            n = self._notifications.begin_send(uow.notifications, payload.get("notification_id", ""), "email")
            user = uow.users.get_by_id(payload.get("user_id", ""))
            address = user.email if user else None
            uow.commit()
        with self._uow() as uow:  # phase 2: the outcome
            n = self._notifications.finish_email(uow.notifications, n, address)
            uow.commit()
        if n.status == "failed" and n.error and n.error.startswith("SMTP"):
            raise RuntimeError(n.error)  # transient: the queue retries
        return {"status": n.status}

    def send_push(self, payload: dict[str, Any], job: Any) -> dict[str, Any]:
        with self._uow() as uow:
            n = self._notifications.begin_send(uow.notifications, payload.get("notification_id", ""), "push")
            tokens = [d.token for d in uow.push.list_for_user(payload.get("user_id", ""))]
            uow.commit()
        with self._uow() as uow:
            n = self._notifications.finish_push(uow.notifications, n, self._push, tokens)
            uow.commit()
        if n.status == "failed" and tokens and n.error and "unavailable" in n.error.lower():
            raise RuntimeError(n.error)
        return {"status": n.status}

    def analyze_evidence_job(self, payload: dict[str, Any], job: Any) -> dict[str, Any]:
        with self._uow() as uow:
            ev = uow.complaints.get_evidence(payload.get("evidence_id", ""))
            if ev is None:
                raise PermanentJobError("evidence not found")
            analyze_evidence(ev, self._storage, self._vision)
            uow.complaints.update_evidence(ev)
            uow.commit()
        return {"status": ev.analysis_status}

    def submit_government(self, payload: dict[str, Any], job: Any) -> dict[str, Any]:
        if self._gov is None:
            raise PermanentJobError("government submission is not wired")
        try:
            return self._gov.execute(payload.get("complaint_id", ""), payload.get("platform", ""))  # type: ignore[no-any-return]
        except ValueError as exc:
            raise PermanentJobError(str(exc)) from exc  # missing record/unknown platform: retrying cannot help

    # ------------------------------------------------------------------ document.ingest
    def ingest_document(self, payload: dict[str, Any], job: Any) -> dict[str, Any]:
        if self._ingestor_factory is None:
            raise PermanentJobError("document ingestion is not wired")
        with self._uow() as uow:
            ingestor = self._ingestor_factory(uow)
            doc = ingestor.process(payload.get("document_id", ""))
            uow.commit()
        if doc.status == "failed" and doc.attempts < 3:
            raise RuntimeError(doc.error or "ingestion failed")
        return {"status": str(doc.status), "chunks": doc.chunk_count}


