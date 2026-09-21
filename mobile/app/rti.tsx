import React, { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { AppButton, Body, Card, Chip, EmptyState, ErrorBanner, Field, H1, Loading, Screen, StepProgress } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { RtiApplication, RtiCategory } from '../src/api/types.ts';
import { useAuth } from '../src/auth/AuthContext.tsx';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { useTheme } from '../src/theme/ThemeContext.tsx';

const TOTAL_STEPS = 3;
const STEP_TITLES = ['What is this about?', 'Records to demand', 'Applicant details & generate'];

export default function Rti() {
  const { t, lang } = useI18n();
  const { user } = useAuth();
  const { colors } = useTheme();
  const [step, setStep] = useState(1);
  const [items, setItems] = useState<RtiApplication[] | null>(null);
  const [categories, setCategories] = useState<RtiCategory[]>([]);
  const [category, setCategory] = useState<string | null>(null);
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [subject, setSubject] = useState(''); const [authority, setAuthority] = useState(''); const [location, setLocation] = useState('');
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

  async function doPreview() {
    setPreviewing(true); setError(null);
    try {
      const recordsRequested = activeCategory ? activeCategory.default_records.filter((r) => checked[r]) : [];
      const r = await endpoints.previewRtiQuestions({
        subject, category, location: location || null, records_requested: recordsRequested,
        tender_reference: tenderRef || null, time_period: timePeriod || null,
        custom_questions: customQs.split('\n').map((s) => s.trim()).filter(Boolean),
      });
      setPreview(r.questions);
    } catch (e: any) { setError(e?.message ?? 'Could not build questions.'); } finally { setPreviewing(false); }
  }
  // Build the questions the moment step 2 is reached, and again whenever the checklist changes.
  useEffect(() => { if (step === 2 && subject.trim()) doPreview(); }, [step]); // eslint-disable-line react-hooks/exhaustive-deps

  async function create() {
    setBusy(true); setError(null);
    try {
      const a = await endpoints.createRti({ subject, public_authority: authority, questions: preview, applicant_name: name, applicant_address: addr, language: lang });
      await endpoints.generateRti(a.id);
      setDone(a);
      setSubject(''); setPreview([]); setChecked({}); setCustomQs(''); setTenderRef(''); setTimePeriod(''); setStep(1);
      await load();
    } catch (e: any) { setError(e?.message + (e?.details ? ` ${JSON.stringify(e.details)}` : '')); } finally { setBusy(false); }
  }

  const step1Ok = subject.trim().length >= 5 && authority.trim().length >= 2;

  return (
    <Screen>
      <H1>{t('nav.rti')}</H1>
      <StepProgress step={step} total={TOTAL_STEPS} label={`${t('lbl.step_of', { current: step, total: TOTAL_STEPS })} · ${STEP_TITLES[step - 1]}`} />

      {done ? (
        <Card style={{ borderColor: colors.ok, borderWidth: 1.5 }}>
          <Text style={{ fontWeight: '800', color: colors.ok }}>✓ RTI drafted</Text>
          <Body soft>Your statutory application was generated. Review it below and mark it as filed once you've submitted it to the department.</Body>
        </Card>
      ) : null}

      {step === 1 ? (
        <Card>
          <Field label={t('lbl.title')} value={subject} onChangeText={setSubject} placeholder="e.g. Pothole repair delay on MG Road" />
          <Field label={t('selectDepartment')} value={authority} onChangeText={setAuthority} placeholder="e.g. BBMP Roads Department" />
          <Field label={t('lbl.location')} value={location} onChangeText={setLocation} />
          <Text style={{ color: colors.textSoft, fontSize: 13 }}>Category (loads the records this kind of RTI usually needs)</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
            {categories.map((c) => <Chip key={c.code} label={c.code} selected={category === c.code} onPress={() => { setCategory(c.code); setChecked({}); }} />)}
          </View>
        </Card>
      ) : null}

      {step === 2 ? (
        <>
          {activeCategory ? (
            <Card>
              <Body soft>Tick the records you want certified copies of</Body>
              {activeCategory.default_records.map((rec) => <Chip key={rec} label={rec} selected={!!checked[rec]} onPress={() => toggle(rec)} />)}
              <Field label="Tender / Work Order number (if known)" value={tenderRef} onChangeText={setTenderRef} />
              <Field label="Time period covered (e.g. Jan 2024 - Mar 2024)" value={timePeriod} onChangeText={setTimePeriod} />
              <Field label="Additional questions of your own (one per line)" value={customQs} onChangeText={setCustomQs} multiline />
              <AppButton label="Rebuild questions" kind="secondary" onPress={doPreview} busy={previewing} />
            </Card>
          ) : <Card><Body soft>No category picked - continuing with the general statutory questions.</Body></Card>}
          {preview.length > 0 ? (
            <Card>
              <Body soft>Statutory questions this RTI will ask</Body>
              {preview.map((q, i) => <Body key={i}>{i + 1}. {q}</Body>)}
            </Card>
          ) : null}
        </>
      ) : null}

      {step === 3 ? (
        <Card>
          <Field label={t('fullName')} value={name} onChangeText={setName} />
          <Field label={t('residentialAddress')} value={addr} onChangeText={setAddr} multiline />
          {error ? <ErrorBanner message={error} /> : null}
          <AppButton label={t('generateLetterBtn')} onPress={create} busy={busy} disabled={preview.length === 0 || !name.trim() || !addr.trim()} />
        </Card>
      ) : null}

      <View style={{ flexDirection: 'row', gap: 8 }}>
        {step > 1 ? <AppButton label={t('act.back')} kind="secondary" onPress={() => setStep((s) => s - 1)} /> : null}
        {step < TOTAL_STEPS ? <AppButton label={t('act.next')} onPress={() => setStep((s) => s + 1)} disabled={step === 1 && !step1Ok} /> : null}
      </View>

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
