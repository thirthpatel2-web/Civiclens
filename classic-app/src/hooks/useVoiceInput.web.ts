// Web build of voice input. expo-audio's recorder + server-side transcription round-trip is
// unreliable in the browser (MediaRecorder's actual output format doesn't match what we tell the
// server it is), so this uses the browser's own SpeechRecognition engine instead - it transcribes
// live, in-browser, no upload needed. Same public interface as the native hook (state/start/stop/
// cancel/retry/edit/selectLanguage), so VoiceField and VoiceInput need no changes: Metro/Expo Router
// picks this file automatically for web builds via the .web.ts extension.
//
// Real constraint, not worked around: the Web Speech API needs a language told to it up front - it
// cannot auto-detect which language is being spoken. When the citizen picks "auto", this recognizes
// using the current UI language and says so in a warning, rather than pretending to auto-detect.
import { useCallback, useEffect, useRef, useReducer } from 'react';
import { initialVoice, voiceReducer } from '../voice/voiceMachine.ts';
import type { VoiceState } from '../voice/voiceMachine.ts';
import type { VoiceResult } from '../api/types.ts';
import type { LanguageCode } from '../i18n/languages.ts';
import { LANGUAGES } from '../i18n/languages.ts';

const BCP47: Record<LanguageCode, string> = {
  en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN', bn: 'bn-IN', gu: 'gu-IN', pa: 'pa-IN', ta: 'ta-IN', te: 'te-IN', kn: 'kn-IN', ml: 'ml-IN',
};

function getSpeechRecognition(): any {
  if (typeof window === 'undefined') return null;
  return (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition ?? null;
}

export function useVoiceInput(initialLanguage: LanguageCode | 'auto', _isOnline: () => Promise<boolean>) {
  const [state, dispatch] = useReducer(voiceReducer, initialVoice(initialLanguage));
  const stateRef = useRef<VoiceState>(state);
  stateRef.current = state;
  const recognitionRef = useRef<any>(null);
  const transcriptRef = useRef('');
  const confidenceRef = useRef<{ sum: number; n: number }>({ sum: 0, n: 0 });
  const safetyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const finish = useCallback((failMessage?: string) => {
    const s = stateRef.current;
    if (s.kind !== 'recording') return;
    const transcript = transcriptRef.current.trim();
    if (failMessage || !transcript) {
      dispatch({ type: 'FAILED', message: failMessage ?? 'No speech was detected. Try again closer to the microphone.' });
      return;
    }
    const requested = s.language;
    const usedLanguage: LanguageCode = requested === 'auto' ? 'en' : requested;
    const warnings = requested === 'auto' ? [`This browser cannot auto-detect the spoken language - recognized using ${LANGUAGES[usedLanguage].native}. Pick a specific language above for better accuracy.`] : [];
    const result: VoiceResult = {
      id: '', status: 'OK', language_requested: requested, language_detected: usedLanguage, detected_by: 'provider',
      transcript, provider: 'web_speech_api', error: null, script_ok: true, warnings,
      confidence: confidenceRef.current.n ? confidenceRef.current.sum / confidenceRef.current.n : null,
    };
    dispatch({ type: 'STOP', audioUri: `web-speech-${Date.now()}`, online: true });
    dispatch({ type: 'TRANSCRIBED', result });
  }, []);

  const start = useCallback(async () => {
    dispatch({ type: 'PRESS_MIC' });
    const Recognition = getSpeechRecognition();
    if (!Recognition) {
      dispatch({ type: 'FAILED', message: 'Voice input needs a browser with speech recognition support (Chrome or Edge). You can still type.', notConfigured: true });
      return;
    }
    const recognition = new Recognition();
    recognition.lang = BCP47[stateRef.current.language === 'auto' ? 'en' : stateRef.current.language];
    recognition.continuous = true;
    recognition.interimResults = false;
    transcriptRef.current = '';
    confidenceRef.current = { sum: 0, n: 0 };
    recognition.onresult = (event: any) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i];
        if (res.isFinal) {
          transcriptRef.current += (transcriptRef.current ? ' ' : '') + res[0].transcript;
          if (typeof res[0].confidence === 'number') { confidenceRef.current.sum += res[0].confidence; confidenceRef.current.n += 1; }
        }
      }
    };
    recognition.onstart = () => dispatch({ type: 'PERMISSION_GRANTED', now: Date.now() });
    recognition.onerror = (event: any) => {
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') dispatch({ type: 'PERMISSION_DENIED' });
      else if (event.error === 'no-speech' || event.error === 'aborted') { /* onend handles this */ }
      else if (event.error === 'network') dispatch({ type: 'FAILED', message: 'Could not reach the browser speech service (network error). Check your connection, or type instead.' });
      else dispatch({ type: 'FAILED', message: `Voice recognition error: ${event.error}` });
    };
    recognition.onend = () => { if (safetyTimer.current) clearTimeout(safetyTimer.current); finish(); };
    recognitionRef.current = recognition;
    // continuous mode (needed so a multi-sentence complaint isn't cut off after the first pause)
    // has no built-in max duration - without this, a session that never gets an explicit Stop
    // (a missed click, a stalled tab) would listen forever instead of failing visibly.
    if (safetyTimer.current) clearTimeout(safetyTimer.current);
    safetyTimer.current = setTimeout(() => recognitionRef.current?.stop(), 60_000);
    try { recognition.start(); } catch (e: any) { dispatch({ type: 'FAILED', message: e?.message ?? 'Could not start voice recognition.' }); }
  }, [finish]);

  const stop = useCallback(async () => { recognitionRef.current?.stop(); }, []);
  const cancel = useCallback(async () => {
    if (safetyTimer.current) clearTimeout(safetyTimer.current);
    if (recognitionRef.current) { recognitionRef.current.onend = null; recognitionRef.current.stop(); }
    dispatch({ type: 'CANCEL' });
  }, []);
  const retry = useCallback(async () => { dispatch({ type: 'RETRY' }); await start(); }, [start]);

  useEffect(() => () => { if (recognitionRef.current) { recognitionRef.current.onend = null; recognitionRef.current.stop(); } }, []);
  return { state, start, stop, cancel, retry, edit: (text: string) => dispatch({ type: 'EDIT', text }), selectLanguage: (language: LanguageCode | 'auto') => dispatch({ type: 'SELECT_LANGUAGE', language }) };
}
