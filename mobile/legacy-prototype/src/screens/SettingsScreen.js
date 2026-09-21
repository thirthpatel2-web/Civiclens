// CivicLens - Settings, Citizen Profile & App Preferences Screen

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  SafeAreaView,
  Modal,
  Alert,
  Platform,
  Image,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE } from '../constants/theme';
import { getCitizenGuides, getFaqs } from '../data/guideData';
import { setupMfa, enableMfa } from '../services/authService';

export default function SettingsScreen({ navigation }) {
  const {
    theme,
    themeMode,
    toggleTheme,
    language,
    setLanguage,
    languagesList,
    t,
    userProfile,
    updateUserProfile,
    userRole,
    officialProfile,
    logout,
  } = useApp();

  // Profile Form State
  const [name, setName] = useState(userProfile.name);
  const [phone, setPhone] = useState(userProfile.phone);
  const [email, setEmail] = useState(userProfile.email);
  const [address, setAddress] = useState(userProfile.address);
  const [pincode, setPincode] = useState(userProfile.pincode);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // ---- MFA (TOTP) setup state ----------------------------------------
  // Calls the existing backend at /auth/mfa/setup and /auth/mfa/enable via
  // authService — no duplicate API client. The secret is shown only as a
  // manual-entry fallback for users whose authenticator app can't scan.
  const [mfaModalVisible, setMfaModalVisible] = useState(false);
  const [mfaQrUrl, setMfaQrUrl] = useState(null);
  const [mfaSecret, setMfaSecret] = useState(null);
  const [mfaCode, setMfaCode] = useState('');
  const [mfaLoading, setMfaLoading] = useState(false);
  const [mfaError, setMfaError] = useState(null);
  const [mfaEnabled, setMfaEnabled] = useState(Boolean(userProfile?.mfaEnabled));

  const handleStartMfaSetup = async () => {
    setMfaLoading(true);
    setMfaError(null);
    setMfaModalVisible(true);
    const { qrCodeDataUrl, secret, error } = await setupMfa();
    setMfaLoading(false);
    if (error) {
      setMfaError(error);
      return;
    }
    setMfaQrUrl(qrCodeDataUrl);
    setMfaSecret(secret);
  };

  const handleConfirmMfa = async () => {
    if (!mfaCode || mfaCode.trim().length < 6) {
      setMfaError('Enter the 6-digit code from your authenticator app.');
      return;
    }
    setMfaLoading(true);
    setMfaError(null);
    const { error } = await enableMfa(mfaCode.trim());
    setMfaLoading(false);
    if (error) {
      setMfaError(error);
      return;
    }
    setMfaEnabled(true);
    setMfaModalVisible(false);
    setMfaCode('');
    setMfaQrUrl(null);
    setMfaSecret(null);
    Alert.alert('Two-factor authentication enabled', 'You will be asked for a code from your authenticator app each time you sign in.');
  };


  // Guide Modal State
  const [showHandbookModal, setShowHandbookModal] = useState(false);

  const handleSaveProfile = async () => {
    await updateUserProfile({
      name,
      phone,
      email,
      address,
      pincode,
    });
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 3000);
  };

  const handleLogout = async () => {
    Alert.alert(
      'Sign Out / Reset Session',
      'Are you sure you want to sign out of your current session?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Sign Out',
          style: 'destructive',
          onPress: async () => {
            await logout();
            Alert.alert('Signed Out', 'Session reset to default citizen mode.');
            navigation.navigate('Main');
          },
        },
      ]
    );
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
            ⚙️ {t('settingsTitle')}
          </Text>
          <Text style={[styles.screenSubtitle, { color: theme.textSecondary }]}>
            Customize language, theme mode, and citizen verification profile
          </Text>
        </View>

        {/* ========================================================= */}
        {/* 1. GOVERNMENT OFFICER PORTAL ACCESS CARD */}
        {/* ========================================================= */}
        <View style={[styles.officialCard, { backgroundColor: theme.card, borderColor: '#BF6B3D' }]}>
          <View style={styles.cardHeaderRow}>
            <Ionicons name="business" size={22} color="#BF6B3D" />
            <Text style={[styles.cardHeaderTitle, { color: theme.text }]}>
              {t('officialDesk')} (All-India Departments)
            </Text>
          </View>
          <Text style={[styles.cardHeaderSub, { color: theme.textSecondary }]}>
            {userRole === 'official'
              ? `Currently logged in as: ${officialProfile.name} (${officialProfile.designation})`
              : 'Dedicated resolution queue, SLA scorecards, and Action Taken Reports (ATRs) for BBMP, BESCOM, Police, PWD, and Central Ministries.'}
          </Text>

          <TouchableOpacity
            style={[styles.officialBtn, { backgroundColor: '#BF6B3D' }]}
            onPress={() => {
              if (userRole === 'official') {
                navigation.navigate('OfficialPortal');
              } else {
                navigation.navigate('Auth');
              }
            }}
            activeOpacity={0.85}
          >
            <Ionicons
              name={userRole === 'official' ? 'speedometer' : 'shield-checkmark'}
              size={18}
              color="#FFFFFF"
            />
            <Text style={styles.officialBtnText}>
              {userRole === 'official' ? 'Open Official Dashboard →' : 'Government Officer Login / Switch Role →'}
            </Text>
          </TouchableOpacity>
        </View>

        {/* ========================================================= */}
        {/* 2. CITIZEN PROFILE DETAILS CARD (For Form Pre-filling) */}
        {/* ========================================================= */}
        <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <View style={styles.cardHeaderRow}>
            <Ionicons name="person-circle" size={22} color={theme.primary} />
            <Text style={[styles.cardHeaderTitle, { color: theme.text }]}>
              {t('profileSection')}
            </Text>
          </View>
          <Text style={[styles.cardHeaderSub, { color: theme.textMuted }]}>
            These verified details are automatically formatted into your formal complaints & RTI applications.
          </Text>

          {/* Form Fields */}
          <View style={styles.fieldGroup}>
            <Text style={[styles.fieldLabel, { color: theme.textSecondary }]}>{t('fullName')}</Text>
            <TextInput
              style={[styles.fieldInput, { backgroundColor: theme.inputBg, color: theme.text, borderColor: theme.border }]}
              value={name}
              onChangeText={setName}
              placeholder="e.g. your full name"
              placeholderTextColor={theme.textMuted}
            />
          </View>

          <View style={styles.formRow}>
            <View style={[styles.fieldGroup, { flex: 1 }]}>
              <Text style={[styles.fieldLabel, { color: theme.textSecondary }]}>{t('phoneNumber')}</Text>
              <TextInput
                style={[styles.fieldInput, { backgroundColor: theme.inputBg, color: theme.text, borderColor: theme.border }]}
                value={phone}
                onChangeText={setPhone}
                placeholder="+91 98765 XXXXX"
                placeholderTextColor={theme.textMuted}
                keyboardType="phone-pad"
              />
            </View>
            <View style={[styles.fieldGroup, { flex: 1 }]}>
              <Text style={[styles.fieldLabel, { color: theme.textSecondary }]}>{t('pincode')}</Text>
              <TextInput
                style={[styles.fieldInput, { backgroundColor: theme.inputBg, color: theme.text, borderColor: theme.border }]}
                value={pincode}
                onChangeText={setPincode}
                placeholder="560102"
                placeholderTextColor={theme.textMuted}
                keyboardType="numeric"
              />
            </View>
          </View>

          <View style={styles.fieldGroup}>
            <Text style={[styles.fieldLabel, { color: theme.textSecondary }]}>{t('emailAddress')}</Text>
            <TextInput
              style={[styles.fieldInput, { backgroundColor: theme.inputBg, color: theme.text, borderColor: theme.border }]}
              value={email}
              onChangeText={setEmail}
              placeholder="citizen@email.com"
              placeholderTextColor={theme.textMuted}
              keyboardType="email-address"
            />
          </View>

          <View style={styles.fieldGroup}>
            <Text style={[styles.fieldLabel, { color: theme.textSecondary }]}>{t('residentialAddress')}</Text>
            <TextInput
              style={[styles.fieldInput, { backgroundColor: theme.inputBg, color: theme.text, borderColor: theme.border, minHeight: 60 }]}
              value={address}
              onChangeText={setAddress}
              placeholder="House/Flat No., Street, Ward, Area"
              placeholderTextColor={theme.textMuted}
              multiline
            />
          </View>

          <TouchableOpacity
            style={[styles.saveProfileBtn, { backgroundColor: theme.primary }]}
            onPress={handleSaveProfile}
            activeOpacity={0.85}
          >
            <Ionicons name="save-outline" size={16} color="#FFFFFF" />
            <Text style={styles.saveProfileBtnText}>{t('saveProfileBtn')}</Text>
          </TouchableOpacity>

          {saveSuccess && (
            <View style={[styles.successBanner, { backgroundColor: 'rgba(46, 158, 99, 0.15)' }]}>
              <Ionicons name="checkmark-circle" size={16} color={theme.accentEmerald} />
              <Text style={[styles.successText, { color: theme.accentEmerald }]}>
                Profile saved and ready for letter pre-filling!
              </Text>
            </View>
          )}
        </View>

        {/* ========================================================= */}
        {/* 3. APP PREFERENCES (Language & Theme) */}
        {/* ========================================================= */}
        <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <View style={styles.cardHeaderRow}>
            <Ionicons name="color-palette-outline" size={22} color={theme.accentSaffron} />
            <Text style={[styles.cardHeaderTitle, { color: theme.text }]}>
              {t('appPreferences')}
            </Text>
          </View>

          {/* Theme Mode Switcher */}
          <View style={styles.preferenceRow}>
            <View>
              <Text style={[styles.prefTitle, { color: theme.text }]}>{t('themeMode')}</Text>
              <Text style={[styles.prefSub, { color: theme.textMuted }]}>
                Current: {themeMode === 'dark' ? '🌙 Dark Mode' : '☀️ Light Mode'}
              </Text>
            </View>
            <TouchableOpacity
              style={[styles.toggleThemeBtn, { backgroundColor: theme.surface, borderColor: theme.border }]}
              onPress={toggleTheme}
              activeOpacity={0.8}
            >
              <Ionicons
                name={themeMode === 'dark' ? 'sunny' : 'moon'}
                size={18}
                color={themeMode === 'dark' ? '#BF6B3D' : theme.primary}
              />
              <Text style={[styles.toggleThemeText, { color: theme.text }]}>
                Switch to {themeMode === 'dark' ? 'Light' : 'Dark'}
              </Text>
            </TouchableOpacity>
          </View>

          {/* Language Switcher Grid */}
          <Text style={[styles.prefTitle, { color: theme.text, marginTop: 16, marginBottom: 10 }]}>
            {t('appLanguage')} (7 Indian Languages)
          </Text>
          <View style={styles.languageGrid}>
            {languagesList.map((lang) => {
              const isSelected = language === lang.code;
              return (
                <TouchableOpacity
                  key={lang.code}
                  style={[
                    styles.langCard,
                    isSelected
                      ? [styles.langCardSelected, { backgroundColor: '#3547A8', borderColor: '#60A5FA' }]
                      : [
                          styles.langCardUnselected,
                          {
                            backgroundColor: themeMode === 'dark' ? '#1E293B' : '#FFFFFF',
                            borderColor: themeMode === 'dark' ? '#334155' : '#CBD5E1',
                          },
                        ],
                  ]}
                  onPress={() => setLanguage(lang.code)}
                  activeOpacity={0.8}
                >
                  <View style={styles.langHeaderRow}>
                    <View
                      style={[
                        styles.scriptBadge,
                        {
                          backgroundColor: isSelected
                            ? 'rgba(255, 255, 255, 0.22)'
                            : themeMode === 'dark'
                            ? '#0F172A'
                            : '#F1F5F9',
                        },
                      ]}
                    >
                      <Text
                        style={[
                          styles.scriptBadgeText,
                          {
                            color: isSelected
                              ? '#FFFFFF'
                              : themeMode === 'dark'
                              ? '#94A3B8'
                              : '#475569',
                          },
                        ]}
                      >
                        {lang.scriptIcon || 'Aa'}
                      </Text>
                    </View>
                    {isSelected ? (
                      <View style={styles.checkCircle}>
                        <Ionicons name="checkmark" size={10} color="#FFFFFF" />
                      </View>
                    ) : (
                      <View style={[styles.uncheckCircle, { borderColor: themeMode === 'dark' ? '#475569' : '#CBD5E1' }]} />
                    )}
                  </View>

                  <Text
                    style={[
                      styles.langNative,
                      {
                        color: isSelected
                          ? '#FFFFFF'
                          : themeMode === 'dark'
                          ? '#F8FAFC'
                          : '#0F172A',
                        fontWeight: isSelected ? '800' : '700',
                      },
                    ]}
                  >
                    {lang.native}
                  </Text>
                  <Text
                    style={[
                      styles.langEnglish,
                      {
                        color: isSelected
                          ? '#DBEAFE'
                          : themeMode === 'dark'
                          ? '#94A3B8'
                          : '#64748B',
                        fontWeight: isSelected ? '600' : '500',
                      },
                    ]}
                  >
                    {lang.name}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* ========================================================= */}
        {/* 4. HELP HANDBOOK & CITIZEN RIGHTS */}
        {/* ========================================================= */}
        <TouchableOpacity
          style={[styles.helpCard, { backgroundColor: theme.card, borderColor: theme.accentEmerald }]}
          onPress={() => setShowHandbookModal(true)}
          activeOpacity={0.85}
        >
          <View style={styles.helpLeft}>
            <View style={[styles.helpIconCircle, { backgroundColor: 'rgba(46, 158, 99, 0.15)' }]}>
              <Ionicons name="book" size={22} color={theme.accentEmerald} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.helpTitle, { color: theme.text }]}>
                {t('helpHandbook')}
              </Text>
              <Text style={[styles.helpSub, { color: theme.textSecondary }]}>
                RTI 2005, Zero FIR, E-Daakhil, BBMP & Escalation
              </Text>
            </View>
          </View>
          <Ionicons name="chevron-forward" size={20} color={theme.accentEmerald} />
        </TouchableOpacity>

        {/* ========================================================= */}
        {/* 4b. DATA & PRIVACY — Consent Grants + Golden Record Linking */}
        {/* ========================================================= */}
        <TouchableOpacity
          style={[styles.helpCard, { backgroundColor: theme.card, borderColor: theme.primary }]}
          onPress={() => navigation.navigate('DataPrivacy')}
          activeOpacity={0.85}
        >
          <View style={styles.helpLeft}>
            <View style={[styles.helpIconCircle, { backgroundColor: theme.primaryGlow }]}>
              <Ionicons name="shield-checkmark" size={22} color={theme.primaryLight} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.helpTitle, { color: theme.text }]}>
                Data & Privacy
              </Text>
              <Text style={[styles.helpSub, { color: theme.textSecondary }]}>
                Manage consent grants, linked government IDs & your activity log
              </Text>
            </View>
          </View>
          <Ionicons name="chevron-forward" size={20} color={theme.primaryLight} />
        </TouchableOpacity>

        {/* ========================================================= */}
        {/* 4b. ACCOUNT SECURITY / MFA */}
        {/* ========================================================= */}
        <TouchableOpacity
          style={[styles.helpCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
          onPress={mfaEnabled ? undefined : handleStartMfaSetup}
          activeOpacity={mfaEnabled ? 1 : 0.85}
        >
          <View style={styles.helpLeft}>
            <View style={[styles.helpIconCircle, { backgroundColor: mfaEnabled ? 'rgba(46,158,99,0.15)' : theme.primaryGlow }]}>
              <Ionicons
                name={mfaEnabled ? 'lock-closed' : 'lock-open-outline'}
                size={22}
                color={mfaEnabled ? '#2E9E63' : theme.primaryLight}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.helpTitle, { color: theme.text }]}>
                Two-Factor Authentication
              </Text>
              <Text style={[styles.helpSub, { color: theme.textSecondary }]}>
                {mfaEnabled
                  ? 'Enabled — a code from your authenticator app is required at sign-in'
                  : 'Add a second step at sign-in using an authenticator app'}
              </Text>
            </View>
          </View>
          {mfaEnabled ? (
            <Ionicons name="checkmark-circle" size={20} color="#2E9E63" />
          ) : (
            <Ionicons name="chevron-forward" size={20} color={theme.primaryLight} />
          )}
        </TouchableOpacity>

        {/* ========================================================= */}
        {/* 5. RESET / LOGOUT SECTION */}
        {/* ========================================================= */}
        <TouchableOpacity
          style={[styles.logoutBtn, { borderColor: theme.border }]}
          onPress={handleLogout}
          activeOpacity={0.8}
        >
          <Ionicons name="log-out-outline" size={18} color={theme.accentRose} />
          <Text style={[styles.logoutText, { color: theme.accentRose }]}>
            {t('logoutAccount')}
          </Text>
        </TouchableOpacity>

        {/* Team Credits */}
        <View style={styles.creditsContainer}>
          <Text style={[styles.creditsText, { color: theme.textMuted }]}>
            CivicLens • Created by Team CodeX
          </Text>
          <Text style={[styles.creditsSub, { color: theme.textMuted }]}>
            Empowering Citizens Through AI-Driven Civic Justice
          </Text>
        </View>

        {/* Citizen Rights Guide Modal */}
        {showHandbookModal && (
          <Modal
            animationType="slide"
            transparent={true}
            visible={showHandbookModal}
            onRequestClose={() => setShowHandbookModal(false)}
          >
            <View style={styles.modalOverlay}>
              <View style={[styles.modalCard, { backgroundColor: theme.card, borderColor: theme.primary }]}>
                <View style={styles.modalHeader}>
                  <Text style={[styles.modalTitle, { color: theme.text }]}>
                    📖 {t('guideModalTitle')}
                  </Text>
                  <TouchableOpacity onPress={() => setShowHandbookModal(false)}>
                    <Ionicons name="close-circle" size={26} color={theme.textMuted} />
                  </TouchableOpacity>
                </View>

                <ScrollView style={{ maxHeight: 420 }} showsVerticalScrollIndicator={false}>
                  {getCitizenGuides(language).map((g) => (
                    <View key={g.id} style={[styles.guideItemCard, { backgroundColor: theme.surface, borderColor: theme.border }]}>
                      <View style={styles.guideTop}>
                        <Text style={styles.guideIcon}>{g.icon}</Text>
                        <Text style={[styles.guideTitle, { color: theme.text }]}>{g.title}</Text>
                      </View>
                      <Text style={[styles.guideSummary, { color: theme.textSecondary }]}>{g.summary}</Text>

                      <View style={styles.guideStepsList}>
                        {g.steps.map((st) => (
                          <View key={st.step} style={styles.stepItemRow}>
                            <Text style={[styles.stepNumText, { color: theme.primaryLight }]}>Step {st.step}:</Text>
                            <Text style={[styles.stepTitleText, { color: theme.text }]}>{st.title}</Text>
                            <Text style={[styles.stepDescText, { color: theme.textSecondary }]}>{st.desc}</Text>
                          </View>
                        ))}
                      </View>

                      <View style={[styles.proTipBox, { backgroundColor: theme.primaryGlow }]}>
                        <Text style={[styles.proTipText, { color: theme.primaryLight }]}>
                          💡 {t('proTip')}: {g.proTip}
                        </Text>
                      </View>
                    </View>
                  ))}

                  {/* FAQs */}
                  <Text style={[styles.faqSectionHeading, { color: theme.text }]}>
                    {t('faqTitle')}
                  </Text>
                  {getFaqs(language).map((f, i) => (
                    <View key={i} style={[styles.faqBox, { backgroundColor: theme.surface }]}>
                      <Text style={[styles.faqQ, { color: theme.text }]}>Q: {f.q}</Text>
                      <Text style={[styles.faqA, { color: theme.textSecondary }]}>A: {f.a}</Text>
                    </View>
                  ))}
                </ScrollView>
              </View>
            </View>
          </Modal>
        )}

        {/* ===================== MFA SETUP MODAL ===================== */}
        <Modal
          visible={mfaModalVisible}
          transparent
          animationType="slide"
          onRequestClose={() => setMfaModalVisible(false)}
        >
          <View style={styles.mfaOverlay}>
            <View style={[styles.mfaSheet, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
              <View style={styles.mfaHeader}>
                <Text style={[styles.mfaTitle, { color: theme.text }]}>Set up two-factor authentication</Text>
                <TouchableOpacity onPress={() => setMfaModalVisible(false)} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
                  <Ionicons name="close" size={22} color={theme.textSecondary} />
                </TouchableOpacity>
              </View>

              {mfaLoading && !mfaQrUrl ? (
                <View style={styles.mfaLoadingBox}>
                  <ActivityIndicator size="small" color={theme.primary} />
                  <Text style={[styles.mfaHint, { color: theme.textSecondary }]}>Preparing your setup code...</Text>
                </View>
              ) : (
                <>
                  <Text style={[styles.mfaHint, { color: theme.textSecondary }]}>
                    Scan this with an authenticator app (Google Authenticator, Authy, or similar), then enter the 6-digit code it shows.
                  </Text>

                  {mfaQrUrl ? (
                    <Image source={{ uri: mfaQrUrl }} style={styles.mfaQr} resizeMode="contain" />
                  ) : null}

                  {mfaSecret ? (
                    <View style={[styles.mfaSecretBox, { backgroundColor: theme.inputBg, borderColor: theme.border }]}>
                      <Text style={[styles.mfaSecretLabel, { color: theme.textMuted }]}>Can't scan? Enter this key manually:</Text>
                      <Text style={[styles.mfaSecretValue, { color: theme.text }]} selectable>{mfaSecret}</Text>
                    </View>
                  ) : null}

                  <TextInput
                    style={[styles.mfaInput, { backgroundColor: theme.inputBg, color: theme.text, borderColor: theme.border }]}
                    placeholder="6-digit code"
                    placeholderTextColor={theme.textMuted}
                    value={mfaCode}
                    onChangeText={setMfaCode}
                    keyboardType="number-pad"
                    maxLength={6}
                  />

                  {mfaError ? (
                    <Text style={[styles.mfaError, { color: theme.accentRose }]}>{mfaError}</Text>
                  ) : null}

                  <TouchableOpacity
                    style={[styles.mfaConfirmBtn, { backgroundColor: mfaLoading ? theme.border : theme.primary }]}
                    onPress={handleConfirmMfa}
                    disabled={mfaLoading}
                    activeOpacity={0.85}
                  >
                    {mfaLoading ? (
                      <ActivityIndicator size="small" color="#FFFFFF" />
                    ) : (
                      <Text style={styles.mfaConfirmText}>Verify & Enable</Text>
                    )}
                  </TouchableOpacity>
                </>
              )}
            </View>
          </View>
        </Modal>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  scrollContent: { paddingHorizontal: SPACING.md, paddingBottom: 120 },
  header: {
    paddingVertical: SPACING.sm,
    marginBottom: SPACING.xs,
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
  officialCard: {
    borderRadius: RADIUS.xl,
    padding: SPACING.md,
    borderWidth: 2,
    marginBottom: SPACING.md,
  },
  officialBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: RADIUS.lg,
    gap: 8,
    marginTop: 10,
  },
  officialBtnText: {
    color: '#FFFFFF',
    fontSize: FONT_SIZE.xs,
    fontWeight: '800',
  },
  card: {
    borderRadius: RADIUS.xl,
    padding: SPACING.md,
    borderWidth: 1,
    marginBottom: SPACING.md,
  },
  cardHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 4,
  },
  cardHeaderTitle: {
    fontSize: FONT_SIZE.md,
    fontWeight: '800',
  },
  cardHeaderSub: {
    fontSize: 11,
    lineHeight: 16,
    marginBottom: SPACING.md,
  },
  fieldGroup: {
    marginBottom: 10,
  },
  fieldLabel: {
    fontSize: 11,
    fontWeight: '700',
    marginBottom: 4,
  },
  fieldInput: {
    borderRadius: RADIUS.md,
    paddingHorizontal: SPACING.sm,
    paddingVertical: 8,
    fontSize: FONT_SIZE.xs,
    borderWidth: 1,
  },
  formRow: {
    flexDirection: 'row',
    gap: 10,
  },
  saveProfileBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: RADIUS.lg,
    gap: 6,
    marginTop: 6,
  },
  saveProfileBtnText: {
    color: '#FFFFFF',
    fontSize: FONT_SIZE.xs,
    fontWeight: '800',
  },
  successBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    padding: 8,
    borderRadius: RADIUS.md,
    marginTop: 8,
    justifyContent: 'center',
  },
  successText: {
    fontSize: 11,
    fontWeight: '700',
  },
  preferenceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: 10,
  },
  prefTitle: {
    fontSize: FONT_SIZE.xs,
    fontWeight: '700',
  },
  prefSub: {
    fontSize: 11,
  },
  toggleThemeBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: RADIUS.full,
    borderWidth: 1,
    gap: 6,
  },
  toggleThemeText: {
    fontSize: 11,
    fontWeight: '700',
  },
  languageGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  langCard: {
    width: '48%',
    padding: 10,
    borderRadius: RADIUS.md,
    borderWidth: 1,
  },
  langCardSelected: {},
  langCardUnselected: {},
  langHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  scriptBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  scriptBadgeText: {
    fontSize: 10,
    fontWeight: '800',
  },
  checkCircle: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: '#2E9E63',
    alignItems: 'center',
    justifyContent: 'center',
  },
  uncheckCircle: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 1.5,
  },
  langNative: {
    fontSize: 13,
    marginBottom: 1,
  },
  langEnglish: {
    fontSize: 10,
  },
  helpCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderRadius: RADIUS.xl,
    padding: SPACING.md,
    borderWidth: 1,
    marginBottom: SPACING.md,
  },
  helpLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flex: 1,
  },
  helpIconCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  helpTitle: {
    fontSize: FONT_SIZE.xs,
    fontWeight: '800',
  },
  helpSub: {
    fontSize: 10,
  },
  mfaOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'flex-end' },
  mfaSheet: { borderTopLeftRadius: RADIUS.lg, borderTopRightRadius: RADIUS.lg, borderWidth: 1, padding: SPACING.lg, gap: 12 },
  mfaHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  mfaTitle: { fontSize: 15, fontWeight: '800', flex: 1 },
  mfaHint: { fontSize: 12, lineHeight: 18 },
  mfaLoadingBox: { alignItems: 'center', gap: 10, paddingVertical: 28 },
  mfaQr: { width: 180, height: 180, alignSelf: 'center', backgroundColor: '#FFFFFF', borderRadius: RADIUS.md },
  mfaSecretBox: { borderRadius: RADIUS.md, borderWidth: 1, padding: 10, gap: 4 },
  mfaSecretLabel: { fontSize: 10 },
  mfaSecretValue: { fontSize: 13, fontWeight: '700', letterSpacing: 1 },
  mfaInput: { height: 46, borderRadius: RADIUS.md, borderWidth: 1, paddingHorizontal: 12, fontSize: 16, letterSpacing: 4, textAlign: 'center' },
  mfaError: { fontSize: 12 },
  mfaConfirmBtn: { height: 46, borderRadius: RADIUS.md, alignItems: 'center', justifyContent: 'center' },
  mfaConfirmText: { color: '#FFFFFF', fontSize: 14, fontWeight: '800' },
  logoutBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: RADIUS.xl,
    borderWidth: 1,
    gap: 6,
    marginBottom: SPACING.md,
  },
  logoutText: {
    fontSize: FONT_SIZE.xs,
    fontWeight: '700',
  },
  creditsContainer: {
    alignItems: 'center',
    paddingVertical: SPACING.sm,
    marginBottom: SPACING.lg,
  },
  creditsText: {
    fontSize: 11,
    fontWeight: '700',
  },
  creditsSub: {
    fontSize: 10,
    marginTop: 2,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    justifyContent: 'center',
    padding: SPACING.md,
  },
  modalCard: {
    borderRadius: RADIUS.xxl,
    padding: SPACING.md,
    borderWidth: 1,
    maxHeight: '80%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.sm,
  },
  modalTitle: {
    fontSize: 15,
    fontWeight: '800',
  },
  guideItemCard: {
    borderRadius: RADIUS.lg,
    padding: SPACING.sm,
    borderWidth: 1,
    marginBottom: 10,
  },
  guideTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  guideIcon: {
    fontSize: 18,
  },
  guideTitle: {
    fontSize: 12,
    fontWeight: '800',
  },
  guideSummary: {
    fontSize: 11,
    marginBottom: 6,
  },
  guideStepsList: {
    gap: 4,
    marginBottom: 6,
  },
  stepItemRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 4,
  },
  stepNumText: {
    fontSize: 10,
    fontWeight: '800',
  },
  stepTitleText: {
    fontSize: 10,
    fontWeight: '700',
  },
  stepDescText: {
    fontSize: 10,
  },
  proTipBox: {
    padding: 6,
    borderRadius: RADIUS.sm,
    marginTop: 4,
  },
  proTipText: {
    fontSize: 10,
    fontWeight: '700',
  },
  faqSectionHeading: {
    fontSize: 13,
    fontWeight: '800',
    marginTop: 10,
    marginBottom: 6,
  },
  faqBox: {
    padding: 8,
    borderRadius: RADIUS.md,
    marginBottom: 6,
  },
  faqQ: {
    fontSize: 11,
    fontWeight: '700',
    marginBottom: 2,
  },
  faqA: {
    fontSize: 10,
    lineHeight: 14,
  },
});
