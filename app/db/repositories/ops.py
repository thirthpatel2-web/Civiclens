from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models.complaints import DuplicateReviewModel
from app.db.models.content import LegalAnalysisModel
from app.db.models.ops import EmergencyContactModel, GovernmentSubmissionModel, PushDeviceModel, WorkflowExecutionModel, WorkflowRuleModel
from app.db.models.ops import AnalyticsSnapshotModel, AnomalyModel, AuditLogModel, DraftModel, InvestigationModel, JobModel, NotificationModel, SchedulerStateModel
from app.db.models.reference import (
    CityModel, CivicServiceModel, DepartmentModel, GovernmentOfficeModel, IntegrationHealthModel, RoutingRuleModel, SlaPolicyModel, WardModel,
)
from app.db.repositories.identity import SqlNotificationPrefs
from app.integrations.base import HealthReport, IntegrationState
from app.services.voice_service import VoiceRecord
from app.services.audit_service import AuditEvent
from app.services.ports import (
    AnomalyRecord, CityRecord, CivicServiceRecord, DepartmentRecord, DraftRecord, EmergencyContactRecord, GovernmentSubmissionRecord, GovOfficeRecord, InvestigationRecord, JobRecord, LegalAnalysisRecord,
    NotificationPreference, NotificationRecord, PushDeviceRecord, WardRecord, WorkflowExecutionRecord, WorkflowRuleRecord,
)
from app.services.routing_service import RoutingRule
from app.services.sla_service import SlaPolicy


class SqlAuditRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def add(self, e: AuditEvent) -> None:
        self.s.add(AuditLogModel(id=str(uuid.uuid4()), action=e.action, actor_id=e.actor_id, resource_type=e.resource_type, resource_id=e.resource_id, audit_metadata=e.metadata, correlation_id=e.correlation_id, occurred_at=e.occurred_at))
        self.s.flush()

    def query(self, *, action_prefix: str | None = None, actor_id: str | None = None, resource_id: str | None = None, since: datetime | None = None, limit: int = 100) -> list[AuditEvent]:
        q = select(AuditLogModel)
        if action_prefix:
            q = q.where(AuditLogModel.action.startswith(action_prefix, autoescape=True))
        if actor_id:
            q = q.where(AuditLogModel.actor_id == actor_id)
        if resource_id:
            q = q.where(AuditLogModel.resource_id == resource_id)
        if since:
            q = q.where(AuditLogModel.occurred_at >= since)
        return [AuditEvent(m.action, m.actor_id, m.resource_type, m.resource_id, m.audit_metadata, m.correlation_id, m.occurred_at) for m in self.s.scalars(q.order_by(AuditLogModel.occurred_at.desc()).limit(limit))]


class SqlNotificationRepository:
    def __init__(self, s: Session) -> None:
        self.s, self._prefs = s, SqlNotificationPrefs(s)

    @staticmethod
    def _rec(m: NotificationModel) -> NotificationRecord:
        return NotificationRecord(m.id, m.user_id, m.kind, m.title, m.body, m.data, m.channel, m.status, m.created_at, m.delivered_at, m.read_at, m.error, m.dedupe_key)

    def add(self, n: NotificationRecord) -> bool:
        # `.rowcount` after ON CONFLICT DO NOTHING is unreliable on this driver (can report 0 even
        # when the row was inserted) - `.returning(...)` reliably tells "inserted" from "deduped" apart.
        stmt = insert(NotificationModel).values(id=n.id, user_id=n.user_id, kind=n.kind, title=n.title, body=n.body, data=n.data, channel=n.channel, status=n.status, created_at=n.created_at,
                                                delivered_at=n.delivered_at, read_at=n.read_at, error=n.error, dedupe_key=n.dedupe_key).on_conflict_do_nothing(constraint="uq_notifications_user_dedupe_key").returning(NotificationModel.id)  # fmt: skip
        return self.s.execute(stmt).first() is not None

    def get(self, notification_id: str) -> NotificationRecord | None:
        m = self.s.get(NotificationModel, notification_id)
        return self._rec(m) if m else None

    def update(self, n: NotificationRecord) -> None:
        m = self.s.get(NotificationModel, n.id)
        if m is not None:
            m.status, m.delivered_at, m.read_at, m.error = n.status, n.delivered_at, n.read_at, n.error
            self.s.flush()

    def list_for_user(self, user_id: str, *, unread_only: bool = False, limit: int = 50) -> list[NotificationRecord]:
        q = select(NotificationModel).where(NotificationModel.user_id == user_id)
        if unread_only:
            q = q.where(NotificationModel.read_at.is_(None))
        return [self._rec(m) for m in self.s.scalars(q.order_by(NotificationModel.created_at.desc()).limit(limit))]

    def unread_count(self, user_id: str) -> int:
        return int(self.s.scalar(select(func.count()).select_from(NotificationModel).where(NotificationModel.user_id == user_id, NotificationModel.read_at.is_(None), NotificationModel.channel == "in_app")) or 0)

    def status_counts(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for channel, status, n in self.s.execute(select(NotificationModel.channel, NotificationModel.status, func.count()).group_by(NotificationModel.channel, NotificationModel.status)):
            out.setdefault(channel, {})[status] = int(n)
        return out

    def get_preferences(self, user_id: str) -> NotificationPreference | None:
        return self._prefs.get(user_id)

    def save_preferences(self, p: NotificationPreference) -> None:
        self._prefs.save(p)


class SqlJobRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: JobModel) -> JobRecord:
        return JobRecord(m.id, m.kind, m.payload, m.idempotency_key, m.status, m.attempts, m.max_attempts, m.run_at, m.created_at, m.updated_at, m.error, m.result, m.worker_id, m.started_at, m.finished_at)

    def add_if_absent(self, j: JobRecord) -> tuple[JobRecord, bool]:
        # `.rowcount` after ON CONFLICT DO NOTHING is unreliable on this driver (can report 0 even
        # when the row was inserted), which silently broke immediate dispatch: the job still got
        # persisted, but `created` came back False so callers never pushed it to the queue backend -
        # it only ever ran once the periodic orphan-sweep found it. `.returning(...)` is dialect-safe.
        stmt = insert(JobModel).values(id=j.id, kind=j.kind, payload=j.payload, idempotency_key=j.idempotency_key, status=j.status, attempts=j.attempts, max_attempts=j.max_attempts,
                                       run_at=j.run_at, created_at=j.created_at, updated_at=j.updated_at).on_conflict_do_nothing(constraint="uq_jobs_idempotency_key").returning(JobModel.id)  # fmt: skip
        created = self.s.execute(stmt).first() is not None
        m = self.s.scalars(select(JobModel).where(JobModel.idempotency_key == j.idempotency_key)).one()
        return self._rec(m), created

    def get(self, job_id: str) -> JobRecord | None:
        m = self.s.get(JobModel, job_id)
        return self._rec(m) if m else None

    def update(self, j: JobRecord) -> None:
        m = self.s.get(JobModel, j.id)
        if m is not None:
            m.status, m.attempts, m.run_at, m.updated_at, m.error, m.result, m.worker_id, m.started_at, m.finished_at = j.status, j.attempts, j.run_at, j.updated_at, j.error, j.result, j.worker_id, j.started_at, j.finished_at
            self.s.flush()

    def list_orphans(self, older_than: datetime, limit: int = 100) -> list[JobRecord]:
        stuck = or_(and_(JobModel.status == "pending", JobModel.updated_at <= older_than), and_(JobModel.status.in_(["queued", "retrying"]), JobModel.run_at <= older_than, JobModel.updated_at <= older_than))
        q = select(JobModel).where(stuck).order_by(JobModel.run_at).limit(limit)
        return [self._rec(m) for m in self.s.scalars(q)]

    def counts_by_status(self) -> dict[str, int]:
        return {st: int(n) for st, n in self.s.execute(select(JobModel.status, func.count()).group_by(JobModel.status))}

    def list_recent(self, limit: int = 50, status: str | None = None) -> list[JobRecord]:
        q = select(JobModel)
        if status:
            q = q.where(JobModel.status == status)
        return [self._rec(m) for m in self.s.scalars(q.order_by(JobModel.created_at.desc()).limit(limit))]


class SqlAnomalyRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: AnomalyModel) -> AnomalyRecord:
        return AnomalyRecord(m.id, m.kind, m.subject, m.severity, m.score, m.explanation, m.detected_at, m.department_code, m.status, m.details, m.dedupe_key)

    def add_if_new(self, a: AnomalyRecord) -> bool:
        exists = self.s.scalar(select(func.count()).select_from(AnomalyModel).where(AnomalyModel.dedupe_key == a.dedupe_key, AnomalyModel.status == "open"))
        if exists:
            return False
        self.s.add(AnomalyModel(id=a.id, kind=a.kind, subject=a.subject, severity=a.severity, score=a.score, explanation=a.explanation, detected_at=a.detected_at, department_code=a.department_code, status=a.status, details=a.details, dedupe_key=a.dedupe_key))
        self.s.flush()
        return True

    def list(self, *, status: str | None = None, department_code: str | None = None, limit: int = 100) -> list[AnomalyRecord]:
        q = select(AnomalyModel)
        if status:
            q = q.where(AnomalyModel.status == status)
        if department_code:
            q = q.where(AnomalyModel.department_code == department_code)
        return [self._rec(m) for m in self.s.scalars(q.order_by(AnomalyModel.detected_at.desc()).limit(limit))]

    def get(self, anomaly_id: str) -> AnomalyRecord | None:
        m = self.s.get(AnomalyModel, anomaly_id)
        return self._rec(m) if m else None

    def update(self, a: AnomalyRecord) -> None:
        m = self.s.get(AnomalyModel, a.id)
        if m is not None:
            m.status, m.details = a.status, a.details
            self.s.flush()


class SqlInvestigationRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: InvestigationModel) -> InvestigationRecord:
        return InvestigationRecord(m.id, m.subject_type, m.subject_id, m.opened_by, m.department_code, m.status, m.created_at, m.closed_at, list(m.notes))

    def add(self, i: InvestigationRecord) -> None:
        self.s.add(InvestigationModel(id=i.id, subject_type=i.subject_type, subject_id=i.subject_id, opened_by=i.opened_by, department_code=i.department_code, status=i.status, created_at=i.created_at, closed_at=i.closed_at, notes=i.notes))
        self.s.flush()

    def get(self, investigation_id: str) -> InvestigationRecord | None:
        m = self.s.get(InvestigationModel, investigation_id)
        return self._rec(m) if m else None

    def update(self, i: InvestigationRecord) -> None:
        m = self.s.get(InvestigationModel, i.id)
        if m is not None:
            m.status, m.closed_at, m.notes = i.status, i.closed_at, list(i.notes)  # reassign: JSONB mutation tracking
            self.s.flush()

    def list(self, *, department_code: str | None = None, limit: int = 100) -> list[InvestigationRecord]:
        q = select(InvestigationModel)
        if department_code:
            q = q.where(InvestigationModel.department_code == department_code)
        return [self._rec(m) for m in self.s.scalars(q.order_by(InvestigationModel.created_at.desc()).limit(limit))]


class SqlDraftRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: DraftModel) -> DraftRecord:
        return DraftRecord(m.id, m.user_id, m.kind, m.client_request_id, m.payload, m.status, m.error, m.result_ref, m.updated_at, m.attempts)

    def get_by_client_request(self, user_id: str, client_request_id: str) -> DraftRecord | None:
        m = self.s.scalars(select(DraftModel).where(DraftModel.user_id == user_id, DraftModel.client_request_id == client_request_id)).first()
        return self._rec(m) if m else None

    def get(self, draft_id: str) -> DraftRecord | None:
        m = self.s.get(DraftModel, draft_id)
        return self._rec(m) if m else None

    def save(self, d: DraftRecord) -> None:
        m = self.s.get(DraftModel, d.id) or DraftModel(id=d.id, user_id=d.user_id, kind=d.kind, client_request_id=d.client_request_id)
        m.payload, m.status, m.error, m.result_ref, m.updated_at, m.attempts = d.payload, d.status, d.error, d.result_ref, d.updated_at, d.attempts
        self.s.add(m)
        self.s.flush()

    def list_for_user(self, user_id: str, kind: str | None = None) -> list[DraftRecord]:
        q = select(DraftModel).where(DraftModel.user_id == user_id)
        if kind:
            q = q.where(DraftModel.kind == kind)
        return [self._rec(m) for m in self.s.scalars(q.order_by(DraftModel.updated_at.desc()))]

    def delete(self, draft_id: str) -> None:
        m = self.s.get(DraftModel, draft_id)
        if m is not None:
            self.s.delete(m)
            self.s.flush()


class SqlConfigRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def departments(self) -> list[DepartmentRecord]:
        return [DepartmentRecord(m.code, m.name, m.active) for m in self.s.scalars(select(DepartmentModel).order_by(DepartmentModel.code))]

    def routing_rules(self) -> list[RoutingRule]:
        return [RoutingRule(m.id, m.priority, m.department_code, m.service_code, frozenset(m.categories), tuple(m.keywords_any), frozenset(m.wards), m.min_severity, m.active) for m in self.s.scalars(select(RoutingRuleModel).order_by(RoutingRuleModel.priority, RoutingRuleModel.id))]

    def sla_policies(self) -> list[SlaPolicy]:
        return [SlaPolicy(m.id, m.priority, m.resolution_hours, m.department_code, m.approaching_fraction, m.escalation_gap_hours, m.max_level) for m in self.s.scalars(select(SlaPolicyModel).order_by(SlaPolicyModel.id))]

    def wards(self) -> list[WardRecord]:
        return [WardRecord(m.code, m.name, m.city_code) for m in self.s.scalars(select(WardModel).order_by(WardModel.code))]

    def cities(self) -> list[CityRecord]:
        return [CityRecord(m.code, m.name, m.state, m.lat, m.lng) for m in self.s.scalars(select(CityModel).order_by(CityModel.code))]

    def services(self) -> list[CivicServiceRecord]:
        return [CivicServiceRecord(m.code, m.name, m.department_code) for m in self.s.scalars(select(CivicServiceModel).order_by(CivicServiceModel.code))]

    def offices(self) -> list[GovOfficeRecord]:
        return [GovOfficeRecord(m.id, m.name, m.department_code, m.lat, m.lng, m.address, m.city_code) for m in self.s.scalars(select(GovernmentOfficeModel).order_by(GovernmentOfficeModel.id))]

    def _merge(self, model: object) -> None:
        self.s.merge(model)
        self.s.flush()

    def save_department(self, d: DepartmentRecord) -> None:
        self._merge(DepartmentModel(code=d.code, name=d.name, active=d.active))

    def save_routing_rule(self, r: RoutingRule) -> None:
        self._merge(RoutingRuleModel(id=r.id, priority=r.priority, department_code=r.department_code, service_code=r.service_code, categories=sorted(r.categories), keywords_any=list(r.keywords_any), wards=sorted(r.wards), min_severity=r.min_severity, active=r.active))

    def delete_routing_rule(self, rule_id: str) -> bool:
        m = self.s.get(RoutingRuleModel, rule_id)
        if m is None:
            return False
        self.s.delete(m)
        self.s.flush()
        return True

    def save_sla_policy(self, p: SlaPolicy) -> None:
        self._merge(SlaPolicyModel(id=p.id, priority=p.priority, department_code=p.department_code, resolution_hours=p.resolution_hours, approaching_fraction=p.approaching_fraction, escalation_gap_hours=p.escalation_gap_hours, max_level=p.max_level))

    def delete_sla_policy(self, policy_id: str) -> bool:
        m = self.s.get(SlaPolicyModel, policy_id)
        if m is None:
            return False
        self.s.delete(m)
        self.s.flush()
        return True

    def save_ward(self, w: WardRecord) -> None:
        self._merge(WardModel(code=w.code, name=w.name, city_code=w.city_code))

    def save_city(self, c: CityRecord) -> None:
        self._merge(CityModel(code=c.code, name=c.name, state=c.state, lat=c.lat, lng=c.lng))

    def save_service(self, v: CivicServiceRecord) -> None:
        self._merge(CivicServiceModel(code=v.code, name=v.name, department_code=v.department_code))

    def save_office(self, o: GovOfficeRecord) -> None:
        self._merge(GovernmentOfficeModel(id=o.id, name=o.name, department_code=o.department_code, lat=o.lat, lng=o.lng, address=o.address, city_code=o.city_code))


class SqlVoiceRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def add(self, v: VoiceRecord) -> None:
        from app.db.models.complaints import VoiceTranscriptModel

        self.s.add(VoiceTranscriptModel(id=v.id, user_id=v.user_id, mime=v.mime, size=v.size, language_requested=v.language_requested, status=v.status, created_at=v.created_at, transcript=v.transcript,
                                        language_detected=v.language_detected, provider=v.provider, error=v.error, detected_by=v.detected_by, confidence=v.confidence, script_ok=v.script_ok, warnings=v.warnings))  # fmt: skip
        self.s.flush()

    def get(self, voice_id: str) -> VoiceRecord | None:
        from app.db.models.complaints import VoiceTranscriptModel

        m = self.s.get(VoiceTranscriptModel, voice_id)
        return VoiceRecord(m.id, m.user_id, m.mime, m.size, m.language_requested, m.status, m.created_at, m.transcript, m.language_detected, m.detected_by, m.provider, m.error, m.script_ok, list(m.warnings), m.confidence) if m else None


class SqlSchedulerState:
    def __init__(self, session_factory) -> None:  # type: ignore[no-untyped-def]
        self._sf = session_factory

    def last_run(self, name: str) -> datetime | None:
        with self._sf() as s:
            m = s.get(SchedulerStateModel, name)
            return m.last_run if m else None

    def set_last_run(self, name: str, at: datetime) -> None:
        with self._sf() as s:
            s.merge(SchedulerStateModel(name=name, last_run=at))
            s.commit()


class SqlIntegrationHealthRepository:
    def __init__(self, session_factory) -> None:  # type: ignore[no-untyped-def]
        self._sf = session_factory

    def save(self, r: HealthReport) -> None:
        from app.db.models.reference import GovernmentPlatformModel

        with self._sf() as s:
            if s.get(GovernmentPlatformModel, r.platform) is None:
                s.add(GovernmentPlatformModel(platform=r.platform, display_name=r.platform, enabled=True))
                s.flush()
            s.add(IntegrationHealthModel(platform=r.platform, state=r.state.value, detail=r.detail[:500], checked_at=r.checked_at, last_success_at=r.last_success_at, last_error=r.last_error, avg_response_ms=r.avg_response_ms, total_calls=r.total_calls, total_failures=r.total_failures))
            s.commit()

    def latest(self, platform: str) -> HealthReport | None:
        with self._sf() as s:
            m = s.scalars(select(IntegrationHealthModel).where(IntegrationHealthModel.platform == platform).order_by(IntegrationHealthModel.checked_at.desc()).limit(1)).first()
            return HealthReport(m.platform, IntegrationState(m.state), m.detail, m.checked_at, m.last_success_at, m.last_error, m.avg_response_ms, m.total_calls, m.total_failures) if m else None


class SqlAnalyticsRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def add_snapshot(self, scope: str, taken_at: datetime, metrics: dict) -> None:  # type: ignore[type-arg]
        self.s.add(AnalyticsSnapshotModel(id=str(uuid.uuid4()), scope=scope, taken_at=taken_at, metrics=metrics))
        self.s.flush()

    def list_snapshots(self, scope: str, since: datetime, limit: int = 500) -> list[tuple[datetime, dict]]:  # type: ignore[type-arg]
        q = select(AnalyticsSnapshotModel).where(AnalyticsSnapshotModel.scope == scope, AnalyticsSnapshotModel.taken_at >= since).order_by(AnalyticsSnapshotModel.taken_at).limit(limit)
        return [(m.taken_at, m.metrics) for m in self.s.scalars(q)]

    def latest_snapshot(self, scope: str) -> dict | None:  # type: ignore[type-arg]
        m = self.s.scalars(select(AnalyticsSnapshotModel).where(AnalyticsSnapshotModel.scope == scope).order_by(AnalyticsSnapshotModel.taken_at.desc()).limit(1)).first()
        return m.metrics if m else None


class SqlPushDeviceRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def upsert(self, d: PushDeviceRecord) -> None:
        stmt = insert(PushDeviceModel).values(id=str(uuid.uuid4()), user_id=d.user_id, token=d.token, platform=d.platform, created_at=d.created_at, last_seen_at=d.last_seen_at)
        self.s.execute(stmt.on_conflict_do_update(constraint="uq_push_devices_token", set_={"user_id": d.user_id, "platform": d.platform, "last_seen_at": d.last_seen_at}))

    def list_for_user(self, user_id: str) -> list[PushDeviceRecord]:
        return [PushDeviceRecord(m.user_id, m.token, m.platform, m.created_at, m.last_seen_at) for m in self.s.scalars(select(PushDeviceModel).where(PushDeviceModel.user_id == user_id))]

    def delete(self, token: str, user_id: str) -> bool:
        m = self.s.scalars(select(PushDeviceModel).where(PushDeviceModel.token == token, PushDeviceModel.user_id == user_id)).first()
        if m is None:
            return False
        self.s.delete(m)
        self.s.flush()
        return True


class SqlEmergencyRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: EmergencyContactModel) -> EmergencyContactRecord:
        return EmergencyContactRecord(m.id, m.number, m.name, m.description, m.scope, m.city_code, m.translations, m.active, m.sort_order)

    def list(self, *, active_only: bool = True, city_code: str | None = None) -> list[EmergencyContactRecord]:
        q = select(EmergencyContactModel)
        if active_only:
            q = q.where(EmergencyContactModel.active.is_(True))
        if city_code:
            q = q.where(or_(EmergencyContactModel.scope == "national", EmergencyContactModel.city_code == city_code))
        return [self._rec(m) for m in self.s.scalars(q.order_by(EmergencyContactModel.sort_order, EmergencyContactModel.id))]

    def save(self, c: EmergencyContactRecord) -> None:
        self.s.merge(EmergencyContactModel(id=c.id, number=c.number, name=c.name, description=c.description, scope=c.scope, city_code=c.city_code, translations=c.translations, active=c.active, sort_order=c.sort_order))
        self.s.flush()

    def delete(self, contact_id: str) -> bool:
        m = self.s.get(EmergencyContactModel, contact_id)
        if m is None:
            return False
        self.s.delete(m)
        self.s.flush()
        return True


class SqlDuplicateReviewRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def add(self, r: Any) -> None:
        self.s.add(DuplicateReviewModel(id=str(uuid.uuid4()), complaint_id=r.complaint_id, other_complaint_id=r.other_complaint_id, decision=r.decision, reviewer_id=r.reviewer_id, note=r.note, at=r.at))
        self.s.flush()

    def list_for_complaint(self, complaint_id: str) -> list[Any]:
        from app.services.duplicate_service import DuplicateReview

        q = select(DuplicateReviewModel).where(DuplicateReviewModel.complaint_id == complaint_id).order_by(DuplicateReviewModel.at)
        return [DuplicateReview(m.complaint_id, m.other_complaint_id, m.decision, m.reviewer_id, m.note, m.at) for m in self.s.scalars(q)]


class SqlWorkflowRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: WorkflowRuleModel) -> WorkflowRuleRecord:
        return WorkflowRuleRecord(m.id, m.name, m.trigger, m.conditions, m.action, m.params, m.priority, m.active, m.created_by, m.created_at)

    def list_rules(self, *, active_only: bool = False) -> list[WorkflowRuleRecord]:
        q = select(WorkflowRuleModel)
        if active_only:
            q = q.where(WorkflowRuleModel.active.is_(True))
        return [self._rec(m) for m in self.s.scalars(q.order_by(WorkflowRuleModel.priority, WorkflowRuleModel.id))]

    def save_rule(self, r: WorkflowRuleRecord) -> None:
        self.s.merge(WorkflowRuleModel(id=r.id, name=r.name, trigger=r.trigger, conditions=r.conditions, action=r.action, params=r.params, priority=r.priority, active=r.active, created_by=r.created_by, created_at=r.created_at))
        self.s.flush()

    def delete_rule(self, rule_id: str) -> bool:
        m = self.s.get(WorkflowRuleModel, rule_id)
        if m is None:
            return False
        self.s.delete(m)
        self.s.flush()
        return True

    def try_record_execution(self, e: WorkflowExecutionRecord) -> bool:
        # `.rowcount` after ON CONFLICT DO NOTHING is unreliable on this driver; `.returning(...)` is dialect-safe.
        stmt = insert(WorkflowExecutionModel).values(id=str(uuid.uuid4()), rule_id=e.rule_id, complaint_id=e.complaint_id, executed_at=e.executed_at, outcome=e.outcome).on_conflict_do_nothing(constraint="uq_workflow_executions_rule_complaint").returning(WorkflowExecutionModel.id)
        return self.s.execute(stmt).first() is not None

    def list_executions(self, *, limit: int = 100) -> list[WorkflowExecutionRecord]:
        q = select(WorkflowExecutionModel).order_by(WorkflowExecutionModel.executed_at.desc()).limit(limit)
        return [WorkflowExecutionRecord(m.rule_id, m.complaint_id, m.executed_at, m.outcome) for m in self.s.scalars(q)]


class SqlGovernmentSubmissionRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: GovernmentSubmissionModel) -> GovernmentSubmissionRecord:
        return GovernmentSubmissionRecord(m.id, m.complaint_id, m.platform, m.state, m.requested_by, m.created_at, m.updated_at, m.external_reference, m.attempts, m.last_error, m.submitted_at)

    def get(self, complaint_id: str, platform: str) -> GovernmentSubmissionRecord | None:
        m = self.s.scalars(select(GovernmentSubmissionModel).where(GovernmentSubmissionModel.complaint_id == complaint_id, GovernmentSubmissionModel.platform == platform)).first()
        return self._rec(m) if m else None

    def save(self, r: GovernmentSubmissionRecord) -> None:
        m = self.s.get(GovernmentSubmissionModel, r.id) or GovernmentSubmissionModel(id=r.id, complaint_id=r.complaint_id, platform=r.platform, requested_by=r.requested_by, created_at=r.created_at)
        m.state, m.external_reference, m.attempts, m.last_error, m.updated_at, m.submitted_at = r.state, r.external_reference, r.attempts, r.last_error, r.updated_at, r.submitted_at
        self.s.add(m)
        self.s.flush()

    def list_for_complaint(self, complaint_id: str) -> list[GovernmentSubmissionRecord]:
        return [self._rec(m) for m in self.s.scalars(select(GovernmentSubmissionModel).where(GovernmentSubmissionModel.complaint_id == complaint_id).order_by(GovernmentSubmissionModel.platform))]

    def counts_by_state(self) -> dict[str, int]:
        return {st: int(n) for st, n in self.s.execute(select(GovernmentSubmissionModel.state, func.count()).group_by(GovernmentSubmissionModel.state))}


class SqlLegalAnalysisRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: LegalAnalysisModel) -> LegalAnalysisRecord:
        return LegalAnalysisRecord(m.id, m.user_id, m.problem, m.status, m.result, m.created_at)

    def add(self, r: LegalAnalysisRecord) -> None:
        self.s.add(LegalAnalysisModel(id=r.id, user_id=r.user_id, problem=r.problem, status=r.status, result=r.result, created_at=r.created_at))
        self.s.flush()

    def get(self, analysis_id: str) -> LegalAnalysisRecord | None:
        m = self.s.get(LegalAnalysisModel, analysis_id)
        return self._rec(m) if m else None

    def list_for_user(self, user_id: str, limit: int = 50) -> list[LegalAnalysisRecord]:
        return [self._rec(m) for m in self.s.scalars(select(LegalAnalysisModel).where(LegalAnalysisModel.user_id == user_id).order_by(LegalAnalysisModel.created_at.desc()).limit(limit))]
