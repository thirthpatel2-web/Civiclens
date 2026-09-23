"""The field mapping catalog (app.interop.catalog.DEFAULT_FIELD_MAPPINGS) is a DATA description of
what app.interop.canonical.v1.transform's real functions do - this cross-checks every seeded row
against the real functions' actual behavior on realistic fixture input, so the catalog can never
silently drift from the code it claims to describe. Pure, no database."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import UTC, datetime

from app.interop.canonical.v1.transform import canonical_document_to_dept_b_fields, dept_a_document_to_canonical
from app.interop.catalog import DEFAULT_FIELD_MAPPINGS, DEFAULT_SERVICES


@dataclass
class _FakeDeptADocument:
    document_id: str = "DOC-1"
    document_type: str = "residence_certificate"
    reference_no: str = "RC-2026-0001"
    status: str = "verified"
    issued_on: datetime = datetime(2026, 1, 15, tzinfo=UTC)
    resident_id: str = "RES-1"


class FieldMappingCatalogTests(unittest.TestCase):
    def setUp(self):
        self.by_id = {m["mapping_id"]: m for m in DEFAULT_FIELD_MAPPINGS}
        self.service_ids = {s["service_id"] for s in DEFAULT_SERVICES}

    def test_every_mapping_points_at_a_real_service(self):
        for m in DEFAULT_FIELD_MAPPINGS:
            self.assertIn(m["service_id"], self.service_ids, m["mapping_id"])

    def test_external_to_canonical_mappings_match_dept_a_document_to_canonical(self):
        """Every "external_to_canonical"/dept_a/Document row must describe a real attribute the
        function actually reads, mapped to the real attribute it actually sets."""
        fake = _FakeDeptADocument()
        canonical = dept_a_document_to_canonical(fake)
        rows = [m for m in DEFAULT_FIELD_MAPPINGS if m["direction"] == "external_to_canonical" and m["system_id"] == "dept_a" and m["entity"] == "Document"]
        self.assertTrue(rows)
        for m in rows:
            source_value = getattr(fake, m["source_field"])
            target_value = getattr(canonical, m["target_field"])
            if m["source_field"] == "issued_on":
                self.assertEqual(target_value, source_value.date())
            else:
                self.assertEqual(target_value, source_value, m["mapping_id"])

    def test_canonical_to_external_mappings_match_canonical_document_to_dept_b_fields(self):
        fake = _FakeDeptADocument()
        canonical = dept_a_document_to_canonical(fake)
        dept_b_fields = canonical_document_to_dept_b_fields(canonical)
        rows = [m for m in DEFAULT_FIELD_MAPPINGS if m["direction"] == "canonical_to_external" and m["system_id"] == "dept_b" and m["entity"] == "Document"]
        self.assertTrue(rows)
        for m in rows:
            source_value = getattr(canonical, m["source_field"])
            self.assertEqual(dept_b_fields[m["target_field"]], source_value, m["mapping_id"])

    def test_every_mapping_id_is_unique(self):
        ids = [m["mapping_id"] for m in DEFAULT_FIELD_MAPPINGS]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
