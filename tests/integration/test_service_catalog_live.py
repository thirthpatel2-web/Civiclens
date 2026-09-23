"""The service catalog & field mapping catalog (app.interop.catalog) against a live database:
seeding is idempotent, and InteropGatewayService's read surfaces return the real seeded rows.
Skips cleanly if no live database is reachable."""

from __future__ import annotations

import unittest

from app.core.authorization import AuthContext, Role
from app.core.config import Settings
from app.db.session import make_engine, make_session_factory
from app.db.uow import SqlUnitOfWork
from app.interop import catalog, connector_registry, mock_systems
from app.interop.federation import idp
from app.interop.workflow.definitions import register_default_workflows
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
class ServiceCatalogLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session_factory = make_session_factory(_engine)
        self.uow_factory = lambda: SqlUnitOfWork(self.session_factory)
        self.gateway = InteropGatewayService(self.uow_factory)
        self.admin = AuthContext("catalog-test-admin", Role.INTEGRATION_ADMIN, None, mfa_verified=True)
        with self.uow_factory() as uow:
            mock_systems.seed_if_empty(uow.session)
            connector_registry.seed_if_empty(uow.session)
            idp.seed_if_empty(uow.session)
            register_default_workflows(uow.session)
            catalog.seed_if_empty(uow.session)
            uow.commit()

    def test_seeding_is_idempotent(self):
        with self.uow_factory() as uow:
            inserted_again = catalog.seed_if_empty(uow.session)
            uow.commit()
        self.assertFalse(inserted_again)

    def test_service_catalog_lists_the_real_no_reupload_service(self):
        services = self.gateway.list_service_catalog(self.admin)
        ids = {s["service_id"] for s in services}
        self.assertIn("residence_certificate_verification", ids)
        entry = next(s for s in services if s["service_id"] == "residence_certificate_verification")
        self.assertEqual(entry["source_system"], "dept_a")
        self.assertEqual(entry["target_system"], "dept_b")
        self.assertEqual(entry["workflow_id"], "residence_certificate_verification")

    def test_field_mappings_filter_by_service_and_system(self):
        mappings = self.gateway.list_field_mappings(self.admin, service_id="residence_certificate_verification")
        self.assertTrue(mappings)
        self.assertTrue(all(m["service_id"] == "residence_certificate_verification" for m in mappings))

        dept_a_mappings = self.gateway.list_field_mappings(self.admin, system_id="dept_a")
        self.assertTrue(all(m["system_id"] == "dept_a" for m in dept_a_mappings))


if __name__ == "__main__":
    unittest.main()
