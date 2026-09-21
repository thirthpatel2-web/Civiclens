"""Backup and restore the CivicLens PostgreSQL database via pg_dump/pg_restore (custom format,
compressed, safe for concurrent use since pg_dump takes a consistent MVCC snapshot).

Usage:
    python scripts/backup_database.py backup [--out backups/]
    python scripts/backup_database.py restore <dump_file> [--yes]

Reads connection details from DATABASE_URL (same variable the app itself uses), so it always
backs up/restores whatever database the app is actually configured against - never a guess.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _connection_parts(database_url: str) -> tuple[str, int, str, str, str]:
    """Parse DATABASE_URL (postgresql+psycopg://user:pass@host:port/db) into pg_dump's pieces."""
    normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    p = urlparse(normalized)
    if p.scheme != "postgresql" or not p.hostname or not p.username or not p.path.lstrip("/"):
        raise ValueError(f"DATABASE_URL is not a usable postgresql:// URL: {database_url!r}")
    return p.hostname, p.port or 5432, p.username, p.password or "", p.path.lstrip("/")


def backup(out_dir: Path) -> Path:
    from app.core.config import Settings

    settings = Settings.load()
    host, port, user, password, dbname = _connection_parts(settings.database_url)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"civiclens_{dbname}_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.dump"

    env = {"PGPASSWORD": password} if password else {}
    result = subprocess.run(
        ["pg_dump", "-h", host, "-p", str(port), "-U", user, "-d", dbname, "-F", "c", "-f", str(dest)],
        env={**os.environ, **env}, capture_output=True, text=True,
    )  # fmt: skip
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr}")
    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"Backed up {dbname}@{host}:{port} -> {dest} ({size_mb:.1f} MB)")
    return dest


def restore(dump_file: Path, *, confirmed: bool) -> None:
    from app.core.config import Settings

    settings = Settings.load()
    host, port, user, password, dbname = _connection_parts(settings.database_url)
    if not confirmed:
        print(f"This will REPLACE data in database {dbname!r} on {host}:{port} from {dump_file}.", file=sys.stderr)
        print("Re-run with --yes to actually do this.", file=sys.stderr)
        raise SystemExit(2)

    env = {"PGPASSWORD": password} if password else {}
    result = subprocess.run(
        ["pg_restore", "-h", host, "-p", str(port), "-U", user, "-d", dbname, "--clean", "--if-exists", "--no-owner", str(dump_file)],
        env={**os.environ, **env}, capture_output=True, text=True,
    )  # fmt: skip
    if result.returncode != 0:
        raise RuntimeError(f"pg_restore failed: {result.stderr}")
    print(f"Restored {dump_file} -> {dbname}@{host}:{port}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--out", type=Path, default=Path("backups"))
    r = sub.add_parser("restore")
    r.add_argument("dump_file", type=Path)
    r.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "backup":
        backup(args.out)
    else:
        restore(args.dump_file, confirmed=args.yes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
