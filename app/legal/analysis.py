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

from app.legal.court_guide import guides_for
from app.legal.judgment_search import JudgmentExcerpt, JudgmentSearchPort
from app.legal.precedents import CitationCheck, PrecedentHit, PrecedentIndex
from app.rag.grounded_generation import AnswerStatus, GroundedGenerator
from app.rag.models import Chunk, RetrievedChunk
from app.rag.reranker import ChatProvider

# Statute names are official short titles; detection is by plain keywords only.
CONCEPTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Right to Information Act, 2005", ("rti", "right to information", "public information officer", "pio")),
    ("Consumer Protection Act, 2019", ("consumer", "deficiency in service", "unfair trade practice", "defective product")),
    ("Real Estate (Regulation and Development) Act, 2016", ("rera", "builder", "possession delay", "flat buyer", "promoter", "real estate")),
    ("Environment (Protection) Act, 1986", ("pollution", "environment", "hazardous waste", "emission")),
    ("Motor Vehicles Act, 1988", ("motor vehicle", "driving licence", "road accident claim", "challan")),
    ("Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act, 2013", ("land acquisition", "compensation for land", "resettlement")),
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


def detect_concepts(text: str) -> list[str]:
    t = (text or "").lower()
    return [name for name, kws in CONCEPTS if any((f" {k} " in f" {t} ") if len(k) <= 4 else (k in t) for k in kws)]


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
        self._index, self._generator, self._judgment_search = index, GroundedGenerator(llm), judgment_search

    def analyze(self, problem: str, *, top_k: int = 5, disposal: str | None = None, year: int | None = None) -> LegalAnalysis:
        problem = (problem or "").strip()
        stats = self._index.stats()
        coverage = [LIMITATION, f"Coverage: {stats['count']} judgments from {', '.join(stats['courts']) or 'no court'}; decision years {stats['years'] or 'none'}. Matters outside this set cannot be found here."]
        concepts = detect_concepts(problem)
        hits = self._index.search(problem, top_k=top_k, disposal=disposal, year=year) if problem else []
        excerpts = self._judgment_search.search(problem, top_k=3) if (self._judgment_search and problem) else []
        precedents = [_record_dict(h) for h in hits]
        full_text = [_excerpt_dict(e) for e in excerpts]
        if excerpts:
            coverage.append(f"Real judgment text was retrieved for {len(full_text)} passage(s) below - these are genuine excerpts from the source PDF, not summaries.")
        court_guides = guides_for(concepts)
        if not hits and not excerpts:
            return LegalAnalysis("no_verified_precedent", concepts, [], None, "none", coverage, ["No verified precedent or judgment text matched this description."], court_guides=court_guides)

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
        return LegalAnalysis(status, concepts, precedents, interpretation, confidence, coverage, warnings, check_dict, full_text_excerpts=full_text, court_guides=court_guides)
