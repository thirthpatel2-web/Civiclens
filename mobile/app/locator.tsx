import React, { useEffect, useMemo, useState } from 'react';
import { Linking, Platform, Text, View } from 'react-native';
import { AppButton, Body, Card, Chip, EmptyState, ErrorBanner, H1, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { DirectoryData } from '../src/api/types.ts';
import { useDeviceLocation } from '../src/hooks/useDeviceLocation.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { useTheme } from '../src/theme/ThemeContext.tsx';

// Same formula the backend uses for "nearby" matching (app.services.location_service.haversine_m) -
// distance is shown for real, computed from your actual device coordinates, never invented.
function haversineMeters(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1), dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
const openInMaps = (lat: number, lng: number, label: string) => {
  const url = Platform.select({
    ios: `maps:0,0?q=${encodeURIComponent(label)}@${lat},${lng}`,
    android: `geo:${lat},${lng}?q=${lat},${lng}(${encodeURIComponent(label)})`,
    default: `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`,
  });
  Linking.openURL(url!).catch(() => Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${lat},${lng}`));
};

export default function CivicLocator() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const loc = useDeviceLocation();
  const [d, setD] = useState<DirectoryData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dept, setDept] = useState<string | null>(null);

  useEffect(() => { endpoints.directory().then(setD).catch((e: any) => setError(e?.message ?? 'Could not load offices.')); }, []);
  useEffect(() => { loc.request(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const offices = useMemo(() => {
    if (!d) return [];
    const filtered = dept ? d.offices.filter((o) => o.department_code === dept) : d.offices;
    if (loc.state.kind !== 'ok') return filtered.map((o) => ({ ...o, distanceM: null as number | null }));
    const { lat, lng } = loc.state;
    return filtered.map((o) => ({ ...o, distanceM: haversineMeters(lat, lng, o.lat, o.lng) })).sort((a, b) => (a.distanceM ?? Infinity) - (b.distanceM ?? Infinity));
  }, [d, dept, loc.state]);

  return (
    <Screen>
      <H1>{t('nav.locator')}</H1>
      <Body soft>The nearest real government offices, sorted by your actual device location.</Body>
      {error ? <ErrorBanner message={error} /> : null}

      {loc.state.kind === 'none' || loc.state.kind === 'locating' ? (
        <Card><Body soft>{loc.state.kind === 'locating' ? 'Finding your location…' : 'Location not available yet.'}</Body><AppButton label="Use my location" kind="secondary" onPress={loc.request} busy={loc.state.kind === 'locating'} /></Card>
      ) : loc.state.kind === 'denied' ? (
        <Card><Body soft>Location permission was denied - offices are shown unsorted. You can still open any office in Maps.</Body><AppButton label="Try again" kind="secondary" onPress={loc.request} /></Card>
      ) : loc.state.kind === 'error' ? (
        <ErrorBanner message={loc.state.message} onRetry={loc.request} />
      ) : null}

      {d ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          <Chip label="All departments" selected={dept === null} onPress={() => setDept(null)} />
          {d.departments.map((x) => <Chip key={x.code} label={x.name} selected={dept === x.code} onPress={() => setDept(x.code)} />)}
        </View>
      ) : null}

      {!d ? <Loading label={t('msg.loading')} /> : offices.length === 0 ? <EmptyState message={t('msg.no_data')} /> : offices.map((o) => (
        <Card key={o.id}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '700', color: colors.text }}>{o.name}</Text>
              {o.address ? <Body soft>{o.address}</Body> : null}
              <Body soft>{o.department_code ?? 'general'}</Body>
            </View>
            {o.distanceM != null ? (
              <View style={{ backgroundColor: colors.primaryGlow, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 }}>
                <Text style={{ color: colors.primary, fontWeight: '700', fontSize: 12 }}>
                  {o.distanceM < 1000 ? `${Math.round(o.distanceM)} m` : `${(o.distanceM / 1000).toFixed(1)} km`}
                </Text>
              </View>
            ) : null}
          </View>
          <AppButton label="Open in Maps" kind="secondary" onPress={() => openInMaps(o.lat, o.lng, o.name)} />
        </Card>
      ))}
    </Screen>
  );
}
