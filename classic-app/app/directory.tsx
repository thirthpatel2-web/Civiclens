import React, { useEffect, useMemo, useState } from 'react';
import { Linking, Platform, Text, View } from 'react-native';
import { Body, Card, Chip, EmptyState, ErrorBanner, H1, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { DirectoryData } from '../src/api/types.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { useTheme } from '../src/theme/ThemeContext.tsx';

const openInMaps = (lat: number, lng: number, label: string) => {
  const url = Platform.select({
    ios: `maps:0,0?q=${encodeURIComponent(label)}@${lat},${lng}`,
    android: `geo:${lat},${lng}?q=${lat},${lng}(${encodeURIComponent(label)})`,
    default: `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`,
  });
  Linking.openURL(url!).catch(() => Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${lat},${lng}`));
};

export default function Directory() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const [d, setD] = useState<DirectoryData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dept, setDept] = useState<string | null>(null);

  useEffect(() => {
    endpoints.directory().then(setD).catch((e: any) => setError(e?.message ?? 'Could not load the department directory.'));
  }, []);

  const services = useMemo(() => (d ? d.services.filter((s) => !dept || s.department_code === dept) : []), [d, dept]);
  const offices = useMemo(() => (d ? d.offices.filter((o) => !dept || o.department_code === dept) : []), [d, dept]);

  if (error) return <Screen><H1>{t('nav.departments')}</H1><ErrorBanner message={error} /></Screen>;
  if (!d) return <Screen><Loading label={t('msg.loading')} /></Screen>;

  return (
    <Screen>
      <H1>{t('nav.departments')}</H1>
      <Body soft>Real departments, services and offices configured for this deployment.</Body>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        <Chip label="All" selected={dept === null} onPress={() => setDept(null)} />
        {d.departments.map((x) => <Chip key={x.code} label={x.name} selected={dept === x.code} onPress={() => setDept(x.code)} />)}
      </View>

      <Card>
        <Text style={{ fontWeight: '600', color: colors.text }}>Services</Text>
        {services.length === 0 ? <EmptyState message={t('msg.no_data')} /> : services.map((s) => (
          <Body key={s.code}>{s.name} <Text style={{ color: colors.textSoft }}>· {s.department_code}</Text></Body>
        ))}
      </Card>

      <Card>
        <Text style={{ fontWeight: '600', color: colors.text }}>Offices</Text>
        {offices.length === 0 ? <EmptyState message={t('msg.no_data')} /> : offices.map((o) => (
          <View key={o.id} style={{ paddingVertical: 6, gap: 2 }}>
            <Text style={{ fontWeight: '600', color: colors.text }}>{o.name}</Text>
            {o.address ? <Body soft>{o.address}</Body> : null}
            <Text style={{ color: colors.primary }} onPress={() => openInMaps(o.lat, o.lng, o.name)}>📍 Open in Maps</Text>
          </View>
        ))}
      </Card>

      <Card>
        <Text style={{ fontWeight: '600', color: colors.text }}>{t('nav.wards')}</Text>
        {d.cities.map((c) => (
          <View key={c.code} style={{ paddingVertical: 4 }}>
            <Text style={{ fontWeight: '600', color: colors.text }}>{c.name}{c.state ? `, ${c.state}` : ''}</Text>
            <Body soft>{d.wards.filter((w) => w.city_code === c.code).map((w) => w.name).join(', ') || 'No wards configured.'}</Body>
          </View>
        ))}
      </Card>
    </Screen>
  );
}
