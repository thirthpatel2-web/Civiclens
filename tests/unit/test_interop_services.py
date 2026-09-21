"""Golden Record linking, the integration exception queue, cross-portal tracking, and the
classification-correction learning-loop capture - all against in-memory doubles."""

from __future__ import annotations

import unittest

from app.core.exceptions import NotFound, PermissionDenied, ValidationFailed
from app.services.interop_service import ExceptionService, ExternalLinksService, MasterDataService
from tests.support_env import ADMIN, CIT, CIT2, OFF_R1, OFF_W1, Env


class MasterDataServiceTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.svc = MasterDataService(self.env.factory, secret="test-secret-key-not-used-for-anything-real")

    def test_linking_never_stores_the_raw_value(self):
        rec = self.svc.link(CIT, "pan", "ABCDE1234F")
        self.assertNotIn("ABCDE1234F", rec.id_hash)
        self.assertEqual(rec.last4, "234F")
        self.assertEqual(rec.user_id, CIT.user_id)

    def test_the_same_id_cannot_be_linked_to_two_different_profiles(self):
        self.svc.link(CIT, "pan", "ABCDE1234F")
        with self.assertRaises(ValidationFailed):
            self.svc.link(CIT2, "pan", "ABCDE1234F")

    def test_normalization_catches_case_and_whitespace_variants_of_the_same_id(self):
        self.svc.link(CIT, "pan", "ABCDE1234F")
        with self.assertRaises(ValidationFailed):
            self.svc.link(CIT2, "pan", " abcde1234f ")

    def test_unknown_id_type_is_rejected(self):
        with self.assertRaises(ValidationFailed):
            self.svc.link(CIT, "not_a_real_id_type", "12345678")

    def test_list_mine_is_scoped_to_the_caller(self):
        self.svc.link(CIT, "pan", "ABCDE1234F")
        self.svc.link(CIT2, "voter_id", "XYZ1234567")
        self.assertEqual(len(self.svc.list_mine(CIT)), 1)
        self.assertEqual(len(self.svc.list_mine(CIT2)), 1)

    def test_unlink_only_works_for_the_owner(self):
        rec = self.svc.link(CIT, "pan", "ABCDE1234F")
        with self.assertRaises(NotFound):
            self.svc.unlink(CIT2, rec.id)
        self.svc.unlink(CIT, rec.id)
        self.assertEqual(self.svc.list_mine(CIT), [])


class ExceptionServiceTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.svc = ExceptionService(self.env.factory)

    def test_log_then_admin_can_list_and_resolve(self):
        rec = self.svc.log(source_system="municipal_legacy", reason="missing external reference id", payload={"a": 1})
        self.assertEqual(self.svc.counts(ADMIN), {"open": 1})
        self.svc.resolve(ADMIN, rec.id, note="reviewed, was a test payload")
        self.assertEqual(self.svc.counts(ADMIN), {"resolved": 1})

    def test_a_citizen_cannot_view_the_exception_queue(self):
        self.svc.log(source_system="x", reason="y", payload={})
        with self.assertRaises(PermissionDenied):
            self.svc.list(CIT)

    def test_resolving_an_unknown_exception_raises_not_found(self):
        with self.assertRaises(NotFound):
            self.svc.resolve(ADMIN, "does-not-exist", note="")


class ExternalLinksServiceTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.svc = ExternalLinksService(self.env.factory)

    def test_add_requires_the_core_fields(self):
        with self.assertRaises(ValidationFailed):
            self.svc.add(CIT, platform="", external_reference="", title="")

    def test_add_then_list_is_scoped_per_citizen(self):
        self.svc.add(CIT, platform="CPGRAMS", external_reference="CPG-2026-001", title="Streetlight complaint")
        self.svc.add(CIT2, platform="Sevottam", external_reference="SEV-2026-002", title="Water issue")
        self.assertEqual(len(self.svc.list_mine(CIT)), 1)
        self.assertEqual(self.svc.list_mine(CIT)[0].platform, "CPGRAMS")

    def test_remove_only_works_for_the_owner(self):
        rec = self.svc.add(CIT, platform="CPGRAMS", external_reference="CPG-1", title="Test")
        with self.assertRaises(NotFound):
            self.svc.remove(CIT2, rec.id)
        self.svc.remove(CIT, rec.id)
        self.assertEqual(self.svc.list_mine(CIT), [])


class CorrectCategoryTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.c = self.env.create()  # category="roads", department "roads", assigned off-roads-1

    def test_officer_in_the_right_department_can_correct_the_category(self):
        updated = self.env.officer.correct_category(OFF_R1, self.c.id, "drainage")
        self.assertEqual(updated.category, "drainage")
        corrections = self.env.uow().classification_corrections.list_recent()
        self.assertEqual(len(corrections), 1)
        self.assertEqual((corrections[0].previous_category, corrections[0].corrected_category), ("roads", "drainage"))

    def test_officer_in_a_different_department_cannot_correct_it(self):
        with self.assertRaises(NotFound):
            self.env.officer.correct_category(OFF_W1, self.c.id, "drainage")

    def test_unknown_category_is_rejected(self):
        with self.assertRaises(ValidationFailed):
            self.env.officer.correct_category(OFF_R1, self.c.id, "not_a_real_category")

    def test_correcting_to_the_same_category_is_a_no_op(self):
        self.env.officer.correct_category(OFF_R1, self.c.id, "roads")
        corrections = self.env.uow().classification_corrections.list_recent()
        self.assertEqual(corrections, [])


if __name__ == "__main__":
    unittest.main()
