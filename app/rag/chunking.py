"""Structure-aware chunking for civic/legal documents.

Strategy (ported from the original CivicLens chunker, re-implemented so it also
works for Indic scripts, which have no upper-case letters and use the danda ``।``):

1. STRUCTURAL – split on headings; table blocks stay atomic (row-split only when a
   single table exceeds the size limit, repeating its header row).
2. SIZE + OVERLAP – pack sentences up to ``max_tokens``; carry trailing sentences
   into the next chunk (``overlap_tokens``) so meaning across a boundary survives.
3. METADATA – page number, nearest heading and extracted identifiers per chunk.

Token counts are an *estimate* (words x 1.3), exactly as in the original.
Embedding-driven semantic sub-chunking from the Node version is intentionally not
ported: it made chunk boundaries depend on a live model, so chunking would not be
deterministic or testable offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_SINGLE_TABLE_TOKENS_FACTOR = 1  # tables larger than max_tokens are row-split

HEADING_PATTERNS = [
    re.compile(r"^#{1,6}\s+\S.*"),
    re.compile(r"^\d+(\.\d+){0,3}[.)]?\s+\S.{1,80}$"),
    re.compile(r"^(CHAPTER|SECTION|PART|ANNEXURE|SCHEDULE|CLAUSE|अध्याय|धारा|भाग)\s+[IVXLCDM\d]+", re.I),
    re.compile(r"^[A-Z][A-Z0-9\s\-,&()/]{5,80}$"),
]
ENTITY_PATTERNS: dict[str, re.Pattern[str]] = {
    "complaintId": re.compile(r"\b[A-Z]{2,5}-\d{3,8}(?:-[A-Z0-9]{4,8})?\b"),
    "projectId": re.compile(r"\b(?:PRJ|PROJ|WORK)[-/]?\d{3,7}\b", re.I),
    "govOrderNumber": re.compile(r"\bG\.?O\.?\s*(?:MS|RT|NO)?\.?\s*No\.?\s*[:\-]?\s*\d{1,7}\b", re.I),
    "wardNumber": re.compile(r"\bWard\s*(?:No\.?)?\s*[:\-]?\s*\d{1,3}\b", re.I),
    "amountInRupees": re.compile(r"₹\s?[\d,]+(?:\.\d{1,2})?|\bRs\.?\s?[\d,]+(?:\.\d{1,2})?", re.I),
    "date": re.compile(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b"),
    "neutralCitation": re.compile(r"\b\d{4}\s?INSC\s?\d{1,4}\b"),
}
_SENT_SPLIT = re.compile(r"(?<=[.?!।॥])\s+")
_ABBREVIATIONS = {
    "no", "nos", "sec", "secs", "art", "dr", "mr", "mrs", "ms", "shri", "smt", "rs", "vs", "v",
    "st", "ltd", "co", "govt", "dept", "e.g", "i.e", "etc", "viz", "cf", "p", "pp", "ch",
}  # fmt: skip


@dataclass(frozen=True)
class ChunkConfig:
    min_tokens: int = 60
    max_tokens: int = 350
    overlap_tokens: int = 40

    def __post_init__(self) -> None:
        if not (0 < self.min_tokens <= self.max_tokens):
            raise ValueError("require 0 < min_tokens <= max_tokens")
        if not (0 <= self.overlap_tokens < self.max_tokens):
            raise ValueError("require 0 <= overlap_tokens < max_tokens")


@dataclass
class RawChunk:
    text: str
    page: int | None
    heading: str | None
    index: int = 0
    entities: dict[str, list[str]] = field(default_factory=dict)
    token_estimate: int = 0
    is_table: bool = False


def approx_tokens(text: str) -> int:
    return round(len(text.split()) * 1.3)


def is_heading(line: str) -> bool:
    s = line.strip()
    return 3 <= len(s) <= 100 and any(p.match(s) for p in HEADING_PATTERNS)


def is_table_line(line: str) -> bool:
    return line.count("|") >= 2 or line.count("\t") >= 2


def extract_entities(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name, pat in ENTITY_PATTERNS.items():
        seen: dict[str, None] = {}
        for m in pat.finditer(text or ""):
            seen.setdefault(m.group(0).strip(), None)
        if seen:
            out[name] = list(seen)
    return out


def split_sentences(text: str) -> list[str]:
    """Sentence split that respects abbreviations (``No.``, ``Sec.``) and numbering (``3.2``)."""
    flat = re.sub(r"\s+", " ", text or "").strip()
    if not flat:
        return []
    parts = _SENT_SPLIT.split(flat)
    merged: list[str] = []
    for part in parts:
        if merged:
            prev_last = merged[-1].rstrip(".?!").split(" ")[-1].lower().rstrip(".")
            if merged[-1].endswith(".") and (prev_last in _ABBREVIATIONS or len(prev_last) == 1):
                merged[-1] += " " + part
                continue
        merged.append(part)
    return merged


@dataclass
class _Block:
    text: str
    page: int | None
    heading: str | None
    is_table: bool = False


def _parse_blocks(pages: list[tuple[int | None, str]]) -> list[_Block]:
    blocks: list[_Block] = []
    heading: str | None = None
    for page, text in pages:
        para: list[str] = []
        table: list[str] = []

        def flush_para(page: int | None = page) -> None:
            if para:
                blocks.append(_Block(" ".join(s.strip() for s in para if s.strip()), page, heading))
                para.clear()

        def flush_table(page: int | None = page) -> None:
            if table:
                blocks.append(_Block("\n".join(table), page, heading, True))
                table.clear()

        for line in (text or "").splitlines():
            if not line.strip():
                flush_para()
                flush_table()
            elif is_table_line(line):
                flush_para()
                table.append(line.rstrip())
            elif is_heading(line):
                flush_para()
                flush_table()
                heading = line.strip().lstrip("#").strip()
            else:
                flush_table()
                para.append(line)
        flush_para()
        flush_table()
    return [b for b in blocks if b.text.strip()]


def _split_long_sentence(sentence: str, max_tokens: int) -> list[str]:
    words = sentence.split()
    step = max(1, int(max_tokens / 1.3))
    return [" ".join(words[i : i + step]) for i in range(0, len(words), step)]


def _split_table(text: str, max_tokens: int) -> list[str]:
    rows = text.split("\n")
    if approx_tokens(text) <= max_tokens or len(rows) < 3:
        return [text]
    header, body = rows[0], rows[1:]
    out: list[str] = []
    cur = [header]
    for row in body:
        if len(cur) > 1 and approx_tokens("\n".join(cur + [row])) > max_tokens:
            out.append("\n".join(cur))
            cur = [header]
        cur.append(row)
    out.append("\n".join(cur))
    return out


def chunk_document(source: str | list[tuple[int | None, str]], config: ChunkConfig | None = None) -> list[RawChunk]:
    """Chunk plain text or ``[(page_number, text), …]``. Deterministic and offline."""
    cfg = config or ChunkConfig()
    pages = [(None, source)] if isinstance(source, str) else list(source)
    chunks: list[RawChunk] = []

    def emit(text: str, page: int | None, heading: str | None, is_table: bool = False) -> None:
        chunks.append(RawChunk(text, page, heading, len(chunks), extract_entities(text), approx_tokens(text), is_table))

    # group consecutive prose blocks by heading; keep tables separate/atomic
    cur_sents: list[str] = []
    cur_tokens = 0
    cur_page: int | None = None
    cur_heading: str | None = None

    def flush() -> None:
        nonlocal cur_sents, cur_tokens
        if cur_sents:
            emit(" ".join(cur_sents), cur_page, cur_heading)
        cur_sents, cur_tokens = [], 0

    for block in _parse_blocks(pages):
        if block.is_table:
            flush()
            for part in _split_table(block.text, cfg.max_tokens):
                emit(part, block.page, block.heading, True)
            continue
        if block.heading != cur_heading:
            flush()
            cur_heading = block.heading
        for sent in split_sentences(block.text):
            pieces = _split_long_sentence(sent, cfg.max_tokens) if approx_tokens(sent) > cfg.max_tokens else [sent]
            for piece in pieces:
                t = approx_tokens(piece)
                if cur_sents and cur_tokens + t > cfg.max_tokens:
                    carried: list[str] = []
                    carried_tokens = 0
                    for prev in reversed(cur_sents):
                        pt = approx_tokens(prev)
                        if carried_tokens + pt > cfg.overlap_tokens:
                            break
                        carried.insert(0, prev)
                        carried_tokens += pt
                    flush()
                    cur_sents, cur_tokens = carried, carried_tokens
                if not cur_sents:
                    cur_page = block.page
                cur_sents.append(piece)
                cur_tokens += t
    flush()

    # fold a tiny trailing prose chunk into its predecessor when they share a heading
    if len(chunks) >= 2:
        last, prev = chunks[-1], chunks[-2]
        if not last.is_table and not prev.is_table and last.heading == prev.heading and last.token_estimate < cfg.min_tokens:
            if prev.token_estimate + last.token_estimate <= cfg.max_tokens + cfg.min_tokens:
                prev.text += " " + last.text
                prev.token_estimate = approx_tokens(prev.text)
                prev.entities = extract_entities(prev.text)
                chunks.pop()
    for i, c in enumerate(chunks):
        c.index = i
    return chunks
