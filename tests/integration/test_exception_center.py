"""The Exception Center (app.interop.exceptions.center) against a live database: logging, retry
with dead-letter after max_retries, and manual resolution/dead-lettering. Skips cleanly if no live
database is reachable."""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete

from app.core.config import Settings
from app.db.models.interop_platform import InteropException
from app.db.session import make_engine, make_session_factory
from app.db.uow import SqlUnitOfWork
from app.interop.exceptions import center

try:
    _engine = make_engine(Settings.load())
    with _engine.connect():
        pass
    _DB_AVAILABLE = True
    _SKIP_REASON = ""
except Exception as exc:  # noqa: BLE001
    _DB_AVAILABLE = False
    _SKIP_REASON = f"no live database available for this integration test: {exc}"


@unittest.skipUnless(_DB_AVAILABLE, _SKIP_REASON)
class ExceptionCenterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session_factory = make_session_factory(_engine)
        self.uow_factory = lambda: SqlUnitOfWork(self.session_factory)
        self.correlation_id = f"test-{uuid.uuid4().hex[:8]}"

    def tearDown(self) -> None:
        with self.uow_factory() as uow:
            uow.session.execute(delete(InteropException).where(InteropException.correlation_id == self.correlation_id))
            uow.commit()

    def test_logging_an_unrecognized_error_code_is_refused(self):
        with self.uow_factory() as uow:
            with self.assertRaises(ValueError):
                center.log_exception(uow.session, error_code="NOT_A_REAL_CODE", message="x", correlation_id=self.correlation_id)

    def test_log_then_list_round_trips_with_the_right_retryable_default(self):
        with self.uow_factory() as uow:
            record = center.log_exception(uow.session, error_code="CONNECTOR_UNAVAILABLE", message="dept_a unreachable", source_system="dept_a", target_system="civiclens", correlation_id=self.correlation_id)
            uow.commit()
        self.assertTrue(record.retryable)  # CONNECTOR_UNAVAILABLE is in RETRYABLE_TYPES
        self.assertEqual(record.resolution_state, "open")

        with self.uow_factory() as uow:
            found = center.list_exceptions(uow.session, correlation_id=self.correlation_id)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].error_code, "CONNECTOR_UNAVAILABLE")

    def test_a_non_retryable_exception_defaults_to_not_retryable(self):
        with self.uow_factory() as uow:
            record = center.log_exception(uow.session, error_code="DATA_QUALITY_FAILURE", message="bad data", correlation_id=self.correlation_id)
            uow.commit()
        self.assertFalse(record.retryable)
        self.assertEqual(record.next_action, "manual review required")

    def test_retry_moves_through_retrying_and_then_dead_once_exhausted(self):
        with self.uow_factory() as uow:
            record = center.log_exception(uow.session, error_code="CONNECTOR_TIMEOUT", message="slow", correlation_id=self.correlation_id, max_retries=2)
            uow.commit()
            exception_id = record.exception_id

        with self.uow_factory() as uow:
            after_first = center.retry(uow.session, exception_id)
            uow.commit()
        self.assertEqual(after_first.resolution_state, "retrying")
        self.assertEqual(after_first.retry_count, 1)

        with self.uow_factory() as uow:
            after_second = center.retry(uow.session, exception_id)
            uow.commit()
        self.assertEqual(after_second.resolution_state, "dead")  # max_retries=2 reached
        self.assertIn("exhausted", after_second.next_action)

        with self.uow_factory() as uow:
            refused = center.retry(uow.session, exception_id)  # already dead - retry() refuses
        self.assertIsNone(refused)

    def test_a_non_retryable_exception_cannot_be_retried_at_all(self):
        with self.uow_factory() as uow:
            record = center.log_exception(uow.session, error_code="IDENTITY_CONFLICT", message="two masters", correlation_id=self.correlation_id)
            uow.commit()
            exception_id = record.exception_id
        with self.uow_factory() as uow:
            result = center.retry(uow.session, exception_id)
        self.assertIsNone(result)

    def test_mark_resolved_sets_a_real_timestamp_and_clears_next_action(self):
        with self.uow_factory() as uow:
            record = center.log_exception(uow.session, error_code="IDENTITY_AMBIGUOUS", message="needs review", correlation_id=self.correlation_id)
            uow.commit()
            exception_id = record.exception_id
        with self.uow_factory() as uow:
            resolved = center.mark_resolved(uow.session, exception_id, clock=lambda: datetime(2026, 6, 1, tzinfo=UTC))
            uow.commit()
        self.assertEqual(resolved.resolution_state, "resolved")
        self.assertIsNone(resolved.next_action)
        self.assertEqual(resolved.resolved_at, datetime(2026, 6, 1, tzinfo=UTC))

    def test_mark_dead_is_an_operators_explicit_give_up_not_only_an_automatic_outcome(self):
        with self.uow_factory() as uow:
            record = center.log_exception(uow.session, error_code="CONNECTOR_UNAVAILABLE", message="down", correlation_id=self.correlation_id)
            uow.commit()
            exception_id = record.exception_id
        with self.uow_factory() as uow:
            dead = center.mark_dead(uow.session, exception_id, reason="vendor confirmed decommissioned")
            uow.commit()
        self.assertEqual(dead.resolution_state, "dead")
        self.assertEqual(dead.next_action, "vendor confirmed decommissioned")

    def test_acting_on_an_unknown_exception_id_is_a_safe_no_op(self):
        with self.uow_factory() as uow:
            self.assertIsNone(center.retry(uow.session, "does-not-exist"))
            self.assertIsNone(center.mark_resolved(uow.session, "does-not-exist"))
            self.assertIsNone(center.mark_dead(uow.session, "does-not-exist"))


if __name__ == "__main__":
    unittest.main()
