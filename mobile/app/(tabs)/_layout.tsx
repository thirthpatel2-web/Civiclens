import React from 'react';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useSync } from '../../src/offline/SyncContext.tsx';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

export default function TabsLayout() {
  const { t } = useI18n();
  const { needsAttention, pending } = useSync();
  const { colors } = useTheme();
  const icon = (name: any) => ({ color, size }: { color: string; size: number }) => <Ionicons name={name} color={color} size={size} />;
  return (
    <Tabs screenOptions={{ tabBarActiveTintColor: colors.primary, tabBarInactiveTintColor: colors.textMuted, tabBarStyle: { backgroundColor: colors.card, borderTopColor: colors.border }, headerStyle: { backgroundColor: colors.primary }, headerTintColor: '#fff' }}>
      <Tabs.Screen name="home" options={{ title: t('nav.dashboard'), tabBarIcon: icon('home') }} />
      <Tabs.Screen name="report" options={{ title: t('nav.report'), tabBarIcon: icon('add-circle') }} />
      <Tabs.Screen name="track" options={{ title: t('nav.grievances'), tabBarIcon: icon('list'), tabBarBadge: pending + needsAttention > 0 ? pending + needsAttention : undefined }} />
      <Tabs.Screen name="copilot" options={{ title: t('nav.copilot'), tabBarIcon: icon('chatbubbles') }} />
      <Tabs.Screen name="more" options={{ title: t('nav.account'), tabBarIcon: icon('menu') }} />
    </Tabs>
  );
}
