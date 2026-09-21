import React, { useEffect, useState } from 'react';
import { Switch, Text, View } from 'react-native';
import { AppButton, Body, Card, Chip, H1, InfoBanner, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import { API_BASE_URL } from '../src/config.ts';
import { LANGUAGES, UI_LANGUAGES } from '../src/i18n/languages.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { useSync } from '../src/offline/SyncContext.tsx';
import { useTheme } from '../src/theme/ThemeContext.tsx';
import type { ThemeMode } from '../src/theme/ThemeContext.tsx';

const PURPOSES = ['ai_processing', 'data_sharing_government', 'document_storage', 'notifications_email'];
const MODES: ThemeMode[] = ['system', 'light', 'dark'];

export default function Settings() {
  const { t, lang, setLang } = useI18n();
  const { online, pending, needsAttention, syncNow, syncing, last } = useSync();
  const { colors, mode, resolvedMode, setMode } = useTheme();
  const [consents, setConsents] = useState<Record<string, { granted: boolean }> | null>(null);
  useEffect(() => { endpoints.consents().then(setConsents).catch(() => setConsents(null)); }, []);
  return (
    <Screen>
      <H1>{t('nav.settings')}</H1>
      <Card>
        <Text style={{ fontWeight: '600', color: colors.text }}>{t('lbl.appearance')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          {MODES.map((m) => (
            <Chip key={m} label={m === 'system' ? `${t('act.enable')} auto` : t(`theme.${m}`)} selected={mode === m} onPress={() => setMode(m)} />
          ))}
        </View>
        <Body soft>{mode === 'system' ? `Following your device (currently ${resolvedMode}).` : `Always ${resolvedMode}.`}</Body>
      </Card>
      <Card>
        <Text style={{ fontWeight: '600', color: colors.text }}>{t('lang.select')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{UI_LANGUAGES.map((l) => <Chip key={l} label={LANGUAGES[l].native} selected={lang === l} onPress={() => setLang(l)} />)}</View>
        <Body soft>Screens not yet translated into your language are shown in English.</Body>
      </Card>
      <Card>
        <Text style={{ fontWeight: '600', color: colors.text }}>Privacy & consent</Text>
        {consents ? PURPOSES.map((p) => (
          <View key={p} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', minHeight: 48 }}>
            <Text style={{ flex: 1, color: colors.text }}>{p.replace(/_/g, ' ')}</Text>
            <Switch value={!!consents[p]?.granted} trackColor={{ true: colors.primary }} onValueChange={async (v: boolean) => { setConsents({ ...consents, [p]: { granted: v } }); try { await endpoints.setConsent(p, v); } catch { setConsents(consents); } }} />
          </View>
        )) : <Body soft>Could not load consent settings.</Body>}
      </Card>
      <Card>
        <Text style={{ fontWeight: '600', color: colors.text }}>Synchronisation</Text>
        <Body>{online ? 'Online' : 'Offline'} · {pending} waiting · {needsAttention} need attention</Body>
        {last ? <Body soft>Last run: {last.synced.length} sent, {last.failed.length} failed, {last.needsReview.length} to review</Body> : null}
        <AppButton label={t('act.sync')} kind="secondary" onPress={syncNow} busy={syncing} disabled={!online} />
      </Card>
      <InfoBanner message={`Server: ${API_BASE_URL || 'not configured'}`} />
    </Screen>
  );
}
