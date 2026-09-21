"""Audit trail: who did what to which resource, with secrets stripped."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from app.core.logging import correlation_id_var, redact_mapping


@dataclass(frozen=True)
class AuditEvent:
    action: str
    actor_id: str | None
    resource_type: str | None = None
    resource_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AuditRepository(Protocol):
    def add(self, event: AuditEvent) -> None: ...
    def query(self, *, action_prefix: str | None = None, actor_id: str | None = None, resource_id: str | None = None, since: datetime | None = None, limit: int = 100) -> list[AuditEvent]: ...


class AuditService:
    """Writes sanitised audit events; a failure to audit is surfaced, never swallowed."""

    def __init__(self, repo: AuditRepository, clock: Callable[[], datetime] | None = None):
        self._repo = repo
        self._clock = clock or (lambda: datetime.now(UTC))

    def record(
        self,
        action: str,
        *,
        actor_id: str | None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            action=action,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=redact_mapping(metadata or {}),
            correlation_id=correlation_id_var.get(),
            occurred_at=self._clock(),
        )
        self._repo.add(event)
        return event
