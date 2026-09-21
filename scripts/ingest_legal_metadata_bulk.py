"""Bulk-load the REAL Supreme Court metadata Parquet files directly from the public S3 bucket
(metadata/parquet/year=YYYY/metadata.parquet, one per year, no auth needed) into legal_precedents.

This is the missing step behind Layer A's empty index: scripts/ingest_legal_metadata.py already
handles normalisation + upsert correctly, but needs a local .parquet file; nothing previously
downloaded one. This script does both - download each year, then reuse the existing pipeline.

Usage:
    python scripts/ingest_legal_metadata_bulk.py [--start-year 1950] [--end-year 2026]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.legal.precedents import PrecedentIndex, load_records, read_parquet_rows  # noqa: E402

BUCKET = "https://indian-supreme-court-judgments.s3.amazonaws.com"
_S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


def list_years() -> list[int]:
    body = urllib.request.urlopen(f"{BUCKET}/?list-type=2&delimiter=/&prefix=metadata/parquet/", timeout=30).read()  # noqa: S310
    root = ElementTree.fromstring(body)  # noqa: S314 - trusted public AWS endpoint
    years = []
    for p in root.findall(f"{_S3_NS}CommonPrefixes/{_S3_NS}Prefix"):
        text = p.text or ""
        if "year=" in text:
            years.append(int(text.rsplit("year=", 1)[1].rstrip("/")))
    return sorted(years)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start-year", type=int, default=1950)
    ap.add_argument("--end-year", type=int, default=2026)
    args = ap.parse_args(argv)

    from app.core.config import Settings
    from app.db.repositories.content import SqlLegalRepository
    from app.db.session import make_engine, make_session_factory

    session_factory = make_session_factory(make_engine(Settings.load()))
    years = [y for y in list_years() if args.start_year <= y <= args.end_year]
    print(f"Found {len(years)} year(s) of real metadata to load: {years[0]}-{years[-1]}")

    total_accepted = total_rejected = total_upserted = 0
    with tempfile.TemporaryDirectory() as tmp:
        for y in years:
            url = f"{BUCKET}/metadata/parquet/year={y}/metadata.parquet"
            dest = Path(tmp) / f"{y}.parquet"
            try:
                urllib.request.urlretrieve(url, dest)  # noqa: S310 - trusted public AWS endpoint
            except urllib.error.HTTPError as exc:
                print(f"  {y}: SKIP (HTTP {exc.code})")
                continue
            rows = read_parquet_rows(str(dest))
            records, rejects = load_records(rows)
            with session_factory() as session:
                n = SqlLegalRepository(session).upsert_all(records)
                session.commit()
            total_accepted += len(records)
            total_rejected += len(rejects)
            total_upserted += n
            print(f"  {y}: {len(rows)} rows -> {len(records)} accepted, {len(rejects)} rejected, {n} upserted")

    with session_factory() as session:
        index = PrecedentIndex(SqlLegalRepository(session).load_all())
    print()
    print(f"Done: {total_accepted} accepted, {total_rejected} rejected across all years.")
    print("Live index stats:", index.stats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
