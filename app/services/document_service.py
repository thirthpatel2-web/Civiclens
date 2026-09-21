"""Document upload validation, secure storage, text extraction and RAG ingestion.

Pipeline: validate -> store -> extract (PDF text / DOCX / TXT; OCR for images and scanned
PDFs *only if an OCR provider is configured*) -> chunk -> embed -> index -> READY.

A document becomes READY only when every step succeeded. Any failure leaves it FAILED
with the reason stored, removes partial index entries and allows a bounded retry.
Without an embedding provider a document can be READY for keyword search only, and that
is recorded (``semantic_indexed=False``) rather than hidden.
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from xml.etree import ElementTree as ET  # noqa: S405 - DOCX XML from an already size-limited zip; see _docx_text

from app.core.exceptions import CivicLensError, NotConfigured, NotFound, ValidationFailed
from app.rag.chunking import ChunkConfig, chunk_document
from app.rag.index import RagIndex
from app.rag.models import Chunk
from app.rag.ollama import EmbeddingProvider

ALLOWED_TYPES: dict[str, str] = {
    ".pdf": "application/pdf", ".txt": "text/plain", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
}  # fmt: skip
IMAGE_TYPES = {"image/png", "image/jpeg"}
MAX_DOCX_UNCOMPRESSED = 50 * 1024 * 1024
MAX_ATTEMPTS = 3
_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class ValidatedUpload:
    display_name: str
    storage_name: str
    mime: str
    size: int
    sha256: str


def safe_filename(name: str) -> str:
    """Drop directories, normalise, restrict to ``[A-Za-z0-9._-]`` and cap the length.

    The extension is kept separately so a non-ASCII stem (``सड़क.pdf``) becomes
    ``file.pdf`` rather than losing its type.
    """
    leaf = (name or "").replace("\\", "/").split("/")[-1]
    stem, dot, ext = leaf.rpartition(".")
    if not dot:
        stem, ext = leaf, ""
    ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    stem = _SAFE_CHARS.sub("_", ascii_stem).strip("._-")[:80] or "file"
    ext = _SAFE_CHARS.sub("", unicodedata.normalize("NFKD", ext).encode("ascii", "ignore").decode())[:8]
    return f"{stem}.{ext}" if ext else stem


def sniff_mime(ext: str, data: bytes) -> str | None:
    """Content-based check that the bytes really are what the extension claims."""
    if ext == ".pdf":
        return "application/pdf" if data.startswith(b"%PDF-") else None
    if ext == ".png":
        return "image/png" if data.startswith(b"\x89PNG\r\n\x1a\n") else None
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg" if data.startswith(b"\xff\xd8\xff") else None
    if ext == ".docx":
        if not data.startswith(b"PK"):
            return None
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return ALLOWED_TYPES[".docx"] if "word/document.xml" in z.namelist() and "[Content_Types].xml" in z.namelist() else None
        except zipfile.BadZipFile:
            return None
    if ext == ".txt":
        if b"\x00" in data:
            return None
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return "text/plain"
    return None


def validate_upload(filename: str, data: bytes, *, max_bytes: int, declared_mime: str | None = None) -> ValidatedUpload:
    ext = Path(safe_filename(filename)).suffix.lower()
    if ext not in ALLOWED_TYPES:
        raise ValidationFailed("This file type is not allowed.", details={"allowed": sorted(ALLOWED_TYPES)})
    if not data:
        raise ValidationFailed("The file is empty.")
    if len(data) > max_bytes:
        raise ValidationFailed(f"The file exceeds the {max_bytes // (1024 * 1024)} MB limit.")
    mime = sniff_mime(ext, data)
    if mime is None:
        raise ValidationFailed("The file content does not match its extension.")
    if declared_mime and declared_mime != mime and not (declared_mime == "application/octet-stream"):
        raise ValidationFailed("The declared file type does not match the file content.")
    return ValidatedUpload(safe_filename(filename), uuid.uuid4().hex + ext, mime, len(data), hashlib.sha256(data).hexdigest())


class Storage(Protocol):
    """Contract shared by every storage provider (Local, Google Drive): identical semantics, checked by one parametrised test."""

    provider_name: str

    def save(self, storage_name: str, data: bytes) -> None: ...
    def read(self, storage_name: str) -> bytes: ...
    def delete(self, storage_name: str) -> None: ...
    def health(self) -> dict[str, str]:
        """{"provider", "state": CONNECTED | UNAVAILABLE, "detail"} - performs a real (harmless) round trip."""
        ...


class LocalStorage:
    """Files live under one root with server-generated names; traversal is impossible."""

    provider_name = "local"

    def health(self) -> dict[str, str]:
        import uuid as _uuid

        probe = f"{_uuid.uuid4().hex}.bin"
        try:
            self.save(probe, b"ok")
            ok = self.read(probe) == b"ok"
            self.delete(probe)
            return {"provider": self.provider_name, "state": "CONNECTED" if ok else "UNAVAILABLE", "detail": str(self._root)}
        except Exception as exc:
            return {"provider": self.provider_name, "state": "UNAVAILABLE", "detail": type(exc).__name__}

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_name: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}\.[a-z0-9]{2,5}", storage_name):
            raise ValidationFailed("Invalid storage name.")
        p = (self._root / storage_name).resolve()
        if p.parent != self._root:
            raise ValidationFailed("Invalid storage path.")
        return p

    def save(self, storage_name: str, data: bytes) -> None:
        p = self._path(storage_name)
        if p.exists():
            raise ValidationFailed("Storage name already exists.")
        p.write_bytes(data)
        p.chmod(0o600)

    def read(self, storage_name: str) -> bytes:
        p = self._path(storage_name)
        if not p.exists():
            raise NotFound("File not found.")
        return p.read_bytes()

    def delete(self, storage_name: str) -> None:
        self._path(storage_name).unlink(missing_ok=True)


class OcrProvider(Protocol):
    def extract(self, data: bytes, mime: str) -> str: ...


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        info = z.getinfo("word/document.xml")
        if info.file_size > MAX_DOCX_UNCOMPRESSED:
            raise ValidationFailed("The document is too large to process.")
        root = ET.fromstring(z.read("word/document.xml"))  # noqa: S314
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paras = ["".join(t.text or "" for t in p.iter(f"{ns}t")) for p in root.iter(f"{ns}p")]
    return "\n".join(paras)


def extract_pages(mime: str, data: bytes, ocr: OcrProvider | None) -> list[tuple[int | None, str]]:
    """Return ``[(page, text)]``. Raises with a specific reason if nothing usable is found."""
    if mime == "text/plain":
        return [(None, data.decode("utf-8"))]
    if mime == ALLOWED_TYPES[".docx"]:
        return [(None, _docx_text(data))]
    if mime == "application/pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ValidationFailed("Password-protected PDFs cannot be processed.")
            pages = [(i + 1, (p.extract_text() or "").strip()) for i, p in enumerate(reader.pages)]
        except ValidationFailed:
            raise
        except Exception as exc:
            raise ValidationFailed(f"The PDF could not be read: {type(exc).__name__}.") from exc
        if any(t for _, t in pages):
            return [(n, t) for n, t in pages if t]
        if ocr is None:
            raise NotConfigured("This PDF has no extractable text (scanned?) and OCR is not configured.")
        return [(None, ocr.extract(data, mime))]
    if mime in IMAGE_TYPES:
        if ocr is None:
            raise NotConfigured("Text extraction from images requires an OCR provider, which is not configured.")
        return [(None, ocr.extract(data, mime))]
    raise ValidationFailed("Unsupported document type.")


@dataclass
class DocumentRecord:
    id: str
    owner_id: str
    name: str
    mime: str
    size: int
    sha256: str
    storage_name: str
    visibility: str = "private"  # private | department | public
    department_id: str | None = None
    status: DocumentStatus = DocumentStatus.UPLOADED
    error: str | None = None
    chunk_count: int = 0
    semantic_indexed: bool = False
    attempts: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class DocumentRepository(Protocol):
    def add(self, doc: DocumentRecord) -> None: ...
    def get(self, doc_id: str) -> DocumentRecord | None: ...
    def update(self, doc: DocumentRecord) -> None: ...


class DocumentIngestor:
    def __init__(self, repo: DocumentRepository, storage: Storage, index: RagIndex, *, embedder: EmbeddingProvider | None = None,
                 ocr: OcrProvider | None = None, chunk_config: ChunkConfig | None = None, clock: Callable[[], datetime] | None = None) -> None:  # fmt: skip
        self._repo, self._storage, self._index = repo, storage, index
        self._embedder, self._ocr, self._chunk_config = embedder, ocr, chunk_config
        self._clock = clock or (lambda: datetime.now(UTC))

    def upload(self, owner_id: str, filename: str, data: bytes, *, max_bytes: int, declared_mime: str | None = None,
               visibility: str = "private", department_id: str | None = None) -> DocumentRecord:  # fmt: skip
        if visibility not in ("private", "department", "public"):
            raise ValidationFailed("Invalid visibility.")
        v = validate_upload(filename, data, max_bytes=max_bytes, declared_mime=declared_mime)
        self._storage.save(v.storage_name, data)
        doc = DocumentRecord(str(uuid.uuid4()), owner_id, v.display_name, v.mime, v.size, v.sha256, v.storage_name, visibility, department_id,
                             created_at=self._clock(), updated_at=self._clock())  # fmt: skip
        self._repo.add(doc)
        return doc

    def process(self, doc_id: str) -> DocumentRecord:
        doc = self._repo.get(doc_id)
        if doc is None:
            raise NotFound("Document not found.")
        if doc.status in (DocumentStatus.PROCESSING, DocumentStatus.READY):
            return doc
        if doc.attempts >= MAX_ATTEMPTS:
            raise ValidationFailed("Maximum processing attempts reached.")
        doc.status, doc.error, doc.attempts, doc.updated_at = DocumentStatus.PROCESSING, None, doc.attempts + 1, self._clock()
        self._repo.update(doc)
        try:
            data = self._storage.read(doc.storage_name)
            pages = extract_pages(doc.mime, data, self._ocr)
            raw = chunk_document(pages, self._chunk_config)
            if not raw:
                raise ValidationFailed("No text could be extracted from the document.")
            chunks = [
                Chunk(f"{doc.id}:{r.index}", doc.id, doc.name, r.text, doc.mime, r.page, r.heading, r.index, r.entities,
                      {"owner_id": doc.owner_id, "visibility": doc.visibility, "department_id": doc.department_id})  # fmt: skip
                for r in raw
            ]
            vectors = self._embedder.embed([c.text for c in chunks]) if self._embedder else None
            self._index.remove_document(doc.id)  # idempotent re-processing
            self._index.add_document(chunks, vectors)
            doc.chunk_count, doc.semantic_indexed, doc.status = len(chunks), vectors is not None, DocumentStatus.READY
        except (CivicLensError, ValueError) as exc:
            self._index.remove_document(doc.id)
            doc.status, doc.error = DocumentStatus.FAILED, getattr(exc, "message", str(exc))
        except Exception as exc:  # unexpected: record a generic reason, keep the detail in logs
            self._index.remove_document(doc.id)
            doc.status, doc.error = DocumentStatus.FAILED, f"Unexpected processing error ({type(exc).__name__})."
        doc.updated_at = self._clock()
        self._repo.update(doc)
        return doc

    def retry(self, doc_id: str) -> DocumentRecord:
        doc = self._repo.get(doc_id)
        if doc is None:
            raise NotFound("Document not found.")
        if doc.status is not DocumentStatus.FAILED:
            raise ValidationFailed("Only failed documents can be retried.")
        return self.process(doc_id)


def document_access_filter(ctx, chunk: Chunk) -> bool:  # type: ignore[no-untyped-def]
    """Who may retrieve a chunk: owner (private), same department (department), anyone (public)."""
    from app.core.authorization import Role

    meta = chunk.metadata
    vis = meta.get("visibility", "private")
    if vis == "public":
        return True
    if meta.get("owner_id") == ctx.user_id:
        return True
    if vis == "department":
        if ctx.role is Role.SUPER_ADMIN:
            return True
        return ctx.role in (Role.OFFICER, Role.ADMIN) and ctx.department_id is not None and ctx.department_id == meta.get("department_id")
    return False
