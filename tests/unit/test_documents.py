import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.core.authorization import AuthContext, Role
from app.core.exceptions import NotConfigured, ValidationFailed
from app.rag.bm25 import BM25Index
from app.rag.hybrid_retrieval import HybridRetriever
from app.rag.index import RagIndex
from app.rag.rag_service import RagService
from app.rag.grounded_generation import GroundedGenerator
from app.rag.query_router import QueryRegistry
from app.rag.vector_search import InMemoryVectorIndex
from app.services.document_service import (
    DocumentIngestor, DocumentStatus, LocalStorage, document_access_filter, extract_pages, safe_filename, validate_upload,
)
from app.services.rti_service import render_pdf
from tests.rag.helpers import DIM, HashingEmbedder, ScriptedChat

MAX = 1024 * 1024
BUDGET = ("1. Road Repair Allocation\nThe Roads Department has allocated Rs. 5,00,000 for road repair and pothole filling in Ward 12 during 2025-26.\n\n"
          "2. Drainage\nStormwater drain desilting in Ward 14 is scheduled before the monsoon.")  # fmt: skip


def make_docx(text):
    body = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.split("\n"))
    xml = f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


class Repo:
    def __init__(self): self.rows = {}
    def add(self, d): self.rows[d.id] = d
    def get(self, i): return self.rows.get(i)
    def update(self, d): self.rows[d.id] = d


class ValidationTests(unittest.TestCase):
    def test_safe_filename(self):
        self.assertEqual(safe_filename("../../etc/passwd"), "passwd")
        self.assertEqual(safe_filename("C:\\Users\\a\\my report (final).PDF"), "my_report_final.PDF")
        self.assertEqual(safe_filename("..."), "file")
        self.assertEqual(safe_filename("noext"), "noext")
        self.assertEqual(safe_filename("a.tar.gz"), "a.tar.gz")
        validate_upload("सड़क.pdf", b"%PDF-1.4 x", max_bytes=MAX)
        self.assertEqual(safe_filename("सड़क.pdf"), "file.pdf")
        self.assertLessEqual(len(safe_filename("a" * 500 + ".pdf")), 90)

    def test_rejects_bad_type_empty_oversize_and_spoofed_content(self):
        with self.assertRaises(ValidationFailed):
            validate_upload("evil.exe", b"MZ...", max_bytes=MAX)
        with self.assertRaises(ValidationFailed):
            validate_upload("a.pdf", b"", max_bytes=MAX)
        with self.assertRaises(ValidationFailed):
            validate_upload("a.pdf", b"%PDF-1.4" + b"x" * 100, max_bytes=50)
        for name, data in [("a.pdf", b"<html>not a pdf</html>"), ("a.png", b"%PDF-1.4"), ("a.jpg", b"GIF89a"), ("a.docx", b"PK\x03\x04junk"),
                           ("a.txt", b"bin\x00ary"), ("a.txt", b"\xff\xfe\xfa")]:  # fmt: skip
            with self.assertRaises(ValidationFailed, msg=name):
                validate_upload(name, data, max_bytes=MAX)
        with self.assertRaises(ValidationFailed):
            validate_upload("a.txt", b"hello", max_bytes=MAX, declared_mime="application/pdf")

    def test_accepts_valid_files_and_generates_server_side_name(self):
        for name, data in [("n.txt", "नमस्ते".encode()), ("d.docx", make_docx("hi")), ("p.png", b"\x89PNG\r\n\x1a\n" + b"x" * 20), ("p.JPG", b"\xff\xd8\xff\xe0" + b"x" * 20)]:
            v = validate_upload(name, data, max_bytes=MAX)
            self.assertRegex(v.storage_name, r"^[0-9a-f]{32}\.[a-z]+$")
            self.assertEqual(len(v.sha256), 64)
        self.assertNotEqual(validate_upload("a.txt", b"x", max_bytes=MAX).storage_name, validate_upload("a.txt", b"x", max_bytes=MAX).storage_name)


class StorageTests(unittest.TestCase):
    def test_round_trip_permissions_and_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            st = LocalStorage(d)
            name = "a" * 32 + ".txt"
            st.save(name, b"data")
            self.assertEqual(st.read(name), b"data")
            if sys.platform != "win32":  # Windows has no POSIX permission bits: chmod(0o600) only toggles read-only there
                self.assertEqual(oct((Path(d) / name).stat().st_mode & 0o777), "0o600")
            with self.assertRaises(ValidationFailed):
                st.save(name, b"again")
            for bad in ("../x.txt", "/etc/passwd", "abc.txt", "a" * 32 + "/../b.txt"):
                with self.assertRaises(ValidationFailed, msg=bad):
                    st.read(bad)
            st.delete(name)
            self.assertFalse((Path(d) / name).exists())


class ExtractionTests(unittest.TestCase):
    def test_txt_docx_pdf(self):
        self.assertEqual(extract_pages("text/plain", "सड़क".encode(), None), [(None, "सड़क")])
        docx = extract_pages("application/vnd.openxmlformats-officedocument.wordprocessingml.document", make_docx("Line one\nLine two"), None)
        self.assertEqual(docx[0][1], "Line one\nLine two")
        pdf = render_pdf("Page text about road repair", title="t")
        pages = extract_pages("application/pdf", pdf, None)
        self.assertIn("road repair", pages[0][1])
        self.assertEqual(pages[0][0], 1)

    def test_images_and_scanned_pdf_need_ocr_and_say_so(self):
        with self.assertRaises(NotConfigured):
            extract_pages("image/png", b"\x89PNG", None)
        blank = render_pdf("", title="t")
        with self.assertRaises(NotConfigured):
            extract_pages("application/pdf", blank, None)

    def test_ocr_provider_used_when_configured(self):
        class Ocr:
            def extract(self, data, mime): return "recognised text"
        self.assertEqual(extract_pages("image/png", b"x", Ocr()), [(None, "recognised text")])

    def test_corrupt_pdf_is_a_validation_error(self):
        with self.assertRaises(ValidationFailed):
            extract_pages("application/pdf", b"%PDF-1.4 garbage", None)


class IngestionTests(unittest.TestCase):
    def build(self, embedder="default", ocr=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        emb = HashingEmbedder() if embedder == "default" else embedder
        self.index = RagIndex(BM25Index(), InMemoryVectorIndex(DIM))
        self.repo = Repo()
        self.ing = DocumentIngestor(self.repo, LocalStorage(self.tmp.name), self.index, embedder=emb, ocr=ocr)
        return self.ing

    def test_upload_process_ready_and_searchable_end_to_end(self):
        ing = self.build()
        doc = ing.upload("citizen-1", "budget.txt", BUDGET.encode(), max_bytes=MAX)
        self.assertEqual(doc.status, DocumentStatus.UPLOADED)
        self.assertEqual(len(self.index), 0)  # not searchable before processing
        doc = ing.process(doc.id)
        self.assertEqual((doc.status, doc.error, doc.semantic_indexed), (DocumentStatus.READY, None, True))
        self.assertGreater(doc.chunk_count, 0)
        self.assertEqual(len(self.index), doc.chunk_count)
        retr = HybridRetriever(self.index.chunks, self.index.bm25, self.index.vectors, HashingEmbedder())
        chat = ScriptedChat("Rs. 5,00,000 allocated for Ward 12 [E1].")
        svc = RagService(retr, GroundedGenerator(chat), QueryRegistry(), access_filter=document_access_filter)
        mine = svc.ask("What is allocated for road repair in Ward 12?", AuthContext("citizen-1", Role.CITIZEN))
        self.assertEqual(mine.status, "answered")
        self.assertEqual(mine.citations[0]["documentName"], "budget.txt")
        other = svc.ask("What is allocated for road repair in Ward 12?", AuthContext("citizen-2", Role.CITIZEN))
        self.assertTrue(other.insufficient_evidence)  # private document invisible to others

    def test_failure_marks_failed_with_reason_cleans_index_and_allows_retry(self):
        emb = HashingEmbedder(fail=True)
        ing = self.build(embedder=emb)
        doc = ing.upload("c", "budget.txt", BUDGET.encode(), max_bytes=MAX)
        doc = ing.process(doc.id)
        self.assertEqual(doc.status, DocumentStatus.FAILED)
        self.assertIn("unreachable", doc.error)
        self.assertEqual((len(self.index), len(self.index.bm25), len(self.index.vectors)), (0, 0, 0))
        emb.fail = False
        doc = ing.retry(doc.id)
        self.assertEqual((doc.status, doc.attempts), (DocumentStatus.READY, 2))
        self.assertGreater(len(self.index), 0)

    def test_retry_only_for_failed_and_bounded(self):
        emb = HashingEmbedder(fail=True)
        ing = self.build(embedder=emb)
        doc = ing.upload("c", "b.txt", BUDGET.encode(), max_bytes=MAX)
        for _ in range(3):
            ing.process(doc.id) if self.repo.get(doc.id).status is DocumentStatus.UPLOADED else ing.retry(doc.id)
        with self.assertRaises(ValidationFailed):
            ing.retry(doc.id)
        ok = self.build()
        d2 = ok.upload("c", "b.txt", BUDGET.encode(), max_bytes=MAX)
        ok.process(d2.id)
        with self.assertRaises(ValidationFailed):
            ok.retry(d2.id)

    def test_no_embedder_is_keyword_only_and_recorded(self):
        ing = self.build(embedder=None)
        doc = ing.process(ing.upload("c", "b.txt", BUDGET.encode(), max_bytes=MAX).id)
        self.assertEqual((doc.status, doc.semantic_indexed), (DocumentStatus.READY, False))
        self.assertEqual(len(self.index.vectors), 0)
        self.assertGreater(len(self.index.bm25), 0)

    def test_image_without_ocr_fails_honestly_never_ready(self):
        ing = self.build()
        doc = ing.process(ing.upload("c", "scan.png", b"\x89PNG\r\n\x1a\n" + b"x" * 50, max_bytes=MAX).id)
        self.assertEqual(doc.status, DocumentStatus.FAILED)
        self.assertIn("OCR", doc.error)
        self.assertEqual(len(self.index), 0)

    def test_reprocessing_is_idempotent(self):
        ing = self.build()
        doc = ing.process(ing.upload("c", "b.txt", BUDGET.encode(), max_bytes=MAX).id)
        n = len(self.index)
        doc.status = DocumentStatus.FAILED
        self.repo.update(doc)
        ing.process(doc.id)
        self.assertEqual(len(self.index), n)  # no duplicate chunks

    def test_visibility_rules(self):
        ing = self.build()
        for vis, dept in [("private", None), ("department", "roads"), ("public", None)]:
            doc = ing.process(ing.upload("owner", f"{vis}.txt", BUDGET.encode(), max_bytes=MAX, visibility=vis, department_id=dept).id)
        chunks = {c.metadata["visibility"]: c for c in self.index.chunks.values()}
        owner, other = AuthContext("owner", Role.CITIZEN), AuthContext("x", Role.CITIZEN)
        officer_r, officer_w = AuthContext("o1", Role.OFFICER, "roads"), AuthContext("o2", Role.OFFICER, "water")
        self.assertTrue(all(document_access_filter(owner, chunks[v]) for v in chunks))
        self.assertEqual([document_access_filter(other, chunks[v]) for v in ("private", "department", "public")], [False, False, True])
        self.assertEqual([document_access_filter(officer_r, chunks[v]) for v in ("private", "department", "public")], [False, True, True])
        self.assertFalse(document_access_filter(officer_w, chunks["department"]))
        with self.assertRaises(ValidationFailed):
            ing.upload("o", "x.txt", b"hi", max_bytes=MAX, visibility="everyone")


if __name__ == "__main__":
    unittest.main()
