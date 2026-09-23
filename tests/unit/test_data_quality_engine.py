"""The generic Data Quality Engine - pure, no database. See
tests/integration/test_interop_gateway_e2e.py::test_data_quality_failure_blocks_the_write_and_is_recorded_honestly
for proof the gateway's real document check (now expressed as rules here) still behaves
identically end to end."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from app.interop.quality.engine import REJECTED, VALID, VALID_WITH_WARNINGS, DataQualityEngine, QualityRule


class DataQualityEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = DataQualityEngine()

    def test_no_rules_is_trivially_valid(self):
        result = self.engine.evaluate({}, [])
        self.assertEqual(result.status, VALID)
        self.assertEqual(result.score, 1.0)

    def test_required_field_present_passes(self):
        result = self.engine.evaluate({"name": "Priya"}, [QualityRule("name", "required")])
        self.assertEqual(result.status, VALID)

    def test_required_field_missing_rejects(self):
        result = self.engine.evaluate({}, [QualityRule("name", "required")])
        self.assertEqual(result.status, REJECTED)
        self.assertIn("name is required", result.errors[0])

    def test_a_warning_severity_failure_is_valid_with_warnings_not_rejected(self):
        result = self.engine.evaluate({}, [QualityRule("mobile", "required", severity="warning")])
        self.assertEqual(result.status, VALID_WITH_WARNINGS)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.warnings), 1)

    def test_min_length_rule(self):
        self.assertEqual(self.engine.evaluate({"ref": "AB"}, [QualityRule("ref", "min_length", {"min": 6})]).status, REJECTED)
        self.assertEqual(self.engine.evaluate({"ref": "ABCDEF"}, [QualityRule("ref", "min_length", {"min": 6})]).status, VALID)

    def test_max_length_rule(self):
        self.assertEqual(self.engine.evaluate({"note": "x" * 500}, [QualityRule("note", "max_length", {"max": 100})]).status, REJECTED)

    def test_regex_rule_validates_a_mobile_number_format(self):
        rule = QualityRule("mobile", "regex", {"pattern": r"^[6-9]\d{9}$"})
        self.assertEqual(self.engine.evaluate({"mobile": "9876543210"}, [rule]).status, VALID)
        self.assertEqual(self.engine.evaluate({"mobile": "12345"}, [rule]).status, REJECTED)

    def test_in_set_rule(self):
        rule = QualityRule("status", "in_set", {"allowed": ["verified", "pending"]})
        self.assertEqual(self.engine.evaluate({"status": "verified"}, [rule]).status, VALID)
        self.assertEqual(self.engine.evaluate({"status": "rejected"}, [rule]).status, REJECTED)

    def test_not_in_future_rule(self):
        rule = QualityRule("issued_on", "not_in_future")
        self.assertEqual(self.engine.evaluate({"issued_on": date.today().isoformat()}, [rule]).status, VALID)
        self.assertEqual(self.engine.evaluate({"issued_on": (date.today() + timedelta(days=5)).isoformat()}, [rule]).status, REJECTED)
        self.assertEqual(self.engine.evaluate({}, [rule]).status, REJECTED)  # missing date fails a date-validity rule

    def test_stale_after_days_rule(self):
        rule = QualityRule("issued_on", "stale_after_days", {"days": 30})
        self.assertEqual(self.engine.evaluate({"issued_on": (date.today() - timedelta(days=5)).isoformat()}, [rule]).status, VALID)
        self.assertEqual(self.engine.evaluate({"issued_on": (date.today() - timedelta(days=90)).isoformat()}, [rule]).status, REJECTED)

    def test_cross_field_equals_rule_catches_conflicting_values(self):
        rule = QualityRule("mobile_a", "cross_field_equals", {"other_field": "mobile_b"})
        self.assertEqual(self.engine.evaluate({"mobile_a": "123", "mobile_b": "123"}, [rule]).status, VALID)
        self.assertEqual(self.engine.evaluate({"mobile_a": "123", "mobile_b": "456"}, [rule]).status, REJECTED)

    def test_an_unrecognized_rule_type_never_blocks_a_real_exchange(self):
        result = self.engine.evaluate({"x": "anything"}, [QualityRule("x", "made_up_rule_type")])
        self.assertEqual(result.status, VALID)

    def test_score_reflects_the_fraction_of_rules_passed(self):
        rules = [QualityRule("a", "required"), QualityRule("b", "required"), QualityRule("c", "required")]
        result = self.engine.evaluate({"a": "x"}, rules)
        self.assertEqual(result.score, round(1 / 3, 2))

    def test_rule_round_trips_through_dict_serialization(self):
        rule = QualityRule("reference", "min_length", {"min": 6}, severity="error", message="custom message")
        restored = QualityRule.from_dict(rule.to_dict())
        self.assertEqual(restored, rule)

    def test_custom_message_overrides_the_default(self):
        rule = QualityRule("name", "required", message="A name is mandatory for this document type.")
        result = self.engine.evaluate({}, [rule])
        self.assertEqual(result.errors, ["A name is mandatory for this document type."])

    def test_the_exact_three_rules_the_gateway_uses_reproduce_its_known_behavior(self):
        """Mirrors InteropGatewayService._document_quality's rubric exactly - status must be
        verified, reference at least 6 chars, issued_on present. This is the safety net proving
        the migration from hand-written checks to rule data didn't change behavior."""
        rules = [
            QualityRule("status", "in_set", {"allowed": ["verified"]}, message="source document status is not verified"),
            QualityRule("reference", "min_length", {"min": 6}, message="reference number is missing or too short to be a real reference"),
            QualityRule("issued_on", "required", message="issue date is missing"),
        ]
        good = self.engine.evaluate({"status": "verified", "reference": "RC-MH-2026-7701", "issued_on": "2026-01-01"}, rules)
        self.assertEqual(good.status, VALID)
        self.assertEqual(good.score, 1.0)

        bad = self.engine.evaluate({"status": "pending", "reference": "AB", "issued_on": None}, rules)
        self.assertEqual(bad.status, REJECTED)
        self.assertEqual(len(bad.errors), 3)


if __name__ == "__main__":
    unittest.main()
