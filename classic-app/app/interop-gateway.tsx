import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { AppButton, Body, Card, Chip, EmptyState, ErrorBanner, Field, H1, InfoBanner, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { ConnectorView, ExchangeResult, IdentityMatchCandidateView, InteropConsent, InteropTransactionView, TimelineResult } from '../src/api/types.ts';
import { useAuth } from '../src/auth/AuthContext.tsx';
import { radius, withAlpha } from '../src/theme.ts';
import { useTheme } from '../src/theme/ThemeContext.tsx';

// The two citizens seeded by app/interop/mock_systems.py - real demo data, not fabricated for the UI.
const DEMO_APPLICATIONS = [
  { label: 'Priya Deshmukh · APP-MH-2026-5501', value: 'APP-MH-2026-5501' },
  { label: 'Arjun Patil · APP-MH-2026-5502', value: 'APP-MH-2026-5502' },
];

const HEALTH_TONE: Record<string, 'ok' | 'warn' | 'bad' | 'muted'> = { healthy: 'ok', degraded: 'warn', unavailable: 'bad', not_configured: 'muted', unknown: 'muted' };

function Badge({ label, tone }: { label: string; tone: 'ok' | 'warn' | 'bad' | 'muted' | 'info' }) {
  const { colors } = useTheme();
  const c = tone === 'ok' ? colors.ok : tone === 'warn' ? colors.warn : tone === 'bad' ? colors.bad : tone === 'info' ? colors.primary : colors.textMuted;
  return (
    <View style={{ backgroundColor: withAlpha(c, 0.15), borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3, alignSelf: 'flex-start' }}>
      <Text style={{ fontSize: 11, fontWeight: '700', color: c }}>{label}</Text>
    </View>
  );
}

const STATUS_COPY: Record<string, { label: string; tone: 'ok' | 'warn' | 'bad' | 'info'; explain: string }> = {
  success: { label: 'Exchange completed', tone: 'ok', explain: 'Department A’s document was fetched and written into Department B’s application. The citizen never downloaded or re-uploaded anything.' },
  already_completed: { label: 'Already completed', tone: 'ok', explain: 'This application’s document requirement was already satisfied by a previous exchange.' },
  consent_required: { label: 'Consent required', tone: 'warn', explain: 'Nothing has been read from Department A yet. Grant the consent request below to proceed.' },
  identity_ambiguous: { label: 'Identity needs manual review', tone: 'warn', explain: 'The match wasn’t confident enough to auto-link. Resolve it in the identity review queue below before this can continue.' },
  identity_conflict: { label: 'Identity conflict', tone: 'bad', explain: 'Department A and Department B resolved to two different identities. This needs manual review.' },
  source_record_not_found: { label: 'No matching record', tone: 'bad', explain: 'No resident in Department A matched this beneficiary by name or mobile number.' },
  failed: { label: 'Exchange failed', tone: 'bad', explain: 'See the reason below.' },
};

export default function InteropGateway() {
  const { colors } = useTheme();
  const { user, signOut } = useAuth();
  const [connectors, setConnectors] = useState<ConnectorView[] | null>(null);
  const [consents, setConsents] = useState<InteropConsent[] | null>(null);
  const [candidates, setCandidates] = useState<IdentityMatchCandidateView[] | null>(null);
  const [transactions, setTransactions] = useState<InteropTransactionView[] | null>(null);

  const [applicationNo, setApplicationNo] = useState(DEMO_APPLICATIONS[0].value);
  const [result, setResult] = useState<ExchangeResult | null>(null);
  const [timeline, setTimeline] = useState<TimelineResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [c, k, cand, t] = await Promise.all([
        endpoints.interopConnectors(), endpoints.interopConsents('pending'), endpoints.interopIdentityCandidates('pending'), endpoints.interopTransactions(20),
      ]);
      setConnectors(c.items); setConsents(k.items); setCandidates(cand.items); setTransactions(t.items);
    } catch (e: any) { setError(e?.message ?? 'Could not load the interop console. You may need admin access.'); setConnectors([]); setConsents([]); setCandidates([]); setTransactions([]); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const runExchange = useCallback(async () => {
    setBusy('exchange'); setError(null); setTimeline(null);
    try {
      const r = await endpoints.requestDocumentExchange(applicationNo.trim());
      setResult(r);
      if (r.status === 'success' || r.status === 'already_completed') setTimeline(await endpoints.interopTimeline(applicationNo.trim()));
      await load();
    } catch (e: any) { setError(e?.message ?? 'Could not run the exchange.'); } finally { setBusy(null); }
  }, [applicationNo, load]);

  async function act(id: string, fn: () => Promise<unknown>) {
    setBusy(id); setError(null);
    try { await fn(); await load(); if (result) { const r = await endpoints.requestDocumentExchange(applicationNo.trim()); setResult(r); if (r.status === 'success') setTimeline(await endpoints.interopTimeline(applicationNo.trim())); } }
    catch (e: any) { setError(e?.message ?? 'That action failed.'); } finally { setBusy(null); }
  }

  const copy = result ? STATUS_COPY[result.status] : null;

  return (
    <Screen>
      <H1>🔄 Interop Gateway</H1>
      <Body soft>The no-reupload cross-department demo: a citizen’s document, already on file with one department, satisfies another department’s requirement automatically - with explicit consent, confidence-scored identity resolution, and a full audit trail.</Body>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Body soft>Signed in as {user?.full_name ?? user?.email} · {user?.role?.replace(/_/g, ' ')}</Body>
        <Pressable accessibilityRole="button" onPress={signOut}><Text style={{ color: colors.bad, fontWeight: '700', fontSize: 13 }}>Sign out</Text></Pressable>
      </View>
      {error ? <ErrorBanner message={error} onRetry={load} /> : null}

      <Text style={{ fontWeight: '700', color: colors.text, marginTop: 4 }}>Connector registry</Text>
      {connectors === null ? <Loading /> : connectors.length === 0 ? <EmptyState message="No connectors registered." /> : (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {connectors.map((c) => (
            <View key={c.connector_id} style={{ flex: 1, minWidth: 220, backgroundColor: colors.card, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: 12, gap: 4 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ fontWeight: '700', color: colors.text }}>{c.name}</Text>
                <Badge label={c.health_state} tone={HEALTH_TONE[c.health_state] ?? 'muted'} />
              </View>
              <Body soft>{c.department}</Body>
              <Text style={{ fontSize: 11, color: colors.textMuted }}>{c.total_calls} call(s){c.total_failures ? ` · ${c.total_failures} failed` : ''}{c.avg_response_ms != null ? ` · ~${Math.round(c.avg_response_ms)}ms` : ''}</Text>
              <AppButton label="Health check" kind="secondary" busy={busy === `health-${c.connector_id}`} onPress={() => act(`health-${c.connector_id}`, () => endpoints.interopConnectorHealthCheck(c.connector_id))} />
            </View>
          ))}
        </View>
      )}

      <Text style={{ fontWeight: '700', color: colors.text, marginTop: 4 }}>Run the demo</Text>
      <InfoBanner message="Every mock system here is clearly demo data - three independently-shaped government systems (different identifier vocabularies), not three pages on one database." />
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        {DEMO_APPLICATIONS.map((a) => <Chip key={a.value} label={a.label} selected={applicationNo === a.value} onPress={() => { setApplicationNo(a.value); setResult(null); setTimeline(null); }} />)}
      </View>
      <Field label="Application number" value={applicationNo} onChangeText={setApplicationNo} />
      <AppButton label="Request document exchange" busy={busy === 'exchange'} disabled={!applicationNo.trim()} onPress={runExchange} />

      {result && copy ? (
        <Card>
          <Badge label={copy.label} tone={copy.tone} />
          <Body soft>{copy.explain}</Body>
          {result.status === 'consent_required' && result.consent_id ? (
            <View style={{ flexDirection: 'row', gap: 6, marginTop: 6 }}>
              <AppButton label="Grant consent" busy={busy === 'grant'} onPress={() => act('grant', () => endpoints.grantConsent(result.consent_id!))} />
              <AppButton label="Deny" kind="secondary" busy={busy === 'deny'} onPress={() => act('deny', () => endpoints.denyConsent(result.consent_id!))} />
            </View>
          ) : null}
          {result.status === 'identity_ambiguous' ? <Body soft>Confidence: {Math.round((result.confidence ?? 0) * 100)}% — {result.explanation}</Body> : null}
          {result.status === 'failed' && result.reason ? <Body soft>Reason: {result.reason}{result.issues?.length ? ` (${result.issues.join('; ')})` : ''}</Body> : null}
          {result.status === 'success' ? <Body soft>Document reference: {result.document_reference} · quality {Math.round((result.quality_score ?? 0) * 100)}%</Body> : null}
        </Card>
      ) : null}

      {timeline ? (
        <Card>
          <Text style={{ fontWeight: '700', color: colors.text }}>Cross-department timeline — {timeline.application.reference}</Text>
          {timeline.events.map((e) => (
            <View key={e.id} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3, borderBottomWidth: 1, borderBottomColor: colors.border }}>
              <Text style={{ fontSize: 12, color: colors.text }}>{e.step.replace(/_/g, ' ')} <Text style={{ color: colors.textMuted }}>({e.source_system})</Text></Text>
              <Badge label={e.status} tone={e.status === 'success' ? 'ok' : 'bad'} />
            </View>
          ))}
        </Card>
      ) : null}

      <Text style={{ fontWeight: '700', color: colors.text, marginTop: 4 }}>Pending consent requests</Text>
      {consents === null ? <Loading /> : consents.length === 0 ? <EmptyState message="Nothing pending." /> : consents.map((c) => (
        <Card key={c.consent_id}>
          <Body>{c.purpose}</Body>
          <Body soft>{c.requesting_system} ← {c.providing_system} · {c.data_category}</Body>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            <AppButton label="Grant" busy={busy === c.consent_id} onPress={() => act(c.consent_id, () => endpoints.grantConsent(c.consent_id))} />
            <AppButton label="Deny" kind="secondary" busy={busy === c.consent_id} onPress={() => act(c.consent_id, () => endpoints.denyConsent(c.consent_id))} />
          </View>
        </Card>
      ))}

      <Text style={{ fontWeight: '700', color: colors.text, marginTop: 4 }}>Identity match review queue</Text>
      <Body soft>Nothing below auto-linked — the resolver wasn’t confident enough, so it’s waiting for a human decision.</Body>
      {candidates === null ? <Loading /> : candidates.length === 0 ? <EmptyState message="No ambiguous matches pending review." /> : candidates.map((c) => (
        <Card key={c.id}>
          <Body>{c.system} · {c.identifier_type} · {c.identifier_value}</Body>
          <Body soft>Confidence {Math.round(c.score * 100)}% — {c.explanation}</Body>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            <AppButton label="Confirm match" busy={busy === c.id} onPress={() => act(c.id, () => endpoints.resolveIdentityCandidate(c.id, true))} />
            <AppButton label="Reject (different person)" kind="secondary" busy={busy === c.id} onPress={() => act(c.id, () => endpoints.resolveIdentityCandidate(c.id, false))} />
          </View>
        </Card>
      ))}

      <Text style={{ fontWeight: '700', color: colors.text, marginTop: 4 }}>Recent transactions</Text>
      {transactions === null ? <Loading /> : transactions.length === 0 ? <EmptyState message="No exchanges recorded yet." /> : transactions.map((t) => (
        <Card key={t.transaction_id}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={{ fontSize: 12, color: colors.text }}>{t.source_system} → {t.target_system} · {t.operation}</Text>
            <Badge label={t.status} tone={t.status === 'success' ? 'ok' : 'bad'} />
          </View>
          {t.error_message ? <Body soft>{t.error_message}</Body> : null}
          <Text style={{ fontSize: 10, color: colors.textMuted }}>{new Date(t.created_at).toLocaleString()}{t.duration_ms != null ? ` · ${Math.round(t.duration_ms)}ms` : ''}</Text>
        </Card>
      ))}
    </Screen>
  );
}
