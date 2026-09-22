// Shown once, after login, until accepted - backed by the existing PUT/GET /consent endpoints
// (app/services/profile_service.py's CONSENT_PURPOSES already tracked ai_processing/data_sharing/
// document_storage/notifications_email; this adds "privacy_policy" as the general, mandatory
// disclosure of what camera/location/microphone/complaint text are used for and why).
import React, { useEffect, useState } from 'react';
import { Modal, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../theme/ThemeContext.tsx';
import type { ThemeColors } from '../theme.ts';
import { endpoints } from '../api/instance.ts';
import { radius, shadow } from '../theme.ts';
import { AppButton } from './ui.tsx';

export function PrivacyConsentGate() {
  const { colors } = useTheme();
  const [state, setState] = useState<'checking' | 'needed' | 'ok'>('checking');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    endpoints.consents()
      .then((c) => setState(c.privacy_policy?.granted ? 'ok' : 'needed'))
      .catch(() => setState('ok')); // best-effort: a failed check never blocks the app
  }, []);

  async function accept() {
    setBusy(true);
    try { await endpoints.setConsent('privacy_policy', true); setState('ok'); }
    catch { /* the modal simply stays open; the citizen can retry */ }
    finally { setBusy(false); }
  }

  if (state !== 'needed') return null;
  return (
    <Modal visible transparent animationType="fade">
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'center', alignItems: 'center', padding: 20 }}>
        <View style={[{ backgroundColor: colors.card, borderRadius: radius.lg, padding: 22, width: '100%', maxWidth: 460, gap: 12 }, shadow.lg]}>
          <Text style={{ fontWeight: '800', color: colors.text, fontSize: 18 }}>Before you continue</Text>
          <Text style={{ color: colors.textSoft, fontSize: 13, lineHeight: 19 }}>
            CivicLens only asks for a permission at the moment you use it, for exactly the reason below - never in the background.
          </Text>
          <PrivacyRow icon="camera" text="Camera / photo library - to attach evidence to a complaint." colors={colors} />
          <PrivacyRow icon="location" text="Location - only when you tap 'Use my location', to attach where the problem is." colors={colors} />
          <PrivacyRow icon="mic" text="Microphone - to turn your spoken complaint into text, in the language you speak." colors={colors} />
          <PrivacyRow icon="document-text" text="Your complaint, RTI and legal text is stored to process your request, and shared only with the department it's routed to." colors={colors} />
          <Text style={{ color: colors.textMuted, fontSize: 11 }}>Privacy policy version 2026-09 - you can review and change permissions any time in Settings.</Text>
          <AppButton label="I understand, continue" onPress={accept} busy={busy} />
        </View>
      </View>
    </Modal>
  );
}

function PrivacyRow({ icon, text, colors }: { icon: keyof typeof Ionicons.glyphMap; text: string; colors: ThemeColors }) {
  return (
    <View style={{ flexDirection: 'row', gap: 10, alignItems: 'flex-start' }}>
      <Ionicons name={icon} size={16} color={colors.primary} style={{ marginTop: 2 }} />
      <Text style={{ color: colors.textSoft, fontSize: 13, flex: 1, lineHeight: 18 }}>{text}</Text>
    </View>
  );
}
