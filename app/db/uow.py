"""PostgreSQL unit of work: one SQLAlchemy session/transaction per operation."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.db.repositories.complaints import SqlComplaintRepository, SqlOfficerDirectory
from app.db.repositories.content import (
    SqlConversationRepository,
    SqlDocumentRepository,
    SqlRtiRepository,
)
from app.db.repositories.identity import (
    SqlConsentRepository,
    SqlMfaRepository,
    SqlProfileRepository,
    SqlResetTokenRepository,
    SqlSessionRepository,
    SqlUserRepository,
)
from app.db.repositories.interop import (
    SqlClassificationCorrectionRepository,
    SqlExceptionRepository,
    SqlExternalLinkRepository,
    SqlMasterDataRepository,
)
from app.db.repositories.ops import (
    SqlAnalyticsRepository,
    SqlAnomalyRepository,
    SqlAuditRepository,
    SqlConfigRepository,
    SqlDraftRepository,
    SqlDuplicateReviewRepository,
    SqlEmergencyRepository,
    SqlGovernmentSubmissionRepository,
    SqlInvestigationRepository,
    SqlJobRepository,
    SqlLegalAnalysisRepository,
    SqlNotificationRepository,
    SqlPushDeviceRepository,
    SqlVoiceRepository,
    SqlWorkflowRepository,
)


class SqlUnitOfWork:
    """``with SqlUnitOfWork(factory) as uow: ...; uow.commit()`` - leaving without commit rolls back."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory
        self.session: Session | None = None
        self.extras: dict[str, Any] = {}

    def __enter__(self) -> SqlUnitOfWork:
        s = self._factory()
        self.session = s
        self.complaints, self.officers = SqlComplaintRepository(s), SqlOfficerDirectory(s)
        self.notifications, self.jobs = SqlNotificationRepository(s), SqlJobRepository(s)
        self.profiles, self.consent, self.drafts = SqlProfileRepository(s), SqlConsentRepository(s), SqlDraftRepository(s)
        self.anomalies, self.investigations, self.conversations = SqlAnomalyRepository(s), SqlInvestigationRepository(s), SqlConversationRepository(s)
        self.config, self.rti, self.audit, self.voice = SqlConfigRepository(s), SqlRtiRepository(s), SqlAuditRepository(s), SqlVoiceRepository(s)
        self.users, self.sessions, self.resets, self.mfa = SqlUserRepository(s), SqlSessionRepository(s), SqlResetTokenRepository(s), SqlMfaRepository(s)
        self.documents = SqlDocumentRepository(s)
        self.analytics = SqlAnalyticsRepository(s)
        self.push, self.emergency, self.duplicate_reviews = SqlPushDeviceRepository(s), SqlEmergencyRepository(s), SqlDuplicateReviewRepository(s)
        self.workflow, self.government, self.legal = SqlWorkflowRepository(s), SqlGovernmentSubmissionRepository(s), SqlLegalAnalysisRepository(s)
        self.master_data, self.exceptions = SqlMasterDataRepository(s), SqlExceptionRepository(s)
        self.external_links, self.classification_corrections = SqlExternalLinkRepository(s), SqlClassificationCorrectionRepository(s)
        return self

    def __exit__(self, *exc: object) -> None:
        assert self.session is not None
        try:
            self.session.rollback()  # no-op after commit(); discards everything if commit() was never reached
        finally:
            self.session.close()
            self.session = None

    def commit(self) -> None:
        assert self.session is not None
        self.session.commit()

    def rollback(self) -> None:
        assert self.session is not None
        self.session.rollback()
