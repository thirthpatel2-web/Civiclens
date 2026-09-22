import React, { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { AppButton, Body, Card, Chip, Disclosure, EmptyState, ErrorBanner, Field, H1, Loading, Screen } from '../src/components/ui.tsx';
import { VoiceField } from '../src/components/VoiceField.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { RtiApplication, RtiCategory } from '../src/api/types.ts';
import { useAuth } from '../src/auth/AuthContext.tsx';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { useTheme } from '../src/theme/ThemeContext.tsx';

export default function Rti() {
  const { t, lang } = useI18n();
  const { user } = useAuth();
  const { colors } = useTheme();
  const [items, setItems] = useState<RtiApplication[] | null>(null);
  const [categories, setCategories] = useState<RtiCategory[]>([]);
  const [category, setCategory] = useState<string | null>(null);
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [subject, setSubject] = useState(''); const [authority, setAuthority] = useState('');
  const [tenderRef, setTenderRef] = useState(''); const [timePeriod, setTimePeriod] = useState(''); const [customQs, setCustomQs] = useState('');
  const [name, setName] = useState(user?.full_name ?? ''); const [addr, setAddr] = useState('');
  const [preview, setPreview] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false); const [previewing, setPreviewing] = useState(false);
  const [done, setDone] = useState<RtiApplication | null>(null);

  const load = useCallback(async () => { try { setItems((await endpoints.listRti()).items); } catch (e: any) { setError(e?.message ?? 'Could not load your RTI applications.'); setItems([]); } }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { endpoints.rtiCategories().then((r) => setCategories(r.categories)).catch(() => setCategories([])); }, []);

  const activeCategory = categories.find((c) => c.code === category);
  const toggle = (rec: string) => setChecked((m) => ({ ...m, [rec]: !m[rec] }));

  const doPreview = useCallback(async () => {
    if (subject.trim().length < 5) { setPreview([]); return; }
    setPreviewing(true); setError(null);
    try {
      const recordsRequested = activeCategory ? activeCategory.default_records.filter((r) => checked[r]) : [];
      const r = await endpoints.previewRtiQuestions({
        subject, category, location: null, records_requested: recordsRequested,
        tender_reference: tenderRef || null, time_period: timePeriod || null,
        custom_questions: customQs.split('\n').map((s) => s.trim()).filter(Boolean),
      });
      setPreview(r.questions);
    } catch (e: any) { setError(e?.message ?? 'Could not build questions.'); } finally { setPreviewing(false); }
  }, [subject, category, activeCategory, checked, tenderRef, timePeriod, customQs]);

  // Rebuild the statutory questions a moment after the citizen stops typing/speaking - no explicit
  // "next step" needed, this used to be a separate wizard page.
  useEffect(() => { const id = setTimeout(doPreview, 600); return () => clearTimeout(id); }, [doPreview]);

  async function create() {
    setBusy(true); setError(null);
    try {
      const a = await endpoints.createRti({ subject, public_authority: authority, questions: preview, applicant_name: name, applicant_address: addr, language: lang });
      await endpoints.generateRti(a.id);
      setDone(a);
      setSubject(''); setAuthority(''); setPreview([]); setChecked({}); setCustomQs(''); setTenderRef(''); setTimePeriod(''); setCategory(null);
      await load();
    } catch (e: any) { setError(e?.message + (e?.details ? ` ${JSON.stringify(e.details)}` : '')); } finally { setBusy(false); }
  }

  const canGenerate = subject.trim().length >= 5 && authority.trim().length >= 2 && preview.length > 0 && name.trim().length > 0 && addr.trim().length > 0;

  return (
    <Screen>
      <H1>{t('nav.rti')}</H1>
      <Body soft>Describe what happened, in your own words or by voice. We'll turn it into a proper RTI Act, Section 6(1) application.</Body>

      {done ? (
        <Card style={{ borderColor: colors.ok, borderWidth: 1.5 }}>
          <Text style={{ fontWeight: '800', color: colors.ok }}>✓ RTI drafted</Text>
          <Body soft>Your statutory application was generated. Review it below and mark it as filed once you've submitted it to the department.</Body>
        </Card>
      ) : null}

      <Card>
        <VoiceField label={t('lbl.title')} value={subject} onChangeText={setSubject} placeholder="e.g. Pothole repair delay on MG Road" maxLength={200} />
        <Field label={t('selectDepartment')} value={authority} onChangeText={setAuthority} placeholder="e.g. BBMP Roads Department" />

        <Text style={{ color: colors.textSoft, fontSize: 13 }}>Category (optional - loads the records this kind of RTI usually needs)</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          {categories.map((c) => <Chip key={c.code} label={c.code} selected={category === c.code} onPress={() => { setCategory(category === c.code ? null : c.code); setChecked({}); }} />)}
        </View>
        {activeCategory ? (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
            {activeCategory.default_records.map((rec) => <Chip key={rec} label={rec} selected={!!checked[rec]} onPress={() => toggle(rec)} />)}
          </View>
        ) : null}

        <Disclosure label="More details (optional)">
          <View style={{ gap: 8 }}>
            <Field label="Tender / Work Order number (if known)" value={tenderRef} onChangeText={setTenderRef} />
            <Field label="Time period covered (e.g. Jan 2024 - Mar 2024)" value={timePeriod} onChangeText={setTimePeriod} />
            <Field label="Additional questions of your own (one per line)" value={customQs} onChangeText={setCustomQs} multiline />
          </View>
        </Disclosure>
      </Card>

      {previewing ? <Loading label="Building your statutory questions..." /> : preview.length > 0 ? (
        <Card>
          <Body soft>Statutory questions this RTI will ask ({preview.length})</Body>
          {preview.map((q, i) => <Body key={i}>{i + 1}. {q}</Body>)}
        </Card>
      ) : null}

      <Card>
        <Field label={t('fullName')} value={name} onChangeText={setName} />
        <Field label={t('residentialAddress')} value={addr} onChangeText={setAddr} multiline />
        {error ? <ErrorBanner message={error} /> : null}
        <AppButton label={t('generateLetterBtn')} onPress={create} busy={busy} disabled={!canGenerate} />
      </Card>

      <Text style={{ fontWeight: '700', color: colors.text, marginTop: 8 }}>Your RTI applications</Text>
      {items === null ? <Loading /> : items.length === 0 ? <EmptyState message={t('msg.no_data')} /> : items.map((a) => (
        <Card key={a.id}>
          <Text style={{ fontWeight: '700', color: colors.text }}>{a.reference ?? 'draft'} · {a.status}</Text>
          <Body>{a.draft.subject}</Body>
          {a.due_at ? <Body soft>Deadline: {new Date(a.due_at).toLocaleDateString()}</Body> : null}
          {a.status === 'generated' ? <AppButton label="Mark as filed" kind="secondary" onPress={async () => { await endpoints.fileRti(a.id); load(); }} /> : null}
        </Card>
      ))}
    </Screen>
  );
}
