import io
import json
import logging
import unittest

from app.core.config import ConfigError, Settings
from app.core.exceptions import CivicLensError, NotFound, RateLimited
from app.core.logging import configure_logging, correlation_id_var, redact, redact_mapping

GOOD = "x" * 40


class ConfigTests(unittest.TestCase):
    def test_defaults_in_development(self):
        s = Settings.load({})
        self.assertEqual(s.app_env, "development")
        self.assertEqual((s.bm25_k1, s.bm25_b, s.rrf_k), (1.5, 0.75, 60))
        self.assertEqual(s.max_upload_bytes, 10 * 1024 * 1024)

    def test_production_rejects_missing_or_placeholder_secrets(self):
        for env in (
            {"APP_ENV": "production"},
            {"APP_ENV": "production", "APP_SECRET_KEY": "change-me", "SESSION_SECRET": GOOD, "DATABASE_URL": "x"},
            {"APP_ENV": "production", "APP_SECRET_KEY": GOOD, "SESSION_SECRET": "short", "DATABASE_URL": "x"},
        ):
            with self.assertRaises(ConfigError):
                Settings.load(env)

    def test_production_accepts_real_secrets(self):
        s = Settings.load({"APP_ENV": "production", "APP_SECRET_KEY": GOOD, "SESSION_SECRET": GOOD + "y", "DATABASE_URL": "postgresql://h/db"})
        self.assertTrue(s.is_production)

    def test_bhashini_and_drive_require_credentials_when_enabled(self):
        with self.assertRaises(ConfigError):
            Settings.load({"BHASHINI_ENABLED": "true"})
        with self.assertRaises(ConfigError):
            Settings.load({"GOOGLE_DRIVE_ENABLED": "true"})
        Settings.load({"BHASHINI_ENABLED": "true", "BHASHINI_API_KEY": "k", "BHASHINI_USER_ID": "u"})

    def test_bad_numbers_and_env(self):
        for env in ({"RRF_K": "abc"}, {"APP_ENV": "staging"}, {"BM25_B": "2"}, {"MAX_UPLOAD_MB": "0"}):
            with self.assertRaises(ConfigError):
                Settings.load(env)

    def test_repr_and_redacted_hide_secrets(self):
        s = Settings.load({"APP_SECRET_KEY": "super-secret-value", "DATABASE_URL": "postgresql://u:pw@h/db"})
        self.assertNotIn("super-secret-value", repr(s))
        self.assertNotIn("pw@h", repr(s))
        self.assertEqual(s.redacted()["app_secret_key"], "<set>")
        self.assertEqual(s.redacted()["session_secret"], "<unset>")


class RedactionTests(unittest.TestCase):
    def test_free_text(self):
        for raw in (
            "login password=hunter2 ok",
            'payload {"api_key": "sk-abc123"} sent',
            "Authorization: Bearer abc.def.ghi",
            "uri otpauth://totp/CivicLens:a@b.co?secret=JBSWY3DPEHPK3PXP&issuer=CivicLens",
            "SESSION_SECRET=abcdef",
            "otp=123456",
        ):
            out = redact(raw)
            for leaked in ("hunter2", "sk-abc123", "abc.def.ghi", "JBSWY3DPEHPK3PXP", "abcdef", "123456"):
                self.assertNotIn(leaked, out, raw)

    def test_mapping(self):
        out = redact_mapping({"user": "a", "password": "p", "nested": {"api_key": "k", "list": [{"token": "t"}]}})
        self.assertEqual(out["user"], "a")
        self.assertEqual(out["password"], "[REDACTED]")
        self.assertEqual(out["nested"]["api_key"], "[REDACTED]")
        self.assertEqual(out["nested"]["list"][0]["token"], "[REDACTED]")

    def test_json_logger_redacts_and_carries_correlation_id(self):
        buf = io.StringIO()
        logger = configure_logging(logging.INFO, buf)
        tok = correlation_id_var.set("req-123")
        try:
            logging.getLogger("civiclens.test").info("user login password=hunter2 done")
        finally:
            correlation_id_var.reset(tok)
        line = json.loads(buf.getvalue().strip())
        self.assertNotIn("hunter2", line["message"])
        self.assertEqual(line["correlation_id"], "req-123")
        self.assertEqual(line["component"], "civiclens.test")
        logger.handlers.clear()


class ExceptionTests(unittest.TestCase):
    def test_response_shape_has_no_traceback(self):
        body = NotFound("Complaint not found.").to_response("cid-1")
        self.assertEqual(body, {"error": {"code": "not_found", "message": "Complaint not found.", "correlation_id": "cid-1"}})
        self.assertEqual(NotFound.status_code, 404)

    def test_rate_limited_carries_retry_after(self):
        e = RateLimited(retry_after_seconds=30)
        self.assertEqual(e.status_code, 429)
        self.assertEqual(e.to_response()["error"]["details"]["retry_after_seconds"], 30)
        self.assertIsInstance(e, CivicLensError)


if __name__ == "__main__":
    unittest.main()
