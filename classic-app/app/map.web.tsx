// Web build of the GIS map. react-native-maps has no web target (native Google/Apple Maps SDK
// only), so this uses Leaflet + OpenStreetMap tiles instead - real, live map, no API key needed.
// Expo Router / Metro picks this file automatically on web and app/map.tsx everywhere else.
import 'leaflet/dist/leaflet.css';
import React, { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { Circle, CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet';
import { Body, EmptyState, ErrorBanner, InfoBanner, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { RadarResponse } from '../src/api/types.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { fontFamily } from '../src/theme.ts';
import { useTheme } from '../src/theme/ThemeContext.tsx';

export default function CivicMapWeb() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const [r, setR] = useState<RadarResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { endpoints.radar().then(setR).catch((e) => setError(e?.message ?? 'Could not load the map data.')); }, []);
  const first = r?.hotspots[0] ?? r?.offices[0];
  return (
    <Screen scroll={false}>
      <Text style={{ fontFamily: fontFamily.displayBold, fontSize: 20, color: colors.text }}>🗺️ {t('nav.gis')}</Text>
      {error ? <ErrorBanner message={error} /> : !r ? <Loading /> : !first ? <EmptyState message={t('msg.no_data')} /> : (
        <>
          <Body soft>{r.mappable} of {r.total_complaints} complaints have coordinates.</Body>
          {r.privacy ? <InfoBanner message={r.privacy} /> : null}
          <View style={{ flex: 1, minHeight: 360, borderRadius: 12, overflow: 'hidden' }}>
            <MapContainer center={[first.lat, first.lng]} zoom={12} style={{ height: '100%', width: '100%', minHeight: 360 }}>
              <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              {r.hotspots.map((h, i) => (
                <Circle key={i} center={[h.lat, h.lng]} radius={150 + 60 * Math.min(h.count, 10)} pathOptions={{ color: colors.bad, fillColor: colors.bad, fillOpacity: 0.25 }}>
                  <Popup>{h.count} complaint{h.count === 1 ? '' : 's'} here</Popup>
                </Circle>
              ))}
              {r.offices.map((o) => (
                <CircleMarker key={o.id} center={[o.lat, o.lng]} radius={7} pathOptions={{ color: colors.primary, fillColor: colors.primary, fillOpacity: 0.9 }}>
                  <Popup>{o.name}</Popup>
                </CircleMarker>
              ))}
            </MapContainer>
          </View>
        </>
      )}
    </Screen>
  );
}
