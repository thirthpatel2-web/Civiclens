"""Duplicate-complaint detection. Advisory only: nothing is merged or deleted.

Score = weighted mean of the *available* components, re-normalised when a component
cannot be computed (no coordinates, no embeddings):
  lexical (token Jaccard blended with character-trigram Dice), semantic (cosine),
  category match, geographic proximity, temporal proximity.
Two complaints far apart or in different categories cannot be "possible duplicates"
however similar their wording, and every result carries a plain-language explanation.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.core.authorization import AuthContext, Permission, can_access_complaint, require
from app.core.exceptions import PermissionDenied, ValidationFailed
from app.rag.text import content_terms
from app.rag.vector_search import cosine_similarity
from app.services.location_service import haversine_m

WEIGHTS = {"lexical": 0.35, "semantic": 0.25, "category": 0.15, "geo": 0.15, "time": 0.10}


@dataclass(frozen=True)
class ComplaintSnapshot:
    id: str
    reference: str
    text: str
    category: str | None
    created_at: datetime
    lat: float | None = None
    lng: float | None = None
    embedding: Sequence[float] | None = None


@dataclass(frozen=True)
class DuplicateMatch:
    reference: str
    complaint_id: str
    score: float
    verdict: str  # "possible_duplicate" | "related"
    components: dict[str, float | None]
    explanation: str


def _trigrams(text: str) -> set[str]:
    s = " ".join(text.lower().split())
    return {s[i : i + 3] for i in range(max(len(s) - 2, 0))} if len(s) >= 3 else {s} if s else set()


def lexical_similarity(a: str, b: str) -> float:
    ta, tb = set(content_terms(a)), set(content_terms(b))
    jaccard = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    ga, gb = _trigrams(a), _trigrams(b)
    dice = 2 * len(ga & gb) / (len(ga) + len(gb)) if ga and gb else 0.0
    return 0.6 * jaccard + 0.4 * dice


class DuplicateDetector:
    def __init__(self, *, duplicate_threshold: float = 0.75, related_threshold: float = 0.55, radius_m: float = 250.0, window: timedelta = timedelta(days=14)) -> None:
        self.dup_t, self.rel_t, self.radius_m, self.window = duplicate_threshold, related_threshold, radius_m, window

    def compare(self, new: ComplaintSnapshot, other: ComplaintSnapshot) -> DuplicateMatch | None:
        comps: dict[str, float | None] = {"lexical": lexical_similarity(new.text, other.text)}
        comps["semantic"] = max(0.0, cosine_similarity(new.embedding, other.embedding)) if new.embedding and other.embedding and len(new.embedding) == len(other.embedding) else None
        comps["category"] = None if not (new.category and other.category) else 1.0 if new.category == other.category else 0.0
        dist = haversine_m(new.lat, new.lng, other.lat, other.lng)
        comps["geo"] = None if dist is None else math.exp(-dist / self.radius_m) if dist <= self.radius_m * 3 else 0.0
        dt = abs(new.created_at - other.created_at)
        comps["time"] = max(0.0, 1.0 - dt / self.window) if dt <= self.window else 0.0

        # hard gates: incompatible category or far apart / long ago cannot be duplicates
        if comps["category"] == 0.0 or (dist is not None and dist > self.radius_m * 3) or dt > self.window:
            return None
        avail = {k: v for k, v in comps.items() if v is not None}
        total_w = sum(WEIGHTS[k] for k in avail)
        score = sum(WEIGHTS[k] * v for k, v in avail.items()) / total_w if total_w else 0.0
        verdict = "possible_duplicate" if score >= self.dup_t else "related" if score >= self.rel_t else None
        if verdict is None:
            return None
        parts = [f"text similarity {comps['lexical']:.0%}"]
        if comps["semantic"] is not None:
            parts.append(f"semantic similarity {comps['semantic']:.0%}")
        if dist is not None:
            parts.append(f"{dist:.0f} m apart")
        parts.append(f"filed {dt.total_seconds() / 86400:.1f} days apart")
        if comps["category"] == 1.0:
            parts.append(f"same category ({new.category})")
        missing = [k for k in ("semantic", "geo", "category") if comps[k] is None]
        note = f" Not compared: {', '.join(missing)}." if missing else ""
        return DuplicateMatch(other.reference, other.id, round(score, 3), verdict, {k: (None if v is None else round(v, 3)) for k, v in comps.items()}, "; ".join(parts) + "." + note)

    def find(self, new: ComplaintSnapshot, candidates: Sequence[ComplaintSnapshot], *, limit: int = 5) -> list[DuplicateMatch]:
        matches = [m for c in candidates if c.id != new.id if (m := self.compare(new, c))]
        matches.sort(key=lambda m: (-m.score, m.reference))
        return matches[:limit]


REVIEW_DECISIONS = ("confirmed_duplicate", "related", "not_duplicate")


@dataclass(frozen=True)
class DuplicateReview:
    complaint_id: str
    other_complaint_id: str
    decision: str
    reviewer_id: str
    note: str | None
    at: datetime


class DuplicateReviewRepository(Protocol):
    def add(self, review: DuplicateReview) -> None: ...


class DuplicateReviewService:
    """Persists an authorised human decision; never merges or deletes a complaint."""

    def __init__(self, repo: DuplicateReviewRepository) -> None:
        self._repo = repo

    def record(self, ctx: AuthContext, *, complaint_id: str, complaint_owner: str, complaint_department: str | None, other_complaint_id: str, decision: str, note: str | None, at: datetime) -> DuplicateReview:  # noqa: PLR0913
        require(ctx, Permission.DUPLICATE_REVIEW)
        if not can_access_complaint(ctx, owner_id=complaint_owner, department_id=complaint_department):
            raise PermissionDenied("You do not have access to this record.")
        if decision not in REVIEW_DECISIONS:
            raise ValidationFailed("Unknown review decision.", details={"allowed": list(REVIEW_DECISIONS)})
        if complaint_id == other_complaint_id:
            raise ValidationFailed("A complaint cannot be a duplicate of itself.")
        review = DuplicateReview(complaint_id, other_complaint_id, decision, ctx.user_id, (note or "").strip() or None, at)
        self._repo.add(review)
        return review
