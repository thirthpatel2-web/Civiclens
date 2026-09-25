import unittest
from dataclasses import replace

from app.core.authorization import Role
from app.core.exceptions import (
    AuthenticationFailed,
    Conflict,
    PermissionDenied,
    RateLimited,
    ValidationFailed,
)
from app.core.rate_limit import FailureThrottle, ThrottlePolicy
from app.core.security import SecretBox, hash_token
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.mfa_service import MFAService
from tests.support import (
    FakeClock,
    MemoryAuditRepo,
    MemoryMfaRepo,
    MemoryResetRepo,
    MemorySessionRepo,
    MemoryUserRepo,
    ReferenceTotp,
    ScryptTestHasher,
)

PW = "a-long-enough-passphrase"


class Harness:
    def __init__(self, throttle=None):
        self.clock = FakeClock()
        self.audit_repo = MemoryAuditRepo()
        audit = AuditService(self.audit_repo, self.clock)
        self.users, self.sessions, self.resets = MemoryUserRepo(), MemorySessionRepo(), MemoryResetRepo()
        self.hasher = ScryptTestHasher()
        self.mfa_repo = MemoryMfaRepo()
        self.mfa = MFAService(self.mfa_repo, SecretBox("m" * 32), ReferenceTotp(), audit, clock=self.clock.epoch)
        self.auth = AuthService(self.users, self.sessions, self.resets, self.hasher, self.mfa, audit,
                                throttle=throttle, clock=self.clock)  # fmt: skip

    def enable_mfa(self, user):
        e = self.mfa.begin_enrollment(user.id, user.email)
        self.mfa.confirm_enrollment(user.id, ReferenceTotp.code_at(e.manual_entry_secret, self.clock.epoch()))
        self.clock.advance(seconds=30)
        return e.manual_entry_secret


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def test_register_creates_citizen_with_hashed_password(self):
        u = self.h.auth.register("  Asha@Example.com ", PW, "Asha Rao")
        self.assertEqual(u.email, "asha@example.com")
        self.assertIs(u.role, Role.CITIZEN)
        self.assertNotIn(PW, u.password_hash)

    def test_register_has_no_role_parameter(self):
        with self.assertRaises(TypeError):
            self.h.auth.register("a@example.com", PW, "Asha Rao", role="admin")  # type: ignore[call-arg]

    def test_duplicate_invalid_and_weak(self):
        self.h.auth.register("a@example.com", PW, "Asha Rao")
        with self.assertRaises(Conflict):
            self.h.auth.register("A@example.com", PW, "Other Person")
        with self.assertRaises(ValidationFailed):
            self.h.auth.register("not-an-email", PW, "Asha Rao")
        with self.assertRaises(ValidationFailed):
            self.h.auth.register("b@example.com", "short", "Asha Rao")
        with self.assertRaises(ValidationFailed):
            self.h.auth.register("b@example.com", PW, "x")


class LoginSessionTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.user = self.h.auth.register("a@example.com", PW, "Asha Rao")

    def test_login_logout_invalidates_session(self):
        res = self.h.auth.login("a@example.com", PW)
        ctx = self.h.auth.authenticate(res.session_token)
        self.assertEqual(ctx.user_id, self.user.id)
        self.h.auth.logout(res.session_token)
        with self.assertRaises(AuthenticationFailed):
            self.h.auth.authenticate(res.session_token)

    def test_only_token_hash_is_stored(self):
        res = self.h.auth.login("a@example.com", PW)
        self.assertNotIn(res.session_token, self.h.sessions.rows)
        self.assertIn(hash_token(res.session_token), self.h.sessions.rows)

    def test_bad_password_and_unknown_user_share_one_message(self):
        msgs = set()
        for email, pw in [("a@example.com", "wrong-password-1"), ("nobody@example.com", PW), ("bad", PW)]:
            with self.assertRaises(AuthenticationFailed) as cm:
                self.h.auth.login(email, pw)
            msgs.add(cm.exception.message)
        self.assertEqual(len(msgs), 1)

    def test_session_idle_expiry(self):
        res = self.h.auth.login("a@example.com", PW)
        self.h.clock.advance(minutes=31)
        with self.assertRaises(AuthenticationFailed):
            self.h.auth.authenticate(res.session_token)

    def test_role_comes_from_database_not_session_or_client(self):
        res = self.h.auth.login("a@example.com", PW)
        self.h.users.update(replace(self.user, role=Role.OFFICER, department_id="dept-roads"))
        ctx = self.h.auth.authenticate(res.session_token)
        self.assertIs(ctx.role, Role.OFFICER)
        self.assertEqual(ctx.department_id, "dept-roads")
        self.h.users.update(replace(self.user, is_active=False))
        with self.assertRaises(AuthenticationFailed):
            self.h.auth.authenticate(res.session_token)

    def test_missing_or_garbage_token(self):
        for tok in (None, "", "garbage"):
            with self.assertRaises(AuthenticationFailed):
                self.h.auth.authenticate(tok)

    def test_lockout_after_repeated_failures(self):
        h = Harness(FailureThrottle(ThrottlePolicy(3, 60, 60), clock=lambda: 0.0))
        h.auth.register("a@example.com", PW, "Asha Rao")
        for _ in range(3):
            with self.assertRaises(AuthenticationFailed):
                h.auth.login("a@example.com", "bad-password-x")
        with self.assertRaises(RateLimited):
            h.auth.login("a@example.com", PW)  # even the right password is refused while locked

    def test_rehash_on_login(self):
        self.h.hasher.force_rehash = True
        old = self.h.users.get_by_id(self.user.id).password_hash
        self.h.auth.login("a@example.com", PW)
        self.assertNotEqual(self.h.users.get_by_id(self.user.id).password_hash, old)


class LoginWith2faTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.user = self.h.auth.register("a@example.com", PW, "Asha Rao")
        self.secret = self.h.enable_mfa(self.user)

    def test_password_alone_is_enough_even_with_mfa_enabled(self):
        """Two-factor is opt-in and never blocks sign-in - an account that enrolled MFA still logs
        in with just email + password, exactly like one that never enrolled."""
        res = self.h.auth.login("a@example.com", PW)
        self.assertTrue(res.context.mfa_verified)
        self.assertEqual(len(self.h.sessions.rows), 1)

    def test_a_wrong_otp_is_simply_ignored_not_checked(self):
        res = self.h.auth.login("a@example.com", PW, otp="000000")
        self.assertTrue(res.context.mfa_verified)

    def test_otp_alone_without_password_rejected(self):
        self.h.clock.advance(seconds=30)
        with self.assertRaises(AuthenticationFailed):
            self.h.auth.login("a@example.com", "wrong-password-1", otp=ReferenceTotp.code_at(self.secret, self.h.clock.epoch()))


class PasswordResetTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.user = self.h.auth.register("a@example.com", PW, "Asha Rao")

    def test_reset_flow_single_use_and_revokes_sessions(self):
        res = self.h.auth.login("a@example.com", PW)
        token = self.h.auth.request_password_reset("a@example.com")
        self.assertIsNotNone(token)
        self.assertNotIn(token, self.h.resets.rows)  # stored hashed
        self.h.auth.reset_password(token, "brand-new-passphrase")
        with self.assertRaises(AuthenticationFailed):
            self.h.auth.authenticate(res.session_token)
        self.h.auth.login("a@example.com", "brand-new-passphrase")
        with self.assertRaises(AuthenticationFailed):
            self.h.auth.login("a@example.com", PW)
        with self.assertRaises(AuthenticationFailed):
            self.h.auth.reset_password(token, "another-new-passphrase")  # reuse

    def test_expired_token_and_unknown_email(self):
        token = self.h.auth.request_password_reset("a@example.com")
        self.h.clock.advance(hours=2)
        with self.assertRaises(AuthenticationFailed):
            self.h.auth.reset_password(token, "brand-new-passphrase")
        self.assertIsNone(self.h.auth.request_password_reset("nobody@example.com"))
        self.assertIsNone(self.h.auth.request_password_reset("garbage"))

    def test_reset_enforces_policy(self):
        token = self.h.auth.request_password_reset("a@example.com")
        with self.assertRaises(ValidationFailed):
            self.h.auth.reset_password(token, "short")

    def test_change_password(self):
        res = self.h.auth.login("a@example.com", PW)
        ctx = self.h.auth.authenticate(res.session_token)
        with self.assertRaises(AuthenticationFailed):
            self.h.auth.change_password(ctx, "not-my-password", "brand-new-passphrase")
        self.h.auth.change_password(ctx, PW, "brand-new-passphrase")
        with self.assertRaises(AuthenticationFailed):
            self.h.auth.authenticate(res.session_token)


class AdminBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def test_requires_setup_token_and_only_once(self):
        with self.assertRaises(PermissionDenied):
            self.h.auth.bootstrap_first_admin("root@example.com", PW, "Root", provided_token="bad", expected_token="tok-123")
        with self.assertRaises(PermissionDenied):
            self.h.auth.bootstrap_first_admin("root@example.com", PW, "Root", provided_token="", expected_token="")
        admin = self.h.auth.bootstrap_first_admin("root@example.com", PW, "Root", provided_token="tok-123", expected_token="tok-123")
        self.assertIs(admin.role, Role.SUPER_ADMIN)
        with self.assertRaises(Conflict):
            self.h.auth.bootstrap_first_admin("two@example.com", PW, "Two", provided_token="tok-123", expected_token="tok-123")


class AuditSafetyTests(unittest.TestCase):
    def test_no_password_or_token_in_audit_events(self):
        h = Harness()
        h.auth.register("a@example.com", PW, "Asha Rao")
        res = h.auth.login("a@example.com", PW)
        with self.assertRaises(AuthenticationFailed):
            h.auth.login("a@example.com", "wrong-password-1")
        h.auth.logout(res.session_token)
        blob = repr(h.audit_repo.events)
        for needle in (PW, "wrong-password-1", res.session_token):
            self.assertNotIn(needle, blob)
        for action in ("auth.registered", "auth.login", "auth.login_failed", "auth.logout"):
            self.assertIn(action, h.audit_repo.actions())


if __name__ == "__main__":
    unittest.main()
