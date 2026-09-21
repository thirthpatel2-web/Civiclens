"""Are the database migrations at the head this code expects? (pure parsing + one read-only query)"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

VERSIONS = Path(__file__).resolve().parent.parent.parent / "alembic" / "versions"


def expected_head(versions_dir: Path = VERSIONS) -> str:
    """The single head revision of the migration chain found on disk (raises if the chain is broken/branched)."""
    revs: dict[str, str | None] = {}
    for f in versions_dir.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        r = re.search(r'^revision\s*=\s*["\']([^"\']+)["\']', text, re.M)
        d = re.search(r'^down_revision\s*=\s*(?:None|["\']([^"\']+)["\'])', text, re.M)
        if r:
            revs[r.group(1)] = d.group(1) if d else None
    parents = {p for p in revs.values() if p}
    heads = [r for r in revs if r not in parents]
    if len(heads) != 1:
        raise ValueError(f"migration chain has {len(heads)} heads: {sorted(heads)}")
    return heads[0]


def check(session: Any, versions_dir: Path = VERSIONS) -> dict[str, str | None]:
    """{"status": ok|behind|ahead|unknown, "current": ..., "expected": ...} - reports, never migrates."""
    expected = expected_head(versions_dir)
    sql: Any = "SELECT version_num FROM alembic_version"
    try:
        from sqlalchemy import text

        sql = text(sql)
    except ImportError:  # only in environments without SQLAlchemy (tests with a fake session)
        pass
    try:
        row = session.execute(sql).first()
    except Exception:
        return {"status": "unknown", "current": None, "expected": expected, "detail": "alembic_version table not readable (migrations never applied?)"}
    current = row[0] if row else None
    return {"status": "ok" if current == expected else "behind" if current is not None else "unknown", "current": current, "expected": expected}
