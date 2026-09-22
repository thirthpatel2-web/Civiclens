// CivicLens Classic - Home Dashboard, ported section-by-section from legacy-prototype's
// HomeScreen.js (same layout, same style names/structure) but wired to real data throughout:
// the "AI classification" is the real IntentRouter (/assistant/route), the "city pulse" is the
// citizen's own real filing history (/dashboards/citizen), notifications and helplines are real
// endpoints. Two zip concepts have no real backend counterpart and are honestly substituted rather
// than faked: "Fragmentation Diagnostic" -> Monitoring (real integration-health diagnostics), and
// the zip's local classifier -> the real rules-based IntentRouter.
import React, { useEffect, useState } from 'react';
import { Linking, Modal, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Screen } from '../../src/components/ui.tsx';
import { useAuth } from '../../src/auth/AuthContext.tsx';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useTheme } from '../../src/theme/ThemeContext.tsx';
import { UI_LANGUAGES, LANGUAGES } from '../../src/i18n/languages.ts';
import { useVoiceInput } from '../../src/hooks/useVoiceInput.ts';
import { isOnline } from '../../src/offline/SyncContext.tsx';
import { endpoints } from '../../src/api/instance.ts';
import type { AssistantDestination, AssistantRouteResult, CitizenDashboard, DirectoryData, Helpline, NotificationItem } from '../../src/api/types.ts';
import { fontFamily, radius, shadow, spacing, withAlpha } from '../../src/theme.ts';

const CITY_KEY = 'civiclens.classic.city';

const DEST: Record<AssistantDestination, { icon: keyof typeof Ionicons.glyphMap; label: string; href: string }> = {
  complaint: { icon: 'document-text', label: 'Civic Complaint', href: '/(tabs)/report?tab=civic' },
  rti: { icon: 'business', label: 'RTI Application', href: '/(tabs)/report?tab=rti' },
  legal: { icon: 'scale', label: 'Case Analyzer', href: '/legal' },
  track: { icon: 'analytics', label: 'Track Grievance', href: '/(tabs)/track' },
  document: { icon: 'scan', label: 'Document Scanner', href: '/documents' },
  map: { icon: 'map', label: 'Civic Heatmap', href: '/map' },
  locator: { icon: 'navigate', label: 'Civic Locator', href: '/locator' },
  emergency: { icon: 'medkit', label: 'Emergency Hub', href: '/emergency' },
};

export default function HomeScreen() {
  const { user, signOut } = useAuth();
  const { t, lang, setLang } = useI18n();
  const { colors, mode, resolvedMode, setMode } = useTheme();
  const router = useRouter();
  const voice = useVoiceInput('auto', isOnline);

  const [searchQuery, setSearchQuery] = useState('');
  const [classified, setClassified] = useState<AssistantRouteResult | null>(null);
  const [classifying, setClassifying] = useState(false);
  const [voiceOpen, setVoiceOpen] = useState(false);

  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [notifPanel, setNotifPanel] = useState(false);
  const unreadCount = notifications.filter((n) => !n.read_at).length;

  const [directory, setDirectory] = useState<DirectoryData | null>(null);
  const [selectedCity, setSelectedCity] = useState<string | null>(null);

  const [dashboard, setDashboard] = useState<CitizenDashboard | null>(null);
  const [helplines, setHelplines] = useState<Helpline[]>([]);

  useEffect(() => { endpoints.notifications().then((r) => setNotifications(r.items)).catch(() => undefined); }, []);
  useEffect(() => { endpoints.directory().then(setDirectory).catch(() => undefined); }, []);
  useEffect(() => { endpoints.citizenDashboard().then(setDashboard).catch(() => undefined); }, []);
  useEffect(() => { endpoints.helplines(lang).then((r) => setHelplines(r.items)).catch(() => undefined); }, [lang]);
  useEffect(() => { AsyncStorage.getItem(CITY_KEY).then((c: string | null) => { if (c) setSelectedCity(c); }); }, []);
  useEffect(() => {
    if (!directory || selectedCity) return;
    if (directory.cities[0]) setSelectedCity(directory.cities[0].code);
  }, [directory, selectedCity]);

  function pickCity(code: string) {
    setSelectedCity(code);
    AsyncStorage.setItem(CITY_KEY, code).catch(() => undefined);
  }

  async function markRead(id: string) {
    await endpoints.markRead(id).catch(() => undefined);
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n)));
  }

  async function classify(text: string) {
    if (text.trim().length < 4) { setClassified(null); return; }
    setClassifying(true);
    try { setClassified(await endpoints.assistantRoute(text)); }
    catch { setClassified(null); }
    finally { setClassifying(false); }
  }
  useEffect(() => { const id = setTimeout(() => classify(searchQuery), 500); return () => clearTimeout(id); }, [searchQuery]); // eslint-disable-line react-hooks/exhaustive-deps

  // Voice search: transcription lands in voice.state.kind === 'review'; feed it straight into search.
  const [handledVoiceUri, setHandledVoiceUri] = useState<string | null>(null);
  if (voice.state.kind === 'review' && voice.state.audioUri !== handledVoiceUri) {
    setHandledVoiceUri(voice.state.audioUri);
    setSearchQuery(voice.state.text);
    setVoiceOpen(false);
  }

  function executeClassification() {
    if (!classified) return;
    router.push(DEST[classified.destination].href as any);
    setClassified(null); setSearchQuery('');
  }

  const cityName = directory?.cities.find((c) => c.code === selectedCity)?.name ?? selectedCity ?? '';
  const resolutionRate = dashboard && dashboard.total > 0 ? `${Math.round((dashboard.resolved / dashboard.total) * 100)}%` : '—';

  return (
    <Screen>
      {/* 1. Top header: identity + quick actions ------------------------------------------------ */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
            <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.full, backgroundColor: colors.primaryGlow }}>
              <Text style={{ fontSize: 9, fontWeight: '800', letterSpacing: 0.3, color: colors.primaryLight }}>🇮🇳 {t('citizenPortal') || 'CITIZEN PORTAL'}</Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.accentEmerald }} />
              <Text style={{ fontSize: 9, color: colors.accentEmerald, fontWeight: '800' }}>LIVE</Text>
            </View>
          </View>
          <Text numberOfLines={1} style={{ fontFamily: fontFamily.displayBold, fontSize: 18, color: colors.text, letterSpacing: -0.3 }}>{user?.full_name || user?.email}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Pressable accessibilityRole="button" accessibilityLabel="Toggle theme" onPress={() => setMode(mode === 'system' ? 'light' : mode === 'light' ? 'dark' : 'system')}
            style={{ width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card }}>
            <Ionicons name={resolvedMode === 'dark' ? 'sunny' : 'moon'} size={16} color={resolvedMode === 'dark' ? colors.accentSaffron : colors.primary} />
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Notifications" onPress={() => setNotifPanel(true)}
            style={{ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card }}>
            <Ionicons name="notifications-outline" size={18} color={colors.text} />
            {unreadCount > 0 ? (
              <View style={{ position: 'absolute', top: -2, right: -2, backgroundColor: colors.bad, borderRadius: 8, minWidth: 16, height: 16, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 3 }}>
                <Text style={{ color: '#fff', fontSize: 9, fontWeight: '800' }}>{unreadCount > 9 ? '9+' : unreadCount}</Text>
              </View>
            ) : null}
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Settings" onPress={() => router.push('/settings')}
            style={{ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary }}>
            <Text style={{ color: '#fff', fontSize: 15, fontWeight: '900' }}>{(user?.full_name || user?.email || 'C').trim().charAt(0).toUpperCase()}</Text>
          </Pressable>
        </View>
      </View>

      <Modal visible={notifPanel} animationType="slide" transparent onRequestClose={() => setNotifPanel(false)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' }}>
          <View style={{ backgroundColor: colors.card, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, borderWidth: 1, borderColor: colors.border, padding: spacing.md, maxHeight: '75%' }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <Text style={{ fontSize: 16, fontWeight: '800', color: colors.text }}>Notifications</Text>
              <Pressable accessibilityRole="button" onPress={() => setNotifPanel(false)}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
            </View>
            <ScrollView style={{ maxHeight: 400 }}>
              {notifications.length === 0 ? (
                <Text style={{ fontSize: 12, lineHeight: 18, paddingVertical: 20, textAlign: 'center', color: colors.textMuted }}>No notifications yet. You'll see one here the instant an official updates a filing you made.</Text>
              ) : notifications.map((n) => (
                <Pressable key={n.id} accessibilityRole="button" onPress={() => markRead(n.id)} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingVertical: 10, opacity: n.read_at ? 0.6 : 1 }}>
                  <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text }}>{n.title}</Text>
                  <Text style={{ fontSize: 11.5, marginTop: 2, color: colors.textSoft }}>{n.body}</Text>
                  <Text style={{ fontSize: 9.5, marginTop: 4, color: colors.textMuted }}>{new Date(n.created_at).toLocaleString('en-IN')}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* 1-tap language row -------------------------------------------------------------------- */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingVertical: 2 }}>
        {UI_LANGUAGES.map((code) => {
          const selected = lang === code;
          return (
            <Pressable key={code} accessibilityRole="button" onPress={() => setLang(code)}
              style={{ paddingVertical: 4, paddingHorizontal: 11, borderRadius: radius.full, borderWidth: 1, backgroundColor: selected ? colors.primary : colors.card, borderColor: selected ? colors.primary : colors.border }}>
              <Text style={{ fontSize: 11, color: selected ? '#fff' : colors.textSoft, fontWeight: selected ? '800' : '600' }}>{LANGUAGES[code].native}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {/* 2. AI search + voice --------------------------------------------------------------------- */}
      <View style={[{ backgroundColor: colors.card, borderRadius: radius.xl, padding: spacing.sm, borderWidth: 1, borderColor: colors.border, gap: 6 }, shadow.sm]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceElevated, paddingHorizontal: spacing.sm, height: 44 }}>
          <Ionicons name="search" size={16} color={colors.textMuted} style={{ marginRight: 6 }} />
          <TextInput
            style={{ flex: 1, fontFamily: fontFamily.body, fontSize: 13, height: '100%', color: colors.text }}
            placeholder="Describe your issue, in any language..." placeholderTextColor={colors.textMuted}
            value={searchQuery} onChangeText={setSearchQuery} returnKeyType="search"
          />
          {searchQuery.length > 0 ? (
            <Pressable accessibilityRole="button" onPress={() => { setSearchQuery(''); setClassified(null); }} style={{ padding: 4, marginRight: 2 }}>
              <Ionicons name="close-circle" size={16} color={colors.textMuted} />
            </Pressable>
          ) : null}
          <Pressable accessibilityRole="button" accessibilityLabel="Speak" onPress={() => { setVoiceOpen(true); voice.start(); }} style={{ width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary }}>
            <Ionicons name="mic" size={16} color="#fff" />
          </Pressable>
        </View>

        {voiceOpen ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            {voice.state.kind === 'recording' ? (<><Ionicons name="radio-button-on" size={12} color={colors.bad} /><Text style={{ fontSize: 11, color: colors.bad, flex: 1 }}>Listening…</Text><Pressable onPress={voice.stop}><Text style={{ color: colors.primary, fontWeight: '700', fontSize: 12 }}>Stop</Text></Pressable></>)
              : voice.state.kind === 'transcribing' ? <Text style={{ fontSize: 11, color: colors.textMuted }}>Converting to text…</Text>
              : voice.state.kind === 'error' ? <Text style={{ fontSize: 11, color: colors.bad }}>{voice.state.message}</Text>
              : null}
          </View>
        ) : null}

        {classifying ? <Text style={{ fontSize: 11, color: colors.textMuted }}>🤖 Thinking…</Text> : classified ? (
          <View>
            <Pressable accessibilityRole="button" onPress={executeClassification}
              style={{ marginTop: 6, padding: 8, borderRadius: radius.md, borderWidth: 1, flexDirection: 'row', alignItems: 'center', backgroundColor: colors.primaryGlow, borderColor: colors.primary }}>
              <Ionicons name={DEST[classified.destination].icon} size={18} color={colors.primaryLight} style={{ marginRight: 6 }} />
              <View style={{ flex: 1, paddingRight: 6 }}>
                <Text style={{ fontSize: 11, fontWeight: '800', color: colors.primaryLight }}>{DEST[classified.destination].label}</Text>
                <Text numberOfLines={1} style={{ fontSize: 10, color: colors.textSoft }}>{classified.explanation}</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.full, backgroundColor: colors.primary }}>
                <Text style={{ color: '#fff', fontSize: 10, fontWeight: '700' }}>Take me there</Text>
                <Ionicons name="arrow-forward" size={11} color="#fff" style={{ marginLeft: 3 }} />
              </View>
            </Pressable>
            {!classified.certain && classified.alternatives.length > 0 ? (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 6, marginTop: 6, paddingHorizontal: 2 }}>
                <Text style={{ fontSize: 10.5, color: colors.textMuted, marginRight: 2 }}>Not quite right?</Text>
                {classified.alternatives.map((d) => (
                  <Pressable key={d} accessibilityRole="button" onPress={() => router.push(DEST[d].href as any)} style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.full, borderWidth: 1, borderColor: colors.border }}>
                    <Text style={{ fontSize: 10, fontWeight: '600', color: colors.textSoft }}><Ionicons name={DEST[d].icon} size={10} /> {DEST[d].label}</Text>
                  </Pressable>
                ))}
              </View>
            ) : null}
          </View>
        ) : null}
      </View>

      {/* 3. Quick services -------------------------------------------------------------------------- */}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <QuickService icon="call" iconColor="#5568D6" bg="rgba(53,71,168,0.15)" label="Directory" sub="Departments" colors={colors} onPress={() => router.push('/directory')} />
        <QuickService icon="navigate" iconColor="#2E9E63" bg="rgba(46,158,99,0.15)" label="GPS Offices" sub="Nearest" colors={colors} onPress={() => router.push('/locator')} />
        <QuickService icon="scan" iconColor="#3B8FA8" bg="rgba(59,143,168,0.15)" label="OCR Scan" sub="Notices/FIR" colors={colors} onPress={() => router.push('/documents')} />
        <QuickService icon="scale" iconColor="#7A5FB0" bg="rgba(122,95,176,0.15)" label="Legal Guide" sub="Ask a question" colors={colors} onPress={() => router.push('/legal')} />
        <QuickService icon="chatbubbles" iconColor="#BF6B3D" bg="rgba(191,107,61,0.15)" label="Civic Saathi" sub="Ask anything" colors={colors} onPress={() => router.push('/(tabs)/copilot')} />
      </View>

      {/* 4. City selector -------------------------------------------------------------------------- */}
      {directory && directory.cities.length > 0 ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Text style={{ fontSize: 11, fontWeight: '700', textTransform: 'uppercase', color: colors.textMuted }}>City:</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {directory.cities.map((c) => {
              const selected = c.code === selectedCity;
              return (
                <Pressable key={c.code} accessibilityRole="button" onPress={() => pickCity(c.code)}
                  style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.full, borderWidth: 1, backgroundColor: selected ? colors.primary : colors.card, borderColor: selected ? colors.primary : colors.border }}>
                  <Text style={{ fontSize: 11, color: selected ? '#fff' : colors.textSoft, fontWeight: selected ? '700' : '500' }}>{c.name}</Text>
                </Pressable>
              );
            })}
          </ScrollView>
        </View>
      ) : null}

      {/* 5. Core pillars grid ------------------------------------------------------------------------ */}
      <View style={{ gap: 10 }}>
        <View style={{ flexDirection: 'row', gap: 10 }}>
          <Pillar icon="document-text" iconColor="#5568D6" bg="rgba(53,71,168,0.15)" title="File a Complaint" sub="AI-classified civic complaint, routed to the right department" tag="Statutory Letter" tagColor={colors.primaryLight} tagBg={colors.primaryGlow} colors={colors} onPress={() => router.push('/(tabs)/report?tab=civic')} />
          <Pillar icon="business" iconColor="#BF6B3D" bg="rgba(191,107,61,0.15)" title="File an RTI" sub="Section 6(1)/7(1) application with precision questionnaires" tag="RTI Act 2005" tagColor="#BF6B3D" tagBg="rgba(191,107,61,0.12)" colors={colors} onPress={() => router.push('/(tabs)/report?tab=rti')} />
        </View>
        <View style={{ flexDirection: 'row', gap: 10 }}>
          <Pillar icon="git-network" iconColor={colors.primaryLight} bg={colors.primaryGlow} title="Interoperability Layer" sub="Real government data formats normalized into one schema" tag="System Integration" tagColor={colors.primaryLight} tagBg={colors.primaryGlow} colors={colors} onPress={() => router.push('/interop')} />
          <Pillar icon="pulse" iconColor="#2E9E63" bg="rgba(46,158,99,0.15)" title="Integration Monitoring" sub="Live health of every connected government platform" tag="Data-Backed" tagColor="#2E9E63" tagBg="rgba(46,158,99,0.12)" colors={colors} onPress={() => router.push('/monitoring')} />
        </View>
        <View style={{ flexDirection: 'row', gap: 10 }}>
          <Pillar icon="analytics" iconColor="#EC4899" bg="rgba(236,72,153,0.15)" title="Track Grievance" sub="Every filing, its timeline and officer remarks in one place" tag="Unified Tracker" tagColor="#EC4899" tagBg="rgba(236,72,153,0.12)" colors={colors} onPress={() => router.push('/(tabs)/track')} />
          <Pillar icon="speedometer" iconColor="#BF6B3D" bg="rgba(191,107,61,0.15)" title="Officer Desk" sub="Department resolution queue - sign in with an officer account" tag="Govt Portal" tagColor="#BF6B3D" tagBg="rgba(191,107,61,0.15)" colors={colors} borderColor="#BF6B3D" onPress={async () => { await signOut(); router.replace('/(auth)/login'); }} />
        </View>
        <Text style={{ fontSize: 10, fontWeight: '800', letterSpacing: 0.8, color: colors.textMuted, marginTop: 4 }}>LEGAL RESOURCES</Text>
        <View style={{ flexDirection: 'row', gap: 10 }}>
          <Pillar icon="scale" iconColor="#7A5FB0" bg="rgba(122,95,176,0.15)" title="Case Analyzer" sub="Judicial outcome patterns & verified court precedents" tag="Precedents" tagColor="#7A5FB0" tagBg="rgba(122,95,176,0.12)" colors={colors} onPress={() => router.push('/legal')} />
          <Pillar icon="map" iconColor="#2E9E63" bg="rgba(46,158,99,0.15)" title="Community Heatmap" sub="Real report density from complaints citizens actually filed" tag="Real Data" tagColor="#2E9E63" tagBg="rgba(46,158,99,0.12)" colors={colors} onPress={() => router.push('/map')} />
        </View>
      </View>

      {/* 6. Civic pulse (real, personal - your own filings, not simulated city data) ------------------ */}
      <View style={[{ backgroundColor: colors.card, borderRadius: radius.xl, padding: spacing.sm, borderWidth: 1, borderColor: colors.border }, shadow.sm]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Ionicons name="stats-chart" size={16} color={colors.accentEmerald} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: colors.text }}>Your Civic Pulse</Text>
          </View>
          <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.full, backgroundColor: colors.primaryGlow }}>
            <Text style={{ fontSize: 10, fontWeight: '700', color: colors.primaryLight }}>{!dashboard ? '...' : dashboard.has_data ? `${dashboard.total} filed` : 'No data yet'}</Text>
          </View>
        </View>
        {!dashboard ? null : !dashboard.has_data ? (
          <Text style={{ fontSize: 11, color: colors.textMuted, textAlign: 'center', paddingVertical: 10 }}>You haven't filed anything yet. Report an issue or RTI and this dashboard reflects it instantly.</Text>
        ) : (
          <View style={{ flexDirection: 'row', gap: 6 }}>
            <MetricBox value={resolutionRate} label="Resolved" color={colors.accentEmerald} colors={colors} />
            <MetricBox value={String(dashboard.escalated)} label="Escalated" color={colors.accentRose} colors={colors} />
            <MetricBox value={dashboard.resolution_hours ? `${Math.round(dashboard.resolution_hours.mean / 24)}d` : '—'} label="Avg. response" color={colors.accentAmber} colors={colors} />
          </View>
        )}
      </View>

      {/* 7. Emergency helplines --------------------------------------------------------------------- */}
      <View>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          <Text style={{ fontSize: 12, fontWeight: '800', textTransform: 'uppercase', color: colors.text }}>🚨 Emergency Helplines</Text>
          <Pressable accessibilityRole="button" onPress={() => router.push('/directory')}><Text style={{ fontSize: 11, fontWeight: '700', color: colors.primaryLight }}>All departments →</Text></Pressable>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {helplines.map((h) => (
            <Pressable key={h.code} accessibilityRole="button" onPress={() => Linking.openURL(h.tel_uri)}
              style={{ width: 120, borderRadius: radius.lg, padding: 8, marginRight: 8, borderWidth: 1, alignItems: 'center', backgroundColor: colors.card, borderColor: colors.border }}>
              <Text style={{ fontSize: 20, marginBottom: 2 }}>📞</Text>
              <Text numberOfLines={1} style={{ fontSize: 10, fontWeight: '700', textAlign: 'center', marginBottom: 4, color: colors.text }}>{h.name}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.full, backgroundColor: colors.primaryGlow }}>
                <Ionicons name="call" size={11} color={colors.primaryLight} />
                <Text style={{ fontSize: 10, fontWeight: '800', color: colors.primaryLight }}>{h.number}</Text>
              </View>
            </Pressable>
          ))}
        </ScrollView>
      </View>

      {/* 8. Daily tip -------------------------------------------------------------------------------- */}
      <View style={{ borderRadius: radius.lg, padding: spacing.sm, borderWidth: 1, backgroundColor: colors.primaryGlow, borderColor: colors.primary }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
          <Ionicons name="bulb" size={18} color={colors.accentSaffron} />
          <Text style={{ fontSize: 10, fontWeight: '800', textTransform: 'uppercase', color: colors.accentSaffron }}>Daily Legal Right</Text>
        </View>
        <Text style={{ fontSize: 12, fontWeight: '800', marginBottom: 2, color: colors.text }}>Section 7(1), RTI Act 2005</Text>
        <Text style={{ fontSize: 11, lineHeight: 15, color: colors.textSoft }}>If your life or personal liberty is at risk, a Public Information Officer must reply within 48 hours - not the usual 30 days. Use the emergency toggle when filing an RTI for this.</Text>
      </View>
    </Screen>
  );
}

function QuickService({ icon, iconColor, bg, label, sub, colors, onPress }: { icon: keyof typeof Ionicons.glyphMap; iconColor: string; bg: string; label: string; sub: string; colors: { card: string; cardBorder?: string; border: string; text: string; textMuted: string }; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={{ flex: 1, borderRadius: radius.lg, paddingVertical: 10, paddingHorizontal: 4, alignItems: 'center', borderWidth: 1, backgroundColor: colors.card, borderColor: colors.border }}>
      <View style={{ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', marginBottom: 4, backgroundColor: bg }}>
        <Ionicons name={icon} size={18} color={iconColor} />
      </View>
      <Text style={{ fontSize: 10, fontWeight: '800', color: colors.text, textAlign: 'center' }}>{label}</Text>
      <Text style={{ fontSize: 8.5, marginTop: 1, color: colors.textMuted, textAlign: 'center' }}>{sub}</Text>
    </Pressable>
  );
}

function Pillar({ icon, iconColor, bg, title, sub, tag, tagColor, tagBg, colors, onPress, borderColor }: {
  icon: keyof typeof Ionicons.glyphMap; iconColor: string; bg: string; title: string; sub: string; tag: string; tagColor: string; tagBg: string;
  colors: { card: string; border: string; text: string; textSoft: string }; onPress: () => void; borderColor?: string;
}) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={[{ flex: 1, borderRadius: radius.xl, padding: spacing.sm, borderWidth: 1, backgroundColor: colors.card, borderColor: borderColor ?? colors.border }, shadow.sm]}>
      <View style={{ width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', marginBottom: 6, backgroundColor: bg }}>
        <Ionicons name={icon} size={22} color={iconColor} />
      </View>
      <Text style={{ fontFamily: fontFamily.bodyExtraBold, fontSize: 11, marginBottom: 2, lineHeight: 16, color: colors.text }}>{title}</Text>
      <Text numberOfLines={2} style={{ fontFamily: fontFamily.body, fontSize: 10, lineHeight: 14, marginBottom: 6, color: colors.textSoft }}>{sub}</Text>
      <View style={{ alignSelf: 'flex-start', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: tagBg }}>
        <Text style={{ fontSize: 9, fontWeight: '700', color: tagColor }}>{tag}</Text>
      </View>
    </Pressable>
  );
}

function MetricBox({ value, label, color, colors }: { value: string; label: string; color: string; colors: { surfaceElevated: string; textMuted: string } }) {
  return (
    <View style={{ flex: 1, borderRadius: radius.md, padding: 6, alignItems: 'center', backgroundColor: withAlpha(color, 0.08) }}>
      <Text style={{ fontSize: 15, fontWeight: '900', marginBottom: 1, color }}>{value}</Text>
      <Text style={{ fontSize: 9, fontWeight: '600', textAlign: 'center', color: colors.textMuted }}>{label}</Text>
    </View>
  );
}
