import React, { useEffect, useRef, useState } from 'react';
import { Image, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { AppButton, Body, Card, Chip, ErrorBanner, Field, H1, InfoBanner, Screen, StepProgress } from '../../src/components/ui.tsx';
import { VoiceInput } from '../../src/components/VoiceInput.tsx';
import type { VoiceAccepted } from '../../src/components/VoiceInput.tsx';
import { LANGUAGES } from '../../src/i18n/languages.ts';
import type { LanguageCode } from '../../src/i18n/languages.ts';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { useSync } from '../../src/offline/SyncContext.tsx';
import { draftStore, persistLocalFile } from '../../src/offline/storage.ts';
import { newDraft } from '../../src/offline/queue.ts';
import type { ComplaintDraft } from '../../src/offline/queue.ts';
import { useDeviceLocation } from '../../src/hooks/useDeviceLocation.ts';
import { pickPhotos, takePhoto } from '../../src/hooks/usePhotos.ts';
import { endpoints } from '../../src/api/instance.ts';
import type { ClassifyPreview } from '../../src/api/types.ts';
import { radius } from '../../src/theme.ts';
import { useTheme } from '../../src/theme/ThemeContext.tsx';
import * as Crypto from 'expo-crypto';

const CATEGORIES = ['roads', 'water', 'electricity', 'sanitation', 'drainage', 'encroachment', 'police'];
const TOTAL_STEPS = 3;
const STEP_TITLES = ['Describe the problem', 'Confirm category & location', 'Evidence & submit'];

export default function Report() {
  const { t, lang } = useI18n();
  const { online, syncNow, reload } = useSync();
  const { colors } = useTheme();
  const router = useRouter();
  const draftId = useRef(Crypto.randomUUID()); // also the server client_request_id: resubmission can never duplicate
  const [step, setStep] = useState(1);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [language, setLanguage] = useState<LanguageCode>(lang);
  const [category, setCategory] = useState<string | null>(null);
  const [ward, setWard] = useState('');
  const [files, setFiles] = useState<ComplaintDraft['attachments']>([]);
  const [voice, setVoice] = useState<{ voiceId: string | null; transcript: string | null; audio: ComplaintDraft['audio'] }>({ voiceId: null, transcript: null, audio: null });
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ kind: 'sent'; reference: string } | { kind: 'queued' } | { kind: 'review' } | null>(null);
  const [busy, setBusy] = useState(false);
  const loc = useDeviceLocation();
  const [explainLoc, setExplainLoc] = useState(false);
  const categoryTouched = useRef(false);
  const [suggestion, setSuggestion] = useState<ClassifyPreview | null>(null);
  const [suggesting, setSuggesting] = useState(false);

  // Live "AI suggests..." preview as the citizen types or speaks - the same rules-only classifier
  // the real submission uses (app.services.classification_service), run read-only, nothing saved.
  useEffect(() => {
    if (description.trim().length < 8) { setSuggestion(null); return; }
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
  }, [title, description]); // eslint-disable-line react-hooks/exhaustive-deps

  const buildDraft = (): ComplaintDraft => newDraft(draftId.current, new Date().toISOString(), {
    title: title.trim(), description, language, category, ward: ward.trim() || null,
    lat: loc.state.kind === 'ok' ? loc.state.lat : null, lng: loc.state.kind === 'ok' ? loc.state.lng : null,
    attachments: files, audio: voice.audio, voiceId: voice.voiceId, transcript: voice.transcript,
  });

  // Auto-save the work in progress locally (survives app kills and dropped connections)
  useEffect(() => {
    if (!title && !description && files.length === 0 && !voice.audio) return;
    const id = setTimeout(() => { draftStore.save(buildDraft(), new Date().toISOString()).then(reload).catch(() => undefined); }, 800);
    return () => clearTimeout(id);
  }); // eslint-disable-line react-hooks/exhaustive-deps

  async function addPhoto(kind: 'camera' | 'library') {
    const picked = kind === 'camera' ? [await takePhoto()].filter(Boolean) as any[] : await pickPhotos();
    const persisted = await Promise.all(picked.map(persistLocalFile));
    setFiles((f) => [...f, ...persisted]);
  }

  function onVoice(v: VoiceAccepted) {
    setDescription(v.text); // the transcription IS the original text, in the spoken language
    if (v.language) setLanguage(v.language);
    setVoice({ voiceId: v.voiceId, transcript: v.edited ? null : v.text, audio: null });
  }
  async function onQueueOffline(uri: string, l: LanguageCode | 'auto') {
    const file = await persistLocalFile({ uri, name: 'voice.m4a', type: 'audio/mp4' });
    setVoice({ voiceId: null, transcript: null, audio: { file, language: l } });
  }

  async function submit() {
    setBusy(true); setError(null);
    try {
      await draftStore.save(buildDraft(), new Date().toISOString());
      await draftStore.submit(draftId.current, new Date().toISOString());
      await reload();
      if (!online) { setResult({ kind: 'queued' }); return; }
      await syncNow();
      const d = await draftStore.get(draftId.current);
      if (d?.status === 'synced') setResult({ kind: 'sent', reference: d.reference! });
      else if (d?.status === 'needs_review') { setResult({ kind: 'review' }); }
      else if (d?.status === 'failed') setError(d.lastError ?? 'The server rejected the complaint.');
      else setResult({ kind: 'queued' }); // still pending: server unreachable, will retry
    } catch (e: any) { setError(e?.message ?? 'Could not submit.'); }
    finally { setBusy(false); }
  }

  if (result) {
    return (
      <Screen>
        <H1>{result.kind === 'sent' ? t('msg.saved') : t('msg.pending_sync')}</H1>
        {result.kind === 'sent' ? <Card><Text style={{ fontSize: 20, fontWeight: '700', color: colors.text }}>{result.reference}</Text><Body soft>Your complaint was received by CivicLens.</Body></Card> : null}
        {result.kind === 'queued' ? <InfoBanner tone="warn" message="NOT SENT YET. Your complaint is saved on this device and will be sent automatically when the connection returns." /> : null}
        {result.kind === 'review' ? <InfoBanner message="Your recording was converted to text. Open it in Track, check the text, then send." /> : null}
        <AppButton label={t('nav.grievances')} onPress={() => router.replace('/(tabs)/track')} />
      </Screen>
    );
  }

  const step1Ok = title.trim().length >= 5 && (description.trim().length >= 10 || !!voice.audio);
  const nextDisabled = step === 1 && !step1Ok;

  return (
    <Screen>
      <H1>{t('nav.report')}</H1>
      <StepProgress step={step} total={TOTAL_STEPS} label={`${t('lbl.step_of', { current: step, total: TOTAL_STEPS })} · ${STEP_TITLES[step - 1]}`} />
      {!online ? <InfoBanner tone="warn" message="You are offline. You can write your complaint now; it will be sent when you are back online." /> : null}

      {step === 1 ? (
        <>
          <Body soft>{t('page.report_help')}</Body>
          <Card>
            <Field label={t('lbl.title')} value={title} onChangeText={setTitle} maxLength={200} />
            <Field label={`${t('lbl.description')} (${LANGUAGES[language].native})`} value={description} onChangeText={setDescription} multiline maxLength={5000} />
            <Text style={{ color: colors.textSoft, fontSize: 13 }}>{t('lbl.language')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{Object.values(LANGUAGES).map((l) => <Chip key={l.code} label={l.native} selected={language === l.code} onPress={() => setLanguage(l.code)} />)}</View>
          </Card>
          <VoiceInput initialLanguage={language} onAccept={onVoice} onQueueOffline={onQueueOffline} />
          {voice.audio ? <InfoBanner message="A voice recording is saved with this complaint and will be converted to text when you are online." /> : null}
        </>
      ) : null}

      {step === 2 ? (
        <>
          <Card>
            {suggesting ? <Body soft>🤖 Reading your description…</Body> : suggestion ? (
              <View style={{ backgroundColor: colors.primaryGlow, borderRadius: radius.sm, padding: 10, gap: 2 }}>
                <Text style={{ fontWeight: '700', color: colors.primary }}>🤖 AI suggests: {suggestion.category} → {suggestion.department_name ?? 'unrouted (needs manual triage)'}</Text>
                <Body soft>{suggestion.explanation} {suggestion.severity !== 'medium' ? `· severity: ${suggestion.severity}` : ''}</Body>
              </View>
            ) : <Body soft>Go back and describe the problem to get an AI suggestion, or pick a category yourself below.</Body>}
            <Text style={{ fontWeight: '600', color: colors.text }}>{t('lbl.category')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{CATEGORIES.map((c) => <Chip key={c} label={c} selected={category === c} onPress={() => { categoryTouched.current = true; setCategory(category === c ? null : c); }} />)}</View>
            <Field label={t('lbl.ward')} value={ward} onChangeText={setWard} />
          </Card>
          <Card>
            <Text style={{ fontWeight: '600', color: colors.text }}>📍 {t('lbl.location')}</Text>
            {loc.state.kind === 'ok' ? <Body>{loc.state.lat.toFixed(5)}, {loc.state.lng.toFixed(5)}{loc.state.accuracy ? ` (±${Math.round(loc.state.accuracy)} m)` : ''}</Body>
              : loc.state.kind === 'denied' ? <InfoBanner tone="warn" message="Location permission was denied. You can still submit without a location." />
              : loc.state.kind === 'error' ? <ErrorBanner message={loc.state.message} /> : <Body soft>No location attached.</Body>}
            {explainLoc ? <Body soft>Your location is read once, only now, and attached to this complaint so officials can find the problem.</Body> : null}
            <AppButton label="Use my location" kind="secondary" busy={loc.state.kind === 'locating'} onPress={() => { setExplainLoc(true); loc.request(); }} />
            {loc.state.kind === 'ok' ? <AppButton label="Remove location" kind="secondary" onPress={loc.clear} /> : null}
          </Card>
        </>
      ) : null}

      {step === 3 ? (
        <>
          <Card>
            <Text style={{ fontWeight: '600', color: colors.text }}>📷 {t('lbl.evidence')} (optional)</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>{files.map((f) => <Image key={f.uri} source={{ uri: f.uri }} style={{ width: 72, height: 72, borderRadius: 8 }} accessibilityLabel={f.name} />)}</View>
            <AppButton label="Take a photo" kind="secondary" onPress={() => addPhoto('camera')} />
            <AppButton label="Choose from gallery" kind="secondary" onPress={() => addPhoto('library')} />
          </Card>
          <Card>
            <Text style={{ fontWeight: '600', color: colors.text }}>Review</Text>
            <Body soft>{t('lbl.title')}</Body><Body>{title}</Body>
            <Body soft>{t('lbl.description')}</Body><Body numberOfLines={4}>{description || '(voice recording, converted when online)'}</Body>
            <Body soft>{t('lbl.category')} · {t('lbl.ward')}</Body><Body>{category ?? 'unset'} · {ward || '—'}</Body>
          </Card>
          {error ? <ErrorBanner message={error} /> : null}
          <AppButton label={online ? t('act.submit') : 'Save to send later'} icon="➤" onPress={submit} busy={busy} />
        </>
      ) : null}

      <View style={{ flexDirection: 'row', gap: 8 }}>
        {step > 1 ? <AppButton label={t('act.back')} kind="secondary" onPress={() => setStep((s) => s - 1)} /> : null}
        {step < TOTAL_STEPS ? <AppButton label={t('act.next')} onPress={() => setStep((s) => s + 1)} disabled={nextDisabled} /> : null}
      </View>
    </Screen>
  );
}
