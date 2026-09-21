from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models.interop import CitizenExternalIdModel, ClassificationCorrectionModel, ExternalServiceLinkModel, IntegrationExceptionModel
from app.services.ports import ClassificationCorrectionRecord, ExternalIdRecord, ExternalServiceLinkRecord, IntegrationExceptionRecord


class SqlMasterDataRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def add(self, r: ExternalIdRecord) -> bool:
        # `.rowcount` after ON CONFLICT DO NOTHING is unreliable on this driver (it can report 0
        # even though the row was inserted) - `.returning(...)` is the dialect-safe way to tell
        # "inserted" from "conflicted" apart.
        stmt = (
            insert(CitizenExternalIdModel)
            .values(id=r.id, user_id=r.user_id, id_type=r.id_type, id_hash=r.id_hash, last4=r.last4, linked_at=r.linked_at)
            .on_conflict_do_nothing(constraint="uq_citizen_external_ids_type_hash")
            .returning(CitizenExternalIdModel.id)
        )
        return self.s.execute(stmt).first() is not None

    def list_for_user(self, user_id: str) -> list[ExternalIdRecord]:
        q = select(CitizenExternalIdModel).where(CitizenExternalIdModel.user_id == user_id).order_by(CitizenExternalIdModel.linked_at.desc())
        return [ExternalIdRecord(m.id, m.user_id, m.id_type, m.id_hash, m.last4, m.linked_at) for m in self.s.scalars(q)]

    def remove(self, record_id: str, user_id: str) -> bool:
        m = self.s.get(CitizenExternalIdModel, record_id)
        if m is None or m.user_id != user_id:
            return False
        self.s.delete(m)
        self.s.flush()
        return True


class SqlExceptionRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: IntegrationExceptionModel) -> IntegrationExceptionRecord:
        return IntegrationExceptionRecord(m.id, m.source_system, m.reason, m.payload, m.detected_at, m.status, m.resolved_at, m.resolved_by, m.resolution_note)

    def add(self, r: IntegrationExceptionRecord) -> None:
        self.s.add(IntegrationExceptionModel(id=r.id, source_system=r.source_system, reason=r.reason, payload=r.payload, status=r.status, detected_at=r.detected_at))
        self.s.flush()

    def get(self, exception_id: str) -> IntegrationExceptionRecord | None:
        m = self.s.get(IntegrationExceptionModel, exception_id)
        return self._rec(m) if m else None

    def update(self, r: IntegrationExceptionRecord) -> None:
        m = self.s.get(IntegrationExceptionModel, r.id)
        if m is not None:
            m.status, m.resolved_at, m.resolved_by, m.resolution_note = r.status, r.resolved_at, r.resolved_by, r.resolution_note
            self.s.flush()

    def list(self, *, status: str | None = None, limit: int = 100) -> list[IntegrationExceptionRecord]:
        q = select(IntegrationExceptionModel)
        if status:
            q = q.where(IntegrationExceptionModel.status == status)
        return [self._rec(m) for m in self.s.scalars(q.order_by(IntegrationExceptionModel.detected_at.desc()).limit(limit))]

    def counts_by_status(self) -> dict[str, int]:
        return {st: int(n) for st, n in self.s.execute(select(IntegrationExceptionModel.status, func.count()).group_by(IntegrationExceptionModel.status))}


class SqlExternalLinkRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: ExternalServiceLinkModel) -> ExternalServiceLinkRecord:
        return ExternalServiceLinkRecord(m.id, m.user_id, m.platform, m.external_reference, m.title, m.created_at, m.updated_at, m.status_note)

    def add(self, r: ExternalServiceLinkRecord) -> None:
        self.s.add(ExternalServiceLinkModel(id=r.id, user_id=r.user_id, platform=r.platform, external_reference=r.external_reference, title=r.title, status_note=r.status_note, created_at=r.created_at, updated_at=r.updated_at))
        self.s.flush()

    def list_for_user(self, user_id: str) -> list[ExternalServiceLinkRecord]:
        q = select(ExternalServiceLinkModel).where(ExternalServiceLinkModel.user_id == user_id).order_by(ExternalServiceLinkModel.created_at.desc())
        return [self._rec(m) for m in self.s.scalars(q)]

    def update(self, r: ExternalServiceLinkRecord) -> None:
        m = self.s.get(ExternalServiceLinkModel, r.id)
        if m is not None and m.user_id == r.user_id:
            m.status_note, m.updated_at = r.status_note, r.updated_at
            self.s.flush()

    def remove(self, record_id: str, user_id: str) -> bool:
        m = self.s.get(ExternalServiceLinkModel, record_id)
        if m is None or m.user_id != user_id:
            return False
        self.s.delete(m)
        self.s.flush()
        return True


class SqlClassificationCorrectionRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: ClassificationCorrectionModel) -> ClassificationCorrectionRecord:
        return ClassificationCorrectionRecord(m.id, m.complaint_id, m.text_snapshot, m.previous_category, m.corrected_category, m.corrected_by, m.corrected_at)

    def add(self, r: ClassificationCorrectionRecord) -> None:
        self.s.add(ClassificationCorrectionModel(id=r.id, complaint_id=r.complaint_id, text_snapshot=r.text_snapshot, previous_category=r.previous_category, corrected_category=r.corrected_category, corrected_by=r.corrected_by, corrected_at=r.corrected_at))
        self.s.flush()

    def list_recent(self, limit: int = 100) -> list[ClassificationCorrectionRecord]:
        q = select(ClassificationCorrectionModel).order_by(ClassificationCorrectionModel.corrected_at.desc()).limit(limit)
        return [self._rec(m) for m in self.s.scalars(q)]

    def find_similar(self, text: str, limit: int = 5) -> list[ClassificationCorrectionRecord]:
        """Deterministic lexical-overlap lookup over recent corrections - the same similarity
        metric used for duplicate-complaint detection, reused here for consistency rather than
        inventing a second one. Never a black-box learned weight."""
        from app.services.duplicate_service import lexical_similarity

        candidates = self.list_recent(limit=500)
        scored = sorted(((lexical_similarity(text, c.text_snapshot), c) for c in candidates), key=lambda t: -t[0])
        return [c for score, c in scored[:limit] if score >= 0.2]


def hash_external_id(id_type: str, raw_value: str, *, salt: str) -> str:
    """Salted SHA-256 of a normalized external ID value - the raw value is never persisted."""
    import hashlib

    normalized = "".join(ch for ch in raw_value.strip().upper() if ch.isalnum())
    return hashlib.sha256(f"{salt}:{id_type}:{normalized}".encode()).hexdigest()
