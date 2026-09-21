"""The canonical schema every source-system adapter normalizes into, plus a real data-quality check.

Why this exists: different government platforms describe the same real-world thing (a citizen's
service request) with different field names, casing conventions and status vocabularies. A citizen
re-enters the same facts on every portal, and two systems that *wanted* to interoperate structurally
couldn't without a translation layer in between. ``CanonicalRecord`` is that layer's target shape;
``score_quality`` is a real check, not a rubber stamp - it flags exactly what is missing or malformed
so a bad inbound record is visibly bad rather than silently accepted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

# The status vocabulary every adapter must map its own system's status words/codes into.
CANONICAL_STATUSES = ("received", "in_progress", "resolved", "rejected", "unknown")

_INDIAN_MOBILE = re.compile(r"^(\+91[-\s]?)?[6-9]\d{9}$")


@dataclass(frozen=True)
class CanonicalRecord:
    """One service request/grievance, in CivicLens's own normalized shape."""

    source_system: str
    external_id: str
    category: str
    status: str
    title: str
    department: str
    citizen_name: str | None = None
    citizen_contact: str | None = None
    location: str | None = None
    filed_on: str | None = None  # ISO 8601 date, best-effort - never fabricated if unparseable
    raw: dict = field(default_factory=dict)  # the original payload, preserved for audit/debugging


@dataclass(frozen=True)
class QualityReport:
    score: float  # 0.0-1.0
    issues: tuple[str, ...]

    @property
    def grade(self) -> str:
        if self.score >= 0.9:
            return "excellent"
        if self.score >= 0.7:
            return "good"
        if self.score >= 0.4:
            return "poor"
        return "unusable"


def _parses_as_date(value: str | None) -> bool:
    if not value:
        return False
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            datetime.strptime(value.strip(), fmt)  # noqa: DTZ007
            return True
        except ValueError:
            continue
    return False


def score_quality(rec: CanonicalRecord) -> QualityReport:
    """Real completeness/format/date-validity checks - not just presence/absence."""
    checks: list[tuple[bool, str]] = [
        (bool(rec.external_id and rec.external_id.strip()), "missing external reference id"),
        (bool(rec.title and len(rec.title.strip()) >= 4), "title is missing or too short to be useful"),
        (rec.status in CANONICAL_STATUSES, f"status {rec.status!r} did not normalize to a known canonical status"),
        (bool(rec.department and rec.department.strip()), "missing responsible department"),
        (rec.citizen_contact is None or bool(_INDIAN_MOBILE.match(rec.citizen_contact.strip())), "citizen contact does not look like a valid Indian mobile number"),
        (rec.filed_on is None or _parses_as_date(rec.filed_on), "filed_on date could not be parsed"),
        (bool(rec.citizen_name and rec.citizen_name.strip()), "missing citizen name"),
        (bool(rec.location and rec.location.strip()), "missing location"),
    ]
    issues = tuple(msg for ok, msg in checks if not ok)
    score = sum(1 for ok, _ in checks if ok) / len(checks)
    return QualityReport(round(score, 2), issues)


def today_iso() -> str:
    return date.today().isoformat()  # noqa: DTZ011
