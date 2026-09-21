"""Unicode-aware tokenisation shared by BM25, reranking and duplicate detection.

The original tokenizer (``[a-z0-9-]{2,}``) silently dropped every Indic word, so
Hindi/Marathi/Bengali/Tamil/Telugu/Kannada text could never be retrieved lexically.
Here a token is a run of letters/digits/combining marks (vowel signs and viramas are
category Mn/Mc, which ``str.isalnum`` rejects) with internal hyphens kept, so
identifiers such as ``cr-1042`` remain single tokens.
"""

from __future__ import annotations

import unicodedata

_JOINERS = {"\u200c", "\u200d"}  # ZWNJ / ZWJ occur inside Indic conjuncts


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch in _JOINERS or unicodedata.category(ch) in ("Mn", "Mc")


def tokenize(text: str, *, min_length: int = 2) -> list[str]:
    """Lower-cased word tokens; hyphens/underscores are kept only *between* word chars."""
    if not text:
        return []
    text = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    buf: list[str] = []
    n = len(text)
    for i, ch in enumerate(text):
        if _is_word_char(ch):
            buf.append(ch)
        elif ch in "-_" and buf and i + 1 < n and _is_word_char(text[i + 1]):
            buf.append(ch)
        elif buf:
            tokens.append("".join(buf))
            buf = []
    if buf:
        tokens.append("".join(buf))
    return [t for t in tokens if len(t) >= min_length]


def unique_terms(text: str) -> list[str]:
    """Order-preserving de-duplicated tokens."""
    seen: set[str] = set()
    out: list[str] = []
    for t in tokenize(text):
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


STOPWORDS_EN = frozenset(
    "a an and are as at be been but by can could did do does for from had has have how i if in "
    "into is it its me my of on or our please s say says she should so than that the their them "
    "then there these they this those to was we were what when where which who whom why will with "
    "would you your about tell give show much many any".split()
)


def content_terms(text: str) -> list[str]:
    """Unique tokens minus English stop-words (used for relevance scoring, not BM25)."""
    return [t for t in unique_terms(text) if t not in STOPWORDS_EN]


def identifier_tokens(text: str) -> list[str]:
    """Digit-bearing tokens that behave like exact identifiers (``4291``, ``cr-1042``, ``2025-26``).

    A retrieved passage that lacks such a token cannot support a claim about it, which is
    how the pipeline refuses to "answer" questions about things that do not exist.
    """
    return [t for t in unique_terms(text) if any(c.isdigit() for c in t) and (len(t) >= 4 or "-" in t)]
