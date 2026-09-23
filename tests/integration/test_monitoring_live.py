"""Monitoring (Section 19-21) against a live database: SLA evaluation + alert creation as a real
side effect of connector_registry.record_call (the same function every genuine connector call goes
through - see app.interop.connectors.runtime.call), and distributed transaction tracing pulling
real cross-table rows back together by correlation_id. Skips cleanly if no live database is
reachable."""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete

from app.core.authorization import AuthContext, Role
from app.core.config import Settings
from app.core.exceptions import NotFound
from app.db.models.interop_platform import ConnectorAlert, ConnectorRegistration, InteropException, InteropTransaction
from app.db.session import make_engine, make_session_factory
from app.db.uow import SqlUnitOfWork
from app.interop import connector_registry
from app.interop.exceptions import center as exception_center
from app.services.interop_gateway_service import InteropGatewayService

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
class MonitoringLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session_factory = make_session_factory(_engine)
        self.uow_factory = lambda: SqlUnitOfWork(self.session_factory)
        self.gateway = InteropGatewayService(self.uow_factory)
        self.admin = AuthContext(str(uuid.uuid4()), Role.INTEGRATION_ADMIN, None, mfa_verified=True)
        self.connector_id = f"test-connector-{uuid.uuid4().hex[:8]}"
        with self.uow_factory() as uow:
            uow.session.add(ConnectorRegistration(connector_id=self.connector_id, name="Test Connector", department="Test Dept", version="1.0", supported_operations=[], enabled=True, health_state="unknown", sla_status="unknown", created_at=datetime.now(UTC)))
            uow.commit()

    def tearDown(self) -> None:
        with self.uow_factory() as uow:
            s = uow.session
            s.execute(delete(ConnectorAlert).where(ConnectorAlert.connector_id == self.connector_id))
            s.execute(delete(ConnectorRegistration).where(ConnectorRegistration.connector_id == self.connector_id))
            uow.commit()

    def test_a_never_called_connector_is_honestly_unknown(self):
        with self.uow_factory() as uow:
            row = connector_registry.get(uow.session, self.connector_id)
            self.assertEqual(row.sla_status, "unknown")

    def test_repeated_real_failures_breach_sla_and_raise_exactly_one_alert(self):
        """A real state transition (met/unknown -> breached) creates one alert; further failed
        calls after that must NOT create a second, duplicate alert for the same ongoing breach."""
        with self.uow_factory() as uow:
            for _ in range(10):
                connector_registry.record_call(uow.session, self.connector_id, success=False, duration_ms=50.0)
            uow.commit()

        with self.uow_factory() as uow:
            row = connector_registry.get(uow.session, self.connector_id)
            self.assertEqual(row.sla_status, "breached")  # 0% success rate, well under the 95% default
            self.assertEqual(row.health_state, "unavailable")  # 100% failure rate

        alerts = self.gateway.list_alerts(self.admin, connector_id=self.connector_id)
        sla_alerts = [a for a in alerts if a["alert_type"] == "SLA_BREACHED"]
        unavailable_alerts = [a for a in alerts if a["alert_type"] == "CONNECTOR_UNAVAILABLE"]
        self.assertEqual(len(sla_alerts), 1)  # not one per failed call - only the transition
        self.assertEqual(len(unavailable_alerts), 1)
        self.assertFalse(sla_alerts[0]["acknowledged"])

    def test_recovering_then_breaching_again_raises_a_second_alert(self):
        with self.uow_factory() as uow:
            for _ in range(10):
                connector_registry.record_call(uow.session, self.connector_id, success=False, duration_ms=50.0)
            uow.commit()
        alerts_after_first_breach = self.gateway.list_alerts(self.admin, connector_id=self.connector_id)
        first_count = len([a for a in alerts_after_first_breach if a["alert_type"] == "SLA_BREACHED"])
        self.assertEqual(first_count, 1)

        with self.uow_factory() as uow:
            # 10 failures already on the books - need total_failures/total_calls <= 0.05 to clear
            # the default 95% success-rate bar, i.e. at least 190 more calls succeeding cleanly.
            for _ in range(300):
                connector_registry.record_call(uow.session, self.connector_id, success=True, duration_ms=10.0)
            uow.commit()
        with self.uow_factory() as uow:
            row = connector_registry.get(uow.session, self.connector_id)
            self.assertEqual(row.sla_status, "met")

        with self.uow_factory() as uow:
            for _ in range(10):
                connector_registry.record_call(uow.session, self.connector_id, success=False, duration_ms=50.0)
            uow.commit()
        alerts_after_second_breach = self.gateway.list_alerts(self.admin, connector_id=self.connector_id)
        second_count = len([a for a in alerts_after_second_breach if a["alert_type"] == "SLA_BREACHED"])
        self.assertEqual(second_count, 2)  # a genuinely new breach after recovery is a new alert

    def test_acknowledge_an_alert(self):
        with self.uow_factory() as uow:
            for _ in range(10):
                connector_registry.record_call(uow.session, self.connector_id, success=False, duration_ms=50.0)
            uow.commit()
        alert = next(a for a in self.gateway.list_alerts(self.admin, connector_id=self.connector_id) if a["alert_type"] == "SLA_BREACHED")

        acknowledged = self.gateway.acknowledge_alert(self.admin, alert_id=alert["alert_id"])
        self.assertTrue(acknowledged["acknowledged"])
        self.assertEqual(acknowledged["acknowledged_by"], self.admin.user_id)
        self.assertIsNotNone(acknowledged["acknowledged_at"])

        with self.assertRaises(NotFound):
            self.gateway.acknowledge_alert(self.admin, alert_id=str(uuid.uuid4()))
        with self.assertRaises(NotFound):
            self.gateway.acknowledge_alert(self.admin, alert_id="not-a-uuid")


@unittest.skipUnless(_DB_AVAILABLE, _SKIP_REASON)
class TransactionTracingLiveTests(unittest.TestCase):
    """Every row across the platform's tables sharing one correlation_id, pulled back together -
    proven with real rows in InteropTransaction, InteropException and audit_logs, not synthetic
    fixtures the trace query wouldn't have to actually join across tables to find."""

    def setUp(self) -> None:
        self.session_factory = make_session_factory(_engine)
        self.uow_factory = lambda: SqlUnitOfWork(self.session_factory)
        self.gateway = InteropGatewayService(self.uow_factory)
        self.admin = AuthContext(str(uuid.uuid4()), Role.INTEGRATION_ADMIN, None, mfa_verified=True)
        self.correlation_id = f"trace-test-{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)
        with self.uow_factory() as uow:
            s = uow.session
            s.add(InteropTransaction(transaction_id=str(uuid.uuid4()), correlation_id=self.correlation_id, operation="document_exchange", source_system="dept_a", target_system="dept_b", status="failed", error_code="document_not_found", error_message="test", fields_exchanged=[], duration_ms=10.0, requested_fields=[], approved_fields=[], denied_fields=[], created_at=now))
            exception_center.log_exception(s, error_code="REMOTE_SYSTEM_ERROR", message="test trace exception", source_system="dept_a", target_system="dept_b", correlation_id=self.correlation_id, clock=lambda: now)
            uow.commit()

    def tearDown(self) -> None:
        with self.uow_factory() as uow:
            s = uow.session
            s.execute(delete(InteropException).where(InteropException.correlation_id == self.correlation_id))
            s.execute(delete(InteropTransaction).where(InteropTransaction.correlation_id == self.correlation_id))
            uow.commit()

    def test_trace_pulls_the_transaction_and_exception_rows_back_together(self):
        trace = self.gateway.get_trace(self.admin, correlation_id=self.correlation_id)
        self.assertEqual(trace["correlation_id"], self.correlation_id)
        self.assertEqual(len(trace["transactions"]), 1)
        self.assertEqual(trace["transactions"][0]["error_code"], "document_not_found")
        self.assertEqual(len(trace["exceptions"]), 1)
        self.assertEqual(trace["exceptions"][0]["error_code"], "REMOTE_SYSTEM_ERROR")

    def test_an_unknown_correlation_id_is_a_clean_not_found_not_an_empty_200(self):
        with self.assertRaises(NotFound):
            self.gateway.get_trace(self.admin, correlation_id=f"never-happened-{uuid.uuid4().hex}")


if __name__ == "__main__":
    unittest.main()
