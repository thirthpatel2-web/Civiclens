"""Application exception hierarchy.

Every error that may reach a client is a :class:`CivicLensError`. The
``to_response`` payload never carries a stack trace or internal detail; the
correlation id lets support staff find the full diagnostic in the logs.
"""

from __future__ import annotations

from typing import Any


class CivicLensError(Exception):
    """Base class: carries an HTTP status, a stable machine code and a safe message."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str = "An unexpected error occurred.", *, details: Any = None):
        super().__init__(message)
        self.message = message
        self.details = details

    def to_response(self, correlation_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"error": {"code": self.code, "message": self.message}}
        if self.details is not None:
            body["error"]["details"] = self.details
        if correlation_id:
            body["error"]["correlation_id"] = correlation_id
        return body


class ValidationFailed(CivicLensError):
    status_code = 422
    code = "validation_failed"


class AuthenticationFailed(CivicLensError):
    status_code = 401
    code = "authentication_failed"


class MfaRequired(CivicLensError):
    status_code = 401
    code = "mfa_required"


class PermissionDenied(CivicLensError):
    status_code = 403
    code = "permission_denied"


class NotFound(CivicLensError):
    status_code = 404
    code = "not_found"


class Conflict(CivicLensError):
    status_code = 409
    code = "conflict"


class RateLimited(CivicLensError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str = "Too many attempts.", *, retry_after_seconds: int = 0):
        super().__init__(message, details={"retry_after_seconds": retry_after_seconds})
        self.retry_after_seconds = retry_after_seconds


class DependencyUnavailable(CivicLensError):
    """A configured external dependency (Ollama, Redis, an adapter…) is down."""

    status_code = 503
    code = "dependency_unavailable"


class NotConfigured(CivicLensError):
    """An optional capability has no configuration; never mask this as success."""

    status_code = 501
    code = "not_configured"
