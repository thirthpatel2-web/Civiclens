"""Shared building blocks for complaint-touching services (events, audit, notifications, outbox)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.authorization import AuthContext
from app.realtime.events import DomainEvent
from app.realtime.websocket_manager import EventBus
from app.services.audit_service import AuditService
from app.services.complaint_status import ComplaintStatus
from app.services.notification_service import NotificationService
from app.services.ports import ComplaintEvent, ComplaintRecord, JobRecord
from app.workers.queue import JobService


@dataclass
class Outbox:
    """Side effects collected inside a transaction and released only after it commits."""

    events: list[DomainEvent] = field(default_factory=list)
    jobs: list[JobRecord] = field(default_factory=list)


class ComplaintEffects:
    def __init__(self, notifications: NotificationService, jobs: JobService, bus: EventBus, clock: Callable[[], datetime] | None = None) -> None:
        self.notifications, self.jobs, self.bus = notifications, jobs, bus
        self.clock = clock or (lambda: datetime.now(UTC))
        self.workflow: Any | None = None  # WorkflowService, attached by the container

    def audit(self, uow: Any) -> AuditService:
        return AuditService(uow.audit, self.clock)

    def event(self, uow: Any, c: ComplaintRecord, kind: str, ctx: AuthContext | None, *, from_status: ComplaintStatus | None = None,
              to_status: ComplaintStatus | None = None, remarks: str | None = None, details: dict[str, Any] | None = None, internal: bool = False,
              actor_label: str | None = None) -> ComplaintEvent:  # fmt: skip
        label = actor_label or (uow.officers.user_label(ctx.user_id) if ctx else "System")
        ev = ComplaintEvent(str(uuid.uuid4()), c.id, kind, from_status, to_status, ctx.user_id if ctx else None, label, (remarks or "").strip() or None, details or {}, self.clock(), internal)
        uow.complaints.add_event(ev)
        return ev

    def notify(self, uow: Any, out: Outbox, user_id: str, kind: str, title: str, body: str, c: ComplaintRecord, dedupe_key: str | None = None) -> None:
        email_ids: list[str] = []
        push_ids: list[str] = []
        devices = len(uow.push.list_for_user(user_id)) if getattr(uow, "push", None) is not None else 0
        rec, ev = self.notifications.notify(uow.notifications, user_id, kind, title, body, data={"complaint_id": c.id, "reference": c.reference}, dedupe_key=dedupe_key,
                                            want_email_job=email_ids, push_devices=devices, want_push_job=push_ids)  # fmt: skip
        if ev:
            out.events.append(ev)
        for nid in email_ids:
            job, created = self.jobs.enqueue(uow, "notification.email", {"notification_id": nid, "user_id": user_id}, f"email:{nid}")
            if created:
                out.jobs.append(job)
        for nid in push_ids:
            job, created = self.jobs.enqueue(uow, "notification.push", {"notification_id": nid, "user_id": user_id}, f"push:{nid}")
            if created:
                out.jobs.append(job)

    def run_workflow(self, uow: Any, c: ComplaintRecord, trigger: str, out: Outbox) -> list[str]:
        return self.workflow.run_for_complaint(uow, c, trigger, out) if self.workflow is not None else []

    def complaint_event(self, kind: str, c: ComplaintRecord, extra: dict[str, Any] | None = None, internal: dict[str, Any] | None = None) -> DomainEvent:
        data = {"reference": c.reference, "status": str(c.status), "department_code": c.department_code, **(extra or {})}
        return DomainEvent(kind, data, internal or {}, owner_id=c.citizen_id, department_code=c.department_code, complaint_id=c.id)

    def flush(self, out: Outbox) -> None:
        """Call AFTER commit. Queue push / websocket failures never undo committed work."""
        if out.jobs:
            self.jobs.dispatch(out.jobs)
        for ev in out.events:
            try:
                self.bus.publish(ev)
            except Exception:  # realtime is best-effort; the timeline/notification rows are the record
                import logging

                logging.getLogger("civiclens.realtime").warning("event publish failed for %s", ev.type)


def assign_least_loaded(uow: Any, department_code: str) -> str | None:
    ids = uow.officers.officer_ids_for_department(department_code)
    if not ids:
        return None
    loads = {ld.officer_id: ld.open_count for ld in uow.complaints.officer_loads(department_code, ids)}
    return min(ids, key=lambda i: (loads.get(i, 0), i))
