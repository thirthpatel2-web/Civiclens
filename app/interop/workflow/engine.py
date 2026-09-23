"""The workflow engine: executes a ``WorkflowDefinition``'s stored, ordered steps against a
registry of step functions - the engine itself never hard-codes what a workflow does, only how to
run one. Each step function is ``Callable[[dict], dict | None]``: it receives the execution's
accumulated context and returns the updates to merge into it (or raises to signal failure - any
exception, the engine doesn't require a specific type).

Real, not decorative, support for:
  - ordered steps (the stored list's order, followed exactly)
  - conditional branches: a step's ``condition_key`` skips it (without running the step function
    at all) when that context key is falsy; ``on_failure: "branch:<step_id>"`` jumps execution to
    a named step when this step fails, instead of stopping the whole run
  - retry policy: ``retry_max_attempts`` re-invokes the step function on failure, recording every
    attempt
  - timeout: ``timeout_seconds`` - detected after the step function returns (this engine has no
    preemptive interrupt; a step that runs long is flagged failed once it returns, not stopped
    mid-flight - named honestly, not claimed as true preemption)
  - manual approval: ``requires_approval`` pauses the execution (status ``waiting_approval``)
    until ``resume()`` is called with that approval recorded in the context
  - failure routing: ``on_failure`` is ``"fail"`` (stop the execution), ``"skip"`` (move to the
    next step anyway), or ``"branch:<step_id>"``

Every attempt of every step is recorded (``WorkflowStepExecution``), so a failed or branched
execution has a real, inspectable history - not just a final status.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.interop_platform import WorkflowDefinition, WorkflowExecution, WorkflowStepExecution

StepFn = Callable[[dict[str, Any]], dict[str, Any] | None]


@dataclass(frozen=True)
class StepSpec:
    step_id: str
    on_failure: str = "fail"  # "fail" | "skip" | "branch:<step_id>"
    retry_max_attempts: int = 1
    timeout_seconds: int | None = None
    requires_approval: bool = False
    condition_key: str | None = None  # if set, the step is skipped (not run) when context[condition_key] is falsy

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepSpec:
        return cls(
            step_id=data["step_id"], on_failure=data.get("on_failure", "fail"), retry_max_attempts=data.get("retry_max_attempts", 1),
            timeout_seconds=data.get("timeout_seconds"), requires_approval=data.get("requires_approval", False), condition_key=data.get("condition_key"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"step_id": self.step_id, "on_failure": self.on_failure, "retry_max_attempts": self.retry_max_attempts, "timeout_seconds": self.timeout_seconds, "requires_approval": self.requires_approval, "condition_key": self.condition_key}


def define_workflow(session: Session, *, workflow_id: str, name: str, steps: list[StepSpec], version: str = "1") -> WorkflowDefinition:
    """Upsert - re-defining an existing workflow_id updates it in place (a new version string is
    the caller's convention for tracking that; this doesn't version automatically)."""
    existing = session.get(WorkflowDefinition, workflow_id)
    step_dicts = [s.to_dict() for s in steps]
    if existing is not None:
        existing.name, existing.version, existing.steps, existing.active = name, version, step_dicts, True
        session.add(existing)
        return existing
    definition = WorkflowDefinition(workflow_id=workflow_id, name=name, version=version, steps=step_dicts, active=True, created_at=datetime.now(UTC))
    session.add(definition)
    return definition


class WorkflowEngine:
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))

    def start(self, session: Session, *, workflow_id: str, correlation_id: str, context: dict[str, Any], step_registry: dict[str, StepFn]) -> WorkflowExecution:
        definition = session.get(WorkflowDefinition, workflow_id)
        if definition is None or not definition.active:
            raise ValueError(f"No active workflow definition {workflow_id!r}")
        execution = WorkflowExecution(execution_id=str(uuid.uuid4()), workflow_id=workflow_id, correlation_id=correlation_id, status="running", current_step_index=0, context=dict(context), started_at=self._clock())
        session.add(execution)
        session.flush()
        return self._run(session, execution, definition, step_registry)

    def resume(self, session: Session, *, execution_id: str, step_registry: dict[str, StepFn], approve_step: str | None = None) -> WorkflowExecution:
        """``approve_step`` records the approval for the step currently waiting, so it doesn't
        immediately re-pause on the very step that was just approved."""
        execution = session.get(WorkflowExecution, execution_id)
        if execution is None:
            raise ValueError(f"No workflow execution {execution_id!r}")
        if execution.status != "waiting_approval":
            raise ValueError(f"Execution is {execution.status!r}, not waiting_approval")
        definition = session.get(WorkflowDefinition, execution.workflow_id)
        if approve_step:
            execution.context = {**execution.context, f"_approved:{approve_step}": True}
        execution.status = "running"
        return self._run(session, execution, definition, step_registry)

    def _run(self, session: Session, execution: WorkflowExecution, definition: WorkflowDefinition, step_registry: dict[str, StepFn]) -> WorkflowExecution:
        steps = [StepSpec.from_dict(d) for d in definition.steps]
        index_by_id = {s.step_id: i for i, s in enumerate(steps)}
        i = execution.current_step_index
        while i < len(steps):
            spec = steps[i]

            if spec.condition_key is not None and not execution.context.get(spec.condition_key):
                self._record_step(session, execution.execution_id, spec.step_id, i, "skipped", attempt=1, error_message=f"condition_key {spec.condition_key!r} was falsy")
                i += 1
                execution.current_step_index = i
                continue

            if spec.requires_approval and execution.context.get(f"_approved:{spec.step_id}") is not True:
                execution.status, execution.current_step_index = "waiting_approval", i
                session.add(execution)
                session.flush()
                return execution

            fn = step_registry.get(spec.step_id)
            if fn is None:
                self._record_step(session, execution.execution_id, spec.step_id, i, "failed", attempt=1, error_message=f"no step function registered for {spec.step_id!r}")
                execution.status, execution.finished_at = "failed", self._clock()
                session.add(execution)
                return execution

            outcome = self._run_step_with_retry(session, execution, spec, i, fn)
            if outcome in ("completed", "skipped"):
                i += 1
                execution.current_step_index = i
                continue

            # outcome == "failed"
            if spec.on_failure.startswith("branch:"):
                target = spec.on_failure.split(":", 1)[1]
                if target not in index_by_id:
                    execution.status, execution.finished_at = "failed", self._clock()
                    session.add(execution)
                    return execution
                i = index_by_id[target]
                execution.current_step_index = i
                continue
            execution.status, execution.finished_at = "failed", self._clock()
            session.add(execution)
            return execution

        execution.status, execution.finished_at = "completed", self._clock()
        session.add(execution)
        return execution

    def _run_step_with_retry(self, session: Session, execution: WorkflowExecution, spec: StepSpec, index: int, fn: StepFn) -> str:
        last_error: str | None = None
        for attempt in range(1, spec.retry_max_attempts + 1):
            t0 = time.monotonic()
            try:
                updates = fn(execution.context)
                elapsed = time.monotonic() - t0
                if spec.timeout_seconds is not None and elapsed > spec.timeout_seconds:
                    raise TimeoutError(f"step took {elapsed:.1f}s, over its {spec.timeout_seconds}s budget")
                execution.context = {**execution.context, **(updates or {})}
                self._record_step(session, execution.execution_id, spec.step_id, index, "completed", attempt=attempt)
                return "completed"
            except Exception as exc:  # noqa: BLE001 - a step's own exception type is never the engine's concern
                last_error = str(exc)
                self._record_step(session, execution.execution_id, spec.step_id, index, "failed", attempt=attempt, error_message=last_error)
        if spec.on_failure == "skip":
            self._record_step(session, execution.execution_id, spec.step_id, index, "skipped", attempt=spec.retry_max_attempts, error_message=last_error)
            return "skipped"
        return "failed"

    def _record_step(self, session: Session, execution_id: str, step_id: str, index: int, status: str, *, attempt: int, error_message: str | None = None) -> None:
        now = self._clock()
        session.add(WorkflowStepExecution(id=str(uuid.uuid4()), execution_id=execution_id, step_id=step_id, step_index=index, status=status, attempt=attempt, error_message=error_message, started_at=now, finished_at=now))
