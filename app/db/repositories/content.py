from __future__ import annotations

import dataclasses
from datetime import datetime

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.db.models.content import ConversationMessageModel, ConversationModel, DocumentChunkModel, DocumentModel, LegalJudgmentChunkModel, LegalJudgmentModel, LegalPrecedentModel, RtiApplicationModel
from app.legal.judgment_ingest import JudgmentRecord
from app.legal.precedents import PrecedentRecord
from app.rag.models import Chunk
from app.services.document_service import DocumentRecord, DocumentStatus
from app.services.ports import ConversationMessage, ConversationRecord
from app.services.rti_service import RtiApplication, RtiDraft, RtiStatus


def _draft_to_json(d: RtiDraft) -> dict:  # type: ignore[type-arg]
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in dataclasses.asdict(d).items()}


def _draft_from_json(j: dict) -> RtiDraft:  # type: ignore[type-arg]
    return RtiDraft(**{**j, "questions": tuple(j.get("questions", ())), "attachments": tuple(j.get("attachments", ()))})


class SqlRtiRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: RtiApplicationModel) -> RtiApplication:
        return RtiApplication(m.id, m.owner_id, _draft_from_json(m.draft), RtiStatus(m.status), m.reference, m.generated_text, m.created_at, m.filed_at, m.received_at, m.due_at, m.deadline_is_estimate, tuple(m.reminders_sent))

    @staticmethod
    def _apply(m: RtiApplicationModel, a: RtiApplication) -> None:
        m.owner_id, m.draft, m.status, m.reference, m.generated_text = a.owner_id, _draft_to_json(a.draft), a.status.value, a.reference, a.generated_text
        m.created_at, m.filed_at, m.received_at, m.due_at, m.deadline_is_estimate, m.reminders_sent = a.created_at, a.filed_at, a.received_at, a.due_at, a.deadline_is_estimate, list(a.reminders_sent)

    def add(self, a: RtiApplication) -> None:
        m = RtiApplicationModel(id=a.id)
        self._apply(m, a)
        self.s.add(m)
        self.s.flush()

    def get(self, app_id: str) -> RtiApplication | None:
        m = self.s.get(RtiApplicationModel, app_id)
        return self._rec(m) if m else None

    def update(self, a: RtiApplication) -> None:
        m = self.s.get(RtiApplicationModel, a.id)
        if m is not None:
            self._apply(m, a)
            self.s.flush()

    def list_for_owner(self, owner_id: str) -> list[RtiApplication]:
        return [self._rec(m) for m in self.s.scalars(select(RtiApplicationModel).where(RtiApplicationModel.owner_id == owner_id).order_by(RtiApplicationModel.created_at.desc()))]

    def list_filed(self) -> list[RtiApplication]:
        return [self._rec(m) for m in self.s.scalars(select(RtiApplicationModel).where(RtiApplicationModel.status == "filed"))]


class SqlDocumentRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: DocumentModel) -> DocumentRecord:
        return DocumentRecord(m.id, m.owner_id, m.name, m.mime, m.size, m.sha256, m.storage_name, m.visibility, m.department_code, DocumentStatus(m.status), m.error, m.chunk_count, m.semantic_indexed, m.attempts, m.created_at, m.updated_at)

    def add(self, d: DocumentRecord) -> None:
        self.s.add(DocumentModel(id=d.id, owner_id=d.owner_id, name=d.name, mime=d.mime, size=d.size, sha256=d.sha256, storage_name=d.storage_name, visibility=d.visibility, department_code=d.department_id,
                                 status=d.status.value, error=d.error, chunk_count=d.chunk_count, semantic_indexed=d.semantic_indexed, attempts=d.attempts, created_at=d.created_at, updated_at=d.updated_at))  # fmt: skip
        self.s.flush()

    def get(self, doc_id: str) -> DocumentRecord | None:
        m = self.s.get(DocumentModel, doc_id)
        return self._rec(m) if m else None

    def update(self, d: DocumentRecord) -> None:
        m = self.s.get(DocumentModel, d.id)
        if m is not None:
            m.status, m.error, m.chunk_count, m.semantic_indexed, m.attempts, m.updated_at = d.status.value, d.error, d.chunk_count, d.semantic_indexed, d.attempts, d.updated_at
            self.s.flush()

    def list_for_owner(self, owner_id: str, limit: int = 50) -> list[DocumentRecord]:
        return [self._rec(m) for m in self.s.scalars(select(DocumentModel).where(DocumentModel.owner_id == owner_id).order_by(DocumentModel.created_at.desc()).limit(limit))]

    def link(self, doc_id: str, linked_type: str, linked_id: str) -> None:
        m = self.s.get(DocumentModel, doc_id)
        if m is not None:
            m.linked_type, m.linked_id = linked_type, linked_id
            self.s.flush()


class SqlChunkStore:
    """Persists chunks + embeddings and serves them to ``IndexSynchronizer`` / pgvector search."""

    def __init__(self, s: Session) -> None:
        self.s = s

    def replace_document(self, document_id: str, chunks: list[Chunk], vectors: list[list[float]] | None) -> None:
        self.s.execute(delete(DocumentChunkModel).where(DocumentChunkModel.document_id == document_id))
        for i, c in enumerate(chunks):
            self.s.add(DocumentChunkModel(chunk_id=c.chunk_id, document_id=document_id, chunk_index=c.chunk_index, document_name=c.document_name, document_type=c.document_type, page=c.page, heading=c.heading,
                                          text=c.text, entities=c.entities, chunk_metadata=c.metadata, embedding=vectors[i] if vectors else None))  # fmt: skip
        self.s.flush()

    def ready_documents(self) -> dict[str, datetime]:
        return {i: t for i, t in self.s.execute(select(DocumentModel.id, DocumentModel.updated_at).where(DocumentModel.status == "ready"))}

    def load_chunks(self, document_id: str) -> tuple[list[Chunk], list[list[float]] | None]:
        rows = list(self.s.scalars(select(DocumentChunkModel).where(DocumentChunkModel.document_id == document_id).order_by(DocumentChunkModel.chunk_index)))
        chunks = [Chunk(m.chunk_id, m.document_id, m.document_name, m.text, m.document_type, m.page, m.heading, m.chunk_index, m.entities, m.chunk_metadata) for m in rows]
        vecs = [list(map(float, m.embedding)) for m in rows if m.embedding is not None]
        return chunks, (vecs if len(vecs) == len(rows) and rows else None)


class PgVectorSearcher:
    """Cosine search inside PostgreSQL (``<=>``) satisfying the same interface as ``InMemoryVectorIndex``.

    Visibility is enforced after the ANN step on an over-fetched candidate set (``oversample`` x top_k),
    so results are exact for the caller's permissions unless more than that many *invisible* chunks
    outrank the visible ones; raise ``oversample`` for corpora with many private documents.
    """

    def __init__(self, session_factory, chunk_loader, oversample: int = 8) -> None:  # type: ignore[no-untyped-def]
        self._sf, self._load, self._over = session_factory, chunk_loader, oversample

    def __len__(self) -> int:
        with self._sf() as s:
            return int(s.scalar(select(func.count()).select_from(DocumentChunkModel).where(DocumentChunkModel.embedding.is_not(None))) or 0)

    def search(self, query_vector, top_k: int = 20, *, min_similarity: float = -1.0, visible=None):  # type: ignore[no-untyped-def]
        from app.rag.vector_search import VectorHit

        with self._sf() as s:
            rows = s.execute(
                text("SELECT chunk_id, 1 - (embedding <=> CAST(:q AS vector)) AS sim FROM document_chunks WHERE embedding IS NOT NULL ORDER BY embedding <=> CAST(:q AS vector) LIMIT :n"),
                {"q": "[" + ",".join(f"{float(x):.8f}" for x in query_vector) + "]", "n": top_k * self._over},
            ).all()
            hits = []
            for chunk_id, sim in rows:
                if sim < min_similarity:
                    continue
                if visible is not None:
                    m = s.get(DocumentChunkModel, chunk_id)
                    chunk = Chunk(m.chunk_id, m.document_id, m.document_name, m.text, m.document_type, m.page, m.heading, m.chunk_index, m.entities, m.chunk_metadata)
                    if not visible(chunk):
                        continue
                hits.append(VectorHit(chunk_id, float(sim)))
                if len(hits) >= top_k:
                    break
        return hits


class SqlLegalRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def upsert_all(self, records: list[PrecedentRecord]) -> int:
        for r in records:
            self.s.merge(LegalPrecedentModel(cnr=r.cnr, neutral_citation=r.neutral_citation, reporter_citation=r.reporter_citation, title=r.title, petitioner=r.petitioner, respondent=r.respondent, judges=list(r.judges),
                                             decision_date=r.decision_date, disposal=r.disposal, court=r.court, languages=list(r.languages), source_path=r.source_path, scraped_at=r.scraped_at))  # fmt: skip
        self.s.flush()
        return len(records)

    def load_all(self) -> list[PrecedentRecord]:
        return [PrecedentRecord(m.cnr, m.neutral_citation, m.reporter_citation, m.title, m.petitioner, m.respondent, tuple(m.judges), m.decision_date, m.disposal, m.court, tuple(m.languages), m.source_path, m.scraped_at)
                for m in self.s.scalars(select(LegalPrecedentModel).order_by(LegalPrecedentModel.cnr))]  # fmt: skip


class SqlLegalJudgmentRepository:
    """Public case-law full-text corpus: judgment metadata + chunks with embeddings. Ingested offline
    (``scripts/ingest_legal_fulltext.py``), served read-only at runtime via ``search``."""

    def __init__(self, s: Session) -> None:
        self.s = s

    def add_judgment(self, r: JudgmentRecord, ingested_at: datetime) -> bool:
        """Insert-or-skip by id (idempotent re-ingestion). Returns True if this call inserted a new row."""
        existing = self.s.get(LegalJudgmentModel, r.id)
        if existing is not None:
            return False
        self.s.add(LegalJudgmentModel(id=r.id, source=r.source, court=r.court, title=r.title, decision_date=r.decision_date, neutral_citation=r.neutral_citation,
                                       reporter_citation=r.reporter_citation, source_pdf_url=r.source_pdf_url, page_count=r.page_count, char_count=r.char_count,
                                       chunk_count=0, ingested_at=ingested_at))  # fmt: skip
        self.s.flush()
        return True

    def replace_chunks(self, judgment_id: str, chunks: list[Chunk], vectors: list[list[float]] | None) -> None:
        self.s.execute(delete(LegalJudgmentChunkModel).where(LegalJudgmentChunkModel.judgment_id == judgment_id))
        for i, c in enumerate(chunks):
            self.s.add(LegalJudgmentChunkModel(chunk_id=c.chunk_id, judgment_id=judgment_id, chunk_index=c.chunk_index, page=c.page, heading=c.heading,
                                                text=c.text, entities=c.entities, embedding=vectors[i] if vectors else None))  # fmt: skip
        m = self.s.get(LegalJudgmentModel, judgment_id)
        if m is not None:
            m.chunk_count = len(chunks)
        self.s.flush()

    def stats(self) -> dict[str, int]:
        judgments = int(self.s.scalar(select(func.count()).select_from(LegalJudgmentModel)) or 0)
        chunks = int(self.s.scalar(select(func.count()).select_from(LegalJudgmentChunkModel)) or 0)
        embedded = int(self.s.scalar(select(func.count()).select_from(LegalJudgmentChunkModel).where(LegalJudgmentChunkModel.embedding.is_not(None))) or 0)
        return {"judgments": judgments, "chunks": chunks, "embedded_chunks": embedded}

    def search(self, query_vector: list[float], top_k: int = 10) -> list[tuple[str, float]]:
        """Cosine search inside PostgreSQL, same ``<=>`` pattern as ``PgVectorSearcher``. No visibility
        filter needed: this corpus is public case law, not citizen data."""
        rows = self.s.execute(
            text("SELECT chunk_id, 1 - (embedding <=> CAST(:q AS vector)) AS sim FROM legal_judgment_chunks WHERE embedding IS NOT NULL ORDER BY embedding <=> CAST(:q AS vector) LIMIT :n"),
            {"q": "[" + ",".join(f"{float(x):.8f}" for x in query_vector) + "]", "n": top_k},
        ).all()
        return [(chunk_id, float(sim)) for chunk_id, sim in rows]

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        m = self.s.get(LegalJudgmentChunkModel, chunk_id)
        if m is None:
            return None
        j = self.s.get(LegalJudgmentModel, m.judgment_id)
        name = (j.title if j and j.title else m.judgment_id)
        return Chunk(m.chunk_id, m.judgment_id, name, m.text, "legal_judgment", m.page, m.heading, m.chunk_index, m.entities, {})

    def get_judgment(self, judgment_id: str) -> JudgmentRecord | None:
        m = self.s.get(LegalJudgmentModel, judgment_id)
        if m is None:
            return None
        return JudgmentRecord(m.id, m.source, m.court, m.title, m.decision_date, m.neutral_citation, m.reporter_citation, m.source_pdf_url, m.page_count, m.char_count)


class SqlConversationRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def add_conversation(self, c: ConversationRecord) -> None:
        self.s.add(ConversationModel(id=c.id, user_id=c.user_id, title=c.title, created_at=c.created_at))
        self.s.flush()

    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        m = self.s.get(ConversationModel, conversation_id)
        return ConversationRecord(m.id, m.user_id, m.title, m.created_at) if m else None

    def list_conversations(self, user_id: str, limit: int = 50) -> list[ConversationRecord]:
        q = select(ConversationModel).where(ConversationModel.user_id == user_id).order_by(ConversationModel.created_at.desc()).limit(limit)
        return [ConversationRecord(m.id, m.user_id, m.title, m.created_at) for m in self.s.scalars(q)]

    def add_message(self, m: ConversationMessage) -> None:
        self.s.add(ConversationMessageModel(id=m.id, conversation_id=m.conversation_id, role=m.role, content=m.content, at=m.at, status=m.status, citations=m.citations, database_facts=m.database_facts, warnings=m.warnings))
        self.s.flush()

    def list_messages(self, conversation_id: str) -> list[ConversationMessage]:
        q = select(ConversationMessageModel).where(ConversationMessageModel.conversation_id == conversation_id).order_by(ConversationMessageModel.at)
        return [ConversationMessage(m.id, m.conversation_id, m.role, m.content, m.at, m.status, m.citations, m.database_facts, m.warnings) for m in self.s.scalars(q)]
