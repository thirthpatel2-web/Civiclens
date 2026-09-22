import React, { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { AppButton, Body, Card, EmptyState, ErrorBanner, H1, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { IntegrationHealth, JobRecordView, NotificationStatus, SystemStatus } from '../src/api/types.ts';
import { radius, shadow } from '../src/theme.ts';
import { useTheme } from '../src/theme/ThemeContext.tsx';

// Ported from legacy-prototype/src/screens/MonitoringScreen.js's 2x2 metric grid - the numbers
// here are our real equivalents (queue depth, RAG chunks indexed, integration failures, dead jobs),
// not the zip's Supabase-specific consent/audit counters, since this backend tracks different things.
function MetricBox({ icon, color, value, label }: { icon: keyof typeof Ionicons.glyphMap; color: string; value: string | number; label: string }) {
  const { colors } = useTheme();
  return (
    <View style={[{ width: '48%', borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12, marginBottom: 10, alignItems: 'flex-start' }, shadow.sm]}>
      <Ionicons name={icon} size={18} color={color} />
      <Text style={{ fontSize: 20, fontWeight: '800', marginTop: 6, color }}>{value}</Text>
      <Text style={{ fontSize: 10, marginTop: 2, color: colors.textMuted }}>{label}</Text>
    </View>
  );
}

const STATE_TONE: Record<string, 'ok' | 'warn' | 'bad' | 'muted'> = {
  CONNECTED: 'ok', ok: 'ok', configured: 'ok', ready: 'ok',
  DEGRADED: 'warn', not_ready: 'warn',
  UNAVAILABLE: 'bad', down: 'bad', not_configured: 'muted', UNKNOWN: 'muted',
};
function toneColor(colors: ReturnType<typeof useTheme>['colors'], state: string) {
  const tone = STATE_TONE[state] ?? 'muted';
  return tone === 'ok' ? colors.ok : tone === 'warn' ? colors.warn : tone === 'bad' ? colors.bad : colors.textMuted;
}

function Pill({ label, state }: { label: string; state: string }) {
  const { colors } = useTheme();
  const c = toneColor(colors, state);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.surfaceElevated, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }}>
      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: c }} />
      <Text style={{ fontSize: 12, color: colors.text }}>{label}: <Text style={{ fontWeight: '700', color: c }}>{state}</Text></Text>
    </View>
  );
}

export default function Monitoring() {
  const { colors } = useTheme();
  const [sys, setSys] = useState<SystemStatus | null>(null);
  const [integrations, setIntegrations] = useState<IntegrationHealth[] | null>(null);
  const [notif, setNotif] = useState<NotificationStatus | null>(null);
  const [jobs, setJobs] = useState<JobRecordView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, i, n, j] = await Promise.all([endpoints.systemStatus(), endpoints.integrationStatus(), endpoints.notificationStatus(), endpoints.monitoringJobs()]);
      setSys(s); setIntegrations(i.items); setNotif(n); setJobs(j.items);
    } catch (e: any) { setError(e?.message ?? 'Could not load system status.'); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <Screen>
      <H1>🖥️ System Health</H1>
      <Body soft>Live status of every real integration this deployment depends on - nothing simulated.</Body>
      {error ? <ErrorBanner message={error} onRetry={load} /> : null}

      {sys && integrations && jobs ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' }}>
          <MetricBox icon="server-outline" color={colors.primary} value={sys.queue.backend_depth} label="Queue Depth" />
          <MetricBox icon="document-text-outline" color={colors.info} value={sys.rag.chunks} label="Document Chunks Indexed" />
          <MetricBox icon="warning-outline" color={integrations.some((i) => i.state !== 'CONNECTED') ? colors.bad : colors.ok} value={integrations.filter((i) => i.state !== 'CONNECTED').length} label="Integrations Not Connected" />
          <MetricBox icon="checkmark-done-outline" color={colors.warn} value={jobs.filter((j) => j.status === 'dead').length} label="Dead Background Jobs" />
        </View>
      ) : null}

      {!sys ? <Loading /> : (
        <Card>
          <Text style={{ fontWeight: '700', color: colors.text }}>Core services</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            <Pill label="Queue backend" state={sys.queue.backend_reachable ? 'ready' : 'not_ready'} />
            <Pill label="Ollama / AI" state={sys.ollama} />
            <Pill label="Semantic search" state={sys.rag.semantic_search ? 'ready' : 'not_ready'} />
            <Pill label="Storage" state={sys.storage.state} />
          </View>
          <Body soft>{sys.websocket_connections} live websocket connection(s) · {sys.rag.chunks} document chunks indexed · queue depth {sys.queue.backend_depth}</Body>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
            {Object.entries(sys.queue.by_status).map(([k, v]) => <Pill key={k} label={k} state={String(v)} />)}
          </View>
        </Card>
      )}

      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
        <Text style={{ fontWeight: '700', color: colors.text }}>Government platform integrations</Text>
        <AppButton label="Check now" kind="secondary" busy={checking} onPress={async () => { setChecking(true); try { const r = await endpoints.integrationCheck(); setIntegrations(r.items); } catch (e: any) { setError(e?.message); } finally { setChecking(false); } }} />
      </View>
      {integrations === null ? <Loading /> : integrations.length === 0 ? <EmptyState message="No integrations configured." /> : integrations.map((it) => (
        <Card key={it.platform}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text style={{ fontWeight: '700', color: colors.text }}>{it.display_name}</Text>
            <Pill label="state" state={it.state} />
          </View>
          <Body soft>{it.detail}</Body>
          <Body soft>{it.total_calls} calls · {it.total_failures} failures{it.avg_response_ms != null ? ` · avg ${Math.round(it.avg_response_ms)}ms` : ''}</Body>
          {it.last_error ? <Body soft>Last error: {it.last_error}</Body> : null}
        </Card>
      ))}

      <Text style={{ fontWeight: '700', color: colors.text, marginTop: 4 }}>Notification delivery</Text>
      {notif === null ? <Loading /> : (
        <Card>
          <Body soft>Email: {notif.email_configured ? 'configured' : 'not configured'} · Push: {notif.push_configured ? 'configured' : 'not configured'}</Body>
          {Object.entries(notif.by_channel).map(([channel, counts]) => (
            <View key={channel}>
              <Text style={{ fontWeight: '600', color: colors.text, marginTop: 4 }}>{channel}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                {Object.entries(counts).map(([status, n]) => <Pill key={status} label={status} state={String(n)} />)}
              </View>
            </View>
          ))}
        </Card>
      )}

      <Text style={{ fontWeight: '700', color: colors.text, marginTop: 4 }}>Recent background jobs</Text>
      {jobs === null ? <Loading /> : jobs.length === 0 ? <EmptyState message="No jobs yet." /> : jobs.slice(0, 20).map((j) => (
        <Card key={j.id}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={{ fontWeight: '600', color: colors.text }}>{j.kind}</Text>
            <Pill label="status" state={j.status} />
          </View>
          <Body soft>{j.attempts}/{j.max_attempts} attempts · updated {new Date(j.updated_at).toLocaleString()}</Body>
          {j.error ? <Body soft>{j.error}</Body> : null}
          {j.status === 'dead' ? <AppButton label="Retry" kind="secondary" onPress={async () => { await endpoints.retryJob(j.id); await load(); }} /> : null}
        </Card>
      ))}
    </Screen>
  );
}
