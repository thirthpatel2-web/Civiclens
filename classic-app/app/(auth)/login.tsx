import React, { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { Link, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { AppButton, Body, Card, ErrorBanner, Field, H1, InfoBanner, Screen } from '../../src/components/ui.tsx';
import { useAuth } from '../../src/auth/AuthContext.tsx';
import { ApiError, NetworkError } from '../../src/api/errors.ts';
import { IS_CONFIGURED, IS_INSECURE } from '../../src/config.ts';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { radius, shadow, spacing, withAlpha } from '../../src/theme.ts';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

type Portal = 'citizen' | 'official';

export default function Login() {
  const { signIn } = useAuth();
  const { t } = useI18n();
  const { colors } = useTheme();
  const { portal: portalParam } = useLocalSearchParams<{ portal?: string }>();
  const [portal, setPortal] = useState<Portal>(portalParam === 'official' ? 'official' : 'citizen');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [needOtp, setNeedOtp] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const accent = portal === 'citizen' ? colors.primary : colors.accentSaffron;

  async function submit() {
    setBusy(true); setError(null);
    try { await signIn(email.trim(), password, needOtp ? otp.trim() : undefined); }
    catch (e) {
      if (e instanceof ApiError && e.isMfaRequired) { setNeedOtp(true); setError(e.message); }
      else if (e instanceof ApiError) setError(e.message);
      else if (e instanceof NetworkError) setError('Cannot reach the server. Check your connection and the server address.');
      else setError('Sign-in failed.');
    } finally { setBusy(false); }
  }

  return (
    <Screen>
      <View style={{ alignItems: 'center', gap: 4, marginBottom: spacing.sm }}>
        <View style={[{ width: 60, height: 60, borderRadius: 30, backgroundColor: colors.card, borderWidth: 2, borderColor: colors.primary, alignItems: 'center', justifyContent: 'center' }, shadow.sm]}>
          <Ionicons name="shield-checkmark" size={30} color={colors.primary} />
        </View>
        <H1>{t('brand')}</H1>
        <Body soft style={{ textAlign: 'center' }}>{t('appTagline')}</Body>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
        {[{ icon: '📝', title: 'Statutory Letters' }, { icon: '🏛️', title: 'Precision RTI 2005' }, { icon: '⚖️', title: 'Verified Precedents' }, { icon: '🎤', title: 'Voice, any language' }].map((f) => (
          <View key={f.title} style={{ width: '47%', flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 10, paddingVertical: 8 }}>
            <Text style={{ fontSize: 16 }}>{f.icon}</Text>
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.textSoft, flex: 1 }}>{f.title}</Text>
          </View>
        ))}
      </View>

      {!IS_CONFIGURED ? <InfoBanner tone="warn" message="No server address configured (EXPO_PUBLIC_API_URL)." /> : null}
      {IS_INSECURE ? <InfoBanner tone="warn" message="This server address is not HTTPS. Your session token would be sent unencrypted." /> : null}

      {/* Dual portal switcher: same real backend underneath both tabs - the server (not this tab)
          decides your account's actual role and where you land after sign-in. */}
      <View style={[{ flexDirection: 'row', backgroundColor: colors.card, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: 4, gap: 4 }, shadow.sm]}>
        {(['citizen', 'official'] as Portal[]).map((p) => {
          const sel = portal === p;
          const c = p === 'citizen' ? colors.primary : colors.accentSaffron;
          return (
            <Pressable
              key={p} accessibilityRole="button" accessibilityState={{ selected: sel }}
              onPress={() => { setPortal(p); setError(null); }}
              style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, minHeight: 44, borderRadius: radius.sm, backgroundColor: sel ? c : 'transparent' }}
            >
              <Ionicons name={p === 'citizen' ? 'person-circle' : 'business'} size={17} color={sel ? '#fff' : colors.textMuted} />
              <Text style={{ color: sel ? '#fff' : colors.textSoft, fontWeight: '700', fontSize: 13 }}>{p === 'citizen' ? 'Citizen Portal' : 'Officer Portal Desk'}</Text>
            </Pressable>
          );
        })}
      </View>

      <Card style={{ borderColor: accent, borderWidth: 1.5 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: portal === 'citizen' ? colors.primaryGlow : withAlpha(colors.accentSaffron, 0.15), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name={portal === 'citizen' ? 'key' : 'shield-half'} size={17} color={accent} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ fontWeight: '800', color: colors.text }}>{portal === 'citizen' ? 'Citizen Sign In' : 'Government Official Portal Login'}</Text>
            <Body soft>{portal === 'citizen' ? 'Report issues, file RTIs, track your grievances' : 'Department queue, dashboard & resolution desk'}</Body>
          </View>
        </View>

        <Field label={t('lbl.email')} value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" />
        <Field label={t('lbl.password')} value={password} onChangeText={setPassword} secureTextEntry autoComplete="password" />
        {needOtp ? <Field label={t('lbl.otp')} value={otp} onChangeText={setOtp} keyboardType="number-pad" maxLength={12} /> : null}
        {error ? <ErrorBanner message={error} /> : null}
        <AppButton
          label={busy ? 'Please wait…' : portal === 'citizen' ? t('act.sign_in') : 'Launch Resolution Desk →'}
          onPress={submit} busy={busy} disabled={!email || !password} color={accent}
        />
        {portal === 'official' ? <Body soft>Officer and admin accounts are created by your department's administrator - contact them if you don't have one yet.</Body> : null}
      </Card>

      {portal === 'citizen' ? <Link href="/(auth)/register"><Body>{t('act.register')}</Body></Link> : null}
    </Screen>
  );
}
