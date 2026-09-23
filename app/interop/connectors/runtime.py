"""Connector runtime: resolves a connector_id to a live GovernmentConnector instance, checking the
registry's enabled flag first. This is the one place that knows which concrete class backs which
connector_id - the gateway asks the runtime, never imports a connector class directly.

    Interop Gateway -> Connector Registry (enabled? healthy?) -> Connector Runtime -> GovernmentConnector

Registering a new government system means adding one line to ``_CONNECTOR_CLASSES`` (and a row in
``app.interop.connector_registry.DEFAULT_CONNECTORS``) - orchestration logic in
``app.services.interop_gateway_service`` never changes.
"""

from __future__ import annotations

import time
from dataclasses import replace

from sqlalchemy.orm import Session

from app.interop import connector_registry
from app.interop.connectors.base import ConnectorResult, GovernmentConnector
from app.interop.connectors.mock_dept_a import DeptAConnector
from app.interop.connectors.mock_dept_b import DeptBConnector
from app.interop.connectors.mock_dept_c import DeptCConnector

_CONNECTOR_CLASSES: dict[str, type[GovernmentConnector]] = {
    "dept_a": DeptAConnector,
    "dept_b": DeptBConnector,
    "dept_c": DeptCConnector,
}


class ConnectorUnavailable(Exception):
    """Raised when a connector_id is unknown or disabled - the caller decides how to surface this
    (the gateway turns it into a structured failure result, never lets it propagate as a 500)."""

    def __init__(self, connector_id: str, reason: str) -> None:
        super().__init__(f"{connector_id}: {reason}")
        self.connector_id = connector_id
        self.reason = reason


def resolve(session: Session, connector_id: str) -> GovernmentConnector:
    cls = _CONNECTOR_CLASSES.get(connector_id)
    if cls is None:
        raise ConnectorUnavailable(connector_id, "no connector class registered for this id")
    row = connector_registry.get(session, connector_id)
    if row is None:
        raise ConnectorUnavailable(connector_id, "not present in the connector registry - seed_if_empty may not have run")
    if not row.enabled:
        raise ConnectorUnavailable(connector_id, "disabled in the connector registry")
    return cls(session)


def call(session: Session, connector_id: str, operation: str, /, *args, **kwargs) -> ConnectorResult:
    """Resolve + invoke one operation, timing it and recording the call against the connector
    registry's live stats (the same accounting ``connector_registry.record_call`` already did for
    direct mock-system calls) - so switching the gateway onto the runtime doesn't lose the
    call-count/health data the connector registry screen shows."""
    t0 = time.monotonic()
    try:
        connector = resolve(session, connector_id)
    except ConnectorUnavailable as exc:
        return ConnectorResult(ok=False, error_code="CONNECTOR_UNAVAILABLE", error_message=str(exc))
    try:
        result: ConnectorResult = getattr(connector, operation)(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - a connector must never crash the gateway
        result = connector.handle_error(exc)
    duration_ms = round((time.monotonic() - t0) * 1000, 2)
    connector_registry.record_call(session, connector_id, success=result.ok, duration_ms=duration_ms)
    return replace(result, meta={**result.meta, "duration_ms": duration_ms})
