// Synchronisation engine: turns queued drafts into server complaints, safely and idempotently.
// Rules: never mark 'synced' without a server complaint id; never auto-submit an unreviewed transcript; keep progress after every step
// (uploaded evidence ids survive a crash); back off on network/5xx; stop on 401; surface 4xx validation errors to the user.

import { ApiError, NetworkError } from '../api/errors.ts';
import type { ComplaintInput, CreateComplaintResponse, Evidence, LocalFile, VoiceResult } from '../api/types.ts';
import type { ComplaintDraft, DraftStore } from './queue.ts';
import type { LanguageCode } from '../i18n/languages.ts';

export interface SyncApi {
  uploadEvidence(file: LocalFile): Promise<Evidence>;
  transcribe(file: LocalFile, language: LanguageCode | 'auto'): Promise<VoiceResult>;
  createComplaint(body: ComplaintInput): Promise<CreateComplaintResponse>;
}

export interface SyncDeps { store: DraftStore; api: SyncApi; isOnline: () => Promise<boolean>; now: () => Date }
export interface SyncSummary { synced: string[]; needsReview: string[]; failed: string[]; deferred: string[]; skippedOffline: boolean; authRequired: boolean }

export function backoffMs(attempts: number): number {
  return Math.min(15 * 60_000, 15_000 * 2 ** Math.max(0, attempts - 1));
}

export async function syncAll(deps: SyncDeps): Promise<SyncSummary> {
  const summary: SyncSummary = { synced: [], needsReview: [], failed: [], deferred: [], skippedOffline: false, authRequired: false };
  if (!(await deps.isOnline())) return { ...summary, skippedOffline: true };
  const now = deps.now();
  const drafts = (await deps.store.list()).filter((d) => (d.status === 'pending' || d.status === 'syncing') && (!d.nextAttemptAt || new Date(d.nextAttemptAt) <= now));
  for (const d of drafts.reverse()) { // oldest first
    if (summary.authRequired) { summary.deferred.push(d.id); continue; }
    const outcome = await syncOne(deps, d);
    if (outcome === 'auth') { summary.authRequired = true; summary.deferred.push(d.id); }
    else if (outcome === 'synced') summary.synced.push(d.id);
    else if (outcome === 'needs_review') summary.needsReview.push(d.id);
    else if (outcome === 'failed') summary.failed.push(d.id);
    else summary.deferred.push(d.id);
  }
  return summary;
}

type Outcome = 'synced' | 'needs_review' | 'failed' | 'deferred' | 'auth';

async function syncOne(deps: SyncDeps, start: ComplaintDraft): Promise<Outcome> {
  const { store, api } = deps;
  const at = () => deps.now().toISOString();
  let d = await store.save({ ...start, status: 'syncing' }, at());
  try {
    // 1) Voice recorded while offline: transcribe now, then STOP for review. Never submit an unreviewed transcript.
    if (d.audio && !d.voiceId) {
      const r = await api.transcribe(d.audio.file, d.audio.language);
      if (r.status !== 'OK' || !r.transcript) {
        d = await store.save({ ...d, status: 'failed', lastError: r.error ?? `Transcription ${r.status}`, attempts: d.attempts + 1 }, at());
        return 'failed';
      }
      d = await store.save({ ...d, voiceId: r.id, transcript: r.transcript, detectedLanguage: r.language_detected,
        description: d.description.trim() ? d.description : r.transcript, // fill only if empty; a typed text is never overwritten
        language: (d.audio.language !== 'auto' ? d.audio.language : (r.language_detected as LanguageCode | null) ?? d.language),
        status: 'needs_review', lastError: r.warnings.join(' ') || null }, at());
      return 'needs_review';
    }
    // 2) Attachments: upload once each, persisting the evidence id immediately (retry-safe).
    for (let i = 0; i < d.attachments.length; i++) {
      if (d.attachments[i].evidenceId) continue;
      const ev = await api.uploadEvidence(d.attachments[i]);
      const attachments = d.attachments.map((a, j) => (j === i ? { ...a, evidenceId: ev.id } : a));
      d = await store.save({ ...d, attachments }, at());
    }
    // 3) Create the complaint. client_request_id = draft id => a replay returns the original complaint (no duplicates).
    const res = await api.createComplaint({
      title: d.title.trim(), description: d.description.trim(), language: d.language, category: d.category, ward: d.ward, lat: d.lat, lng: d.lng,
      client_request_id: d.id, evidence_ids: d.attachments.map((a) => a.evidenceId!).filter(Boolean), voice_id: d.voiceId,
    });
    await store.save({ ...d, status: 'synced', serverId: res.complaint.id, reference: res.complaint.reference, lastError: null, nextAttemptAt: null }, at());
    return 'synced';
  } catch (e: any) {
    if (e instanceof ApiError) {
      if (e.isAuth) { await store.save({ ...d, status: 'pending', lastError: 'Sign in again to finish sending this complaint.' }, at()); return 'auth'; }
      if (e.status >= 500 || e.status === 429) return retryLater(deps, d, e.message);
      await store.save({ ...d, status: 'failed', attempts: d.attempts + 1, lastError: describe(e) }, at()); // 4xx: the user must fix it
      return 'failed';
    }
    if (e instanceof NetworkError) return retryLater(deps, d, e.message);
    return retryLater(deps, d, String(e?.message ?? e));
  }
}

async function retryLater(deps: SyncDeps, d: ComplaintDraft, message: string): Promise<Outcome> {
  const attempts = d.attempts + 1;
  const next = new Date(deps.now().getTime() + backoffMs(attempts)).toISOString();
  await deps.store.save({ ...d, status: 'pending', attempts, lastError: message, nextAttemptAt: next }, deps.now().toISOString());
  return 'deferred';
}

function describe(e: ApiError): string {
  const d = e.details && typeof e.details === 'object' ? Object.entries(e.details as Record<string, unknown>).map(([k, v]) => `${k}: ${v}`).join('; ') : '';
  return d ? `${e.message} (${d})` : e.message;
}
