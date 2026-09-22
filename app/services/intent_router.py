"""Which screen does this sentence belong to?

``ClassificationService`` answers "what *kind of civic problem* is this" (roads, water, ...). It
cannot answer "does this person want to file an RTI, look up a court precedent, or check the status
of something they already filed" - those are different destinations, not different categories.

This router fills that gap with an explicit keyword table per destination. It is deliberately
rules-only and fully inspectable: every result carries the terms that matched, so the interface can
show *why* it is sending someone somewhere and the person can override it. When nothing matches it
returns ``complaint`` with confidence 0.0 and says so, rather than guessing a destination.

Keyword coverage is English + Devanagari (Hindi/Marathi) + the scripts whose terms are unambiguous.
Anything else falls through to ``complaint``, where the civic classifier takes over.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# destination -> terms. Order matters only for tie-breaking (earlier wins), which is why the
# narrow, high-signal destinations are listed before the broad ones.
INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "emergency": ("emergency", "ambulance", "fire brigade", "helpline", "urgent help", "call police", "आपातकाल", "एम्बुलेंस", "अग्निशमन", "हेल्पलाइन", "आणीबाणी", "रुग्णवाहिका", "অ্যাম্বুলেন্স", "அவசர", "అత్యవసర", "ತುರ್ತು"),
    "rti": ("rti", "right to information", "information act", "section 6(1)", "section 6", "section 7", "first appeal", "pio", "spio", "public information officer", "सूचना का अधिकार", "सूचना अधिकार", "आरटीआई", "जन सूचना अधिकारी", "माहितीचा अधिकार", "माहिती अधिकार", "তথ্য অধিকার", "தகவல் அறியும் உரிமை", "సమాచార హక్కు", "ಮಾಹಿತಿ ಹಕ್ಕು"),
    "legal": ("court", "high court", "supreme court", "judgment", "judgement", "case law", "precedent", "petition", "writ", "appeal against", "legal notice", "advocate", "lawyer", "अदालत", "न्यायालय", "याचिका", "फैसला", "वकील", "कानूनी नोटिस", "खटला", "निकाल", "আদালত", "நீதிமன்றம்", "న్యాయస్థానం", "ನ್ಯಾಯಾಲಯ"),
    "track": ("status of", "track my", "what happened to", "follow up", "reference number", "complaint id", "my complaint", "already filed", "स्थिति", "ट्रैक", "शिकायत संख्या", "पहले दर्ज", "स्थिती", "तक्रार क्रमांक", "ট্র্যাক", "நிலை", "స్థితి", "ಸ್ಥಿತಿ"),
    "document": ("scan this", "scan a", "scan the", "upload document", "read this notice", "this notice says", "receipt", "challan", "ocr", "दस्तावेज़", "स्कैन", "रसीद", "चालान", "नोटिस", "कागदपत्र", "पावती", "নথি", "ஆவணம்", "పత్రం", "ದಾಖಲೆ"),
    "map": ("heatmap", "hotspot", "on the map", "near me", "nearby", "in my area", "which areas", "नक्शा", "मानचित्र", "मेरे पास", "आसपास", "नकाशा", "जवळ", "মানচিত্র", "வரைபடம்", "మ్యాప్", "ನಕ್ಷೆ"),
    "locator": ("nearest office", "office address", "which office", "ward office", "department office", "where do i go", "कार्यालय", "दफ्तर", "वार्ड कार्यालय", "कुठे जायचे", "অফিস", "அலுவலகம்", "కార్యాలయం", "ಕಚೇರಿ"),
}

DESTINATIONS = (*INTENT_KEYWORDS, "complaint")


@dataclass
class IntentResult:
    destination: str
    confidence: float
    matched: list[str] = field(default_factory=list)
    explanation: str = ""

    @property
    def certain(self) -> bool:
        """True when exactly one destination matched. Ambiguous text still routes somewhere, but
        the interface should show the alternatives rather than move the person automatically."""
        return self.confidence >= 0.6


class IntentRouter:
    def route(self, text: str) -> IntentResult:
        text_l = (text or "").strip().lower()
        if not text_l:
            return IntentResult("complaint", 0.0, [], "Nothing typed yet.")
        hits: dict[str, list[str]] = {}
        for dest, terms in INTENT_KEYWORDS.items():
            matched = sorted({t for t in terms if t in text_l})
            if matched:
                hits[dest] = matched
        if not hits:
            return IntentResult("complaint", 0.0, [], "No destination keyword matched, so this is treated as a civic complaint.")
        ranked = sorted(hits.items(), key=lambda kv: (-len(kv[1]), list(INTENT_KEYWORDS).index(kv[0])))
        top, top_terms = ranked[0]
        runner_up = len(ranked[1][1]) if len(ranked) > 1 else 0
        # Confidence is the share of matches the winner holds, so two equally-matched destinations
        # can never present as certain.
        total = sum(len(v) for v in hits.values())
        confidence = round(len(top_terms) / total, 2)
        if runner_up == len(top_terms):
            confidence = min(confidence, 0.5)
        return IntentResult(top, confidence, top_terms, f"Matched {', '.join(top_terms)}.")

    def alternatives(self, text: str) -> list[str]:
        """Other destinations whose keywords also appear - shown as one-tap corrections."""
        text_l = (text or "").strip().lower()
        best = self.route(text_l).destination
        return [d for d, terms in INTENT_KEYWORDS.items() if d != best and any(t in text_l for t in terms)]
