import asyncio
import unittest

from app.core.authorization import AuthContext, Role
from app.core.exceptions import NotFound, ValidationFailed
from app.realtime.events import DomainEvent, may_receive, view_for
from app.realtime.websocket_manager import LocalEventBus, WebSocketManager
from app.services.notification_service import KINDS, NotificationService
from app.services.ports import NotificationPreference
from tests.support import FakeClock
from tests.support_mem import MemNotifications, Stores

CIT1, CIT2 = AuthContext("c1", Role.CITIZEN), AuthContext("c2", Role.CITIZEN)
OFF_R, OFF_W = AuthContext("o1", Role.OFFICER, "roads"), AuthContext("o2", Role.OFFICER, "water")
ADMIN, ADMIN_R, SUPER = AuthContext("a1", Role.ADMIN, None, True), AuthContext("a2", Role.ADMIN, "roads", True), AuthContext("s1", Role.SUPER_ADMIN, None, True)


class FakeSocket:
    def __init__(self, fail=False): self.sent, self.fail = [], fail
    async def send_json(self, data):
        if self.fail:
            raise ConnectionError("closed")
        self.sent.append(data)


def ev(type_="complaint.status_changed", owner="c1", dept="roads"):
    return DomainEvent(type_, {"reference": "CL-1", "to": "resolved"}, {"remarks": "internal"}, owner_id=owner, department_code=dept, complaint_id="x")


class AudienceTests(unittest.TestCase):
    def test_matrix_for_complaint_events(self):
        e = ev()
        self.assertEqual([may_receive(c, e) for c in (CIT1, CIT2, OFF_R, OFF_W, ADMIN, ADMIN_R, SUPER)], [True, False, True, False, True, True, True])
        other = ev(dept="water")
        self.assertEqual([may_receive(c, other) for c in (OFF_R, OFF_W, ADMIN_R, ADMIN)], [False, True, False, True])

    def test_notification_only_to_recipient_and_integration_only_to_unbound_admins(self):
        n = ev("notification.created", owner="c1", dept=None)
        self.assertEqual([may_receive(c, n) for c in (CIT1, CIT2, OFF_R, ADMIN, SUPER)], [True, False, False, False, False])
        i = ev("integration.status_changed", owner=None, dept=None)
        self.assertEqual([may_receive(c, i) for c in (CIT1, OFF_R, ADMIN, ADMIN_R, SUPER)], [False, False, True, False, True])

    def test_internal_details_never_reach_citizens(self):
        self.assertNotIn("internal", view_for(CIT1, ev()))
        self.assertEqual(view_for(OFF_R, ev())["internal"], {"remarks": "internal"})

    def test_unknown_event_type_rejected(self):
        with self.assertRaises(ValueError):
            DomainEvent("complaint.exploded", {})


class ManagerTests(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    def test_delivery_is_isolated_by_citizen_and_department(self):
        async def go():
            m = WebSocketManager()
            socks = {n: FakeSocket() for n in ("c1", "c2", "o_r", "o_w", "admin", "admin_r")}
            ctxs = {"c1": CIT1, "c2": CIT2, "o_r": OFF_R, "o_w": OFF_W, "admin": ADMIN, "admin_r": ADMIN_R}
            for n, s in socks.items():
                await m.connect(s, ctxs[n])
            sent = await m.deliver(ev())
            got = {n: len(s.sent) for n, s in socks.items()}
            return sent, got, socks
        sent, got, socks = self.run_async(go())
        self.assertEqual(got, {"c1": 1, "c2": 0, "o_r": 1, "o_w": 0, "admin": 1, "admin_r": 1})
        self.assertEqual(sent, 4)
        self.assertNotIn("internal", socks["c1"].sent[0])
        self.assertIn("internal", socks["o_r"].sent[0])

    def test_failed_connection_is_dropped_and_others_still_receive(self):
        async def go():
            m = WebSocketManager()
            dead, alive = FakeSocket(fail=True), FakeSocket()
            await m.connect(dead, CIT1)
            await m.connect(alive, CIT1)
            n = await m.deliver(ev())
            return m.connection_count(), n, len(alive.sent), m.dropped_total
        self.assertEqual(self.run_async(go()), (1, 1, 1, 1))

    def test_disconnect_and_notification_event_targeting(self):
        async def go():
            m = WebSocketManager()
            s1, s2 = FakeSocket(), FakeSocket()
            c1 = await m.connect(s1, CIT1)
            await m.connect(s2, CIT2)
            await m.deliver(ev("notification.created", owner="c1", dept=None))
            m.disconnect(c1)
            await m.deliver(ev("notification.created", owner="c1", dept=None))
            return len(s1.sent), len(s2.sent), m.connection_count()
        self.assertEqual(self.run_async(go()), (1, 0, 1))

    def test_local_bus_without_loop_is_a_safe_noop_and_with_loop_delivers(self):
        m = WebSocketManager()
        LocalEventBus(m).publish(ev())  # no loop bound: must not raise

        async def go():
            bus, s = LocalEventBus(m), FakeSocket()
            await m.connect(s, CIT1)
            bus.bind_loop(asyncio.get_running_loop())
            await asyncio.to_thread(bus.publish, ev())
            await asyncio.sleep(0.05)
            return len(s.sent)
        self.assertEqual(self.run_async(go()), 1)


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.stores, self.clock = Stores(), FakeClock()
        self.repo, self.svc = MemNotifications(self.stores), NotificationService(self.clock)

    def test_in_app_delivery_dedupe_and_event(self):
        rec, event = self.svc.notify(self.repo, "c1", "complaint.created", "Registered", "Body", data={"reference": "CL-1"}, dedupe_key="d1")
        self.assertEqual((rec.status, rec.channel, rec.delivered_at), ("delivered", "in_app", self.clock.now))
        self.assertEqual((event.type, event.owner_id), ("notification.created", "c1"))
        self.assertEqual(self.svc.notify(self.repo, "c1", "complaint.created", "Registered", "Body", dedupe_key="d1"), (None, None))
        self.assertEqual(len(self.stores.notifications), 1)

    def test_muted_kinds_and_disabled_in_app_respected(self):
        self.svc.save_preferences(CIT1, self.repo, in_app=True, email=False, muted_kinds=["complaint.assigned"])
        self.assertEqual(self.svc.notify(self.repo, "c1", "complaint.assigned", "t", "b"), (None, None))
        self.assertIsNotNone(self.svc.notify(self.repo, "c1", "complaint.created", "t", "b")[0])
        self.svc.save_preferences(CIT1, self.repo, in_app=False, email=False, muted_kinds=[])
        self.assertEqual(self.svc.notify(self.repo, "c1", "complaint.created", "t2", "b"), (None, None))
        with self.assertRaises(ValidationFailed):
            self.svc.save_preferences(CIT1, self.repo, in_app=True, email=False, muted_kinds=["bogus"])
        self.assertTrue(set(KINDS) >= {"rti.deadline", "complaint.escalated"})

    def test_email_is_never_reported_delivered_without_a_sender(self):
        self.svc.save_preferences(CIT1, self.repo, in_app=True, email=True, muted_kinds=[])
        ids: list[str] = []
        self.svc.notify(self.repo, "c1", "complaint.created", "t", "b", dedupe_key="e1", want_email_job=ids)
        self.assertEqual(len(ids), 1)
        n = self.svc.deliver_email(self.repo, ids[0], "citizen@example.com")
        self.assertEqual(n.status, "not_configured")
        self.assertIn("not configured", n.error)
        self.assertIsNone(n.delivered_at)

    def test_email_delivery_with_sender_failure_and_missing_address(self):
        sent = []

        class Sender:
            def __init__(self, fail): self.fail = fail
            def send(self, to, subject, body):
                if self.fail:
                    raise OSError("smtp down")
                sent.append((to, subject))

        ids: list[str] = []
        self.svc.save_preferences(CIT1, self.repo, in_app=True, email=True, muted_kinds=[])
        for i in range(3):
            self.svc.notify(self.repo, "c1", "complaint.created", f"t{i}", "b", dedupe_key=f"k{i}", want_email_job=ids)
        ok = NotificationService(self.clock, Sender(False)).deliver_email(self.repo, ids[0], "a@b.co")
        self.assertEqual((ok.status, sent), ("delivered", [("a@b.co", "t0")]))
        again = NotificationService(self.clock, Sender(False)).deliver_email(self.repo, ids[0], "a@b.co")
        self.assertEqual(len(sent), 1)  # not re-sent
        self.assertEqual(NotificationService(self.clock, Sender(True)).deliver_email(self.repo, ids[1], "a@b.co").status, "failed")
        self.assertEqual(NotificationService(self.clock, Sender(False)).deliver_email(self.repo, ids[2], None).status, "failed")  # no address: cannot be delivered
        self.assertIs(again.status, "delivered")

    def test_read_state_and_ownership(self):
        rec, _ = self.svc.notify(self.repo, "c1", "complaint.created", "t", "b")
        self.assertEqual(len(self.svc.list_for(CIT1, self.repo, unread_only=True)), 1)
        with self.assertRaises(NotFound):
            self.svc.mark_read(CIT2, self.repo, rec.id)
        self.svc.mark_read(CIT1, self.repo, rec.id)
        self.assertEqual(self.svc.list_for(CIT1, self.repo, unread_only=True), [])
        self.svc.notify(self.repo, "c1", "complaint.assigned", "t2", "b")
        self.svc.notify(self.repo, "c1", "complaint.escalated", "t3", "b")
        self.assertEqual(self.svc.mark_all_read(CIT1, self.repo), 2)
        self.assertEqual(self.repo.unread_count("c1"), 0)
        self.assertEqual(self.svc.preferences(CIT1, self.repo), NotificationPreference("c1"))


if __name__ == "__main__":
    unittest.main()
