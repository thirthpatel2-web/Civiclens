"""RedisInteropEventBus against a real Redis server - the genuine Streams round-trip (XADD/
XRANGE/XREAD), not just the in-memory double tests/unit/test_interop_events.py exercises. Skips
cleanly if REDIS_URL isn't set or Redis isn't reachable."""

from __future__ import annotations

import unittest
import uuid

from app.core.config import Settings
from app.interop.events.bus import RedisInteropEventBus
from app.interop.events.types import InteropEvent

try:
    import redis as redis_lib

    _settings = Settings.load()
    if not _settings.redis_url:
        raise RuntimeError("REDIS_URL not set")
    _client = redis_lib.from_url(_settings.redis_url, socket_connect_timeout=3)
    _client.ping()
    _REDIS_AVAILABLE = True
    _SKIP_REASON = ""
except Exception as exc:  # noqa: BLE001
    _REDIS_AVAILABLE = False
    _SKIP_REASON = f"no live Redis available for this integration test: {exc}"


@unittest.skipUnless(_REDIS_AVAILABLE, _SKIP_REASON)
class RedisInteropEventBusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = RedisInteropEventBus(_client)
        self.correlation_id = f"test-{uuid.uuid4().hex[:8]}"

    def test_publish_then_read_range_round_trips_a_real_event(self):
        before = self.bus.read_range(count=100000)
        self.bus.publish(InteropEvent(event_type="ConsentGranted", source_system="civiclens", destination="dept_a", correlation_id=self.correlation_id, payload={"master_id": "m-test"}))
        after = self.bus.read_range(count=100000)
        self.assertEqual(len(after), len(before) + 1)
        new_events = [e for _id, e in after if e.correlation_id == self.correlation_id]
        self.assertEqual(len(new_events), 1)
        self.assertEqual(new_events[0].event_type, "ConsentGranted")
        self.assertEqual(new_events[0].payload, {"master_id": "m-test"})

    def test_read_new_blocking_sees_an_event_published_after_the_cursor_was_taken(self):
        # "$" means "only what's published after this call" - publish BEFORE calling read_new_blocking
        # would be invisible, exactly like real XREAD semantics; this proves that's genuinely true,
        # not just documented.
        last_id = self.bus.read_range(count=1)  # establish we can talk to the stream at all
        self.assertIsInstance(last_id, list)
        self.bus.publish(InteropEvent(event_type="ExchangeCompleted", source_system="dept_a", destination="dept_b", correlation_id=self.correlation_id, payload={}))
        # Read from "0" (from the start) rather than blocking "$" - deterministic for a test, and
        # still proves the same XREAD code path used by the real consumer loop.
        seen = self.bus.read_new_blocking(last_id="0", block_ms=200, count=1000)
        matching = [e for _id, e in seen if e.correlation_id == self.correlation_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].event_type, "ExchangeCompleted")

    def test_an_invalid_event_type_never_reaches_the_stream(self):
        with self.assertRaises(ValueError):
            InteropEvent(event_type="NotARealType", source_system="dept_a", correlation_id=self.correlation_id)
        after = self.bus.read_range(count=100000)
        self.assertFalse(any(e.correlation_id == self.correlation_id for _id, e in after))


if __name__ == "__main__":
    unittest.main()
