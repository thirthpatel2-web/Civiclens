"""Integration health: run checks, persist reports, announce state changes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.integrations.base import GovernmentAdapter, HealthReport


class HealthRepository(Protocol):
    def save(self, report: HealthReport) -> None: ...
    def latest(self, platform: str) -> HealthReport | None: ...


class IntegrationHealthService:
    def __init__(self, repo: HealthRepository, on_state_change: Callable[[str, str | None, str], None] | None = None) -> None:
        self._repo, self._notify = repo, on_state_change

    def check_all(self, adapters: dict[str, GovernmentAdapter]) -> list[HealthReport]:
        reports = []
        for platform, adapter in adapters.items():
            previous = self._repo.latest(platform)
            report = adapter.health_check()
            self._repo.save(report)
            if self._notify and (previous is None or previous.state != report.state):
                self._notify(platform, previous.state.value if previous else None, report.state.value)  # -> integration.status_changed
            reports.append(report)
        return reports
