"""Deterministic court/forum guidance, keyed to the same statute concepts ``analysis.py`` detects
by keyword. This is general procedural information sourced from the governing statute - which forum
hears the matter, whether an advocate is mandatory, how filing fees are set, and the broad procedural
steps - never a per-case prediction of outcome or a fabricated confidence score.

A specific rupee filing fee is deliberately never stated: fee schedules vary by state, tribunal and
claim value and change over time, so only the fee *basis* is given. Every entry carries the same
"not legal advice" framing as the rest of the Legal Analyzer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CourtGuide:
    forum: str
    advocate_mandatory: str
    fee_basis: str
    steps: tuple[str, ...]


COURT_GUIDES: dict[str, CourtGuide] = {
    "Right to Information Act, 2005": CourtGuide(
        forum="The Public Information Officer (PIO) of the concerned public authority; appeals go to the First Appellate Authority, then the State/Central Information Commission.",
        advocate_mandatory="No - an advocate is not required at any stage of the RTI process.",
        fee_basis="A nominal application fee (commonly around ₹10) plus a per-page charge for copies; applicants below the poverty line are exempt by law.",
        steps=(
            "File a written RTI application with the PIO describing the information sought.",
            "The PIO must respond within 30 days (48 hours if life or liberty is involved).",
            "If unanswered or unsatisfactory, file a first appeal to the First Appellate Authority within 30 days.",
            "If still unresolved, file a second appeal or complaint with the Information Commission.",
        ),
    ),
    "Consumer Protection Act, 2019": CourtGuide(
        forum="District Consumer Disputes Redressal Commission, State Commission or National Commission, depending on the value of goods/services and compensation claimed.",
        advocate_mandatory="No - a consumer may appear in person or through an authorised representative; an advocate is optional.",
        fee_basis="A modest fee, in slabs tied to the claim value, fixed by the Consumer Protection Rules.",
        steps=(
            "Send a written notice to the seller or service provider demanding redress.",
            "If unresolved, file a complaint with the appropriate Consumer Commission with supporting evidence.",
            "The Commission may direct mediation, or proceed to a hearing.",
            "An order can be appealed to the next higher Commission within the statutory period.",
        ),
    ),
    "Real Estate (Regulation and Development) Act, 2016": CourtGuide(
        forum="The State Real Estate Regulatory Authority (RERA); appeals go to that state's Real Estate Appellate Tribunal.",
        advocate_mandatory="No - a complainant may appear in person before RERA; representation is optional.",
        fee_basis="A fixed complaint fee set by the state's RERA rules (amount varies by state).",
        steps=(
            "File a complaint with the state RERA against the promoter, citing the project's RERA registration number.",
            "RERA is statutorily expected to dispose of complaints within about 60 days.",
            "Reliefs can include possession, refund with interest, or compensation.",
            "An aggrieved party may appeal to the Real Estate Appellate Tribunal within 60 days.",
        ),
    ),
    "Environment (Protection) Act, 1986": CourtGuide(
        forum="The National Green Tribunal (NGT), which has original jurisdiction over most environmental matters.",
        advocate_mandatory="No - representation before the NGT is optional, though it is a specialised forum where legal assistance is often useful.",
        fee_basis="A fixed application fee prescribed by the NGT (Practices and Procedure) Rules.",
        steps=(
            "File an application or appeal before the NGT within the limitation period (typically 6 months of the cause of action).",
            "The Tribunal may call for an expert or fact-finding committee report.",
            "Interim relief, such as a stay, can be sought where there is urgency.",
            "Appeals from NGT orders lie to the Supreme Court.",
        ),
    ),
    "Motor Vehicles Act, 1988": CourtGuide(
        forum="The Motor Accident Claims Tribunal (MACT) of the district where the accident occurred, the claimant resides, or the opposite party resides.",
        advocate_mandatory="No - a claimant may file and argue a claim in person, though legal help is common for compensation claims.",
        fee_basis="Compensation claim petitions before the MACT are generally exempt from court fees.",
        steps=(
            "Lodge a First Information Report (FIR) with the police, if not already done.",
            "File a compensation claim petition before the MACT with medical and police records.",
            "The Tribunal may direct the insurer to pay interim compensation.",
            "The final award can be appealed to the High Court.",
        ),
    ),
    "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act, 2013": CourtGuide(
        forum="The Land Acquisition, Rehabilitation and Resettlement Authority notified for the state; further appeal lies to the High Court.",
        advocate_mandatory="No - representation before the Authority is optional.",
        fee_basis="Reference and appeal fees are prescribed under the state's land acquisition rules.",
        steps=(
            "Object to the draft Social Impact Assessment or acquisition notice within the statutory window.",
            "Seek a reference to the Authority if dissatisfied with the compensation award.",
            "The Authority determines fair compensation using the Act's statutory formula.",
            "The award can be further appealed to the High Court.",
        ),
    ),
}


def guides_for(concepts: list[str]) -> list[dict[str, object]]:
    return [
        {"concept": name, "forum": g.forum, "advocateMandatory": g.advocate_mandatory, "feeBasis": g.fee_basis, "steps": list(g.steps)}
        for name in concepts
        if (g := COURT_GUIDES.get(name)) is not None
    ]
