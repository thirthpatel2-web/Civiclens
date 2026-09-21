"""Investigation mode: an authorised, audited case file around a complaint or an anomaly."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.authorization import AuthContext, Permission, Role, can_access_complaint, require
from app.core.exceptions import NotFound, ValidationFailed
from app.services.audit_service import AuditService
from app.services.complaint_status import build_timeline
from app.services.location_service import haversine_m
from app.services.ports import InvestigationRecord
from app.services.uow import UowFactory

NEARBY_RADIUS_M = 500.0
LOOKBACK = timedelta(days=30)
RagLookup = Callable[[AuthContext, str], dict[str, Any]]
LegalLookup = Callable[[str], dict[str, Any]]


class InvestigationService:
    def __init__(self, uow_factory: UowFactory, clock: Callable[[], datetime] | None = None, rag_lookup: RagLookup | None = None, legal_lookup: LegalLookup | None = None) -> None:
        self._uow, self._clock, self._rag, self._legal = uow_factory, clock or (lambda: datetime.now(UTC)), rag_lookup, legal_lookup

    def _audit(self, uow: Any) -> AuditService:
        return AuditService(uow.audit, self._clock)

    def _complaint(self, uow: Any, ctx: AuthContext, cid: str):  # type: ignore[no-untyped-def]
        c = uow.complaints.get(cid)
        if c is None or not can_access_complaint(ctx, owner_id=c.citizen_id, department_id=c.department_code):
            raise NotFound("Complaint not found.")
        return c

    def _visible(self, ctx: AuthContext, inv: InvestigationRecord) -> bool:
        return ctx.role is Role.SUPER_ADMIN or ctx.department_id is None and ctx.role is Role.ADMIN or (ctx.department_id is not None and inv.department_code == ctx.department_id)

    def open(self, ctx: AuthContext, subject_type: str, subject_id: str) -> InvestigationRecord:
        require(ctx, Permission.INVESTIGATION_RUN)
        if subject_type not in ("complaint", "anomaly"):
            raise ValidationFailed("Subject must be a complaint or an anomaly.")
        with self._uow() as uow:
            if subject_type == "complaint":
                dept = self._complaint(uow, ctx, subject_id).department_code
            else:
                a = uow.anomalies.get(subject_id)
                if a is None or (ctx.department_id is not None and a.department_code != ctx.department_id):
                    raise NotFound("Anomaly not found.")
                dept = a.department_code
            inv = InvestigationRecord(str(uuid.uuid4()), subject_type, subject_id, ctx.user_id, dept, created_at=self._clock())
            uow.investigations.add(inv)
            self._audit(uow).record("investigation.opened", actor_id=ctx.user_id, resource_type=subject_type, resource_id=subject_id, metadata={"investigation_id": inv.id})
            uow.commit()
        return inv

    def _get(self, uow: Any, ctx: AuthContext, inv_id: str) -> InvestigationRecord:
        inv = uow.investigations.get(inv_id)
        if inv is None or not self._visible(ctx, inv):
            raise NotFound("Investigation not found.")
        return inv

    def add_note(self, ctx: AuthContext, inv_id: str, text: str) -> InvestigationRecord:
        require(ctx, Permission.INVESTIGATION_RUN)
        if not (text or "").strip():
            raise ValidationFailed("Enter a note.", details={"field": "note"})
        with self._uow() as uow:
            inv = self._get(uow, ctx, inv_id)
            if inv.status != "open":
                raise ValidationFailed("This investigation is closed.")
            inv.notes.append({"by": ctx.user_id, "at": self._clock().isoformat(), "text": text.strip()[:4000]})
            uow.investigations.update(inv)
            self._audit(uow).record("investigation.note_added", actor_id=ctx.user_id, resource_type="investigation", resource_id=inv_id)
            uow.commit()
        return inv

    def close(self, ctx: AuthContext, inv_id: str) -> InvestigationRecord:
        require(ctx, Permission.INVESTIGATION_RUN)
        with self._uow() as uow:
            inv = self._get(uow, ctx, inv_id)
            inv.status, inv.closed_at = "closed", self._clock()
            uow.investigations.update(inv)
            self._audit(uow).record("investigation.closed", actor_id=ctx.user_id, resource_type="investigation", resource_id=inv_id)
            uow.commit()
        return inv

    def list(self, ctx: AuthContext) -> list[InvestigationRecord]:
        require(ctx, Permission.INVESTIGATION_RUN)
        with self._uow() as uow:
            return [i for i in uow.investigations.list(department_code=ctx.department_id) if self._visible(ctx, i)]

    def report(self, ctx: AuthContext, inv_id: str) -> dict[str, Any]:
        """Assemble everything known about the subject. Each source is labelled; nothing is inferred."""
        require(ctx, Permission.INVESTIGATION_RUN)
        now = self._clock()
        with self._uow() as uow:
            inv = self._get(uow, ctx, inv_id)
            self._audit(uow).record("investigation.report_viewed", actor_id=ctx.user_id, resource_type="investigation", resource_id=inv_id)
            out: dict[str, Any] = {"investigation": inv, "generated_at": now}
            if inv.subject_type == "anomaly":
                out["anomaly"] = uow.anomalies.get(inv.subject_id)
                out["related_complaints"] = [r for r in uow.complaints.rows(department_code=inv.department_code, since=now - LOOKBACK)][:50]
                uow.commit()
                return out
            c = self._complaint(uow, ctx, inv.subject_id)
            events = uow.complaints.list_events(c.id)
            scope_rows = uow.complaints.rows(department_code=c.department_code, since=now - LOOKBACK) if c.department_code else []
            nearby = [r for r in scope_rows if r.id != c.id and r.category == c.category and (d := haversine_m(c.lat, c.lng, r.lat, r.lng)) is not None and d <= NEARBY_RADIUS_M]
            cluster = [r for r in scope_rows if r.id != c.id and c.ward and r.ward == c.ward and r.category == c.category]
            out.update({
                "complaint": c, "timeline": build_timeline(c.status, events), "events": events, "evidence": uow.complaints.list_evidence(c.id),
                "location": {"lat": c.lat, "lng": c.lng, "address": c.address, "ward": c.ward, "city": c.city},
                "duplicates": c.duplicates, "nearby_same_category": nearby, "ward_category_cluster": cluster,
                "anomalies": [a for a in uow.anomalies.list(status="open", department_code=c.department_code, limit=50) if c.category in (a.details or {}).get("categories", [c.category]) or c.ward and c.ward in a.subject],
                "audit_trail": uow.audit.query(resource_id=c.id, limit=100),
            })  # fmt: skip
            uow.commit()
        text = f"{c.title}. {c.description}"
        out["rag_findings"] = self._rag(ctx, text) if self._rag else {"status": "not_configured", "detail": "No document assistant is wired to investigations."}
        out["legal_sources"] = self._legal(text) if self._legal else {"status": "not_configured"}
        return out
