import React, { useCallback, useEffect, useState } from 'react';
import { Linking, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { AppButton, Body, Card, Chip, ErrorBanner, Field, H1, Loading, Screen, StatusBadge } from '../../src/components/ui.tsx';
import { Timeline } from '../../src/components/Timeline.tsx';
import { endpoints } from '../../src/api/instance.ts';
import type { DuplicateCandidate, GovernmentSubmissionState, OfficerComplaintDetail } from '../../src/api/types.ts';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

// Same civic-category taxonomy the web officer console uses (app.services.classification_service.CATEGORIES) - a fixed enum, not deployment data.
const CATEGORIES = ['roads', 'water', 'electricity', 'sanitation', 'drainage', 'encroachment', 'police', 'other'];
// Mirrors app.services.complaint_status.TRANSITIONS exactly - the backend rejects anything not listed here.
const NEXT_STATUS: Record<string, string[]> = {
  submitted: ['ai_routed', 'rejected'], ai_routed: ['assigned', 'rejected'], assigned: ['under_review', 'ai_routed', 'rejected'],
  under_review: ['inspection_scheduled', 'in_progress', 'resolved', 'rejected', 'assigned'], inspection_scheduled: ['under_review', 'in_progress', 'resolved'],
  in_progress: ['under_review', 'inspection_scheduled', 'resolved'], resolved: ['closed', 'in_progress'], closed: [], rejected: [],
};
// app.services.complaint_status.REMARK_REQUIRED: these two transitions are rejected by the backend without remarks.
const REMARK_REQUIRED = new Set(['resolved', 'rejected']);

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const { colors } = useTheme();
  return <Card><Text style={{ fontWeight: '600', color: colors.text, marginBottom: 4 }}>{title}</Text>{children}</Card>;
}

export default function OfficerComplaintScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useI18n();
  const { colors } = useTheme();
  const router = useRouter();
  const [d, setD] = useState<OfficerComplaintDetail | null>(null);
  const [dup, setDup] = useState<DuplicateCandidate[] | null>(null);
  const [gov, setGov] = useState<GovernmentSubmissionState[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [remarks, setRemarks] = useState('');
  const [category, setCategory] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const detail = await endpoints.officerComplaintDetail(id);
      setD(detail); setCategory(detail.complaint.category);
      const [d1, d2] = await Promise.allSettled([endpoints.duplicateCandidates(id), endpoints.officerGovernmentStates(id)]);
      setDup(d1.status === 'fulfilled' ? d1.value.items : []);
      setGov(d2.status === 'fulfilled' ? d2.value.items : []);
    } catch (e: any) { setError(e?.message ?? 'Could not load this complaint.'); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label); setError(null);
    try { await fn(); await load(); } catch (e: any) { setError(e?.message ?? `Could not ${label}.`); } finally { setBusy(null); }
  };

  if (error && !d) return <Screen><ErrorBanner message={error} onRetry={load} /></Screen>;
  if (!d) return <Screen><Loading label={t('msg.loading')} /></Screen>;
  const c = d.complaint;
  const nextStatuses = NEXT_STATUS[c.status] ?? [];

  return (
    <Screen>
      <H1>📄 {c.reference}</H1>
      <StatusBadge status={c.status} />
      {error ? <ErrorBanner message={error} /> : null}

      <Section title={t('lbl.description')}>
        <Body>{c.original_text}</Body>
        {c.translated_text ? <Body soft>Translation: {c.translated_text}</Body> : null}
        <Body soft>{c.category} · {c.priority} · {c.severity}{c.ward ? ` · Ward ${c.ward}` : ''}</Body>
        {c.lat != null && c.lng != null ? <Text style={{ color: colors.primary }} onPress={() => Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${c.lat},${c.lng}`)}>📍 Open in Maps</Text> : null}
        {c.priority_factors?.length ? <Body soft>Priority factors: {c.priority_factors.join('; ')}</Body> : null}
      </Section>

      <Section title="SLA">
        <Body>{d.sla.state.replace(/_/g, ' ')}{d.sla.due_at ? ` · due ${new Date(d.sla.due_at).toLocaleString()}` : ''}</Body>
        {d.sla.remaining != null ? <Body soft>{(d.sla.remaining / 3600).toFixed(1)}h remaining</Body> : null}
      </Section>

      <Section title="Correct category">
        <Body soft>Captured to the correction log, then applied for real - not a silent re-classification.</Body>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{CATEGORIES.map((cat) => <Chip key={cat} label={cat} selected={category === cat} onPress={() => setCategory(cat)} />)}</View>
        <AppButton label="Save correction" kind="secondary" busy={busy === 'correct'} disabled={!category || category === c.category}
          onPress={() => act('correct', () => endpoints.correctCategory(id, category!))} />
      </Section>

      <Section title="Update status">
        <Field label={`${t('lbl.remarks')} (required for Resolved / Rejected)`} value={remarks} onChangeText={setRemarks} multiline />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          {nextStatuses.map((s) => (
            <Chip key={s} label={s.replace(/_/g, ' ')} onPress={() => (!REMARK_REQUIRED.has(s) || remarks.trim()) && act(s, () => endpoints.setStatus(id, s, remarks || undefined))} />
          ))}
        </View>
        <AppButton label="Add remark (without changing status)" kind="secondary" busy={busy === 'remark'} disabled={!remarks.trim()} onPress={() => act('remark', async () => { await endpoints.remarkComplaint(id, remarks); setRemarks(''); })} />
      </Section>

      {c.status === 'in_progress' ? (
        <Section title="Resolve">
          <ResolveForm busy={busy === 'resolve'} onSubmit={(notes) => act('resolve', () => endpoints.resolveComplaint(id, notes))} />
        </Section>
      ) : null}

      <Section title="Field actions">
        <FieldActions busy={busy} act={act} id={id} />
      </Section>

      <Section title="Assign / triage / escalate">
        <AssignTriageEscalate busy={busy} act={act} id={id} currentDept={c.department_code} />
      </Section>

      <Section title="Timeline">
        <Timeline steps={d.timeline} />
      </Section>

      {d.events.filter((e) => e.remarks).length ? (
        <Section title="Remarks & events">
          {d.events.filter((e) => e.remarks).map((e) => <Text key={e.id} style={{ color: colors.text }}><Text style={{ fontWeight: '600' }}>{e.actor_label ?? 'System'}: </Text>{e.remarks}</Text>)}
        </Section>
      ) : null}

      <Section title={t('lbl.evidence')}>
        {d.evidence.length ? d.evidence.map((e) => <Body key={e.id}>{e.name} · {e.analysis_status}</Body>) : <Body soft>No evidence attached.</Body>}
      </Section>

      <Section title="Duplicate candidates">
        {dup === null ? <Loading /> : dup.length === 0 ? <Body soft>None flagged.</Body> : dup.map((cand) => (
          <View key={cand.complaint_id} style={{ paddingVertical: 6, gap: 4 }}>
            <Text style={{ fontWeight: '600', color: colors.text }}>{cand.reference} · {cand.verdict} ({Math.round(cand.score * 100)}%)</Text>
            <Body soft>{cand.explanation}</Body>
            {cand.review ? <Body soft>Reviewed: {cand.review.decision}</Body> : (
              <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                <AppButton label="Confirm duplicate" kind="secondary" onPress={() => act('dup', () => endpoints.duplicateDecision(id, cand.complaint_id, 'confirmed_duplicate'))} />
                <AppButton label="Related" kind="secondary" onPress={() => act('dup', () => endpoints.duplicateDecision(id, cand.complaint_id, 'related'))} />
                <AppButton label="Not a duplicate" kind="secondary" onPress={() => act('dup', () => endpoints.duplicateDecision(id, cand.complaint_id, 'not_duplicate'))} />
              </View>
            )}
          </View>
        ))}
      </Section>

      <Section title="Government platforms">
        {gov === null ? <Loading /> : gov.map((g) => (
          <View key={g.platform} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 4 }}>
            <View style={{ flex: 1 }}><Text style={{ fontWeight: '600', color: colors.text }}>{g.display_name}</Text><Body soft>{g.state}{g.external_reference ? ` · ${g.external_reference}` : ''}{g.last_error ? ` · ${g.last_error}` : ''}</Body></View>
            <AppButton label="Share" kind="secondary" disabled={!g.configured || !g.consent_granted || ['submitted', 'queued', 'submitting'].includes(g.state)}
              onPress={() => act('gov', () => endpoints.officerRequestGovernmentSubmission(id, g.platform))} />
          </View>
        ))}
      </Section>

      <AppButton label="Open investigation" kind="secondary"
        onPress={() => act('inv', async () => { const inv = await endpoints.openInvestigation('complaint', c.id); router.push(`/investigation/${inv.id}`); })} />
    </Screen>
  );
}

function ResolveForm({ busy, onSubmit }: { busy: boolean; onSubmit: (notes: string) => void }) {
  const [notes, setNotes] = useState('');
  return (
    <>
      <Field label="Resolution notes" value={notes} onChangeText={setNotes} multiline />
      <AppButton label="Mark resolved" busy={busy} disabled={!notes.trim()} onPress={() => onSubmit(notes)} />
    </>
  );
}

function FieldActions({ busy, act, id }: { busy: string | null; act: (label: string, fn: () => Promise<unknown>) => Promise<void>; id: string }) {
  const [visitAt, setVisitAt] = useState(''); const [visitNotes, setVisitNotes] = useState('');
  const [findings, setFindings] = useState(''); const [orderRef, setOrderRef] = useState(''); const [orderDesc, setOrderDesc] = useState('');
  const [team, setTeam] = useState(''); const [note, setNote] = useState(''); const [percent, setPercent] = useState('');
  return (
    <View style={{ gap: 10 }}>
      <View style={{ gap: 4 }}>
        <Field label="Schedule field visit (e.g. 2026-09-25T10:00)" value={visitAt} onChangeText={setVisitAt} />
        <Field label="Notes" value={visitNotes} onChangeText={setVisitNotes} multiline />
        <AppButton label="Schedule visit" kind="secondary" busy={busy === 'visit'} disabled={!visitAt.trim()}
          onPress={() => act('visit', async () => { await endpoints.fieldVisit(id, new Date(visitAt).toISOString(), visitNotes || undefined); setVisitAt(''); setVisitNotes(''); })} />
      </View>
      <View style={{ gap: 4 }}>
        <Field label="Inspection findings" value={findings} onChangeText={setFindings} multiline />
        <AppButton label="Record inspection" kind="secondary" busy={busy === 'inspection'} disabled={!findings.trim()} onPress={() => act('inspection', async () => { await endpoints.inspection(id, findings); setFindings(''); })} />
      </View>
      <View style={{ gap: 4 }}>
        <Field label="Work order reference" value={orderRef} onChangeText={setOrderRef} />
        <Field label="Description" value={orderDesc} onChangeText={setOrderDesc} multiline />
        <AppButton label="Log work order" kind="secondary" busy={busy === 'workorder'} disabled={!orderRef.trim() || !orderDesc.trim()} onPress={() => act('workorder', async () => { await endpoints.workOrder(id, orderRef, orderDesc); setOrderRef(''); setOrderDesc(''); })} />
      </View>
      <View style={{ gap: 4 }}>
        <Field label="Coordinate with (team)" value={team} onChangeText={setTeam} />
        <Field label="Note" value={note} onChangeText={setNote} multiline />
        <AppButton label="Log coordination" kind="secondary" busy={busy === 'coord'} disabled={!team.trim() || !note.trim()} onPress={() => act('coord', async () => { await endpoints.coordinationNote(id, team, note); setTeam(''); setNote(''); })} />
      </View>
      <View style={{ gap: 4 }}>
        <Field label="Progress % (0-100)" value={percent} onChangeText={setPercent} keyboardType="numeric" />
        <AppButton label="Log progress" kind="secondary" busy={busy === 'progress'} disabled={!percent.trim()} onPress={() => act('progress', async () => { await endpoints.progressUpdate(id, Number(percent)); setPercent(''); })} />
      </View>
    </View>
  );
}

function AssignTriageEscalate({ busy, act, id, currentDept }: { busy: string | null; act: (label: string, fn: () => Promise<unknown>) => Promise<void>; id: string; currentDept: string | null }) {
  const [officerId, setOfficerId] = useState(''); const [deptCode, setDeptCode] = useState(currentDept ?? ''); const [reason, setReason] = useState('');
  return (
    <View style={{ gap: 10 }}>
      <View style={{ gap: 4 }}>
        <Field label="Officer ID to assign" value={officerId} onChangeText={setOfficerId} />
        <AppButton label="Assign" kind="secondary" busy={busy === 'assign'} disabled={!officerId.trim()} onPress={() => act('assign', async () => { await endpoints.assign(id, officerId); setOfficerId(''); })} />
      </View>
      <View style={{ gap: 4 }}>
        <Field label="Department code" value={deptCode} onChangeText={setDeptCode} />
        <AppButton label="Triage to department" kind="secondary" busy={busy === 'triage'} disabled={!deptCode.trim()} onPress={() => act('triage', () => endpoints.triage(id, deptCode))} />
      </View>
      <View style={{ gap: 4 }}>
        <Field label="Escalation reason" value={reason} onChangeText={setReason} multiline />
        <AppButton label="Escalate" kind="danger" busy={busy === 'escalate'} disabled={!reason.trim()} onPress={() => act('escalate', async () => { await endpoints.escalate(id, reason); setReason(''); })} />
      </View>
    </View>
  );
}
