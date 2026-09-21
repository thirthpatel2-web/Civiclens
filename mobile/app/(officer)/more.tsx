import React from 'react';
import { Pressable, Text } from 'react-native';
import { useRouter } from 'expo-router';
import { Body, Card, H1, Screen } from '../../src/components/ui.tsx';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useAuth } from '../../src/auth/AuthContext.tsx';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

const items: Array<[string, string, string]> = [
  ['/notifications', 'nav.notifications', '🔔'], ['/directory', 'nav.departments', '📖'], ['/locator', 'nav.locator', '📍'],
  ['/interop', 'nav.interop', '🔗'], ['/copilot', 'nav.copilot', '🤖'], ['/map', 'nav.gis', '🗺️'], ['/settings', 'nav.settings', '⚙️'],
];
const adminItems: Array<[string, string, string]> = [
  ['/monitoring', 'nav.monitoring', '🩺'], ['/workflow-rules', 'nav.workflow', '⚙️'],
];
export default function OfficerMore() {
  const { t } = useI18n();
  const { user, signOut } = useAuth();
  const { colors } = useTheme();
  const router = useRouter();
  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin';
  return (
    <Screen>
      <H1>{t('nav.account')}</H1>
      <Card><Body>{user?.full_name ?? user?.email}</Body><Body soft>{user?.role} · {user?.department_code ?? 'no department assigned'}</Body></Card>
      {(isAdmin ? [...items, ...adminItems] : items).map(([href, key, icon]) => (
        <Pressable key={href} accessibilityRole="button" onPress={() => router.push(href as any)} style={{ minHeight: 56 }}>
          <Card><Text style={{ fontSize: 17, color: colors.text }}>{icon}  {t(key)}</Text></Card>
        </Pressable>
      ))}
      <Pressable accessibilityRole="button" onPress={signOut} style={{ minHeight: 56 }}><Card><Text style={{ fontSize: 17, color: colors.bad }}>↩︎  {t('act.sign_out')}</Text></Card></Pressable>
    </Screen>
  );
}
