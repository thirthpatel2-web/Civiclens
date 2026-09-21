"""Optional error tracking (Sentry). Degrades honestly: without SENTRY_DSN, this is a no-op -
no crash, no silent pretend-success, exactly like every other optional integration in this app
(no Redis -> jobs stay pending; no Ollama -> no model; no SMTP -> e-mail not_configured)."""

from __future__ import annotations

import os


def init_error_tracking() -> bool:
    """Initialise Sentry if SENTRY_DSN is set. Returns whether it actually initialised, so the
    caller can log the real state rather than assume."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("APP_ENV", "development"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0") or 0),
        send_default_pii=False,  # citizen complaint/RTI/legal text must never leave via error reports
    )
    return True


def error_tracking_status() -> str:
    """For /monitoring/system - reports the real, current state, not just whether init was tried."""
    try:
        import sentry_sdk
    except ImportError:
        return "not_configured"
    return "configured" if sentry_sdk.is_initialized() else "not_configured"
