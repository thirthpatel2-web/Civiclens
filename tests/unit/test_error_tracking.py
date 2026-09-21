import os
import unittest
from unittest.mock import patch

from app.core.error_tracking import error_tracking_status, init_error_tracking


class ErrorTrackingTests(unittest.TestCase):
    def test_no_dsn_is_a_no_op(self):
        with patch.dict(os.environ, {"SENTRY_DSN": ""}, clear=False):
            with patch("sentry_sdk.init") as mock_init:
                self.assertFalse(init_error_tracking())
                mock_init.assert_not_called()

    def test_dsn_configured_initialises_without_sending_pii(self):
        env = {"SENTRY_DSN": "https://key@sentry.example/1", "APP_ENV": "production", "SENTRY_TRACES_SAMPLE_RATE": "0.1"}
        with patch.dict(os.environ, env, clear=False):
            with patch("sentry_sdk.init") as mock_init:
                self.assertTrue(init_error_tracking())
                mock_init.assert_called_once()
                kwargs = mock_init.call_args.kwargs
                self.assertEqual(kwargs["dsn"], env["SENTRY_DSN"])
                self.assertEqual(kwargs["environment"], "production")
                self.assertEqual(kwargs["traces_sample_rate"], 0.1)
                self.assertFalse(kwargs["send_default_pii"])  # citizen data must never leave via error reports

    def test_status_reflects_real_sdk_state_not_just_whether_init_was_attempted(self):
        with patch("sentry_sdk.is_initialized", return_value=False):
            self.assertEqual(error_tracking_status(), "not_configured")
        with patch("sentry_sdk.is_initialized", return_value=True):
            self.assertEqual(error_tracking_status(), "configured")


if __name__ == "__main__":
    unittest.main()
