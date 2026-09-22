import React, { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import MapView, { Circle, Marker } from 'react-native-maps';
import { Body, EmptyState, ErrorBanner, InfoBanner, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { RadarResponse } from '../src/api/types.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { fontFamily, withAlpha } from '../src/theme.ts';
import { useTheme } from '../src/theme/ThemeContext.tsx';

export default function CivicMap() {
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
          <View style={{ flex: 1, minHeight: 360 }}>
            <MapView style={{ flex: 1 }} initialRegion={{ latitude: first.lat, longitude: first.lng, latitudeDelta: 0.1, longitudeDelta: 0.1 }}>
              {r.hotspots.map((h, i) => <Circle key={i} center={{ latitude: h.lat, longitude: h.lng }} radius={150 + 60 * Math.min(h.count, 10)} strokeColor={colors.bad} fillColor={withAlpha(colors.bad, 0.25)} />)}
              {r.offices.map((o) => <Marker key={o.id} coordinate={{ latitude: o.lat, longitude: o.lng }} title={o.name} />)}
            </MapView>
          </View>
        </>
      )}
    </Screen>
  );
}
