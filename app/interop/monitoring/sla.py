"""SLA evaluation (Section 19): a connector's `sla_status` (met | breached | unknown) computed from
its real call history (`ConnectorRegistration.total_calls/total_failures/avg_response_ms` -
`app.interop.connector_registry.record_call` updates these on every genuine invocation), against
either that connector's own thresholds or a sensible default. Never simulated - a connector that
has never been called is honestly `unknown`, not `met` by default.
"""

from __future__ import annotations

from app.db.models.interop_platform import ConnectorRegistration

DEFAULT_MAX_AVG_RESPONSE_MS = 1000.0
DEFAULT_MIN_SUCCESS_RATE = 0.95


def evaluate_sla(row: ConnectorRegistration) -> str:
    if row.total_calls == 0:
        return "unknown"
    max_response = row.sla_max_avg_response_ms if row.sla_max_avg_response_ms is not None else DEFAULT_MAX_AVG_RESPONSE_MS
    min_success = row.sla_min_success_rate if row.sla_min_success_rate is not None else DEFAULT_MIN_SUCCESS_RATE
    success_rate = 1.0 - (row.total_failures / row.total_calls)
    response_ok = row.avg_response_ms is None or row.avg_response_ms <= max_response
    return "met" if response_ok and success_rate >= min_success else "breached"
