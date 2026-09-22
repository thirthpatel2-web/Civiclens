import React, { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { AppButton, Body, Card, ErrorBanner, Field, H1, InfoBanner, Loading, Screen, StatusBadge } from '../../src/components/ui.tsx';
import { Timeline } from '../../src/components/Timeline.tsx';
import { endpoints } from '../../src/api/instance.ts';
import type { ComplaintDetail, GovernmentSubmissionState } from '../../src/api/types.ts';
import { LANGUAGES } from '../../src/i18n/languages.ts';
import type { LanguageCode } from '../../src/i18n/languages.ts';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

export default function ComplaintScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useI18n();
  const { colors } = useTheme();
  const [d, setD] = useState<ComplaintDetail | null>(null);
  const [gov, setGov] = useState<GovernmentSubmissionState[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const load = useCallback(async () => { setError(null); try { setD(await endpoints.complaintDetail(id)); } catch (e: any) { setError(e?.message ?? 'Could not load the complaint.'); } }, [id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { endpoints.governmentStates(id).then((r) => setGov(r.items)).catch(() => setGov([])); }, [id]);
  if (error) return <Screen><ErrorBanner message={error} onRetry={load} /></Screen>;
  if (!d) return <Screen><Loading label={t('msg.loading')} /></Screen>;
  const c = d.complaint;
  const langName = LANGUAGES[(c.original_language as LanguageCode)]?.native ?? c.original_language;
  return (
    <Screen>
      <H1>📄 {c.reference}</H1>
      <StatusBadge status={c.status} />
      <Card>
        <Body soft>{t('lbl.description')} · {langName}{c.input_method === 'voice' ? ' · 🎤' : ''}</Body>
        <Body>{c.original_text}</Body>
        {c.translated_text ? (<View><Body soft>Translation (machine-generated, for officials; your original above is kept)</Body><Body>{c.translated_text}</Body></View>) : null}
      </Card>
      <Card>
        <Body>{t('lbl.department')}: {c.department_code ?? '—'}   {t('lbl.priority')}: {c.priority}</Body>
        {c.sla_due_at ? <Body soft>{t('lbl.due')}: {new Date(c.sla_due_at).toLocaleString()}</Body> : null}
        {c.escalation_level ? <InfoBanner tone="warn" message={`Escalated to level ${c.escalation_level}`} /> : null}
        {c.duplicates.length ? <InfoBanner message={`Similar complaints exist: ${c.duplicates.map((x) => x.reference).join(', ')}`} /> : null}
      </Card>
      <Card><Timeline steps={d.timeline} /></Card>
      {d.events.length ? <Card>{d.events.filter((e) => e.remarks).map((e) => <Text key={e.id} style={{ color: colors.text }}><Text style={{ fontWeight: '600' }}>{e.actor_label ?? 'System'}: </Text>{e.remarks}</Text>)}</Card> : null}
      <Card>{d.evidence.length ? d.evidence.map((e) => <Body key={e.id}>{e.name} · {e.analysis_status}</Body>) : <Body soft>No evidence attached.</Body>}</Card>
      <Card>
        <Body soft>Government platforms</Body>
        {gov === null ? null : gov.length === 0 ? <Body soft>{t('msg.no_data')}</Body> : gov.map((g) => (
          <View key={g.platform} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 4 }}>
            <View style={{ flex: 1 }}><Text style={{ fontWeight: '600', color: colors.text }}>{g.display_name}</Text><Body soft>{g.state}{g.external_reference ? ` · ${g.external_reference}` : ''}{g.last_error ? ` · ${g.last_error}` : ''}</Body></View>
            <AppButton label="Share" kind="secondary" disabled={!g.configured || !g.consent_granted || ['submitted', 'queued', 'submitting'].includes(g.state)}
              onPress={async () => { try { await endpoints.requestGovernmentSubmission(c.id, g.platform); const r = await endpoints.governmentStates(c.id); setGov(r.items); } catch (e: any) { setError(e?.message ?? 'Could not share this complaint.'); } }} />
          </View>
        ))}
        {gov && gov.some((g) => !g.consent_granted) ? <InfoBanner tone="warn" message="Grant government-sharing consent in Settings to share complaints with these platforms." /> : null}
      </Card>
      {['resolved', 'closed'].includes(c.status) && !d.feedback ? (
        <Card>
          <Body>{t('lbl.rating')}: {rating}/5</Body>
          <View style={{ flexDirection: 'row', gap: 8 }}>{[1, 2, 3, 4, 5].map((n) => <AppButton key={n} label={String(n)} kind={n === rating ? 'primary' : 'secondary'} onPress={() => setRating(n)} />)}</View>
          <Field label={t('lbl.comment')} value={comment} onChangeText={setComment} multiline />
          <AppButton label={t('act.submit')} onPress={async () => { try { await endpoints.feedback(c.id, rating, comment || null); await load(); } catch (e: any) { setError(e?.message ?? 'Could not send feedback.'); } }} />
        </Card>
      ) : d.feedback ? <Body soft>Your rating: {d.feedback.rating}/5</Body> : null}
    </Screen>
  );
}
