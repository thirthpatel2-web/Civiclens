"""Operational anomaly detection and trend estimates.

All inputs are real counts supplied by repositories. When there is too little history the
functions return ``InsufficientData`` - never a made-up "normal". Forecasts are labelled
estimates (``is_estimate=True``) with their method and sample size so a UI cannot present
them as facts.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class InsufficientData:
    needed: int
    have: int
    reason: str = "not enough history to judge"


@dataclass(frozen=True)
class AnomalyEvent:
    kind: str  # volume_spike | ward_spike | department_backlog | sla_failure_rate
    subject: str
    observed: float
    expected: float
    score: float
    severity: str  # "warning" | "critical"
    explanation: str
    details: dict[str, float] = field(default_factory=dict)


def _robust_z(history: Sequence[float], value: float) -> tuple[float, float]:
    """Modified z-score (median/MAD): resistant to the spikes we are trying to find."""
    med = statistics.median(history)
    mad = statistics.median(abs(x - med) for x in history)
    scale = 1.4826 * mad if mad > 0 else max(statistics.pstdev(history), 0.5)  # floor avoids divide-by-zero on flat counts
    return (value - med) / scale, med


def detect_volume_spike(subject: str, history: Sequence[float], today: float, *, kind: str = "volume_spike", min_history: int = 14,
                        z_warning: float = 3.0, z_critical: float = 5.0, min_absolute_increase: float = 3.0) -> AnomalyEvent | InsufficientData | None:  # fmt: skip
    if len(history) < min_history:
        return InsufficientData(min_history, len(history))
    z, med = _robust_z(history, today)
    if z < z_warning or today - med < min_absolute_increase:
        return None
    sev = "critical" if z >= z_critical else "warning"
    return AnomalyEvent(kind, subject, today, med, round(z, 2), sev, f"{subject}: {today:g} today vs typical {med:g} (robust z={z:.1f}) over {len(history)} days.", {"z": round(z, 2)})


def detect_ward_spikes(today_by_ward: Mapping[str, float], history_by_ward: Mapping[str, Sequence[float]], **kw: float) -> tuple[list[AnomalyEvent], list[str]]:
    """Returns (events, wards skipped for insufficient history)."""
    events: list[AnomalyEvent] = []
    skipped: list[str] = []
    for ward, today in today_by_ward.items():
        r = detect_volume_spike(f"Ward {ward}", history_by_ward.get(ward, ()), today, kind="ward_spike", **kw)  # type: ignore[arg-type]
        if isinstance(r, InsufficientData):
            skipped.append(ward)
        elif r:
            events.append(r)
    return sorted(events, key=lambda e: -e.score), sorted(skipped)


def detect_backlog(department: str, open_count: int, closed_last_7d: int, *, weeks_warning: float = 4.0, weeks_critical: float = 8.0, min_open: int = 10) -> AnomalyEvent | None:
    """Backlog measured in weeks of current closure throughput."""
    if open_count < min_open:
        return None
    if closed_last_7d <= 0:
        return AnomalyEvent("department_backlog", department, open_count, 0, math.inf, "critical", f"{department}: {open_count} open complaints and none closed in the last 7 days.", {})
    weeks = open_count / closed_last_7d
    if weeks < weeks_warning:
        return None
    sev = "critical" if weeks >= weeks_critical else "warning"
    return AnomalyEvent("department_backlog", department, open_count, closed_last_7d * weeks_warning, round(weeks, 1), sev,
                        f"{department}: {open_count} open, ~{weeks:.1f} weeks of work at the current closure rate ({closed_last_7d}/week).", {"weeks_of_work": round(weeks, 1)})  # fmt: skip


def detect_sla_failure_rate(subject: str, breached: int, total_due: int, *, min_sample: int = 20, warning: float = 0.2, critical: float = 0.4) -> AnomalyEvent | InsufficientData | None:
    if total_due < min_sample:
        return InsufficientData(min_sample, total_due)
    rate = breached / total_due
    if rate < warning:
        return None
    return AnomalyEvent("sla_failure_rate", subject, rate, warning, round(rate, 3), "critical" if rate >= critical else "warning", f"{subject}: {breached} of {total_due} complaints past SLA ({rate:.0%}).", {"rate": round(rate, 3)})


@dataclass(frozen=True)
class Forecast:
    is_estimate: bool
    method: str
    sample_size: int
    horizon: int
    values: tuple[float, ...]
    lower: tuple[float, ...]
    upper: tuple[float, ...]
    label: str


def forecast_linear(series: Sequence[float], horizon: int = 7, *, min_points: int = 8) -> Forecast | InsufficientData:
    """Ordinary least-squares trend with an approximate 95% band. An estimate, not a fact."""
    n = len(series)
    if n < min_points:
        return InsufficientData(min_points, n)
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(series) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, series, strict=True)) / sxx
    intercept = my - slope * mx
    resid = [y - (intercept + slope * x) for x, y in zip(xs, series, strict=True)]
    se = math.sqrt(sum(r * r for r in resid) / max(n - 2, 1))
    vals, lo, hi = [], [], []
    for h in range(1, horizon + 1):
        x = n - 1 + h
        yhat = max(0.0, intercept + slope * x)
        band = 1.96 * se * math.sqrt(1 + 1 / n + (x - mx) ** 2 / sxx)
        vals.append(round(yhat, 2))
        lo.append(round(max(0.0, yhat - band), 2))
        hi.append(round(yhat + band, 2))
    return Forecast(True, "ols_linear_trend", n, horizon, tuple(vals), tuple(lo), tuple(hi), f"Model-generated estimate from {n} observations; not an official figure.")
