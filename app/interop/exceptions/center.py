"""The Exception Center (Section 16-18): logs a structured ``InteropException`` for every
interop-platform failure, with real retry (Section 17) and dead-letter (Section 18) state -
``resolution_state`` moves ``open -> retrying -> resolved`` or ``open -> retrying -> dead`` once
``max_retries`` is exhausted, never silently. Retry here is *manual* (an operator or a caller
explicitly invokes ``retry()``) - real exponential-backoff automatic retry is the job queue's
existing job (``app.workers.queue``), which this section doesn't duplicate; the taxonomy, history
and dead-letter state below are what's new.

Plain functions taking a session (the same pattern ``app.interop.mock_systems``/
``connector_registry``/``federation.idp`` already use) so ``log_exception`` can be called from
inside a caller's own open transaction - a broken exception log must never itself break the
operation it's describing, and it must commit or roll back atomically with everything else that
transaction did.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.interop_platform import InteropException
from app.interop.exceptions.taxonomy import EXCEPTION_TYPES, is_retryable

_Clock = Callable[[], datetime]
_default_clock: _Clock = lambda: datetime.now(UTC)  # noqa: E731


def log_exception(
    session: Session, *, error_code: str, message: str, source_system: str | None = None, target_system: str | None = None,
    correlation_id: str | None = None, retryable: bool | None = None, max_retries: int = 3, clock: _Clock = _default_clock,
) -> InteropException:
    if error_code not in EXCEPTION_TYPES:
        raise ValueError(f"{error_code!r} is not a recognized exception type")
    resolved_retryable = is_retryable(error_code) if retryable is None else retryable
    record = InteropException(
        exception_id=str(uuid.uuid4()), error_code=error_code, message=message[:500], source_system=source_system, target_system=target_system,
        correlation_id=correlation_id, retryable=resolved_retryable, retry_count=0, max_retries=max_retries,
        next_action="retry automatically" if resolved_retryable else "manual review required", resolution_state="open", created_at=clock(),
    )
    session.add(record)
    return record


def list_exceptions(session: Session, *, resolution_state: str | None = None, error_code: str | None = None, correlation_id: str | None = None, limit: int = 100) -> list[InteropException]:
    q = select(InteropException).order_by(InteropException.created_at.desc()).limit(limit)
    if resolution_state:
        q = q.where(InteropException.resolution_state == resolution_state)
    if error_code:
        q = q.where(InteropException.error_code == error_code)
    if correlation_id:
        q = q.where(InteropException.correlation_id == correlation_id)
    return list(session.execute(q).scalars().all())


def _safe_get(session: Session, exception_id: str) -> InteropException | None:
    """``exception_id`` is a native Postgres ``uuid`` column - handing a non-UUID-shaped string to
    ``session.get()`` makes psycopg raise a SQL-level cast error instead of SQLAlchemy returning
    ``None`` for "not found". Acting on an unknown id must be a safe no-op, so validate the shape
    first rather than letting that DB error propagate (and poison the session's transaction)."""
    try:
        uuid.UUID(exception_id)
    except (ValueError, AttributeError, TypeError):
        return None
    return session.get(InteropException, exception_id)


def retry(session: Session, exception_id: str, *, clock: _Clock = _default_clock) -> InteropException | None:
    """One manual retry attempt. Once ``retry_count`` reaches ``max_retries`` the record moves to
    ``dead`` - the dead-letter state (Section 18) - and stops accepting further retries; the
    caller re-attempting the underlying operation is a separate concern from this bookkeeping."""
    record = _safe_get(session, exception_id)
    if record is None or not record.retryable or record.resolution_state == "dead":
        return None
    record.retry_count += 1
    if record.retry_count >= record.max_retries:
        record.resolution_state, record.next_action = "dead", "retries exhausted - manual review required"
    else:
        record.resolution_state, record.next_action = "retrying", f"retry {record.retry_count}/{record.max_retries}"
    session.add(record)
    return record


def mark_resolved(session: Session, exception_id: str, *, clock: _Clock = _default_clock) -> InteropException | None:
    record = _safe_get(session, exception_id)
    if record is None:
        return None
    record.resolution_state, record.next_action, record.resolved_at = "resolved", None, clock()
    session.add(record)
    return record


def mark_dead(session: Session, exception_id: str, *, reason: str | None = None, clock: _Clock = _default_clock) -> InteropException | None:
    """An operator giving up on this one directly - distinct from retries being exhausted
    automatically inside ``retry()``, but lands in the same dead-letter state either way."""
    record = _safe_get(session, exception_id)
    if record is None:
        return None
    record.resolution_state, record.next_action = "dead", (reason or "marked dead by an operator")
    session.add(record)
    return record
