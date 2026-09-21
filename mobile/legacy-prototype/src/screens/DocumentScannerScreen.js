// CivicLens - Document Vision Scanner & OCR Analyzer

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  SafeAreaView,
  Image,
  ActivityIndicator,
  Alert,
  Platform,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS } from '../constants/theme';
import { analyzeDocumentImage } from '../services/aiService';

const DOC_TYPES = [
  { id: 'auto', name: '✨ On-Device Text Scan', icon: 'sparkles' },
  { id: 'challan', name: '🚗 Traffic E-Challan', icon: 'car-sport' },
  { id: 'notice', name: '🏢 Municipal Notice', icon: 'business' },
  { id: 'fir', name: '🚨 Police FIR Copy', icon: 'shield' },
  { id: 'invoice', name: '🧾 Bill / Invoice', icon: 'receipt' },
  { id: 'defect', name: '🛣️ Civic Defect Photo', icon: 'camera' },
];

export default function DocumentScannerScreen({ navigation }) {
  const { theme, t } = useApp();

  const [selectedDocType, setSelectedDocType] = useState('auto');
  const [selectedImage, setSelectedImage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState(null);

  const handlePickImage = async (useCamera = false) => {
    try {
      let result;
      if (useCamera) {
        const { status } = await ImagePicker.requestCameraPermissionsAsync();
        if (status !== 'granted') {
          Alert.alert('Permission Denied', 'Camera permission is required to snap documents.');
          return;
        }
        result = await ImagePicker.launchCameraAsync({
          mediaTypes: ImagePicker.MediaTypeOptions.Images,
          quality: 0.8,
        });
      } else {
        result = await ImagePicker.launchImageLibraryAsync({
          mediaTypes: ImagePicker.MediaTypeOptions.Images,
          quality: 0.8,
        });
      }

      if (!result.canceled && result.assets && result.assets.length > 0) {
        const asset = result.assets[0];
        setSelectedImage(asset.uri);
        handleAnalyzeDoc(asset, selectedDocType);
      }
    } catch (e) {
      console.log('Image picker error:', e);
    }
  };

  const handleAnalyzeDoc = async (asset, docType = selectedDocType) => {
    setLoading(true);
    setAnalysis(null);
    try {
      const res = await analyzeDocumentImage({
        imageUri: asset.uri,
        docType,
      });
      setAnalysis(res);
      if (!res.visionAnalysisAvailable && docType === 'auto') {
        Alert.alert(
          'On-Device Scan Found Nothing Usable',
          'Either no readable text was found in this photo, or on-device text recognition isn\'t available in this build (you may be running Expo Go instead of a dev client — see README). Pick the correct category above and try again for a tailored draft.'
        );
      }
    } catch (e) {
      Alert.alert('Analysis Failed', e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateComplaintFromDoc = () => {
    if (!analysis) return;
    navigation.navigate('Complaint', {
      tab: 'civic',
      initialText: `Regarding: ${analysis.documentType}\nAuthority: ${analysis.issuingAuthority}\nSection: ${analysis.statutorySection}\nDetails: ${analysis.plainSummary}`,
    });
  };

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={[styles.screenTitle, { color: theme.text }]}>
            📄 {t('scanDocument')}
          </Text>
          <Text style={[styles.screenSubtitle, { color: theme.textSecondary }]}>
            Scan notices, challans, FIRs & disputed bills with AI Vision & OCR
          </Text>
        </View>

        {/* Document Type Selector Chips */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.docTypeScroll}>
          {DOC_TYPES.map((dt) => {
            const isSelected = selectedDocType === dt.id;
            return (
              <TouchableOpacity
                key={dt.id}
                style={[
                  styles.docTypeChip,
                  {
                    backgroundColor: isSelected ? theme.primary : theme.card,
                    borderColor: isSelected ? theme.primary : theme.cardBorder,
                  },
                ]}
                onPress={() => {
                  setSelectedDocType(dt.id);
                  if (selectedImage) handleAnalyzeDoc(selectedImage, dt.id);
                }}
                activeOpacity={0.8}
              >
                <Text
                  style={[
                    styles.docTypeChipText,
                    { color: isSelected ? '#FFFFFF' : theme.textSecondary, fontWeight: isSelected ? '700' : '500' },
                  ]}
                >
                  {dt.name}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {/* Upload Action Area */}
        <View style={[styles.uploadCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
          {selectedImage ? (
            <View style={styles.imagePreviewContainer}>
              <Image source={{ uri: selectedImage }} style={styles.previewImage} resizeMode="contain" />
              <TouchableOpacity
                style={[styles.removeImageBtn, { backgroundColor: theme.accentRose }]}
                onPress={() => { setSelectedImage(null); setAnalysis(null); }}
              >
                <Ionicons name="trash" size={16} color="#FFFFFF" />
              </TouchableOpacity>
            </View>
          ) : (
            <View style={styles.uploadPlaceholder}>
              <Ionicons name="document-scanner-outline" size={48} color={theme.primary} />
              <Text style={[styles.uploadHeading, { color: theme.text }]}>
                Snap or Upload Official Document
              </Text>
              <Text style={[styles.uploadSub, { color: theme.textMuted }]}>
                Upload Traffic Challans, Municipal Notices, FIR copies, Utility Bills, or Civic Hazard Photos
              </Text>
            </View>
          )}

          {/* Button Actions */}
          <View style={styles.uploadActionsRow}>
            <TouchableOpacity
              style={[styles.uploadBtn, { backgroundColor: theme.primary }]}
              onPress={() => handlePickImage(true)}
              activeOpacity={0.85}
            >
              <Ionicons name="camera" size={18} color="#FFFFFF" />
              <Text style={styles.uploadBtnText}>Camera</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.uploadBtn, { backgroundColor: theme.surface, borderColor: theme.border, borderWidth: 1 }]}
              onPress={() => handlePickImage(false)}
              activeOpacity={0.85}
            >
              <Ionicons name="image" size={18} color={theme.text} />
              <Text style={[styles.uploadBtnText, { color: theme.text }]}>Gallery</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Loading Indicator */}
        {loading && (
          <View style={styles.loadingBox}>
            <ActivityIndicator size="large" color={theme.primary} />
            <Text style={[styles.loadingText, { color: theme.textSecondary }]}>
              AI Vision is inspecting document headers, seals & legal clauses...
            </Text>
          </View>
        )}

        {/* Analysis Output */}
        {analysis && (
          <>
            {!analysis.isValidDocument ? (
              /* Case 1: Unrelated / Non-Government Image Detected */
              <View style={[styles.invalidDocCard, { backgroundColor: theme.card, borderColor: theme.accentAmber }]}>
                <View style={styles.invalidHeaderRow}>
                  <View style={[styles.alertIconBadge, { backgroundColor: theme.accentAmber + '22' }]}>
                    <Ionicons name="alert-circle" size={24} color={theme.accentAmber} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.invalidTitle, { color: theme.accentAmber }]}>
                      ⚠️ Unrelated Image Detected
                    </Text>
                    <Text style={[styles.invalidSub, { color: theme.textSecondary }]}>
                      {analysis.classification || 'Non-Government / Everyday Photo'}
                    </Text>
                  </View>
                </View>

                <View style={[styles.infoBlock, { backgroundColor: theme.surface, borderColor: theme.border, borderWidth: 1 }]}>
                  <Text style={[styles.infoBlockTitle, { color: theme.text }]}>
                    🔍 Detection Summary:
                  </Text>
                  <Text style={[styles.infoBlockText, { color: theme.textSecondary }]}>
                    {analysis.plainSummary}
                  </Text>
                  {analysis.rejectionReason && (
                    <Text style={[styles.rejectionText, { color: theme.accentRose }]}>
                      • {analysis.rejectionReason}
                    </Text>
                  )}
                </View>

                <View style={[styles.guidanceCard, { backgroundColor: theme.primaryGlow, borderColor: theme.primary }]}>
                  <Ionicons name="information-circle-outline" size={18} color={theme.primary} />
                  <Text style={[styles.guidanceText, { color: theme.text }]}>
                    <Text style={{ fontWeight: '800', color: theme.primary }}>How to proceed:</Text> {analysis.guidance}
                  </Text>
                </View>

                <Text style={[styles.supportedTitle, { color: theme.textMuted }]}>
                  Supported Document Types:
                </Text>
                <View style={styles.examplesGrid}>
                  {analysis.supportedExamples?.map((ex, i) => (
                    <View key={i} style={[styles.exampleChip, { backgroundColor: theme.surface, borderColor: theme.border }]}>
                      <Text style={[styles.exampleText, { color: theme.text }]}>{ex}</Text>
                    </View>
                  ))}
                </View>
              </View>
            ) : (
              /* Case 2: Verified Government Document / Civic Issue */
              <View style={[styles.analysisCard, { backgroundColor: theme.card, borderColor: theme.primary }]}>
                <View style={[styles.verificationSourceBadge, { backgroundColor: analysis.visionAnalysisAvailable ? 'rgba(46,158,99,0.15)' : 'rgba(191,107,61,0.15)' }]}>
                  <Ionicons
                    name={analysis.visionAnalysisAvailable ? 'text' : 'hand-left'}
                    size={12}
                    color={analysis.visionAnalysisAvailable ? '#2E9E63' : '#BF6B3D'}
                  />
                  <Text style={[styles.verificationSourceText, { color: analysis.visionAnalysisAvailable ? '#2E9E63' : '#BF6B3D' }]}>
                    {analysis.visionAnalysisAvailable
                      ? 'Matched from real on-device text recognition (free, runs on your device)'
                      : 'Based on your manual category selection'}
                  </Text>
                </View>

                <View style={styles.analysisHeader}>
                  <View style={styles.docTypeBadge}>
                    <Ionicons name="shield-checkmark" size={16} color={theme.primary} />
                    <Text style={[styles.docTypeText, { color: theme.primary }]}>
                      {analysis.documentType}
                    </Text>
                  </View>
                  <View style={[styles.deadlineBadge, { backgroundColor: theme.accentRose + '22' }]}>
                    <Ionicons name="time" size={12} color={theme.accentRose} />
                    <Text style={[styles.deadlineText, { color: theme.accentRose }]}>
                      {analysis.deadlineDays}
                    </Text>
                  </View>
                </View>

                {/* Quick Metrics Grid */}
                <View style={[styles.docStatGrid, { backgroundColor: theme.surface }]}>
                  <View style={styles.docStatItem}>
                    <Text style={[styles.docStatLabel, { color: theme.textMuted }]}>ISSUING AUTHORITY</Text>
                    <Text style={[styles.docStatValue, { color: theme.text }]}>
                      {analysis.issuingAuthority}
                    </Text>
                  </View>
                  <View style={styles.docStatItem}>
                    <Text style={[styles.docStatLabel, { color: theme.textMuted }]}>STATUTORY LAW</Text>
                    <Text style={[styles.docStatValue, { color: theme.accentPurple }]}>
                      {analysis.statutorySection}
                    </Text>
                  </View>
                </View>

                {/* Plain Summary */}
                <View style={[styles.infoBlock, { backgroundColor: theme.surface }]}>
                  <Text style={[styles.infoBlockTitle, { color: theme.text }]}>
                    📋 Citizen Plain-Language Summary
                  </Text>
                  <Text style={[styles.infoBlockText, { color: theme.textSecondary }]}>
                    {analysis.plainSummary}
                  </Text>
                </View>

                {/* Critical Warnings */}
                {analysis.criticalWarnings && (
                  <View style={[styles.infoBlock, { backgroundColor: theme.accentAmber + '15' }]}>
                    <Text style={[styles.infoBlockTitle, { color: theme.accentAmber }]}>
                      ⚠️ Legal Risk & Compliance Warnings
                    </Text>
                    {analysis.criticalWarnings.map((w, i) => (
                      <View key={i} style={styles.bulletRow}>
                        <Text style={[styles.bulletText, { color: theme.textSecondary }]}>• {w}</Text>
                      </View>
                    ))}
                  </View>
                )}

                {/* Recommended Next Steps */}
                {analysis.recommendedNextSteps && (
                  <View style={[styles.infoBlock, { backgroundColor: theme.surface }]}>
                    <Text style={[styles.infoBlockTitle, { color: theme.text }]}>
                      🎯 Recommended Action Steps
                    </Text>
                    {analysis.recommendedNextSteps.map((s, i) => (
                      <Text key={i} style={[styles.bulletText, { color: theme.text, marginTop: 4 }]}>
                        {s}
                      </Text>
                    ))}
                  </View>
                )}

                {/* 1-Click Action Button */}
                <TouchableOpacity
                  style={[styles.actionCtaBtn, { backgroundColor: theme.primary }]}
                  onPress={handleGenerateComplaintFromDoc}
                  activeOpacity={0.85}
                >
                  <Ionicons name="document-text" size={18} color="#FFFFFF" />
                  <Text style={styles.actionCtaText}>
                    📝 Draft Formal Reply / Complaint for this Document
                  </Text>
                </TouchableOpacity>
              </View>
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  scrollContent: { paddingHorizontal: SPACING.md, paddingBottom: 260 },
  header: { paddingTop: Platform.OS === 'android' ? 30 : 10, marginBottom: SPACING.sm },
  screenTitle: { fontSize: 20, fontWeight: '800' },
  screenSubtitle: { fontSize: 12, marginTop: 3 },
  docTypeScroll: { flexDirection: 'row', marginBottom: SPACING.md },
  docTypeChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: RADIUS.full,
    borderWidth: 1,
    marginRight: 8,
  },
  docTypeChipText: { fontSize: 12 },
  uploadCard: {
    borderRadius: RADIUS.lg,
    padding: SPACING.md,
    borderWidth: 1,
    alignItems: 'center',
    marginBottom: SPACING.md,
  },
  uploadPlaceholder: { alignItems: 'center', paddingVertical: 20 },
  uploadHeading: { fontSize: 14, fontWeight: '800', marginTop: 10 },
  uploadSub: { fontSize: 11, textAlign: 'center', marginTop: 4, paddingHorizontal: 20 },
  imagePreviewContainer: { width: '100%', height: 220, position: 'relative', marginBottom: 12 },
  previewImage: { width: '100%', height: '100%', borderRadius: RADIUS.md },
  removeImageBtn: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  uploadActionsRow: { flexDirection: 'row', gap: 12, width: '100%', marginTop: 8 },
  uploadBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: RADIUS.md,
    gap: 6,
  },
  uploadBtnText: { color: '#FFFFFF', fontSize: 13, fontWeight: '800' },
  loadingBox: { alignItems: 'center', paddingVertical: 20, gap: 10 },
  loadingText: { fontSize: 12 },
  analysisCard: {
    borderRadius: RADIUS.lg,
    padding: SPACING.md,
    borderWidth: 1.5,
    marginBottom: SPACING.lg,
  },
  analysisHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  verificationSourceBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    alignSelf: 'flex-start',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: RADIUS.full,
    marginBottom: 10,
  },
  verificationSourceText: {
    fontSize: 10,
    fontWeight: '700',
  },
  docTypeBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1, paddingRight: 8 },
  docTypeText: { fontSize: 13, fontWeight: '800' },
  deadlineBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  deadlineText: { fontSize: 11, fontWeight: '700' },
  docStatGrid: { flexDirection: 'row', borderRadius: RADIUS.md, padding: 10, marginBottom: 10 },
  docStatItem: { flex: 1 },
  docStatLabel: { fontSize: 9, fontWeight: '800' },
  docStatValue: { fontSize: 11, fontWeight: '700', marginTop: 2 },
  infoBlock: { borderRadius: RADIUS.md, padding: 12, marginBottom: 10 },
  infoBlockTitle: { fontSize: 12, fontWeight: '800', marginBottom: 6 },
  infoBlockText: { fontSize: 12, lineHeight: 18 },
  bulletRow: { marginTop: 4 },
  bulletText: { fontSize: 12, lineHeight: 18 },
  actionCtaBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 13,
    borderRadius: RADIUS.md,
    gap: 8,
    marginTop: 4,
  },
  actionCtaText: { color: '#FFFFFF', fontSize: 13, fontWeight: '800' },
  invalidDocCard: {
    borderRadius: RADIUS.lg,
    padding: SPACING.md,
    borderWidth: 1.5,
    marginBottom: SPACING.lg,
  },
  invalidHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
  },
  alertIconBadge: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  invalidTitle: { fontSize: 14, fontWeight: '800' },
  invalidSub: { fontSize: 11, marginTop: 2 },
  rejectionText: { fontSize: 11, marginTop: 6, fontWeight: '600' },
  guidanceCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 10,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    gap: 8,
    marginBottom: 12,
  },
  guidanceText: { fontSize: 11, flex: 1, lineHeight: 16 },
  supportedTitle: { fontSize: 11, fontWeight: '700', marginBottom: 6 },
  examplesGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  exampleChip: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: RADIUS.sm,
    borderWidth: 1,
  },
  exampleText: { fontSize: 11 },
});
