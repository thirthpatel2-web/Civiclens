// CivicLens - Dedicated Government Official Portal & Department Resolution Dashboard

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  SafeAreaView,
  TextInput,
  Modal,
  Alert,
  Linking,
  Platform,
  ActivityIndicator,
  Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE } from '../constants/theme';
import { ALL_PUBLIC_AUTHORITIES, getDepartmentById } from '../data/departmentsData';
import { loadDepartmentQueue, updateComplaintStatusRemote, resolveComplaintImageUrl, loadDepartmentDashboard, loadComplaintHistory, addOfficerUpdate } from '../services/trackingService';
import { backendReady } from '../services/authService';
import { loadWorkflowRules, createWorkflowRule, toggleWorkflowRule, deleteWorkflowRule } from '../services/workflowRulesService';

// The complete set of statuses actually used across CivicLens (see
// server/src/services/complaintStatus.js — the single source of truth
// this list mirrors). An officer can move a complaint into any of the
// non-intake ones; Filed/Submitted are citizen-side intake states only.
const OFFICER_STATUS_ACTIONS = [
  { status: 'Under Review', label: 'Acknowledge', icon: 'checkmark-circle-outline', color: '#3547A8' },
  { status: 'Inspection Scheduled', label: 'Schedule Inspection', icon: 'calendar-outline', color: '#BF6B3D' },
  { status: 'In Progress', label: 'Mark In Progress', icon: 'construct-outline', color: '#3547A8' },
  { status: 'Resolved', label: 'Upload ATR & Resolve', icon: 'checkmark-done-circle-outline', color: '#2E9E63' },
  { status: 'Closed', label: 'Close', icon: 'lock-closed-outline', color: '#2E9E63' },
  { status: 'Rejected', label: 'Reject / Not Jurisdiction', icon: 'close-circle-outline', color: '#C24545' },
];

/** Real SLA countdown text from the complaint's own sla_due_at, replacing
 *  what used to be a hardcoded "26 Days Left" placeholder. */
function slaCountdownText(complaint) {
  if (!complaint) return { text: 'SLA not set', urgent: false };
  if (complaint.status === 'Resolved' || complaint.status === 'Closed') {
    return { text: 'Resolved — SLA closed', urgent: false };
  }
  if (!complaint.slaDueAt) return { text: 'SLA not set', urgent: false };
  const hoursRemaining = (new Date(complaint.slaDueAt).getTime() - Date.now()) / 3600000;
  if (hoursRemaining < 0) {
    const daysOver = Math.abs(Math.round(hoursRemaining / 24));
    return { text: `SLA breached — ${daysOver}d overdue${complaint.escalationLevel ? ` (escalation level ${complaint.escalationLevel})` : ''}`, urgent: true };
  }
  const daysLeft = Math.round(hoursRemaining / 24);
  if (hoursRemaining <= 24) return { text: `SLA due within 24 hours`, urgent: true };
  return { text: `${daysLeft} day${daysLeft === 1 ? '' : 's'} left on SLA`, urgent: false };
}

export default function OfficialPortalScreen({ navigation }) {
  const {
    theme,
    t,
    officialProfile,
    logout,
    currentUserId,
  } = useApp();

  // Locked to the officer's own department — the backend enforces this
  // strictly (an official can never view or act on another department's
  // complaints, see server/src/routes/complaints.js and dashboards.js),
  // so there is no legitimate "switch department" action for this role.
  const activeDeptId = officialProfile.deptId || 'bbmp_roads';
  const [filterStatus, setFilterStatus] = useState('all'); // 'all', 'pending', 'inspection', 'resolved', 'rejected'
  const [selectedComplaint, setSelectedComplaint] = useState(null);
  const [officerRemarksInput, setOfficerRemarksInput] = useState('');
  const [actionInProgress, setActionInProgress] = useState(false);
  const [deptComplaints, setDeptComplaints] = useState([]);
  const [loadingQueue, setLoadingQueue] = useState(true);
  const [dashboardStats, setDashboardStats] = useState(null);
  const [complaintHistory, setComplaintHistory] = useState({ updateLog: [], auditTrail: [] });
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [updateNoteInput, setUpdateNoteInput] = useState('');
  const [savingUpdate, setSavingUpdate] = useState(false);
  const [rulesModalVisible, setRulesModalVisible] = useState(false);
  const [workflowRules, setWorkflowRules] = useState([]);
  const [newRuleName, setNewRuleName] = useState('');
  const [newRuleCategory, setNewRuleCategory] = useState('');
  const [newRuleKeywords, setNewRuleKeywords] = useState('');
  const [savingRule, setSavingRule] = useState(false);

  const refreshWorkflowRules = useCallback(async () => {
    const rules = await loadWorkflowRules();
    setWorkflowRules(rules);
  }, []);

  useEffect(() => {
    if (rulesModalVisible) refreshWorkflowRules();
  }, [rulesModalVisible, refreshWorkflowRules]);

  const handleCreateRule = async () => {
    if (!newRuleName.trim()) {
      Alert.alert('Rule name needed', 'Give this routing rule a name.');
      return;
    }
    setSavingRule(true);
    const result = await createWorkflowRule(currentUserId, {
      ruleName: newRuleName.trim(),
      matchCategory: newRuleCategory.trim() || null,
      matchKeywords: newRuleKeywords.split(',').map((k) => k.trim()).filter(Boolean),
      routeToDepartmentId: activeDeptId,
      priority: 100,
    });
    setSavingRule(false);
    if (!result.success) return Alert.alert('Could not save rule', result.error);
    setNewRuleName('');
    setNewRuleCategory('');
    setNewRuleKeywords('');
    refreshWorkflowRules();
  };

  const handleToggleRule = async (rule) => {
    await toggleWorkflowRule(rule.id, !rule.active);
    refreshWorkflowRules();
  };

  const handleDeleteRule = async (ruleId) => {
    await deleteWorkflowRule(ruleId);
    refreshWorkflowRules();
  };

  const currentDept = getDepartmentById(activeDeptId) || ALL_PUBLIC_AUTHORITIES[0];

  const refreshQueue = useCallback(async () => {
    setLoadingQueue(true);
    const rows = await loadDepartmentQueue(activeDeptId);
    setDeptComplaints(rows);
    setLoadingQueue(false);
  }, [activeDeptId]);

  const refreshDashboard = useCallback(async () => {
    if (!backendReady) return;
    const result = await loadDepartmentDashboard(activeDeptId);
    if (result.success) setDashboardStats(result.stats);
  }, [activeDeptId]);

  useEffect(() => {
    refreshQueue();
    refreshDashboard();
  }, [refreshQueue, refreshDashboard]);

  const refreshHistory = useCallback(async (complaintId) => {
    setLoadingHistory(true);
    const result = await loadComplaintHistory(complaintId);
    setComplaintHistory(result.success ? { updateLog: result.updateLog, auditTrail: result.auditTrail } : { updateLog: [], auditTrail: [] });
    setLoadingHistory(false);
  }, []);

  const openComplaintDetail = (complaint) => {
    setSelectedComplaint(complaint);
    setComplaintHistory({ updateLog: [], auditTrail: [] });
    setUpdateNoteInput('');
    refreshHistory(complaint.id);
  };

  const filteredQueue = deptComplaints.filter((c) => {
    if (filterStatus === 'all') return true;
    if (filterStatus === 'pending') return c.status === 'Filed' || c.status === 'Submitted' || c.status === 'Under Review' || !c.status;
    if (filterStatus === 'inspection') return c.status === 'Inspection Scheduled' || c.status === 'In Progress';
    if (filterStatus === 'resolved') return c.status === 'Resolved' || c.status === 'Closed';
    if (filterStatus === 'rejected') return c.status === 'Rejected';
    return true;
  });

  // Metrics: prefer the server-computed dashboard stats (real SQL
  // aggregation, escalation-aware — see GET /dashboards/department/:deptId)
  // and only fall back to counting the currently-loaded queue page when
  // that endpoint hasn't returned yet (e.g. backend not configured).
  const totalCount = dashboardStats ? dashboardStats.total : deptComplaints.length;
  const resolvedCount = dashboardStats ? dashboardStats.resolved : deptComplaints.filter(c => c.status === 'Resolved' || c.status === 'Closed').length;
  const pendingCount = dashboardStats ? dashboardStats.pending : totalCount - resolvedCount;
  const escalatedCount = dashboardStats ? dashboardStats.escalated : deptComplaints.filter((c) => (c.escalationLevel || 0) > 0 && c.status !== 'Resolved' && c.status !== 'Closed').length;
  const complianceRate = totalCount > 0 ? Math.round((resolvedCount / totalCount) * 100) : null;
  const avgResponseDays = (() => {
    const resolved = deptComplaints.filter((c) => (c.status === 'Resolved' || c.status === 'Closed') && c.dateFiled && c.updatedAt);
    if (resolved.length === 0) return '—';
    const totalDays = resolved.reduce((sum, c) => {
      const days = (new Date(c.updatedAt).getTime() - new Date(c.dateFiled).getTime()) / (1000 * 60 * 60 * 24);
      return sum + Math.max(days, 0);
    }, 0);
    return `${(totalDays / resolved.length).toFixed(1)}d`;
  })();

  // Handle Official Status Change — writes through to the backend, which
  // enforces department ownership and builds the history entry itself
  // (see PATCH /complaints/:id/status). We no longer compute `stage` or
  // `history` here; the server owns both now.
  const handleUpdateStatus = async (newStatus) => {
    if (!selectedComplaint) return;
    if (!backendReady) {
      Alert.alert(
        'Backend not connected',
        'Connect the backend (see README) to save real status updates. This is a preview-only queue right now.'
      );
      return;
    }
    setActionInProgress(true);
    const remarks = officerRemarksInput || `Status updated to ${newStatus} by Nodal Officer ${officialProfile.name}`;
    const isResolved = newStatus === 'Resolved' || newStatus === 'Closed';
    const result = await updateComplaintStatusRemote(selectedComplaint.id, {
      status: newStatus,
      officer: officialProfile.name,
      officer_remarks: remarks,
      atr_file_name: isResolved ? `ATR-${activeDeptId.toUpperCase()}-${Date.now().toString().slice(-4)}.pdf` : null,
    });
    setActionInProgress(false);

    if (!result.success) {
      Alert.alert('Update failed', result.error || 'Could not update this complaint.');
      return;
    }
    setDeptComplaints((prev) => prev.map((c) => (c.id === selectedComplaint.id ? result.complaint : c)));
    setSelectedComplaint(result.complaint);
    refreshHistory(selectedComplaint.id);
    refreshDashboard();
    Alert.alert('Grievance Updated', `Complaint status successfully updated to "${newStatus}". Synced to Citizen Portal.`);
    setOfficerRemarksInput('');
  };

  // Investigation/action-taken note that does NOT change the complaint's
  // status — distinct from handleUpdateStatus above (see POST
  // /complaints/:id/updates). Lets an officer log progress without
  // forcing a status transition just to leave a note.
  const handleAddUpdate = async () => {
    if (!selectedComplaint || !updateNoteInput.trim()) return;
    if (!backendReady) {
      Alert.alert('Backend not connected', 'Connect the backend (see README) to save officer updates.');
      return;
    }
    setSavingUpdate(true);
    const result = await addOfficerUpdate(selectedComplaint.id, updateNoteInput.trim());
    setSavingUpdate(false);
    if (!result.success) {
      Alert.alert('Could not add update', result.error || 'Please try again.');
      return;
    }
    setUpdateNoteInput('');
    setDeptComplaints((prev) => prev.map((c) => (c.id === selectedComplaint.id ? result.complaint : c)));
    setSelectedComplaint(result.complaint);
    refreshHistory(selectedComplaint.id);
  };

  const handleContactCitizen = (phone, email) => {
    if (phone) {
      Linking.openURL(`tel:${phone}`);
    } else if (email) {
      Linking.openURL(`mailto:${email}`);
    }
  };

  // Phase 3 — same "open in maps" pattern already used by
  // CivicLocatorScreen.js (platform-specific maps: URI scheme, with a
  // plain Google Maps web fallback), reused here instead of inventing a
  // second implementation.
  const handleOpenComplaintLocation = (lat, lng, address) => {
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
      >
        {/* Officer Identity & Security Card */}
        <View style={[styles.officerCard, { backgroundColor: theme.card, borderColor: '#BF6B3D' }]}>
          <View style={styles.officerTopRow}>
            <View style={[styles.govBadge, { backgroundColor: 'rgba(191, 107, 61, 0.15)' }]}>
              <Text style={styles.govBadgeText}>🏛️ Verified Government Nodal Officer</Text>
            </View>
            <TouchableOpacity onPress={() => navigation.navigate('Auth')} style={styles.switchRoleBtn}>
              <Ionicons name="swap-horizontal" size={14} color="#BF6B3D" />
              <Text style={styles.switchRoleText}>Switch Dept / Role</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.officerProfileRow}>
            <View style={[styles.officerAvatar, { backgroundColor: '#BF6B3D' }]}>
              <Text style={styles.officerAvatarText}>
                {officialProfile.name ? officialProfile.name.charAt(0) : 'E'}
              </Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.officerName, { color: theme.text }]}>
                {officialProfile.name || 'Nodal Officer'}
              </Text>
              <Text style={[styles.officerDesignation, { color: theme.textSecondary }]}>
                {officialProfile.designation || 'Assistant Executive Engineer'} • {officialProfile.officerId || 'OFF-BBMP-749'}
              </Text>
              <Text style={[styles.officerDept, { color: '#BF6B3D' }]}>
                {currentDept.fullName || currentDept.name}
              </Text>
            </View>
          </View>

          <TouchableOpacity
            style={[styles.rulesBtn, { borderColor: '#BF6B3D' }]}
            onPress={() => setRulesModalVisible(true)}
            activeOpacity={0.85}
          >
            <Ionicons name="git-branch-outline" size={14} color="#BF6B3D" />
            <Text style={styles.rulesBtnText}>Configure Routing Rules ({workflowRules.filter((r) => r.active).length} active)</Text>
          </TouchableOpacity>
        </View>

        {/* Configurable Workflow Orchestration Modal */}
        <Modal visible={rulesModalVisible} animationType="slide" transparent onRequestClose={() => setRulesModalVisible(false)}>
          <View style={styles.rulesModalOverlay}>
            <View style={[styles.rulesModalCard, { backgroundColor: theme.card, borderColor: '#BF6B3D' }]}>
              <View style={styles.rulesModalHeader}>
                <Text style={[styles.rulesModalTitle, { color: theme.text }]}>Routing Rules</Text>
                <TouchableOpacity onPress={() => setRulesModalVisible(false)}>
                  <Ionicons name="close" size={22} color={theme.textMuted} />
                </TouchableOpacity>
              </View>
              <Text style={[styles.rulesModalSub, { color: theme.textMuted }]}>
                Real, runtime-configurable routing — add a rule here and it takes effect immediately, no code deploy.
              </Text>

              <ScrollView style={{ maxHeight: 220, marginBottom: 12 }}>
                {workflowRules.length === 0 ? (
                  <Text style={[styles.rulesEmptyText, { color: theme.textMuted }]}>No rules configured yet.</Text>
                ) : (
                  workflowRules.map((rule) => (
                    <View key={rule.id} style={[styles.ruleRow, { borderColor: theme.border }]}>
                      <View style={{ flex: 1 }}>
                        <Text style={[styles.ruleName, { color: theme.text }]}>{rule.rule_name}</Text>
                        <Text style={[styles.ruleDetail, { color: theme.textMuted }]}>
                          {rule.match_category ? `Category: ${rule.match_category}` : 'Any category'}
                          {rule.match_keywords?.length ? ` · Keywords: ${rule.match_keywords.join(', ')}` : ''} → {rule.route_to_department_id}
                        </Text>
                      </View>
                      <TouchableOpacity onPress={() => handleToggleRule(rule)} style={{ padding: 6 }}>
                        <Ionicons name={rule.active ? 'toggle' : 'toggle-outline'} size={26} color={rule.active ? '#2E9E63' : theme.textMuted} />
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => handleDeleteRule(rule.id)} style={{ padding: 6 }}>
                        <Ionicons name="trash-outline" size={16} color={theme.textMuted} />
                      </TouchableOpacity>
                    </View>
                  ))
                )}
              </ScrollView>

              <Text style={[styles.rulesModalSub, { color: theme.text, fontWeight: '700', marginBottom: 6 }]}>New Rule (routes to {currentDept.name})</Text>
              <TextInput
                style={[styles.rulesInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                value={newRuleName}
                onChangeText={setNewRuleName}
                placeholder="Rule name, e.g. 'Pothole fast-track'"
                placeholderTextColor={theme.textMuted}
              />
              <TextInput
                style={[styles.rulesInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                value={newRuleCategory}
                onChangeText={setNewRuleCategory}
                placeholder="Match category (optional), e.g. 'roads'"
                placeholderTextColor={theme.textMuted}
              />
              <TextInput
                style={[styles.rulesInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                value={newRuleKeywords}
                onChangeText={setNewRuleKeywords}
                placeholder="Match keywords, comma-separated (optional)"
                placeholderTextColor={theme.textMuted}
              />
              <TouchableOpacity style={[styles.rulesSaveBtn, { backgroundColor: '#BF6B3D' }]} onPress={handleCreateRule} disabled={savingRule}>
                <Text style={{ color: '#FFFFFF', fontWeight: '700' }}>{savingRule ? 'Saving...' : 'Add Rule'}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>

        {/* Officer's own department — not a switcher. The backend
            enforces department isolation server-side (an officer's JWT
            carries their department_id and every complaint route checks
            it), so this app never lets an officer pick a different one. */}
        <View style={styles.deptSelectorRow}>
          <Text style={[styles.deptSelectLabel, { color: theme.textMuted }]}>
            YOUR DEPARTMENT DESK:
          </Text>
          <View
            style={[
              styles.deptChip,
              { backgroundColor: '#BF6B3D', borderColor: '#BF6B3D', opacity: 1 },
            ]}
          >
            <Text style={styles.deptEmoji}>{currentDept.icon}</Text>
            <Text style={[styles.deptChipText, { color: '#FFFFFF', fontWeight: '700' }]}>
              {currentDept.name.split(' - ')[0]}
            </Text>
          </View>
        </View>
        <Text style={[styles.deptLockedNote, { color: theme.textMuted }]}>
          Officers only see and act on complaints routed to their own department — enforced server-side, not just in this app.
        </Text>

        {/* Department SLA Scorecard */}
        <View style={[styles.metricsCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <View style={styles.metricsHeader}>
            <View style={styles.metricsTitleRow}>
              <Ionicons name="speedometer-outline" size={18} color="#BF6B3D" />
              <Text style={[styles.metricsTitle, { color: theme.text }]}>
                Department SLA & Resolution Scorecard
              </Text>
            </View>
            <View style={[styles.slaBadge, { backgroundColor: 'rgba(46, 158, 99, 0.15)' }]}>
              <Text style={[styles.slaBadgeText, { color: '#2E9E63' }]}>
                SLA Compliance: {complianceRate === null ? '—' : `${complianceRate}%`}
              </Text>
            </View>
          </View>

          <View style={styles.metricsGrid}>
            <View style={styles.metricItem}>
              <Text style={[styles.metricValue, { color: theme.primaryLight }]}>{totalCount}</Text>
              <Text style={[styles.metricLabel, { color: theme.textMuted }]}>Total Inbound</Text>
            </View>
            <View style={styles.metricDivider} />
            <View style={styles.metricItem}>
              <Text style={[styles.metricValue, { color: '#BF6B3D' }]}>{pendingCount}</Text>
              <Text style={[styles.metricLabel, { color: theme.textMuted }]}>Pending Action</Text>
            </View>
            <View style={styles.metricDivider} />
            <View style={styles.metricItem}>
              <Text style={[styles.metricValue, { color: '#2E9E63' }]}>{resolvedCount}</Text>
              <Text style={[styles.metricLabel, { color: theme.textMuted }]}>Resolved (ATRs)</Text>
            </View>
            <View style={styles.metricDivider} />
            <View style={styles.metricItem}>
              <Text style={[styles.metricValue, { color: '#3B8FA8' }]}>{avgResponseDays}</Text>
              <Text style={[styles.metricLabel, { color: theme.textMuted }]}>Avg Response</Text>
            </View>
            <View style={styles.metricDivider} />
            <View style={styles.metricItem}>
              <Text style={[styles.metricValue, { color: '#C24545' }]}>{escalatedCount}</Text>
              <Text style={[styles.metricLabel, { color: theme.textMuted }]}>Escalated</Text>
            </View>
          </View>
        </View>

        {!backendReady && (
          <View style={[styles.backendNotice, { backgroundColor: 'rgba(194, 69, 69, 0.1)', borderColor: '#C24545' }]}>
            <Ionicons name="warning-outline" size={13} color="#C24545" />
            <Text style={styles.backendNoticeText}>
              Backend not connected — this queue is empty until the backend is configured (see README) and citizens start filing real complaints.
            </Text>
          </View>
        )}

        {/* Inbound Queue Header & Filter Tabs */}
        <View style={styles.sectionHeaderRow}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>
            📥 Inbound Citizen Grievance & RTI Queue ({filteredQueue.length})
          </Text>
        </View>

        <View style={styles.filterTabsRow}>
          {[
            { id: 'all', label: 'All Queue' },
            { id: 'pending', label: 'Pending Action' },
            { id: 'inspection', label: 'In Progress' },
            { id: 'resolved', label: 'Resolved' },
            { id: 'rejected', label: 'Rejected' },
          ].map((tab) => (
            <TouchableOpacity
              key={tab.id}
              style={[
                styles.filterTabBtn,
                filterStatus === tab.id
                  ? [styles.filterTabActive, { backgroundColor: '#BF6B3D' }]
                  : { backgroundColor: theme.surface, borderColor: theme.border },
              ]}
              onPress={() => setFilterStatus(tab.id)}
              activeOpacity={0.8}
            >
              <Text
                style={[
                  styles.filterTabText,
                  { color: filterStatus === tab.id ? '#FFFFFF' : theme.textSecondary },
                ]}
              >
                {tab.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Grievance Queue List */}
        {loadingQueue ? (
          <View style={[styles.emptyQueueCard, { backgroundColor: theme.card, borderColor: theme.border }]}>
            <ActivityIndicator color={theme.primary} />
            <Text style={[styles.emptySub, { color: theme.textMuted, marginTop: 8 }]}>Loading department queue…</Text>
          </View>
        ) : filteredQueue.length === 0 ? (
          <View style={[styles.emptyQueueCard, { backgroundColor: theme.card, borderColor: theme.border }]}>
            <Ionicons name="checkmark-done-circle-outline" size={44} color="#2E9E63" />
            <Text style={[styles.emptyTitle, { color: theme.text }]}>Queue Cleared!</Text>
            <Text style={[styles.emptySub, { color: theme.textMuted }]}>
              No pending grievances under this filter for {currentDept.name}.
            </Text>
          </View>
        ) : (
          filteredQueue.map((item) => {
            const isResolved = item.status === 'Resolved' || item.status === 'Closed';
            const isInspection = item.status === 'Inspection Scheduled' || item.status === 'In Progress';
            const sla = slaCountdownText(item);
            return (
              <TouchableOpacity
                key={item.id}
                style={[
                  styles.grievanceCard,
                  {
                    backgroundColor: theme.card,
                    borderColor: isResolved ? '#2E9E63' : isInspection ? '#BF6B3D' : theme.primary,
                  },
                ]}
                onPress={() => openComplaintDetail(item)}
                activeOpacity={0.85}
              >
                <View style={styles.cardTopRow}>
                  <View style={styles.citizenInfoRow}>
                    <View style={[styles.citizenAvatar, { backgroundColor: theme.surface }]}>
                      <Text style={styles.citizenAvatarText}>
                        {item.citizenName ? item.citizenName.charAt(0) : 'C'}
                      </Text>
                    </View>
                    <View>
                      <Text style={[styles.citizenNameText, { color: theme.text }]}>
                        {item.citizenName || 'Citizen Grievance'}
                      </Text>
                      <Text style={[styles.refNumText, { color: theme.textMuted }]}>
                        {item.referenceCode || item.id} • {item.dateFiled ? new Date(item.dateFiled).toLocaleDateString() : 'Today'}
                      </Text>
                    </View>
                  </View>

                  <View
                    style={[
                      styles.statusPill,
                      {
                        backgroundColor: isResolved
                          ? 'rgba(46, 158, 99, 0.15)'
                          : isInspection
                          ? 'rgba(191, 107, 61, 0.15)'
                          : 'rgba(53, 71, 168, 0.15)',
                      },
                    ]}
                  >
                    <Text
                      style={[
                        styles.statusPillText,
                        { color: isResolved ? '#2E9E63' : isInspection ? '#BF6B3D' : theme.primaryLight },
                      ]}
                    >
                      {item.status || 'Under Review'}
                    </Text>
                  </View>
                </View>

                {/* Category / Priority / Severity — from the existing AI
                    classification fields (absent if not yet classified,
                    shown as-is, never invented) */}
                {(item.category || item.priority || item.severity) && (
                  <View style={styles.badgeRow}>
                    {item.category && (
                      <View style={[styles.miniBadge, { backgroundColor: theme.surface }]}>
                        <Text style={[styles.miniBadgeText, { color: theme.textSecondary }]}>{item.category}</Text>
                      </View>
                    )}
                    {item.priority && (
                      <View style={[styles.miniBadge, { backgroundColor: 'rgba(191, 107, 61, 0.15)' }]}>
                        <Text style={[styles.miniBadgeText, { color: '#BF6B3D' }]}>Priority: {item.priority}</Text>
                      </View>
                    )}
                    {item.severity && (
                      <View style={[styles.miniBadge, { backgroundColor: 'rgba(194, 69, 69, 0.12)' }]}>
                        <Text style={[styles.miniBadgeText, { color: '#C24545' }]}>Severity: {item.severity}</Text>
                      </View>
                    )}
                  </View>
                )}

                {/* Grievance Snippet */}
                <Text style={[styles.grievanceTitle, { color: theme.text }]} numberOfLines={1}>
                  {item.title || 'Civic Grievance / RTI Request'}
                </Text>
                <Text style={[styles.grievanceBody, { color: theme.textSecondary }]} numberOfLines={2}>
                  {item.issue || 'Deep potholes causing road safety hazards and traffic bottlenecks.'}
                </Text>

                {/* Real SLA status, computed from this complaint's own sla_due_at */}
                <View style={[styles.slaRow, { backgroundColor: theme.surface }]}>
                  <Ionicons name="time-outline" size={13} color={sla.urgent ? '#C24545' : theme.accentAmber} />
                  <Text style={[styles.slaText, { color: theme.textMuted }]}>
                    <Text style={{ color: sla.urgent ? '#C24545' : theme.text, fontWeight: '700' }}>{sla.text}</Text>
                  </Text>
                  <Text style={[styles.tapToActText, { color: '#BF6B3D' }]}>Take Action →</Text>
                </View>
              </TouchableOpacity>
            );
          })
        )}

        {/* Modal: Complaint Action & ATR Upload Desk */}
        {selectedComplaint && (
          <Modal
            animationType="slide"
            transparent={true}
            visible={!!selectedComplaint}
            onRequestClose={() => setSelectedComplaint(null)}
          >
            <View style={styles.modalOverlay}>
              <View style={[styles.modalCard, { backgroundColor: theme.card, borderColor: '#BF6B3D' }]}>
                <View style={styles.modalHeader}>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.modalTitle, { color: theme.text }]}>
                      Official Resolution Action Desk
                    </Text>
                    <Text style={[styles.modalSub, { color: theme.textMuted }]}>
                      Grievance ID: {selectedComplaint.id}
                    </Text>
                  </View>
                  <TouchableOpacity onPress={() => setSelectedComplaint(null)}>
                    <Ionicons name="close-circle" size={26} color={theme.textMuted} />
                  </TouchableOpacity>
                </View>

                <ScrollView style={{ maxHeight: 460 }} showsVerticalScrollIndicator={false}>
                  {/* Complaint Information — the fields Step 5 of the
                      officer workflow spec calls for, from the actual
                      complaint record (nothing invented). */}
                  <View style={[styles.citizenDetailBox, { backgroundColor: theme.surface }]}>
                    <Text style={[styles.boxHeader, { color: theme.text }]}>Complaint Information:</Text>
                    <Text style={[styles.boxText, { color: theme.textSecondary }]}>
                      Category: <Text style={{ color: theme.text, fontWeight: '700' }}>{selectedComplaint.category || 'Not classified'}</Text>
                      {selectedComplaint.priority ? `   •   Priority: ${selectedComplaint.priority}` : ''}
                      {selectedComplaint.severity ? `   •   Severity: ${selectedComplaint.severity}` : ''}
                    </Text>
                    <Text style={[styles.boxText, { color: theme.textSecondary }]}>
                      Status: <Text style={{ color: theme.text, fontWeight: '700' }}>{selectedComplaint.status || 'Filed'}</Text>
                    </Text>
                    <Text style={[styles.boxText, { color: theme.textSecondary }]}>
                      Filed: {selectedComplaint.dateFiled ? new Date(selectedComplaint.dateFiled).toLocaleString() : '—'}
                      {selectedComplaint.updatedAt ? `   •   Updated: ${new Date(selectedComplaint.updatedAt).toLocaleString()}` : ''}
                    </Text>
                    <Text style={[styles.boxText, { color: (slaCountdownText(selectedComplaint).urgent ? '#C24545' : theme.textSecondary), fontWeight: slaCountdownText(selectedComplaint).urgent ? '700' : '400' }]}>
                      SLA: {slaCountdownText(selectedComplaint).text}
                    </Text>
                  </View>

                  {/* Citizen Details */}
                  <View style={[styles.citizenDetailBox, { backgroundColor: theme.surface }]}>
                    <Text style={[styles.boxHeader, { color: theme.text }]}>Citizen Information:</Text>
                    <Text style={[styles.boxText, { color: theme.textSecondary }]}>
                      Name: <Text style={{ color: theme.text, fontWeight: '700' }}>{selectedComplaint.citizenName || 'Not provided'}</Text>
                    </Text>
                    <Text style={[styles.boxText, { color: theme.textSecondary }]}>
                      Contact: {selectedComplaint.citizenPhone || selectedComplaint.citizenEmail || 'Not provided'}
                    </Text>
                    <Text style={[styles.boxText, { color: theme.textSecondary }]}>
                      City: {selectedComplaint.city || 'Not specified'}
                    </Text>

                    <View style={styles.contactActionRow}>
                      <TouchableOpacity
                        style={[styles.contactBtn, { backgroundColor: theme.primaryGlow }]}
                        onPress={() => handleContactCitizen(selectedComplaint.citizenPhone, selectedComplaint.citizenEmail)}
                      >
                        <Ionicons name="call" size={14} color={theme.primaryLight} />
                        <Text style={[styles.contactBtnText, { color: theme.primaryLight }]}>Call Citizen</Text>
                      </TouchableOpacity>
                    </View>
                  </View>

                  {/* Grievance Statement */}
                  <Text style={[styles.sectionLabel, { color: theme.text }]}>Formal Complaint Body:</Text>
                  <View style={[styles.letterContentBox, { backgroundColor: theme.surface, borderColor: theme.border }]}>
                    <Text style={[styles.letterText, { color: theme.textSecondary }]}>
                      {selectedComplaint.letterText || selectedComplaint.issue || 'Formal grievance filed with department authorities requesting urgent civic inspection and repair under statutory citizen charter rules.'}
                    </Text>
                  </View>

                  {/* Phase 3: Evidence Photo */}
                  {selectedComplaint.imageUrl && (
                    <>
                      <Text style={[styles.sectionLabel, { color: theme.text, marginTop: 12 }]}>
                        📷 Evidence Photo:
                      </Text>
                      <Image
                        source={{ uri: resolveComplaintImageUrl(selectedComplaint.imageUrl) }}
                        style={styles.evidenceImage}
                        resizeMode="cover"
                      />
                    </>
                  )}

                  {/* Phase 3: Precise Location — what officer_location_understanding
                      needs to be able to answer "where exactly is this?" from the
                      structured record rather than free text alone. */}
                  {(selectedComplaint.wardNumber || selectedComplaint.address || (selectedComplaint.lat != null && selectedComplaint.lng != null)) && (
                    <>
                      <Text style={[styles.sectionLabel, { color: theme.text, marginTop: 12 }]}>
                        📍 Precise Location:
                      </Text>
                      <View style={[styles.citizenDetailBox, { backgroundColor: theme.surface }]}>
                        {selectedComplaint.wardNumber && (
                          <Text style={[styles.boxText, { color: theme.textSecondary }]}>
                            Ward: <Text style={{ color: theme.text, fontWeight: '700' }}>{selectedComplaint.wardNumber}</Text>
                          </Text>
                        )}
                        {selectedComplaint.address && (
                          <Text style={[styles.boxText, { color: theme.textSecondary }]}>
                            Address: <Text style={{ color: theme.text, fontWeight: '700' }}>{selectedComplaint.address}</Text>
                          </Text>
                        )}
                        <Text style={[styles.boxText, { color: theme.textSecondary }]}>
                          City: {selectedComplaint.city || 'Not specified'}
                        </Text>
                        {selectedComplaint.lat != null && selectedComplaint.lng != null && (
                          <Text style={[styles.boxText, { color: theme.textSecondary }]}>
                            Latitude: {Number(selectedComplaint.lat).toFixed(6)} • Longitude: {Number(selectedComplaint.lng).toFixed(6)}
                          </Text>
                        )}
                        {(selectedComplaint.lat != null || selectedComplaint.address) && (
                          <View style={styles.contactActionRow}>
                            <TouchableOpacity
                              style={[styles.contactBtn, { backgroundColor: theme.primaryGlow }]}
                              onPress={() => handleOpenComplaintLocation(selectedComplaint.lat, selectedComplaint.lng, selectedComplaint.address)}
                            >
                              <Ionicons name="map-outline" size={14} color={theme.primaryLight} />
                              <Text style={[styles.contactBtnText, { color: theme.primaryLight }]}>Open in Maps</Text>
                            </TouchableOpacity>
                          </View>
                        )}
                      </View>
                    </>
                  )}
                  {/* Update / History Log — Step 7 & 8: operational
                      updates and a tamper-evident audit trail, both
                      derived from data the backend already tracks. */}
                  <Text style={[styles.sectionLabel, { color: theme.text, marginTop: 12 }]}>
                    Update History:
                  </Text>
                  <View style={[styles.letterContentBox, { backgroundColor: theme.surface, borderColor: theme.border, maxHeight: 160 }]}>
                    {loadingHistory ? (
                      <ActivityIndicator color={theme.primary} />
                    ) : complaintHistory.updateLog.length === 0 ? (
                      <Text style={[styles.boxText, { color: theme.textMuted }]}>No updates logged yet.</Text>
                    ) : (
                      <ScrollView showsVerticalScrollIndicator={false}>
                        {[...complaintHistory.updateLog].reverse().map((entry, idx) => (
                          <View key={idx} style={{ marginBottom: 8 }}>
                            <Text style={[styles.boxText, { color: theme.text, fontWeight: '700' }]}>
                              {entry.action === 'note' ? 'Note' : (entry.status || 'Update')}
                              {entry.timestamp ? ` — ${new Date(entry.timestamp).toLocaleString()}` : ''}
                            </Text>
                            {entry.remarks ? (
                              <Text style={[styles.boxText, { color: theme.textSecondary }]}>{entry.remarks}</Text>
                            ) : null}
                          </View>
                        ))}
                      </ScrollView>
                    )}
                  </View>

                  {/* Add an operational note without changing status */}
                  <TextInput
                    style={[styles.remarksInput, { backgroundColor: theme.inputBg, color: theme.text, borderColor: theme.border, marginTop: 8 }]}
                    placeholder="Add an investigation note or action-taken update (does not change status)..."
                    placeholderTextColor={theme.textMuted}
                    value={updateNoteInput}
                    onChangeText={setUpdateNoteInput}
                    multiline
                    numberOfLines={2}
                  />
                  <TouchableOpacity
                    style={[styles.contactBtn, { backgroundColor: theme.primaryGlow, alignSelf: 'flex-start', marginTop: 6, opacity: (!updateNoteInput.trim() || savingUpdate) ? 0.5 : 1 }]}
                    onPress={handleAddUpdate}
                    disabled={!updateNoteInput.trim() || savingUpdate}
                  >
                    {savingUpdate ? <ActivityIndicator size="small" color={theme.primaryLight} /> : <Ionicons name="add-circle-outline" size={14} color={theme.primaryLight} />}
                    <Text style={[styles.contactBtnText, { color: theme.primaryLight }]}>Add Update</Text>
                  </TouchableOpacity>

                  {/* Officer Remarks Field */}
                  <Text style={[styles.sectionLabel, { color: theme.text, marginTop: 12 }]}>
                    Official Action Remarks & ATR Notes:
                  </Text>
                  <TextInput
                    style={[styles.remarksInput, { backgroundColor: theme.inputBg, color: theme.text, borderColor: theme.border }]}
                    placeholder="Enter official remarks, contractor inspection details, or completion work order number..."
                    placeholderTextColor={theme.textMuted}
                    value={officerRemarksInput}
                    onChangeText={setOfficerRemarksInput}
                    multiline
                    numberOfLines={3}
                  />

                  {/* Status Action Buttons — every transition the officer
                      is actually allowed to make, mirroring the same
                      status list the server validates against (see
                      server/src/services/complaintStatus.js). */}
                  <Text style={[styles.sectionLabel, { color: theme.text, marginTop: 14 }]}>
                    Update Grievance Status:
                  </Text>
                  <View style={styles.actionButtonsGrid}>
                    {OFFICER_STATUS_ACTIONS.map((action) => (
                      <TouchableOpacity
                        key={action.status}
                        style={[styles.statusBtn, { backgroundColor: action.color, opacity: actionInProgress ? 0.6 : 1 }]}
                        onPress={() => handleUpdateStatus(action.status)}
                        activeOpacity={0.8}
                        disabled={actionInProgress}
                      >
                        <Ionicons name={action.icon} size={16} color="#FFFFFF" />
                        <Text style={styles.statusBtnText}>{action.label}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </ScrollView>
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
  scrollContent: { padding: SPACING.md, paddingBottom: 60 },
  officerCard: {
    borderRadius: RADIUS.xl,
    padding: SPACING.md,
    borderWidth: 1.5,
    marginBottom: SPACING.md,
  },
  officerTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  govBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: RADIUS.full,
  },
  govBadgeText: { fontSize: 11, fontWeight: '700', color: '#BF6B3D' },
  switchRoleBtn: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  switchRoleText: { fontSize: 11, color: '#BF6B3D', fontWeight: '700' },
  rulesBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderRadius: RADIUS.md,
    paddingVertical: 8,
    marginTop: 10,
    gap: 6,
  },
  rulesBtnText: { fontSize: 11, color: '#BF6B3D', fontWeight: '700' },
  rulesModalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', padding: SPACING.md },
  rulesModalCard: { borderRadius: RADIUS.xl, padding: SPACING.md, borderWidth: 1.5, maxHeight: '85%' },
  rulesModalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  rulesModalTitle: { fontSize: 16, fontWeight: '800' },
  rulesModalSub: { fontSize: 11, lineHeight: 16, marginBottom: 10 },
  rulesEmptyText: { fontSize: 12, textAlign: 'center', paddingVertical: 12 },
  ruleRow: { flexDirection: 'row', alignItems: 'center', borderTopWidth: 1, paddingVertical: 8 },
  ruleName: { fontSize: 12.5, fontWeight: '700' },
  ruleDetail: { fontSize: 10, marginTop: 2 },
  rulesInput: { borderRadius: RADIUS.md, borderWidth: 1, padding: 9, fontSize: 12.5, marginBottom: 8 },
  rulesSaveBtn: { paddingVertical: 11, borderRadius: RADIUS.md, alignItems: 'center', marginTop: 4 },
  officerProfileRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  officerAvatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  officerAvatarText: { color: '#FFFFFF', fontSize: 20, fontWeight: '900' },
  officerName: { fontSize: 16, fontWeight: '800' },
  officerDesignation: { fontSize: 11, marginTop: 1 },
  officerDept: { fontSize: 12, fontWeight: '700', marginTop: 2 },
  deptSelectorRow: { marginBottom: SPACING.md, flexDirection: 'row', alignItems: 'center' },
  deptLockedNote: { fontSize: 10, lineHeight: 14, marginTop: -6, marginBottom: SPACING.md },
  deptSelectLabel: { fontSize: 10, fontWeight: '800', letterSpacing: 0.5, marginBottom: 6, marginRight: 8 },
  deptScroll: { flexDirection: 'row' },
  deptChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: RADIUS.full,
    borderWidth: 1,
    marginRight: 6,
    gap: 6,
  },
  deptEmoji: { fontSize: 14 },
  deptChipText: { fontSize: 11 },
  metricsCard: {
    borderRadius: RADIUS.lg,
    padding: SPACING.md,
    borderWidth: 1.5,
    marginBottom: SPACING.md,
  },
  metricsHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  metricsTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  metricsTitle: { fontSize: 13, fontWeight: '800' },
  slaBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  slaBadgeText: { fontSize: 10, fontWeight: '700' },
  metricsGrid: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  metricItem: { flex: 1, alignItems: 'center' },
  metricValue: { fontSize: 16, fontWeight: '900' },
  metricLabel: { fontSize: 10, marginTop: 2 },
  metricDivider: { width: 1, height: 26, backgroundColor: 'rgba(150,150,150,0.2)' },
  sectionHeaderRow: { marginBottom: 8 },
  sectionTitle: { fontSize: 14, fontWeight: '800' },
  filterTabsRow: { flexDirection: 'row', gap: 6, marginBottom: SPACING.md },
  filterTabBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: RADIUS.sm,
    borderWidth: 1,
  },
  filterTabActive: { borderWidth: 1, borderColor: '#BF6B3D' },
  filterTabText: { fontSize: 11, fontWeight: '700' },
  emptyQueueCard: {
    padding: 30,
    borderRadius: RADIUS.lg,
    alignItems: 'center',
    borderWidth: 1,
  },
  emptyTitle: { fontSize: 15, fontWeight: '800', marginTop: 8 },
  emptySub: { fontSize: 11, textAlign: 'center', marginTop: 2 },
  backendNotice: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    padding: 8,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    marginBottom: SPACING.sm,
  },
  backendNoticeText: {
    fontSize: 10.5,
    color: '#C24545',
    flex: 1,
    lineHeight: 14,
  },
  grievanceCard: {
    borderRadius: RADIUS.lg,
    padding: 12,
    borderWidth: 1.5,
    marginBottom: 10,
  },
  cardTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  citizenInfoRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  citizenAvatar: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  citizenAvatarText: { fontSize: 12, fontWeight: '800' },
  citizenNameText: { fontSize: 12, fontWeight: '700' },
  refNumText: { fontSize: 10 },
  statusPill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  statusPillText: { fontSize: 10, fontWeight: '700' },
  grievanceTitle: { fontSize: 13, fontWeight: '800', marginBottom: 2 },
  grievanceBody: { fontSize: 11, lineHeight: 16, marginBottom: 8 },
  badgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 6 },
  miniBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.sm },
  miniBadgeText: { fontSize: 10, fontWeight: '700' },
  slaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 6,
    borderRadius: RADIUS.sm,
  },
  slaText: { fontSize: 10 },
  tapToActText: { fontSize: 11, fontWeight: '800' },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', padding: SPACING.md },
  modalCard: { borderRadius: RADIUS.xl, padding: SPACING.md, borderWidth: 1.5 },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  modalTitle: { fontSize: 15, fontWeight: '800' },
  modalSub: { fontSize: 10, marginTop: 1 },
  citizenDetailBox: { padding: 10, borderRadius: RADIUS.md, marginBottom: 10 },
  evidenceImage: { width: '100%', height: 200, borderRadius: RADIUS.md, marginBottom: 10 },
  boxHeader: { fontSize: 12, fontWeight: '800', marginBottom: 4 },
  boxText: { fontSize: 11, marginBottom: 2 },
  contactActionRow: { marginTop: 6 },
  contactBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: RADIUS.sm,
    alignSelf: 'flex-start',
  },
  contactBtnText: { fontSize: 11, fontWeight: '700' },
  sectionLabel: { fontSize: 12, fontWeight: '800', marginBottom: 4 },
  letterContentBox: { padding: 10, borderRadius: RADIUS.md, borderWidth: 1, maxHeight: 120 },
  letterText: { fontSize: 11, lineHeight: 16 },
  remarksInput: { borderRadius: RADIUS.md, padding: 8, fontSize: 12, borderWidth: 1, minHeight: 60 },
  actionButtonsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 },
  statusBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: RADIUS.sm,
    width: '48%',
    justifyContent: 'center',
  },
  statusBtnText: { color: '#FFFFFF', fontSize: 10, fontWeight: '800' },
});
