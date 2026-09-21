import json
import logging
import unittest
from datetime import UTC, datetime

from app.core.exceptions import DependencyUnavailable, NotConfigured, NotFound, ValidationFailed
from app.i18n.languages import detect_language
from app.integrations.base import TransportResponse
from app.providers.speech import BhashiniConfig, BhashiniProvider, sniff_audio
from app.providers.stt import SttCapabilities, Transcript
from app.providers.vision import analyze_evidence
from app.realtime.events import DomainEvent, event_from_json, event_to_json
from app.services.classification_service import ClassificationService
from app.services.notification_service import NotificationService
from app.services.ports import EvidenceRecord
from app.services.voice_service import TranslationService, VoiceService
from app.storage.providers import GoogleDriveStorageProvider
from app.workers.handlers import GrievanceWorker
from app.workers.redis_backend import (
    RedisEventBus,
    RedisLock,
    RedisQueueBackend,
    RedisSchedulerState,
)
from tests.rag.helpers import ScriptedChat
from tests.support_env import CIT, PNG, VAGUE, Env
from tests.support_mem import MemQueueBackend

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


class FakeVision:
    name = "fake-vision"

    def __init__(self, fail=False): self.fail = fail
    def analyze(self, image, mime):
        if self.fail:
            raise DependencyUnavailable("vision model down")
        return {"summary": "a pothole", "issue_category": "roads", "severity_hint": "high", "visible_text": "", "confidence": 0.8}


def worker_for(env, *, llm=None, vision=None, consent=True):
    ai = ClassificationService(llm) if llm is not None else None
    w = GrievanceWorker(env.factory, env.complaints, ai, vision, env.storage, env.fx, env.notifications, consent_check=lambda uid, purpose: consent)
    env.jobs.handlers.update(w.handlers())
    return w


class EnrichmentTests(unittest.TestCase):
    def test_end_to_end_through_the_queue_llm_routes_a_vague_complaint(self):
        llm = ScriptedChat('{"category": "water", "severity": "high", "confidence": 0.85, "reason": "supply problem"}')
        env = Env(llm=llm)
        worker_for(env, llm=llm)
        c = env.create(category=None, lat=None, lng=None, **VAGUE)
        self.assertEqual((c.category, c.department_code, c.status.value, c.ai_status), ("other", None, "submitted", "pending"))
        self.assertEqual(llm.calls, [])  # intake never calls a model
        env.bus.events.clear()
        res = env.jobs.drain("w1")
        self.assertEqual([(r.kind, r.status) for r in res], [("complaint.enrich", "succeeded")])
        after = env.stores.complaints[c.id]
        self.assertEqual((after.category, after.department_code, after.status.value, after.assigned_officer_id, after.ai_status), ("water", "water", "assigned", "off-water-1", "ok"))
        self.assertEqual(after.classification["source"], "llm")
        self.assertIsNotNone(after.sla_due_at)
        self.assertEqual([e.type for e in env.bus.events if e.type.startswith("complaint.")], ["complaint.processed"])
        self.assertIn("complaint.ai_enriched", env.actions())

    def test_without_consent_no_model_is_called(self):
        llm = ScriptedChat("should not be used")
        env = Env(llm=llm)
        worker_for(env, llm=llm, consent=False)
        c = env.create(lat=None, lng=None, **VAGUE)
        env.jobs.drain("w1")
        self.assertEqual(env.stores.complaints[c.id].ai_status, "consent_required")
        self.assertEqual(llm.calls, [])

    def test_model_outage_and_no_model_are_recorded_honestly(self):
        down = ScriptedChat(DependencyUnavailable("Ollama is unreachable."))
        env = Env(llm=down)
        worker_for(env, llm=down)
        c = env.create(lat=None, lng=None, **VAGUE)
        self.assertEqual(env.stores.complaints[c.id].ai_status, "pending")
        env.jobs.drain("w1")
        after = env.stores.complaints[c.id]
        self.assertEqual((after.ai_status, after.department_code, after.category), ("unavailable", None, "other"))
        env2 = Env()
        worker_for(env2)
        c2 = env2.create(lat=None, lng=None, **VAGUE)
        env2.jobs.drain("w1")
        self.assertEqual(env2.stores.complaints[c2.id].ai_status, "not_configured")

    def test_clear_complaints_skip_the_model_but_still_analyse_evidence(self):
        llm = ScriptedChat("unused")
        env = Env(llm=llm, vision=True)
        worker_for(env, llm=llm, vision=FakeVision())
        ev = env.complaints.upload_evidence(CIT, "p.png", PNG)
        c = env.create(evidence_ids=[ev.id])
        env.jobs.drain("w1")
        self.assertEqual(llm.calls, [])
        stored = env.stores.evidence[ev.id]
        self.assertEqual((stored.analysis_status, stored.analysis_provider, stored.analysis_result["issue_category"]), ("OK", "fake-vision", "roads"))
        self.assertEqual(env.stores.complaints[c.id].ai_status, "not_needed")

    def test_vision_failure_is_stored_never_fabricated(self):
        env = Env(vision=True)
        worker_for(env, vision=FakeVision(fail=True))
        ev = env.complaints.upload_evidence(CIT, "p.png", PNG)
        env.create(evidence_ids=[ev.id])
        env.jobs.drain("w1")
        s = env.stores.evidence[ev.id]
        self.assertEqual((s.analysis_status, s.analysis_result), ("FAILED", None))
        self.assertIn("vision model down", s.analysis_error)

    def test_analyze_evidence_states(self):
        env = Env()
        ev = EvidenceRecord("e", None, "u", "a.png", "image/png", 1, "h", "n.png")
        self.assertEqual(analyze_evidence(ev, env.storage, None).analysis_status, "IMAGE_ANALYSIS_UNAVAILABLE")
        doc = EvidenceRecord("d", None, "u", "a.txt", "text/plain", 1, "h", "n.txt")
        self.assertEqual(analyze_evidence(doc, env.storage, FakeVision()).analysis_status, "NOT_APPLICABLE")

    def test_missing_complaint_is_a_permanent_failure(self):
        env = Env()
        w = worker_for(env)
        with env.factory() as uow:
            job, _ = env.jobs.enqueue(uow, "complaint.enrich", {"complaint_id": "nope"}, "enrich:nope")
            uow.commit()
        env.jobs.dispatch([job])
        r = env.jobs.drain("w1")[0]
        self.assertEqual((r.status, r.attempts), ("dead", 1))
        _ = w

    def test_email_job_not_sent_without_smtp_and_retried_on_failure(self):
        env = Env()
        w = worker_for(env)
        with env.factory() as uow:
            from app.services.auth_service import UserRecord

            uow.users.add(UserRecord("cit-1", "a@example.com", "h", "Asha"))
            uow.notifications.save_preferences(__import__("app.services.ports", fromlist=["x"]).NotificationPreference("cit-1", True, True))
            uow.commit()
        env.create()
        res = {r.kind: r for r in env.jobs.drain("w1")}
        self.assertEqual(res["notification.email"].status, "succeeded")
        emails = [n for n in env.stores.notifications.values() if n.channel == "email"]
        self.assertTrue(emails and all(n.status == "not_configured" and n.delivered_at is None for n in emails))

        class Failing:
            def send(self, *a):
                raise OSError("smtp down")

        w2 = GrievanceWorker(env.factory, env.complaints, None, None, env.storage, env.fx, NotificationService(env.clock, Failing()))
        pending = emails[0]
        pending.status, pending.error = "queued", None  # simulate an unsent e-mail
        with self.assertRaises(RuntimeError):
            w2.send_email({"notification_id": pending.id, "user_id": "cit-1"}, None)  # raising makes the queue retry it
        self.assertEqual(env.stores.notifications[pending.id].status, "failed")
        _ = w


class VoiceTests(unittest.TestCase):
    def test_without_provider_there_is_no_transcript(self):
        env = Env()
        r = VoiceService(env.factory, None, env.clock).transcribe(CIT, WAV, "audio/wav", "hi")
        self.assertEqual((r.status, r.transcript, r.provider), ("NOT_CONFIGURED", None, None))
        self.assertIn("no transcript", r.error)
        self.assertEqual(len(env.stores.voice), 1)

    def test_validation(self):
        svc = VoiceService(Env().factory, None)
        for audio in (b"", b"not audio at all, just text!!", b"x" * (11 * 1024 * 1024)):
            with self.assertRaises(ValidationFailed):
                svc.transcribe(CIT, audio, None, "hi")
        with self.assertRaises(ValidationFailed):
            svc.transcribe(CIT, WAV, None, "xx")
        self.assertEqual(sniff_audio(WAV), "audio/wav")
        self.assertEqual(sniff_audio(b"OggS" + b"\x00" * 20), "audio/ogg")

    def test_provider_success_failure_and_language_detection(self):
        class P:
            name = "stub"
            def __init__(self, mode): self.mode = mode
            def capabilities(self): return SttCapabilities(frozenset({"hi", "en"}), False)
            def transcribe(self, audio, mime, language):
                if self.mode == "fail":
                    raise DependencyUnavailable("Bhashini is unreachable (x).")
                return Transcript("सड़क पर गड्ढा है", language, "stub")
        env = Env()
        ok = VoiceService(env.factory, P("ok"), env.clock).transcribe(CIT, WAV, None, "hi")
        self.assertEqual((ok.status, ok.transcript, ok.language_detected, ok.provider, ok.script_ok), ("OK", "सड़क पर गड्ढा है", "hi", "stub", True))
        bad = VoiceService(env.factory, P("fail"), env.clock).transcribe(CIT, WAV, None, "hi")
        self.assertEqual((bad.status, bad.transcript), ("FAILED", None))

    def test_script_detection(self):
        for text, lang in [("hello road", "en"), ("रस्ता खराब", "hi"), ("சாலை மோசம்", "ta"), ("రోడ్డు", "te"), ("ರಸ್ತೆ", "kn"), ("রাস্তা", "bn"), ("റോഡ്", "ml"), ("રસ્તો", "gu"), ("ਸੜਕ", "pa")]:
            self.assertEqual(detect_language(text)[0], lang)
        self.assertTrue(detect_language("रस्ता")[1])  # Hindi/Marathi ambiguity is flagged


class BhashiniTests(unittest.TestCase):
    CFG = BhashiniConfig("uid", "key-SECRET", "pipe-1", allow_private_hosts=True)  # skips DNS/SSRF resolution (no network in tests)

    class T:
        def __init__(self, replies): self.replies, self.calls = replies, []
        def request(self, method, url, headers, body, timeout):
            self.calls.append((method, url, headers, body))
            code, data = self.replies.pop(0)
            return TransportResponse(code, data, 1.0)

    PIPE = {"pipelineInferenceAPIEndPoint": {"callbackUrl": "https://infer.example/x", "inferenceApiKey": {"name": "Authorization", "value": "tok"}},
            "pipelineResponseConfig": [{"config": [{"serviceId": "svc-9"}]}]}  # fmt: skip

    def test_not_configured_without_credentials(self):
        for cfg in (BhashiniConfig(), BhashiniConfig("u", "k", "")):
            with self.assertRaises(NotConfigured):
                BhashiniProvider(cfg)

    def test_two_step_transcription_and_translation(self):
        t = self.T([(200, self.PIPE), (200, {"pipelineResponse": [{"output": [{"source": "  सड़क खराब  "}]}]}), (200, self.PIPE), (200, {"pipelineResponse": [{"output": [{"target": "road is bad"}]}]})])
        p = BhashiniProvider(self.CFG, t)
        tr = p.transcribe(WAV, "audio/wav", "hi")
        self.assertEqual((tr.text, tr.provider), ("सड़क खराब", "bhashini"))
        self.assertEqual(t.calls[0][2], {"userID": "uid", "ulcaApiKey": "key-SECRET"})
        self.assertEqual(t.calls[1][2], {"Authorization": "tok"})
        self.assertEqual(t.calls[1][3]["pipelineTasks"][0]["config"]["serviceId"], "svc-9")
        self.assertEqual(p.translate("सड़क खराब", "hi", "en"), "road is bad")

    def test_failures_are_errors_not_fake_output(self):
        for replies in ([(503, {})], [(200, {"unexpected": 1})], [(200, self.PIPE), (200, {"nope": 1})], [(200, self.PIPE), (200, {"pipelineResponse": [{"output": [{"source": ""}]}]})]):
            with self.assertRaises((DependencyUnavailable, ValidationFailed)):
                BhashiniProvider(self.CFG, self.T(list(replies))).transcribe(WAV, "audio/wav", "hi")
        with self.assertRaises(ValidationFailed):
            BhashiniProvider(self.CFG, self.T([])).transcribe(WAV, "audio/wav", "xx")
        self.assertNotIn("key-SECRET", repr(self.CFG))

    def test_translation_service(self):
        svc = TranslationService(None)
        self.assertEqual(svc.translate("hi", "en", "en"), "hi")
        with self.assertRaises(NotConfigured):
            svc.translate("hello", "en", "hi")
        with self.assertRaises(ValidationFailed):
            svc.translate(" ", "en", "hi")


class DriveTests(unittest.TestCase):
    class Svc:
        def __init__(self):
            self.files, self.n = {}, 0

        def files_(self): return self
        def files(self): return _Files(self)

    def test_not_configured(self):
        with self.assertRaises(NotConfigured):
            GoogleDriveStorageProvider("", "")

    def test_save_read_delete_and_name_validation(self):
        svc = _FakeDrive()
        d = GoogleDriveStorageProvider("creds.json", "folder1", service=svc, media_factory=lambda data: data)
        name = "a" * 32 + ".png"
        d.save(name, b"bytes")
        self.assertEqual(d.read(name), b"bytes")
        with self.assertRaises(ValidationFailed):
            d.save(name, b"again")
        d.delete(name)
        with self.assertRaises(NotFound):
            d.read(name)
        for bad in ("../x.png", "abc.png", "a" * 32 + ".png'; drop"):
            with self.assertRaises(ValidationFailed):
                d.read(bad)

    def test_api_errors_become_dependency_unavailable(self):
        svc = _FakeDrive(fail=True)
        d = GoogleDriveStorageProvider("c", "f", service=svc, media_factory=lambda x: x)
        with self.assertRaises(DependencyUnavailable):
            d.save("a" * 32 + ".png", b"x")


class _Files:
    def __init__(self, svc): self.s = svc
    def list(self, q, fields, pageSize):
        if self.s.fail:
            raise RuntimeError("boom")
        name = q.split("'")[1]
        return _Exec({"files": [{"id": name}] if name in self.s.store else []})
    def create(self, body, media_body, fields):
        self.s.store[body["name"]] = media_body
        return _Exec({})
    def get_media(self, fileId): return _Exec(self.s.store[fileId])
    def delete(self, fileId):
        self.s.store.pop(fileId, None)
        return _Exec({})


class _Exec:
    def __init__(self, v): self.v = v
    def execute(self): return self.v


class _FakeDrive:
    def __init__(self, fail=False): self.store, self.fail = {}, fail
    def files(self): return _Files(self)


class FakeRedis:
    """Minimal in-memory stand-in for redis-py used to test the wrapper logic (NOT Redis itself)."""

    def __init__(self):
        self.z, self.kv, self.h, self.published = {}, {}, {}, []

    def register_script(self, src):
        def run(keys, args):
            due = sorted((s, m) for m, s in self.z.items() if s <= float(args[0]))
            if not due:
                return None
            self.z.pop(due[0][1])
            return due[0][1].encode()
        return run

    def zadd(self, k, m): self.z.update(m)
    def zcard(self, k): return len(self.z)
    def setex(self, k, ttl, v): self.kv[k] = v
    def get(self, k): return self.kv.get(k)
    def scan_iter(self, match, count): return [k for k in list(self.kv) if k.startswith(match.rstrip("*"))]
    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.kv:
            return None
        self.kv[k] = v
        return True
    def delete(self, k): self.kv.pop(k, None)
    def hset(self, k, f, v): self.h.setdefault(k, {})[f] = v
    def hget(self, k, f): return self.h.get(k, {}).get(f)
    def publish(self, ch, msg): self.published.append((ch, msg))
    def ping(self): return True


class RedisWrapperTests(unittest.TestCase):
    def test_queue_ordering_delay_and_workers(self):
        r = FakeRedis()
        q = RedisQueueBackend(r)
        t = datetime(2026, 1, 1, tzinfo=UTC)
        q.push("later", datetime(2026, 1, 1, 1, tzinfo=UTC))
        q.push("now", t)
        self.assertEqual(q.depth(), 2)
        self.assertEqual(q.pop_due(t), "now")
        self.assertIsNone(q.pop_due(t))
        q.heartbeat("w1", t, {"handlers": ["a"]})
        self.assertEqual(q.workers(t)["w1"]["handlers"], ["a"])
        self.assertEqual(q.workers(datetime(2026, 1, 1, 0, 5, tzinfo=UTC)), {})  # stale heartbeat
        self.assertTrue(q.ping())

    def test_lock_and_state(self):
        r = FakeRedis()
        a, b = RedisLock(r), RedisLock(r)
        self.assertTrue(a.acquire("x", 10))
        self.assertFalse(b.acquire("x", 10))
        b.release("x")  # not the owner: must not free it
        self.assertFalse(b.acquire("x", 10))
        a.release("x")
        self.assertTrue(b.acquire("x", 10))
        st = RedisSchedulerState(r)
        self.assertIsNone(st.last_run("t"))
        now = datetime(2026, 1, 1, tzinfo=UTC)
        st.set_last_run("t", now)
        self.assertEqual(st.last_run("t"), now)

    def test_event_bus_serialisation_round_trip(self):
        e = DomainEvent("complaint.escalated", {"level": 2}, {"reason": "x"}, "c1", "roads", "cid")
        back = event_from_json(event_to_json(e))
        self.assertEqual((back.type, back.payload, back.internal, back.owner_id, back.department_code, back.at), (e.type, e.payload, e.internal, e.owner_id, e.department_code, e.at))
        r = FakeRedis()
        RedisEventBus(r).publish(e)
        self.assertEqual(json.loads(r.published[0][1])["type"], "complaint.escalated")
        with self.assertRaises(ValueError):
            event_from_json(json.dumps({"type": "bogus", "at": e.at.isoformat()}))

    def test_backend_protocol_parity_with_memory_double(self):
        for backend in (RedisQueueBackend(FakeRedis()), MemQueueBackend()):
            for m in ("push", "pop_due", "depth", "heartbeat", "workers", "ping"):
                self.assertTrue(callable(getattr(backend, m)))


if __name__ == "__main__":
    unittest.main()
