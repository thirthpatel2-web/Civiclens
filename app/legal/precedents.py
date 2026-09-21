"""Verified precedent records built from the Supreme Court metadata Parquet file.

WHAT THE DATA ACTUALLY IS (inspected, not assumed): 856 rows x 18 string columns, all
"Supreme Court of India", all decided in 2023. Columns: title, petitioner, respondent,
description (always empty), judge (comma-separated bench), author_judge (always null),
citation (SCR reporter citation), case_id (neutral citation ``YYYY INSC N``), cnr,
decision_date (``DD-MM-YYYY``), disposal_nature (blank in 11 rows), court,
available_languages, raw_html (a language-picker widget, discarded), path, nc_display,
scraped_at, year.

**It contains no judgment text** - no facts, holdings or ratio. So this index can verify
that a case *exists* and report its metadata; it cannot support claims about what a case
decided. ``cnr``, ``citation`` and ``path`` are unique per row; ``case_id`` is *not*
(clubbed matters share one neutral citation), so ``cnr`` is the primary key.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.rag.bm25 import BM25Index
from app.rag.models import Chunk

PARQUET_COLUMNS = ("title", "petitioner", "respondent", "judge", "citation", "case_id", "cnr", "decision_date", "disposal_nature",
                   "court", "available_languages", "path", "nc_display", "scraped_at", "year")  # fmt: skip
_NEUTRAL = re.compile(r"\b(\d{4})\s*INSC\s*(\d{1,5})\b", re.I)
_SCR = re.compile(r"\[\s*(\d{4})\s*\]\s*(\d{1,3})\s*S\.?\s*C\.?\s*R\.?\s*(\d{1,5})", re.I)
_OTHER_REPORTERS = re.compile(r"\(\s*\d{4}\s*\)\s*\d+\s*SCC\b|\bAIR\s+\d{4}\s+SC\b|\b\d{4}\s+SCC\s+OnLine\b|\b\d{4}\s+\(\d+\)\s+SCALE\b", re.I)


@dataclass(frozen=True)
class PrecedentRecord:
    cnr: str
    neutral_citation: str  # "2023 INSC 1043"
    reporter_citation: str | None  # "[2023] 16 S.C.R. 872"
    title: str
    petitioner: str | None
    respondent: str | None
    judges: tuple[str, ...]
    decision_date: date
    disposal: str | None
    court: str
    languages: tuple[str, ...]
    source_path: str | None
    scraped_at: str | None

    @property
    def year(self) -> int:
        return self.decision_date.year


@dataclass(frozen=True)
class Reject:
    row_number: int
    reason: str


def _s(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v != v:  # NaN
        return None
    t = str(v).strip()
    return t or None


def normalize_neutral(text: str) -> str | None:
    m = _NEUTRAL.search(text or "")
    return f"{m.group(1)} INSC {int(m.group(2))}" if m else None


def normalize_scr(text: str) -> str | None:
    m = _SCR.search(text or "")
    return f"[{m.group(1)}] {int(m.group(2))} S.C.R. {int(m.group(3))}" if m else None


def normalize_row(row: Mapping[str, Any]) -> PrecedentRecord:
    """One Parquet row -> record. Raises ``ValueError`` (with a reason) if the row is unusable."""
    cnr, title = _s(row.get("cnr")), _s(row.get("title"))
    title = " ".join(title.split()) if title else title  # source has double spaces around "versus"
    if not cnr:
        raise ValueError("missing cnr")
    if not title:
        raise ValueError("missing title")
    neutral = normalize_neutral(_s(row.get("case_id")) or _s(row.get("nc_display")) or "")
    if not neutral:
        raise ValueError("missing or unparsable neutral citation")
    raw_date = _s(row.get("decision_date"))
    try:
        decided = datetime.strptime(raw_date or "", "%d-%m-%Y").date()
    except ValueError:
        raise ValueError(f"unparsable decision_date {raw_date!r}") from None
    judges = tuple(j.strip() for j in (_s(row.get("judge")) or "").split(",") if j.strip())
    langs = tuple(x.strip().upper() for x in (_s(row.get("available_languages")) or "").split(",") if x.strip())
    return PrecedentRecord(cnr, neutral, normalize_scr(_s(row.get("citation")) or ""), title, _s(row.get("petitioner")), _s(row.get("respondent")),
                           judges, decided, _s(row.get("disposal_nature")), _s(row.get("court")) or "Supreme Court of India", langs,
                           _s(row.get("path")), _s(row.get("scraped_at")))  # fmt: skip


def load_records(rows: Iterable[Mapping[str, Any]]) -> tuple[list[PrecedentRecord], list[Reject]]:
    """Normalise all rows; duplicates by ``cnr`` keep the first and are reported as rejects."""
    seen: set[str] = set()
    records: list[PrecedentRecord] = []
    rejects: list[Reject] = []
    for i, row in enumerate(rows, start=1):
        try:
            rec = normalize_row(row)
        except ValueError as exc:
            rejects.append(Reject(i, str(exc)))
            continue
        if rec.cnr in seen:
            rejects.append(Reject(i, f"duplicate cnr {rec.cnr}"))
            continue
        seen.add(rec.cnr)
        records.append(rec)
    return records, rejects


def read_parquet_rows(path: str) -> list[dict[str, Any]]:
    """Read only the useful columns (``raw_html`` is 4.6 MB of widget markup and is skipped)."""
    import pandas as pd  # requires pyarrow (see requirements.txt)

    df = pd.read_parquet(path, columns=list(PARQUET_COLUMNS))
    return [{k: (None if pd.isna(v) else v) for k, v in rec.items()} for rec in df.to_dict("records")]


@dataclass(frozen=True)
class CitationCheck:
    verified: tuple[str, ...]
    unverified: tuple[str, ...]  # looks like a verifiable citation but is not in the index
    unverifiable: tuple[str, ...]  # a reporter format this dataset cannot check (SCC, AIR, ...)


@dataclass(frozen=True)
class PrecedentHit:
    record: PrecedentRecord
    score: float
    matched_on: str


class PrecedentIndex:
    """In-memory index over verified records: exact citation lookup + BM25 over metadata."""

    def __init__(self, records: Iterable[PrecedentRecord] = ()) -> None:
        self._by_cnr: dict[str, PrecedentRecord] = {}
        self._by_neutral: dict[str, list[str]] = defaultdict(list)
        self._by_scr: dict[str, str] = {}
        self._bm25 = BM25Index()
        for r in records:
            self.add(r)

    def __len__(self) -> int:
        return len(self._by_cnr)

    def add(self, r: PrecedentRecord) -> None:
        self._by_cnr[r.cnr] = r
        self._by_neutral[r.neutral_citation].append(r.cnr)
        if r.reporter_citation:
            self._by_scr[r.reporter_citation] = r.cnr
        text = f"{r.title} {' '.join(r.judges)} {r.disposal or ''} {r.neutral_citation} {r.reporter_citation or ''} {r.decision_date:%d %B %Y}"
        self._bm25.add(Chunk(r.cnr, r.cnr, r.title, text, "precedent_metadata", None, None, 0, {"neutralCitation": [r.neutral_citation]}))

    def get(self, cnr: str) -> PrecedentRecord | None:
        return self._by_cnr.get(cnr)

    def by_neutral_citation(self, citation: str) -> list[PrecedentRecord]:
        norm = normalize_neutral(citation)
        return [self._by_cnr[c] for c in self._by_neutral.get(norm or "", [])]

    def by_reporter_citation(self, citation: str) -> PrecedentRecord | None:
        norm = normalize_scr(citation)
        cnr = self._by_scr.get(norm or "")
        return self._by_cnr.get(cnr) if cnr else None

    def stats(self) -> dict[str, Any]:
        years = sorted({r.year for r in self._by_cnr.values()})
        courts = sorted({r.court for r in self._by_cnr.values()})
        return {"count": len(self), "years": years, "courts": courts, "has_judgment_text": False}

    def search(self, query: str, *, top_k: int = 5, disposal: str | None = None, year: int | None = None) -> list[PrecedentHit]:
        """Exact citations in the query win; otherwise BM25 over party names, bench, disposal and dates."""
        hits: list[PrecedentHit] = []
        seen: set[str] = set()
        for rec in [*[r for m in _NEUTRAL.finditer(query or "") for r in self.by_neutral_citation(m.group(0))],
                    *[r for m in _SCR.finditer(query or "") if (r := self.by_reporter_citation(m.group(0)))]]:  # fmt: skip
            if rec.cnr not in seen:
                seen.add(rec.cnr)
                hits.append(PrecedentHit(rec, 1.0, "exact citation"))
        for h in self._bm25.search(query, top_k * 3):
            rec = self._by_cnr[h.chunk_id]
            if rec.cnr in seen:
                continue
            seen.add(rec.cnr)
            hits.append(PrecedentHit(rec, h.score, "metadata text match"))
        out = [h for h in hits if (disposal is None or (h.record.disposal or "").lower() == disposal.lower()) and (year is None or h.record.year == year)]
        return out[:top_k]

    def verify_citations(self, text: str) -> CitationCheck:
        verified: list[str] = []
        unverified: list[str] = []
        for m in _NEUTRAL.finditer(text or ""):
            c = normalize_neutral(m.group(0)) or m.group(0)
            (verified if self.by_neutral_citation(c) else unverified).append(c)
        for m in _SCR.finditer(text or ""):
            c = normalize_scr(m.group(0)) or m.group(0)
            (verified if self.by_reporter_citation(c) else unverified).append(c)
        unverifiable = [m.group(0) for m in _OTHER_REPORTERS.finditer(text or "")]
        dedupe = lambda xs: tuple(dict.fromkeys(xs))  # noqa: E731
        return CitationCheck(dedupe(verified), dedupe(unverified), dedupe(unverifiable))
