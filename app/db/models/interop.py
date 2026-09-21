"""Interoperability-adjacent persistence: Golden Record links, the integration exception queue,
manual cross-portal tracking, and classification-correction capture for the transparent learning
loop. See app/interop/ for the pure normalization layer these support."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, jsonb, tstz, uuid_pk


class CitizenExternalIdModel(Base):
    """Golden Record: external government IDs linked to one CivicLens profile.

    Only a salted hash of the normalized ID value is ever stored - never the raw number - and the
    unique constraint on (id_type, id_hash) is the actual entity-resolution conflict guard: the
    database itself refuses to let the same real-world ID attach to two different profiles.
    """

    __tablename__ = "citizen_external_ids"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    id_type: Mapped[str] = mapped_column(String(30), nullable=False)
    id_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    last4: Mapped[str | None] = mapped_column(String(8))
    linked_at: Mapped[datetime] = tstz(False)
    __table_args__ = (UniqueConstraint("id_type", "id_hash", name="uq_citizen_external_ids_type_hash"), Index("ix_citizen_external_ids_user", "user_id"))


class IntegrationExceptionModel(Base):
    """A record that failed Common Data Model validation, queued for review instead of dropped."""

    __tablename__ = "integration_exceptions"
    id: Mapped[str] = uuid_pk()
    source_system: Mapped[str] = mapped_column(String(60), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    payload: Mapped[Any] = jsonb(dict)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="open")
    detected_at: Mapped[datetime] = tstz(False)
    resolved_at: Mapped[datetime | None] = tstz()
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    resolution_note: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (Index("ix_integration_exceptions_status_detected", "status", "detected_at"),)


class ExternalServiceLinkModel(Base):
    """Honest manual tracking for a portal (CPGRAMS, a state portal, ...) that requires the
    citizen's own login and exposes no public API to sync from - kept alongside CivicLens's own
    live-tracked filings instead of pretending to sync something that structurally cannot sync."""

    __tablename__ = "external_service_links"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(60), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status_note: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = tstz(False)
    updated_at: Mapped[datetime] = tstz(False)
    __table_args__ = (Index("ix_external_service_links_user", "user_id"),)


class ClassificationCorrectionModel(Base):
    """Every time staff corrects a misclassified complaint, the correction is captured here -
    transparent and inspectable (app/services/classification_service.py cites these records when
    it falls back to a learned suggestion), never a black-box weight update."""

    __tablename__ = "classification_corrections"
    id: Mapped[str] = uuid_pk()
    complaint_id: Mapped[str] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    text_snapshot: Mapped[str] = mapped_column(String(2000), nullable=False)
    previous_category: Mapped[str] = mapped_column(String(30), nullable=False)
    corrected_category: Mapped[str] = mapped_column(String(30), nullable=False)
    corrected_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    corrected_at: Mapped[datetime] = tstz(False)
    __table_args__ = (Index("ix_classification_corrections_category", "corrected_category"),)
