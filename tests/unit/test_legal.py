"""Legal tests use REAL rows sampled from the supplied Parquet file (tests/fixtures)."""

import json
import unittest
from datetime import date
from pathlib import Path

from app.core.exceptions import DependencyUnavailable
from app.legal.analysis import LegalAnalysisService, detect_concepts
from app.legal.judgment_search import JudgmentExcerpt
from app.legal.precedents import (
    PrecedentIndex,
    load_records,
    normalize_neutral,
    normalize_row,
    normalize_scr,
)
from tests.rag.helpers import ScriptedChat

ROWS = json.loads((Path(__file__).parent.parent / "fixtures" / "sc_metadata_sample.json").read_text(encoding="utf-8"))


class FakeJudgmentSearch:
    """TEST DOUBLE: returns a fixed list of excerpts regardless of query, records call count."""

    def __init__(self, excerpts: list[JudgmentExcerpt]) -> None:
        self.excerpts, self.calls = excerpts, 0

    def search(self, query: str, top_k: int = 3) -> list[JudgmentExcerpt]:
        self.calls += 1
        return list(self.excerpts)


VIJAY_SINGH = JudgmentExcerpt(
    judgment_id="sc:2024:2024_10_108_125_EN", title="Vijay Singh @ Vijay Kr. Sharma v. The State of Bihar",
    court="Supreme Court of India", neutral_citation="2024 INSC 735", reporter_citation="[2024] 10 S.C.R. 108",
    decision_date=date(2024, 9, 25), page=17,
    text="The offence of murder is entirely dependent on circumstantial evidence in this case.", similarity=0.79,
)


def eldeco():
    return next(r for r in ROWS if r["cnr"] == "ESCR010008242023")


class NormalizationTests(unittest.TestCase):
    def test_real_row_maps_exactly(self):
        r = normalize_row(eldeco())
        self.assertEqual(r.cnr, "ESCR010008242023")
        self.assertEqual(r.neutral_citation, "2023 INSC 1043")
        self.assertEqual(r.reporter_citation, "[2023] 16 S.C.R. 872")
        self.assertEqual(r.title, "ELDECO HOUSING AND INDUSTRIES LIMITED versus ASHOK VIDYARTHI AND OTHERS")  # whitespace collapsed
        self.assertEqual(r.petitioner, "ELDECO HOUSING AND INDUSTRIES LIMITED")
        self.assertEqual(r.judges, ("VIKRAM NATH",))
        self.assertEqual(r.decision_date, date(2023, 11, 30))
        self.assertEqual(r.disposal, "Appeal(s) allowed")
        self.assertEqual(r.languages, ("ENG", "PUN"))
        self.assertEqual((r.court, r.year), ("Supreme Court of India", 2023))

    def test_multi_judge_bench_split(self):
        row = next(r for r in ROWS if "," in (r["judge"] or ""))
        self.assertGreaterEqual(len(normalize_row(row).judges), 2)

    def test_blank_disposal_becomes_none_not_empty_string(self):
        row = dict(eldeco(), disposal_nature="")
        self.assertIsNone(normalize_row(row).disposal)

    def test_bad_rows_are_rejected_with_reasons(self):
        base = eldeco()
        for patch, why in [({"cnr": None}, "cnr"), ({"title": ""}, "title"), ({"decision_date": "2023/11/30"}, "decision_date"),
                           ({"decision_date": "31-02-2023"}, "decision_date"), ({"case_id": "garbage", "nc_display": ""}, "neutral")]:  # fmt: skip
            with self.assertRaises(ValueError, msg=patch) as cm:
                normalize_row({**base, **patch})
            self.assertIn(why, str(cm.exception))

    def test_citation_normalisers(self):
        self.assertEqual(normalize_neutral("see 2023INSC1043 here"), "2023 INSC 1043")
        self.assertEqual(normalize_neutral("2023 insc 0108"), "2023 INSC 108")
        self.assertEqual(normalize_scr("[2023]  16 SCR 872"), "[2023] 16 S.C.R. 872")
        self.assertIsNone(normalize_neutral("no citation"))

    def test_load_records_dedupes_on_cnr_but_keeps_shared_neutral_citations(self):
        recs, rejects = load_records(ROWS + [eldeco(), {"title": "x"}])
        self.assertEqual(len(recs), len(ROWS))
        self.assertEqual(sorted(r.reason.split()[0] for r in rejects), ["duplicate", "missing"])
        shared = [r for r in recs if r.neutral_citation == "2023 INSC 108"]
        self.assertEqual(len(shared), 4)  # clubbed matters: same neutral citation, distinct cnr
        self.assertEqual(len({r.cnr for r in shared}), 4)


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.index = PrecedentIndex(load_records(ROWS)[0])

    def test_exact_lookups(self):
        self.assertEqual(self.index.get("ESCR010008242023").title.split()[0], "ELDECO")
        self.assertEqual(len(self.index.by_neutral_citation("2023INSC108")), 4)
        self.assertEqual(self.index.by_reporter_citation("[2023] 16 SCR 872").cnr, "ESCR010008242023")
        self.assertIsNone(self.index.by_reporter_citation("[2023] 99 S.C.R. 1"))

    def test_search_by_party_name_and_by_exact_citation(self):
        hits = self.index.search("Eldeco Housing versus Ashok Vidyarthi")
        self.assertEqual(hits[0].record.cnr, "ESCR010008242023")
        self.assertEqual(hits[0].matched_on, "metadata text match")
        exact = self.index.search("please look at 2023 INSC 1043")
        self.assertEqual((exact[0].record.cnr, exact[0].matched_on), ("ESCR010008242023", "exact citation"))

    def test_filters(self):
        allowed = self.index.search("state", top_k=50, disposal="Dismissed")
        self.assertTrue(allowed and all(h.record.disposal == "Dismissed" for h in allowed))
        self.assertEqual(self.index.search("state", year=2019), [])

    def test_stats_state_the_data_limits(self):
        s = self.index.stats()
        self.assertEqual((s["years"], s["courts"], s["has_judgment_text"]), ([2023], ["Supreme Court of India"], False))

    def test_citation_verification_flags_fabrications(self):
        text = "See 2023 INSC 1043 and [2023] 16 S.C.R. 872, also 2023 INSC 99999, (2019) 5 SCC 1 and AIR 2020 SC 44."
        c = self.index.verify_citations(text)
        self.assertEqual(c.verified, ("2023 INSC 1043", "[2023] 16 S.C.R. 872"))
        self.assertEqual(c.unverified, ("2023 INSC 99999",))
        self.assertEqual(len(c.unverifiable), 2)  # SCC/AIR cannot be checked with this data
        self.assertEqual(self.index.verify_citations("no citations here").verified, ())


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.index = PrecedentIndex(load_records(ROWS)[0])
        self.problem = "Dispute between Eldeco Housing and a flat buyer about builder possession delay"

    def test_no_llm_returns_verified_records_and_states_limits(self):
        res = LegalAnalysisService(self.index).analyze(self.problem)
        self.assertEqual((res.status, res.confidence, res.interpretation), ("precedents_only", "low", None))
        self.assertEqual(res.precedents[0]["neutralCitation"], "2023 INSC 1043")
        self.assertTrue(all(p["origin"] == "verified index" for p in res.precedents))
        self.assertIn("Real Estate (Regulation and Development) Act, 2016", res.concepts)
        self.assertTrue(any("no judgment text" in x for x in res.bias_and_coverage))
        self.assertTrue(any("No language model" in w for w in res.warnings))
        self.assertIn("not legal advice", res.disclaimer)

    def test_no_match_says_so_and_invents_nothing(self):
        res = LegalAnalysisService(self.index).analyze("zzzz qqqq unrelated words")
        self.assertEqual((res.status, res.precedents, res.confidence, res.interpretation), ("no_verified_precedent", [], "none", None))
        empty = LegalAnalysisService(PrecedentIndex()).analyze(self.problem)
        self.assertEqual(empty.status, "no_verified_precedent")
        self.assertEqual(LegalAnalysisService(self.index).analyze("   ").status, "no_verified_precedent")

    def test_model_explanation_shown_only_when_citations_verify(self):
        chat = ScriptedChat("The records list Eldeco Housing v Ashok Vidyarthi (2023 INSC 1043), disposed as appeal allowed [E1].")
        res = LegalAnalysisService(self.index, chat).analyze(self.problem)
        self.assertEqual(res.status, "analysed")
        self.assertIn("2023 INSC 1043", res.interpretation)
        self.assertEqual(res.citations_check["unverified"], [])
        system = chat.calls[0][0]["content"]
        self.assertIn("ONLY the evidence", system)

    def test_hallucinated_case_citation_withholds_the_explanation(self):
        chat = ScriptedChat("Held in 2023 INSC 99999 that builders are always liable [E1]. Also (2019) 5 SCC 1 [E1].")
        res = LegalAnalysisService(self.index, chat).analyze(self.problem)
        self.assertEqual(res.status, "precedents_only")
        self.assertIsNone(res.interpretation)
        self.assertEqual(res.citations_check["unverified"], ["2023 INSC 99999"])
        self.assertTrue(any("withheld" in w for w in res.warnings))
        self.assertEqual(res.precedents[0]["neutralCitation"], "2023 INSC 1043")  # verified records still shown

    def test_uncited_model_output_is_withheld(self):
        res = LegalAnalysisService(self.index, ScriptedChat("Builders must always refund.")).analyze(self.problem)
        self.assertIsNone(res.interpretation)
        self.assertEqual(res.status, "precedents_only")

    def test_model_outage_degrades_to_records(self):
        res = LegalAnalysisService(self.index, ScriptedChat(DependencyUnavailable("down"))).analyze(self.problem)
        self.assertEqual((res.status, res.interpretation), ("precedents_only", None))

    def test_prompt_contains_only_index_records(self):
        chat = ScriptedChat("ok [E1]")
        LegalAnalysisService(self.index, chat).analyze(self.problem)
        user = chat.calls[0][1]["content"]
        self.assertIn("2023 INSC 1043", user)
        self.assertIn("Metadata only; no judgment text", user)

    def test_concept_detection_is_keyword_based(self):
        self.assertEqual(detect_concepts("I filed an RTI to the PIO"), ["Right to Information Act, 2005"])
        self.assertEqual(detect_concepts("garbage on the street"), [])
        self.assertEqual(detect_concepts("my print job"), [])  # 'rti'/'pio' are matched as whole words only

    def test_court_guide_is_attached_for_a_detected_concept_and_invents_no_fee_figure(self):
        # The problem text matches the RERA concept via the index-derived precedent, not a keyword,
        # so this also proves the guide is looked up from `concepts`, not from the precedent hits.
        res = LegalAnalysisService(self.index).analyze(self.problem)
        self.assertIn("Real Estate (Regulation and Development) Act, 2016", res.concepts)
        guide = next(g for g in res.court_guides if g["concept"] == "Real Estate (Regulation and Development) Act, 2016")
        self.assertIn("RERA", guide["forum"])
        self.assertEqual(guide["advocateMandatory"][:2], "No")
        self.assertNotRegex(guide["feeBasis"], r"₹\s?\d")  # a specific rupee figure is never invented
        self.assertGreaterEqual(len(guide["steps"]), 3)

    def test_court_guide_is_still_shown_when_the_precedent_index_is_empty(self):
        # Statute guidance is independent of whether the curated precedent index has a matching case.
        res = LegalAnalysisService(PrecedentIndex()).analyze("I filed an RTI to the PIO and got no reply")
        self.assertEqual(res.status, "no_verified_precedent")
        self.assertEqual([g["concept"] for g in res.court_guides], ["Right to Information Act, 2005"])

    def test_no_concept_detected_means_no_court_guide_invented(self):
        res = LegalAnalysisService(self.index).analyze("zzzz qqqq unrelated words")
        self.assertEqual(res.court_guides, [])


class FullTextIntegrationTests(unittest.TestCase):
    """Full-text judgment search is optional (default None -> identical behaviour to AnalysisTests
    above). These cover what changes when it is configured and actually returns real excerpts."""

    def setUp(self):
        self.index = PrecedentIndex(load_records(ROWS)[0])
        self.problem = "murder case relying only on circumstantial evidence"

    def test_excerpt_alone_avoids_no_verified_precedent_even_with_no_metadata_hit(self):
        judgment_search = FakeJudgmentSearch([VIJAY_SINGH])
        res = LegalAnalysisService(PrecedentIndex(), None, judgment_search).analyze(self.problem)
        self.assertEqual(judgment_search.calls, 1)
        self.assertEqual(len(res.full_text_excerpts), 1)
        self.assertEqual(res.full_text_excerpts[0]["neutralCitation"], "2024 INSC 735")
        self.assertNotEqual(res.status, "no_verified_precedent")

    def test_coverage_mentions_real_excerpt_count(self):
        res = LegalAnalysisService(PrecedentIndex(), None, FakeJudgmentSearch([VIJAY_SINGH])).analyze(self.problem)
        self.assertTrue(any("Real judgment text was retrieved for 1 passage" in c for c in res.bias_and_coverage))

    def test_citation_from_full_text_excerpt_is_not_a_metadata_index_citation_but_still_verifies(self):
        # "2024 INSC 735" does not exist in the 2023-only metadata index, so the plain index check
        # alone would call it unverified; the excerpt itself makes it genuinely real.
        self.assertEqual(self.index.verify_citations("See 2024 INSC 735.").verified, ())
        chat = ScriptedChat("Held in 2024 INSC 735 that murder can rest on circumstantial evidence alone [E1].")
        res = LegalAnalysisService(self.index, chat, FakeJudgmentSearch([VIJAY_SINGH])).analyze(self.problem)
        self.assertEqual(res.status, "analysed")
        self.assertEqual(res.citations_check["verified"], ["2024 INSC 735"])
        self.assertEqual(res.citations_check["unverified"], [])

    def test_confidence_is_medium_only_when_the_grounded_answer_actually_cites_judgment_text(self):
        # An empty metadata index guarantees the excerpt is the only evidence (unambiguously [E1]).
        chat = ScriptedChat("Held in 2024 INSC 735 that murder can rest on circumstantial evidence alone [E1].")
        res = LegalAnalysisService(PrecedentIndex(), chat, FakeJudgmentSearch([VIJAY_SINGH])).analyze(self.problem)
        self.assertEqual(res.confidence, "medium")

    def test_confidence_stays_low_when_answer_only_cites_metadata(self):
        chat = ScriptedChat("The records list Eldeco Housing v Ashok Vidyarthi (2023 INSC 1043) [E1].")
        res = LegalAnalysisService(self.index, chat, FakeJudgmentSearch([VIJAY_SINGH])).analyze("Eldeco Housing dispute")
        self.assertEqual(res.confidence, "low")

    def test_unrelated_fabricated_citation_is_still_caught_even_with_full_text_configured(self):
        chat = ScriptedChat("Held in 2099 INSC 1 that this is true [E1].")
        res = LegalAnalysisService(self.index, chat, FakeJudgmentSearch([VIJAY_SINGH])).analyze(self.problem)
        self.assertEqual(res.status, "precedents_only")
        self.assertEqual(res.citations_check["unverified"], ["2099 INSC 1"])

    def test_judgment_search_not_called_for_a_blank_problem(self):
        judgment_search = FakeJudgmentSearch([VIJAY_SINGH])
        LegalAnalysisService(PrecedentIndex(), None, judgment_search).analyze("   ")
        self.assertEqual(judgment_search.calls, 0)

    def test_default_behaviour_is_unchanged_when_judgment_search_is_not_configured(self):
        res = LegalAnalysisService(self.index).analyze("zzzz qqqq unrelated words")
        self.assertEqual(res.full_text_excerpts, [])
        self.assertEqual(res.status, "no_verified_precedent")  # no metadata match, no judgment search configured


if __name__ == "__main__":
    unittest.main()
