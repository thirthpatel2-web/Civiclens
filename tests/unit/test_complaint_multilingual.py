"""Complaints keep the citizen's ORIGINAL text/language untouched; translation and detection are separate, derived fields."""

import unittest

from app.core.exceptions import ValidationFailed
from app.services.complaint_service import ComplaintInput
from app.services.voice_service import TranslationService, VoiceService
from app.workers.handlers import GrievanceWorker
from tests.rag.helpers import ScriptedChat
from tests.support_env import CIT, CIT2, Env
from tests.unit.test_voice_multilingual import ENGLISH_TRANSLATION, SAMPLES, WAV, ScriptedEngine

KN_TITLE = "ರಸ್ತೆಯಲ್ಲಿ ಗುಂಡಿ"
KN_TEXT = SAMPLES["kn"] + " ದಯವಿಟ್ಟು ಸರಿಪಡಿಸಿ"  # padded to satisfy the minimum length rule


class FakeTranslator:
    name = "fake-nmt"

    def __init__(self, fail=False): self.calls, self.fail = [], fail
    def translate(self, text, source, target):
        self.calls.append((text, source, target))
        if self.fail:
            from app.core.exceptions import DependencyUnavailable

            raise DependencyUnavailable("translator down")
        return ENGLISH_TRANSLATION


def worker(env, translator=None, llm=None):
    from app.services.classification_service import ClassificationService

    w = GrievanceWorker(env.factory, env.complaints, ClassificationService(llm) if llm else None, None, env.storage, env.fx, env.notifications,
                        consent_check=lambda u, p: True, translation=TranslationService(translator))  # fmt: skip
    env.jobs.handlers.update(w.handlers())
    return w


class OriginalTextTests(unittest.TestCase):
    def test_native_script_complaint_is_routed_from_the_original_text_without_translation(self):
        env = Env()
        for code, text in SAMPLES.items():
            c = env.complaints.create(CIT, ComplaintInput(f"Road issue {code}", text + " ದಯವಿಟ್ಟು" if code == "kn" else text + " please fix", code)).complaint
            self.assertEqual((c.category, c.department_code), ("roads", "roads"), code)
            self.assertIn(text, c.description)
            self.assertEqual((c.language, c.detected_language, c.translated_text), (code, code, None))

    def test_translation_is_a_separate_derived_field_and_never_overwrites_the_original(self):
        env = Env()
        tr = FakeTranslator()
        worker(env, tr)
        c = env.complaints.create(CIT, ComplaintInput(KN_TITLE, KN_TEXT, "kn")).complaint
        original = (c.title, c.description, c.language)
        env.jobs.drain("w")
        after = env.stores.complaints[c.id]
        self.assertEqual((after.title, after.description, after.language), original)
        self.assertEqual((after.translated_text, after.translated_language, after.translation_provider), (ENGLISH_TRANSLATION, "en", "fake-nmt"))
        self.assertEqual(tr.calls, [(KN_TEXT, "kn", "en")])

    def test_english_needs_no_translation_and_missing_or_failing_provider_leaves_it_empty(self):
        env = Env()
        tr = FakeTranslator()
        worker(env, tr)
        en = env.complaints.create(CIT, ComplaintInput("Pothole", "A large pothole on my road near the school", "en")).complaint
        env.jobs.drain("w")
        self.assertEqual((env.stores.complaints[en.id].translated_text, tr.calls), (None, []))
        env2 = Env()
        worker(env2, None)
        c = env2.complaints.create(CIT, ComplaintInput(KN_TITLE, KN_TEXT, "kn")).complaint
        env2.jobs.drain("w")
        self.assertEqual((env2.stores.complaints[c.id].translated_text, env2.stores.complaints[c.id].description), (None, KN_TEXT))
        env3 = Env()
        worker(env3, FakeTranslator(fail=True))
        c3 = env3.complaints.create(CIT, ComplaintInput(KN_TITLE, KN_TEXT, "kn")).complaint
        env3.jobs.drain("w")
        self.assertIsNone(env3.stores.complaints[c3.id].translated_text)
        self.assertEqual(env3.stores.complaints[c3.id].description, KN_TEXT)

    def test_language_mismatch_is_warned_about_but_text_is_kept_as_written(self):
        env = Env()
        r = env.complaints.create(CIT, ComplaintInput("Pothole", SAMPLES["kn"] + " ದಯವಿಟ್ಟು ಸರಿಪಡಿಸಿ", "en"))
        self.assertTrue(any("Kannada" in w for w in r.warnings))
        self.assertEqual((r.complaint.language, r.complaint.detected_language), ("en", "kn"))
        self.assertEqual(r.complaint.description, SAMPLES["kn"] + " ದಯವಿಟ್ಟು ಸರಿಪಡಿಸಿ")
        hi = env.complaints.create(CIT, ComplaintInput("Sadak", SAMPLES["hi"] + " कृपया ठीक करें", "mr"))
        self.assertEqual(hi.warnings, [])  # Devanagari could be Hindi or Marathi: no false alarm

    def test_all_registry_languages_are_accepted_and_unknown_ones_rejected(self):
        env = Env()
        for code in ("en", "hi", "mr", "bn", "ta", "te", "kn", "ml", "gu", "pa"):
            env.complaints.create(CIT2, ComplaintInput(f"Issue {code}", "A pothole on the road near my house needs repair", code, client_request_id=f"req-{code}-000001"))
        with self.assertRaises(ValidationFailed):
            env.complaints.create(CIT, ComplaintInput("Issue", "A pothole on the road near my house needs repair", "xx"))


class VoiceToComplaintTests(unittest.TestCase):
    def test_kannada_voice_to_complaint_keeps_the_kannada_text_and_the_unedited_transcript(self):
        env = Env()
        voice = VoiceService(env.factory, ScriptedEngine(), env.clock)
        rec = voice.transcribe(CIT, WAV, "audio/wav", "kn")
        edited = rec.transcript + " ದಯವಿಟ್ಟು ಬೇಗ"  # the citizen edits the transcription before submitting
        c = env.complaints.create(CIT, ComplaintInput("ರಸ್ತೆ ಗುಂಡಿ", edited, "kn", voice_id=rec.id)).complaint
        stored = env.stores.complaints[c.id]
        self.assertEqual((stored.description, stored.language, stored.input_method, stored.voice_id), (edited, "kn", "voice", rec.id))
        self.assertEqual(env.stores.voice[rec.id].transcript, SAMPLES["kn"])  # the engine output is preserved unedited
        self.assertNotIn(ENGLISH_TRANSLATION, stored.description)
        self.assertEqual(stored.department_code, "roads")

    def test_voice_id_must_be_owned_and_usable(self):
        env = Env()
        voice = VoiceService(env.factory, ScriptedEngine(), env.clock)
        rec = voice.transcribe(CIT, WAV, "audio/wav", "hi")
        for vid in ("nope", rec.id):
            with self.assertRaises(ValidationFailed):
                env.complaints.create(CIT2, ComplaintInput("Sadak", SAMPLES["hi"] + " कृपया ठीक करें", "hi", voice_id=vid))
        unconfigured = VoiceService(env.factory, None, env.clock).transcribe(CIT, WAV, "audio/wav", "hi")
        with self.assertRaises(ValidationFailed):
            env.complaints.create(CIT, ComplaintInput("Sadak", SAMPLES["hi"] + " कृपया ठीक करें", "hi", voice_id=unconfigured.id))  # no transcript => not usable
        self.assertEqual(len(env.stores.complaints), 0)

    def test_typed_complaints_are_marked_typed(self):
        env = Env()
        self.assertEqual(env.create().input_method, "typed")


if __name__ == "__main__":
    unittest.main()
