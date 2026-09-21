// CivicLens - Digital India Citizen Portal Home Screen
// Ultra-Clean, Sleek UI/UX with Minimal Text Clutter & Fast Discoverability

import React, { useState, useEffect } from 'react';
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
  ActivityIndicator,
  Modal,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE, FONT_FAMILY } from '../constants/theme';
import { CITIES, NATIONAL_HELPLINES } from '../data/departmentsData';
import { loadCityHeatmapSummary } from '../services/heatmapService';
import { classifyCitizenIssue, recordClassificationFeedback } from '../services/aiService';
import { loadNotifications, markNotificationRead, subscribeToNotifications } from '../services/notificationService';
import VoiceListeningModal from '../components/VoiceListeningModal';
import HoverCard from '../components/HoverCard';
import HoverChip from '../components/HoverChip';

export default function HomeScreen({ navigation }) {
  const {
    theme,
    themeMode,
    toggleTheme,
    t,
    userProfile,
    userRole,
    officialProfile,
    selectedCity,
    setCity,
    language,
    setLanguage,
    languagesList,
    getCityName,
    getHelplineInfo,
    logout,
    currentUserId,
  } = useApp();

  const CLASSIFICATION_CATEGORIES = [
    { id: 'rti', icon: '🏛️', label: 'RTI', targetScreen: 'Complaint', screenParams: { tab: 'rti' } },
    { id: 'legal', icon: '⚖️', label: 'Legal Case', targetScreen: 'CaseAI', screenParams: {} },
    { id: 'heatmap', icon: '🗺️', label: 'Map', targetScreen: 'Heatmap', screenParams: {} },
    { id: 'document', icon: '📄', label: 'Document', targetScreen: 'DocumentScanner', screenParams: {} },
    { id: 'locator', icon: '📍', label: 'Locator', targetScreen: 'CivicLocator', screenParams: {} },
    { id: 'civic', icon: '📝', label: 'Civic Complaint', targetScreen: 'Complaint', screenParams: { tab: 'civic' } },
  ];

  const [searchQuery, setSearchQuery] = useState('');
  const [classifiedAction, setClassifiedAction] = useState(null);
  const [voiceModalVisible, setVoiceModalVisible] = useState(false);
  const [cityPulse, setCityPulse] = useState(null);
  const [cityPulseLoading, setCityPulseLoading] = useState(true);
  const [notifications, setNotifications] = useState([]);
  const [notifPanelVisible, setNotifPanelVisible] = useState(false);
  const unreadCount = notifications.filter((n) => !n.is_read).length;

  useEffect(() => {
    if (!currentUserId) return;
    loadNotifications(currentUserId).then(setNotifications);

    const unsubscribe = subscribeToNotifications(currentUserId, (newNotif) => {
      setNotifications((prev) => [newNotif, ...prev]);
    });
    return unsubscribe;
  }, [currentUserId]);

  const handleMarkNotificationRead = async (id) => {
    await markNotificationRead(id);
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
  };

  useEffect(() => {
    let cancelled = false;
    setCityPulseLoading(true);
    loadCityHeatmapSummary(selectedCity).then((result) => {
      if (!cancelled) {
        setCityPulse(result);
        setCityPulseLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [selectedCity]);

  const handleSearchChange = (text) => {
    setSearchQuery(text);
    if (text.trim().length > 3) {
      const classification = classifyCitizenIssue(text);
      setClassifiedAction(classification);
    } else {
      setClassifiedAction(null);
    }
  };

  const handleVoiceSearchResult = (transcript) => {
    setSearchQuery(transcript);
    const classification = classifyCitizenIssue(transcript);
    setClassifiedAction(classification);
  };

  const handleExecuteClassification = () => {
    if (classifiedAction) {
      navigation.navigate(classifiedAction.targetScreen, classifiedAction.screenParams);
      setClassifiedAction(null);
      setSearchQuery('');
    }
  };

  const handleClassificationCorrection = async (correctCategory) => {
    await recordClassificationFeedback({
      issueText: searchQuery,
      predictedCategory: classifiedAction?.categoryId,
      correctedCategory: correctCategory.id,
      userId: currentUserId,
    });
    navigation.navigate(correctCategory.targetScreen, {
      ...correctCategory.screenParams,
      initialText: searchQuery,
    });
    setClassifiedAction(null);
    setSearchQuery('');
  };

  const handleCallHelpline = (number) => {
    Linking.openURL(`tel:${number}`);
  };

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        {/* ========================================================= */}
        {/* 1. TOP HEADER & QUICK CONTROLS (LANGUAGE, THEME, PROFILE) */}
        {/* ========================================================= */}
        <View style={styles.topHeader}>
          {/* Identity & Portal Mode Badge */}
          <View style={{ flex: 1 }}>
            <View style={styles.badgeRow}>
              <View style={[styles.govBadge, { backgroundColor: theme.primaryGlow }]}>
                <Text style={[styles.govBadgeText, { color: theme.primaryLight }]}>
                  🇮🇳 {userRole === 'official' ? 'GOVT OFFICER DESK' : t('citizenPortal')}
                </Text>
              </View>
              <View style={styles.livePulseBadge}>
                <View style={styles.liveDot} />
                <Text style={styles.liveText}>LIVE</Text>
              </View>
            </View>
            <Text style={[styles.userNameText, { color: theme.text }]} numberOfLines={1}>
              {userRole === 'official' ? officialProfile.name : userProfile.name}
            </Text>
          </View>

          {/* Quick Actions (Theme Switcher, Officer Portal, Profile/Logout) */}
          <View style={styles.topActionGroup}>
            {/* Theme Toggle Button */}
            <TouchableOpacity
              style={[styles.actionIconBtn, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
              onPress={toggleTheme}
              activeOpacity={0.8}
            >
              <Ionicons
                name={themeMode === 'dark' ? 'sunny' : 'moon'}
                size={16}
                color={themeMode === 'dark' ? '#BF6B3D' : theme.primary}
              />
            </TouchableOpacity>

            {/* Officer Portal Switcher Button */}
            <TouchableOpacity
              style={[
                styles.officerToggleBtn,
                {
                  backgroundColor: userRole === 'official' ? 'rgba(191, 107, 61, 0.15)' : theme.card,
                  borderColor: userRole === 'official' ? '#BF6B3D' : theme.cardBorder,
                },
              ]}
              onPress={() => {
                if (userRole === 'official') {
                  navigation.navigate('OfficialPortal');
                } else {
                  navigation.navigate('Auth');
                }
              }}
              activeOpacity={0.8}
            >
              <Ionicons
                name={userRole === 'official' ? 'speedometer' : 'business'}
                size={14}
                color={userRole === 'official' ? '#BF6B3D' : theme.primary}
              />
              <Text
                style={[
                  styles.officerToggleText,
                  { color: userRole === 'official' ? '#BF6B3D' : theme.text },
                ]}
              >
                {userRole === 'official' ? 'Desk' : 'Official Desk'}
              </Text>
            </TouchableOpacity>

            {/* Notification Bell — real-time push via Supabase Realtime */}
            <TouchableOpacity
              style={[styles.notifBellBtn, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
              onPress={() => setNotifPanelVisible(true)}
              activeOpacity={0.85}
            >
              <Ionicons name="notifications-outline" size={18} color={theme.text} />
              {unreadCount > 0 && (
                <View style={styles.notifBadge}>
                  <Text style={styles.notifBadgeText}>{unreadCount > 9 ? '9+' : unreadCount}</Text>
                </View>
              )}
            </TouchableOpacity>

            {/* Profile Avatar / Logout */}
            <TouchableOpacity
              style={[styles.profileAvatarBtn, { backgroundColor: theme.primary }]}
              onPress={() => navigation.navigate('Settings')}
              activeOpacity={0.85}
            >
              <Text style={styles.avatarInitialText}>
                {userProfile.name ? userProfile.name.trim().charAt(0).toUpperCase() : 'T'}
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Notification Panel */}
        <Modal visible={notifPanelVisible} animationType="slide" transparent onRequestClose={() => setNotifPanelVisible(false)}>
          <View style={styles.notifOverlay}>
            <View style={[styles.notifPanel, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
              <View style={styles.notifPanelHeader}>
                <Text style={[styles.notifPanelTitle, { color: theme.text }]}>Notifications</Text>
                <TouchableOpacity onPress={() => setNotifPanelVisible(false)}>
                  <Ionicons name="close" size={22} color={theme.textMuted} />
                </TouchableOpacity>
              </View>
              <ScrollView style={{ maxHeight: 400 }}>
                {notifications.length === 0 ? (
                  <Text style={[styles.notifEmptyText, { color: theme.textMuted }]}>
                    No notifications yet. You'll be pushed one here the instant an official updates a filing you made.
                  </Text>
                ) : (
                  notifications.map((n) => (
                    <TouchableOpacity
                      key={n.id}
                      style={[styles.notifItem, { borderColor: theme.border, opacity: n.is_read ? 0.6 : 1 }]}
                      onPress={() => handleMarkNotificationRead(n.id)}
                    >
                      <Text style={[styles.notifItemTitle, { color: theme.text }]}>{n.title}</Text>
                      <Text style={[styles.notifItemBody, { color: theme.textSecondary }]}>{n.body}</Text>
                      <Text style={[styles.notifItemTime, { color: theme.textMuted }]}>
                        {new Date(n.created_at).toLocaleString('en-IN')}
                      </Text>
                    </TouchableOpacity>
                  ))
                )}
              </ScrollView>
            </View>
          </View>
        </Modal>

        {/* 1-Tap Horizontal Language Switcher Bar */}
        <View style={styles.quickLangRow}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.langPillsContent}
          >
            {languagesList.map((lang) => {
              const isSelected = language === lang.code;
              return (
                <TouchableOpacity
                  key={lang.code}
                  style={[
                    styles.langPill,
                    isSelected
                      ? [styles.langPillActive, { backgroundColor: theme.primary, borderColor: '#60A5FA' }]
                      : [styles.langPillInactive, { backgroundColor: theme.card, borderColor: theme.cardBorder }],
                  ]}
                  onPress={() => setLanguage(lang.code)}
                  activeOpacity={0.75}
                >
                  <Text
                    style={[
                      styles.langPillText,
                      { color: isSelected ? '#FFFFFF' : theme.textSecondary, fontWeight: isSelected ? '800' : '600' },
                    ]}
                  >
                    {lang.native}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>

        {/* ========================================================= */}
        {/* 2. AI SMART ASSISTANT SEARCH & VOICE BAR */}
        {/* ========================================================= */}
        <View style={[styles.aiSearchCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <View style={[styles.searchInputWrapper, { backgroundColor: theme.surface, borderColor: theme.border }]}>
            <Ionicons name="search" size={16} color={theme.textMuted} style={styles.searchIcon} />
            <TextInput
              style={[styles.searchInput, { color: theme.text }]}
              placeholder={t('searchPlaceholder')}
              placeholderTextColor={theme.textMuted}
              value={searchQuery}
              onChangeText={handleSearchChange}
              returnKeyType="search"
            />
            {searchQuery.length > 0 && (
              <TouchableOpacity onPress={() => handleSearchChange('')} style={styles.clearBtn}>
                <Ionicons name="close-circle" size={16} color={theme.textMuted} />
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={[styles.micBtn, { backgroundColor: theme.primary }]}
              onPress={() => setVoiceModalVisible(true)}
              activeOpacity={0.8}
            >
              <Ionicons name="mic" size={16} color="#FFFFFF" />
            </TouchableOpacity>
          </View>

          {/* AI Action Intent Badge */}
          {classifiedAction && (
            <View>
              <TouchableOpacity
                style={[styles.classificationResult, { backgroundColor: theme.primaryGlow, borderColor: theme.primary }]}
                onPress={handleExecuteClassification}
                activeOpacity={0.85}
              >
                <Text style={styles.classificationIcon}>{classifiedAction.icon}</Text>
                <View style={{ flex: 1, paddingRight: 6 }}>
                  <Text style={[styles.classificationLabel, { color: theme.primaryLight }]}>
                    {classifiedAction.categoryName}
                  </Text>
                  <Text style={[styles.classificationDesc, { color: theme.textSecondary }]} numberOfLines={1}>
                    {classifiedAction.actionText}
                  </Text>
                </View>
                <View style={[styles.actionBadge, { backgroundColor: theme.primary }]}>
                  <Text style={styles.actionBadgeText}>{classifiedAction.actionText}</Text>
                  <Ionicons name="arrow-forward" size={11} color="#FFFFFF" style={{ marginLeft: 3 }} />
                </View>
              </TouchableOpacity>

              {/* Correction control: feeds the real learning loop in aiService.js */}
              <View style={styles.correctionRow}>
                <Text style={[styles.correctionPrompt, { color: theme.textMuted }]}>Not quite right?</Text>
                {CLASSIFICATION_CATEGORIES.filter((c) => c.id !== classifiedAction.categoryId).map((c) => (
                  <TouchableOpacity
                    key={c.id}
                    style={[styles.correctionChip, { borderColor: theme.border }]}
                    onPress={() => handleClassificationCorrection(c)}
                    activeOpacity={0.8}
                  >
                    <Text style={[styles.correctionChipText, { color: theme.textSecondary }]}>{c.icon} {c.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}
        </View>

        {/* ========================================================= */}
        {/* 3. QUICK SERVICES ROW (DIRECTORY, GPS, OCR, VOICE) */}
        {/* ========================================================= */}
        <View style={styles.quickServicesStrip}>
          <TouchableOpacity
            style={[styles.quickServiceItem, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
            onPress={() => navigation.navigate('DepartmentDirectory')}
            activeOpacity={0.8}
          >
            <View style={[styles.quickIconCircle, { backgroundColor: 'rgba(53, 71, 168, 0.15)' }]}>
              <Ionicons name="call" size={18} color="#5568D6" />
            </View>
            <Text style={[styles.quickServiceText, { color: theme.text }]}>Directory</Text>
            <Text style={[styles.quickServiceSub, { color: theme.textMuted }]}>50+ Depts</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.quickServiceItem, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
            onPress={() => navigation.navigate('CivicLocator')}
            activeOpacity={0.8}
          >
            <View style={[styles.quickIconCircle, { backgroundColor: 'rgba(46, 158, 99, 0.15)' }]}>
              <Ionicons name="navigate" size={18} color="#2E9E63" />
            </View>
            <Text style={[styles.quickServiceText, { color: theme.text }]}>GPS Offices</Text>
            <Text style={[styles.quickServiceSub, { color: theme.textMuted }]}>Nearest</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.quickServiceItem, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
            onPress={() => navigation.navigate('DocumentScanner')}
            activeOpacity={0.8}
          >
            <View style={[styles.quickIconCircle, { backgroundColor: 'rgba(59, 143, 168, 0.15)' }]}>
              <Ionicons name="scan" size={18} color="#3B8FA8" />
            </View>
            <Text style={[styles.quickServiceText, { color: theme.text }]}>OCR Scan</Text>
            <Text style={[styles.quickServiceSub, { color: theme.textMuted }]}>Notices/FIR</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.quickServiceItem, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
            onPress={() => navigation.navigate('Chatbot')}
            activeOpacity={0.8}
          >
            <View style={[styles.quickIconCircle, { backgroundColor: 'rgba(191, 107, 61, 0.15)' }]}>
              <Ionicons name="chatbubbles" size={18} color="#BF6B3D" />
            </View>
            <Text style={[styles.quickServiceText, { color: theme.text }]}>Legal Guide</Text>
            <Text style={[styles.quickServiceSub, { color: theme.textMuted }]}>Ask a question</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.quickServiceItem, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
            onPress={() => navigation.navigate('CivicAssistant')}
            activeOpacity={0.8}
          >
            <View style={[styles.quickIconCircle, { backgroundColor: 'rgba(53, 71, 168, 0.15)' }]}>
              <Ionicons name="shield-checkmark" size={18} color="#3547A8" />
            </View>
            <Text style={[styles.quickServiceText, { color: theme.text }]}>Civic Assistant</Text>
            <Text style={[styles.quickServiceSub, { color: theme.textMuted }]}>Spending & records</Text>
          </TouchableOpacity>
        </View>

        {/* ========================================================= */}
        {/* 4. CITY SELECTION CHIPS */}
        {/* ========================================================= */}
        <View style={styles.cityRow}>
          <Text style={[styles.cityLabel, { color: theme.textMuted }]}>
            {t('selectCity')}:
          </Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.cityChipsContent}
          >
            {CITIES.map((c) => {
              const isSelected = c.id === selectedCity;
              const localizedCityName = getCityName(c.id);
              return (
                <HoverChip
                  key={c.id}
                  isSelected={isSelected}
                  activeColor={theme.primary}
                  onPress={() => setCity(c.id)}
                >
                  <Text
                    style={[
                      styles.cityChipText,
                      { color: isSelected ? '#FFFFFF' : theme.textSecondary, fontWeight: isSelected ? '700' : '500' },
                    ]}
                  >
                    {localizedCityName}
                  </Text>
                </HoverChip>
              );
            })}
          </ScrollView>
        </View>

        {/* ========================================================= */}
        {/* 5. 6 CORE PILLARS GRID (CLEAN & VISUAL) */}
        {/* ========================================================= */}
        <View style={styles.gridSection}>
          {/* Row 1: File Grievance & RTI */}
          <View style={styles.cardRow}>
            <HoverCard
              style={styles.halfCard}
              cardColor={theme.card}
              borderColor={theme.cardBorder}
              hoverBorderColor={theme.primary}
              onPress={() => navigation.navigate('Complaint', { tab: 'civic' })}
            >
              <View style={[styles.cardIconCircle, { backgroundColor: 'rgba(53, 71, 168, 0.15)' }]}>
                <Ionicons name="document-text" size={22} color="#5568D6" />
              </View>
              <Text style={[styles.cardTitle, { color: theme.text }]}>
                {t('fileComplaint')}
              </Text>
              <Text style={[styles.cardSub, { color: theme.textSecondary }]} numberOfLines={2}>
                AI legal complaint letter to authorities & commissioners
              </Text>
              <View style={[styles.miniTag, { backgroundColor: theme.primaryGlow }]}>
                <Text style={[styles.miniTagText, { color: theme.primaryLight }]}>Statutory Letter</Text>
              </View>
            </HoverCard>

            <HoverCard
              style={styles.halfCard}
              cardColor={theme.card}
              borderColor={theme.cardBorder}
              hoverBorderColor="#BF6B3D"
              onPress={() => navigation.navigate('Complaint', { tab: 'rti' })}
            >
              <View style={[styles.cardIconCircle, { backgroundColor: 'rgba(191, 107, 61, 0.15)' }]}>
                <Ionicons name="business" size={22} color="#BF6B3D" />
              </View>
              <Text style={[styles.cardTitle, { color: theme.text }]}>
                {t('fileRTI')}
              </Text>
              <Text style={[styles.cardSub, { color: theme.textSecondary }]} numberOfLines={2}>
                Section 6(1) & 7(1) application with precision questionnaires
              </Text>
              <View style={[styles.miniTag, { backgroundColor: 'rgba(191, 107, 61, 0.12)' }]}>
                <Text style={[styles.miniTagText, { color: '#BF6B3D' }]}>RTI Act 2005</Text>
              </View>
            </HoverCard>
          </View>

          {/* Row 2: Interoperability Layer & Fragmentation Diagnostic — the
              actual flagship features answering the problem statement */}
          <View style={styles.cardRow}>
            <HoverCard
              style={styles.halfCard}
              cardColor={theme.card}
              borderColor={theme.cardBorder}
              hoverBorderColor={theme.primary}
              onPress={() => navigation.navigate('Interoperability')}
            >
              <View style={[styles.cardIconCircle, { backgroundColor: theme.primaryGlow }]}>
                <Ionicons name="git-network" size={22} color={theme.primaryLight} />
              </View>
              <Text style={[styles.cardTitle, { color: theme.text }]}>
                Interoperability Layer
              </Text>
              <Text style={[styles.cardSub, { color: theme.textSecondary }]} numberOfLines={2}>
                Live: 4 department data formats normalized into one schema
              </Text>
              <View style={[styles.miniTag, { backgroundColor: theme.primaryGlow }]}>
                <Text style={[styles.miniTagText, { color: theme.primaryLight }]}>System Integration</Text>
              </View>
            </HoverCard>

            <HoverCard
              style={styles.halfCard}
              cardColor={theme.card}
              borderColor={theme.cardBorder}
              hoverBorderColor="#2E9E63"
              onPress={() => navigation.navigate('Fragmentation')}
            >
              <View style={[styles.cardIconCircle, { backgroundColor: 'rgba(46, 158, 99, 0.15)' }]}>
                <Ionicons name="stats-chart" size={22} color="#2E9E63" />
              </View>
              <Text style={[styles.cardTitle, { color: theme.text }]}>
                Fragmentation Diagnostic
              </Text>
              <Text style={[styles.cardSub, { color: theme.textSecondary }]} numberOfLines={2}>
                Quantify service fragmentation — national data + your own
              </Text>
              <View style={[styles.miniTag, { backgroundColor: 'rgba(46, 158, 99, 0.12)' }]}>
                <Text style={[styles.miniTagText, { color: '#2E9E63' }]}>Data-Backed</Text>
              </View>
            </HoverCard>
          </View>

          {/* Row 3: Tracking & Government Official Portal */}
          <View style={styles.cardRow}>
            <HoverCard
              style={styles.halfCard}
              cardColor={theme.card}
              borderColor={theme.cardBorder}
              hoverBorderColor="#EC4899"
              onPress={() => navigation.navigate('Tracker')}
            >
              <View style={[styles.cardIconCircle, { backgroundColor: 'rgba(236, 72, 153, 0.15)' }]}>
                <Ionicons name="analytics" size={22} color="#EC4899" />
              </View>
              <Text style={[styles.cardTitle, { color: theme.text }]}>
                {t('trackGrievance')}
              </Text>
              <Text style={[styles.cardSub, { color: theme.textSecondary }]} numberOfLines={2}>
                One window: CivicLens filings + other portals, in one place
              </Text>
              <View style={[styles.miniTag, { backgroundColor: 'rgba(236, 72, 153, 0.12)' }]}>
                <Text style={[styles.miniTagText, { color: '#EC4899' }]}>Unified Tracker</Text>
              </View>
            </HoverCard>

            <HoverCard
              style={styles.halfCard}
              cardColor={theme.card}
              borderColor="#BF6B3D"
              hoverBorderColor="#BF6B3D"
              onPress={() => {
                if (userRole === 'official') {
                  navigation.navigate('OfficialPortal');
                } else {
                  navigation.navigate('Auth');
                }
              }}
            >
              <View style={[styles.cardIconCircle, { backgroundColor: 'rgba(191, 107, 61, 0.15)' }]}>
                <Ionicons name="speedometer" size={22} color="#BF6B3D" />
              </View>
              <Text style={[styles.cardTitle, { color: theme.text }]}>
                Officer Desk
              </Text>
              <Text style={[styles.cardSub, { color: theme.textSecondary }]} numberOfLines={2}>
                Department resolution queue, SLA scorecard & ATR uploads
              </Text>
              <View style={[styles.miniTag, { backgroundColor: 'rgba(191, 107, 61, 0.15)' }]}>
                <Text style={[styles.miniTagText, { color: '#BF6B3D' }]}>Govt Portal</Text>
              </View>
            </HoverCard>
          </View>

          {/* Row 4: Legal Resources (secondary — different problem than
              interoperability, kept since the work is genuinely useful) */}
          <Text style={[styles.sectionLabel, { color: theme.textMuted }]}>LEGAL RESOURCES</Text>
          <View style={styles.cardRow}>
            <HoverCard
              style={styles.halfCard}
              cardColor={theme.card}
              borderColor={theme.cardBorder}
              hoverBorderColor="#7A5FB0"
              onPress={() => navigation.navigate('CaseAI')}
            >
              <View style={[styles.cardIconCircle, { backgroundColor: 'rgba(122, 95, 176, 0.15)' }]}>
                <Ionicons name="scale" size={22} color="#7A5FB0" />
              </View>
              <Text style={[styles.cardTitle, { color: theme.text }]}>
                {t('analyzeCase')}
              </Text>
              <Text style={[styles.cardSub, { color: theme.textSecondary }]} numberOfLines={2}>
                Judicial outcome patterns & 31 curated court precedents
              </Text>
              <View style={[styles.miniTag, { backgroundColor: 'rgba(122, 95, 176, 0.12)' }]}>
                <Text style={[styles.miniTagText, { color: '#7A5FB0' }]}>Precedents</Text>
              </View>
            </HoverCard>

            <HoverCard
              style={styles.halfCard}
              cardColor={theme.card}
              borderColor={theme.cardBorder}
              hoverBorderColor="#2E9E63"
              onPress={() => navigation.navigate('Heatmap')}
            >
              <View style={[styles.cardIconCircle, { backgroundColor: 'rgba(46, 158, 99, 0.15)' }]}>
                <Ionicons name="map" size={22} color="#2E9E63" />
              </View>
              <Text style={[styles.cardTitle, { color: theme.text }]}>
                {t('communityHeatmap')}
              </Text>
              <Text style={[styles.cardSub, { color: theme.textSecondary }]} numberOfLines={2}>
                Real report density from complaints citizens actually filed
              </Text>
              <View style={[styles.miniTag, { backgroundColor: 'rgba(46, 158, 99, 0.12)' }]}>
                <Text style={[styles.miniTagText, { color: '#2E9E63' }]}>Real Data</Text>
              </View>
            </HoverCard>
          </View>
        </View>

        {/* ========================================================= */}
        {/* 6. LIVE CITY CIVIC PULSE METRICS — built from real filed complaints */}
        {/* ========================================================= */}
        <View style={[styles.metricsCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <View style={styles.metricsHeader}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Ionicons name="stats-chart" size={16} color={theme.accentEmerald} />
              <Text style={[styles.metricsHeading, { color: theme.text }]}>
                {getCityName(selectedCity)} Civic Pulse
              </Text>
            </View>
            <View style={[styles.cityBadge, { backgroundColor: theme.primaryGlow }]}>
              <Text style={[styles.cityBadgeText, { color: theme.primaryLight }]}>
                {cityPulseLoading ? '...' : cityPulse?.hasData ? `${cityPulse.totalReported} Reports` : 'No data yet'}
              </Text>
            </View>
          </View>

          {cityPulseLoading ? (
            <View style={{ paddingVertical: 16, alignItems: 'center' }}>
              <ActivityIndicator color={theme.primary} size="small" />
            </View>
          ) : !cityPulse?.hasData ? (
            <View style={{ paddingVertical: 10 }}>
              <Text style={[styles.metricLabel, { color: theme.textMuted, textAlign: 'center' }]}>
                No complaints filed yet in this city. Be the first to report an issue and this dashboard will reflect it in real time.
              </Text>
            </View>
          ) : (
            <View style={styles.metricGrid}>
              <View style={[styles.metricBox, { backgroundColor: theme.surface }]}>
                <Text style={[styles.metricValue, { color: theme.accentEmerald }]}>
                  {cityPulse.resolutionRate}
                </Text>
                <Text style={[styles.metricLabel, { color: theme.textMuted }]}>
                  {t('complaintsResolved')}
                </Text>
              </View>

              <View style={[styles.metricBox, { backgroundColor: theme.surface }]}>
                <Text style={[styles.metricValue, { color: theme.accentRose }]}>
                  {cityPulse.activeHotspotsCount}
                </Text>
                <Text style={[styles.metricLabel, { color: theme.textMuted }]}>
                  {t('activeHotspots')}
                </Text>
              </View>

              <View style={[styles.metricBox, { backgroundColor: theme.surface }]}>
                <Text style={[styles.metricValue, { color: theme.accentAmber }]}>
                  {cityPulse.avgResponseDays ? `${cityPulse.avgResponseDays}d` : '—'}
                </Text>
                <Text style={[styles.metricLabel, { color: theme.textMuted }]}>
                  {t('avgResponseDays')}
                </Text>
              </View>
            </View>
          )}
        </View>

        {/* ========================================================= */}
        {/* 7. EMERGENCY HELPLINES BAR */}
        {/* ========================================================= */}
        <View style={styles.helplineSection}>
          <View style={styles.sectionHeaderRow}>
            <Text style={[styles.sectionHeading, { color: theme.text }]}>
              🚨 {t('emergencyHelplines')}
            </Text>
            <TouchableOpacity onPress={() => navigation.navigate('DepartmentDirectory')}>
              <Text style={[styles.viewAllText, { color: theme.primaryLight }]}>All 50+ Depts →</Text>
            </TouchableOpacity>
          </View>

          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.helplineScroll}>
            {NATIONAL_HELPLINES.map((h) => {
              const info = getHelplineInfo(h.id);
              return (
                <TouchableOpacity
                  key={h.id}
                  style={[styles.helplineCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
                  onPress={() => handleCallHelpline(h.number)}
                  activeOpacity={0.8}
                >
                  <Text style={styles.helplineIcon}>{h.icon}</Text>
                  <Text style={[styles.helplineName, { color: theme.text }]} numberOfLines={1}>
                    {info.name || h.name}
                  </Text>
                  <View style={[styles.callPill, { backgroundColor: theme.primaryGlow }]}>
                    <Ionicons name="call" size={11} color={theme.primaryLight} />
                    <Text style={[styles.callNumber, { color: theme.primaryLight }]}>{h.number}</Text>
                  </View>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>

        {/* ========================================================= */}
        {/* 8. DAILY LEGAL RIGHT / RTI TIP */}
        {/* ========================================================= */}
        <View style={[styles.tipCard, { backgroundColor: theme.primaryGlow, borderColor: theme.primary }]}>
          <View style={styles.tipHeader}>
            <Ionicons name="bulb" size={18} color={theme.accentSaffron} />
            <Text style={[styles.tipTag, { color: theme.accentSaffron }]}>
              {t('dailyLegalTip')}
            </Text>
          </View>
          <Text style={[styles.tipTitleText, { color: theme.text }]}>
            {t('tipTitle')}
          </Text>
          <Text style={[styles.tipDescText, { color: theme.textSecondary }]}>
            {t('tipText')}
          </Text>
        </View>
      </ScrollView>

      {/* Multilingual Voice Listening Hub Modal */}
      <VoiceListeningModal
        visible={voiceModalVisible}
        onClose={() => setVoiceModalVisible(false)}
        onSpeechResult={handleVoiceSearchResult}
        language={language}
        title="Civic Voice AI Search"
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: SPACING.md,
    paddingTop: SPACING.sm,
    paddingBottom: 100,
  },

  // 1. Top Header
  topHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: SPACING.xs,
  },
  badgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 2,
  },
  govBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: RADIUS.full,
  },
  govBadgeText: {
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.3,
  },
  livePulseBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  liveDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#2E9E63',
  },
  liveText: {
    fontSize: 9,
    color: '#2E9E63',
    fontWeight: '800',
  },
  userNameText: {
    fontFamily: FONT_FAMILY.displayBold,
    fontSize: FONT_SIZE.lg,
    letterSpacing: -0.3,
  },
  topActionGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  actionIconBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
  },
  officerToggleBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 9,
    borderRadius: RADIUS.full,
    borderWidth: 1,
    gap: 4,
  },
  officerToggleText: {
    fontSize: 10,
    fontWeight: '800',
  },
  profileAvatarBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  notifBellBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    marginRight: 8,
  },
  notifBadge: {
    position: 'absolute',
    top: -2,
    right: -2,
    backgroundColor: '#C24545',
    borderRadius: 8,
    minWidth: 16,
    height: 16,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 3,
  },
  notifBadgeText: { color: '#FFFFFF', fontSize: 9, fontWeight: '800' },
  notifOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  notifPanel: { borderTopLeftRadius: RADIUS.xl, borderTopRightRadius: RADIUS.xl, borderWidth: 1, padding: SPACING.md, maxHeight: '75%' },
  notifPanelHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  notifPanelTitle: { fontSize: 16, fontWeight: '800' },
  notifEmptyText: { fontSize: 12, lineHeight: 18, paddingVertical: 20, textAlign: 'center' },
  notifItem: { borderTopWidth: 1, paddingVertical: 10 },
  notifItemTitle: { fontSize: 13, fontWeight: '700' },
  notifItemBody: { fontSize: 11.5, marginTop: 2 },
  notifItemTime: { fontSize: 9.5, marginTop: 4 },
  avatarInitialText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '900',
  },

  // Quick Language Row
  quickLangRow: {
    marginBottom: SPACING.sm,
  },
  langPillsContent: {
    gap: 6,
    paddingVertical: 4,
  },
  langPill: {
    paddingVertical: 4,
    paddingHorizontal: 11,
    borderRadius: RADIUS.full,
    borderWidth: 1,
  },
  langPillActive: {},
  langPillInactive: {},
  langPillText: {
    fontSize: 11,
  },

  // 2. AI Search Bar
  aiSearchCard: {
    borderRadius: RADIUS.xl,
    padding: SPACING.sm,
    marginBottom: SPACING.md,
    borderWidth: 1,
  },
  searchInputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: RADIUS.lg,
    borderWidth: 1,
    paddingHorizontal: SPACING.sm,
    height: 44,
  },
  searchIcon: {
    marginRight: 6,
  },
  searchInput: {
    flex: 1,
    fontSize: FONT_SIZE.xs,
    height: '100%',
  },
  clearBtn: {
    padding: 4,
    marginRight: 2,
  },
  micBtn: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  classificationResult: {
    marginTop: 8,
    padding: 8,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
  },
  correctionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 6,
    marginTop: 6,
    paddingHorizontal: 2,
  },
  correctionPrompt: {
    fontSize: 10.5,
    marginRight: 2,
  },
  correctionChip: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: RADIUS.full,
    borderWidth: 1,
  },
  correctionChipText: {
    fontSize: 10,
    fontWeight: '600',
  },
  classificationIcon: {
    fontSize: 18,
    marginRight: 6,
  },
  classificationLabel: {
    fontSize: 11,
    fontWeight: '800',
  },
  classificationDesc: {
    fontSize: 10,
  },
  actionBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: RADIUS.full,
  },
  actionBadgeText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '700',
  },

  // 3. Quick Services Row
  quickServicesStrip: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: SPACING.md,
  },
  quickServiceItem: {
    flex: 1,
    borderRadius: RADIUS.lg,
    paddingVertical: 10,
    paddingHorizontal: 6,
    alignItems: 'center',
    borderWidth: 1,
  },
  quickIconCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
  },
  quickServiceText: {
    fontSize: 11,
    fontWeight: '800',
  },
  quickServiceSub: {
    fontSize: 9,
    marginTop: 1,
  },

  // 4. City Selector Row
  cityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: SPACING.md,
    gap: 6,
  },
  cityLabel: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  cityChipsContent: {
    gap: 6,
  },
  cityChipText: {
    fontSize: 11,
  },

  // 5. Grid Section
  gridSection: {
    marginBottom: SPACING.md,
  },
  cardRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 10,
  },
  sectionLabel: {
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.8,
    marginBottom: 8,
    marginTop: 4,
  },
  halfCard: {
    flex: 1,
    borderRadius: RADIUS.xl,
    padding: SPACING.sm,
    borderWidth: 1,
  },
  cardIconCircle: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 6,
  },
  cardTitle: {
    fontSize: FONT_SIZE.xs,
    fontWeight: '800',
    marginBottom: 2,
    lineHeight: 16,
  },
  cardSub: {
    fontSize: 10,
    lineHeight: 14,
    marginBottom: 6,
  },
  miniTag: {
    alignSelf: 'flex-start',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  miniTagText: {
    fontSize: 9,
    fontWeight: '700',
  },

  // 6. Metrics
  metricsCard: {
    borderRadius: RADIUS.xl,
    padding: SPACING.sm,
    marginBottom: SPACING.md,
    borderWidth: 1,
  },
  metricsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  metricsHeading: {
    fontSize: 12,
    fontWeight: '700',
  },
  cityBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: RADIUS.full,
  },
  cityBadgeText: {
    fontSize: 10,
    fontWeight: '700',
  },
  metricGrid: {
    flexDirection: 'row',
    gap: 6,
  },
  metricBox: {
    flex: 1,
    borderRadius: RADIUS.md,
    padding: 6,
    alignItems: 'center',
  },
  metricValue: {
    fontSize: FONT_SIZE.md,
    fontWeight: '900',
    marginBottom: 1,
  },
  metricLabel: {
    fontSize: 9,
    fontWeight: '600',
    textAlign: 'center',
  },

  // 7. Helplines
  helplineSection: {
    marginBottom: SPACING.md,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  sectionHeading: {
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  viewAllText: {
    fontSize: 11,
    fontWeight: '700',
  },
  helplineScroll: {
    flexDirection: 'row',
  },
  helplineCard: {
    width: 120,
    borderRadius: RADIUS.lg,
    padding: 8,
    marginRight: 8,
    borderWidth: 1,
    alignItems: 'center',
  },
  helplineIcon: {
    fontSize: 20,
    marginBottom: 2,
  },
  helplineName: {
    fontSize: 10,
    fontWeight: '700',
    textAlign: 'center',
    marginBottom: 4,
  },
  callPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: RADIUS.full,
  },
  callNumber: {
    fontSize: 10,
    fontWeight: '800',
  },

  // 8. Tip Card
  tipCard: {
    borderRadius: RADIUS.lg,
    padding: SPACING.sm,
    borderWidth: 1,
    marginBottom: SPACING.sm,
  },
  tipHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 2,
  },
  tipTag: {
    fontSize: 10,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  tipTitleText: {
    fontSize: 12,
    fontWeight: '800',
    marginBottom: 2,
  },
  tipDescText: {
    fontSize: 11,
    lineHeight: 15,
  },
});
