// CivicLens - Civic GPS & Nearby Government Offices Locator Screen

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  SafeAreaView,
  Linking,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE } from '../constants/theme';
import { getNearbyCivicOffices } from '../services/locationService';

export default function CivicLocatorScreen() {
  const { theme, t, selectedCity, userProfile, getCityName } = useApp();
  const nearbyOffices = getNearbyCivicOffices(selectedCity);

  const handleCall = (number) => {
    if (number) Linking.openURL(`tel:${number}`);
  };

  const handleOpenMaps = (name, address) => {
    const query = encodeURIComponent(`${name}, ${address}`);
    const url = Platform.select({
      ios: `maps:0,0?q=${query}`,
      android: `geo:0,0?q=${query}`,
      default: `https://www.google.com/maps/search/?api=1&query=${query}`,
    });
    Linking.openURL(url);
  };

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={[styles.screenTitle, { color: theme.text }]}>
            📍 {t('civicGPS')}
          </Text>
          <Text style={[styles.screenSubtitle, { color: theme.textSecondary }]}>
            {t('civicGPSSub')}
          </Text>
        </View>

        {/* Current Location Badge */}
        <View style={[styles.locationBanner, { backgroundColor: theme.primaryGlow, borderColor: theme.primary }]}>
          <Ionicons name="navigate-circle" size={22} color={theme.primaryLight} />
          <View style={{ flex: 1 }}>
            <Text style={[styles.locationHeading, { color: theme.text }]}>
              {t('selectCity')}: {getCityName(selectedCity)}
            </Text>
            <Text style={[styles.locationSub, { color: theme.textSecondary }]}>
              {userProfile.address || 'GPS Coordinates Locked'}
            </Text>
          </View>
        </View>

        {/* Nearby Offices List */}
        <View style={styles.sectionHeaderRow}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>
            Closest Administrative Centers
          </Text>
        </View>

        {nearbyOffices.map((office) => (
          <View
            key={office.id}
            style={[styles.officeCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
          >
            {/* Top row */}
            <View style={styles.officeHeader}>
              <Text style={styles.officeIcon}>{office.icon}</Text>
              <View style={{ flex: 1 }}>
                <View style={styles.typeBadgeRow}>
                  <Text style={[styles.officeType, { color: theme.primaryLight }]}>
                    {office.type}
                  </Text>
                  <View style={[styles.distanceBadge, { backgroundColor: theme.surface }]}>
                    <Ionicons name="walk-outline" size={12} color={theme.accentEmerald} />
                    <Text style={[styles.distanceText, { color: theme.accentEmerald }]}>
                      {office.distanceKm} km ({office.estTimeMins} min)
                    </Text>
                  </View>
                </View>

                <Text style={[styles.officeName, { color: theme.text }]}>
                  {office.name}
                </Text>
              </View>
            </View>

            {/* Address & Hours */}
            <View style={[styles.detailsBox, { backgroundColor: theme.surface }]}>
              <View style={styles.detailItem}>
                <Ionicons name="location-outline" size={14} color={theme.accentRose} />
                <Text style={[styles.detailText, { color: theme.textSecondary }]} numberOfLines={2}>
                  {office.address}
                </Text>
              </View>
              <View style={styles.detailItem}>
                <Ionicons name="time-outline" size={14} color={theme.textMuted} />
                <Text style={[styles.detailText, { color: theme.textMuted }]}>
                  {office.hours}
                </Text>
              </View>
              <View style={styles.detailItem}>
                <Ionicons name="person-outline" size={14} color={theme.primary} />
                <Text style={[styles.detailText, { color: theme.textMuted }]}>
                  {office.officer}
                </Text>
              </View>
            </View>

            {/* Services Offered */}
            <Text style={[styles.servicesTitle, { color: theme.textMuted }]}>
              KEY SERVICES AT THIS LOCATION:
            </Text>
            <View style={styles.servicesRow}>
              {office.services?.map((srv, idx) => (
                <View key={idx} style={[styles.serviceTag, { backgroundColor: theme.inputBg }]}>
                  <Text style={[styles.serviceTagText, { color: theme.textSecondary }]}>• {srv}</Text>
                </View>
              ))}
            </View>

            {/* Action Buttons (Call & Directions) */}
            <View style={styles.actionButtonsRow}>
              <TouchableOpacity
                style={[styles.callBtn, { backgroundColor: theme.surface, borderColor: theme.border }]}
                onPress={() => handleCall(office.phone)}
                activeOpacity={0.8}
              >
                <Ionicons name="call" size={14} color={theme.accentEmerald} />
                <Text style={[styles.callBtnText, { color: theme.text }]}>Call: {office.phone}</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.directionsBtn, { backgroundColor: theme.primary }]}
                onPress={() => handleOpenMaps(office.name, office.address)}
                activeOpacity={0.85}
              >
                <Ionicons name="navigate" size={14} color="#FFFFFF" />
                <Text style={styles.directionsBtnText}>Directions</Text>
              </TouchableOpacity>
            </View>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  scrollContent: { paddingHorizontal: SPACING.md, paddingBottom: 60 },
  header: { paddingTop: Platform.OS === 'android' ? 30 : 10, marginBottom: SPACING.md },
  screenTitle: { fontSize: 20, fontWeight: '800' },
  screenSubtitle: { fontSize: 12, marginTop: 3 },
  locationBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    gap: 10,
    marginBottom: SPACING.md,
  },
  locationHeading: { fontSize: 13, fontWeight: '800' },
  locationSub: { fontSize: 11, marginTop: 2 },
  sectionHeaderRow: { marginBottom: SPACING.sm, marginTop: SPACING.xs },
  sectionTitle: { fontSize: 14, fontWeight: '800' },
  officeCard: {
    borderRadius: RADIUS.lg,
    padding: SPACING.md,
    borderWidth: 1,
    marginBottom: 12,
  },
  officeHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginBottom: 8 },
  officeIcon: { fontSize: 24 },
  typeBadgeRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 },
  officeType: { fontSize: 11, fontWeight: '800' },
  distanceBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.full },
  distanceText: { fontSize: 10, fontWeight: '800' },
  officeName: { fontSize: 14, fontWeight: '800' },
  detailsBox: { borderRadius: RADIUS.md, padding: 10, gap: 6, marginBottom: 8 },
  detailItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  detailText: { fontSize: 11, flex: 1 },
  servicesTitle: { fontSize: 9, fontWeight: '800', letterSpacing: 0.5, marginBottom: 4 },
  servicesRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginBottom: 10 },
  serviceTag: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.xs },
  serviceTagText: { fontSize: 10 },
  actionButtonsRow: { flexDirection: 'row', gap: 8 },
  callBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 9,
    borderRadius: RADIUS.sm,
    borderWidth: 1,
    gap: 4,
  },
  callBtnText: { fontSize: 11, fontWeight: '700' },
  directionsBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 9,
    borderRadius: RADIUS.sm,
    gap: 4,
  },
  directionsBtnText: { color: '#FFFFFF', fontSize: 11, fontWeight: '800' },
});
