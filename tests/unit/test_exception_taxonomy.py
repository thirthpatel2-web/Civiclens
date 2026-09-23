"""The exception taxonomy - pure, no database."""

from __future__ import annotations

import unittest

from app.interop.exceptions.taxonomy import EXCEPTION_TYPES, RETRYABLE_TYPES, classify, is_retryable


class TaxonomyTests(unittest.TestCase):
    def test_all_twenty_types_from_the_spec_are_present(self):
        self.assertEqual(len(EXCEPTION_TYPES), 20)

    def test_retryable_types_are_a_subset_of_all_types(self):
        self.assertTrue(RETRYABLE_TYPES.issubset(EXCEPTION_TYPES))

    def test_data_quality_failure_is_not_retryable(self):
        """Retrying a rejected document against the exact same source data would just fail again -
        this needs a human, not a retry loop."""
        self.assertFalse(is_retryable("DATA_QUALITY_FAILURE"))

    def test_connector_unavailable_is_retryable(self):
        self.assertTrue(is_retryable("CONNECTOR_UNAVAILABLE"))

    def test_classify_maps_every_known_gateway_reason(self):
        expected = {
            "document_not_found": "REMOTE_SYSTEM_ERROR",
            "data_quality_failed": "DATA_QUALITY_FAILURE",
            "data_field_not_consented": "AUTHORIZATION_FAILURE",
            "identity_ambiguous": "IDENTITY_AMBIGUOUS",
            "identity_conflict": "IDENTITY_CONFLICT",
            "source_record_not_found": "IDENTITY_NOT_FOUND",
            "consent_required": "CONSENT_REQUIRED",
        }
        for reason, code in expected.items():
            self.assertEqual(classify(reason), code)
            self.assertIn(code, EXCEPTION_TYPES)

    def test_an_unknown_reason_falls_back_to_remote_system_error_not_a_crash(self):
        self.assertEqual(classify("something_nobody_named_yet"), "REMOTE_SYSTEM_ERROR")


if __name__ == "__main__":
    unittest.main()
