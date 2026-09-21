// CivicLens - Grievance Tracking, Status Timeline & 30-Day Auto-Escalator

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  SafeAreaView,
  Alert,
  Platform,
  Modal,
  Linking,
  Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE } from '../constants/theme';
import {
  loadExternalLinks,
  addExternalLink,
  updateExternalLinkStatus,
  deleteExternalLink,
  getKnownExternalSystems,
} from '../services/externalLinksService';
import { resolveComplaintImageUrl } from '../services/trackingService';

export default function TrackingScreen({ navigation }) {
  const { theme, t, complaints, loadingComplaints, addComplaintNote, currentUserId } = useApp();

  const [filterStatus, setFilterStatus] = useState('All'); // 'All', 'In Progress', 'Resolved'
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [noteInput, setNoteInput] = useState('');
  const [externalLinks, setExternalLinks] = useState([]);
  const [addLinkModalVisible, setAddLinkModalVisible] = useState(false);
  const [newLinkSystem, setNewLinkSystem] = useState(getKnownExternalSystems()[0]);
  const [newLinkRef, setNewLinkRef] = useState('');
  const [newLinkStatus, setNewLinkStatus] = useState('');
  const [savingLink, setSavingLink] = useState(false);

  const refreshExternalLinks = useCallback(async () => {
    const links = await loadExternalLinks(currentUserId);
    setExternalLinks(links);
  }, [currentUserId]);

  useEffect(() => {
    refreshExternalLinks();
  }, [refreshExternalLinks]);

  const handleAddExternalLink = async () => {
    if (!newLinkRef.trim()) {
      Alert.alert('Reference number needed', 'Enter the reference/registration number from that portal.');
      return;
    }
    setSavingLink(true);
    const result = await addExternalLink(currentUserId, {
      systemName: newLinkSystem.label,
      referenceNumber: newLinkRef.trim(),
      portalUrl: newLinkSystem.url,
      description: newLinkStatus.trim(),
    });
    setSavingLink(false);
    if (!result.success) {
      Alert.alert('Could not save', result.error);
      return;
    }
    setAddLinkModalVisible(false);
    setNewLinkRef('');
    setNewLinkStatus('');
    refreshExternalLinks();
  };

  const handleDeleteExternalLink = async (id) => {
    await deleteExternalLink(id);
    refreshExternalLinks();
  };


  const filteredComplaints = complaints.filter(c => {
    const matchesFilter = filterStatus === 'All'
      ? true
      : filterStatus === 'Resolved'
      ? c.status === 'Resolved'
      : c.status !== 'Resolved';

    const matchesSearch = searchQuery.trim() === ''
      ? true
      : (c.id + ' ' + c.title + ' ' + c.department).toLowerCase().includes(searchQuery.toLowerCase());

    return matchesFilter && matchesSearch;
  });

  const handleAddNote = async (complaintId) => {
    if (!noteInput.trim()) return;
    const res = await addComplaintNote(complaintId, noteInput);
    if (res.success) {
      setNoteInput('');
      Alert.alert('Note Saved', 'Personal case note added successfully.');
    }
  };

  const handleAutoEscalate = (complaint) => {
    navigation.navigate('Complaint', {
      tab: 'rti',
      initialText: `FIRST APPEAL / RTI FOR DELAYED CIVIC GRIEVANCE: Reference ID ${complaint.id} regarding "${complaint.title}" filed on ${new Date(complaint.dateFiled).toLocaleDateString('en-IN')} with ${complaint.department}. Over 30 days have elapsed without statutory resolution.`,
    });
  };

  // Phase 3 — same "open in maps" pattern used elsewhere in the app
  // (CivicLocatorScreen.js, OfficialPortalScreen.js).
  const handleOpenLocation = (lat, lng, address) => {
    const query = lat != null && lng != null ? `${lat},${lng}` : encodeURIComponent(address || '');
    if (!query) return;
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
        keyboardShouldPersistTaps="handled"
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headerTitleRow}>
            <View>
              <Text style={[styles.screenTitle, { color: theme.text }]}>
                📊 {t('trackerTitle')}
              </Text>
              <Text style={[styles.screenSubtitle, { color: theme.textSecondary }]}>
                One window across CivicLens filings and other government portals
              </Text>
            </View>
            <TouchableOpacity
              style={[styles.syncBtn, { backgroundColor: theme.primaryGlow, borderColor: theme.primary }]}
              onPress={() => setAddLinkModalVisible(true)}
              activeOpacity={0.8}
            >
              <Ionicons name="add-circle-outline" size={16} color={theme.primary} />
              <Text style={[styles.syncBtnText, { color: theme.primaryLight }]}>
                Track External
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* External Portal References — honest manual aggregation, since
            CPGRAMS/state portals require the citizen's own login and have
            no public API to sync from live. */}
        {externalLinks.length > 0 && (
          <View style={styles.externalSection}>
            <Text style={[styles.externalSectionTitle, { color: theme.textMuted }]}>
              OTHER GOVERNMENT PORTALS (manually tracked — no live sync available)
            </Text>
            {externalLinks.map((link) => (
              <View key={link.id} style={[styles.externalCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.externalSystemName, { color: theme.text }]}>{link.system_name}</Text>
                  <Text style={[styles.externalRef, { color: theme.textSecondary }]}>Ref: {link.reference_number}</Text>
                  {link.description ? (
                    <Text style={[styles.externalStatus, { color: theme.textMuted }]}>{link.description}</Text>
                  ) : null}
                </View>
                {link.portal_url ? (
                  <TouchableOpacity onPress={() => Linking.openURL(link.portal_url)} style={styles.externalOpenBtn}>
                    <Ionicons name="open-outline" size={16} color={theme.primaryLight} />
                  </TouchableOpacity>
                ) : null}
                <TouchableOpacity onPress={() => handleDeleteExternalLink(link.id)} style={styles.externalOpenBtn}>
                  <Ionicons name="trash-outline" size={16} color={theme.textMuted} />
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}

        {/* Add External Reference Modal */}
        <Modal visible={addLinkModalVisible} animationType="slide" transparent onRequestClose={() => setAddLinkModalVisible(false)}>
          <View style={styles.modalOverlay}>
            <View style={[styles.modalCard, { backgroundColor: theme.card, borderColor: theme.primary }]}>
              <Text style={[styles.modalTitle, { color: theme.text }]}>Track a Reference from Another Portal</Text>
              <Text style={[styles.modalSub, { color: theme.textMuted }]}>
                CPGRAMS and most state portals need your own login and have no public status API — so this just keeps the reference number in one place alongside your CivicLens filings. You'll still check status on that portal directly.
              </Text>

              <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>System</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10 }}>
                {getKnownExternalSystems().map((sys) => (
                  <TouchableOpacity
                    key={sys.id}
                    style={[
                      styles.sysChip,
                      { backgroundColor: newLinkSystem.id === sys.id ? theme.primary : theme.surface, borderColor: theme.border },
                    ]}
                    onPress={() => setNewLinkSystem(sys)}
                  >
                    <Text style={{ color: newLinkSystem.id === sys.id ? '#FFFFFF' : theme.textSecondary, fontSize: 11, fontWeight: '600' }}>
                      {sys.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>

              <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Reference / Registration Number</Text>
              <TextInput
                style={[styles.modalInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                value={newLinkRef}
                onChangeText={setNewLinkRef}
                placeholder="e.g. DPPGxxxxxxxxx"
                placeholderTextColor={theme.textMuted}
              />

              <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Last Known Status (optional)</Text>
              <TextInput
                style={[styles.modalInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                value={newLinkStatus}
                onChangeText={setNewLinkStatus}
                placeholder="e.g. Forwarded to department"
                placeholderTextColor={theme.textMuted}
              />

              <View style={{ flexDirection: 'row', gap: 10, marginTop: 12 }}>
                <TouchableOpacity style={[styles.modalBtn, { backgroundColor: theme.surface }]} onPress={() => setAddLinkModalVisible(false)}>
                  <Text style={{ color: theme.textSecondary, fontWeight: '700' }}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.modalBtn, { backgroundColor: theme.primary }]} onPress={handleAddExternalLink} disabled={savingLink}>
                  <Text style={{ color: '#FFFFFF', fontWeight: '700' }}>{savingLink ? 'Saving...' : 'Save'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>


        {/* Search Bar */}
        <View style={[styles.searchBarRow, { backgroundColor: theme.card, borderColor: theme.border }]}>
          <Ionicons name="search-outline" size={18} color={theme.textMuted} />
          <TextInput
            style={[styles.searchInput, { color: theme.text }]}
            placeholder="Enter Govt Ref ID (e.g. CVL-2026-BLR-1092 or CPGRAMS)..."
            placeholderTextColor={theme.textMuted}
            value={searchQuery}
            onChangeText={setSearchQuery}
          />
        </View>

        {/* Status Filters */}
        <View style={styles.filterRow}>
          {['All', 'In Progress', 'Resolved'].map((st) => {
            const isSelected = filterStatus === st;
            return (
              <TouchableOpacity
                key={st}
                style={[
                  styles.filterChip,
                  {
                    backgroundColor: isSelected ? theme.primary : theme.card,
                    borderColor: isSelected ? theme.primary : theme.cardBorder,
                  },
                ]}
                onPress={() => setFilterStatus(st)}
                activeOpacity={0.8}
              >
                <Text
                  style={[
                    styles.filterChipText,
                    { color: isSelected ? '#FFFFFF' : theme.textSecondary, fontWeight: isSelected ? '700' : '500' },
                  ]}
                >
                  {st === 'All' ? t('filterStatusAll') : st === 'In Progress' ? t('filterStatusPending') : t('filterStatusResolved')}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* Grievances List */}
        {filteredComplaints.length === 0 ? (
          <View style={[styles.emptyCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
            <Ionicons name="folder-open-outline" size={42} color={theme.textMuted} />
            <Text style={[styles.emptyTitle, { color: theme.text }]}>
              No Grievances Found
            </Text>
            <Text style={[styles.emptySub, { color: theme.textMuted }]}>
              File a complaint from the Draft Letter tab to track status and auto-escalations here.
            </Text>
          </View>
        ) : (
          filteredComplaints.map((c) => {
            const isExpanded = expandedId === c.id;
            const isResolved = c.status === 'Resolved';
            const daysSince = Math.floor((Date.now() - new Date(c.dateFiled).getTime()) / (1000 * 60 * 60 * 24));
            const isOverdue = daysSince >= 30 && !isResolved;

            return (
              <View
                key={c.id}
                style={[
                  styles.complaintCard,
                  {
                    backgroundColor: theme.card,
                    borderColor: isOverdue ? theme.accentAmber : theme.cardBorder,
                  },
                ]}
              >
                {/* Top Info */}
                <TouchableOpacity
                  style={styles.cardHeader}
                  onPress={() => setExpandedId(isExpanded ? null : c.id)}
                  activeOpacity={0.85}
                >
                  <View style={{ flex: 1 }}>
                    <View style={styles.idBadgeRow}>
                      <Text style={[styles.trackingIdText, { color: theme.primaryLight }]}>
                        {c.id}
                      </Text>
                      <View
                        style={[
                          styles.statusBadge,
                          {
                            backgroundColor: isResolved
                              ? 'rgba(46, 158, 99, 0.15)'
                              : isOverdue
                              ? 'rgba(191, 107, 61, 0.15)'
                              : theme.primaryGlow,
                          },
                        ]}
                      >
                        <Text
                          style={[
                            styles.statusBadgeText,
                            {
                              color: isResolved
                                ? theme.accentEmerald
                                : isOverdue
                                ? theme.accentAmber
                                : theme.primaryLight,
                            },
                          ]}
                        >
                          {isResolved ? 'Resolved' : isOverdue ? '30d Overdue' : c.status}
                        </Text>
                      </View>
                    </View>

                    <Text style={[styles.complaintTitle, { color: theme.text }]}>
                      {c.title}
                    </Text>

                    <Text style={[styles.deptInfo, { color: theme.textMuted }]}>
                      🏢 {c.department} • Filed {daysSince} days ago
                    </Text>
                  </View>

                  <Ionicons
                    name={isExpanded ? 'chevron-up' : 'chevron-down'}
                    size={20}
                    color={theme.textMuted}
                  />
                </TouchableOpacity>

                {/* 30-Day Auto-Escalation Alert Banner */}
                {isOverdue && (
                  <View style={[styles.escalateAlertBox, { backgroundColor: 'rgba(191, 107, 61, 0.15)', borderColor: theme.accentAmber }]}>
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.escalateHeading, { color: theme.text }]}>
                        ⚠️ Statutory 30-Day Limit Exceeded
                      </Text>
                      <Text style={[styles.escalateSub, { color: theme.textSecondary }]}>
                        Under citizen charter rules, you are entitled to file a formal RTI Appeal for administrative delay.
                      </Text>
                    </View>
                    <TouchableOpacity
                      style={[styles.escalateActionBtn, { backgroundColor: theme.accentAmber }]}
                      onPress={() => handleAutoEscalate(c)}
                      activeOpacity={0.85}
                    >
                      <Text style={styles.escalateBtnText}>Auto RTI</Text>
                    </TouchableOpacity>
                  </View>
                )}

                {/* Expanded Details & 5-Stage Timeline */}
                {isExpanded && (
                  <View style={[styles.expandedContent, { borderTopColor: theme.border }]}>
                    <Text style={[styles.timelineHeading, { color: theme.text }]}>
                      Grievance Progression Timeline
                    </Text>

                    {/* Timeline Stages */}
                    <View style={styles.timelineContainer}>
                      {c.timeline?.map((stage, sIdx) => (
                        <View key={sIdx} style={styles.timelineRow}>
                          <View style={styles.timelineIndicatorColumn}>
                            <View
                              style={[
                                styles.timelineDot,
                                {
                                  backgroundColor: stage.done ? theme.accentEmerald : theme.borderLight,
                                },
                              ]}
                            >
                              {stage.done && (
                                <Ionicons name="checkmark" size={10} color="#FFFFFF" />
                              )}
                            </View>
                            {sIdx < c.timeline.length - 1 && (
                              <View
                                style={[
                                  styles.timelineLine,
                                  {
                                    backgroundColor: stage.done ? theme.accentEmerald : theme.border,
                                  },
                                ]}
                              />
                            )}
                          </View>

                          <View style={styles.timelineStageInfo}>
                            <Text
                              style={[
                                styles.stageName,
                                { color: stage.done ? theme.text : theme.textMuted },
                              ]}
                            >
                              {stage.stage}
                            </Text>
                            <Text style={[styles.stageDate, { color: theme.textMuted }]}>
                              {stage.date}
                            </Text>
                          </View>
                        </View>
                      ))}
                    </View>

                    {/* Phase 3: Evidence Photo + Precise Location */}
                    {c.imageUrl && (
                      <>
                        <Text style={[styles.notesHeading, { color: theme.text }]}>Evidence Photo:</Text>
                        <Image
                          source={{ uri: resolveComplaintImageUrl(c.imageUrl) }}
                          style={styles.evidenceThumb}
                          resizeMode="cover"
                        />
                      </>
                    )}
                    {(c.wardNumber || c.address || (c.lat != null && c.lng != null)) && (
                      <View style={[styles.locationBox, { backgroundColor: theme.surface, borderColor: theme.border }]}>
                        {c.wardNumber && (
                          <Text style={[styles.noteText, { color: theme.textSecondary }]}>Ward: {c.wardNumber}</Text>
                        )}
                        {c.address && (
                          <Text style={[styles.noteText, { color: theme.textSecondary }]}>Address: {c.address}</Text>
                        )}
                        {c.lat != null && c.lng != null && (
                          <TouchableOpacity onPress={() => handleOpenLocation(c.lat, c.lng, c.address)}>
                            <Text style={[styles.noteText, { color: theme.primaryLight, fontWeight: '700' }]}>
                              📍 Open location in Maps
                            </Text>
                          </TouchableOpacity>
                        )}
                      </View>
                    )}

                    {/* Case Notes */}
                    <Text style={[styles.notesHeading, { color: theme.text }]}>
                      Case Activity & Notes:
                    </Text>
                    {c.notes?.map((n, i) => (
                      <View key={i} style={[styles.noteBubble, { backgroundColor: theme.surface }]}>
                        <Text style={[styles.noteText, { color: theme.textSecondary }]}>• {n}</Text>
                      </View>
                    ))}

                    {/* Add Note Input */}
                    <View style={styles.addNoteRow}>
                      <TextInput
                        style={[styles.noteInput, { backgroundColor: theme.inputBg, color: theme.text, borderColor: theme.border }]}
                        placeholder="Add personal follow-up note..."
                        placeholderTextColor={theme.textMuted}
                        value={noteInput}
                        onChangeText={setNoteInput}
                      />
                      <TouchableOpacity
                        style={[styles.saveNoteBtn, { backgroundColor: theme.primary }]}
                        onPress={() => handleAddNote(c.id)}
                      >
                        <Text style={styles.saveNoteText}>Add</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                )}
              </View>
            );
          })
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  scrollContent: { paddingHorizontal: SPACING.md, paddingBottom: 260 },
  header: { paddingTop: Platform.OS === 'android' ? 30 : 10, marginBottom: SPACING.md },
  headerTitleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  syncBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    gap: 4,
  },
  syncBtnText: { fontSize: 11, fontWeight: '700' },
  syncBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 10,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    marginBottom: SPACING.sm,
    gap: 8,
  },
  syncBannerText: { fontSize: 11, fontWeight: '600', flex: 1 },
  externalSection: { marginBottom: SPACING.md },
  externalSectionTitle: { fontSize: 10, fontWeight: '800', letterSpacing: 0.5, marginBottom: 6 },
  externalCard: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: RADIUS.md,
    borderWidth: 1,
    padding: 10,
    marginBottom: 6,
  },
  externalSystemName: { fontSize: 12.5, fontWeight: '700' },
  externalRef: { fontSize: 11, marginTop: 2 },
  externalStatus: { fontSize: 10.5, marginTop: 2, fontStyle: 'italic' },
  externalOpenBtn: { padding: 6, marginLeft: 4 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', padding: SPACING.md },
  modalCard: { borderRadius: RADIUS.xl, padding: SPACING.md, borderWidth: 1.5 },
  modalTitle: { fontSize: 15, fontWeight: '800', marginBottom: 6 },
  modalSub: { fontSize: 11, lineHeight: 16, marginBottom: 14 },
  inputLabel: { fontSize: 11, fontWeight: '700', marginBottom: 6 },
  modalInput: { borderRadius: RADIUS.md, borderWidth: 1, padding: 10, fontSize: 13, marginBottom: 12 },
  sysChip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.full, borderWidth: 1, marginRight: 8 },
  modalBtn: { flex: 1, paddingVertical: 12, borderRadius: RADIUS.md, alignItems: 'center' },
  screenTitle: { fontSize: 20, fontWeight: '800' },
  screenSubtitle: { fontSize: 12, marginTop: 3 },
  searchBarRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    height: 44,
    marginBottom: SPACING.sm,
    gap: 8,
  },
  searchInput: { flex: 1, fontSize: 13 },
  filterRow: { flexDirection: 'row', gap: 8, marginBottom: SPACING.md },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: RADIUS.full,
    borderWidth: 1,
  },
  filterChipText: { fontSize: 12 },
  emptyCard: {
    borderRadius: RADIUS.lg,
    padding: SPACING.xl,
    alignItems: 'center',
    borderWidth: 1,
    marginTop: 20,
  },
  emptyTitle: { fontSize: 14, fontWeight: '800', marginTop: 10 },
  emptySub: { fontSize: 12, textAlign: 'center', marginTop: 4, lineHeight: 18 },
  complaintCard: {
    borderRadius: RADIUS.lg,
    padding: SPACING.md,
    borderWidth: 1,
    marginBottom: 12,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  idBadgeRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 },
  trackingIdText: { fontSize: 11, fontWeight: '800', letterSpacing: 0.5 },
  statusBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: RADIUS.full },
  statusBadgeText: { fontSize: 10, fontWeight: '800' },
  complaintTitle: { fontSize: 14, fontWeight: '800', marginTop: 2 },
  deptInfo: { fontSize: 11, marginTop: 4 },
  escalateAlertBox: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 10,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    marginTop: 10,
    gap: 8,
  },
  escalateHeading: { fontSize: 12, fontWeight: '800' },
  escalateSub: { fontSize: 10, marginTop: 1, lineHeight: 14 },
  escalateActionBtn: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.sm },
  escalateBtnText: { color: '#FFFFFF', fontSize: 11, fontWeight: '800' },
  expandedContent: { marginTop: 12, paddingTop: 10, borderTopWidth: 1 },
  timelineHeading: { fontSize: 13, fontWeight: '800', marginBottom: 10 },
  timelineContainer: { paddingLeft: 6, marginBottom: 12 },
  timelineRow: { flexDirection: 'row', minHeight: 40 },
  timelineIndicatorColumn: { alignItems: 'center', width: 20 },
  timelineDot: {
    width: 16,
    height: 16,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  timelineLine: { width: 2, flex: 1, marginVertical: 2 },
  timelineStageInfo: { flex: 1, paddingLeft: 10, paddingBottom: 10 },
  stageName: { fontSize: 12, fontWeight: '700' },
  stageDate: { fontSize: 10, marginTop: 1 },
  notesHeading: { fontSize: 12, fontWeight: '800', marginBottom: 6 },
  evidenceThumb: { width: '100%', height: 160, borderRadius: RADIUS.md, marginBottom: 10 },
  locationBox: { padding: 10, borderRadius: RADIUS.md, borderWidth: 1, gap: 4, marginBottom: 10 },
  noteBubble: { padding: 8, borderRadius: RADIUS.sm, marginBottom: 6 },
  noteText: { fontSize: 11, lineHeight: 16 },
  addNoteRow: { flexDirection: 'row', gap: 8, marginTop: 6 },
  noteInput: { flex: 1, height: 38, borderRadius: RADIUS.sm, paddingHorizontal: 10, fontSize: 12, borderWidth: 1 },
  saveNoteBtn: { paddingHorizontal: 14, borderRadius: RADIUS.sm, alignItems: 'center', justifyContent: 'center' },
  saveNoteText: { color: '#FFFFFF', fontSize: 12, fontWeight: '800' },
});
