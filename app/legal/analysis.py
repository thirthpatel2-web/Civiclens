"""Legal Analyzer: evidence-first, with retrieved precedent kept apart from model opinion.

Outputs are labelled by origin:
* ``concepts``    - keyword-detected statute hints (deterministic, not legal advice);
* ``precedents``  - records **retrieved from the verified index** (never model-generated);
* ``interpretation`` - optional model text, shown only if every citation in it verifies
  and it cites the supplied evidence; otherwise it is withheld.
Because the indexed data holds metadata only (see ``precedents.py``), confidence is never
above ``low`` and the response says why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.legal.court_guide import GENERAL_FALLBACK_GUIDE, guides_for
from app.legal.judgment_search import JudgmentExcerpt, JudgmentSearchPort
from app.legal.precedents import CitationCheck, PrecedentHit, PrecedentIndex
from app.rag.grounded_generation import AnswerStatus, GroundedGenerator
from app.rag.models import Chunk, RetrievedChunk
from app.rag.reranker import ChatProvider

# Statute/regulation names are official short titles; detection is by plain keywords only. Note on
# "Consumer Protection Act, 2019" and education: the Supreme Court has held education is NOT a
# "service" a student can sue over as a consumer (Maharshi Dayanand University v. Surjeet Kaur,
# (2010) 11 SCC 159; P.T. Koshy v. Ellen Charitable Trust, (2012) 3 SCC 87) - so a college/university
# fee or exam dispute is deliberately its own concept below, routed to the real, purpose-built
# UGC grievance mechanism instead of being misfiled under consumer law.
CONCEPTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Right to Information Act, 2005", ("rti", "right to information", "public information officer", "pio")),
    ("Consumer Protection Act, 2019", ("consumer", "deficiency in service", "unfair trade practice", "defective product")),
    ("Real Estate (Regulation and Development) Act, 2016", ("rera", "builder", "possession delay", "flat buyer", "promoter", "real estate")),
    ("Environment (Protection) Act, 1986", ("pollution", "environment", "hazardous waste", "emission")),
    ("Motor Vehicles Act, 1988", ("motor vehicle", "driving licence", "road accident claim", "challan")),
    ("Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act, 2013", ("land acquisition", "compensation for land", "resettlement")),
    ("UGC (Redressal of Grievances of Students) Regulations, 2023", ("college fee", "university fee", "school fee", "tuition fee", "hostel fee", "student grievance", "exam grievance", "admission grievance", "scholarship dispute", "college fees", "university fees")),
    ("Code on Wages, 2019", ("salary not paid", "unpaid salary", "salary is not paid", "not paying my salary", "not paying salary", "wages not paid", "salary dispute", "delayed salary", "withheld salary", "employer not paying")),
)
LIMITATION = "The verified citation index contains case metadata only (parties, bench, dates, citations, disposal) and no judgment text by itself; it cannot show what any case held unless real judgment text was separately retrieved and cited below."
NOT_LEGAL_ADVICE = "This is an information aid, not legal advice. Consult a qualified advocate."


@dataclass
class LegalAnalysis:
    status: str
    concepts: list[str]
    precedents: list[dict[str, Any]]
    interpretation: str | None
    confidence: str  # "none" | "low" | "medium"
    bias_and_coverage: list[str]
    warnings: list[str] = field(default_factory=list)
    citations_check: dict[str, list[str]] = field(default_factory=dict)
    disclaimer: str = NOT_LEGAL_ADVICE
    full_text_excerpts: list[dict[str, Any]] = field(default_factory=list)
    court_guides: list[dict[str, Any]] = field(default_factory=list)
    concept_explanations: dict[str, str] = field(default_factory=dict)


def _format_year_span(years: list[int]) -> str:
    """Compress a list of individual years (which can run into the hundreds) into readable ranges,
    e.g. [1950..1959, 1961..2026] -> '1950-1959, 1961-2026' - accurate about gaps, never claims
    continuous coverage where there isn't any, but never spells out every single year either."""
    if not years:
        return "none"
    ys = sorted(set(years))
    spans: list[str] = []
    start = prev = ys[0]
    for y in ys[1:]:
        if y == prev + 1:
            prev = y
            continue
        spans.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = y
    spans.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(spans)


def detect_concepts(text: str) -> list[str]:
    t = (text or "").lower()
    return [name for name, kws in CONCEPTS if any((f" {k} " in f" {t} ") if len(k) <= 4 else (k in t) for k in kws)]


def detect_concepts_with_llm(text: str, llm: ChatProvider | None) -> list[str]:
    """Fallback for when keyword matching finds nothing - natural phrasing varies too much for a
    fixed keyword list to ever fully cover ("I paid fees but they say I haven't" matches no keyword
    literally, even though it is squarely a student-fee grievance). The model picks ONLY from this
    app's own known, human-verified statute/regulation list below - it can never introduce a law this
    app doesn't already have a researched CourtGuide entry for, so this stays as accurate as the
    keyword path, just less brittle about exact wording."""
    if llm is None or not text.strip():
        return []
    import json
    import re

    names = [name for name, _ in CONCEPTS]
    prompt = (
        f'A citizen described this situation: "{text.strip()[:1500]}"\n\n'
        "Which of these laws/regulations, if any, plausibly apply? Pick ONLY from this exact list "
        "(reply with the exact strings, character-for-character unchanged) - never suggest anything "
        "not in this list, even if you think of a better fit:\n" + "\n".join(f"- {n}" for n in names) + "\n\n"
        "Pick only the single best-fitting law/regulation unless more than one is genuinely, "
        "directly applicable - do not pad the list with a weak or indirect fit just because it's "
        "loosely related. Important: Indian courts have held that education is NOT a 'service' a "
        "student can sue over as a 'consumer' (Maharshi Dayanand University v. Surjeet Kaur, (2010) "
        "11 SCC 159; P.T. Koshy v. Ellen Charitable Trust, (2012) 3 SCC 87) - never pick 'Consumer "
        "Protection Act, 2019' for a dispute with a school/college/university (admission, fees, exams, "
        "hostel, etc.); use 'UGC (Redressal of Grievances of Students) Regulations, 2023' for those instead.\n\n"
        'Reply with ONLY a JSON array of the matching name(s), e.g. ["Right to Information Act, 2005"]. '
        "If none plausibly apply, reply with an empty JSON array []."
    )
    try:
        raw = llm.chat([{"role": "user", "content": prompt}], temperature=0.0)
        fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        picked = json.loads(fenced)
        if not isinstance(picked, list):
            return []
        return [p for p in picked if isinstance(p, str) and p in names]
    except Exception:  # noqa: BLE001 - any failure (timeout, bad JSON, provider error) just means no LLM-assisted match
        return []


def _record_dict(hit: PrecedentHit) -> dict[str, Any]:
    r = hit.record
    return {"cnr": r.cnr, "neutralCitation": r.neutral_citation, "reporterCitation": r.reporter_citation, "title": r.title,
            "bench": list(r.judges), "decisionDate": r.decision_date.isoformat(), "disposal": r.disposal, "court": r.court,
            "matchedOn": hit.matched_on, "score": round(hit.score, 3), "origin": "verified index"}  # fmt: skip


def _as_evidence(hits: list[PrecedentHit]) -> list[RetrievedChunk]:
    out = []
    for h in hits:
        r = h.record
        text = (f"Case: {r.title}. Neutral citation {r.neutral_citation}. Reporter citation {r.reporter_citation or 'n/a'}. "
                f"Bench: {', '.join(r.judges) or 'n/a'}. Decided {r.decision_date.isoformat()}. Disposal: {r.disposal or 'not recorded'}. (Metadata only; no judgment text.)")  # fmt: skip
        out.append(RetrievedChunk(Chunk(r.cnr, r.cnr, f"{r.neutral_citation} - {r.title}", text, "precedent_metadata"), found_via=["bm25"], fused_score=h.score, rerank_score=1.0))
    return out


def _excerpt_dict(e: JudgmentExcerpt) -> dict[str, Any]:
    return {"judgmentId": e.judgment_id, "title": e.title, "court": e.court, "neutralCitation": e.neutral_citation,
            "reporterCitation": e.reporter_citation, "decisionDate": e.decision_date.isoformat() if e.decision_date else None,
            "page": e.page, "text": e.text, "similarity": round(e.similarity, 3), "origin": "full text (verified download)"}  # fmt: skip


def _as_full_text_evidence(excerpts: list[JudgmentExcerpt]) -> list[RetrievedChunk]:
    """Unlike ``_as_evidence``, this text is the real, verbatim judgment - the model may describe
    what it actually says, not just what the metadata shows."""
    out = []
    for e in excerpts:
        name = f"{e.neutral_citation or e.judgment_id} - {e.title or 'untitled'}"
        out.append(RetrievedChunk(Chunk(e.judgment_id, e.judgment_id, name, e.text, "legal_judgment", page=e.page), found_via=["semantic"], semantic_similarity=e.similarity, fused_score=e.similarity, rerank_score=1.0))
    return out


def _merged_citation_check(index: PrecedentIndex, excerpts: list[JudgmentExcerpt], answer: str) -> CitationCheck:
    """A citation the metadata index doesn't recognise may still be real: every full-text excerpt was
    downloaded and its citation parsed straight from the judgment PDF this session, so it is just as
    verified as an index hit. Anything neither source recognises is still flagged unverified."""
    base = index.verify_citations(answer)
    known = {c for e in excerpts for c in (e.neutral_citation, e.reporter_citation) if c}
    verified = list(base.verified) + [c for c in base.unverified if c in known]
    unverified = tuple(c for c in base.unverified if c not in known)
    return CitationCheck(tuple(verified), unverified, base.unverifiable)


class LegalAnalysisService:
    def __init__(self, index: PrecedentIndex, llm: ChatProvider | None = None, judgment_search: JudgmentSearchPort | None = None) -> None:
        self._index, self._llm, self._generator, self._judgment_search = index, llm, GroundedGenerator(llm), judgment_search

    def _explain_concept(self, concept: str, problem: str) -> str | None:
        """Best-effort, plain-language 'how does this law generally apply here' - explicitly about the
        named Act's own real mechanics, never a prediction of outcome or an invented fact about this
        citizen's specific case. Degrades to nothing (never an error) if no model is configured or the
        call fails - the static CourtGuide entry is still shown regardless."""
        if self._llm is None or not problem.strip():
            return None
        prompt = (
            f'A citizen described this situation, in their own words: "{problem.strip()[:1500]}"\n\n'
            f'In plain, simple language (3-5 short sentences, no legal jargon), explain how the "{concept}" '
            "generally applies to a situation like this in India - what it covers and what someone in this "
            "position would typically be able to ask for or do under it. Do not invent any fact about THIS "
            "specific situation beyond what was stated above. Do not predict how this particular matter would "
            "be decided or guarantee any result - describe the law's own mechanics, not an outcome."
        )
        try:
            text = self._llm.chat([{"role": "user", "content": prompt}], temperature=0.2).strip()
        except Exception:  # noqa: BLE001 - a model outage/error just means no deep-dive text, not a failed analysis
            return None
        return text or None

    def analyze(self, problem: str, *, top_k: int = 5, disposal: str | None = None, year: int | None = None) -> LegalAnalysis:
        problem = (problem or "").strip()
        stats = self._index.stats()
        coverage = [LIMITATION, f"Coverage: {stats['count']} judgments from {', '.join(stats['courts']) or 'no court'}; decision years {_format_year_span(stats['years'])}. Matters outside this set cannot be found here."]
        concepts = detect_concepts(problem)
        hits = self._index.search(problem, top_k=top_k, disposal=disposal, year=year) if problem else []
        excerpts = self._judgment_search.search(problem, top_k=3) if (self._judgment_search and problem) else []
        precedents = [_record_dict(h) for h in hits]
        full_text = [_excerpt_dict(e) for e in excerpts]
        if excerpts:
            coverage.append(f"Real judgment text was retrieved for {len(full_text)} passage(s) below - these are genuine excerpts from the source PDF, not summaries.")
        if not hits and not excerpts:
            # Nothing else was found either, so no grounded-generator call happens on this branch -
            # the shared ``ChatProvider`` is safe to use for concept detection right away.
            if not concepts and problem:
                concepts = detect_concepts_with_llm(problem, self._llm)
            real_guides = guides_for(concepts)
            concept_explanations = {str(g["concept"]): t for g in real_guides[:2] if (t := self._explain_concept(str(g["concept"]), problem))}
            court_guides = real_guides or ([GENERAL_FALLBACK_GUIDE] if problem else [])
            return LegalAnalysis("no_verified_precedent", concepts, [], None, "none", coverage, ["No verified precedent or judgment text matched this description."], court_guides=court_guides, concept_explanations=concept_explanations)

        gen = self._generator.generate(
            f"Which of these verified records relate to: {problem[:1500]}? For metadata-only records, describe only what the metadata shows. "
            "For judgment-text excerpts, you may describe what the text actually says, quoting or paraphrasing only what is shown.",
            _as_evidence(hits) + _as_full_text_evidence(excerpts), language="English")  # fmt: skip
        warnings = list(gen.warnings)
        interpretation: str | None = None
        check_dict: dict[str, list[str]] = {}
        status = "precedents_only"
        confidence = "low"
        if gen.status is AnswerStatus.ANSWERED and gen.answer:
            check = _merged_citation_check(self._index, excerpts, gen.answer)
            check_dict = {"verified": list(check.verified), "unverified": list(check.unverified), "unverifiable": list(check.unverifiable)}
            if check.unverified or check.unverifiable:
                warnings.append("The model's explanation was withheld because it cited case references that cannot be verified: " + ", ".join(check.unverified + check.unverifiable))
            else:
                interpretation, status = gen.answer, "analysed"
                if any(c.document_type == "legal_judgment" for c in gen.citations):
                    confidence = "medium"  # the grounded, citation-verified answer actually cites real judgment text, not metadata alone
        elif gen.status is AnswerStatus.MODEL_UNAVAILABLE:
            warnings.append("No language model available: showing verified precedent records and any retrieved judgment text only.")
        elif gen.status is AnswerStatus.INSUFFICIENT_EVIDENCE:
            warnings.append("The retrieved records didn't contain enough to describe your situation confidently - showing the verified precedent records and any retrieved judgment text only.")
        elif gen.status is AnswerStatus.UNGROUNDED:
            warnings.append("The model's explanation wasn't clearly tied to the verified records, so it was withheld - showing the verified precedent records and any retrieved judgment text only.")
        elif gen.status is AnswerStatus.ANSWERED and not gen.answer:
            warnings.append("The model returned an empty response - showing the verified precedent records and any retrieved judgment text only.")
        # Deliberately AFTER the grounded generator call above: both share the same ``ChatProvider``,
        # and that citation-verified answer is the one call that must never be pre-empted by another.
        if not concepts and problem:
            concepts = detect_concepts_with_llm(problem, self._llm)
        real_guides = guides_for(concepts)
        concept_explanations = {str(g["concept"]): t for g in real_guides[:2] if (t := self._explain_concept(str(g["concept"]), problem))}
        court_guides = real_guides or ([GENERAL_FALLBACK_GUIDE] if problem else [])
        return LegalAnalysis(status, concepts, precedents, interpretation, confidence, coverage, warnings, check_dict, full_text_excerpts=full_text, court_guides=court_guides, concept_explanations=concept_explanations)
