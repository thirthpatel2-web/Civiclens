import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { AppButton, Body, Card, Chip, EmptyState, ErrorBanner, H1, Loading, Screen, StatusBadge } from '../../src/components/ui.tsx';
import { endpoints } from '../../src/api/instance.ts';
import type { Complaint } from '../../src/api/types.ts';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useSync } from '../../src/offline/SyncContext.tsx';
import { draftStore, deleteLocalFile } from '../../src/offline/storage.ts';
import type { ComplaintDraft } from '../../src/offline/queue.ts';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

const FILTERS = ['all', 'active', 'resolved', 'rti', 'municipal', 'utility', 'legal'];
const draftLabel: Record<string, string> = { draft: 'Draft (not submitted)', pending: 'Waiting to send', syncing: 'Sending…', needs_review: 'Check the text, then send', failed: 'Needs your attention', synced: 'Sent' };

export default function Track() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const router = useRouter();
  const { online, syncNow, syncing, reload } = useSync();
  const [filter, setFilter] = useState('all');
  const [items, setItems] = useState<Complaint[] | null>(null);
  const [drafts, setDrafts] = useState<ComplaintDraft[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    setDrafts((await draftStore.list()).filter((d) => d.status !== 'synced'));
    try { setItems((await endpoints.listComplaints(filter)).items); } catch (e: any) { setItems([]); setError(online ? (e?.message ?? 'Could not load your complaints.') : 'You are offline. Showing drafts saved on this device.'); }
  }, [filter, online]);
  useEffect(() => { load(); }, [load]);

  const mutate = async (fn: () => Promise<unknown>) => { await fn(); await reload(); await load(); };
  return (
    <Screen>
      <H1>{t('nav.grievances')}</H1>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{FILTERS.map((f) => <Chip key={f} label={t(`filter.${f}`)} selected={filter === f} onPress={() => setFilter(f)} />)}</View>
      {drafts.length > 0 ? (
        <>
          <Text style={{ fontWeight: '700', color: colors.text }}>On this device</Text>
          {drafts.map((d) => (
            <Card key={d.id}>
              <Body>{d.title || d.description.slice(0, 60) || 'Voice recording'}</Body>
              <Body soft>{draftLabel[d.status]}{d.attempts ? ` · attempt ${d.attempts}` : ''}</Body>
              {d.lastError ? <ErrorBanner message={d.lastError} /> : null}
              {d.status === 'needs_review' ? <Body>{d.description}</Body> : null}
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                {(d.status === 'needs_review' || d.status === 'failed' || d.status === 'draft') ? <AppButton label="Send" onPress={() => mutate(async () => { await draftStore.submit(d.id, new Date().toISOString()); await syncNow(); })} disabled={!online} /> : null}
                {d.status === 'pending' ? <AppButton label={t('act.retry')} kind="secondary" onPress={() => mutate(syncNow as any)} disabled={!online} busy={syncing} /> : null}
                <AppButton label="Delete" kind="danger" onPress={() => mutate(async () => { await Promise.all([...d.attachments.map((a) => deleteLocalFile(a.uri)), d.audio ? deleteLocalFile(d.audio.file.uri) : Promise.resolve()]); await draftStore.remove(d.id); })} />
              </View>
            </Card>
          ))}
        </>
      ) : null}
      {error ? <ErrorBanner message={error} onRetry={load} /> : null}
      {items === null ? <Loading label={t('msg.loading')} /> : items.length === 0 && drafts.length === 0 ? <EmptyState message={t('msg.empty_complaints')} /> : items.map((c) => (
        <Pressable key={c.id} accessibilityRole="button" onPress={() => router.push(`/complaint/${c.id}`)}>
          <Card>
            <Text style={{ fontWeight: '700', color: colors.text }}>{c.reference}</Text>
            <Body>{c.original_text.slice(0, 140)}</Body>
            <StatusBadge status={c.status} />
            {c.input_method === 'voice' ? <Body soft>🎤 voice · {c.original_language}</Body> : null}
          </Card>
        </Pressable>
      ))}
      <AppButton label={t('act.refresh')} kind="secondary" onPress={async () => { setRefreshing(true); await load(); setRefreshing(false); }} busy={refreshing} />
    </Screen>
  );
}
