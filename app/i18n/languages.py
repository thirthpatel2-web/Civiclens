"""Language registry: BCP-47/ISO 639-1 codes, native names, scripts, and script detection.

Design rule for the whole product: the citizen's **original text and language are never replaced**.
Anything derived (translation, normalisation) lives in separate fields. This module is the single place that
knows which languages exist and which script each is written in, so voice, complaint intake and the
assistant agree. Support for a language *in a given speech engine* is declared by that engine
(``SttCapabilities``), not here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str  # ISO 639-1 (BCP-47 primary subtag)
    name: str  # English name (used in model prompts)
    native: str  # name in its own script
    script: str  # ISO 15924
    ranges: tuple[tuple[int, int], ...]  # Unicode blocks of the script


_LATN = ((0x41, 0x5A), (0x61, 0x7A), (0xC0, 0x24F))
LANGUAGES: dict[str, Language] = {
    "en": Language("en", "English", "English", "Latn", _LATN),
    "hi": Language("hi", "Hindi", "हिन्दी", "Deva", ((0x900, 0x97F),)),
    "mr": Language("mr", "Marathi", "मराठी", "Deva", ((0x900, 0x97F),)),
    "bn": Language("bn", "Bengali", "বাংলা", "Beng", ((0x980, 0x9FF),)),
    "gu": Language("gu", "Gujarati", "ગુજરાતી", "Gujr", ((0xA80, 0xAFF),)),
    "pa": Language("pa", "Punjabi", "ਪੰਜਾਬੀ", "Guru", ((0xA00, 0xA7F),)),
    "ta": Language("ta", "Tamil", "தமிழ்", "Taml", ((0xB80, 0xBFF),)),
    "te": Language("te", "Telugu", "తెలుగు", "Telu", ((0xC00, 0xC7F),)),
    "kn": Language("kn", "Kannada", "ಕನ್ನಡ", "Knda", ((0xC80, 0xCFF),)),
    "ml": Language("ml", "Malayalam", "മലയാളം", "Mlym", ((0xD00, 0xD7F),)),
}
UI_LANGUAGES = ("en", "hi", "mr", "bn", "ta", "te", "kn")  # languages with a translated UI dictionary
_SCRIPT_TO_DEFAULT = {"Latn": "en", "Deva": "hi", "Beng": "bn", "Gujr": "gu", "Guru": "pa", "Taml": "ta", "Telu": "te", "Knda": "kn", "Mlym": "ml"}
_SCRIPT_RANGES = {lang.script: lang.ranges for lang in LANGUAGES.values()}


def is_supported(code: str | None) -> bool:
    return (code or "") in LANGUAGES


def language_name(code_or_name: str | None) -> str:
    """English language name for prompts; accepts a code (``kn``) or an already-spelled name."""
    c = (code_or_name or "").strip()
    if c.lower() in LANGUAGES:
        return LANGUAGES[c.lower()].name
    return c or "English"


def script_histogram(text: str) -> dict[str, int]:
    """Count letters per script (digits, punctuation and spaces are ignored)."""
    counts: dict[str, int] = {}
    for ch in text or "":
        cp = ord(ch)
        if not ch.isalpha() and not (0x900 <= cp <= 0xD7F):  # Indic vowel signs are not str.isalpha()
            continue
        for script, ranges in _SCRIPT_RANGES.items():
            if any(lo <= cp <= hi for lo, hi in ranges):
                counts[script] = counts.get(script, 0) + 1
                break
    return counts


def dominant_script(text: str) -> str | None:
    h = script_histogram(text)
    return max(h, key=lambda k: h[k]) if h else None


def detect_language(text: str) -> tuple[str | None, bool]:
    """Script-based language guess: ``(code, ambiguous)``. Devanagari could be Hindi *or* Marathi -> ``('hi', True)``.

    Deliberately conservative: it only names the language a script uniquely implies, and says so when it cannot decide.
    """
    script = dominant_script(text)
    if script is None:
        return None, False
    return _SCRIPT_TO_DEFAULT[script], script == "Deva"


def script_matches(code: str, text: str, min_ratio: float = 0.6) -> bool:
    """Is the text (mostly) written in the script of ``code``? Used to catch silent translation/romanisation."""
    lang = LANGUAGES.get(code)
    if lang is None:
        return False
    h = script_histogram(text)
    total = sum(h.values())
    return total == 0 or h.get(lang.script, 0) / total >= min_ratio
