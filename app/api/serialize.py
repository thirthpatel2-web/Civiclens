"""Turn domain records into JSON-safe structures (dataclasses, enums, datetimes, tuples/sets)."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from enum import Enum
from typing import Any

_HIDE = {"password_hash", "secret_encrypted", "backup_code_hashes", "token_hash", "storage_name", "sha256"}


def to_jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj) if f.name not in _HIDE}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items() if k not in _HIDE}
    if isinstance(obj, list | tuple | set | frozenset):
        return [to_jsonable(v) for v in (sorted(obj) if isinstance(obj, set | frozenset) else obj)]
    if isinstance(obj, float) and obj in (float("inf"), float("-inf")):
        return None
    return obj


def complaint_json(c: Any) -> dict[str, Any]:
    """API view of a complaint: ``original_*`` make explicit that the citizen's text/language are never rewritten."""
    d = to_jsonable(c)
    d["original_text"], d["original_language"] = d.get("description"), d.get("language")
    return d
