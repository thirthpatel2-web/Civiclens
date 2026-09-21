// CivicLens - Judicial Case Outcome Predictor & Legal Precedent Analyzer

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  SafeAreaView,
  ActivityIndicator,
  Modal,
  Platform,
  Linking,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE } from '../constants/theme';
import { LEGAL_CATEGORIES } from '../data/legalCasesData';
import { analyzeLegalCase } from '../services/aiService';
import VoiceListeningModal from '../components/VoiceListeningModal';
import HoverCard from '../components/HoverCard';
import HoverChip from '../components/HoverChip';

const CASE_EXAMPLES = [
  'Friend issued ₹3.5 Lakh cheque which bounced due to insufficient funds',
  'Builder delayed flat possession by 2 years and refusing to pay interest or refund',
  'Landlord refusing to refund ₹1.2 Lakh security deposit after lease ended',
  'Police station refusing to register Zero FIR for phone theft and physical assault',
  'Airline cancelled flight without notice and forcing credit voucher instead of cash refund',
  'Unauthorized UPI debit of ₹45,000 from bank account through phishing link',
  'Employer terminated me without notice and withheld 3 months salary and PF',
  'My father is giving all ancestral property to my brother and refusing to give me any share',
];

export default function CaseAnalyzerScreen({ route }) {
  const { theme, t, language } = useApp();

  const [caseText, setCaseText] = useState(route.params?.initialText || '');
  const [selectedCategory, setSelectedCategory] = useState(LEGAL_CATEGORIES[0]);
  const [loading, setLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [activeAnalysisTab, setActiveAnalysisTab] = useState('prediction'); // prediction, laws, bias, cases, court
  const [selectedModalCase, setSelectedModalCase] = useState(null);
  const [voiceModalVisible, setVoiceModalVisible] = useState(false);

  useEffect(() => {
    if (route.params?.initialText) {
      setCaseText(route.params.initialText);
      handleAnalyze(route.params.initialText);
    }
  }, [route.params]);

  const handleVoiceResult = (transcript) => {
    setCaseText(transcript);
    handleAnalyze(transcript);
  };

  const handleAnalyze = async (overrideText = null) => {
    const textToAnalyze = overrideText || caseText;
    if (!textToAnalyze.trim() || textToAnalyze.trim().length < 10) {
      return;
    }

    setLoading(true);
    setAnalysisResult(null);

    try {
      const res = await analyzeLegalCase({
        text: textToAnalyze,
        category: selectedCategory.id,
      });
      if (res.success) {
        setAnalysisResult(res.data);
      }
    } catch (e) {
      console.log('Analysis error:', e);
    } finally {
      setLoading(false);
    }
  };

  const getConfidenceColor = (score) => {
    if (score >= 80) return theme.accentEmerald;
    if (score >= 60) return theme.accentAmber;
    return theme.accentRose;
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
            ⚖️ {t('analyzeCase')}
          </Text>
          <Text style={[styles.screenSubtitle, { color: theme.textSecondary }]}>
            {t('analyzeCaseSub')}
          </Text>
        </View>

        {/* Category Selector with Touch Feedback */}
        <Text style={[styles.inputLabel, { color: theme.textSecondary }]}>
          Select Legal Dispute Domain:
        </Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.catScroll}>
          {LEGAL_CATEGORIES.map((cat) => {
            const isSelected = selectedCategory.id === cat.id;
            return (
              <HoverChip
                key={cat.id}
                isSelected={isSelected}
                activeColor={cat.color}
                onPress={() => setSelectedCategory(cat)}
              >
                <Text style={styles.catIcon}>{cat.icon}</Text>
                <Text
                  style={[
                    styles.catText,
                    { color: isSelected ? '#FFFFFF' : theme.text, fontWeight: isSelected ? '700' : '500' },
                  ]}
                >
                  {cat.name}
                </Text>
              </HoverChip>
            );
          })}
        </ScrollView>

        {/* Input Card */}
        <View style={[styles.inputCard, { backgroundColor: theme.card, borderColor: theme.cardBorder, shadowColor: '#000', shadowOpacity: 0.08, shadowOffset: { width: 0, height: 2 }, elevation: 3 }]}>
          <View style={styles.inputHeaderRow}>
            <Text style={[styles.inputLabel, { color: theme.text }]}>
              {t('caseInputLabel')}
            </Text>
            <TouchableOpacity
              style={[styles.voiceMicBadge, { backgroundColor: theme.primaryGlow }]}
              onPress={() => setVoiceModalVisible(true)}
              activeOpacity={0.7}
            >
              <Ionicons name="mic" size={15} color={theme.primary} />
              <Text style={[styles.voiceMicText, { color: theme.primary }]}>
                Voice Input
              </Text>
            </TouchableOpacity>
          </View>

          <TextInput
            style={[styles.caseTextArea, { backgroundColor: theme.inputBg, color: theme.text, borderColor: theme.border }]}
            placeholder={t('caseInputPlaceholder')}
            placeholderTextColor={theme.textMuted}
            multiline
            numberOfLines={5}
            value={caseText}
            onChangeText={setCaseText}
            textAlignVertical="top"
          />

          {/* Quick Case Examples */}
          <Text style={[styles.exampleTitle, { color: theme.textMuted }]}>
            Sample Dispute Scenarios:
          </Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.exampleScroll}>
            {CASE_EXAMPLES.map((ex, i) => (
              <TouchableOpacity
                key={i}
                style={[styles.exampleChip, { backgroundColor: theme.surface, borderColor: theme.border }]}
                onPress={() => { setCaseText(ex); }}
                activeOpacity={0.8}
              >
                <Text style={[styles.exampleText, { color: theme.textSecondary }]} numberOfLines={1}>
                  {ex}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <TouchableOpacity
            style={[styles.analyzeBtn, { backgroundColor: theme.primary }, loading && { opacity: 0.7 }]}
            onPress={() => handleAnalyze()}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading ? (
              <>
                <ActivityIndicator color="#FFFFFF" size="small" />
                <Text style={styles.analyzeBtnText}>Analyzing Legal Precedents...</Text>
              </>
            ) : (
              <>
                <Ionicons name="analytics" size={18} color="#FFFFFF" />
                <Text style={styles.analyzeBtnText}>{t('analyzeBtn')}</Text>
              </>
            )}
          </TouchableOpacity>
        </View>

        {/* Analysis Results 5-Tab Section */}
        {analysisResult && (
          <View style={styles.resultsContainer}>
            {/* 5-Tab Selector Header with Hover */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabNavScroll}>
              {[
                { key: 'prediction', label: t('tabPrediction') },
                { key: 'laws', label: t('tabLaws') },
                { key: 'bias', label: t('tabBias') },
                { key: 'cases', label: t('tabCases') },
                { key: 'court', label: t('tabCourtGuide') },
              ].map((tab) => {
                const isActive = activeAnalysisTab === tab.key;
                return (
                  <HoverChip
                    key={tab.key}
                    isSelected={isActive}
                    activeColor={theme.primary}
                    onPress={() => setActiveAnalysisTab(tab.key)}
                  >
                    <Text
                      style={[
                        styles.tabNavText,
                        { color: isActive ? '#FFFFFF' : theme.textSecondary, fontWeight: isActive ? '700' : '500' },
                      ]}
                    >
                      {tab.label}
                    </Text>
                  </HoverChip>
                );
              })}
            </ScrollView>

            {/* TAB 1: Outcome Prediction */}
            {activeAnalysisTab === 'prediction' && (
              <View style={[styles.tabContentCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
                <View style={styles.outcomeHeaderRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.outcomeLabel, { color: theme.textMuted }]}>
                      {t('predictedOutcome').toUpperCase()}
                    </Text>
                    <Text style={[styles.outcomeTitle, { color: theme.text }]}>
                      {analysisResult.predicted_outcome}
                    </Text>
                  </View>
                  <View style={[styles.confidenceBadge, { borderColor: getConfidenceColor(analysisResult.confidence_score) }]}>
                    <Text style={[styles.confidenceScore, { color: getConfidenceColor(analysisResult.confidence_score) }]}>
                      {analysisResult.confidence_score}%
                    </Text>
                    <Text style={[styles.confidenceText, { color: theme.textMuted }]}>
                      {t('confidenceScore')}
                    </Text>
                  </View>
                </View>

                {/* Progress Bar */}
                <View style={[styles.progressBarTrack, { backgroundColor: theme.surface }]}>
                  <View
                    style={[
                      styles.progressBarFill,
                      {
                        width: `${analysisResult.confidence_score}%`,
                        backgroundColor: getConfidenceColor(analysisResult.confidence_score),
                      },
                    ]}
                  />
                </View>

                {/* Summary */}
                <View style={[styles.infoBlock, { backgroundColor: theme.surface }]}>
                  <Text style={[styles.infoBlockTitle, { color: theme.text }]}>
                    📋 Judicial Assessment Summary
                  </Text>
                  <Text style={[styles.infoBlockText, { color: theme.textSecondary }]}>
                    {analysisResult.case_summary}
                  </Text>
                </View>

                {/* Explainable AI Reasoning */}
                <View style={[styles.infoBlock, { backgroundColor: theme.surface }]}>
                  <Text style={[styles.infoBlockTitle, { color: theme.text }]}>
                    🧠 {t('xaiReasoning')}
                  </Text>
                  {analysisResult.outcome_reasoning?.map((reason, idx) => (
                    <View key={idx} style={styles.bulletRow}>
                      <View style={[styles.bulletDot, { backgroundColor: theme.primary }]} />
                      <Text style={[styles.bulletText, { color: theme.textSecondary }]}>
                        {reason}
                      </Text>
                    </View>
                  ))}
                </View>

                {/* Recommended Actions */}
                <View style={[styles.infoBlock, { backgroundColor: theme.surface }]}>
                  <Text style={[styles.infoBlockTitle, { color: theme.text }]}>
                    🎯 {t('recommendedSteps')}
                  </Text>
                  {analysisResult.recommended_actions?.map((act, idx) => (
                    <View key={idx} style={styles.actionStepRow}>
                      <View style={[styles.stepNumCircle, { backgroundColor: theme.primaryGlow }]}>
                        <Text style={[styles.stepNum, { color: theme.primary }]}>{idx + 1}</Text>
                      </View>
                      <Text style={[styles.actionStepText, { color: theme.text }]}>{act}</Text>
                    </View>
                  ))}
                </View>
              </View>
            )}

            {/* TAB 2: Applicable Laws */}
            {activeAnalysisTab === 'laws' && (
              <View style={[styles.tabContentCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
                <Text style={[styles.tabHeaderTitle, { color: theme.text }]}>
                  📜 {t('applicableSections')} (Indian Law)
                </Text>
                <Text style={[styles.tabHeaderSub, { color: theme.textMuted }]}>
                  Key statutory protections governing this dispute domain:
                </Text>

                {analysisResult.applicable_sections?.map((sec, idx) => (
                  <View key={idx} style={[styles.lawCard, { backgroundColor: theme.surface, borderColor: theme.border }]}>
                    <View style={styles.lawCardHeader}>
                      <Ionicons name="bookmark" size={16} color={theme.accentPurple} />
                      <Text style={[styles.lawSectionTitle, { color: theme.accentPurple }]}>
                        {sec.section}
                      </Text>
                    </View>
                    <Text style={[styles.lawName, { color: theme.text }]}>{sec.name}</Text>
                    <Text style={[styles.lawDesc, { color: theme.textSecondary }]}>{sec.desc}</Text>
                  </View>
                ))}
              </View>
            )}

            {/* TAB 3: Bias Risk Analysis */}
            {activeAnalysisTab === 'bias' && (
              <View style={[styles.tabContentCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
                <View style={[styles.biasRiskBanner, { backgroundColor: 'rgba(191, 107, 61, 0.15)', borderColor: theme.accentAmber }]}>
                  <Ionicons name="shield-half" size={24} color={theme.accentAmber} />
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.biasRiskHeading, { color: theme.text }]}>
                      {t('biasRiskLevel')}: {analysisResult.bias_risk_level}
                    </Text>
                    <Text style={[styles.biasRiskSub, { color: theme.textSecondary }]}>
                      Identified socio-economic asymmetries and litigation friction
                    </Text>
                  </View>
                </View>

                <View style={[styles.infoBlock, { backgroundColor: theme.surface, marginTop: 12 }]}>
                  <Text style={[styles.infoBlockTitle, { color: theme.text }]}>
                    Analysis of Power Disparities
                  </Text>
                  <Text style={[styles.infoBlockText, { color: theme.textSecondary }]}>
                    {analysisResult.bias_explanation}
                  </Text>
                </View>

                <View style={[styles.infoBlock, { backgroundColor: theme.surface }]}>
                  <Text style={[styles.infoBlockTitle, { color: theme.text }]}>
                    Potential Friction Factors
                  </Text>
                  {analysisResult.bias_factors?.map((bf, idx) => (
                    <View key={idx} style={styles.bulletRow}>
                      <Ionicons name="warning-outline" size={14} color={theme.accentAmber} style={{ marginTop: 2 }} />
                      <Text style={[styles.bulletText, { color: theme.textSecondary }]}>
                        {bf}
                      </Text>
                    </View>
                  ))}
                </View>
              </View>
            )}

            {/* TAB 4: 5 Similar Cases */}
            {activeAnalysisTab === 'cases' && (
              <View style={[styles.tabContentCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
                <Text style={[styles.tabHeaderTitle, { color: theme.text }]}>
                  📁 5 Similar Indian Court Precedents
                </Text>
                <Text style={[styles.tabHeaderSub, { color: theme.textMuted }]}>
                  Tap any case to inspect court orders, ratio decidendi & laws cited:
                </Text>

                {analysisResult.precedents?.map((c) => (
                  <HoverCard
                    key={c.id}
                    glowColor={theme.primary}
                    style={[styles.precedentCard, { backgroundColor: theme.surface, borderColor: theme.border }]}
                    onPress={() => setSelectedModalCase(c)}
                  >
                    <View style={styles.precTopRow}>
                      <Text style={[styles.precTitle, { color: theme.text }]}>{c.title}</Text>
                      <View style={[styles.precWinBadge, { backgroundColor: 'rgba(46, 158, 99, 0.15)' }]}>
                        <Text style={[styles.precWinText, { color: theme.accentEmerald }]}>
                          {c.outcome.includes('Won') ? 'Citizen Won' : 'Settled'}
                        </Text>
                      </View>
                    </View>

                    <Text style={[styles.precCourt, { color: theme.primaryLight }]}>
                      🏛️ {c.court} ({c.year})
                    </Text>
                    <Text style={[styles.precSummary, { color: theme.textSecondary }]} numberOfLines={2}>
                      {c.summary}
                    </Text>

                    <View style={styles.precFooter}>
                      <Text style={[styles.tapInspectText, { color: theme.primary }]}>
                        View Judicial Takeaway →
                      </Text>
                    </View>
                  </HoverCard>
                ))}

                {/* Live search against a real, continuously-updated case-law
                    database — this curated list is a fixed, hand-picked set
                    for offline reasoning, so anything wider than that opens
                    the real corpus rather than fabricating more entries. */}
                <TouchableOpacity
                  style={[styles.liveCaseSearchBtn, { backgroundColor: theme.primaryGlow, borderColor: theme.primary }]}
                  onPress={() =>
                    Linking.openURL(
                      `https://indiankanoon.org/search/?formInput=${encodeURIComponent(caseText || analysisResult.case_summary || '')}`
                    )
                  }
                  activeOpacity={0.85}
                >
                  <Ionicons name="globe-outline" size={16} color={theme.primary} />
                  <View style={{ flex: 1, marginLeft: 8 }}>
                    <Text style={[styles.liveCaseSearchTitle, { color: theme.primaryLight }]}>
                      Search the full live case-law database
                    </Text>
                    <Text style={[styles.liveCaseSearchSub, { color: theme.textMuted }]}>
                      Opens real, current judgments on Indian Kanoon for this fact pattern — not limited to this app's curated list
                    </Text>
                  </View>
                  <Ionicons name="open-outline" size={16} color={theme.primary} />
                </TouchableOpacity>
              </View>
            )}

            {/* TAB 5: Court Guide & Fees */}
            {activeAnalysisTab === 'court' && (
              <View style={[styles.tabContentCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
                <Text style={[styles.tabHeaderTitle, { color: theme.text }]}>
                  ⚖️ Court Procedures & Fee Estimator
                </Text>

                <View style={[styles.courtStatGrid, { backgroundColor: theme.surface }]}>
                  <View style={styles.courtStatItem}>
                    <Text style={[styles.courtStatLabel, { color: theme.textMuted }]}>FORUM</Text>
                    <Text style={[styles.courtStatValue, { color: theme.text }]} numberOfLines={2}>
                      {analysisResult.court_guide?.forumName}
                    </Text>
                  </View>
                  <View style={styles.courtStatItem}>
                    <Text style={[styles.courtStatLabel, { color: theme.textMuted }]}>FILING FEE</Text>
                    <Text style={[styles.courtStatValue, { color: theme.accentEmerald }]}>
                      {analysisResult.court_guide?.filingFee}
                    </Text>
                  </View>
                </View>

                <View style={[styles.infoBlock, { backgroundColor: theme.surface }]}>
                  <Text style={[styles.infoBlockTitle, { color: theme.text }]}>
                    Is an Advocate Mandatory?
                  </Text>
                  <Text style={[styles.infoBlockText, { color: theme.textSecondary }]}>
                    {analysisResult.court_guide?.advocateMandatory}
                  </Text>
                </View>

                <View style={[styles.infoBlock, { backgroundColor: theme.surface }]}>
                  <Text style={[styles.infoBlockTitle, { color: theme.text }]}>
                    Procedural Step-by-Step Pathway
                  </Text>
                  {analysisResult.court_guide?.steps?.map((st, idx) => (
                    <View key={idx} style={styles.stepPathwayRow}>
                      <Text style={[styles.stepPathwayText, { color: theme.textSecondary }]}>
                        {st}
                      </Text>
                    </View>
                  ))}
                </View>
              </View>
            )}
          </View>
        )}

        {/* Modal for Expanded Precedent Case Detail */}
        {selectedModalCase && (
          <Modal
            animationType="slide"
            transparent={true}
            visible={!!selectedModalCase}
            onRequestClose={() => setSelectedModalCase(null)}
          >
            <View style={styles.modalOverlay}>
              <View style={[styles.modalCard, { backgroundColor: theme.card, borderColor: theme.primary }]}>
                <View style={styles.modalHeader}>
                  <Text style={[styles.modalTitle, { color: theme.text }]}>
                    {selectedModalCase.title}
                  </Text>
                  <TouchableOpacity onPress={() => setSelectedModalCase(null)}>
                    <Ionicons name="close-circle" size={26} color={theme.textMuted} />
                  </TouchableOpacity>
                </View>

                <ScrollView style={{ maxHeight: 400 }}>
                  <Text style={[styles.modalCourtName, { color: theme.primaryLight }]}>
                    🏛️ {selectedModalCase.court} | Year {selectedModalCase.year}
                  </Text>

                  <View style={[styles.modalOutcomeBox, { backgroundColor: 'rgba(46, 158, 99, 0.15)' }]}>
                    <Text style={[styles.modalOutcomeText, { color: theme.accentEmerald }]}>
                      Verdict: {selectedModalCase.outcome}
                    </Text>
                  </View>

                  <Text style={[styles.modalSectionHeading, { color: theme.text }]}>Case Summary:</Text>
                  <Text style={[styles.modalBodyText, { color: theme.textSecondary }]}>
                    {selectedModalCase.summary}
                  </Text>

                  <Text style={[styles.modalSectionHeading, { color: theme.text }]}>Key Indian Laws Cited:</Text>
                  <View style={styles.modalLawsRow}>
                    {selectedModalCase.keyLaws?.map((l, i) => (
                      <View key={i} style={[styles.modalLawTag, { backgroundColor: theme.surface }]}>
                        <Text style={[styles.modalLawTagText, { color: theme.primary }]}>{l}</Text>
                      </View>
                    ))}
                  </View>

                  <Text style={[styles.modalSectionHeading, { color: theme.text }]}>Judicial Takeaway for Citizens:</Text>
                  <Text style={[styles.modalBodyText, { color: theme.text }]}>
                    💡 {selectedModalCase.takeaway}
                  </Text>
                </ScrollView>

                <TouchableOpacity
                  style={[styles.modalCloseBtn, { backgroundColor: theme.primary }]}
                  onPress={() => setSelectedModalCase(null)}
                >
                  <Text style={styles.modalCloseBtnText}>Close Case View</Text>
                </TouchableOpacity>
              </View>
            </View>
          </Modal>
        )}
      </ScrollView>

      {/* Voice Dictation Hub Modal */}
      <VoiceListeningModal
        visible={voiceModalVisible}
        onClose={() => setVoiceModalVisible(false)}
        onSpeechResult={handleVoiceResult}
        language={language}
        title="Judicial Case Voice Dictation"
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  scrollContent: { paddingHorizontal: SPACING.md, paddingBottom: 260 },
  header: { paddingTop: Platform.OS === 'android' ? 30 : 10, marginBottom: SPACING.md },
  screenTitle: { fontSize: 20, fontWeight: '800' },
  screenSubtitle: { fontSize: 12, marginTop: 3 },
  inputLabel: { fontSize: 12, fontWeight: '700', marginBottom: 8 },
  catScroll: { flexDirection: 'row', marginBottom: SPACING.md },
  catChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: RADIUS.md,
    borderWidth: 1.5,
    marginRight: 8,
    gap: 6,
  },
  catIcon: { fontSize: 16 },
  catText: { fontSize: 12 },
  inputCard: {
    borderRadius: RADIUS.lg,
    padding: SPACING.md,
    borderWidth: 1,
    marginBottom: SPACING.md,
  },
  inputHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  voiceMicBadge: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full, gap: 5 },
  voiceMicText: { fontSize: 11, fontWeight: '700' },
  listeningNoticeBox: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 8,
    borderRadius: RADIUS.sm,
    borderWidth: 1,
    marginBottom: 8,
    gap: 6,
  },
  listeningNoticeText: { fontSize: 11, fontWeight: '600', flex: 1 },
  caseTextArea: {
    borderRadius: RADIUS.md,
    padding: 12,
    fontSize: 13,
    minHeight: 100,
    borderWidth: 1,
    lineHeight: 20,
  },
  exampleTitle: { fontSize: 11, fontWeight: '600', marginTop: 10, marginBottom: 6 },
  exampleScroll: { flexDirection: 'row', marginBottom: 12 },
  exampleChip: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: RADIUS.sm,
    borderWidth: 1,
    marginRight: 8,
    maxWidth: 240,
  },
  exampleText: { fontSize: 11 },
  analyzeBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: RADIUS.md,
    gap: 8,
  },
  analyzeBtnText: { color: '#FFFFFF', fontSize: 14, fontWeight: '800' },
  resultsContainer: { marginTop: SPACING.sm },
  tabNavScroll: { flexDirection: 'row', marginBottom: SPACING.sm },
  tabNavItem: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    marginRight: 8,
  },
  tabNavText: { fontSize: 12 },
  tabContentCard: {
    borderRadius: RADIUS.lg,
    padding: SPACING.md,
    borderWidth: 1,
  },
  outcomeHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 10,
    marginBottom: 10,
  },
  outcomeLabel: { fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  outcomeTitle: { fontSize: 15, fontWeight: '800', marginTop: 2, lineHeight: 22 },
  confidenceBadge: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: RADIUS.md,
    borderWidth: 1.5,
  },
  confidenceScore: { fontSize: 18, fontWeight: '900' },
  confidenceText: { fontSize: 9, fontWeight: '600', marginTop: 1 },
  progressBarTrack: { height: 6, borderRadius: 3, overflow: 'hidden', marginBottom: 12 },
  progressBarFill: { height: 6, borderRadius: 3 },
  infoBlock: { borderRadius: RADIUS.md, padding: 12, marginBottom: 10 },
  infoBlockTitle: { fontSize: 13, fontWeight: '800', marginBottom: 6 },
  infoBlockText: { fontSize: 12, lineHeight: 18 },
  bulletRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginTop: 6 },
  bulletDot: { width: 6, height: 6, borderRadius: 3, marginTop: 6 },
  bulletText: { flex: 1, fontSize: 12, lineHeight: 18 },
  actionStepRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 8 },
  stepNumCircle: { width: 22, height: 22, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  stepNum: { fontSize: 11, fontWeight: '800' },
  actionStepText: { flex: 1, fontSize: 12, fontWeight: '600' },
  tabHeaderTitle: { fontSize: 14, fontWeight: '800', marginBottom: 4 },
  tabHeaderSub: { fontSize: 11, marginBottom: 12 },
  lawCard: { borderRadius: RADIUS.md, padding: 12, borderWidth: 1, marginBottom: 10 },
  lawCardHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 },
  lawSectionTitle: { fontSize: 12, fontWeight: '800' },
  lawName: { fontSize: 13, fontWeight: '700', marginBottom: 2 },
  lawDesc: { fontSize: 12, lineHeight: 18 },
  biasRiskBanner: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12, borderRadius: RADIUS.md, borderWidth: 1 },
  biasRiskHeading: { fontSize: 13, fontWeight: '800' },
  biasRiskSub: { fontSize: 11, marginTop: 2 },
  precedentCard: { borderRadius: RADIUS.md, padding: 12, borderWidth: 1, marginBottom: 10 },
  liveCaseSearchBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    marginTop: 4,
  },
  liveCaseSearchTitle: {
    fontSize: FONT_SIZE.sm,
    fontWeight: '700',
  },
  liveCaseSearchSub: {
    fontSize: 10.5,
    marginTop: 2,
    lineHeight: 14,
  },
  precTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 6 },
  precTitle: { flex: 1, fontSize: 13, fontWeight: '800' },
  precWinBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.full },
  precWinText: { fontSize: 10, fontWeight: '700' },
  precCourt: { fontSize: 11, fontWeight: '600', marginTop: 4 },
  precSummary: { fontSize: 12, marginTop: 4, lineHeight: 18 },
  precFooter: { marginTop: 8, alignItems: 'flex-end' },
  tapInspectText: { fontSize: 11, fontWeight: '700' },
  courtStatGrid: { flexDirection: 'row', borderRadius: RADIUS.md, padding: 12, marginBottom: 10 },
  courtStatItem: { flex: 1 },
  courtStatLabel: { fontSize: 10, fontWeight: '800' },
  courtStatValue: { fontSize: 12, fontWeight: '700', marginTop: 2 },
  stepPathwayRow: { paddingVertical: 4 },
  stepPathwayText: { fontSize: 12, lineHeight: 18 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', padding: SPACING.md },
  modalCard: { borderRadius: RADIUS.xl, padding: SPACING.md, borderWidth: 1.5 },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 },
  modalTitle: { flex: 1, fontSize: 15, fontWeight: '800', marginRight: 10 },
  modalCourtName: { fontSize: 12, fontWeight: '700', marginBottom: 8 },
  modalOutcomeBox: { padding: 8, borderRadius: RADIUS.md, marginBottom: 10 },
  modalOutcomeText: { fontSize: 12, fontWeight: '800' },
  modalSectionHeading: { fontSize: 12, fontWeight: '800', marginTop: 10, marginBottom: 4 },
  modalBodyText: { fontSize: 12, lineHeight: 18 },
  modalLawsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 },
  modalLawTag: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: RADIUS.sm },
  modalLawTagText: { fontSize: 11, fontWeight: '700' },
  modalCloseBtn: { paddingVertical: 12, borderRadius: RADIUS.md, alignItems: 'center', marginTop: 14 },
  modalCloseBtnText: { color: '#FFFFFF', fontSize: 13, fontWeight: '800' },
});
