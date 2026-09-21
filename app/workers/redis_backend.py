"""Redis implementations of the queue backend, scheduler lock/state and the event bridge.

Written against redis-py's synchronous client. NOT executed in this build (no Redis server or
package available): the *semantics* they must satisfy are pinned by the QueueBackend/LockProvider
Protocols and by the tests that run against in-memory doubles.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.exceptions import DependencyUnavailable
from app.realtime.events import DomainEvent, event_from_json, event_to_json

_POP_LUA = """
local r = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, 1)
if #r == 0 then return false end
redis.call('ZREM', KEYS[1], r[1])
return r[1]
"""


def _wrap(fn):  # type: ignore[no-untyped-def]
    def inner(*a, **k):  # type: ignore[no-untyped-def]
        try:
            return fn(*a, **k)
        except Exception as exc:
            if type(exc).__module__.startswith("redis"):
                raise DependencyUnavailable("Redis is unreachable.") from exc
            raise

    return inner


class RedisQueueBackend:
    def __init__(self, client: Any, prefix: str = "civiclens") -> None:
        self._r, self._q, self._w = client, f"{prefix}:queue", f"{prefix}:worker:"
        self._pop = client.register_script(_POP_LUA)

    @_wrap
    def push(self, job_id: str, run_at: datetime) -> None:
        self._r.zadd(self._q, {job_id: run_at.timestamp()})

    @_wrap
    def pop_due(self, now: datetime) -> str | None:
        v = self._pop(keys=[self._q], args=[now.timestamp()])
        return None if not v else (v.decode() if isinstance(v, bytes) else str(v))

    @_wrap
    def depth(self) -> int:
        return int(self._r.zcard(self._q))

    @_wrap
    def heartbeat(self, worker_id: str, now: datetime, info: dict[str, Any]) -> None:
        self._r.setex(self._w + worker_id, 120, json.dumps({"last_seen": now.isoformat(), **info}))

    @_wrap
    def workers(self, now: datetime, max_age_seconds: int = 60) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for key in self._r.scan_iter(match=self._w + "*", count=100):
            k = key.decode() if isinstance(key, bytes) else key
            raw = self._r.get(k)
            if raw:
                info = json.loads(raw)
                if (now - datetime.fromisoformat(info["last_seen"])).total_seconds() <= max_age_seconds:
                    out[k[len(self._w):]] = info
        return out

    def ping(self) -> bool:
        try:
            return bool(self._r.ping())
        except Exception:
            return False


class RedisLock:
    def __init__(self, client: Any, prefix: str = "civiclens") -> None:
        self._r, self._p, self._tokens = client, f"{prefix}:lock:", {}

    @_wrap
    def acquire(self, name: str, ttl_seconds: int) -> bool:
        token = uuid.uuid4().hex
        if self._r.set(self._p + name, token, nx=True, ex=ttl_seconds):
            self._tokens[name] = token
            return True
        return False

    @_wrap
    def release(self, name: str) -> None:
        token = self._tokens.pop(name, None)
        if token and (cur := self._r.get(self._p + name)) and (cur.decode() if isinstance(cur, bytes) else cur) == token:
            self._r.delete(self._p + name)


class RedisSchedulerState:
    def __init__(self, client: Any, prefix: str = "civiclens") -> None:
        self._r, self._k = client, f"{prefix}:scheduler:last_run"

    @_wrap
    def last_run(self, name: str) -> datetime | None:
        v = self._r.hget(self._k, name)
        return datetime.fromisoformat(v.decode() if isinstance(v, bytes) else v) if v else None

    @_wrap
    def set_last_run(self, name: str, at: datetime) -> None:
        self._r.hset(self._k, name, at.astimezone(UTC).isoformat())


class RedisEventBus:
    """Publishes domain events to a channel so every web process can push to its own sockets."""

    CHANNEL = "civiclens:events"

    def __init__(self, client: Any) -> None:
        self._r = client

    @_wrap
    def publish(self, event: DomainEvent) -> None:
        self._r.publish(self.CHANNEL, event_to_json(event))

    def listen(self, on_event: Any, stop: Any) -> None:
        """Blocking subscriber loop (run in a thread). ``on_event(DomainEvent)`` schedules delivery."""
        pubsub = self._r.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(self.CHANNEL)
        while not stop.is_set():
            msg = pubsub.get_message(timeout=1.0)
            if msg and msg.get("type") == "message":
                data = msg["data"]
                on_event(event_from_json(data.decode() if isinstance(data, bytes) else data))
            else:
                time.sleep(0.05)
