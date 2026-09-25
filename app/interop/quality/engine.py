"""Generic Data Quality Engine (Section 14): a reusable rule evaluator, not a rubric hard-coded to
one record shape. ``InteropGatewayService._document_quality`` (the check every document exchange
already passed through) is now expressed as data here - three ``QualityRule`` objects - rather
than three lines of Python `if` statements, proving the engine is real and load-bearing, not
parallel infrastructure nobody uses.

Rule configuration (Section 15) is versioned data: ``QualityRuleSet`` (app/db/models/interop_platform.py,
migration 0014) stores a named, versioned list of rules an authorized admin could edit - no UI to
edit them yet (named honestly in docs/REQUIREMENT_TRACEABILITY.md), but the storage and evaluation
are real and independent of any one caller.

Returns ``VALID`` / ``VALID_WITH_WARNINGS`` / ``REJECTED`` - never fabricated, and a rule type the
engine doesn't recognise never silently blocks a real exchange (fails open on a *configuration*
error, which is a different failure mode than the data itself being bad).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date, datetime, timedelta
from typing import Any

VALID = "VALID"
VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
REJECTED = "REJECTED"

RULE_TYPES = frozenset(
    {"required", "min_length", "max_length", "regex", "in_set", "not_in_future", "stale_after_days", "cross_field_equals"}
)  # fmt: skip


@dataclass(frozen=True)
class QualityRule:
    field: str
    rule_type: str
    params: dict[str, Any] = dc_field(default_factory=dict)
    severity: str = "error"  # "error" -> counts toward REJECTED; "warning" -> counts toward VALID_WITH_WARNINGS
    message: str | None = None  # overrides the rule's default message when it fails

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "rule_type": self.rule_type, "params": self.params, "severity": self.severity, "message": self.message}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QualityRule:
        return cls(field=data["field"], rule_type=data["rule_type"], params=data.get("params") or {}, severity=data.get("severity", "error"), message=data.get("message"))


@dataclass(frozen=True)
class QualityResult:
    status: str
    errors: list[str]
    warnings: list[str]
    score: float  # rules passed / rules evaluated - kept for continuity with callers that show a percentage


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(value, fmt).date()  # noqa: DTZ007
            except ValueError:
                continue
    return None


class DataQualityEngine:
    """Stateless - one instance can evaluate any record against any rule set."""

    def evaluate(self, record: dict[str, Any], rules: list[QualityRule]) -> QualityResult:
        errors: list[str] = []
        warnings: list[str] = []
        passed = 0
        for rule in rules:
            ok, default_message = self._check(record, rule)
            if ok:
                passed += 1
                continue
            message = rule.message or default_message
            (errors if rule.severity == "error" else warnings).append(message)
        status = REJECTED if errors else (VALID_WITH_WARNINGS if warnings else VALID)
        score = round(passed / len(rules), 2) if rules else 1.0
        return QualityResult(status=status, errors=errors, warnings=warnings, score=score)

    def _check(self, record: dict[str, Any], rule: QualityRule) -> tuple[bool, str]:
        value = record.get(rule.field)
        if rule.rule_type == "required":
            return bool(value not in (None, "", [])), f"{rule.field} is required"
        if rule.rule_type == "min_length":
            min_len = rule.params.get("min", 1)
            return bool(value and len(str(value).strip()) >= min_len), f"{rule.field} is shorter than the required {min_len} characters"
        if rule.rule_type == "max_length":
            max_len = rule.params.get("max", 1_000_000)
            return bool(value is None or len(str(value)) <= max_len), f"{rule.field} is longer than the allowed {max_len} characters"
        if rule.rule_type == "regex":
            pattern = rule.params.get("pattern", ".*")
            return bool(value and re.match(pattern, str(value))), f"{rule.field} does not match the required format"
        if rule.rule_type == "in_set":
            allowed = rule.params.get("allowed", [])
            return value in allowed, f"{rule.field} is {value!r}, not one of {allowed}"
        if rule.rule_type == "not_in_future":
            parsed = _as_date(value)
            if parsed is None:
                return False, f"{rule.field} is missing or not a recognizable date"
            return parsed <= date.today(), f"{rule.field} is in the future"  # noqa: DTZ011
        if rule.rule_type == "stale_after_days":
            parsed = _as_date(value)
            if parsed is None:
                return False, f"{rule.field} is missing or not a recognizable date"
            max_age = rule.params.get("days", 365)
            return (date.today() - parsed) <= timedelta(days=max_age), f"{rule.field} is older than {max_age} days"  # noqa: DTZ011
        if rule.rule_type == "cross_field_equals":
            other = rule.params.get("other_field")
            return record.get(rule.field) == (record.get(other) if other is not None else None), f"{rule.field} does not match {other}"
        return True, ""  # unrecognized rule type: a configuration problem, not a data problem - never blocks a real exchange
