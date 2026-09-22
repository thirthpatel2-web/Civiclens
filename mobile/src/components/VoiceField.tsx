// A text field with a built-in mic: speak instead of typing, in any language. Shared by RTI and the
// Legal/Case Analyzer so both get the same voice input the dashboard assistant has, instead of each
// screen inventing its own recorder UI.
import React, { useState } from 'react';
import { ActivityIndicator, Pressable, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { MIN_TOUCH } from '../theme.ts';
import { useTheme } from '../theme/ThemeContext.tsx';
import { useI18n } from '../i18n/I18nContext.tsx';
import { useVoiceInput } from '../hooks/useVoiceInput.ts';
import { isOnline } from '../offline/SyncContext.tsx';

export function VoiceField({ label, value, onChangeText, placeholder, multiline, maxLength }: { label: string; value: string; onChangeText: (text: string) => void; placeholder?: string; multiline?: boolean; maxLength?: number }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const v = useVoiceInput('auto', isOnline);
  const s = v.state;
  const [handledUri, setHandledUri] = useState<string | null>(null);
  if (s.kind === 'review' && s.audioUri !== handledUri) {
    setHandledUri(s.audioUri);
    const trimmed = value.trim();
    const joined = trimmed ? `${trimmed} ${s.text}` : s.text;
    onChangeText(maxLength ? joined.slice(0, maxLength) : joined);
  }
  const micBusy = s.kind === 'requesting_permission' || s.kind === 'transcribing';

  return (
    <View style={{ gap: 4 }}>
      <Text style={{ color: colors.textSoft, fontSize: 13 }}>{label}</Text>
      <View style={{ flexDirection: 'row', alignItems: multiline ? 'flex-end' : 'center', gap: 8 }}>
        <TextInput
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor={colors.textMuted}
          multiline={multiline}
          maxLength={maxLength}
          accessibilityLabel={label}
          style={[
            { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.card, paddingHorizontal: 12, paddingVertical: 10, fontSize: 16, minHeight: MIN_TOUCH, color: colors.text },
            multiline ? { minHeight: 110, textAlignVertical: 'top' as const } : null,
          ]}
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={s.kind === 'recording' ? t('assistant.listening') : t('assistant.mic_tip')}
          onPress={s.kind === 'recording' ? v.stop : v.start}
          style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: s.kind === 'recording' ? colors.bad : colors.accentPurple, alignItems: 'center', justifyContent: 'center' }}
        >
          {micBusy ? <ActivityIndicator color="#fff" size="small" /> : <Ionicons name={s.kind === 'recording' ? 'stop' : 'mic'} size={18} color="#fff" />}
        </Pressable>
      </View>
      {s.kind === 'recording' ? <Text style={{ color: colors.bad, fontSize: 12 }}>● {t('assistant.listening')}</Text> : null}
      {s.kind === 'error' ? <Text style={{ color: colors.bad, fontSize: 12 }}>{s.permissionDenied ? t('assistant.mic_denied') : s.notConfigured ? t('assistant.mic_off') : `${t('assistant.mic_failed')} (${s.message})`}</Text> : null}
    </View>
  );
}
