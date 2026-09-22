import React, { useCallback, useEffect, useState } from 'react';
import { Text } from 'react-native';
import { AppButton, Body, Card, EmptyState, ErrorBanner, H1, InfoBanner, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { NotificationItem } from '../src/api/types.ts';
import { enableNotifications, useNotificationAlerts } from '../src/hooks/useNotifications.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { withAlpha } from '../src/theme.ts';
import { useTheme } from '../src/theme/ThemeContext.tsx';

export default function Notifications() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [perm, setPerm] = useState<'granted' | 'denied' | 'unavailable' | null>(null);
  const load = useCallback(async () => { setError(null); try { setItems((await endpoints.notifications()).items); } catch (e: any) { setError(e?.message ?? 'Could not load notifications.'); } }, []);
  useEffect(() => { load(); }, [load]);
  useNotificationAlerts(perm === 'granted');
  return (
    <Screen>
      <H1>{t('nav.notifications')}</H1>
      {perm === null ? (<Card><Body>Get an alert when your complaint's status changes or an escalation happens. CivicLens will ask your phone for permission next.</Body><AppButton label="Turn on alerts" onPress={async () => setPerm(await enableNotifications())} /></Card>) : null}
      {perm === 'denied' ? <InfoBanner tone="warn" message="Alerts are off. You can enable them in your phone's settings." /> : null}
      {perm === 'unavailable' ? <InfoBanner message="Alerts work while the app is open. Background push is not available for this build." /> : null}
      {error ? <ErrorBanner message={error} onRetry={load} /> : items === null ? <Loading /> : items.length === 0 ? <EmptyState message={t('msg.no_data')} /> : items.map((n) => (
        <Card key={n.id} style={n.read_at ? undefined : { backgroundColor: withAlpha(colors.primary, 0.08) }}>
          <Text style={{ fontWeight: '600', color: colors.text }}>{n.title}</Text><Body>{n.body}</Body><Body soft>{new Date(n.created_at).toLocaleString()}</Body>
          {!n.read_at ? <AppButton label="Mark read" kind="secondary" onPress={async () => { await endpoints.markRead(n.id); load(); }} /> : null}
        </Card>
      ))}
    </Screen>
  );
}
