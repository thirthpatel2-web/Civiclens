import logging
import unittest
from datetime import timedelta

from app.core.exceptions import DependencyUnavailable
from app.services.ports import NotificationPreference
from app.workers.queue import JobService, PermanentJobError
from app.workers.scheduler import SchedulerService, TaskSpec
from tests.support import FakeClock
from tests.support_mem import MemQueueBackend, Stores, uow_factory


def setUpModule():
    logging.disable(logging.CRITICAL)  # handlers deliberately log tracebacks


def tearDownModule():
    logging.disable(logging.NOTSET)


class JobTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.stores, self.backend = FakeClock(), Stores(), MemQueueBackend()
        self.calls, self.factory = [], uow_factory(self.stores)
        self.svc = JobService(self.factory, self.backend, {"echo": self._echo, "boom": self._boom, "bad": self._bad}, clock=self.clock, max_attempts=3)

    def _echo(self, payload, job):
        self.calls.append(payload)
        return {"ok": payload["n"]}

    def _boom(self, payload, job):
        raise RuntimeError("temporary failure password=hunter2")

    def _bad(self, payload, job):
        raise PermanentJobError("payload invalid")

    def enqueue(self, kind="echo", key="k1", **payload):
        with self.factory() as uow:
            job, created = self.svc.enqueue(uow, kind, payload or {"n": 1}, key)
            uow.commit()
        self.svc.dispatch([job])
        return job, created

    def test_enqueue_is_idempotent_by_key(self):
        a, created_a = self.enqueue()
        b, created_b = self.enqueue()
        self.assertEqual((created_a, created_b, a.id == b.id), (True, False, True))
        self.assertEqual(len(self.stores.jobs), 1)

    def test_success_records_result_and_only_runs_once_even_if_pushed_twice(self):
        job, _ = self.enqueue(n=7)
        self.backend.push(job.id, self.clock.now)  # duplicate delivery
        res = self.svc.drain("w1")
        self.assertEqual([(r.status, r.attempts) for r in res], [("succeeded", 1)])
        self.assertEqual(self.calls, [{"n": 7}])
        self.assertEqual(self.stores.jobs[job.id].result, {"ok": 7})

    def test_retry_with_backoff_then_dead_and_secrets_are_redacted(self):
        job, _ = self.enqueue("boom", "k-boom")
        self.assertEqual(self.svc.run_once("w1").status, "retrying")  # attempt 1 failed, rescheduled
        self.assertIsNone(self.svc.run_once("w1"))  # not due yet (5s backoff)
        self.clock.advance(seconds=5)
        self.assertEqual(self.svc.run_once("w1").status, "retrying")
        self.clock.advance(seconds=30)
        last = self.svc.run_once("w1")
        self.assertEqual((last.status, last.attempts), ("dead", 3))
        stored = self.stores.jobs[job.id]
        self.assertNotIn("hunter2", stored.error)
        self.assertIn("RuntimeError", stored.error)

    def test_permanent_error_goes_straight_to_dead_and_unknown_kind_too(self):
        self.enqueue("bad", "k-bad")
        self.enqueue("no-such-handler", "k-x")
        res = {r.kind: r for r in self.svc.drain("w1")}
        self.assertEqual((res["bad"].status, res["bad"].attempts), ("dead", 1))
        self.assertEqual(res["no-such-handler"].status, "dead")
        self.assertIn("no handler", res["no-such-handler"].error)

    def test_redis_outage_leaves_pending_then_reconciles(self):
        self.backend.up = False
        job, _ = self.enqueue()
        self.assertEqual(self.stores.jobs[job.id].status, "pending")
        self.assertIsNone(self.svc.run_once("w1"))  # worker cannot reach Redis: no crash
        self.backend.up = True
        self.assertEqual(self.svc.requeue_orphans(older_than_seconds=0), 1)
        self.assertEqual(self.svc.drain("w1")[0].status, "succeeded")

    def test_stats_report_queue_and_workers_or_unreachable(self):
        self.enqueue()
        self.svc.run_once("worker-A")
        s = self.svc.stats()
        self.assertEqual(s["by_status"], {"succeeded": 1})
        self.assertTrue(s["backend_reachable"])
        self.assertIn("worker-A", s["workers"])
        self.backend.up = False
        down = self.svc.stats()
        self.assertEqual((down["backend_reachable"], down["workers"]), (False, {}))
        self.assertIsInstance(DependencyUnavailable("x"), Exception)

    def test_delayed_job_waits_for_run_at(self):
        with self.factory() as uow:
            job, _ = self.svc.enqueue(uow, "echo", {"n": 2}, "later", run_at=self.clock.now + timedelta(minutes=10))
            uow.commit()
        self.svc.dispatch([job])
        self.assertIsNone(self.svc.run_once("w1"))
        self.clock.advance(minutes=11)
        self.assertEqual(self.svc.run_once("w1").status, "succeeded")


class MemState:
    def __init__(self): self.d = {}
    def last_run(self, n): return self.d.get(n)
    def set_last_run(self, n, at): self.d[n] = at


class MemLock:
    def __init__(self): self.held, self.deny = set(), set()
    def acquire(self, name, ttl): return name not in self.deny and not (name in self.held) and (self.held.add(name) or True)
    def release(self, name): self.held.discard(name)


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.state, self.lock, self.runs = FakeClock(), MemState(), MemLock(), []
        self.tasks = [TaskSpec("fast", timedelta(minutes=1), lambda now: self.runs.append("fast") or {"n": 1}),
                      TaskSpec("slow", timedelta(hours=1), lambda now: self.runs.append("slow")),
                      TaskSpec("broken", timedelta(minutes=1), self._broken)]  # fmt: skip
        self.sched = SchedulerService(self.tasks, self.state, self.lock, self.clock)

    def _broken(self, now):
        self.runs.append("broken")
        raise ValueError("boom api_key=sk-secret")

    def test_first_tick_runs_everything_and_failure_is_isolated_and_redacted(self):
        runs = {r.name: r for r in self.sched.tick()}
        self.assertEqual(set(runs), {"fast", "slow", "broken"})
        self.assertTrue(runs["fast"].ok and runs["fast"].summary == {"n": 1})
        self.assertFalse(runs["broken"].ok)
        self.assertNotIn("sk-secret", runs["broken"].error)

    def test_interval_respected(self):
        self.sched.tick()
        self.runs.clear()
        self.clock.advance(seconds=59)
        self.assertEqual(self.sched.tick(), [])
        self.clock.advance(seconds=2)
        self.assertEqual({r.name for r in self.sched.tick()}, {"fast", "broken"})
        self.clock.advance(hours=1)
        self.assertIn("slow", {r.name for r in self.sched.tick()})

    def test_lock_prevents_duplicate_execution_across_instances(self):
        self.lock.deny.add("scheduler:fast")
        names = {r.name for r in self.sched.tick()}
        self.assertNotIn("fast", names)
        self.assertNotIn("fast", self.runs)
        self.assertEqual(self.lock.held, set())  # locks released

    def test_duplicate_task_names_rejected(self):
        with self.assertRaises(ValueError):
            SchedulerService([self.tasks[0], self.tasks[0]], self.state, self.lock)


if __name__ == "__main__":
    unittest.main()
