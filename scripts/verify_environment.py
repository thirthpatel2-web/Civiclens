"""Report what is actually available in this environment. Nothing is assumed or faked.

Exit code 0 only if every *required* check passes. Optional/unconfigured items are listed
with their true state (NOT_CONFIGURED / SKIPPED), never as success.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import ConfigError, Settings  # noqa: E402

REQUIRED_PACKAGES = [("cryptography", "cryptography"), ("numpy", "numpy"), ("pypdf", "pypdf"), ("reportlab", "reportlab")]
INFRA_PACKAGES = [
    ("argon2", "argon2-cffi"), ("pyotp", "pyotp"), ("qrcode", "qrcode"), ("PIL", "Pillow"), ("pandas", "pandas"), ("pyarrow", "pyarrow"),
    ("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("nicegui", "nicegui"), ("pydantic", "pydantic"), ("sqlalchemy", "SQLAlchemy"),
    ("psycopg", "psycopg"), ("pgvector", "pgvector"), ("alembic", "alembic"), ("redis", "redis"), ("httpx", "httpx"), ("pytest", "pytest"),
    ("ruff", "ruff"), ("mypy", "mypy"),
]  # fmt: skip


@dataclass
class Row:
    name: str
    status: str  # PASS | FAIL | MISSING | NOT_CONFIGURED | SKIPPED | UNREACHABLE
    detail: str = ""
    required: bool = False


def check_package(module: str, dist: str, required: bool) -> Row:
    try:
        importlib.import_module(module)
        return Row(f"package {dist}", "PASS", importlib.metadata.version(dist), required)
    except ImportError:
        return Row(f"package {dist}", "FAIL" if required else "MISSING", "not installed", required)
    except importlib.metadata.PackageNotFoundError:
        return Row(f"package {dist}", "PASS", "importable (version unknown)", required)


def tcp(url: str, default_port: int, name: str) -> Row:
    if not url:
        return Row(name, "NOT_CONFIGURED", "URL not set")
    p = urlparse(url)
    try:
        with socket.create_connection((p.hostname or "", p.port or default_port), timeout=2):
            return Row(name, "PASS", f"TCP connect to {p.hostname}:{p.port or default_port} ok")
    except OSError as exc:
        return Row(name, "UNREACHABLE", f"{p.hostname}:{p.port or default_port} -> {type(exc).__name__}")


def main() -> int:
    rows: list[Row] = []
    v = sys.version_info
    rows.append(Row("python >= 3.12", "PASS" if v >= (3, 12) else "FAIL", f"{v.major}.{v.minor}.{v.micro} (3.14 is the deployment target)", True))
    rows += [check_package(m, d, True) for m, d in REQUIRED_PACKAGES] + [check_package(m, d, False) for m, d in INFRA_PACKAGES]

    try:
        settings = Settings.load()
        rows.append(Row("settings load/validate", "PASS", f"APP_ENV={settings.app_env}", True))
    except ConfigError as exc:
        rows.append(Row("settings load/validate", "FAIL", str(exc), True))
        settings = Settings()

    rows.append(tcp(settings.database_url, 5432, "postgresql"))
    rows.append(tcp(settings.redis_url, 6379, "redis"))
    if settings.ollama_base_url:
        from app.rag.ollama import OllamaClient, probe

        ok, detail, _ = probe(OllamaClient(settings.ollama_base_url, timeout=3), [settings.ollama_model, settings.ollama_embedding_model])
        rows.append(Row("ollama", "PASS" if ok else "UNREACHABLE", detail))
    for name, val in (("OLLAMA_MODEL", settings.ollama_model), ("OLLAMA_EMBEDDING_MODEL", settings.ollama_embedding_model)):
        rows.append(Row(f"config {name}", "PASS" if val else "NOT_CONFIGURED", "set" if val else "unset: no model is guessed"))
    rows.append(Row("config EMBEDDING_DIMENSIONS", "PASS" if settings.embedding_dimensions else "NOT_CONFIGURED", str(settings.embedding_dimensions or "unset")))
    rows.append(Row("bhashini", "PASS" if settings.bhashini_enabled else "NOT_CONFIGURED", "enabled" if settings.bhashini_enabled else "disabled"))
    rows.append(Row("google drive", "PASS" if settings.google_drive_enabled else "NOT_CONFIGURED", "enabled" if settings.google_drive_enabled else "disabled"))

    from app.data.seed import load_seed, validate
    from app.i18n.translator import Translator
    from app.integrations.adapters import build_adapters

    problems = validate(load_seed())
    rows.append(Row("seed data consistency", "PASS" if not problems else "FAIL", "; ".join(problems) or "ok", True))
    cov = Translator.from_files().coverage()
    rows.append(Row("translations", "PASS", ", ".join(f"{k}:{c['translated']}/{c['total']}" for k, c in sorted(cov.items()))))
    for platform, adapter in build_adapters(dict(os.environ)).items():
        rows.append(Row(f"adapter {platform}", adapter.state.value if adapter.state.value != "UNAVAILABLE" else "NOT_CONFIGURED" if not adapter.is_configured() else "SKIPPED",
                        "configured (not probed here)" if adapter.is_configured() else "missing: " + ", ".join(adapter.config.missing())))  # fmt: skip
    versions = sorted((Path(__file__).resolve().parent.parent / "alembic" / "versions").glob("0*.py"))
    rows.append(Row("alembic revisions present", "PASS" if len(versions) >= 3 else "FAIL", ", ".join(v.stem for v in versions), True))
    try:
        from app.main import create_app  # needs fastapi/nicegui/sqlalchemy; a missing package is reported, not hidden

        app = create_app(with_ui=False)
        rows.append(Row("application factory / routes", "PASS", f"{len(app.routes)} routes registered", True))
    except ImportError as exc:
        rows.append(Row("application factory / routes", "MISSING", f"cannot import: {exc}"))
    except Exception as exc:
        rows.append(Row("application factory / routes", "FAIL", f"{type(exc).__name__}: {exc}", True))
    try:
        import pytesseract

        langs = pytesseract.get_languages()
        rows.append(Row("OCR engine (tesseract)", "PASS", f"v{pytesseract.get_tesseract_version()} languages: {', '.join(langs)}"))
    except Exception:
        rows.append(Row("OCR engine (tesseract)", "MISSING", "pytesseract/tesseract binary not found (OCR_PROVIDER=tesseract will be NOT_CONFIGURED)"))
    try:
        import faster_whisper  # noqa: F401

        rows.append(Row("speech engine (faster-whisper)", "PASS", "package present; also set WHISPER_MODEL"))
    except ImportError:
        rows.append(Row("speech engine (faster-whisper)", "MISSING", "not installed (STT_PROVIDER=whisper unavailable)"))
    rows.append(Row("database migrations applied", "SKIPPED", "run: alembic upgrade head (needs PostgreSQL + pgvector + EMBEDDING_DIMENSIONS)"))
    rows.append(Row("websocket / live server", "SKIPPED", "start with: python run.py, then connect to /ws with a session cookie"))

    width = max(len(r.name) for r in rows)
    for r in rows:
        print(f"{r.status:<15} {r.name:<{width}}  {r.detail}")
    failed = [r for r in rows if r.required and r.status != "PASS"]
    print(f"\n{len(failed)} required check(s) failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
