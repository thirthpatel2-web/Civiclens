"""UI string lookup: ported dictionary + ``ui_extra.json`` (strings for screens the original app lacked).

The extras exist in English and Hindi only; other languages fall back to English for those keys and
the gap is reported by ``coverage()`` - it is not machine-translated or guessed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.i18n.translator import Translator


class UiText:
    def __init__(self, base: Translator, extras: dict[str, dict[str, str]]) -> None:
        self.base, self.extras = base, extras

    @classmethod
    def load(cls) -> UiText:
        extras = json.loads((Path(__file__).with_name("ui_extra.json")).read_text(encoding="utf-8"))
        return cls(Translator.from_files(), extras)

    @property
    def languages(self) -> list[str]:
        return self.base.languages

    def t(self, key: str, lang: str | None = None, **params: Any) -> str:
        code = self.base.resolve_language(lang)
        if key in self.extras["en"]:
            text = self.extras.get(code, {}).get(key) or self.extras["en"][key]
            for k, v in params.items():
                text = text.replace("{" + k + "}", str(v))
            return text
        return self.base.t(key, code, **params)

    def extras_coverage(self) -> dict[str, tuple[int, int]]:
        total = len(self.extras["en"])
        return {lang: (sum(1 for k in self.extras["en"] if k in self.extras.get(lang, {})), total) for lang in self.base.languages}
