from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at, jsonb, tstz, uuid_pk


class ComplaintModel(Base):
    __tablename__ = "complaints"
    id: Mapped[str] = uuid_pk()
    reference: Mapped[str] = mapped_column(String(32), nullable=False)
    citizen_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    complaint_type: Mapped[str] = mapped_column(String(20), nullable=False, default="municipal")
    department_code: Mapped[str | None] = mapped_column(ForeignKey("departments.code"))
    service_code: Mapped[str | None] = mapped_column(String(60))
    ward: Mapped[str | None] = mapped_column(String(40))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    address: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100))
    assigned_officer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = tstz(False)
    updated_at: Mapped[datetime] = tstz(False)
    sla_due_at: Mapped[datetime | None] = tstz()
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    escalated_at: Mapped[datetime | None] = tstz()
    resolved_at: Mapped[datetime | None] = tstz()
    client_request_id: Mapped[str | None] = mapped_column(String(64))
    ai_status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_needed")
    classification: Mapped[Any] = jsonb(dict)
    routing: Mapped[Any] = jsonb(dict)
    duplicates: Mapped[Any] = jsonb(list)
    priority_factors: Mapped[Any] = jsonb(list)
    has_duplicates: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Multilingual: ``description``/``language`` are the citizen's ORIGINAL text and language and are never rewritten.
    detected_language: Mapped[str | None] = mapped_column(String(5))
    translated_text: Mapped[str | None] = mapped_column(Text)  # derived, separate from the original
    translated_language: Mapped[str | None] = mapped_column(String(5))
    translation_provider: Mapped[str | None] = mapped_column(String(40))
    input_method: Mapped[str] = mapped_column(String(10), nullable=False, default="typed", server_default="typed")
    voice_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("reference", name="uq_complaints_reference"),
        UniqueConstraint("citizen_id", "client_request_id", name="uq_complaints_citizen_client_request"),
        Index("ix_complaints_citizen_created", "citizen_id", "created_at"),
        Index("ix_complaints_department_status", "department_code", "status"),
        Index("ix_complaints_assigned_officer_status", "assigned_officer_id", "status"),
        Index("ix_complaints_category_created", "category", "created_at"),
        Index("ix_complaints_ward", "ward"),
        Index("ix_complaints_sla_due_at", "sla_due_at"),
    )


class ComplaintEventModel(Base):
    __tablename__ = "complaint_events"
    id: Mapped[str] = uuid_pk()
    complaint_id: Mapped[str] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    actor_label: Mapped[str | None] = mapped_column(String(120))
    remarks: Mapped[str | None] = mapped_column(Text)
    details: Mapped[Any] = jsonb(dict)
    at: Mapped[datetime] = tstz(False)
    internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (Index("ix_complaint_events_complaint_at", "complaint_id", "at"),)


class ComplaintEvidenceModel(Base):
    __tablename__ = "complaint_evidence"
    id: Mapped[str] = uuid_pk()
    complaint_id: Mapped[str | None] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"))
    uploader_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    mime: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = created_at()
    analysis_status: Mapped[str] = mapped_column(String(40), nullable=False)
    analysis_provider: Mapped[str | None] = mapped_column(String(40))
    analysis_result: Mapped[Any] = mapped_column(JSONB, nullable=True)
    analysis_error: Mapped[str | None] = mapped_column(String(300))
    __table_args__ = (Index("ix_complaint_evidence_complaint_id", "complaint_id"), UniqueConstraint("storage_name", name="uq_complaint_evidence_storage_name"))


class FeedbackModel(Base):
    __tablename__ = "feedback"
    complaint_id: Mapped[str] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"), primary_key=True)
    citizen_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = tstz(False)


class DuplicateReviewModel(Base):
    __tablename__ = "duplicate_reviews"
    id: Mapped[str] = uuid_pk()
    complaint_id: Mapped[str] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    other_complaint_id: Mapped[str] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = tstz(False)
    __table_args__ = (Index("ix_duplicate_reviews_complaint_id", "complaint_id"),)


class VoiceTranscriptModel(Base):
    __tablename__ = "voice_transcripts"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    mime: Mapped[str] = mapped_column(String(40), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    language_requested: Mapped[str] = mapped_column(String(5), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = tstz(False)
    transcript: Mapped[str | None] = mapped_column(Text)
    language_detected: Mapped[str | None] = mapped_column(String(5))
    provider: Mapped[str | None] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(String(500))
    detected_by: Mapped[str | None] = mapped_column(String(10))
    confidence: Mapped[float | None] = mapped_column(Float)
    script_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    warnings: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    __table_args__ = (Index("ix_voice_transcripts_user_id", "user_id"),)
