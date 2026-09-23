"""Canonical v1 model + transform tests - pure, no database. See
tests/integration/test_connectors.py for the connector implementations these transforms sit
behind (those need a real database, since the mock systems are real persisted tables)."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import UTC, datetime

from app.interop.canonical.v1.models import CANONICAL_APPLICATION_STATES, Application, Document
from app.interop.canonical.v1.transform import (
    canonical_document_to_dept_b_fields,
    canonical_status_to_dept_b_status,
    dept_a_document_to_canonical,
    dept_b_application_to_canonical,
)


@dataclass
class _FakeDeptADocument:
    document_id: str
    resident_id: str
    document_type: str
    status: str
    reference_no: str
    issued_on: datetime | None


@dataclass
class _FakeDeptBApplication:
    application_no: str
    beneficiary_code: str
    service_type: str
    status: str
    document_status: str


class ApplicationStateTests(unittest.TestCase):
    def test_all_eleven_canonical_states_are_distinct(self):
        self.assertEqual(len(CANONICAL_APPLICATION_STATES), 11)
        self.assertEqual(len(set(CANONICAL_APPLICATION_STATES)), 11)

    def test_application_rejects_a_non_canonical_status(self):
        with self.assertRaises(ValueError):
            Application(application_id="x", reference="x", service_id=None, master_id=None, primary_system="dept_b", status="made_up_status")

    def test_application_accepts_every_canonical_status(self):
        for status in CANONICAL_APPLICATION_STATES:
            Application(application_id="x", reference="x", service_id=None, master_id=None, primary_system="dept_b", status=status)


class DeptATransformTests(unittest.TestCase):
    def test_document_to_canonical_carries_the_real_fields(self):
        doc = _FakeDeptADocument(document_id="d1", resident_id="RES-MH-00101", document_type="residence_certificate", status="verified", reference_no="RC-MH-2026-7701", issued_on=datetime(2026, 1, 5, tzinfo=UTC))
        canonical = dept_a_document_to_canonical(doc)
        self.assertIsInstance(canonical, Document)
        self.assertEqual(canonical.reference, "RC-MH-2026-7701")
        self.assertEqual(canonical.status, "verified")
        self.assertEqual(canonical.source_system, "dept_a")
        self.assertEqual(canonical.issued_on.isoformat(), "2026-01-05")
        self.assertEqual(canonical.raw["resident_id"], "RES-MH-00101")

    def test_document_to_canonical_handles_a_missing_issue_date(self):
        doc = _FakeDeptADocument(document_id="d2", resident_id="RES-MH-00102", document_type="residence_certificate", status="pending", reference_no="RC-MH-2026-7702", issued_on=None)
        self.assertIsNone(dept_a_document_to_canonical(doc).issued_on)

    def test_canonical_document_to_dept_b_fields_sends_only_what_dept_b_needs(self):
        canonical = Document(document_id="d1", document_type="residence_certificate", reference="RC-MH-2026-7701", status="verified", source_system="dept_a", raw={"resident_id": "RES-MH-00101", "some_other_field": "should not leak"})
        fields = canonical_document_to_dept_b_fields(canonical)
        self.assertEqual(fields, {"document_reference": "RC-MH-2026-7701", "document_status": "verified"})
        self.assertNotIn("resident_id", fields)
        self.assertNotIn("some_other_field", fields)

    def test_canonical_document_to_dept_b_fields_does_not_claim_verified_for_an_unverified_source(self):
        canonical = Document(document_id="d3", document_type="residence_certificate", reference="RC-MH-2026-7703", status="pending", source_system="dept_a")
        self.assertEqual(canonical_document_to_dept_b_fields(canonical)["document_status"], "pending")


class DeptBTransformTests(unittest.TestCase):
    def test_every_dept_b_status_maps_to_a_canonical_state(self):
        for dept_b_status in ("pending_document", "processing", "approved", "rejected"):
            app_row = _FakeDeptBApplication(application_no="APP-1", beneficiary_code="BEN-1", service_type="Small Business Registration", status=dept_b_status, document_status="missing")
            canonical = dept_b_application_to_canonical(app_row, master_id="m-1")
            self.assertIn(canonical.status, CANONICAL_APPLICATION_STATES)

    def test_pending_document_maps_to_waiting_for_external_system(self):
        app_row = _FakeDeptBApplication(application_no="APP-1", beneficiary_code="BEN-1", service_type="x", status="pending_document", document_status="missing")
        self.assertEqual(dept_b_application_to_canonical(app_row, master_id=None).status, "WAITING_FOR_EXTERNAL_SYSTEM")

    def test_an_unrecognized_dept_b_status_falls_back_to_in_progress_rather_than_crashing(self):
        app_row = _FakeDeptBApplication(application_no="APP-1", beneficiary_code="BEN-1", service_type="x", status="some_new_status_dept_b_added", document_status="missing")
        self.assertEqual(dept_b_application_to_canonical(app_row, master_id=None).status, "IN_PROGRESS")

    def test_canonical_status_round_trips_back_to_dept_bs_own_vocabulary(self):
        self.assertEqual(canonical_status_to_dept_b_status("APPROVED"), "approved")
        self.assertEqual(canonical_status_to_dept_b_status("REJECTED"), "rejected")
        self.assertEqual(canonical_status_to_dept_b_status("WAITING_FOR_EXTERNAL_SYSTEM"), "pending_document")

    def test_master_id_is_carried_through_unchanged(self):
        app_row = _FakeDeptBApplication(application_no="APP-1", beneficiary_code="BEN-1", service_type="x", status="processing", document_status="verified")
        self.assertEqual(dept_b_application_to_canonical(app_row, master_id="master-42").master_id, "master-42")
        self.assertIsNone(dept_b_application_to_canonical(app_row, master_id=None).master_id)


if __name__ == "__main__":
    unittest.main()
