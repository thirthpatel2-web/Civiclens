import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { AppButton, Body, Card, EmptyState, ErrorBanner, Loading, Screen, StatusBadge } from '../../src/components/ui.tsx';
import { endpoints } from '../../src/api/instance.ts';
import type { Complaint } from '../../src/api/types.ts';
import { useAuth } from '../../src/auth/AuthContext.tsx';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useSync } from '../../src/offline/SyncContext.tsx';
import { radius, withAlpha } from '../../src/theme.ts';
import type { ThemeColors } from '../../src/theme.ts';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

type Pillar = { icon: keyof typeof Ionicons.glyphMap; title: string; sub: string; tag: string; color: string; tint: string; href: string };
function buildPillars(colors: ThemeColors): Pillar[] {
  return [
    { icon: 'add-circle', title: 'Report an Issue', sub: 'AI-classified civic complaint, routed to the right department', tag: 'Grievance', color: colors.primary, tint: withAlpha(colors.primary, 0.12), href: '/(tabs)/report' },
    { icon: 'business', title: 'RTI Drafter', sub: 'Section 6(1)/7(1) application with a precise questionnaire', tag: 'RTI Act 2005', color: colors.accentSaffron, tint: withAlpha(colors.accentSaffron, 0.12), href: '/rti' },
    { icon: 'scale', title: 'Case Analyzer', sub: 'Legal concepts, precedents & disposal outcomes', tag: 'Precedents', color: colors.accentPurple, tint: withAlpha(colors.accentPurple, 0.12), href: '/legal' },
    { icon: 'map', title: 'Civic GIS Radar', sub: 'Real complaint hotspots near you, privacy-thresholded', tag: 'Live map', color: colors.accentEmerald, tint: withAlpha(colors.accentEmerald, 0.12), href: '/map' },
    { icon: 'business-outline', title: 'Department Directory', sub: 'Real departments, offices & services for this deployment', tag: 'Directory', color: colors.primaryLight, tint: withAlpha(colors.primaryLight, 0.12), href: '/directory' },
    { icon: 'navigate', title: 'Civic Locator', sub: 'Nearest real government offices, sorted by your location', tag: 'Nearby', color: colors.ok, tint: withAlpha(colors.ok, 0.12), href: '/locator' },
    { icon: 'chatbubbles', title: 'Civic Saathi', sub: 'Ask about your complaints, RTI deadlines or documents', tag: 'AI Assistant', color: colors.accent, tint: withAlpha(colors.accent, 0.12), href: '/copilot' },
    { icon: 'git-network', title: 'Interoperability Lab', sub: 'See real government data formats normalize into one schema', tag: 'Golden Record', color: colors.accentPurple, tint: withAlpha(colors.accentPurple, 0.12), href: '/interop' },
    { icon: 'scan', title: 'Scan a Document', sub: 'Camera-scan a notice or receipt so Civic Saathi can cite it', tag: 'Documents', color: colors.accentRose, tint: withAlpha(colors.accentRose, 0.12), href: '/documents' },
    { icon: 'medkit', title: 'Emergency Hub', sub: 'Verified helplines - never use this form for emergencies', tag: 'Helplines', color: colors.info, tint: withAlpha(colors.info, 0.12), href: '/emergency' },
    { icon: 'settings', title: 'Settings & Privacy', sub: 'Language, consent, linked IDs and two-factor security', tag: 'Account', color: colors.muted, tint: withAlpha(colors.muted, 0.12), href: '/settings' },
  ];
}

function PillarCard({ p, onPress, colors }: { p: Pillar; onPress: () => void; colors: ThemeColors }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={{ flex: 1, minWidth: '46%' }}>
      <View style={{ backgroundColor: colors.card, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 8, minHeight: 148 }}>
        <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: p.tint, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={p.icon} size={20} color={p.color} />
        </View>
        <Text style={{ fontWeight: '800', color: colors.text, fontSize: 14 }}>{p.title}</Text>
        <Text style={{ color: colors.textSoft, fontSize: 12, lineHeight: 16 }} numberOfLines={2}>{p.sub}</Text>
        <View style={{ alignSelf: 'flex-start', backgroundColor: p.tint, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 }}>
          <Text style={{ color: p.color, fontSize: 10, fontWeight: '700' }}>{p.tag}</Text>
        </View>
      </View>
    </Pressable>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <View style={{ flex: 1, alignItems: 'center', gap: 2 }}>
      <Text style={{ fontSize: 24, fontWeight: '800', color: color ?? '#fff' }}>{value}</Text>
      <Text style={{ fontSize: 11, color: 'rgba(255,255,255,0.85)', textAlign: 'center' }}>{label}</Text>
    </View>
  );
}

export default function Home() {
  const { user } = useAuth();
  const { t } = useI18n();
  const { online, pending, needsAttention, syncNow, syncing } = useSync();
  const { colors } = useTheme();
  const router = useRouter();
  const [items, setItems] = useState<Complaint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => { setError(null); try { setItems((await endpoints.listComplaints()).items); } catch (e: any) { setError(e?.message ?? 'Could not load complaints.'); } }, []);
  useEffect(() => { load(); }, [load]);
  const open = items?.filter((c) => !['resolved', 'closed', 'rejected'].includes(c.status)).length ?? 0;
  const resolved = items?.filter((c) => ['resolved', 'closed'].includes(c.status)).length ?? 0;
  const atRisk = items?.filter((c) => c.escalation_level > 0).length ?? 0;
  const pillars = useMemo(() => buildPillars(colors), [colors]);

  return (
    <Screen>
      <View style={{ backgroundColor: colors.primary, borderRadius: radius.lg, padding: 18, gap: 10 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: 'rgba(255,255,255,0.16)', alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="shield-checkmark" size={22} color="#fff" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 12 }}>{t('welcomeBack')}</Text>
            <Text style={{ color: '#fff', fontSize: 18, fontWeight: '800' }}>{user?.full_name || user?.email}</Text>
          </View>
        </View>
        {items ? (
          <View style={{ flexDirection: 'row', borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.2)', paddingTop: 10 }}>
            <Stat label={t('card.active')} value={open} />
            <Stat label={t('card.resolved')} value={resolved} />
            <Stat label={t('card.escalated')} value={atRisk} color={atRisk > 0 ? '#FFD9A0' : '#fff'} />
          </View>
        ) : null}
      </View>

      {!online ? <ErrorBanner message="You are offline. Drafts are kept on this device and sent when you reconnect." /> : null}
      {pending + needsAttention > 0 ? (<Card><Body>{pending} waiting to send · {needsAttention} need your attention</Body><AppButton label={t('act.sync')} kind="secondary" onPress={syncNow} busy={syncing} disabled={!online} /></Card>) : null}

      <Text style={{ fontWeight: '800', color: colors.text, fontSize: 15, marginTop: 4 }}>Everything a citizen needs</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        {pillars.map((p) => <PillarCard key={p.title} p={p} colors={colors} onPress={() => router.push(p.href as any)} />)}
      </View>

      <Text style={{ fontWeight: '800', color: colors.text, fontSize: 15, marginTop: 4 }}>{t('nav.grievances')}</Text>
      {error ? <ErrorBanner message={error} onRetry={load} /> : items === null ? <Loading label={t('msg.loading')} /> : items.length === 0 ? <EmptyState message={t('msg.empty_complaints')} /> : (
        items.slice(0, 5).map((c) => (
          <Pressable key={c.id} accessibilityRole="button" onPress={() => router.push(`/complaint/${c.id}`)}>
            <Card>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ fontWeight: '700', color: colors.text }}>{c.reference}</Text>
                <StatusBadge status={c.status} />
              </View>
              <Body soft numberOfLines={2}>{c.original_text.slice(0, 140)}</Body>
            </Card>
          </Pressable>
        ))
      )}
      {items && items.length > 5 ? <AppButton label={t('act.view_all')} kind="secondary" onPress={() => router.push('/(tabs)/track')} /> : null}
    </Screen>
  );
}
