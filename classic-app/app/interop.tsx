import React, { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { AppButton, Body, Card, Chip, EmptyState, ErrorBanner, Field, H1, InfoBanner, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { ExternalIdLink, ExternalServiceLink, FragmentationDiagnostic, InteropSystem, IntegrationException, NormalizeDemoResult } from '../src/api/types.ts';
import { useAuth } from '../src/auth/AuthContext.tsx';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { radius, withAlpha } from '../src/theme.ts';
import { useTheme } from '../src/theme/ThemeContext.tsx';

// Same fixed ID taxonomy the backend accepts (app.services.interop_service.ID_TYPES) - not deployment data.
const ID_TYPES = ['aadhaar_ref', 'pan', 'voter_id', 'driving_license', 'ration_card'];
const GRADE_TONE: Record<string, 'ok' | 'info' | 'warn' | 'bad'> = { excellent: 'ok', good: 'info', poor: 'warn', unusable: 'bad' };

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ flex: 1, minWidth: 140, backgroundColor: colors.card, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: 12, gap: 2 }}>
      <Text style={{ fontSize: 20, fontWeight: '800', color: colors.primary }}>{value}</Text>
      <Text style={{ fontSize: 12, color: colors.text, fontWeight: '600' }}>{label}</Text>
      {hint ? <Text style={{ fontSize: 10, color: colors.textSoft }}>{hint}</Text> : null}
    </View>
  );
}

export default function InteropLab() {
  const { t } = useI18n();
  const { user } = useAuth();
  const { colors } = useTheme();
  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin';

  const [frag, setFrag] = useState<FragmentationDiagnostic | null>(null);
  const [systems, setSystems] = useState<InteropSystem[]>([]);
  const [system, setSystem] = useState<string | null>(null);
  const [corrupt, setCorrupt] = useState(false);
  const [demo, setDemo] = useState<NormalizeDemoResult | null>(null);
  const [demoBusy, setDemoBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [links, setLinks] = useState<ExternalIdLink[] | null>(null);
  const [idType, setIdType] = useState(ID_TYPES[0]);
  const [idValue, setIdValue] = useState('');
  const [linkBusy, setLinkBusy] = useState(false);

  const [tracked, setTracked] = useState<ExternalServiceLink[] | null>(null);
  const [platform, setPlatform] = useState(''); const [ref, setRef] = useState(''); const [title, setTitle] = useState('');
  const [trackBusy, setTrackBusy] = useState(false);

  const [exceptions, setExceptions] = useState<IntegrationException[] | null>(null);

  useEffect(() => {
    endpoints.interopSystems().then((r) => { setSystems(r.items); setSystem(r.items[0]?.code ?? null); }).catch(() => setSystems([]));
    if (user?.role === 'citizen') endpoints.interopFragmentation().then(setFrag).catch(() => setFrag(null));
    endpoints.listMasterData().then((r) => setLinks(r.items)).catch(() => setLinks([]));
    endpoints.listExternalLinks().then((r) => setTracked(r.items)).catch(() => setTracked([]));
    if (isAdmin) endpoints.interopExceptions('open').then((r) => setExceptions(r.items)).catch(() => setExceptions([]));
  }, [user?.role]); // eslint-disable-line react-hooks/exhaustive-deps

  const runDemo = useCallback(async (sys: string, corruptFlag: boolean) => {
    setDemoBusy(true); setError(null);
    try { setDemo(await endpoints.interopNormalizeDemo(sys, corruptFlag)); }
    catch (e: any) { setError(e?.message ?? 'Could not run the normalization demo.'); }
    finally { setDemoBusy(false); }
  }, []);
  useEffect(() => { if (system) runDemo(system, corrupt); }, [system, corrupt]); // eslint-disable-line react-hooks/exhaustive-deps

  async function reloadLinks() { setLinks((await endpoints.listMasterData()).items); }
  async function reloadTracked() { setTracked((await endpoints.listExternalLinks()).items); }

  return (
    <Screen>
      <H1>{t('nav.interop')}</H1>
      <Body soft>Different government systems describe the same request with different field names, casing and status words. See the real normalization mechanism, live - this is the actual technical answer to fragmented service delivery.</Body>
      {error ? <ErrorBanner message={error} /> : null}

      <Text style={{ fontWeight: '700', color: colors.text }}>Fragmentation, in numbers</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        <Stat label="Services on India's own unification app" value="1,700+" hint="UMANG, Digital India - across 100+ departments" />
        {frag ? (
          <>
            <Stat label="Departments you've dealt with" value={frag.personal.distinct_departments} hint={`across ${frag.personal.total_filings} filing(s) through CivicLens`} />
            <Stat label="Re-entries avoided" value={frag.personal.profile_reuses} hint="times your one profile was reused instead of re-typing KYC" />
          </>
        ) : user?.role !== 'citizen' ? <Stat label="Personal fragmentation" value="—" hint="tracked per-citizen (sign in as a citizen to see yours)" /> : null}
      </View>

      <Text style={{ fontWeight: '700', color: colors.text, marginTop: 4 }}>Live normalization demo</Text>
      <Body soft>Pick a system to see its real (fixture) export shape transform into CivicLens's Common Data Model.</Body>
      <InfoBanner message="These are realistic illustrative fixtures shaped like real system exports, not a live feed - no department has given CivicLens a data-sharing agreement yet. The adapter code itself is real and directly reusable the day one exists." />
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        {systems.map((s) => <Chip key={s.code} label={s.label} selected={system === s.code} onPress={() => setSystem(s.code)} />)}
      </View>
      <AppButton label={corrupt ? '☑ Simulating a malformed record' : '☐ Simulate a malformed record'} kind="secondary" onPress={() => setCorrupt((v) => !v)} />

      {demoBusy ? <Loading /> : demo ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <Card style={{ flex: 1, minWidth: 260 }}>
            <Body soft>Raw payload (exactly as that system would export it)</Body>
            <Text style={{ fontFamily: 'monospace', fontSize: 11, color: colors.text }}>{JSON.stringify(demo.payload, null, 2)}</Text>
          </Card>
          <Card style={{ flex: 1, minWidth: 260 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Body soft>Normalized (Common Data Model)</Body>
              {(() => {
                const gradeColor = colors[GRADE_TONE[demo.quality.grade]];
                return (
                  <View style={{ backgroundColor: withAlpha(gradeColor, 0.15), borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: gradeColor }}>{demo.quality.grade} · {Math.round(demo.quality.score * 100)}%</Text>
                  </View>
                );
              })()}
            </View>
            {([['External ID', demo.record.external_id], ['Category', demo.record.category], ['Status', demo.record.status], ['Title', demo.record.title],
               ['Department', demo.record.department], ['Citizen', demo.record.citizen_name], ['Contact', demo.record.citizen_contact],
               ['Location', demo.record.location], ['Filed on', demo.record.filed_on]] as [string, string | null][]).map(([label, value]) => (
              <View key={label} style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ fontSize: 12, color: colors.textSoft }}>{label}</Text>
                <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{value || '—'}</Text>
              </View>
            ))}
            {demo.quality.issues.length ? (
              <>
                <Text style={{ fontSize: 12, fontWeight: '700', color: colors.bad, marginTop: 6 }}>Data-quality issues detected:</Text>
                {demo.quality.issues.map((iss) => <Text key={iss} style={{ fontSize: 12, color: colors.bad }}>• {iss}</Text>)}
                {demo.quality.grade === 'poor' || demo.quality.grade === 'unusable' ? (
                  <AppButton label="Queue as an integration exception" kind="danger" onPress={async () => {
                    try { await endpoints.interopLogException(demo.record.source_system, demo.quality.issues.join('; ').slice(0, 300), demo.payload); setError(null); }
                    catch (e: any) { setError(e?.message ?? 'Could not queue the exception.'); }
                  }} />
                ) : null}
              </>
            ) : null}
          </Card>
        </View>
      ) : null}

      <Text style={{ fontWeight: '700', color: colors.text, marginTop: 4 }}>Linked government IDs (Golden Record)</Text>
      <Body soft>Only a salted hash is ever stored - the raw value never reaches the server after this screen.</Body>
      {links === null ? <Loading /> : links.length === 0 ? <EmptyState message="No IDs linked yet." /> : links.map((l) => (
        <Card key={l.id}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <Body>{l.id_type.replace(/_/g, ' ')} · ****{l.last4}</Body>
            <AppButton label="Unlink" kind="secondary" onPress={async () => { await endpoints.unlinkMasterData(l.id); await reloadLinks(); }} />
          </View>
        </Card>
      ))}
      <Card>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{ID_TYPES.map((it) => <Chip key={it} label={it.replace(/_/g, ' ')} selected={idType === it} onPress={() => setIdType(it)} />)}</View>
        <Field label="ID value" value={idValue} onChangeText={setIdValue} />
        <AppButton label="Link this ID" busy={linkBusy} disabled={idValue.trim().length < 4} onPress={async () => {
          setLinkBusy(true); setError(null);
          try { await endpoints.linkMasterData(idType, idValue); setIdValue(''); await reloadLinks(); }
          catch (e: any) { setError(e?.message ?? 'Could not link this ID.'); } finally { setLinkBusy(false); }
        }} />
      </Card>

      <Text style={{ fontWeight: '700', color: colors.text, marginTop: 4 }}>Other portals you're tracking manually</Text>
      <Body soft>For platforms that require your own login and expose no API to sync from - honest manual tracking, not a fake live sync.</Body>
      {tracked === null ? <Loading /> : tracked.length === 0 ? <EmptyState message="Nothing tracked yet." /> : tracked.map((x) => (
        <Card key={x.id}>
          <Text style={{ fontWeight: '700', color: colors.text }}>{x.platform} · {x.external_reference}</Text>
          <Body soft>{x.title}</Body>
          {x.status_note ? <Body soft>{x.status_note}</Body> : null}
          <AppButton label="Remove" kind="secondary" onPress={async () => { await endpoints.removeExternalLink(x.id); await reloadTracked(); }} />
        </Card>
      ))}
      <Card>
        <Field label="Platform (e.g. CPGRAMS)" value={platform} onChangeText={setPlatform} />
        <Field label="Reference number on that platform" value={ref} onChangeText={setRef} />
        <Field label="Title" value={title} onChangeText={setTitle} />
        <AppButton label="Track this" busy={trackBusy} disabled={!platform.trim() || !ref.trim() || !title.trim()} onPress={async () => {
          setTrackBusy(true); setError(null);
          try { await endpoints.addExternalLink(platform, ref, title); setPlatform(''); setRef(''); setTitle(''); await reloadTracked(); }
          catch (e: any) { setError(e?.message ?? 'Could not save this.'); } finally { setTrackBusy(false); }
        }} />
      </Card>

      {isAdmin ? (
        <>
          <Text style={{ fontWeight: '700', color: colors.text, marginTop: 4 }}>Integration exceptions (open)</Text>
          {exceptions === null ? <Loading /> : exceptions.length === 0 ? <EmptyState message="No open exceptions." /> : exceptions.map((ex) => (
            <Card key={ex.id}>
              <Text style={{ fontWeight: '700', color: colors.text }}>{ex.source_system}</Text>
              <Body soft>{ex.reason}</Body>
              <View style={{ flexDirection: 'row', gap: 6 }}>
                <AppButton label="Resolve" kind="secondary" onPress={async () => { await endpoints.interopResolveException(ex.id, 'Reviewed', false); setExceptions((await endpoints.interopExceptions('open')).items); }} />
                <AppButton label="Ignore" kind="secondary" onPress={async () => { await endpoints.interopResolveException(ex.id, '', true); setExceptions((await endpoints.interopExceptions('open')).items); }} />
              </View>
            </Card>
          ))}
        </>
      ) : null}
    </Screen>
  );
}
