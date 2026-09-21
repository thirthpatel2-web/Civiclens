"""Human review of duplicate candidates. Advisory only: no complaint is ever merged, closed or deleted by a review."""

from __future__ import annotations

from typing import Any

from app.core.authorization import AuthContext, Permission, can_access_complaint, require
from app.core.exceptions import NotFound, ValidationFailed
from app.services.complaint_common import ComplaintEffects
from app.services.duplicate_service import REVIEW_DECISIONS, DuplicateReview
from app.services.uow import UowFactory

STATE_OF_DECISION = {"confirmed_duplicate": "confirmed duplicate", "related": "related", "not_duplicate": "not a duplicate"}


class DuplicateReviewApp:
    def __init__(self, uow_factory: UowFactory, effects: ComplaintEffects) -> None:
        self._uow, self._fx = uow_factory, effects

    def _load(self, uow: Any, ctx: AuthContext, complaint_id: str):  # type: ignore[no-untyped-def]
        c = uow.complaints.get(complaint_id)
        if c is None or not can_access_complaint(ctx, owner_id=c.citizen_id, department_id=c.department_code):
            raise NotFound("Complaint not found.")
        return c

    def candidates(self, ctx: AuthContext, complaint_id: str) -> list[dict[str, Any]]:
        """Candidates flagged at intake, each with its similarity explanation and the latest human decision (if any)."""
        require(ctx, Permission.DUPLICATE_REVIEW)
        with self._uow() as uow:
            c = self._load(uow, ctx, complaint_id)
            latest = {r.other_complaint_id: r for r in uow.duplicate_reviews.list_for_complaint(c.id)}
            out = []
            for d in c.duplicates:
                other = uow.complaints.get(d["complaint_id"])
                visible = other is not None and can_access_complaint(ctx, owner_id=other.citizen_id, department_id=other.department_code)
                r = latest.get(d["complaint_id"])
                out.append({"complaint_id": d["complaint_id"], "reference": d["reference"], "score": d["score"], "verdict": d["verdict"], "explanation": d["explanation"],
                            "other_status": str(other.status) if visible else None, "other_title": other.title if visible else None,
                            "review": None if r is None else {"decision": r.decision, "reviewer_id": r.reviewer_id, "note": r.note, "at": r.at}})  # fmt: skip
        return out

    def decide(self, ctx: AuthContext, complaint_id: str, other_complaint_id: str, decision: str, note: str | None = None) -> DuplicateReview:
        require(ctx, Permission.DUPLICATE_REVIEW)
        if decision not in REVIEW_DECISIONS:
            raise ValidationFailed("Unknown review decision.", details={"allowed": list(REVIEW_DECISIONS)})
        with self._uow() as uow:
            c = self._load(uow, ctx, complaint_id)
            if other_complaint_id == c.id:
                raise ValidationFailed("A complaint cannot be a duplicate of itself.")
            if other_complaint_id not in {d["complaint_id"] for d in c.duplicates}:
                raise ValidationFailed("That complaint was not flagged as a candidate for this one.")
            review = DuplicateReview(c.id, other_complaint_id, decision, ctx.user_id, (note or "").strip() or None, self._fx.clock())
            uow.duplicate_reviews.add(review)
            other = uow.complaints.get(other_complaint_id)
            self._fx.event(uow, c, "duplicate_review", ctx, remarks=review.note, internal=True,
                           details={"other_reference": other.reference if other else None, "decision": decision, "state": STATE_OF_DECISION[decision]})  # fmt: skip
            self._fx.audit(uow).record("complaint.duplicate_reviewed", actor_id=ctx.user_id, resource_type="complaint", resource_id=c.id, metadata={"other": other_complaint_id, "decision": decision})
            uow.commit()
        return review

    def history(self, ctx: AuthContext, complaint_id: str) -> list[DuplicateReview]:
        require(ctx, Permission.DUPLICATE_REVIEW)
        with self._uow() as uow:
            self._load(uow, ctx, complaint_id)
            return list(uow.duplicate_reviews.list_for_complaint(complaint_id))


