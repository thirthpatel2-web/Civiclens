// CivicLens - Data & Privacy: Consent Grants + Golden Record Linking
//
// Two real capabilities live here:
// 1. Consent-based data sharing: see and revoke every department you've
//    granted data access to — not just access control (RLS), but citizen-
//    controlled consent with a full audit trail (see consentService.js).
// 2. Master Data Management: link the external government IDs you hold
//    (Aadhaar reference, PAN, etc.) to your one CivicLens profile — the
//    "Golden Record" — so future integrations can resolve records about
//    you to a single identity instead of fragmenting across systems.

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, SafeAreaView, TextInput, Alert, Platform, Modal } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE } from '../constants/theme';
import { ALL_PUBLIC_AUTHORITIES } from '../data/departmentsData';
import { loadConsentGrants, grantConsent, revokeConsent, DATA_SCOPE_OPTIONS } from '../services/consentService';
import { loadLinkedExternalIds, linkExternalId, unlinkExternalId, ID_SYSTEMS } from '../services/masterDataService';
import { loadMyAuditTrail } from '../services/auditService';

export default function DataPrivacyScreen() {
  const { theme, currentUserId, isGuestMode } = useApp();
  const [consents, setConsents] = useState([]);
  const [externalIds, setExternalIds] = useState([]);
  const [auditTrail, setAuditTrail] = useState([]);
  const [grantModalVisible, setGrantModalVisible] = useState(false);
  const [linkModalVisible, setLinkModalVisible] = useState(false);
  const [selectedDept, setSelectedDept] = useState(ALL_PUBLIC_AUTHORITIES[0]);
  const [selectedScope, setSelectedScope] = useState(['name', 'phone']);
  const [selectedIdSystem, setSelectedIdSystem] = useState(ID_SYSTEMS[0]);
  const [idValue, setIdValue] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!currentUserId) return;
    const [c, e, a] = await Promise.all([
      loadConsentGrants(currentUserId),
      loadLinkedExternalIds(currentUserId),
      loadMyAuditTrail(currentUserId, 15),
    ]);
    setConsents(c);
    setExternalIds(e);
    setAuditTrail(a);
  }, [currentUserId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const toggleScope = (id) => {
    setSelectedScope((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]));
  };

  const handleGrant = async () => {
    setBusy(true);
    const result = await grantConsent(currentUserId, selectedDept.id, selectedScope);
    setBusy(false);
    if (!result.success) return Alert.alert('Could not grant consent', result.error);
    setGrantModalVisible(false);
    refresh();
  };

  const handleRevoke = async (grantId) => {
    const result = await revokeConsent(grantId);
    if (result.success) refresh();
  };

  const handleLinkId = async () => {
    if (!idValue.trim()) return Alert.alert('Enter a value', 'Enter the ID number to link.');
    setBusy(true);
    const result = await linkExternalId(currentUserId, selectedIdSystem.id, idValue.trim());
    setBusy(false);
    if (!result.success) return Alert.alert(result.conflict ? 'Already Linked Elsewhere' : 'Could not link', result.error);
    setLinkModalVisible(false);
    setIdValue('');
    refresh();
  };

  if (isGuestMode || !currentUserId) {
    return (
      <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
        <View style={styles.centerFill}>
          <Ionicons name="lock-closed-outline" size={36} color={theme.textMuted} />
          <Text style={[styles.emptyTitle, { color: theme.text }]}>Sign in required</Text>
          <Text style={[styles.emptySub, { color: theme.textMuted }]}>
            Consent grants and identity linking need a real account, not Guest Mode.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
        <View style={styles.header}>
          <Text style={[styles.screenTitle, { color: theme.text }]}>🔐 Data & Privacy</Text>
          <Text style={[styles.screenSubtitle, { color: theme.textSecondary }]}>
            Control who sees your data, and link the government IDs that make up your Golden Record
          </Text>
        </View>

        {/* Consent Grants */}
        <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <View style={styles.cardHeaderRow}>
            <Text style={[styles.cardTitle, { color: theme.text }]}>Consent Grants</Text>
            <TouchableOpacity style={[styles.addBtn, { backgroundColor: theme.primaryGlow }]} onPress={() => setGrantModalVisible(true)}>
              <Ionicons name="add" size={16} color={theme.primaryLight} />
            </TouchableOpacity>
          </View>
          {consents.length === 0 ? (
            <Text style={[styles.emptyText, { color: theme.textMuted }]}>No consent grants yet. Departments only see what you explicitly allow.</Text>
          ) : (
            consents.map((c) => (
              <View key={c.id} style={[styles.rowItem, { borderColor: theme.border }]}>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.rowTitle, { color: theme.text }]}>{ALL_PUBLIC_AUTHORITIES.find((d) => d.id === c.department_id)?.name || c.department_id}</Text>
                  <Text style={[styles.rowSub, { color: theme.textMuted }]}>Scope: {c.data_scope.join(', ')} · {c.status === 'active' ? 'Active' : 'Revoked'}</Text>
                </View>
                {c.status === 'active' && (
                  <TouchableOpacity onPress={() => handleRevoke(c.id)} style={styles.revokeBtn}>
                    <Text style={{ color: '#C24545', fontSize: 11, fontWeight: '700' }}>Revoke</Text>
                  </TouchableOpacity>
                )}
              </View>
            ))
          )}
        </View>

        {/* Golden Record / Master Data */}
        <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <View style={styles.cardHeaderRow}>
            <Text style={[styles.cardTitle, { color: theme.text }]}>Linked Government IDs (Golden Record)</Text>
            <TouchableOpacity style={[styles.addBtn, { backgroundColor: theme.primaryGlow }]} onPress={() => setLinkModalVisible(true)}>
              <Ionicons name="add" size={16} color={theme.primaryLight} />
            </TouchableOpacity>
          </View>
          <Text style={[styles.emptyText, { color: theme.textMuted, marginBottom: 8 }]}>
            ID numbers are hashed before storage — CivicLens never stores your raw ID number.
          </Text>
          {externalIds.length === 0 ? (
            <Text style={[styles.emptyText, { color: theme.textMuted }]}>No IDs linked yet.</Text>
          ) : (
            externalIds.map((e) => (
              <View key={e.id} style={[styles.rowItem, { borderColor: theme.border }]}>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.rowTitle, { color: theme.text }]}>{ID_SYSTEMS.find((s) => s.id === e.id_system)?.label}</Text>
                  <Text style={[styles.rowSub, { color: theme.textMuted }]}>Linked {new Date(e.added_at).toLocaleDateString('en-IN')}</Text>
                </View>
                <TouchableOpacity onPress={() => unlinkExternalId(e.id).then(refresh)} style={styles.revokeBtn}>
                  <Ionicons name="trash-outline" size={14} color={theme.textMuted} />
                </TouchableOpacity>
              </View>
            ))
          )}
        </View>

        {/* Personal Audit Trail */}
        <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <Text style={[styles.cardTitle, { color: theme.text, marginBottom: 8 }]}>Your Recent Activity Log</Text>
          {auditTrail.length === 0 ? (
            <Text style={[styles.emptyText, { color: theme.textMuted }]}>No activity recorded yet.</Text>
          ) : (
            auditTrail.map((a) => (
              <Text key={a.id} style={[styles.auditLine, { color: theme.textSecondary }]}>
                {new Date(a.created_at).toLocaleString('en-IN')} — {a.action} on {a.resource_type}
              </Text>
            ))
          )}
        </View>

        {/* Grant Consent Modal */}
        <Modal visible={grantModalVisible} animationType="slide" transparent onRequestClose={() => setGrantModalVisible(false)}>
          <View style={styles.modalOverlay}>
            <View style={[styles.modalCard, { backgroundColor: theme.card, borderColor: theme.primary }]}>
              <Text style={[styles.modalTitle, { color: theme.text }]}>Grant Data Access</Text>
              <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Department</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }}>
                {ALL_PUBLIC_AUTHORITIES.slice(0, 10).map((d) => (
                  <TouchableOpacity
                    key={d.id}
                    style={[styles.chip, { backgroundColor: selectedDept.id === d.id ? theme.primary : theme.surface, borderColor: theme.border }]}
                    onPress={() => setSelectedDept(d)}
                  >
                    <Text style={{ color: selectedDept.id === d.id ? '#FFFFFF' : theme.textSecondary, fontSize: 11 }}>{d.name}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
              <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Data to Share</Text>
              {DATA_SCOPE_OPTIONS.map((s) => (
                <TouchableOpacity key={s.id} style={styles.checkRow} onPress={() => toggleScope(s.id)}>
                  <Ionicons name={selectedScope.includes(s.id) ? 'checkbox' : 'square-outline'} size={18} color={theme.primary} />
                  <Text style={{ color: theme.text, marginLeft: 8, fontSize: 13 }}>{s.label}</Text>
                </TouchableOpacity>
              ))}
              <View style={styles.modalBtnRow}>
                <TouchableOpacity style={[styles.modalBtn, { backgroundColor: theme.surface }]} onPress={() => setGrantModalVisible(false)}>
                  <Text style={{ color: theme.textSecondary, fontWeight: '700' }}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.modalBtn, { backgroundColor: theme.primary }]} onPress={handleGrant} disabled={busy}>
                  <Text style={{ color: '#FFFFFF', fontWeight: '700' }}>{busy ? 'Saving...' : 'Grant'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        {/* Link External ID Modal */}
        <Modal visible={linkModalVisible} animationType="slide" transparent onRequestClose={() => setLinkModalVisible(false)}>
          <View style={styles.modalOverlay}>
            <View style={[styles.modalCard, { backgroundColor: theme.card, borderColor: theme.primary }]}>
              <Text style={[styles.modalTitle, { color: theme.text }]}>Link a Government ID</Text>
              <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>ID Type</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }}>
                {ID_SYSTEMS.map((s) => (
                  <TouchableOpacity
                    key={s.id}
                    style={[styles.chip, { backgroundColor: selectedIdSystem.id === s.id ? theme.primary : theme.surface, borderColor: theme.border }]}
                    onPress={() => setSelectedIdSystem(s)}
                  >
                    <Text style={{ color: selectedIdSystem.id === s.id ? '#FFFFFF' : theme.textSecondary, fontSize: 11 }}>{s.label}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
              <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>ID Number</Text>
              <TextInput
                style={[styles.textInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                value={idValue}
                onChangeText={setIdValue}
                placeholder="Enter the ID number"
                placeholderTextColor={theme.textMuted}
              />
              <View style={styles.modalBtnRow}>
                <TouchableOpacity style={[styles.modalBtn, { backgroundColor: theme.surface }]} onPress={() => setLinkModalVisible(false)}>
                  <Text style={{ color: theme.textSecondary, fontWeight: '700' }}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.modalBtn, { backgroundColor: theme.primary }]} onPress={handleLinkId} disabled={busy}>
                  <Text style={{ color: '#FFFFFF', fontWeight: '700' }}>{busy ? 'Linking...' : 'Link'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
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
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: SPACING.lg },
  emptyTitle: { fontSize: 15, fontWeight: '800', marginTop: 10 },
  emptySub: { fontSize: 12, textAlign: 'center', marginTop: 6, lineHeight: 17 },
  card: { borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, marginBottom: SPACING.md },
  cardHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  cardTitle: { fontSize: 14, fontWeight: '800' },
  addBtn: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  emptyText: { fontSize: 12, lineHeight: 17 },
  rowItem: { flexDirection: 'row', alignItems: 'center', borderTopWidth: 1, paddingVertical: 10 },
  rowTitle: { fontSize: 12.5, fontWeight: '700' },
  rowSub: { fontSize: 10.5, marginTop: 2 },
  revokeBtn: { paddingHorizontal: 10, paddingVertical: 6 },
  auditLine: { fontSize: 10.5, lineHeight: 18 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', padding: SPACING.md },
  modalCard: { borderRadius: RADIUS.xl, padding: SPACING.md, borderWidth: 1.5, maxHeight: '85%' },
  modalTitle: { fontSize: 15, fontWeight: '800', marginBottom: 12 },
  inputLabel: { fontSize: 11, fontWeight: '700', marginBottom: 6 },
  chip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.full, borderWidth: 1, marginRight: 8 },
  checkRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 6 },
  textInput: { borderRadius: RADIUS.md, borderWidth: 1, padding: 10, fontSize: 13, marginBottom: 6 },
  modalBtnRow: { flexDirection: 'row', gap: 10, marginTop: 14 },
  modalBtn: { flex: 1, paddingVertical: 12, borderRadius: RADIUS.md, alignItems: 'center' },
});
