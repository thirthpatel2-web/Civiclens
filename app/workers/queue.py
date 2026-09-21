"""Job queue: PostgreSQL is the source of truth, Redis is the transport (transactional outbox).

* ``enqueue`` writes a ``JobRecord`` inside the caller's transaction; a unique
  ``idempotency_key`` makes retries/replays harmless (the existing job is returned).
* ``dispatch`` (after commit) pushes job ids to the backend and marks them ``queued``.
  If the backend (Redis) is down the job simply stays ``pending`` - honestly visible in the
  admin monitor - and ``requeue_orphans`` (scheduler) pushes it once Redis is back.
* ``run_once`` pops a due id, runs the registered handler, records success/failure, retries
  with exponential backoff and ends in ``dead`` after ``max_attempts``.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.core.exceptions import DependencyUnavailable
from app.core.logging import redact
from app.services.ports import JobRecord
from app.services.uow import UowFactory

logger = logging.getLogger("civiclens.workers.queue")
BACKOFF_SECONDS = (5, 30, 120, 600)


class PermanentJobError(Exception):
    """Raise from a handler when retrying cannot help (bad payload, missing record)."""


class QueueBackend(Protocol):
    def push(self, job_id: str, run_at: datetime) -> None: ...
    def pop_due(self, now: datetime) -> str | None: ...
    def depth(self) -> int: ...
    def heartbeat(self, worker_id: str, now: datetime, info: dict[str, Any]) -> None: ...
    def workers(self, now: datetime, max_age_seconds: int = 60) -> dict[str, dict[str, Any]]: ...
    def ping(self) -> bool: ...


Handler = Callable[[dict[str, Any], JobRecord], dict[str, Any] | None]


@dataclass(frozen=True)
class RunResult:
    job_id: str
    kind: str
    status: str
    attempts: int
    error: str | None = None


class JobService:
    def __init__(self, uow_factory: UowFactory, backend: QueueBackend, handlers: dict[str, Handler] | None = None, *,
                 clock: Callable[[], datetime] | None = None, max_attempts: int = 3) -> None:  # fmt: skip
        self._uow, self._backend = uow_factory, backend
        self.handlers: dict[str, Handler] = dict(handlers or {})
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_attempts = max_attempts

    # ------------------------------------------------------------------ producer side
    def enqueue(self, uow: Any, kind: str, payload: dict[str, Any], idempotency_key: str, *, run_at: datetime | None = None) -> tuple[JobRecord, bool]:
        """Insert inside the caller's transaction. Returns ``(job, created)``."""
        now = self._clock()
        job = JobRecord(str(uuid.uuid4()), kind, payload, idempotency_key, max_attempts=self._max_attempts, run_at=run_at or now, created_at=now, updated_at=now)
        return uow.jobs.add_if_absent(job)

    def dispatch(self, jobs: list[JobRecord]) -> int:
        """After commit: push to the backend. Backend failure leaves jobs ``pending`` (never lost)."""
        pushed = 0
        for job in jobs:
            if job.status not in ("pending", "retrying", "queued"):
                continue
            try:
                self._backend.push(job.id, job.run_at)
            except DependencyUnavailable:
                logger.warning("queue backend unavailable; job %s stays pending", job.id)
                break
            with self._uow() as uow:
                fresh = uow.jobs.get(job.id)
                if fresh and fresh.status == "pending":  # 'retrying' stays visible as retrying while it waits in Redis
                    fresh.status, fresh.updated_at = "queued", self._clock()
                    uow.jobs.update(fresh)
                uow.commit()
            pushed += 1
        return pushed

    def requeue_orphans(self, older_than_seconds: int = 30) -> int:
        """Push ``pending`` jobs that never reached the backend (Redis outage / crash after commit)."""
        with self._uow() as uow:
            orphans = uow.jobs.list_orphans(self._clock() - timedelta(seconds=older_than_seconds))
        return self.dispatch(orphans)

    # ------------------------------------------------------------------ consumer side
    def run_once(self, worker_id: str) -> RunResult | None:
        now = self._clock()
        try:
            self._backend.heartbeat(worker_id, now, {"handlers": sorted(self.handlers)})
            job_id = self._backend.pop_due(now)
        except DependencyUnavailable:
            return None
        if job_id is None:
            return None
        with self._uow() as uow:
            job = uow.jobs.get(job_id)
            if job is None or job.status in ("succeeded", "dead", "running"):
                return None  # duplicate delivery of an already-handled job: idempotent no-op
            job.status, job.attempts, job.worker_id, job.updated_at, job.started_at = "running", job.attempts + 1, worker_id, now, now
            uow.jobs.update(job)
            uow.commit()
        handler = self.handlers.get(job.kind)
        error: str | None = None
        permanent = False
        result: dict[str, Any] | None = None
        try:
            if handler is None:
                raise PermanentJobError(f"no handler registered for job kind {job.kind!r}")
            result = handler(job.payload, job) or {}
        except PermanentJobError as exc:
            error, permanent = redact(str(exc))[:500], True
        except Exception as exc:  # handler failure must never kill the worker loop
            error = redact(f"{type(exc).__name__}: {exc}")[:500]
            logger.exception("job %s (%s) failed", job.id, job.kind)
        finished = self._clock()
        with self._uow() as uow:
            job = uow.jobs.get(job_id) or job
            job.updated_at = finished
            if error is None:
                job.status, job.result, job.error, job.finished_at = "succeeded", result, None, finished
            elif permanent or job.attempts >= job.max_attempts:
                job.status, job.error, job.finished_at = "dead", error, finished
            else:
                delay = BACKOFF_SECONDS[min(job.attempts - 1, len(BACKOFF_SECONDS) - 1)]
                job.status, job.error, job.run_at, job.finished_at = "retrying", error, finished + timedelta(seconds=delay), None
            uow.jobs.update(job)
            uow.commit()
        outcome = job.status
        if job.status == "retrying":
            self.dispatch([job])
        return RunResult(job.id, job.kind, outcome, job.attempts, error)

    def drain(self, worker_id: str, max_jobs: int = 100) -> list[RunResult]:
        out: list[RunResult] = []
        for _ in range(max_jobs):
            r = self.run_once(worker_id)
            if r is None:
                break
            out.append(r)
        return out

    def retry_dead(self, job_id: str) -> JobRecord:
        """Admin action: give a dead job a fresh set of attempts (idempotent handlers make this safe)."""
        with self._uow() as uow:
            job = uow.jobs.get(job_id)
            if job is None or job.status != "dead":
                from app.core.exceptions import ValidationFailed

                raise ValidationFailed("Only dead jobs can be retried.")
            job.status, job.attempts, job.error, job.run_at, job.finished_at, job.updated_at = "pending", 0, None, self._clock(), None, self._clock()
            uow.jobs.update(job)
            uow.commit()
        self.dispatch([job])
        return job

    # ------------------------------------------------------------------ monitoring
    def stats(self) -> dict[str, Any]:
        with self._uow() as uow:
            counts = uow.jobs.counts_by_status()
        try:
            depth, reachable = self._backend.depth(), self._backend.ping()
            workers = self._backend.workers(self._clock())
        except DependencyUnavailable:
            depth, reachable, workers = 0, False, {}
        return {"by_status": counts, "backend_reachable": reachable, "backend_depth": depth, "workers": workers}
