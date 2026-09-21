"""Interoperability layer: every adapter normalizes its fixture correctly, and the quality
scorer genuinely distinguishes a well-formed record from a malformed one (not a rubber stamp)."""

from __future__ import annotations

import unittest

from app.interop.adapters import SYSTEMS
from app.interop.common_data_model import CANONICAL_STATUSES, CanonicalRecord, score_quality
from app.interop.fragmentation import personal_diagnostic


class AdapterTests(unittest.TestCase):
    def test_every_system_normalizes_its_own_fixture_to_a_valid_canonical_record(self) -> None:
        for key, (label, fixture, adapt) in SYSTEMS.items():
            with self.subTest(system=key):
                record = adapt(fixture)
                self.assertIsInstance(record, CanonicalRecord)
                self.assertEqual(record.source_system, key)
                self.assertTrue(record.external_id, f"{label} adapter produced no external id")
                self.assertIn(record.status, CANONICAL_STATUSES)
                self.assertTrue(record.title)
                self.assertTrue(record.department)

    def test_status_vocabularies_are_reconciled_to_the_same_canonical_set(self) -> None:
        # Each source system spells "being worked on" differently; all four must agree once normalized.
        in_progress = {adapt(fixture).status for _label, fixture, adapt in SYSTEMS.values()}
        self.assertEqual(in_progress, {"in_progress"})

    def test_unrecognized_status_maps_to_unknown_not_a_guess(self) -> None:
        from app.interop.adapters import from_state_portal

        rec = from_state_portal({"ref_no": "X", "status_code": 999, "service_name": "test", "dept_code": "X"})
        self.assertEqual(rec.status, "unknown")


class QualityScoreTests(unittest.TestCase):
    def test_a_complete_well_formed_record_scores_highly(self) -> None:
        rec = CanonicalRecord(
            source_system="test", external_id="X-1", category="roads", status="received", title="Pothole on Main Street",
            department="PWD", citizen_name="A Citizen", citizen_contact="9845012345", location="Ward 4", filed_on="2026-09-01",
        )
        report = score_quality(rec)
        self.assertEqual(report.grade, "excellent")
        self.assertEqual(report.issues, ())

    def test_a_malformed_record_is_flagged_not_silently_accepted(self) -> None:
        rec = CanonicalRecord(source_system="test", external_id="", category="x", status="not_a_real_status", title="ab", department="")
        report = score_quality(rec)
        self.assertEqual(report.grade, "unusable")
        self.assertIn("missing external reference id", report.issues)
        self.assertIn("status 'not_a_real_status' did not normalize to a known canonical status", report.issues)

    def test_bad_phone_format_is_caught(self) -> None:
        rec = CanonicalRecord(source_system="test", external_id="X-1", category="roads", status="received", title="Valid title", department="PWD", citizen_contact="12345")
        report = score_quality(rec)
        self.assertTrue(any("mobile" in issue for issue in report.issues))

    def test_unparseable_date_is_caught(self) -> None:
        rec = CanonicalRecord(source_system="test", external_id="X-1", category="roads", status="received", title="Valid title", department="PWD", filed_on="whenever")
        report = score_quality(rec)
        self.assertTrue(any("filed_on" in issue for issue in report.issues))


class FragmentationDiagnosticTests(unittest.TestCase):
    def test_counts_distinct_departments_and_reuses(self) -> None:
        diag = personal_diagnostic(["roads", "water", "roads", None, "police"])
        self.assertEqual(diag.distinct_departments, 3)
        self.assertEqual(diag.total_filings, 4)
        self.assertEqual(diag.profile_reuses, 3)

    def test_empty_history_is_zero_not_fabricated(self) -> None:
        diag = personal_diagnostic([])
        self.assertEqual((diag.distinct_departments, diag.total_filings, diag.profile_reuses), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
