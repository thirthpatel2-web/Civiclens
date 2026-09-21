"""OCR providers for document ingestion (scanned PDFs, photographed documents).

Contract: return the text that is *in the image*, in its original language and script - no translation, no summary, no
correction. If nothing legible is found, raise (the document is marked FAILED with the reason) - never return a guess.

* ``TesseractOcr``      - local Tesseract via ``pytesseract`` (needs the tesseract binary + traineddata for each language in OCR_LANGUAGES).
* ``OllamaVisionOcr``   - a vision-capable model served by Ollama (reuses OLLAMA_VISION_MODEL); quality depends on the model.
Neither runs in the build sandbox (packages/binaries/models absent); they are tested with injected engines only.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Callable
from typing import Any

from app.core.exceptions import DependencyUnavailable, NotConfigured, ValidationFailed

MAX_PDF_PAGES = 20
_PROMPT = ("Transcribe ALL text visible in this image exactly as written, in its original language and script. "
           "Do not translate, summarise, correct or add anything. If there is no legible text, reply with exactly: NO_TEXT")  # fmt: skip


def _render_pdf_pages(data: bytes, scale: float = 2.0) -> list[bytes]:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise NotConfigured("Scanned-PDF OCR needs pypdfium2 to render pages.") from exc
    pdf = pdfium.PdfDocument(data)
    out: list[bytes] = []
    for i in range(min(len(pdf), MAX_PDF_PAGES)):
        buf = io.BytesIO()
        pdf[i].render(scale=scale).to_pil().save(buf, format="PNG")
        out.append(buf.getvalue())
    return out


class _PagedOcr:
    def _one(self, image: bytes) -> str:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    def __init__(self, render_pdf: Callable[[bytes], list[bytes]] | None = None) -> None:
        self._render = render_pdf or _render_pdf_pages

    def extract(self, data: bytes, mime: str) -> str:
        images = self._render(data) if mime == "application/pdf" else [data]
        texts = [t for t in (self._one(img).strip() for img in images) if t and t != "NO_TEXT"]
        if not texts:
            raise ValidationFailed("No legible text was found by OCR.")
        return "\n\n".join(texts)


class TesseractOcr(_PagedOcr):
    name = "tesseract"

    def __init__(self, languages: str = "eng", *, tesseract_cmd: str = "", tessdata_dir: str = "",
                 engine: Callable[[bytes, str], str] | None = None, render_pdf: Callable[[bytes], list[bytes]] | None = None) -> None:  # fmt: skip
        super().__init__(render_pdf)
        self._langs = languages
        if engine is not None:  # injected (tests)
            self._engine = engine
            return
        try:
            import pytesseract
            from PIL import Image

            if tesseract_cmd:  # not on system PATH (e.g. a non-admin Windows install)
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            pytesseract.get_tesseract_version()  # raises if the binary is missing
        except ImportError as exc:
            raise NotConfigured("Install pytesseract and Pillow (and the tesseract binary) to use OCR_PROVIDER=tesseract.") from exc
        except Exception as exc:
            raise NotConfigured("The tesseract binary is not installed, not on PATH, and TESSERACT_CMD is not set.") from exc
        # No quotes: pytesseract splits `config` with shlex(posix=False) on Windows, which does
        # NOT strip quote characters (they'd end up literally embedded in the path and fail) - so
        # a tessdata_dir containing a space cannot be passed this way. Documented in .env.example.
        config = f"--tessdata-dir {tessdata_dir}" if tessdata_dir else ""
        self._engine = lambda img, langs: pytesseract.image_to_string(Image.open(io.BytesIO(img)), lang=langs, config=config)

    def _one(self, image: bytes) -> str:
        try:
            return self._engine(image, self._langs)
        except Exception as exc:
            raise DependencyUnavailable(f"OCR failed ({type(exc).__name__}); check that Tesseract language data for '{self._langs}' is installed.") from exc


class OllamaVisionOcr(_PagedOcr):
    name = "ollama_vision"

    def __init__(self, client: Any, model: str, *, render_pdf: Callable[[bytes], list[bytes]] | None = None) -> None:
        super().__init__(render_pdf)
        if not model:
            raise NotConfigured("OLLAMA_VISION_MODEL is not set.")
        self._client, self._model = client, model

    def _one(self, image: bytes) -> str:
        return str(self._client.chat(self._model, [{"role": "user", "content": _PROMPT}], images=[base64.b64encode(image).decode("ascii")]))


def build_ocr(provider: str, *, languages: str, ollama_client: Any | None, vision_model: str, tesseract_cmd: str = "", tessdata_dir: str = "") -> Any | None:
    if provider == "none":
        return None
    if provider == "tesseract":
        return TesseractOcr(languages, tesseract_cmd=tesseract_cmd, tessdata_dir=tessdata_dir)
    if provider == "ollama_vision":
        if ollama_client is None:
            raise NotConfigured("OCR_PROVIDER=ollama_vision needs an Ollama connection.")
        return OllamaVisionOcr(ollama_client, vision_model)
    raise NotConfigured(f"Unknown OCR provider '{provider}'.")
