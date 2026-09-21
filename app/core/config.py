"""Typed, validated application settings loaded from the environment.

Secrets are never given usable defaults in production: ``Settings.load`` raises
if ``APP_ENV=production`` and a secret is missing, short or a known placeholder.
``repr``/``redacted`` never print secret values.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

_PLACEHOLDERS = {"", "change-me", "changeme", "secret", "password"}
_MIN_SECRET_LEN = 32
ENVIRONMENTS = ("development", "test", "production")
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_dotenv() -> None:
    """Load .env into os.environ without overriding variables a deployment platform already set
    for real. A no-op (no error, no exception) when .env doesn't exist, e.g. in production where
    configuration comes from the platform, not a file. Cheap enough to call on every Settings.load()."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_REPO_ROOT / ".env", override=False)


class ConfigError(ValueError):
    """Raised when the environment cannot yield a safe configuration."""


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    """Immutable settings object."""

    app_env: str = "development"
    app_secret_key: str = field(default="", repr=False)
    session_secret: str = field(default="", repr=False)
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    database_url: str = field(default="", repr=False)
    redis_url: str = field(default="", repr=False)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    ollama_embedding_model: str = ""
    ollama_vision_model: str = ""
    embedding_dimensions: int = 0
    rag_top_k: int = 5
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    rrf_k: int = 60
    rerank_top_k: int = 20
    rag_min_relevance: float = 0.15
    upload_dir: str = "./uploads"
    max_upload_mb: int = 10
    bhashini_enabled: bool = False
    bhashini_api_key: str = field(default="", repr=False)
    bhashini_user_id: str = ""
    google_drive_enabled: bool = False
    google_credentials_file: str = ""
    gov_adapter_timeout_seconds: float = 10.0
    gov_adapter_max_retries: int = 2
    rti_response_days: int = 30
    rti_life_liberty_hours: int = 48
    rti_pdf_font: str = ""
    stt_provider: str = "auto"  # auto | bhashini | whisper | none
    whisper_model: str = ""
    expo_push_enabled: bool = False
    ocr_provider: str = "none"  # none | tesseract | ollama_vision
    ocr_languages: str = "eng"  # Tesseract language codes, e.g. "eng+hin+kan"
    tesseract_cmd: str = ""     # full path to tesseract.exe; unset = resolved from PATH
    tessdata_dir: str = ""      # directory holding <lang>.traineddata; unset = tesseract's own default

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def redacted(self) -> dict[str, Any]:
        """Settings suitable for logging/diagnostics: secrets replaced by a flag."""
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if not f.repr:
                out[f.name] = "<set>" if value else "<unset>"
            else:
                out[f.name] = value
        return out

    @classmethod
    def load(cls, env: Mapping[str, str] | None = None) -> Settings:
        if env is None:
            _load_dotenv()  # tests pass an explicit `env` dict and must stay isolated from .env
        e: Mapping[str, str] = os.environ if env is None else env
        app_env = e.get("APP_ENV", "development").strip().lower() or "development"
        if app_env not in ENVIRONMENTS:
            raise ConfigError(f"APP_ENV must be one of {ENVIRONMENTS}, got {app_env!r}")

        settings = cls(
            app_env=app_env,
            app_secret_key=e.get("APP_SECRET_KEY", "").strip(),
            session_secret=e.get("SESSION_SECRET", "").strip(),
            session_idle_minutes=_int(e, "SESSION_IDLE_MINUTES", 30),
            session_absolute_hours=_int(e, "SESSION_ABSOLUTE_HOURS", 12),
            database_url=e.get("DATABASE_URL", "").strip(),
            redis_url=e.get("REDIS_URL", "").strip(),
            ollama_base_url=e.get("OLLAMA_BASE_URL", "http://localhost:11434").strip(),
            ollama_model=e.get("OLLAMA_MODEL", "").strip(),
            ollama_embedding_model=e.get("OLLAMA_EMBEDDING_MODEL", "").strip(),
            ollama_vision_model=e.get("OLLAMA_VISION_MODEL", "").strip(),
            embedding_dimensions=_int(e, "EMBEDDING_DIMENSIONS", 0),
            rag_top_k=_int(e, "RAG_TOP_K", 5),
            bm25_k1=_float(e, "BM25_K1", 1.5),
            bm25_b=_float(e, "BM25_B", 0.75),
            rrf_k=_int(e, "RRF_K", 60),
            rerank_top_k=_int(e, "RERANK_TOP_K", 20),
            rag_min_relevance=_float(e, "RAG_MIN_RELEVANCE", 0.15),
            upload_dir=e.get("UPLOAD_DIR", "./uploads").strip() or "./uploads",
            max_upload_mb=_int(e, "MAX_UPLOAD_MB", 10),
            bhashini_enabled=_bool(e.get("BHASHINI_ENABLED")),
            bhashini_api_key=e.get("BHASHINI_API_KEY", "").strip(),
            bhashini_user_id=e.get("BHASHINI_USER_ID", "").strip(),
            google_drive_enabled=_bool(e.get("GOOGLE_DRIVE_ENABLED")),
            google_credentials_file=e.get("GOOGLE_CREDENTIALS_FILE", "").strip(),
            gov_adapter_timeout_seconds=_float(e, "GOV_ADAPTER_TIMEOUT_SECONDS", 10.0),
            gov_adapter_max_retries=_int(e, "GOV_ADAPTER_MAX_RETRIES", 2),
            rti_response_days=_int(e, "RTI_RESPONSE_DAYS", 30),
            rti_life_liberty_hours=_int(e, "RTI_LIFE_LIBERTY_HOURS", 48),
            rti_pdf_font=e.get("RTI_PDF_FONT", "").strip(),
            stt_provider=e.get("STT_PROVIDER", "auto").strip().lower() or "auto",
            whisper_model=e.get("WHISPER_MODEL", "").strip(),
            expo_push_enabled=_bool(e.get("EXPO_PUSH_ENABLED")),
            ocr_provider=e.get("OCR_PROVIDER", "none").strip().lower() or "none",
            ocr_languages=e.get("OCR_LANGUAGES", "eng").strip() or "eng",
            tesseract_cmd=e.get("TESSERACT_CMD", "").strip(),
            tessdata_dir=e.get("TESSDATA_DIR", "").strip(),
        )
        settings._validate()
        return settings

    def _validate(self) -> None:
        problems: list[str] = []
        if self.stt_provider not in ("auto", "bhashini", "whisper", "none"):
            problems.append("STT_PROVIDER must be auto, bhashini, whisper or none")
        if self.stt_provider == "whisper" and not self.whisper_model:
            problems.append("STT_PROVIDER=whisper requires WHISPER_MODEL")
        if self.ocr_provider not in ("none", "tesseract", "ollama_vision"):
            problems.append("OCR_PROVIDER must be none, tesseract or ollama_vision")
        if self.bm25_k1 <= 0 or not 0 <= self.bm25_b <= 1:
            problems.append("BM25_K1 must be > 0 and BM25_B within [0, 1]")
        if self.rrf_k <= 0:
            problems.append("RRF_K must be positive")
        if self.max_upload_mb <= 0:
            problems.append("MAX_UPLOAD_MB must be positive")
        if self.bhashini_enabled and not (self.bhashini_api_key and self.bhashini_user_id):
            problems.append("BHASHINI_ENABLED=true requires BHASHINI_API_KEY and BHASHINI_USER_ID")
        if self.google_drive_enabled and not self.google_credentials_file:
            problems.append("GOOGLE_DRIVE_ENABLED=true requires GOOGLE_CREDENTIALS_FILE")
        if self.is_production:
            for name in ("app_secret_key", "session_secret"):
                value = getattr(self, name)
                if value.lower() in _PLACEHOLDERS or len(value) < _MIN_SECRET_LEN:
                    problems.append(
                        f"{name.upper()} must be a random value of >= {_MIN_SECRET_LEN} chars in production"
                    )
            if not self.database_url:
                problems.append("DATABASE_URL is required in production")
        if problems:
            raise ConfigError("; ".join(problems))
