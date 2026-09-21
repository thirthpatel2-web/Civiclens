"""UI string lookup for the seven supported languages.

The dictionary (``translations.json``) was ported from the original CivicLens app: 142
English keys; Hindi and Kannada lack 2 of them and Tamil, Telugu, Marathi and Bengali lack
10. A missing key falls back to English (and is *reported*, so gaps are visible) - it is
never machine-translated on the fly and never silently invented.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_LANGUAGE = "en"
BRAND_NAME = "CivicLens"  # the product name is never transliterated or translated
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class Translator:
    def __init__(self, translations: Mapping[str, Mapping[str, str]], default: str = DEFAULT_LANGUAGE) -> None:
        if default not in translations:
            raise ValueError("default language missing from translations")
        self._tr, self._default = translations, default
        self.missing: set[tuple[str, str]] = set()  # (language, key) pairs that fell back

    @classmethod
    def from_files(cls) -> Translator:
        raw = json.loads((Path(__file__).with_name("translations.json")).read_text(encoding="utf-8"))
        for table in raw.values():  # the source dictionary transliterated the brand in 5 languages
            table["appName"] = BRAND_NAME
        return cls(raw)

    @property
    def languages(self) -> list[str]:
        return sorted(self._tr)

    def resolve_language(self, code: str | None) -> str:
        c = (code or "").lower().split("-")[0]
        return c if c in self._tr else self._default

    def t(self, key: str, lang: str | None = None, **params: Any) -> str:
        lang = self.resolve_language(lang)
        text = self._tr[lang].get(key)
        if text is None:
            self.missing.add((lang, key))
            text = self._tr[self._default].get(key, key)  # last resort: the key itself, visibly untranslated
        return _PLACEHOLDER.sub(lambda m: str(params.get(m.group(1), m.group(0))), text)

    def coverage(self) -> dict[str, dict[str, Any]]:
        base = set(self._tr[self._default])
        out: dict[str, dict[str, Any]] = {}
        for lang, table in self._tr.items():
            missing = sorted(base - set(table))
            out[lang] = {"translated": len(base) - len(missing), "total": len(base), "missing_keys": missing}
        return out


def load_json(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
