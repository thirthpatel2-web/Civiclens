"""Interop event bus (Section 10): Redis Streams when Redis is configured (durable, replayable,
supports multiple independent consumers reading at their own pace - the reason Streams was chosen
over plain pub/sub, which drops anything published while no one is listening), an in-memory bus
otherwise so the platform still runs, honestly, without Redis (the same degrade-gracefully
convention this codebase already uses for e-mail/push - see ``app.container.build_container``).

Independent from ``app.workers.redis_backend.RedisEventBus`` (a different Redis channel, a
different event shape - see ``types.py``'s docstring for why they're not merged).
"""

from __future__ import annotations

from typing import Any, Protocol

from app.interop.events.types import InteropEvent, event_from_dict, event_to_dict


class InteropEventBus(Protocol):
    def publish(self, event: InteropEvent) -> None: ...
    def read_range(self, *, start_id: str = "-", count: int = 100) -> list[tuple[str, InteropEvent]]: ...


class InMemoryInteropEventBus:
    """No Redis configured: events are still captured (for tests, and so ``list_recent_events``
    has something real to show), just not durable across a process restart - the honest
    degradation, not a silent no-op."""

    def __init__(self) -> None:
        self._log: list[tuple[str, InteropEvent]] = []

    def publish(self, event: InteropEvent) -> None:
        self._log.append((str(len(self._log)), event))

    def read_range(self, *, start_id: str = "-", count: int = 100) -> list[tuple[str, InteropEvent]]:
        # "-" is the only "from the beginning" sentinel (matching Redis XRANGE's own convention) -
        # "0" is a legitimate real id (the first published event) and must not be treated as one.
        start = 0 if start_id == "-" else int(start_id) + 1
        return self._log[start : start + count]


class RedisInteropEventBus:
    """Redis Streams (``XADD``/``XRANGE``/``XREAD``) - durable, replayable, independent of whether
    a consumer happens to be listening at publish time."""

    STREAM = "civiclens:interop:events"
    MAXLEN = 10000  # approximate cap so the stream doesn't grow unbounded in a long-running demo

    def __init__(self, client: Any) -> None:
        self._r = client

    def publish(self, event: InteropEvent) -> None:
        import json

        self._r.xadd(self.STREAM, {"data": json.dumps(event_to_dict(event))}, maxlen=self.MAXLEN, approximate=True)

    def read_range(self, *, start_id: str = "-", count: int = 100) -> list[tuple[str, InteropEvent]]:
        """Non-blocking (``XRANGE``) - deterministic for tests and for a one-shot drain, unlike a
        blocking ``XREAD``. ``start_id="-"`` reads from the beginning of the stream; any other
        ``start_id`` is EXCLUSIVE (Redis's own ``(id`` syntax) - matching
        ``InMemoryInteropEventBus``'s semantics, where "start after this id" means what it says
        and never re-includes the boundary entry itself."""
        import json

        min_bound = start_id if start_id == "-" else f"({start_id}"
        entries = self._r.xrange(self.STREAM, min=min_bound, count=count)
        out = []
        for entry_id, fields in entries:
            eid = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
            raw = fields[b"data"] if b"data" in fields else fields["data"]
            data = raw.decode() if isinstance(raw, bytes) else raw
            out.append((eid, event_from_dict(json.loads(data))))
        return out

    def read_new_blocking(self, *, last_id: str = "$", block_ms: int = 1000, count: int = 10) -> list[tuple[str, InteropEvent]]:
        """Blocking ``XREAD`` for a real background consumer loop (run in a thread, the same
        pattern ``RedisEventBus.listen`` already uses for the complaint domain). ``last_id="$"``
        means "only events published after this call starts" - a fresh subscriber never replays
        history, matching ``XREAD``'s own semantics."""
        import json

        resp = self._r.xread({self.STREAM: last_id}, count=count, block=block_ms)
        out: list[tuple[str, InteropEvent]] = []
        for _stream_name, entries in resp or []:
            for entry_id, fields in entries:
                eid = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                raw = fields[b"data"] if b"data" in fields else fields["data"]
                data = raw.decode() if isinstance(raw, bytes) else raw
                out.append((eid, event_from_dict(json.loads(data))))
        return out
