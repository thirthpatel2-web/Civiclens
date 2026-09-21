"""Adapter behaviour against a local STUB server (test double, not a government system)."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.integrations.adapters import ADAPTER_CLASSES, CPGRAMSAdapter, build_adapters
from app.integrations.base import (
    AdapterConfig,
    IntegrationState,
    OperationStatus,
    TransportError,
    assert_safe_url,
)
from app.integrations.health import IntegrationHealthService


class Stub(BaseHTTPRequestHandler):
    hits: list[dict] = []
    script: list[tuple[int, object]] = []

    def log_message(self, *a):
        pass

    def _handle(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n)) if n else None
        Stub.hits.append({"method": method, "path": self.path, "headers": dict(self.headers), "body": body})
        code, payload = Stub.script.pop(0) if Stub.script else (200, {"reference": "EXT-1", "status": "Registered", "remarks": "ok"})
        if code == 302:
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/internal")
            self.end_headers()
            return
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


ENDPOINTS = {"health": "/health", "submit": "/grievances", "status": "/grievances", "update": "/grievances/update", "reference": "/grievances/ref", "sync": "/sync"}
SECRET = "sk-live-VERY-SECRET-KEY"


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Stub.hits, Stub.script = [], []
        self.sleeps, self.audit = [], []

    def adapter(self, **kw):
        cfg = AdapterConfig(**{"base_url": self.url, "api_key": SECRET, "endpoints": ENDPOINTS, "timeout_seconds": 3, "max_retries": 2,
                               "backoff_seconds": 0.5, "allow_private_hosts": True, "allow_insecure_http": True, **kw})  # fmt: skip
        return CPGRAMSAdapter(cfg, sleep=self.sleeps.append, audit=lambda a, m: self.audit.append((a, m)))

    # ------------------------------------------------------------ NOT_CONFIGURED
    def test_every_adapter_is_not_configured_without_credentials_and_makes_no_request(self):
        adapters = build_adapters({})
        self.assertEqual(set(adapters), {"cpgrams", "umang", "swachhata", "bbmp_sahaaya", "mygov"})
        for name, a in adapters.items():
            self.assertFalse(a.is_configured(), name)
            self.assertIs(a.state, IntegrationState.NOT_CONFIGURED)
            report = a.health_check()
            self.assertIs(report.state, IntegrationState.NOT_CONFIGURED)
            self.assertIn("base_url", report.detail)
            for res in (a.submit_grievance({"t": 1}, idempotency_key="k"), a.get_status("X"), a.update_status("X", "Resolved", idempotency_key="k"),
                        a.add_reference("X", "CL-1", idempotency_key="k"), a.synchronize()):  # fmt: skip
                self.assertIs(res.status, OperationStatus.NOT_CONFIGURED)
                self.assertFalse(res.ok)
                self.assertEqual(res.attempts, 0)
        self.assertEqual(Stub.hits, [])

    def test_partial_configuration_is_still_not_configured(self):
        for cfg in (AdapterConfig(base_url=self.url), AdapterConfig(base_url=self.url, api_key="k"), AdapterConfig(api_key="k", endpoints=ENDPOINTS),
                    AdapterConfig(base_url=self.url, api_key="k", endpoints={"health": "/h"})):  # fmt: skip
            a = CPGRAMSAdapter(cfg)
            self.assertIs(a.health_check().state, IntegrationState.NOT_CONFIGURED)
        self.assertEqual(Stub.hits, [])

    def test_from_env_reads_prefix_and_endpoint_variables(self):
        env = {"CPGRAMS_BASE_URL": "https://x.example/", "CPGRAMS_API_KEY": "k", "CPGRAMS_ENDPOINT_HEALTH": "/h", "CPGRAMS_ENDPOINT_SUBMIT": "/s",
               "CPGRAMS_ENDPOINT_STATUS": "/st", "MYGOV_BASE_URL": "https://m.example", "MYGOV_API_KEY": "k"}  # fmt: skip
        a = build_adapters(env)
        self.assertTrue(a["cpgrams"].is_configured())
        self.assertEqual(a["cpgrams"].config.base_url, "https://x.example")
        self.assertFalse(a["mygov"].is_configured())  # key + url but no endpoints: nothing invented

    def test_missing_optional_endpoint_reports_not_configured_without_request(self):
        a = self.adapter(endpoints={"health": "/h", "submit": "/s", "status": "/st"})
        self.assertIs(a.update_status("X", "Resolved", idempotency_key="k").status, OperationStatus.NOT_CONFIGURED)
        self.assertEqual(Stub.hits, [])

    # ----------------------------------------------------------------- success
    def test_health_check_connected_and_metrics(self):
        a = self.adapter()
        r = a.health_check()
        self.assertIs(r.state, IntegrationState.CONNECTED)
        self.assertIsNotNone(r.last_success_at)
        self.assertEqual((r.total_calls, r.total_failures), (1, 0))
        self.assertIsNotNone(r.avg_response_ms)
        self.assertEqual(Stub.hits[0]["headers"]["Authorization"], f"Bearer {SECRET}")

    def test_submit_success_is_normalised_and_carries_idempotency_key(self):
        a = self.adapter()
        res = a.submit_grievance({"title": "Pothole"}, idempotency_key="idem-1")
        self.assertIs(res.status, OperationStatus.SUCCESS)
        self.assertEqual((res.data.external_reference, res.data.status, res.data.remarks), ("EXT-1", "Registered", "ok"))
        self.assertEqual(Stub.hits[0]["headers"]["Idempotency-Key"], "idem-1")
        self.assertEqual(Stub.hits[0]["body"], {"title": "Pothole"})

    def test_field_map_normalisation(self):
        Stub.script = [(200, {"grievance_no": "G-9", "state": "Closed", "note": "done", "ts": "2026-01-01"})]
        a = self.adapter(field_map={"reference": "grievance_no", "status": "state", "remarks": "note", "updated_at": "ts"})
        d = a.get_status("G-9").data
        self.assertEqual((d.external_reference, d.status, d.remarks, d.updated_at), ("G-9", "Closed", "done", "2026-01-01"))
        self.assertEqual(Stub.hits[0]["path"], "/grievances/G-9")

    def test_status_reference_is_validated_before_any_request(self):
        a = self.adapter()
        for bad in ("../admin?x=1", "..", "a/b", "", "x" * 200, "ref with space", "-lead"):
            res = a.get_status(bad)
            self.assertEqual(res.status, OperationStatus.FAILED, bad)
            self.assertEqual(res.attempts, 0)
        self.assertEqual(Stub.hits, [])
        self.assertTrue(a.get_status("CPG-2026:0042.a").ok)
        self.assertEqual(Stub.hits[0]["path"], "/grievances/CPG-2026%3A0042.a")

    # ----------------------------------------------------------------- failures
    def test_retries_5xx_with_backoff_then_succeeds_using_same_idempotency_key(self):
        Stub.script = [(503, {}), (503, {}), (200, {"reference": "EXT-2", "status": "ok"})]
        res = self.adapter().submit_grievance({"t": 1}, idempotency_key="idem-2")
        self.assertIs(res.status, OperationStatus.SUCCESS)
        self.assertEqual(res.attempts, 3)
        self.assertEqual(self.sleeps, [0.5, 1.0])
        self.assertEqual({h["headers"]["Idempotency-Key"] for h in Stub.hits}, {"idem-2"})

    def test_gives_up_after_max_retries_and_reports_failed_and_unavailable(self):
        Stub.script = [(500, {})] * 5
        a = self.adapter()
        res = a.submit_grievance({"t": 1}, idempotency_key="k")
        self.assertEqual((res.status, res.attempts, res.http_status), (OperationStatus.FAILED, 3, 500))
        Stub.script = [(500, {})] * 5
        self.assertIs(a.health_check().state, IntegrationState.UNAVAILABLE)
        self.assertIsNotNone(a.health_snapshot().last_error)

    def test_client_errors_are_not_retried(self):
        Stub.script = [(400, {"error": "bad"})]
        res = self.adapter().submit_grievance({"t": 1}, idempotency_key="k")
        self.assertEqual((res.status, res.attempts, len(Stub.hits)), (OperationStatus.FAILED, 1, 1))

    def test_429_is_retried(self):
        Stub.script = [(429, {}), (200, {"reference": "E"})]
        self.assertTrue(self.adapter().submit_grievance({}, idempotency_key="k").ok)

    def test_timeout_is_a_failure_not_a_success(self):
        a = self.adapter(base_url="http://127.0.0.1:1", max_retries=1)
        res = a.submit_grievance({}, idempotency_key="k")
        self.assertEqual((res.status, res.attempts), (OperationStatus.FAILED, 2))
        self.assertIn("network error", res.error)
        self.assertIs(a.health_check().state, IntegrationState.UNAVAILABLE)

    def test_invalid_body_on_2xx_is_failure(self):
        Stub.script = [(200, b"<html>gateway</html>")]
        res = self.adapter().submit_grievance({}, idempotency_key="k")
        self.assertEqual(res.status, OperationStatus.FAILED)

    def test_redirects_are_not_followed(self):
        Stub.script = [(302, {})]
        res = self.adapter(max_retries=0).submit_grievance({}, idempotency_key="k")
        self.assertEqual((res.status, res.http_status), (OperationStatus.FAILED, 302))
        self.assertEqual(len(Stub.hits), 1)

    # ---------------------------------------------------------------------- SSRF
    def test_ssrf_guard(self):
        for url in ("http://example.com/x", "ftp://example.com", "https://user:pw@example.com/", "https:///nohost"):
            with self.assertRaises(TransportError, msg=url):
                assert_safe_url(url, allow_private=False, allow_http=False)
        for url in ("https://127.0.0.1/x", "https://10.0.0.5/x", "https://169.254.169.254/latest", "https://[::1]/x", "https://192.168.1.1/"):
            with self.assertRaises(TransportError, msg=url):
                assert_safe_url(url, allow_private=False, allow_http=False)
        assert_safe_url("http://127.0.0.1:8000/x", allow_private=True, allow_http=True)

    def test_private_target_refused_by_default_without_retry_or_request(self):
        a = self.adapter(allow_private_hosts=False, allow_insecure_http=False)
        res = a.submit_grievance({}, idempotency_key="k")
        self.assertEqual((res.status, res.attempts), (OperationStatus.FAILED, 1))
        self.assertEqual(Stub.hits, [])

    # ------------------------------------------------------- secrets and audit
    def test_api_key_never_appears_in_audit_errors_repr_or_reports(self):
        Stub.script = [(500, {})] * 3
        a = self.adapter()
        res = a.submit_grievance({"t": 1}, idempotency_key="k")
        blob = repr(self.audit) + repr(res) + repr(a.health_snapshot()) + repr(a.config)
        self.assertNotIn(SECRET, blob)
        self.assertEqual(self.audit[0][0], "integration.request")
        self.assertEqual(self.audit[0][1]["operation"], "submit_grievance")
        self.assertNotIn("body", self.audit[0][1])

    # ------------------------------------------------------------ health service
    def test_health_service_persists_and_announces_only_changes(self):
        class Repo:
            def __init__(self): self.rows = {}
            def save(self, r): self.rows[r.platform] = r
            def latest(self, p): return self.rows.get(p)
        events = []
        svc = IntegrationHealthService(Repo(), lambda p, old, new: events.append((p, old, new)))
        adapters = build_adapters({}) | {"cpgrams": self.adapter()}
        reports = {r.platform: r.state for r in svc.check_all(adapters)}
        self.assertIs(reports["cpgrams"], IntegrationState.CONNECTED)
        self.assertIs(reports["umang"], IntegrationState.NOT_CONFIGURED)
        self.assertEqual(len(events), 5)
        svc.check_all(adapters)
        self.assertEqual(len(events), 5)  # unchanged -> no new events
        Stub.script = [(500, {})] * 5
        svc.check_all(adapters)
        self.assertEqual(events[-1], ("cpgrams", "CONNECTED", "UNAVAILABLE"))

    def test_five_platform_adapters_exist_with_distinct_identity(self):
        self.assertEqual(len({c.platform for c in ADAPTER_CLASSES}), 5)


if __name__ == "__main__":
    unittest.main()
