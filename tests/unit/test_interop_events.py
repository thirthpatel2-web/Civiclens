"""Interop event types + the in-memory bus - pure, no Redis, no database. See
tests/integration/test_interop_events_redis.py for the real Redis Streams round-trip and
tests/integration/test_interop_gateway_e2e.py for events published by a live exchange."""

from __future__ import annotations

import unittest

from app.interop.events.bus import InMemoryInteropEventBus
from app.interop.events.subscribers import NotificationSubscriber
from app.interop.events.types import INTEROP_EVENT_TYPES, InteropEvent, event_from_dict, event_to_dict


class InteropEventTests(unittest.TestCase):
    def test_all_twenty_one_event_types_from_the_spec_are_distinct(self):
        self.assertEqual(len(INTEROP_EVENT_TYPES), 21)

    def test_an_unrecognized_event_type_is_rejected(self):
        with self.assertRaises(ValueError):
            InteropEvent(event_type="SomethingMadeUp", source_system="dept_a", correlation_id="c-1")

    def test_every_declared_event_type_can_be_constructed(self):
        for event_type in INTEROP_EVENT_TYPES:
            InteropEvent(event_type=event_type, source_system="dept_a", correlation_id="c-1")

    def test_round_trips_through_dict_serialization_unchanged(self):
        original = InteropEvent(event_type="ConsentGranted", source_system="civiclens", destination="dept_b", entity_id="consent-1", correlation_id="c-42", payload={"master_id": "m-1"})
        restored = event_from_dict(event_to_dict(original))
        self.assertEqual(restored.event_type, original.event_type)
        self.assertEqual(restored.correlation_id, original.correlation_id)
        self.assertEqual(restored.payload, original.payload)
        self.assertEqual(restored.occurred_at, original.occurred_at)
        self.assertEqual(restored.event_id, original.event_id)


class InMemoryBusTests(unittest.TestCase):
    def test_publish_then_read_range_returns_everything_in_order(self):
        bus = InMemoryInteropEventBus()
        bus.publish(InteropEvent(event_type="ConsentRequested", source_system="dept_b", correlation_id="c-1"))
        bus.publish(InteropEvent(event_type="ConsentGranted", source_system="civiclens", correlation_id="c-1"))
        read = bus.read_range()
        self.assertEqual([e.event_type for _id, e in read], ["ConsentRequested", "ConsentGranted"])

    def test_read_range_respects_start_id(self):
        bus = InMemoryInteropEventBus()
        bus.publish(InteropEvent(event_type="ConsentRequested", source_system="dept_b", correlation_id="c-1"))
        bus.publish(InteropEvent(event_type="ConsentGranted", source_system="civiclens", correlation_id="c-1"))
        first_id, _ = bus.read_range()[0]
        read_after_first = bus.read_range(start_id=first_id)
        self.assertEqual([e.event_type for _id, e in read_after_first], ["ConsentGranted"])


class _FakeNotificationRepo:
    def __init__(self):
        self.added = []

    def get_preferences(self, user_id):
        return None  # NotificationService treats None as default prefs: in_app=True, no mute

    def add(self, record):
        self.added.append(record)
        return True


class NotificationSubscriberTests(unittest.TestCase):
    def setUp(self):
        from app.services.notification_service import NotificationService

        self.repo = _FakeNotificationRepo()

        class _FakeUow:
            def __init__(self, repo):
                self.notifications = repo

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def commit(self):
                pass

        self.subscriber = NotificationSubscriber(lambda: _FakeUow(self.repo), NotificationService())

    def test_ignores_event_types_other_than_exchange_completed(self):
        handled = self.subscriber.handle(InteropEvent(event_type="ConsentGranted", source_system="civiclens", correlation_id="c-1", payload={"citizen_user_id": "u-1"}))
        self.assertFalse(handled)
        self.assertEqual(self.repo.added, [])

    def test_ignores_exchange_completed_with_no_citizen_attached(self):
        handled = self.subscriber.handle(InteropEvent(event_type="ExchangeCompleted", source_system="dept_a", correlation_id="c-1", payload={}))
        self.assertFalse(handled)

    def test_creates_a_real_notification_for_exchange_completed(self):
        handled = self.subscriber.handle(InteropEvent(event_type="ExchangeCompleted", source_system="dept_a", destination="dept_b", correlation_id="c-1", payload={"citizen_user_id": "u-1", "document_type": "residence_certificate", "document_reference": "RC-1", "application_no": "APP-1"}))
        self.assertTrue(handled)
        self.assertEqual(len(self.repo.added), 1)
        self.assertEqual(self.repo.added[0].user_id, "u-1")
        self.assertIn("RC-1", self.repo.added[0].body)

    def test_drain_processes_every_matching_event_in_a_bus(self):
        bus = InMemoryInteropEventBus()
        bus.publish(InteropEvent(event_type="ConsentRequested", source_system="dept_b", correlation_id="c-1"))
        bus.publish(InteropEvent(event_type="ExchangeCompleted", source_system="dept_a", destination="dept_b", correlation_id="c-1", payload={"citizen_user_id": "u-1"}))
        bus.publish(InteropEvent(event_type="ExchangeCompleted", source_system="dept_a", destination="dept_b", correlation_id="c-2", payload={"citizen_user_id": "u-2"}))
        handled = self.subscriber.drain(bus)
        self.assertEqual(handled, 2)
        self.assertEqual({r.user_id for r in self.repo.added}, {"u-1", "u-2"})


if __name__ == "__main__":
    unittest.main()
