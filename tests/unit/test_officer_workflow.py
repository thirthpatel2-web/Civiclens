import unittest
from datetime import timedelta

from app.core.exceptions import NotFound, PermissionDenied, ValidationFailed
from app.services.complaint_status import ComplaintStatus as S
from tests.support_env import ADMIN, ADMIN_ROADS, CIT, OFF_R1, OFF_R2, OFF_W1, VAGUE, Env


class OfficerTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.c = self.env.create()  # roads, assigned off-roads-1
        self.w = self.env.create(title="No water in the tap", description="There has been no water supply in our street for two days now", lat=13.5, lng=77.9)
        self.env.bus.events.clear()

    # ---------------------------------------------------------------- isolation
    def test_queue_is_scoped_to_the_officers_department_in_the_query(self):
        self.assertEqual([x.id for x in self.env.officer.queue(OFF_R1)], [self.c.id])
        self.assertEqual([x.id for x in self.env.officer.queue(OFF_W1)], [self.w.id])
        self.assertEqual([x.id for x in self.env.officer.queue(OFF_R2, mine_only=True)], [])
        self.assertEqual([x.id for x in self.env.officer.queue(OFF_R1, mine_only=True)], [self.c.id])
        self.assertEqual(self.env.officer.queue(OFF_R1, statuses=[S.RESOLVED]), [])

    def test_cross_department_and_citizen_access_denied(self):
        with self.assertRaises(NotFound):
            self.env.officer.detail(OFF_W1, self.c.id)
        with self.assertRaises(NotFound):
            self.env.officer.update_status(OFF_W1, self.c.id, S.UNDER_REVIEW)
        with self.assertRaises(PermissionDenied):
            self.env.officer.queue(CIT)
        with self.assertRaises(PermissionDenied):
            self.env.officer.update_status(CIT, self.c.id, S.UNDER_REVIEW)
        self.assertEqual(self.env.stores.complaints[self.c.id].status, S.ASSIGNED)

    def test_officer_without_department_sees_nothing(self):
        from app.core.authorization import AuthContext, Role

        with self.assertRaises(PermissionDenied):
            self.env.officer.queue(AuthContext("x", Role.OFFICER, None))

    def test_detail_includes_internal_events_sla_and_is_audited(self):
        self.env.officer.remark(OFF_R1, self.c.id, "secret internal note")
        d = self.env.officer.detail(OFF_R1, self.c.id)
        self.assertIn("secret internal note", [e.remarks for e in d["events"]])
        self.assertEqual(d["sla"].state, "on_track")
        self.assertIn("complaint.viewed", self.env.actions())

    # ---------------------------------------------------------------- transitions
    def test_status_flow_to_resolution_creates_events_notifications_and_realtime(self):
        self.env.officer.update_status(OFF_R1, self.c.id, S.UNDER_REVIEW)
        self.env.officer.update_status(OFF_R1, self.c.id, S.IN_PROGRESS, "crew dispatched")
        self.env.clock.advance(hours=5)
        done = self.env.officer.resolve(OFF_R1, self.c.id, "Pothole filled and compacted")
        self.assertEqual((done.status, done.resolved_at), (S.RESOLVED, self.env.clock.now))
        status_events = [e for e in self.env.stores.events[self.c.id] if e.kind == "status_change" and e.actor_id == "off-roads-1"]
        self.assertEqual([e.to_status for e in status_events], [S.UNDER_REVIEW, S.IN_PROGRESS, S.RESOLVED])
        self.assertEqual(status_events[-1].remarks, "Pothole filled and compacted")
        self.assertEqual(status_events[-1].actor_label, "Officer R1")
        kinds = [n.kind for n in self.env.stores.notifications.values() if n.user_id == "cit-1"]
        self.assertIn("complaint.resolved", kinds)
        rt = self.env.bus.of("complaint.status_changed")
        self.assertEqual([e.payload["to"] for e in rt], ["under_review", "in_progress", "resolved"])
        self.assertTrue(all(e.owner_id == "cit-1" and e.department_code == "roads" for e in rt))
        self.assertEqual(self.env.actions().count("complaint.status_changed"), 3)

    def test_illegal_transition_or_missing_remark_changes_nothing(self):
        with self.assertRaises(ValidationFailed):
            self.env.officer.update_status(OFF_R1, self.c.id, S.RESOLVED, "skipping review")  # ASSIGNED -> RESOLVED not allowed
        self.env.officer.update_status(OFF_R1, self.c.id, S.UNDER_REVIEW)
        with self.assertRaises(ValidationFailed):
            self.env.officer.update_status(OFF_R1, self.c.id, S.RESOLVED, "  ")
        self.assertEqual(self.env.stores.complaints[self.c.id].status, S.UNDER_REVIEW)
        self.assertEqual(len(self.env.bus.of("complaint.status_changed")), 1)

    def test_reopen_after_resolution_clears_resolved_at(self):
        for t, r in [(S.UNDER_REVIEW, None), (S.RESOLVED, "done")]:
            self.env.officer.update_status(OFF_R1, self.c.id, t, r)
        reopened = self.env.officer.update_status(OFF_R1, self.c.id, S.IN_PROGRESS, "citizen reports it recurred")
        self.assertEqual((reopened.status, reopened.resolved_at), (S.IN_PROGRESS, None))

    # ---------------------------------------------------------------- assignment
    def test_reassignment_stays_in_department_and_is_recorded(self):
        moved = self.env.officer.assign(OFF_R1, self.c.id, "off-roads-2")
        self.assertEqual(moved.assigned_officer_id, "off-roads-2")
        ev = [e for e in self.env.stores.events[self.c.id] if e.kind == "assigned"][-1]
        self.assertEqual(ev.details["previous_officer_id"], "off-roads-1")
        self.assertIn(("off-roads-2", "complaint.assigned"), {(n.user_id, n.kind) for n in self.env.stores.notifications.values()})
        with self.assertRaises(ValidationFailed):
            self.env.officer.assign(OFF_R1, self.c.id, "off-water-1")  # other department's officer
        with self.assertRaises(NotFound):
            self.env.officer.assign(OFF_W1, self.c.id, "off-water-1")

    def test_triage_by_admin_only_and_only_for_unrouted(self):
        v = self.env.create(**VAGUE)
        with self.assertRaises(PermissionDenied):
            self.env.officer.triage(OFF_R1, v.id, "roads")
        with self.assertRaises(PermissionDenied):
            self.env.officer.triage(ADMIN_ROADS, v.id, "water")  # admin bound to roads
        with self.assertRaises(ValidationFailed):
            self.env.officer.triage(ADMIN, v.id, "atlantis")
        routed = self.env.officer.triage(ADMIN, v.id, "water")
        self.assertEqual((routed.department_code, routed.status, routed.routing["source"]), ("water", S.AI_ROUTED, "manual"))
        with self.assertRaises(ValidationFailed):
            self.env.officer.triage(ADMIN, self.c.id, "water")  # already routed
        assigned = self.env.officer.assign(OFF_W1, v.id, "off-water-1")
        self.assertEqual(assigned.status, S.ASSIGNED)

    # ---------------------------------------------------------------- field actions
    def test_field_visit_inspection_work_order_progress_coordination(self):
        self.env.officer.update_status(OFF_R1, self.c.id, S.UNDER_REVIEW)
        when = self.env.clock.now + timedelta(days=1)
        c = self.env.officer.field_visit(OFF_R1, self.c.id, when, "site check")
        self.assertEqual(c.status, S.INSPECTION_SCHEDULED)
        self.env.officer.inspection(OFF_R1, self.c.id, "Pothole 40cm wide, 8cm deep")
        c = self.env.officer.work_order(OFF_R1, self.c.id, "WO-2026-118", "Cold-mix patching", "Crew B")
        self.assertEqual(c.status, S.IN_PROGRESS)
        self.env.officer.progress(OFF_R1, self.c.id, 60, "half done")
        self.env.officer.coordination_note(OFF_R1, self.c.id, "Electricity Board", "Cable marking needed first")
        kinds = [e.kind for e in self.env.stores.events[self.c.id]]
        for k in ("field_visit", "inspection", "work_order", "progress", "coordination"):
            self.assertIn(k, kinds)
        coord = next(e for e in self.env.stores.events[self.c.id] if e.kind == "coordination")
        self.assertTrue(coord.internal)
        for a in ("complaint.field_visit", "complaint.inspection", "complaint.work_order", "complaint.progress", "complaint.coordination"):
            self.assertIn(a, self.env.actions())

    def test_field_action_validation_and_finished_guard(self):
        for fn in (lambda: self.env.officer.progress(OFF_R1, self.c.id, 101), lambda: self.env.officer.progress(OFF_R1, self.c.id, True),
                   lambda: self.env.officer.inspection(OFF_R1, self.c.id, " "), lambda: self.env.officer.work_order(OFF_R1, self.c.id, "", "x"),
                   lambda: self.env.officer.remark(OFF_R1, self.c.id, " ")):  # fmt: skip
            with self.assertRaises(ValidationFailed):
                fn()
        for t, r in [(S.UNDER_REVIEW, None), (S.RESOLVED, "done")]:
            self.env.officer.update_status(OFF_R1, self.c.id, t, r)
        self.env.officer.update_status(OFF_R1, self.c.id, S.IN_PROGRESS, "reopen")
        self.env.officer.resolve(OFF_R1, self.c.id, "fixed again")
        self.env.officer.update_status(OFF_R1, self.c.id, S.CLOSED)
        with self.assertRaises(ValidationFailed):
            self.env.officer.remark(OFF_R1, self.c.id, "too late")

    # ---------------------------------------------------------------- escalation
    def test_manual_escalation_levels_and_notifications(self):
        with self.assertRaises(ValidationFailed):
            self.env.officer.escalate(OFF_R1, self.c.id, " ")
        for level in (1, 2, 3):
            c = self.env.officer.escalate(OFF_R1, self.c.id, f"reason {level}")
            self.assertEqual(c.escalation_level, level)
        with self.assertRaises(ValidationFailed):
            self.env.officer.escalate(OFF_R1, self.c.id, "again")
        self.assertIn(("admin-1", "complaint.escalated"), {(n.user_id, n.kind) for n in self.env.stores.notifications.values()})
        esc = self.env.bus.of("complaint.escalated")
        self.assertEqual([e.payload["level"] for e in esc], [1, 2, 3])
        self.assertEqual(esc[0].internal["reason"], "reason 1")


class SlaScanTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()

    def test_overdue_complaint_is_escalated_once_per_step_with_notifications(self):
        c = self.env.create(title="Pothole causing accidents", description="A deep pothole on the road near the school gate keeps causing accidents", lat=12.9, lng=77.5)
        self.assertEqual((c.priority, c.assigned_officer_id, (c.sla_due_at - c.created_at)), ("critical", "off-roads-1", timedelta(hours=8)))
        self.env.bus.events.clear()
        self.env.clock.advance(hours=1)
        self.assertEqual(self.env.sla.scan(self.env.clock.now)["escalated"], 0)
        due = c.sla_due_at
        self.env.clock.now = due + timedelta(minutes=1)
        r = self.env.sla.scan(self.env.clock.now)
        self.assertEqual((r["breached"], r["escalated"]), (1, 1))
        stored = self.env.stores.complaints[c.id]
        self.assertEqual((stored.escalation_level, stored.escalated_at), (1, self.env.clock.now))
        self.assertEqual(self.env.sla.scan(self.env.clock.now)["escalated"], 0)  # idempotent within the gap
        self.assertEqual([e.payload["level"] for e in self.env.bus.of("complaint.escalated")], [1])
        recipients = {n.user_id for n in self.env.stores.notifications.values() if n.kind == "complaint.escalated"}
        self.assertEqual(recipients, {"admin-1", "off-roads-1"})  # admin + the responsible officer
        self.env.clock.advance(hours=49)
        self.assertEqual(self.env.stores.complaints[c.id].escalation_level, 1)
        self.env.sla.scan(self.env.clock.now)
        self.assertEqual(self.env.stores.complaints[c.id].escalation_level, 2)
        sys_events = [e for e in self.env.stores.events[c.id] if e.kind == "escalated"]
        self.assertTrue(all(e.actor_id is None and e.actor_label == "SLA monitor" for e in sys_events))

    def test_at_risk_warning_is_sent_once_and_finished_complaints_are_ignored(self):
        c = self.env.create()
        window = c.sla_due_at - c.created_at
        self.env.clock.now = c.sla_due_at - window * 0.1
        r = self.env.sla.scan(self.env.clock.now)
        self.assertEqual((r["at_risk"], r["at_risk_notified"]), (1, 1))
        self.assertEqual(self.env.sla.scan(self.env.clock.now)["at_risk_notified"], 0)  # deduped
        for t, note in [(S.UNDER_REVIEW, None), (S.RESOLVED, "done")]:
            self.env.officer.update_status(OFF_R1, c.id, t, note)
        self.env.clock.now = c.sla_due_at + timedelta(days=30)
        self.assertEqual(self.env.sla.scan(self.env.clock.now), {"scanned": 0, "at_risk": 0, "breached": 0, "escalated": 0, "at_risk_notified": 0})


if __name__ == "__main__":
    unittest.main()
