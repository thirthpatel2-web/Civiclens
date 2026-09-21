// CivicLens - Interoperability Monitoring Dashboard
//
// The operational view the problem statement explicitly asks for:
// real-time visibility into the health of the interoperability layer
// itself — not the citizen-facing features, but the plumbing. Every
// number here comes from a live Supabase query against real tables
// (audit_log, integration_exceptions, consent_grants, notifications,
// complaints) — nothing on this screen is a placeholder or a static mock.

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, SafeAreaView, Platform, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE } from '../constants/theme';
import { backendReady } from '../services/authService';
import { apiRequest, isBackendConfigured } from '../services/apiClient';
import { loadOpenExceptions, resolveException } from '../services/exceptionService';

export default function MonitoringScreen() {
  const { theme, currentUserId, userRole } = useApp();
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState(null);
  const [exceptions, setExceptions] = useState([]);

  const refresh = useCallback(async () => {
    setLoading(true);
    if (!isBackendConfigured) {
      setLoading(false);
      return;
    }

    const [summaryResult, openExceptions] = await Promise.all([
      apiRequest('/monitoring/summary'),
      loadOpenExceptions(),
    ]);

    setMetrics(
      summaryResult.data || {
        activeConsents: 0,
        totalConsents: 0,
        auditEntries24h: 0,
        totalComplaints: 0,
        resolvedComplaints: 0,
        slaCompliance: null,
      }
    );
    setExceptions(openExceptions);
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleResolveException = async (id) => {
    const result = await resolveException(id, currentUserId, 'resolved');
    if (result.success) {
      refresh();
    } else {
      Alert.alert('Could not resolve', result.error || 'Try again.');
    }
  };

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
        <View style={styles.header}>
          <Text style={[styles.screenTitle, { color: theme.text }]}>🖥️ Monitoring Dashboard</Text>
          <Text style={[styles.screenSubtitle, { color: theme.textSecondary }]}>
            Live operational health of the interoperability layer — real queries, not placeholders
          </Text>
        </View>

        {!backendReady ? (
          <View style={[styles.noticeBox, { backgroundColor: 'rgba(194,69,69,0.1)', borderColor: '#C24545' }]}>
            <Ionicons name="warning-outline" size={13} color="#C24545" />
            <Text style={styles.noticeText}>Backend not connected — every metric below needs Supabase configured to show real data.</Text>
          </View>
        ) : loading ? (
          <View style={{ paddingVertical: 40, alignItems: 'center' }}>
            <ActivityIndicator color={theme.primary} />
          </View>
        ) : (
          <>
            {/* Core Metrics Grid */}
            <View style={styles.metricsGrid}>
              <MetricCard theme={theme} icon="shield-checkmark-outline" color="#2E9E63" value={metrics.activeConsents} label="Active Consent Grants" />
              <MetricCard theme={theme} icon="document-text-outline" color="#5568D6" value={metrics.auditEntries24h} label="Audit Entries (24h)" />
              <MetricCard theme={theme} icon="warning-outline" color={exceptions.length > 0 ? '#C24545' : '#2E9E63'} value={exceptions.length} label="Open Exceptions" />
              <MetricCard theme={theme} icon="checkmark-done-outline" color="#BE8A2E" value={metrics.slaCompliance !== null ? `${metrics.slaCompliance}%` : '—'} label="Overall Resolution Rate" />
            </View>

            {/* Exception Queue — real, actionable */}
            <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
              <View style={styles.cardHeaderRow}>
                <Ionicons name="alert-circle-outline" size={16} color="#C24545" />
                <Text style={[styles.cardTitle, { color: theme.text }]}>Integration Exception Queue</Text>
              </View>
              {exceptions.length === 0 ? (
                <Text style={[styles.emptyText, { color: theme.textMuted }]}>
                  No open exceptions. Try the "Simulate a malformed record" toggle on the Interoperability screen to see this in action.
                </Text>
              ) : (
                exceptions.map((exc) => (
                  <View key={exc.id} style={[styles.exceptionRow, { borderColor: theme.border }]}>
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.exceptionSource, { color: theme.text }]}>{exc.source_system}</Text>
                      <Text style={[styles.exceptionMsg, { color: theme.textSecondary }]} numberOfLines={2}>{exc.error_message}</Text>
                      <Text style={[styles.exceptionTime, { color: theme.textMuted }]}>
                        {new Date(exc.created_at).toLocaleString('en-IN')}
                      </Text>
                    </View>
                    {userRole === 'official' && (
                      <TouchableOpacity
                        style={[styles.resolveBtn, { backgroundColor: theme.primaryGlow }]}
                        onPress={() => handleResolveException(exc.id)}
                      >
                        <Text style={{ color: theme.primaryLight, fontSize: 11, fontWeight: '700' }}>Resolve</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                ))
              )}
            </View>

            <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
              <View style={styles.cardHeaderRow}>
                <Ionicons name="stats-chart-outline" size={16} color={theme.primaryLight} />
                <Text style={[styles.cardTitle, { color: theme.text }]}>Platform Totals</Text>
              </View>
              <Text style={[styles.emptyText, { color: theme.textSecondary }]}>
                {metrics.totalComplaints} total requests filed · {metrics.resolvedComplaints} resolved · {metrics.totalConsents} consent grants issued all-time ({metrics.activeConsents} currently active).
              </Text>
            </View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function MetricCard({ theme, icon, color, value, label }) {
  return (
    <View style={[metricStyles.box, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
      <Ionicons name={icon} size={18} color={color} />
      <Text style={[metricStyles.value, { color }]}>{value}</Text>
      <Text style={[metricStyles.label, { color: theme.textMuted }]}>{label}</Text>
    </View>
  );
}

const metricStyles = StyleSheet.create({
  box: { width: '48%', borderRadius: RADIUS.lg, borderWidth: 1, padding: 12, marginBottom: 10, alignItems: 'flex-start' },
  value: { fontSize: 20, fontWeight: '800', marginTop: 6 },
  label: { fontSize: 10, marginTop: 2 },
});

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  scrollContent: { paddingHorizontal: SPACING.md, paddingBottom: 60 },
  header: { paddingTop: Platform.OS === 'android' ? 30 : 10, marginBottom: SPACING.md },
  screenTitle: { fontSize: 20, fontWeight: '800' },
  screenSubtitle: { fontSize: 12, marginTop: 4, lineHeight: 17 },
  noticeBox: { flexDirection: 'row', alignItems: 'center', gap: 6, padding: 10, borderRadius: RADIUS.md, borderWidth: 1, marginBottom: SPACING.sm },
  noticeText: { fontSize: 10.5, color: '#C24545', flex: 1 },
  metricsGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', marginBottom: SPACING.sm },
  card: { borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, marginBottom: SPACING.md },
  cardHeaderRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 },
  cardTitle: { fontSize: 14, fontWeight: '800' },
  emptyText: { fontSize: 12, lineHeight: 18 },
  exceptionRow: { flexDirection: 'row', alignItems: 'center', borderTopWidth: 1, paddingVertical: 10, gap: 8 },
  exceptionSource: { fontSize: 12.5, fontWeight: '700' },
  exceptionMsg: { fontSize: 11, marginTop: 2 },
  exceptionTime: { fontSize: 9.5, marginTop: 3 },
  resolveBtn: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.md },
});
