import { test } from 'node:test';
import assert from 'node:assert/strict';
import { initialVoice, offeredLanguages, voiceReducer } from '../src/voice/voiceMachine.ts';
import type { VoiceEvent, VoiceState } from '../src/voice/voiceMachine.ts';
import type { VoiceResult } from '../src/api/types.ts';
import { ENGLISH_TRANSLATION, SAMPLES } from './helpers.ts';

const run = (s: VoiceState, ...events: VoiceEvent[]) => events.reduce(voiceReducer, s);
const result = (over: Partial<VoiceResult>): VoiceResult => ({ id: 'v1', status: 'OK', language_requested: 'kn', language_detected: 'kn', detected_by: 'provider', transcript: SAMPLES.kn, provider: 'p', error: null, script_ok: true, warnings: [], confidence: 0.9, ...over });
const toReview = (lang: any, r: VoiceResult) => run(initialVoice(lang), { type: 'PRESS_MIC' }, { type: 'PERMISSION_GRANTED', now: 1 }, { type: 'STOP', audioUri: 'file:///a.m4a', online: true }, { type: 'TRANSCRIBED', result: r });

test('speech in each language reaches the review screen in that language and script, never as an English translation', () => {
  for (const code of ['kn', 'hi', 'ta', 'te', 'en'] as const) {
    const s = toReview(code, result({ language_requested: code, language_detected: code, transcript: SAMPLES[code] }));
    assert.equal(s.kind, 'review');
    if (s.kind !== 'review') return;
    assert.equal(s.text, SAMPLES[code], code);
    assert.equal(s.original, SAMPLES[code]);
    assert.notEqual(s.text, ENGLISH_TRANSLATION);
    assert.equal(s.detected, code);
    assert.equal(s.edited, false);
    assert.deepEqual(s.warnings, []);
  }
});

test('the citizen can edit the transcript; the engine original is kept and the edit is flagged', () => {
  const s = run(toReview('kn', result({})), { type: 'EDIT', text: SAMPLES.kn + ' ದಯವಿಟ್ಟು ಸರಿಪಡಿಸಿ' });
  assert.ok(s.kind === 'review' && s.edited && s.original === SAMPLES.kn && s.text.endsWith('ಸರಿಪಡಿಸಿ'));
  const back = run(s, { type: 'EDIT', text: SAMPLES.kn });
  assert.ok(back.kind === 'review' && back.edited === false);
});

test('auto-detect keeps the detected language shown with its source', () => {
  const s = toReview('auto', result({ language_requested: 'auto', language_detected: 'ta', transcript: SAMPLES.ta, detected_by: 'provider' }));
  assert.ok(s.kind === 'review' && s.language === 'auto' && s.detected === 'ta' && s.detectedBy === 'provider' && s.text === SAMPLES.ta);
});

test('a romanised/translated-looking result is flagged (server flag and client script check), not altered', () => {
  const server = toReview('kn', result({ transcript: 'nanna rasteyalli dodda gundi ide', script_ok: false, warnings: ['not in expected script'] }));
  assert.ok(server.kind === 'review' && server.warnings.length === 1 && server.text === 'nanna rasteyalli dodda gundi ide');
  const client = toReview('kn', result({ transcript: ENGLISH_TRANSLATION, script_ok: true }));
  assert.ok(client.kind === 'review' && client.warnings.some((w) => w.includes('script')) && client.text === ENGLISH_TRANSLATION);
});

test('not configured, provider failure, permission denial and offline recordings are each shown truthfully', () => {
  const nc = toReview('kn', result({ status: 'NOT_CONFIGURED', transcript: null, error: 'No speech-to-text engine is configured; no transcript was produced.' }));
  assert.ok(nc.kind === 'error' && nc.notConfigured && nc.message.includes('no transcript'));
  const failed = run(initialVoice('hi'), { type: 'PRESS_MIC' }, { type: 'PERMISSION_GRANTED', now: 1 }, { type: 'STOP', audioUri: 'u', online: true }, { type: 'FAILED', message: 'boom' });
  assert.ok(failed.kind === 'error' && !failed.notConfigured);
  assert.equal(run(failed, { type: 'RETRY' }).kind, 'transcribing'); // the recording is kept, so retry re-sends it
  const denied = run(initialVoice('hi'), { type: 'PRESS_MIC' }, { type: 'PERMISSION_DENIED' });
  assert.ok(denied.kind === 'error' && denied.permissionDenied && denied.audioUri === null);
  assert.equal(run(denied, { type: 'RETRY' }).kind, 'requesting_permission');
  const offline = run(initialVoice('kn'), { type: 'PRESS_MIC' }, { type: 'PERMISSION_GRANTED', now: 1 }, { type: 'STOP', audioUri: 'u', online: false });
  assert.equal(offline.kind, 'queued_offline'); // nothing is transcribed or "submitted" while offline
});

test('cancel returns to idle; events in the wrong state are ignored', () => {
  assert.equal(run(initialVoice('kn'), { type: 'PRESS_MIC' }, { type: 'CANCEL' }).kind, 'idle');
  assert.equal(run(initialVoice('kn'), { type: 'STOP', audioUri: 'u', online: true }).kind, 'idle');
  assert.equal(run(initialVoice('kn'), { type: 'TRANSCRIBED', result: result({}) }).kind, 'idle');
});

test('only languages the server engine declares are offered; auto only if declared', () => {
  assert.deepEqual(offeredLanguages(null), []);
  assert.deepEqual(offeredLanguages({ state: 'NOT_CONFIGURED', auto_detect: true, languages: [{ code: 'kn' }] }), []);
  assert.deepEqual(offeredLanguages({ state: 'CONFIGURED', auto_detect: false, languages: [{ code: 'kn' }, { code: 'hi' }] }), ['kn', 'hi']);
  assert.deepEqual(offeredLanguages({ state: 'CONFIGURED', auto_detect: true, languages: [{ code: 'ta' }] }), ['auto', 'ta']);
});
