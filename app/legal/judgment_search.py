"""Semantic search over the full-text judgment corpus (app/legal/judgment_ingest.py populates it).

Kept separate from ``PrecedentIndex`` (metadata-only, in-memory, DB-free) because this needs a live
embedder + database round-trip per query - a ``JudgmentSearchPort`` so ``LegalAnalysisService`` stays
testable with a fake, and returns nothing (never a guess) when the corpus is empty or unreachable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from sqlalchemy import text


@dataclass(frozen=True)
class JudgmentExcerpt:
    """A real passage of judgment text, not a summary - ``text`` is verbatim from the source PDF."""

    judgment_id: str
    title: str | None
    court: str
    neutral_citation: str | None
    reporter_citation: str | None
    decision_date: date | None
    page: int | None
    text: str
    similarity: float


class JudgmentSearchPort(Protocol):
    def search(self, query: str, top_k: int = 3) -> list[JudgmentExcerpt]: ...


class SqlJudgmentSearch:
    """Embeds the query, then does one joined pgvector query (chunk + its judgment's metadata) -
    no N+1 lookups. Degrades to an empty result (never raises into the caller) if the embedder or
    database is unavailable, so a Legal Analyzer request never fails just because this extra was down."""

    def __init__(self, session_factory, embedder) -> None:
        self._sf, self._embedder = session_factory, embedder

    def search(self, query: str, top_k: int = 3) -> list[JudgmentExcerpt]:
        query = (query or "").strip()
        if not query:
            return []
        try:
            qvec = self._embedder.embed([query])[0]
        except Exception:  # noqa: BLE001 - embedding outage degrades to "no full text", not an error
            return []
        q = "[" + ",".join(f"{float(x):.8f}" for x in qvec) + "]"
        try:
            with self._sf() as session:
                rows = session.execute(
                    text(
                        "SELECT c.page, c.text, j.id, j.title, j.court, j.neutral_citation, j.reporter_citation, j.decision_date, "
                        "1 - (c.embedding <=> CAST(:q AS vector)) AS sim "
                        "FROM legal_judgment_chunks c JOIN legal_judgments j ON j.id = c.judgment_id "
                        "WHERE c.embedding IS NOT NULL ORDER BY c.embedding <=> CAST(:q AS vector) LIMIT :n"
                    ),
                    {"q": q, "n": top_k},
                ).all()
        except Exception:  # noqa: BLE001 - database outage degrades the same way
            return []
        return [JudgmentExcerpt(jid, title, court, neutral, reporter, ddate, page, chunk_text, float(sim))
                for page, chunk_text, jid, title, court, neutral, reporter, ddate, sim in rows]  # fmt: skip
