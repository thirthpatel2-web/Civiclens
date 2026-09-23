// Microphone -> server transcription in the SPOKEN language (never translated). The reducer (voiceMachine.ts) is the single source of truth.
import { useCallback, useEffect, useReducer, useRef } from 'react';
import { requestRecordingPermissionsAsync, setAudioModeAsync, useAudioRecorder, RecordingPresets } from 'expo-audio';
import { initialVoice, voiceReducer } from '../voice/voiceMachine.ts';
import type { VoiceState } from '../voice/voiceMachine.ts';
import { endpoints } from '../api/instance.ts';
import { ApiError, NetworkError } from '../api/errors.ts';
import type { LanguageCode } from '../i18n/languages.ts';

export function useVoiceInput(initialLanguage: LanguageCode | 'auto', isOnline: () => Promise<boolean>) {
  const [state, dispatch] = useReducer(voiceReducer, initialVoice(initialLanguage));
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const stateRef = useRef<VoiceState>(state);
  stateRef.current = state;

  const transcribe = useCallback(async (uri: string, language: LanguageCode | 'auto') => {
    try {
      const result = await endpoints.transcribe({ uri, name: 'voice.m4a', type: 'audio/mp4' }, language);
      dispatch({ type: 'TRANSCRIBED', result });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof NetworkError ? 'No connection. The recording was kept; retry when you are online.' : 'Transcription failed.';
      dispatch({ type: 'FAILED', message: msg, notConfigured: e instanceof ApiError && e.isNotConfigured });
    }
  }, []);

  const start = useCallback(async () => {
    dispatch({ type: 'PRESS_MIC' });
    const perm = await requestRecordingPermissionsAsync(); // the OS prompt shows the purpose text from app.json
    if (!perm.granted) { dispatch({ type: 'PERMISSION_DENIED' }); return; }
    try {
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      dispatch({ type: 'PERMISSION_GRANTED', now: Date.now() });
    } catch (e: any) { dispatch({ type: 'FAILED', message: e?.message ?? 'Could not start recording.' }); }
  }, [recorder]);

  const stop = useCallback(async () => {
    if (!recorder.isRecording) return;
    try {
      await recorder.stop();
      await setAudioModeAsync({ allowsRecording: false });
      const uri = recorder.uri;
      if (!uri) { dispatch({ type: 'FAILED', message: 'The recording is empty.' }); return; }
      const online = await isOnline();
      dispatch({ type: 'STOP', audioUri: uri, online });
      if (online) await transcribe(uri, stateRef.current.language);
    } catch (e: any) { dispatch({ type: 'FAILED', message: e?.message ?? 'Could not finish recording.' }); }
  }, [recorder, isOnline, transcribe]);

  const cancel = useCallback(async () => {
    if (recorder.isRecording) await recorder.stop().catch(() => undefined);
    dispatch({ type: 'CANCEL' });
  }, [recorder]);

  const retry = useCallback(async () => {
    const s = stateRef.current;
    dispatch({ type: 'RETRY' });
    if (s.kind === 'error' && s.audioUri) await transcribe(s.audioUri, s.language);
  }, [transcribe]);

  useEffect(() => () => { if (recorder.isRecording) recorder.stop().catch(() => undefined); }, [recorder]);
  // interimText: web shows live captions while recording (see useVoiceInput.web.ts); native has no
  // equivalent live-partial API from expo-audio, so this always stays empty - same return shape either way.
  return { state, start, stop, cancel, retry, interimText: '', edit: (text: string) => dispatch({ type: 'EDIT', text }), selectLanguage: (language: LanguageCode | 'auto') => dispatch({ type: 'SELECT_LANGUAGE', language }) };
}
