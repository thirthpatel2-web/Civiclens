import importlib.util
import unittest
from urllib.parse import parse_qs, urlparse

from app.core.exceptions import AuthenticationFailed, Conflict, ValidationFailed
from app.core.rate_limit import FailureThrottle, ThrottlePolicy
from app.core.security import SecretBox
from app.services.audit_service import AuditService
from app.services.mfa_service import MFAService
from tests.support import FakeClock, MemoryAuditRepo, MemoryMfaRepo, ReferenceTotp, hotp


class Rfc6238VectorTests(unittest.TestCase):
    """Validates the reference engine used by the other tests (RFC 6238 appendix B, SHA-1)."""

    def test_published_vectors(self):
        key = b"12345678901234567890"
        for t, expected in [
            (59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
            (1234567890, "89005924"), (2000000000, "69279037"), (20000000000, "65353130"),
        ]:  # fmt: skip
            self.assertEqual(hotp(key, t // 30, digits=8), expected, t)


def make_service(clock=None, throttle=None):
    clock = clock or FakeClock()
    audit_repo = MemoryAuditRepo()
    repo = MemoryMfaRepo()
    svc = MFAService(
        repo, SecretBox("m" * 32), ReferenceTotp(), AuditService(audit_repo, clock),
        clock=clock.epoch, throttle=throttle,
    )  # fmt: skip
    return svc, repo, audit_repo, clock


class MfaFlowTests(unittest.TestCase):
    def enroll(self, svc, clock, user="u1"):
        enrollment = svc.begin_enrollment(user, "citizen@example.com")
        code = ReferenceTotp.code_at(enrollment.manual_entry_secret, clock.epoch())
        backup = svc.confirm_enrollment(user, code)
        return enrollment, backup

    def test_provisioning_uri_is_authenticator_compatible(self):
        svc, *_ = make_service()
        e = svc.begin_enrollment("u1", "citizen@example.com")
        u = urlparse(e.provisioning_uri)
        self.assertEqual(u.scheme, "otpauth")
        self.assertEqual(u.netloc, "totp")
        q = parse_qs(u.query)
        self.assertEqual(q["secret"][0], e.manual_entry_secret)
        self.assertEqual(q["issuer"][0], "CivicLens")
        self.assertIn("citizen%40example.com", u.path)

    def test_secret_is_encrypted_at_rest(self):
        svc, repo, *_ = make_service()
        e = svc.begin_enrollment("u1", "a@b.co")
        stored = repo.get("u1").secret_encrypted
        self.assertNotIn(e.manual_entry_secret, stored)

    def test_not_enabled_until_confirmed(self):
        svc, _, _, clock = make_service()
        e = svc.begin_enrollment("u1", "a@b.co")
        self.assertFalse(svc.is_enabled("u1"))
        self.assertFalse(svc.verify_login("u1", ReferenceTotp.code_at(e.manual_entry_secret, clock.epoch())))

    def test_confirm_rejects_wrong_code_and_malformed_code(self):
        svc, *_ = make_service()
        svc.begin_enrollment("u1", "a@b.co")
        with self.assertRaises(AuthenticationFailed):
            svc.confirm_enrollment("u1", "000000")
        with self.assertRaises(ValidationFailed):
            svc.confirm_enrollment("u1", "12ab")

    def test_full_enrollment_then_login_verification(self):
        svc, _, _, clock = make_service()
        e, backup = self.enroll(svc, clock)
        self.assertTrue(svc.is_enabled("u1"))
        self.assertEqual(len(backup), 8)
        clock.advance(seconds=30)
        self.assertTrue(svc.verify_login("u1", ReferenceTotp.code_at(e.manual_entry_secret, clock.epoch())))

    def test_replay_of_same_code_is_rejected(self):
        svc, _, _, clock = make_service()
        e, _ = self.enroll(svc, clock)
        clock.advance(seconds=60)
        code = ReferenceTotp.code_at(e.manual_entry_secret, clock.epoch())
        self.assertTrue(svc.verify_login("u1", code))
        self.assertFalse(svc.verify_login("u1", code))

    def test_confirmation_code_cannot_be_replayed_for_login(self):
        svc, _, _, clock = make_service()
        e, _ = self.enroll(svc, clock)
        same = ReferenceTotp.code_at(e.manual_entry_secret, clock.epoch())
        self.assertFalse(svc.verify_login("u1", same))

    def test_wrong_and_stale_codes_rejected(self):
        svc, _, _, clock = make_service()
        e, _ = self.enroll(svc, clock)
        clock.advance(seconds=30)
        self.assertFalse(svc.verify_login("u1", "123456"))
        old = ReferenceTotp.code_at(e.manual_entry_secret, clock.epoch() - 300)
        self.assertFalse(svc.verify_login("u1", old))

    def test_backup_code_single_use(self):
        svc, _, _, clock = make_service()
        _, backup = self.enroll(svc, clock)
        self.assertTrue(svc.verify_login("u1", backup[0].lower()))
        self.assertFalse(svc.verify_login("u1", backup[0]))
        self.assertTrue(svc.verify_login("u1", backup[1]))

    def test_backup_codes_stored_hashed(self):
        svc, repo, _, clock = make_service()
        _, backup = self.enroll(svc, clock)
        for code in backup:
            self.assertNotIn(code, repo.get("u1").backup_code_hashes)

    def test_disable_requires_reauth_and_valid_code(self):
        svc, _, _, clock = make_service()
        e, _ = self.enroll(svc, clock)
        clock.advance(seconds=60)
        code = ReferenceTotp.code_at(e.manual_entry_secret, clock.epoch())
        with self.assertRaises(AuthenticationFailed):
            svc.disable("u1", code, reauthenticated=False)
        with self.assertRaises(AuthenticationFailed):
            svc.disable("u1", "000000", reauthenticated=True)
        svc.disable("u1", code, reauthenticated=True)
        self.assertFalse(svc.is_enabled("u1"))

    def test_cannot_reenroll_while_enabled(self):
        svc, _, _, clock = make_service()
        self.enroll(svc, clock)
        with self.assertRaises(Conflict):
            svc.begin_enrollment("u1", "a@b.co")

    def test_failed_attempts_are_throttled(self):
        clock = FakeClock()
        th = FailureThrottle(ThrottlePolicy(3, 60, 60), clock=clock.epoch)
        svc, _, _, _ = make_service(clock, th)
        self.enroll(svc, clock)
        from app.core.exceptions import RateLimited

        for _ in range(3):
            svc.verify_login("u1", "111111")
        with self.assertRaises(RateLimited):
            svc.verify_login("u1", "111111")

    def test_audit_trail_contains_no_secret_or_code(self):
        svc, _, audit_repo, clock = make_service()
        e, backup = self.enroll(svc, clock)
        blob = repr(audit_repo.events)
        self.assertNotIn(e.manual_entry_secret, blob)
        for code in backup:
            self.assertNotIn(code, blob)
        self.assertIn("mfa.enabled", audit_repo.actions())

    def test_invalid_window_type_rejected(self):
        with self.assertRaises(ValueError):
            MFAService(MemoryMfaRepo(), SecretBox("m" * 32), ReferenceTotp(),
                       AuditService(MemoryAuditRepo()), window=0.5)  # type: ignore[arg-type]


@unittest.skipUnless(importlib.util.find_spec("pyotp"), "pyotp not installed in this environment")
class PyOtpInteropTests(unittest.TestCase):
    """Runs only where pyotp exists: proves PyOtpEngine agrees with the RFC reference."""

    def test_engine_matches_reference_and_uri(self):
        from app.services.mfa_service import PyOtpEngine

        eng = PyOtpEngine()
        secret = eng.random_secret()
        now = 1_800_000_000.0
        code = ReferenceTotp.code_at(secret, now)
        self.assertEqual(eng.match(secret, code, at=now), int(now // 30))
        self.assertIsNone(eng.match(secret, "000000", at=now))
        self.assertTrue(eng.provisioning_uri(secret, "a@b.co", "CivicLens").startswith("otpauth://totp/"))


@unittest.skipUnless(importlib.util.find_spec("qrcode"), "qrcode not installed in this environment")
class QrTests(unittest.TestCase):
    def test_qr_png_bytes(self):
        from app.services.mfa_service import render_qr_png

        png = render_qr_png("otpauth://totp/CivicLens:a@b.co?secret=JBSWY3DPEHPK3PXP&issuer=CivicLens")
        self.assertTrue(png.startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
