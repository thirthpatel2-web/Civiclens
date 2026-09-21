"""HTTP-level tests of the FastAPI application (routers, cookies, CSRF, RBAC, WebSocket).

ENVIRONMENT-DEPENDENT: these need ``fastapi`` and ``httpx`` (see requirements.txt). They are skipped, visibly,
where those packages are missing - which was the case in the build sandbox, so they have NOT been executed yet.
They run against the real application factory with in-memory repositories and Redis/Ollama test doubles.
"""

import importlib.util
import unittest

HAVE = bool(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"))

if HAVE:
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.realtime.websocket_manager import LocalEventBus
    from tests.end_to_end.test_full_flow import PW, Sys
    from tests.support import ReferenceTotp


@unittest.skipUnless(HAVE, "fastapi/httpx not installed in this environment")
class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.s = Sys(bus_factory=LocalEventBus)
        self.app = create_app(self.s.c, with_ui=False)
        self.client = TestClient(self.app)
        # Entering as a context manager runs the ASGI lifespan, which binds the event-bus/websocket
        # loop (app.main's lifespan calls c.ws.bind_loop / c.bus.bind_loop) - without it, LocalEventBus
        # silently no-ops and any test waiting on a pushed websocket message would hang forever.
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    # ------------------------------------------------------------------ helpers
    def signup(self, email="asha@example.com", client=None):
        client = client or self.client
        r = client.post("/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Asha Rao"})
        self.assertEqual(r.status_code, 201, r.text)
        r = client.post("/api/v1/auth/login", json={"email": email, "password": PW})
        self.assertEqual(r.status_code, 200, r.text)
        return {"X-CSRF-Token": r.json()["csrf_token"]}

    def complaint(self, headers, **kw):
        body = {"title": "Big pothole on MG Road", "description": "A very large pothole near the bus stop is causing accidents", "lat": 12.9716, "lng": 77.5946, **kw}
        return self.client.post("/api/v1/complaints", json=body, headers=headers)

    # ------------------------------------------------------------------ auth & sessions
    def test_register_login_me_protected_logout_invalidates_session(self):
        h = self.signup()
        me = self.client.get("/api/v1/auth/me")
        self.assertEqual((me.status_code, me.json()["user"]["role"], me.json()["user"]["email"]), (200, "citizen", "asha@example.com"))
        self.assertEqual(self.client.get("/api/v1/complaints").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/logout", headers=h).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/complaints").status_code, 401)

    def test_session_cookie_is_httponly_samesite_and_role_field_is_rejected(self):
        self.client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": PW, "full_name": "Asha Rao"})
        r = self.client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": PW})
        cookie = r.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        bad = self.client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": PW, "full_name": "Bad Actor", "role": "admin"})
        self.assertEqual(bad.status_code, 422)
        self.assertFalse(any(u.email == "b@example.com" for u in self.s.stores.users.values()))

    def test_bad_password_and_duplicate_registration(self):
        self.signup()
        self.assertEqual(self.client.post("/api/v1/auth/login", json={"email": "asha@example.com", "password": "wrong-password-1"}).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/register", json={"email": "asha@example.com", "password": PW, "full_name": "Asha Rao"}).status_code, 409)

    def test_csrf_is_required_for_state_changing_requests(self):
        h = self.signup()
        self.assertEqual(self.complaint({}).status_code, 403)
        self.assertEqual(self.complaint({"X-CSRF-Token": "forged"}).status_code, 403)
        self.assertEqual(self.complaint(h).status_code, 201)

    def test_cross_origin_state_change_is_rejected(self):
        h = self.signup()
        r = self.client.post("/api/v1/complaints", json={}, headers={**h, "Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)

    def test_two_factor_enrolment_and_login_require_otp(self):
        h = self.signup()
        enrol = self.client.post("/api/v1/auth/mfa/enroll", headers=h).json()
        secret = enrol["manual_entry_secret"]
        self.assertTrue(enrol["provisioning_uri"].startswith("otpauth://totp/"))
        code = ReferenceTotp.code_at(secret, self.s.clock.epoch())
        conf = self.client.post("/api/v1/auth/mfa/confirm", json={"otp": code}, headers=h)
        self.assertEqual(len(conf.json()["backup_codes"]), 8)
        self.client.post("/api/v1/auth/logout", headers=h)
        r = self.client.post("/api/v1/auth/login", json={"email": "asha@example.com", "password": PW})
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (401, "mfa_required"))
        self.s.clock.advance(seconds=30)
        ok = self.client.post("/api/v1/auth/login", json={"email": "asha@example.com", "password": PW, "otp": ReferenceTotp.code_at(secret, self.s.clock.epoch())})
        self.assertEqual((ok.status_code, ok.json()["mfa_verified"]), (200, True))

    def test_admin_bootstrap_disabled_without_token(self):
        r = self.client.post("/api/v1/auth/admin/bootstrap", json={"email": "root@gov.example", "password": PW, "full_name": "Root", "setup_token": "x"})
        self.assertEqual(r.status_code, 404)

    def test_password_reset_never_reveals_account_existence(self):
        self.signup()
        a = self.client.post("/api/v1/auth/password/forgot", json={"email": "asha@example.com"})
        b = self.client.post("/api/v1/auth/password/forgot", json={"email": "nobody@example.com"})
        self.assertEqual((a.status_code, a.json()), (b.status_code, b.json()))

    # ------------------------------------------------------------------ RBAC
    def test_citizen_cannot_reach_officer_or_admin_routes(self):
        h = self.signup()
        for method, url in (("get", "/api/v1/admin/users"), ("get", "/api/v1/admin/audit"), ("get", "/api/v1/officer/queue"), ("get", "/api/v1/dashboards/admin"), ("get", "/api/v1/monitoring/queue"), ("post", "/api/v1/officer/investigations")):
            r = getattr(self.client, method)(url, **({"headers": h, "json": {}} if method == "post" else {}))
            self.assertIn(r.status_code, (403, 422), (url, r.status_code))
            self.assertNotEqual(r.status_code, 200)

    def test_unauthenticated_requests_are_401_and_errors_are_structured(self):
        r = self.client.get("/api/v1/complaints")
        self.assertEqual(r.status_code, 401)
        body = r.json()["error"]
        self.assertEqual(body["code"], "authentication_failed")
        self.assertIn("correlation_id", body)
        self.assertIn("x-request-id", r.headers)
        self.assertNotIn("Traceback", r.text)

    # ------------------------------------------------------------------ complaints
    def test_complaint_create_track_and_isolation(self):
        h = self.signup()
        r = self.complaint(h)
        self.assertEqual(r.status_code, 201, r.text)
        cm = r.json()["complaint"]
        self.assertTrue(cm["reference"].startswith("CL-"))
        self.assertEqual((cm["category"], cm["department_code"]), ("roads", "roads"))
        detail = self.client.get(f"/api/v1/complaints/{cm['id']}").json()
        self.assertEqual(detail["timeline"][0]["label"], "Submitted")
        other = TestClient(self.app)
        h2 = self.signup("bala@example.com", client=other)
        self.assertEqual(other.get(f"/api/v1/complaints/{cm['id']}").status_code, 404)
        self.assertEqual(self.complaint(h, title="x").status_code, 422)
        _ = h2

    def test_idempotent_complaint_submission_via_client_request_id(self):
        h = self.signup()
        a = self.complaint(h, client_request_id="offline-req-0001").json()
        b = self.complaint(h, client_request_id="offline-req-0001").json()
        self.assertEqual((a["replayed"], b["replayed"], a["complaint"]["id"] == b["complaint"]["id"]), (False, True, True))

    # ------------------------------------------------------------------ RAG surface
    def test_rag_endpoints_are_post_only_and_grounded(self):
        h = self.signup()
        for url in ("/api/v1/rag/query", "/api/v1/rag/retrieve", "/api/v1/assistant/ask", "/api/v1/assistant/chat"):
            self.assertEqual(self.client.get(url).status_code, 405, url)
        r = self.client.post("/api/v1/rag/query", json={"question": "What does the ward budget say about drainage?"}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["status"], r.json()["citations"]), ("insufficient_evidence", []))

    def test_legal_analyzer_reports_metadata_only_limits(self):
        h = self.signup()
        r = self.client.post("/api/v1/legal/analyze", json={"problem": "Eldeco Housing versus buyer possession delay"}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["precedents"][0]["neutralCitation"], "2023 INSC 1043")
        self.assertTrue(any("no judgment text" in x for x in r.json()["bias_and_coverage"]))

    # ------------------------------------------------------------------ RTI, GIS, monitoring, headers
    def test_rti_lifecycle_and_pdf_download(self):
        h = self.signup()
        body = {"subject": "Road repair expenditure", "public_authority": "Public Works Department", "questions": ["Sanctioned amount?"], "applicant_name": "Asha Rao", "applicant_address": "12 Cross Road, Bengaluru 560011"}
        rid = self.client.post("/api/v1/rti", json=body, headers=h).json()["id"]
        self.assertEqual(self.client.post(f"/api/v1/rti/{rid}/generate", headers=h).json()["status"], "generated")
        self.assertEqual(self.client.post(f"/api/v1/rti/{rid}/file", json={}, headers=h).json()["status"], "filed")
        pdf = self.client.get(f"/api/v1/rti/{rid}/pdf")
        self.assertEqual((pdf.status_code, pdf.headers["content-type"], pdf.content[:4]), (200, "application/pdf", b"%PDF"))
        other = TestClient(self.app)
        self.signup("bala@example.com", client=other)
        self.assertEqual(other.get(f"/api/v1/rti/{rid}").status_code, 404)

    def test_gis_health_ready_and_security_headers(self):
        self.signup()
        self.assertEqual(self.client.get("/api/v1/gis/radar").json()["ward_boundaries"], "not_available")
        self.assertEqual(self.client.get("/api/v1/monitoring/health").json()["status"], "ok")
        ready = self.client.get("/api/v1/monitoring/ready").json()
        self.assertEqual(ready["checks"]["ollama"]["status"], "not_configured")
        r = self.client.get("/health")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertEqual(r.headers["x-frame-options"], "DENY")

    # ------------------------------------------------------------------ WebSocket
    def test_websocket_requires_a_session_and_isolates_citizens(self):
        from starlette.websockets import WebSocketDisconnect

        with self.assertRaises(WebSocketDisconnect):
            with TestClient(self.app).websocket_connect("/ws"):
                pass
        h = self.signup()
        with self.client.websocket_connect("/ws") as ws:
            ws.send_text("ping")
            self.assertEqual(ws.receive_json()["type"], "pong")
            self.complaint(h)
            msg = ws.receive_json()
            self.assertIn(msg["type"], ("complaint.created", "notification.created"))
            self.assertNotIn("internal", msg)  # citizens never receive staff-only detail


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE, "fastapi/httpx not installed in this environment")
class MobileAndReleaseHttpTests(unittest.TestCase):
    """Bearer/mobile flows and the release-scope endpoints (skipped here; run wherever FastAPI is installed)."""

    def setUp(self):
        self.s = Sys(bus_factory=LocalEventBus)
        self.app = create_app(self.s.c, with_ui=False)
        self.client = TestClient(self.app)

    signup = HttpApiTests.signup
    complaint = HttpApiTests.complaint

    def mobile_login(self, email="mob@example.com"):
        self.client.post("/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Mobile User"})
        r = self.client.post("/api/v1/auth/mobile/login", json={"email": email, "password": PW})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_mobile_bearer_session_needs_no_csrf_has_no_cookie_and_is_revocable(self):
        body = self.mobile_login()
        self.assertEqual(body["token_type"], "Bearer")
        self.assertNotIn("set-cookie", {k.lower() for k in self.client.post("/api/v1/auth/mobile/login", json={"email": "mob@example.com", "password": PW}).headers})
        auth = {"Authorization": f"Bearer {body['session_token']}"}
        fresh = TestClient(self.app)  # no cookies at all
        self.assertEqual(fresh.get("/api/v1/auth/me", headers=auth).json()["user"]["email"], "mob@example.com")
        made = fresh.post("/api/v1/complaints", json={"title": "Pothole on MG Road", "description": "A large pothole near the bus stop is dangerous", "lat": 12.9716, "lng": 77.5946}, headers=auth)
        self.assertEqual(made.status_code, 201, made.text)  # state change without a CSRF token: safe because Bearer is never auto-attached by a browser
        self.assertEqual(fresh.post("/api/v1/complaints", json={}, headers={"Authorization": "Bearer forged"}).status_code, 401)
        self.assertEqual(fresh.post("/api/v1/auth/logout", headers=auth).status_code, 200)
        self.assertEqual(fresh.get("/api/v1/auth/me", headers=auth).status_code, 401)

    def test_web_login_never_returns_the_raw_session_token_in_the_body(self):
        h = self.signup("web@example.com")
        me = self.client.get("/api/v1/auth/me").json()
        self.assertNotIn("session_token", me)
        r = self.client.post("/api/v1/auth/login", json={"email": "web@example.com", "password": PW})
        self.assertNotIn("session_token", r.json())
        _ = h

    def test_emergency_helplines_are_public_and_honest_when_unconfigured(self):
        r = TestClient(self.app).get("/api/v1/emergency/helplines", params={"lang": "hi"})
        self.assertEqual((r.status_code, r.json()["configured"], r.json()["items"]), (200, False, []))
        self.s.c.emergency.seed_defaults()
        self.assertEqual(len(TestClient(self.app).get("/api/v1/emergency/helplines").json()["items"]), 6)

    def test_voice_languages_reports_only_what_the_engine_supports(self):
        self.signup()
        caps = self.client.get("/api/v1/voice/languages").json()
        self.assertEqual((caps["state"], caps["languages"]), ("NOT_CONFIGURED", []))
        r = self.client.post("/api/v1/voice/transcribe", files={"audio": ("v.wav", b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32, "audio/wav")}, data={"language": "kn"}, headers=self.csrf())
        self.assertEqual((r.status_code, r.json()["status"], r.json()["transcript"]), (200, "NOT_CONFIGURED", None))

    def csrf(self):
        return {"X-CSRF-Token": self.client.get("/api/v1/auth/me").json()["csrf_token"]}

    def test_devices_government_states_and_evidence_access(self):
        h = self.signup()
        self.assertEqual(self.client.post("/api/v1/notifications/devices", json={"token": "ExponentPushToken[abc123]", "platform": "android"}, headers=h).status_code, 204)
        cid = self.complaint(h).json()["complaint"]["id"]
        states = self.client.get(f"/api/v1/complaints/{cid}/government-submissions").json()["items"]
        self.assertTrue(states and all(s["state"] == "not_started" and s["adapter_state"] == "NOT_CONFIGURED" for s in states))
        r = self.client.post(f"/api/v1/complaints/{cid}/government-submissions", json={"platform": "cpgrams"}, headers=h)
        self.assertEqual((r.status_code, r.json()["state"]), (202, "consent_required"))
        ev = self.client.post("/api/v1/complaints/evidence", files={"file": ("p.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "image/png")}, headers=h).json()
        other = TestClient(self.app)
        self.signup("bala@example.com", client=other)
        self.assertEqual(other.get(f"/api/v1/complaints/evidence/{ev['id']}/file").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/complaints/evidence/{ev['id']}/file").status_code, 200)

