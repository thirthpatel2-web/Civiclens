"""Verified closure: a citizen can send a "resolved" complaint back when it was not actually fixed."""

from __future__ import annotations

import unittest

from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.services.complaint_status import ComplaintStatus as S
from tests.support_env import CIT, CIT2, OFF_R1, Env


class CitizenReopenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = Env()
        self.c = self.env.create()  # roads, assigned to off-roads-1
        self.env.officer.update_status(OFF_R1, self.c.id, S.UNDER_REVIEW, "checking")
        self.env.officer.resolve(OFF_R1, self.c.id, "Filled the pothole")

    def test_the_citizen_can_reopen_with_a_reason_and_the_officer_hears_about_it(self) -> None:
        out = self.env.complaints.reopen_by_citizen(CIT, self.c.id, "The pothole is back after one day of rain")
        self.assertEqual((out.status, out.resolved_at), (S.IN_PROGRESS, None))
        self.assertIn("complaint.reopened_by_citizen", self.env.actions())
        kinds = [n.kind for n in self.env.stores.notifications.values() if n.user_id == "off-roads-1"]
        self.assertIn("complaint.reopened", kinds)

    def test_only_the_owner_only_with_a_reason_and_only_once_rated_is_final(self) -> None:
        with self.assertRaises(NotFound):
            self.env.complaints.reopen_by_citizen(CIT2, self.c.id, "not mine but still")
        with self.assertRaises(ValidationFailed):
            self.env.complaints.reopen_by_citizen(CIT, self.c.id, " ")
        self.env.complaints.add_feedback(CIT, self.c.id, 5, "fixed")
        with self.assertRaises(Conflict):
            self.env.complaints.reopen_by_citizen(CIT, self.c.id, "changed my mind")

    def test_the_window_closes_after_thirty_days(self) -> None:
        self.env.clock.advance(days=31)
        with self.assertRaises(ValidationFailed):
            self.env.complaints.reopen_by_citizen(CIT, self.c.id, "It broke again this month")

    def test_ratings_become_the_departments_satisfaction_score(self) -> None:
        from app.services.dashboard_service import DashboardService

        dash = DashboardService(self.env.factory, self.env.clock)
        self.assertIsNone(dash.department(OFF_R1)["satisfaction"])
        self.env.complaints.add_feedback(CIT, self.c.id, 4, "fixed, took a while")
        self.assertEqual(dash.department(OFF_R1)["satisfaction"], {"average": 4.0, "count": 1})


if __name__ == "__main__":
    unittest.main()
