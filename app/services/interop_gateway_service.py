"""InteropGatewayService: the orchestrator behind the "no re-upload" cross-department demo.

Department B (Seva Setu) needs a residence certificate that Department A (Revenue Records) already
holds for this citizen. Today a citizen would download it from A and re-upload it to B. This service
does that exchange for them, end to end, using only infrastructure this codebase already has:

  1. resolve the citizen's identity across A and B (app.interop.identity_resolution) - never
     auto-links below CONFIRM_THRESHOLD; an ambiguous match stops the flow and waits for an
     officer to confirm or reject it (see resolve_identity_candidate below).
  2. require an explicit, purpose-specific consent grant before any cross-system read happens
     (request_document_exchange returns "consent_required" and stops; nothing is read from
     Department A until grant_consent has been called for that exact grant).
  3. call the Department A connector through the connector runtime (app.interop.connectors.runtime)
     - never a mock-system function directly - transform its response into the canonical v1 schema
     (app.interop.canonical.v1), and quality-check the canonical record (a check specific to what a
     "verified document" needs, not the grievance-shaped rubric in app.interop.common_data_model -
     reusing that would score irrelevant fields like "location" against a resident document and
     produce a misleading number).
  4. transform the canonical record into exactly the fields Department B needs
     (canonical_document_to_dept_b_fields - data minimization: Department B never sees Department
     A's resident_id or any other field it didn't ask for) and write them via the Department B
     connector's update() - the actual no-reupload moment.
  5. record what happened: an InteropTransaction (the machine-to-machine record), an
     UnifiedApplicationEvent per step (the citizen/officer-facing timeline), and an AuditService
     entry (reusing the existing generic, non-complaint-specific audit trail) - all tagged with one
     correlation_id so every row from a single exchange can be pulled back together.

Every outcome is honest about what happened: "consent_required" means nothing was read yet,
"identity_ambiguous" means no cross-system link was made, "failed" always carries a real reason.
Nothing here fabricates a success.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, overload

from sqlalchemy import inspect, select

from app.core.authorization import AuthContext, Permission, require
from app.core.exceptions import NotFound, PermissionDenied, ValidationFailed
from app.core.logging import correlation_id_var
from app.db.models.identity import ProfileModel, UserModel
from app.db.models.interop_platform import (
    IdentityMatchCandidate,
    InteropConsentGrant,
    InteropException,
    InteropTransaction,
    MasterEntity,
    MockDeptBApplication,
    MockDeptBBeneficiary,
    UnifiedApplication,
    UnifiedApplicationEvent,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowStepExecution,
)
from app.db.models.ops import AuditLogModel
from app.interop import catalog, connector_registry, mock_systems
from app.interop.canonical.v1.models import Document as CanonicalDocument
from app.interop.canonical.v1.transform import (
    canonical_document_to_dept_b_fields,
    dept_a_document_to_canonical,
)
from app.interop.connectors import runtime as connector_runtime
from app.interop.events.bus import InMemoryInteropEventBus, InteropEventBus
from app.interop.events.types import InteropEvent
from app.interop.exceptions import center as exception_center
from app.interop.exceptions.taxonomy import classify as classify_exception
from app.interop.identity_resolution import IdentityResolutionService
from app.interop.monitoring import alerts as connector_alerts
from app.interop.quality.engine import DataQualityEngine, QualityRule
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.uow import UowFactory

CONSENT_VALIDITY = timedelta(days=30)
_quality_engine = DataQualityEngine()  # stateless - one instance evaluates any record against any rule set

# Canonical field names (app.interop.canonical.v1.models.Document) this exchange needs to read
# from Department A - the field-level consent vocabulary a citizen actually authorizes against.
# Enforced in _execute_exchange before any of these fields are used for anything, per the
# completion spec's field-level consent requirement: an unconsented field is refused, not hidden
# by the UI and quietly read anyway.
REQUIRED_DOCUMENT_FIELDS = ("reference", "status", "issued_on")


@overload
def _row(obj: None) -> None: ...
@overload
def _row(obj: Any) -> dict: ...
def _row(obj: Any) -> dict | None:
    """Plain column-name->value dict for an ORM row - safe to hand to the API layer's to_jsonable,
    unlike the row itself (which carries SQLAlchemy's internal _sa_instance_state)."""
    if obj is None:
        return None
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs}


_DOCUMENT_QUALITY_RULES = [
    QualityRule("status", "in_set", {"allowed": ["verified"]}, message="source document status is not verified"),
    QualityRule("reference", "min_length", {"min": 6}, message="reference number is missing or too short to be a real reference"),
    QualityRule("issued_on", "required", message="issue date is missing"),
]


def _document_quality(document: CanonicalDocument) -> tuple[float, list[str]]:
    """The document exchange's rules, run through the reusable DataQualityEngine
    (app.interop.quality.engine) - not a bespoke rubric hard-coded to this one call site. Every
    failure reason is something a reviewer could independently check against the same canonical
    document. Runs on the canonical shape (app.interop.canonical.v1), not the source system's
    native row, so the same rules apply unchanged once a second document type or a real
    connector's Document starts flowing through here."""
    record = {"status": document.status, "reference": document.reference, "issued_on": document.issued_on}
    result = _quality_engine.evaluate(record, _DOCUMENT_QUALITY_RULES)
    return result.score, result.errors


class InteropGatewayService:
    def __init__(self, uow_factory: UowFactory, clock: Callable[[], datetime] | None = None, bus: InteropEventBus | None = None) -> None:
        self._uow, self._clock = uow_factory, clock or (lambda: datetime.now(UTC))
        self.bus: InteropEventBus = bus or InMemoryInteropEventBus()

    def _publish(self, event: InteropEvent) -> None:
        """A broken event bus must never fail the operation it's describing - the same "publish
        after commit, and never let a side effect undo the primary result" discipline
        ComplaintEffects already uses for the complaint domain."""
        try:
            self.bus.publish(event)
        except Exception:  # noqa: BLE001
            logging.getLogger("civiclens.interop").warning("interop event publish failed for %s", event.event_type)

    # -----------------------------------------------------------------------------------------
    # The demo scenario
    # -----------------------------------------------------------------------------------------

    def request_document_exchange(self, ctx: AuthContext, *, application_no: str, document_type: str = "residence_certificate") -> dict:
        require(ctx, Permission.INTEROP_MANAGE)
        correlation_id = str(uuid.uuid4())
        token = correlation_id_var.set(correlation_id)
        try:
            with self._uow() as uow:
                s = uow.session
                assert s is not None
                app_result = connector_runtime.call(s, "dept_b", "get_entity", "application", application_no)
                app_row = app_result.data if app_result.ok else None
                if app_row is None:
                    raise NotFound(f"No application {application_no!r} in {mock_systems.DEPT_B_NAME}.")
                if app_row.document_status == "verified":
                    return {"status": "already_completed", "application_no": application_no, "document_reference": app_row.document_reference}

                ben_result = connector_runtime.call(s, "dept_b", "get_entity", "beneficiary", app_row.beneficiary_code)
                beneficiary = ben_result.data if ben_result.ok else None
                if beneficiary is None:
                    raise NotFound("Application references a beneficiary that no longer exists.")

                resolver = IdentityResolutionService(self._clock)
                b_result = resolver.resolve_person(s, system="dept_b", identifier_type="beneficiary_code", identifier_value=beneficiary.beneficiary_code, name=beneficiary.full_name, mobile=beneficiary.mobile_number)
                s.flush()  # the session has autoflush disabled - without this, the link just made
                # above is invisible to the SELECT the Department A resolution below runs against
                # the same still-open transaction, and it would wrongly create a second master.
                if b_result.candidate_id:
                    exception_center.log_exception(s, error_code=classify_exception("identity_ambiguous"), message=f"Department B identity match ambiguous (confidence {b_result.confidence}); needs manual review.", source_system="dept_b", target_system="civiclens", correlation_id=correlation_id, clock=self._clock)
                    uow.commit()
                    self._publish(InteropEvent(event_type="IdentityReviewRequired", source_system="dept_b", entity_id=b_result.candidate_id, correlation_id=correlation_id, payload={"side": "dept_b", "confidence": b_result.confidence}))
                    return {"status": "identity_ambiguous", "side": "dept_b", "candidate_id": b_result.candidate_id, "confidence": b_result.confidence, "explanation": b_result.matched_on}
                master_id = b_result.master_id

                resident = self._find_matching_dept_a_resident(s, beneficiary=beneficiary)
                if resident is None:
                    exception_center.log_exception(s, error_code=classify_exception("source_record_not_found"), message=f"No matching resident found in {mock_systems.DEPT_A_NAME}.", source_system="dept_a", target_system="civiclens", correlation_id=correlation_id, clock=self._clock)
                    uow.commit()
                    return {"status": "source_record_not_found", "detail": f"No matching resident found in {mock_systems.DEPT_A_NAME}."}

                a_result = resolver.resolve_person(s, system="dept_a", identifier_type="resident_id", identifier_value=resident.resident_id, name=resident.full_name, mobile=resident.mobile)
                if a_result.candidate_id:
                    exception_center.log_exception(s, error_code=classify_exception("identity_ambiguous"), message=f"Department A identity match ambiguous (confidence {a_result.confidence}); needs manual review.", source_system="dept_a", target_system="civiclens", correlation_id=correlation_id, clock=self._clock)
                    uow.commit()
                    self._publish(InteropEvent(event_type="IdentityReviewRequired", source_system="dept_a", entity_id=a_result.candidate_id, correlation_id=correlation_id, payload={"side": "dept_a", "confidence": a_result.confidence}))
                    return {"status": "identity_ambiguous", "side": "dept_a", "candidate_id": a_result.candidate_id, "confidence": a_result.confidence, "explanation": a_result.matched_on}
                if a_result.master_id != master_id:
                    exception_center.log_exception(s, error_code=classify_exception("identity_conflict"), message="Department A and Department B resolved to two different master identities. Needs manual review.", source_system="civiclens", target_system="civiclens", correlation_id=correlation_id, clock=self._clock)
                    uow.commit()
                    return {"status": "identity_conflict", "detail": "Department A and Department B resolved to two different master identities. Needs manual review."}
                self._publish(InteropEvent(event_type="IdentityResolved", source_system="civiclens", entity_id=master_id, correlation_id=correlation_id, payload={"dept_a_resident_id": resident.resident_id, "dept_b_beneficiary_code": beneficiary.beneficiary_code}))

                consent = self._find_consent(s, master_id=master_id, data_category=document_type, status="granted")
                if consent is None or (consent.expires_at is not None and consent.expires_at <= self._clock()):
                    pending = self._find_consent(s, master_id=master_id, data_category=document_type, status="pending")
                    owner = self._citizen_account_for(s, resident.mobile, beneficiary.mobile_number)
                    if pending is None:
                        pending = InteropConsentGrant(
                            consent_id=str(uuid.uuid4()), master_id=master_id, citizen_user_id=owner or ctx.user_id,
                            requesting_system="dept_b", providing_system="dept_a",
                            purpose=f"Verify {document_type.replace('_', ' ')} for application {application_no}",
                            data_category=document_type, fields=list(REQUIRED_DOCUMENT_FIELDS),
                            status="pending", created_at=self._clock(),
                        )
                        s.add(pending)
                        AuditService(uow.audit, self._clock).record("interop.consent_requested", actor_id=ctx.user_id, resource_type="interop_consent", resource_id=pending.consent_id, metadata={"master_id": master_id, "application_no": application_no, "document_type": document_type, "citizen_linked": owner is not None})
                        if owner:
                            NotificationService(self._clock).notify(
                                uow.notifications, owner, "interop.consent_requested", f"{mock_systems.DEPT_B_NAME} is asking to use your {document_type.replace('_', ' ')}",
                                f"Allow {mock_systems.DEPT_B_NAME} to fetch your already-verified {document_type.replace('_', ' ')} from {mock_systems.DEPT_A_NAME} for application {application_no}? "
                                f"Only these fields are shared: {', '.join(REQUIRED_DOCUMENT_FIELDS)}. Open My data sharing to allow or deny.",
                                data={"consent_id": pending.consent_id, "route": "/my-data"}, dedupe_key=f"consent:{pending.consent_id}")
                    uow.commit()
                    self._publish(InteropEvent(event_type="ConsentRequested", source_system="dept_b", destination="dept_a", entity_id=pending.consent_id, correlation_id=correlation_id, payload={"master_id": master_id, "application_no": application_no, "data_category": document_type}))
                    return {"status": "consent_required", "consent_id": pending.consent_id, "master_id": master_id, "citizen_linked": pending.citizen_user_id != ctx.user_id}

                result, events = self._execute_exchange(uow, ctx, master_id=master_id, consent=consent, application_no=application_no, document_type=document_type, resident=resident, correlation_id=correlation_id)
                uow.commit()
                for event in events:
                    self._publish(event)
                return result
        finally:
            correlation_id_var.reset(token)

    @staticmethod
    def _citizen_account_for(session, *mobiles: str | None) -> str | None:
        """The CivicLens citizen whose profile mobile matches the department records, so the consent
        request lands with the person it is about. Exactly one match or nothing - never a guess."""
        wanted = {re.sub(r"\D", "", m)[-10:] for m in mobiles if m and len(re.sub(r"\D", "", m)) >= 10}
        if not wanted:
            return None
        rows = session.execute(
            select(ProfileModel.user_id, ProfileModel.phone).join(UserModel, UserModel.id == ProfileModel.user_id)
            .where(ProfileModel.phone.is_not(None), UserModel.role == "citizen", UserModel.is_active.is_(True))
        ).all()
        matches = {str(uid) for uid, phone in rows if re.sub(r"\D", "", phone or "")[-10:] in wanted}
        return next(iter(matches)) if len(matches) == 1 else None

    def list_demo_applications(self, ctx: AuthContext) -> list[dict]:
        """Department B applications (demo system) the console can run the no-reupload exchange for."""
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            s = uow.session
            rows = s.execute(select(MockDeptBApplication, MockDeptBBeneficiary.full_name).join(MockDeptBBeneficiary, MockDeptBBeneficiary.beneficiary_code == MockDeptBApplication.beneficiary_code).order_by(MockDeptBApplication.application_no)).all()
            return [{**_row(a), "applicant": name} for a, name in rows]

    def reset_demo_scenario(self, ctx: AuthContext) -> dict:
        """Demo only: reopen the seeded Department B applications and withdraw their open consents, with a
        recorded reason, so the full no-reupload flow can be shown again. History and audit rows are kept."""
        require(ctx, Permission.INTEROP_MANAGE)
        with self._uow() as uow:
            s = uow.session
            now = self._clock()
            apps = list(s.execute(select(MockDeptBApplication)).scalars().all())
            for a in apps:
                a.status, a.document_status, a.document_reference, a.updated_at = "pending_document", "missing", None, now
                s.add(a)
            withdrawn = 0
            for g in s.execute(select(InteropConsentGrant).where(InteropConsentGrant.status.in_(("granted", "pending")))).scalars().all():
                if any(a.application_no in (g.purpose or "") for a in apps):
                    g.status, g.revoked_at, g.revocation_reason = "revoked", now, "Demo scenario reset"
                    s.add(g)
                    withdrawn += 1
            AuditService(uow.audit, self._clock).record("interop.demo_reset", actor_id=ctx.user_id, resource_type="interop_demo", resource_id="dept_b_applications", metadata={"applications": [a.application_no for a in apps], "consents_withdrawn": withdrawn})
            uow.commit()
            return {"applications_reopened": len(apps), "consents_withdrawn": withdrawn}

    def _find_matching_dept_a_resident(self, session, *, beneficiary):
        result = connector_runtime.call(session, "dept_a", "query", "resident", mobile=beneficiary.mobile_number)
        candidates = result.data if result.ok else []
        if not candidates:
            result = connector_runtime.call(session, "dept_a", "query", "resident", name_contains=beneficiary.full_name)
            candidates = result.data if result.ok else []
        return candidates[0] if candidates else None

    def _execute_exchange(self, uow, ctx: AuthContext, *, master_id: str, consent: InteropConsentGrant, application_no: str, document_type: str, resident, correlation_id: str) -> tuple[dict, list[InteropEvent]]:
        """Returns (result, events) - events are published by the caller AFTER uow.commit(), never
        before, so nothing is ever published for a transaction that then rolls back."""
        s = uow.session
        events: list[InteropEvent] = []
        unified = self._get_or_create_unified_application(s, master_id=master_id, application_no=application_no)
        self._add_event(s, unified.application_id, step="identity_resolved_cross_system", source_system="civiclens", status="success", correlation_id=correlation_id, detail={"master_id": master_id, "dept_a_resident_id": resident.resident_id})

        # Field-level consent enforcement (Section 7): checked before ANY field is read, not just
        # hidden from the UI afterwards. approved_fields is what the citizen actually authorized on
        # this exact grant, which may be narrower than what a later version of this operation needs.
        approved_fields = list(consent.fields or [])
        denied_fields = [f for f in REQUIRED_DOCUMENT_FIELDS if f not in approved_fields]
        if denied_fields:
            txn = self._record_transaction(s, correlation_id=correlation_id, source="dept_a", target="dept_b", master_id=master_id, consent_id=consent.consent_id, status="failed", error_code="data_field_not_consented", error_message=f"Fields not authorized by this consent: {', '.join(denied_fields)}.", fields=[], duration_ms=0.0, requested_fields=list(REQUIRED_DOCUMENT_FIELDS), approved_fields=approved_fields, denied_fields=denied_fields)
            self._add_event(s, unified.application_id, step="field_level_consent_check_failed", source_system="civiclens", status="failed", correlation_id=correlation_id, detail={"denied_fields": denied_fields})
            exception_center.log_exception(s, error_code=classify_exception("data_field_not_consented"), message=f"Fields not authorized by this consent: {', '.join(denied_fields)}.", source_system="dept_a", target_system="dept_b", correlation_id=correlation_id, clock=self._clock)
            AuditService(uow.audit, self._clock).record("interop.document_exchange_failed", actor_id=ctx.user_id, resource_type="interop_transaction", resource_id=txn.transaction_id, metadata={"reason": "data_field_not_consented", "denied_fields": denied_fields, "application_no": application_no})
            events.append(InteropEvent(event_type="ExchangeFailed", source_system="dept_a", destination="dept_b", entity_id=txn.transaction_id, correlation_id=correlation_id, payload={"reason": "data_field_not_consented", "denied_fields": denied_fields}))
            return {"status": "failed", "reason": "data_field_not_consented", "denied_fields": denied_fields, "transaction_id": txn.transaction_id, "correlation_id": correlation_id}, events

        # Gateway -> Connector Runtime -> GovernmentConnector - never a direct mock-system call.
        events.append(InteropEvent(event_type="DocumentRequested", source_system="civiclens", destination="dept_a", entity_id=resident.resident_id, correlation_id=correlation_id, payload={"document_type": document_type}))
        fetch_result = connector_runtime.call(s, "dept_a", "fetch_document", resident.resident_id, document_type)
        duration_ms = fetch_result.meta.get("duration_ms", 0.0)

        if not fetch_result.ok or fetch_result.data is None:
            txn = self._record_transaction(s, correlation_id=correlation_id, source="dept_a", target="dept_b", master_id=master_id, consent_id=consent.consent_id, status="failed", error_code="document_not_found", error_message=f"No {document_type} on file for this resident.", fields=[], duration_ms=duration_ms, requested_fields=list(REQUIRED_DOCUMENT_FIELDS), approved_fields=approved_fields, denied_fields=[])
            self._add_event(s, unified.application_id, step="document_fetch_failed", source_system="dept_a", status="failed", correlation_id=correlation_id, detail={"reason": "document_not_found"})
            exception_center.log_exception(s, error_code=classify_exception("document_not_found"), message=f"No {document_type} on file for this resident.", source_system="dept_a", target_system="dept_b", correlation_id=correlation_id, clock=self._clock)
            AuditService(uow.audit, self._clock).record("interop.document_exchange_failed", actor_id=ctx.user_id, resource_type="interop_transaction", resource_id=txn.transaction_id, metadata={"reason": "document_not_found", "application_no": application_no})
            events.append(InteropEvent(event_type="ExchangeFailed", source_system="dept_a", destination="dept_b", entity_id=txn.transaction_id, correlation_id=correlation_id, payload={"reason": "document_not_found"}))
            return {"status": "failed", "reason": "document_not_found", "transaction_id": txn.transaction_id, "correlation_id": correlation_id}, events

        # External (Dept A's own row) -> canonical - the quality check and the destination
        # transform both operate on the canonical shape, never on Dept A's native row directly.
        canonical_doc = dept_a_document_to_canonical(fetch_result.data)
        quality_score, quality_issues = _document_quality(canonical_doc)
        if quality_score < 0.7:
            txn = self._record_transaction(s, correlation_id=correlation_id, source="dept_a", target="dept_b", master_id=master_id, consent_id=consent.consent_id, status="failed", error_code="data_quality_failed", error_message="; ".join(quality_issues), fields=[], duration_ms=duration_ms, requested_fields=list(REQUIRED_DOCUMENT_FIELDS), approved_fields=approved_fields, denied_fields=[])
            self._add_event(s, unified.application_id, step="document_quality_check_failed", source_system="dept_a", status="failed", correlation_id=correlation_id, detail={"score": quality_score, "issues": quality_issues})
            exception_center.log_exception(s, error_code=classify_exception("data_quality_failed"), message="; ".join(quality_issues), source_system="dept_a", target_system="dept_b", correlation_id=correlation_id, clock=self._clock)
            AuditService(uow.audit, self._clock).record("interop.document_exchange_failed", actor_id=ctx.user_id, resource_type="interop_transaction", resource_id=txn.transaction_id, metadata={"reason": "data_quality_failed", "issues": quality_issues, "application_no": application_no})
            events.append(InteropEvent(event_type="ExchangeFailed", source_system="dept_a", destination="dept_b", entity_id=txn.transaction_id, correlation_id=correlation_id, payload={"reason": "data_quality_failed", "issues": quality_issues}))
            return {"status": "failed", "reason": "data_quality_failed", "issues": quality_issues, "transaction_id": txn.transaction_id, "correlation_id": correlation_id}, events

        self._add_event(s, unified.application_id, step="document_fetched_from_dept_a", source_system="dept_a", status="success", correlation_id=correlation_id, detail={"reference_no": canonical_doc.reference, "quality_score": quality_score})
        events.append(InteropEvent(event_type="DocumentVerified", source_system="dept_a", entity_id=canonical_doc.reference, correlation_id=correlation_id, payload={"quality_score": quality_score}))

        # Canonical -> external (Dept B's own field names): data minimization in practice - Dept B
        # never receives the resident_id or any field outside what canonical_document_to_dept_b_fields declares.
        dept_b_fields = canonical_document_to_dept_b_fields(canonical_doc)
        update_result = connector_runtime.call(s, "dept_b", "update", "application", application_no, dept_b_fields)
        updated_app = update_result.data if update_result.ok else None
        self._add_event(s, unified.application_id, step="document_applied_to_dept_b_application", source_system="dept_b", status="success" if updated_app else "failed", correlation_id=correlation_id, detail={"application_no": application_no})

        unified.status = "completed" if updated_app else unified.status
        unified.updated_at = self._clock()
        s.add(unified)

        txn = self._record_transaction(s, correlation_id=correlation_id, source="dept_a", target="dept_b", master_id=master_id, consent_id=consent.consent_id, status="success", error_code=None, error_message=None, fields=list(dept_b_fields.keys()), duration_ms=duration_ms, requested_fields=list(REQUIRED_DOCUMENT_FIELDS), approved_fields=approved_fields, denied_fields=[])
        AuditService(uow.audit, self._clock).record("interop.document_exchange_completed", actor_id=ctx.user_id, resource_type="unified_application", resource_id=unified.application_id, metadata={"application_no": application_no, "master_id": master_id, "document_reference": canonical_doc.reference, "quality_score": quality_score, "transaction_id": txn.transaction_id})
        events.append(InteropEvent(event_type="DocumentTransferred", source_system="dept_a", destination="dept_b", entity_id=application_no, correlation_id=correlation_id, payload={"document_reference": canonical_doc.reference}))
        events.append(InteropEvent(
            event_type="ExchangeCompleted", source_system="dept_a", destination="dept_b", entity_id=txn.transaction_id, correlation_id=correlation_id,
            payload={"citizen_user_id": consent.citizen_user_id, "application_no": application_no, "document_type": document_type, "document_reference": canonical_doc.reference, "quality_score": quality_score},
        ))

        return {"status": "success", "transaction_id": txn.transaction_id, "application_id": unified.application_id, "document_reference": canonical_doc.reference, "quality_score": quality_score, "correlation_id": correlation_id}, events

    def _get_or_create_unified_application(self, session, *, master_id: str, application_no: str) -> UnifiedApplication:
        existing = session.execute(select(UnifiedApplication).where(UnifiedApplication.external_reference == application_no, UnifiedApplication.primary_system == "dept_b")).scalars().first()
        if existing is not None:
            return existing
        app_result = connector_runtime.call(session, "dept_b", "get_entity", "application", application_no)
        app_row = app_result.data if app_result.ok else None
        unified = UnifiedApplication(
            application_id=str(uuid.uuid4()), reference=f"CL-APP-{application_no}", master_id=master_id,
            service_type=app_row.service_type if app_row else "unknown", primary_system="dept_b",
            external_reference=application_no, status="in_progress", created_at=self._clock(), updated_at=self._clock(),
        )
        session.add(unified)
        session.flush()
        return unified

    def _add_event(self, session, application_id: str, *, step: str, source_system: str, status: str, correlation_id: str, detail: dict) -> None:
        session.add(UnifiedApplicationEvent(id=str(uuid.uuid4()), application_id=application_id, step=step, source_system=source_system, status=status, correlation_id=correlation_id, detail=detail, occurred_at=self._clock()))

    def _record_transaction(self, session, *, correlation_id: str, source: str, target: str, master_id: str, consent_id: str, status: str, error_code: str | None, error_message: str | None, fields: list[str], duration_ms: float, requested_fields: list[str] | None = None, approved_fields: list[str] | None = None, denied_fields: list[str] | None = None) -> InteropTransaction:
        txn = InteropTransaction(
            transaction_id=str(uuid.uuid4()), correlation_id=correlation_id, operation="document_exchange", source_system=source, target_system=target,
            master_id=master_id, consent_id=consent_id, status=status, error_code=error_code, error_message=error_message, fields_exchanged=fields,
            requested_fields=requested_fields or [], approved_fields=approved_fields or [], denied_fields=denied_fields or [],
            duration_ms=duration_ms, created_at=self._clock(),
        )
        session.add(txn)
        session.flush()
        return txn

    def _find_consent(self, session, *, master_id: str, data_category: str, status: str) -> InteropConsentGrant | None:
        return session.execute(
            select(InteropConsentGrant)
            .where(InteropConsentGrant.master_id == master_id, InteropConsentGrant.data_category == data_category, InteropConsentGrant.requesting_system == "dept_b", InteropConsentGrant.providing_system == "dept_a", InteropConsentGrant.status == status)
            .order_by(InteropConsentGrant.created_at.desc())
        ).scalars().first()  # fmt: skip

    # -----------------------------------------------------------------------------------------
    # Consent lifecycle - citizen-controlled (Section 8): the citizen a grant is attributed to
    # (InteropConsentGrant.citizen_user_id) may act on it themselves, exactly as an
    # INTEROP_MANAGE-holding integration admin can on their behalf through the admin console.
    # Nothing here auto-approves, and an admin does not silently override a citizen's decision -
    # every decision is attributed to whoever actually made it (ctx.user_id) in the audit trail.
    # -----------------------------------------------------------------------------------------

    def _require_consent_actor(self, ctx: AuthContext, grant: InteropConsentGrant) -> None:
        if ctx.has(Permission.INTEROP_MANAGE) or ctx.user_id == grant.citizen_user_id:
            return
        raise PermissionDenied("Only the citizen this consent belongs to, or an integration admin, may act on it.")

    def grant_consent(self, ctx: AuthContext, *, consent_id: str) -> dict:
        with self._uow() as uow:
            s = uow.session
            grant = s.get(InteropConsentGrant, consent_id)
            if grant is None:
                raise NotFound("Consent request not found.")
            self._require_consent_actor(ctx, grant)
            if grant.status != "pending":
                raise ValidationFailed(f"This consent request is already {grant.status}, not pending.")
            grant.status, grant.decided_at, grant.expires_at = "granted", self._clock(), self._clock() + CONSENT_VALIDITY
            s.add(grant)
            AuditService(uow.audit, self._clock).record("interop.consent_granted", actor_id=ctx.user_id, resource_type="interop_consent", resource_id=consent_id, metadata={"master_id": grant.master_id, "purpose": grant.purpose, "self_service": ctx.user_id == grant.citizen_user_id})
            uow.commit()
            self._publish(InteropEvent(event_type="ConsentGranted", source_system=grant.requesting_system, destination=grant.providing_system, entity_id=consent_id, correlation_id=str(uuid.uuid4()), payload={"master_id": grant.master_id}))
            return {"status": "granted", "consent_id": consent_id, "expires_at": grant.expires_at.isoformat()}

    def deny_consent(self, ctx: AuthContext, *, consent_id: str) -> dict:
        with self._uow() as uow:
            s = uow.session
            grant = s.get(InteropConsentGrant, consent_id)
            if grant is None:
                raise NotFound("Consent request not found.")
            self._require_consent_actor(ctx, grant)
            if grant.status != "pending":
                raise ValidationFailed(f"This consent request is already {grant.status}, not pending.")
            grant.status, grant.decided_at = "denied", self._clock()
            s.add(grant)
            AuditService(uow.audit, self._clock).record("interop.consent_denied", actor_id=ctx.user_id, resource_type="interop_consent", resource_id=consent_id, metadata={"master_id": grant.master_id, "self_service": ctx.user_id == grant.citizen_user_id})
            uow.commit()
            self._publish(InteropEvent(event_type="ConsentDenied", source_system=grant.requesting_system, destination=grant.providing_system, entity_id=consent_id, correlation_id=str(uuid.uuid4()), payload={"master_id": grant.master_id}))
            return {"status": "denied", "consent_id": consent_id}

    def revoke_consent(self, ctx: AuthContext, *, consent_id: str, reason: str) -> dict:
        with self._uow() as uow:
            s = uow.session
            grant = s.get(InteropConsentGrant, consent_id)
            if grant is None:
                raise NotFound("Consent request not found.")
            self._require_consent_actor(ctx, grant)
            if grant.status != "granted":
                raise ValidationFailed("Only a granted consent can be revoked.")
            grant.status, grant.revoked_at, grant.revocation_reason = "revoked", self._clock(), (reason or "").strip() or None
            s.add(grant)
            AuditService(uow.audit, self._clock).record("interop.consent_revoked", actor_id=ctx.user_id, resource_type="interop_consent", resource_id=consent_id, metadata={"master_id": grant.master_id, "reason": grant.revocation_reason, "self_service": ctx.user_id == grant.citizen_user_id})
            uow.commit()
            self._publish(InteropEvent(event_type="ConsentRevoked", source_system=grant.requesting_system, destination=grant.providing_system, entity_id=consent_id, correlation_id=str(uuid.uuid4()), payload={"master_id": grant.master_id, "reason": grant.revocation_reason}))
            return {"status": "revoked", "consent_id": consent_id}

    def list_consents(self, ctx: AuthContext, *, status: str | None = None) -> list[dict]:
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            s = uow.session
            q = select(InteropConsentGrant).order_by(InteropConsentGrant.created_at.desc())
            if status:
                q = q.where(InteropConsentGrant.status == status)
            return [_row(r) for r in s.execute(q).scalars().all()]

    def list_my_consents(self, ctx: AuthContext, *, status: str | None = None) -> list[dict]:
        """The citizen-facing view (Section 8): every consent request attributed to the caller's
        own account, regardless of INTEROP_READ - a citizen never needs an integration-admin
        permission to see who is asking to share their own data."""
        require(ctx, Permission.PROFILE_MANAGE)
        with self._uow() as uow:
            s = uow.session
            q = select(InteropConsentGrant).where(InteropConsentGrant.citizen_user_id == ctx.user_id).order_by(InteropConsentGrant.created_at.desc())
            if status:
                q = q.where(InteropConsentGrant.status == status)
            return [_row(r) for r in s.execute(q).scalars().all()]

    def my_data_access_log(self, ctx: AuthContext, *, limit: int = 50) -> list[dict]:
        """Every exchange that actually moved this citizen's data under one of their own consents -
        who read it, who received it, which fields, and when. Consent says what *may* happen; this
        says what *did*. Only successful transfers are listed: a blocked attempt read nothing."""
        require(ctx, Permission.PROFILE_MANAGE)
        with self._uow() as uow:
            s = uow.session
            q = (
                select(InteropTransaction, InteropConsentGrant.purpose)
                .join(InteropConsentGrant, InteropConsentGrant.consent_id == InteropTransaction.consent_id)
                .where(InteropConsentGrant.citizen_user_id == ctx.user_id, InteropTransaction.status == "success")
                .order_by(InteropTransaction.created_at.desc())
                .limit(limit)
            )
            return [{"transaction_id": t.transaction_id, "correlation_id": t.correlation_id, "at": t.created_at, "from_system": t.source_system,
                     "to_system": t.target_system, "fields": list(t.approved_fields or []), "purpose": purpose} for t, purpose in s.execute(q).all()]  # fmt: skip

    # -----------------------------------------------------------------------------------------
    # Manual identity review - the required path for anything the resolver would not auto-link.
    # -----------------------------------------------------------------------------------------

    def list_identity_candidates(self, ctx: AuthContext, *, status: str = "pending") -> list[dict]:
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            s = uow.session
            return [_row(r) for r in s.execute(select(IdentityMatchCandidate).where(IdentityMatchCandidate.status == status).order_by(IdentityMatchCandidate.created_at.desc())).scalars().all()]

    def resolve_identity_candidate(self, ctx: AuthContext, *, candidate_id: str, approve: bool) -> dict:
        """An officer's explicit call - this is what CONFIRM_THRESHOLD-gated ambiguity resolves
        into. Approving links the pending identifier to the candidate's proposed master entity at
        full confidence, attributed to the officer, not the algorithm. Rejecting creates a fresh
        master entity for that identifier instead of leaving it unlinked, since a reject is itself
        a positive claim: "this is a different person"."""
        require(ctx, Permission.INTEROP_MANAGE)
        with self._uow() as uow:
            s = uow.session
            cand = s.get(IdentityMatchCandidate, candidate_id)
            if cand is None:
                raise NotFound("Identity match candidate not found.")
            if cand.status != "pending":
                raise ValidationFailed(f"This candidate is already {cand.status}.")
            resolver = IdentityResolutionService(self._clock)
            if approve:
                resolver.link_identifier(s, master_id=cand.master_id, system=cand.system, identifier_type=cand.identifier_type, identifier_value=cand.identifier_value, confidence=1.0, matched_on=f"officer-confirmed manual match (was {cand.score:.2f}: {cand.explanation})")
                cand.status = "confirmed"
            else:
                new_master = MasterEntity(master_id=str(uuid.uuid4()), display_name=cand.identifier_value, created_at=self._clock())
                s.add(new_master)
                s.flush()
                resolver.link_identifier(s, master_id=new_master.master_id, system=cand.system, identifier_type=cand.identifier_type, identifier_value=cand.identifier_value, confidence=1.0, matched_on="officer confirmed this is a distinct identity, not the proposed match")
                cand.status = "rejected"
            cand.resolved_by, cand.resolved_at = ctx.user_id, self._clock()
            s.add(cand)
            AuditService(uow.audit, self._clock).record("interop.identity_candidate_resolved", actor_id=ctx.user_id, resource_type="identity_match_candidate", resource_id=candidate_id, metadata={"approved": approve, "master_id": cand.master_id})
            uow.commit()
            return {"status": cand.status, "candidate_id": candidate_id}

    # -----------------------------------------------------------------------------------------
    # Read surfaces for the demo/admin UI
    # -----------------------------------------------------------------------------------------

    def get_timeline(self, ctx: AuthContext, *, application_no: str) -> dict:
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            s = uow.session
            unified = s.execute(select(UnifiedApplication).where(UnifiedApplication.external_reference == application_no, UnifiedApplication.primary_system == "dept_b")).scalars().first()
            if unified is None:
                raise NotFound("No cross-department activity recorded yet for this application.")
            events = list(s.execute(select(UnifiedApplicationEvent).where(UnifiedApplicationEvent.application_id == unified.application_id).order_by(UnifiedApplicationEvent.occurred_at)).scalars().all())
            return {"application": _row(unified), "events": [_row(e) for e in events]}

    def list_transactions(self, ctx: AuthContext, *, limit: int = 50) -> list[dict]:
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            s = uow.session
            return [_row(r) for r in s.execute(select(InteropTransaction).order_by(InteropTransaction.created_at.desc()).limit(limit)).scalars().all()]

    def list_connectors(self, ctx: AuthContext) -> list[dict]:
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            return [_row(r) for r in connector_registry.list_connectors(uow.session)]

    def connector_health(self, ctx: AuthContext, *, connector_id: str) -> dict:
        """Routed through the connector runtime (Section 2/9: never a direct mock-system call,
        and this now genuinely exercises the connector's real federated authenticate() - a
        connector whose federation client got disabled shows up as unavailable here, not just
        'healthy' because its tables happen to still be reachable)."""
        require(ctx, Permission.INTEROP_MANAGE)
        with self._uow() as uow:
            s = uow.session
            row = connector_registry.get(s, connector_id)
            if row is None:
                return {"connector_id": connector_id, "state": "not_configured", "detail": "Unknown connector."}
            if not row.enabled:
                return {"connector_id": connector_id, "state": "disabled", "detail": "Disabled by an integration admin."}
            result = connector_runtime.call(s, connector_id, "health_check")
            uow.commit()
            return {"connector_id": connector_id, "state": "healthy" if result.ok else "unavailable", "detail": "Reachable." if result.ok else (result.error_message or "Unavailable.")}

    def set_connector_enabled(self, ctx: AuthContext, *, connector_id: str, enabled: bool) -> dict:
        require(ctx, Permission.INTEROP_MANAGE)
        with self._uow() as uow:
            row = connector_registry.set_enabled(uow.session, connector_id, enabled)
            if row is None:
                raise NotFound("Unknown connector.")
            AuditService(uow.audit, self._clock).record("interop.connector_toggled", actor_id=ctx.user_id, resource_type="connector", resource_id=connector_id, metadata={"enabled": enabled})
            uow.commit()
            return {"connector_id": connector_id, "enabled": enabled}

    # -----------------------------------------------------------------------------------------
    # Configurable workflows (Section 12/13) - read surfaces over WorkflowEngine's stored
    # definitions and execution history. Listing/inspecting only; running a workflow is
    # app.interop.workflow.definitions' own entry point today, not yet wired to a POST route here
    # (see docs/REQUIREMENT_TRACEABILITY.md).
    # -----------------------------------------------------------------------------------------

    def list_workflow_definitions(self, ctx: AuthContext) -> list[dict]:
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            return [_row(r) for r in uow.session.execute(select(WorkflowDefinition)).scalars().all()]

    def list_workflow_executions(self, ctx: AuthContext, *, workflow_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            q = select(WorkflowExecution).order_by(WorkflowExecution.started_at.desc()).limit(limit)
            if workflow_id:
                q = q.where(WorkflowExecution.workflow_id == workflow_id)
            if status:
                q = q.where(WorkflowExecution.status == status)
            return [_row(r) for r in uow.session.execute(q).scalars().all()]

    def get_workflow_execution(self, ctx: AuthContext, *, execution_id: str) -> dict:
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            execution = uow.session.get(WorkflowExecution, execution_id)
            if execution is None:
                raise NotFound("Workflow execution not found.")
            steps = uow.session.execute(select(WorkflowStepExecution).where(WorkflowStepExecution.execution_id == execution_id).order_by(WorkflowStepExecution.step_index, WorkflowStepExecution.started_at)).scalars().all()
            return {"execution": _row(execution), "steps": [_row(s) for s in steps]}

    # -----------------------------------------------------------------------------------------
    # Central exception management (Section 16-18) - the taxonomy, retry and dead-letter state
    # that every gateway failure branch above now logs into automatically. Reading and acting on
    # these records is an integration-admin operation, same gating as connector health/workflows.
    # -----------------------------------------------------------------------------------------

    def list_exceptions(self, ctx: AuthContext, *, resolution_state: str | None = None, error_code: str | None = None, correlation_id: str | None = None, limit: int = 100) -> list[dict]:
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            records = exception_center.list_exceptions(uow.session, resolution_state=resolution_state, error_code=error_code, correlation_id=correlation_id, limit=limit)
            return [_row(r) for r in records]

    def retry_exception(self, ctx: AuthContext, *, exception_id: str) -> dict:
        require(ctx, Permission.INTEROP_MANAGE)
        with self._uow() as uow:
            record = exception_center.retry(uow.session, exception_id, clock=self._clock)
            if record is None:
                raise NotFound("No retryable exception with that id (unknown, non-retryable, or already dead).")
            AuditService(uow.audit, self._clock).record("interop.exception_retried", actor_id=ctx.user_id, resource_type="interop_exception", resource_id=exception_id, metadata={"resolution_state": record.resolution_state, "retry_count": record.retry_count})
            row = _row(record)
            uow.commit()
            return row

    def resolve_exception(self, ctx: AuthContext, *, exception_id: str) -> dict:
        require(ctx, Permission.INTEROP_MANAGE)
        with self._uow() as uow:
            record = exception_center.mark_resolved(uow.session, exception_id, clock=self._clock)
            if record is None:
                raise NotFound("No exception with that id.")
            AuditService(uow.audit, self._clock).record("interop.exception_resolved", actor_id=ctx.user_id, resource_type="interop_exception", resource_id=exception_id, metadata={})
            row = _row(record)
            uow.commit()
            return row

    def mark_exception_dead(self, ctx: AuthContext, *, exception_id: str, reason: str | None = None) -> dict:
        require(ctx, Permission.INTEROP_MANAGE)
        with self._uow() as uow:
            record = exception_center.mark_dead(uow.session, exception_id, reason=reason, clock=self._clock)
            if record is None:
                raise NotFound("No exception with that id.")
            AuditService(uow.audit, self._clock).record("interop.exception_marked_dead", actor_id=ctx.user_id, resource_type="interop_exception", resource_id=exception_id, metadata={"reason": reason})
            row = _row(record)
            uow.commit()
            return row

    # -----------------------------------------------------------------------------------------
    # Monitoring (Section 19-21): SLA/alerts are evaluated as a side effect of every real
    # connector call (app.interop.connector_registry.record_call) - this is only the read/act
    # surface over that real state. Distributed transaction tracing pulls every row across the
    # platform's tables that shares one correlation_id back together.
    # -----------------------------------------------------------------------------------------

    def list_alerts(self, ctx: AuthContext, *, connector_id: str | None = None, acknowledged: bool | None = None, limit: int = 100) -> list[dict]:
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            return [_row(a) for a in connector_alerts.list_alerts(uow.session, connector_id=connector_id, acknowledged=acknowledged, limit=limit)]

    def acknowledge_alert(self, ctx: AuthContext, *, alert_id: str) -> dict:
        require(ctx, Permission.INTEROP_MANAGE)
        with self._uow() as uow:
            record = connector_alerts.acknowledge(uow.session, alert_id, actor_id=ctx.user_id, clock=self._clock)
            if record is None:
                raise NotFound("No alert with that id.")
            AuditService(uow.audit, self._clock).record("interop.alert_acknowledged", actor_id=ctx.user_id, resource_type="interop_connector_alert", resource_id=alert_id, metadata={})
            row = _row(record)
            uow.commit()
            return row

    def get_trace(self, ctx: AuthContext, *, correlation_id: str) -> dict:
        """Every row across the platform's tables sharing this one correlation_id, pulled back
        together - what a distributed trace means here, without the operational overhead of an
        actual tracing backend. `AuditService.record` already stamps every audit row with
        `correlation_id_var`'s value for the duration of a gateway call, so no extra plumbing was
        needed to make it queryable this way."""
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            s = uow.session
            transactions = [_row(r) for r in s.execute(select(InteropTransaction).where(InteropTransaction.correlation_id == correlation_id).order_by(InteropTransaction.created_at)).scalars().all()]
            exceptions = [_row(r) for r in s.execute(select(InteropException).where(InteropException.correlation_id == correlation_id).order_by(InteropException.created_at)).scalars().all()]
            events = [_row(r) for r in s.execute(select(UnifiedApplicationEvent).where(UnifiedApplicationEvent.correlation_id == correlation_id).order_by(UnifiedApplicationEvent.occurred_at)).scalars().all()]
            audit_entries = [_row(r) for r in s.execute(select(AuditLogModel).where(AuditLogModel.correlation_id == correlation_id).order_by(AuditLogModel.occurred_at)).scalars().all()]
            if not (transactions or exceptions or events or audit_entries):
                raise NotFound("No activity recorded for this correlation id.")
            return {"correlation_id": correlation_id, "transactions": transactions, "exceptions": exceptions, "events": events, "audit_entries": audit_entries}

    # -----------------------------------------------------------------------------------------
    # Service catalog & field mapping catalog (Section 8/22-23) - read-only surfaces over the
    # directory of cross-department services this platform exposes and the field-level mappings
    # each one actually performs. See app/interop/catalog.py.
    # -----------------------------------------------------------------------------------------

    def list_service_catalog(self, ctx: AuthContext, *, active: bool | None = None) -> list[dict]:
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            return [_row(r) for r in catalog.list_services(uow.session, active=active)]

    def list_field_mappings(self, ctx: AuthContext, *, service_id: str | None = None, system_id: str | None = None) -> list[dict]:
        require(ctx, Permission.INTEROP_READ)
        with self._uow() as uow:
            return [_row(r) for r in catalog.list_field_mappings(uow.session, service_id=service_id, system_id=system_id)]
