"""SLA policy selection, due-time calculation, risk status and escalation.

Pure and clock-injected so a scheduler (not the UI) can call ``SlaScanner.scan``
periodically. The escalation engine is idempotent: given the same complaint state and
time it returns the same single action, and it returns nothing once the complaint has
already been escalated to the required level.

The original Node engine re-escalated using a status-history timestamp; here the
last-escalation time is stored on the complaint (``escalated_at``) and the ladder is
explicit, which fixes that class of bug.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.services.complaint_status import FINISHED, ComplaintStatus


@dataclass(frozen=True)
class SlaPolicy:
    id: str
    priority: str
    resolution_hours: int
    department_code: str | None = None  # None = default for any department
    approaching_fraction: float = 0.25  # "at risk" when <= 25% of the window remains
    escalation_gap_hours: int = 48
    max_level: int = 3

    def __post_init__(self) -> None:
        if self.resolution_hours <= 0 or not 0 < self.approaching_fraction < 1 or self.max_level < 1:
            raise ValueError("invalid SLA policy")


@dataclass(frozen=True)
class SlaSubject:
    id: str
    priority: str
    department_code: str | None
    status: ComplaintStatus
    created_at: datetime
    sla_due_at: datetime | None = None
    escalation_level: int = 0
    escalated_at: datetime | None = None


@dataclass(frozen=True)
class SlaStatus:
    state: str  # "no_policy" | "finished" | "on_track" | "at_risk" | "breached"
    due_at: datetime | None
    remaining: timedelta | None
    policy_id: str | None


@dataclass(frozen=True)
class EscalationAction:
    complaint_id: str
    from_level: int
    to_level: int
    reason: str
    at: datetime


@dataclass
class ScanReport:
    at_risk: list[str] = field(default_factory=list)
    breached: list[str] = field(default_factory=list)
    actions: list[EscalationAction] = field(default_factory=list)


class SlaCalculator:
    def __init__(self, policies: list[SlaPolicy]) -> None:
        self._policies = policies

    def policy_for(self, priority: str, department_code: str | None) -> SlaPolicy | None:
        exact = [p for p in self._policies if p.priority == priority and p.department_code == department_code and department_code]
        if exact:
            return exact[0]
        generic = [p for p in self._policies if p.priority == priority and p.department_code is None]
        return generic[0] if generic else None

    def due_at(self, created_at: datetime, priority: str, department_code: str | None) -> datetime | None:
        p = self.policy_for(priority, department_code)
        return created_at + timedelta(hours=p.resolution_hours) if p else None

    def status(self, s: SlaSubject, now: datetime) -> SlaStatus:
        policy = self.policy_for(s.priority, s.department_code)
        if s.status in FINISHED:
            return SlaStatus("finished", s.sla_due_at, None, policy.id if policy else None)
        due = s.sla_due_at or (self.due_at(s.created_at, s.priority, s.department_code))
        if due is None or policy is None:
            return SlaStatus("no_policy", None, None, None)
        remaining = due - now
        if remaining <= timedelta(0):
            return SlaStatus("breached", due, remaining, policy.id)
        window = timedelta(hours=policy.resolution_hours)
        return SlaStatus("at_risk" if remaining <= window * policy.approaching_fraction else "on_track", due, remaining, policy.id)


class EscalationEngine:
    def __init__(self, calculator: SlaCalculator) -> None:
        self._calc = calculator

    def evaluate(self, s: SlaSubject, now: datetime) -> EscalationAction | None:
        st = self._calc.status(s, now)
        policy = self._calc.policy_for(s.priority, s.department_code)
        if st.state != "breached" or policy is None or s.escalation_level >= policy.max_level:
            return None
        if s.escalation_level == 0:
            return EscalationAction(s.id, 0, 1, "SLA due time passed without resolution.", now)
        last = s.escalated_at or st.due_at
        if last is not None and now - last >= timedelta(hours=policy.escalation_gap_hours):
            return EscalationAction(s.id, s.escalation_level, s.escalation_level + 1, f"Still unresolved {policy.escalation_gap_hours}h after level {s.escalation_level} escalation.", now)
        return None


class SlaScanner:
    def __init__(self, calculator: SlaCalculator) -> None:
        self._calc, self._engine = calculator, EscalationEngine(calculator)

    def scan(self, subjects: list[SlaSubject], now: datetime) -> ScanReport:
        report = ScanReport()
        for s in subjects:
            st = self._calc.status(s, now)
            if st.state == "at_risk":
                report.at_risk.append(s.id)
            elif st.state == "breached":
                report.breached.append(s.id)
                if (action := self._engine.evaluate(s, now)) is not None:
                    report.actions.append(action)
        return report
