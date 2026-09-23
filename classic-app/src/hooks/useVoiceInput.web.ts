// Web build of voice input. The browser's own SpeechRecognition API was tried first, but it turned
// out unreliable in real use - it consistently returned generic hallucinated text ("Thank you.")
// regardless of what was actually said, a well-known failure mode of that API on quiet/ambiguous
// audio. This version instead records real audio with MediaRecorder and uploads it through the
// SAME /voice/transcribe endpoint the native app uses (now backed by Groq's hosted Whisper, verified
// to produce exact transcripts) - one accurate transcription path for every platform, not two.
// Same public interface as the native hook, so VoiceField/VoiceInput need no changes: Metro/Expo
// Router picks this file automatically for web builds via the useVoiceInput extensionless import.
//
// interimText: SpeechRecognition also runs in parallel, purely to paint live captions while
// recording - display only, never used as the submitted answer. Groq Whisper (via MediaRecorder's
// real audio, above) stays the one authoritative transcript; if the live captions engine fails or
// isn't supported, recording and the final transcript are completely unaffected.
import { useCallback, useEffect, useRef, useReducer, useState } from 'react';
import { initialVoice, voiceReducer } from '../voice/voiceMachine.ts';
import type { VoiceState } from '../voice/voiceMachine.ts';
import { endpoints } from '../api/instance.ts';
import { ApiError, NetworkError } from '../api/errors.ts';
import type { LanguageCode } from '../i18n/languages.ts';

const BCP47: Record<LanguageCode, string> = {
  en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN', bn: 'bn-IN', gu: 'gu-IN', pa: 'pa-IN', ta: 'ta-IN', te: 'te-IN', kn: 'kn-IN', ml: 'ml-IN',
};

function pickMimeType(): string {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
  const MR: any = typeof window !== 'undefined' ? (window as any).MediaRecorder : null;
  return candidates.find((t) => MR?.isTypeSupported?.(t)) ?? '';
}
function getSpeechRecognition(): any {
  if (typeof window === 'undefined') return null;
  return (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition ?? null;
}

export function useVoiceInput(initialLanguage: LanguageCode | 'auto', isOnline: () => Promise<boolean>) {
  const [state, dispatch] = useReducer(voiceReducer, initialVoice(initialLanguage));
  const stateRef = useRef<VoiceState>(state);
  stateRef.current = state;
  const recorderRef = useRef<any>(null);
  const streamRef = useRef<any>(null);
  const chunksRef = useRef<Blob[]>([]);
  const liveRecognitionRef = useRef<any>(null);
  const [interimText, setInterimText] = useState('');

  const transcribe = useCallback(async (uri: string, mime: string, language: LanguageCode | 'auto') => {
    try {
      const result = await endpoints.transcribe({ uri, name: `voice.${mime.includes('ogg') ? 'ogg' : mime.includes('mp4') ? 'm4a' : 'webm'}`, type: mime }, language);
      dispatch({ type: 'TRANSCRIBED', result });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof NetworkError ? 'No connection. Try again when you are online.' : 'Transcription failed.';
      dispatch({ type: 'FAILED', message: msg, notConfigured: e instanceof ApiError && e.isNotConfigured });
    }
  }, []);

  const stopLiveCaptions = () => {
    const r = liveRecognitionRef.current;
    if (r) { r.onresult = null; r.onerror = null; r.onend = null; try { r.stop(); } catch { /* already stopped */ } }
    liveRecognitionRef.current = null;
  };

  const startLiveCaptions = (language: LanguageCode | 'auto') => {
    const Recognition = getSpeechRecognition();
    if (!Recognition) return; // no live captions in this browser - real recording/transcription is unaffected
    setInterimText('');
    const recognition = new Recognition();
    recognition.lang = BCP47[language === 'auto' ? 'en' : language];
    recognition.continuous = true;
    recognition.interimResults = true;
    let finalSoFar = '';
    recognition.onresult = (event: any) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i];
        if (res.isFinal) finalSoFar += (finalSoFar ? ' ' : '') + res[0].transcript;
        else interim += res[0].transcript;
      }
      setInterimText((finalSoFar + ' ' + interim).trim());
    };
    recognition.onerror = () => { /* captions are best-effort; the real recording keeps going regardless */ };
    recognition.onend = () => { if (liveRecognitionRef.current === recognition) { try { recognition.start(); } catch { /* recording likely stopped */ } } }; // browsers auto-end continuous sessions periodically; restart while we're still recording
    liveRecognitionRef.current = recognition;
    try { recognition.start(); } catch { liveRecognitionRef.current = null; }
  };

  const start = useCallback(async () => {
    dispatch({ type: 'PRESS_MIC' });
    const md: any = typeof navigator !== 'undefined' ? (navigator as any).mediaDevices : null;
    if (!md?.getUserMedia) { dispatch({ type: 'FAILED', message: 'This browser cannot access the microphone. You can still type.', notConfigured: true }); return; }
    let stream: any;
    try {
      stream = await md.getUserMedia({ audio: true });
    } catch (e: any) {
      if (e?.name === 'NotAllowedError' || e?.name === 'PermissionDeniedError') dispatch({ type: 'PERMISSION_DENIED' });
      else dispatch({ type: 'FAILED', message: e?.message ?? 'Could not access the microphone.' });
      return;
    }
    streamRef.current = stream;
    const mime = pickMimeType();
    const MR: any = (window as any).MediaRecorder;
    const recorder = new MR(stream, mime ? { mimeType: mime } : undefined);
    chunksRef.current = [];
    recorder.ondataavailable = (e: any) => { if (e.data && e.data.size > 0) chunksRef.current.push(e.data); };
    recorder.onerror = () => dispatch({ type: 'FAILED', message: 'Recording failed.' });
    recorderRef.current = recorder;
    recorder.start();
    startLiveCaptions(stateRef.current.language);
    dispatch({ type: 'PERMISSION_GRANTED', now: Date.now() });
  }, []);

  const teardownStream = () => { streamRef.current?.getTracks?.().forEach((t: any) => t.stop()); streamRef.current = null; };

  const stop = useCallback(async () => {
    stopLiveCaptions();
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === 'inactive') return;
    const mime = recorder.mimeType || 'audio/webm';
    const blob: Blob = await new Promise((resolve) => {
      recorder.onstop = () => resolve(new Blob(chunksRef.current, { type: mime }));
      recorder.stop();
    });
    teardownStream();
    if (!blob.size) { dispatch({ type: 'FAILED', message: 'The recording is empty. Try again closer to the microphone.' }); return; }
    const uri = URL.createObjectURL(blob);
    const online = await isOnline();
    dispatch({ type: 'STOP', audioUri: uri, online });
    if (online) await transcribe(uri, mime, stateRef.current.language);
  }, [isOnline, transcribe]);

  const cancel = useCallback(async () => {
    stopLiveCaptions();
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') { recorder.onstop = null; recorder.stop(); }
    teardownStream();
    dispatch({ type: 'CANCEL' });
  }, []);

  const retry = useCallback(async () => {
    const s = stateRef.current;
    dispatch({ type: 'RETRY' });
    if (s.kind === 'error' && s.audioUri) {
      const blob = await (await fetch(s.audioUri)).blob();
      await transcribe(s.audioUri, blob.type || 'audio/webm', s.language);
    } else await start();
  }, [transcribe, start]);

  useEffect(() => () => {
    stopLiveCaptions();
    const r = recorderRef.current; if (r && r.state !== 'inactive') { r.onstop = null; r.stop(); } teardownStream();
  }, []);
  return {
    state, start, stop, cancel, retry, interimText,
    edit: (text: string) => dispatch({ type: 'EDIT', text }),
    selectLanguage: (language: LanguageCode | 'auto') => dispatch({ type: 'SELECT_LANGUAGE', language }),
  };
}
