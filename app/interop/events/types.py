"""Interop event schema (Section 10 - event-driven pub/sub). Deliberately independent from
``app.realtime.events.DomainEvent`` - that class is tightly coupled to the complaint/notification
WebSocket-delivery domain (a fixed ``EVENT_TYPES`` frozenset, ``owner_id``/``department_code``/
``complaint_id`` fields); forcing interop events through it would mean either widening a
domain-specific class to mean two things, or bolting on fields it was never designed for. This is
its own event, its own bus (``app.interop.events.bus``), and its own subscribers
(``app.interop.events.subscribers``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "v1"

INTEROP_EVENT_TYPES = frozenset(
    {
        "ApplicationCreated", "ApplicationUpdated", "ApplicationApproved", "ApplicationRejected",
        "DocumentRequested", "DocumentVerified", "DocumentTransferred",
        "ConsentRequested", "ConsentGranted", "ConsentDenied", "ConsentRevoked",
        "IdentityResolved", "IdentityReviewRequired",
        "WorkflowStarted", "WorkflowStepCompleted",
        "ConnectorFailure", "ConnectorRecovered",
        "SLAWarning", "SLABreached",
        "ExchangeCompleted", "ExchangeFailed",
    }
)  # fmt: skip


@dataclass(frozen=True)
class InteropEvent:
    event_type: str
    source_system: str
    correlation_id: str
    destination: str | None = None
    entity_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = SCHEMA_VERSION
    retry_count: int = 0

    def __post_init__(self) -> None:
        if self.event_type not in INTEROP_EVENT_TYPES:
            raise ValueError(f"{self.event_type!r} is not a recognized interop event type")


def event_to_dict(event: InteropEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id, "event_type": event.event_type, "source_system": event.source_system,
        "destination": event.destination, "entity_id": event.entity_id, "correlation_id": event.correlation_id,
        "occurred_at": event.occurred_at.isoformat(), "schema_version": event.schema_version,
        "payload": event.payload, "retry_count": event.retry_count,
    }


def event_from_dict(data: dict[str, Any]) -> InteropEvent:
    return InteropEvent(
        event_id=data["event_id"], event_type=data["event_type"], source_system=data["source_system"],
        destination=data.get("destination"), entity_id=data.get("entity_id"), correlation_id=data["correlation_id"],
        occurred_at=datetime.fromisoformat(data["occurred_at"]), schema_version=data.get("schema_version", SCHEMA_VERSION),
        payload=data.get("payload") or {}, retry_count=data.get("retry_count", 0),
    )
