"""Connector Registry: one row per connector (the three mock departments, plus this app's existing
real government adapters from app.integrations), independent of the business logic that calls
them - a connector can be disabled, and its health tracked, without touching the interop gateway.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.interop_platform import ConnectorRegistration

DEFAULT_CONNECTORS: tuple[dict, ...] = (
    {"connector_id": "dept_a", "name": "Maharashtra Revenue Records System (demo)", "department": "Revenue Department", "supported_operations": ["get_entity", "fetch_document", "health_check"]},
    {"connector_id": "dept_b", "name": "Seva Setu Service Application System (demo)", "department": "Skills, Employment, Entrepreneurship & Innovation Dept", "supported_operations": ["get_entity", "submit_application", "query_application", "health_check"]},
    {"connector_id": "dept_c", "name": "Nagrik Grievance Cell (demo)", "department": "General Administration Department", "supported_operations": ["get_entity", "health_check"]},
)


def seed_if_empty(session: Session) -> bool:
    if session.execute(select(ConnectorRegistration).limit(1)).first() is not None:
        return False
    now = datetime.now(UTC)
    for c in DEFAULT_CONNECTORS:
        session.add(ConnectorRegistration(connector_id=c["connector_id"], name=c["name"], department=c["department"], version="1.0", supported_operations=list(c["supported_operations"]), enabled=True, health_state="unknown", created_at=now))
    return True


def list_connectors(session: Session) -> list[ConnectorRegistration]:
    return list(session.execute(select(ConnectorRegistration)).scalars().all())


def get(session: Session, connector_id: str) -> ConnectorRegistration | None:
    return session.get(ConnectorRegistration, connector_id)


def set_enabled(session: Session, connector_id: str, enabled: bool) -> ConnectorRegistration | None:
    row = session.get(ConnectorRegistration, connector_id)
    if row is None:
        return None
    row.enabled = enabled
    session.add(row)
    return row


def record_call(session: Session, connector_id: str, *, success: bool, duration_ms: float) -> None:
    """Every real connector invocation updates its own registry row - health/metrics come from
    what actually happened, not a separate simulated 'monitoring' pass."""
    row = session.get(ConnectorRegistration, connector_id)
    if row is None:
        return
    now = datetime.now(UTC)
    row.total_calls += 1
    row.last_health_check = now
    if success:
        row.last_success_at = now
        row.health_state = "healthy"
    else:
        row.total_failures += 1
        row.last_failure_at = now
        row.health_state = "degraded" if row.total_calls and row.total_failures / row.total_calls < 0.5 else "unavailable"
    prev = row.avg_response_ms
    row.avg_response_ms = duration_ms if prev is None else round((prev * (row.total_calls - 1) + duration_ms) / row.total_calls, 2)
    session.add(row)
