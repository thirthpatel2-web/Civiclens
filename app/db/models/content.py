from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at, jsonb, tstz, uuid_pk


class DocumentModel(Base):
    __tablename__ = "documents"
    id: Mapped[str] = uuid_pk()
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    mime: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_name: Mapped[str] = mapped_column(String(64), nullable=False)
    visibility: Mapped[str] = mapped_column(String(12), nullable=False, default="private")
    department_code: Mapped[str | None] = mapped_column(ForeignKey("departments.code"))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="uploaded")
    error: Mapped[str | None] = mapped_column(String(500))
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    semantic_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    linked_type: Mapped[str | None] = mapped_column(String(20))  # complaint | rti | legal_case
    linked_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = tstz(False)
    updated_at: Mapped[datetime] = tstz(False)
    __table_args__ = (UniqueConstraint("storage_name", name="uq_documents_storage_name"), Index("ix_documents_owner_id", "owner_id"), Index("ix_documents_status", "status"), Index("ix_documents_linked", "linked_type", "linked_id"))


class DocumentChunkModel(Base):
    """A chunk with its pgvector embedding (column added by migration 0002 with the configured dimension)."""

    __tablename__ = "document_chunks"
    chunk_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    document_name: Mapped[str] = mapped_column(String(120), nullable=False)
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    heading: Mapped[str | None] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    entities: Mapped[Any] = jsonb(dict)
    chunk_metadata: Mapped[Any] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    embedding: Mapped[Any] = mapped_column(Vector(), nullable=True)
    __table_args__ = (Index("ix_document_chunks_document_id", "document_id"),)


class LegalPrecedentModel(Base):
    """Rows from the Supreme Court metadata Parquet. cnr is the key; neutral citation is shared by clubbed matters."""

    __tablename__ = "legal_precedents"
    cnr: Mapped[str] = mapped_column(String(40), primary_key=True)
    neutral_citation: Mapped[str] = mapped_column(String(30), nullable=False)
    reporter_citation: Mapped[str | None] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    petitioner: Mapped[str | None] = mapped_column(Text)
    respondent: Mapped[str | None] = mapped_column(Text)
    judges: Mapped[Any] = jsonb(list)
    decision_date: Mapped[date] = mapped_column(Date, nullable=False)
    disposal: Mapped[str | None] = mapped_column(String(300))  # widened by migration 0009; some real disposal_nature values exceed 80 chars
    court: Mapped[str] = mapped_column(String(80), nullable=False)
    languages: Mapped[Any] = jsonb(list)
    source_path: Mapped[str | None] = mapped_column(String(300))
    scraped_at: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (UniqueConstraint("reporter_citation", name="uq_legal_precedents_reporter_citation"), Index("ix_legal_precedents_neutral_citation", "neutral_citation"), Index("ix_legal_precedents_decision_date", "decision_date"))


class LegalJudgmentModel(Base):
    """A full-text-indexed judgment sourced from a public S3 corpus (not the citizen document store -
    no owner, no visibility rules: this is public case law). ``id`` is a deterministic key derived
    from the source path, so re-running ingestion over the same PDF never creates a duplicate.
    ``neutral_citation``/``reporter_citation`` are parsed from the judgment's own text when present,
    for cross-referencing with ``legal_precedents`` (metadata-only rows sourced separately)."""

    __tablename__ = "legal_judgments"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # "sc" | "hc"
    court: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    decision_date: Mapped[date | None] = mapped_column(Date)
    neutral_citation: Mapped[str | None] = mapped_column(String(30))
    reporter_citation: Mapped[str | None] = mapped_column(String(40))
    source_pdf_url: Mapped[str] = mapped_column(String(400), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ingested_at: Mapped[datetime] = tstz(False)
    __table_args__ = (Index("ix_legal_judgments_neutral_citation", "neutral_citation"), Index("ix_legal_judgments_decision_date", "decision_date"))


class LegalJudgmentChunkModel(Base):
    """A chunk of real judgment text with its pgvector embedding. Mirrors ``DocumentChunkModel`` but
    decoupled from the citizen document/ownership model, since this corpus is public case law."""

    __tablename__ = "legal_judgment_chunks"
    chunk_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    judgment_id: Mapped[str] = mapped_column(ForeignKey("legal_judgments.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    heading: Mapped[str | None] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    entities: Mapped[Any] = jsonb(dict)
    embedding: Mapped[Any] = mapped_column(Vector(), nullable=True)
    __table_args__ = (Index("ix_legal_judgment_chunks_judgment_id", "judgment_id"),)


class LegalAnalysisModel(Base):
    __tablename__ = "legal_analyses"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    result: Mapped[Any] = jsonb(dict)
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (Index("ix_legal_analyses_user_id", "user_id"),)


class RtiApplicationModel(Base):
    __tablename__ = "rti_applications"
    id: Mapped[str] = uuid_pk()
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    draft: Mapped[Any] = jsonb(dict)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft")
    reference: Mapped[str | None] = mapped_column(String(32))
    generated_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = tstz(False)
    filed_at: Mapped[datetime | None] = tstz()
    received_at: Mapped[datetime | None] = tstz()
    due_at: Mapped[datetime | None] = tstz()
    deadline_is_estimate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reminders_sent: Mapped[Any] = jsonb(list)
    __table_args__ = (UniqueConstraint("reference", name="uq_rti_applications_reference"), Index("ix_rti_applications_owner_id", "owner_id"), Index("ix_rti_applications_status_due", "status", "due_at"))


class ConversationModel(Base):
    __tablename__ = "ai_conversations"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = tstz(False)
    __table_args__ = (Index("ix_ai_conversations_user_id", "user_id"),)


class ConversationMessageModel(Base):
    __tablename__ = "ai_messages"
    id: Mapped[str] = uuid_pk()
    conversation_id: Mapped[str] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = tstz(False)
    status: Mapped[str | None] = mapped_column(String(30))
    citations: Mapped[Any] = jsonb(list)
    database_facts: Mapped[Any] = mapped_column(JSONB, nullable=True)
    warnings: Mapped[Any] = jsonb(list)
    __table_args__ = (Index("ix_ai_messages_conversation_at", "conversation_id", "at"),)
