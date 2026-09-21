// CivicLens - Community Civic Grievance Overview
//
// Previously this screen displayed a "GIS SATELLITE RADAR" with fabricated
// ward names, invented officer names, invented upvote counts, and a fixed
// coordinate readout that never changed even when you switched cities.
// None of it was real. This version shows what CivicLens actually has:
// a real aggregation of complaints citizens have genuinely filed through
// the app (see src/services/heatmapService.js), with an honest empty
// state when a city has no real reports yet.

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  SafeAreaView,
  Modal,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE } from '../constants/theme';
import { CITIES } from '../data/departmentsData';
import { loadCityHeatmapSummary } from '../services/heatmapService';
import { backendReady } from '../services/authService';

export default function HeatmapScreen({ navigation }) {
  const { theme, t, selectedCity, setCity, getCityName } = useApp();

  const [activeCategory, setActiveCategory] = useState('All');
  const [selectedReport, setSelectedReport] = useState(null);
  const [showGlow, setShowGlow] = useState(true);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  const cityInfo = CITIES.find((c) => c.id === selectedCity) || CITIES[0];

  const refresh = useCallback(async () => {
    setLoading(true);
    const result = await loadCityHeatmapSummary(selectedCity);
    setSummary(result);
    setLoading(false);
  }, [selectedCity]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const categories = summary?.categories || [];
  const filteredCategories = activeCategory === 'All' ? categories : categories.filter((c) => c.category === activeCategory);
  const filteredReports = (summary?.recentReports || []).filter(
    (r) => activeCategory === 'All' || r.category === activeCategory
  );

  const handleReportInArea = (category) => {
    navigation.navigate('Complaint', {
      tab: 'civic',
      initialText: `${category} issue in ${cityInfo.name}: `,
    });
  };

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={[styles.screenTitle, { color: theme.text }]}>🗺️ {t('heatmapTitle')}</Text>
          <Text style={[styles.screenSubtitle, { color: theme.textSecondary }]}>
            Real reports filed by citizens through CivicLens — not official municipal data
          </Text>
        </View>

        {/* City Selector */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.cityScroll}>
          {CITIES.map((c) => {
            const isSelected = c.id === selectedCity;
            return (
              <TouchableOpacity
                key={c.id}
                style={[
                  styles.cityChip,
                  { backgroundColor: isSelected ? theme.primary : theme.card, borderColor: isSelected ? theme.primary : theme.cardBorder },
                ]}
                onPress={() => setCity(c.id)}
                activeOpacity={0.8}
              >
                <Text style={[styles.cityChipText, { color: isSelected ? '#FFFFFF' : theme.textSecondary, fontWeight: isSelected ? '700' : '500' }]}>
                  {getCityName(c.id)}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {!backendReady && (
          <View style={[styles.noticeBox, { backgroundColor: 'rgba(239,68,68,0.1)', borderColor: '#C24545' }]}>
            <Ionicons name="warning-outline" size={13} color="#C24545" />
            <Text style={styles.noticeText}>Backend not connected — this map has no data source yet. See README.</Text>
          </View>
        )}

        {loading ? (
          <View style={[styles.mapCard, styles.centerContent, { backgroundColor: '#0A1128', borderColor: '#1E293B', height: 260 }]}>
            <ActivityIndicator color="#FFFFFF" />
          </View>
        ) : !summary?.hasData ? (
          /* Honest empty state — no fabricated numbers when there's genuinely no data yet */
          <View style={[styles.mapCard, styles.centerContent, { backgroundColor: '#0A1128', borderColor: '#1E293B', height: 260, padding: SPACING.lg }]}>
            <Ionicons name="megaphone-outline" size={40} color="#475569" />
            <Text style={styles.emptyMapTitle}>No reports filed yet in {cityInfo.name}</Text>
            <Text style={styles.emptyMapSub}>
              This view is built entirely from real complaints citizens file through CivicLens. Be the first to report a civic issue here.
            </Text>
            <TouchableOpacity
              style={[styles.emptyMapCta, { backgroundColor: theme.primary }]}
              onPress={() => navigation.navigate('Complaint', { tab: 'civic' })}
            >
              <Text style={styles.emptyMapCtaText}>Report an Issue</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <>
            {/* Real Metrics Strip */}
            <View style={[styles.metricsRow, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
              <View style={styles.metricItem}>
                <Text style={[styles.metricValue, { color: theme.primaryLight }]}>{summary.totalReported}</Text>
                <Text style={[styles.metricLabel, { color: theme.textMuted }]}>Reports Filed</Text>
              </View>
              <View style={styles.metricItem}>
                <Text style={[styles.metricValue, { color: '#2E9E63' }]}>{summary.resolutionRate}</Text>
                <Text style={[styles.metricLabel, { color: theme.textMuted }]}>Resolution Rate</Text>
              </View>
              <View style={styles.metricItem}>
                <Text style={[styles.metricValue, { color: '#3B8FA8' }]}>{summary.avgResponseDays ? `${summary.avgResponseDays}d` : '—'}</Text>
                <Text style={[styles.metricLabel, { color: theme.textMuted }]}>Avg Resolution Time</Text>
              </View>
              <View style={styles.metricItem}>
                <Text style={[styles.metricValue, { color: '#BF6B3D' }]}>{summary.activeHotspotsCount}</Text>
                <Text style={[styles.metricLabel, { color: theme.textMuted }]}>Categories Reported</Text>
              </View>
            </View>

            {/* Category Filters — driven by real data present, not a fixed fake list */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.catFilterScroll}>
              {['All', ...categories.map((c) => c.category)].map((cat) => {
                const isSelected = activeCategory === cat;
                return (
                  <TouchableOpacity
                    key={cat}
                    style={[styles.catFilterChip, { backgroundColor: isSelected ? theme.primaryGlow : theme.card, borderColor: isSelected ? theme.primary : theme.cardBorder }]}
                    onPress={() => setActiveCategory(cat)}
                    activeOpacity={0.8}
                  >
                    <Text style={[styles.catFilterText, { color: isSelected ? theme.primaryLight : theme.textMuted, fontWeight: isSelected ? '700' : '500' }]}>
                      {cat}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>

            {/* Illustrative Category Density Map */}
            <View style={[styles.mapCard, { backgroundColor: '#0A1128', borderColor: '#1E293B' }]}>
              <View style={styles.mapTopBar}>
                <View style={styles.mapTitleRow}>
                  <View style={styles.liveRadarDot} />
                  <Text style={styles.mapTitleText}>{cityInfo.name.toUpperCase()} — COMMUNITY REPORT DENSITY</Text>
                </View>
                <View style={styles.mapCoordinatesBadge}>
                  <Text style={styles.mapCoordText}>{cityInfo.lat.toFixed(4)}° N, {cityInfo.lng.toFixed(4)}° E</Text>
                </View>
              </View>

              <View style={styles.mapStage}>
                <View style={styles.lakeArea} />
                <View style={styles.greenZone} />
                <View style={styles.ringRoadOuter} />
                <View style={styles.highwayHorizontal} />
                <View style={styles.highwayVertical} />

                {showGlow &&
                  filteredCategories.slice(0, 3).map((c, i) => {
                    const glowPositions = [{ top: '15%', left: '20%' }, { top: '50%', left: '60%' }, { top: '30%', left: '68%' }];
                    return (
                      <View
                        key={c.category}
                        style={[
                          styles.heatGlow,
                          glowPositions[i],
                          { backgroundColor: `${c.color}33`, width: 60 + c.count * 4, height: 60 + c.count * 4, borderRadius: (60 + c.count * 4) / 2 },
                        ]}
                      />
                    );
                  })}

                {/* Pins represent real categories with real report counts.
                    Position is illustrative layout, NOT precise GPS. */}
                {filteredCategories.map((c, idx) => {
                  const positions = [
                    { top: '22%', left: '26%' }, { top: '56%', left: '66%' }, { top: '34%', left: '74%' },
                    { top: '68%', left: '30%' }, { top: '44%', left: '46%' }, { top: '15%', left: '55%' },
                  ];
                  const pos = positions[idx % positions.length];
                  return (
                    <TouchableOpacity
                      key={c.category}
                      style={[styles.pinContainer, pos]}
                      onPress={() => setSelectedReport({ isCategorySummary: true, ...c })}
                      activeOpacity={0.85}
                    >
                      <View style={[styles.sonarWave, { borderColor: c.color }]} />
                      <View style={[styles.mapPinHead, { backgroundColor: c.color }]}>
                        <Text style={{ fontSize: 11 }}>{c.icon}</Text>
                      </View>
                      <View style={styles.mapPinCallout}>
                        <Text style={styles.mapPinCalloutText}>{c.category} ({c.count})</Text>
                      </View>
                    </TouchableOpacity>
                  );
                })}

                <View style={styles.mapControls}>
                  <TouchableOpacity style={[styles.mapControlBtn, showGlow && { backgroundColor: theme.primary }]} onPress={() => setShowGlow(!showGlow)}>
                    <Ionicons name="flame" size={16} color="#FFFFFF" />
                  </TouchableOpacity>
                </View>
              </View>

              <View style={styles.illustrativeNote}>
                <Text style={styles.illustrativeNoteText}>
                  Pin size/position reflects real report volume by category — illustrative layout, not exact GPS coordinates.
                </Text>
              </View>
            </View>

            {/* Recent Real Reports List */}
            <View style={styles.sectionHeaderRow}>
              <Text style={[styles.sectionTitle, { color: theme.text }]}>
                Recent Reports in {cityInfo.name} ({filteredReports.length})
              </Text>
            </View>

            {filteredReports.map((r) => (
              <TouchableOpacity
                key={r.id}
                style={[styles.reportCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
                onPress={() => setSelectedReport(r)}
                activeOpacity={0.85}
              >
                <View style={{ flex: 1 }}>
                  <Text style={[styles.reportCategory, { color: theme.primaryLight }]}>{r.category}</Text>
                  <Text style={[styles.reportTitle, { color: theme.text }]} numberOfLines={1}>{r.title}</Text>
                  <Text style={[styles.reportMeta, { color: theme.textMuted }]}>{r.daysPending} days ago • {r.status}</Text>
                </View>
                <Ionicons name="chevron-forward" size={16} color={theme.textMuted} />
              </TouchableOpacity>
            ))}
          </>
        )}

        {/* Detail Modal — category summary or individual real report */}
        {selectedReport && (
          <Modal animationType="slide" transparent visible onRequestClose={() => setSelectedReport(null)}>
            <View style={styles.modalOverlay}>
              <View style={[styles.modalCard, { backgroundColor: theme.card, borderColor: theme.primary }]}>
                <View style={styles.modalTopHeader}>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.modalWardText, { color: theme.primaryLight }]}>
                      {selectedReport.isCategorySummary ? 'Category Summary' : selectedReport.category}
                    </Text>
                    <Text style={[styles.modalLocationText, { color: theme.text }]}>
                      {selectedReport.isCategorySummary ? selectedReport.category : selectedReport.title}
                    </Text>
                  </View>
                  <TouchableOpacity onPress={() => setSelectedReport(null)}>
                    <Ionicons name="close-circle" size={26} color={theme.textMuted} />
                  </TouchableOpacity>
                </View>

                {selectedReport.isCategorySummary ? (
                  <View>
                    <Text style={[styles.modalBodyText, { color: theme.textSecondary }]}>
                      {selectedReport.count} real reports filed in this category, {selectedReport.resolved} resolved so far.
                    </Text>
                  </View>
                ) : (
                  <Text style={[styles.modalBodyText, { color: theme.textSecondary }]}>
                    Status: {selectedReport.status} • Filed {selectedReport.daysPending} days ago
                  </Text>
                )}

                <TouchableOpacity
                  style={[styles.reportInAreaBtn, { backgroundColor: theme.primary }]}
                  onPress={() => {
                    setSelectedReport(null);
                    handleReportInArea(selectedReport.category);
                  }}
                  activeOpacity={0.85}
                >
                  <Ionicons name="create-outline" size={18} color="#FFFFFF" />
                  <Text style={styles.reportInAreaBtnText}>{t('reportHere') || 'Report Similar Issue'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          </Modal>
        )}
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
  cityScroll: { flexDirection: 'row', marginBottom: 10 },
  cityChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: RADIUS.full, borderWidth: 1, marginRight: 8 },
  cityChipText: { fontSize: 12 },
  noticeBox: { flexDirection: 'row', alignItems: 'center', gap: 6, padding: 8, borderRadius: RADIUS.md, borderWidth: 1, marginBottom: SPACING.sm },
  noticeText: { fontSize: 10.5, color: '#C24545', flex: 1 },
  centerContent: { alignItems: 'center', justifyContent: 'center' },
  emptyMapTitle: { color: '#E2E8F0', fontSize: 14, fontWeight: '800', marginTop: 10, textAlign: 'center' },
  emptyMapSub: { color: '#94A3B8', fontSize: 11.5, marginTop: 6, textAlign: 'center', lineHeight: 16 },
  emptyMapCta: { marginTop: 14, paddingHorizontal: 18, paddingVertical: 10, borderRadius: RADIUS.md },
  emptyMapCtaText: { color: '#FFFFFF', fontSize: 12.5, fontWeight: '700' },
  metricsRow: { flexDirection: 'row', justifyContent: 'space-between', borderRadius: RADIUS.lg, borderWidth: 1, padding: SPACING.sm, marginBottom: SPACING.sm },
  metricItem: { alignItems: 'center', flex: 1 },
  metricValue: { fontSize: 16, fontWeight: '800' },
  metricLabel: { fontSize: 9.5, marginTop: 2, textAlign: 'center' },
  catFilterScroll: { flexDirection: 'row', marginBottom: SPACING.md },
  catFilterChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: RADIUS.md, borderWidth: 1, marginRight: 8 },
  catFilterText: { fontSize: 11 },
  mapCard: { borderRadius: RADIUS.lg, padding: SPACING.sm, borderWidth: 1.5, marginBottom: SPACING.md, overflow: 'hidden' },
  mapTopBar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.08)' },
  mapTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  liveRadarDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#2E9E63' },
  mapTitleText: { color: '#E2E8F0', fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  mapCoordinatesBadge: { backgroundColor: 'rgba(30,41,59,0.8)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  mapCoordText: { color: '#94A3B8', fontSize: 9, fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace' },
  mapStage: { height: 260, backgroundColor: '#0F172A', position: 'relative', overflow: 'hidden', borderRadius: RADIUS.md, marginTop: 6 },
  lakeArea: { position: 'absolute', top: 20, right: 25, width: 100, height: 70, borderRadius: 35, backgroundColor: '#1E3A8A', opacity: 0.5, transform: [{ rotate: '-15deg' }] },
  greenZone: { position: 'absolute', bottom: 25, left: 20, width: 90, height: 60, borderRadius: 20, backgroundColor: '#064E3B', opacity: 0.4 },
  ringRoadOuter: { position: 'absolute', top: 30, left: 30, right: 30, bottom: 30, borderRadius: 60, borderWidth: 2, borderColor: '#334155', borderStyle: 'dashed' },
  highwayHorizontal: { position: 'absolute', top: '48%', left: 0, right: 0, height: 5, backgroundColor: '#334155' },
  highwayVertical: { position: 'absolute', left: '52%', top: 0, bottom: 0, width: 5, backgroundColor: '#334155' },
  heatGlow: { position: 'absolute' },
  pinContainer: { position: 'absolute', alignItems: 'center', justifyContent: 'center', transform: [{ translateX: -12 }, { translateY: -12 }] },
  sonarWave: { position: 'absolute', width: 32, height: 32, borderRadius: 16, borderWidth: 2, opacity: 0.6 },
  mapPinHead: { width: 22, height: 22, borderRadius: 11, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: '#FFFFFF' },
  mapPinCallout: { backgroundColor: 'rgba(15,23,42,0.92)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, borderWidth: 0.5, borderColor: '#475569', marginTop: 2 },
  mapPinCalloutText: { color: '#FFFFFF', fontSize: 8, fontWeight: '800' },
  mapControls: { position: 'absolute', right: 10, bottom: 10, backgroundColor: 'rgba(15,23,42,0.85)', borderRadius: 6, padding: 4, borderWidth: 1, borderColor: '#334155' },
  mapControlBtn: { width: 28, height: 28, borderRadius: 4, backgroundColor: '#1E293B', alignItems: 'center', justifyContent: 'center' },
  illustrativeNote: { paddingTop: 8, paddingHorizontal: 4 },
  illustrativeNoteText: { color: '#64748B', fontSize: 9, fontStyle: 'italic' },
  sectionHeaderRow: { marginBottom: SPACING.sm, marginTop: SPACING.md },
  sectionTitle: { fontSize: 14, fontWeight: '800' },
  reportCard: { flexDirection: 'row', alignItems: 'center', borderRadius: RADIUS.md, padding: 12, borderWidth: 1, marginBottom: 8 },
  reportCategory: { fontSize: 10.5, fontWeight: '700' },
  reportTitle: { fontSize: 13, fontWeight: '700', marginTop: 2 },
  reportMeta: { fontSize: 10.5, marginTop: 3 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', padding: SPACING.md },
  modalCard: { borderRadius: RADIUS.xl, padding: SPACING.md, borderWidth: 1.5 },
  modalTopHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 },
  modalWardText: { fontSize: 12, fontWeight: '700' },
  modalLocationText: { fontSize: 15, fontWeight: '800', marginTop: 2 },
  modalBodyText: { fontSize: 12, lineHeight: 18 },
  reportInAreaBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 12, borderRadius: RADIUS.md, gap: 8, marginTop: 14 },
  reportInAreaBtnText: { color: '#FFFFFF', fontSize: 13, fontWeight: '800' },
});
