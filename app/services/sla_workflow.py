"""Scheduled SLA scan: at-risk warnings and overdue escalation, without any UI involved."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.realtime.events import COMPLAINT_ESCALATED
from app.services.complaint_common import ComplaintEffects, Outbox
from app.services.officer_service import _subject
from app.services.sla_service import SlaCalculator, SlaScanner
from app.services.uow import UowFactory


class SlaWorkflowService:
    def __init__(self, uow_factory: UowFactory, effects: ComplaintEffects) -> None:
        self._uow, self._fx = uow_factory, effects

    def scan(self, now: datetime) -> dict[str, Any]:
        out = Outbox()
        escalated = at_risk_notified = 0
        with self._uow() as uow:
            calc = SlaCalculator(list(uow.config.sla_policies()))
            open_complaints = uow.complaints.list_open()
            by_id = {c.id: c for c in open_complaints}
            report = SlaScanner(calc).scan([_subject(c) for c in open_complaints], now)
            for cid in report.at_risk:
                c = by_id[cid]
                if c.assigned_officer_id:
                    before = len(out.events)
                    self._fx.notify(uow, out, c.assigned_officer_id, "sla.at_risk", "SLA at risk", f"{c.reference} is close to its SLA deadline.", c, dedupe_key=f"sla_at_risk:{c.id}")
                    at_risk_notified += len(out.events) - before
            for act in report.actions:
                c = by_id[act.complaint_id]
                c.escalation_level, c.escalated_at, c.updated_at = act.to_level, now, now
                uow.complaints.update(c)
                self._fx.event(uow, c, "escalated", None, remarks=act.reason, details={"from_level": act.from_level, "to_level": act.to_level, "manual": False}, actor_label="SLA monitor")
                recipients = {*uow.officers.admin_ids(), *([c.assigned_officer_id] if c.assigned_officer_id else [])}
                for uid in sorted(recipients):
                    self._fx.notify(uow, out, uid, "complaint.escalated", "SLA breached: escalated", f"{c.reference} escalated to level {act.to_level}", c, dedupe_key=f"esc:{c.id}:{act.to_level}:{uid}")
                out.events.append(self._fx.complaint_event(COMPLAINT_ESCALATED, c, {"level": act.to_level}, {"reason": act.reason}))
                self._fx.audit(uow).record("complaint.escalated", actor_id=None, resource_type="complaint", resource_id=c.id, metadata={"level": act.to_level, "manual": False})
                escalated += 1
            uow.commit()
        self._fx.flush(out)
        return {"scanned": len(open_complaints), "at_risk": len(report.at_risk), "breached": len(report.breached), "escalated": escalated, "at_risk_notified": at_risk_notified}
