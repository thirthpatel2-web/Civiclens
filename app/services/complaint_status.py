"""Complaint lifecycle: statuses, allowed transitions, tracker timeline and filters.

The original Node workflow was deliberately permissive (it only blocked moving a
finished complaint back to intake). Here transitions form an explicit graph matching
the product flow *Submitted -> AI Routed -> Assigned -> Under Review -> In Progress ->
Resolved*, with side-states for inspection, rejection and closure. Every accepted
transition yields a ``HistoryEvent`` so nothing changes without a trace.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.core.exceptions import ValidationFailed


class ComplaintStatus(StrEnum):
    SUBMITTED = "submitted"
    AI_ROUTED = "ai_routed"
    ASSIGNED = "assigned"
    UNDER_REVIEW = "under_review"
    INSPECTION_SCHEDULED = "inspection_scheduled"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REJECTED = "rejected"


S = ComplaintStatus
TRANSITIONS: dict[ComplaintStatus, frozenset[ComplaintStatus]] = {
    S.SUBMITTED: frozenset({S.AI_ROUTED, S.REJECTED}),
    S.AI_ROUTED: frozenset({S.ASSIGNED, S.REJECTED}),
    S.ASSIGNED: frozenset({S.UNDER_REVIEW, S.AI_ROUTED, S.REJECTED}),  # AI_ROUTED = re-route
    S.UNDER_REVIEW: frozenset({S.INSPECTION_SCHEDULED, S.IN_PROGRESS, S.RESOLVED, S.REJECTED, S.ASSIGNED}),
    S.INSPECTION_SCHEDULED: frozenset({S.UNDER_REVIEW, S.IN_PROGRESS, S.RESOLVED}),
    S.IN_PROGRESS: frozenset({S.UNDER_REVIEW, S.INSPECTION_SCHEDULED, S.RESOLVED}),
    S.RESOLVED: frozenset({S.CLOSED, S.IN_PROGRESS}),  # IN_PROGRESS = reopen
    S.CLOSED: frozenset(),
    S.REJECTED: frozenset(),
}
TERMINAL = frozenset({S.CLOSED, S.REJECTED})
FINISHED = frozenset({S.RESOLVED, S.CLOSED, S.REJECTED})
REMARK_REQUIRED = frozenset({S.REJECTED, S.RESOLVED})

# Citizen-facing tracker stages (product flow), in order.
TIMELINE_STAGES: tuple[tuple[str, frozenset[ComplaintStatus]], ...] = (
    ("Submitted", frozenset({S.SUBMITTED})),
    ("AI Routed", frozenset({S.AI_ROUTED})),
    ("Assigned", frozenset({S.ASSIGNED})),
    ("Under Review", frozenset({S.UNDER_REVIEW, S.INSPECTION_SCHEDULED})),
    ("In Progress", frozenset({S.IN_PROGRESS})),
    ("Resolved", frozenset({S.RESOLVED, S.CLOSED})),
)


@dataclass(frozen=True)
class HistoryEvent:
    complaint_id: str
    action: str
    from_status: ComplaintStatus | None
    to_status: ComplaintStatus | None
    actor_id: str | None
    actor_label: str | None
    remarks: str | None
    at: datetime


def can_transition(current: ComplaintStatus, target: ComplaintStatus) -> bool:
    return target in TRANSITIONS[current]


def validate_transition(current: ComplaintStatus, target: ComplaintStatus, remarks: str | None) -> None:
    if not can_transition(current, target):
        raise ValidationFailed(
            f"A complaint cannot move from '{current}' to '{target}'.",
            details={"allowed": sorted(TRANSITIONS[current])},
        )
    if target in REMARK_REQUIRED and not (remarks and remarks.strip()):
        raise ValidationFailed(f"A remark is required when setting status to '{target}'.", details={"field": "remarks"})
    if current is S.RESOLVED and target is S.IN_PROGRESS and not (remarks and remarks.strip()):
        raise ValidationFailed("A remark is required to reopen a resolved complaint.", details={"field": "remarks"})


def apply_transition(
    complaint_id: str, current: ComplaintStatus, target: ComplaintStatus, *, actor_id: str | None,
    actor_label: str | None, remarks: str | None, at: datetime,
) -> HistoryEvent:  # fmt: skip
    validate_transition(current, target, remarks)
    return HistoryEvent(complaint_id, "status_change", current, target, actor_id, actor_label, (remarks or "").strip() or None, at)


@dataclass(frozen=True)
class TimelineStep:
    label: str
    state: str  # "done" | "current" | "upcoming" | "skipped" | "rejected"
    at: datetime | None


def build_timeline(current: ComplaintStatus, events: list[HistoryEvent]) -> list[TimelineStep]:
    """Tracker view. Timestamps come only from recorded events (never invented)."""
    reached: dict[str, datetime] = {}
    for ev in sorted(events, key=lambda e: e.at):
        if ev.to_status is None:
            continue
        for label, statuses in TIMELINE_STAGES:
            if ev.to_status in statuses:
                reached.setdefault(label, ev.at)
    if current is S.REJECTED:
        steps = [TimelineStep(label, "done" if label in reached else "skipped", reached.get(label)) for label, _ in TIMELINE_STAGES[:1]]
        rejected_at = next((e.at for e in events if e.to_status is S.REJECTED), None)
        return steps + [TimelineStep("Rejected", "rejected", rejected_at)]
    current_idx = next(i for i, (_, sts) in enumerate(TIMELINE_STAGES) if current in sts)
    steps: list[TimelineStep] = []
    for i, (label, _) in enumerate(TIMELINE_STAGES):
        if i < current_idx:
            steps.append(TimelineStep(label, "done" if label in reached else "skipped", reached.get(label)))
        elif i == current_idx:
            done = current in {S.RESOLVED, S.CLOSED}
            steps.append(TimelineStep(label, "done" if done else "current", reached.get(label)))
        else:
            steps.append(TimelineStep(label, "upcoming", None))
    return steps


TRACKER_FILTERS = ("all", "active", "resolved", "rti", "municipal", "utility", "legal")


def matches_filter(filter_name: str, *, status: ComplaintStatus, complaint_type: str) -> bool:
    """``complaint_type`` is one of municipal | utility | legal | rti (plus others)."""
    f = filter_name.lower()
    if f not in TRACKER_FILTERS:
        raise ValidationFailed(f"Unknown filter {filter_name!r}.", details={"allowed": list(TRACKER_FILTERS)})
    if f == "all":
        return True
    if f == "active":
        return status not in FINISHED
    if f == "resolved":
        return status in {S.RESOLVED, S.CLOSED}
    return complaint_type.lower() == f
