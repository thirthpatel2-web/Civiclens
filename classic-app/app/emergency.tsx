import React, { useEffect, useState } from 'react';
import { Linking, Text } from 'react-native';
import { AppButton, Body, Card, EmptyState, ErrorBanner, H1, InfoBanner, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { Helpline } from '../src/api/types.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { useTheme } from '../src/theme/ThemeContext.tsx';

export default function Emergency() {
  const { t, lang } = useI18n();
  const { colors } = useTheme();
  const [data, setData] = useState<{ notice: string; items: Helpline[]; configured: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { endpoints.helplines(lang).then(setData).catch((e) => setError(e?.message ?? 'Could not load helplines.')); }, [lang]);
  return (
    <Screen>
      <H1>{t('nav.emergency')}</H1>
      <InfoBanner tone="warn" message={t('msg.emergency_warning')} />
      {error ? <ErrorBanner message={error} /> : !data ? <Loading /> : !data.configured || data.items.length === 0 ? <EmptyState message="No emergency contacts are configured on this server." /> : data.items.map((h) => (
        <Card key={h.code}>
          <Text style={{ fontWeight: '700', fontSize: 16, color: colors.text }}>{h.name}</Text><Body soft>{h.description}</Body>
          <AppButton label={`Call ${h.number}`} icon="📞" onPress={() => Linking.openURL(h.tel_uri)} />
        </Card>
      ))}
    </Screen>
  );
}
