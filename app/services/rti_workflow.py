"""RTI deadline reminders (scheduled) and the persistence-facing RTI operations for citizens."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.notification_service import NotificationService
from app.services.rti_service import RtiRules, due_reminders
from app.services.uow import UowFactory
from app.realtime.events import DomainEvent


class RtiReminderService:
    def __init__(self, uow_factory: UowFactory, notifications: NotificationService, rules: RtiRules, bus: Any) -> None:
        self._uow, self._notifications, self._rules, self._bus = uow_factory, notifications, rules, bus

    def run(self, now: datetime) -> dict[str, Any]:
        sent = 0
        events: list[DomainEvent] = []
        with self._uow() as uow:
            for app in uow.rti.list_filed():
                for threshold in due_reminders(app, now, self._rules):
                    days = max((app.due_at - now).days, 0) if app.due_at else threshold
                    rec, ev = self._notifications.notify(uow.notifications, app.owner_id, "rti.deadline", "RTI deadline approaching",
                                                         f"{app.reference}: {days} day(s) left for the public authority to respond.", data={"reference": app.reference}, dedupe_key=f"rti:{app.id}:{threshold}")  # fmt: skip
                    app.reminders_sent = (*app.reminders_sent, threshold)
                    uow.rti.update(app)
                    if ev:
                        events.append(ev)
                        sent += 1
            uow.commit()
        for ev in events:
            try:
                self._bus.publish(ev)
            except Exception:  # best-effort push; the notification row is the record
                pass
        return {"reminders_sent": sent}
