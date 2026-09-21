import unittest

from app.services.analytics_service import (
    AnomalyEvent,
    InsufficientData,
    detect_backlog,
    detect_sla_failure_rate,
    detect_volume_spike,
    detect_ward_spikes,
    forecast_linear,
)

NORMAL = [10, 12, 9, 11, 10, 13, 8, 11, 10, 12, 9, 10, 11, 12]


class AnomalyTests(unittest.TestCase):
    def test_spike_detected_with_severity_and_explanation(self):
        w = detect_volume_spike("All complaints", NORMAL, 25)
        self.assertIsInstance(w, AnomalyEvent)
        self.assertIn(w.severity, ("warning", "critical"))
        self.assertEqual(w.expected, 10.5)
        self.assertIn("25", w.explanation)
        self.assertEqual(detect_volume_spike("All", NORMAL, 60).severity, "critical")

    def test_normal_and_small_changes_are_not_anomalies(self):
        self.assertIsNone(detect_volume_spike("All", NORMAL, 12))
        self.assertIsNone(detect_volume_spike("All", NORMAL, 3))  # a drop is not a spike
        flat = [0] * 20
        self.assertIsNone(detect_volume_spike("Ward 1", flat, 2))  # below min absolute increase
        self.assertIsInstance(detect_volume_spike("Ward 1", flat, 9), AnomalyEvent)  # flat history, big jump

    def test_short_history_is_reported_not_guessed(self):
        r = detect_volume_spike("All", [1, 2, 3], 100)
        self.assertEqual((type(r), r.needed, r.have), (InsufficientData, 14, 3))

    def test_ward_spikes_sorted_and_skips_reported(self):
        events, skipped = detect_ward_spikes({"1": 30, "2": 11, "3": 50, "9": 99}, {"1": NORMAL, "2": NORMAL, "3": NORMAL, "9": [1, 2]})
        self.assertEqual([e.subject for e in events], ["Ward 3", "Ward 1"])
        self.assertEqual(skipped, ["9"])
        self.assertTrue(all(e.kind == "ward_spike" for e in events))

    def test_backlog(self):
        self.assertIsNone(detect_backlog("Roads", 5, 0))  # too small to matter
        self.assertIsNone(detect_backlog("Roads", 30, 20))
        w = detect_backlog("Roads", 50, 10)
        self.assertEqual((w.severity, w.score), ("warning", 5.0))
        self.assertEqual(detect_backlog("Roads", 100, 10).severity, "critical")
        self.assertEqual(detect_backlog("Roads", 30, 0).severity, "critical")

    def test_sla_failure_rate_min_sample(self):
        self.assertIsInstance(detect_sla_failure_rate("Water", 5, 10), InsufficientData)
        self.assertIsNone(detect_sla_failure_rate("Water", 2, 50))
        self.assertEqual(detect_sla_failure_rate("Water", 12, 50).severity, "warning")
        self.assertEqual(detect_sla_failure_rate("Water", 30, 50).severity, "critical")


class ForecastTests(unittest.TestCase):
    def test_exact_linear_series(self):
        f = forecast_linear([2 * i + 5 for i in range(10)], horizon=3)
        self.assertEqual(f.values, (25.0, 27.0, 29.0))
        self.assertEqual(f.lower, f.values)  # zero residual -> zero band
        self.assertTrue(f.is_estimate)
        self.assertIn("estimate", f.label)
        self.assertEqual((f.method, f.sample_size), ("ols_linear_trend", 10))

    def test_noisy_series_has_widening_band_and_non_negative_values(self):
        f = forecast_linear([10, 12, 9, 11, 8, 10, 7, 9, 6, 8, 5, 7], horizon=30)
        self.assertTrue(all(v >= 0 for v in f.values + f.lower))
        self.assertGreater(f.upper[-1] - f.lower[-1], f.upper[0] - f.lower[0])

    def test_insufficient_history(self):
        r = forecast_linear([1, 2, 3])
        self.assertIsInstance(r, InsufficientData)
        self.assertEqual((r.needed, r.have), (8, 3))


if __name__ == "__main__":
    unittest.main()
