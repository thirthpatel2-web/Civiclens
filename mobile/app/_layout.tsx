import React, { useEffect } from 'react';
import { View } from 'react-native';
import { Slot, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { AuthProvider, useAuth } from '../src/auth/AuthContext.tsx';
import { I18nProvider } from '../src/i18n/I18nContext.tsx';
import { SyncProvider } from '../src/offline/SyncContext.tsx';
import { registerBackgroundSync } from '../src/offline/backgroundTask.ts';
import { Loading } from '../src/components/ui.tsx';
import { TopBar } from '../src/components/TopBar.tsx';
import { PrivacyConsentGate } from '../src/components/PrivacyConsentGate.tsx';
import { ThemeProvider, useTheme } from '../src/theme/ThemeContext.tsx';

const homeFor = (role: string) => (role === 'citizen' ? '/(tabs)/home' : '/(officer)/dashboard');

function Gate() {
  const { user, loading } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  useEffect(() => {
    if (loading) return;
    const inAuth = segments[0] === '(auth)';
    const inOfficerArea = segments[0] === '(officer)';
    const inCitizenArea = segments[0] === '(tabs)';
    if (!user && !inAuth) router.replace('/(auth)/login');
    else if (user && inAuth) router.replace(homeFor(user.role));
    // A citizen who somehow lands on the officer tabs (or vice versa) gets redirected home for
    // their real role - the API already enforces this server-side; this just keeps the UI honest.
    else if (user && user.role === 'citizen' && inOfficerArea) router.replace('/(tabs)/home');
    else if (user && user.role !== 'citizen' && inCitizenArea) router.replace('/(officer)/dashboard');
  }, [user, loading, segments, router]);
  useEffect(() => { if (user?.role === 'citizen') registerBackgroundSync().catch(() => undefined); }, [user]);
  if (loading) return <Loading label="CivicLens" />;
  if (!user) return <Slot />;
  return (
    <View style={{ flex: 1 }}>
      <TopBar />
      <View style={{ flex: 1 }}><Slot /></View>
      <PrivacyConsentGate />
    </View>
  );
}

function ThemedStatusBar() {
  const { resolvedMode, colors } = useTheme();
  return <StatusBar style={resolvedMode === 'dark' ? 'light' : 'dark'} backgroundColor={colors.bg} />;
}

export default function RootLayout() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <I18nProvider>
          <SyncProvider>
            <ThemedStatusBar />
            <Gate />
          </SyncProvider>
        </I18nProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
