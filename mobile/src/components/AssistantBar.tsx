// The voice/text triage assistant, embedded at the top of the home dashboard: type or speak an
// issue in any language and get told which screen it belongs to (and, for a civic complaint, which
// department) - one tap and you're there. Backed by /api/v1/assistant/route, which is IntentRouter
// + the same rules-only classifier real intake uses; nothing here is invented, and an uncertain
// match shows the alternatives instead of silently guessing.
import React, { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { radius, shadow, withAlpha } from '../theme.ts';
import { useTheme } from '../theme/ThemeContext.tsx';
import { useI18n } from '../i18n/I18nContext.tsx';
import { useVoiceInput } from '../hooks/useVoiceInput.ts';
import { isOnline } from '../offline/SyncContext.tsx';
import { endpoints } from '../api/instance.ts';
import { ApiError } from '../api/errors.ts';
import type { AssistantDestination, AssistantRouteResult } from '../api/types.ts';

const DEST: Record<AssistantDestination, { icon: keyof typeof Ionicons.glyphMap; labelKey: string; href: string }> = {
  complaint: { icon: 'add-circle', labelKey: 'nav.report', href: '/(tabs)/report' },
  rti: { icon: 'business', labelKey: 'nav.rti', href: '/rti' },
  legal: { icon: 'scale', labelKey: 'nav.legal', href: '/legal' },
  track: { icon: 'list', labelKey: 'nav.grievances', href: '/(tabs)/track' },
  document: { icon: 'scan', labelKey: 'nav.documents', href: '/documents' },
  map: { icon: 'map', labelKey: 'nav.gis', href: '/map' },
  locator: { icon: 'navigate', labelKey: 'nav.locator', href: '/locator' },
  emergency: { icon: 'medkit', labelKey: 'nav.emergency', href: '/emergency' },
};

const SEVERITY_COLOR: Record<string, string> = { low: '#79735A', medium: '#28728A', high: '#9C7025', critical: '#B23A3A' };

export function AssistantBar() {
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const [text, setText] = useState('');
  const [result, setResult] = useState<AssistantRouteResult | null>(null);
  const [routing, setRouting] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);
  const v = useVoiceInput('auto', isOnline);

  const doRoute = useCallback(async (spoken: string) => {
    const query = spoken.trim();
    if (!query) return;
    setRouting(true);
    setRouteError(null);
    try {
      setResult(await endpoints.assistantRoute(query));
    } catch (e) {
      setResult(null);
      setRouteError(e instanceof ApiError ? e.message : 'Could not reach the assistant. Check your connection.');
    } finally {
      setRouting(false);
    }
  }, []);

  // A finished voice recording fills the box and routes immediately - the citizen already reviewed
  // it by speaking; they can still edit and re-submit if the transcript needs a correction.
  const s = v.state;
  const lastReviewedUri = useMemo(() => (s.kind === 'review' ? s.audioUri : null), [s]);
  const [handledUri, setHandledUri] = useState<string | null>(null);
  if (s.kind === 'review' && lastReviewedUri !== handledUri) {
    setHandledUri(lastReviewedUri);
    if (s.text !== text) setText(s.text);
    doRoute(s.text);
  }

  const dest = result ? DEST[result.destination] : null;
  const cls = result?.classification;

  return (
    <View style={[{ backgroundColor: colors.card, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 16, gap: 10 }, shadow.md]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <View style={{ width: 30, height: 30, borderRadius: 15, backgroundColor: withAlpha(colors.accentPurple, 0.15), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="sparkles" size={16} color={colors.accentPurple} />
        </View>
        <Text style={{ fontWeight: '800', color: colors.text, fontSize: 15, flex: 1 }}>{t('nav.assistant')}</Text>
      </View>
      <Text style={{ color: colors.textSoft, fontSize: 12.5, lineHeight: 17 }}>{t('page.assistant_help')}</Text>

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.surfaceElevated, borderRadius: radius.full, borderWidth: 1, borderColor: colors.border, paddingLeft: 16, paddingRight: 6, paddingVertical: 6 }}>
        <TextInput
          value={text}
          onChangeText={setText}
          placeholder={t('assistant.placeholder')}
          placeholderTextColor={colors.textMuted}
          style={{ flex: 1, color: colors.text, fontSize: 15, paddingVertical: 6 }}
          onSubmitEditing={() => doRoute(text)}
          returnKeyType="send"
          editable={s.kind !== 'recording' && s.kind !== 'transcribing'}
        />
        {text.trim().length > 0 ? (
          <Pressable accessibilityRole="button" accessibilityLabel={t('act.submit')} onPress={() => doRoute(text)} style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' }}>
            {routing ? <ActivityIndicator color="#fff" size="small" /> : <Ionicons name="arrow-forward" size={18} color="#fff" />}
          </Pressable>
        ) : (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={s.kind === 'recording' ? t('assistant.listening') : t('assistant.mic_tip')}
            onPress={s.kind === 'recording' ? v.stop : v.start}
            style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: s.kind === 'recording' ? colors.bad : colors.accentPurple, alignItems: 'center', justifyContent: 'center' }}
          >
            {s.kind === 'requesting_permission' || s.kind === 'transcribing' ? <ActivityIndicator color="#fff" size="small" /> : <Ionicons name={s.kind === 'recording' ? 'stop' : 'mic'} size={17} color="#fff" />}
          </Pressable>
        )}
      </View>

      {s.kind === 'recording' ? <Text style={{ color: colors.bad, fontSize: 12.5 }}>● {t('assistant.listening')}</Text> : null}
      {s.kind === 'error' ? <Text style={{ color: colors.bad, fontSize: 12.5 }}>{s.permissionDenied ? t('assistant.mic_denied') : s.notConfigured ? t('assistant.mic_off') : t('assistant.mic_failed')}</Text> : null}
      {routeError ? <Text style={{ color: colors.bad, fontSize: 12.5 }}>{routeError}</Text> : null}

      {result && dest ? (
        <View style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 10, gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: withAlpha(colors.primary, 0.12), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={dest.icon} size={17} color={colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>{t('assistant.goes_to')}</Text>
              <Text style={{ color: colors.text, fontWeight: '700', fontSize: 14 }}>{t(dest.labelKey)}</Text>
            </View>
            <Pressable accessibilityRole="button" onPress={() => router.push(dest.href as any)} style={{ backgroundColor: colors.primary, borderRadius: radius.full, paddingHorizontal: 14, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <Text style={{ color: '#fff', fontWeight: '700', fontSize: 12.5 }}>{t('assistant.take_me')}</Text>
              <Ionicons name="arrow-forward" size={13} color="#fff" />
            </Pressable>
          </View>

          {cls ? (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
              <Tag label={`${t('lbl.category')}: ${cls.category === 'other' ? t('assistant.unsure') : cls.category}`} colors={colors} />
              <Tag label={`${t('lbl.severity')}: ${cls.severity}`} tint={SEVERITY_COLOR[cls.severity]} colors={colors} />
              {cls.department_name ? <Tag label={cls.department_name} colors={colors} /> : null}
              <Tag label={cls.source === 'rules' ? t('assistant.decided_by_rules') : t('assistant.decided_by_ai')} colors={colors} />
            </View>
          ) : null}

          {!result.certain && result.alternatives.length > 0 ? (
            <View style={{ gap: 6 }}>
              <Text style={{ color: colors.textSoft, fontSize: 12 }}>{t('assistant.not_right')}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                {result.alternatives.map((d) => (
                  <Pressable key={d} accessibilityRole="button" onPress={() => router.push(DEST[d].href as any)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, borderWidth: 1, borderColor: colors.border, borderRadius: radius.full, paddingHorizontal: 10, paddingVertical: 5 }}>
                    <Ionicons name={DEST[d].icon} size={12} color={colors.textSoft} />
                    <Text style={{ color: colors.textSoft, fontSize: 12 }}>{t(DEST[d].labelKey)}</Text>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

function Tag({ label, tint, colors }: { label: string; tint?: string; colors: { border: string; textSoft: string } }) {
  const c = tint ?? colors.textSoft;
  return (
    <View style={{ backgroundColor: withAlpha(c, 0.12), borderRadius: radius.full, paddingHorizontal: 9, paddingVertical: 4 }}>
      <Text style={{ color: c, fontSize: 11, fontWeight: '600' }}>{label}</Text>
    </View>
  );
}
