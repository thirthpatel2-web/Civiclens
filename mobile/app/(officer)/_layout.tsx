import React from 'react';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

export default function OfficerTabsLayout() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const icon = (name: any) => ({ color, size }: { color: string; size: number }) => <Ionicons name={name} color={color} size={size} />;
  return (
    <Tabs screenOptions={{ tabBarActiveTintColor: colors.primary, tabBarInactiveTintColor: colors.textMuted, tabBarStyle: { backgroundColor: colors.card, borderTopColor: colors.border }, headerStyle: { backgroundColor: colors.primary }, headerTintColor: '#fff' }}>
      <Tabs.Screen name="dashboard" options={{ title: t('nav.dashboard'), tabBarIcon: icon('stats-chart') }} />
      <Tabs.Screen name="queue" options={{ title: t('nav.officer_queue'), tabBarIcon: icon('list') }} />
      <Tabs.Screen name="investigations" options={{ title: t('nav.investigations'), tabBarIcon: icon('search') }} />
      <Tabs.Screen name="more" options={{ title: t('nav.account'), tabBarIcon: icon('menu') }} />
    </Tabs>
  );
}
