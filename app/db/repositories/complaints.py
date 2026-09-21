from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.authorization import Role
from app.db.models.complaints import (
    ComplaintEventModel,
    ComplaintEvidenceModel,
    ComplaintModel,
    FeedbackModel,
)
from app.db.models.identity import UserModel
from app.services.complaint_status import FINISHED, ComplaintStatus
from app.services.ports import (
    ComplaintEvent,
    ComplaintRecord,
    ComplaintRow,
    EvidenceRecord,
    FeedbackRecord,
    OfficerLoad,
)

_FINISHED = [str(s) for s in FINISHED]
_COLS = ("reference citizen_id title description language category subcategory severity priority complaint_type department_code service_code ward lat lng address city "
         "assigned_officer_id created_at updated_at sla_due_at escalation_level escalated_at resolved_at client_request_id ai_status classification routing duplicates priority_factors detected_language translated_text translated_language translation_provider input_method voice_id").split()  # fmt: skip


def _rec(m: ComplaintModel) -> ComplaintRecord:
    return ComplaintRecord(id=m.id, status=ComplaintStatus(m.status), **{c: getattr(m, c) for c in _COLS})


def _apply(m: ComplaintModel, c: ComplaintRecord) -> None:
    for col in _COLS:
        setattr(m, col, getattr(c, col))
    m.status, m.has_duplicates = str(c.status), bool(c.duplicates)


class SqlComplaintRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def add(self, c: ComplaintRecord) -> None:
        m = ComplaintModel(id=c.id)
        _apply(m, c)
        self.s.add(m)
        self.s.flush()

    def get(self, complaint_id: str) -> ComplaintRecord | None:
        m = self.s.get(ComplaintModel, complaint_id)
        return _rec(m) if m else None

    def get_by_reference(self, reference: str) -> ComplaintRecord | None:
        m = self.s.scalars(select(ComplaintModel).where(ComplaintModel.reference == reference)).first()
        return _rec(m) if m else None

    def get_by_client_request(self, citizen_id: str, client_request_id: str) -> ComplaintRecord | None:
        m = self.s.scalars(select(ComplaintModel).where(ComplaintModel.citizen_id == citizen_id, ComplaintModel.client_request_id == client_request_id)).first()
        return _rec(m) if m else None

    def reference_exists(self, reference: str) -> bool:
        return self.s.scalar(select(func.count()).select_from(ComplaintModel).where(ComplaintModel.reference == reference)) > 0

    def update(self, c: ComplaintRecord) -> None:
        m = self.s.get(ComplaintModel, c.id)
        if m is None:
            raise LookupError("complaint not found")
        _apply(m, c)
        self.s.flush()

    def list_for_citizen(self, citizen_id: str, *, limit: int = 50, offset: int = 0) -> list[ComplaintRecord]:
        q = select(ComplaintModel).where(ComplaintModel.citizen_id == citizen_id).order_by(ComplaintModel.created_at.desc()).limit(limit).offset(offset)
        return [_rec(m) for m in self.s.scalars(q)]

    def list_for_department(self, department_code: str, *, statuses: list[ComplaintStatus] | None = None, officer_id: str | None = None, limit: int = 50, offset: int = 0) -> list[ComplaintRecord]:
        q = select(ComplaintModel).where(ComplaintModel.department_code == department_code)  # isolation is part of the SQL, not a post-filter
        if statuses:
            q = q.where(ComplaintModel.status.in_([str(s) for s in statuses]))
        if officer_id:
            q = q.where(ComplaintModel.assigned_officer_id == officer_id)
        return [_rec(m) for m in self.s.scalars(q.order_by(ComplaintModel.created_at.desc()).limit(limit).offset(offset))]

    def list_unrouted(self, *, limit: int = 100) -> list[ComplaintRecord]:
        q = select(ComplaintModel).where(ComplaintModel.department_code.is_(None), ComplaintModel.status == "submitted").order_by(ComplaintModel.created_at).limit(limit)
        return [_rec(m) for m in self.s.scalars(q)]

    def list_open(self) -> list[ComplaintRecord]:
        return [_rec(m) for m in self.s.scalars(select(ComplaintModel).where(ComplaintModel.status.notin_(_FINISHED)))]

    def list_by_status(self, statuses: list[ComplaintStatus], *, limit: int = 1000) -> list[ComplaintRecord]:
        q = select(ComplaintModel).where(ComplaintModel.status.in_([str(x) for x in statuses])).order_by(ComplaintModel.updated_at).limit(limit)
        return [_rec(m) for m in self.s.scalars(q)]

    def duplicate_candidates(self, category: str, since: datetime, *, limit: int = 200) -> list[ComplaintRecord]:
        q = select(ComplaintModel).where(ComplaintModel.category == category, ComplaintModel.created_at >= since).order_by(ComplaintModel.created_at.desc()).limit(limit)
        return [_rec(m) for m in self.s.scalars(q)]

    def rows(self, *, citizen_id: str | None = None, department_code: str | None = None, since: datetime | None = None) -> list[ComplaintRow]:
        q = select(ComplaintModel.id, ComplaintModel.reference, ComplaintModel.status, ComplaintModel.category, ComplaintModel.severity, ComplaintModel.priority, ComplaintModel.department_code, ComplaintModel.ward,
                   ComplaintModel.complaint_type, ComplaintModel.created_at, ComplaintModel.resolved_at, ComplaintModel.sla_due_at, ComplaintModel.escalation_level, ComplaintModel.lat, ComplaintModel.lng,
                   ComplaintModel.assigned_officer_id, ComplaintModel.citizen_id, ComplaintModel.routing["source"].astext, ComplaintModel.has_duplicates)  # fmt: skip
        if citizen_id:
            q = q.where(ComplaintModel.citizen_id == citizen_id)
        if department_code:
            q = q.where(ComplaintModel.department_code == department_code)
        if since:
            q = q.where(ComplaintModel.created_at >= since)
        return [ComplaintRow(r[0], r[1], ComplaintStatus(r[2]), *r[3:17], r[17], bool(r[18])) for r in self.s.execute(q)]  # type: ignore[arg-type]

    # ---- events / evidence / feedback
    def add_event(self, e: ComplaintEvent) -> None:
        self.s.add(ComplaintEventModel(id=e.id, complaint_id=e.complaint_id, kind=e.kind, from_status=str(e.from_status) if e.from_status else None, to_status=str(e.to_status) if e.to_status else None,
                                       actor_id=e.actor_id, actor_label=e.actor_label, remarks=e.remarks, details=e.details, at=e.at, internal=e.internal))  # fmt: skip
        self.s.flush()

    def list_events(self, complaint_id: str) -> list[ComplaintEvent]:
        q = select(ComplaintEventModel).where(ComplaintEventModel.complaint_id == complaint_id).order_by(ComplaintEventModel.at)
        return [ComplaintEvent(m.id, m.complaint_id, m.kind, ComplaintStatus(m.from_status) if m.from_status else None, ComplaintStatus(m.to_status) if m.to_status else None, m.actor_id, m.actor_label, m.remarks, m.details, m.at, m.internal) for m in self.s.scalars(q)]

    @staticmethod
    def _ev(m: ComplaintEvidenceModel) -> EvidenceRecord:
        return EvidenceRecord(m.id, m.complaint_id, m.uploader_id, m.name, m.mime, m.size, m.sha256, m.storage_name, m.created_at, m.analysis_status, m.analysis_provider, m.analysis_result, m.analysis_error)

    def add_evidence(self, e: EvidenceRecord) -> None:
        self.s.add(ComplaintEvidenceModel(id=e.id, complaint_id=e.complaint_id, uploader_id=e.uploader_id, name=e.name, mime=e.mime, size=e.size, sha256=e.sha256, storage_name=e.storage_name,
                                          analysis_status=e.analysis_status, analysis_provider=e.analysis_provider, analysis_result=e.analysis_result, analysis_error=e.analysis_error))  # fmt: skip
        self.s.flush()

    def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        m = self.s.get(ComplaintEvidenceModel, evidence_id)
        return self._ev(m) if m else None

    def update_evidence(self, e: EvidenceRecord) -> None:
        m = self.s.get(ComplaintEvidenceModel, e.id)
        if m is not None:
            m.complaint_id, m.analysis_status, m.analysis_provider, m.analysis_result, m.analysis_error = e.complaint_id, e.analysis_status, e.analysis_provider, e.analysis_result, e.analysis_error
            self.s.flush()

    def list_evidence(self, complaint_id: str) -> list[EvidenceRecord]:
        return [self._ev(m) for m in self.s.scalars(select(ComplaintEvidenceModel).where(ComplaintEvidenceModel.complaint_id == complaint_id).order_by(ComplaintEvidenceModel.created_at))]

    def add_feedback(self, f: FeedbackRecord) -> None:
        self.s.add(FeedbackModel(complaint_id=f.complaint_id, citizen_id=f.citizen_id, rating=f.rating, comment=f.comment, created_at=f.created_at))
        self.s.flush()

    def get_feedback(self, complaint_id: str) -> FeedbackRecord | None:
        m = self.s.get(FeedbackModel, complaint_id)
        return FeedbackRecord(m.complaint_id, m.citizen_id, m.rating, m.comment, m.created_at) if m else None

    def officer_loads(self, department_code: str, officer_ids: list[str]) -> list[OfficerLoad]:
        q = (select(ComplaintModel.assigned_officer_id, func.count()).where(ComplaintModel.assigned_officer_id.in_(officer_ids), ComplaintModel.status.notin_(_FINISHED)).group_by(ComplaintModel.assigned_officer_id))
        counts = {oid: n for oid, n in self.s.execute(q)}
        return [OfficerLoad(i, int(counts.get(i, 0))) for i in officer_ids]


class SqlOfficerDirectory:
    def __init__(self, s: Session) -> None:
        self.s = s

    def officer_ids_for_department(self, department_code: str) -> list[str]:
        q = select(UserModel.id).where(UserModel.role == str(Role.OFFICER), UserModel.department_code == department_code, UserModel.is_active.is_(True)).order_by(UserModel.id)
        return list(self.s.scalars(q))

    def user_label(self, user_id: str) -> str | None:
        return self.s.scalar(select(UserModel.full_name).where(UserModel.id == user_id))

    def admin_ids(self) -> list[str]:
        q = select(UserModel.id).where(UserModel.role.in_([str(Role.ADMIN), str(Role.SUPER_ADMIN)]), UserModel.is_active.is_(True)).order_by(UserModel.id)
        return list(self.s.scalars(q))
