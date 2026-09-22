import React, { useState } from 'react';
import { useRouter } from 'expo-router';
import { AppButton, Card, ErrorBanner, Field, H1, Screen } from '../../src/components/ui.tsx';
import { endpoints } from '../../src/api/instance.ts';
import { ApiError } from '../../src/api/errors.ts';
import { useAuth } from '../../src/auth/AuthContext.tsx';
import { useI18n } from '../../src/i18n/I18nContext.tsx';

export default function Register() {
  const { t } = useI18n();
  const { signIn } = useAuth();
  const router = useRouter();
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true); setError(null);
    try {
      await endpoints.register(email.trim(), password, name.trim()); // accounts are always citizen accounts: the API accepts no role
      await signIn(email.trim(), password);
      router.replace('/(tabs)/home');
    } catch (e) {
      setError(e instanceof ApiError ? e.message + (e.details ? ` (${Object.values(e.details as object).join('; ')})` : '') : 'Registration failed. Check your connection.');
    } finally { setBusy(false); }
  }
  return (
    <Screen>
      <H1>👤 {t('act.register')}</H1>
      <Card>
        <Field label={t('fullName')} value={name} onChangeText={setName} />
        <Field label={t('lbl.email')} value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" />
        <Field label={t('lbl.password')} value={password} onChangeText={setPassword} secureTextEntry />
        {error ? <ErrorBanner message={error} /> : null}
        <AppButton label={t('act.register')} onPress={submit} busy={busy} disabled={!name || !email || password.length < 10} />
      </Card>
    </Screen>
  );
}
