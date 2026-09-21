"""Structured JSON logging with correlation ids and secret redaction."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import time
from typing import Any

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)

_SENSITIVE_KEYS = re.compile(
    r"(pass(word)?|secret|token|api[_-]?key|authorization|cookie|otp|totp|credential)", re.I
)
# key=value / key: value / "key": "value" pairs whose key looks sensitive
_PAIR = re.compile(
    r"""(?P<k>["']?[\w-]*(?:pass(?:word)?|secret|token|api[_-]?key|authorization|cookie|otp|credential)[\w-]*["']?)"""
    r"""(?P<sep>\s*[:=]\s*)(?P<v>"[^"]*"|'[^']*'|Bearer\s+\S+|[^\s,;&}]+)""",
    re.I,
)
_OTPAUTH_SECRET = re.compile(r"(otpauth://[^\s]*?secret=)[A-Za-z2-7=]+", re.I)
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.I)
REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    """Mask credential-looking values in free text."""
    text = _OTPAUTH_SECRET.sub(lambda m: m.group(1) + REDACTED, text)
    text = _BEARER.sub(lambda m: m.group(1) + REDACTED, text)
    return _PAIR.sub(lambda m: f"{m.group('k')}{m.group('sep')}{REDACTED}", text)


def redact_mapping(data: Any) -> Any:
    """Recursively mask values whose *key* looks sensitive."""
    if isinstance(data, dict):
        return {
            k: (REDACTED if isinstance(k, str) and _SENSITIVE_KEYS.search(k) else redact_mapping(v))
            for k, v in data.items()
        }
    if isinstance(data, list | tuple):
        return [redact_mapping(v) for v in data]
    if isinstance(data, str):
        return redact(data)
    return data


class RedactingFilter(logging.Filter):
    """Removes secrets from the message and structured extras before emission."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        if hasattr(record, "extra_fields"):
            record.extra_fields = redact_mapping(record.extra_fields)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: int = logging.INFO, stream: Any = None) -> logging.Logger:
    """Install JSON + redaction on the root ``civiclens`` logger (idempotent)."""
    logger = logging.getLogger("civiclens")
    logger.handlers.clear()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
