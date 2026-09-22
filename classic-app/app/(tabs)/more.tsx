import React from 'react';
import { Pressable, Text } from 'react-native';
import { useRouter } from 'expo-router';
import { Card, H1, Screen } from '../../src/components/ui.tsx';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useAuth } from '../../src/auth/AuthContext.tsx';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

const items: Array<[string, string, string]> = [
  ['/notifications', 'nav.notifications', '🔔'], ['/(tabs)/report?tab=rti', 'nav.rti', '⚖️'], ['/legal', 'nav.legal', '🏛️'], ['/emergency', 'nav.emergency', '🚨'],
  ['/map', 'nav.gis', '🗺️'], ['/directory', 'nav.departments', '📖'], ['/locator', 'nav.locator', '📍'], ['/documents', 'nav.documents', '📄'], ['/interop', 'nav.interop', '🔗'], ['/settings', 'nav.settings', '⚙️'],
];
export default function More() {
  const { t } = useI18n();
  const { signOut } = useAuth();
  const { colors } = useTheme();
  const router = useRouter();
  return (
    <Screen>
      <H1>👤 {t('nav.account')}</H1>
      {items.map(([href, key, icon]) => (
        <Pressable key={href} accessibilityRole="button" onPress={() => router.push(href as any)} style={{ minHeight: 56 }}>
          <Card><Text style={{ fontSize: 17, color: colors.text }}>{icon}  {t(key)}</Text></Card>
        </Pressable>
      ))}
      <Pressable accessibilityRole="button" onPress={signOut} style={{ minHeight: 56 }}><Card><Text style={{ fontSize: 17, color: colors.bad }}>↩︎  {t('act.sign_out')}</Text></Card></Pressable>
    </Screen>
  );
}
