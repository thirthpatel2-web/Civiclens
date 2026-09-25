"""The workflow engine's control flow - pure, against a tiny in-memory fake session (the engine
only ever calls session.get/add/flush), matching this codebase's in-memory-doubles convention
rather than needing a real database to test ordering/retry/branch/approval logic. See
tests/integration/test_workflow_engine_live.py for the version that stores real rows in Postgres.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from app.db.models.interop_platform import (
    WorkflowStepExecution,
)
from app.interop.workflow.engine import StepSpec, WorkflowEngine, define_workflow


class _FakeSession:
    def __init__(self) -> None:
        self._store: dict[tuple[type, str], object] = {}
        self.step_executions: list[WorkflowStepExecution] = []

    def add(self, obj) -> None:
        if isinstance(obj, WorkflowStepExecution):
            self.step_executions.append(obj)
            return
        pk_name = obj.__mapper__.primary_key[0].name
        self._store[(type(obj), getattr(obj, pk_name))] = obj

    def get(self, cls, pk):
        return self._store.get((cls, pk))

    def flush(self) -> None:
        pass


class WorkflowEngineTests(unittest.TestCase):
    def setUp(self):
        self.session = _FakeSession()
        self.engine = WorkflowEngine(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))

    def test_steps_run_in_the_stored_order(self):
        calls: list[str] = []
        define_workflow(self.session, workflow_id="wf-order", name="Order test", steps=[StepSpec("a"), StepSpec("b"), StepSpec("c")])
        registry = {name: (lambda ctx, n=name: calls.append(n) or {}) for name in "abc"}
        execution = self.engine.start(self.session, workflow_id="wf-order", correlation_id="c-1", context={}, step_registry=registry)
        self.assertEqual(calls, ["a", "b", "c"])
        self.assertEqual(execution.status, "completed")

    def test_context_updates_from_one_step_are_visible_to_the_next(self):
        define_workflow(self.session, workflow_id="wf-ctx", name="Context test", steps=[StepSpec("produce"), StepSpec("consume")])
        seen = {}
        registry = {
            "produce": lambda ctx: {"value": 42},
            "consume": lambda ctx: seen.update(value=ctx.get("value")) or {},
        }
        self.engine.start(self.session, workflow_id="wf-ctx", correlation_id="c-1", context={}, step_registry=registry)
        self.assertEqual(seen["value"], 42)

    def test_unknown_step_id_fails_the_execution_immediately(self):
        define_workflow(self.session, workflow_id="wf-missing", name="Missing step", steps=[StepSpec("nope")])
        execution = self.engine.start(self.session, workflow_id="wf-missing", correlation_id="c-1", context={}, step_registry={})
        self.assertEqual(execution.status, "failed")

    def test_on_failure_fail_stops_the_whole_execution(self):
        define_workflow(self.session, workflow_id="wf-fail", name="Fail test", steps=[StepSpec("a"), StepSpec("b", on_failure="fail"), StepSpec("c")])
        calls = []
        registry = {"a": lambda ctx: calls.append("a") or {}, "b": lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")), "c": lambda ctx: calls.append("c") or {}}
        execution = self.engine.start(self.session, workflow_id="wf-fail", correlation_id="c-1", context={}, step_registry=registry)
        self.assertEqual(execution.status, "failed")
        self.assertEqual(calls, ["a"])  # "c" never ran

    def test_on_failure_skip_continues_past_the_failing_step(self):
        define_workflow(self.session, workflow_id="wf-skip", name="Skip test", steps=[StepSpec("a", on_failure="skip"), StepSpec("b")])
        calls = []
        registry = {"a": lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")), "b": lambda ctx: calls.append("b") or {}}
        execution = self.engine.start(self.session, workflow_id="wf-skip", correlation_id="c-1", context={}, step_registry=registry)
        self.assertEqual(execution.status, "completed")
        self.assertEqual(calls, ["b"])

    def test_on_failure_branch_jumps_to_the_named_step(self):
        define_workflow(self.session, workflow_id="wf-branch", name="Branch test", steps=[StepSpec("a", on_failure="branch:recovery"), StepSpec("normal_path"), StepSpec("recovery")])
        calls = []
        registry = {
            "a": lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")),
            "normal_path": lambda ctx: calls.append("normal_path") or {},
            "recovery": lambda ctx: calls.append("recovery") or {},
        }
        execution = self.engine.start(self.session, workflow_id="wf-branch", correlation_id="c-1", context={}, step_registry=registry)
        self.assertEqual(execution.status, "completed")
        self.assertEqual(calls, ["recovery"])  # jumped past normal_path entirely

    def test_retry_reattempts_up_to_max_attempts_before_giving_up(self):
        define_workflow(self.session, workflow_id="wf-retry", name="Retry test", steps=[StepSpec("flaky", retry_max_attempts=3)])
        attempts = []

        def flaky(ctx):
            attempts.append(len(attempts) + 1)
            if len(attempts) < 3:
                raise RuntimeError("not yet")
            return {"succeeded_on_attempt": len(attempts)}

        execution = self.engine.start(self.session, workflow_id="wf-retry", correlation_id="c-1", context={}, step_registry={"flaky": flaky})
        self.assertEqual(execution.status, "completed")
        self.assertEqual(attempts, [1, 2, 3])
        self.assertEqual(execution.context["succeeded_on_attempt"], 3)

    def test_retry_exhausted_fails_the_execution(self):
        define_workflow(self.session, workflow_id="wf-retry-fail", name="Retry exhausted", steps=[StepSpec("always_fails", retry_max_attempts=2)])
        attempts = []
        execution = self.engine.start(self.session, workflow_id="wf-retry-fail", correlation_id="c-1", context={}, step_registry={"always_fails": lambda ctx: attempts.append(1) or (_ for _ in ()).throw(RuntimeError("nope"))})
        self.assertEqual(execution.status, "failed")
        self.assertEqual(len(attempts), 2)

    def test_condition_key_skips_a_step_without_running_it(self):
        define_workflow(self.session, workflow_id="wf-cond", name="Conditional test", steps=[StepSpec("gated", condition_key="should_run"), StepSpec("always")])
        calls = []
        registry = {"gated": lambda ctx: calls.append("gated") or {}, "always": lambda ctx: calls.append("always") or {}}
        execution = self.engine.start(self.session, workflow_id="wf-cond", correlation_id="c-1", context={"should_run": False}, step_registry=registry)
        self.assertEqual(execution.status, "completed")
        self.assertEqual(calls, ["always"])  # "gated" was skipped, never called

    def test_condition_key_true_runs_the_step_normally(self):
        define_workflow(self.session, workflow_id="wf-cond2", name="Conditional true", steps=[StepSpec("gated", condition_key="should_run")])
        calls = []
        execution = self.engine.start(self.session, workflow_id="wf-cond2", correlation_id="c-1", context={"should_run": True}, step_registry={"gated": lambda ctx: calls.append("gated") or {}})
        self.assertEqual(calls, ["gated"])
        self.assertEqual(execution.status, "completed")

    def test_manual_approval_pauses_and_resume_continues(self):
        define_workflow(self.session, workflow_id="wf-approve", name="Approval test", steps=[StepSpec("gate", requires_approval=True), StepSpec("after")])
        calls = []
        registry = {"gate": lambda ctx: calls.append("gate") or {}, "after": lambda ctx: calls.append("after") or {}}
        execution = self.engine.start(self.session, workflow_id="wf-approve", correlation_id="c-1", context={}, step_registry=registry)
        self.assertEqual(execution.status, "waiting_approval")
        self.assertEqual(calls, [])  # nothing ran yet - the gate itself hasn't executed

        resumed = self.engine.resume(self.session, execution_id=execution.execution_id, step_registry=registry, approve_step="gate")
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(calls, ["gate", "after"])

    def test_resuming_a_non_waiting_execution_is_refused(self):
        define_workflow(self.session, workflow_id="wf-noop", name="No approval needed", steps=[StepSpec("a")])
        execution = self.engine.start(self.session, workflow_id="wf-noop", correlation_id="c-1", context={}, step_registry={"a": lambda ctx: {}})
        self.assertEqual(execution.status, "completed")
        with self.assertRaises(ValueError):
            self.engine.resume(self.session, execution_id=execution.execution_id, step_registry={"a": lambda ctx: {}})

    def test_timeout_is_detected_after_the_step_returns(self):
        import time

        define_workflow(self.session, workflow_id="wf-timeout", name="Timeout test", steps=[StepSpec("slow", timeout_seconds=0)])

        def slow(ctx):
            time.sleep(0.05)
            return {}

        execution = self.engine.start(self.session, workflow_id="wf-timeout", correlation_id="c-1", context={}, step_registry={"slow": slow})
        self.assertEqual(execution.status, "failed")
        self.assertTrue(any("timeout" in (se.error_message or "").lower() or "budget" in (se.error_message or "") for se in self.session.step_executions))

    def test_every_step_attempt_is_recorded_with_a_real_history(self):
        define_workflow(self.session, workflow_id="wf-history", name="History test", steps=[StepSpec("flaky", retry_max_attempts=2)])
        self.engine.start(self.session, workflow_id="wf-history", correlation_id="c-1", context={}, step_registry={"flaky": lambda ctx: (_ for _ in ()).throw(RuntimeError("x"))})
        statuses = [se.status for se in self.session.step_executions]
        self.assertEqual(statuses, ["failed", "failed"])  # both attempts recorded, no history erased

    def test_starting_an_unknown_or_inactive_workflow_raises(self):
        with self.assertRaises(ValueError):
            self.engine.start(self.session, workflow_id="does-not-exist", correlation_id="c-1", context={}, step_registry={})


if __name__ == "__main__":
    unittest.main()
