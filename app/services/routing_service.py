"""Department routing: deterministic rules first, AI only as a recorded fallback.

* Rules are evaluated in ascending ``priority``; the first match wins.
* If no rule matches, the AI/category suggestion is used *only* if it names a real
  department; otherwise the complaint is left ``unrouted`` for manual triage.
* A rule decision is never silently replaced by an AI opinion: when both exist and
  differ, the disagreement is stored on the decision (``ai_disagreement``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.classification_service import SEVERITIES, ClassificationResult


@dataclass(frozen=True)
class RoutingRule:
    id: str
    priority: int
    department_code: str
    service_code: str | None = None
    categories: frozenset[str] = frozenset()
    keywords_any: tuple[str, ...] = ()
    wards: frozenset[str] = frozenset()
    min_severity: str | None = None
    active: bool = True

    def matches(self, cls: ClassificationResult, text: str, ward: str | None) -> bool:
        if not self.active:
            return False
        if self.categories and cls.category not in self.categories:
            return False
        if self.wards and (ward is None or ward not in self.wards):
            return False
        if self.min_severity and SEVERITIES.index(cls.severity) < SEVERITIES.index(self.min_severity):
            return False
        if self.keywords_any:
            t = text.lower()
            if not any(k.lower() in t for k in self.keywords_any):
                return False
        return bool(self.categories or self.wards or self.min_severity or self.keywords_any)  # empty rule matches nothing


@dataclass(frozen=True)
class AiSuggestion:
    department_code: str
    confidence: float
    rationale: str


@dataclass
class RoutingDecision:
    department_code: str | None
    service_code: str | None
    source: str  # "rule" | "ai_fallback" | "unrouted"
    rule_id: str | None
    confidence: float | None
    explanation: str
    ai_disagreement: dict[str, Any] | None = None
    needs_manual_triage: bool = False


@dataclass
class DepartmentRouter:
    rules: list[RoutingRule]
    known_departments: frozenset[str]
    min_ai_confidence: float = 0.5
    _sorted: list[RoutingRule] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._sorted = sorted(self.rules, key=lambda r: (r.priority, r.id))
        bad = [r.id for r in self.rules if r.department_code not in self.known_departments]
        if bad:
            raise ValueError(f"routing rules reference unknown departments: {bad}")

    def route(self, cls: ClassificationResult, text: str, ward: str | None = None, ai: AiSuggestion | None = None) -> RoutingDecision:
        for rule in self._sorted:
            if rule.matches(cls, text, ward):
                disagreement = None
                if ai and ai.department_code != rule.department_code:
                    disagreement = {"ai_department": ai.department_code, "ai_confidence": ai.confidence, "kept": "rule", "reason": "deterministic rules take precedence"}
                return RoutingDecision(rule.department_code, rule.service_code, "rule", rule.id, 1.0, f"Matched routing rule {rule.id} (priority {rule.priority}).", disagreement)
        if ai and ai.department_code in self.known_departments and ai.confidence >= self.min_ai_confidence:
            return RoutingDecision(ai.department_code, None, "ai_fallback", None, ai.confidence, f"No rule matched; AI suggested {ai.department_code}: {ai.rationale}")
        why = "AI suggestion unavailable or below confidence threshold" if ai is None or ai.confidence < self.min_ai_confidence else f"AI suggested unknown department {ai.department_code!r}"
        return RoutingDecision(None, None, "unrouted", None, None, f"No rule matched; {why}. Queued for manual triage.", needs_manual_triage=True)
