"""Unit of work: one transaction spanning several repositories.

``SqlUnitOfWork`` (app/db/uow.py) is the production implementation. Services call
``with self._uow() as uow: ... uow.commit()``; leaving the block without ``commit`` rolls back.
Side effects that must not happen for a rolled-back change (queue push, websocket delivery)
are performed by the caller *after* ``commit``; jobs are written inside the transaction
(transactional outbox) so a crash between commit and push loses nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from app.services.audit_service import AuditRepository
from app.services.auth_service import ResetTokenRepository, SessionRepository, UserRepository
from app.services.mfa_service import MfaRepository
from app.services.ports import (
    AnomalyRepository,
    ComplaintRepository,
    ConfigRepository,
    ConsentRepository,
    ConversationRepository,
    DraftRepository,
    InvestigationRepository,
    JobRepository,
    NotificationRepository,
    OfficerDirectory,
    ProfileRepository,
)
from app.services.rti_service import RtiRepository


class UnitOfWork(Protocol):
    complaints: ComplaintRepository
    officers: OfficerDirectory
    notifications: NotificationRepository
    jobs: JobRepository
    profiles: ProfileRepository
    consent: ConsentRepository
    drafts: DraftRepository
    anomalies: AnomalyRepository
    investigations: InvestigationRepository
    conversations: ConversationRepository
    config: ConfigRepository
    rti: RtiRepository
    audit: AuditRepository
    users: UserRepository
    sessions: SessionRepository
    resets: ResetTokenRepository
    mfa: MfaRepository
    voice: Any
    analytics: Any
    push: Any
    emergency: Any
    duplicate_reviews: Any
    workflow: Any
    government: Any
    legal: Any
    master_data: Any
    exceptions: Any
    external_links: Any
    classification_corrections: Any
    extras: dict[str, Any]

    def __enter__(self) -> UnitOfWork: ...
    def __exit__(self, *exc: object) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


UowFactory = Callable[[], UnitOfWork]
