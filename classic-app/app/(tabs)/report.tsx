// Unified "File a Request" screen: Civic Complaint and RTI Application share one screen with a
// segmented tab switcher, matching the legacy prototype's ComplaintScreen.js pattern - a citizen
// describes their issue once, picks Civic or RTI, and everything (category, department, RTI
// records checklist) is suggested inline instead of gating progress behind a wizard.
import React, { useEffect, useRef, useState } from 'react';
import { Image, Linking, Pressable, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { AppButton, Body, Card, Chip, Disclosure, ErrorBanner, Field, H1, InfoBanner, Screen } from '../../src/components/ui.tsx';
import { VoiceInput } from '../../src/components/VoiceInput.tsx';
import type { VoiceAccepted } from '../../src/components/VoiceInput.tsx';
import { LANGUAGES } from '../../src/i18n/languages.ts';
import type { LanguageCode } from '../../src/i18n/languages.ts';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useAuth } from '../../src/auth/AuthContext.tsx';
import { useSync } from '../../src/offline/SyncContext.tsx';
import { draftStore, persistLocalFile } from '../../src/offline/storage.ts';
import { newDraft } from '../../src/offline/queue.ts';
import type { ComplaintDraft } from '../../src/offline/queue.ts';
import { useDeviceLocation } from '../../src/hooks/useDeviceLocation.ts';
import { pickPhotos, takePhoto } from '../../src/hooks/usePhotos.ts';
import { endpoints } from '../../src/api/instance.ts';
import type { ClassifyPreview, RtiApplication, RtiCategory } from '../../src/api/types.ts';
import { fontFamily, radius, spacing } from '../../src/theme.ts';
import { useTheme } from '../../src/theme/ThemeContext.tsx';
import * as Crypto from 'expo-crypto';

const CATEGORIES = ['roads', 'water', 'electricity', 'sanitation', 'drainage', 'encroachment', 'police'];
const QUICK_EXAMPLE_KEYS = ['report.example.pothole', 'report.example.garbage', 'report.example.power', 'report.example.water'];

type Tab = 'civic' | 'rti';

export default function FileRequest() {
  const { t, lang } = useI18n();
  const { user } = useAuth();
  const { online, syncNow, reload } = useSync();
  const { colors } = useTheme();
  const router = useRouter();
  const params = useLocalSearchParams<{ tab?: string }>();
  const [activeTab, setActiveTab] = useState<Tab>(params.tab === 'rti' ? 'rti' : 'civic');

  // ---- shared: the issue, in the citizen's own words (voice or typed) ------------------------
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [language, setLanguage] = useState<LanguageCode>(lang);
  const [ward, setWard] = useState('');
  const [voice, setVoice] = useState<{ voiceId: string | null; transcript: string | null; audio: ComplaintDraft['audio'] }>({ voiceId: null, transcript: null, audio: null });

  function useExample(text: string) {
    setDescription(text);
    if (!title.trim()) setTitle(text.length > 60 ? `${text.slice(0, 57)}...` : text);
  }
  function onVoice(v: VoiceAccepted) {
    setDescription(v.text);
    if (!title.trim()) setTitle(v.text.length > 60 ? `${v.text.slice(0, 57)}...` : v.text);
    if (v.language) setLanguage(v.language);
    setVoice({ voiceId: v.voiceId || null, transcript: v.edited ? null : v.text, audio: null }); // web speech recognition has no server-side voice record, so its id is ''
  }
  async function onQueueOffline(uri: string, l: LanguageCode | 'auto') {
    const file = await persistLocalFile({ uri, name: 'voice.m4a', type: 'audio/mp4' });
    setVoice({ voiceId: null, transcript: null, audio: { file, language: l } });
  }

  // ---- civic complaint state -------------------------------------------------------------------
  const draftId = useRef(Crypto.randomUUID());
  const [category, setCategory] = useState<string | null>(null);
  const categoryTouched = useRef(false);
  const [files, setFiles] = useState<ComplaintDraft['attachments']>([]);
  const [suggestion, setSuggestion] = useState<ClassifyPreview | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const loc = useDeviceLocation();
  const [explainLoc, setExplainLoc] = useState(false);
  const [civicResult, setCivicResult] = useState<{ kind: 'sent'; reference: string } | { kind: 'queued' } | { kind: 'review' } | null>(null);
  const [civicBusy, setCivicBusy] = useState(false);
  const [civicError, setCivicError] = useState<string | null>(null);

  useEffect(() => {
    if (activeTab !== 'civic' || description.trim().length < 8) { setSuggestion(null); return; }
    const id = setTimeout(async () => {
      setSuggesting(true);
      try {
        const r = await endpoints.classifyPreview(title, description, ward || null);
        setSuggestion(r);
        if (!categoryTouched.current && r.category !== 'other') setCategory(r.category);
      } catch { /* preview is best-effort; submission still works without it */ }
      finally { setSuggesting(false); }
    }, 600);
    return () => clearTimeout(id);
  }, [activeTab, title, description]); // eslint-disable-line react-hooks/exhaustive-deps

  const buildDraft = (): ComplaintDraft => newDraft(draftId.current, new Date().toISOString(), {
    title: title.trim(), description, language, category, ward: ward.trim() || null,
    lat: loc.state.kind === 'ok' ? loc.state.lat : null, lng: loc.state.kind === 'ok' ? loc.state.lng : null,
    attachments: files, audio: voice.audio, voiceId: voice.voiceId, transcript: voice.transcript,
  });

  useEffect(() => {
    if (activeTab !== 'civic') return;
    if (!title && !description && files.length === 0 && !voice.audio) return;
    const id = setTimeout(() => { draftStore.save(buildDraft(), new Date().toISOString()).then(reload).catch(() => undefined); }, 800);
    return () => clearTimeout(id);
  }); // eslint-disable-line react-hooks/exhaustive-deps

  async function addPhoto(kind: 'camera' | 'library') {
    const picked = kind === 'camera' ? [await takePhoto()].filter(Boolean) as any[] : await pickPhotos();
    const persisted = await Promise.all(picked.map(persistLocalFile));
    setFiles((f) => [...f, ...persisted]);
  }

  async function submitCivic() {
    setCivicBusy(true); setCivicError(null);
    try {
      await draftStore.save(buildDraft(), new Date().toISOString());
      await draftStore.submit(draftId.current, new Date().toISOString());
      await reload();
      if (!online) { setCivicResult({ kind: 'queued' }); return; }
      await syncNow();
      const d = await draftStore.get(draftId.current);
      if (d?.status === 'synced' && d.serverId) { router.replace(`/complaint/${d.serverId}`); return; } // straight into the real result: department, priority, AI classification, timeline
      else if (d?.status === 'synced') setCivicResult({ kind: 'sent', reference: d.reference! });
      else if (d?.status === 'needs_review') setCivicResult({ kind: 'review' });
      else if (d?.status === 'failed') setCivicError(d.lastError ?? 'The server rejected the complaint.');
      else setCivicResult({ kind: 'queued' });
    } catch (e: any) { setCivicError(e?.message ?? 'Could not submit.'); }
    finally { setCivicBusy(false); }
  }

  // ---- RTI state ---------------------------------------------------------------------------------
  const [publicAuthority, setPublicAuthority] = useState('');
  const [rtiCategory, setRtiCategory] = useState<string | null>(null);
  const [categories, setCategories] = useState<RtiCategory[]>([]);
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [tenderRef, setTenderRef] = useState(''); const [timePeriod, setTimePeriod] = useState('');
  const [customQs, setCustomQs] = useState('');
  const [lifeOrLiberty, setLifeOrLiberty] = useState(false);
  const [applicantName, setApplicantName] = useState(user?.full_name ?? '');
  const [applicantAddress, setApplicantAddress] = useState('');
  const [preview, setPreview] = useState<string[]>([]);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [rtiItems, setRtiItems] = useState<RtiApplication[]>([]);
  const [rtiBusy, setRtiBusy] = useState(false);
  const [rtiError, setRtiError] = useState<string | null>(null);
  const [rtiDone, setRtiDone] = useState<RtiApplication | null>(null);

  useEffect(() => { endpoints.rtiCategories().then((r) => setCategories(r.categories)).catch(() => setCategories([])); }, []);
  useEffect(() => { endpoints.listRti().then((r) => setRtiItems(r.items)).catch(() => undefined); }, []);
  const activeRtiCategory = categories.find((c) => c.code === rtiCategory);

  const doPreview = React.useCallback(async () => {
    if (description.trim().length < 5) { setPreview([]); setPreviewError(null); return; }
    setPreviewing(true); setPreviewError(null);
    try {
      const recordsRequested = activeRtiCategory ? activeRtiCategory.default_records.filter((r) => checked[r]) : [];
      const r = await endpoints.previewRtiQuestions({
        subject: description, category: rtiCategory, location: ward || null, records_requested: recordsRequested,
        tender_reference: tenderRef || null, time_period: timePeriod || null,
        custom_questions: customQs.split('\n').map((s) => s.trim()).filter(Boolean),
      });
      setPreview(r.questions);
    } catch (e: any) { setPreview([]); setPreviewError(e?.message ?? 'Could not draft questions - the boilerplate statutory letter still works, or try a shorter description.'); }
    finally { setPreviewing(false); }
  }, [description, rtiCategory, activeRtiCategory, checked, ward, tenderRef, timePeriod, customQs]);

  useEffect(() => { if (activeTab !== 'rti') return; const id = setTimeout(doPreview, 600); return () => clearTimeout(id); }, [activeTab, doPreview]);

  async function submitRti() {
    setRtiBusy(true); setRtiError(null);
    try {
      const a = await endpoints.createRti({ subject: title || description.slice(0, 60), public_authority: publicAuthority, questions: preview, applicant_name: applicantName, applicant_address: applicantAddress, language: lang, life_or_liberty: lifeOrLiberty });
      await endpoints.generateRti(a.id);
      setRtiDone(a);
      const r = await endpoints.listRti(); setRtiItems(r.items);
    } catch (e: any) { setRtiError(e?.message + (e?.details ? ` ${JSON.stringify(e.details)}` : '')); }
    finally { setRtiBusy(false); }
  }

  if (civicResult) {
    return (
      <Screen>
        <H1>{civicResult.kind === 'sent' ? t('msg.saved') : t('msg.pending_sync')}</H1>
        {civicResult.kind === 'sent' ? <Card><Text style={{ fontSize: 20, fontWeight: '700', color: colors.text }}>{civicResult.reference}</Text><Body soft>Your complaint was received by CivicLens.</Body></Card> : null}
        {civicResult.kind === 'queued' ? <InfoBanner tone="warn" message="NOT SENT YET. Your complaint is saved on this device and will be sent automatically when the connection returns." /> : null}
        {civicResult.kind === 'review' ? <InfoBanner message="Your recording was converted to text. Open it in Track, check the text, then send." /> : null}
        <AppButton label={t('nav.grievances')} onPress={() => router.replace('/(tabs)/track')} />
      </Screen>
    );
  }

  const canSubmitCivic = title.trim().length >= 5 && (description.trim().length >= 10 || !!voice.audio);
  const canSubmitRti = title.trim().length >= 5 && publicAuthority.trim().length >= 2 && preview.length > 0 && applicantName.trim().length > 0 && applicantAddress.trim().length > 0;

  return (
    <Screen>
      <H1>{activeTab === 'civic' ? t('nav.report') : t('nav.rti')}</H1>
      <Body soft>{activeTab === 'civic' ? t('page.report_help') : "Describe what happened, in your own words or by voice. We'll turn it into a proper RTI Act, Section 6(1) application."}</Body>
      {!online ? <InfoBanner tone="warn" message="You are offline. You can write your complaint now; it will be sent when you are back online." /> : null}

      <View style={{ flexDirection: 'row', backgroundColor: colors.card, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: 4, gap: 4 }}>
        <TabButton label={t('nav.report')} selected={activeTab === 'civic'} onPress={() => setActiveTab('civic')} colors={colors} accent={colors.primary} />
        <TabButton label={t('nav.rti')} selected={activeTab === 'rti'} onPress={() => setActiveTab('rti')} colors={colors} accent={colors.accentSaffron} />
      </View>

      {rtiDone && activeTab === 'rti' ? (
        <Card style={{ borderColor: colors.ok, borderWidth: 1.5 }}>
          <Text style={{ fontWeight: '800', color: colors.ok }}>✓ RTI drafted</Text>
          <Body soft>Your statutory application was generated. Review it under My Grievances / Track and mark it as filed once you've submitted it to the department.</Body>
        </Card>
      ) : null}

      <Card>
        <Field label={t('lbl.title')} value={title} onChangeText={setTitle} maxLength={200} />
        <Field label={`${t('lbl.description')} (${LANGUAGES[language].native})`} value={description} onChangeText={setDescription} multiline maxLength={5000} />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {QUICK_EXAMPLE_KEYS.map((key) => {
            const ex = t(key);
            return (
              <Pressable key={key} accessibilityRole="button" onPress={() => useExample(ex)} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: 10, paddingVertical: 6, maxWidth: 220 }}>
                <Text style={{ color: colors.textSoft, fontSize: 11 }} numberOfLines={1}>💡 {ex}</Text>
              </Pressable>
            );
          })}
        </View>
        <Text style={{ color: colors.textSoft, fontSize: 13 }}>{t('lbl.language')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{Object.values(LANGUAGES).map((l) => <Chip key={l.code} label={l.native} selected={language === l.code} onPress={() => setLanguage(l.code)} />)}</View>
      </Card>

      <VoiceInput initialLanguage={language} onAccept={onVoice} onQueueOffline={onQueueOffline} />
      {voice.audio ? <InfoBanner message="A voice recording is saved and will be converted to text when you are online." /> : null}

      {activeTab === 'civic' ? (
        <>
          <Card>
            {suggesting ? <Body soft>🤖 Reading your description…</Body> : suggestion ? (
              <View style={{ backgroundColor: colors.primaryGlow, borderRadius: radius.sm, padding: 10, gap: 2 }}>
                <Text style={{ fontWeight: '700', color: colors.primary }}>🤖 AI suggests: {suggestion.category} → {suggestion.department_name ?? 'unrouted (needs manual triage)'}</Text>
                <Body soft>{suggestion.explanation} {suggestion.severity !== 'medium' ? `· severity: ${suggestion.severity}` : ''}</Body>
              </View>
            ) : <Body soft>Describe the problem above to get an AI suggestion, or pick a category yourself below.</Body>}
            <Text style={{ fontWeight: '600', color: colors.text }}>{t('lbl.category')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{CATEGORIES.map((c) => <Chip key={c} label={c} selected={category === c} onPress={() => { categoryTouched.current = true; setCategory(category === c ? null : c); }} />)}</View>
            <Field label={t('lbl.ward')} value={ward} onChangeText={setWard} />
          </Card>

          <Card>
            <Text style={{ fontWeight: '600', color: colors.text }}>📍 {t('lbl.location')}</Text>
            {loc.state.kind === 'ok' ? (
              <View style={{ gap: 4 }}>
                {loc.state.addressLoading ? <Body soft>Looking up the address…</Body>
                  : loc.state.address ? (
                    <View style={{ gap: 2 }}>
                      {loc.state.address.area ? <Body>{loc.state.address.area}</Body> : null}
                      <Body soft>{[loc.state.address.city, loc.state.address.state, loc.state.address.pincode].filter(Boolean).join(', ') || loc.state.address.display_name}</Body>
                    </View>
                  ) : <Body soft>Address lookup unavailable - the exact coordinates below are still attached.</Body>}
                <Text style={{ color: colors.textMuted, fontSize: 11 }}>{loc.state.lat.toFixed(5)}, {loc.state.lng.toFixed(5)}{loc.state.accuracy ? ` · accuracy ±${Math.round(loc.state.accuracy)} m` : ''}</Text>
              </View>
            ) : loc.state.kind === 'denied' ? <InfoBanner tone="warn" message="Location permission was denied. You can still submit without a location." />
              : loc.state.kind === 'error' ? <ErrorBanner message={loc.state.message} /> : <Body soft>No location attached.</Body>}
            {explainLoc ? <Body soft>Your location is read once, only now, and attached to this complaint so officials can find the problem.</Body> : null}
            <AppButton label="Use my location" kind="secondary" busy={loc.state.kind === 'locating'} onPress={() => { setExplainLoc(true); loc.request(); }} />
            {loc.state.kind === 'ok' ? <AppButton label="Remove location" kind="secondary" onPress={loc.clear} /> : null}
          </Card>

          <Disclosure label={`📷 ${t('lbl.evidence')} (optional)`}>
            <View style={{ gap: 8 }}>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>{files.map((f) => <Image key={f.uri} source={{ uri: f.uri }} style={{ width: 72, height: 72, borderRadius: 8 }} accessibilityLabel={f.name} />)}</View>
              <AppButton label="Take a photo" kind="secondary" onPress={() => addPhoto('camera')} />
              <AppButton label="Choose from gallery" kind="secondary" onPress={() => addPhoto('library')} />
            </View>
          </Disclosure>

          {civicError ? <ErrorBanner message={civicError} /> : null}
          <AppButton label={online ? t('act.submit') : 'Save to send later'} icon="➤" onPress={submitCivic} busy={civicBusy} disabled={!canSubmitCivic} />
          <Pressable accessibilityRole="button" onPress={() => Linking.openURL('https://pgportal.gov.in')}
            style={{ flexDirection: 'row', alignItems: 'center', padding: 12, borderRadius: radius.md, borderWidth: 1, backgroundColor: colors.surfaceElevated, borderColor: colors.border }}>
            <Ionicons name="open-outline" size={16} color={colors.textSoft} />
            <View style={{ flex: 1, marginLeft: 8 }}>
              <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text }}>File directly on CPGRAMS instead</Text>
              <Text style={{ fontSize: 10.5, marginTop: 2, color: colors.textMuted }}>The Govt of India's own Centralized Public Grievance Redress portal - separate from this app, opens in a new tab</Text>
            </View>
          </Pressable>
        </>
      ) : (
        <>
          <View style={{ borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, backgroundColor: colors.primaryGlow, borderColor: colors.primary, gap: 4 }}>
            <Text style={{ fontSize: 13, fontWeight: '800', color: colors.text }}>💡 What is an RTI?</Text>
            <Body soft>{t('rti.plain.intro')}</Body>
          </View>

          <Card>
            <Field label={t('selectDepartment')} value={publicAuthority} onChangeText={setPublicAuthority} placeholder="e.g. BBMP Roads Department" />
            <Text style={{ color: colors.textSoft, fontSize: 13 }}>Category (optional - loads the records this kind of RTI usually needs)</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{categories.map((c) => <Chip key={c.code} label={c.code} selected={rtiCategory === c.code} onPress={() => { setRtiCategory(rtiCategory === c.code ? null : c.code); setChecked({}); }} />)}</View>
            {activeRtiCategory ? (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{activeRtiCategory.default_records.map((rec) => <Chip key={rec} label={rec} selected={!!checked[rec]} onPress={() => setChecked((m) => ({ ...m, [rec]: !m[rec] }))} />)}</View>
            ) : null}
            <Disclosure label="More details (optional)">
              <View style={{ gap: 8 }}>
                <Field label="Tender / Work Order number (if known)" value={tenderRef} onChangeText={setTenderRef} />
                <Field label="Time period covered (e.g. Jan 2024 - Mar 2024)" value={timePeriod} onChangeText={setTimePeriod} />
                <Field label="Additional questions of your own (one per line)" value={customQs} onChangeText={setCustomQs} multiline />
              </View>
            </Disclosure>
            <Pressable accessibilityRole="button" onPress={() => setLifeOrLiberty((v) => !v)} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: lifeOrLiberty ? `${colors.bad}1f` : colors.surfaceElevated, borderWidth: 1, borderColor: lifeOrLiberty ? colors.bad : colors.border, borderRadius: radius.md, padding: 10 }}>
              <View style={{ width: 20, height: 20, borderRadius: 5, borderWidth: 2, borderColor: lifeOrLiberty ? colors.bad : colors.border, backgroundColor: lifeOrLiberty ? colors.bad : 'transparent' }} />
              <View style={{ flex: 1 }}>
                <Text style={{ fontWeight: '700', color: lifeOrLiberty ? colors.bad : colors.text, fontSize: 13 }}>🚨 48-hour emergency proviso (Section 7(1))</Text>
                <Text style={{ color: colors.textMuted, fontSize: 11 }}>Mandates a reply within 48 hours for life & safety risks, instead of 30 days.</Text>
              </View>
            </Pressable>
          </Card>

          {previewing ? <Body soft>🤖 Building your statutory questions…</Body> : previewError ? <ErrorBanner message={previewError} /> : preview.length > 0 ? (
            <Card>
              <Body soft>Statutory questions this RTI will ask ({preview.length})</Body>
              <Body soft style={{ fontSize: 11.5, fontStyle: 'italic' }}>{t('rti.plain.questions_why')}</Body>
              {preview.map((q, i) => <Body key={i}>{i + 1}. {q}</Body>)}
            </Card>
          ) : null}

          <Card>
            <Field label={t('fullName')} value={applicantName} onChangeText={setApplicantName} />
            <Field label={t('residentialAddress')} value={applicantAddress} onChangeText={setApplicantAddress} multiline />
            {rtiError ? <ErrorBanner message={rtiError} /> : null}
            <AppButton label={t('generateLetterBtn')} onPress={submitRti} busy={rtiBusy} disabled={!canSubmitRti} />
          </Card>

          <Pressable accessibilityRole="button" onPress={() => Linking.openURL('https://rtionline.gov.in')}
            style={{ flexDirection: 'row', alignItems: 'center', padding: 12, borderRadius: radius.md, borderWidth: 1, backgroundColor: colors.surfaceElevated, borderColor: colors.border }}>
            <Ionicons name="open-outline" size={16} color={colors.textSoft} />
            <View style={{ flex: 1, marginLeft: 8 }}>
              <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text }}>File directly on RTI Online instead</Text>
              <Text style={{ fontSize: 10.5, marginTop: 2, color: colors.textMuted }}>The Govt of India's own RTI portal for central authorities - separate from this app, opens in a new tab</Text>
            </View>
          </Pressable>

          {rtiItems.length > 0 ? (
            <>
              <Text style={{ fontWeight: '700', color: colors.text, marginTop: 8 }}>Your RTI applications</Text>
              {rtiItems.map((a) => (
                <Card key={a.id}>
                  <Text style={{ fontWeight: '700', color: colors.text }}>{a.reference ?? 'draft'} · {a.status}</Text>
                  <Body>{a.draft.subject}</Body>
                  {a.due_at ? <Body soft>Deadline: {new Date(a.due_at).toLocaleDateString()}</Body> : null}
                  {a.generated_text ? (
                    <Disclosure label="View the generated RTI letter" defaultOpen>
                      <View style={{ borderRadius: radius.md, padding: 12, backgroundColor: colors.surfaceElevated, borderWidth: 1, borderColor: colors.border }}>
                        <Text selectable style={{ fontFamily: fontFamily.body, fontSize: 13, lineHeight: 19, color: colors.text }}>{a.generated_text}</Text>
                      </View>
                      <AppButton
                        label="Copy letter text" kind="secondary"
                        onPress={() => {
                          const nav: any = typeof navigator !== 'undefined' ? navigator : null;
                          if (nav?.clipboard?.writeText) nav.clipboard.writeText(a.generated_text ?? '');
                        }}
                      />
                    </Disclosure>
                  ) : a.status === 'generated' ? <Body soft>The letter was generated but its text isn't available - try regenerating.</Body> : null}
                  {a.status === 'generated' ? <AppButton label="Mark as filed" kind="secondary" onPress={async () => { await endpoints.fileRti(a.id); const r = await endpoints.listRti(); setRtiItems(r.items); }} /> : null}
                </Card>
              ))}
            </>
          ) : null}
        </>
      )}
    </Screen>
  );
}

function TabButton({ label, selected, onPress, colors, accent }: { label: string; selected: boolean; onPress: () => void; colors: { textMuted: string; textSoft: string }; accent: string }) {
  return (
    <Pressable accessibilityRole="button" accessibilityState={{ selected }} onPress={onPress} style={{ flex: 1, alignItems: 'center', justifyContent: 'center', minHeight: 40, borderRadius: radius.sm, backgroundColor: selected ? accent : 'transparent' }}>
      <Text style={{ color: selected ? '#fff' : colors.textSoft, fontWeight: '700', fontSize: 13 }}>{label}</Text>
    </Pressable>
  );
}
