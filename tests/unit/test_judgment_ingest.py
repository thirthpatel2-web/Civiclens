"""Tests use a REAL first-page excerpt sampled from a public Supreme Court judgment PDF
(tests/fixtures/sc_judgment_firstpage_sample.txt, downloaded from the public
indian-supreme-court-judgments S3 bucket, CC-BY-4.0), same convention as test_legal.py."""

import unittest
from datetime import date
from pathlib import Path

from app.legal.judgment_ingest import (
    JudgmentSource,
    _guess_title,
    build_chunks,
    extract_judgment_text,
    judgment_id_for,
    parse_decision_date,
)

FIRST_PAGE = (Path(__file__).parent.parent / "fixtures" / "sc_judgment_firstpage_sample.txt").read_text(encoding="utf-8")


class TitleAndDateTests(unittest.TestCase):
    def test_guess_title_from_real_first_page(self):
        self.assertEqual(_guess_title(FIRST_PAGE), "Vijay Singh @ Vijay Kr. Sharma v. The State of Bihar")

    def test_guess_title_returns_none_without_a_v_pattern(self):
        self.assertIsNone(_guess_title("Nothing resembling a case caption here."))

    def test_parse_decision_date_from_real_first_page(self):
        self.assertEqual(parse_decision_date(((1, FIRST_PAGE),)), date(2024, 9, 25))

    def test_parse_decision_date_returns_none_without_a_date_line(self):
        self.assertIsNone(parse_decision_date(((1, "no date here"),)))
        self.assertIsNone(parse_decision_date(()))


class SourceAndIdTests(unittest.TestCase):
    def test_judgment_id_is_deterministic_and_source_prefixed(self):
        src = JudgmentSource("data/pdf/year=2024/english/2024_10_108_125_EN.pdf", 2024, "https://x/2024_10_108_125_EN.pdf")
        self.assertEqual(judgment_id_for(src), "sc:2024:2024_10_108_125_EN")
        self.assertEqual(judgment_id_for(src), judgment_id_for(src))  # re-ingesting the same key is idempotent


class ExtractionTests(unittest.TestCase):
    def test_real_first_page_yields_neutral_and_reporter_citation(self):
        from app.legal.precedents import normalize_neutral, normalize_scr

        self.assertEqual(normalize_neutral(FIRST_PAGE), "2024 INSC 735")
        self.assertEqual(normalize_scr(FIRST_PAGE), "[2024] 10 S.C.R. 108")

    def test_rejects_pdfs_with_no_usable_text(self):
        # A minimal, valid, but blank single-page PDF (no text objects) - pypdf extracts "".
        blank_pdf = (
            b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \n"
            b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n164\n%%EOF"
        )
        with self.assertRaises(ValueError) as cm:
            extract_judgment_text(blank_pdf)
        self.assertIn("no usable extracted text", str(cm.exception))


class ChunkingTests(unittest.TestCase):
    def test_build_chunks_tags_legal_judgment_type_and_stable_ids(self):
        from app.legal.judgment_ingest import JudgmentText

        text = JudgmentText(((1, FIRST_PAGE * 20),), len(FIRST_PAGE) * 20, "2024 INSC 735", "[2024] 10 S.C.R. 108", "Vijay Singh v. The State of Bihar")
        chunks = build_chunks("sc:2024:test", "Vijay Singh v. The State of Bihar", text)
        self.assertTrue(chunks)
        self.assertTrue(all(c.document_type == "legal_judgment" for c in chunks))
        self.assertTrue(all(c.chunk_id.startswith("sc:2024:test:") for c in chunks))
        self.assertEqual([c.chunk_index for c in chunks], list(range(len(chunks))))


if __name__ == "__main__":
    unittest.main()
