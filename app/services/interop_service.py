"""Services backing the interoperability layer: Golden Record linking, the integration exception
queue, honest manual cross-portal tracking, and classification-correction capture.

See app/interop/ for the pure Common Data Model + adapters these are adjacent to.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.core.authorization import AuthContext, Permission, require
from app.core.exceptions import NotFound, ValidationFailed
from app.db.repositories.interop import hash_external_id
from app.services.audit_service import AuditService
from app.services.ports import (
    ClassificationCorrectionRecord,
    ExternalIdRecord,
    ExternalServiceLinkRecord,
    IntegrationExceptionRecord,
)
from app.services.uow import UowFactory

ID_TYPES = ("aadhaar_ref", "pan", "voter_id", "driving_license", "ration_card")


class MasterDataService:
    """Golden Record: link external government IDs to one CivicLens profile.

    Only a salted hash is ever persisted (see ``hash_external_id``); the raw value never reaches
    storage or the audit log. The database's own unique constraint on (id_type, id_hash) is the
    real entity-resolution guard - two different profiles can never hold the same real-world ID.
    """

    def __init__(self, uow_factory: UowFactory, secret: str, clock: Callable[[], datetime] | None = None) -> None:
        self._uow, self._secret, self._clock = uow_factory, secret, clock or (lambda: datetime.now(UTC))

    def link(self, ctx: AuthContext, id_type: str, raw_value: str) -> ExternalIdRecord:
        require(ctx, Permission.PROFILE_MANAGE)
        if id_type not in ID_TYPES:
            raise ValidationFailed("Unknown ID type.", details={"id_type": f"Must be one of {', '.join(ID_TYPES)}."})
        raw_value = (raw_value or "").strip()
        if len(raw_value) < 4:
            raise ValidationFailed("Enter the ID value.", details={"raw_value": "Too short to be a real ID."})
        digest = hash_external_id(id_type, raw_value, salt=self._secret)
        record = ExternalIdRecord(str(uuid.uuid4()), ctx.user_id, id_type, digest, raw_value[-4:], self._clock())
        with self._uow() as uow:
            added = uow.master_data.add(record)
            if not added:
                raise ValidationFailed("This ID is already linked to a CivicLens account.", details={"raw_value": "Already linked (possibly to a different profile) - this is the entity-resolution conflict guard working as intended."})
            AuditService(uow.audit, self._clock).record("master_data.linked", actor_id=ctx.user_id, resource_type="external_id", resource_id=record.id, metadata={"id_type": id_type, "last4": record.last4})
            uow.commit()
        return record

    def list_mine(self, ctx: AuthContext) -> list[ExternalIdRecord]:
        require(ctx, Permission.PROFILE_MANAGE)
        with self._uow() as uow:
            return uow.master_data.list_for_user(ctx.user_id)

    def unlink(self, ctx: AuthContext, record_id: str) -> None:
        require(ctx, Permission.PROFILE_MANAGE)
        with self._uow() as uow:
            if not uow.master_data.remove(record_id, ctx.user_id):
                raise NotFound("Linked ID not found.")
            AuditService(uow.audit, self._clock).record("master_data.unlinked", actor_id=ctx.user_id, resource_type="external_id", resource_id=record_id)
            uow.commit()


class ExceptionService:
    """Malformed inbound records get queued here instead of silently dropped."""

    def __init__(self, uow_factory: UowFactory, clock: Callable[[], datetime] | None = None) -> None:
        self._uow, self._clock = uow_factory, clock or (lambda: datetime.now(UTC))

    def log(self, *, source_system: str, reason: str, payload: dict) -> IntegrationExceptionRecord:  # type: ignore[type-arg]
        record = IntegrationExceptionRecord(str(uuid.uuid4()), source_system, reason, payload, self._clock())
        with self._uow() as uow:
            uow.exceptions.add(record)
            uow.commit()
        return record

    def list(self, ctx: AuthContext, *, status: str | None = None) -> list[IntegrationExceptionRecord]:
        require(ctx, Permission.ADMIN_INTEGRATIONS)
        with self._uow() as uow:
            return uow.exceptions.list(status=status)

    def counts(self, ctx: AuthContext) -> dict[str, int]:
        require(ctx, Permission.ADMIN_INTEGRATIONS)
        with self._uow() as uow:
            return uow.exceptions.counts_by_status()

    def resolve(self, ctx: AuthContext, exception_id: str, *, note: str, ignore: bool = False) -> None:
        require(ctx, Permission.ADMIN_INTEGRATIONS)
        with self._uow() as uow:
            rec = uow.exceptions.get(exception_id)
            if rec is None:
                raise NotFound("Exception not found.")
            rec.status = "ignored" if ignore else "resolved"
            rec.resolved_at, rec.resolved_by, rec.resolution_note = self._clock(), ctx.user_id, note.strip() or None
            uow.exceptions.update(rec)
            AuditService(uow.audit, self._clock).record("integration_exception.resolved", actor_id=ctx.user_id, resource_type="integration_exception", resource_id=exception_id, metadata={"status": rec.status})
            uow.commit()


class ExternalLinksService:
    """Honest manual tracking for a portal that requires the citizen's own login and exposes no
    public API to sync from (CPGRAMS and most state portals, today) - kept alongside CivicLens's
    own live-tracked filings rather than pretending to sync something that structurally can't."""

    def __init__(self, uow_factory: UowFactory, clock: Callable[[], datetime] | None = None) -> None:
        self._uow, self._clock = uow_factory, clock or (lambda: datetime.now(UTC))

    def add(self, ctx: AuthContext, *, platform: str, external_reference: str, title: str, status_note: str = "") -> ExternalServiceLinkRecord:
        require(ctx, Permission.PROFILE_MANAGE)
        platform, external_reference, title = platform.strip(), external_reference.strip(), title.strip()
        errors = {}
        if not platform:
            errors["platform"] = "Name the platform, e.g. CPGRAMS."
        if not external_reference:
            errors["external_reference"] = "Enter that platform's reference number."
        if not title:
            errors["title"] = "Give it a short title."
        if errors:
            raise ValidationFailed("Fill in the required fields.", details=errors)
        now = self._clock()
        record = ExternalServiceLinkRecord(str(uuid.uuid4()), ctx.user_id, platform, external_reference, title, now, now, status_note.strip())
        with self._uow() as uow:
            uow.external_links.add(record)
            AuditService(uow.audit, self._clock).record("external_link.added", actor_id=ctx.user_id, resource_type="external_service_link", resource_id=record.id, metadata={"platform": platform})
            uow.commit()
        return record

    def list_mine(self, ctx: AuthContext) -> list[ExternalServiceLinkRecord]:
        require(ctx, Permission.PROFILE_MANAGE)
        with self._uow() as uow:
            return uow.external_links.list_for_user(ctx.user_id)

    def update_status(self, ctx: AuthContext, record_id: str, status_note: str) -> None:
        require(ctx, Permission.PROFILE_MANAGE)
        with self._uow() as uow:
            existing = next((r for r in uow.external_links.list_for_user(ctx.user_id) if r.id == record_id), None)
            if existing is None:
                raise NotFound("Tracked reference not found.")
            existing.status_note, existing.updated_at = status_note.strip(), self._clock()
            uow.external_links.update(existing)
            uow.commit()

    def remove(self, ctx: AuthContext, record_id: str) -> None:
        require(ctx, Permission.PROFILE_MANAGE)
        with self._uow() as uow:
            if not uow.external_links.remove(record_id, ctx.user_id):
                raise NotFound("Tracked reference not found.")
            uow.commit()


class ClassificationCorrectionService:
    """Phase 1 of a transparent learning loop: a review surface over corrections captured by
    ``OfficerService.correct_category`` (which enforces department-scoped write access - a
    standalone service here could not). Every record traces back to one real correction, never a
    black-box weight update. Feeding these back to auto-bias live classification is a follow-up;
    today this is capture + an inspectable admin view, plus a same-text suggestion hint.
    """

    def __init__(self, uow_factory: UowFactory, clock: Callable[[], datetime] | None = None) -> None:
        self._uow, self._clock = uow_factory, clock or (lambda: datetime.now(UTC))

    def recent(self, ctx: AuthContext, limit: int = 100) -> list[ClassificationCorrectionRecord]:
        require(ctx, Permission.ADMIN_MONITORING)
        with self._uow() as uow:
            return uow.classification_corrections.list_recent(limit)

    def suggest(self, text: str) -> str | None:
        """Best-effort suggestion from past corrections for genuinely similar text - used only
        as a hint the caller may show, never applied automatically."""
        with self._uow() as uow:
            matches = uow.classification_corrections.find_similar(text, limit=1)
            return matches[0].corrected_category if matches else None
