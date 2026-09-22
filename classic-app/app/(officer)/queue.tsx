import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { AppButton, Body, Card, Chip, EmptyState, ErrorBanner, H1, Loading, Screen, StatusBadge } from '../../src/components/ui.tsx';
import { endpoints } from '../../src/api/instance.ts';
import type { OfficerQueueItem } from '../../src/api/types.ts';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

const STATUSES = ['submitted', 'ai_routed', 'assigned', 'under_review', 'inspection_scheduled', 'in_progress', 'resolved', 'closed', 'rejected'];

export default function OfficerQueue() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const router = useRouter();
  const [status, setStatus] = useState<string | null>(null);
  const [mineOnly, setMineOnly] = useState(false);
  const [items, setItems] = useState<OfficerQueueItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try { setItems((await endpoints.officerQueue({ mine_only: mineOnly, status })).items); }
    catch (e: any) { setItems([]); setError(e?.message ?? 'Could not load the queue.'); }
  }, [status, mineOnly]);
  useEffect(() => { load(); }, [load]);

  return (
    <Screen>
      <H1>{t('nav.officer_queue')}</H1>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        <Chip label="All" selected={status === null} onPress={() => setStatus(null)} />
        {STATUSES.map((s) => <Chip key={s} label={s.replace(/_/g, ' ')} selected={status === s} onPress={() => setStatus(s)} />)}
      </View>
      <Pressable accessibilityRole="button" onPress={() => setMineOnly((v) => !v)} style={{ minHeight: 44 }}>
        <Card><Text style={{ color: colors.text }}>{mineOnly ? '☑' : '☐'}  Assigned to me only</Text></Card>
      </Pressable>
      {error ? <ErrorBanner message={error} onRetry={load} /> : null}
      {items === null ? <Loading label={t('msg.loading')} /> : items.length === 0 ? <EmptyState message={t('msg.no_data')} /> : items.map((c) => (
        <Pressable key={c.id} accessibilityRole="button" onPress={() => router.push(`/officer-complaint/${c.id}`)}>
          <Card>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ fontWeight: '700', color: colors.text }}>{c.reference}</Text>
              <StatusBadge status={c.status} />
            </View>
            <Body>{c.title}</Body>
            <Body soft>{c.category} · {c.priority}{c.ward ? ` · Ward ${c.ward}` : ''}</Body>
            {c.sla_due_at ? <Body soft>Due: {new Date(c.sla_due_at).toLocaleString()}</Body> : null}
            {c.escalation_level ? <Body soft>⚠ Escalated (level {c.escalation_level})</Body> : null}
          </Card>
        </Pressable>
      ))}
      <AppButton label={t('act.refresh')} kind="secondary" onPress={async () => { setRefreshing(true); await load(); setRefreshing(false); }} busy={refreshing} />
    </Screen>
  );
}
