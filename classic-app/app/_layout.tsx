import React, { useEffect } from 'react';
import { View } from 'react-native';
import { Slot, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useFonts, Fraunces_600SemiBold, Fraunces_700Bold, Fraunces_600SemiBold_Italic } from '@expo-google-fonts/fraunces';
import { Manrope_400Regular, Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold } from '@expo-google-fonts/manrope';
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
  const { resolvedMode } = useTheme();
  // backgroundColor was dropped from expo-status-bar's props (Android now always renders edge-to-edge).
  return <StatusBar style={resolvedMode === 'dark' ? 'light' : 'dark'} />;
}

export default function RootLayout() {
  // Fraunces (headlines) + Manrope (body/UI) - the zip's actual brand typography, ported 1:1
  // (legacy-prototype/src/constants/theme.js FONT_FAMILY). Until this resolves, text renders in
  // the system font rather than blocking the whole app on a loading screen.
  useFonts({ Fraunces_600SemiBold, Fraunces_700Bold, Fraunces_600SemiBold_Italic, Manrope_400Regular, Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold });
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
