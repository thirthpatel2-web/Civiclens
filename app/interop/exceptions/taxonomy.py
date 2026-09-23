"""Central exception taxonomy (Section 16): one consistent set of error codes across every layer
of the interop platform - the connector runtime already used several of these directly
(``CONNECTOR_UNAVAILABLE``, ``AUTHENTICATION_FAILURE``, ``IDENTITY_NOT_FOUND``,
``SCHEMA_VALIDATION_FAILURE``, ``REMOTE_SYSTEM_ERROR`` - see ``app/interop/connectors/base.py``);
this module is the single place that list is declared, plus which codes are inherently retryable.

``classify()`` maps ``InteropGatewayService``'s existing lowercase reason strings (``"document_not_found"``,
``"data_quality_failed"``, ...) onto this taxonomy - additive, not a rename: those strings stay
exactly as they are in every API response and existing test, since real callers (the frontend,
tests written earlier this session) depend on them. The canonical code is what gets logged to the
central exception record (``InteropException``), not what the gateway returns to its caller.
"""

from __future__ import annotations

EXCEPTION_TYPES = frozenset(
    {
        "AUTHENTICATION_FAILURE", "AUTHORIZATION_FAILURE",
        "CONSENT_REQUIRED", "CONSENT_DENIED", "CONSENT_EXPIRED", "CONSENT_REVOKED",
        "IDENTITY_NOT_FOUND", "IDENTITY_AMBIGUOUS", "IDENTITY_CONFLICT",
        "SCHEMA_VALIDATION_FAILURE", "DATA_QUALITY_FAILURE",
        "CONNECTOR_TIMEOUT", "CONNECTOR_UNAVAILABLE", "RATE_LIMITED", "REMOTE_SYSTEM_ERROR",
        "DUPLICATE_REQUEST", "EVENT_PUBLISH_FAILURE", "EVENT_DELIVERY_FAILURE",
        "WORKFLOW_TIMEOUT", "WORKFLOW_FAILURE",
    }
)  # fmt: skip

# Transient-by-nature codes: safe to retry without a human deciding first. Everything else
# (a data problem, a policy refusal, an identity question) needs a person to look at it - retrying
# a DATA_QUALITY_FAILURE automatically would just get the same rejection again.
RETRYABLE_TYPES = frozenset({"CONNECTOR_TIMEOUT", "CONNECTOR_UNAVAILABLE", "RATE_LIMITED", "REMOTE_SYSTEM_ERROR", "EVENT_PUBLISH_FAILURE", "EVENT_DELIVERY_FAILURE", "WORKFLOW_TIMEOUT"})

_GATEWAY_REASON_TO_CODE: dict[str, str] = {
    "document_not_found": "REMOTE_SYSTEM_ERROR",
    "data_quality_failed": "DATA_QUALITY_FAILURE",
    "data_field_not_consented": "AUTHORIZATION_FAILURE",
    "identity_ambiguous": "IDENTITY_AMBIGUOUS",
    "identity_conflict": "IDENTITY_CONFLICT",
    "source_record_not_found": "IDENTITY_NOT_FOUND",
    "consent_required": "CONSENT_REQUIRED",
}


def classify(gateway_reason: str) -> str:
    return _GATEWAY_REASON_TO_CODE.get(gateway_reason, "REMOTE_SYSTEM_ERROR")


def is_retryable(code: str) -> bool:
    return code in RETRYABLE_TYPES
