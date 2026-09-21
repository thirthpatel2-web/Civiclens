// CivicLens - Fragmentation Diagnostic
//
// Directly addresses "fragmented service delivery": quantifies it rather
// than just asserting it, using a sourced national statistic plus the
// citizen's own real filing history from CivicLens (real Supabase rows,
// not simulated numbers).

import React from 'react';
import { View, Text, StyleSheet, ScrollView, SafeAreaView, Platform, Linking, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE } from '../constants/theme';
import { computeFragmentationDiagnostic, NATIONAL_CONTEXT } from '../services/fragmentationService';

export default function FragmentationScreen({ navigation }) {
  const { theme, complaints, getCityName, selectedCity } = useApp();
  const diagnostic = computeFragmentationDiagnostic(complaints);

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
        <View style={styles.header}>
          <Text style={[styles.screenTitle, { color: theme.text }]}>📊 Fragmentation Diagnostic</Text>
          <Text style={[styles.screenSubtitle, { color: theme.textSecondary }]}>
            How scattered is civic service delivery, really? A sourced national picture, plus your own numbers.
          </Text>
        </View>

        {/* National Context — sourced, not invented */}
        <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <View style={styles.cardHeaderRow}>
            <Ionicons name="globe-outline" size={16} color={theme.primaryLight} />
            <Text style={[styles.cardTitle, { color: theme.text }]}>The National Picture</Text>
          </View>
          <Text style={[styles.cardBody, { color: theme.textSecondary }]}>{NATIONAL_CONTEXT.statText}.</Text>
          <Text style={[styles.cardBody, { color: theme.textSecondary, marginTop: 6 }]}>{NATIONAL_CONTEXT.interpretation}</Text>
          <Text style={[styles.sourceText, { color: theme.textMuted }]}>Source: {NATIONAL_CONTEXT.source}</Text>
        </View>

        {/* Personal Diagnostic — real, computed from this citizen's actual data */}
        <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <View style={styles.cardHeaderRow}>
            <Ionicons name="person-circle-outline" size={16} color={theme.accentEmerald} />
            <Text style={[styles.cardTitle, { color: theme.text }]}>Your Own Fragmentation Footprint</Text>
          </View>

          {!diagnostic.hasEnoughDataToShow ? (
            <Text style={[styles.cardBody, { color: theme.textMuted }]}>
              File a complaint or RTI application to see your personal diagnostic here — computed from your real CivicLens history, not a demo number.
            </Text>
          ) : (
            <>
              <View style={styles.statsGrid}>
                <View style={styles.statBox}>
                  <Text style={[styles.statValue, { color: theme.primaryLight }]}>{diagnostic.totalFilings}</Text>
                  <Text style={[styles.statLabel, { color: theme.textMuted }]}>Requests Filed</Text>
                </View>
                <View style={styles.statBox}>
                  <Text style={[styles.statValue, { color: theme.accentSaffron }]}>{diagnostic.distinctDepartmentCount}</Text>
                  <Text style={[styles.statLabel, { color: theme.textMuted }]}>Separate Departments</Text>
                </View>
                <View style={styles.statBox}>
                  <Text style={[styles.statValue, { color: theme.accentEmerald }]}>{diagnostic.redundantEntriesAvoided}</Text>
                  <Text style={[styles.statLabel, { color: theme.textMuted }]}>Repeated Fields Avoided</Text>
                </View>
              </View>
              <Text style={[styles.cardBody, { color: theme.textSecondary, marginTop: 10 }]}>
                Without a unified profile, each of your {diagnostic.totalFilings} filings across {diagnostic.distinctDepartmentCount}{' '}
                different department{diagnostic.distinctDepartmentCount === 1 ? '' : 's'} would have needed your name, phone, email,
                address, city, and pincode re-entered on that department's own form. CivicLens's single profile means you typed those{' '}
                {diagnostic.kycFieldsTracked.length} fields once — saving {diagnostic.redundantEntriesAvoided} repeated entries so far, in{' '}
                {getCityName(selectedCity)} alone.
              </Text>
            </>
          )}
        </View>

        {/* The Solution Pattern */}
        <TouchableOpacity
          style={[styles.solutionCard, { backgroundColor: theme.primaryGlow, borderColor: theme.primary }]}
          onPress={() => navigation.navigate('Interoperability')}
          activeOpacity={0.85}
        >
          <Ionicons name="git-network-outline" size={20} color={theme.primaryLight} />
          <View style={{ flex: 1, marginLeft: 10 }}>
            <Text style={[styles.solutionTitle, { color: theme.primaryLight }]}>See the technical fix →</Text>
            <Text style={[styles.solutionSub, { color: theme.textSecondary }]}>
              CivicLens's Interoperability Layer normalizes different departments' data formats into one schema, live.
            </Text>
          </View>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  scrollContent: { paddingHorizontal: SPACING.md, paddingBottom: 60 },
  header: { paddingTop: Platform.OS === 'android' ? 30 : 10, marginBottom: SPACING.md },
  screenTitle: { fontSize: 20, fontWeight: '800' },
  screenSubtitle: { fontSize: 12, marginTop: 4, lineHeight: 17 },
  card: { borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, marginBottom: SPACING.md },
  cardHeaderRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  cardTitle: { fontSize: 14, fontWeight: '800' },
  cardBody: { fontSize: 12.5, lineHeight: 19 },
  sourceText: { fontSize: 10, marginTop: 8, fontStyle: 'italic' },
  statsGrid: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 },
  statBox: { alignItems: 'center', flex: 1 },
  statValue: { fontSize: 22, fontWeight: '800' },
  statLabel: { fontSize: 9.5, marginTop: 2, textAlign: 'center' },
  solutionCard: { flexDirection: 'row', alignItems: 'center', borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1 },
  solutionTitle: { fontSize: 13, fontWeight: '800' },
  solutionSub: { fontSize: 11, marginTop: 3, lineHeight: 15 },
});
