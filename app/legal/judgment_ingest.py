"""Full-text ingestion of public court judgment PDFs (Supreme Court bucket first; see judgment_ingest.md
notes in the ingestion script for High Court scoping).

Nothing here invents text: every judgment is downloaded from its real public S3 URL, extracted with
the same ``pypdf`` code path ``document_service.extract_pages`` uses for citizen uploads, chunked with
the existing structure-aware chunker, and embedded with the configured Ollama model. A judgment whose
PDF is scanned (no extractable text) is skipped and reported, never OCR'd-by-guessing or faked.

Standard library + pypdf only, matching ``app/rag/ollama.py``'s no-heavy-dependency style: the source
buckets are public (``--no-sign-request`` equivalent - no auth headers needed) so a bare urllib GET
against the S3 REST API is sufficient and avoids adding boto3 as a dependency.
"""

from __future__ import annotations

import io
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from xml.etree import ElementTree

from app.legal.precedents import normalize_neutral, normalize_scr
from app.rag.chunking import ChunkConfig, chunk_document
from app.rag.models import Chunk

SC_BUCKET = "https://indian-supreme-court-judgments.s3.amazonaws.com"
_S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
_FILENAME_YEAR = re.compile(r"^(\d{4})_")


@dataclass(frozen=True)
class JudgmentSource:
    """One judgment PDF found in the public bucket, not yet downloaded."""

    key: str
    year: int
    url: str


@dataclass(frozen=True)
class JudgmentText:
    """Extracted, not-yet-chunked judgment text."""

    pages: tuple[tuple[int, str], ...]
    char_count: int
    neutral_citation: str | None
    reporter_citation: str | None
    title: str | None


@dataclass(frozen=True)
class JudgmentRecord:
    id: str
    source: str
    court: str
    title: str | None
    decision_date: date | None
    neutral_citation: str | None
    reporter_citation: str | None
    source_pdf_url: str
    page_count: int
    char_count: int


def _http_get(url: str, *, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "CivicLens-legal-ingest/1.0"})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Could not reach {url}: {exc}") from exc


def list_sc_pdf_keys(year: int, language: str = "english", *, limit: int = 0) -> list[JudgmentSource]:
    """List real PDF object keys in the public Supreme Court bucket for one year. No auth: the bucket
    allows anonymous ``ListObjectsV2``. Returns at most ``limit`` keys (0 = all)."""
    prefix = f"data/pdf/year={year}/{language}/"
    keys: list[JudgmentSource] = []
    token: str | None = None
    while True:
        url = f"{SC_BUCKET}/?list-type=2&prefix={prefix}&max-keys=1000"
        if token:
            url += f"&continuation-token={urllib.parse.quote(token, safe='')}"
        body = _http_get(url)
        root = ElementTree.fromstring(body)  # noqa: S314 - trusted public AWS endpoint, not user input
        for c in root.findall(f"{_S3_NS}Contents"):
            key = (c.findtext(f"{_S3_NS}Key") or "").strip()
            if not key.endswith(".pdf"):
                continue
            keys.append(JudgmentSource(key, year, f"{SC_BUCKET}/{key}"))
            if limit and len(keys) >= limit:
                return keys
        is_truncated = (root.findtext(f"{_S3_NS}IsTruncated") or "false").lower() == "true"
        token = root.findtext(f"{_S3_NS}NextContinuationToken")
        if not is_truncated or not token:
            break
    return keys


def extract_judgment_text(pdf_bytes: bytes) -> JudgmentText:
    """Same extraction path as citizen document uploads (``pypdf``). Raises ``ValueError`` if the PDF
    has no extractable text (e.g. a scanned image with no text layer) - callers must skip, not guess."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if reader.is_encrypted:
        raise ValueError("password-protected PDF")
    pages = [(i + 1, (p.extract_text() or "").strip()) for i, p in enumerate(reader.pages)]
    total_chars = sum(len(t) for _, t in pages)
    if total_chars < 200:
        raise ValueError(f"no usable extracted text ({total_chars} chars across {len(pages)} pages - likely scanned)")
    first_page = pages[0][1] if pages else ""
    neutral = normalize_neutral(first_page)
    reporter = normalize_scr(first_page)
    title = _guess_title(first_page)
    return JudgmentText(tuple(pages), total_chars, neutral, reporter, title)


_TITLE_VS = re.compile(r"^(.{3,150}?)\s+v\.?s?\.?\s+(.{3,150})$", re.I)


def _guess_title(first_page: str) -> str | None:
    """Best-effort case title from the first page's early lines (SC judgments print it right after the
    citation header). Returns None rather than a wrong guess if no "X v. Y" pattern is found nearby."""
    lines = [ln.strip() for ln in first_page.splitlines()[:12] if ln.strip()]
    for i, line in enumerate(lines):
        if re.fullmatch(r"v\.?s?\.?", line, re.I) and 0 < i < len(lines) - 1:
            return f"{lines[i - 1]} v. {lines[i + 1]}"
        m = _TITLE_VS.match(line)
        if m:
            return f"{m.group(1).strip()} v. {m.group(2).strip()}"
    return None


def parse_decision_date(pages: tuple[tuple[int, str], ...]) -> date | None:
    """SC judgments print a plain date line near the top, e.g. '25 September 2024'."""
    if not pages:
        return None
    m = re.search(r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b", pages[0][1])
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").date()
    except ValueError:
        return None


def build_chunks(judgment_id: str, title: str, text: JudgmentText, config: ChunkConfig | None = None) -> list[Chunk]:
    raw = chunk_document(list(text.pages), config)
    return [
        Chunk(
            chunk_id=f"{judgment_id}:{r.index}",
            document_id=judgment_id,
            document_name=title,
            text=r.text,
            document_type="legal_judgment",
            page=r.page,
            heading=r.heading,
            chunk_index=r.index,
            entities=r.entities,
            metadata={"source": "sc_judgment"},
        )
        for r in raw
    ]


def judgment_id_for(source: JudgmentSource) -> str:
    """Deterministic id from the source key (not a random uuid) so re-ingesting the same PDF is idempotent."""
    stem = source.key.rsplit("/", 1)[-1].removesuffix(".pdf")
    return f"sc:{source.year}:{stem}"


def make_record(source: JudgmentSource, text: JudgmentText) -> JudgmentRecord:
    return JudgmentRecord(
        id=judgment_id_for(source),
        source="sc",
        court="Supreme Court of India",
        title=text.title,
        decision_date=parse_decision_date(text.pages),
        neutral_citation=text.neutral_citation,
        reporter_citation=text.reporter_citation,
        source_pdf_url=source.url,
        page_count=len(text.pages),
        char_count=text.char_count,
    )


def download_and_extract(source: JudgmentSource) -> tuple[JudgmentRecord, JudgmentText]:
    """Network I/O + extraction only - no chunking/embedding/DB here, so this step alone is easy to
    retry or run standalone (e.g. to audit how many PDFs in a year are scanned vs. text-native)."""
    pdf_bytes = _http_get(source.url, timeout=90.0)
    text = extract_judgment_text(pdf_bytes)
    return make_record(source, text), text
