import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, Text } from 'react-native';
import { useRouter } from 'expo-router';
import { Body, Card, EmptyState, ErrorBanner, H1, Loading, Screen, StatusBadge } from '../../src/components/ui.tsx';
import { endpoints } from '../../src/api/instance.ts';
import type { Investigation } from '../../src/api/types.ts';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

export default function Investigations() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const router = useRouter();
  const [items, setItems] = useState<Investigation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try { setItems((await endpoints.listInvestigations()).items); }
    catch (e: any) { setItems([]); setError(e?.message ?? 'Could not load investigations.'); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <Screen>
      <H1>{t('nav.investigations')}</H1>
      <Body soft>Open an investigation from a complaint's detail screen to build a case file around it.</Body>
      {error ? <ErrorBanner message={error} onRetry={load} /> : null}
      {items === null ? <Loading label={t('msg.loading')} /> : items.length === 0 ? <EmptyState message={t('msg.no_data')} /> : items.map((inv) => (
        <Pressable key={inv.id} accessibilityRole="button" onPress={() => router.push(`/investigation/${inv.id}`)}>
          <Card>
            <Text style={{ fontWeight: '700', color: colors.text }}>{inv.subject_type} · {inv.subject_id.slice(0, 8)}</Text>
            <StatusBadge status={inv.status} />
            <Body soft>Opened {new Date(inv.created_at).toLocaleString()}</Body>
            {inv.notes.length ? <Body soft>{inv.notes.length} note{inv.notes.length === 1 ? '' : 's'}</Body> : null}
          </Card>
        </Pressable>
      ))}
    </Screen>
  );
}
