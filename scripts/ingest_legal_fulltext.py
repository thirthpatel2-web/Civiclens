"""Ingest real Supreme Court judgment PDFs (public S3 bucket, no auth) into the full-text legal
corpus: extract -> chunk -> embed (Ollama) -> pgvector (legal_judgments / legal_judgment_chunks).

Usage:
    python scripts/ingest_legal_fulltext.py --year 2024 [--limit 50] [--dry-run]
    python scripts/ingest_legal_fulltext.py --start-year 1950 --end-year 2026   # full corpus

Resumable: before downloading a PDF, its deterministic id is checked against the database, so
re-running (e.g. after an interruption) skips already-ingested judgments without spending any
network or embedding time on them - only genuinely new work is done.

``--dry-run`` downloads/extracts/chunks/embeds but does not write to PostgreSQL - useful to check
how many PDFs in a year are text-native vs. scanned before committing to a full run. Requires
DATABASE_URL, OLLAMA_BASE_URL and OLLAMA_EMBEDDING_MODEL (matching EMBEDDING_DIMENSIONS) unless
--dry-run is set, in which case only OLLAMA_* are needed for the embedding step.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.legal.judgment_ingest import (  # noqa: E402
    build_chunks,
    download_and_extract,
    judgment_id_for,
    list_sc_pdf_keys,
)


def ingest_year(year: int, language: str, limit: int, embedder, session_factory, repo_cls) -> dict[str, int]:
    print(f"Listing s3://indian-supreme-court-judgments/data/pdf/year={year}/{language}/ ...")
    sources = list_sc_pdf_keys(year, language, limit=limit)
    print(f"Found {len(sources)} PDF(s) for {year}.")

    counts = {"ok": 0, "already": 0, "scanned": 0, "download_failed": 0, "embed_failed": 0}
    t0 = time.monotonic()
    for i, src in enumerate(sources, start=1):
        jid = judgment_id_for(src)
        if session_factory is not None:
            with session_factory() as session:
                if repo_cls(session).get_judgment(jid) is not None:
                    counts["already"] += 1
                    continue

        try:
            record, jtext = download_and_extract(src)
        except ValueError as exc:  # scanned / no text
            counts["scanned"] += 1
            print(f"  [{i}/{len(sources)}] SKIP (scanned/no text): {src.key} - {exc}")
            continue
        except RuntimeError as exc:  # network
            counts["download_failed"] += 1
            print(f"  [{i}/{len(sources)}] SKIP (download failed): {src.key} - {exc}")
            continue

        title = record.title or record.neutral_citation or record.id
        chunks = build_chunks(record.id, title, jtext)
        try:
            vectors = embedder.embed([c.text for c in chunks]) if chunks else []
        except Exception as exc:  # noqa: BLE001 - report and move on; never fabricate an embedding
            counts["embed_failed"] += 1
            print(f"  [{i}/{len(sources)}] SKIP (embedding failed): {src.key} - {type(exc).__name__}: {exc}")
            continue

        counts["ok"] += 1
        cite = record.neutral_citation or record.reporter_citation or "(no citation parsed)"
        print(f"  [{i}/{len(sources)}] OK  {record.id}  {cite}  {record.page_count}p/{record.char_count}ch -> {len(chunks)} chunks  \"{title[:70]}\"")

        if session_factory is not None:
            from datetime import UTC, datetime

            with session_factory() as session:
                repo = repo_cls(session)
                repo.add_judgment(record, datetime.now(UTC))
                repo.replace_chunks(record.id, chunks, vectors)
                session.commit()

    elapsed = time.monotonic() - t0
    print(f"{year} done in {elapsed:.1f}s: {counts['ok']} ingested, {counts['already']} already had it, "
          f"{counts['scanned']} scanned/no-text, {counts['download_failed']} download failures, {counts['embed_failed']} embedding failures.")
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, help="a single year (mutually exclusive with --start-year/--end-year)")
    ap.add_argument("--start-year", type=int)
    ap.add_argument("--end-year", type=int)
    ap.add_argument("--language", default="english")
    ap.add_argument("--limit", type=int, default=0, help="max judgments to process per year (0 = all)")
    ap.add_argument("--dry-run", action="store_true", help="skip PostgreSQL writes")
    args = ap.parse_args(argv)

    if args.year is not None:
        years = [args.year]
    elif args.start_year is not None and args.end_year is not None:
        years = list(range(args.start_year, args.end_year + 1))
    else:
        print("Pass either --year or both --start-year and --end-year.", file=sys.stderr)
        return 2

    from app.core.config import Settings
    from app.db.repositories.content import SqlLegalJudgmentRepository
    from app.rag.ollama import OllamaClient, OllamaEmbeddingProvider

    settings = Settings.load()
    embedder = OllamaEmbeddingProvider(OllamaClient(settings.ollama_base_url), settings.ollama_embedding_model, settings.embedding_dimensions)

    session_factory = None
    if not args.dry_run:
        from app.db.session import make_engine, make_session_factory

        session_factory = make_session_factory(make_engine(settings))

    totals = {"ok": 0, "already": 0, "scanned": 0, "download_failed": 0, "embed_failed": 0}
    t0 = time.monotonic()
    for year in years:
        counts = ingest_year(year, args.language, args.limit, embedder, session_factory, SqlLegalJudgmentRepository)
        for k, v in counts.items():
            totals[k] += v

    elapsed = time.monotonic() - t0
    print()
    print(f"ALL YEARS done in {elapsed / 3600:.2f}h: {totals['ok']} newly ingested, {totals['already']} already had it, "
          f"{totals['scanned']} scanned/no-text, {totals['download_failed']} download failures, {totals['embed_failed']} embedding failures.")
    if session_factory is not None:
        with session_factory() as session:
            print("Corpus stats:", SqlLegalJudgmentRepository(session).stats())
    return 0 if totals["ok"] > 0 or totals["already"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
