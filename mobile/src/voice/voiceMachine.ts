// Voice-input state machine (pure). The UI hook feeds it events; it decides what the screen shows.
// Guarantees: the transcript shown is the engine's output in the spoken language (never translated); the user can edit it;
// nothing is submitted from here; offline recordings are queued, not transcribed by guesswork.

import type { LanguageCode } from '../i18n/languages.ts';
import { scriptMatches } from '../i18n/languages.ts';
import type { VoiceResult } from '../api/types.ts';

export type VoiceState =
  | { kind: 'idle'; language: LanguageCode | 'auto' }
  | { kind: 'requesting_permission'; language: LanguageCode | 'auto' }
  | { kind: 'recording'; language: LanguageCode | 'auto'; startedAt: number }
  | { kind: 'transcribing'; language: LanguageCode | 'auto'; audioUri: string }
  | { kind: 'review'; language: LanguageCode | 'auto'; audioUri: string; voiceId: string; text: string; original: string; detected: string | null; detectedBy: string | null; warnings: string[]; edited: boolean }
  | { kind: 'queued_offline'; language: LanguageCode | 'auto'; audioUri: string }
  | { kind: 'error'; language: LanguageCode | 'auto'; message: string; audioUri: string | null; notConfigured: boolean; permissionDenied: boolean };

export type VoiceEvent =
  | { type: 'SELECT_LANGUAGE'; language: LanguageCode | 'auto' }
  | { type: 'PRESS_MIC' }
  | { type: 'PERMISSION_GRANTED'; now: number }
  | { type: 'PERMISSION_DENIED' }
  | { type: 'STOP'; audioUri: string; online: boolean }
  | { type: 'CANCEL' }
  | { type: 'TRANSCRIBED'; result: VoiceResult }
  | { type: 'FAILED'; message: string; notConfigured?: boolean }
  | { type: 'EDIT'; text: string }
  | { type: 'RETRY' };

export const initialVoice = (language: LanguageCode | 'auto' = 'auto'): VoiceState => ({ kind: 'idle', language });

export function voiceReducer(s: VoiceState, e: VoiceEvent): VoiceState {
  switch (e.type) {
    case 'SELECT_LANGUAGE':
      return s.kind === 'idle' || s.kind === 'error' || s.kind === 'review' ? { ...(s as any), language: e.language } as VoiceState : s;
    case 'PRESS_MIC':
      return s.kind === 'idle' || s.kind === 'error' || s.kind === 'queued_offline' || s.kind === 'review' ? { kind: 'requesting_permission', language: s.language } : s;
    case 'PERMISSION_GRANTED':
      return s.kind === 'requesting_permission' ? { kind: 'recording', language: s.language, startedAt: e.now } : s;
    case 'PERMISSION_DENIED':
      return s.kind === 'requesting_permission' ? { kind: 'error', language: s.language, message: 'Microphone permission is needed for voice input. You can still type your complaint.', audioUri: null, notConfigured: false, permissionDenied: true } : s;
    case 'STOP':
      if (s.kind !== 'recording') return s;
      return e.online ? { kind: 'transcribing', language: s.language, audioUri: e.audioUri } : { kind: 'queued_offline', language: s.language, audioUri: e.audioUri };
    case 'CANCEL':
      return s.kind === 'recording' || s.kind === 'transcribing' || s.kind === 'requesting_permission' ? { kind: 'idle', language: s.language } : s;
    case 'TRANSCRIBED': {
      if (s.kind !== 'transcribing') return s;
      const r = e.result;
      if (r.status === 'NOT_CONFIGURED') return { kind: 'error', language: s.language, message: r.error ?? 'Voice transcription is not configured on this server.', audioUri: s.audioUri, notConfigured: true, permissionDenied: false };
      if (r.status !== 'OK' || !r.transcript) return { kind: 'error', language: s.language, message: r.error ?? 'Could not transcribe the recording.', audioUri: s.audioUri, notConfigured: false, permissionDenied: false };
      const warnings = [...r.warnings];
      const expected = s.language !== 'auto' ? s.language : (r.language_detected as LanguageCode | null);
      if (r.script_ok && expected && !scriptMatches(expected, r.transcript)) warnings.push('The text may not be in the expected script. Please check it.'); // client-side second opinion
      return { kind: 'review', language: s.language, audioUri: s.audioUri, voiceId: r.id, text: r.transcript, original: r.transcript, detected: r.language_detected, detectedBy: r.detected_by, warnings, edited: false };
    }
    case 'FAILED':
      return s.kind === 'transcribing' || s.kind === 'requesting_permission' || s.kind === 'recording'
        ? { kind: 'error', language: s.language, message: e.message, audioUri: (s as any).audioUri ?? null, notConfigured: !!e.notConfigured, permissionDenied: false } : s;
    case 'EDIT':
      return s.kind === 'review' ? { ...s, text: e.text, edited: e.text !== s.original } : s;
    case 'RETRY':
      return s.kind === 'error' && s.audioUri ? { kind: 'transcribing', language: s.language, audioUri: s.audioUri } : s.kind === 'error' ? { kind: 'requesting_permission', language: s.language } : s;
  }
}

/** Languages to offer: exactly what the server's engine declares (never more), plus "auto" only if declared. */
export function offeredLanguages(caps: { state: string; auto_detect: boolean; languages: Array<{ code: LanguageCode }> } | null): Array<LanguageCode | 'auto'> {
  if (!caps || caps.state !== 'CONFIGURED') return [];
  return [...(caps.auto_detect ? (['auto'] as const) : []), ...caps.languages.map((l) => l.code)];
}
