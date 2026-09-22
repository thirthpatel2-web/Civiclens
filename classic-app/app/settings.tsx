// Ported from legacy-prototype/src/screens/SettingsScreen.js (profile card, MFA enrollment card,
// theme/language cards, sign-out) - the MFA flow calls the real /auth/mfa/enroll + /confirm
// endpoints (app.services.mfa_service.MfaService), not the zip's Supabase-backed setupMfa/enableMfa.
import React, { useEffect, useState } from 'react';
import { Alert, Switch, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { AppButton, Body, Card, Chip, Field, InfoBanner, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import { API_BASE_URL } from '../src/config.ts';
import { LANGUAGES, UI_LANGUAGES } from '../src/i18n/languages.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { useAuth } from '../src/auth/AuthContext.tsx';
import { useSync } from '../src/offline/SyncContext.tsx';
import { useTheme } from '../src/theme/ThemeContext.tsx';
import type { ThemeMode } from '../src/theme/ThemeContext.tsx';
import { fontFamily } from '../src/theme.ts';

const PURPOSES = ['ai_processing', 'data_sharing_government', 'document_storage', 'notifications_email'];
const MODES: ThemeMode[] = ['system', 'light', 'dark'];

export default function Settings() {
  const { t, lang, setLang } = useI18n();
  const { user, signOut, refresh } = useAuth();
  const router = useRouter();
  const { online, pending, needsAttention, syncNow, syncing, last } = useSync();
  const { colors, mode, resolvedMode, setMode } = useTheme();
  const [consents, setConsents] = useState<Record<string, { granted: boolean }> | null>(null);
  useEffect(() => { endpoints.consents().then(setConsents).catch(() => setConsents(null)); }, []);

  // ---- profile ------------------------------------------------------------------------------
  const [name, setName] = useState(user?.full_name ?? '');
  const [city, setCity] = useState('');
  const [ward, setWard] = useState('');
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);
  async function saveProfile() {
    setSavingProfile(true);
    try { await endpoints.updateProfile({ full_name: name, city, ward }); await refresh(); setProfileSaved(true); setTimeout(() => setProfileSaved(false), 3000); }
    finally { setSavingProfile(false); }
  }

  // ---- MFA ------------------------------------------------------------------------------------
  const [mfaStep, setMfaStep] = useState<'idle' | 'enrolling' | 'confirm'>('idle');
  const [mfaSecret, setMfaSecret] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState('');
  const [mfaBusy, setMfaBusy] = useState(false);
  const [mfaError, setMfaError] = useState<string | null>(null);
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);

  async function startMfaEnroll() {
    setMfaStep('enrolling'); setMfaError(null);
    try { const r = await endpoints.mfaEnroll(); setMfaSecret(r.secret); setMfaStep('confirm'); }
    catch (e: any) { setMfaError(e?.message ?? 'Could not start enrollment.'); setMfaStep('idle'); }
  }
  async function confirmMfa() {
    if (mfaCode.trim().length < 6) { setMfaError('Enter the 6-digit code from your authenticator app.'); return; }
    setMfaBusy(true); setMfaError(null);
    try {
      const r = await endpoints.mfaConfirm(mfaCode.trim());
      setBackupCodes(r.backup_codes);
      setMfaStep('idle'); setMfaCode(''); setMfaSecret(null);
      await refresh();
    } catch (e: any) { setMfaError(e?.message ?? 'Invalid code.'); }
    finally { setMfaBusy(false); }
  }

  return (
    <Screen>
      <Text style={{ fontFamily: fontFamily.displayBold, fontSize: 20, color: colors.text }}>⚙️ {t('nav.settings')}</Text>
      <Body soft>Customize language, theme, and your citizen verification profile</Body>

      <Card>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="person-circle" size={22} color={colors.primary} />
          <Text style={{ fontFamily: fontFamily.bodyExtraBold, fontSize: 14, color: colors.text }}>Citizen Profile</Text>
        </View>
        <Body soft>These verified details are automatically formatted into your formal complaints & RTI applications.</Body>
        <Field label={t('fullName')} value={name} onChangeText={setName} />
        <Field label="City" value={city} onChangeText={setCity} />
        <Field label={t('lbl.ward')} value={ward} onChangeText={setWard} />
        <AppButton label={profileSaved ? 'Saved ✓' : 'Save Profile'} onPress={saveProfile} busy={savingProfile} />
      </Card>

      <Card style={{ borderColor: mode === 'dark' ? undefined : undefined }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="shield-checkmark" size={22} color={user?.mfa_enabled ? colors.ok : colors.accentSaffron} />
          <Text style={{ fontFamily: fontFamily.bodyExtraBold, fontSize: 14, color: colors.text }}>Two-Factor Authentication</Text>
        </View>
        {user?.mfa_enabled ? (
          <InfoBanner message="Two-factor authentication is enabled on your account. You'll be asked for a code from your authenticator app each time you sign in." />
        ) : mfaStep === 'confirm' && mfaSecret ? (
          <View style={{ gap: 8 }}>
            <Body soft>Add this key to your authenticator app (Google Authenticator, Authy, etc.), then enter the 6-digit code it shows:</Body>
            <View style={{ padding: 10, borderRadius: 8, backgroundColor: colors.surfaceElevated }}>
              <Text selectable style={{ fontFamily: 'monospace', fontSize: 13, letterSpacing: 1, color: colors.text }}>{mfaSecret}</Text>
            </View>
            <Field label="6-digit code" value={mfaCode} onChangeText={setMfaCode} keyboardType="number-pad" maxLength={6} />
            {mfaError ? <Text style={{ color: colors.bad, fontSize: 12 }}>{mfaError}</Text> : null}
            <AppButton label="Confirm & Enable" onPress={confirmMfa} busy={mfaBusy} />
          </View>
        ) : backupCodes ? (
          <View style={{ gap: 6 }}>
            <InfoBanner message="Two-factor authentication enabled. Save these one-time backup codes somewhere safe - each can be used once if you lose access to your authenticator app." />
            {backupCodes.map((c) => <Text key={c} selectable style={{ fontFamily: 'monospace', fontSize: 13, color: colors.text }}>{c}</Text>)}
            <AppButton label="Done" kind="secondary" onPress={() => setBackupCodes(null)} />
          </View>
        ) : (
          <>
            <Body soft>Not enabled. Add a second factor so your account can't be accessed with your password alone.</Body>
            <AppButton label="Set up two-factor authentication" onPress={startMfaEnroll} busy={mfaStep === 'enrolling'} />
          </>
        )}
      </Card>

      <Card>
        <Text style={{ fontWeight: '600', color: colors.text }}>{t('lbl.appearance')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          {MODES.map((m) => <Chip key={m} label={m === 'system' ? `${t('act.enable')} auto` : t(`theme.${m}`)} selected={mode === m} onPress={() => setMode(m)} />)}
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

      <AppButton label="Sign Out" kind="danger" onPress={() => Alert.alert('Sign Out', 'Are you sure you want to sign out?', [{ text: 'Cancel', style: 'cancel' }, { text: 'Sign Out', style: 'destructive', onPress: async () => { await signOut(); router.replace('/(auth)/login'); } }])} />
    </Screen>
  );
}
