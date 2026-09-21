"""Domain events and the audience rules that decide who may receive them."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.authorization import AuthContext, Role

COMPLAINT_CREATED = "complaint.created"
COMPLAINT_PROCESSED = "complaint.processed"
COMPLAINT_ASSIGNED = "complaint.assigned"
COMPLAINT_STATUS_CHANGED = "complaint.status_changed"
COMPLAINT_ESCALATED = "complaint.escalated"
NOTIFICATION_CREATED = "notification.created"
INTEGRATION_STATUS_CHANGED = "integration.status_changed"
EVENT_TYPES = frozenset({COMPLAINT_CREATED, COMPLAINT_PROCESSED, COMPLAINT_ASSIGNED, COMPLAINT_STATUS_CHANGED, COMPLAINT_ESCALATED, NOTIFICATION_CREATED, INTEGRATION_STATUS_CHANGED})


@dataclass(frozen=True)
class DomainEvent:
    type: str
    payload: dict[str, Any]  # safe for the citizen who owns the record
    internal: dict[str, Any] = field(default_factory=dict)  # staff-only additions
    owner_id: str | None = None  # citizen (complaint.*) or recipient (notification.*)
    department_code: str | None = None
    complaint_id: str | None = None
    at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {self.type!r}")


def may_receive(ctx: AuthContext, event: DomainEvent) -> bool:
    """Server-side audience check, applied per connection on every delivery."""
    if event.type == NOTIFICATION_CREATED:
        return event.owner_id is not None and ctx.user_id == event.owner_id
    if event.type == INTEGRATION_STATUS_CHANGED:
        return ctx.role in (Role.ADMIN, Role.SUPER_ADMIN) and ctx.department_id is None
    # complaint.* events
    if ctx.role is Role.CITIZEN:
        return event.owner_id is not None and ctx.user_id == event.owner_id
    if ctx.role is Role.OFFICER:
        return ctx.department_id is not None and ctx.department_id == event.department_code
    if ctx.role is Role.ADMIN:
        return ctx.department_id is None or ctx.department_id == event.department_code
    return True  # SUPER_ADMIN


def view_for(ctx: AuthContext, event: DomainEvent) -> dict[str, Any]:
    """Wire format; staff additionally get ``internal``. Citizens never see it."""
    body: dict[str, Any] = {"type": event.type, "complaint_id": event.complaint_id, "at": event.at.isoformat(), "data": dict(event.payload)}
    if ctx.role is not Role.CITIZEN and event.internal:
        body["internal"] = dict(event.internal)
    return body


def event_to_json(e: DomainEvent) -> str:
    """Wire form for the Redis pub/sub bridge (multi-process deployments)."""
    import json

    return json.dumps({"type": e.type, "payload": e.payload, "internal": e.internal, "owner_id": e.owner_id, "department_code": e.department_code, "complaint_id": e.complaint_id, "at": e.at.isoformat()}, default=str)


def event_from_json(raw: str) -> DomainEvent:
    import json

    d = json.loads(raw)
    return DomainEvent(d["type"], d.get("payload") or {}, d.get("internal") or {}, d.get("owner_id"), d.get("department_code"), d.get("complaint_id"), datetime.fromisoformat(d["at"]))
