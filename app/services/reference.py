"""Human-friendly, checksummed reference numbers (``CL-20260919-7K3M9QXA``)."""

from __future__ import annotations

import re
import secrets
from datetime import date

_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # no 0/O/1/I/L
_BODY_LEN = 7
_RE = re.compile(rf"^(?P<prefix>[A-Z]{{2,5}})-(?P<date>\d{{8}})-(?P<body>[{_ALPHABET}]{{{_BODY_LEN}}})(?P<check>[{_ALPHABET}])$")


def _check_char(prefix: str, day: str, body: str) -> str:
    total = 0
    for i, ch in enumerate(f"{prefix}{day}{body}"):
        total += (i + 1) * (_ALPHABET.index(ch) if ch in _ALPHABET else ord(ch))
    return _ALPHABET[total % len(_ALPHABET)]


def generate_reference(prefix: str, on: date, *, rand: secrets.SystemRandom | None = None) -> str:
    """Random body + check character. Uniqueness is enforced by a DB constraint (retry on clash)."""
    r = rand or secrets.SystemRandom()
    body = "".join(r.choice(_ALPHABET) for _ in range(_BODY_LEN))
    day = on.strftime("%Y%m%d")
    return f"{prefix}-{day}-{body}{_check_char(prefix, day, body)}"


def is_valid_reference(ref: str, prefix: str | None = None) -> bool:
    m = _RE.match((ref or "").strip().upper())
    if not m or (prefix and m["prefix"] != prefix):
        return False
    return _check_char(m["prefix"], m["date"], m["body"]) == m["check"]
