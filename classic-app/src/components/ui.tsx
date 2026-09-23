import React, { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import type { TextInputProps, ViewStyle } from 'react-native';
import { MIN_TOUCH, fontFamily, shadow, spacing, withAlpha } from '../theme.ts';
import type { ThemeColors } from '../theme.ts';
import { useTheme } from '../theme/ThemeContext.tsx';

// Capped-width, centered content column - on a wide desktop browser, an unbounded flex layout
// stretches every card and banner edge-to-edge, which reads as broken rather than "responsive".
// Mobile/native is unaffected: below the cap, width: '100%' just fills the (already narrow) screen.
// 720 read as a cramped, over-centered column on a normal desktop viewport - widened so grids
// (dashboard stats, queue lists) actually use the screen instead of leaving huge side margins.
const CONTENT_MAX_WIDTH = 1080;

export function Screen({ children, scroll = true, style }: { children: React.ReactNode; scroll?: boolean; style?: ViewStyle }) {
  const { colors } = useTheme();
  // scroll=false screens (the map) have content that wants to flex-grow to fill the viewport - that
  // only works if this wrapper itself stretches full height, not just its outer parent. Without
  // `flex: 1` here, a child's own `flex: 1` (e.g. the map) has no sized ancestor to grow into and
  // just falls back to its minHeight, leaving a large empty gap below it.
  const body = <View style={[{ width: '100%', maxWidth: CONTENT_MAX_WIDTH, padding: spacing.lg, gap: spacing.md }, !scroll && { flex: 1 }, style]}>{children}</View>;
  return scroll ? (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }} contentContainerStyle={{ flexGrow: 1, alignItems: 'center' }} keyboardShouldPersistTaps="handled">{body}</ScrollView>
  ) : (
    <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center' }}>{body}</View>
  );
}

export const Card = ({ children, style }: { children: React.ReactNode; style?: ViewStyle }) => {
  const { colors } = useTheme();
  return <View style={[{ backgroundColor: colors.card, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, gap: spacing.sm }, shadow.sm, style]}>{children}</View>;
};

export const H1 = ({ children }: { children: React.ReactNode }) => {
  const { colors } = useTheme();
  return <Text accessibilityRole="header" style={{ fontFamily: fontFamily.displayBold, fontSize: 22, color: colors.text, letterSpacing: -0.3 }}>{children}</Text>;
};

export const Body = ({ children, soft, style, numberOfLines }: { children: React.ReactNode; soft?: boolean; style?: any; numberOfLines?: number }) => {
  const { colors } = useTheme();
  return <Text numberOfLines={numberOfLines} style={[{ fontFamily: fontFamily.body, color: soft ? colors.textSoft : colors.text, fontSize: 15 }, style]}>{children}</Text>;
};

export function AppButton({ label, onPress, kind = 'primary', disabled, busy, icon, color }: { label: string; onPress: () => void; kind?: 'primary' | 'secondary' | 'danger'; disabled?: boolean; busy?: boolean; icon?: string; color?: string }) {
  const { colors } = useTheme();
  const accent = color ?? colors.primary;
  const bg = kind === 'primary' ? accent : kind === 'danger' ? colors.bad : 'transparent';
  const fg = kind === 'secondary' ? accent : '#fff';
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled: !!disabled || !!busy, busy: !!busy }} disabled={disabled || busy} onPress={onPress}
      style={({ pressed }: { pressed: boolean }) => [
        { minHeight: MIN_TOUCH, borderRadius: 10, alignItems: 'center' as const, justifyContent: 'center' as const, paddingHorizontal: spacing.lg },
        { backgroundColor: bg, borderColor: accent, borderWidth: kind === 'secondary' ? 1.5 : 0, opacity: disabled ? 0.5 : pressed ? 0.85 : 1 },
        kind === 'primary' && !disabled ? shadow.sm : null,
        pressed ? { transform: [{ scale: 0.98 }] } : null,
      ]}>
      {busy ? <ActivityIndicator color={fg} /> : <Text style={{ fontFamily: fontFamily.bodySemiBold, color: fg, fontSize: 16 }}>{icon ? `${icon}  ` : ''}{label}</Text>}
    </Pressable>
  );
}

export function Field({ label, error, ...props }: TextInputProps & { label: string; error?: string | null }) {
  const { colors } = useTheme();
  return (
    <View style={{ gap: 4 }}>
      <Text style={{ fontFamily: fontFamily.bodySemiBold, color: colors.textSoft, fontSize: 13 }}>{label}</Text>
      <TextInput
        accessibilityLabel={label} placeholderTextColor={colors.textMuted}
        style={[
          { fontFamily: fontFamily.body, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.card, paddingHorizontal: 12, paddingVertical: 10, fontSize: 16, minHeight: MIN_TOUCH, color: colors.text },
          props.multiline && { minHeight: 110, textAlignVertical: 'top' as const },
          error ? { borderColor: colors.bad } : null,
        ]}
        {...props}
      />
      {error ? <Text style={{ color: colors.bad, fontSize: 13 }}>{error}</Text> : null}
    </View>
  );
}

export const StatusBadge = ({ status }: { status: string }) => {
  const { colors, statusColor } = useTheme();
  return (
    <View style={{ alignSelf: 'flex-start', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3, backgroundColor: statusColor[status] ?? colors.muted }}>
      <Text style={{ color: '#fff', fontSize: 12, fontWeight: '600' }}>{status.replace(/_/g, ' ')}</Text>
    </View>
  );
};

export const ErrorBanner = ({ message, onRetry }: { message: string; onRetry?: () => void }) => {
  const { colors } = useTheme();
  return (
    <View accessibilityRole="alert" style={{ borderWidth: 1, borderRadius: 10, padding: spacing.md, gap: spacing.sm, backgroundColor: withAlpha(colors.bad, colors.mode === 'dark' ? 0.18 : 0.08), borderColor: colors.bad }}>
      <Text style={{ color: colors.bad }}>{message}</Text>
      {onRetry ? <AppButton label="Retry" kind="secondary" onPress={onRetry} /> : null}
    </View>
  );
};

export const InfoBanner = ({ message, tone = 'info' }: { message: string; tone?: 'info' | 'warn' }) => {
  const { colors } = useTheme();
  const accent = tone === 'warn' ? colors.warn : colors.primary;
  return (
    <View style={{ borderWidth: 1, borderRadius: 10, padding: spacing.md, gap: spacing.sm, backgroundColor: withAlpha(accent, colors.mode === 'dark' ? 0.18 : 0.08), borderColor: accent }}>
      <Text style={{ color: colors.text }}>{message}</Text>
    </View>
  );
};

export const EmptyState = ({ message }: { message: string }) => {
  const { colors } = useTheme();
  return <View style={{ alignItems: 'center', padding: spacing.xl }}><Text style={{ color: colors.textSoft, textAlign: 'center' }}>{message}</Text></View>;
};

export const Loading = ({ label }: { label?: string }) => {
  const { colors } = useTheme();
  return <View style={{ alignItems: 'center', padding: spacing.xl, gap: 8 }}><ActivityIndicator color={colors.primary} />{label ? <Text style={{ color: colors.textSoft }}>{label}</Text> : null}</View>;
};

export function Chip({ label, selected, onPress }: { label: string; selected?: boolean; onPress: () => void }) {
  const { colors } = useTheme();
  return (
    <Pressable accessibilityRole="button" accessibilityState={{ selected: !!selected }} onPress={onPress}
      style={{ minHeight: 40, paddingHorizontal: 14, borderRadius: 999, borderWidth: 1, borderColor: selected ? colors.primary : colors.border, justifyContent: 'center', backgroundColor: selected ? colors.primary : colors.card, marginRight: 8, marginBottom: 8 }}>
      <Text style={{ color: selected ? '#fff' : colors.text }}>{label}</Text>
    </Pressable>
  );
}

/** A step wizard's progress bar + "Step X of Y - Title" caption. Shared so every multi-step flow (Report, RTI, ...) looks and feels the same. */
export function StepProgress({ step, total, label }: { step: number; total: number; label: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ gap: 6 }}>
      <View style={{ flexDirection: 'row', gap: 6 }}>
        {Array.from({ length: total }).map((_, i) => <View key={i} style={{ flex: 1, height: 5, borderRadius: 3, backgroundColor: i < step ? colors.primary : colors.border }} />)}
      </View>
      <Text style={{ color: colors.textSoft, fontSize: 12, fontWeight: '600' }}>{label}</Text>
    </View>
  );
}

/** A collapsed-by-default "more options" section, so advanced/optional fields don't crowd the primary flow. */
export function Disclosure({ label, children, defaultOpen }: { label: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <View style={{ gap: 8 }}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded: open }} onPress={() => setOpen((o) => !o)} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 32 }}>
        <Text style={{ color: colors.primary, fontWeight: '700', fontSize: 13 }}>{open ? '▾' : '▸'} {label}</Text>
      </Pressable>
      {open ? children : null}
    </View>
  );
}

export type { ThemeColors };
