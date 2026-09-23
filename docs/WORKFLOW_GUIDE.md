# Workflow guide — the configurable workflow engine

How to define and run a new cross-department workflow through `WorkflowEngine`
(`app/interop/workflow/engine.py`) — a generic step-sequence executor that knows nothing about
identity resolution or document exchange, only how to run an ordered list of named steps against a
registry of step functions. See `docs/INTEROPERABILITY.md`'s "Configurable workflows" section for
the architecture and its honestly-stated scope (the primary no-reupload entry point,
`InteropGatewayService.request_document_exchange`, remains separate, tested, production code — the
engine is a genuine additional path proven to drive the same real flow, not a replacement).

## The pieces

- **`WorkflowDefinition`** (`interop_workflow_definitions`) — a `workflow_id`, a `name`, a
  `version`, and `steps`: an ordered list of `StepSpec` dicts. This is *data*, editable without
  touching Python.
- **`StepSpec`** (`app/interop/workflow/engine.py`) — one step in that list:

  ```python
  @dataclass(frozen=True)
  class StepSpec:
      step_id: str
      on_failure: str = "fail"          # "fail" | "skip" | "branch:<step_id>"
      retry_max_attempts: int = 1
      timeout_seconds: int | None = None
      requires_approval: bool = False
      condition_key: str | None = None  # step is skipped (not run) when context[condition_key] is falsy
  ```

- **A step function** — `Callable[[dict], dict | None]`. Receives the execution's accumulated
  `context` dict, returns the updates to merge into it, or raises any exception to signal failure
  (the engine doesn't require a specific exception type). A **step registry** —
  `dict[str, StepFn]` — maps each `StepSpec.step_id` to its real function for one run.
- **`WorkflowExecution`** / **`WorkflowStepExecution`** — the real, inspectable run history: one
  execution row (`status`: `running` | `completed` | `failed` | `waiting_approval`,
  `current_step_index`, `context`) and one row **per attempt** of every step that actually ran (not
  a `pending`/`running` placeholder row for steps that never executed).

## What the engine actually does

- **Ordered steps**, run in the definition's stored order.
- **Conditional branches**: `condition_key` skips a step (the step function is never even called)
  when that context key is falsy; a step's `on_failure: "branch:<step_id>"` jumps execution to a
  named step on failure instead of stopping.
- **Retry policy**: `retry_max_attempts` re-invokes a failed step, with every attempt recorded as
  its own `WorkflowStepExecution` row.
- **Timeout**: `timeout_seconds`, detected once the step function *returns* — this engine has no
  preemptive interrupt, named honestly as detection, not true preemption.
- **Manual approval**: `requires_approval` pauses the execution (`status: "waiting_approval"`) until
  `WorkflowEngine.resume(session, execution_id=..., step_registry=..., approve_step=...)` is called,
  which records the approval in context (`context["_approved:<step_id>"] = True`) so the step
  doesn't immediately re-pause on itself.
- **Failure routing**: `on_failure` is `"fail"` (stop), `"skip"` (continue to the next step anyway —
  used for steps whose failure must never undo an already-completed exchange, like publishing an
  event or sending a notification), or `"branch:<step_id>"`.

## Defining a new workflow

1. **Write the step functions.** Build them from primitives the codebase already has and has
   already tested independently — the connector runtime, `IdentityResolutionService`, the canonical
   transform functions, `InteropGatewayService._document_quality` — the same discipline
   `app/interop/workflow/definitions.py` follows for `residence_certificate_verification`: this
   keeps a new workflow as *orchestration*, not new, unproven business logic.

2. **Declare the step list** as `StepSpec` objects:

   ```python
   MY_WORKFLOW_STEPS: list[StepSpec] = [
       StepSpec("resolve_identity"),
       StepSpec("request_consent", requires_approval=True),
       StepSpec("fetch_record", retry_max_attempts=2, timeout_seconds=10),
       StepSpec("publish_event", on_failure="skip"),
   ]
   ```

3. **Register the definition**, idempotently, the same way `register_default_workflows` does —
   call this from `app.main._seed_interop_demo_data` (or an equivalent app-startup hook) so it's
   real on every boot, not a one-off script:

   ```python
   def register_my_workflow(session: Session) -> None:
       define_workflow(session, workflow_id="my_workflow", name="My Workflow", steps=MY_WORKFLOW_STEPS)
   ```

4. **Build the step registry** — a function taking the session (and a clock, for testability) and
   returning `dict[str, StepFn]`, closures over that session so each step function can read/write
   real rows:

   ```python
   def build_my_workflow_step_registry(session: Session, *, clock=None) -> dict[str, StepFn]:
       def resolve_identity(ctx: dict) -> dict:
           ...
           return {"master_id": master_id}
       ...
       return {"resolve_identity": resolve_identity, "request_consent": request_consent, ...}
   ```

5. **Run it**:

   ```python
   engine = WorkflowEngine()
   execution = engine.start(session, workflow_id="my_workflow", correlation_id=correlation_id,
                             context={"application_no": application_no}, step_registry=registry)
   # if execution.status == "waiting_approval": ... later ...
   execution = engine.resume(session, execution_id=execution.execution_id, step_registry=registry, approve_step="request_consent")
   ```

6. **A context value must always be plain JSON** — `WorkflowExecution.context` is a `jsonb` column.
   Never merge a raw SQLAlchemy ORM row or a bare `datetime`/`date` object into it; extract plain
   fields (and `.isoformat()` any date) the way `fetch_document`/`_canonical_document_from_context`
   do for the existing workflow. Violating this corrupts the whole session on the next flush
   (`TypeError: Object of type X is not JSON serializable`, then a `PendingRollbackError` on every
   later query in that same session) — this was a real bug found and fixed during Phase 5.

7. **Register the two read routes' worth of visibility for free** —
   `GET /interop-gateway/workflows`, `GET /interop-gateway/workflow-executions`,
   `GET /interop-gateway/workflow-executions/{id}` already list every registered
   `WorkflowDefinition` and every `WorkflowExecution`/`WorkflowStepExecution`, generically — a new
   workflow needs no new API route to become visible.

8. **Test it** the way `tests/unit/test_workflow_engine.py` (pure — ordering, retry, branch, skip,
   conditional, manual-approval+resume, timeout, history) and
   `tests/integration/test_workflow_engine_live.py` (live DB — the real flow run through the engine
   end to end, including a genuine pause) test the existing one.

## The spec's own example

`residence_certificate_verification` (`app/interop/workflow/definitions.py`) is the completion
spec's Section 12 example, registered on every app start. Its nine steps — `resolve_identity`,
`request_consent` (a real manual gate, not a placeholder), `fetch_document` (retried, timed),
`validate_document`, `transform_data`, `deliver_document` (retried), `publish_event`,
`update_tracker`, `notify` (the last three `on_failure="skip"`) — are the reference implementation
for everything above.
