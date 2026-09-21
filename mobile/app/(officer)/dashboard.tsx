import React, { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { Body, Card, EmptyState, ErrorBanner, H1, Loading, Screen } from '../../src/components/ui.tsx';
import { endpoints } from '../../src/api/instance.ts';
import type { DepartmentDashboard } from '../../src/api/types.ts';
import { useAuth } from '../../src/auth/AuthContext.tsx';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useTheme } from '../../src/theme/ThemeContext.tsx';
import type { ThemeColors } from '../../src/theme.ts';

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ minWidth: 108, flexGrow: 1, backgroundColor: colors.card, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 12, gap: 2 }}>
      <Text style={{ fontSize: 22, fontWeight: '800', color: tone ?? colors.text }}>{value}</Text>
      <Text style={{ fontSize: 12, color: colors.textSoft }}>{label}</Text>
    </View>
  );
}
const Row = ({ children }: { children: React.ReactNode }) => <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>{children}</View>;
function Bar({ label, count, max, colors }: { label: string; count: number; max: number; colors: ThemeColors }) {
  return (
    <View style={{ gap: 2 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><Text style={{ color: colors.text, fontSize: 13 }}>{label.replace(/_/g, ' ')}</Text><Text style={{ color: colors.textSoft, fontSize: 13 }}>{count}</Text></View>
      <View style={{ height: 6, borderRadius: 3, backgroundColor: colors.bg }}><View style={{ height: 6, borderRadius: 3, width: `${max ? Math.max(4, (count / max) * 100) : 0}%`, backgroundColor: colors.primary }} /></View>
    </View>
  );
}

export default function OfficerDashboard() {
  const { t } = useI18n();
  const { user } = useAuth();
  const { colors } = useTheme();
  const [d, setD] = useState<DepartmentDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try { setD(await endpoints.departmentDashboard()); }
    catch (e: any) { setError(e?.message ?? 'Could not load the department dashboard.'); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (error) return <Screen><ErrorBanner message={error} onRetry={load} /></Screen>;
  if (!d) return <Screen><Loading label={t('msg.loading')} /></Screen>;
  if (!d.has_data) return <Screen><H1>{t('nav.dashboard')}</H1><EmptyState message={t('msg.no_data')} /></Screen>;

  const maxCategory = Math.max(1, ...Object.values(d.by_category));
  const maxPriority = Math.max(1, ...Object.values(d.by_priority));
  const workloadEntries = Object.entries(d.workload).sort((a, b) => b[1] - a[1]);

  return (
    <Screen>
      <H1>{d.department_code ?? 'All departments'}{user?.department_code ? '' : ' (org-wide)'}</H1>
      <Row>
        <Stat label="Total" value={d.total} />
        <Stat label="Open" value={d.open} tone={colors.primary} />
        <Stat label="Resolved" value={d.resolved} tone={colors.ok} />
        <Stat label="Escalated" value={d.escalated} tone={d.escalated > 0 ? colors.bad : colors.text} />
        <Stat label="Unrouted" value={d.unrouted} tone={d.unrouted > 0 ? colors.warn : colors.text} />
        <Stat label="Backlog" value={d.backlog} />
      </Row>

      <Card>
        <Body soft>SLA status of open complaints</Body>
        <Row>
          <Stat label="On track" value={d.sla.on_track} tone={colors.ok} />
          <Stat label="At risk" value={d.sla.at_risk} tone={colors.warn} />
          <Stat label="Breached" value={d.sla.breached} tone={colors.bad} />
          <Stat label="No policy" value={d.sla.no_policy} tone={colors.muted} />
        </Row>
      </Card>

      {d.resolution_hours ? (
        <Card>
          <Body soft>Resolution time (from {d.resolution_hours.count} resolved complaints)</Body>
          <Body>Median: {d.resolution_hours.median.toFixed(1)}h · Mean: {d.resolution_hours.mean.toFixed(1)}h</Body>
        </Card>
      ) : null}

      <Card>
        <Body soft>By category</Body>
        {Object.entries(d.by_category).sort((a, b) => b[1] - a[1]).map(([k, v]) => <Bar key={k} label={k} count={v} max={maxCategory} colors={colors} />)}
      </Card>

      <Card>
        <Body soft>By priority</Body>
        {Object.entries(d.by_priority).sort((a, b) => b[1] - a[1]).map(([k, v]) => <Bar key={k} label={k} count={v} max={maxPriority} colors={colors} />)}
      </Card>

      <Card>
        <Body soft>Officer workload (open complaints assigned)</Body>
        {workloadEntries.length === 0 ? <Body soft>Nothing assigned yet.</Body> : workloadEntries.map(([officerId, count]) => (
          <Text key={officerId} style={{ color: colors.text }}>{officerId === user?.id ? 'You' : officerId.slice(0, 8)}: {count}</Text>
        ))}
      </Card>

      <Card>
        <Body soft>Open anomalies flagged by the system</Body>
        {d.anomalies.length === 0 ? <Body soft>No anomalies flagged.</Body> : d.anomalies.map((a) => (
          <View key={a.id} style={{ paddingVertical: 4 }}>
            <Text style={{ fontWeight: '600', color: a.severity === 'high' ? colors.bad : a.severity === 'medium' ? colors.warn : colors.text }}>{a.kind} · {a.severity}</Text>
            <Body soft>{a.explanation}</Body>
          </View>
        ))}
      </Card>
    </Screen>
  );
}
