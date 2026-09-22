import React, { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { useVoiceInput } from '../hooks/useVoiceInput.ts';
import { AppButton, Body, Card, Chip, ErrorBanner, Field, InfoBanner, Loading } from './ui.tsx';
import { endpoints } from '../api/instance.ts';
import { LANGUAGES } from '../i18n/languages.ts';
import type { LanguageCode } from '../i18n/languages.ts';
import type { VoiceCapabilities } from '../api/types.ts';
import { offeredLanguages } from '../voice/voiceMachine.ts';
import { isOnline } from '../offline/SyncContext.tsx';
import { useI18n } from '../i18n/I18nContext.tsx';

export interface VoiceAccepted { text: string; voiceId: string; language: LanguageCode | null; detectedBy: string | null; edited: boolean }
interface Props { initialLanguage: LanguageCode; onAccept(v: VoiceAccepted): void; onQueueOffline?(audioUri: string, language: LanguageCode | 'auto'): void }

/** Speak -> text in the language spoken (native script). Shows the language, lets the citizen edit, and never translates. */
export function VoiceInput({ initialLanguage, onAccept, onQueueOffline }: Props) {
  const { t } = useI18n();
  const [caps, setCaps] = useState<VoiceCapabilities | null>(null);
  const [capsError, setCapsError] = useState<string | null>(null);
  const v = useVoiceInput(initialLanguage, isOnline);

  useEffect(() => { endpoints.voiceLanguages().then(setCaps).catch((e) => setCapsError(e?.message ?? 'Could not check voice support.')); }, []);

  if (capsError) return <InfoBanner tone="warn" message={`Voice input is unavailable right now (${capsError}). You can still type.`} />;
  if (!caps) return <Loading label={t('msg.loading')} />;
  if (caps.state !== 'CONFIGURED') return <InfoBanner tone="warn" message="Voice transcription is not configured on this server. You can still type your complaint." />;

  const offered = offeredLanguages(caps);
  const s = v.state;
  const langLabel = (l: LanguageCode | 'auto') => (l === 'auto' ? 'Auto-detect' : `${LANGUAGES[l].native} (${LANGUAGES[l].name})`);

  return (
    <Card>
      <Text accessibilityRole="header" style={{ fontWeight: '700', fontSize: 16 }}>🎤 Voice</Text>
      {s.kind === 'idle' || s.kind === 'error' || s.kind === 'review' || s.kind === 'queued_offline' ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          {offered.map((l) => <Chip key={l} label={langLabel(l)} selected={s.language === l} onPress={() => v.selectLanguage(l)} />)}
        </View>
      ) : null}
      {s.kind === 'idle' ? <AppButton label={`Speak — ${langLabel(s.language)}`} icon="🎤" onPress={v.start} /> : null}
      {s.kind === 'requesting_permission' ? <Loading label="Waiting for microphone permission…" /> : null}
      {s.kind === 'recording' ? (<View style={{ gap: 8 }}><Body>🔴 Listening… speak in {langLabel(s.language)}</Body><AppButton label="Stop" onPress={v.stop} /><AppButton label="Cancel" kind="secondary" onPress={v.cancel} /></View>) : null}
      {s.kind === 'transcribing' ? (<View><Loading label="Converting your speech to text…" /><AppButton label="Cancel" kind="secondary" onPress={v.cancel} /></View>) : null}
      {s.kind === 'queued_offline' ? (
        <View style={{ gap: 8 }}>
          <InfoBanner tone="warn" message="You are offline. The recording is saved on this device and will be converted to text when you are online. Nothing has been submitted." />
          {onQueueOffline ? <AppButton label="Save recording to this complaint" onPress={() => onQueueOffline(s.audioUri, s.language)} /> : null}
        </View>
      ) : null}
      {s.kind === 'error' ? (
        <View style={{ gap: 8 }}>
          <ErrorBanner message={s.message} />
          {!s.notConfigured ? <AppButton label={s.permissionDenied ? 'Try again' : 'Retry'} kind="secondary" onPress={v.retry} /> : null}
          <AppButton label="Speak again" onPress={v.start} />
        </View>
      ) : null}
      {s.kind === 'review' ? (
        <View style={{ gap: 8 }}>
          <Body soft>Language: {s.detected ? langLabel((s.detected as LanguageCode) in LANGUAGES ? (s.detected as LanguageCode) : 'en') : langLabel(s.language)}{s.detectedBy ? ` · detected by ${s.detectedBy}` : ''}</Body>
          <Field label="Transcription (edit if needed)" multiline value={s.text} onChangeText={v.edit} autoCorrect={false} />
          {s.warnings.map((w) => <InfoBanner key={w} tone="warn" message={w} />)}
          <Body soft>This is exactly what you said, in your language — it is not translated.</Body>
          <AppButton label="Use this text" onPress={() => onAccept({ text: s.text, voiceId: s.voiceId, language: s.detected && s.detected in LANGUAGES ? (s.detected as LanguageCode) : s.language === 'auto' ? null : s.language, detectedBy: s.detectedBy, edited: s.edited })} />
          <AppButton label="Record again" kind="secondary" onPress={v.start} />
        </View>
      ) : null}
    </Card>
  );
}
