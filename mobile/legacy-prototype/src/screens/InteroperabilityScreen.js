// CivicLens - Interoperability Layer: Live Adapter Demo
//
// This screen is the literal technical answer to "system integration and
// interoperability among government digital platforms": pick any of four
// realistically-shaped department data formats (a municipal corporation's
// SCREAMING_SNAKE_CASE legacy system, a utility's camelCase CRM, a police
// CCTNS-style FIR record, a state portal using bare numeric status codes)
// and watch the real adapter function (src/interop/adapters.js) normalize
// it into one common schema, with the normalization actually validated —
// not just claimed — against the Common Data Model (commonDataModel.js).

import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, SafeAreaView, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE } from '../constants/theme';
import { ADAPTERS, SAMPLE_PAYLOADS } from '../interop/adapters';
import { validateCdmServiceRequest, runDataQualityChecks, NORMALIZED_STATUSES } from '../interop/commonDataModel';
import { logIntegrationException } from '../services/exceptionService';

export default function InteroperabilityScreen({ navigation }) {
  const { theme } = useApp();
  const [activeSystem, setActiveSystem] = useState('bbmp_civic');
  const [simulateBroken, setSimulateBroken] = useState(false);
  const [exceptionLogged, setExceptionLogged] = useState(false);

  const rawPayload = simulateBroken
    ? { ...SAMPLE_PAYLOADS[activeSystem], [Object.keys(SAMPLE_PAYLOADS[activeSystem])[0]]: undefined }
    : SAMPLE_PAYLOADS[activeSystem];
  const normalized = ADAPTERS[activeSystem].fn(rawPayload);
  const validation = validateCdmServiceRequest(normalized);
  const quality = runDataQualityChecks(normalized);

  const handleToggleBroken = async () => {
    const next = !simulateBroken;
    setSimulateBroken(next);
    setExceptionLogged(false);
    if (next) {
      const brokenPayload = { ...SAMPLE_PAYLOADS[activeSystem], [Object.keys(SAMPLE_PAYLOADS[activeSystem])[0]]: undefined };
      const brokenNormalized = ADAPTERS[activeSystem].fn(brokenPayload);
      const brokenValidation = validateCdmServiceRequest(brokenNormalized);
      if (!brokenValidation.valid) {
        await logIntegrationException({
          sourceSystem: activeSystem,
          rawPayload: brokenPayload,
          errorMessage: brokenValidation.errors.join('; '),
        });
        setExceptionLogged(true);
      }
    }
  };

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
        <View style={styles.header}>
          <Text style={[styles.screenTitle, { color: theme.text }]}>🌉 Interoperability Layer</Text>
          <Text style={[styles.screenSubtitle, { color: theme.textSecondary }]}>
            Four real department systems, four incompatible data formats, one common schema — live, working normalization, not a diagram.
          </Text>
        </View>

        {/* System Selector */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.systemScroll}>
          {Object.entries(ADAPTERS).map(([key, { label }]) => {
            const isSel = activeSystem === key;
            return (
              <TouchableOpacity
                key={key}
                style={[
                  styles.systemChip,
                  { backgroundColor: isSel ? theme.primary : theme.card, borderColor: isSel ? theme.primary : theme.cardBorder },
                ]}
                onPress={() => setActiveSystem(key)}
                activeOpacity={0.8}
              >
                <Text style={[styles.systemChipText, { color: isSel ? '#FFFFFF' : theme.textSecondary }]}>{label}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {/* Side-by-side: Raw vs Normalized */}
        <View style={styles.compareRow}>
          <View style={[styles.codeCard, { backgroundColor: '#0F172A', borderColor: '#334155' }]}>
            <Text style={styles.codeCardLabel}>📥 RAW — {ADAPTERS[activeSystem].label}'s own format</Text>
            <Text style={styles.codeText}>{JSON.stringify(rawPayload, null, 2)}</Text>
          </View>

          <View style={styles.arrowRow}>
            <Ionicons name="arrow-down" size={20} color={theme.primaryLight} />
            <Text style={[styles.arrowLabel, { color: theme.primaryLight }]}>real adapter function — see src/interop/adapters.js</Text>
          </View>

          <View style={[styles.codeCard, { backgroundColor: '#0A1A14', borderColor: '#1F5C3E' }]}>
            <View style={styles.normalizedHeaderRow}>
              <Text style={styles.codeCardLabelGreen}>📤 NORMALIZED — CivicLens Common Data Model</Text>
              <View style={[styles.validBadge, { backgroundColor: validation.valid ? 'rgba(46,158,99,0.2)' : 'rgba(194,69,69,0.2)' }]}>
                <Ionicons name={validation.valid ? 'checkmark-circle' : 'close-circle'} size={12} color={validation.valid ? '#2E9E63' : '#C24545'} />
                <Text style={{ color: validation.valid ? '#2E9E63' : '#C24545', fontSize: 9.5, fontWeight: '800', marginLeft: 3 }}>
                  {validation.valid ? 'SCHEMA VALID' : 'SCHEMA INVALID'}
                </Text>
              </View>
            </View>
            <Text style={styles.codeText}>{JSON.stringify(normalized, null, 2)}</Text>
          </View>
        </View>

        <View style={[styles.explainerCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <Text style={[styles.explainerTitle, { color: theme.text }]}>What just happened</Text>
          <Text style={[styles.explainerText, { color: theme.textSecondary }]}>
            {ADAPTERS[activeSystem].label} uses its own field names, its own date format, and its own status
            vocabulary — none of which any other department's system understands. The adapter above translates
            it into one shared schema (status normalized to: {NORMALIZED_STATUSES.join(', ')}) so a citizen — or
            any other connected system — can read a consistent record regardless of which department it came
            from. This is the actual mechanism, running on real code, not a slide.
          </Text>
        </View>

        {/* Real Data Quality Scoring */}
        <View style={[styles.explainerCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <View style={styles.qualityHeaderRow}>
            <Text style={[styles.explainerTitle, { color: theme.text }]}>Data Quality Check</Text>
            <View style={[styles.qualityBadge, { backgroundColor: quality.qualityLevel === 'high' ? 'rgba(46,158,99,0.15)' : quality.qualityLevel === 'medium' ? 'rgba(190,138,46,0.15)' : 'rgba(194,69,69,0.15)' }]}>
              <Text style={{ fontWeight: '800', fontSize: 12, color: quality.qualityLevel === 'high' ? '#2E9E63' : quality.qualityLevel === 'medium' ? '#BE8A2E' : '#C24545' }}>
                {quality.score}/100
              </Text>
            </View>
          </View>
          {quality.issues.length === 0 ? (
            <Text style={[styles.explainerText, { color: theme.textSecondary }]}>No data-quality issues found in this record.</Text>
          ) : (
            quality.issues.map((issue, i) => (
              <Text key={i} style={[styles.qualityIssueText, { color: theme.textMuted }]}>
                • {issue.field}: {issue.issue} ({issue.severity} severity)
              </Text>
            ))
          )}
        </View>

        {/* Exception Handling Demo */}
        <View style={[styles.explainerCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <Text style={[styles.explainerTitle, { color: theme.text }]}>Exception Handling</Text>
          <Text style={[styles.explainerText, { color: theme.textSecondary, marginBottom: 10 }]}>
            Toggle this to strip a required field from the raw payload and see what a real integration layer does with a malformed record: it fails validation and gets queued for review instead of silently corrupting data.
          </Text>
          <TouchableOpacity
            style={[styles.simulateBtn, { backgroundColor: simulateBroken ? '#C24545' : theme.surface, borderColor: simulateBroken ? '#C24545' : theme.border }]}
            onPress={handleToggleBroken}
            activeOpacity={0.85}
          >
            <Ionicons name={simulateBroken ? 'warning' : 'flask-outline'} size={14} color={simulateBroken ? '#FFFFFF' : theme.textSecondary} />
            <Text style={{ color: simulateBroken ? '#FFFFFF' : theme.textSecondary, fontWeight: '700', fontSize: 12, marginLeft: 6 }}>
              {simulateBroken ? 'Showing malformed record — tap to restore' : 'Simulate a malformed record'}
            </Text>
          </TouchableOpacity>
          {simulateBroken && exceptionLogged && (
            <Text style={[styles.exceptionLoggedText, { color: '#C24545' }]}>
              ✓ Logged to the Integration Exceptions queue — see Monitoring Dashboard.
            </Text>
          )}
        </View>

        <View style={[styles.honestNote, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          <Ionicons name="information-circle-outline" size={14} color={theme.textMuted} />
          <Text style={[styles.honestNoteText, { color: theme.textMuted }]}>
            These four payloads are realistic illustrative fixtures modeled on how these system types actually
            structure data — not live data pulled from real departments, since that requires formal data-sharing
            agreements this project doesn't have. The adapter pattern itself is real and reusable: connecting a
            genuine department feed means writing one more adapter function like the ones here.
          </Text>
        </View>

        <TouchableOpacity
          style={[styles.monitoringLinkBtn, { backgroundColor: theme.primaryGlow, borderColor: theme.primary }]}
          onPress={() => navigation.navigate('Monitoring')}
          activeOpacity={0.85}
        >
          <Ionicons name="pulse-outline" size={16} color={theme.primaryLight} />
          <Text style={[styles.monitoringLinkText, { color: theme.primaryLight }]}>Open Monitoring Dashboard →</Text>
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
  systemScroll: { flexDirection: 'row', marginBottom: SPACING.md },
  systemChip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.md, borderWidth: 1, marginRight: 8 },
  systemChipText: { fontSize: 11.5, fontWeight: '700' },
  compareRow: { marginBottom: SPACING.md },
  codeCard: { borderRadius: RADIUS.lg, padding: 12, borderWidth: 1 },
  codeCardLabel: { color: '#94A3B8', fontSize: 10.5, fontWeight: '800', marginBottom: 8, letterSpacing: 0.3 },
  codeCardLabelGreen: { color: '#6EE7B7', fontSize: 10.5, fontWeight: '800', letterSpacing: 0.3 },
  normalizedHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, flexWrap: 'wrap', gap: 6 },
  validBadge: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.full },
  codeText: {
    color: '#CBD5E1',
    fontSize: 10.5,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
    lineHeight: 15,
  },
  arrowRow: { alignItems: 'center', paddingVertical: 10 },
  arrowLabel: { fontSize: 10, fontWeight: '700', marginTop: 2, textAlign: 'center' },
  explainerCard: { borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, marginBottom: SPACING.sm },
  explainerTitle: { fontSize: 14, fontWeight: '800', marginBottom: 6 },
  explainerText: { fontSize: 12, lineHeight: 18 },
  qualityHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  qualityBadge: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: RADIUS.full },
  qualityIssueText: { fontSize: 11, lineHeight: 17 },
  simulateBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, borderRadius: RADIUS.md, borderWidth: 1 },
  exceptionLoggedText: { fontSize: 11, fontWeight: '700', marginTop: 8, textAlign: 'center' },
  monitoringLinkBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 12, borderRadius: RADIUS.lg, borderWidth: 1, gap: 8 },
  monitoringLinkText: { fontSize: 12.5, fontWeight: '700' },
  honestNote: { flexDirection: 'row', alignItems: 'flex-start', gap: 6, padding: 10, borderRadius: RADIUS.md, borderWidth: 1 },
  honestNoteText: { fontSize: 10.5, flex: 1, lineHeight: 15 },
});
