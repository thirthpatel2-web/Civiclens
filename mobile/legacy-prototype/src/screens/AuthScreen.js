// CivicLens - National Portal Landing, Authentication & Role Selection Screen
// Premium onboarding & authentication experience

import React, { useState } from 'react';
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
  Dimensions,
  ActivityIndicator,
  Modal,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE, FONT_FAMILY } from '../constants/theme';
import { ALL_PUBLIC_AUTHORITIES } from '../data/departmentsData';
import {
  backendReady,
  signUpWithPassword,
  signInWithPassword,
  verifyMfaLogin,
  sendMagicLinkCode,
  verifyMagicLinkCode,
} from '../services/authService';

const { width } = Dimensions.get('window');

const FEATURE_PILLARS = [
  { icon: '📝', title: 'Statutory Letters', desc: 'AI-formatted complaints under Municipal Acts' },
  { icon: '🏛️', title: 'Precision RTI 2005', desc: 'Section 6(1) & 7(1) mandatory disclosure' },
  { icon: '⚖️', title: 'Judicial Precedents', desc: '30+ curated Supreme Court & tribunal cases' },
  { icon: '📧', title: 'Direct PIO Email', desc: '1-tap instant official dispatch' },
];

export default function AuthScreen({ navigation }) {
  const {
    theme,
    themeMode,
    toggleTheme,
    t,
    language,
    setLanguage,
    languagesList,
    loginAsGuest,
    completeCitizenProfile,
    completeOfficialProfile,
    userProfile,
  } = useApp();

  const [activeTab, setActiveTab] = useState('citizen'); // 'citizen' or 'official'

  // Citizen auth method: 'password' | 'magiclink' (Phone OTP omitted — needs a paid SMS provider)
  const [citizenMethod, setCitizenMethod] = useState('password');
  const [isSignUp, setIsSignUp] = useState(false);
  const [citizenName, setCitizenName] = useState(userProfile.name || '');
  const [citizenEmail, setCitizenEmail] = useState(userProfile.email || '');
  const [citizenPassword, setCitizenPassword] = useState('');
  const [citizenPhone, setCitizenPhone] = useState(userProfile.phone || '');
  const [magicLinkSent, setMagicLinkSent] = useState(false);
  const [magicLinkCode, setMagicLinkCode] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [mfaModalVisible, setMfaModalVisible] = useState(false);
  const [mfaPendingToken, setMfaPendingToken] = useState(null);
  const [mfaCode, setMfaCode] = useState('');
  const [mfaCompleteAction, setMfaCompleteAction] = useState(null); // fn to run after MFA succeeds

  // Official Login State (real Supabase email/password + department selection)
  const [officialEmail, setOfficialEmail] = useState('');
  const [officialPassword, setOfficialPassword] = useState('');
  const [officialIsSignUp, setOfficialIsSignUp] = useState(false);
  const [selectedDeptId, setSelectedDeptId] = useState('bbmp_roads');
  const [officerId, setOfficerId] = useState('');
  const [officerName, setOfficerName] = useState('');
  const [designation, setDesignation] = useState('');

  const handleAuthError = (label, error) => {
    Alert.alert(label, error);
  };

  const goToMain = () => navigation?.navigate && navigation.navigate('Main');
  const goToOfficialPortal = () => navigation?.navigate && navigation.navigate('OfficialPortal');

  // ---- Citizen: Email + Password -----------------------------------------
  const handlePasswordAuth = async () => {
    if (!citizenEmail.includes('@') || citizenPassword.length < 6) {
      Alert.alert('Check your details', 'Enter a valid email and a password of at least 6 characters.');
      return;
    }
    setIsSubmitting(true);
    const result = isSignUp
      ? await signUpWithPassword({ email: citizenEmail, password: citizenPassword, fullName: citizenName })
      : await signInWithPassword({ email: citizenEmail, password: citizenPassword });
    setIsSubmitting(false);

    if (result.error) return handleAuthError('Sign-in failed', result.error);

    // MFA required — must be checked before "!result.session" below,
    // since an MFA-pending result also has no session yet.
    if (result.mfaRequired) {
      setMfaPendingToken(result.pendingToken);
      setMfaCompleteAction(() => async () => {
        await completeCitizenProfile({ name: citizenName || 'Citizen', phone: citizenPhone });
        goToMain();
      });
      setMfaModalVisible(true);
      return;
    }

    if (!result.session) {
      Alert.alert(
        'Check your inbox',
        'Account created. If email confirmation is required, confirm your email before signing in.'
      );
      return;
    }

    await completeCitizenProfile({ name: citizenName || 'Citizen', phone: citizenPhone });
    goToMain();
  };

  // ---- Citizen: Magic Link (real 6-digit emailed code, custom backend) ----
  const handleRequestMagicLinkCode = async () => {
    if (!citizenEmail.includes('@')) {
      Alert.alert('Invalid email', 'Enter a valid email address to receive your sign-in code.');
      return;
    }
    setIsSubmitting(true);
    const { error, devFallback } = await sendMagicLinkCode(citizenEmail);
    setIsSubmitting(false);
    if (error) return handleAuthError('Could not send code', error);
    setMagicLinkSent(true);
    Alert.alert(
      'Code sent',
      devFallback
        ? `Email sending isn't configured on the server, so check the server's console log for your code (dev mode only).`
        : `Check ${citizenEmail} for a 6-digit sign-in code.`
    );
  };

  const handleVerifyMagicLinkCode = async () => {
    if (magicLinkCode.trim().length < 4) {
      Alert.alert('Enter the code', 'Enter the code you received by email.');
      return;
    }
    setIsSubmitting(true);
    const result = await verifyMagicLinkCode({ email: citizenEmail, code: magicLinkCode.trim() });
    setIsSubmitting(false);
    if (result.error) return handleAuthError('Verification failed', result.error);
    await completeCitizenProfile({ name: citizenName || 'Citizen', phone: citizenPhone });
    goToMain();
  };

  // NOTE: Phone OTP sign-in was removed from the default UI on purpose.
  // Real SMS delivery requires configuring a paid third-party provider
  // (Twilio, etc.) — no free tier realistically covers this. Password and
  // Magic Link below are both genuinely free. If you later add a paid SMS
  // provider, the
  // sendPhoneOtp/verifyPhoneOtp functions are still in authService.js.

  // ---- Official Login (real custom-backend auth + department profile) -----
  const handleOfficialAuth = async () => {
    if (!officialEmail.includes('@') || officialPassword.length < 6) {
      Alert.alert('Check your details', 'Enter a valid official email and a password of at least 6 characters.');
      return;
    }
    setIsSubmitting(true);
    const result = officialIsSignUp
      ? await signUpWithPassword({ email: officialEmail, password: officialPassword, fullName: officerName })
      : await signInWithPassword({ email: officialEmail, password: officialPassword });
    setIsSubmitting(false);

    if (result.error) return handleAuthError('Sign-in failed', result.error);

    // MFA required — the account has no real session yet until the
    // second factor is verified. This check MUST come before the
    // "!result.session" fallback below, since an MFA-pending result also
    // has no session and would otherwise be misread as "needs email confirmation".
    if (result.mfaRequired) {
      setMfaPendingToken(result.pendingToken);
      setMfaCompleteAction(() => () => finishOfficialLoginAfterAuth());
      setMfaModalVisible(true);
      return;
    }

    if (!result.session) {
      Alert.alert('Check your inbox', 'Account created. Confirm your email if required, then sign in.');
      return;
    }

    await finishOfficialLoginAfterAuth();
  };

  const finishOfficialLoginAfterAuth = async () => {
    const targetDept = ALL_PUBLIC_AUTHORITIES.find((d) => d.id === selectedDeptId);
    const profileResult = await completeOfficialProfile({
      deptId: selectedDeptId,
      officerId: officerId || 'PENDING-VERIFICATION',
      name: officerName || 'Nodal Officer',
      designation: designation || 'Nodal Officer',
      jurisdiction: targetDept ? targetDept.name : '',
    });
    if (!profileResult.success) return handleAuthError('Could not save officer profile', profileResult.error);
    goToOfficialPortal();
  };

  // Shared MFA verification handler — used by both citizen and official
  // login paths, since technically any account can have MFA enabled.
  const handleVerifyMfaCode = async () => {
    if (mfaCode.trim().length < 6) {
      Alert.alert('Enter the code', 'Enter the 6-digit code from your authenticator app.');
      return;
    }
    setIsSubmitting(true);
    const result = await verifyMfaLogin({ pendingToken: mfaPendingToken, token: mfaCode.trim() });
    setIsSubmitting(false);
    if (result.error) return handleAuthError('Verification failed', result.error);

    setMfaModalVisible(false);
    setMfaCode('');
    setMfaPendingToken(null);
    if (mfaCompleteAction) await mfaCompleteAction();
  };

  // ---- Instant Demo / Guest Login (explicitly local-only) ------------------
  const handleGuestDemo = async () => {
    await loginAsGuest();
    goToMain();
  };


  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        {/* ========================================================= */}
        {/* TOP QUICK BAR: LANGUAGE PILLS & THEME TOGGLE */}
        {/* ========================================================= */}
        <View style={styles.topBarRow}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.topLangScroll}
          >
            {languagesList.map((lang) => {
              const isSelected = language === lang.code;
              return (
                <TouchableOpacity
                  key={lang.code}
                  style={[
                    styles.langChip,
                    {
                      backgroundColor: isSelected ? theme.primary : theme.card,
                      borderColor: isSelected ? '#60A5FA' : theme.cardBorder,
                    },
                  ]}
                  onPress={() => setLanguage(lang.code)}
                  activeOpacity={0.8}
                >
                  <Text
                    style={[
                      styles.langChipText,
                      { color: isSelected ? '#FFFFFF' : theme.textSecondary, fontWeight: isSelected ? '800' : '600' },
                    ]}
                  >
                    {lang.native}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          <TouchableOpacity
            style={[styles.themeBtn, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
            onPress={toggleTheme}
            activeOpacity={0.8}
          >
            <Ionicons
              name={themeMode === 'dark' ? 'sunny' : 'moon'}
              size={15}
              color={themeMode === 'dark' ? '#BF6B3D' : theme.primary}
            />
          </TouchableOpacity>
        </View>

        {/* ========================================================= */}
        {/* HERO SECTION: DIGITAL INDIA & CIVICLENS HOLOGRAPHIC LOGO */}
        {/* ========================================================= */}
        <View style={styles.heroSection}>
          {/* Trust & Credibility Badges */}
          <View style={styles.heroBadgeRow}>
            <View style={[styles.sihBadge, { backgroundColor: 'rgba(191, 107, 61, 0.15)', borderColor: '#BF6B3D' }]}>
              <Text style={styles.sihBadgeText}>🏆 Trusted Civic Platform</Text>
            </View>
          </View>

          {!backendReady && (
            <View style={[styles.backendWarningBox, { backgroundColor: 'rgba(194, 69, 69, 0.12)', borderColor: '#C24545' }]}>
              <Ionicons name="warning-outline" size={14} color="#C24545" />
              <Text style={styles.backendWarningText}>
                Backend not connected — add your Supabase keys in app.json to enable real accounts. Guest Mode works now.
              </Text>
            </View>
          )}

          {/* Glowing Emblem Circle */}
          <View style={[styles.emblemCircle, { backgroundColor: theme.card, borderColor: theme.primary }]}>
            <Ionicons name="shield-checkmark" size={38} color={theme.primary} />
          </View>

          <Text style={[styles.heroTitle, { color: theme.text }]}>
            CivicLens
          </Text>
          <Text style={[styles.heroSubtitle, { color: theme.textSecondary }]}>
            India's 1st AI Statutory Grievance & RTI Copilot
          </Text>
        </View>

        {/* ========================================================= */}
        {/* DUAL PORTAL SWITCHER: CITIZEN VS GOVERNMENT OFFICIAL */}
        {/* ========================================================= */}
        <View style={[styles.tabSelector, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          <TouchableOpacity
            style={[
              styles.tabBtn,
              activeTab === 'citizen' && [styles.tabBtnActive, { backgroundColor: theme.primary }],
            ]}
            onPress={() => setActiveTab('citizen')}
            activeOpacity={0.8}
          >
            <Ionicons
              name="person-circle"
              size={18}
              color={activeTab === 'citizen' ? '#FFFFFF' : theme.textMuted}
            />
            <Text
              style={[
                styles.tabBtnText,
                { color: activeTab === 'citizen' ? '#FFFFFF' : theme.textSecondary },
              ]}
            >
              Citizen Portal
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.tabBtn,
              activeTab === 'official' && [styles.tabBtnActive, { backgroundColor: '#BF6B3D' }],
            ]}
            onPress={() => setActiveTab('official')}
            activeOpacity={0.8}
          >
            <Ionicons
              name="business"
              size={18}
              color={activeTab === 'official' ? '#FFFFFF' : theme.textMuted}
            />
            <Text
              style={[
                styles.tabBtnText,
                { color: activeTab === 'official' ? '#FFFFFF' : theme.textSecondary },
              ]}
            >
              Officer Portal Desk
            </Text>
          </TouchableOpacity>
        </View>

        {/* ========================================================= */}
        {/* TAB 1: CITIZEN AUTHENTICATION CARD (Password / Magic Link / Phone OTP) */}
        {/* ========================================================= */}
        {activeTab === 'citizen' && (
          <View style={[styles.authCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
            <View style={styles.cardHeaderRow}>
              <View style={[styles.iconCircle, { backgroundColor: theme.primaryGlow }]}>
                <Ionicons name="key" size={18} color={theme.primaryLight} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[styles.cardTitle, { color: theme.text }]}>Citizen Sign In</Text>
                <Text style={[styles.cardSub, { color: theme.textMuted }]}>
                  Real account, synced across your devices
                </Text>
              </View>
            </View>

            {/* Method Switcher — Phone OTP intentionally omitted: it needs
                a paid SMS provider (Twilio, etc.), unlike these two which
                are genuinely free on Supabase. */}
            <View style={styles.methodRow}>
              {[
                { id: 'password', label: 'Password', icon: 'lock-closed-outline' },
                { id: 'magiclink', label: 'Magic Link', icon: 'mail-outline' },
              ].map((m) => {
                const isSel = citizenMethod === m.id;
                return (
                  <TouchableOpacity
                    key={m.id}
                    style={[
                      styles.methodChip,
                      { backgroundColor: isSel ? theme.primary : theme.surface, borderColor: isSel ? theme.primary : theme.border },
                    ]}
                    onPress={() => {
                      setCitizenMethod(m.id);
                      setMagicLinkSent(false);
                    }}
                    activeOpacity={0.8}
                  >
                    <Ionicons name={m.icon} size={13} color={isSel ? '#FFFFFF' : theme.textSecondary} />
                    <Text style={[styles.methodChipText, { color: isSel ? '#FFFFFF' : theme.textSecondary }]}>
                      {m.label}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Name (only needed for sign-up / first-time profile) */}
            {(citizenMethod !== 'password' || isSignUp) && (
              <View style={styles.inputGroup}>
                <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Full Name</Text>
                <TextInput
                  style={[styles.textInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                  value={citizenName}
                  onChangeText={setCitizenName}
                  placeholder="e.g. your full name"
                  placeholderTextColor={theme.textMuted}
                />
              </View>
            )}

            {/* PASSWORD METHOD */}
            {citizenMethod === 'password' && (
              <>
                <View style={styles.inputGroup}>
                  <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Email</Text>
                  <TextInput
                    style={[styles.textInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                    value={citizenEmail}
                    onChangeText={setCitizenEmail}
                    placeholder="you@example.com"
                    placeholderTextColor={theme.textMuted}
                    autoCapitalize="none"
                    keyboardType="email-address"
                  />
                </View>
                <View style={styles.inputGroup}>
                  <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Password</Text>
                  <TextInput
                    style={[styles.textInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                    value={citizenPassword}
                    onChangeText={setCitizenPassword}
                    placeholder="At least 6 characters"
                    placeholderTextColor={theme.textMuted}
                    secureTextEntry
                  />
                </View>
                <TouchableOpacity onPress={() => setIsSignUp(!isSignUp)} style={{ marginBottom: SPACING.sm }}>
                  <Text style={{ color: theme.primaryLight, fontSize: FONT_SIZE.sm, fontWeight: '600' }}>
                    {isSignUp ? 'Already have an account? Sign in' : "New here? Create an account"}
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.primarySubmitBtn, { backgroundColor: theme.primary }]}
                  onPress={handlePasswordAuth}
                  disabled={isSubmitting}
                  activeOpacity={0.85}
                >
                  {isSubmitting ? (
                    <ActivityIndicator color="#FFFFFF" size="small" />
                  ) : (
                    <Ionicons name="log-in" size={18} color="#FFFFFF" />
                  )}
                  <Text style={styles.primarySubmitText}>
                    {isSubmitting ? 'Please wait…' : isSignUp ? 'Create Account' : 'Sign In'}
                  </Text>
                </TouchableOpacity>
              </>
            )}

            {/* MAGIC LINK METHOD — real 6-digit emailed code, custom backend */}
            {citizenMethod === 'magiclink' && (
              <>
                <View style={styles.inputGroup}>
                  <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Email</Text>
                  <TextInput
                    style={[styles.textInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                    value={citizenEmail}
                    onChangeText={setCitizenEmail}
                    placeholder="you@example.com"
                    placeholderTextColor={theme.textMuted}
                    autoCapitalize="none"
                    keyboardType="email-address"
                    editable={!magicLinkSent}
                  />
                </View>

                {magicLinkSent && (
                  <View style={styles.otpSection}>
                    <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>
                      Enter the code sent to your email
                    </Text>
                    <TextInput
                      style={[styles.otpBoxInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.primary }]}
                      value={magicLinkCode}
                      onChangeText={setMagicLinkCode}
                      placeholder="123456"
                      placeholderTextColor={theme.textMuted}
                      keyboardType="numeric"
                      maxLength={6}
                    />
                  </View>
                )}

                <TouchableOpacity
                  style={[styles.primarySubmitBtn, { backgroundColor: theme.primary }]}
                  onPress={magicLinkSent ? handleVerifyMagicLinkCode : handleRequestMagicLinkCode}
                  disabled={isSubmitting}
                  activeOpacity={0.85}
                >
                  {isSubmitting ? (
                    <ActivityIndicator color="#FFFFFF" size="small" />
                  ) : (
                    <Ionicons name="paper-plane-outline" size={18} color="#FFFFFF" />
                  )}
                  <Text style={styles.primarySubmitText}>
                    {magicLinkSent ? 'Verify & Sign In' : 'Send Sign-In Code'}
                  </Text>
                </TouchableOpacity>
                {magicLinkSent && (
                  <TouchableOpacity onPress={handleRequestMagicLinkCode} style={{ marginTop: 8 }}>
                    <Text style={{ color: theme.primaryLight, fontSize: 11, textAlign: 'center' }}>Resend code</Text>
                  </TouchableOpacity>
                )}
              </>
            )}
          </View>
        )}

        {/* ========================================================= */}
        {/* TAB 2: GOVERNMENT OFFICIAL LOGIN CARD */}
        {/* ========================================================= */}
        {activeTab === 'official' && (
          <View style={[styles.authCard, { backgroundColor: theme.card, borderColor: '#BF6B3D' }]}>
            <View style={styles.cardHeaderRow}>
              <View style={[styles.iconCircle, { backgroundColor: 'rgba(191, 107, 61, 0.2)' }]}>
                <Ionicons name="shield-half" size={18} color="#BF6B3D" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[styles.cardTitle, { color: theme.text }]}>
                  Government Official Portal Login
                </Text>
                <Text style={[styles.cardSub, { color: theme.textMuted }]}>
                  Resolution Desk & Action Taken Reports (ATRs)
                </Text>
              </View>
            </View>

            {/* Department Selection */}
            <View style={styles.inputGroup}>
              <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Select Department Desk</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.deptPillsScroll}>
                {ALL_PUBLIC_AUTHORITIES.slice(0, 8).map((dept) => {
                  const isSelected = selectedDeptId === dept.id;
                  return (
                    <TouchableOpacity
                      key={dept.id}
                      style={[
                        styles.deptPill,
                        {
                          backgroundColor: isSelected ? 'rgba(191, 107, 61, 0.2)' : theme.surface,
                          borderColor: isSelected ? '#BF6B3D' : theme.border,
                        },
                      ]}
                      onPress={() => setSelectedDeptId(dept.id)}
                      activeOpacity={0.8}
                    >
                      <Text style={{ fontSize: 13, marginRight: 4 }}>{dept.icon || '🏛️'}</Text>
                      <Text
                        style={[
                          styles.deptPillText,
                          { color: isSelected ? '#BF6B3D' : theme.textSecondary, fontWeight: isSelected ? '700' : '500' },
                        ]}
                      >
                        {dept.name}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>
            </View>

            {/* Officer Name & ID */}
            <View style={styles.formRow}>
              <View style={[styles.inputGroup, { flex: 1 }]}>
                <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Officer Name</Text>
                <TextInput
                  style={[styles.textInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                  value={officerName}
                  onChangeText={setOfficerName}
                  placeholder="e.g. your full name"
                  placeholderTextColor={theme.textMuted}
                />
              </View>
              <View style={[styles.inputGroup, { flex: 1 }]}>
                <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Official ID</Text>
                <TextInput
                  style={[styles.textInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                  value={officerId}
                  onChangeText={setOfficerId}
                  placeholder="e.g. your department staff ID"
                  placeholderTextColor={theme.textMuted}
                />
              </View>
            </View>

            <View style={styles.inputGroup}>
              <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Designation</Text>
              <TextInput
                style={[styles.textInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                value={designation}
                onChangeText={setDesignation}
                placeholder="e.g. Assistant Executive Engineer"
                placeholderTextColor={theme.textMuted}
              />
            </View>

            {/* Real Email + Password (Supabase auth) */}
            <View style={styles.inputGroup}>
              <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Official Email</Text>
              <TextInput
                style={[styles.textInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                value={officialEmail}
                onChangeText={setOfficialEmail}
                placeholder="you@department.gov.in"
                placeholderTextColor={theme.textMuted}
                autoCapitalize="none"
                keyboardType="email-address"
              />
            </View>
            <View style={styles.inputGroup}>
              <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>Password</Text>
              <TextInput
                style={[styles.textInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                value={officialPassword}
                onChangeText={setOfficialPassword}
                placeholder="At least 6 characters"
                placeholderTextColor={theme.textMuted}
                secureTextEntry
              />
            </View>
            <TouchableOpacity onPress={() => setOfficialIsSignUp(!officialIsSignUp)} style={{ marginBottom: SPACING.sm }}>
              <Text style={{ color: '#BF6B3D', fontSize: FONT_SIZE.sm, fontWeight: '600' }}>
                {officialIsSignUp ? 'Already registered? Sign in' : 'First time? Register this desk'}
              </Text>
            </TouchableOpacity>

            {/* Official Submit Button */}
            <TouchableOpacity
              style={[styles.primarySubmitBtn, { backgroundColor: '#BF6B3D' }]}
              onPress={handleOfficialAuth}
              disabled={isSubmitting}
              activeOpacity={0.85}
            >
              {isSubmitting ? (
                <ActivityIndicator color="#FFFFFF" size="small" />
              ) : (
                <Ionicons name="speedometer" size={18} color="#FFFFFF" />
              )}
              <Text style={styles.primarySubmitText}>
                {isSubmitting ? 'Please wait…' : 'Launch Government Resolution Desk →'}
              </Text>
            </TouchableOpacity>
          </View>
        )}

        {/* ========================================================= */}
        {/* INSTANT DEMO GUEST ACCESS BUTTON (FOR INSTANT EVALUATION) */}
        {/* ========================================================= */}
        <TouchableOpacity
          style={[styles.guestDemoBtn, { backgroundColor: theme.card, borderColor: theme.primary }]}
          onPress={handleGuestDemo}
          activeOpacity={0.85}
        >
          <View style={styles.guestLeft}>
            <Ionicons name="flash" size={20} color={theme.accentEmerald} />
            <View>
              <Text style={[styles.guestTitle, { color: theme.text }]}>
                ✨ Instant Live Demo (Explore as Guest)
              </Text>
              <Text style={[styles.guestSub, { color: theme.textMuted }]}>
                Experience all 11 AI legal & civic modules without signing in
              </Text>
            </View>
          </View>
          <Ionicons name="arrow-forward-circle" size={24} color={theme.primary} />
        </TouchableOpacity>

        {/* ========================================================= */}
        {/* 4 CORE CAPABILITY HIGHLIGHTS */}
        {/* ========================================================= */}
        <View style={styles.pillarsGrid}>
          {FEATURE_PILLARS.map((p, idx) => (
            <View
              key={idx}
              style={[styles.pillarBox, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}
            >
              <Text style={styles.pillarIcon}>{p.icon}</Text>
              <Text style={[styles.pillarTitle, { color: theme.text }]}>{p.title}</Text>
              <Text style={[styles.pillarDesc, { color: theme.textMuted }]}>{p.desc}</Text>
            </View>
          ))}
        </View>

        {/* Team Credits */}
        <View style={styles.footerCredits}>
          <Text style={[styles.footerText, { color: theme.textMuted }]}>
            CivicLens • Created by Team CodeX
          </Text>
          <Text style={[styles.footerSub, { color: theme.textMuted }]}>
            National AI Civic & Legal Copilot
          </Text>
        </View>
      </ScrollView>

      {/* MFA Verification Modal — the "popup" your team planned for the
          second factor, shared by both citizen and official login paths */}
      <Modal visible={mfaModalVisible} animationType="slide" transparent onRequestClose={() => setMfaModalVisible(false)}>
        <View style={styles.mfaModalOverlay}>
          <View style={[styles.mfaModalCard, { backgroundColor: theme.card, borderColor: theme.primary }]}>
            <Ionicons name="shield-checkmark" size={32} color={theme.primaryLight} style={{ alignSelf: 'center', marginBottom: 10 }} />
            <Text style={[styles.mfaModalTitle, { color: theme.text }]}>Two-Factor Verification</Text>
            <Text style={[styles.mfaModalSub, { color: theme.textMuted }]}>
              Enter the 6-digit code from your authenticator app.
            </Text>
            <TextInput
              style={[styles.otpBoxInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.primary, alignSelf: 'center', marginTop: 14 }]}
              value={mfaCode}
              onChangeText={setMfaCode}
              placeholder="123456"
              placeholderTextColor={theme.textMuted}
              keyboardType="numeric"
              maxLength={6}
              autoFocus
            />
            <TouchableOpacity
              style={[styles.primarySubmitBtn, { backgroundColor: theme.primary, marginTop: 16 }]}
              onPress={handleVerifyMfaCode}
              disabled={isSubmitting}
              activeOpacity={0.85}
            >
              {isSubmitting ? <ActivityIndicator color="#FFFFFF" size="small" /> : <Ionicons name="lock-open" size={18} color="#FFFFFF" />}
              <Text style={styles.primarySubmitText}>{isSubmitting ? 'Verifying...' : 'Verify & Continue'}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => { setMfaModalVisible(false); setMfaCode(''); }} style={{ marginTop: 10 }}>
              <Text style={{ color: theme.textMuted, fontSize: 12, textAlign: 'center' }}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
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
    paddingBottom: 60,
  },
  topBarRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: SPACING.sm,
    gap: 8,
  },
  topLangScroll: {
    gap: 6,
    paddingVertical: 2,
  },
  langChip: {
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: RADIUS.full,
    borderWidth: 1,
  },
  langChipText: {
    fontSize: 11,
  },
  themeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
  },
  heroSection: {
    alignItems: 'center',
    marginVertical: SPACING.md,
  },
  heroBadgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  sihBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: RADIUS.full,
    borderWidth: 1,
  },
  sihBadgeText: {
    fontSize: 10,
    color: '#BF6B3D',
    fontWeight: '800',
  },
  govPill: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: RADIUS.full,
  },
  govPillText: {
    fontSize: 10,
    fontWeight: '700',
  },
  backendWarningBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    marginTop: 8,
    marginHorizontal: 4,
  },
  backendWarningText: {
    fontSize: 10.5,
    color: '#C24545',
    fontWeight: '600',
    flex: 1,
  },
  methodRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: SPACING.sm,
  },
  methodChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: RADIUS.full,
    borderWidth: 1,
  },
  methodChipText: {
    fontSize: 11.5,
    fontWeight: '700',
  },
  helperNote: {
    fontSize: FONT_SIZE.xs,
    marginTop: -4,
    marginBottom: SPACING.sm,
    textAlign: 'center',
  },
  emblemCircle: {
    width: 74,
    height: 74,
    borderRadius: 37,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    shadowColor: '#3547A8',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.35,
    shadowRadius: 10,
    elevation: 6,
    marginBottom: 10,
  },
  heroTitle: {
    fontFamily: FONT_FAMILY.displayBold,
    fontSize: 30,
    letterSpacing: -0.5,
    marginBottom: 4,
  },
  heroSubtitle: {
    fontFamily: FONT_FAMILY.body,
    fontSize: 12,
    textAlign: 'center',
    maxWidth: 280,
    lineHeight: 16,
  },
  tabSelector: {
    flexDirection: 'row',
    borderRadius: RADIUS.xl,
    padding: 4,
    marginBottom: SPACING.md,
    borderWidth: 1,
  },
  tabBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: RADIUS.lg,
    gap: 6,
  },
  tabBtnActive: {},
  tabBtnText: {
    fontSize: FONT_SIZE.xs,
    fontWeight: '800',
  },
  authCard: {
    borderRadius: RADIUS.xxl,
    padding: SPACING.md,
    borderWidth: 1,
    marginBottom: SPACING.md,
  },
  cardHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: SPACING.md,
  },
  iconCircle: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardTitle: {
    fontSize: FONT_SIZE.sm,
    fontWeight: '800',
  },
  cardSub: {
    fontSize: 11,
    marginTop: 1,
  },
  inputGroup: {
    marginBottom: 12,
  },
  inputLabel: {
    fontSize: 11,
    fontWeight: '700',
    marginBottom: 4,
  },
  textInput: {
    borderRadius: RADIUS.lg,
    paddingHorizontal: SPACING.sm,
    paddingVertical: 9,
    fontSize: FONT_SIZE.xs,
    borderWidth: 1,
  },
  formRow: {
    flexDirection: 'row',
    gap: 10,
  },
  phoneInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: RADIUS.lg,
    borderWidth: 1,
    paddingLeft: SPACING.sm,
    paddingRight: 4,
    height: 44,
  },
  flagPrefix: {
    fontSize: 12,
    fontWeight: '700',
    marginRight: 6,
  },
  phoneInput: {
    flex: 1,
    fontSize: FONT_SIZE.xs,
    height: '100%',
  },
  otpActionBtn: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: RADIUS.md,
  },
  otpActionText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '800',
  },
  otpSection: {
    marginBottom: 12,
  },
  otpHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  demoOtpBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
  },
  demoOtpText: {
    fontSize: 10,
    fontWeight: '800',
  },
  otpBoxInput: {
    borderRadius: RADIUS.lg,
    paddingHorizontal: SPACING.sm,
    paddingVertical: 10,
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 8,
    textAlign: 'center',
    borderWidth: 1.5,
  },
  mfaModalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.75)', justifyContent: 'center', padding: SPACING.lg },
  mfaModalCard: { borderRadius: RADIUS.xl, padding: SPACING.lg, borderWidth: 1.5 },
  mfaModalTitle: { fontSize: 17, fontWeight: '800', textAlign: 'center' },
  mfaModalSub: { fontSize: 12, textAlign: 'center', marginTop: 6, lineHeight: 17 },
  primarySubmitBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 13,
    borderRadius: RADIUS.xl,
    gap: 8,
    marginTop: 4,
  },
  primarySubmitText: {
    color: '#FFFFFF',
    fontSize: FONT_SIZE.xs,
    fontWeight: '800',
  },
  deptPillsScroll: {
    flexDirection: 'row',
  },
  deptPill: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: RADIUS.full,
    borderWidth: 1,
    marginRight: 6,
  },
  deptPillText: {
    fontSize: 11,
  },
  guestDemoBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: SPACING.md,
    borderRadius: RADIUS.xl,
    borderWidth: 1.5,
    marginBottom: SPACING.md,
  },
  guestLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flex: 1,
    paddingRight: 8,
  },
  guestTitle: {
    fontSize: FONT_SIZE.xs,
    fontWeight: '800',
  },
  guestSub: {
    fontSize: 10,
    marginTop: 1,
  },
  pillarsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: SPACING.md,
  },
  pillarBox: {
    width: (width - 44) / 2,
    borderRadius: RADIUS.lg,
    padding: 10,
    borderWidth: 1,
  },
  pillarIcon: {
    fontSize: 18,
    marginBottom: 4,
  },
  pillarTitle: {
    fontSize: 11,
    fontWeight: '800',
    marginBottom: 2,
  },
  pillarDesc: {
    fontSize: 10,
    lineHeight: 13,
  },
  footerCredits: {
    alignItems: 'center',
    marginTop: SPACING.xs,
  },
  footerText: {
    fontSize: 11,
    fontWeight: '700',
  },
  footerSub: {
    fontSize: 10,
    marginTop: 1,
  },
});
