"""End-to-end flow through the REAL composition root (AppContainer) and every service, on in-memory
repositories and test doubles for Redis/Ollama. It exercises wiring and behaviour across layers.

What this does NOT prove: HTTP, PostgreSQL, Redis, Ollama, browser/UI. Those are environment-dependent.
"""

import json
import logging
import unittest
from datetime import timedelta
from pathlib import Path

from app.container import AppContainer
from app.core.authorization import Role
from app.core.config import Settings
from app.core.exceptions import AuthenticationFailed, NotFound, PermissionDenied
from app.core.security import SecretBox
from app.legal.precedents import load_records
from app.rag.ollama import OllamaChatProvider  # noqa: F401  (documented provider type)
from app.rag.vector_search import InMemoryVectorIndex
from app.realtime.events import may_receive
from app.realtime.websocket_manager import WebSocketManager
from app.services.complaint_service import ComplaintInput
from app.services.complaint_status import ComplaintStatus as S
from app.services.document_service import DocumentIngestor
from app.services.rti_service import RtiDraft
from tests.rag.helpers import DIM, HashingEmbedder, ScriptedChat
from tests.support import FakeClock, ReferenceTotp, ScryptTestHasher
from tests.support_env import PNG
from tests.support_mem import MemQueueBackend, MemStorage, RecordingBus, Stores, uow_factory

FIXTURE = json.loads((Path(__file__).parent.parent / "fixtures" / "sc_metadata_sample.json").read_text(encoding="utf-8"))
PW = "a-long-enough-passphrase"


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


class Sys:
    """A booted system + helpers to sign users in through AuthService exactly as the API/UI do."""

    def __init__(self, bus_factory=None):
        self.clock, self.stores = FakeClock(), Stores()
        self.ws = WebSocketManager()
        self.bus = bus_factory(self.ws) if bus_factory else RecordingBus()
        self.chat = ScriptedChat()
        self.totp = ReferenceTotp()
        self.storage = MemStorage()
        self.c = AppContainer(Settings.load({}), uow_factory(self.stores), ScryptTestHasher(), SecretBox("e2e-secret-key-e2e-secret-key!"), self.totp, self.storage, MemQueueBackend(), self.bus, self.ws,
                              llm=self.chat, embedder=HashingEmbedder(), vector_index=InMemoryVectorIndex(DIM), clock=self.clock)  # fmt: skip
        self.c.precedents.__init__(load_records(FIXTURE)[0])  # type: ignore[misc]
        self.c.ingestor_factory = lambda uow: DocumentIngestor(uow.documents, self.storage, self.c.rag_index, embedder=self.c.embedder, clock=self.clock)
        self.c.worker._ingestor_factory = self.c.ingestor_factory
        self.secrets: dict[str, str] = {}
        with self.c.uow_factory() as uow:  # organisation reference data, as scripts/seed.py would
            uow.commit()

    def _uow(self, fn, commit_on_error=False):
        from app.core.transactions import run_in_uow

        return run_in_uow(self.c, fn, commit_on_error=commit_on_error)

    def register(self, email, name="Test User"):
        return self._uow(lambda u: self.c.auth_for(u).register(email, PW, name))

    def login(self, email, otp=None):
        return self._uow(lambda u: self.c.auth_for(u).login(email, PW, otp=otp), commit_on_error=True)

    def otp(self, email):
        self.clock.advance(seconds=30)
        return ReferenceTotp.code_at(self.secrets[email], self.clock.epoch())

    def enrol_mfa(self, ctx, email, token):
        def op(u):
            e = self.c.mfa_for(u).begin_enrollment(ctx.user_id, email)
            self.secrets[email] = e.manual_entry_secret
            code = ReferenceTotp.code_at(e.manual_entry_secret, self.clock.epoch())
            codes = self.c.mfa_for(u).confirm_enrollment(ctx.user_id, code)
            self.c.auth_for(u).mark_session_mfa_verified(token)
            return codes, e.provisioning_uri

        return self._uow(op)

    def auth(self, token):
        return self._uow(lambda u: self.c.auth_for(u).authenticate(token))


class FullFlowTests(unittest.TestCase):
    def test_complete_platform_flow(self):
        s = Sys()
        c = s.c

        # ---------------- admin bootstrap (once, token-guarded); two-factor is opt-in, never a gate
        with self.assertRaises(PermissionDenied):
            s._uow(lambda u: c.auth_for(u).bootstrap_first_admin("root@gov.example", PW, "Root Admin", provided_token="wrong", expected_token="setup-token-123"), commit_on_error=True)
        root = s._uow(lambda u: c.auth_for(u).bootstrap_first_admin("root@gov.example", PW, "Root Admin", provided_token="setup-token-123", expected_token="setup-token-123"))
        self.assertIs(root.role, Role.SUPER_ADMIN)
        first = s.login("root@gov.example")
        self.assertTrue(first.context.mfa_verified)
        c.admin.list_users(first.context)  # a privileged role works immediately, no second factor required
        admin = first.context

        # ---------------- admin configures staff, SLA policy and reference data
        off_roads = c.admin.create_staff(admin, "roads.officer@gov.example", PW, "Ravi Roads", Role.OFFICER, "roads")
        c.admin.create_staff(admin, "water.officer@gov.example", PW, "Wendy Water", Role.OFFICER, "water")
        s.stores.officers = {"roads": [off_roads.id], "water": []}  # directory is DB-derived in production; here mirrored for the memory double
        for pri, hrs in (("low", 240), ("medium", 72), ("high", 24), ("critical", 8)):
            c.admin.save_sla_policy(admin, f"default-{pri}", pri, hrs)
        c.admin.save_office(admin, "roads-hq", "Roads HQ", "roads", 12.97, 77.59, "MG Road")

        # ---------------- citizen: register, onboarding, 2FA, logout, login with OTP
        cit_user = s.register("asha@example.com", "Asha Rao")
        self.assertIs(cit_user.role, Role.CITIZEN)
        with self.assertRaises(AuthenticationFailed):
            s._uow(lambda u: c.auth_for(u).login("asha@example.com", "wrong-password-1"), commit_on_error=True)
        sess = s.login("asha@example.com")
        cit = sess.context
        c.profiles.update(cit, phone="9876543210", city="Bengaluru", ward="12", language="hi", complete_onboarding=True)
        c.profiles.set_consent(cit, "ai_processing", True)
        self.assertTrue(c.profiles.get(cit).onboarding_complete)
        s.enrol_mfa(cit, "asha@example.com", sess.session_token)
        s._uow(lambda u: c.auth_for(u).logout(sess.session_token))
        with self.assertRaises(AuthenticationFailed):
            s.auth(sess.session_token)  # logout really invalidated the server-side session
        cit = s.login("asha@example.com").context  # enrolled MFA still never blocks login
        self.assertEqual(c.dashboards.citizen(cit)["has_data"], False)

        # ---------------- complaint with evidence + location; classification/routing/duplicate/reference/SLA
        ev = c.complaints.upload_evidence(cit, "pothole.png", PNG)
        c.jobs.drain("noop")  # nothing queued yet
        res = c.complaints.create(cit, ComplaintInput("Big pothole on MG Road", "A very large pothole near the bus stop is causing accidents", "hi", lat=12.9716, lng=77.5946, ward="12", evidence_ids=[ev.id], client_request_id="offline-req-0001"))
        cm = res.complaint
        self.assertEqual((cm.category, cm.department_code, cm.status, cm.assigned_officer_id), ("roads", "roads", S.ASSIGNED, off_roads.id))
        self.assertIsNotNone(cm.sla_due_at)
        self.assertEqual(c.complaints.create(cit, ComplaintInput("Big pothole on MG Road", "A very large pothole near the bus stop is causing accidents", "hi", client_request_id="offline-req-0001")).complaint.id, cm.id)
        self.assertEqual(len(s.stores.complaints), 1)

        other = s.register("bala@example.com", "Bala K")
        bala = s.login("bala@example.com").context
        dup = c.complaints.create(bala, ComplaintInput("Big pothole on MG Road", "A very large pothole near the bus stop is causing accidents", lat=12.97161, lng=77.59461)).complaint
        self.assertEqual([d["complaint_id"] for d in dup.duplicates], [cm.id])
        with self.assertRaises(NotFound):
            c.complaints.detail_for_citizen(bala, cm.id)  # ownership enforced
        _ = other

        # ---------------- background processing (queue) - AI enrichment job for both complaints
        done = c.jobs.drain("worker-1")
        self.assertEqual({r.kind for r in done}, {"complaint.enrich"})
        self.assertTrue(all(r.status == "succeeded" for r in done))
        self.assertEqual(s.stores.evidence[ev.id].analysis_status, "IMAGE_ANALYSIS_UNAVAILABLE")  # no vision provider: stated, not faked

        # ---------------- officer workflow with department isolation
        officer = s.login("roads.officer@gov.example").context
        self.assertEqual({x.id for x in c.officer.queue(officer)}, {cm.id, dup.id})  # both roads complaints; nothing from other departments
        detail = c.officer.detail(officer, cm.id)
        self.assertEqual((len(detail["evidence"]), detail["sla"].state), (1, "on_track"))
        c.officer.update_status(officer, cm.id, S.UNDER_REVIEW)
        c.officer.field_visit(officer, cm.id, s.clock.now + timedelta(hours=3), "site check")
        c.officer.inspection(officer, cm.id, "40 cm wide, 8 cm deep")
        c.officer.work_order(officer, cm.id, "WO-1", "Cold-mix patching", "Crew B")
        c.officer.progress(officer, cm.id, 80)
        s.bus.events.clear()
        s.clock.advance(hours=4)
        c.officer.resolve(officer, cm.id, "Pothole filled and compacted")
        status_events = s.bus.of("complaint.status_changed")
        self.assertEqual(status_events[-1].payload["to"], "resolved")
        self.assertTrue(may_receive(cit, status_events[-1]))  # the owning citizen receives it ...
        self.assertFalse(may_receive(bala, status_events[-1]))  # ... another citizen does not
        with self.assertRaises(PermissionDenied):
            c.officer.queue(cit)

        # ---------------- citizen sees resolution, gives feedback
        d = c.complaints.detail_for_citizen(cit, cm.id)
        self.assertEqual((d["complaint"].status, d["timeline"][-1].state), (S.RESOLVED, "done"))
        self.assertNotIn("coordination", {e.kind for e in d["events"]})
        c.complaints.add_feedback(cit, cm.id, 5, "Thank you")
        notes = [n.kind for n in s.stores.notifications.values() if n.user_id == cit.user_id]
        self.assertIn("complaint.resolved", notes)

        # ---------------- SLA scan (scheduler task) leaves resolved work alone and escalates the overdue duplicate
        s.clock.advance(days=5)
        report = c.sla.scan(s.clock.now)
        self.assertEqual(report["escalated"], 1)

        # ---------------- RTI: draft -> save -> generate -> file -> countdown -> PDF
        def rti(u):
            svc = c.rti_for(u)
            a = svc.create(cit, RtiDraft("Road repair expenditure", "Public Works Department", ("Sanctioned amount for MG Road repair?",), "Asha Rao", "12 Cross Road, Bengaluru 560011"))
            svc.generate(cit, a.id)
            svc.mark_filed(cit, a.id)
            return a.id

        rid = s._uow(rti)
        app_, cd = s._uow(lambda u: c.rti_for(u).track(cit, rid))
        self.assertEqual((app_.status.value, cd.state, cd.days_remaining, cd.is_estimate), ("filed", "running", 30, True))
        self.assertTrue(s._uow(lambda u: c.rti_for(u).export_pdf(cit, rid)).startswith(b"%PDF"))
        s.clock.advance(days=24)
        self.assertEqual(c.rti_reminders.run(s.clock.now), {"reminders_sent": 1})
        self.assertIn("rti.deadline", {n.kind for n in s.stores.notifications.values()})

        # ---------------- legal analyzer on the real precedent metadata
        legal = c.legal.analyze(cit, "Dispute between Eldeco Housing and a flat buyer about builder possession delay")
        self.assertEqual(legal.result["precedents"][0]["neutralCitation"], "2023 INSC 1043")
        self.assertTrue(any("no judgment text" in x for x in legal.result["bias_and_coverage"]))
        self.assertEqual(c.legal.get_mine(cit, legal.id).id, legal.id)  # persisted and retrievable by its owner
        with self.assertRaises(NotFound):
            c.legal.get_mine(bala, legal.id)

        # ---------------- RAG: real document -> ingest job -> BM25+vector+RRF+rerank -> grounded answer with citation
        def upload(u):
            ing = c.ingestor_factory(u)
            doc = ing.upload(cit.user_id, "ward-budget.txt", b"1. Road Repair\nThe Roads Department allocated Rs. 5,00,000 for road repair in Ward 12 during 2025-26.", max_bytes=1_000_000)
            job, _ = c.jobs.enqueue(u, "document.ingest", {"document_id": doc.id}, f"ingest:{doc.id}")
            return doc, job

        doc, job = s._uow(upload)
        c.jobs.dispatch([job])
        self.assertEqual(c.jobs.drain("worker-1")[0].status, "succeeded")
        self.assertEqual(str(s.stores.documents[doc.id].status), "ready")
        # first reply: the multilingual router (not a records question); second: the grounded answer
        s.chat.replies = ['{"sqlFunction": null}', "Rs. 5,00,000 was allocated for road repair in Ward 12 [E1]."]
        ans = c.assistant.ask(cit, "What is allocated for road repair in Ward 12?")
        self.assertEqual((ans["status"], ans["citations"][0]["documentName"]), ("answered", "ward-budget.txt"))
        self.assertEqual(sorted(ans["citations"][0]["foundVia"]), ["bm25", "semantic"])
        # private document invisible to another citizen: at most clearly-labelled general guidance, never its content or citation
        s.chat.replies = ['{"sqlFunction": null}', "Ward budgets are published by the municipal corporation."]
        other = c.assistant.ask(bala, "What is allocated for road repair in Ward 12?")
        self.assertEqual((other["status"], other["citations"], other["database_facts"]), ("general_guidance", [], None))
        self.assertNotIn("5,00,000", other["answer"])

        # ---------------- GIS, dashboards, integrations, anomalies, audit (admin)
        gis = c.gis.radar(admin)
        self.assertEqual(gis["mappable"], 2)
        self.assertEqual([o["id"] for o in gis["offices"]], ["roads-hq"])
        self.assertEqual(c.gis.radar(cit)["hotspots"], [])  # k-anonymity: a group of 2 is hidden from citizens
        dash = c.dashboards.admin(admin)
        self.assertEqual((dash["total"], dash["resolved"]), (2, 1))
        self.assertTrue(all(v == "NOT_CONFIGURED" for v in dash["system"]["adapters"].values()))
        self.assertEqual(dash["system"]["queue"]["backend_reachable"], True)
        actions = {e.action for e in c.admin.audit_log(admin, limit=500)}
        for needed in ("auth.registered", "auth.login", "auth.logout", "mfa.enabled", "complaint.created", "complaint.status_changed", "complaint.field_visit", "complaint.work_order", "complaint.escalated", "admin.staff_created", "admin.sla_policy_saved", "consent.changed", "admin.audit_viewed"):
            self.assertIn(needed, actions)
        inv = c.investigations.open(admin, "complaint", cm.id)
        rep = c.investigations.report(admin, inv.id)
        self.assertEqual(rep["complaint"].reference, cm.reference)
        self.assertIn(rep["legal_sources"]["status"], ("precedents_only", "analysed", "no_verified_precedent"))  # looked up, never fabricated
        self.assertEqual(rep["rag_findings"]["status"] in ("answered", "insufficient_evidence", "ungrounded", "model_unavailable"), True)

        # ---------------- every scheduled task runs against the real wiring without raising
        s.clock.advance(hours=2)
        runs = {r.name: r for r in c.scheduler.tick()}
        self.assertTrue(all(r.ok for r in runs.values()), {k: v.error for k, v in runs.items() if not v.ok})
        self.assertIn("sla.scan", runs)
        self.assertEqual(runs["analytics.refresh"].summary["total"], 2)
        self.assertEqual(s.stores.snapshots[-1][0], "all")


class WiringTests(unittest.TestCase):
    def test_container_registers_all_job_handlers_and_scheduler_tasks(self):
        s = Sys()
        self.assertEqual(set(s.c.jobs.handlers), {"complaint.enrich", "notification.email", "notification.push", "gov.submit", "evidence.analyze", "document.ingest"})
        self.assertEqual({t.name for t in s.c.scheduler._tasks}, {"sla.scan", "rti.deadlines", "anomaly.detect", "queue.requeue_orphans", "integrations.health", "rag.index_refresh", "analytics.refresh", "workflow.sweep"})

    def test_missing_optional_dependencies_degrade_honestly(self):
        s = Sys()
        c = s.c
        self.assertIsNone(c.speech)
        from tests.support_env import CIT

        rec = c.voice.transcribe(CIT, b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32, "audio/wav", "hi")
        self.assertEqual((rec.status, rec.transcript), ("NOT_CONFIGURED", None))  # never a fake transcript
        for a in c.adapters.values():
            self.assertEqual(a.state.value, "NOT_CONFIGURED")
        with self.assertRaises(Exception) as cm:
            c.translation.translate("hello", "en", "hi")
        self.assertEqual(getattr(cm.exception, "code", ""), "not_configured")


if __name__ == "__main__":
    unittest.main()
