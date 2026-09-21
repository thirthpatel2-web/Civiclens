from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, jsonb, tstz, uuid_pk


class NotificationModel(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)
    data: Mapped[Any] = jsonb(dict)
    channel: Mapped[str] = mapped_column(String(12), nullable=False, default="in_app")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    created_at: Mapped[datetime] = tstz(False)
    delivered_at: Mapped[datetime | None] = tstz()
    read_at: Mapped[datetime | None] = tstz()
    error: Mapped[str | None] = mapped_column(String(500))
    dedupe_key: Mapped[str | None] = mapped_column(String(160))
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe_key"), Index("ix_notifications_user_created", "user_id", "created_at"), Index("ix_notifications_user_unread", "user_id", "read_at"))


class JobModel(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[Any] = jsonb(dict)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    run_at: Mapped[datetime] = tstz(False)
    created_at: Mapped[datetime] = tstz(False)
    updated_at: Mapped[datetime] = tstz(False)
    error: Mapped[str | None] = mapped_column(String(500))
    result: Mapped[Any] = mapped_column(JSONB, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime | None] = tstz()
    finished_at: Mapped[datetime | None] = tstz()
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"), Index("ix_jobs_status_updated", "status", "updated_at"))


class AuditLogModel(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = uuid_pk()
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36))  # no FK: audit must outlive user rows
    resource_type: Mapped[str | None] = mapped_column(String(40))
    resource_id: Mapped[str | None] = mapped_column(String(80))
    audit_metadata: Mapped[Any] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = tstz(False)
    __table_args__ = (Index("ix_audit_logs_occurred_at", "occurred_at"), Index("ix_audit_logs_actor_id", "actor_id"), Index("ix_audit_logs_resource", "resource_type", "resource_id"), Index("ix_audit_logs_action", "action"))


class AnomalyModel(Base):
    __tablename__ = "anomalies"
    id: Mapped[str] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = tstz(False)
    department_code: Mapped[str | None] = mapped_column(ForeignKey("departments.code"))
    status: Mapped[str] = mapped_column(String(14), nullable=False, default="open")
    details: Mapped[Any] = jsonb(dict)
    dedupe_key: Mapped[str] = mapped_column(String(300), nullable=False)
    __table_args__ = (Index("ix_anomalies_status_detected", "status", "detected_at"), Index("ix_anomalies_dedupe_key", "dedupe_key"))


class InvestigationModel(Base):
    __tablename__ = "investigations"
    id: Mapped[str] = uuid_pk()
    subject_type: Mapped[str] = mapped_column(String(12), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False)
    opened_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    department_code: Mapped[str | None] = mapped_column(ForeignKey("departments.code"))
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="open")
    created_at: Mapped[datetime] = tstz(False)
    closed_at: Mapped[datetime | None] = tstz()
    notes: Mapped[Any] = jsonb(list)
    __table_args__ = (Index("ix_investigations_department_status", "department_code", "status"), Index("ix_investigations_subject", "subject_type", "subject_id"))


class DraftModel(Base):
    __tablename__ = "drafts"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[Any] = jsonb(dict)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft")
    error: Mapped[str | None] = mapped_column(String(500))
    result_ref: Mapped[str | None] = mapped_column(String(40))
    updated_at: Mapped[datetime] = tstz(False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (UniqueConstraint("user_id", "client_request_id", name="uq_drafts_user_client_request"),)


class AnalyticsSnapshotModel(Base):
    __tablename__ = "analytics_snapshots"
    id: Mapped[str] = uuid_pk()
    scope: Mapped[str] = mapped_column(String(60), nullable=False)  # "all" | "department:<code>"
    taken_at: Mapped[datetime] = tstz(False)
    metrics: Mapped[Any] = jsonb(dict)
    __table_args__ = (Index("ix_analytics_snapshots_scope_taken", "scope", "taken_at"),)


class SchedulerStateModel(Base):
    __tablename__ = "scheduler_state"
    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    last_run: Mapped[datetime] = tstz(False)




class WorkflowRuleModel(Base):
    """Configurable automation: trigger + conditions -> action (distinct from routing rules and SLA policies)."""

    __tablename__ = "workflow_rules"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    conditions: Mapped[Any] = jsonb(dict)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    params: Mapped[Any] = jsonb(dict)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = tstz(False)
    __table_args__ = (Index("ix_workflow_rules_trigger_active", "trigger", "active"),)


class WorkflowExecutionModel(Base):
    __tablename__ = "workflow_executions"
    id: Mapped[str] = uuid_pk()
    rule_id: Mapped[str] = mapped_column(ForeignKey("workflow_rules.id", ondelete="CASCADE"), nullable=False)
    complaint_id: Mapped[str] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    executed_at: Mapped[datetime] = tstz(False)
    outcome: Mapped[str] = mapped_column(String(200), nullable=False)
    __table_args__ = (UniqueConstraint("rule_id", "complaint_id", name="uq_workflow_executions_rule_complaint"),)


class EmergencyContactModel(Base):
    __tablename__ = "emergency_contacts"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    scope: Mapped[str] = mapped_column(String(10), nullable=False, default="national")
    city_code: Mapped[str | None] = mapped_column(ForeignKey("cities.code"))
    translations: Mapped[Any] = jsonb(dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    __table_args__ = (Index("ix_emergency_contacts_scope_city", "scope", "city_code"),)


class GovernmentSubmissionModel(Base):
    """State machine per (complaint, platform). No row ever says ``submitted`` unless an adapter call really succeeded."""

    __tablename__ = "government_submissions"
    id: Mapped[str] = uuid_pk()
    complaint_id: Mapped[str] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(120))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = tstz(False)
    updated_at: Mapped[datetime] = tstz(False)
    submitted_at: Mapped[datetime | None] = tstz()
    __table_args__ = (UniqueConstraint("complaint_id", "platform", name="uq_government_submissions_complaint_platform"), Index("ix_government_submissions_state", "state"))


class PushDeviceModel(Base):
    __tablename__ = "push_devices"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[str] = mapped_column(String(200), nullable=False)
    platform: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = tstz(False)
    last_seen_at: Mapped[datetime] = tstz(False)
    __table_args__ = (UniqueConstraint("token", name="uq_push_devices_token"), Index("ix_push_devices_user_id", "user_id"))
