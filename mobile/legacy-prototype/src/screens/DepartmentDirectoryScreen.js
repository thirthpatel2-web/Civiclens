// CivicLens - All-India 6-Tier Public Authority Directory & Direct Officer Email Hub

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  SafeAreaView,
  Linking,
  Platform,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE } from '../constants/theme';
import {
  ALL_PUBLIC_AUTHORITIES,
  DEPARTMENT_TIERS,
  NATIONAL_HELPLINES,
} from '../data/departmentsData';
import { sendEmail } from '../services/emailService';

export default function DepartmentDirectoryScreen({ navigation }) {
  const { theme, t, selectedCity, getHelplineInfo } = useApp();

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTier, setSelectedTier] = useState('all');

  // Filter authorities by search query and tier
  const filteredAuthorities = ALL_PUBLIC_AUTHORITIES.filter((d) => {
    const matchesTier = selectedTier === 'all' || d.tier === selectedTier;
    const q = searchQuery.trim().toLowerCase();
    if (!q) return matchesTier;

    const matchesSearch =
      d.name.toLowerCase().includes(q) ||
      (d.fullName && d.fullName.toLowerCase().includes(q)) ||
      (d.nodalOfficer && d.nodalOfficer.toLowerCase().includes(q)) ||
      (d.email && d.email.toLowerCase().includes(q)) ||
      (d.category && d.category.toLowerCase().includes(q)) ||
      (d.keywords && d.keywords.some((kw) => kw.toLowerCase().includes(q)));

    return matchesTier && matchesSearch;
  });

  const handleCall = (num) => {
    if (num) Linking.openURL(`tel:${num}`);
  };

  const handleEmailOfficer = async (email, deptName) => {
    if (!email) {
      Alert.alert('Notice', 'No official email on file.');
      return;
    }
    const subject = `Statutory Representation / Citizen Grievance - [${deptName}]`;
    const body = `To,\nThe Nodal Officer / Public Information Officer,\n${deptName}\n\nRespected Sir/Madam,\n\nI am writing to formally submit a representation regarding civic/statutory matters under your jurisdiction.\n\nRegards,\nCitizen Applicant`;

    const result = await sendEmail({ to: email, subject, body });
    if (result.sentAutomatically) {
      Alert.alert('Email Sent', `Representation automatically sent to ${deptName} (${email}).`);
    }
    // If not auto-sent, sendEmail already opened the mailto: fallback.
  };

  const handleOpenPortal = (url) => {
    if (url) Linking.openURL(url);
  };

  const handleDraftForDept = (dept) => {
    navigation.navigate('Complaint', {
      tab: 'civic',
      initialText: `Grievance addressed to ${dept.name}: `,
    });
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
          <Text style={[styles.screenTitle, { color: theme.text }]}>
            🏛️ All-India Authority Directory
          </Text>
          <Text style={[styles.screenSubtitle, { color: theme.textSecondary }]}>
            Reference contacts & nodal officer info for Central & State bodies — confirm against the department's official RTI page before relying on it
          </Text>
        </View>

        <View style={[styles.verifyBanner, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          <Ionicons name="information-circle-outline" size={14} color={theme.textMuted} />
          <Text style={[styles.verifyBannerText, { color: theme.textMuted }]}>
            Officer names, emails and phone numbers change over time. CivicLens compiles these as a starting point — tap "Official Portal" on any entry to verify current details.
          </Text>
        </View>

        {/* Search Bar */}
        <View style={[styles.searchBox, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <Ionicons name="search" size={18} color={theme.textMuted} style={{ marginRight: 8 }} />
          <TextInput
            style={[styles.searchInput, { color: theme.text }]}
            placeholder="Search ministries, departments, officers, or keywords..."
            placeholderTextColor={theme.textMuted}
            value={searchQuery}
            onChangeText={setSearchQuery}
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity onPress={() => setSearchQuery('')}>
              <Ionicons name="close-circle" size={18} color={theme.textMuted} />
            </TouchableOpacity>
          )}
        </View>

        {/* 6-Tier Filter Pills */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.tierScroll}
          contentContainerStyle={styles.tierScrollContent}
        >
          {DEPARTMENT_TIERS.map((tier) => {
            const isSelected = selectedTier === tier.id;
            return (
              <TouchableOpacity
                key={tier.id}
                style={[
                  styles.tierPill,
                  isSelected
                    ? [styles.tierPillActive, { backgroundColor: theme.primary, borderColor: '#60A5FA' }]
                    : [styles.tierPillInactive, { backgroundColor: theme.card, borderColor: theme.cardBorder }],
                ]}
                onPress={() => setSelectedTier(tier.id)}
                activeOpacity={0.8}
              >
                <Text
                  style={[
                    styles.tierPillText,
                    {
                      color: isSelected ? '#FFFFFF' : theme.textSecondary,
                      fontWeight: isSelected ? '800' : '600',
                    },
                  ]}
                >
                  {tier.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {/* 24x7 Emergency Hotlines Quick Strip */}
        <View style={styles.sectionHeaderRow}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>
            🚨 24x7 National Emergency Hotlines
          </Text>
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.hotlinesScroll}>
          {NATIONAL_HELPLINES.map((hl) => {
            const hlInfo = getHelplineInfo(hl.id);
            return (
              <TouchableOpacity
                key={hl.id}
                style={[styles.hotlineCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
                onPress={() => handleCall(hl.number)}
                activeOpacity={0.8}
              >
                <Text style={styles.hotlineIcon}>{hl.icon}</Text>
                <Text style={[styles.hotlineName, { color: theme.text }]} numberOfLines={1}>
                  {hlInfo.name || hl.name}
                </Text>
                <View style={[styles.hotlinePill, { backgroundColor: theme.primaryGlow }]}>
                  <Ionicons name="call" size={11} color={theme.primaryLight} />
                  <Text style={[styles.hotlineNumber, { color: theme.primaryLight }]}>{hl.number}</Text>
                </View>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {/* Authority Cards List */}
        <View style={styles.deptListHeader}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>
            Public Authorities ({filteredAuthorities.length} found)
          </Text>
        </View>

        {filteredAuthorities.map((dept) => (
          <View
            key={dept.id}
            style={[styles.deptCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
          >
            {/* Card Top Row */}
            <View style={styles.deptTopRow}>
              <View style={[styles.deptIconCircle, { backgroundColor: theme.primaryGlow }]}>
                <Text style={styles.deptIconText}>{dept.icon || '🏛️'}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <View style={styles.tierTagRow}>
                  <View style={[styles.tierTag, { backgroundColor: 'rgba(53, 71, 168, 0.12)' }]}>
                    <Text style={[styles.tierTagText, { color: theme.primaryLight }]}>
                      {dept.tier ? dept.tier.toUpperCase() : 'AUTHORITY'}
                    </Text>
                  </View>
                  <Text style={[styles.slaTag, { color: theme.accentEmerald }]}>⚡ {dept.slaDays || 30}d SLA</Text>
                </View>
                <Text style={[styles.deptName, { color: theme.text }]}>{dept.name}</Text>
                <Text style={[styles.deptFullName, { color: theme.textSecondary }]} numberOfLines={2}>
                  {dept.fullName || dept.category}
                </Text>
              </View>
            </View>

            {/* Officer & Address Info */}
            <View style={[styles.officerBox, { backgroundColor: theme.surface }]}>
              <View style={styles.officerRow}>
                <Ionicons name="person" size={13} color={theme.primary} />
                <Text style={[styles.officerLabel, { color: theme.textSecondary }]}>
                  Nodal Officer: <Text style={{ color: theme.text, fontWeight: '700' }}>{dept.nodalOfficer || 'Executive Commissioner / PIO'}</Text>
                </Text>
              </View>
              <View style={styles.officerRow}>
                <Ionicons name="location" size={13} color={theme.accentEmerald} />
                <Text style={[styles.officerLabel, { color: theme.textSecondary }]}>
                  Jurisdiction: <Text style={{ color: theme.text }}>{dept.address || dept.city}</Text>
                </Text>
              </View>
            </View>

            {/* Direct Action Buttons Strip */}
            <View style={styles.deptActionsRow}>
              {/* Direct Call */}
              <TouchableOpacity
                style={[styles.actionBtn, { backgroundColor: theme.surface, borderColor: theme.border }]}
                onPress={() => handleCall(dept.helpline)}
                activeOpacity={0.8}
              >
                <Ionicons name="call" size={14} color={theme.accentEmerald} />
                <Text style={[styles.actionBtnText, { color: theme.text }]}>Call</Text>
              </TouchableOpacity>

              {/* Direct Email to Official */}
              <TouchableOpacity
                style={[styles.actionBtn, { backgroundColor: theme.primaryGlow, borderColor: theme.primary }]}
                onPress={() => handleEmailOfficer(dept.email, dept.name)}
                activeOpacity={0.8}
              >
                <Ionicons name="mail" size={14} color={theme.primaryLight} />
                <Text style={[styles.actionBtnText, { color: theme.primaryLight, fontWeight: '800' }]}>
                  Email PIO
                </Text>
              </TouchableOpacity>

              {/* Official Portal */}
              {dept.portalUrl && (
                <TouchableOpacity
                  style={[styles.actionBtn, { backgroundColor: theme.surface, borderColor: theme.border }]}
                  onPress={() => handleOpenPortal(dept.portalUrl)}
                  activeOpacity={0.8}
                >
                  <Ionicons name="globe-outline" size={14} color={theme.textSecondary} />
                  <Text style={[styles.actionBtnText, { color: theme.textSecondary }]}>Portal</Text>
                </TouchableOpacity>
              )}

              {/* Draft Complaint Shortcut */}
              <TouchableOpacity
                style={[styles.draftShortcutBtn, { backgroundColor: theme.primary }]}
                onPress={() => handleDraftForDept(dept)}
                activeOpacity={0.85}
              >
                <Ionicons name="document-text" size={13} color="#FFFFFF" />
                <Text style={styles.draftShortcutText}>Draft Letter</Text>
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
  scrollContent: { paddingHorizontal: SPACING.md, paddingBottom: 100 },
  header: {
    paddingVertical: SPACING.sm,
    marginBottom: SPACING.xs,
  },
  verifyBanner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    padding: 8,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    marginBottom: SPACING.sm,
  },
  verifyBannerText: {
    fontSize: 10.5,
    flex: 1,
    lineHeight: 14,
  },
  screenTitle: {
    fontSize: FONT_SIZE.xl,
    fontWeight: '800',
    letterSpacing: -0.3,
  },
  screenSubtitle: {
    fontSize: FONT_SIZE.xs,
    marginTop: 2,
    lineHeight: 16,
  },
  searchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: RADIUS.lg,
    paddingHorizontal: SPACING.sm,
    height: 46,
    borderWidth: 1,
    marginBottom: SPACING.sm,
  },
  searchInput: {
    flex: 1,
    fontSize: FONT_SIZE.xs,
    height: '100%',
  },
  tierScroll: {
    marginBottom: SPACING.md,
  },
  tierScrollContent: {
    gap: 6,
    paddingVertical: 2,
  },
  tierPill: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: RADIUS.full,
    borderWidth: 1,
  },
  tierPillActive: {},
  tierPillInactive: {},
  tierPillText: {
    fontSize: 11,
  },
  sectionHeaderRow: {
    marginBottom: SPACING.xs,
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.3,
  },
  hotlinesScroll: {
    flexDirection: 'row',
    marginBottom: SPACING.md,
  },
  hotlineCard: {
    width: 120,
    borderRadius: RADIUS.lg,
    padding: SPACING.sm,
    marginRight: 8,
    borderWidth: 1,
    alignItems: 'center',
  },
  hotlineIcon: {
    fontSize: 22,
    marginBottom: 4,
  },
  hotlineName: {
    fontSize: 10,
    fontWeight: '700',
    textAlign: 'center',
    marginBottom: 4,
  },
  hotlinePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: RADIUS.full,
  },
  hotlineNumber: {
    fontSize: 10,
    fontWeight: '800',
  },
  deptListHeader: {
    marginBottom: SPACING.sm,
  },
  deptCard: {
    borderRadius: RADIUS.xl,
    padding: SPACING.md,
    borderWidth: 1,
    marginBottom: SPACING.md,
  },
  deptTopRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: SPACING.xs,
  },
  deptIconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  deptIconText: {
    fontSize: 22,
  },
  tierTagRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 2,
  },
  tierTag: {
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 4,
  },
  tierTagText: {
    fontSize: 9,
    fontWeight: '800',
  },
  slaTag: {
    fontSize: 10,
    fontWeight: '800',
  },
  deptName: {
    fontSize: FONT_SIZE.sm,
    fontWeight: '800',
    marginBottom: 2,
  },
  deptFullName: {
    fontSize: 11,
    lineHeight: 15,
  },
  officerBox: {
    borderRadius: RADIUS.md,
    padding: 8,
    marginVertical: 8,
    gap: 4,
  },
  officerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  officerLabel: {
    fontSize: 10,
    flex: 1,
  },
  deptActionsRow: {
    flexDirection: 'row',
    gap: 6,
    marginTop: 4,
  },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    gap: 4,
  },
  actionBtnText: {
    fontSize: 11,
    fontWeight: '700',
  },
  draftShortcutBtn: {
    flex: 1.4,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    borderRadius: RADIUS.md,
    gap: 4,
  },
  draftShortcutText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '800',
  },
});
