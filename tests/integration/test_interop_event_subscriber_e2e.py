"""Section 11: "do not only publish events - demonstrate subscribers actually reacting", proven
end to end against the real gateway, real Postgres, and a real Redis stream - not a mocked bus.

A full no-reupload exchange runs through InteropGatewayService wired to a genuine
RedisInteropEventBus. The resulting ExchangeCompleted event is read back from the real stream and
handed to NotificationSubscriber, which is entirely decoupled from the gateway (it only knows the
bus) - and it creates a real, queryable in-app notification for the citizen. That notification
existing is the observable proof a subscriber reacted, not an inferred side effect.

Skips cleanly if either a live database or a live Redis server isn't reachable.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.core.authorization import AuthContext, Role
from app.core.config import Settings
from app.db.models.identity import UserModel
from app.db.models.interop_platform import (
    InteropConsentGrant,
    InteropTransaction,
    MasterEntity,
    MasterIdentifier,
    MockDeptADocument,
    MockDeptAResident,
    MockDeptBApplication,
    MockDeptBBeneficiary,
    UnifiedApplication,
    UnifiedApplicationEvent,
)
from app.db.session import make_engine, make_session_factory
from app.db.uow import SqlUnitOfWork
from app.interop import connector_registry, mock_systems
from app.interop.events.bus import RedisInteropEventBus
from app.interop.events.subscribers import NotificationSubscriber
from app.interop.federation import idp
from app.services.interop_gateway_service import InteropGatewayService
from app.services.notification_service import NotificationService

try:
    _engine = make_engine(Settings.load())
    with _engine.connect():
        pass
    _DB_AVAILABLE = True
    _DB_SKIP_REASON = ""
except Exception as exc:  # noqa: BLE001
    _DB_AVAILABLE = False
    _DB_SKIP_REASON = f"no live database available: {exc}"

try:
    import redis as redis_lib

    _redis_settings = Settings.load()
    _redis_client = redis_lib.from_url(_redis_settings.redis_url, socket_connect_timeout=3) if _redis_settings.redis_url else None
    if _redis_client is None:
        raise RuntimeError("REDIS_URL not set")
    _redis_client.ping()
    _REDIS_AVAILABLE = True
    _REDIS_SKIP_REASON = ""
except Exception as exc:  # noqa: BLE001
    _REDIS_AVAILABLE = False
    _REDIS_SKIP_REASON = f"no live Redis available: {exc}"


@unittest.skipUnless(_DB_AVAILABLE and _REDIS_AVAILABLE, _DB_SKIP_REASON or _REDIS_SKIP_REASON)
class EventSubscriberEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session_factory = make_session_factory(_engine)
        self.uow_factory = lambda: SqlUnitOfWork(self.session_factory)
        self.bus = RedisInteropEventBus(_redis_client)
        self.gateway = InteropGatewayService(self.uow_factory, bus=self.bus)
        self.subscriber = NotificationSubscriber(self.uow_factory, NotificationService())

        self._suffix = uuid.uuid4().hex[:8]
        self.resident_id = f"TEST-EVT-A-{self._suffix}"
        self.beneficiary_code = f"TEST-EVT-B-{self._suffix}"
        self.application_no = f"TEST-EVT-APP-{self._suffix}"
        self.reference_no = f"TESTREF-EVT-{self._suffix}"
        self._created_master_ids: set[str] = set()

        now = datetime.now(UTC)
        with self.uow_factory() as uow:
            s = uow.session
            mock_systems.seed_if_empty(s)
            connector_registry.seed_if_empty(s)
            idp.seed_if_empty(s)
            s.add(MockDeptAResident(resident_id=self.resident_id, full_name="Event Test Citizen", mobile="9811122233", address="1 Event Rd", city="Pune", state="Maharashtra", created_at=now))
            s.flush()
            s.add(MockDeptADocument(document_id=str(uuid.uuid4()), resident_id=self.resident_id, document_type="residence_certificate", status="verified", reference_no=self.reference_no, issued_on=now, created_at=now))
            s.add(MockDeptBBeneficiary(beneficiary_code=self.beneficiary_code, full_name="Event Test Citizen", mobile_number="9811122233", created_at=now))
            s.flush()
            s.add(MockDeptBApplication(application_no=self.application_no, beneficiary_code=self.beneficiary_code, service_type="Small Business Registration", status="pending_document", required_document_type="residence_certificate", document_status="missing", created_at=now, updated_at=now))
            user = UserModel(id=str(uuid.uuid4()), email=f"event-subscriber-test-{self._suffix}@example.invalid", password_hash="x", full_name="Event Subscriber Test Citizen", role="admin", is_active=True, created_at=now)
            s.add(user)
            uow.commit()
            self.user_id = user.id
        self.admin = AuthContext(self.user_id, Role.ADMIN, None, True)

    def tearDown(self) -> None:
        with self.uow_factory() as uow:
            s = uow.session
            unified = s.execute(select(UnifiedApplication).where(UnifiedApplication.external_reference == self.application_no)).scalars().first()
            if unified is not None:
                s.execute(delete(UnifiedApplicationEvent).where(UnifiedApplicationEvent.application_id == unified.application_id))
                s.execute(delete(UnifiedApplication).where(UnifiedApplication.application_id == unified.application_id))
            if self._created_master_ids:
                s.execute(delete(InteropTransaction).where(InteropTransaction.master_id.in_(self._created_master_ids)))
                s.execute(delete(InteropConsentGrant).where(InteropConsentGrant.master_id.in_(self._created_master_ids)))
                s.execute(delete(MasterIdentifier).where(MasterIdentifier.master_id.in_(self._created_master_ids)))
                s.execute(delete(MasterEntity).where(MasterEntity.master_id.in_(self._created_master_ids)))
            s.execute(delete(MockDeptADocument).where(MockDeptADocument.resident_id == self.resident_id))
            s.execute(delete(MockDeptAResident).where(MockDeptAResident.resident_id == self.resident_id))
            s.execute(delete(MockDeptBApplication).where(MockDeptBApplication.application_no == self.application_no))
            s.execute(delete(MockDeptBBeneficiary).where(MockDeptBBeneficiary.beneficiary_code == self.beneficiary_code))
            from app.db.models.ops import NotificationModel

            s.execute(delete(NotificationModel).where(NotificationModel.user_id == self.user_id))
            s.execute(delete(UserModel).where(UserModel.id == self.user_id))
            uow.commit()

    def test_a_real_exchange_publishes_to_redis_and_the_subscriber_creates_a_real_notification(self) -> None:
        independent_reader = RedisInteropEventBus(_redis_client)
        # The stream is shared/durable across every run of this test (and real demo usage) - scope
        # the drain to only what THIS run publishes, not the whole stream's history, or it would
        # try to notify citizens from earlier runs whose throwaway accounts no longer exist.
        existing = independent_reader.read_range(count=100000)
        cursor_before = existing[-1][0] if existing else "-"

        first = self.gateway.request_document_exchange(self.admin, application_no=self.application_no)
        self.assertEqual(first["status"], "consent_required")
        self._created_master_ids.add(first["master_id"])
        self.gateway.grant_consent(self.admin, consent_id=first["consent_id"])

        result = self.gateway.request_document_exchange(self.admin, application_no=self.application_no)
        self.assertEqual(result["status"], "success", result)
        correlation_id = result["correlation_id"]

        # The events are genuinely in Redis - read them back independently of the gateway/bus object.
        new_events = independent_reader.read_range(start_id=cursor_before, count=100000)
        mine = [e for _id, e in new_events if e.correlation_id == correlation_id]
        event_types = {e.event_type for e in mine}
        self.assertIn("IdentityResolved", event_types)
        self.assertIn("DocumentRequested", event_types)
        self.assertIn("DocumentVerified", event_types)
        self.assertIn("DocumentTransferred", event_types)
        self.assertIn("ExchangeCompleted", event_types)

        exchange_completed = next(e for e in mine if e.event_type == "ExchangeCompleted")
        self.assertEqual(exchange_completed.payload["citizen_user_id"], self.user_id)

        # The subscriber is decoupled from the gateway - it only ever talks to the bus, and only
        # processes what this run actually published.
        handled = self.subscriber.drain(independent_reader, start_id=cursor_before, count=100000)
        self.assertGreaterEqual(handled, 1)

        from app.db.models.ops import NotificationModel

        with self.uow_factory() as uow:
            notifications = list(uow.session.execute(select(NotificationModel).where(NotificationModel.user_id == self.user_id)).scalars().all())
            self.assertEqual(len(notifications), 1)
            self.assertEqual(notifications[0].kind, "interop.exchange_completed")
            self.assertIn(self.reference_no, notifications[0].body)

        # Draining again is idempotent - NotificationService.notify's dedupe_key means the same
        # correlation_id never produces a second notification, so handle() reports it did NOT
        # produce a (new) side effect the second time, and the notification count stays at 1.
        handled_again = self.subscriber.drain(independent_reader, start_id=cursor_before, count=100000)
        self.assertEqual(handled_again, 0)
        with self.uow_factory() as uow:
            notifications_after = list(uow.session.execute(select(NotificationModel).where(NotificationModel.user_id == self.user_id)).scalars().all())
            self.assertEqual(len(notifications_after), 1)


if __name__ == "__main__":
    unittest.main()
