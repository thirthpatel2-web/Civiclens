import unittest
from dataclasses import replace
from datetime import timedelta

from app.core.authorization import AuthContext, Role
from app.core.exceptions import NotFound, PermissionDenied, ValidationFailed
from app.core.security import SecretBox
from app.rag.bm25 import BM25Index
from app.rag.grounded_generation import GroundedGenerator
from app.rag.hybrid_retrieval import HybridRetriever
from app.rag.index import RagIndex
from app.rag.rag_service import RagService
from app.services.admin_service import AdminService
from app.services.anomaly_job import AnomalyDetectionJob
from app.services.assistant_service import AssistantService, build_query_registry
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService, UserRecord
from app.services.complaint_status import ComplaintStatus as S
from app.services.dashboard_service import DashboardService
from app.services.document_service import document_access_filter
from app.services.gis_service import GisService
from app.services.investigation_service import InvestigationService
from app.services.mfa_service import MFAService
from app.services.profile_service import DraftService, ProfileService
from app.services.rti_service import RtiApplication, RtiDraft, RtiRules, RtiStatus
from app.services.rti_workflow import RtiReminderService
from tests.rag.helpers import ScriptedChat
from tests.support import FakeClock, ReferenceTotp, ScryptTestHasher
from tests.support_env import (
    ADMIN,
    ADMIN_ROADS,
    CIT,
    CIT2,
    OFF_R1,
    OFF_W1,
    SUPER,
    VAGUE,
    Env,
    complaint_input,
)
from tests.support_mem import MemoryUow


def with_auth(env: Env):
    hasher = ScryptTestHasher()

    def factory(uow):
        audit = AuditService(uow.audit, env.clock)
        mfa = MFAService(uow.mfa, SecretBox("m" * 32), ReferenceTotp(), audit, clock=env.clock.epoch)
        return AuthService(uow.users, uow.sessions, uow.resets, hasher, mfa, audit, clock=env.clock)

    return factory


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.dash = DashboardService(self.env.factory, self.env.clock, system_status=lambda: {"queue": "up"})

    def test_empty_database_says_no_data_rather_than_zeros_as_insight(self):
        d = self.dash.citizen(CIT)
        self.assertFalse(d["has_data"])
        self.assertIsNone(d["resolution_hours"])
        self.assertEqual((d["total"], d["recent"]), (0, []))

    def test_citizen_dashboard_reflects_only_own_records(self):
        a = self.env.create()
        self.env.create(CIT2, **VAGUE)
        for t, r in [(S.UNDER_REVIEW, None), (S.RESOLVED, "fixed")]:
            self.env.officer.update_status(OFF_R1, a.id, t, r)
        d = self.dash.citizen(CIT)
        self.assertEqual((d["total"], d["open"], d["resolved"], d["pending_feedback"]), (1, 0, 1, [a.id]))
        self.assertEqual(d["by_category"], {"roads": 1})
        self.assertEqual(d["resolution_hours"]["count"], 1)
        self.assertEqual(d["unread_notifications"], 3)  # created + status + resolved

    def test_officer_department_dashboard_is_scoped_and_computes_sla(self):
        self.env.create()
        self.env.create(title="No water", description="No water supply in our street for two days", lat=13.5, lng=77.9)
        d = self.dash.department(OFF_R1)
        self.assertEqual((d["total"], d["department_code"], d["by_department"]), (1, "roads", {"roads": 1}))
        self.assertEqual(d["workload"], {"off-roads-1": 1})
        self.assertEqual(d["sla"]["on_track"] + d["sla"]["at_risk"], 1)
        self.env.clock.advance(days=30)
        self.assertEqual(self.dash.department(OFF_R1)["sla"]["breached"], 1)
        with self.assertRaises(PermissionDenied):
            self.dash.department(CIT)

    def test_trend_backlog_and_admin_view(self):
        self.env.create()
        self.env.clock.advance(days=2)
        self.env.create(CIT2, title="Second pothole", description="Another deep pothole on a different road far away from here", lat=13.3, lng=77.8)
        d = self.dash.admin(ADMIN)
        self.assertEqual(sum(x["count"] for x in d["trend_daily"]), 2)
        self.assertEqual((d["backlog"], len(d["trend_daily"])), (2, 30))
        self.assertEqual(d["system"], {"queue": "up"})
        self.assertGreater(len(d["recent_audit"]), 0)
        self.assertEqual(d["jobs"], {"queued": 2})
        with self.assertRaises(PermissionDenied):
            self.dash.admin(OFF_R1)
        self.assertEqual(self.dash.admin(ADMIN_ROADS)["total"], 2)  # bound admin still limited to own department

    def test_unbound_admin_department_drilldown(self):
        self.env.create()
        self.assertEqual(self.dash.department(ADMIN, department_code="water")["total"], 0)
        self.assertEqual(self.dash.department(ADMIN, department_code="roads")["total"], 1)


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.admin = AdminService(self.env.factory, with_auth(self.env), self.env.clock)
        self.pw = "a-long-enough-passphrase"

    def test_only_admins_and_mfa_verified_and_denials_are_audited(self):
        for ctx in (CIT, OFF_R1):
            with self.assertRaises(PermissionDenied):
                self.admin.list_users(ctx)
        with self.assertRaises(PermissionDenied):
            self.admin.list_users(AuthContext("a", Role.ADMIN, None, mfa_verified=False))
        denied = [e for e in self.env.stores.audit if e.action == "admin.access_denied"]
        self.assertEqual([e.actor_id for e in denied], ["cit-1", "off-roads-1", "a"])

    def test_staff_creation_rules(self):
        off = self.admin.create_staff(ADMIN, "o@example.com", self.pw, "Officer One", Role.OFFICER, "roads")
        self.assertEqual((off.role, off.department_id), (Role.OFFICER, "roads"))
        for role in (Role.ADMIN, Role.SUPER_ADMIN, Role.CITIZEN):
            with self.assertRaises(PermissionDenied):
                self.admin.create_staff(ADMIN, f"{role}@example.com", self.pw, "Someone", role, None)
        adm = self.admin.create_staff(SUPER, "a@example.com", self.pw, "Admin Two", Role.ADMIN, None)
        self.assertEqual(adm.role, Role.ADMIN)
        with self.assertRaises(ValidationFailed):
            self.admin.create_staff(ADMIN, "o2@example.com", self.pw, "Officer Two", Role.OFFICER, "atlantis")
        with self.assertRaises(PermissionDenied):
            self.admin.create_staff(ADMIN_ROADS, "o3@example.com", self.pw, "Officer Three", Role.OFFICER, "water")  # outside own department
        self.assertIn("admin.staff_created", self.env.actions())
        self.assertIn("admin.create_staff_denied", self.env.actions())  # persisted even though the operation itself was rolled back

    def test_role_change_no_self_promotion_and_sessions_revoked(self):
        off = self.admin.create_staff(ADMIN, "o@example.com", self.pw, "Officer One", Role.OFFICER, "roads")
        with self.assertRaises(PermissionDenied):
            self.admin.change_role(AuthContext(off.id, Role.OFFICER, "roads"), off.id, Role.SUPER_ADMIN, None)
        with self.assertRaises(PermissionDenied):
            self.admin.change_role(ADMIN, off.id, Role.ADMIN, None)
        moved = self.admin.change_role(ADMIN, off.id, Role.OFFICER, "water")
        self.assertEqual(moved.department_id, "water")
        with self.assertRaises(ValidationFailed):
            self.admin.change_role(ADMIN, off.id, Role.OFFICER, None)
        deact = self.admin.set_user_active(ADMIN, off.id, False)
        self.assertFalse(deact.is_active)
        with self.assertRaises(ValidationFailed):
            self.admin.set_user_active(ADMIN, ADMIN.user_id, False)  # cannot lock yourself out

    def test_routing_rules_validated_with_runtime_classes_and_used_by_complaints(self):
        with self.assertRaises(ValidationFailed) as cm:
            self.admin.save_routing_rule(ADMIN, "bad", 5000, "roads", categories=["dragons"])
        self.assertEqual(set(cm.exception.details), {"priority", "categories"})
        with self.assertRaises(ValidationFailed):
            self.admin.save_routing_rule(ADMIN, "empty", 10, "roads")  # no conditions
        with self.assertRaises(ValueError):
            self.admin.save_routing_rule(ADMIN, "ghost", 10, "atlantis", categories=["roads"])
        self.admin.save_routing_rule(ADMIN, "sewage-to-water", 5, "water", categories=["drainage"])
        c = self.env.create(title="Sewage overflow", description="Sewage overflow on the street from a blocked drain near the market")
        self.assertEqual((c.department_code, c.routing["rule_id"]), ("water", "sewage-to-water"))
        with self.assertRaises(PermissionDenied):
            self.admin.save_routing_rule(ADMIN_ROADS, "x-rule", 5, "water", categories=["water"])
        self.admin.delete_routing_rule(ADMIN, "sewage-to-water")
        with self.assertRaises(NotFound):
            self.admin.delete_routing_rule(ADMIN, "sewage-to-water")
        self.assertIn("admin.routing_rule_deleted", self.env.actions())

    def test_sla_policies_and_reference_data(self):
        p = self.admin.save_sla_policy(ADMIN, "roads-high", "high", 12, department_code="roads")
        self.assertEqual(p.resolution_hours, 12)
        with self.assertRaises(ValidationFailed):
            self.admin.save_sla_policy(ADMIN, "bad", "urgent", 12)
        with self.assertRaises(ValidationFailed):
            self.admin.save_sla_policy(ADMIN, "bad2", "high", 0)
        self.admin.save_department(SUPER, "electricity", "Electricity Board")
        with self.assertRaises(PermissionDenied):
            self.admin.save_department(ADMIN_ROADS, "roads2", "Roads Two")
        self.admin.save_city(ADMIN, "blr", "Bengaluru", "Karnataka", 12.97, 77.59)
        self.admin.save_ward(ADMIN, "w12", "Ward 12", "blr")
        with self.assertRaises(ValidationFailed):
            self.admin.save_ward(ADMIN, "w13", "Ward 13", "nowhere")
        self.admin.save_service(ADMIN, "pothole", "Pothole repair", "roads")
        self.admin.save_office(ADMIN, "roads-hq", "Roads HQ", "roads", 12.97, 77.59, "MG Road")
        with self.assertRaises(ValidationFailed):
            self.admin.save_city(ADMIN, "bad", "Nowhere", None, 999, 5)
        ref = self.admin.reference_data(ADMIN)
        self.assertEqual({d.code for d in ref["departments"]}, {"roads", "water", "general", "electricity"})
        self.assertEqual(len(ref["wards"]) + len(ref["cities"]) + len(ref["services"]) + len(ref["offices"]), 4)

    def test_audit_log_access(self):
        self.env.create()
        events = self.admin.audit_log(ADMIN, action_prefix="complaint.")
        self.assertTrue(events and all(e.action.startswith("complaint.") for e in events))
        with self.assertRaises(PermissionDenied):
            self.admin.audit_log(ADMIN_ROADS)
        with self.assertRaises(PermissionDenied):
            self.admin.audit_log(OFF_R1)
        self.assertIn("admin.audit_viewed", self.env.actions())

    def test_anomaly_status_scoping(self):
        from app.services.ports import AnomalyRecord

        a = AnomalyRecord("an1", "volume_spike", "All", "warning", 4.0, "x", self.env.clock.now, "water", dedupe_key="k")
        self.env.stores.anomalies["an1"] = a
        self.assertEqual(len(self.admin.anomalies(ADMIN)), 1)
        self.assertEqual(self.admin.anomalies(ADMIN_ROADS), [])
        with self.assertRaises(NotFound):
            self.admin.set_anomaly_status(ADMIN_ROADS, "an1", "resolved")
        self.assertEqual(self.admin.set_anomaly_status(ADMIN, "an1", "acknowledged").status, "acknowledged")
        with self.assertRaises(ValidationFailed):
            self.admin.set_anomaly_status(ADMIN, "an1", "deleted")


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.rag_calls = []
        self.inv = InvestigationService(self.env.factory, self.env.clock, lambda ctx, q: (self.rag_calls.append(q) or {"status": "insufficient_evidence"}))
        self.a = self.env.create()
        self.b = self.env.create(CIT2, title="Pothole nearby", description="Another pothole on the same stretch of road close to the bus stop", lat=12.9718, lng=77.5948, ward="12")

    def test_report_assembles_labelled_sources_and_is_audited(self):
        i = self.inv.open(OFF_R1, "complaint", self.a.id)
        self.inv.add_note(OFF_R1, i.id, "Visited site; pattern of potholes")
        rep = self.inv.report(OFF_R1, i.id)
        self.assertEqual([r.id for r in rep["nearby_same_category"]], [self.b.id])
        self.assertEqual([r.id for r in rep["ward_category_cluster"]], [self.b.id])
        self.assertEqual(rep["location"]["ward"], "12")
        self.assertEqual(rep["rag_findings"], {"status": "insufficient_evidence"})
        self.assertEqual(rep["legal_sources"], {"status": "not_configured"})
        self.assertTrue(rep["events"] and rep["timeline"])
        self.assertIn("investigation.opened", [e.action for e in rep["audit_trail"]] + self.env.actions())
        self.assertEqual(rep["investigation"].notes[0]["text"], "Visited site; pattern of potholes")
        self.assertEqual(len(self.rag_calls), 1)

    def test_authorization_and_department_isolation(self):
        with self.assertRaises(PermissionDenied):
            self.inv.open(CIT, "complaint", self.a.id)
        with self.assertRaises(NotFound):
            self.inv.open(OFF_W1, "complaint", self.a.id)
        i = self.inv.open(OFF_R1, "complaint", self.a.id)
        for fn in (lambda: self.inv.report(OFF_W1, i.id), lambda: self.inv.add_note(OFF_W1, i.id, "x"), lambda: self.inv.close(OFF_W1, i.id)):
            with self.assertRaises(NotFound):
                fn()
        self.assertEqual([x.id for x in self.inv.list(OFF_W1)], [])
        self.assertEqual([x.id for x in self.inv.list(ADMIN)], [i.id])
        self.assertEqual(self.inv.report(ADMIN, i.id)["complaint"].id, self.a.id)

    def test_closed_investigations_reject_notes_and_validation(self):
        i = self.inv.open(OFF_R1, "complaint", self.a.id)
        with self.assertRaises(ValidationFailed):
            self.inv.add_note(OFF_R1, i.id, "  ")
        self.inv.close(OFF_R1, i.id)
        with self.assertRaises(ValidationFailed):
            self.inv.add_note(OFF_R1, i.id, "late")
        with self.assertRaises(ValidationFailed):
            self.inv.open(OFF_R1, "cluster", "x")

    def test_anomaly_subject(self):
        from app.services.ports import AnomalyRecord

        self.env.stores.anomalies["an1"] = AnomalyRecord("an1", "ward_spike", "Ward 12", "warning", 5.0, "spike", self.env.clock.now, "roads", dedupe_key="k")
        i = self.inv.open(OFF_R1, "anomaly", "an1")
        rep = self.inv.report(OFF_R1, i.id)
        self.assertEqual(rep["anomaly"].id, "an1")
        self.assertEqual(len(rep["related_complaints"]), 2)
        with self.assertRaises(NotFound):
            self.inv.open(OFF_W1, "anomaly", "an1")


class AnomalyJobTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.job = AnomalyDetectionJob(self.env.factory)

    def seed_history(self, per_day=2, days=20, ward="12"):
        base = self.env.clock.now
        for d in range(days, 0, -1):
            for k in range(per_day):
                self.env.clock.now = base - timedelta(days=d)
                self.env.create(CIT, title=f"Pothole {d}-{k}", description=f"A pothole on road segment number {d}-{k} that needs repair soon", lat=12.9 + d * 0.01 + k * 0.001, lng=77.5, ward=ward)
        self.env.clock.now = base

    def test_insufficient_history_creates_nothing(self):
        self.env.create()
        r = self.job.run(self.env.clock.now)
        self.assertEqual(r["created"], 0)
        self.assertGreater(r["skipped_insufficient_history"], 0)

    def test_spike_is_detected_persisted_once_per_day_and_visible_to_admin(self):
        self.seed_history()
        for k in range(15):
            self.env.create(CIT, title=f"Pothole burst {k}", description=f"A pothole in the burst of reports number {k} on the same ward", lat=13.0 + k * 0.01, lng=77.6, ward="12")
        r = self.job.run(self.env.clock.now)
        self.assertGreaterEqual(r["created"], 1)
        kinds = {a.kind for a in self.env.stores.anomalies.values()}
        self.assertIn("volume_spike", kinds)
        self.assertIn("ward_spike", kinds)
        n = len(self.env.stores.anomalies)
        again = self.job.run(self.env.clock.now)
        self.assertEqual((again["created"], len(self.env.stores.anomalies)), (0, n))  # deduped
        admin = AdminService(self.env.factory, with_auth(self.env), self.env.clock)
        self.assertEqual(len(admin.anomalies(ADMIN)), n)

    def test_backlog_anomaly_per_department(self):
        for k in range(12):
            self.env.create(CIT, title=f"Pothole backlog {k}", description=f"A pothole in the backlog set number {k} somewhere in the city", lat=12.0 + k * 0.05, lng=77.0)
        r = self.job.run(self.env.clock.now)
        backlog = [a for a in self.env.stores.anomalies.values() if a.kind == "department_backlog"]
        self.assertEqual((len(backlog), backlog[0].department_code, backlog[0].severity), (1, "roads", "critical"))
        self.assertGreaterEqual(r["detected"], 1)


class GisTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.gis = GisService(self.env.factory, self.env.clock)
        self.env.create(lat=12.9716, lng=77.5946)
        self.env.create(CIT2, title="Pothole again", description="Another pothole right next to the first one on the same road", lat=12.9717, lng=77.5947)
        self.env.create(CIT2, title="Pothole third", description="A third pothole on the same road beside the other two potholes", lat=12.9718, lng=77.5946)
        self.env.create(CIT, title="No water", description="No water supply since morning in the whole lane", lat=13.3, lng=77.9)
        self.env.create(CIT, lat=None, lng=None, **VAGUE)  # no coordinates

    def test_staff_get_scoped_points_and_all_hotspots_with_ids(self):
        r = self.gis.radar(OFF_R1)
        self.assertEqual((r["total_complaints"], r["mappable"], r["not_mappable"]), (3, 3, 0))  # roads department only; water/no-coordinate ones excluded
        self.assertEqual([h["count"] for h in r["hotspots"]], [3])
        self.assertIn("complaint_ids", r["hotspots"][0])
        self.assertEqual(len(r["points"]), 3)
        self.assertEqual(r["ward_boundaries"], "not_available")

    def test_admin_sees_everything_and_counts_unmappable_honestly(self):
        r = self.gis.radar(ADMIN)
        self.assertEqual((r["total_complaints"], r["mappable"], r["not_mappable"]), (5, 4, 1))

    def test_citizen_gets_only_aggregates_with_minimum_group_size(self):
        r = self.gis.radar(CIT)
        self.assertEqual([h["count"] for h in r["hotspots"]], [3])  # the lone water complaint is hidden
        self.assertNotIn("complaint_ids", r["hotspots"][0])
        self.assertEqual(r["points"], [])
        self.assertIn("fewer than 3", r["privacy"])

    def test_filters_and_offices(self):
        self.assertEqual(self.gis.radar(ADMIN, category="water")["hotspots"][0]["categories"], {"water": 1})
        self.assertEqual(self.gis.radar(ADMIN, category="roads", ward="nope")["hotspots"], [])
        self.assertEqual(self.gis.radar(ADMIN, min_severity="critical")["total_complaints"], 0)
        from app.services.ports import GovOfficeRecord

        self.env.stores.offices = [GovOfficeRecord("o1", "Roads HQ", "roads", 12.97, 77.59), GovOfficeRecord("o2", "Water HQ", "water", 13.0, 77.6)]
        self.assertEqual([o["id"] for o in self.gis.radar(OFF_R1)["offices"]], ["o1"])
        self.assertEqual(len(self.gis.radar(CIT)["offices"]), 2)


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.c = self.env.create()
        idx = RagIndex(BM25Index(), None)
        self.chat = ScriptedChat()
        retr = HybridRetriever(idx.chunks, idx.bm25, None, None)
        rag = RagService(retr, GroundedGenerator(self.chat), build_query_registry(self.env.factory), access_filter=document_access_filter)
        self.svc = AssistantService(self.env.factory, rag, self.env.clock)

    def test_status_question_uses_allowlisted_db_query_and_labels_facts(self):
        self.chat.replies = [f"Your complaint {self.c.reference} is assigned [DB]."]
        r = self.svc.ask(CIT, f"What is the status of {self.c.reference}?")
        self.assertEqual((r["status"], r["database_query"]), ("answered", "complaintStatus"))
        self.assertEqual((r["database_facts"]["status"], r["database_facts"]["found"]), ("assigned", True))
        self.assertIn('"status": "assigned"', self.chat.calls[0][1]["content"])

    def test_cannot_read_someone_elses_complaint_through_the_assistant(self):
        self.chat.replies = ["x [DB]"]
        r = self.svc.ask(CIT2, f"status of {self.c.reference}")
        self.assertEqual(r["database_facts"], {"found": False})
        self.assertNotIn("assigned", str(self.chat.calls[0][1]["content"]))
        officer_view = self.svc.ask(OFF_W1, f"status of {self.c.reference}")
        self.assertEqual(officer_view["database_facts"], {"found": False})

    def test_counts_and_conversation_persistence(self):
        self.chat.replies = ["You have 1 complaint [DB].", "Still 1 [DB]."]
        a = self.svc.ask(CIT, "How many complaints do I have?")
        self.assertEqual(a["database_facts"]["total"], 1)
        b = self.svc.ask(CIT, "how many complaints are open?", conversation_id=a["conversation_id"])
        msgs = self.svc.history(CIT, a["conversation_id"])
        self.assertEqual([m.role for m in msgs], ["user", "assistant", "user", "assistant"])
        self.assertEqual(msgs[1].status, "answered")
        self.assertEqual(msgs[1].database_facts["total"], 1)
        self.assertEqual(b["conversation_id"], a["conversation_id"])
        with self.assertRaises(NotFound):
            self.svc.history(CIT2, a["conversation_id"])
        with self.assertRaises(NotFound):
            self.svc.ask(CIT2, "hello", conversation_id=a["conversation_id"])
        self.assertEqual(len(self.svc.conversations(CIT)), 1)

    def test_no_documents_means_insufficient_evidence_and_no_model_call(self):
        r = self.svc.ask(CIT, "What does the ward budget say about drainage?")
        self.assertTrue(r["insufficient_evidence"])
        self.assertEqual(self.chat.calls, [])

    def test_validation_and_role(self):
        for q in ("", "  ", "x" * 2001):
            with self.assertRaises(ValidationFailed):
                self.svc.ask(CIT, q)


class ProfileAndDraftTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.profiles = ProfileService(self.env.factory, self.env.clock)
        self.drafts = DraftService(self.env.factory, self.env.complaints, self.env.clock)
        with self.env.uow() as u:
            u.users.add(UserRecord("cit-1", "asha@example.com", "h", "Asha Rao"))
            u.commit()

    def test_profile_defaults_from_user_and_updates_validated(self):
        p = self.profiles.get(CIT)
        self.assertEqual((p.full_name, p.onboarding_complete), ("Asha Rao", False))
        p = self.profiles.update(CIT, phone="+91 98765 43210", city="Bengaluru", ward="12", language="hi", complete_onboarding=True)
        self.assertEqual((p.phone, p.language, p.onboarding_complete), ("+919876543210", "hi", True))
        for kw in ({"language": "xx"}, {"phone": "12"}, {"full_name": "x"}):
            with self.assertRaises(ValidationFailed):
                self.profiles.update(CIT, **kw)
        self.assertEqual(self.profiles.get(CIT).language, "hi")
        self.assertIn("profile.updated", self.env.actions())

    def test_consent_is_append_only_defaults_to_not_granted_and_audited(self):
        self.assertFalse(any(v["granted"] for v in self.profiles.consents(CIT).values()))
        self.profiles.set_consent(CIT, "ai_processing", True)
        self.profiles.set_consent(CIT, "ai_processing", False)
        self.profiles.set_consent(CIT, "document_storage", True)
        c = self.profiles.consents(CIT)
        self.assertEqual((c["ai_processing"]["granted"], c["document_storage"]["granted"]), (False, True))
        self.assertEqual(len(self.env.stores.consent), 3)
        self.assertFalse(self.profiles.has_consent("cit-1", "ai_processing"))
        self.assertTrue(self.profiles.has_consent("cit-1", "document_storage"))
        with self.assertRaises(ValidationFailed):
            self.profiles.set_consent(CIT, "sell_my_data", True)
        self.assertEqual(self.env.actions().count("consent.changed"), 3)

    def test_offline_draft_sync_is_idempotent_and_never_duplicates(self):
        payload = {"title": "Pothole on MG Road", "description": "A big pothole near the bus stop on MG Road", "lat": 12.97, "lng": 77.59}
        d = self.drafts.save(CIT, "complaint", payload, "client-req-0001")
        again = self.drafts.save(CIT, "complaint", {**payload, "title": "Pothole on MG Road (edited)"}, "client-req-0001")
        self.assertEqual((d.id, again.payload["title"]), (again.id, "Pothole on MG Road (edited)"))
        self.assertEqual(len(self.drafts.list(CIT)), 1)
        self.drafts.mark_pending(CIT, d.id)
        first = self.drafts.sync_all(CIT)
        self.assertEqual([x.status for x in first], ["synced"])
        ref = first[0].result_ref
        self.assertEqual(len(self.env.stores.complaints), 1)
        self.assertEqual(self.drafts.sync(CIT, d.id).result_ref, ref)  # retry after reconnect: no second complaint
        self.drafts.save(CIT, "complaint", {**payload, "title": "Edited after sync"}, "client-req-0001")
        self.assertEqual(self.env.stores.drafts[d.id].payload["title"], "Pothole on MG Road (edited)")  # a synced draft is immutable
        self.assertEqual(len(self.env.stores.complaints), 1)
        self.assertEqual(self.drafts.save(CIT, "complaint", payload, "client-req-0001").status, "synced")

    def test_failed_sync_is_reported_and_retryable_after_edit(self):
        d = self.drafts.save(CIT, "complaint", {"title": "bad", "description": "short"}, "client-req-0002")
        r = self.drafts.sync(CIT, d.id)
        self.assertEqual((r.status, r.attempts), ("failed", 1))
        self.assertIn("errors", r.error)
        fixed = self.drafts.save(CIT, "complaint", {"title": "Pothole on MG Road", "description": "A big pothole near the bus stop on MG Road"}, "client-req-0002")
        self.assertEqual(fixed.status, "draft")
        self.assertEqual(self.drafts.sync(CIT, fixed.id).status, "synced")

    def test_draft_ownership_and_validation(self):
        d = self.drafts.save(CIT, "complaint", {"title": "t"}, "client-req-0003")
        with self.assertRaises(NotFound):
            self.drafts.sync(CIT2, d.id)
        with self.assertRaises(NotFound):
            self.drafts.discard(CIT2, d.id)
        for kw in ({"kind": "rti"}, {"client_request_id": "short"}):
            with self.assertRaises(ValidationFailed):
                self.drafts.save(CIT, kw.get("kind", "complaint"), {}, kw.get("client_request_id", "client-req-0004"))
        self.drafts.discard(CIT, d.id)
        self.assertEqual(self.drafts.list(CIT), [])


class RtiReminderTests(unittest.TestCase):
    def test_reminders_notify_once_and_persist_state(self):
        env = Env()
        due = env.clock.now + timedelta(days=6, hours=2)
        draft = RtiDraft("Road expenditure", "Public Works Department", ("q",), "Asha", "12 Cross Road Bengaluru")
        with env.uow() as u:
            u.rti.add(RtiApplication("r1", "cit-1", draft, RtiStatus.FILED, "RTI-1", due_at=due))
            u.commit()
        svc = RtiReminderService(env.factory, env.notifications, RtiRules(), env.bus)
        self.assertEqual(svc.run(env.clock.now), {"reminders_sent": 1})
        self.assertEqual(svc.run(env.clock.now), {"reminders_sent": 0})
        n = next(iter(env.stores.notifications.values()))
        self.assertEqual((n.kind, n.user_id), ("rti.deadline", "cit-1"))
        self.assertEqual(env.stores.rti["r1"].reminders_sent, (7,))
        self.assertEqual(len(env.bus.of("notification.created")), 1)


_ = (replace, MemoryUow, complaint_input, FakeClock)

if __name__ == "__main__":
    unittest.main()
