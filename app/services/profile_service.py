"""Citizen/officer profile, onboarding, consent records, and server-side offline drafts."""

from __future__ import annotations

import builtins
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.core.authorization import AuthContext, Permission, require
from app.core.exceptions import NotFound, ValidationFailed
from app.services.audit_service import AuditService
from app.services.complaint_service import SUPPORTED_LANGUAGES, ComplaintInput, ComplaintService
from app.services.ports import ConsentRecord, DraftRecord, ProfileRecord
from app.services.uow import UowFactory

POLICY_VERSION = "2026-09"
CONSENT_PURPOSES = ("privacy_policy", "ai_processing", "data_sharing_government", "document_storage", "notifications_email")
_PHONE = re.compile(r"^\+?[0-9]{10,13}$")


class ProfileService:
    def __init__(self, uow_factory: UowFactory, clock: Callable[[], datetime] | None = None) -> None:
        self._uow, self._clock = uow_factory, clock or (lambda: datetime.now(UTC))

    def get(self, ctx: AuthContext) -> ProfileRecord:
        require(ctx, Permission.PROFILE_MANAGE)
        with self._uow() as uow:
            p = uow.profiles.get(ctx.user_id)
            if p is None:
                u = uow.users.get_by_id(ctx.user_id)
                p = ProfileRecord(ctx.user_id, u.full_name if u else "", updated_at=self._clock())
            return p

    def update(self, ctx: AuthContext, *, full_name: str | None = None, phone: str | None = None, city: str | None = None, ward: str | None = None,
               language: str | None = None, complete_onboarding: bool = False) -> ProfileRecord:  # fmt: skip
        require(ctx, Permission.PROFILE_MANAGE)
        errors: dict[str, str] = {}
        if language is not None and language not in SUPPORTED_LANGUAGES:
            errors["language"] = "Unsupported language."
        if phone and not _PHONE.match(phone.replace(" ", "")):
            errors["phone"] = "Enter a valid phone number."
        if full_name is not None and not 2 <= len(full_name.strip()) <= 120:
            errors["full_name"] = "Enter your full name."
        if errors:
            raise ValidationFailed("The profile has errors.", details=errors)
        with self._uow() as uow:
            # One lookup, not two: this previously called get_by_id twice - once for the guard and
            # again for the attribute - so creating a profile cost an extra query every time.
            user = uow.users.get_by_id(ctx.user_id)
            p = uow.profiles.get(ctx.user_id) or ProfileRecord(ctx.user_id, user.full_name if user else "")
            if full_name is not None:
                p.full_name = full_name.strip()
            if phone is not None:
                p.phone = phone.replace(" ", "") or None
            if city is not None:
                p.city = city.strip()[:100] or None
            if ward is not None:
                p.ward = ward.strip()[:40] or None
            if language is not None:
                p.language = language
            if complete_onboarding:
                p.onboarding_complete = True
            p.updated_at = self._clock()
            uow.profiles.save(p)
            AuditService(uow.audit, self._clock).record("profile.updated", actor_id=ctx.user_id, resource_type="profile", resource_id=ctx.user_id, metadata={"fields": [k for k, v in dict(full_name=full_name, phone=phone, city=city, ward=ward, language=language).items() if v is not None]})
            uow.commit()
        return p

    # ---------------------------------------------------------------- consent
    def set_consent(self, ctx: AuthContext, purpose: str, granted: bool) -> ConsentRecord:
        require(ctx, Permission.PROFILE_MANAGE)
        if purpose not in CONSENT_PURPOSES:
            raise ValidationFailed("Unknown consent purpose.", details={"allowed": list(CONSENT_PURPOSES)})
        rec = ConsentRecord(ctx.user_id, purpose, bool(granted), POLICY_VERSION, self._clock())
        with self._uow() as uow:
            uow.consent.add(rec)  # append-only history
            AuditService(uow.audit, self._clock).record("consent.changed", actor_id=ctx.user_id, resource_type="consent", resource_id=purpose, metadata={"granted": bool(granted), "policy_version": POLICY_VERSION})
            uow.commit()
        return rec

    def consents(self, ctx: AuthContext) -> dict[str, dict[str, Any]]:
        require(ctx, Permission.PROFILE_MANAGE)
        with self._uow() as uow:
            latest = uow.consent.latest_by_purpose(ctx.user_id)
        return {p: ({"granted": latest[p].granted, "at": latest[p].at, "policy_version": latest[p].policy_version} if p in latest else {"granted": False, "at": None, "policy_version": None}) for p in CONSENT_PURPOSES}

    def has_consent(self, user_id: str, purpose: str) -> bool:
        with self._uow() as uow:
            rec = uow.consent.latest_by_purpose(user_id).get(purpose)
        return bool(rec and rec.granted)


class DraftService:
    """Server-side draft/sync queue: the safe Python-native equivalent of the source app's offline queue.

    Drafts are saved on the server as the user types (so a dropped connection or reload loses
    nothing that reached the server). A ``client_request_id`` makes submission idempotent, so a
    retry after reconnect can never create a duplicate complaint. Content typed while the browser
    has NO connection to the server cannot be persisted by a server-rendered UI; the page keeps it
    in the live form and flags it unsynced (see ARCHITECTURE.md, "Offline behaviour").
    """

    def __init__(self, uow_factory: UowFactory, complaints: ComplaintService, clock: Callable[[], datetime] | None = None) -> None:
        self._uow, self._complaints, self._clock = uow_factory, complaints, clock or (lambda: datetime.now(UTC))

    def save(self, ctx: AuthContext, kind: str, payload: dict[str, Any], client_request_id: str) -> DraftRecord:
        require(ctx, Permission.COMPLAINT_CREATE)
        if kind != "complaint":
            raise ValidationFailed("Only complaint drafts are supported.")
        if not 8 <= len(client_request_id or "") <= 64:
            raise ValidationFailed("client_request_id must be 8-64 characters.")
        if len(str(payload)) > 20000:
            raise ValidationFailed("Draft is too large.")
        with self._uow() as uow:
            d = uow.drafts.get_by_client_request(ctx.user_id, client_request_id)
            if d and d.status == "synced":
                return d
            if d is None:
                d = DraftRecord(str(uuid.uuid4()), ctx.user_id, kind, client_request_id, payload)
            d.payload, d.updated_at = payload, self._clock()
            if d.status == "failed":
                d.status = "draft"
            uow.drafts.save(d)
            uow.commit()
        return d

    def mark_pending(self, ctx: AuthContext, draft_id: str) -> DraftRecord:
        with self._uow() as uow:
            d = self._own(uow, ctx, draft_id)
            if d.status != "synced":
                d.status = "pending_sync"
                uow.drafts.save(d)
            uow.commit()
        return d

    def _own(self, uow: Any, ctx: AuthContext, draft_id: str) -> DraftRecord:
        d = uow.drafts.get(draft_id)
        if d is None or d.user_id != ctx.user_id:
            raise NotFound("Draft not found.")
        return d

    def list(self, ctx: AuthContext) -> list[DraftRecord]:
        require(ctx, Permission.COMPLAINT_CREATE)
        with self._uow() as uow:
            return uow.drafts.list_for_user(ctx.user_id, "complaint")

    def sync(self, ctx: AuthContext, draft_id: str) -> DraftRecord:
        """Submit one draft. Idempotent: an already-synced draft returns unchanged."""
        with self._uow() as uow:
            d = self._own(uow, ctx, draft_id)
            if d.status == "synced":
                return d
            payload, crid = dict(d.payload), d.client_request_id
        try:
            # title/description are ComplaintInput's only required (non-Optional, no-default)
            # fields, so they are pulled out and validated explicitly rather than folded into the
            # **allowed unpack below: a draft saved before either was typed in would otherwise
            # reach ComplaintInput(**allowed) missing a required argument and crash with an
            # unhandled TypeError instead of the ValidationFailed this method already handles.
            title, description = str(payload.get("title") or "").strip(), str(payload.get("description") or "").strip()
            if not title or not description:
                raise ValidationFailed("A draft needs both a title and a description before it can be submitted.")
            allowed: dict[str, Any] = {k: payload[k] for k in ("language", "category", "complaint_type", "ward", "lat", "lng", "address", "city") if payload.get(k) not in (None, "")}
            result = self._complaints.create(ctx, ComplaintInput(title=title, description=description, client_request_id=crid, evidence_ids=list(payload.get("evidence_ids") or []), **allowed))
            status, error, ref = "synced", None, result.complaint.reference
        except ValidationFailed as exc:
            status, error, ref = "failed", exc.message + (f" {exc.details}" if exc.details else ""), None
        with self._uow() as uow:
            d = self._own(uow, ctx, draft_id)
            d.status, d.error, d.result_ref, d.attempts, d.updated_at = status, error, ref, d.attempts + 1, self._clock()
            uow.drafts.save(d)
            uow.commit()
        return d

    def sync_all(self, ctx: AuthContext) -> builtins.list[DraftRecord]:
        # `builtins.list`, not `list`: this class defines its own method named `list` above, and
        # with `from __future__ import annotations` mypy resolves the bare name in a later method's
        # annotation against the class's own namespace first, so it saw the method, not the type.
        # The `def list(...) -> list[...]` naming convention itself is deliberate and used the same
        # way across most services in this codebase, so it stays; only this one annotation needs
        # the qualified name.
        return [self.sync(ctx, d.id) for d in self.list(ctx) if d.status == "pending_sync"]

    def discard(self, ctx: AuthContext, draft_id: str) -> None:
        with self._uow() as uow:
            self._own(uow, ctx, draft_id)
            uow.drafts.delete(draft_id)
            uow.commit()
