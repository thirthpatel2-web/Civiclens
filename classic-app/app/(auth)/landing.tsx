// Pre-login landing/hero page - the entry point at "/", before any sign-in form. Mirrors the
// backend's own NiceGUI landing page (localhost:8080) in spirit: brand, tagline, three real entry
// points, and honest stats pulled straight from this codebase's own constants (not invented to
// match a marketing number) - 7 UI languages (i18n/languages.ts), 8 classification categories
// (app/services/classification_service.py's CATEGORIES, including "other"), and the RTI Act's own
// 30-day statutory response window (app/services/rti_service.py's default RtiRules).
import React from 'react';
import { Pressable, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Body, Screen } from '../../src/components/ui.tsx';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { fontFamily, radius, shadow, spacing, withAlpha } from '../../src/theme.ts';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

const STEPS: Array<{ icon: keyof typeof Ionicons.glyphMap; labelKey: string }> = [
  { icon: 'create-outline', labelKey: 'landing.step_report' },
  { icon: 'sparkles-outline', labelKey: 'landing.step_ai' },
  { icon: 'git-network-outline', labelKey: 'landing.step_routing' },
  { icon: 'checkmark-done-outline', labelKey: 'landing.step_tracked' },
];

export default function Landing() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const router = useRouter();

  return (
    <Screen>
      <View style={{ alignItems: 'center', gap: 10, paddingTop: spacing.lg }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.primaryGlow, borderRadius: radius.full, paddingHorizontal: 14, paddingVertical: 6 }}>
          <Ionicons name="sparkles" size={13} color={colors.primaryLight} />
          <Text style={{ fontSize: 11.5, fontWeight: '700', color: colors.primaryLight }}>{t('landing.badge')}</Text>
        </View>
        <Text accessibilityRole="header" style={{ fontFamily: fontFamily.displayBold, fontSize: 34, color: colors.text, letterSpacing: -0.5, textAlign: 'center' }}>{t('brand')}</Text>
        <Body soft style={{ textAlign: 'center', fontSize: 15 }}>{t('appTagline')}</Body>
      </View>

      <View style={{ gap: 10, marginTop: spacing.md }}>
        <EntryCard icon="person-circle" accent={colors.primary} title={t('landing.citizen')} sub={t('landing.citizen_sub')} onPress={() => router.push('/(auth)/login?portal=citizen' as any)} colors={colors} />
        <EntryCard icon="business" accent={colors.accentSaffron} title={t('landing.official')} sub={t('landing.official_sub')} onPress={() => router.push('/(auth)/login?portal=official' as any)} colors={colors} />
        <EntryCard icon="medkit" accent={colors.bad} title={t('landing.emergency')} sub={t('landing.emergency_sub')} onPress={() => router.push('/emergency' as any)} colors={colors} />
      </View>

      <View style={{ flexDirection: 'row', justifyContent: 'space-around', marginTop: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.lg, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }}>
        <Stat value="7" label={t('landing.stat_languages')} colors={colors} />
        <Stat value="8" label={t('landing.stat_categories')} colors={colors} />
        <Stat value="30" label={t('landing.stat_rti_days')} colors={colors} />
      </View>

      <View style={{ marginTop: spacing.lg, gap: spacing.sm }}>
        <Text style={{ fontSize: 13, fontWeight: '800', textAlign: 'center', color: colors.text }}>{t('landing.how_it_works')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 8 }}>
          {STEPS.map((s, i) => (
            <React.Fragment key={s.labelKey}>
              <View style={{ width: 84, alignItems: 'center', gap: 6 }}>
                <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: colors.primaryGlow, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={s.icon} size={20} color={colors.primaryLight} />
                </View>
                <Text style={{ fontSize: 10.5, fontWeight: '700', textAlign: 'center', color: colors.textSoft }}>{t(s.labelKey)}</Text>
              </View>
              {i < STEPS.length - 1 ? <Ionicons name="arrow-forward" size={14} color={colors.textMuted} style={{ marginTop: 16 }} /> : null}
            </React.Fragment>
          ))}
        </View>
      </View>
    </Screen>
  );
}

function EntryCard({ icon, accent, title, sub, onPress, colors }: { icon: keyof typeof Ionicons.glyphMap; accent: string; title: string; sub: string; onPress: () => void; colors: { card: string; border: string; text: string; textSoft: string } }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress}
      style={[{ flexDirection: 'row', alignItems: 'center', gap: 14, borderRadius: radius.lg, borderWidth: 1.5, borderColor: accent, backgroundColor: colors.card, padding: spacing.md }, shadow.sm]}>
      <View style={{ width: 46, height: 46, borderRadius: 23, backgroundColor: withAlpha(accent, 0.15), alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={icon} size={23} color={accent} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ fontWeight: '800', fontSize: 15, color: colors.text }}>{title}</Text>
        <Text style={{ fontSize: 12, color: colors.textSoft, marginTop: 1 }}>{sub}</Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color={accent} />
    </Pressable>
  );
}

function Stat({ value, label, colors }: { value: string; label: string; colors: { text: string; textMuted: string } }) {
  return (
    <View style={{ alignItems: 'center' }}>
      <Text style={{ fontSize: 22, fontWeight: '900', color: colors.text }}>{value}</Text>
      <Text style={{ fontSize: 10, color: colors.textMuted, textAlign: 'center', maxWidth: 80 }}>{label}</Text>
    </View>
  );
}
