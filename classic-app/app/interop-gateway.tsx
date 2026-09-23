import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { AppButton, Body, Card, Chip, Disclosure, EmptyState, ErrorBanner, Field, H1, InfoBanner, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type {
  ConnectorAlertView, ConnectorView, ExchangeResult, FieldMappingView, IdentityMatchCandidateView, InteropConsent,
  InteropExceptionView, InteropTransactionView, ServiceCatalogEntryView, TimelineResult,
} from '../src/api/types.ts';
import { useAuth } from '../src/auth/AuthContext.tsx';
import { radius, withAlpha } from '../src/theme.ts';
import { useTheme } from '../src/theme/ThemeContext.tsx';

// The two citizens seeded by app/interop/mock_systems.py - real demo data, not fabricated for the UI.
const DEMO_APPLICATIONS = [
  { label: 'Priya Deshmukh · APP-MH-2026-5501', value: 'APP-MH-2026-5501' },
  { label: 'Arjun Patil · APP-MH-2026-5502', value: 'APP-MH-2026-5502' },
];

const HEALTH_TONE: Record<string, 'ok' | 'warn' | 'bad' | 'muted'> = { healthy: 'ok', degraded: 'warn', unavailable: 'bad', not_configured: 'muted', unknown: 'muted' };
const SLA_TONE: Record<string, 'ok' | 'warn' | 'bad' | 'muted'> = { met: 'ok', breached: 'bad', unknown: 'muted' };
const RESOLUTION_TONE: Record<string, 'ok' | 'warn' | 'bad' | 'muted'> = { open: 'warn', retrying: 'warn', resolved: 'ok', dead: 'bad' };

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
  const [exceptions, setExceptions] = useState<InteropExceptionView[] | null>(null);
  const [alerts, setAlerts] = useState<ConnectorAlertView[] | null>(null);
  const [services, setServices] = useState<ServiceCatalogEntryView[] | null>(null);
  const [fieldMappings, setFieldMappings] = useState<Record<string, FieldMappingView[]>>({});

  const [applicationNo, setApplicationNo] = useState(DEMO_APPLICATIONS[0].value);
  const [result, setResult] = useState<ExchangeResult | null>(null);
  const [timeline, setTimeline] = useState<TimelineResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [c, k, cand, t, exc, al, svc] = await Promise.all([
        endpoints.interopConnectors(), endpoints.interopConsents('pending'), endpoints.interopIdentityCandidates('pending'), endpoints.interopTransactions(20),
        endpoints.interopGatewayExceptions(), endpoints.interopAlerts(false), endpoints.interopServiceCatalog(),
      ]);
      setConnectors(c.items); setConsents(k.items); setCandidates(cand.items); setTransactions(t.items);
      setExceptions(exc.items); setAlerts(al.items); setServices(svc.items);
    } catch (e: any) {
      setError(e?.message ?? 'Could not load the interop console. You may need admin access.');
      setConnectors([]); setConsents([]); setCandidates([]); setTransactions([]); setExceptions([]); setAlerts([]); setServices([]);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const loadFieldMappings = useCallback(async (serviceId: string) => {
    if (fieldMappings[serviceId]) return;
    try { const r = await endpoints.interopFieldMappings(serviceId); setFieldMappings((prev) => ({ ...prev, [serviceId]: r.items })); }
    catch { /* the Disclosure just shows nothing below - not worth a separate error banner for a read-only catalog view */ }
  }, [fieldMappings]);

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
                <View style={{ flexDirection: 'row', gap: 4 }}>
                  <Badge label={c.health_state} tone={HEALTH_TONE[c.health_state] ?? 'muted'} />
                  <Badge label={`SLA ${c.sla_status}`} tone={SLA_TONE[c.sla_status] ?? 'muted'} />
                </View>
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
          {result.status === 'failed' && result.reason ? <Body soft>Reason: {result.reason}{result.issues?.length ? ` (${result.issues.join('; ')})` : ''}{result.denied_fields?.length ? ` — not authorized: ${result.denied_fields.join(', ')}` : ''}</Body> : null}
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

      <Disclosure label={`Connector alerts${alerts && alerts.length ? ` (${alerts.length} unacknowledged)` : ''}`}>
        <Body soft>Raised only on a genuine state change - an SLA that just breached, or a connector that just became unavailable - never once per failed call.</Body>
        {alerts === null ? <Loading /> : alerts.length === 0 ? <EmptyState message="No unacknowledged alerts." /> : alerts.map((a) => (
          <Card key={a.alert_id}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Badge label={a.alert_type.replace(/_/g, ' ')} tone={a.severity === 'critical' ? 'bad' : 'warn'} />
              <Text style={{ fontSize: 10, color: colors.textMuted }}>{new Date(a.created_at).toLocaleString()}</Text>
            </View>
            <Body soft>{a.message}</Body>
            <AppButton label="Acknowledge" kind="secondary" busy={busy === a.alert_id} onPress={() => act(a.alert_id, () => endpoints.acknowledgeInteropAlert(a.alert_id))} />
          </Card>
        ))}
      </Disclosure>

      <Disclosure label={`Exception log${exceptions && exceptions.length ? ` (${exceptions.length})` : ''}`}>
        <Body soft>Every failed exchange lands here with a canonical error code, retry bookkeeping, and dead-letter state - not just the plain-language reason shown above.</Body>
        {exceptions === null ? <Loading /> : exceptions.length === 0 ? <EmptyState message="No exceptions logged." /> : exceptions.map((x) => (
          <Card key={x.exception_id}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ fontWeight: '700', fontSize: 12, color: colors.text }}>{x.error_code}</Text>
              <Badge label={x.resolution_state} tone={RESOLUTION_TONE[x.resolution_state] ?? 'muted'} />
            </View>
            <Body soft>{x.message}</Body>
            <Text style={{ fontSize: 10, color: colors.textMuted }}>{x.source_system ?? '?'} → {x.target_system ?? '?'}{x.retryable ? ` · retry ${x.retry_count}/${x.max_retries}` : ' · not retryable'}</Text>
            {x.resolution_state !== 'resolved' && x.resolution_state !== 'dead' ? (
              <View style={{ flexDirection: 'row', gap: 6, marginTop: 4 }}>
                {x.retryable ? <AppButton label="Retry" kind="secondary" busy={busy === `retry-${x.exception_id}`} onPress={() => act(`retry-${x.exception_id}`, () => endpoints.retryInteropException(x.exception_id))} /> : null}
                <AppButton label="Resolve" kind="secondary" busy={busy === `resolve-${x.exception_id}`} onPress={() => act(`resolve-${x.exception_id}`, () => endpoints.resolveInteropException(x.exception_id))} />
                <AppButton label="Mark dead" kind="danger" busy={busy === `dead-${x.exception_id}`} onPress={() => act(`dead-${x.exception_id}`, () => endpoints.markInteropExceptionDead(x.exception_id))} />
              </View>
            ) : null}
          </Card>
        ))}
      </Disclosure>

      <Disclosure label="Service catalog & field mappings">
        <Body soft>The cross-department services this platform exposes, and exactly which fields each one reads and writes - generated from, and verified against, the real transform code.</Body>
        {services === null ? <Loading /> : services.length === 0 ? <EmptyState message="No services in the catalog." /> : services.map((s) => (
          <Card key={s.service_id}>
            <Text style={{ fontWeight: '700', fontSize: 13, color: colors.text }}>{s.name}</Text>
            <Body soft>{s.description}</Body>
            <Text style={{ fontSize: 11, color: colors.textMuted }}>{s.source_system} → {s.target_system} · {s.data_category}</Text>
            <Disclosure label="Field mappings" defaultOpen={false}>
              {(() => {
                const mappings = fieldMappings[s.service_id];
                if (!mappings) { loadFieldMappings(s.service_id); return <Loading />; }
                return mappings.length === 0 ? <EmptyState message="No mappings recorded." /> : mappings.map((m) => {
                  const from = m.direction === 'external_to_canonical' ? `${m.system_id}.${m.source_field}` : `canonical.${m.source_field}`;
                  const to = m.direction === 'external_to_canonical' ? `canonical.${m.target_field}` : `${m.system_id}.${m.target_field}`;
                  return (
                    <View key={m.mapping_id} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3, borderBottomWidth: 1, borderBottomColor: colors.border }}>
                      <Text style={{ fontSize: 11, color: colors.text }}>{from} → {to}</Text>
                      <Text style={{ fontSize: 10, color: colors.textMuted }}>{m.transform_note}</Text>
                    </View>
                  );
                });
              })()}
            </Disclosure>
          </Card>
        ))}
      </Disclosure>
    </Screen>
  );
}
