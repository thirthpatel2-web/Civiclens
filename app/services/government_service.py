"""Government-platform submission: consent-gated, queued, state-machine driven, honest.

    request -> consent_required | not_configured | queued -> submitting -> submitted | failed

* A row reaches ``submitted`` ONLY after an adapter call really returned SUCCESS (an HTTP 2xx with a valid body).
* No consent (``data_sharing_government``) => nothing leaves the system.
* No credentials/endpoints => ``not_configured`` and **no network call**.
* The outbound body is CivicLens' canonical grievance (no citizen name/e-mail/phone). When a platform's documented contract
  is supplied, only ``GovernmentAdapter.build_submission`` (per-adapter) and the field map need to change - this orchestration stays.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.authorization import AuthContext, Permission, Role, can_access_complaint, require
from app.core.exceptions import NotFound, ValidationFailed
from app.integrations.base import GovernmentAdapter, OperationStatus
from app.services.complaint_common import ComplaintEffects, Outbox
from app.services.ports import ComplaintRecord, GovernmentSubmissionRecord
from app.services.uow import UowFactory

CONSENT_PURPOSE = "data_sharing_government"


def canonical_payload(c: ComplaintRecord) -> dict[str, Any]:
    return {"reference": c.reference, "title": c.title, "description": c.description, "language": c.language, "translated_text": c.translated_text, "category": c.category,
            "priority": c.priority, "department": c.department_code, "ward": c.ward, "latitude": c.lat, "longitude": c.lng, "created_at": c.created_at.isoformat()}  # fmt: skip


class GovernmentSubmissionService:
    def __init__(self, uow_factory: UowFactory, effects: ComplaintEffects, adapters: dict[str, GovernmentAdapter]) -> None:
        self._uow, self._fx, self._adapters = uow_factory, effects, adapters

    def _complaint_for(self, uow: Any, ctx: AuthContext, complaint_id: str, *, write: bool) -> ComplaintRecord:
        c = uow.complaints.get(complaint_id)
        if c is None:
            raise NotFound("Complaint not found.")
        if ctx.role is Role.CITIZEN:
            if c.citizen_id != ctx.user_id:
                raise NotFound("Complaint not found.")
        elif not can_access_complaint(ctx, owner_id=c.citizen_id, department_id=c.department_code, write=write):
            raise NotFound("Complaint not found.")
        return c

    def states(self, ctx: AuthContext, complaint_id: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            c = self._complaint_for(uow, ctx, complaint_id, write=False)
            rows = {r.platform: r for r in uow.government.list_for_complaint(c.id)}
            consent = bool(uow.consent.latest_by_purpose(c.citizen_id).get(CONSENT_PURPOSE) and uow.consent.latest_by_purpose(c.citizen_id)[CONSENT_PURPOSE].granted)
        out = []
        for platform, a in self._adapters.items():
            r = rows.get(platform)
            out.append({"platform": platform, "display_name": a.display_name, "adapter_state": a.state.value, "configured": a.is_configured(), "consent_granted": consent,
                        "state": r.state if r else "not_started", "external_reference": r.external_reference if r else None, "attempts": r.attempts if r else 0, "last_error": r.last_error if r else None})  # fmt: skip
        return out

    def request(self, ctx: AuthContext, complaint_id: str, platform: str) -> GovernmentSubmissionRecord:
        if ctx.role is Role.CITIZEN:
            require(ctx, Permission.COMPLAINT_READ_OWN)
        else:
            require(ctx, Permission.COMPLAINT_UPDATE_STATUS)
        adapter = self._adapters.get(platform)
        if adapter is None:
            raise ValidationFailed("Unknown platform.", details={"allowed": sorted(self._adapters)})
        out = Outbox()
        with self._uow() as uow:
            c = self._complaint_for(uow, ctx, complaint_id, write=ctx.role is not Role.CITIZEN)
            now = self._fx.clock()
            rec = uow.government.get(c.id, platform) or GovernmentSubmissionRecord(str(uuid.uuid4()), c.id, platform, "not_started", ctx.user_id, now, now)
            if rec.state in ("submitted", "queued", "submitting"):
                return rec  # idempotent
            consent = uow.consent.latest_by_purpose(c.citizen_id).get(CONSENT_PURPOSE)
            if not (consent and consent.granted):
                rec.state, rec.last_error = "consent_required", "The citizen has not consented to sharing this complaint with government platforms."
            elif not adapter.is_configured():
                rec.state, rec.last_error = "not_configured", "Integration is not configured: " + ", ".join(adapter.config.missing()) + ". Nothing was sent."
            else:
                rec.state, rec.last_error, rec.attempts = "queued", None, 0
                job, created = self._fx.jobs.enqueue(uow, "gov.submit", {"complaint_id": c.id, "platform": platform}, f"gov:{c.id}:{platform}:{now.isoformat()}")
                if created:
                    out.jobs.append(job)
            rec.updated_at = now
            uow.government.save(rec)
            self._fx.audit(uow).record("government.submission_requested", actor_id=ctx.user_id, resource_type="complaint", resource_id=c.id, metadata={"platform": platform, "state": rec.state})
            uow.commit()
        self._fx.flush(out)
        return rec

    def execute(self, complaint_id: str, platform: str) -> dict[str, Any]:
        """Worker step: really call the adapter. Raises (for the queue to retry) only on transient failure."""
        adapter = self._adapters.get(platform)
        if adapter is None:
            raise ValueError("unknown platform")
        with self._uow() as uow:
            c = uow.complaints.get(complaint_id)
            rec = uow.government.get(complaint_id, platform)
            if c is None or rec is None:
                raise ValueError("submission not found")
            if rec.state == "submitted":
                return {"state": "submitted", "note": "already submitted"}
            rec.state, rec.attempts, rec.updated_at = "submitting", rec.attempts + 1, self._fx.clock()
            uow.government.save(rec)
            uow.commit()
            payload = canonical_payload(c)
        result = adapter.submit_grievance(payload, idempotency_key=f"civiclens:{complaint_id}:{platform}")
        out = Outbox()
        with self._uow() as uow:
            c = uow.complaints.get(complaint_id)
            rec = uow.government.get(complaint_id, platform)
            assert c is not None and rec is not None
            now = self._fx.clock()
            rec.updated_at = now
            if result.status is OperationStatus.SUCCESS:
                rec.state, rec.last_error, rec.submitted_at = "submitted", None, now
                rec.external_reference = result.data.external_reference if result.data else None
                self._fx.event(uow, c, "government_submitted", None, remarks=f"Shared with {adapter.display_name}" + (f" (reference {rec.external_reference})" if rec.external_reference else ""),
                               details={"platform": platform, "external_reference": rec.external_reference}, actor_label=adapter.display_name)  # fmt: skip
                self._fx.notify(uow, out, c.citizen_id, "system", "Complaint shared", f"{c.reference} was submitted to {adapter.display_name}.", c, dedupe_key=f"gov:{c.id}:{platform}")
            elif result.status is OperationStatus.NOT_CONFIGURED:
                rec.state, rec.last_error = "not_configured", result.error
            else:
                rec.state, rec.last_error = "failed", result.error
            uow.government.save(rec)
            self._fx.audit(uow).record("government.submission_result", actor_id=None, resource_type="complaint", resource_id=complaint_id, metadata={"platform": platform, "status": str(result.status), "attempts": result.attempts})
            uow.commit()
        self._fx.flush(out)
        if result.status is OperationStatus.FAILED:
            raise RuntimeError(result.error or "government submission failed")  # queue retries with backoff
        return {"state": rec.state}


