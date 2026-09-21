"""Officer workflow. Department isolation is enforced in the *query* (department code is taken
from the authenticated context, never from a request) and again on every record access."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.core.authorization import (
    AuthContext, Permission, Role, can_access_complaint, require, require_complaint_access,
)
from app.core.exceptions import NotFound, PermissionDenied, ValidationFailed
from app.realtime.events import COMPLAINT_ASSIGNED, COMPLAINT_ESCALATED, COMPLAINT_STATUS_CHANGED
from app.services.complaint_common import ComplaintEffects, Outbox
from app.services.complaint_status import FINISHED, apply_transition, build_timeline, can_transition
from app.services.complaint_status import ComplaintStatus as S
from app.services.ports import ComplaintRecord
from app.services.sla_service import SlaCalculator, SlaSubject
from app.services.uow import UowFactory

MAX_ESCALATION_LEVEL = 3
_NOTIFY_KIND = {S.RESOLVED: "complaint.resolved"}


class OfficerService:
    def __init__(self, uow_factory: UowFactory, effects: ComplaintEffects) -> None:
        self._uow, self._fx = uow_factory, effects

    # ---------------------------------------------------------------- helpers
    def _department(self, ctx: AuthContext) -> str:
        if ctx.department_id is None:
            raise PermissionDenied("Your account is not assigned to a department.")
        return ctx.department_id

    def _load(self, uow: Any, ctx: AuthContext, complaint_id: str, *, write: bool) -> ComplaintRecord:
        c = uow.complaints.get(complaint_id)
        if c is None or not can_access_complaint(ctx, owner_id=c.citizen_id, department_id=c.department_code, write=write):
            raise NotFound("Complaint not found.")  # do not reveal existence across departments
        return c

    def _transition(self, uow: Any, out: Outbox, ctx: AuthContext, c: ComplaintRecord, target: S, remarks: str | None, *, kind: str = "status_change", details: dict[str, Any] | None = None) -> None:
        prev = c.status
        ev = apply_transition(c.id, prev, target, actor_id=ctx.user_id, actor_label=uow.officers.user_label(ctx.user_id), remarks=remarks, at=self._fx.clock())
        self._fx.event(uow, c, kind, ctx, from_status=prev, to_status=target, remarks=ev.remarks, details=details)
        c.status, c.updated_at = target, ev.at
        if target is S.RESOLVED:
            c.resolved_at = ev.at
        elif prev is S.RESOLVED:
            c.resolved_at = None
        uow.complaints.update(c)
        self._fx.run_workflow(uow, c, "complaint.status_changed", out)
        note = _NOTIFY_KIND.get(target, "complaint.status_changed")
        self._fx.notify(uow, out, c.citizen_id, note, "Complaint update", f"{c.reference} is now {str(target).replace('_', ' ')}.", c, dedupe_key=f"status:{c.id}:{target}:{int(ev.at.timestamp())}")
        out.events.append(self._fx.complaint_event(COMPLAINT_STATUS_CHANGED, c, {"from": str(prev), "to": str(target)}, {"remarks": ev.remarks}))
        audit = self._fx.audit(uow)
        audit.record("complaint.status_changed", actor_id=ctx.user_id, resource_type="complaint", resource_id=c.id, metadata={"from": str(prev), "to": str(target), "reference": c.reference})
        if kind != "status_change":  # the specific sensitive action (field visit, work order, assignment, routing) is audited under its own name too
            audit.record(f"complaint.{kind}", actor_id=ctx.user_id, resource_type="complaint", resource_id=c.id, metadata={k: v for k, v in (details or {}).items() if k != "notes"})

    # ---------------------------------------------------------------- reads
    def queue(self, ctx: AuthContext, *, mine_only: bool = False, statuses: list[S] | None = None, limit: int = 50, offset: int = 0) -> list[ComplaintRecord]:
        require(ctx, Permission.COMPLAINT_READ_DEPARTMENT)
        dept = self._department(ctx)
        with self._uow() as uow:
            return uow.complaints.list_for_department(dept, statuses=statuses, officer_id=ctx.user_id if mine_only else None, limit=limit, offset=offset)

    def detail(self, ctx: AuthContext, complaint_id: str) -> dict[str, Any]:
        require(ctx, Permission.COMPLAINT_READ_DEPARTMENT)
        with self._uow() as uow:
            c = self._load(uow, ctx, complaint_id, write=False)
            require_complaint_access(ctx, owner_id=c.citizen_id, department_id=c.department_code)
            events = uow.complaints.list_events(c.id)
            evidence = uow.complaints.list_evidence(c.id)
            sla = SlaCalculator(list(uow.config.sla_policies())).status(_subject(c), self._fx.clock())
            self._fx.audit(uow).record("complaint.viewed", actor_id=ctx.user_id, resource_type="complaint", resource_id=c.id, metadata={"role": str(ctx.role)})
            uow.commit()
        return {"complaint": c, "timeline": build_timeline(c.status, events), "events": events, "evidence": evidence, "sla": sla, "feedback": None}

    # ---------------------------------------------------------------- workflow
    def update_status(self, ctx: AuthContext, complaint_id: str, target: S, remarks: str | None = None) -> ComplaintRecord:
        require(ctx, Permission.COMPLAINT_UPDATE_STATUS)
        out = Outbox()
        with self._uow() as uow:
            c = self._load(uow, ctx, complaint_id, write=True)
            self._transition(uow, out, ctx, c, target, remarks)
            uow.commit()
        self._fx.flush(out)
        return c

    def resolve(self, ctx: AuthContext, complaint_id: str, resolution_notes: str) -> ComplaintRecord:
        return self.update_status(ctx, complaint_id, S.RESOLVED, resolution_notes)

    def assign(self, ctx: AuthContext, complaint_id: str, officer_id: str) -> ComplaintRecord:
        """Assign/reassign within the complaint's own department."""
        require(ctx, Permission.COMPLAINT_ASSIGN)
        out = Outbox()
        with self._uow() as uow:
            c = self._load(uow, ctx, complaint_id, write=True)
            if c.department_code is None or officer_id not in uow.officers.officer_ids_for_department(c.department_code):
                raise ValidationFailed("The officer does not belong to this complaint's department.")
            if c.status in FINISHED:
                raise ValidationFailed("A finished complaint cannot be reassigned.")
            previous, c.assigned_officer_id = c.assigned_officer_id, officer_id
            if c.status is S.AI_ROUTED:
                self._transition(uow, out, ctx, c, S.ASSIGNED, None, kind="assigned", details={"officer_id": officer_id})
            else:
                self._fx.event(uow, c, "assigned", ctx, details={"officer_id": officer_id, "previous_officer_id": previous})
                uow.complaints.update(c)
                self._fx.audit(uow).record("complaint.reassigned", actor_id=ctx.user_id, resource_type="complaint", resource_id=c.id, metadata={"from": previous, "to": officer_id})
            self._fx.notify(uow, out, officer_id, "complaint.assigned", "Complaint assigned to you", f"{c.reference}: {c.title}", c, dedupe_key=f"assigned:{c.id}:{officer_id}")
            out.events.append(self._fx.complaint_event(COMPLAINT_ASSIGNED, c, internal={"officer_id": officer_id, "previous": previous}))
            uow.commit()
        self._fx.flush(out)
        return c

    def triage(self, ctx: AuthContext, complaint_id: str, department_code: str) -> ComplaintRecord:
        """Admin manual routing of a complaint the rules/AI could not route."""
        require(ctx, Permission.COMPLAINT_ASSIGN)
        if ctx.role not in (Role.ADMIN, Role.SUPER_ADMIN):
            raise PermissionDenied("Only administrators can triage unrouted complaints.")
        if ctx.role is Role.ADMIN and ctx.department_id not in (None, department_code):
            raise PermissionDenied("You cannot route outside your department.")
        out = Outbox()
        with self._uow() as uow:
            c = uow.complaints.get(complaint_id)
            if c is None:
                raise NotFound("Complaint not found.")
            if c.department_code is not None or c.status is not S.SUBMITTED:
                raise ValidationFailed("Only unrouted, newly submitted complaints can be triaged.")
            if department_code not in {d.code for d in uow.config.departments() if d.active}:
                raise ValidationFailed("Unknown department.")
            c.department_code, c.routing = department_code, {**c.routing, "source": "manual", "manual_triage": False, "explanation": f"Routed manually by administrator to {department_code}."}
            self._transition(uow, out, ctx, c, S.AI_ROUTED, None, kind="routed", details={"department": department_code, "source": "manual"})
            due = SlaCalculator(list(uow.config.sla_policies())).due_at(c.created_at, c.priority, department_code)
            c.sla_due_at = due
            uow.complaints.update(c)
            uow.commit()
        self._fx.flush(out)
        return c

    def _typed_event(self, ctx: AuthContext, complaint_id: str, perm: Permission, kind: str, details: dict[str, Any], remarks: str | None, *, move_to: S | None = None, internal: bool = False) -> ComplaintRecord:
        require(ctx, perm)
        out = Outbox()
        with self._uow() as uow:
            c = self._load(uow, ctx, complaint_id, write=True)
            if c.status in FINISHED:
                raise ValidationFailed("This complaint is already finished.")
            if move_to is not None and c.status is not move_to and can_transition(c.status, move_to):
                self._transition(uow, out, ctx, c, move_to, remarks, kind=kind, details=details)
            else:
                self._fx.event(uow, c, kind, ctx, remarks=remarks, details=details, internal=internal)
                c.updated_at = self._fx.clock()
                uow.complaints.update(c)
                self._fx.audit(uow).record(f"complaint.{kind}", actor_id=ctx.user_id, resource_type="complaint", resource_id=c.id, metadata={k: v for k, v in details.items() if k != "notes"})
            uow.commit()
        self._fx.flush(out)
        return c

    def remark(self, ctx: AuthContext, cid: str, text: str, *, internal: bool = True) -> ComplaintRecord:
        if not (text or "").strip():
            raise ValidationFailed("Enter a remark.", details={"field": "remarks"})
        return self._typed_event(ctx, cid, Permission.COMPLAINT_REMARK, "remark", {}, text, internal=internal)

    def correct_category(self, ctx: AuthContext, cid: str, corrected_category: str) -> ComplaintRecord:
        """Phase 1 of a transparent learning loop: capture the correction (never a silent
        black-box re-weight), then apply it for real. Goes through the same department-scoped
        ``_load`` as every other write, so an officer can only correct complaints in their own
        department - a bare classification-corrections service could not enforce that."""
        from app.services.classification_service import CATEGORIES
        from app.services.ports import ClassificationCorrectionRecord

        require(ctx, Permission.COMPLAINT_REMARK)
        if corrected_category not in CATEGORIES:
            raise ValidationFailed("Unknown category.", details={"category": f"Must be one of {', '.join(CATEGORIES)}."})
        with self._uow() as uow:
            c = self._load(uow, ctx, cid, write=True)
            if c.category == corrected_category:
                return c
            record = ClassificationCorrectionRecord(str(uuid.uuid4()), c.id, f"{c.title}. {c.description}"[:2000], c.category, corrected_category, ctx.user_id, self._fx.clock())
            uow.classification_corrections.add(record)
            previous = c.category
            c.category, c.updated_at = corrected_category, self._fx.clock()
            uow.complaints.update(c)
            self._fx.event(uow, c, "category_corrected", ctx, details={"from": previous, "to": corrected_category}, internal=True)
            self._fx.audit(uow).record("classification.corrected", actor_id=ctx.user_id, resource_type="complaint", resource_id=c.id, metadata={"from": previous, "to": corrected_category})
            uow.commit()
        return c

    def field_visit(self, ctx: AuthContext, cid: str, scheduled_for: datetime, notes: str | None = None) -> ComplaintRecord:
        return self._typed_event(ctx, cid, Permission.COMPLAINT_FIELD_ACTION, "field_visit", {"scheduled_for": scheduled_for.isoformat()}, notes, move_to=S.INSPECTION_SCHEDULED)

    def inspection(self, ctx: AuthContext, cid: str, findings: str, notes: str | None = None) -> ComplaintRecord:
        if not (findings or "").strip():
            raise ValidationFailed("Record the inspection findings.", details={"field": "findings"})
        return self._typed_event(ctx, cid, Permission.COMPLAINT_FIELD_ACTION, "inspection", {"findings": findings.strip()[:2000]}, notes)

    def work_order(self, ctx: AuthContext, cid: str, order_ref: str, description: str, team: str | None = None) -> ComplaintRecord:
        if not (order_ref or "").strip() or not (description or "").strip():
            raise ValidationFailed("Work order reference and description are required.")
        return self._typed_event(ctx, cid, Permission.COMPLAINT_FIELD_ACTION, "work_order", {"order_ref": order_ref.strip()[:60], "team": team}, description, move_to=S.IN_PROGRESS)

    def coordination_note(self, ctx: AuthContext, cid: str, with_team: str, note: str) -> ComplaintRecord:
        if not (note or "").strip():
            raise ValidationFailed("Enter a note.", details={"field": "note"})
        return self._typed_event(ctx, cid, Permission.COMPLAINT_FIELD_ACTION, "coordination", {"with": with_team[:80]}, note, internal=True)

    def progress(self, ctx: AuthContext, cid: str, percent: int, notes: str | None = None) -> ComplaintRecord:
        if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
            raise ValidationFailed("Progress must be 0-100.", details={"field": "percent"})
        return self._typed_event(ctx, cid, Permission.COMPLAINT_FIELD_ACTION, "progress", {"percent": percent}, notes, move_to=S.IN_PROGRESS)

    def escalate(self, ctx: AuthContext, complaint_id: str, reason: str) -> ComplaintRecord:
        require(ctx, Permission.COMPLAINT_UPDATE_STATUS)
        if not (reason or "").strip():
            raise ValidationFailed("Give a reason for escalation.", details={"field": "reason"})
        out = Outbox()
        with self._uow() as uow:
            c = self._load(uow, ctx, complaint_id, write=True)
            if c.status in FINISHED:
                raise ValidationFailed("A finished complaint cannot be escalated.")
            if c.escalation_level >= MAX_ESCALATION_LEVEL:
                raise ValidationFailed("Already at the highest escalation level.")
            frm = c.escalation_level
            c.escalation_level, c.escalated_at, c.updated_at = frm + 1, self._fx.clock(), self._fx.clock()
            uow.complaints.update(c)
            self._fx.event(uow, c, "escalated", ctx, remarks=reason, details={"from_level": frm, "to_level": c.escalation_level, "manual": True})
            for admin_id in uow.officers.admin_ids():
                self._fx.notify(uow, out, admin_id, "complaint.escalated", "Complaint escalated", f"{c.reference} escalated to level {c.escalation_level}", c, dedupe_key=f"esc:{c.id}:{c.escalation_level}:{admin_id}")
            out.events.append(self._fx.complaint_event(COMPLAINT_ESCALATED, c, {"level": c.escalation_level}, {"reason": reason}))
            self._fx.audit(uow).record("complaint.escalated", actor_id=ctx.user_id, resource_type="complaint", resource_id=c.id, metadata={"level": c.escalation_level, "manual": True})
            uow.commit()
        self._fx.flush(out)
        return c


def _subject(c: ComplaintRecord) -> SlaSubject:
    return SlaSubject(c.id, c.priority, c.department_code, c.status, c.created_at, c.sla_due_at, c.escalation_level, c.escalated_at)
