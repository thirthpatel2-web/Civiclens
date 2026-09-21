import logging
import unittest

from app.core.exceptions import (
    Conflict,
    DependencyUnavailable,
    NotConfigured,
    NotFound,
    ValidationFailed,
)
from app.providers.ocr import OllamaVisionOcr, TesseractOcr, build_ocr
from app.services.complaint_status import ComplaintStatus as S
from app.services.document_service import extract_pages
from app.workers.handlers import GrievanceWorker
from tests.support_env import CIT, CIT2, OFF_R1, OFF_W1, PNG, Env

PDF_LIKE = b"%PDF-1.4 scanned"


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


class OcrTests(unittest.TestCase):
    def test_no_provider_means_scans_and_images_fail_with_a_clear_reason(self):
        for mime in ("image/png", "application/pdf"):
            with self.assertRaises((NotConfigured, ValidationFailed)):
                extract_pages(mime, b"x", None) if mime != "application/pdf" else extract_pages(mime, b"%PDF-1.4\n%%EOF", None)

    def test_tesseract_returns_text_in_its_original_script_and_receives_the_configured_languages(self):
        seen = []
        ocr = TesseractOcr("eng+kan", engine=lambda img, langs: (seen.append(langs), "ಸರ್ಕಾರಿ ಆದೇಶ 2025 order")[1])
        self.assertEqual(ocr.extract(PNG, "image/png"), "ಸರ್ಕಾರಿ ಆದೇಶ 2025 order")
        self.assertEqual(seen, ["eng+kan"])
        self.assertEqual(extract_pages("image/png", PNG, ocr), [(None, "ಸರ್ಕಾರಿ ಆದೇಶ 2025 order")])

    def test_scanned_pdf_pages_are_rendered_and_joined(self):
        ocr = TesseractOcr("eng", engine=lambda img, langs: f"text of {img.decode()}", render_pdf=lambda data: [b"p1", b"p2", b"p3"])
        self.assertEqual(ocr.extract(b"%PDF", "application/pdf"), "text of p1\n\ntext of p2\n\ntext of p3")

    def test_empty_or_no_text_is_an_error_not_a_guess_and_engine_failure_is_reported(self):
        with self.assertRaises(ValidationFailed):
            TesseractOcr("eng", engine=lambda i, l: "   ").extract(PNG, "image/png")
        with self.assertRaises(ValidationFailed):
            TesseractOcr("eng", engine=lambda i, l: "x").__class__("eng", engine=lambda i, l: "").extract(PNG, "image/png")
        with self.assertRaises(DependencyUnavailable) as cm:
            TesseractOcr("kan", engine=lambda i, l: (_ for _ in ()).throw(RuntimeError("missing kan.traineddata"))).extract(PNG, "image/png")
        self.assertIn("language data", cm.exception.message)

    def test_missing_tesseract_binary_or_package_is_not_configured(self):
        import sys
        from unittest import mock

        with mock.patch.dict(sys.modules, {"pytesseract": None}):  # simulates "package not installed"
            with self.assertRaises(NotConfigured):
                TesseractOcr("eng")

    def test_ollama_vision_ocr_asks_for_verbatim_untranslated_text_and_treats_NO_TEXT_as_empty(self):
        class Client:
            def __init__(self, reply): self.reply, self.calls = reply, []
            def chat(self, model, messages, images=None):
                self.calls.append((model, messages[0]["content"], images))
                return self.reply

        c = Client("नमस्ते अधिसूचना")
        ocr = OllamaVisionOcr(c, "llava", render_pdf=lambda d: [b"a"])
        self.assertEqual(ocr.extract(PNG, "image/png"), "नमस्ते अधिसूचना")
        self.assertIn("Do not translate", c.calls[0][1])
        self.assertEqual(c.calls[0][0], "llava")
        with self.assertRaises(ValidationFailed):
            OllamaVisionOcr(Client("NO_TEXT"), "llava").extract(PNG, "image/png")
        with self.assertRaises(NotConfigured):
            OllamaVisionOcr(c, "")

    def test_build_ocr(self):
        self.assertIsNone(build_ocr("none", languages="eng", ollama_client=None, vision_model=""))
        with self.assertRaises(NotConfigured):
            build_ocr("ollama_vision", languages="eng", ollama_client=None, vision_model="m")
        with self.assertRaises(NotConfigured):
            build_ocr("magic", languages="eng", ollama_client=None, vision_model="")


def _tesseract_available():
    try:
        import pytesseract
        from PIL import Image  # noqa: F401

        pytesseract.get_tesseract_version()
        return "eng" in pytesseract.get_languages()
    except Exception:
        return False


@unittest.skipUnless(_tesseract_available(), "tesseract (with eng data), pytesseract and Pillow are required")
class RealTesseractTests(unittest.TestCase):
    """Runs the REAL Tesseract engine (present in the build sandbox): image, scanned PDF, and document ingestion end to end."""

    @staticmethod
    def _image(text="Road repair budget 2025"):

        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (1000, 200), "white")
        ImageDraw.Draw(img).text((20, 60), text, fill="black", font=ImageFont.load_default(size=40))
        return img

    def test_real_ocr_of_an_image_and_of_an_image_only_pdf(self):
        import io

        img = self._image()
        png, pdf = io.BytesIO(), io.BytesIO()
        img.save(png, "PNG")
        img.save(pdf, "PDF")
        ocr = TesseractOcr("eng")
        self.assertEqual(ocr.extract(png.getvalue(), "image/png"), "Road repair budget 2025")
        self.assertEqual(ocr.extract(pdf.getvalue(), "application/pdf"), "Road repair budget 2025")

    def test_blank_image_is_an_error_and_a_missing_language_pack_is_reported(self):
        import io

        from PIL import Image

        blank = io.BytesIO()
        Image.new("RGB", (400, 100), "white").save(blank, "PNG")
        with self.assertRaises(ValidationFailed):
            TesseractOcr("eng").extract(blank.getvalue(), "image/png")
        import pytesseract

        if "kan" not in pytesseract.get_languages():
            with self.assertRaises(DependencyUnavailable):
                TesseractOcr("kan").extract(blank.getvalue(), "image/png")

    def test_scanned_pdf_document_is_ingested_and_becomes_searchable(self):
        import io

        from app.rag.bm25 import BM25Index
        from app.rag.index import RagIndex
        from app.services.document_service import DocumentIngestor

        env = Env()
        pdf = io.BytesIO()
        self._image("Road repair budget 2025").save(pdf, "PDF")
        index = RagIndex(BM25Index(), None)
        ing = DocumentIngestor(env.uow().documents, env.storage, index, ocr=TesseractOcr("eng"), clock=env.clock)
        doc = ing.upload("cit-1", "scan.pdf", pdf.getvalue(), max_bytes=5_000_000)
        ing.process(doc.id)
        stored = env.stores.documents[doc.id]
        self.assertEqual((str(stored.status), stored.chunk_count > 0), ("ready", True))
        self.assertTrue(index.bm25.search("road repair budget", 3))


class EvidenceFlowTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.c = self.env.create()

    def upload(self, ctx=CIT):
        return self.env.complaints.upload_evidence(ctx, "extra.png", PNG)

    def test_owner_adds_evidence_after_creation_officer_sees_it_and_is_notified(self):
        ev = self.upload()
        self.env.complaints.add_evidence(CIT, self.c.id, ev.id)
        self.assertEqual(self.env.stores.evidence[ev.id].complaint_id, self.c.id)
        e = [x for x in self.env.stores.events[self.c.id] if x.kind == "evidence_added"][0]
        self.assertFalse(e.internal)
        self.assertTrue(any(n.user_id == "off-roads-1" and n.title == "New evidence added" for n in self.env.stores.notifications.values()))
        self.assertIn("evidence.attached", self.env.actions())
        with self.assertRaises(ValidationFailed):
            self.env.complaints.add_evidence(CIT, self.c.id, ev.id)  # already used

    def test_only_the_owner_can_add_and_only_to_unfinished_complaints(self):
        ev = self.upload(CIT2)
        with self.assertRaises(NotFound):
            self.env.complaints.add_evidence(CIT2, self.c.id, ev.id)
        mine = self.upload()
        with self.assertRaises(ValidationFailed):
            self.env.complaints.add_evidence(CIT, self.c.id, ev.id)  # someone else's upload
        for t in (S.UNDER_REVIEW, S.RESOLVED, S.CLOSED):
            self.env.officer.update_status(OFF_R1, self.c.id, t, "x")
        with self.assertRaises(Conflict):
            self.env.complaints.add_evidence(CIT, self.c.id, mine.id)

    def test_read_access_is_owner_or_department_staff_and_every_read_is_audited(self):
        ev = self.upload()
        self.env.complaints.add_evidence(CIT, self.c.id, ev.id)
        for ctx in (CIT, OFF_R1):
            rec, data = self.env.complaints.read_evidence(ctx, ev.id)
            self.assertEqual((rec.id, data), (ev.id, PNG))
        for ctx in (CIT2, OFF_W1):
            with self.assertRaises(NotFound):
                self.env.complaints.read_evidence(ctx, ev.id)
        self.assertEqual(self.env.actions().count("evidence.accessed"), 2)

    def test_reanalysis_without_a_vision_provider_says_so_and_with_one_runs_through_the_queue(self):
        ev = self.upload()
        self.env.complaints.add_evidence(CIT, self.c.id, ev.id)
        self.env.complaints._vision = None  # no vision provider configured
        self.assertEqual(self.env.complaints.request_analysis(CIT, ev.id).analysis_status, "IMAGE_ANALYSIS_UNAVAILABLE")

        class Vision:
            name = "stub"
            def analyze(self, image, mime): return {"summary": "a pothole", "issue_category": "roads", "severity_hint": "high", "visible_text": "", "confidence": 0.8}

        self.env.complaints._vision = Vision()
        w = GrievanceWorker(self.env.factory, self.env.complaints, None, Vision(), self.env.storage, self.env.fx, self.env.notifications)
        self.env.jobs.handlers.update(w.handlers())
        self.assertEqual(self.env.complaints.request_analysis(OFF_R1, ev.id).analysis_status, "PENDING")
        self.env.jobs.drain("w")
        done = self.env.stores.evidence[ev.id]
        self.assertEqual((done.analysis_status, done.analysis_provider, done.analysis_result["summary"]), ("OK", "stub", "a pothole"))
        with self.assertRaises(NotFound):
            self.env.complaints.request_analysis(CIT2, ev.id)
        pdf = self.env.complaints.upload_evidence(CIT, "doc.pdf", b"%PDF-1.4\n%%EOF")
        with self.assertRaises(ValidationFailed):
            self.env.complaints.request_analysis(CIT, pdf.id)


class DeviceRegistrationTests(unittest.TestCase):
    def test_devices_belong_to_one_user_and_validate_input(self):
        env = Env()
        with env.uow() as u:
            env.notifications.register_device(CIT, u, "ExponentPushToken[abc123]", "android")
            u.commit()
        with env.uow() as u:
            env.notifications.register_device(CIT2, u, "ExponentPushToken[abc123]", "ios")  # shared phone: the token moves to the new user
            u.commit()
        self.assertEqual([d.user_id for d in env.stores.push], ["cit-2"])
        for tok, plat in (("short", "android"), ("ExponentPushToken[abc123]", "windows")):
            with self.assertRaises(ValidationFailed):
                with env.uow() as u:
                    env.notifications.register_device(CIT, u, tok, plat)


if __name__ == "__main__":
    unittest.main()
