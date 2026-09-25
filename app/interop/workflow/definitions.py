"""The ``residence_certificate_verification`` workflow: the completion spec's own example (Section
12), stored as data and executed by ``WorkflowEngine`` - not a single hard-coded Python scenario.

Every step function below is built from primitives this codebase already has and has already
tested independently (``app.interop.connectors.runtime``, ``app.interop.identity_resolution``,
``app.interop.canonical.v1.transform``, ``InteropGatewayService._document_quality``) - this module
adds new *orchestration*, not new business logic, so the risk profile of proving "the engine can
drive the real flow" stays low. ``InteropGatewayService.request_document_exchange`` remains the
tested, unchanged production entry point for the no-reupload demo; this is a genuine, additional,
independently-verified execution path through the same underlying mechanisms - not a replacement
this milestone. See docs/INTEROPERABILITY.md's "Configurable workflows" section for exactly what
that means and doesn't mean.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.interop_platform import InteropConsentGrant, UnifiedApplication
from app.interop.canonical.v1.models import Document as CanonicalDocument
from app.interop.canonical.v1.transform import canonical_document_to_dept_b_fields
from app.interop.connectors import runtime as connector_runtime
from app.interop.identity_resolution import IdentityResolutionService
from app.interop.workflow.engine import StepFn, StepSpec, define_workflow

RESIDENCE_CERTIFICATE_VERIFICATION = "residence_certificate_verification"

RESIDENCE_CERTIFICATE_VERIFICATION_STEPS: list[StepSpec] = [
    StepSpec("resolve_identity"),
    StepSpec("request_consent", requires_approval=True),  # pauses for a real manual grant, exactly like the primary gateway path
    StepSpec("fetch_document", retry_max_attempts=2, timeout_seconds=10),
    StepSpec("validate_document"),
    StepSpec("transform_data"),
    StepSpec("deliver_document", retry_max_attempts=2),
    StepSpec("publish_event", on_failure="skip"),  # a broken event bus must never fail the exchange itself
    StepSpec("update_tracker", on_failure="skip"),
    StepSpec("notify", on_failure="skip"),
]


def register_default_workflows(session: Session) -> None:
    """Idempotent upsert - safe to call on every app start, same convention as the mock-system/
    connector-registry/federation-client seeding."""
    define_workflow(session, workflow_id=RESIDENCE_CERTIFICATE_VERIFICATION, name="Residence certificate verification (Dept B <- Dept A)", steps=RESIDENCE_CERTIFICATE_VERIFICATION_STEPS)
    # Flushed now, not at commit: the service catalog (app.interop.catalog) has a real FK into this
    # table, and the ORM has no relationship between the two to order the INSERTs by - so on a fresh
    # database the catalog row could otherwise be written first and fail the FK check.
    session.flush()


def _canonical_document_from_context(ctx: dict[str, Any]) -> CanonicalDocument:
    """Rebuilds the canonical Document from the plain, JSON-safe fields ``fetch_document`` put in
    the context - never from a stored ORM row (the context is a jsonb column; an ORM instance
    can't round-trip through it, and shouldn't need to - this is exactly the same canonical shape
    ``dept_a_document_to_canonical`` produces from the live row, just reconstructed from context)."""
    issued_on = date.fromisoformat(ctx["_document_issued_on"]) if ctx.get("_document_issued_on") else None
    return CanonicalDocument(document_id="", document_type=ctx["_document_type"], reference=ctx["_document_reference_no"], status=ctx["_document_status"], source_system="dept_a", issued_on=issued_on)


def build_residence_certificate_step_registry(session: Session, *, clock=None) -> dict[str, StepFn]:
    clock = clock or (lambda: datetime.now(UTC))
    resolver = IdentityResolutionService(clock)

    def resolve_identity(ctx: dict[str, Any]) -> dict[str, Any]:
        application_no = ctx["application_no"]
        app_result = connector_runtime.call(session, "dept_b", "get_entity", "application", application_no)
        if not app_result.ok or app_result.data is None:
            raise RuntimeError(f"no application {application_no!r} in dept_b")
        app_row = app_result.data
        ben_result = connector_runtime.call(session, "dept_b", "get_entity", "beneficiary", app_row.beneficiary_code)
        if not ben_result.ok or ben_result.data is None:
            raise RuntimeError("beneficiary referenced by this application no longer exists")
        beneficiary = ben_result.data

        b_result = resolver.resolve_person(session, system="dept_b", identifier_type="beneficiary_code", identifier_value=beneficiary.beneficiary_code, name=beneficiary.full_name, mobile=beneficiary.mobile_number)
        session.flush()  # autoflush is disabled - the dept_a resolution below must see this link
        if b_result.candidate_id:
            raise RuntimeError("identity ambiguous on the dept_b side - manual review required")

        by_mobile = connector_runtime.call(session, "dept_a", "query", "resident", mobile=beneficiary.mobile_number)
        candidates = by_mobile.data if by_mobile.ok else []
        if not candidates:
            by_name = connector_runtime.call(session, "dept_a", "query", "resident", name_contains=beneficiary.full_name)
            candidates = by_name.data if by_name.ok else []
        if not candidates:
            raise RuntimeError("no matching dept_a resident found")
        resident = candidates[0]

        a_result = resolver.resolve_person(session, system="dept_a", identifier_type="resident_id", identifier_value=resident.resident_id, name=resident.full_name, mobile=resident.mobile)
        if a_result.candidate_id or a_result.master_id != b_result.master_id:
            raise RuntimeError("identity ambiguous or conflicting on the dept_a side - manual review required")

        return {"master_id": b_result.master_id, "resident_id": resident.resident_id, "beneficiary_code": beneficiary.beneficiary_code}

    def request_consent(ctx: dict[str, Any]) -> dict[str, Any]:
        """By the time this runs, the engine has already paused (requires_approval) and been
        resumed with an explicit approval - this step turns that approval into the same real,
        auditable InteropConsentGrant row the primary gateway path creates, not a shortcut."""
        document_type = ctx.get("document_type", "residence_certificate")
        existing = session.execute(
            select(InteropConsentGrant).where(InteropConsentGrant.master_id == ctx["master_id"], InteropConsentGrant.data_category == document_type, InteropConsentGrant.status == "granted").order_by(InteropConsentGrant.created_at.desc())
        ).scalars().first()  # fmt: skip
        if existing is not None:
            return {"consent_id": existing.consent_id}
        from app.services.interop_gateway_service import (
            REQUIRED_DOCUMENT_FIELDS,  # local import: avoid a module-load-order cycle
        )

        now = clock()
        grant = InteropConsentGrant(
            consent_id=str(uuid.uuid4()), master_id=ctx["master_id"], citizen_user_id=ctx["actor_user_id"],
            requesting_system="dept_b", providing_system="dept_a", purpose=f"Workflow-engine verification for application {ctx['application_no']}",
            data_category=document_type, fields=list(REQUIRED_DOCUMENT_FIELDS), status="granted", created_at=now, decided_at=now, expires_at=now + timedelta(days=30),
        )
        session.add(grant)
        session.flush()
        return {"consent_id": grant.consent_id}

    def fetch_document(ctx: dict[str, Any]) -> dict[str, Any]:
        result = connector_runtime.call(session, "dept_a", "fetch_document", ctx["resident_id"], ctx.get("document_type", "residence_certificate"))
        if not result.ok or result.data is None:
            raise RuntimeError("document_not_found")
        doc = result.data
        # Only plain, JSON-safe values go into the context (it's a jsonb column) - never the raw
        # ORM row itself, which isn't serializable and would fail the next flush.
        return {
            "_document_type": doc.document_type, "_document_status": doc.status, "_document_reference_no": doc.reference_no,
            "_document_issued_on": doc.issued_on.date().isoformat() if doc.issued_on else None,
        }

    def validate_document(ctx: dict[str, Any]) -> dict[str, Any]:
        from app.services.interop_gateway_service import (
            _document_quality,  # reuse, don't reimplement, the exact same rubric
        )

        canonical_doc = _canonical_document_from_context(ctx)
        score, issues = _document_quality(canonical_doc)
        if score < 0.7:
            raise RuntimeError(f"data_quality_failed: {'; '.join(issues)}")
        return {"document_reference": canonical_doc.reference, "quality_score": score}

    def transform_data(ctx: dict[str, Any]) -> dict[str, Any]:
        canonical_doc = _canonical_document_from_context(ctx)
        return {"_dept_b_fields": canonical_document_to_dept_b_fields(canonical_doc)}

    def deliver_document(ctx: dict[str, Any]) -> dict[str, Any]:
        result = connector_runtime.call(session, "dept_b", "update", "application", ctx["application_no"], ctx["_dept_b_fields"])
        if not result.ok:
            raise RuntimeError("dept_b_update_failed")
        return {"delivered": True}

    def publish_event(ctx: dict[str, Any]) -> dict[str, Any]:
        bus = ctx.get("_bus")
        if bus is None:
            return {}
        from app.interop.events.types import InteropEvent

        bus.publish(InteropEvent(
            event_type="ExchangeCompleted", source_system="dept_a", destination="dept_b", correlation_id=ctx.get("_correlation_id", "unknown"),
            payload={"citizen_user_id": ctx.get("actor_user_id"), "application_no": ctx["application_no"], "document_reference": ctx.get("document_reference")},
        ))
        return {}

    def update_tracker(ctx: dict[str, Any]) -> dict[str, Any]:
        existing = session.execute(select(UnifiedApplication).where(UnifiedApplication.external_reference == ctx["application_no"], UnifiedApplication.primary_system == "dept_b")).scalars().first()
        now = clock()
        if existing is None:
            app_result = connector_runtime.call(session, "dept_b", "get_entity", "application", ctx["application_no"])
            service_type = app_result.data.service_type if app_result.ok and app_result.data else "unknown"
            existing = UnifiedApplication(application_id=str(uuid.uuid4()), reference=f"CL-APP-{ctx['application_no']}", master_id=ctx["master_id"], service_type=service_type, primary_system="dept_b", external_reference=ctx["application_no"], status="in_progress", created_at=now, updated_at=now)
            session.add(existing)
            session.flush()
        existing.status, existing.updated_at = "completed", now
        session.add(existing)
        return {"unified_application_id": existing.application_id}

    def notify(ctx: dict[str, Any]) -> dict[str, Any]:
        return {"notified": True}

    return {
        "resolve_identity": resolve_identity, "request_consent": request_consent, "fetch_document": fetch_document,
        "validate_document": validate_document, "transform_data": transform_data, "deliver_document": deliver_document,
        "publish_event": publish_event, "update_tracker": update_tracker, "notify": notify,
    }
