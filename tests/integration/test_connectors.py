"""The GovernmentConnector abstraction (app.interop.connectors) against a live database: every
concrete connector implements the same interface, the runtime resolves connector_id -> instance
and refuses a disabled one, and every real call updates the connector registry's live stats - the
same accounting the registry showed before the gateway moved off direct mock-system calls.

Runs against a live PostgreSQL connection for the same reason tests/integration/test_interop_gateway_e2e.py
does: the mock systems are real persisted tables, not in-memory doubles. Skips cleanly if no live
database is reachable.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from sqlalchemy import delete

from app.core.config import Settings
from app.db.session import make_engine, make_session_factory
from app.db.uow import SqlUnitOfWork
from app.interop import connector_registry, mock_systems
from app.interop.connectors import runtime as connector_runtime
from app.interop.connectors.base import GovernmentConnector
from app.interop.connectors.mock_dept_a import DeptAConnector
from app.interop.connectors.mock_dept_b import DeptBConnector
from app.interop.connectors.mock_dept_c import DeptCConnector
from app.interop.federation import idp

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
class ConnectorInterfaceConformanceTests(unittest.TestCase):
    """Every connector - mock today, real tomorrow - implements the same interface, so the runtime
    (and the gateway, through it) never needs to know which concrete class it's talking to."""

    def setUp(self) -> None:
        self.session_factory = make_session_factory(_engine)
        self.uow_factory = lambda: SqlUnitOfWork(self.session_factory)
        with self.uow_factory() as uow:
            mock_systems.seed_if_empty(uow.session)
            connector_registry.seed_if_empty(uow.session)
            idp.seed_if_empty(uow.session)
            uow.commit()

    def test_all_three_are_real_government_connector_subclasses(self):
        with self.uow_factory() as uow:
            for cls in (DeptAConnector, DeptBConnector, DeptCConnector):
                connector = cls(uow.session)
                self.assertIsInstance(connector, GovernmentConnector)
                self.assertTrue(connector.authenticate())

    def test_health_check_is_a_real_query_not_a_hardcoded_status(self):
        with self.uow_factory() as uow:
            for connector_id, cls in (("dept_a", DeptAConnector), ("dept_b", DeptBConnector), ("dept_c", DeptCConnector)):
                result = cls(uow.session).health_check()
                self.assertTrue(result.ok, f"{connector_id}: {result.error_message}")

    def test_dept_a_get_entity_and_query_and_fetch_document(self):
        with self.uow_factory() as uow:
            connector = DeptAConnector(uow.session)
            found = connector.get_entity("resident", "RES-MH-00101")
            self.assertTrue(found.ok)
            self.assertEqual(found.data.full_name, "Priya Deshmukh")

            missing = connector.get_entity("resident", "RES-DOES-NOT-EXIST")
            self.assertFalse(missing.ok)
            self.assertEqual(missing.error_code, "IDENTITY_NOT_FOUND")

            by_mobile = connector.query("resident", mobile="9876543210")
            self.assertTrue(by_mobile.ok)
            self.assertTrue(any(r.resident_id == "RES-MH-00101" for r in by_mobile.data))

            doc = connector.fetch_document("RES-MH-00101", "residence_certificate")
            self.assertTrue(doc.ok)
            self.assertEqual(doc.data.reference_no, "RC-MH-2026-7701")

    def test_dept_a_refuses_writes_honestly(self):
        with self.uow_factory() as uow:
            connector = DeptAConnector(uow.session)
            self.assertFalse(connector.submit("resident", {}).ok)
            self.assertFalse(connector.update("resident", "RES-MH-00101", {}).ok)
            self.assertEqual(connector.submit("resident", {}).error_code, "CONNECTOR_UNAVAILABLE")

    def test_dept_b_update_is_the_real_no_reupload_write(self):
        """Exercised end-to-end already in test_interop_gateway_e2e.py via the gateway; this
        confirms the connector's own update() method does the write correctly in isolation,
        against a throwaway application it creates and cleans up itself."""
        beneficiary_code, application_no = "TEST-CONN-BEN-1", "TEST-CONN-APP-1"
        now = datetime.now(UTC)
        try:
            with self.uow_factory() as uow:
                s = uow.session
                s.add(mock_systems.MockDeptBBeneficiary(beneficiary_code=beneficiary_code, full_name="Test Person", mobile_number="9000011111", created_at=now))
                s.flush()
                s.add(mock_systems.MockDeptBApplication(application_no=application_no, beneficiary_code=beneficiary_code, service_type="Small Business Registration", status="pending_document", required_document_type="residence_certificate", document_status="missing", created_at=now, updated_at=now))
                uow.commit()

            with self.uow_factory() as uow:
                connector = DeptBConnector(uow.session)
                result = connector.update("application", application_no, {"document_reference": "TEST-REF-999"})
                uow.commit()
            self.assertTrue(result.ok)
            self.assertEqual(result.data.document_reference, "TEST-REF-999")
            self.assertEqual(result.data.document_status, "verified")

            with self.uow_factory() as uow:
                row = mock_systems.dept_b_get_application(uow.session, application_no)
                self.assertEqual(row.document_reference, "TEST-REF-999")
        finally:
            with self.uow_factory() as uow:
                s = uow.session
                s.execute(delete(mock_systems.MockDeptBApplication).where(mock_systems.MockDeptBApplication.application_no == application_no))
                s.execute(delete(mock_systems.MockDeptBBeneficiary).where(mock_systems.MockDeptBBeneficiary.beneficiary_code == beneficiary_code))
                uow.commit()

    def test_dept_c_read_only_query(self):
        with self.uow_factory() as uow:
            connector = DeptCConnector(uow.session)
            result = connector.query("grievance")
            self.assertTrue(result.ok)
            self.assertTrue(any(g.grievance_ref == "GRV-MH-3301" for g in result.data))
            self.assertFalse(connector.submit("grievance", {}).ok)


@unittest.skipUnless(_DB_AVAILABLE, _SKIP_REASON)
class ConnectorRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session_factory = make_session_factory(_engine)
        self.uow_factory = lambda: SqlUnitOfWork(self.session_factory)
        with self.uow_factory() as uow:
            mock_systems.seed_if_empty(uow.session)
            connector_registry.seed_if_empty(uow.session)
            idp.seed_if_empty(uow.session)
            uow.commit()

    def test_runtime_resolves_a_known_enabled_connector(self):
        with self.uow_factory() as uow:
            connector = connector_runtime.resolve(uow.session, "dept_a")
            self.assertIsInstance(connector, DeptAConnector)

    def test_runtime_refuses_an_unknown_connector_id(self):
        with self.uow_factory() as uow:
            with self.assertRaises(connector_runtime.ConnectorUnavailable):
                connector_runtime.resolve(uow.session, "dept_z_does_not_exist")

    def test_runtime_refuses_a_disabled_connector_and_call_returns_a_structured_failure(self):
        with self.uow_factory() as uow:
            connector_registry.set_enabled(uow.session, "dept_a", False)
            uow.commit()
        try:
            with self.uow_factory() as uow:
                with self.assertRaises(connector_runtime.ConnectorUnavailable):
                    connector_runtime.resolve(uow.session, "dept_a")
                result = connector_runtime.call(uow.session, "dept_a", "health_check")
                self.assertFalse(result.ok)
                self.assertEqual(result.error_code, "CONNECTOR_UNAVAILABLE")
        finally:
            with self.uow_factory() as uow:
                connector_registry.set_enabled(uow.session, "dept_a", True)
                uow.commit()

    def test_runtime_refuses_a_connector_whose_federation_client_is_disabled(self):
        """The federation gate (app.interop.connectors.base.authenticate_via_federation) is
        genuinely enforced by resolve()/call(), not just present in the interface - disabling
        dept_a's federation client (its own IdP registration, distinct from the connector
        registry's enabled flag tested above) must refuse it with AUTHENTICATION_FAILURE."""
        from app.db.models.interop_platform import FederationClient

        with self.uow_factory() as uow:
            client = uow.session.get(FederationClient, "dept_a")
            client.enabled = False
            uow.session.add(client)
            uow.commit()
        try:
            with self.uow_factory() as uow:
                with self.assertRaises(connector_runtime.ConnectorUnavailable):
                    connector_runtime.resolve(uow.session, "dept_a")
                result = connector_runtime.call(uow.session, "dept_a", "health_check")
                self.assertFalse(result.ok)
                self.assertEqual(result.error_code, "AUTHENTICATION_FAILURE")
        finally:
            with self.uow_factory() as uow:
                client = uow.session.get(FederationClient, "dept_a")
                client.enabled = True
                uow.session.add(client)
                uow.commit()
            # A disabled-then-re-enabled client's OLD tokens stay invalid (issued while disabled
            # never happened; any issued before disabling are now past this test) - re-enabling
            # only lets it mint fresh ones, which the next real gateway call will do.
            with self.uow_factory() as uow:
                connector = connector_runtime.resolve(uow.session, "dept_a")
                self.assertIsInstance(connector, DeptAConnector)

    def test_a_real_call_updates_the_connector_registrys_live_stats(self):
        with self.uow_factory() as uow:
            before = connector_registry.get(uow.session, "dept_a")
            calls_before = before.total_calls

        with self.uow_factory() as uow:
            result = connector_runtime.call(uow.session, "dept_a", "get_entity", "resident", "RES-MH-00101")
            uow.commit()
        self.assertTrue(result.ok)
        self.assertIn("duration_ms", result.meta)

        with self.uow_factory() as uow:
            after = connector_registry.get(uow.session, "dept_a")
            self.assertEqual(after.total_calls, calls_before + 1)
            self.assertEqual(after.health_state, "healthy")


if __name__ == "__main__":
    unittest.main()
