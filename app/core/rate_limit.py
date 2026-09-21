"""Failure throttling / account lock-out with an injectable clock."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from app.core.exceptions import RateLimited


@dataclass(frozen=True)
class ThrottlePolicy:
    max_failures: int = 5
    window_seconds: int = 300
    lockout_seconds: int = 900


class FailureThrottle:
    """Counts failures per key inside a sliding window and locks the key out.

    In production the same policy should be backed by Redis so it is shared
    across processes; this class is the in-process implementation and the
    reference for the semantics.
    """

    def __init__(self, policy: ThrottlePolicy | None = None, clock: Callable[[], float] = monotonic):
        self.policy = policy or ThrottlePolicy()
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._locked_until: dict[str, float] = {}

    def _prune(self, key: str, now: float) -> None:
        q = self._failures[key]
        while q and now - q[0] > self.policy.window_seconds:
            q.popleft()

    def check(self, key: str) -> None:
        """Raise :class:`RateLimited` if ``key`` is currently locked out."""
        now = self._clock()
        until = self._locked_until.get(key)
        if until is not None:
            if now < until:
                raise RateLimited(retry_after_seconds=int(until - now) + 1)
            del self._locked_until[key]
            self._failures.pop(key, None)

    def record_failure(self, key: str) -> None:
        now = self._clock()
        self._prune(key, now)
        self._failures[key].append(now)
        if len(self._failures[key]) >= self.policy.max_failures:
            self._locked_until[key] = now + self.policy.lockout_seconds

    def record_success(self, key: str) -> None:
        self._failures.pop(key, None)
        self._locked_until.pop(key, None)


class SlidingWindowLimiter:
    """Allow at most ``limit`` calls per ``window_seconds`` per key (in-process; back with Redis for multi-process)."""

    def __init__(self, limit: int, window_seconds: int, clock: Callable[[], float] = monotonic) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("limit and window must be positive")
        self._limit, self._window, self._clock = limit, window_seconds, clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> None:
        """Record a call or raise :class:`RateLimited`."""
        now = self._clock()
        q = self._hits[key]
        while q and now - q[0] >= self._window:
            q.popleft()
        if len(q) >= self._limit:
            raise RateLimited(retry_after_seconds=max(1, int(self._window - (now - q[0])) + 1))
        q.append(now)
