"""Citations are built from retrieved evidence, never from model output.

The model is asked to reference evidence as ``[E1]``, ``[E2]`` … (and ``[DB]`` for
database facts). ``validate_answer_citations`` then checks each marker against the
citations actually supplied; markers that do not exist are stripped and reported, so
a fabricated source can never reach the user as a citation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.rag.models import RetrievedChunk

_MARKER = re.compile(r"\[(E\d+|DB)\]")
DB_MARKER = "DB"


@dataclass(frozen=True)
class Citation:
    marker: str
    chunk_id: str
    document_id: str
    document_name: str
    document_type: str
    page: int | None
    heading: str | None
    excerpt: str
    found_via: tuple[str, ...]
    bm25_score: float | None
    semantic_similarity: float | None
    rerank_score: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "marker": self.marker, "chunkId": self.chunk_id, "documentId": self.document_id,
            "documentName": self.document_name, "documentType": self.document_type,
            "page": self.page, "heading": self.heading, "excerpt": self.excerpt,
            "foundVia": list(self.found_via), "bm25Score": self.bm25_score,
            "semanticSimilarity": self.semantic_similarity, "rerankScore": self.rerank_score,
        }  # fmt: skip


def build_citations(chunks: list[RetrievedChunk], excerpt_chars: int = 400) -> list[Citation]:
    out: list[Citation] = []
    for i, rc in enumerate(chunks, start=1):
        c = rc.chunk
        out.append(
            Citation(
                marker=f"E{i}", chunk_id=c.chunk_id, document_id=c.document_id,
                document_name=c.document_name, document_type=c.document_type, page=c.page,
                heading=c.heading, excerpt=c.text[:excerpt_chars], found_via=tuple(rc.found_via),
                bm25_score=rc.bm25_score, semantic_similarity=rc.semantic_similarity,
                rerank_score=rc.rerank_score,
            )
        )  # fmt: skip
    return out


@dataclass(frozen=True)
class CitationCheck:
    cleaned_answer: str
    used_markers: tuple[str, ...]
    invalid_markers: tuple[str, ...]

    @property
    def is_grounded(self) -> bool:
        return bool(self.used_markers)


def validate_answer_citations(answer: str, citations: list[Citation], *, db_available: bool) -> CitationCheck:
    valid = {c.marker for c in citations} | ({DB_MARKER} if db_available else set())
    used: list[str] = []
    invalid: list[str] = []

    def repl(m: re.Match[str]) -> str:
        marker = m.group(1)
        if marker in valid:
            if marker not in used:
                used.append(marker)
            return m.group(0)
        if marker not in invalid:
            invalid.append(marker)
        return ""

    cleaned = re.sub(r"[ \t]{2,}", " ", _MARKER.sub(repl, answer)).strip()
    return CitationCheck(cleaned, tuple(used), tuple(invalid))
