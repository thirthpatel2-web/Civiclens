"""The mock Government Identity Provider (app.interop.federation.idp) against a live database:
client registration, the client_credentials grant, token validation, expiry, and revocation
("logout") - the concrete pieces Section 9 (federated identity / SSO) of the completion spec asks
for. Skips cleanly if no live database is reachable, for the same reason the other interop
integration tests do (real persisted tables, not in-memory doubles)."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.core.config import Settings
from app.db.models.interop_platform import FederationClient, FederationToken
from app.db.session import make_engine, make_session_factory
from app.db.uow import SqlUnitOfWork
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


class _FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


@unittest.skipUnless(_DB_AVAILABLE, _SKIP_REASON)
class MockGovernmentIdPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session_factory = make_session_factory(_engine)
        self.uow_factory = lambda: SqlUnitOfWork(self.session_factory)
        self.client_id = f"test-client-{id(self)}"
        with self.uow_factory() as uow:
            idp.register_client(uow.session, client_id=self.client_id, name="Test System (demo)", system="test_system", client_secret="correct-horse-battery-staple", scopes=["interop:read", "interop:write"])
            uow.commit()

    def tearDown(self) -> None:
        with self.uow_factory() as uow:
            s = uow.session
            s.execute(delete(FederationToken).where(FederationToken.client_id == self.client_id))
            s.execute(delete(FederationClient).where(FederationClient.client_id == self.client_id))
            uow.commit()

    def test_demo_client_set_is_exactly_the_three_mock_connectors(self):
        # Pure/static - avoids fighting seed_if_empty's whole-table emptiness gate against this
        # test class's own setUp fixture client (see test_registering_a_demo_client_directly below
        # for the actual registration behavior, exercised without that interaction).
        self.assertEqual({connector_id for connector_id, _n, _s in idp._DEMO_CLIENTS}, {"dept_a", "dept_b", "dept_c"})  # noqa: SLF001

    def test_registering_a_demo_client_directly_produces_a_working_client(self):
        connector_id, name, secret = idp._DEMO_CLIENTS[0]  # noqa: SLF001
        probe_id = f"{connector_id}-probe-{id(self)}"
        try:
            with self.uow_factory() as uow:
                idp.register_client(uow.session, client_id=probe_id, name=name, system=connector_id, client_secret=secret, scopes=list(idp.DEFAULT_SCOPES))
                uow.commit()
            with self.uow_factory() as uow:
                raw, claims = idp.issue_token(uow.session, client_id=probe_id, client_secret=secret)
                uow.commit()
            self.assertEqual(claims.system, connector_id)
            self.assertEqual(set(claims.scope), set(idp.DEFAULT_SCOPES))
        finally:
            with self.uow_factory() as uow:
                s = uow.session
                s.execute(delete(FederationToken).where(FederationToken.client_id == probe_id))
                s.execute(delete(FederationClient).where(FederationClient.client_id == probe_id))
                uow.commit()

    def test_client_credentials_grant_issues_a_valid_token(self):
        with self.uow_factory() as uow:
            raw, claims = idp.issue_token(uow.session, client_id=self.client_id, client_secret="correct-horse-battery-staple")
            uow.commit()
        self.assertTrue(raw)
        self.assertEqual(claims.client_id, self.client_id)
        self.assertEqual(claims.system, "test_system")
        self.assertEqual(set(claims.scope), {"interop:read", "interop:write"})

        with self.uow_factory() as uow:
            validated = idp.validate_token(uow.session, raw)
        self.assertEqual(validated.client_id, self.client_id)

    def test_wrong_secret_is_refused(self):
        with self.uow_factory() as uow:
            with self.assertRaises(idp.InvalidClient):
                idp.issue_token(uow.session, client_id=self.client_id, client_secret="wrong-secret")

    def test_unknown_client_is_refused(self):
        with self.uow_factory() as uow:
            with self.assertRaises(idp.InvalidClient):
                idp.issue_token(uow.session, client_id="no-such-client", client_secret="anything")

    def test_scope_narrowing_is_honored_and_never_widened(self):
        with self.uow_factory() as uow:
            _raw, claims = idp.issue_token(uow.session, client_id=self.client_id, client_secret="correct-horse-battery-staple", scope=["interop:read", "interop:admin_override"])
            uow.commit()
        # "interop:admin_override" was never in allowed_scopes - a client cannot grant itself more than it was registered with.
        self.assertEqual(set(claims.scope), {"interop:read"})

    def test_an_unrecognized_token_is_invalid(self):
        with self.uow_factory() as uow:
            with self.assertRaises(idp.InvalidToken):
                idp.validate_token(uow.session, "this-token-was-never-issued")

    def test_a_token_stops_validating_after_expiry(self):
        clock = _FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
        with self.uow_factory() as uow:
            raw, _claims = idp.issue_token(uow.session, client_id=self.client_id, client_secret="correct-horse-battery-staple", clock=clock)
            uow.commit()
        with self.uow_factory() as uow:
            idp.validate_token(uow.session, raw, clock=clock)  # still valid right after issuance

        clock.advance(hours=2)  # past the 1-hour TOKEN_TTL
        with self.uow_factory() as uow:
            with self.assertRaises(idp.InvalidToken):
                idp.validate_token(uow.session, raw, clock=clock)

    def test_revocation_is_immediate_even_before_expiry(self):
        with self.uow_factory() as uow:
            raw, _claims = idp.issue_token(uow.session, client_id=self.client_id, client_secret="correct-horse-battery-staple")
            uow.commit()
        with self.uow_factory() as uow:
            idp.validate_token(uow.session, raw)  # valid before revocation

        with self.uow_factory() as uow:
            self.assertTrue(idp.revoke_token(uow.session, raw))
            uow.commit()

        with self.uow_factory() as uow:
            with self.assertRaises(idp.InvalidToken):
                idp.validate_token(uow.session, raw)

        with self.uow_factory() as uow:
            self.assertFalse(idp.revoke_token(uow.session, raw))  # revoking twice is a no-op, not an error

    def test_introspect_never_explains_why_a_token_is_invalid(self):
        """RFC 7662's own privacy rule: {"active": false}, nothing more - expired, revoked, and
        unknown must all look identical from the outside."""
        with self.uow_factory() as uow:
            unknown = idp.introspect(uow.session, "never-issued")
        self.assertEqual(unknown, {"active": False})

        with self.uow_factory() as uow:
            raw, _claims = idp.issue_token(uow.session, client_id=self.client_id, client_secret="correct-horse-battery-staple")
            uow.commit()
        with self.uow_factory() as uow:
            idp.revoke_token(uow.session, raw)
            uow.commit()
        with self.uow_factory() as uow:
            revoked = idp.introspect(uow.session, raw)
        self.assertEqual(revoked, {"active": False})

    def test_introspect_of_a_valid_token_carries_real_claims(self):
        with self.uow_factory() as uow:
            raw, _claims = idp.issue_token(uow.session, client_id=self.client_id, client_secret="correct-horse-battery-staple")
            uow.commit()
        with self.uow_factory() as uow:
            result = idp.introspect(uow.session, raw)
        self.assertTrue(result["active"])
        self.assertEqual(result["client_id"], self.client_id)
        self.assertEqual(result["system"], "test_system")
        self.assertEqual(result["iss"], idp.ISSUER)

    def test_disabling_the_client_invalidates_its_already_issued_tokens(self):
        with self.uow_factory() as uow:
            raw, _claims = idp.issue_token(uow.session, client_id=self.client_id, client_secret="correct-horse-battery-staple")
            uow.commit()
        with self.uow_factory() as uow:
            idp.validate_token(uow.session, raw)  # valid while the client is enabled

        with self.uow_factory() as uow:
            client = uow.session.get(FederationClient, self.client_id)
            client.enabled = False
            uow.session.add(client)
            uow.commit()

        with self.uow_factory() as uow:
            with self.assertRaises(idp.InvalidToken):
                idp.validate_token(uow.session, raw)


if __name__ == "__main__":
    unittest.main()
