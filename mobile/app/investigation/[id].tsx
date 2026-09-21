import React, { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { AppButton, Body, Card, EmptyState, ErrorBanner, Field, H1, InfoBanner, Loading, Screen, StatusBadge } from '../../src/components/ui.tsx';
import { Timeline } from '../../src/components/Timeline.tsx';
import { endpoints } from '../../src/api/instance.ts';
import type { InvestigationReport } from '../../src/api/types.ts';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const { colors } = useTheme();
  return <Card><Text style={{ fontWeight: '600', color: colors.text, marginBottom: 4 }}>{title}</Text>{children}</Card>;
}

export default function InvestigationScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useI18n();
  const { colors } = useTheme();
  const [r, setR] = useState<InvestigationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try { setR(await endpoints.investigationReport(id)); }
    catch (e: any) { setError(e?.message ?? 'Could not load this investigation.'); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  if (error && !r) return <Screen><ErrorBanner message={error} onRetry={load} /></Screen>;
  if (!r) return <Screen><Loading label={t('msg.loading')} /></Screen>;
  const inv = r.investigation;

  return (
    <Screen>
      <H1>Investigation · {inv.subject_type}</H1>
      <StatusBadge status={inv.status} />
      {error ? <ErrorBanner message={error} /> : null}
      <Body soft>Opened {new Date(inv.created_at).toLocaleString()}{inv.closed_at ? ` · closed ${new Date(inv.closed_at).toLocaleString()}` : ''}</Body>

      {r.complaint ? (
        <Section title={`Complaint ${r.complaint.reference}`}>
          <StatusBadge status={r.complaint.status} />
          <Body>{r.complaint.title}</Body>
          <Body soft>{r.complaint.category} · {r.complaint.priority}</Body>
        </Section>
      ) : null}

      {r.anomaly ? (
        <Section title="Anomaly">
          <Text style={{ fontWeight: '600', color: colors.text }}>{r.anomaly.kind} · {r.anomaly.severity}</Text>
          <Body soft>{r.anomaly.explanation}</Body>
        </Section>
      ) : null}

      {r.location ? (
        <Section title={t('lbl.location')}>
          <Body>{r.location.address ?? '—'}{r.location.ward ? ` · Ward ${r.location.ward}` : ''}{r.location.city ? ` · ${r.location.city}` : ''}</Body>
        </Section>
      ) : null}

      {r.timeline ? <Section title="Timeline"><Timeline steps={r.timeline} /></Section> : null}

      {r.duplicates?.length ? (
        <Section title="Duplicates flagged at intake">
          {r.duplicates.map((d) => <Body key={d.complaint_id}>{d.reference} · {d.verdict} ({Math.round(d.score * 100)}%)</Body>)}
        </Section>
      ) : null}

      {(r.nearby_same_category?.length || r.ward_category_cluster?.length) ? (
        <Section title="Related complaints">
          {r.nearby_same_category?.length ? <Body soft>{r.nearby_same_category.length} nearby (same category, within 500m)</Body> : null}
          {r.ward_category_cluster?.length ? <Body soft>{r.ward_category_cluster.length} in the same ward &amp; category</Body> : null}
        </Section>
      ) : null}

      {r.related_complaints?.length ? (
        <Section title="Related complaints in this department">
          {r.related_complaints.slice(0, 10).map((c) => <Body key={c.id}>{c.reference} · {c.status}</Body>)}
        </Section>
      ) : null}

      {r.anomalies?.length ? (
        <Section title="Related anomalies">
          {r.anomalies.map((a) => <Body key={a.id}>{a.kind} · {a.severity} — {a.explanation}</Body>)}
        </Section>
      ) : null}

      {r.rag_findings ? (
        <Section title="Document assistant findings">
          {r.rag_findings.status === 'not_configured' ? <Body soft>Not configured.</Body> : (
            <>
              <Body>{r.rag_findings.answer ?? t('msg.insufficient')}</Body>
              {r.rag_findings.warnings?.map((w) => <InfoBanner key={w} tone="warn" message={w} />)}
            </>
          )}
        </Section>
      ) : null}

      {r.legal_sources ? (
        <Section title="Legal precedents">
          {r.legal_sources.status === 'not_configured' || !r.legal_sources.precedents?.length ? <EmptyState message="No verified precedent matched." /> : r.legal_sources.precedents.map((p) => (
            <Body key={p.neutralCitation}>{p.neutralCitation} — {p.title}</Body>
          ))}
        </Section>
      ) : null}

      {r.audit_trail?.length ? (
        <Section title="Audit trail">
          {r.audit_trail.slice(0, 20).map((e, i) => <Body key={i} soft>{new Date(e.occurred_at).toLocaleString()} · {e.action}</Body>)}
        </Section>
      ) : null}

      <Section title="Notes">
        {inv.notes.length === 0 ? <Body soft>No notes yet.</Body> : inv.notes.map((n, i) => <Body key={i}>{new Date(n.at).toLocaleString()}: {n.text}</Body>)}
        {inv.status === 'open' ? (
          <>
            <Field label="Add a note" value={note} onChangeText={setNote} multiline />
            <AppButton label="Add note" kind="secondary" busy={busy} disabled={!note.trim()} onPress={async () => { setBusy(true); try { await endpoints.addInvestigationNote(id, note); setNote(''); await load(); } catch (e: any) { setError(e?.message); } finally { setBusy(false); } }} />
            <AppButton label="Close investigation" kind="danger" onPress={async () => { setBusy(true); try { await endpoints.closeInvestigation(id); await load(); } catch (e: any) { setError(e?.message); } finally { setBusy(false); } }} />
          </>
        ) : null}
      </Section>
    </Screen>
  );
}
