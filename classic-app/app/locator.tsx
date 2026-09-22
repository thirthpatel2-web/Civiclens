// Ported from legacy-prototype/src/screens/CivicLocatorScreen.js (location banner + office cards
// with a distance badge and a Directions action). The zip's per-office phone/hours/officer/services
// fields were invented placeholder data; our real office records only have name/address/coordinates,
// so the card shows exactly that plus a real, computed distance - nothing fabricated.
import React, { useEffect, useMemo, useState } from 'react';
import { Linking, Platform, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { AppButton, Body, Card, Chip, EmptyState, ErrorBanner, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { DirectoryData } from '../src/api/types.ts';
import { useDeviceLocation } from '../src/hooks/useDeviceLocation.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { useTheme } from '../src/theme/ThemeContext.tsx';
import { fontFamily, radius, shadow, spacing } from '../src/theme.ts';

function haversineMeters(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371000;
  const toRad = (dv: number) => (dv * Math.PI) / 180;
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
      <Text style={{ fontFamily: fontFamily.displayBold, fontSize: 20, color: colors.text }}>📍 {t('nav.locator')}</Text>
      <Body soft>The nearest real government offices, sorted by your actual device location.</Body>
      {error ? <ErrorBanner message={error} /> : null}

      <View style={[{ flexDirection: 'row', alignItems: 'center', padding: 12, borderRadius: radius.md, borderWidth: 1, gap: 10, backgroundColor: colors.primaryGlow, borderColor: colors.primary }]}>
        <Ionicons name="navigate-circle" size={22} color={colors.primaryLight} />
        <View style={{ flex: 1 }}>
          {loc.state.kind === 'ok' ? (
            <>
              <Text style={{ fontSize: 13, fontWeight: '800', color: colors.text }}>{loc.state.address?.city ?? 'Location locked'}{loc.state.address?.state ? `, ${loc.state.address.state}` : ''}</Text>
              <Text style={{ fontSize: 11, marginTop: 2, color: colors.textSoft }}>{loc.state.address?.area ?? `${loc.state.lat.toFixed(4)}, ${loc.state.lng.toFixed(4)}`}</Text>
            </>
          ) : (
            <>
              <Text style={{ fontSize: 13, fontWeight: '800', color: colors.text }}>{loc.state.kind === 'locating' ? 'Finding your location…' : 'Location not available yet'}</Text>
              <AppButton label="Use my location" kind="secondary" onPress={loc.request} busy={loc.state.kind === 'locating'} />
            </>
          )}
        </View>
      </View>
      {loc.state.kind === 'denied' ? <ErrorBanner message="Location permission was denied - offices are shown unsorted. You can still open any office in Maps." onRetry={loc.request} /> : null}

      {d ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          <Chip label="All departments" selected={dept === null} onPress={() => setDept(null)} />
          {d.departments.map((x) => <Chip key={x.code} label={x.name} selected={dept === x.code} onPress={() => setDept(x.code)} />)}
        </View>
      ) : null}

      <Text style={{ fontSize: 12, fontWeight: '800', textTransform: 'uppercase', color: colors.text }}>Closest Administrative Centers</Text>
      {!d ? <Loading label={t('msg.loading')} /> : offices.length === 0 ? <EmptyState message={t('msg.no_data')} /> : offices.map((o) => (
        <View key={o.id} style={[{ borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, backgroundColor: colors.card, borderColor: colors.border, gap: 8 }, shadow.sm]}>
          <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}>
            <Text style={{ fontSize: 24 }}>🏛️</Text>
            <View style={{ flex: 1 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ fontSize: 11, fontWeight: '800', color: colors.primaryLight }}>{o.department_code ?? 'GENERAL'}</Text>
                {o.distanceM != null ? (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.full, backgroundColor: colors.surfaceElevated }}>
                    <Ionicons name="walk-outline" size={12} color={colors.accentEmerald} />
                    <Text style={{ fontSize: 10, fontWeight: '800', color: colors.accentEmerald }}>{o.distanceM < 1000 ? `${Math.round(o.distanceM)} m` : `${(o.distanceM / 1000).toFixed(1)} km`}</Text>
                  </View>
                ) : null}
              </View>
              <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text }}>{o.name}</Text>
            </View>
          </View>
          {o.address ? (
            <View style={{ borderRadius: radius.md, padding: 10, backgroundColor: colors.surfaceElevated }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Ionicons name="location-outline" size={14} color={colors.accentRose} />
                <Text style={{ fontSize: 11, flex: 1, color: colors.textSoft }}>{o.address}</Text>
              </View>
            </View>
          ) : null}
          <AppButton label="Directions" icon="🧭" onPress={() => openInMaps(o.lat, o.lng, o.name)} />
        </View>
      ))}
    </Screen>
  );
}
