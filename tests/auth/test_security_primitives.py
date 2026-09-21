import importlib.util
import unittest
from datetime import UTC, datetime, timedelta

from app.core.exceptions import RateLimited, ValidationFailed
from app.core.rate_limit import FailureThrottle, ThrottlePolicy
from app.core.security import (
    SecretBox,
    SessionPolicy,
    SessionRecord,
    csrf_token_for,
    hash_token,
    new_token,
    validate_password_policy,
    verify_csrf,
)


class PasswordPolicyTests(unittest.TestCase):
    def test_accepts_long_password(self):
        validate_password_policy("a-long-enough-passphrase")

    def test_rejects_short_common_and_email(self):
        for pw, kw in [("short", {}), ("password123", {}), ("me@example.com", {"email": "ME@example.com"})]:
            with self.assertRaises(ValidationFailed, msg=pw):
                validate_password_policy(pw, **kw)

    def test_rejects_padded_whitespace(self):
        with self.assertRaises(ValidationFailed):
            validate_password_policy("  a-long-enough-passphrase")


class SecretBoxTests(unittest.TestCase):
    def test_round_trip_and_ciphertext_differs(self):
        box = SecretBox("k" * 32)
        token = box.encrypt("JBSWY3DPEHPK3PXP")
        self.assertNotIn("JBSWY3DPEHPK3PXP", token)
        self.assertEqual(box.decrypt(token), "JBSWY3DPEHPK3PXP")
        self.assertNotEqual(token, box.encrypt("JBSWY3DPEHPK3PXP"))  # random IV

    def test_wrong_key_and_tampering_fail(self):
        token = SecretBox("a" * 32).encrypt("x")
        with self.assertRaises(ValueError):
            SecretBox("b" * 32).decrypt(token)
        with self.assertRaises(ValueError):
            SecretBox("a" * 32).decrypt(token[:-4] + "AAAA")

    def test_key_rotation(self):
        old = SecretBox("o" * 32).encrypt("secret")
        self.assertEqual(SecretBox("n" * 32, "o" * 32).decrypt(old), "secret")

    def test_short_secret_rejected(self):
        with self.assertRaises(ValueError):
            SecretBox("short")


class SessionAndCsrfTests(unittest.TestCase):
    def test_tokens_unique_and_only_hash_is_derived(self):
        a, b = new_token(), new_token()
        self.assertNotEqual(a, b)
        self.assertEqual(len(hash_token(a)), 64)
        self.assertNotEqual(hash_token(a), a)

    def test_idle_absolute_and_revoked_expiry(self):
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        pol = SessionPolicy(idle=timedelta(minutes=30), absolute=timedelta(hours=2))
        s = SessionRecord("1", "u", "h", t0, t0)
        self.assertTrue(s.is_active(t0 + timedelta(minutes=29), pol))
        self.assertFalse(s.is_active(t0 + timedelta(minutes=31), pol))
        s.last_seen_at = t0 + timedelta(hours=2, minutes=1)
        self.assertFalse(s.is_active(t0 + timedelta(hours=2, minutes=2), pol))  # absolute
        s2 = SessionRecord("2", "u", "h", t0, t0, revoked_at=t0)
        self.assertFalse(s2.is_active(t0, pol))

    def test_csrf_binding(self):
        tok = csrf_token_for("sess-hash-1", "server-secret")
        self.assertTrue(verify_csrf(tok, "sess-hash-1", "server-secret"))
        self.assertFalse(verify_csrf(tok, "sess-hash-2", "server-secret"))
        self.assertFalse(verify_csrf(tok, "sess-hash-1", "other-secret"))
        self.assertFalse(verify_csrf(None, "sess-hash-1", "server-secret"))


class ThrottleTests(unittest.TestCase):
    def test_lockout_and_expiry(self):
        now = [1000.0]
        th = FailureThrottle(ThrottlePolicy(3, 60, 120), clock=lambda: now[0])
        for _ in range(3):
            th.check("k")
            th.record_failure("k")
        with self.assertRaises(RateLimited) as cm:
            th.check("k")
        self.assertGreater(cm.exception.retry_after_seconds, 0)
        now[0] += 121
        th.check("k")  # lock expired

    def test_failures_outside_window_do_not_count_and_success_resets(self):
        now = [0.0]
        th = FailureThrottle(ThrottlePolicy(3, 60, 120), clock=lambda: now[0])
        th.record_failure("k"); th.record_failure("k")
        now[0] += 61
        th.record_failure("k")
        th.check("k")
        th.record_failure("k"); th.record_success("k"); th.record_failure("k"); th.record_failure("k")
        th.check("k")


@unittest.skipUnless(importlib.util.find_spec("argon2"), "argon2-cffi not installed in this environment")
class Argon2Tests(unittest.TestCase):
    def test_hash_verify_and_no_plaintext(self):
        from app.core.security import Argon2Hasher

        h = Argon2Hasher()
        digest = h.hash("correct horse battery")
        self.assertTrue(digest.startswith("$argon2"))
        self.assertNotIn("correct horse", digest)
        self.assertTrue(h.verify(digest, "correct horse battery"))
        self.assertFalse(h.verify(digest, "wrong"))
        self.assertFalse(h.verify("not-a-hash", "x"))


if __name__ == "__main__":
    unittest.main()
