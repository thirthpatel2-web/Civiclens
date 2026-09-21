"""CRITICAL requirement: speech in language X is transcribed as language X, in X's own script, never translated.

These tests use a *scripted engine* (a test double that returns what a correct engine returns) so they verify the
service's guarantees, not any real model's accuracy. Real-provider accuracy is environment-dependent (see docs).
"""

import unittest

from app.core.exceptions import ValidationFailed
from app.i18n.languages import LANGUAGES, detect_language, dominant_script, script_histogram, script_matches
from app.providers.stt import SttCapabilities, Transcript, WhisperProvider
from tests.support_env import CIT, Env
from tests.support_mem import MemDict  # noqa: F401  (voice repo lives in the memory UoW)

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32

# The exact examples from the product brief.
SAMPLES = {
    "kn": "ನನ್ನ ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಇದೆ",
    "hi": "मेरे इलाके में सड़क खराब है",
    "ta": "எங்கள் பகுதியில் சாலை மிகவும் மோசமாக உள்ளது",
    "te": "మా ప్రాంతంలో రోడ్డు చాలా దారుణంగా ఉంది",
    "en": "My road has a large pothole",
}
ENGLISH_TRANSLATION = "There is a big pothole on my road."


class ScriptedEngine:
    """Returns the sample for whichever language it is asked for (or told to detect). Records every call."""

    name = "scripted"

    def __init__(self, auto=True, langs=None, translates=False, romanises=False):
        self.auto, self.langs, self.translates, self.romanises = auto, frozenset(langs or SAMPLES), translates, romanises
        self.calls, self.translate_calls = [], 0

    def capabilities(self):
        return SttCapabilities(self.langs, self.auto)

    def transcribe(self, audio, mime, language):
        self.calls.append(language)
        spoken = language or self.spoken_when_auto
        if self.translates:
            return Transcript(ENGLISH_TRANSLATION, spoken, self.name, spoken, translated=True)
        if self.romanises:
            return Transcript("nanna rasteyalli dodda gundi ide", spoken, self.name, spoken)
        return Transcript(SAMPLES[spoken], spoken, self.name, spoken if language is None else None, 0.9)

    spoken_when_auto = "kn"

    def translate(self, *a):  # a real transcription path must never reach this
        self.translate_calls += 1
        raise AssertionError("translation must never be part of voice input")


class NativeScriptTests(unittest.TestCase):
    def service(self, engine):
        from app.services.voice_service import VoiceService

        self.env = Env()
        return VoiceService(self.env.factory, engine, self.env.clock)

    def test_each_language_stays_in_its_own_language_and_script_when_selected(self):
        for code, text in SAMPLES.items():
            eng = ScriptedEngine()
            rec = self.service(eng).transcribe(CIT, WAV, "audio/wav", code)
            self.assertEqual((rec.status, rec.transcript), ("OK", text), code)
            self.assertNotEqual(rec.transcript, ENGLISH_TRANSLATION)
            self.assertTrue(rec.script_ok, code)
            self.assertEqual(eng.calls, [code])  # the engine was asked for that language, not for English
            self.assertEqual(eng.translate_calls, 0)
            if code != "en":
                self.assertNotEqual(dominant_script(rec.transcript), "Latn", f"{code} transcript fell back to Latin script")

    def test_auto_detect_transcribes_in_the_detected_language(self):
        for spoken in ("kn", "hi", "ta", "te", "en"):
            eng = ScriptedEngine()
            eng.spoken_when_auto = spoken
            rec = self.service(eng).transcribe(CIT, WAV, "audio/wav", "auto")
            self.assertEqual((rec.transcript, rec.language_requested, rec.language_detected, rec.detected_by), (SAMPLES[spoken], "auto", spoken, "provider"))
            self.assertEqual(eng.calls, [None])

    def test_script_based_detection_used_when_the_engine_does_not_report_a_language(self):
        eng = ScriptedEngine()
        rec = self.service(eng).transcribe(CIT, WAV, "audio/wav", "kn")
        self.assertEqual((rec.language_detected, rec.detected_by), ("kn", "script"))  # Kannada script implies Kannada

    def test_an_engine_that_translates_is_rejected_and_nothing_is_stored_as_a_transcript(self):
        rec = self.service(ScriptedEngine(translates=True)).transcribe(CIT, WAV, "audio/wav", "kn")
        self.assertEqual((rec.status, rec.transcript), ("FAILED", None))
        self.assertIn("translation", rec.error)

    def test_romanised_or_translated_looking_output_is_flagged_not_silently_accepted(self):
        rec = self.service(ScriptedEngine(romanises=True)).transcribe(CIT, WAV, "audio/wav", "kn")
        self.assertEqual(rec.status, "OK")
        self.assertFalse(rec.script_ok)
        self.assertIn("script", rec.warnings[0])
        self.assertEqual(rec.transcript, "nanna rasteyalli dodda gundi ide")  # returned as-is, never rewritten

    def test_auto_detect_and_languages_are_offered_only_if_the_engine_declares_them(self):
        no_auto = self.service(ScriptedEngine(auto=False, langs={"kn", "hi"}))
        with self.assertRaises(ValidationFailed) as cm:
            no_auto.transcribe(CIT, WAV, "audio/wav", "auto")
        self.assertIn("auto-detect", cm.exception.message)
        with self.assertRaises(ValidationFailed):
            no_auto.transcribe(CIT, WAV, "audio/wav", "ta")  # valid language, but this engine does not declare it
        caps = no_auto.capabilities()
        self.assertEqual((caps["auto_detect"], [x["code"] for x in caps["languages"]]), (False, ["hi", "kn"]))
        self.assertEqual({x["native"] for x in caps["languages"]}, {"हिन्दी", "ಕನ್ನಡ"})

    def test_no_engine_configured_means_no_transcript_for_any_language(self):
        svc = self.service(None)
        for code in ("kn", "hi", "auto"):
            rec = svc.transcribe(CIT, WAV, "audio/wav", code)
            self.assertEqual((rec.status, rec.transcript), ("NOT_CONFIGURED", None))
        self.assertEqual(svc.capabilities()["state"], "NOT_CONFIGURED")

    def test_record_is_persisted_with_metadata_and_owner_isolated(self):
        svc = self.service(ScriptedEngine())
        rec = svc.transcribe(CIT, WAV, "audio/wav", "hi")
        stored = svc.get_for_user(CIT, rec.id)
        self.assertEqual((stored.transcript, stored.language_requested, stored.provider, stored.script_ok), (SAMPLES["hi"], "hi", "scripted", True))
        from app.core.exceptions import NotFound
        from tests.support_env import CIT2

        with self.assertRaises(NotFound):
            svc.get_for_user(CIT2, rec.id)


class WhisperProviderTests(unittest.TestCase):
    """The self-hosted engine must request transcription (not translation) and honour the chosen language."""

    class Model:
        def __init__(self, text, lang="kn"):
            self.text, self.lang, self.kwargs = text, lang, None

        def transcribe(self, audio, **kw):
            self.kwargs = kw

            class Seg:
                def __init__(s, t): s.text = t

            class Info:
                language, language_probability = self.lang, 0.93

            return [Seg(self.text)], Info()

    def test_task_is_transcribe_never_translate_and_language_is_forwarded(self):
        m = self.Model(SAMPLES["kn"])
        t = WhisperProvider("small", model=m).transcribe(b"audio", "audio/wav", "kn")
        self.assertEqual((m.kwargs["task"], m.kwargs["language"]), ("transcribe", "kn"))
        self.assertEqual((t.text, t.language, t.detected_language, t.translated), (SAMPLES["kn"], "kn", "kn", False))

    def test_auto_detect_passes_no_language_and_reports_the_detected_one(self):
        m = self.Model(SAMPLES["ta"], lang="ta")
        t = WhisperProvider("small", model=m).transcribe(b"audio", "audio/wav", None)
        self.assertIsNone(m.kwargs["language"])
        self.assertEqual((t.language, t.detected_language, t.text), ("ta", "ta", SAMPLES["ta"]))

    def test_capabilities_and_unsupported_language_and_empty_result(self):
        w = WhisperProvider("small", model=self.Model(""))
        caps = w.capabilities()
        self.assertTrue(caps.auto_detect)
        self.assertTrue({"en", "hi", "kn", "ta", "te", "ml", "mr", "bn", "gu", "pa"} <= caps.languages)
        with self.assertRaises(ValidationFailed):
            w.transcribe(b"a", "audio/wav", "xx")
        with self.assertRaises(ValidationFailed):
            w.transcribe(b"a", "audio/wav", "kn")  # silence -> no text, not a made-up transcript

    def test_not_configured_without_model_name_or_package(self):
        from unittest.mock import patch

        from app.core.exceptions import NotConfigured

        with self.assertRaises(NotConfigured):
            WhisperProvider("")
        # Force the "package missing" branch deterministically, regardless of whether faster-whisper
        # actually happens to be installed in this environment (it may be, when real STT is configured).
        with patch.dict("sys.modules", {"faster_whisper": None}), self.assertRaises(NotConfigured):
            WhisperProvider("small")


class LanguageRegistryTests(unittest.TestCase):
    def test_registry_covers_the_target_languages_with_native_names_and_scripts(self):
        self.assertEqual({"en", "kn", "hi", "ta", "te", "ml", "mr", "bn", "gu", "pa"}, set(LANGUAGES))
        self.assertEqual((LANGUAGES["kn"].native, LANGUAGES["kn"].script), ("ಕನ್ನಡ", "Knda"))

    def test_script_detection_and_matching(self):
        for code, text in SAMPLES.items():
            self.assertTrue(script_matches(code, text), code)
            self.assertEqual(detect_language(text)[0], code)
        self.assertFalse(script_matches("kn", ENGLISH_TRANSLATION))
        self.assertFalse(script_matches("hi", SAMPLES["kn"]))
        self.assertTrue(script_matches("kn", "ನನ್ನ road ನಲ್ಲಿ ಗುಂಡಿ ಇದೆ 123"))  # code-mixed text is still mostly Kannada
        self.assertEqual(detect_language(""), (None, False))
        self.assertEqual(script_histogram("abc ಕ"), {"Latn": 3, "Knda": 1})


if __name__ == "__main__":
    unittest.main()
