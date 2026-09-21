"""Redis-backed rate limiting and login throttling so limits hold across web processes.

Semantics
* ``RedisFixedWindowLimiter``: atomic INCR + EXPIRE per (bucket, key). Fixed window (a burst of up to 2x the limit is possible across a
  window boundary) - chosen for atomicity and simplicity; the in-process ``SlidingWindowLimiter`` remains the reference for exact sliding semantics.
* ``RedisFailureThrottle``: failure counter with a window + a lock key with a lock-out TTL (same behaviour as ``FailureThrottle``).
* ``Resilient*``: if Redis is unreachable the per-process in-memory limiter takes over (fail-*degraded*, not fail-open and not a total lock-out),
  and ``degraded`` is exposed so the admin monitor can show it.
Tested against a fake client that emulates INCR/EXPIRE/TTL/SET-NX-EX; not executed against a real Redis in the build sandbox.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.exceptions import RateLimited
from app.core.rate_limit import FailureThrottle, SlidingWindowLimiter, ThrottlePolicy

logger = logging.getLogger("civiclens.ratelimit")


class RedisFixedWindowLimiter:
    def __init__(self, client: Any, bucket: str, limit: int, window_seconds: int, prefix: str = "civiclens") -> None:
        self._r, self._k, self._limit, self._window = client, f"{prefix}:rl:{bucket}:", limit, window_seconds

    def hit(self, key: str) -> None:
        k = self._k + key
        n = int(self._r.incr(k))
        if n == 1 or int(self._r.ttl(k)) < 0:  # (re)arm the expiry; also heals a key left without TTL by a crash
            self._r.expire(k, self._window)
        if n > self._limit:
            raise RateLimited(retry_after_seconds=max(1, int(self._r.ttl(k))))


class RedisFailureThrottle:
    def __init__(self, client: Any, name: str, policy: ThrottlePolicy | None = None, prefix: str = "civiclens") -> None:
        self._r, self._p, self.policy = client, f"{prefix}:throttle:{name}:", policy or ThrottlePolicy()

    def check(self, key: str) -> None:
        ttl = int(self._r.ttl(self._p + "lock:" + key))
        if ttl > 0:
            raise RateLimited(retry_after_seconds=ttl)

    def record_failure(self, key: str) -> None:
        k = self._p + "fail:" + key
        n = int(self._r.incr(k))
        if n == 1 or int(self._r.ttl(k)) < 0:
            self._r.expire(k, self.policy.window_seconds)
        if n >= self.policy.max_failures:
            self._r.set(self._p + "lock:" + key, "1", ex=self.policy.lockout_seconds)

    def record_success(self, key: str) -> None:
        self._r.delete(self._p + "fail:" + key)
        self._r.delete(self._p + "lock:" + key)


class ResilientLimiter:
    def __init__(self, primary: Any, fallback: SlidingWindowLimiter) -> None:
        self._primary, self._fallback, self.degraded = primary, fallback, False

    def hit(self, key: str) -> None:
        try:
            self._primary.hit(key)
            self.degraded = False
        except RateLimited:
            raise
        except Exception:
            if not self.degraded:
                logger.warning("redis rate limiter unavailable; using the in-process limiter")
            self.degraded = True
            self._fallback.hit(key)


class ResilientThrottle:
    def __init__(self, primary: Any, fallback: FailureThrottle) -> None:
        self._primary, self._fallback, self.degraded = primary, fallback, False

    def _call(self, name: str, key: str) -> None:
        try:
            getattr(self._primary, name)(key)
            self.degraded = False
        except RateLimited:
            raise
        except Exception:
            if not self.degraded:
                logger.warning("redis throttle unavailable; using the in-process throttle")
            self.degraded = True
            getattr(self._fallback, name)(key)

    def check(self, key: str) -> None:
        self._call("check", key)

    def record_failure(self, key: str) -> None:
        self._call("record_failure", key)
        if self.degraded:
            return
        self._fallback.record_failure(key)  # keep the local copy warm so a Redis outage does not reset counters

    def record_success(self, key: str) -> None:
        self._call("record_success", key)
        self._fallback.record_success(key)
