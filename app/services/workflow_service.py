"""Workflow rules: configurable automation on complaint events (distinct from routing rules and SLA policies).

    rule = trigger + conditions -> action           (evaluated by a pure engine, executed once per rule per complaint)

Triggers:   complaint.created | complaint.status_changed | scheduled (periodic sweep for age-based rules)
Conditions: categories, priorities(min), departments, wards, statuses, languages, unrouted, age_hours_min
Actions:    notify_admins | escalate | auto_close | assign_least_loaded | add_internal_note
Every execution writes a complaint event + audit record, and is idempotent (unique rule/complaint).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.core.exceptions import ValidationFailed
from app.realtime.events import COMPLAINT_ESCALATED
from app.services.classification_service import CATEGORIES
from app.services.complaint_common import ComplaintEffects, Outbox, assign_least_loaded
from app.services.complaint_status import FINISHED, ComplaintStatus, can_transition
from app.services.ports import ComplaintRecord, WorkflowExecutionRecord, WorkflowRuleRecord
from app.services.uow import UowFactory

TRIGGERS = ("complaint.created", "complaint.status_changed", "scheduled")
ACTIONS = ("notify_admins", "escalate", "auto_close", "assign_least_loaded", "add_internal_note")
PRIORITY_ORDER = ("low", "medium", "high", "critical")
CONDITION_KEYS = {"categories", "priority_min", "departments", "wards", "statuses", "languages", "unrouted", "age_hours_min"}
MAX_ESCALATION = 3


def validate_rule(r: WorkflowRuleRecord) -> WorkflowRuleRecord:
    errors: dict[str, str] = {}
    if r.trigger not in TRIGGERS:
        errors["trigger"] = f"One of {TRIGGERS}."
    if r.action not in ACTIONS:
        errors["action"] = f"One of {ACTIONS}."
    unknown = set(r.conditions) - CONDITION_KEYS
    if unknown:
        errors["conditions"] = f"Unknown condition(s): {sorted(unknown)}."
    if any(c not in CATEGORIES for c in r.conditions.get("categories", [])):
        errors["categories"] = "Unknown category."
    if r.conditions.get("priority_min") not in (None, *PRIORITY_ORDER):
        errors["priority_min"] = "Unknown priority."
    if any(s not in {x.value for x in ComplaintStatus} for s in r.conditions.get("statuses", [])):
        errors["statuses"] = "Unknown status."
    age = r.conditions.get("age_hours_min")
    if age is not None and (not isinstance(age, int | float) or age < 0):
        errors["age_hours_min"] = "Must be a non-negative number."
    if r.trigger == "scheduled" and age is None:
        errors["age_hours_min"] = "Scheduled rules need age_hours_min (otherwise they would fire on every complaint at once)."
    if r.action == "auto_close" and r.conditions.get("statuses") != ["resolved"]:
        errors["conditions"] = "auto_close only applies to resolved complaints: set statuses to ['resolved']."
    if r.action == "add_internal_note" and not str(r.params.get("text", "")).strip():
        errors["params"] = "add_internal_note needs params.text."
    if not r.conditions and r.trigger != "complaint.created":
        errors["conditions"] = "Give at least one condition."
    if not 2 <= len(r.name.strip()) <= 120 or not r.id.replace("-", "").replace("_", "").isalnum():
        errors["id"] = "Valid id (letters, digits, - _) and a name are required."
    if errors:
        raise ValidationFailed("Invalid workflow rule.", details=errors)
    return r


def matches(rule: WorkflowRuleRecord, c: ComplaintRecord, trigger: str, now: datetime) -> bool:
    """Pure evaluation."""
    if not rule.active or rule.trigger != trigger:
        return False
    k = rule.conditions
    if k.get("categories") and c.category not in k["categories"]:
        return False
    if k.get("priority_min") and PRIORITY_ORDER.index(c.priority) < PRIORITY_ORDER.index(k["priority_min"]):
        return False
    if k.get("departments") and c.department_code not in k["departments"]:
        return False
    if k.get("wards") and c.ward not in k["wards"]:
        return False
    if k.get("statuses") and str(c.status) not in k["statuses"]:
        return False
    if k.get("languages") and c.language not in k["languages"]:
        return False
    if k.get("unrouted") is True and c.department_code is not None:
        return False
    if k.get("age_hours_min") is not None:
        base = c.resolved_at if str(c.status) == "resolved" and c.resolved_at else c.created_at
        if now - base < timedelta(hours=float(k["age_hours_min"])):
            return False
    return True


class WorkflowService:
    def __init__(self, uow_factory: UowFactory, effects: ComplaintEffects) -> None:
        self._uow, self._fx = uow_factory, effects

    # ---- execution (called inside the caller's transaction for event triggers)
    def run_for_complaint(self, uow: Any, c: ComplaintRecord, trigger: str, out: Outbox) -> list[str]:
        """Claim the (rule, complaint) slot first - a rule runs at most once per complaint - then apply the action."""
        now = self._fx.clock()
        fired: list[str] = []
        for rule in uow.workflow.list_rules(active_only=True):
            if not matches(rule, c, trigger, now):
                continue
            if not uow.workflow.try_record_execution(WorkflowExecutionRecord(rule.id, c.id, now, rule.action)):
                continue  # already executed for this complaint
            outcome = self._apply(uow, rule, c, out, now)
            self._fx.event(uow, c, "workflow", None, details={"rule": rule.id, "action": rule.action, "outcome": outcome}, internal=True, actor_label=f"Workflow: {rule.name}")
            self._fx.audit(uow).record("workflow.executed", actor_id=None, resource_type="complaint", resource_id=c.id, metadata={"rule": rule.id, "action": rule.action, "outcome": outcome})
            fired.append(rule.id)
        return fired

    def _apply(self, uow: Any, rule: WorkflowRuleRecord, c: ComplaintRecord, out: Outbox, now: datetime) -> str:
        if rule.action == "notify_admins":
            for admin_id in uow.officers.admin_ids():
                self._fx.notify(uow, out, admin_id, "system", rule.name, str(rule.params.get("message") or f"{c.reference}: workflow rule '{rule.name}' matched"), c, dedupe_key=f"wf:{rule.id}:{c.id}:{admin_id}")
            return "notified_admins"
        if rule.action == "escalate":
            if c.status in FINISHED or c.escalation_level >= MAX_ESCALATION:
                return "skipped"
            frm = c.escalation_level
            c.escalation_level, c.escalated_at, c.updated_at = frm + 1, now, now
            uow.complaints.update(c)
            self._fx.event(uow, c, "escalated", None, remarks=f"Workflow rule: {rule.name}", details={"from_level": frm, "to_level": c.escalation_level, "manual": False}, actor_label="Workflow")
            out.events.append(self._fx.complaint_event(COMPLAINT_ESCALATED, c, {"level": c.escalation_level}, {"reason": rule.name}))
            return f"escalated_to_{c.escalation_level}"
        if rule.action == "auto_close":
            if str(c.status) != "resolved" or not can_transition(c.status, ComplaintStatus.CLOSED):
                return "skipped"
            self._fx.event(uow, c, "status_change", None, from_status=c.status, to_status=ComplaintStatus.CLOSED, remarks=f"Closed automatically by workflow rule: {rule.name}", actor_label="Workflow")
            c.status, c.updated_at = ComplaintStatus.CLOSED, now
            uow.complaints.update(c)
            self._fx.notify(uow, out, c.citizen_id, "complaint.status_changed", "Complaint closed", f"{c.reference} was closed.", c, dedupe_key=f"wfclose:{c.id}")
            return "closed"
        if rule.action == "assign_least_loaded":
            if not c.department_code or c.assigned_officer_id or c.status in FINISHED:
                return "skipped"
            officer_id = assign_least_loaded(uow, c.department_code)
            if not officer_id:
                return "no_officer_available"
            c.assigned_officer_id, c.updated_at = officer_id, now
            uow.complaints.update(c)
            self._fx.notify(uow, out, officer_id, "complaint.assigned", "Complaint assigned to you", f"{c.reference}: {c.title}", c, dedupe_key=f"wfassign:{c.id}:{officer_id}")
            return f"assigned_{officer_id}"
        self._fx.event(uow, c, "remark", None, remarks=str(rule.params.get("text", "")), internal=True, actor_label=f"Workflow: {rule.name}")
        return "note_added"

    def sweep(self, now: datetime) -> dict[str, Any]:
        """Scheduled task: age-based rules over open complaints and resolved ones (for auto-close)."""
        out = Outbox()
        fired = 0
        with self._uow() as uow:
            rules = [r for r in uow.workflow.list_rules(active_only=True) if r.trigger == "scheduled"]
            if not rules:
                return {"rules": 0, "fired": 0}
            candidates = uow.complaints.list_open() + uow.complaints.list_by_status([ComplaintStatus.RESOLVED], limit=5000)
            for c in candidates:
                fired += len(self.run_for_complaint(uow, c, "scheduled", out))
            uow.commit()
        self._fx.flush(out)
        return {"rules": len(rules), "fired": fired}
