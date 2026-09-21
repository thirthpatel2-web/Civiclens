// Microphone -> server transcription in the SPOKEN language (never translated). The reducer (voiceMachine.ts) is the single source of truth.
import { useCallback, useEffect, useReducer, useRef } from 'react';
import { Audio } from 'expo-av';
import { initialVoice, voiceReducer } from '../voice/voiceMachine.ts';
import type { VoiceState } from '../voice/voiceMachine.ts';
import { endpoints } from '../api/instance.ts';
import { ApiError, NetworkError } from '../api/errors.ts';
import type { LanguageCode } from '../i18n/languages.ts';

export function useVoiceInput(initialLanguage: LanguageCode | 'auto', isOnline: () => Promise<boolean>) {
  const [state, dispatch] = useReducer(voiceReducer, initialVoice(initialLanguage));
  const recording = useRef<Audio.Recording | null>(null);
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
    const perm = await Audio.requestPermissionsAsync(); // the OS prompt shows the purpose text from app.json
    if (!perm.granted) { dispatch({ type: 'PERMISSION_DENIED' }); return; }
    try {
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording: rec } = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      recording.current = rec;
      dispatch({ type: 'PERMISSION_GRANTED', now: Date.now() });
    } catch (e: any) { dispatch({ type: 'FAILED', message: e?.message ?? 'Could not start recording.' }); }
  }, []);

  const stop = useCallback(async () => {
    const rec = recording.current;
    if (!rec) return;
    recording.current = null;
    try {
      await rec.stopAndUnloadAsync();
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false });
      const uri = rec.getURI();
      if (!uri) { dispatch({ type: 'FAILED', message: 'The recording is empty.' }); return; }
      const online = await isOnline();
      dispatch({ type: 'STOP', audioUri: uri, online });
      if (online) await transcribe(uri, stateRef.current.language);
    } catch (e: any) { dispatch({ type: 'FAILED', message: e?.message ?? 'Could not finish recording.' }); }
  }, [isOnline, transcribe]);

  const cancel = useCallback(async () => {
    const rec = recording.current; recording.current = null;
    if (rec) await rec.stopAndUnloadAsync().catch(() => undefined);
    dispatch({ type: 'CANCEL' });
  }, []);

  const retry = useCallback(async () => {
    const s = stateRef.current;
    dispatch({ type: 'RETRY' });
    if (s.kind === 'error' && s.audioUri) await transcribe(s.audioUri, s.language);
  }, [transcribe]);

  useEffect(() => () => { recording.current?.stopAndUnloadAsync().catch(() => undefined); }, []);
  return { state, start, stop, cancel, retry, edit: (text: string) => dispatch({ type: 'EDIT', text }), selectLanguage: (language: LanguageCode | 'auto') => dispatch({ type: 'SELECT_LANGUAGE', language }) };
}
