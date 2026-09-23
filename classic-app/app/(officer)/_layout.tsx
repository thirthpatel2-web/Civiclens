import React from 'react';
import type { ColorValue } from 'react-native';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

export default function OfficerTabsLayout() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const icon = (name: any) => ({ color, size }: { focused: boolean; color: ColorValue; size: number }) => <Ionicons name={name} color={color as string} size={size} />;
  return (
    <Tabs screenOptions={{ headerShown: false, tabBarActiveTintColor: colors.primary, tabBarInactiveTintColor: colors.textMuted, tabBarStyle: { backgroundColor: colors.card, borderTopColor: colors.border } }}>
      <Tabs.Screen name="dashboard" options={{ title: t('nav.dashboard'), tabBarIcon: icon('stats-chart') }} />
      <Tabs.Screen name="queue" options={{ title: t('nav.officer_queue'), tabBarIcon: icon('list') }} />
      <Tabs.Screen name="investigations" options={{ title: t('nav.investigations'), tabBarIcon: icon('search') }} />
      <Tabs.Screen name="more" options={{ title: t('nav.account'), tabBarIcon: icon('menu') }} />
    </Tabs>
  );
}
