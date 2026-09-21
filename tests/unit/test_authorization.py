import unittest

from app.core.authorization import (
    AuthContext,
    Role,
    can_access_complaint,
    can_assign_role,
    require,
    require_complaint_access,
    require_mfa_for_privileged,
)
from app.core.authorization import (
    Permission as P,
)
from app.core.exceptions import PermissionDenied

CIT = AuthContext("citizen-1", Role.CITIZEN)
OFF_ROADS = AuthContext("off-1", Role.OFFICER, "roads")
OFF_NODEPT = AuthContext("off-2", Role.OFFICER, None)
ADMIN = AuthContext("adm-1", Role.ADMIN, None, mfa_verified=True)
ADMIN_ROADS = AuthContext("adm-2", Role.ADMIN, "roads", mfa_verified=True)
SUPER = AuthContext("sup-1", Role.SUPER_ADMIN, None, mfa_verified=True)


class PermissionMatrixTests(unittest.TestCase):
    def test_citizen_cannot_reach_admin_or_officer_functions(self):
        for p in (P.ADMIN_DASHBOARD, P.ADMIN_USERS, P.ADMIN_AUDIT, P.COMPLAINT_UPDATE_STATUS,
                  P.COMPLAINT_READ_DEPARTMENT, P.ROLE_ASSIGN_PRIVILEGED):  # fmt: skip
            with self.assertRaises(PermissionDenied, msg=p):
                require(CIT, p)

    def test_citizen_can_use_citizen_functions(self):
        for p in (P.COMPLAINT_CREATE, P.EVIDENCE_UPLOAD, P.RTI_MANAGE_OWN, P.LEGAL_ANALYZE,
                  P.GIS_VIEW, P.ASSISTANT_USE, P.COMPLAINT_FEEDBACK, P.NOTIFICATION_READ_OWN):  # fmt: skip
            require(CIT, p)

    def test_officer_can_action_but_not_administer_or_file(self):
        for p in (P.COMPLAINT_UPDATE_STATUS, P.COMPLAINT_REMARK, P.COMPLAINT_FIELD_ACTION, P.SLA_VIEW):
            require(OFF_ROADS, p)
        for p in (P.ADMIN_DASHBOARD, P.ADMIN_USERS, P.ADMIN_ROUTING_RULES, P.COMPLAINT_CREATE):
            with self.assertRaises(PermissionDenied):
                require(OFF_ROADS, p)

    def test_admin_administers_but_cannot_action_complaints_or_grant_privileged(self):
        for p in (P.ADMIN_DASHBOARD, P.ADMIN_AUDIT, P.ADMIN_INTEGRATIONS, P.ANALYTICS_VIEW):
            require(ADMIN, p)
        for p in (P.COMPLAINT_UPDATE_STATUS, P.ROLE_ASSIGN_PRIVILEGED):
            with self.assertRaises(PermissionDenied):
                require(ADMIN, p)

    def test_super_admin_has_every_permission(self):
        for p in P:
            require(SUPER, p)


class RecordAccessTests(unittest.TestCase):
    def test_citizen_only_own_and_read_only(self):
        self.assertTrue(can_access_complaint(CIT, owner_id="citizen-1", department_id="roads"))
        self.assertFalse(can_access_complaint(CIT, owner_id="someone-else", department_id="roads"))
        self.assertFalse(can_access_complaint(CIT, owner_id="citizen-1", department_id="roads", write=True))

    def test_officer_department_isolation(self):
        self.assertTrue(can_access_complaint(OFF_ROADS, owner_id="x", department_id="roads", write=True))
        self.assertFalse(can_access_complaint(OFF_ROADS, owner_id="x", department_id="water"))
        self.assertFalse(can_access_complaint(OFF_ROADS, owner_id="x", department_id=None))
        self.assertFalse(can_access_complaint(OFF_NODEPT, owner_id="x", department_id="roads"))
        with self.assertRaises(PermissionDenied):
            require_complaint_access(OFF_ROADS, owner_id="x", department_id="water")

    def test_admin_scope(self):
        self.assertTrue(can_access_complaint(ADMIN, owner_id="x", department_id="water"))
        self.assertTrue(can_access_complaint(ADMIN_ROADS, owner_id="x", department_id="roads"))
        self.assertFalse(can_access_complaint(ADMIN_ROADS, owner_id="x", department_id="water"))
        self.assertFalse(can_access_complaint(ADMIN, owner_id="x", department_id="water", write=True))

    def test_super_admin_everything(self):
        self.assertTrue(can_access_complaint(SUPER, owner_id="x", department_id="water", write=True))


class RoleAssignmentTests(unittest.TestCase):
    def test_no_self_promotion(self):
        for actor in (CIT, OFF_ROADS, ADMIN, SUPER):
            self.assertFalse(can_assign_role(actor, target_user_id=actor.user_id, new_role=Role.SUPER_ADMIN))

    def test_only_super_admin_grants_privileged(self):
        self.assertFalse(can_assign_role(ADMIN, target_user_id="u", new_role=Role.ADMIN))
        self.assertTrue(can_assign_role(SUPER, target_user_id="u", new_role=Role.ADMIN))

    def test_admin_manages_lower_roles_but_citizen_and_officer_cannot(self):
        self.assertTrue(can_assign_role(ADMIN, target_user_id="u", new_role=Role.OFFICER))
        self.assertFalse(can_assign_role(OFF_ROADS, target_user_id="u", new_role=Role.OFFICER))
        self.assertFalse(can_assign_role(CIT, target_user_id="u", new_role=Role.CITIZEN))


class MfaRequirementTests(unittest.TestCase):
    def test_privileged_requires_mfa(self):
        with self.assertRaises(PermissionDenied):
            require_mfa_for_privileged(AuthContext("a", Role.ADMIN, None, mfa_verified=False))
        require_mfa_for_privileged(ADMIN)
        require_mfa_for_privileged(CIT)


if __name__ == "__main__":
    unittest.main()
