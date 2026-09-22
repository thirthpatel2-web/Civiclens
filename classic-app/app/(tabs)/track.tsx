// Ported from legacy-prototype/src/screens/TrackingScreen.js (header, search bar, status filter
// chips, 30-day overdue banner + escalation, expandable card layout) - wired to the real
// /complaints list and the real offline draft queue instead of the zip's local complaints array.
import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { AppButton, Body, Card, EmptyState, ErrorBanner, Loading, Screen, StatusBadge } from '../../src/components/ui.tsx';
import { endpoints } from '../../src/api/instance.ts';
import type { Complaint } from '../../src/api/types.ts';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useSync } from '../../src/offline/SyncContext.tsx';
import { draftStore, deleteLocalFile } from '../../src/offline/storage.ts';
import type { ComplaintDraft } from '../../src/offline/queue.ts';
import { useTheme } from '../../src/theme/ThemeContext.tsx';
import { fontFamily, radius, shadow, spacing, withAlpha } from '../../src/theme.ts';

const FILTERS = ['all', 'active', 'resolved', 'rti', 'municipal', 'utility', 'legal'];
const draftLabel: Record<string, string> = { draft: 'Draft (not submitted)', pending: 'Waiting to send', syncing: 'Sending…', needs_review: 'Check the text, then send', failed: 'Needs your attention', synced: 'Sent' };
const RESOLVED_STATUSES = ['resolved', 'closed'];

export default function Track() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const router = useRouter();
  const { online, syncNow, syncing, reload } = useSync();
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
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

  const visible = (items ?? []).filter((c) => !search.trim() || `${c.reference} ${c.title} ${c.department_code ?? ''}`.toLowerCase().includes(search.trim().toLowerCase()));

  return (
    <Screen>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View>
          <Text style={{ fontFamily: fontFamily.displayBold, fontSize: 20, color: colors.text }}>📊 {t('nav.grievances')}</Text>
          <Text style={{ fontSize: 12, marginTop: 3, color: colors.textSoft }}>One window across every filing you've made with CivicLens</Text>
        </View>
      </View>

      <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, borderRadius: radius.md, borderWidth: 1, height: 44, gap: 8, backgroundColor: colors.card, borderColor: colors.border }}>
        <Ionicons name="search-outline" size={18} color={colors.textMuted} />
        <TextInput style={{ flex: 1, fontFamily: fontFamily.body, fontSize: 13, color: colors.text }} placeholder="Search by reference, title or department..." placeholderTextColor={colors.textMuted} value={search} onChangeText={setSearch} />
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {FILTERS.map((f) => {
          const selected = filter === f;
          return (
            <Pressable key={f} accessibilityRole="button" onPress={() => setFilter(f)} style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.full, borderWidth: 1, backgroundColor: selected ? colors.primary : colors.card, borderColor: selected ? colors.primary : colors.border }}>
              <Text style={{ fontSize: 12, color: selected ? '#fff' : colors.textSoft, fontWeight: selected ? '700' : '500' }}>{t(`filter.${f}`)}</Text>
            </Pressable>
          );
        })}
      </View>

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
      {items === null ? <Loading label={t('msg.loading')} /> : visible.length === 0 && drafts.length === 0 ? <EmptyState message={t('msg.empty_complaints')} /> : visible.map((c) => {
        const isResolved = RESOLVED_STATUSES.includes(c.status);
        const daysSince = Math.floor((Date.now() - new Date(c.created_at).getTime()) / 86400000);
        const isOverdue = daysSince >= 30 && !isResolved;
        return (
          <Pressable key={c.id} accessibilityRole="button" onPress={() => router.push(`/complaint/${c.id}`)}>
            <View style={[{ borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, backgroundColor: colors.card, borderColor: isOverdue ? colors.accentAmber : colors.border }, shadow.sm]}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <Text style={{ fontSize: 11, fontWeight: '800', letterSpacing: 0.5, color: colors.primaryLight }}>{c.reference}</Text>
                    <StatusBadge status={c.status} />
                  </View>
                  <Text numberOfLines={2} style={{ fontFamily: fontFamily.bodyExtraBold, fontSize: 14, color: colors.text }}>{c.original_text.slice(0, 140)}</Text>
                  <Text style={{ fontSize: 11, marginTop: 4, color: colors.textMuted }}>🏢 {c.department_code ?? 'unrouted'} · filed {daysSince}d ago{c.input_method === 'voice' ? ` · 🎤 ${c.original_language}` : ''}</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
              </View>
              {isOverdue ? (
                <View style={{ flexDirection: 'row', alignItems: 'center', padding: 10, borderRadius: radius.md, borderWidth: 1, marginTop: 10, gap: 8, backgroundColor: withAlpha(colors.accentAmber, 0.15), borderColor: colors.accentAmber }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 12, fontWeight: '800', color: colors.text }}>⚠️ Statutory 30-Day Limit Exceeded</Text>
                    <Text style={{ fontSize: 10, marginTop: 1, lineHeight: 14, color: colors.textSoft }}>You're entitled to file a formal RTI Appeal for administrative delay.</Text>
                  </View>
                  <Pressable accessibilityRole="button" onPress={() => router.push({ pathname: '/(tabs)/report', params: { tab: 'rti' } })} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.sm, backgroundColor: colors.accentAmber }}>
                    <Text style={{ color: '#fff', fontSize: 11, fontWeight: '800' }}>Auto RTI</Text>
                  </Pressable>
                </View>
              ) : null}
            </View>
          </Pressable>
        );
      })}
      <AppButton label={t('act.refresh')} kind="secondary" onPress={async () => { setRefreshing(true); await load(); setRefreshing(false); }} busy={refreshing} />
    </Screen>
  );
}
