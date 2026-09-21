"""Periodic background tasks with a distributed lock and persisted last-run times."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.core.logging import redact

logger = logging.getLogger("civiclens.workers.scheduler")


class SchedulerState(Protocol):
    def last_run(self, name: str) -> datetime | None: ...
    def set_last_run(self, name: str, at: datetime) -> None: ...


class LockProvider(Protocol):
    def acquire(self, name: str, ttl_seconds: int) -> bool: ...
    def release(self, name: str) -> None: ...


@dataclass(frozen=True)
class TaskSpec:
    name: str
    interval: timedelta
    fn: Callable[[datetime], dict[str, Any] | None]


@dataclass(frozen=True)
class TaskRun:
    name: str
    ok: bool
    summary: dict[str, Any]
    error: str | None = None


class SchedulerService:
    """``tick`` runs every task whose interval has elapsed. Safe to run in several processes:
    the lock ensures one runs a given task at a time; a failing task never stops the others."""

    def __init__(self, tasks: list[TaskSpec], state: SchedulerState, lock: LockProvider, clock: Callable[[], datetime] | None = None) -> None:
        names = [t.name for t in tasks]
        if len(set(names)) != len(names):
            raise ValueError("duplicate task names")
        self._tasks, self._state, self._lock = tasks, state, lock
        self._clock = clock or (lambda: datetime.now(UTC))

    def due(self, now: datetime) -> list[TaskSpec]:
        out = []
        for t in self._tasks:
            last = self._state.last_run(t.name)
            if last is None or now - last >= t.interval:
                out.append(t)
        return out

    def tick(self) -> list[TaskRun]:
        now = self._clock()
        runs: list[TaskRun] = []
        for t in self.due(now):
            ttl = max(int(t.interval.total_seconds()), 30)
            if not self._lock.acquire(f"scheduler:{t.name}", ttl):
                continue  # another instance is running it
            try:
                summary = t.fn(now) or {}
                self._state.set_last_run(t.name, now)
                runs.append(TaskRun(t.name, True, summary))
            except Exception as exc:
                logger.exception("scheduled task %s failed", t.name)
                self._state.set_last_run(t.name, now)  # avoid a hot retry loop; next attempt after one interval
                runs.append(TaskRun(t.name, False, {}, redact(f"{type(exc).__name__}: {exc}")[:300]))
            finally:
                self._lock.release(f"scheduler:{t.name}")
        return runs

    async def run_forever(self, poll_seconds: float = 15.0) -> None:
        while True:
            await asyncio.to_thread(self.tick)
            await asyncio.sleep(poll_seconds)
