import unittest
from datetime import timedelta

from app.core.exceptions import NotFound, PermissionDenied, ValidationFailed
from app.services.complaint_service import ComplaintInput
from app.services.complaint_status import ComplaintStatus as S
from app.services.reference import is_valid_reference
from tests.rag.helpers import ScriptedChat
from tests.support_env import CIT, CIT2, OFF_R1, PNG, POTHOLE, VAGUE, Env, complaint_input


class CreateTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()

    def test_full_pipeline_routes_assigns_sets_sla_notifies_and_audits(self):
        c = self.env.create()
        self.assertTrue(is_valid_reference(c.reference, "CL"))
        self.assertEqual((c.category, c.department_code, c.status, c.assigned_officer_id), ("roads", "roads", S.ASSIGNED, "off-roads-1"))
        self.assertEqual(c.routing["source"], "rule")
        self.assertEqual(c.routing["rule_id"], "r-roads")
        self.assertEqual(c.sla_due_at, c.created_at + timedelta(hours=72 if c.priority == "medium" else 24))
        events = self.env.stores.events[c.id]
        self.assertEqual([e.to_status for e in events], [S.SUBMITTED, S.AI_ROUTED, S.ASSIGNED])
        kinds = {(n.user_id, n.kind) for n in self.env.stores.notifications.values()}
        self.assertEqual(kinds, {("cit-1", "complaint.created"), ("off-roads-1", "complaint.assigned")})
        self.assertEqual([e.type for e in self.env.bus.events if e.type.startswith("complaint")], ["complaint.created", "complaint.assigned"])
        self.assertIn("complaint.created", self.env.actions())
        stored = self.env.stores.complaints[c.id]
        self.assertEqual(stored.reference, c.reference)

    def test_ai_enrichment_is_enqueued_after_commit_and_complaint_is_saved_without_a_model(self):
        c = self.env.create()
        self.assertEqual(c.ai_status, "not_needed")  # clear rules match: no model needed
        jobs = list(self.env.stores.jobs.values())
        self.assertEqual([(j.kind, j.payload, j.status) for j in jobs], [("complaint.enrich", {"complaint_id": c.id}, "queued")])
        self.assertEqual(len(self.env.backend.items), 1)

    def test_vague_complaint_is_saved_unrouted_with_honest_state(self):
        c = self.env.create(**VAGUE)
        self.assertEqual((c.category, c.department_code, c.status, c.assigned_officer_id), ("other", None, S.SUBMITTED, None))
        self.assertTrue(c.routing["manual_triage"])
        self.assertEqual(c.ai_status, "not_configured")  # no model configured; nothing invented
        self.assertEqual(Env(llm=ScriptedChat("x")).create(**VAGUE).ai_status, "pending")  # model configured: enrichment queued, not run inline
        self.assertEqual([e.type for e in self.env.bus.events if e.type == "complaint.assigned"], [])

    def test_assignment_balances_workload(self):
        a = self.env.create(title="Pothole one on road", description="A big pothole on the road near the market crossing", lat=12.90, lng=77.50)
        b = self.env.create(CIT2, title="Pothole two on road", description="A different big pothole on the road near the temple gate", lat=13.10, lng=77.70)
        self.assertEqual({a.assigned_officer_id, b.assigned_officer_id}, {"off-roads-1", "off-roads-2"})

    def test_client_request_id_makes_creation_idempotent(self):
        first = self.env.complaints.create(CIT, complaint_input(client_request_id="req-12345678"))
        second = self.env.complaints.create(CIT, complaint_input(client_request_id="req-12345678"))
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(first.complaint.id, second.complaint.id)
        self.assertEqual(len(self.env.stores.complaints), 1)
        self.assertEqual(len(self.env.stores.notifications), 2)
        self.assertEqual(len(self.env.stores.jobs), 1)
        other = self.env.complaints.create(CIT2, complaint_input(client_request_id="req-12345678"))  # same id, different user
        self.assertFalse(other.replayed)

    def test_validation_reports_every_field(self):
        with self.assertRaises(ValidationFailed) as cm:
            self.env.complaints.create(CIT, ComplaintInput("abc", "short", language="xx", category="dragons", complaint_type="alien", client_request_id="x"))
        self.assertEqual(set(cm.exception.details), {"title", "description", "language", "category", "complaint_type", "client_request_id"})
        with self.assertRaises(ValidationFailed):
            self.env.complaints.create(CIT, complaint_input(lat=91, lng=10))
        self.assertEqual(len(self.env.stores.complaints), 0)

    def test_only_citizens_create(self):
        with self.assertRaises(PermissionDenied):
            self.env.complaints.create(OFF_R1, complaint_input())

    def test_citizen_category_used_when_rules_are_ambiguous(self):
        c = self.env.create(category="water", **VAGUE)
        self.assertEqual((c.category, c.department_code, c.classification["source"]), ("water", "water", "citizen_selected"))

    def test_similar_complaints_are_flagged_not_merged(self):
        a = self.env.create()
        b = self.env.create(CIT2, title="Large pothole on MG Road", description="A very large pothole on the main road near the bus stop is causing accidents", lat=12.97161, lng=77.59461)
        self.assertEqual(len(self.env.stores.complaints), 2)
        self.assertEqual([d["complaint_id"] for d in b.duplicates], [a.id])
        self.assertEqual(b.duplicates[0]["verdict"], "possible_duplicate")
        self.assertEqual(a.duplicates, [])

    def test_redis_outage_never_blocks_or_loses_the_complaint(self):
        self.env.backend.up = False
        c = self.env.create()
        job = next(iter(self.env.stores.jobs.values()))
        self.assertEqual(job.status, "pending")  # honest: not queued
        self.assertIn(c.id, self.env.stores.complaints)
        self.env.backend.up = True
        self.env.clock.advance(minutes=5)
        self.assertEqual(self.env.jobs.requeue_orphans(), 1)
        self.assertEqual(next(iter(self.env.stores.jobs.values())).status, "queued")

    def test_failure_rolls_back_everything(self):
        with self.assertRaises(ValidationFailed):
            self.env.complaints.create(CIT, complaint_input(evidence_ids=["does-not-exist"]))
        s = self.env.stores
        self.assertEqual((len(s.complaints), len(s.events), len(s.notifications), len(s.jobs), len(s.audit)), (0, 0, 0, 0, 0))
        self.assertEqual(self.env.bus.events, [])
        self.assertEqual(self.env.backend.items, [])


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()

    def test_upload_validates_stores_and_marks_analysis_unavailable_without_provider(self):
        ev = self.env.complaints.upload_evidence(CIT, "photo.png", PNG)
        self.assertEqual((ev.mime, ev.analysis_status, ev.complaint_id), ("image/png", "IMAGE_ANALYSIS_UNAVAILABLE", None))
        self.assertIn(ev.storage_name, self.env.storage.files)
        self.assertIn("evidence.uploaded", self.env.actions())
        doc = self.env.complaints.upload_evidence(CIT, "note.txt", b"hello evidence")
        self.assertEqual(doc.analysis_status, "NOT_APPLICABLE")

    def test_pending_analysis_when_vision_configured(self):
        env = Env(vision=True)
        self.assertEqual(env.complaints.upload_evidence(CIT, "p.png", PNG).analysis_status, "PENDING")

    def test_rejects_bad_files(self):
        for name, data in [("a.exe", b"MZ"), ("a.png", b"not a png"), ("a.png", b"")]:
            with self.assertRaises(ValidationFailed):
                self.env.complaints.upload_evidence(CIT, name, data)
        with self.assertRaises(PermissionDenied):
            self.env.complaints.upload_evidence(OFF_R1, "a.png", PNG)

    def test_attach_at_creation_and_ownership_and_single_use(self):
        ev = self.env.complaints.upload_evidence(CIT, "photo.png", PNG)
        c = self.env.create(evidence_ids=[ev.id])
        self.assertEqual(self.env.stores.evidence[ev.id].complaint_id, c.id)
        with self.assertRaises(ValidationFailed):
            self.env.create(evidence_ids=[ev.id])  # already used
        stolen = self.env.complaints.upload_evidence(CIT2, "x.png", PNG)
        with self.assertRaises(ValidationFailed):
            self.env.create(evidence_ids=[stolen.id])  # someone else's upload


class CitizenReadTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.c = self.env.create()

    def test_detail_hides_internal_events_and_isolates_citizens(self):
        self.env.officer.remark(OFF_R1, self.c.id, "internal only note", internal=True)
        self.env.officer.remark(OFF_R1, self.c.id, "public update for citizen", internal=False)
        d = self.env.complaints.detail_for_citizen(CIT, self.c.id)
        remarks = [e.remarks for e in d["events"] if e.kind == "remark"]
        self.assertEqual(remarks, ["public update for citizen"])
        self.assertEqual([t.state for t in d["timeline"]], ["done", "done", "current", "upcoming", "upcoming", "upcoming"])
        self.assertEqual(d["timeline"][2].label, "Assigned")
        self.assertEqual(d["timeline"][2].state, "current")
        with self.assertRaises(NotFound):
            self.env.complaints.detail_for_citizen(CIT2, self.c.id)
        with self.assertRaises(NotFound):
            self.env.complaints.detail_for_citizen(CIT, "nope")

    def test_list_mine_filters_and_isolation(self):
        self.env.create(CIT2)
        mine = self.env.complaints.list_mine(CIT)
        self.assertEqual([c.id for c in mine], [self.c.id])
        self.assertEqual(len(self.env.complaints.list_mine(CIT, filter_name="active")), 1)
        self.assertEqual(self.env.complaints.list_mine(CIT, filter_name="resolved"), [])
        self.assertEqual(len(self.env.complaints.list_mine(CIT, filter_name="municipal")), 1)
        self.assertEqual(self.env.complaints.list_mine(CIT, filter_name="rti"), [])

    def test_feedback_rules(self):
        with self.assertRaises(ValidationFailed):
            self.env.complaints.add_feedback(CIT, self.c.id, 5, "great")  # not resolved yet
        for target, note in [(S.UNDER_REVIEW, None), (S.IN_PROGRESS, None), (S.RESOLVED, "Filled the pothole")]:
            self.env.officer.update_status(OFF_R1, self.c.id, target, note)
        for bad in (0, 6, True, "5", 4.5):
            with self.assertRaises(ValidationFailed, msg=bad):
                self.env.complaints.add_feedback(CIT, self.c.id, bad, None)  # type: ignore[arg-type]
        with self.assertRaises(NotFound):
            self.env.complaints.add_feedback(CIT2, self.c.id, 5, None)
        fb = self.env.complaints.add_feedback(CIT, self.c.id, 4, " good work ")
        self.assertEqual((fb.rating, fb.comment), (4, "good work"))
        from app.core.exceptions import Conflict

        with self.assertRaises(Conflict):
            self.env.complaints.add_feedback(CIT, self.c.id, 5, None)
        self.assertIn("complaint.feedback", self.env.actions())


if __name__ == "__main__":
    unittest.main()
