import unittest

from app.rag.chunking import ChunkConfig, chunk_document, extract_entities, split_sentences
from app.rag.text import content_terms, identifier_tokens, tokenize


class TokenizerTests(unittest.TestCase):
    def test_latin_identifiers_stay_whole(self):
        self.assertEqual(tokenize("Complaint CR-1042 filed"), ["complaint", "cr-1042", "filed"])

    def test_indic_scripts_are_not_dropped_or_split(self):
        self.assertEqual(tokenize("सड़क पर गड्ढा है"), ["सड़क", "पर", "गड्ढा", "है"])
        self.assertEqual(tokenize("தமிழ் நாடு"), ["தமிழ்", "நாடு"])
        self.assertEqual(tokenize("ಬೆಂಗಳೂರು ರಸ್ತೆ"), ["ಬೆಂಗಳೂರು", "ರಸ್ತೆ"])
        self.assertEqual(tokenize("বাংলা ভাষা"), ["বাংলা", "ভাষা"])
        self.assertEqual(tokenize("తెలుగు భాష"), ["తెలుగు", "భాష"])

    def test_hyphen_only_inside_tokens_and_punctuation_splits(self):
        self.assertEqual(tokenize("a - b, c--d e-"), [])  # all single chars / min length 2
        self.assertEqual(tokenize("well-known; end."), ["well-known", "end"])

    def test_empty(self):
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize(None), [])  # type: ignore[arg-type]

    def test_identifier_tokens_and_content_terms(self):
        self.assertEqual(identifier_tokens("spent on Ward 4291 monorail"), ["4291"])
        self.assertEqual(identifier_tokens("cr-1042 and 2025-26 but not 12"), ["cr-1042", "2025-26"])
        self.assertNotIn("the", content_terms("What is the road budget"))


class SentenceTests(unittest.TestCase):
    def test_abbreviations_and_decimals_do_not_split(self):
        s = split_sentences("See Sec. 4 of the Act. Ward No. 12 has 3.2 km of road. Done.")
        self.assertEqual(len(s), 3)
        self.assertTrue(s[0].endswith("Act."))

    def test_danda_splits_indic_text(self):
        self.assertEqual(len(split_sentences("यह पहला वाक्य है। यह दूसरा वाक्य है। Third one.")), 3)


class EntityTests(unittest.TestCase):
    def test_extracts_civic_identifiers(self):
        e = extract_entities("Complaint CR-1042 for Ward No. 12 cost Rs. 5,00,000 on 12/03/2024; see 2023 INSC 1043")
        self.assertEqual(e["complaintId"], ["CR-1042"])
        self.assertEqual(e["wardNumber"], ["Ward No. 12"])
        self.assertEqual(e["amountInRupees"], ["Rs. 5,00,000"])
        self.assertEqual(e["date"], ["12/03/2024"])
        self.assertEqual(e["neutralCitation"], ["2023 INSC 1043"])


class ChunkingTests(unittest.TestCase):
    TEXT = "1. Roads\n" + " ".join(f"Sentence number {i} about potholes on the main road." for i in range(80)) + \
        "\n\nANNEXURE A\n| ward | amount |\n| 12 | Rs. 5,00,000 |\n| 13 | Rs. 6,00,000 |\n"

    def test_config_validation(self):
        with self.assertRaises(ValueError):
            ChunkConfig(min_tokens=0)
        with self.assertRaises(ValueError):
            ChunkConfig(max_tokens=100, overlap_tokens=100)

    def test_size_bound_headings_and_table_atomicity(self):
        cfg = ChunkConfig(min_tokens=20, max_tokens=120, overlap_tokens=20)
        chunks = chunk_document(self.TEXT, cfg)
        prose = [c for c in chunks if not c.is_table]
        self.assertGreater(len(prose), 3)
        self.assertTrue(all(c.token_estimate <= cfg.max_tokens + cfg.min_tokens for c in prose))
        tables = [c for c in chunks if c.is_table]
        self.assertEqual(len(tables), 1)
        self.assertIn("| 12 |", tables[0].text)
        self.assertIn("| 13 |", tables[0].text)  # not cut in half
        self.assertEqual(prose[0].heading, "1. Roads")
        self.assertEqual([c.index for c in chunks], list(range(len(chunks))))

    def test_no_content_lost_and_overlap_present(self):
        cfg = ChunkConfig(min_tokens=20, max_tokens=120, overlap_tokens=30)
        chunks = [c for c in chunk_document(self.TEXT, cfg) if not c.is_table]
        joined = " ".join(c.text for c in chunks)
        for i in range(80):
            self.assertIn(f"Sentence number {i} ", joined)
        first_tail = chunks[0].text.split(". ")[-1]
        self.assertIn(first_tail.strip(), chunks[1].text)  # overlap carried forward

    def test_oversized_table_is_row_split_with_header_repeated(self):
        rows = "\n".join(f"| {i} | Rs. {i*1000} |" for i in range(200))
        chunks = chunk_document("| ward | amount |\n" + rows, ChunkConfig(min_tokens=10, max_tokens=100, overlap_tokens=10))
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(c.text.startswith("| ward | amount |") for c in chunks))

    def test_pages_are_recorded(self):
        chunks = chunk_document([(1, "First page sentence."), (2, "Second page sentence.")], ChunkConfig(min_tokens=1, max_tokens=6, overlap_tokens=0))
        self.assertEqual([c.page for c in chunks][0], 1)
        self.assertIn(2, [c.page for c in chunks])

    def test_empty_and_indic(self):
        self.assertEqual(chunk_document(""), [])
        c = chunk_document("सड़क पर गड्ढा है। कृपया मरम्मत करें।")
        self.assertEqual(len(c), 1)


if __name__ == "__main__":
    unittest.main()
