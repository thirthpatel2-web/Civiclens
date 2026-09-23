"""Alerting (Section 20): a real `ConnectorAlert` row is created only on a genuine state
TRANSITION - a connector's SLA just breached, or it just became unavailable - never on every
single failed call after that, which would flood the alert log with duplicates for the same
underlying problem. Plain functions taking a session, the same pattern
`app.interop.exceptions.center`/`connector_registry` already use, so alert creation commits
atomically with whatever call caused it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.interop_platform import ConnectorAlert, ConnectorRegistration

_Clock = Callable[[], datetime]
_default_clock: _Clock = lambda: datetime.now(UTC)  # noqa: E731


def raise_alert_if_needed(session: Session, row: ConnectorRegistration, *, previous_sla_status: str, previous_health_state: str, clock: _Clock = _default_clock) -> list[ConnectorAlert]:
    """The two conditions are independent, not mutually exclusive - a connector's SLA can breach
    on the exact same call that also tips its health_state to unavailable, and both deserve their
    own alert; an earlier version of this used `elif` and silently dropped the second one."""
    created: list[ConnectorAlert] = []
    if row.sla_status == "breached" and previous_sla_status != "breached":
        created.append(ConnectorAlert(
            alert_id=str(uuid.uuid4()), connector_id=row.connector_id, alert_type="SLA_BREACHED", severity="warning",
            message=f"{row.connector_id}: SLA breached (avg {row.avg_response_ms}ms over {row.total_calls} calls, {row.total_failures} failures)",
            created_at=clock(), acknowledged=False,
        ))
    if row.health_state == "unavailable" and previous_health_state != "unavailable":
        created.append(ConnectorAlert(
            alert_id=str(uuid.uuid4()), connector_id=row.connector_id, alert_type="CONNECTOR_UNAVAILABLE", severity="critical",
            message=f"{row.connector_id}: connector unavailable ({row.total_failures}/{row.total_calls} calls have failed)",
            created_at=clock(), acknowledged=False,
        ))
    for alert in created:
        session.add(alert)
    return created


def list_alerts(session: Session, *, connector_id: str | None = None, acknowledged: bool | None = None, limit: int = 100) -> list[ConnectorAlert]:
    q = select(ConnectorAlert).order_by(ConnectorAlert.created_at.desc()).limit(limit)
    if connector_id:
        q = q.where(ConnectorAlert.connector_id == connector_id)
    if acknowledged is not None:
        q = q.where(ConnectorAlert.acknowledged == acknowledged)
    return list(session.execute(q).scalars().all())


def acknowledge(session: Session, alert_id: str, *, actor_id: str | None, clock: _Clock = _default_clock) -> ConnectorAlert | None:
    try:
        uuid.UUID(alert_id)
    except (ValueError, AttributeError, TypeError):
        return None
    record = session.get(ConnectorAlert, alert_id)
    if record is None:
        return None
    record.acknowledged, record.acknowledged_at, record.acknowledged_by = True, clock(), actor_id
    session.add(record)
    return record
