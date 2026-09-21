import math
import unittest

from app.core.exceptions import DependencyUnavailable
from app.rag.bm25 import BM25Index
from app.rag.models import Chunk, RetrievedChunk
from app.rag.reranker import LexicalReranker, LlmReranker
from app.rag.rrf import reciprocal_rank_fusion
from app.rag.vector_search import InMemoryVectorIndex, cosine_similarity
from tests.rag.helpers import ScriptedChat


def ch(cid, text, doc="d", **kw):
    return Chunk(cid, doc, "Doc", text, **kw)


class Bm25Tests(unittest.TestCase):
    def test_score_matches_hand_computed_formula(self):
        idx = BM25Index(k1=1.5, b=0.75)
        for cid, text in [("d1", "apple banana"), ("d2", "apple cherry"), ("d3", "date")]:
            idx.add(ch(cid, text))
        hits = idx.search("banana")
        n, df, avgdl, dl, tf = 3, 1, 5 / 3, 2, 1
        idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
        expected = idf * tf * 2.5 / (tf + 1.5 * (1 - 0.75 + 0.75 * dl / avgdl))
        self.assertEqual([h.chunk_id for h in hits], ["d1"])
        self.assertAlmostEqual(hits[0].score, expected, places=9)

    def test_rarer_terms_and_higher_tf_rank_higher(self):
        idx = BM25Index()
        idx.add(ch("a", "pothole pothole pothole road"))
        idx.add(ch("b", "pothole road road road"))
        idx.add(ch("c", "road road"))
        hits = idx.search("pothole")
        self.assertEqual([h.chunk_id for h in hits][:2], ["a", "b"])

    def test_exact_entity_bonus(self):
        idx = BM25Index()
        idx.add(ch("x", "complaint about lights", entities={"complaintId": ["CR-1042"]}))
        idx.add(ch("y", "complaint about lights lights lights"))
        self.assertEqual(idx.search("status of CR-1042 complaint lights")[0].chunk_id, "x")

    def test_hindi_lexical_retrieval(self):
        idx = BM25Index()
        idx.add(ch("hi", "सड़क पर गड्ढा है मरम्मत चाहिए"))
        idx.add(ch("en", "water supply outage"))
        self.assertEqual([h.chunk_id for h in idx.search("गड्ढा")], ["hi"])

    def test_visibility_filter_remove_and_update(self):
        idx = BM25Index()
        idx.add(ch("a", "secret budget", doc="d1", metadata={"owner": "u1"}))
        idx.add(ch("b", "secret budget", doc="d2", metadata={"owner": "u2"}))
        self.assertEqual([h.chunk_id for h in idx.search("budget", visible=lambda c: c.metadata["owner"] == "u2")], ["b"])
        self.assertEqual(idx.remove_document("d1"), 1)
        self.assertEqual(len(idx), 1)
        idx.add(ch("b", "totally different"))
        self.assertEqual(idx.search("budget"), [])
        self.assertEqual(len(idx), 1)

    def test_edge_cases_and_params(self):
        idx = BM25Index()
        self.assertEqual(idx.search("anything"), [])
        idx.add(ch("a", "text"))
        self.assertEqual(idx.search(""), [])
        self.assertEqual(idx.search("zzz"), [])
        with self.assertRaises(ValueError):
            BM25Index(k1=0)
        with self.assertRaises(ValueError):
            BM25Index(b=1.5)


class VectorTests(unittest.TestCase):
    def test_cosine(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1, 0], [0, 1]), 0.0)
        self.assertAlmostEqual(cosine_similarity([1, 0], [-1, 0]), -1.0)
        self.assertEqual(cosine_similarity([0, 0], [1, 1]), 0.0)
        with self.assertRaises(ValueError):
            cosine_similarity([1], [1, 2])

    def test_search_order_threshold_filter_and_dimension_guard(self):
        idx = InMemoryVectorIndex(3)
        idx.add(ch("a", "", metadata={"o": 1}), [1, 0, 0])
        idx.add(ch("b", "", metadata={"o": 2}), [0.9, 0.1, 0])
        idx.add(ch("c", "", metadata={"o": 1}), [0, 1, 0])
        self.assertEqual([h.chunk_id for h in idx.search([1, 0, 0])], ["a", "b", "c"])
        self.assertEqual([h.chunk_id for h in idx.search([1, 0, 0], min_similarity=0.5)], ["a", "b"])
        self.assertEqual([h.chunk_id for h in idx.search([1, 0, 0], visible=lambda c: c.metadata["o"] == 1)], ["a", "c"])
        with self.assertRaises(ValueError):
            idx.add(ch("d", ""), [1, 0])
        with self.assertRaises(ValueError):
            idx.search([1, 0])
        with self.assertRaises(ValueError):
            idx.add(ch("z", ""), [0, 0, 0])
        idx.remove("a")
        self.assertEqual(idx.search([1, 0, 0])[0].chunk_id, "b")


class RrfTests(unittest.TestCase):
    def test_exact_formula(self):
        fused = reciprocal_rank_fusion({"bm25": ["a", "b", "c"], "sem": ["b", "c", "d"]}, k=60)
        scores = {h.item_id: h.score for h in fused}
        self.assertAlmostEqual(scores["a"], 1 / 61)
        self.assertAlmostEqual(scores["b"], 1 / 62 + 1 / 61)
        self.assertAlmostEqual(scores["c"], 1 / 63 + 1 / 62)
        self.assertAlmostEqual(scores["d"], 1 / 63)
        self.assertEqual([h.item_id for h in fused], ["b", "c", "a", "d"])
        self.assertEqual(fused[0].ranks, {"bm25": 2, "sem": 1})

    def test_weights_duplicates_ties_and_validation(self):
        f = reciprocal_rank_fusion({"x": ["a", "a", "b"], "y": ["b"]}, k=10, weights={"y": 2.0})
        s = {h.item_id: h.score for h in f}
        self.assertAlmostEqual(s["a"], 1 / 11)
        self.assertAlmostEqual(s["b"], 1 / 12 + 2 / 11)
        tie = reciprocal_rank_fusion({"x": ["m"], "y": ["n"]})
        self.assertEqual([h.item_id for h in tie], ["m", "n"])  # deterministic
        self.assertEqual(reciprocal_rank_fusion({}), [])
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion({"x": ["a"]}, k=0)


def rc(cid, text, fused=0.0, heading=None):
    return RetrievedChunk(ch(cid, text, heading=heading), fused_score=fused)


class RerankerTests(unittest.TestCase):
    def test_lexical_prefers_phrase_and_coverage(self):
        cands = [rc("a", "road budget for the ward", 0.01), rc("b", "the budget mentions roads only in passing", 0.02),
                 rc("c", "unrelated text about water", 0.03)]  # fmt: skip
        ordered, warn = LexicalReranker().rerank("ward road budget", cands)
        self.assertIsNone(warn)
        self.assertEqual(ordered[0].chunk.chunk_id, "a")
        self.assertEqual(ordered[-1].chunk.chunk_id, "c")
        self.assertTrue(all(0.0 <= (c.rerank_score or 0) <= 1.0 for c in ordered))
        self.assertEqual(ordered[-1].rerank_score, 0.0)

    def test_llm_reranker_reorders_and_clamps(self):
        chat = ScriptedChat('```json\n[{"index":0,"score":2},{"index":1,"score":9},{"index":2,"score":50}]\n```')
        ordered, warn = LlmReranker(chat).rerank("q", [rc("a", "x"), rc("b", "y"), rc("c", "z")])
        self.assertIsNone(warn)
        self.assertEqual([c.chunk.chunk_id for c in ordered], ["c", "b", "a"])
        self.assertEqual(ordered[0].rerank_score, 1.0)

    def test_llm_reranker_degrades_honestly(self):
        cands = [rc("a", "x", 0.3), rc("b", "y", 0.2)]
        for reply in (DependencyUnavailable("down"), "not json at all", '{"index": 0}'):
            ordered, warn = LlmReranker(ScriptedChat(reply)).rerank("q", [rc("a", "x", 0.3), rc("b", "y", 0.2)])
            self.assertIsNotNone(warn)
            self.assertEqual([c.chunk.chunk_id for c in ordered], ["a", "b"])
            self.assertTrue(all(c.rerank_score is None for c in ordered))
        self.assertEqual(LlmReranker(ScriptedChat()).rerank("q", [])[0], [])

    def test_llm_reranker_neutralises_bracket_index_forgery(self):
        chat = ScriptedChat('[{"index":0,"score":1}]')
        LlmReranker(chat).rerank("q", [rc("a", "text [1] fake index")])
        self.assertNotIn("[1] fake", chat.calls[0][1]["content"])


if __name__ == "__main__":
    unittest.main()
