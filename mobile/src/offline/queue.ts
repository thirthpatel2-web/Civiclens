// Offline draft store. Storage is injected (AsyncStorage in the app, an in-memory map in tests).
// Nothing here ever claims a server submission: 'synced' is set only by the sync engine after the server returned a complaint id.

import type { LanguageCode } from '../i18n/languages.ts';
import type { LocalFile } from '../api/types.ts';

export interface KeyValueStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export type DraftStatus = 'draft' | 'pending' | 'syncing' | 'needs_review' | 'failed' | 'synced';

export interface DraftAttachment extends LocalFile { evidenceId?: string }
export interface DraftAudio { file: LocalFile; language: LanguageCode | 'auto' }

export interface ComplaintDraft {
  id: string; // doubles as the server-side client_request_id: makes resubmission idempotent
  createdAt: string;
  updatedAt: string;
  title: string;
  description: string; // ORIGINAL text as typed/spoken - never replaced by a translation
  language: LanguageCode;
  category: string | null;
  ward: string | null;
  lat: number | null;
  lng: number | null;
  attachments: DraftAttachment[];
  audio: DraftAudio | null; // recorded while offline, awaiting transcription
  voiceId: string | null;
  transcript: string | null; // engine output kept unedited for provenance
  detectedLanguage: string | null;
  status: DraftStatus;
  attempts: number;
  lastError: string | null;
  nextAttemptAt: string | null;
  serverId: string | null;
  reference: string | null;
}

const INDEX_KEY = 'civiclens.drafts.index.v1';
const itemKey = (id: string) => `civiclens.draft.${id}.v1`;

export function newDraft(id: string, now: string, partial: Partial<ComplaintDraft> = {}): ComplaintDraft {
  return {
    id, createdAt: now, updatedAt: now, title: '', description: '', language: 'en', category: null, ward: null, lat: null, lng: null,
    attachments: [], audio: null, voiceId: null, transcript: null, detectedLanguage: null, status: 'draft', attempts: 0, lastError: null,
    nextAttemptAt: null, serverId: null, reference: null, ...partial,
  };
}

export class DraftStore {
  private storage: KeyValueStorage;
  constructor(storage: KeyValueStorage) { this.storage = storage; }

  private async ids(): Promise<string[]> {
    const raw = await this.storage.getItem(INDEX_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  }

  async list(): Promise<ComplaintDraft[]> {
    const out: ComplaintDraft[] = [];
    for (const id of await this.ids()) {
      const d = await this.get(id);
      if (d) out.push(d);
    }
    return out.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }

  async get(id: string): Promise<ComplaintDraft | null> {
    const raw = await this.storage.getItem(itemKey(id));
    return raw ? (JSON.parse(raw) as ComplaintDraft) : null;
  }

  async save(d: ComplaintDraft, now: string): Promise<ComplaintDraft> {
    const saved = { ...d, updatedAt: now };
    await this.storage.setItem(itemKey(d.id), JSON.stringify(saved));
    const ids = await this.ids();
    if (!ids.includes(d.id)) await this.storage.setItem(INDEX_KEY, JSON.stringify([...ids, d.id]));
    return saved;
  }

  async remove(id: string): Promise<void> {
    await this.storage.removeItem(itemKey(id));
    await this.storage.setItem(INDEX_KEY, JSON.stringify((await this.ids()).filter((x) => x !== id)));
  }

  /** Queue the draft for synchronisation. Refuses an empty draft (needs text, or audio awaiting transcription). */
  async submit(id: string, now: string): Promise<ComplaintDraft> {
    const d = await this.get(id);
    if (!d) throw new Error('draft not found');
    const hasText = d.description.trim().length >= 10 && d.title.trim().length >= 5;
    if (!hasText && !d.audio) throw new Error('Add a title and description (or a voice recording) before submitting.');
    return this.save({ ...d, status: 'pending', lastError: null, nextAttemptAt: null }, now);
  }

  async counts(): Promise<Record<DraftStatus, number>> {
    const c: Record<DraftStatus, number> = { draft: 0, pending: 0, syncing: 0, needs_review: 0, failed: 0, synced: 0 };
    for (const d of await this.list()) c[d.status] += 1;
    return c;
  }
}
