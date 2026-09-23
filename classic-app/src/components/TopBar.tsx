// Persistent bar above every authenticated screen (wired once in app/_layout.tsx, not per-screen):
// brand mark, language switcher, theme toggle, and a short "how this app works" guide. Answers the
// "where's the theme/language option" gap - previously both were buried three taps deep in Settings.
import React, { useState } from 'react';
import { Modal, Pressable, Text, View } from 'react-native';
import type { ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useSegments } from 'expo-router';
import { useTheme } from '../theme/ThemeContext.tsx';
import type { ThemeColors } from '../theme.ts';
import { useI18n } from '../i18n/I18nContext.tsx';
import { LANGUAGES, UI_LANGUAGES } from '../i18n/languages.ts';
import { radius, shadow } from '../theme.ts';

const overlay: ViewStyle = { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'center', alignItems: 'center', padding: 20 };
// The tab roots have their own bottom/side tab navigation to move between them, so a back arrow
// there would be redundant (and "back" from a tab root is a confusing no-op); everywhere else
// (Settings, detail pages, admin screens, ...) was only reachable by pushing forward, with no way
// back in the UI at all - the browser back button worked, but nothing on-screen told you that.
const TAB_ROOTS = new Set(['(tabs)', '(officer)']);

export function TopBar() {
  const { colors, mode, resolvedMode, setMode } = useTheme();
  const { t, lang, setLang } = useI18n();
  const [langOpen, setLangOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const router = useRouter();
  const segments = useSegments();
  const canGoBack = router.canGoBack() && !(segments.length <= 2 && TAB_ROOTS.has(segments[0] as string));

  const cycleTheme = () => setMode(mode === 'system' ? 'light' : mode === 'light' ? 'dark' : 'system');
  const themeIcon = mode === 'system' ? 'phone-portrait-outline' : resolvedMode === 'dark' ? 'moon' : 'sunny';
  const themeLabel = mode === 'system' ? 'System theme' : resolvedMode === 'dark' ? 'Dark theme' : 'Light theme';

  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16, paddingVertical: 10, backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', width: '100%', maxWidth: 900 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          {canGoBack ? (
            <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => router.back()} style={{ width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center', marginRight: 2 }}>
              <Ionicons name="arrow-back" size={20} color={colors.text} />
            </Pressable>
          ) : null}
          <Ionicons name="shield-checkmark" size={18} color={colors.primary} />
          <Text style={{ fontWeight: '800', color: colors.text, fontSize: 15 }}>{t('brand')}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Pressable accessibilityRole="button" accessibilityLabel="Change language" onPress={() => setLangOpen(true)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, borderWidth: 1, borderColor: colors.border, borderRadius: radius.full, paddingHorizontal: 10, paddingVertical: 6 }}>
            <Ionicons name="language" size={15} color={colors.textSoft} />
            <Text style={{ color: colors.textSoft, fontSize: 12, fontWeight: '700' }}>{LANGUAGES[lang].native}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel={themeLabel} onPress={cycleTheme} style={{ width: 32, height: 32, borderRadius: 16, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name={themeIcon as any} size={16} color={colors.textSoft} />
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Guide" onPress={() => setGuideOpen(true)} style={{ width: 32, height: 32, borderRadius: 16, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="help-circle-outline" size={17} color={colors.textSoft} />
          </Pressable>
        </View>
      </View>

      <Modal visible={langOpen} transparent animationType="fade" onRequestClose={() => setLangOpen(false)}>
        <Pressable style={overlay} onPress={() => setLangOpen(false)}>
          <Pressable style={[{ backgroundColor: colors.card, borderRadius: radius.lg, padding: 16, width: 280, gap: 4 }, shadow.lg]} onPress={(e: any) => e.stopPropagation()}>
            <Text style={{ fontWeight: '800', color: colors.text, fontSize: 15, marginBottom: 6 }}>{t('lbl.language')}</Text>
            {UI_LANGUAGES.map((code) => (
              <Pressable key={code} accessibilityRole="button" onPress={() => { setLang(code); setLangOpen(false); }} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, paddingHorizontal: 10, borderRadius: radius.md, backgroundColor: lang === code ? colors.primaryGlow : 'transparent' }}>
                <Text style={{ color: colors.text, fontSize: 14 }}>{LANGUAGES[code].native} <Text style={{ color: colors.textMuted }}>({LANGUAGES[code].name})</Text></Text>
                {lang === code ? <Ionicons name="checkmark" size={16} color={colors.primary} /> : null}
              </Pressable>
            ))}
          </Pressable>
        </Pressable>
      </Modal>

      <Modal visible={guideOpen} transparent animationType="fade" onRequestClose={() => setGuideOpen(false)}>
        <Pressable style={overlay} onPress={() => setGuideOpen(false)}>
          <Pressable style={[{ backgroundColor: colors.card, borderRadius: radius.lg, padding: 20, width: '100%', maxWidth: 420, gap: 12 }, shadow.lg]} onPress={(e: any) => e.stopPropagation()}>
            <Text style={{ fontWeight: '800', color: colors.text, fontSize: 17 }}>How CivicLens works</Text>
            <GuideRow icon="mic" text="Speak or type your issue on the Dashboard - the Voice Assistant works out which desk it belongs to and takes you there in one tap." colors={colors} />
            <GuideRow icon="add-circle" text="Report an Issue for civic complaints - potholes, water, power, sanitation. AI suggests the category and department as you type." colors={colors} />
            <GuideRow icon="business" text="RTI Drafter generates a statutory Right to Information application in minutes, with the right records already suggested." colors={colors} />
            <GuideRow icon="scale" text="Legal Analyzer finds real precedents and applicable statutes for your situation." colors={colors} />
            <GuideRow icon="list" text="My Grievances tracks every complaint's status, timeline and officer remarks." colors={colors} />
            <Pressable accessibilityRole="button" onPress={() => setGuideOpen(false)} style={{ alignSelf: 'flex-end', marginTop: 4 }}>
              <Text style={{ color: colors.primary, fontWeight: '700' }}>Got it</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

function GuideRow({ icon, text, colors }: { icon: keyof typeof Ionicons.glyphMap; text: string; colors: ThemeColors }) {
  return (
    <View style={{ flexDirection: 'row', gap: 10, alignItems: 'flex-start' }}>
      <Ionicons name={icon} size={16} color={colors.primary} style={{ marginTop: 2 }} />
      <Text style={{ color: colors.textSoft, fontSize: 13, flex: 1, lineHeight: 18 }}>{text}</Text>
    </View>
  );
}
