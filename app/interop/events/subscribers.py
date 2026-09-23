"""Real event subscribers (Section 11: "do not only publish events - demonstrate subscribers
actually reacting"). Each subscriber is decoupled from the publisher (``InteropGatewayService``
never imports or calls a subscriber directly) - it only knows the event bus, exactly like a real
department's own system would consume CivicLens's interop events.
"""

from __future__ import annotations

from collections.abc import Callable

from app.interop.events.bus import InteropEventBus
from app.interop.events.types import InteropEvent
from app.services.notification_service import NotificationService
from app.services.uow import UowFactory


class NotificationSubscriber:
    """Reacts to ``ExchangeCompleted`` by creating a real in-app notification for the citizen the
    exchange was about - reusing the existing, generic ``NotificationService`` rather than a
    parallel notification path. This is the concrete version of Section 11's own example
    ("... Dept B subscriber -> Application automatically updated -> ... -> Citizen notification"):
    the application update already happens synchronously inside the gateway (see
    ``InteropGatewayService._execute_exchange``); this subscriber is what turns the *fact* that it
    happened into a citizen-visible notification, asynchronously, from a consumer that has no
    other coupling to the gateway than the event it reads.
    """

    def __init__(self, uow_factory: UowFactory, notifications: NotificationService) -> None:
        self._uow, self._notifications = uow_factory, notifications

    def handle(self, event: InteropEvent) -> bool:
        """Returns True if it produced a real, observable side effect - tests assert on this
        directly rather than inferring success from the absence of an exception."""
        if event.event_type != "ExchangeCompleted":
            return False
        citizen_user_id = event.payload.get("citizen_user_id")
        if not citizen_user_id:
            return False
        document_type = event.payload.get("document_type", "document")
        document_reference = event.payload.get("document_reference", "")
        application_no = event.payload.get("application_no", "")
        with self._uow() as uow:
            rec, _domain_event = self._notifications.notify(
                uow.notifications, citizen_user_id, "interop.exchange_completed",
                "A document was shared on your behalf",
                f"Your {document_type.replace('_', ' ')} was shared with {event.destination} for application {application_no} (reference {document_reference}). You did not need to re-upload anything.",
                data={"correlation_id": event.correlation_id, "application_no": application_no, "document_reference": document_reference},
                dedupe_key=f"interop-exchange:{event.correlation_id}",
            )
            uow.commit()
        return rec is not None

    def drain(self, bus: InteropEventBus, *, start_id: str = "-", count: int = 100) -> int:
        """Pull-based: process everything currently available from ``start_id`` onward. Used both
        by a background consumer loop and directly by tests (against a real Redis stream) - the
        same method, not a test-only shortcut."""
        handled = 0
        for _entry_id, event in bus.read_range(start_id=start_id, count=count):
            if self.handle(event):
                handled += 1
        return handled


def run_consumer_loop(bus, subscriber: NotificationSubscriber, stop: Callable[[], bool], *, last_id: str = "$") -> None:
    """Blocking loop for a background thread (the same shape ``RedisEventBus.listen`` already uses
    for the complaint domain event bus - see app/workers/redis_backend.py). Only meaningful for a
    real ``RedisInteropEventBus`` (blocking XREAD); the in-memory bus has no blocking read and is
    drained directly via ``subscriber.drain`` instead."""
    cursor = last_id
    while not stop():
        for entry_id, event in bus.read_new_blocking(last_id=cursor):
            subscriber.handle(event)
            cursor = entry_id
