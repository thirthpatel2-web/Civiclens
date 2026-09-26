"""Citizen-owned consent against a live database: a consent request lands with the citizen whose
verified mobile matches the department records (and notifies them), never guesses when two accounts
share a number, and the demo reset reopens applications while keeping history. Skips without a DB."""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.core.authorization import AuthContext, Role
from app.db.models.identity import ProfileModel, UserModel
from app.db.models.interop_platform import (
    InteropConsentGrant,
    MasterIdentifier,
    MockDeptBApplication,
)
from app.db.models.ops import NotificationModel
from app.db.uow import SqlUnitOfWork
from tests.integration.test_interop_gateway_e2e import (
    _DB_AVAILABLE,
    _SKIP_REASON,
    DocumentExchangeEndToEndTests,
)


@unittest.skipUnless(_DB_AVAILABLE, _SKIP_REASON)
class CitizenOwnedConsentTests(DocumentExchangeEndToEndTests):
    """Reuses the e2e fixture (its own resident/beneficiary with mobile 9812345678, cleaned up after)."""

    def setUp(self) -> None:
        super().setUp()
        self._extra_users: list[str] = []

    def tearDown(self) -> None:
        with SqlUnitOfWork(self.session_factory) as uow:
            # find this test's identities from its own fixture ids, so even a test that failed before
            # recording its master id leaves nothing behind for the next run to trip over
            found = uow.session.execute(select(MasterIdentifier.master_id).where(MasterIdentifier.identifier_value.in_([self.resident_id, self.beneficiary_code]))).scalars().all()
            self._created_master_ids.update(str(m) for m in found)
        super().tearDown()  # transactions before consents before identities - the parent knows the FK order
        with SqlUnitOfWork(self.session_factory) as uow:
            s = uow.session
            for uid in self._extra_users:
                s.execute(delete(InteropConsentGrant).where(InteropConsentGrant.citizen_user_id == uid))
                s.execute(delete(NotificationModel).where(NotificationModel.user_id == uid))
                s.execute(delete(ProfileModel).where(ProfileModel.user_id == uid))
            s.execute(delete(UserModel).where(UserModel.id.in_(self._extra_users)))
            uow.commit()

    def _citizen(self, phone: str) -> str:
        uid = str(uuid.uuid4())
        now = datetime.now(UTC)
        with SqlUnitOfWork(self.session_factory) as uow:
            uow.session.add(UserModel(id=uid, email=f"consent-{uid[:8]}@example.invalid", password_hash="x", full_name="Kavita Rane", role="citizen", is_active=True, created_at=now))
            uow.session.flush()
            uow.session.add(ProfileModel(user_id=uid, full_name="Kavita Rane", phone=phone, language="en", onboarding_complete=True, updated_at=now))
            uow.commit()
        self._extra_users.append(uid)
        return uid

    def test_consent_request_lands_with_the_matching_citizen_and_notifies_them(self) -> None:
        citizen = self._citizen("+91 98123 45678")  # same number as the fixture resident, different formatting
        first = self.gateway.request_document_exchange(self.admin, application_no=self.application_no)
        self._created_master_ids.add(first["master_id"])
        self.assertEqual((first["status"], first["citizen_linked"]), ("consent_required", True))
        with SqlUnitOfWork(self.session_factory) as uow:
            self.assertEqual(uow.session.get(InteropConsentGrant, first["consent_id"]).citizen_user_id, citizen)
            kinds = [n.kind for n in uow.session.execute(select(NotificationModel).where(NotificationModel.user_id == citizen)).scalars()]
        self.assertIn("interop.consent_requested", kinds)
        me = AuthContext(citizen, Role.CITIZEN, None, True)
        self.assertEqual([c["consent_id"] for c in self.gateway.list_my_consents(me)], [first["consent_id"]])
        self.assertEqual(self.gateway.grant_consent(me, consent_id=first["consent_id"])["status"], "granted")  # the citizen decides
        self.assertEqual(self.gateway.request_document_exchange(self.admin, application_no=self.application_no)["status"], "success")

    def test_two_accounts_with_the_same_number_are_never_guessed_between(self) -> None:
        self._citizen("9812345678")
        self._citizen("09812345678")
        first = self.gateway.request_document_exchange(self.admin, application_no=self.application_no)
        self._created_master_ids.add(first["master_id"])
        self.assertFalse(first["citizen_linked"])
        with SqlUnitOfWork(self.session_factory) as uow:
            self.assertEqual(uow.session.get(InteropConsentGrant, first["consent_id"]).citizen_user_id, self.user_id)

    def test_demo_reset_reopens_applications_and_withdraws_consents_with_a_reason(self) -> None:
        first = self.gateway.request_document_exchange(self.admin, application_no=self.application_no)
        self._created_master_ids.add(first["master_id"])
        self.gateway.grant_consent(self.admin, consent_id=first["consent_id"])
        self.assertEqual(self.gateway.request_document_exchange(self.admin, application_no=self.application_no)["status"], "success")
        out = self.gateway.reset_demo_scenario(self.admin)
        self.assertGreaterEqual(out["consents_withdrawn"], 1)
        with SqlUnitOfWork(self.session_factory) as uow:
            app_row = uow.session.get(MockDeptBApplication, self.application_no)
            grant = uow.session.get(InteropConsentGrant, first["consent_id"])
            self.assertEqual((app_row.status, app_row.document_status, app_row.document_reference), ("pending_document", "missing", None))
            self.assertEqual((grant.status, grant.revocation_reason), ("revoked", "Demo scenario reset"))
        self.assertEqual({a["application_no"] for a in self.gateway.list_demo_applications(self.admin)} >= {self.application_no}, True)

    def test_an_auditor_can_list_but_never_reset(self) -> None:
        from app.core.exceptions import PermissionDenied

        auditor = AuthContext(self.user_id, Role.AUDITOR, None, True)
        self.assertTrue(self.gateway.list_demo_applications(auditor))
        with self.assertRaises(PermissionDenied):
            self.gateway.reset_demo_scenario(auditor)


# Only this class's own tests: the fixture is inherited, the parent's test methods are not re-run here.
for _name in dir(DocumentExchangeEndToEndTests):
    if _name.startswith("test_") and _name not in CitizenOwnedConsentTests.__dict__:
        setattr(CitizenOwnedConsentTests, _name, None)


if __name__ == "__main__":
    unittest.main()
