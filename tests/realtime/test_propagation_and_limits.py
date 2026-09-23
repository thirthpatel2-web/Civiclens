"""Real-time propagation end to end (domain action -> bus -> manager -> sockets), session-bound sockets, and Redis-backed limits (fake client)."""

import asyncio
import logging
import tempfile
import threading
import unittest
from pathlib import Path

from app.core.exceptions import AuthenticationFailed, NotFound, PermissionDenied, RateLimited
from app.core.rate_limit import FailureThrottle, SlidingWindowLimiter, ThrottlePolicy
from app.core.redis_limits import (
    RedisFailureThrottle,
    RedisFixedWindowLimiter,
    ResilientLimiter,
    ResilientThrottle,
)
from app.core.security import hash_token
from app.db.schema_check import check, expected_head
from app.realtime.events import DomainEvent
from app.realtime.websocket_manager import LocalEventBus, WebSocketManager
from app.services.complaint_status import ComplaintStatus as S
from app.workers.redis_backend import RedisEventBus
from tests.end_to_end.test_full_flow import PW, Sys
from tests.support_env import ADMIN, CIT, CIT2, OFF_R1, OFF_W1, Env


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


class Sock:
    def __init__(self, fail=False):
        self.messages, self.closed_with, self.fail = [], None, fail

    async def send_json(self, data):
        if self.fail:
            raise ConnectionError("gone")
        self.messages.append(data)

    async def close(self, code=1000):
        self.closed_with = code


class PropagationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = Env()
        self.manager = WebSocketManager()
        self.bus = LocalEventBus(self.manager)
        self.bus.bind_loop(asyncio.get_running_loop())
        self.env.fx.bus = self.bus
        self.socks = {n: Sock() for n in ("cit", "cit2", "off_r", "off_w", "admin")}
        for name, ctx in (("cit", CIT), ("cit2", CIT2), ("off_r", OFF_R1), ("off_w", OFF_W1), ("admin", ADMIN)):
            await self.manager.connect(self.socks[name], ctx)

    async def settle(self):
        for _ in range(20):
            await asyncio.sleep(0.01)

    async def test_status_change_reaches_only_the_authorised_sockets_and_never_leaks_internal_detail(self):
        c = await asyncio.to_thread(self.env.create)  # services are synchronous: run them in a worker thread like FastAPI does
        await self.settle()
        for s in self.socks.values():
            s.messages.clear()
        await asyncio.to_thread(self.env.officer.update_status, OFF_R1, c.id, S.UNDER_REVIEW, "internal secret remark")
        await self.settle()
        got = {n: [m["type"] for m in s.messages] for n, s in self.socks.items()}
        self.assertIn("complaint.status_changed", got["cit"])  # the owning citizen
        self.assertIn("complaint.status_changed", got["off_r"])  # the department's officer
        self.assertIn("complaint.status_changed", got["admin"])
        self.assertEqual(got["cit2"], [])  # another citizen: nothing
        self.assertEqual(got["off_w"], [])  # another department: nothing
        self.assertNotIn("internal secret remark", repr(self.socks["cit"].messages))  # citizens never receive staff-only detail
        self.assertIn("internal secret remark", repr(self.socks["off_r"].messages) + repr(self.socks["admin"].messages) or "")

    async def test_new_complaint_notifies_its_owner_and_the_department_in_real_time(self):
        await asyncio.to_thread(self.env.create)
        await self.settle()
        self.assertTrue({m["type"] for m in self.socks["cit"].messages} >= {"complaint.created", "notification.created"})
        self.assertIn("complaint.created", [m["type"] for m in self.socks["off_r"].messages])
        self.assertEqual(self.socks["off_w"].messages, [])
        self.assertEqual(self.socks["cit2"].messages, [])

    async def test_a_dead_socket_is_dropped_without_affecting_the_others(self):
        dead = Sock(fail=True)
        await self.manager.connect(dead, CIT)
        before = self.manager.connection_count()
        await asyncio.to_thread(self.env.create)
        await self.settle()
        self.assertEqual(self.manager.connection_count(), before - 1)
        self.assertTrue(self.socks["cit"].messages)

    async def test_redis_bus_subscriber_path_delivers_through_the_same_manager(self):
        redis = TtlFakeRedis()
        publisher = RedisEventBus(redis)
        loop = asyncio.get_running_loop()
        stop = threading.Event()
        threading.Thread(target=publisher.listen, args=(lambda ev: asyncio.run_coroutine_threadsafe(self.manager.deliver(ev), loop), stop), daemon=True).start()
        try:
            c = await asyncio.to_thread(self.env.create)
            ev = DomainEvent("complaint.status_changed", {"reference": c.reference, "to": "resolved"}, {"remarks": "x"}, owner_id=c.citizen_id, department_code=c.department_code, complaint_id=c.id)
            await asyncio.to_thread(publisher.publish, ev)  # e.g. a WORKER process publishing
            for _ in range(60):
                await asyncio.sleep(0.05)
                if any(m["type"] == "complaint.status_changed" for m in self.socks["cit"].messages):
                    break
            self.assertTrue(any(m["type"] == "complaint.status_changed" and m["data"].get("to") == "resolved" for m in self.socks["cit"].messages))
            self.assertFalse(any(m["type"] == "complaint.status_changed" for m in self.socks["cit2"].messages))
        finally:
            stop.set()

    async def test_logout_closes_that_sessions_sockets_and_the_sweep_drops_expired_sessions(self):
        s1, s2 = Sock(), Sock()
        await self.manager.connect(s1, CIT, hash_token("tok-A"))
        await self.manager.connect(s2, CIT, hash_token("tok-B"))
        self.assertEqual(await self.manager.drop_session(hash_token("tok-A")), 1)
        self.assertEqual((s1.closed_with, s2.closed_with), (4401, None))

        async def valid(h):
            return h != hash_token("tok-B")

        self.assertEqual(await self.manager.sweep(valid), 1)
        self.assertEqual(s2.closed_with, 4401)
        self.assertEqual(await self.manager.sweep(valid), 0)

    async def test_sync_handlers_can_request_a_drop_through_the_bound_loop(self):
        s = Sock()
        self.manager.bind_loop(asyncio.get_running_loop())
        await self.manager.connect(s, CIT, hash_token("tok-C"))
        await asyncio.to_thread(self.manager.drop_session_threadsafe, hash_token("tok-C"))
        await self.settle()
        self.assertEqual(s.closed_with, 4401)


class TtlFakeRedis:
    """Emulates the few commands used (INCR/EXPIRE/TTL/SET NX EX/DELETE/PUBLISH/pubsub) with a controllable clock. NOT Redis itself."""

    def __init__(self):
        self.now, self.kv, self.exp, self.channel, self.down = 0.0, {}, {}, [], False

    def _live(self, k):
        if k in self.exp and self.exp[k] <= self.now:
            self.kv.pop(k, None)
            self.exp.pop(k, None)
        return k in self.kv

    def _chk(self):
        if self.down:
            raise ConnectionError("redis down")

    def incr(self, k):
        self._chk()
        self._live(k)
        self.kv[k] = int(self.kv.get(k, 0)) + 1
        return self.kv[k]

    def expire(self, k, s):
        self._chk()
        self.exp[k] = self.now + s

    def ttl(self, k):
        self._chk()
        if not self._live(k):
            return -2
        return int(self.exp[k] - self.now) if k in self.exp else -1

    def set(self, k, v, nx=False, ex=None):
        self._chk()
        if nx and self._live(k):
            return None
        self.kv[k] = v
        if ex:
            self.exp[k] = self.now + ex
        return True

    def delete(self, k):
        self._chk()
        self.kv.pop(k, None)
        self.exp.pop(k, None)

    def publish(self, ch, msg):
        self.channel.append(msg)

    def pubsub(self, ignore_subscribe_messages=True):
        r = self

        class PS:
            def subscribe(self, ch): pass
            def get_message(self, timeout=0):
                return {"type": "message", "data": r.channel.pop(0)} if r.channel else None

        return PS()


class RedisLimitTests(unittest.TestCase):
    def test_fixed_window_limit_is_shared_by_two_processes_and_resets_after_the_window(self):
        r = TtlFakeRedis()
        a, b = RedisFixedWindowLimiter(r, "expensive", 3, 60), RedisFixedWindowLimiter(r, "expensive", 3, 60)  # two web processes, one Redis
        for lim in (a, b, a):
            lim.hit("1.2.3.4")
        with self.assertRaises(RateLimited) as cm:
            b.hit("1.2.3.4")
        self.assertTrue(1 <= cm.exception.retry_after_seconds <= 60)
        b.hit("9.9.9.9")  # other keys are independent
        r.now += 61
        a.hit("1.2.3.4")  # window over

    def test_failure_throttle_locks_out_across_processes_and_success_clears_it(self):
        r = TtlFakeRedis()
        pol = ThrottlePolicy(max_failures=3, window_seconds=60, lockout_seconds=120)
        a, b = RedisFailureThrottle(r, "login", pol), RedisFailureThrottle(r, "login", pol)
        for t in (a, b, a):
            t.check("u@example.com")
            t.record_failure("u@example.com")
        with self.assertRaises(RateLimited) as cm:
            b.check("u@example.com")
        self.assertGreater(cm.exception.retry_after_seconds, 100)
        r.now += 121
        b.check("u@example.com")  # lock expired
        b.record_failure("v@example.com")
        b.record_success("v@example.com")
        for _ in range(2):
            b.record_failure("v@example.com")
        b.check("v@example.com")  # counter was cleared by the success

    def test_a_key_left_without_ttl_by_a_crash_is_healed(self):
        r = TtlFakeRedis()
        r.kv["civiclens:rl:x:k"] = 2
        RedisFixedWindowLimiter(r, "x", 5, 30).hit("k")
        self.assertEqual(r.ttl("civiclens:rl:x:k"), 30)

    def test_redis_outage_falls_back_to_in_process_limits_and_reports_degraded(self):
        r = TtlFakeRedis()
        lim = ResilientLimiter(RedisFixedWindowLimiter(r, "e", 2, 60), SlidingWindowLimiter(2, 60))
        lim.hit("k")
        r.down = True
        lim.hit("k")
        self.assertTrue(lim.degraded)
        lim.hit("k")  # the local limiter starts from zero (it never saw the Redis hit): a documented, bounded relaxation
        with self.assertRaises(RateLimited):
            lim.hit("k")  # ...but it does limit: the outage is not fail-open
        thr = ResilientThrottle(RedisFailureThrottle(r, "login", ThrottlePolicy(2, 60, 60)), FailureThrottle(ThrottlePolicy(2, 60, 60)))
        thr.record_failure("u")
        thr.record_failure("u")
        with self.assertRaises(RateLimited):
            thr.check("u")
        r.down = False
        lim2 = ResilientLimiter(RedisFixedWindowLimiter(r, "e2", 1, 60), SlidingWindowLimiter(1, 60))
        lim2.hit("z")
        self.assertFalse(lim2.degraded)


class SchemaCheckTests(unittest.TestCase):
    def test_expected_head_is_the_last_revision_of_the_real_chain(self):
        self.assertEqual(expected_head(), "0011")

    def test_branched_or_broken_chains_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.py").write_text('revision = "1"\ndown_revision = None\n')
            (Path(d) / "b.py").write_text('revision = "2"\ndown_revision = "1"\n')
            (Path(d) / "c.py").write_text('revision = "3"\ndown_revision = "1"\n')
            with self.assertRaises(ValueError):
                expected_head(Path(d))

    def test_check_reports_ok_behind_and_unknown(self):
        class Row(tuple):
            pass

        class Session:
            def __init__(self, row=None, fail=False): self.row, self.fail = row, fail
            def execute(self, q):
                if self.fail:
                    raise RuntimeError("no such table")
                class R:
                    def first(s2): return self.row
                return R()

        self.assertEqual(check(Session(Row(("0011",))))["status"], "ok")
        behind = check(Session(Row(("0004",))))
        self.assertEqual((behind["status"], behind["current"], behind["expected"]), ("behind", "0004", "0011"))
        self.assertEqual(check(Session(fail=True))["status"], "unknown")


class SessionAndResetTests(unittest.TestCase):
    def test_mobile_sessions_outlive_web_sessions_and_both_are_revocable(self):
        s = Sys()
        s.register("m@example.com")
        web = s._uow(lambda u: s.c.auth_for(u).login("m@example.com", PW))
        mob = s._uow(lambda u: s.c.auth_for(u).login("m@example.com", PW, client="mobile"))
        s.clock.advance(days=3)
        with self.assertRaises(AuthenticationFailed):
            s.auth(web.session_token)  # web: 12 h absolute
        self.assertEqual(s.auth(mob.session_token).user_id, web.context.user_id)  # mobile: still valid after 3 days
        self.assertTrue(s._uow(lambda u: s.c.auth_for(u).is_session_active(hash_token(mob.session_token))))
        s._uow(lambda u: s.c.auth_for(u).logout(mob.session_token))
        self.assertFalse(s._uow(lambda u: s.c.auth_for(u).is_session_active(hash_token(mob.session_token))))
        s.clock.advance(days=61)
        mob2 = s._uow(lambda u: s.c.auth_for(u).login("m@example.com", PW, client="mobile"))
        s.clock.advance(days=61)
        with self.assertRaises(AuthenticationFailed):
            s.auth(mob2.session_token)  # 60-day absolute cap

    def test_admin_assisted_reset_is_one_time_audited_scoped_and_never_exposes_a_password(self):
        s = Sys()
        c = s.c
        user = s.register("nomail@example.com")
        root = s._uow(lambda u: c.auth_for(u).bootstrap_first_admin("root@gov.example", PW, "Root", provided_token="t" * 10, expected_token="t" * 10))
        first = s.login("root@gov.example")
        s.enrol_mfa(first.context, "root@gov.example", first.session_token)
        s.clock.advance(seconds=30)
        admin = s.login("root@gov.example", otp=s.otp("root@gov.example")).context
        r = c.admin.issue_password_reset(admin, user.id)
        self.assertTrue(len(r["token"]) >= 30 and "password" not in r)
        old = s.login("nomail@example.com")
        s._uow(lambda u: c.auth_for(u).reset_password(r["token"], "brand-new-passphrase-1"), commit_on_error=True)
        with self.assertRaises(AuthenticationFailed):
            s.auth(old.session_token)  # existing sessions are revoked
        with self.assertRaises(AuthenticationFailed):
            s._uow(lambda u: c.auth_for(u).reset_password(r["token"], "another-passphrase-22"), commit_on_error=True)  # single use
        self.assertTrue(s._uow(lambda u: c.auth_for(u).login("nomail@example.com", "brand-new-passphrase-1")))
        with self.assertRaises(NotFound):
            c.admin.issue_password_reset(admin, "no-such-user")
        acts = [e.action for e in s.stores.audit]
        self.assertIn("admin.password_reset_issued", acts)
        self.assertIn("auth.password_reset_issued", acts)
        self.assertNotIn(r["token"], repr([e.metadata for e in s.stores.audit]))
        # a department-bound admin or officer cannot reset an administrator
        with self.assertRaises(PermissionDenied):
            c.admin.issue_password_reset(OFF_R1, user.id)
        _ = root

    def test_admin_assisted_reset_for_a_deactivated_user_raises_not_found_not_a_crash(self):
        # Regression: auth_service.issue_reset_for_user() referenced NotFound without importing it,
        # so this path (target exists but is deactivated - admin_service's own existence check does
        # not catch this) raised an unhandled NameError instead of the intended 404-equivalent.
        s = Sys()
        c = s.c
        user = s.register("deactivated@example.com")
        root = s._uow(lambda u: c.auth_for(u).bootstrap_first_admin("root2@gov.example", PW, "Root", provided_token="t" * 10, expected_token="t" * 10))
        first = s.login("root2@gov.example")
        s.enrol_mfa(first.context, "root2@gov.example", first.session_token)
        s.clock.advance(seconds=30)
        admin = s.login("root2@gov.example", otp=s.otp("root2@gov.example")).context
        c.admin.set_user_active(admin, user.id, False)
        with self.assertRaises(NotFound):
            c.admin.issue_password_reset(admin, user.id)
        _ = root


if __name__ == "__main__":
    unittest.main()
