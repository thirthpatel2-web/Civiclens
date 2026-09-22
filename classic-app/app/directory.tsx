// Ported from legacy-prototype/src/screens/DepartmentDirectoryScreen.js (search bar, emergency
// hotlines strip, department cards with their services/offices). The zip's 6-tier classification
// and per-officer name/email/portal fields don't exist in our real schema (app.services.location_service
// never invents an address, and this app never invented officer contact details either) - so each
// department card here shows only what the backend actually has: real services and real offices,
// with "Open in Maps" using the office's real coordinates.
import React, { useEffect, useMemo, useState } from 'react';
import { Linking, Platform, Pressable, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Body, EmptyState, ErrorBanner, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { DirectoryData, Helpline } from '../src/api/types.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { useTheme } from '../src/theme/ThemeContext.tsx';
import { fontFamily, radius, shadow, spacing } from '../src/theme.ts';

const openInMaps = (lat: number, lng: number, label: string) => {
  const url = Platform.select({
    ios: `maps:0,0?q=${encodeURIComponent(label)}@${lat},${lng}`,
    android: `geo:${lat},${lng}?q=${lat},${lng}(${encodeURIComponent(label)})`,
    default: `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`,
  });
  Linking.openURL(url!).catch(() => Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${lat},${lng}`));
};

export default function Directory() {
  const { t, lang } = useI18n();
  const { colors } = useTheme();
  const [d, setD] = useState<DirectoryData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [helplines, setHelplines] = useState<Helpline[]>([]);

  useEffect(() => { endpoints.directory().then(setD).catch((e: any) => setError(e?.message ?? 'Could not load the department directory.')); }, []);
  useEffect(() => { endpoints.helplines(lang).then((r) => setHelplines(r.items)).catch(() => undefined); }, [lang]);

  const q = search.trim().toLowerCase();
  const departments = useMemo(() => {
    if (!d) return [];
    if (!q) return d.departments;
    return d.departments.filter((dept) =>
      dept.name.toLowerCase().includes(q) ||
      d.services.some((s) => s.department_code === dept.code && s.name.toLowerCase().includes(q)) ||
      d.offices.some((o) => o.department_code === dept.code && o.name.toLowerCase().includes(q)));
  }, [d, q]);

  if (error) return <Screen><Text style={{ fontFamily: fontFamily.displayBold, fontSize: 20, color: colors.text }}>{t('nav.departments')}</Text><ErrorBanner message={error} /></Screen>;
  if (!d) return <Screen><Loading label={t('msg.loading')} /></Screen>;

  return (
    <Screen>
      <Text style={{ fontFamily: fontFamily.displayBold, fontSize: 20, color: colors.text }}>🏛️ {t('nav.departments')}</Text>
      <Body soft>Real departments, services and offices configured for this deployment.</Body>

      <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, borderRadius: radius.lg, height: 46, borderWidth: 1, backgroundColor: colors.card, borderColor: colors.border }}>
        <Ionicons name="search" size={18} color={colors.textMuted} style={{ marginRight: 8 }} />
        <TextInput style={{ flex: 1, fontFamily: fontFamily.body, fontSize: 13, color: colors.text }} placeholder="Search departments, services or offices..." placeholderTextColor={colors.textMuted} value={search} onChangeText={setSearch} />
        {search.length > 0 ? <Pressable onPress={() => setSearch('')}><Ionicons name="close-circle" size={18} color={colors.textMuted} /></Pressable> : null}
      </View>

      {helplines.length > 0 ? (
        <View>
          <Text style={{ fontSize: 12, fontWeight: '800', textTransform: 'uppercase', marginBottom: 6, color: colors.text }}>🚨 24x7 Emergency Hotlines</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {helplines.map((h) => (
              <Pressable key={h.code} accessibilityRole="button" onPress={() => Linking.openURL(h.tel_uri)} style={{ width: 118, borderRadius: radius.lg, padding: 8, borderWidth: 1, alignItems: 'center', backgroundColor: colors.card, borderColor: colors.border }}>
                <Text numberOfLines={1} style={{ fontSize: 10, fontWeight: '700', textAlign: 'center', marginBottom: 4, color: colors.text }}>{h.name}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.full, backgroundColor: colors.primaryGlow }}>
                  <Ionicons name="call" size={11} color={colors.primaryLight} />
                  <Text style={{ fontSize: 10, fontWeight: '800', color: colors.primaryLight }}>{h.number}</Text>
                </View>
              </Pressable>
            ))}
          </View>
        </View>
      ) : null}

      <Text style={{ fontSize: 12, fontWeight: '800', textTransform: 'uppercase', color: colors.text }}>Public Authorities ({departments.length})</Text>
      {departments.length === 0 ? <EmptyState message={t('msg.no_data')} /> : departments.map((dept) => {
        const services = d.services.filter((s) => s.department_code === dept.code);
        const offices = d.offices.filter((o) => o.department_code === dept.code);
        return (
          <View key={dept.code} style={[{ borderRadius: radius.xl, padding: spacing.md, borderWidth: 1, backgroundColor: colors.card, borderColor: colors.border, gap: 8 }, shadow.sm]}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{ width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primaryGlow }}>
                <Ionicons name="business" size={18} color={colors.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontFamily: fontFamily.bodyExtraBold, fontSize: 14, color: colors.text }}>{dept.name}</Text>
                <Text style={{ fontSize: 11, color: colors.textMuted }}>{services.length} service{services.length === 1 ? '' : 's'} · {offices.length} office{offices.length === 1 ? '' : 's'}</Text>
              </View>
            </View>

            {services.length > 0 ? (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                {services.map((s) => (
                  <View key={s.code} style={{ backgroundColor: colors.surfaceElevated, borderRadius: radius.sm, paddingHorizontal: 8, paddingVertical: 4 }}>
                    <Text style={{ fontSize: 10.5, color: colors.textSoft }}>{s.name}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            {offices.map((o) => (
              <Pressable key={o.id} accessibilityRole="button" onPress={() => openInMaps(o.lat, o.lng, o.name)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: radius.md, padding: 8, backgroundColor: colors.surfaceElevated }}>
                <Ionicons name="location" size={14} color={colors.accentEmerald} />
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text }}>{o.name}</Text>
                  {o.address ? <Text style={{ fontSize: 10.5, color: colors.textMuted }}>{o.address}</Text> : null}
                </View>
                <Text style={{ fontSize: 11, fontWeight: '700', color: colors.primaryLight }}>Directions →</Text>
              </Pressable>
            ))}
          </View>
        );
      })}
    </Screen>
  );
}
