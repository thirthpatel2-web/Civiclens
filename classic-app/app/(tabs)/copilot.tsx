// Ported from legacy-prototype/src/screens/ChatbotScreen.js (avatar header, online-status dot,
// quick topic chips, message bubbles, docked input bar with voice mic) - the reply is the real
// RAG-grounded /assistant/ask (citations from actual ingested documents), not the zip's static
// rule-based reply generator.
import React, { useRef, useState } from 'react';
import { ScrollView, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Pressable } from 'react-native';
import { AppButton, Body, H1, Screen } from '../../src/components/ui.tsx';
import { VoiceField } from '../../src/components/VoiceField.tsx';
import { endpoints } from '../../src/api/instance.ts';
import type { AskResponse } from '../../src/api/types.ts';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { ApiError, NetworkError } from '../../src/api/errors.ts';
import { useTheme } from '../../src/theme/ThemeContext.tsx';
import { fontFamily, radius, shadow, spacing } from '../../src/theme.ts';

interface Turn { q: string; a?: AskResponse; error?: string }
const QUICK_TOPICS = ['What documents do I need for RTI?', 'How long until my complaint is resolved?', 'What is the 48-hour emergency RTI clause?', 'How do I escalate a delayed complaint?'];

export default function Copilot() {
  const { t, lang } = useI18n();
  const { colors } = useTheme();
  const [text, setText] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conv, setConv] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<any>(null);

  async function ask(q: string) {
    if (!q.trim()) return;
    setBusy(true); setText('');
    const idx = turns.length;
    setTurns((x) => [...x, { q }]);
    try {
      const a = await endpoints.ask(q, lang, conv);
      setConv(a.conversation_id);
      setTurns((x) => x.map((tn, i) => (i === idx ? { ...tn, a } : tn)));
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof NetworkError ? 'No connection. Try again when you are online.' : 'Something went wrong.';
      setTurns((x) => x.map((tn, i) => (i === idx ? { ...tn, error: msg } : tn)));
    } finally { setBusy(false); setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100); }
  }

  return (
    <Screen scroll={false} style={{ flex: 1 }}>
      <View style={[{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border }]}>
        <View style={[{ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary }, shadow.md]}>
          <Ionicons name="sparkles" size={18} color="#fff" />
        </View>
        <View>
          <Text style={{ fontFamily: fontFamily.bodyExtraBold, fontSize: 14, color: colors.text }}>{t('chatbotTitle')}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 }}>
            <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.accentEmerald }} />
            <Text style={{ fontSize: 10, color: colors.accentEmerald, fontWeight: '600' }}>RAG-grounded · cites your real documents</Text>
          </View>
        </View>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0, paddingVertical: 6 }} contentContainerStyle={{ gap: 8 }}>
        {QUICK_TOPICS.map((topic) => (
          <Pressable key={topic} accessibilityRole="button" onPress={() => ask(topic)} style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.full, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ fontSize: 11, color: colors.textSoft }}>{topic}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView ref={scrollRef} style={{ flex: 1 }} contentContainerStyle={{ gap: 12, paddingVertical: 10 }} keyboardShouldPersistTaps="handled">
        {turns.length === 0 ? <Body soft>{t('page.copilot_help')}</Body> : null}
        {turns.map((tn, i) => (
          <View key={i} style={{ gap: 8 }}>
            <View style={{ alignSelf: 'flex-end', maxWidth: '85%' }}>
              <View style={[{ borderRadius: radius.lg, padding: 12, borderWidth: 1, backgroundColor: colors.primary, borderColor: colors.primary }, shadow.sm]}>
                <Text style={{ fontSize: 13, lineHeight: 19, color: '#fff' }}>{tn.q}</Text>
              </View>
            </View>
            {tn.error ? <View style={{ alignSelf: 'flex-start', maxWidth: '85%' }}><Text style={{ color: colors.bad, fontSize: 12 }}>{tn.error}</Text><Pressable onPress={() => ask(tn.q)}><Text style={{ color: colors.primary, fontWeight: '700', fontSize: 12 }}>Retry</Text></Pressable></View> : null}
            {tn.a ? (
              <View style={{ flexDirection: 'row', gap: 8, maxWidth: '85%', alignSelf: 'flex-start' }}>
                <View style={{ width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', marginTop: 4, backgroundColor: colors.primaryGlow }}>
                  <Ionicons name="shield-checkmark" size={14} color={colors.primary} />
                </View>
                <View style={[{ borderRadius: radius.lg, padding: 12, borderWidth: 1, flex: 1, backgroundColor: colors.card, borderColor: colors.border }, shadow.sm]}>
                  <Text style={{ fontSize: 13, lineHeight: 19, color: colors.text }}>{tn.a.answer ?? (tn.a.status === 'model_unavailable' ? 'The language model is unavailable; the sources below were found.' : t('msg.insufficient'))}</Text>
                  {tn.a.citations.map((c) => <Text key={c.marker} style={{ fontSize: 11, color: colors.textMuted, marginTop: 6 }}>[{c.marker}] {c.documentName}{c.page ? ` p.${c.page}` : ''}: {c.excerpt.slice(0, 100)}…</Text>)}
                  {tn.a.warnings.map((w) => <Text key={w} style={{ fontSize: 11, color: colors.warn, marginTop: 4 }}>⚠ {w}</Text>)}
                </View>
              </View>
            ) : !tn.error ? <Body soft>…</Body> : null}
          </View>
        ))}
      </ScrollView>

      <VoiceField label="" value={text} onChangeText={setText} placeholder={t('chatbotPlaceholder')} multiline />
      <AppButton label={t('act.submit')} onPress={() => ask(text)} busy={busy} disabled={!text.trim()} />
    </Screen>
  );
}
