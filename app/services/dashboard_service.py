"""Database-backed dashboards. Every number is computed from persisted complaint rows;
with no rows the result says ``has_data=False`` instead of showing zeros as if they were insights."""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.authorization import AuthContext, Permission, Role, require
from app.core.exceptions import PermissionDenied
from app.services.complaint_status import FINISHED, ComplaintStatus
from app.services.ports import ComplaintRow
from app.services.sla_service import SlaCalculator, SlaSubject
from app.services.uow import UowFactory

OPEN = [s for s in ComplaintStatus if s not in FINISHED]


def summarize(rows: list[ComplaintRow], now: datetime, calc: SlaCalculator, *, trend_days: int = 30) -> dict[str, Any]:
    open_rows = [r for r in rows if r.status not in FINISHED]
    resolved = [r for r in rows if r.resolved_at is not None and r.status in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED)]
    sla = Counter(calc.status(SlaSubject(r.id, r.priority, r.department_code, r.status, r.created_at, r.sla_due_at, r.escalation_level), now).state for r in open_rows)
    hours = [(r.resolved_at - r.created_at).total_seconds() / 3600 for r in resolved if r.resolved_at]
    start = (now - timedelta(days=trend_days - 1)).date()
    per_day = Counter(r.created_at.date() for r in rows if r.created_at.date() >= start)
    trend = [{"date": (start + timedelta(days=i)).isoformat(), "count": per_day.get(start + timedelta(days=i), 0)} for i in range(trend_days)]
    routed = Counter(r.routing_source or "unknown" for r in rows)
    return {
        "has_data": bool(rows), "total": len(rows), "open": len(open_rows), "resolved": len(resolved),
        "by_status": {str(k): v for k, v in Counter(r.status for r in rows).items()},
        "by_priority": dict(Counter(r.priority for r in rows)), "by_category": dict(Counter(r.category for r in rows)),
        "by_department": dict(Counter(r.department_code or "unrouted" for r in rows)), "by_ward": dict(Counter(r.ward for r in rows if r.ward)),
        "sla": {"on_track": sla.get("on_track", 0), "at_risk": sla.get("at_risk", 0), "breached": sla.get("breached", 0), "no_policy": sla.get("no_policy", 0)},
        "escalated": sum(1 for r in open_rows if r.escalation_level > 0),
        "resolution_hours": {"count": len(hours), "mean": round(statistics.fmean(hours), 1), "median": round(statistics.median(hours), 1)} if hours else None,
        "trend_daily": trend, "backlog": len(open_rows), "routing_sources": dict(routed),
        "unrouted": sum(1 for r in open_rows if r.department_code is None),
    }


class DashboardService:
    def __init__(self, uow_factory: UowFactory, clock: Callable[[], datetime] | None = None, system_status: Callable[[], dict[str, Any]] | None = None) -> None:
        self._uow, self._clock, self._system = uow_factory, clock or (lambda: datetime.now(UTC)), system_status

    def citizen(self, ctx: AuthContext) -> dict[str, Any]:
        require(ctx, Permission.COMPLAINT_READ_OWN)
        now = self._clock()
        with self._uow() as uow:
            calc = SlaCalculator(list(uow.config.sla_policies()))
            rows = uow.complaints.rows(citizen_id=ctx.user_id)
            recent = uow.complaints.list_for_citizen(ctx.user_id, limit=5)
            awaiting = [r.id for r in rows if r.status is ComplaintStatus.RESOLVED and uow.complaints.get_feedback(r.id) is None]
            rti = [a for a in uow.rti.list_for_owner(ctx.user_id) if getattr(a.status, "value", a.status) == "filed"]
            unread = uow.notifications.unread_count(ctx.user_id)
        summary = summarize(rows, now, calc)
        return {**summary, "recent": recent, "pending_feedback": awaiting, "unread_notifications": unread,
                "rti_countdowns": [{"reference": a.reference, "due_at": a.due_at, "days_left": (a.due_at - now).days if a.due_at else None, "estimate": a.deadline_is_estimate} for a in rti]}  # fmt: skip

    def department(self, ctx: AuthContext, *, department_code: str | None = None) -> dict[str, Any]:
        """Officer's own department (from context). Unbound admins may pass a department to inspect."""
        require(ctx, Permission.DASHBOARD_DEPARTMENT)
        if ctx.role is Role.OFFICER or ctx.department_id is not None:
            dept = ctx.department_id
            if dept is None:
                raise PermissionDenied("Your account is not assigned to a department.")
        else:
            dept = department_code
        now = self._clock()
        with self._uow() as uow:
            calc = SlaCalculator(list(uow.config.sla_policies()))
            rows = uow.complaints.rows(department_code=dept) if dept else uow.complaints.rows()
            loads: dict[str, int] = {}
            for r in rows:
                if r.assigned_officer_id and r.status not in FINISHED:
                    loads[r.assigned_officer_id] = loads.get(r.assigned_officer_id, 0) + 1
            anomalies = uow.anomalies.list(status="open", department_code=dept, limit=20)
            # what citizens said about "resolved": the accountability number a resolved count alone hides
            ratings = [fb.rating for r in rows if r.status in FINISHED and (fb := uow.complaints.get_feedback(r.id)) is not None]
        out = summarize(rows, now, calc)
        out.update({"department_code": dept, "workload": loads, "anomalies": anomalies, "priority_counts": out["by_priority"],
                    "satisfaction": {"average": round(sum(ratings) / len(ratings), 1), "count": len(ratings)} if ratings else None})  # fmt: skip
        return out

    def history(self, ctx: AuthContext, *, days: int = 30) -> dict[str, Any]:
        """Historical metrics read from the scheduled analytics snapshots (organisation-wide; empty until snapshots exist)."""
        require(ctx, Permission.ANALYTICS_VIEW)
        if ctx.department_id is not None:
            raise PermissionDenied("Historical analytics are organisation-wide.")
        since = self._clock() - timedelta(days=max(1, min(days, 365)))
        with self._uow() as uow:
            snaps = uow.analytics.list_snapshots("all", since)
        points = [snapshot_point(t, m) for t, m in snaps]
        return {"has_data": bool(points), "days": days, "points": points}

    def admin(self, ctx: AuthContext) -> dict[str, Any]:
        require(ctx, Permission.ADMIN_DASHBOARD)
        base = self.department(ctx, department_code=None) if ctx.department_id is None else self.department(ctx)
        now = self._clock()
        with self._uow() as uow:
            recent_audit = uow.audit.query(limit=15)
            job_counts = uow.jobs.counts_by_status()
        base.update({"recent_audit": recent_audit, "jobs": job_counts, "system": self._system() if self._system else None, "generated_at": now})
        return base


def snapshot_point(taken_at: datetime, m: dict[str, Any]) -> dict[str, Any]:
    sla = m.get("sla", {})
    return {"taken_at": taken_at, "total": m.get("total", 0), "open": m.get("open", 0), "resolved": m.get("resolved", 0), "backlog": m.get("backlog", 0), "escalated": m.get("escalated", 0),
            "breached": sla.get("breached", 0), "at_risk": sla.get("at_risk", 0), "unrouted": m.get("unrouted", 0)}  # fmt: skip
