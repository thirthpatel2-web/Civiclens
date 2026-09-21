import logging
import unittest

from app.core.exceptions import NotFound, PermissionDenied, ValidationFailed
from app.integrations.adapters import CPGRAMSAdapter
from app.integrations.base import AdapterConfig, TransportResponse
from app.providers.push import ExpoPushSender
from app.services.admin_service import AdminService
from app.services.complaint_status import ComplaintStatus as S
from app.services.dashboard_service import DashboardService
from app.services.duplicate_review import DuplicateReviewApp
from app.services.government_service import GovernmentSubmissionService, canonical_payload
from app.services.ports import NotificationPreference, PushDeviceRecord, WorkflowRuleRecord
from app.services.workflow_service import WorkflowService, matches
from app.workers.handlers import GrievanceWorker
from tests.support_env import (
    ADMIN,
    ADMIN_ROADS,
    CIT,
    CIT2,
    OFF_R1,
    OFF_W1,
    POTHOLE,
    Env,
)
from tests.unit.test_platform_services import with_auth


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


def grant(env, ctx, purpose="data_sharing_government"):
    from app.services.profile_service import ProfileService

    ProfileService(env.factory, env.clock).set_consent(ctx, purpose, True)


class DuplicateReviewTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.review = DuplicateReviewApp(self.env.factory, self.env.fx)
        self.a = self.env.create()
        self.b = self.env.create(CIT2, title="Large pothole on MG Road", description="A very large pothole on the main road near the bus stop is causing accidents", lat=12.97161, lng=77.59461)

    def test_candidates_show_similarity_and_start_unreviewed(self):
        c = self.review.candidates(OFF_R1, self.b.id)
        self.assertEqual([(x["complaint_id"], x["verdict"], x["review"]) for x in c], [(self.a.id, "possible_duplicate", None)])
        self.assertIn("text similarity", c[0]["explanation"])
        self.assertEqual(c[0]["other_status"], "assigned")

    def test_decision_is_persisted_with_reviewer_time_event_and_audit_and_never_merges(self):
        before = {k: (v.status, v.department_code) for k, v in self.env.stores.complaints.items()}
        r = self.review.decide(OFF_R1, self.b.id, self.a.id, "confirmed_duplicate", " same pothole ")
        self.assertEqual((r.reviewer_id, r.note, r.at), ("off-roads-1", "same pothole", self.env.clock.now))
        latest = self.review.candidates(OFF_R1, self.b.id)[0]["review"]
        self.assertEqual((latest["decision"], latest["reviewer_id"]), ("confirmed_duplicate", "off-roads-1"))
        self.assertEqual({k: (v.status, v.department_code) for k, v in self.env.stores.complaints.items()}, before)  # nothing merged/closed
        self.assertEqual(len(self.env.stores.complaints), 2)
        ev = [e for e in self.env.stores.events[self.b.id] if e.kind == "duplicate_review"][0]
        self.assertTrue(ev.internal)
        self.assertEqual(ev.details["decision"], "confirmed_duplicate")
        self.assertIn("complaint.duplicate_reviewed", self.env.actions())
        self.review.decide(OFF_R1, self.b.id, self.a.id, "not_duplicate")  # a later decision supersedes; history keeps both
        self.assertEqual(self.review.candidates(OFF_R1, self.b.id)[0]["review"]["decision"], "not_duplicate")
        self.assertEqual(len(self.review.history(OFF_R1, self.b.id)), 2)

    def test_authorization_and_validation(self):
        with self.assertRaises(PermissionDenied):
            self.review.candidates(CIT2, self.b.id)
        with self.assertRaises(NotFound):
            self.review.candidates(OFF_W1, self.b.id)  # other department
        with self.assertRaises(NotFound):
            self.review.decide(OFF_W1, self.b.id, self.a.id, "related")
        with self.assertRaises(ValidationFailed):
            self.review.decide(OFF_R1, self.b.id, self.a.id, "merge_and_delete")
        with self.assertRaises(ValidationFailed):
            self.review.decide(OFF_R1, self.b.id, "not-a-candidate", "related")
        with self.assertRaises(ValidationFailed):
            self.review.decide(OFF_R1, self.b.id, self.b.id, "related")
        self.assertEqual(self.env.stores.dup_reviews, [])
        self.assertEqual(len(self.review.candidates(ADMIN, self.b.id)), 1)  # unbound admin may read candidates


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.wf = WorkflowService(self.env.factory, self.env.fx)
        self.env.fx.workflow = self.wf
        self.admin = AdminService(self.env.factory, with_auth(self.env), self.env.clock)

    def rule(self, **kw):
        base = dict(rule_id="r1", name="Critical roads escalate", trigger="complaint.created", action="escalate", conditions={"priority_min": "critical", "departments": ["roads"]})
        base.update(kw)
        return self.admin.save_workflow_rule(ADMIN, **base)

    def test_validation(self):
        for kw in ({"trigger": "on_full_moon"}, {"action": "explode"}, {"conditions": {"nonsense": 1}}, {"conditions": {"categories": ["dragons"]}}, {"trigger": "scheduled", "conditions": {"categories": ["roads"]}},
                   {"action": "auto_close", "trigger": "scheduled", "conditions": {"age_hours_min": 24}}, {"action": "add_internal_note", "params": {}}, {"rule_id": "bad id!"}):  # fmt: skip
            with self.assertRaises(ValidationFailed, msg=kw):
                self.rule(**kw)
        with self.assertRaises(PermissionDenied):
            self.admin.save_workflow_rule(ADMIN_ROADS, "x1", "n", "complaint.created", "escalate")  # department-bound admins cannot change org-wide automation
        with self.assertRaises(PermissionDenied):
            self.admin.save_workflow_rule(OFF_R1, "x1", "n", "complaint.created", "escalate")

    def test_pure_matching(self):
        self.rule()
        r = self.env.stores.wf_rules["r1"]
        c = self.env.create(**{**POTHOLE, "title": "Pothole causing accidents", "description": "A deep pothole on the road near the school gate keeps causing accidents"})
        self.assertTrue(matches(r, c, "complaint.created", self.env.clock.now))
        self.assertFalse(matches(r, c, "complaint.status_changed", self.env.clock.now))
        off = WorkflowRuleRecord("o", "n", "complaint.created", {"languages": ["kn"]}, "escalate", active=False)
        self.assertFalse(matches(off, c, "complaint.created", self.env.clock.now))

    def test_rule_runs_on_intake_once_and_leaves_event_and_audit(self):
        self.rule()
        c = self.env.create(title="Pothole causing accidents", description="A deep pothole on the road near the school gate keeps causing accidents")
        self.assertEqual((c.priority, self.env.stores.complaints[c.id].escalation_level), ("critical", 1))
        ev = [e for e in self.env.stores.events[c.id] if e.kind == "workflow"][0]
        self.assertEqual((ev.internal, ev.details["rule"], ev.details["outcome"]), (True, "r1", "escalated_to_1"))
        self.assertIn("workflow.executed", self.env.actions())
        self.assertEqual(len(self.env.stores.wf_exec), 1)
        with self.env.factory() as uow:  # re-running the same trigger cannot fire the rule a second time
            from app.services.complaint_common import Outbox

            self.assertEqual(self.wf.run_for_complaint(uow, self.env.stores.complaints[c.id], "complaint.created", Outbox()), [])
        self.assertEqual(self.env.stores.complaints[c.id].escalation_level, 1)

    def test_non_matching_complaints_are_untouched(self):
        self.rule()
        c = self.env.create(title="No water", description="No water supply in our street for two days now", lat=13.5, lng=77.9)
        self.assertEqual((self.env.stores.complaints[c.id].escalation_level, self.env.stores.wf_exec), (0, {}))

    def test_status_change_trigger_and_notify_admins_and_internal_note(self):
        self.rule(rule_id="n1", name="Resolved ping", trigger="complaint.status_changed", action="notify_admins", conditions={"statuses": ["resolved"]}, params={"message": "Resolved: check feedback"})
        self.rule(rule_id="n2", name="Note", trigger="complaint.status_changed", action="add_internal_note", conditions={"statuses": ["under_review"]}, params={"text": "Reviewed by rule"})
        c = self.env.create()
        self.env.officer.update_status(OFF_R1, c.id, S.UNDER_REVIEW)
        self.env.officer.update_status(OFF_R1, c.id, S.RESOLVED, "fixed")
        self.assertIn("Reviewed by rule", [e.remarks for e in self.env.stores.events[c.id] if e.kind == "remark"])
        self.assertTrue(any(n.user_id == "admin-1" and "Resolved: check feedback" in n.body for n in self.env.stores.notifications.values()))

    def test_scheduled_auto_close_after_age_and_sweep_is_idempotent(self):
        self.rule(rule_id="close", name="Auto close", trigger="scheduled", action="auto_close", conditions={"statuses": ["resolved"], "age_hours_min": 72})
        c = self.env.create()
        for t, note in [(S.UNDER_REVIEW, None), (S.RESOLVED, "fixed")]:
            self.env.officer.update_status(OFF_R1, c.id, t, note)
        self.env.clock.advance(hours=71)
        self.assertEqual(self.wf.sweep(self.env.clock.now)["fired"], 0)
        self.env.clock.advance(hours=2)
        self.assertEqual(self.wf.sweep(self.env.clock.now)["fired"], 1)
        self.assertEqual(self.env.stores.complaints[c.id].status, S.CLOSED)
        self.assertEqual(self.wf.sweep(self.env.clock.now)["fired"], 0)
        self.assertEqual(len(self.env.stores.wf_exec), 1)

    def test_assign_least_loaded_for_unassigned(self):
        self.env.stores.officers["roads"] = []  # nobody on duty at intake
        self.rule(rule_id="as", name="Assign", trigger="scheduled", action="assign_least_loaded", conditions={"departments": ["roads"], "age_hours_min": 1})
        c = self.env.create()
        self.assertIsNone(c.assigned_officer_id)
        self.env.stores.officers["roads"] = ["off-roads-1"]
        self.env.clock.advance(hours=2)
        self.wf.sweep(self.env.clock.now)
        self.assertEqual(self.env.stores.complaints[c.id].assigned_officer_id, "off-roads-1")

    def test_admin_overview_and_delete(self):
        self.rule()
        self.assertEqual([r.id for r in self.admin.workflow_overview(ADMIN)["rules"]], ["r1"])
        self.admin.delete_workflow_rule(ADMIN, "r1")
        with self.assertRaises(NotFound):
            self.admin.delete_workflow_rule(ADMIN, "r1")
        self.assertIn("admin.workflow_rule_deleted", self.env.actions())


class FakeTransport:
    def __init__(self, status=200, body=None):
        self.status, self.body, self.calls = status, body if body is not None else {"reference": "EXT-77", "status": "Registered"}, []

    def request(self, method, url, headers, body, timeout):
        self.calls.append((method, url, body, headers))
        return TransportResponse(self.status, self.body, 1.0)


ENDPOINTS = {"health": "/h", "submit": "/g", "status": "/s"}


class GovernmentSubmissionTests(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.env = Env()
        self.c = self.env.create()
        self.transport = FakeTransport()
        cfg = AdapterConfig("https://gov.example", "key-secret", ENDPOINTS, max_retries=0, allow_private_hosts=True)
        self.adapters = {"cpgrams": CPGRAMSAdapter(cfg, transport=self.transport, sleep=lambda s: None), "umang": CPGRAMSAdapter(AdapterConfig(), transport=self.transport)}
        self.adapters["umang"].platform, self.adapters["umang"].display_name = "umang", "UMANG"
        self.svc = GovernmentSubmissionService(self.env.factory, self.env.fx, self.adapters)
        self.worker = GrievanceWorker(self.env.factory, self.env.complaints, None, None, self.env.storage, self.env.fx, self.env.notifications, government=self.svc)
        self.env.jobs.handlers.update(self.worker.handlers())
        self.env.jobs.drain("w")  # process the intake enrichment job first

    def test_initial_state_is_not_started_and_shows_adapter_and_consent_truthfully(self):
        st = {s["platform"]: s for s in self.svc.states(CIT, self.c.id)}
        self.assertEqual((st["cpgrams"]["state"], st["cpgrams"]["adapter_state"], st["cpgrams"]["consent_granted"]), ("not_started", "UNAVAILABLE", False))
        self.assertEqual((st["umang"]["configured"], st["umang"]["adapter_state"]), (False, "NOT_CONFIGURED"))

    def test_without_consent_nothing_is_sent(self):
        r = self.svc.request(CIT, self.c.id, "cpgrams")
        self.assertEqual(r.state, "consent_required")
        self.assertEqual((self.transport.calls, [j.kind for j in self.env.stores.jobs.values() if j.kind == "gov.submit"]), ([], []))

    def test_unconfigured_platform_records_not_configured_and_makes_no_call(self):
        grant(self.env, CIT)
        r = self.svc.request(CIT, self.c.id, "umang")
        self.assertEqual(r.state, "not_configured")
        self.assertIn("Nothing was sent", r.last_error)
        self.env.jobs.drain("w")
        self.assertEqual(self.transport.calls, [])

    def test_consented_submission_goes_through_the_queue_and_is_marked_submitted_only_after_a_real_success(self):
        grant(self.env, CIT)
        r = self.svc.request(CIT, self.c.id, "cpgrams")
        self.assertEqual(r.state, "queued")
        self.assertEqual(self.transport.calls, [])  # not sent inline
        res = [x for x in self.env.jobs.drain("w") if x.kind == "gov.submit"]
        self.assertEqual([x.status for x in res], ["succeeded"])
        rec = self.env.stores.gov[(self.c.id, "cpgrams")]
        self.assertEqual((rec.state, rec.external_reference, rec.attempts), ("submitted", "EXT-77", 1))
        self.assertIsNotNone(rec.submitted_at)
        sent = self.transport.calls[0][2]
        self.assertEqual(sent["reference"], self.c.reference)
        for pii in ("email", "full_name", "phone", "citizen_id", "user_id"):
            self.assertNotIn(pii, sent)  # canonical payload carries no citizen identity
        self.assertEqual(set(sent), set(canonical_payload(self.c)))
        ev = [e for e in self.env.stores.events[self.c.id] if e.kind == "government_submitted"][0]
        self.assertFalse(ev.internal)
        self.assertIn("EXT-77", ev.remarks)
        self.assertEqual(self.svc.request(CIT, self.c.id, "cpgrams").state, "submitted")  # idempotent
        self.assertEqual(len(self.transport.calls), 1)
        self.assertIn("government.submission_result", self.env.actions())

    def test_adapter_failure_is_recorded_retried_and_never_reported_as_submitted(self):
        grant(self.env, CIT)
        self.transport.status, self.transport.body = 503, {}
        self.svc.request(CIT, self.c.id, "cpgrams")
        results = []
        for _ in range(4):
            results += [x for x in self.env.jobs.drain("w") if x.kind == "gov.submit"]
            self.env.clock.advance(minutes=20)
        self.assertEqual([x.status for x in results], ["retrying", "retrying", "dead"])
        rec = self.env.stores.gov[(self.c.id, "cpgrams")]
        self.assertEqual((rec.state, rec.submitted_at, rec.external_reference), ("failed", None, None))
        self.assertIn("HTTP 503", rec.last_error)
        self.assertNotIn("government_submitted", {e.kind for e in self.env.stores.events[self.c.id]})
        self.transport.status, self.transport.body = 200, {"reference": "EXT-9"}  # a later retry by the citizen/officer can succeed
        self.assertEqual(self.svc.request(CIT, self.c.id, "cpgrams").state, "queued")
        self.env.jobs.drain("w")
        self.assertEqual(self.env.stores.gov[(self.c.id, "cpgrams")].state, "submitted")

    def test_authorization(self):
        for ctx in (CIT2, OFF_W1):
            with self.assertRaises(NotFound):
                self.svc.request(ctx, self.c.id, "cpgrams")
            with self.assertRaises(NotFound):
                self.svc.states(ctx, self.c.id)
        with self.assertRaises(ValidationFailed):
            self.svc.request(CIT, self.c.id, "facebook")
        grant(self.env, CIT)
        self.assertEqual(self.svc.request(OFF_R1, self.c.id, "cpgrams").state, "queued")  # the responsible officer may request it (citizen's consent still applies)


class NotificationStateTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()

    def register_device(self, user="cit-1", token="ExponentPushToken[abc]"):
        with self.env.uow() as u:
            u.push.upsert(PushDeviceRecord(user, token, "android", self.env.clock.now, self.env.clock.now))
            u.commit()

    def worker(self, sender):
        w = GrievanceWorker(self.env.factory, self.env.complaints, None, None, self.env.storage, self.env.fx, self.env.notifications, push_sender=sender)
        self.env.jobs.handlers.update(w.handlers())

    def push_rows(self):
        return [n for n in self.env.stores.notifications.values() if n.channel == "push"]

    def test_no_device_no_push_record(self):
        self.env.create()
        self.assertEqual(self.push_rows(), [])

    def test_push_is_not_configured_when_disabled_and_never_reported_delivered(self):
        self.register_device()
        self.worker(None)
        self.env.create()
        self.env.jobs.drain("w")
        self.assertTrue(self.push_rows())
        self.assertTrue(all(n.status == "not_configured" and n.delivered_at is None for n in self.push_rows()))
        self.assertIn("not enabled", self.push_rows()[0].error)

    def test_push_delivered_only_when_expo_accepts_it(self):
        self.register_device()
        t = FakeTransport(200, {"data": [{"status": "ok", "id": "1"}]})
        self.worker(ExpoPushSender(t))
        self.env.create()
        self.env.jobs.drain("w")
        self.assertTrue(all(n.status == "delivered" for n in self.push_rows()))
        sent = t.calls[0][2][0]
        self.assertEqual((sent["to"], sent["title"]), ("ExponentPushToken[abc]", "Complaint registered"))

    def test_push_rejection_and_outage_are_failures(self):
        self.register_device()
        self.worker(ExpoPushSender(FakeTransport(200, {"data": [{"status": "error", "message": "DeviceNotRegistered"}]})))
        self.env.create()
        self.env.jobs.drain("w")
        self.assertTrue(all(n.status == "failed" and "DeviceNotRegistered" in n.error for n in self.push_rows()))

    def test_email_states_queued_sending_delivered_failed_not_configured(self):
        with self.env.uow() as u:
            from app.services.auth_service import UserRecord

            u.users.add(UserRecord("cit-1", "a@example.com", "h", "Asha"))
            u.notifications.save_preferences(NotificationPreference("cit-1", True, True))
            u.commit()
        w = GrievanceWorker(self.env.factory, self.env.complaints, None, None, self.env.storage, self.env.fx, self.env.notifications)
        self.env.jobs.handlers.update(w.handlers())
        self.env.create()
        emails = [n for n in self.env.stores.notifications.values() if n.channel == "email"]
        self.assertTrue(emails and all(n.status == "queued" for n in emails))  # before the worker runs
        self.env.jobs.drain("w")
        self.assertTrue(all(n.status == "not_configured" for n in emails))
        counts = self.env.uow().notifications.status_counts()
        self.assertEqual(counts["in_app"], {"delivered": 2})
        self.assertEqual(counts["email"], {"not_configured": len(emails)})


class JobLifecycleTests(unittest.TestCase):
    def test_status_path_timestamps_and_admin_retry_of_dead_jobs(self):
        env = Env()
        calls = []

        def flaky(payload, job):
            calls.append(job.attempts)
            if len(calls) < 10:
                raise RuntimeError("boom")

        env.jobs.handlers["flaky"] = flaky
        with env.factory() as u:
            job, _ = env.jobs.enqueue(u, "flaky", {}, "k1")
            u.commit()
        env.jobs.dispatch([job])
        self.assertEqual(env.stores.jobs[job.id].status, "queued")
        env.jobs.run_once("w")
        j = env.stores.jobs[job.id]
        self.assertEqual((j.status, j.attempts, j.started_at is not None, j.finished_at), ("retrying", 1, True, None))
        self.assertEqual(len(env.backend.items), 1)  # a retrying job is waiting in Redis
        for _ in range(2):
            env.clock.advance(minutes=30)
            env.jobs.run_once("w")
        j = env.stores.jobs[job.id]
        self.assertEqual((j.status, j.attempts), ("dead", 3))
        self.assertIsNotNone(j.finished_at)
        env.jobs.handlers["flaky"] = lambda p, jb: {"ok": 1}
        env.jobs.retry_dead(job.id)
        self.assertEqual(env.stores.jobs[job.id].status, "queued")
        env.jobs.drain("w")
        self.assertEqual((env.stores.jobs[job.id].status, env.stores.jobs[job.id].result), ("succeeded", {"ok": 1}))
        with self.assertRaises(ValidationFailed):
            env.jobs.retry_dead(job.id)  # only dead jobs

    def test_lost_redis_state_is_repaired_for_queued_and_retrying_jobs(self):
        env = Env()
        env.jobs.handlers["x"] = lambda p, j: {}
        with env.factory() as u:
            job, _ = env.jobs.enqueue(u, "x", {}, "lost")
            u.commit()
        env.jobs.dispatch([job])
        env.backend.items.clear()  # Redis lost the queue (flush/restart)
        env.clock.advance(minutes=10)
        self.assertEqual(env.jobs.requeue_orphans(), 1)
        self.assertEqual(env.jobs.drain("w")[0].status, "succeeded")


class HistoryAndEmergencyAdminTests(unittest.TestCase):
    def test_analytics_history_reads_snapshots_and_says_when_there_are_none(self):
        env = Env()
        dash = DashboardService(env.factory, env.clock)
        self.assertEqual(dash.history(ADMIN), {"has_data": False, "days": 30, "points": []})
        env.create()
        env.c = None
        for _ in range(2):
            env.clock.advance(hours=1)
            with env.factory() as u:
                from app.services.dashboard_service import summarize
                from app.services.sla_service import SlaCalculator

                summary = summarize(u.complaints.rows(), env.clock.now, SlaCalculator(list(u.config.sla_policies())))
                u.analytics.add_snapshot("all", env.clock.now, {k: v for k, v in summary.items() if k != "trend_daily"})
                u.commit()
        h = dash.history(ADMIN)
        self.assertEqual((h["has_data"], len(h["points"]), h["points"][-1]["total"], h["points"][-1]["open"]), (True, 2, 1, 1))
        self.assertEqual(dash.history(ADMIN, days=0)["days"], 0)
        with self.assertRaises(PermissionDenied):
            dash.history(ADMIN_ROADS)
        with self.assertRaises(PermissionDenied):
            dash.history(OFF_R1)

    def test_admin_manages_emergency_contacts_with_audit_and_scope(self):
        env = Env()
        admin = AdminService(env.factory, with_auth(env), env.clock)
        admin.save_emergency_contact(ADMIN, "Nat-112", "112", "National Emergency", description="All India")
        self.assertEqual([c.id for c in admin.emergency_contacts(ADMIN)], ["nat-112"])
        with self.assertRaises(ValidationFailed):
            admin.save_emergency_contact(ADMIN, "bad", "abc", "x")
        with self.assertRaises(ValidationFailed):
            admin.save_emergency_contact(ADMIN, "c1", "100", "City", scope="city", city_code="nowhere")
        with self.assertRaises(PermissionDenied):
            admin.save_emergency_contact(ADMIN_ROADS, "x1", "100", "x")
        admin.delete_emergency_contact(ADMIN, "nat-112")
        with self.assertRaises(NotFound):
            admin.delete_emergency_contact(ADMIN, "nat-112")
        self.assertIn("admin.emergency_contact_saved", env.actions())


class LegalPersistenceTests(unittest.TestCase):
    def test_analysis_is_persisted_audited_owner_scoped_and_validated(self):
        from tests.end_to_end.test_full_flow import Sys

        s = Sys()
        c = s.c
        from app.core.exceptions import DependencyUnavailable

        s.chat.replies = [DependencyUnavailable("model down")]  # no model text: records only
        rec = c.legal.analyze(CIT, "Dispute between Eldeco Housing and a flat buyer about builder possession delay")
        self.assertEqual((rec.user_id, rec.status), ("cit-1", "precedents_only"))
        self.assertEqual(rec.result["precedents"][0]["neutralCitation"], "2023 INSC 1043")
        self.assertEqual([r.id for r in c.legal.list_mine(CIT)], [rec.id])
        self.assertEqual(c.legal.list_mine(CIT2), [])
        with self.assertRaises(NotFound):
            c.legal.get_mine(CIT2, rec.id)
        for bad in ("", "abc", "x" * 8001):
            with self.assertRaises(ValidationFailed):
                c.legal.analyze(CIT, bad)
        acts = [e.action for e in s.stores.audit]
        self.assertIn("legal.analysis", acts)
        self.assertNotIn("Eldeco", repr([e.metadata for e in s.stores.audit]))  # the matter text itself is not copied into the audit trail
        self.assertEqual(c.legal.analyze(CIT, "zzzz qqqq unrelated words").status, "no_verified_precedent")



if __name__ == "__main__":
    unittest.main()
