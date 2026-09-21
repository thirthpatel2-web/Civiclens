import React from 'react';
import { Text, View } from 'react-native';
import type { TimelineStep } from '../api/types.ts';
import { useTheme } from '../theme/ThemeContext.tsx';

export function Timeline({ steps }: { steps: TimelineStep[] }) {
  const { colors } = useTheme();
  const tone = { done: colors.ok, current: colors.primary, upcoming: colors.borderLight, skipped: colors.borderLight, rejected: colors.bad } as const;
  return (
    <View accessibilityLabel="Complaint timeline">
      {steps.map((st, i) => (
        <View key={st.label} style={{ flexDirection: 'row', gap: 12, minHeight: 44 }}>
          <View style={{ alignItems: 'center' }}>
            <View style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: tone[st.state], borderWidth: st.state === 'current' ? 3 : 0, borderColor: colors.primaryGlow }} />
            {i < steps.length - 1 ? <View style={{ width: 2, flex: 1, backgroundColor: colors.border }} /> : null}
          </View>
          <View style={{ flex: 1, paddingBottom: 10 }}>
            <Text style={{ fontWeight: st.state === 'current' ? '700' : '500', color: st.state === 'upcoming' ? colors.textSoft : colors.text }}>{st.label}</Text>
            <Text style={{ color: colors.textSoft, fontSize: 12 }}>{st.at ? new Date(st.at).toLocaleString() : st.state}</Text>
          </View>
        </View>
      ))}
    </View>
  );
}
