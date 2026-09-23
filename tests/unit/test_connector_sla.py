"""app.interop.monitoring.sla - pure, no database."""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from app.interop.monitoring.sla import evaluate_sla


@dataclass
class _Row:
    connector_id: str = "dept_a"
    total_calls: int = 0
    total_failures: int = 0
    avg_response_ms: float | None = None
    sla_max_avg_response_ms: float | None = None
    sla_min_success_rate: float | None = None


class SlaTests(unittest.TestCase):
    def test_never_called_is_honestly_unknown_not_met(self):
        self.assertEqual(evaluate_sla(_Row(total_calls=0)), "unknown")

    def test_all_success_fast_response_is_met(self):
        self.assertEqual(evaluate_sla(_Row(total_calls=10, total_failures=0, avg_response_ms=50.0)), "met")

    def test_slow_average_response_breaches_the_default_threshold(self):
        self.assertEqual(evaluate_sla(_Row(total_calls=10, total_failures=0, avg_response_ms=5000.0)), "breached")

    def test_too_many_failures_breaches_the_default_success_rate(self):
        self.assertEqual(evaluate_sla(_Row(total_calls=10, total_failures=3, avg_response_ms=50.0)), "breached")

    def test_a_connectors_own_thresholds_override_the_default(self):
        row = _Row(total_calls=10, total_failures=0, avg_response_ms=200.0, sla_max_avg_response_ms=100.0)
        self.assertEqual(evaluate_sla(row), "breached")  # would be "met" under the default 1000ms

    def test_a_looser_custom_success_rate_can_forgive_what_the_default_would_breach(self):
        row = _Row(total_calls=10, total_failures=3, avg_response_ms=50.0, sla_min_success_rate=0.5)
        self.assertEqual(evaluate_sla(row), "met")  # 70% success rate clears a 50% bar


if __name__ == "__main__":
    unittest.main()
