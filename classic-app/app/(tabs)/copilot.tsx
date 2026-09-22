import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { AppButton, Body, Card, ErrorBanner, Field, H1, InfoBanner, Screen } from '../../src/components/ui.tsx';
import { VoiceInput } from '../../src/components/VoiceInput.tsx';
import { endpoints } from '../../src/api/instance.ts';
import type { AskResponse } from '../../src/api/types.ts';
import { useI18n } from '../../src/i18n/I18nContext.tsx';
import { ApiError, NetworkError } from '../../src/api/errors.ts';
import { withAlpha } from '../../src/theme.ts';
import { useTheme } from '../../src/theme/ThemeContext.tsx';

interface Turn { q: string; a?: AskResponse; error?: string }

export default function Copilot() {
  const { t, lang } = useI18n();
  const { colors } = useTheme();
  const [text, setText] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conv, setConv] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function ask(q: string) {
    if (!q.trim()) return;
    setBusy(true); setText('');
    const idx = turns.length;
    setTurns((x) => [...x, { q }]);
    try {
      const a = await endpoints.ask(q, lang, conv); // the answer is composed in the citizen's language where the model supports it
      setConv(a.conversation_id);
      setTurns((x) => x.map((tn, i) => (i === idx ? { ...tn, a } : tn)));
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof NetworkError ? 'No connection. Try again when you are online.' : 'Something went wrong.';
      setTurns((x) => x.map((tn, i) => (i === idx ? { ...tn, error: msg } : tn)));
    } finally { setBusy(false); }
  }

  return (
    <Screen>
      <H1>{t('chatbotTitle')}</H1>
      <Body soft>{t('page.copilot_help')}</Body>
      {turns.map((tn, i) => (
        <View key={i} style={{ gap: 8 }}>
          <Card style={{ backgroundColor: withAlpha(colors.primary, 0.08) }}><Body>{tn.q}</Body></Card>
          {tn.error ? <ErrorBanner message={tn.error} onRetry={() => ask(tn.q)} /> : null}
          {tn.a ? (
            <Card>
              <Body>{tn.a.answer ?? (tn.a.status === 'model_unavailable' ? 'The language model is unavailable; the sources below were found.' : t('msg.insufficient'))}</Body>
              {tn.a.database_facts != null ? <InfoBanner message={`From the database: ${JSON.stringify(tn.a.database_facts)}`} /> : null}
              {tn.a.citations.map((c) => <Text key={c.marker} style={{ fontSize: 12, color: colors.textSoft }}>[{c.marker}] {c.documentName}{c.page ? ` p.${c.page}` : ''}: {c.excerpt.slice(0, 120)}…</Text>)}
              {tn.a.warnings.map((w) => <InfoBanner key={w} tone="warn" message={w} />)}
            </Card>
          ) : !tn.error ? <Body soft>…</Body> : null}
        </View>
      ))}
      <Field label={t('chatbotPlaceholder')} value={text} onChangeText={setText} multiline />
      <AppButton label={t('act.submit')} onPress={() => ask(text)} busy={busy} disabled={!text.trim()} />
      <VoiceInput initialLanguage={lang} onAccept={(v) => { setText(v.text); }} />
    </Screen>
  );
}
