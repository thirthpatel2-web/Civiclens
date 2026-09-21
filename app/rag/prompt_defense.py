"""Prompt-injection defence for retrieved documents and user text.

Layers (none is sufficient alone, together they are defence in depth):
1. **Quarantine** – passages containing instruction-like text are withheld from the
   model and reported, rather than trusted to be ignored.
2. **Neutralise** – control/zero-width characters and delimiter look-alikes are
   stripped so a document cannot forge the evidence fence.
3. **Nonce fencing** – evidence is wrapped in markers carrying a per-request random
   nonce that a document cannot know, and the system prompt names that nonce.
4. **Output gating** – answers must cite evidence; uncited output is withheld
   (see ``grounded_generation``).

Limitation: pattern detection covers English phrasing only. Structural layers 2-4
apply to every language.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("override_instructions", re.compile(r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b(?:previous|prior|above|earlier|all|any|your|the)\b[^.\n]{0,30}\b(?:instructions?|prompts?|rules?|guidelines?)\b", re.I)),
    ("prompt_extraction", re.compile(r"\b(?:reveal|show|print|repeat|output|leak|display)\b[^.\n]{0,25}\b(?:system|hidden|initial|original)?\s*(?:prompt|instructions)\b", re.I)),
    ("role_hijack", re.compile(r"\byou are now\b|\bact as (?:if|an? (?:ai|assistant|system|admin|administrator|developer|root))\b|\bpretend to be\b", re.I)),
    ("new_instructions", re.compile(r"\bnew (?:system )?instructions?\s*:", re.I)),
    ("role_marker", re.compile(r"(?:^|\n)\s*(?:system|assistant|developer)\s*:", re.I)),
    ("chat_template_tokens", re.compile(r"<\|[a-z_]+\|>|\[/?INST\]|<</?SYS>>", re.I)),
    ("concealment", re.compile(r"\bdo not (?:tell|inform|alert|warn) the user\b", re.I)),
]
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b\u2060\ufeff\u202a-\u202e]")
_FENCE_LIKE = re.compile(r"<{3,}|>{3,}|`{3,}|\"{3,}|={4,}")


def scan_for_injection(text: str) -> list[str]:
    """Names of injection patterns present in ``text`` (empty list = none found)."""
    return [name for name, pat in _PATTERNS if pat.search(text or "")]


def neutralize(text: str) -> str:
    """Strip characters and sequences that could forge structure inside the prompt."""
    text = _CONTROL.sub("", text or "")
    return _FENCE_LIKE.sub(lambda m: m.group(0)[0] + "\u00b7" * (len(m.group(0)) - 1), text)


@dataclass(frozen=True)
class Quarantined:
    chunk_id: str
    reasons: list[str]


def new_nonce() -> str:
    return secrets.token_hex(8)


def fence(marker: str, body: str, nonce: str) -> str:
    """One fenced, neutralised evidence item."""
    return f"<<<EVIDENCE {marker} {nonce}>>>\n{neutralize(body)}\n<<<END {marker} {nonce}>>>"
