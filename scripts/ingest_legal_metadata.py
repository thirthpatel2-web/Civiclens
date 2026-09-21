"""Validate and normalise the Supreme Court metadata Parquet into precedent records.

Usage:
    python scripts/ingest_legal_metadata.py PATH.parquet [--out precedents.jsonl] [--reader auto|pandas|minimal]

``pandas`` (with pyarrow) is the production reader. ``minimal`` is a dependency-free
reader for flat string columns (tools/minimal_parquet_reader.py) used when pyarrow is
not installable; ``auto`` tries pandas first. Writing to PostgreSQL is done by the
repository layer, which this script does not replace: it reports and exports only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.legal.precedents import (  # noqa: E402
    PARQUET_COLUMNS,
    PrecedentIndex,
    load_records,
    read_parquet_rows,
)


def _minimal_rows(path: str) -> list[dict]:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from minimal_parquet_reader import read_parquet_strings  # type: ignore[import-not-found]

    cols = read_parquet_strings(path)
    n = len(next(iter(cols.values())))
    return [{k: (cols[k][i] if k in cols else None) for k in PARQUET_COLUMNS} for i in range(n)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("parquet")
    ap.add_argument("--out")
    ap.add_argument("--reader", choices=["auto", "pandas", "minimal"], default="auto")
    ap.add_argument("--db", action="store_true", help="upsert the accepted records into PostgreSQL (needs DATABASE_URL and migrations applied)")
    args = ap.parse_args(argv)

    reader = args.reader
    rows: list[dict]
    if reader in ("auto", "pandas"):
        try:
            rows, reader = read_parquet_rows(args.parquet), "pandas"
        except ImportError as exc:
            if args.reader == "pandas":
                print(f"pandas/pyarrow unavailable: {exc}", file=sys.stderr)
                return 2
            rows, reader = _minimal_rows(args.parquet), "minimal"
    else:
        rows = _minimal_rows(args.parquet)

    records, rejects = load_records(rows)
    index = PrecedentIndex(records)
    print(f"reader={reader} rows={len(rows)} accepted={len(records)} rejected={len(rejects)}")
    for r in rejects[:10]:
        print(f"  reject row {r.row_number}: {r.reason}")
    print("index stats:", index.stats())
    print("disposal:", dict(Counter(r.disposal or "(blank)" for r in records).most_common()))
    shared = Counter(r.neutral_citation for r in records)
    print("neutral citations shared by >1 case:", {k: v for k, v in shared.items() if v > 1})
    if args.db:
        from app.core.config import Settings
        from app.db.repositories.content import SqlLegalRepository
        from app.db.session import make_engine, make_session_factory

        with make_session_factory(make_engine(Settings.load()))() as session:
            n = SqlLegalRepository(session).upsert_all(records)
            session.commit()
        print(f"upserted {n} precedent records into PostgreSQL")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps({**r.__dict__, "decision_date": r.decision_date.isoformat(), "judges": list(r.judges), "languages": list(r.languages)}, ensure_ascii=False) + "\n")
        print(f"wrote {len(records)} records to {args.out}")
    return 0 if not rejects else 1


if __name__ == "__main__":
    raise SystemExit(main())
