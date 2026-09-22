"""Scheduled anomaly detection over persisted complaints; results are stored, not just computed."""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from app.services.analytics_service import (
    AnomalyEvent,
    InsufficientData,
    detect_backlog,
    detect_sla_failure_rate,
    detect_volume_spike,
    detect_ward_spikes,
)
from app.services.complaint_status import FINISHED
from app.services.ports import AnomalyRecord, ComplaintRow
from app.services.sla_service import SlaCalculator, SlaSubject
from app.services.uow import UowFactory

HISTORY_DAYS = 28


def _daily(rows: list[ComplaintRow], today: datetime, key=lambda r: True) -> tuple[list[int], int]:
    counts = Counter(r.created_at.date() for r in rows if key(r))
    hist = [counts.get(today.date() - timedelta(days=i), 0) for i in range(HISTORY_DAYS, 0, -1)]
    return hist, counts.get(today.date(), 0)


class AnomalyDetectionJob:
    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow = uow_factory

    def run(self, now: datetime) -> dict[str, Any]:
        found: list[tuple[AnomalyEvent, str | None]] = []
        insufficient: list[str] = []
        with self._uow() as uow:
            rows = uow.complaints.rows(since=now - timedelta(days=HISTORY_DAYS + 1))
            calc = SlaCalculator(list(uow.config.sla_policies()))

            def take(r: AnomalyEvent | InsufficientData | None, label: str, dept: str | None = None) -> None:
                if isinstance(r, InsufficientData):
                    insufficient.append(label)
                elif r is not None:
                    found.append((r, dept))

            hist, today = _daily(rows, now)
            take(detect_volume_spike("All complaints", hist, today), "all complaints")
            hist_d, today_d = _daily(rows, now, lambda r: r.has_duplicates)
            take(detect_volume_spike("Duplicate-flagged complaints", hist_d, today_d, kind="duplicate_spike"), "duplicates")

            wards = {r.ward for r in rows if r.ward}
            events, skipped = detect_ward_spikes({w: _daily(rows, now, lambda r, w=w: r.ward == w)[1] for w in wards}, {w: _daily(rows, now, lambda r, w=w: r.ward == w)[0] for w in wards})
            found += [(e, None) for e in events]
            insufficient += [f"ward {w}" for w in skipped]

            pairs = {(r.ward, r.category) for r in rows if r.ward}
            for w, cat in sorted(pairs):
                h, t = _daily(rows, now, lambda r, w=w, cat=cat: r.ward == w and r.category == cat)
                r = detect_volume_spike(f"Ward {w} / {cat}", h, t, kind="ward_category_cluster")
                if isinstance(r, AnomalyEvent):
                    found.append((AnomalyEvent(r.kind, r.subject, r.observed, r.expected, r.score, r.severity, r.explanation, {"categories": [cat]}), None))

            by_dept: dict[str, list[ComplaintRow]] = defaultdict(list)
            for row in rows:  # not `r`: that name already holds a detector result in this scope
                if row.department_code:
                    by_dept[row.department_code].append(row)
            for dept, drows in sorted(by_dept.items()):
                open_n = sum(1 for r in drows if r.status not in FINISHED)
                closed_7d = sum(1 for r in drows if r.resolved_at and r.resolved_at >= now - timedelta(days=7))
                if (b := detect_backlog(dept, open_n, closed_7d)) is not None:
                    found.append((b, dept))
                subjects = [SlaSubject(r.id, r.priority, r.department_code, r.status, r.created_at, r.sla_due_at, r.escalation_level) for r in drows if r.status not in FINISHED]
                breached = sum(1 for s in subjects if calc.status(s, now).state == "breached")
                take(detect_sla_failure_rate(dept, breached, len(subjects)), f"sla {dept}", dept)

            created = 0
            for ev, event_dept in found:  # not `dept`: that name is str (a dict key) above; this is str | None
                rec = AnomalyRecord(str(uuid.uuid4()), ev.kind, ev.subject, ev.severity, float(ev.score) if ev.score != float("inf") else 9999.0, ev.explanation, now, event_dept, details={**ev.details, "observed": ev.observed, "expected": ev.expected},
                                    dedupe_key=f"{ev.kind}:{ev.subject}:{now.date().isoformat()}")  # fmt: skip
                if uow.anomalies.add_if_new(rec):
                    created += 1
            uow.commit()
        return {"rows_examined": len(rows), "detected": len(found), "created": created, "skipped_insufficient_history": len(insufficient)}
