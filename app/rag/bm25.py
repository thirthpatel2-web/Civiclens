"""Okapi BM25 lexical retrieval over an in-memory inverted index.

Unlike the Node original (which took candidate rows from Postgres FTS and only then
scored), this index owns real corpus statistics (N, document frequencies, average
length) so scores are true BM25 for the indexed corpus. In deployment the index is
rebuilt/updated from ``document_chunks`` when documents become *ready*.

Score(q, d) = sum over query terms t of
    idf(t) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * |d| / avgdl)),
    idf(t) = ln(1 + (N - df + 0.5) / (df + 0.5)).
An optional exact-identifier bonus rewards chunks whose extracted entities (complaint
ids, G.O. numbers …) literally occur in the query, which pure BM25 under-weights.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from app.rag.models import Chunk
from app.rag.text import tokenize, unique_terms


@dataclass(frozen=True)
class Bm25Hit:
    chunk_id: str
    score: float


@dataclass
class _Doc:
    chunk: Chunk
    tf: Counter[str]
    length: int
    entity_values: list[str] = field(default_factory=list)


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75, exact_entity_bonus: float = 10.0) -> None:
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("BM25 requires k1 > 0 and 0 <= b <= 1")
        self.k1, self.b, self.exact_entity_bonus = k1, b, exact_entity_bonus
        self._docs: dict[str, _Doc] = {}
        self._postings: dict[str, set[str]] = {}
        self._total_length = 0

    def __len__(self) -> int:
        return len(self._docs)

    @property
    def average_length(self) -> float:
        return self._total_length / len(self._docs) if self._docs else 0.0

    def add(self, chunk: Chunk) -> None:
        if chunk.chunk_id in self._docs:
            self.remove(chunk.chunk_id)
        tokens = tokenize(f"{chunk.heading or ''} {chunk.text}")
        tf = Counter(tokens)
        values = [v for vs in chunk.entities.values() for v in vs if str(v).strip()]
        self._docs[chunk.chunk_id] = _Doc(chunk, tf, len(tokens), values)
        self._total_length += len(tokens)
        for term in tf:
            self._postings.setdefault(term, set()).add(chunk.chunk_id)

    def remove(self, chunk_id: str) -> None:
        doc = self._docs.pop(chunk_id, None)
        if doc is None:
            return
        self._total_length -= doc.length
        for term in doc.tf:
            posting = self._postings.get(term)
            if posting is not None:
                posting.discard(chunk_id)
                if not posting:
                    del self._postings[term]

    def remove_document(self, document_id: str) -> int:
        ids = [cid for cid, d in self._docs.items() if d.chunk.document_id == document_id]
        for cid in ids:
            self.remove(cid)
        return len(ids)

    def idf(self, term: str) -> float:
        n = len(self._docs)
        df = len(self._postings.get(term, ()))
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(
        self, query: str, top_k: int = 20, *, visible: Callable[[Chunk], bool] | None = None
    ) -> list[Bm25Hit]:
        """Top-k hits; ``visible`` enforces access/filters *before* scoring is returned."""
        terms = unique_terms(query)
        if not terms or not self._docs:
            return []
        candidates: set[str] = set()
        for t in terms:
            candidates |= self._postings.get(t, set())
        query_upper = (query or "").upper()
        avgdl = self.average_length or 1.0
        hits: list[Bm25Hit] = []
        for cid in candidates:
            doc = self._docs[cid]
            if visible is not None and not visible(doc.chunk):
                continue
            score = 0.0
            for t in terms:
                tf = doc.tf.get(t, 0)
                if not tf:
                    continue
                norm = tf + self.k1 * (1 - self.b + self.b * doc.length / avgdl)
                score += self.idf(t) * tf * (self.k1 + 1) / norm
            if any(v.upper() in query_upper for v in doc.entity_values):
                score += self.exact_entity_bonus
            if score > 0:
                hits.append(Bm25Hit(cid, score))
        hits.sort(key=lambda h: (-h.score, h.chunk_id))
        return hits[:top_k]
