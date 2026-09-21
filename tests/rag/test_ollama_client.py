"""Exercises OllamaClient against a local *stub* HTTP server (test double, not Ollama)."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.core.exceptions import DependencyUnavailable, NotConfigured
from app.rag.ollama import (
    OllamaChatProvider,
    OllamaClient,
    OllamaEmbeddingProvider,
    probe,
    validate_base_url,
)


class Stub(BaseHTTPRequestHandler):
    mode = "ok"
    seen: list[tuple[str, str, dict]] = []

    def log_message(self, *a):  # silence
        pass

    def _send(self, code, body):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        Stub.seen.append(("GET", self.path, {}))
        if self.path == "/api/tags":
            self._send(200, {"models": [{"name": "embed-x:latest"}, {"name": "chat-y"}]})
        else:
            self._send(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Stub.seen.append(("POST", self.path, body))
        if Stub.mode == "http500":
            return self._send(500, {"error": "boom"})
        if Stub.mode == "garbage":
            return self._send(200, b"not json")
        if self.path == "/api/embed":
            n = 2 if Stub.mode == "wrongcount" else len(body["input"])
            dim = 5 if Stub.mode == "wrongdim" else 3
            return self._send(200, {"embeddings": [[0.1] * dim for _ in range(n)]})
        if self.path == "/api/chat":
            return self._send(200, {"message": {"role": "assistant", "content": "hello [E1]"}})
        self._send(404, {})


class OllamaClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Stub)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Stub.mode, Stub.seen = "ok", []
        self.client = OllamaClient(self.url, timeout=5)

    def test_embed_sends_configured_model_and_batches(self):
        vecs = OllamaEmbeddingProvider(self.client, "embed-x", 3).embed(["a", "b"])
        self.assertEqual(len(vecs), 2)
        method, path, body = Stub.seen[-1]
        self.assertEqual((method, path, body["model"], body["input"]), ("POST", "/api/embed", "embed-x", ["a", "b"]))

    def test_dimension_mismatch_is_an_error_not_silent(self):
        Stub.mode = "wrongdim"
        with self.assertRaises(DependencyUnavailable) as cm:
            OllamaEmbeddingProvider(self.client, "embed-x", 3).embed(["a"])
        self.assertIn("EMBEDDING_DIMENSIONS", cm.exception.message)

    def test_dimension_learned_when_unset(self):
        p = OllamaEmbeddingProvider(self.client, "embed-x", 0)
        p.embed(["a"])
        self.assertEqual(p.dimensions, 3)

    def test_wrong_vector_count_and_http_error_and_garbage(self):
        for mode in ("wrongcount", "http500", "garbage"):
            Stub.mode = mode
            with self.assertRaises(DependencyUnavailable, msg=mode):
                self.client.embed("m", ["a", "b", "c"])

    def test_chat_payload_and_reply(self):
        reply = OllamaChatProvider(self.client, "chat-y").chat([{"role": "user", "content": "hi"}], temperature=0.2)
        self.assertEqual(reply, "hello [E1]")
        _, path, body = Stub.seen[-1]
        self.assertEqual((path, body["model"], body["stream"], body["options"]["temperature"]), ("/api/chat", "chat-y", False, 0.2))

    def test_unconfigured_models_are_reported_not_guessed(self):
        with self.assertRaises(NotConfigured):
            OllamaChatProvider(self.client, "")
        with self.assertRaises(NotConfigured):
            OllamaEmbeddingProvider(self.client, "")

    def test_unreachable_server(self):
        dead = OllamaClient("http://127.0.0.1:1", timeout=1)
        with self.assertRaises(DependencyUnavailable):
            dead.chat("m", [{"role": "user", "content": "x"}])

    def test_probe_reports_missing_models(self):
        ok, detail, _ = probe(self.client, ["embed-x", "chat-y"])
        self.assertTrue(ok)
        ok2, detail2, _ = probe(self.client, ["embed-x", "not-pulled"])
        self.assertFalse(ok2)
        self.assertIn("not-pulled", detail2)
        self.assertFalse(probe(OllamaClient("http://127.0.0.1:1", timeout=1), [])[0])

    def test_base_url_validation(self):
        for bad in ("ftp://x", "file:///etc/passwd", "http://user:pw@host", "notaurl"):
            with self.assertRaises(ValueError, msg=bad):
                validate_base_url(bad)
        self.assertEqual(validate_base_url("http://localhost:11434/"), "http://localhost:11434")


if __name__ == "__main__":
    unittest.main()
