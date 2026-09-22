import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ApiError, NetworkError } from '../src/api/errors.ts';
import { DraftStore, newDraft } from '../src/offline/queue.ts';
import { backoffMs, syncAll } from '../src/offline/sync.ts';
import type { SyncApi } from '../src/offline/sync.ts';
import type { ComplaintInput, VoiceResult } from '../src/api/types.ts';
import { MemoryStorage, SAMPLES } from './helpers.ts';

class Clock { t = Date.parse('2026-09-20T10:00:00Z'); now = () => new Date(this.t); tick(ms: number) { this.t += ms; } }

function setup(over: Partial<SyncApi> = {}, online = true) {
  const clock = new Clock();
  const store = new DraftStore(new MemoryStorage());
  const created: ComplaintInput[] = [];
  const uploads: string[] = [];
  const state = { online, serverIds: new Map<string, string>() };
  const api: SyncApi = {
    uploadEvidence: async (f) => { uploads.push(f.uri); return { id: `ev-${uploads.length}`, name: f.name, mime: f.type, analysis_status: 'PENDING' }; },
    transcribe: async () => { throw new Error('not expected'); },
    createComplaint: async (b) => {
      created.push(b);
      const id = state.serverIds.get(b.client_request_id!) ?? `srv-${state.serverIds.size + 1}`;
      const replayed = state.serverIds.has(b.client_request_id!);
      state.serverIds.set(b.client_request_id!, id);
      return { complaint: { id, reference: 'CL-20260920-ABCDEFGH' } as any, replayed, warnings: [] };
    },
    ...over,
  };
  const deps = { store, api, isOnline: async () => state.online, now: clock.now };
  return { clock, store, created, uploads, state, deps };
}
const draft = (id: string, over = {}) => newDraft(id, '2026-09-20T09:00:00Z', { title: 'Pothole on MG Road', description: 'A large pothole near the bus stop', ...over });

test('offline: nothing is sent and nothing is reported as synced; when online it syncs once with the client_request_id', async () => {
  const s = setup({}, false);
  await s.store.save(draft('d1'), '2026-09-20T09:00:00Z');
  await s.store.submit('d1', '2026-09-20T09:00:01Z');
  const off = await syncAll(s.deps);
  assert.equal(off.skippedOffline, true);
  assert.equal(s.created.length, 0);
  assert.equal((await s.store.get('d1'))!.status, 'pending'); // still pending, honestly
  s.state.online = true;
  const on = await syncAll(s.deps);
  assert.deepEqual(on.synced, ['d1']);
  const d = (await s.store.get('d1'))!;
  assert.deepEqual([d.status, d.serverId, d.reference], ['synced', 'srv-1', 'CL-20260920-ABCDEFGH']);
  assert.equal(s.created[0].client_request_id, 'd1');
});

test('the original-language text is sent exactly as stored (no translation, no normalisation)', async () => {
  const s = setup();
  await s.store.save(draft('k1', { title: 'ರಸ್ತೆ ಗುಂಡಿ', description: SAMPLES.kn + ' ದಯವಿಟ್ಟು', language: 'kn' }), 'x');
  await s.store.submit('k1', 'x');
  await syncAll(s.deps);
  assert.deepEqual([s.created[0].description, s.created[0].language], [SAMPLES.kn + ' ದಯವಿಟ್ಟು', 'kn']);
});

test('a retry after a lost response cannot create a duplicate (same client_request_id => server replays)', async () => {
  const s = setup();
  await s.store.save(draft('r1'), 'x');
  await s.store.submit('r1', 'x');
  await syncAll(s.deps);
  // simulate: app crashed before it recorded success -> draft back to pending, then synced again
  const d = (await s.store.get('r1'))!;
  await s.store.save({ ...d, status: 'pending', serverId: null }, 'x');
  await syncAll(s.deps);
  assert.equal(s.state.serverIds.size, 1);
  assert.equal(s.created.filter((c) => c.client_request_id === 'r1').length, 2); // sent twice, one server complaint
  assert.equal((await s.store.get('r1'))!.serverId, 'srv-1');
});

test('attachments: evidence ids are persisted per file, so a mid-way network failure resumes without re-uploading', async () => {
  let failCreate = true;
  const s = setup({ createComplaint: async (b) => { if (failCreate) throw new NetworkError('offline'); return { complaint: { id: 'srv-9', reference: 'CL-1' } as any, replayed: false, warnings: [] }; } });
  await s.store.save(draft('a1', { attachments: [{ uri: 'file:///1.jpg', name: '1.jpg', type: 'image/jpeg' }, { uri: 'file:///2.jpg', name: '2.jpg', type: 'image/jpeg' }] }), 'x');
  await s.store.submit('a1', 'x');
  const first = await syncAll(s.deps);
  assert.deepEqual(first.deferred, ['a1']);
  assert.deepEqual(s.uploads, ['file:///1.jpg', 'file:///2.jpg']);
  assert.deepEqual((await s.store.get('a1'))!.attachments.map((a) => a.evidenceId), ['ev-1', 'ev-2']);
  failCreate = false;
  s.clock.tick(60 * 60_000);
  await syncAll(s.deps);
  assert.deepEqual(s.uploads.length, 2); // not uploaded again
  assert.equal((await s.store.get('a1'))!.status, 'synced');
});

test('network and 5xx errors back off exponentially; the draft stays pending with the reason', async () => {
  const s = setup({ createComplaint: async () => { throw new ApiError(503, 'dependency_unavailable', 'down'); } });
  await s.store.save(draft('b1'), 'x');
  await s.store.submit('b1', 'x');
  await syncAll(s.deps);
  let d = (await s.store.get('b1'))!;
  assert.deepEqual([d.status, d.attempts, d.lastError], ['pending', 1, 'down']);
  const early = await syncAll(s.deps); // before nextAttemptAt: not retried
  assert.equal(early.deferred.length + early.failed.length + early.synced.length, 0);
  s.clock.tick(backoffMs(1) + 1);
  await syncAll(s.deps);
  d = (await s.store.get('b1'))!;
  assert.equal(d.attempts, 2);
  assert.ok(backoffMs(2) > backoffMs(1) && backoffMs(50) === 15 * 60_000);
});

test('validation errors (4xx) mark the draft failed with a readable reason and are not retried automatically', async () => {
  const s = setup({ createComplaint: async () => { throw new ApiError(422, 'validation_failed', 'The complaint has errors.', { title: 'Title must be 5-200 characters.' }); } });
  await s.store.save(draft('v1'), 'x');
  await s.store.submit('v1', 'x');
  const r = await syncAll(s.deps);
  assert.deepEqual(r.failed, ['v1']);
  const d = (await s.store.get('v1'))!;
  assert.equal(d.status, 'failed');
  assert.match(d.lastError!, /title: Title must be 5-200/);
  s.clock.tick(3_600_000);
  assert.equal((await syncAll(s.deps)).failed.length, 0);
});

test('401 stops the whole run (drafts stay pending and are deferred) and reports authRequired', async () => {
  const s = setup({ createComplaint: async () => { throw new ApiError(401, 'authentication_failed', 'Your session has expired.'); } });
  for (const id of ['u1', 'u2']) { await s.store.save(draft(id), 'x'); await s.store.submit(id, 'x'); }
  const r = await syncAll(s.deps);
  assert.equal(r.authRequired, true);
  assert.deepEqual(r.deferred.sort(), ['u1', 'u2']);
  assert.equal((await s.store.get('u2'))!.status, 'pending');
});

test('offline voice: transcribed later, then STOPPED for review - never auto-submitted; typed text is never overwritten', async () => {
  const transcribe = async (): Promise<VoiceResult> => ({ id: 'voice-1', status: 'OK', language_requested: 'kn', language_detected: 'kn', detected_by: 'provider', transcript: SAMPLES.kn, provider: 'p', error: null, script_ok: true, warnings: [], confidence: 0.9 });
  const s = setup({ transcribe });
  await s.store.save(draft('m1', { title: '', description: '', language: 'kn', audio: { file: { uri: 'file:///v.m4a', name: 'v.m4a', type: 'audio/mp4' }, language: 'kn' } }), 'x');
  await s.store.submit('m1', 'x');
  const r = await syncAll(s.deps);
  assert.deepEqual(r.needsReview, ['m1']);
  assert.equal(s.created.length, 0);
  const d = (await s.store.get('m1'))!;
  assert.deepEqual([d.status, d.voiceId, d.description, d.transcript, d.language], ['needs_review', 'voice-1', SAMPLES.kn, SAMPLES.kn, 'kn']);
  // typed text present -> transcript is stored for provenance but does not replace it
  await s.store.save(draft('m2', { description: 'My own typed description here', language: 'kn', audio: { file: { uri: 'f', name: 'v', type: 'audio/mp4' }, language: 'kn' } }), 'x');
  await s.store.submit('m2', 'x');
  await syncAll(s.deps);
  assert.equal((await s.store.get('m2'))!.description, 'My own typed description here');
  // after the citizen reviews and confirms, it is sent WITH the voice id
  await s.store.save({ ...(await s.store.get('m1'))!, title: 'ರಸ್ತೆ ಗುಂಡಿ', status: 'pending' }, 'x');
  await syncAll(s.deps);
  assert.equal(s.created[0].voice_id, 'voice-1');
});

test('voice engine not configured: the draft fails honestly instead of inventing text', async () => {
  const s = setup({ transcribe: async () => ({ id: 'v', status: 'NOT_CONFIGURED', language_requested: 'kn', language_detected: null, detected_by: null, transcript: null, provider: null, error: 'No speech-to-text engine is configured; no transcript was produced.', script_ok: true, warnings: [], confidence: null }) });
  await s.store.save(draft('n1', { title: '', description: '', audio: { file: { uri: 'f', name: 'v', type: 'audio/mp4' }, language: 'kn' } }), 'x');
  await s.store.submit('n1', 'x');
  const r = await syncAll(s.deps);
  assert.deepEqual(r.failed, ['n1']);
  const d = (await s.store.get('n1'))!;
  assert.equal(d.description, '');
  assert.match(d.lastError!, /no transcript/);
});

test('store: submit refuses an empty draft; counts reflect statuses; remove deletes', async () => {
  const s = setup();
  await s.store.save(draft('e1', { title: '', description: '' }), 'x');
  await assert.rejects(s.store.submit('e1', 'x'), /title and description/);
  await s.store.save(draft('e2'), 'x');
  await s.store.submit('e2', 'x');
  const c = await s.store.counts();
  assert.deepEqual([c.draft, c.pending], [1, 1]);
  await s.store.remove('e1');
  assert.equal((await s.store.list()).length, 1);
});
