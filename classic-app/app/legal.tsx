// Ported from legacy-prototype/src/screens/CaseAnalyzerScreen.js (input card + example chips +
// tabbed results). The zip's tabs were prediction/laws/bias/cases/court-guide, driven by a fake
// generative model (predicted_outcome, confidence_score%, court fees - all invented). Our real
// /legal/analyze returns concepts/precedents/bias_and_coverage/full_text_excerpts/confidence
// (never above "medium", and only when grounded in real judgment text) - so the tabs here are
// Assessment/Statutes/Coverage & Bias/Precedents; there is no "court guide" tab because we have no
// real data to back one, and this codebase never fabricates court fees or procedure.
import React, { useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { AppButton, Body, EmptyState, ErrorBanner, Screen } from '../src/components/ui.tsx';
import { VoiceField } from '../src/components/VoiceField.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { LegalAnalysis } from '../src/api/types.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { fontFamily, radius, shadow, spacing, withAlpha } from '../src/theme.ts';
import { useTheme } from '../src/theme/ThemeContext.tsx';

const CASE_EXAMPLES = [
  'Friend issued a cheque which bounced due to insufficient funds',
  'Builder delayed flat possession by 2 years and refusing to pay interest',
  'Landlord refusing to refund security deposit after lease ended',
  'Police station refusing to register a Zero FIR for theft',
  'Employer terminated me without notice and withheld salary and PF',
];
const TABS = ['assessment', 'statutes', 'bias', 'precedents'] as const;
const TAB_LABEL: Record<(typeof TABS)[number], string> = { assessment: 'Assessment', statutes: 'Applicable Statutes', bias: 'Coverage & Bias', precedents: 'Precedents' };
const CONFIDENCE_STYLE: Record<string, { label: string }> = { none: { label: 'No verified match' }, low: { label: 'Low (metadata-only match)' }, medium: { label: 'Medium (grounded in real judgment text)' } };

export default function Legal() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const [text, setText] = useState('');
  const [r, setR] = useState<LegalAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>('assessment');

  async function run(override?: string) {
    const q = override ?? text;
    if (q.trim().length < 5) return;
    setBusy(true); setError(null);
    try { setR(await endpoints.analyzeLegal(q)); } catch (e: any) { setError(e?.message ?? 'Analysis failed.'); } finally { setBusy(false); }
  }
  const confColor = r ? (r.confidence === 'medium' ? colors.accentEmerald : r.confidence === 'low' ? colors.accentAmber : colors.textMuted) : colors.textMuted;

  return (
    <Screen>
      <Text style={{ fontFamily: fontFamily.displayBold, fontSize: 20, color: colors.text }}>⚖️ {t('nav.legal')}</Text>
      <Text style={{ fontSize: 12, marginTop: 3, color: colors.textSoft }}>{t('msg.metadata_only')}</Text>

      <View style={[{ borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, backgroundColor: colors.card, borderColor: colors.border, gap: 8 }, shadow.sm]}>
        <VoiceField label={t('caseInputLabel')} value={text} onChangeText={setText} multiline placeholder={t('caseInputPlaceholder')} />
        <Text style={{ fontSize: 11, fontWeight: '600', color: colors.textMuted }}>Sample dispute scenarios:</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {CASE_EXAMPLES.map((ex) => (
            <Pressable key={ex} accessibilityRole="button" onPress={() => { setText(ex); run(ex); }} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, maxWidth: 260 }}>
              <Text numberOfLines={1} style={{ fontSize: 11, color: colors.textSoft }}>{ex}</Text>
            </Pressable>
          ))}
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <AppButton label={busy ? 'Analyzing…' : t('act.submit')} icon="⚖️" onPress={() => run()} busy={busy} disabled={text.trim().length < 5} />
          <AppButton label="Search Indian Kanoon" kind="secondary" disabled={text.trim().length < 5} onPress={() => Linking.openURL(`https://indiankanoon.org/search/?formInput=${encodeURIComponent(text.trim())}`)} />
        </View>
      </View>

      {error ? <ErrorBanner message={error} /> : null}

      {r ? (
        <View style={{ gap: 10 }}>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {TABS.map((tk) => {
              const selected = tab === tk;
              return (
                <Pressable key={tk} accessibilityRole="button" onPress={() => setTab(tk)} style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: radius.md, borderWidth: 1, backgroundColor: selected ? colors.primary : colors.card, borderColor: selected ? colors.primary : colors.border }}>
                  <Text style={{ fontSize: 11, color: selected ? '#fff' : colors.textSoft, fontWeight: selected ? '700' : '500' }}>{TAB_LABEL[tk]}</Text>
                </Pressable>
              );
            })}
          </View>

          <View style={[{ borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, backgroundColor: colors.card, borderColor: colors.border }, shadow.sm]}>
            {tab === 'assessment' ? (
              <View style={{ gap: 10 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                  <View style={{ width: 56, height: 56, borderRadius: 28, borderWidth: 3, borderColor: confColor, alignItems: 'center', justifyContent: 'center' }}>
                    <Text style={{ fontSize: 11, fontWeight: '800', color: confColor, textAlign: 'center' }}>{r.confidence.toUpperCase()}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: '700', color: colors.text }}>Confidence: {CONFIDENCE_STYLE[r.confidence]?.label ?? r.confidence}</Text>
                    <Body soft>Never inflated - this index holds case metadata only, so confidence cannot honestly exceed "low" unless grounded in real judgment text.</Body>
                  </View>
                </View>
                {r.interpretation ? (
                  <View style={{ borderRadius: radius.md, padding: 12, backgroundColor: colors.surfaceElevated }}>
                    <Text style={{ fontSize: 13, fontWeight: '800', marginBottom: 6, color: colors.text }}>🧠 Model interpretation (from the records above)</Text>
                    <Text style={{ fontSize: 12, lineHeight: 18, color: colors.textSoft }}>{r.interpretation}</Text>
                  </View>
                ) : null}
                {r.warnings.map((w) => <Text key={w} style={{ color: colors.warn, fontSize: 12 }}>⚠ {w}</Text>)}
                <Body soft>{r.disclaimer}</Body>
              </View>
            ) : null}

            {tab === 'statutes' ? (
              r.concepts.length === 0 ? <EmptyState message="No statutes detected for this text." /> : (
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {r.concepts.map((c) => (
                    <View key={c} style={{ backgroundColor: colors.primaryGlow, borderRadius: radius.sm, paddingHorizontal: 10, paddingVertical: 6, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Ionicons name="bookmark" size={13} color={colors.primary} />
                      <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '600' }}>{c}</Text>
                    </View>
                  ))}
                </View>
              )
            ) : null}

            {tab === 'bias' ? (
              r.bias_and_coverage.length === 0 ? <EmptyState message="No coverage/bias notes for this text." /> : (
                <View style={{ gap: 8 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, borderRadius: radius.md, borderWidth: 1, backgroundColor: withAlpha(colors.accentAmber, 0.15), borderColor: colors.accentAmber }}>
                    <Ionicons name="shield-half" size={22} color={colors.accentAmber} />
                    <Text style={{ flex: 1, fontSize: 12, lineHeight: 17, color: colors.text }}>Identified gaps or asymmetries in what this index can verify for your situation.</Text>
                  </View>
                  {r.bias_and_coverage.map((b, i) => (
                    <View key={i} style={{ flexDirection: 'row', gap: 8, alignItems: 'flex-start' }}>
                      <Ionicons name="warning-outline" size={14} color={colors.accentAmber} style={{ marginTop: 2 }} />
                      <Text style={{ flex: 1, fontSize: 12, lineHeight: 18, color: colors.textSoft }}>{b}</Text>
                    </View>
                  ))}
                </View>
              )
            ) : null}

            {tab === 'precedents' ? (
              <View style={{ gap: 10 }}>
                <Text style={{ fontSize: 13, fontWeight: '800', color: colors.text }}>📁 Verified precedents ({r.precedents.length})</Text>
                {r.precedents.length === 0 ? <EmptyState message="No verified precedent matched." /> : r.precedents.map((p) => (
                  <View key={p.cnr} style={{ borderRadius: radius.md, padding: 12, borderWidth: 1, backgroundColor: colors.surfaceElevated, borderColor: colors.border }}>
                    <Text style={{ fontWeight: '800', fontSize: 13, color: colors.text }}>{p.title}</Text>
                    <Text style={{ fontSize: 11, fontWeight: '600', marginTop: 4, color: colors.primaryLight }}>🏛️ {p.court} · {p.decisionDate}</Text>
                    <Body soft>{p.neutralCitation} · {p.disposal ?? 'disposal not recorded'}</Body>
                    {p.bench.length ? <Body soft>Bench: {p.bench.join(', ')}</Body> : null}
                    <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
                      <View style={{ backgroundColor: colors.card, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 }}><Text style={{ fontSize: 10, color: colors.textSoft }}>matched: {p.matchedOn}</Text></View>
                      <View style={{ backgroundColor: colors.card, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 }}><Text style={{ fontSize: 10, color: colors.textSoft }}>score {p.score.toFixed(2)}</Text></View>
                    </View>
                  </View>
                ))}
                {r.full_text_excerpts.length ? (
                  <>
                    <Text style={{ fontSize: 13, fontWeight: '800', color: colors.text, marginTop: 4 }}>Real judgment excerpts ({r.full_text_excerpts.length})</Text>
                    {r.full_text_excerpts.map((e, i) => (
                      <View key={`${e.judgmentId}:${i}`} style={{ borderRadius: radius.md, padding: 12, borderWidth: 1, backgroundColor: colors.surfaceElevated, borderColor: colors.border }}>
                        <Text style={{ fontWeight: '800', fontSize: 13, color: colors.text }}>{e.neutralCitation ?? e.judgmentId}</Text>
                        <Body soft>{e.title ?? 'Untitled judgment'}</Body>
                        <Body soft>{e.court} · {e.decisionDate ?? 'date not recorded'}{e.page ? ` · page ${e.page}` : ''}</Body>
                        <View style={{ backgroundColor: colors.card, borderRadius: radius.sm, padding: 10, marginTop: 6 }}><Body>{e.text}</Body></View>
                        <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 4 }}>match {e.similarity.toFixed(2)} · verbatim from the source PDF</Text>
                      </View>
                    ))}
                  </>
                ) : null}
                <Pressable accessibilityRole="button" onPress={() => Linking.openURL(`https://indiankanoon.org/search/?formInput=${encodeURIComponent(text || r.interpretation || '')}`)}
                  style={{ flexDirection: 'row', alignItems: 'center', padding: 12, borderRadius: radius.md, borderWidth: 1, backgroundColor: colors.primaryGlow, borderColor: colors.primary }}>
                  <Ionicons name="globe-outline" size={16} color={colors.primary} />
                  <View style={{ flex: 1, marginLeft: 8 }}>
                    <Text style={{ fontSize: 13, fontWeight: '700', color: colors.primaryLight }}>Search the full live case-law database</Text>
                    <Text style={{ fontSize: 10.5, marginTop: 2, lineHeight: 14, color: colors.textMuted }}>Opens real, current judgments on Indian Kanoon - not limited to this app's verified corpus</Text>
                  </View>
                  <Ionicons name="open-outline" size={16} color={colors.primary} />
                </Pressable>
              </View>
            ) : null}
          </View>
        </View>
      ) : null}
    </Screen>
  );
}
