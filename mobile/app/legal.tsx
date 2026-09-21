import React, { useState } from 'react';
import { Linking, Text, View } from 'react-native';
import { AppButton, Body, Card, EmptyState, ErrorBanner, Field, H1, InfoBanner, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { LegalAnalysis } from '../src/api/types.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { radius, withAlpha } from '../src/theme.ts';
import { useTheme } from '../src/theme/ThemeContext.tsx';

export default function Legal() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const [text, setText] = useState('');
  const [r, setR] = useState<LegalAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run() { setBusy(true); setError(null); try { setR(await endpoints.analyzeLegal(text)); } catch (e: any) { setError(e?.message ?? 'Analysis failed.'); } finally { setBusy(false); } }
  // The verified precedent index holds case METADATA only; when real judgment text is also
  // retrieved and the model's answer actually cites it, confidence honestly rises to "medium" -
  // never higher, since this is still a small, growing corpus. See app/legal/analysis.py.
  const CONFIDENCE_STYLE: Record<string, { label: string; color: string }> = {
    none: { label: 'No verified match', color: colors.textMuted },
    low: { label: 'Low (metadata-only match)', color: colors.warn },
    medium: { label: 'Medium (grounded in real judgment text)', color: colors.ok },
  };
  const conf = r ? CONFIDENCE_STYLE[r.confidence] ?? { label: r.confidence, color: colors.textMuted } : null;

  return (
    <Screen>
      <H1>{t('nav.legal')}</H1>
      <InfoBanner tone="warn" message={t('msg.metadata_only')} />
      <Field label={t('caseInputLabel')} value={text} onChangeText={setText} multiline placeholder={t('caseInputPlaceholder')} />
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <AppButton label={t('act.submit')} onPress={run} busy={busy} disabled={text.trim().length < 5} />
        <AppButton
          label="Search Indian Kanoon" kind="secondary" disabled={text.trim().length < 5}
          onPress={() => Linking.openURL(`https://indiankanoon.org/search/?formInput=${encodeURIComponent(text.trim())}`)}
        />
      </View>
      {error ? <ErrorBanner message={error} /> : null}

      {r ? (
        <>
          <Card style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <View style={{ width: 56, height: 56, borderRadius: 28, borderWidth: 3, borderColor: conf!.color, alignItems: 'center', justifyContent: 'center' }}>
              <Text style={{ fontSize: 11, fontWeight: '800', color: conf!.color, textAlign: 'center' }}>{r.confidence.toUpperCase()}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '700', color: colors.text }}>Confidence: {conf!.label}</Text>
              <Body soft>Never inflated - this index holds case metadata only, so confidence cannot honestly exceed "low".</Body>
            </View>
          </Card>

          {r.concepts.length ? (
            <Card>
              <Text style={{ fontWeight: '700', color: colors.text }}>📜 Applicable statutes (keyword-detected)</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {r.concepts.map((c) => (
                  <View key={c} style={{ backgroundColor: colors.primaryGlow, borderRadius: radius.sm, paddingHorizontal: 10, paddingVertical: 6 }}>
                    <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '600' }}>{c}</Text>
                  </View>
                ))}
              </View>
            </Card>
          ) : null}

          {r.bias_and_coverage.length ? (
            <View style={{ backgroundColor: withAlpha(colors.warn, 0.12), borderRadius: radius.md, borderWidth: 1, borderColor: colors.warn, padding: 12, gap: 4 }}>
              <Text style={{ fontWeight: '800', color: colors.warn }}>⚠ Coverage & bias</Text>
              {r.bias_and_coverage.map((b, i) => <Body key={i} soft>{b}</Body>)}
            </View>
          ) : null}

          <Text style={{ fontWeight: '700', color: colors.text }}>Verified precedents ({r.precedents.length})</Text>
          {r.precedents.length === 0 ? <EmptyState message="No verified precedent matched." /> : r.precedents.map((p) => (
            <Card key={p.cnr}>
              <Text style={{ fontWeight: '700', color: colors.text }}>{p.neutralCitation}</Text>
              <Body>{p.title}</Body>
              <Body soft>{p.court} · {p.decisionDate} · {p.disposal ?? 'disposal not recorded'}</Body>
              {p.bench.length ? <Body soft>Bench: {p.bench.join(', ')}</Body> : null}
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 2 }}>
                <View style={{ backgroundColor: colors.surfaceElevated, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 }}>
                  <Text style={{ fontSize: 10, color: colors.textSoft }}>matched: {p.matchedOn}</Text>
                </View>
                <View style={{ backgroundColor: colors.surfaceElevated, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 }}>
                  <Text style={{ fontSize: 10, color: colors.textSoft }}>score {p.score.toFixed(2)}</Text>
                </View>
              </View>
            </Card>
          ))}

          {r.full_text_excerpts.length ? (
            <>
              <Text style={{ fontWeight: '700', color: colors.text }}>Real judgment excerpts ({r.full_text_excerpts.length})</Text>
              {r.full_text_excerpts.map((e, i) => (
                <Card key={`${e.judgmentId}:${i}`}>
                  <Text style={{ fontWeight: '700', color: colors.text }}>{e.neutralCitation ?? e.judgmentId}</Text>
                  <Body>{e.title ?? 'Untitled judgment'}</Body>
                  <Body soft>{e.court} · {e.decisionDate ?? 'date not recorded'}{e.page ? ` · page ${e.page}` : ''}</Body>
                  <View style={{ backgroundColor: colors.surfaceElevated, borderRadius: radius.sm, padding: 10, marginTop: 4 }}>
                    <Body>{e.text}</Body>
                  </View>
                  <View style={{ backgroundColor: colors.surfaceElevated, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3, alignSelf: 'flex-start', marginTop: 4 }}>
                    <Text style={{ fontSize: 10, color: colors.textSoft }}>match {e.similarity.toFixed(2)} · verbatim from the source PDF</Text>
                  </View>
                </Card>
              ))}
            </>
          ) : null}

          {r.interpretation ? <Card><Body soft>Model interpretation (from the records above)</Body><Body>{r.interpretation}</Body></Card> : null}
          {r.warnings.map((w) => <InfoBanner key={w} tone="warn" message={w} />)}
          <Body soft>{r.disclaimer}</Body>
        </>
      ) : null}
    </Screen>
  );
}
