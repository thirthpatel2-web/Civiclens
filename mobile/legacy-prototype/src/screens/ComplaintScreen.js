// CivicLens - Legal Complaint & RTI 2005 Generator Screen
// Featuring AI-Driven Dynamic Fact Formulation & Direct PIO Email Dispatch

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
  KeyboardAvoidingView,
  Platform,
  Share,
  Alert,
  Linking,
  Switch,
  Modal,
  Image,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE } from '../constants/theme';
import {
  DEPARTMENTS_BY_CITY,
  ALL_PUBLIC_AUTHORITIES,
  DEPARTMENT_TIERS,
  detectDepartment,
} from '../data/departmentsData';
import { generateComplaintLetter, generateRTIDraft } from '../services/aiService';
import { exportLetterToPdf, generatePdfBase64 } from '../services/pdfService';
import { sendEmail } from '../services/emailService';
import VoiceListeningModal from '../components/VoiceListeningModal';

const QUICK_EXAMPLES = [
  'Deep pothole on 27th Main HSR causing accidents for 2 weeks',
  'Garbage dump overflow in front of school gate Indiranagar',
  'Low voltage power supply and transformer sparks BESCOM',
  'Contaminated muddy drinking water pipeline BWSSB',
  'Delayed municipal road asphalt tender inspection',
];

// Helper to formulate dynamic clarifying questions based on user's grievance
function getDynamicRTIQuestions(issueText) {
  const lower = (issueText || '').toLowerCase();

  if (lower.includes('pothole') || lower.includes('road') || lower.includes('asphalt') || lower.includes('pavement') || lower.includes('footpath')) {
    return {
      category: 'Roads & Infrastructure',
      defaultRecords: [
        'Certified copy of Measurement Book (MB Book) entries',
        'Asphalt Quality & Strength Lab Test Reports',
        'Daily Work Progress Register & Completion Deadlines',
        'Contractor Delay Penalty Ledger',
      ],
      timePeriodDefault: 'FY 2024-2025',
      tenderPlaceholder: 'e.g. BBMP/EE/RD/WO/2024-25/1042 or "Unknown"',
      emergencyRecommended: lower.includes('accident') || lower.includes('danger') || lower.includes('risk'),
      promptTip: 'Demanding Measurement Books & Lab Strength Reports prevents contractor substandard materials.',
    };
  }

  if (lower.includes('water') || lower.includes('pipeline') || lower.includes('sewage') || lower.includes('drain') || lower.includes('bwssb')) {
    return {
      category: 'Water Supply & Sanitation',
      defaultRecords: [
        'Bacteriological & Chemical Water Quality Test Reports',
        'Pipeline Replacement Tender Work Order & Estimates',
        'Valve Operation & Pressure Maintenance Inspection Log',
        'Budget Sanctioned vs Funds Utilized Ledger',
      ],
      timePeriodDefault: 'Past 6 Months',
      tenderPlaceholder: 'e.g. BWSSB/WTR/MAINT/2024 or "Unknown"',
      emergencyRecommended: lower.includes('contaminated') || lower.includes('muddy') || lower.includes('poison'),
      promptTip: 'Demanding Water Test Reports provides legal evidence of potable water duty breach.',
    };
  }

  if (lower.includes('electricity') || lower.includes('power') || lower.includes('transformer') || lower.includes('bescom') || lower.includes('wire') || lower.includes('voltage')) {
    return {
      category: 'Electricity & Public Utilities',
      defaultRecords: [
        'Transformer Load Audit & Capacity Certification',
        'Voltage Fluctuation & Outage Maintenance Log',
        'Scheduled Preventive Maintenance Job Cards',
        'Safety Audit Report of Overhead Electrical Lines',
      ],
      timePeriodDefault: 'Past 12 Months',
      tenderPlaceholder: 'e.g. BESCOM/TR/WO/2024 or "Unknown"',
      emergencyRecommended: lower.includes('spark') || lower.includes('shock') || lower.includes('fire'),
      promptTip: 'Demanding Load Audit Reports proves grid negligence.',
    };
  }

  if (lower.includes('police') || lower.includes('fir') || lower.includes('theft') || lower.includes('assault') || lower.includes('station')) {
    return {
      category: 'Police & Law Enforcement',
      defaultRecords: [
        'Certified copy of Station General Diary (GD) entry',
        'Reason recorded on file for non-registration of Zero FIR',
        'Station Duty Officer Log on date of complaint',
        'CCTV Preservation Memo for police station premises',
      ],
      timePeriodDefault: 'Incident Date',
      tenderPlaceholder: 'e.g. GD No. / Station Memo No.',
      emergencyRecommended: true,
      promptTip: 'Invoking General Diary extracts establishes non-cognizable / cognizable duty breach.',
    };
  }

  // Default General Public Governance RTI Framework
  return {
    category: 'Public Works & Governance',
    defaultRecords: [
      'Certified copy of Sanctioned Work Order & Technical Sanction',
      'Measurement Book (MB Book) and Quality Lab Test Reports',
      'Name & Designation of Junior & Executive Engineers in charge',
      'Total Budget Allocated vs Expenditure Disbursed',
    ],
    timePeriodDefault: 'Current Financial Year',
    tenderPlaceholder: 'e.g. Tender Ref or "Unknown"',
    emergencyRecommended: false,
    promptTip: 'Demanding Work Orders and Engineer names ensures direct individual officer accountability.',
  };
}

export default function ComplaintScreen({ route, navigation }) {
  const {
    theme,
    t,
    userProfile,
    selectedCity,
    addComplaint,
    language,
    getCityName,
  } = useApp();

  const [activeTab, setActiveTab] = useState(route.params?.tab || 'civic'); // 'civic' or 'rti'
  const [issueText, setIssueText] = useState(route.params?.initialText || '');
  const [incidentLocation, setIncidentLocation] = useState('');
  const [selectedDept, setSelectedDept] = useState(null);
  const [selectedTier, setSelectedTier] = useState('all');
  const [prefillEnabled, setPrefillEnabled] = useState(true);
  const [draftLanguage, setDraftLanguage] = useState(language);
  const [voiceModalVisible, setVoiceModalVisible] = useState(false);

  // ---- Phase 3: Photo Evidence ----------------------------------------
  // imageAsset carries exactly what apiClient's multipart helper needs
  // (uri/name/type) — see services/trackingService.js saveNewComplaint.
  const [imageAsset, setImageAsset] = useState(null); // { uri, name, type } | null

  // ---- Phase 3: Precise Location ---------------------------------------
  const [coords, setCoords] = useState(null); // { lat, lng } | null
  const [address, setAddress] = useState('');
  const [wardNumber, setWardNumber] = useState('');
  const [cityText, setCityText] = useState('');
  const [locationLoading, setLocationLoading] = useState(false);
  const [reverseGeocodeAvailable, setReverseGeocodeAvailable] = useState(true);

  // Dynamic AI Clarification State
  const [analysisActive, setAnalysisActive] = useState(false);
  const [aiAnalysisResult, setAiAnalysisResult] = useState(null);
  const [tenderWorkOrder, setTenderWorkOrder] = useState('');
  const [timePeriod, setTimePeriod] = useState('FY 2024-2025');
  const [selectedRecords, setSelectedRecords] = useState([]);
  const [emergency48Hr, setEmergency48Hr] = useState(false);

  // Generation & Results
  const [loading, setLoading] = useState(false);
  const [generatedResult, setGeneratedResult] = useState(null);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState(false);
  // AI classification/priority returned by the backend when a complaint is
  // filed. Null unless the server actually produced one — never a
  // client-side guess.
  const [aiResult, setAiResult] = useState(null);
  const [pdfExporting, setPdfExporting] = useState(false);
  const [isSendingEmail, setIsSendingEmail] = useState(false);

  // Quick Direct Email Modal State
  const [emailModalVisible, setEmailModalVisible] = useState(false);

  const cityDepartments = DEPARTMENTS_BY_CITY[selectedCity] || DEPARTMENTS_BY_CITY['bengaluru'];

  const filteredDepartments = ALL_PUBLIC_AUTHORITIES.filter((d) => {
    if (selectedTier === 'all') {
      return (
        d.city === selectedCity ||
        d.tier === 'central' ||
        d.tier === 'state' ||
        d.tier === 'regulatory' ||
        d.tier === 'psu'
      );
    }
    return d.tier === selectedTier;
  });

  useEffect(() => {
    if (route.params?.tab) {
      setActiveTab(route.params.tab);
    }
    if (route.params?.initialText) {
      setIssueText(route.params.initialText);
      const matched = detectDepartment(selectedCity, route.params.initialText);
      setSelectedDept(matched);
      triggerDynamicAnalysis(route.params.initialText);
    } else if (!selectedDept && cityDepartments.length > 0) {
      setSelectedDept(cityDepartments[0]);
    }
  }, [route.params, selectedCity]);

  // Trigger dynamic AI inspection on complaint text
  const triggerDynamicAnalysis = (text) => {
    if (text && text.trim().length >= 8) {
      const dynamicQ = getDynamicRTIQuestions(text);
      setAiAnalysisResult(dynamicQ);
      setSelectedRecords(dynamicQ.defaultRecords);
      setTimePeriod(dynamicQ.timePeriodDefault);
      setEmergency48Hr(dynamicQ.emergencyRecommended);
      setAnalysisActive(true);
    }
  };

  const handleIssueChange = (text) => {
    setIssueText(text);
    if (text.length > 8) {
      const autoMatched = detectDepartment(selectedCity, text);
      if (autoMatched) setSelectedDept(autoMatched);
      triggerDynamicAnalysis(text);
    }
  };

  const handleVoiceResult = (transcript) => {
    setIssueText(transcript);
    const autoMatched = detectDepartment(selectedCity, transcript);
    if (autoMatched) setSelectedDept(autoMatched);
    triggerDynamicAnalysis(transcript);
  };

  // ---- Phase 3: Photo Evidence ------------------------------------------
  // Reuses the exact camera/gallery pattern already used by
  // DocumentScannerScreen.js (same expo-image-picker calls, same
  // permission-request shape) rather than inventing a second one.
  const handlePickEvidenceImage = async (useCamera = false) => {
    try {
      let result;
      if (useCamera) {
        const { status } = await ImagePicker.requestCameraPermissionsAsync();
        if (status !== 'granted') {
          Alert.alert('Permission Denied', 'Camera permission is required to photograph the issue.');
          return;
        }
        result = await ImagePicker.launchCameraAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.8 });
      } else {
        const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
        if (status !== 'granted') {
          Alert.alert('Permission Denied', 'Photo library access is required to choose an evidence photo.');
          return;
        }
        result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.8 });
      }

      if (!result.canceled && result.assets && result.assets.length > 0) {
        const asset = result.assets[0];
        const fileName = asset.fileName || `evidence-${Date.now()}.jpg`;
        const mimeType = asset.mimeType || (fileName.toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg');
        setImageAsset({ uri: asset.uri, name: fileName, type: mimeType });
      }
    } catch (e) {
      console.log('Evidence image picker error:', e);
      Alert.alert('Could Not Open Camera/Gallery', e.message);
    }
  };

  const handleRemoveEvidenceImage = () => setImageAsset(null);

  // ---- Phase 3: Precise Location ----------------------------------------
  // Captures real GPS coordinates, then best-effort reverse-geocodes
  // them to an address/city using expo-location's on-device geocoder.
  // Ward number is NEVER derived from this — this project has no
  // ward-boundary API, so ward stays a citizen-entered/verified field
  // regardless of whether reverse geocoding succeeds. If reverse
  // geocoding fails or is unavailable, the coordinates are still kept
  // and the citizen can fill in / correct the address manually.
  const handleUseCurrentLocation = async () => {
    setLocationLoading(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Denied', 'Location permission is required to attach your precise location to this complaint.');
        return;
      }

      const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      const lat = position.coords.latitude;
      const lng = position.coords.longitude;
      setCoords({ lat, lng });

      try {
        const [place] = await Location.reverseGeocodeAsync({ latitude: lat, longitude: lng });
        if (place) {
          const line = [place.streetNumber, place.street, place.district, place.subregion]
            .filter(Boolean)
            .join(', ');
          if (line) setAddress(line);
          if (place.city) setCityText(place.city);
          setReverseGeocodeAvailable(true);
        }
      } catch (geocodeErr) {
        // Not fatal — coordinates remain the authoritative location;
        // the citizen enters/verifies the address manually instead.
        console.log('Reverse geocoding unavailable:', geocodeErr.message);
        setReverseGeocodeAvailable(false);
      }
    } catch (e) {
      Alert.alert('Could Not Get Location', e.message || 'Please ensure location services are enabled.');
    } finally {
      setLocationLoading(false);
    }
  };

  const toggleRecordSelection = (record) => {
    if (selectedRecords.includes(record)) {
      setSelectedRecords(selectedRecords.filter((r) => r !== record));
    } else {
      setSelectedRecords([...selectedRecords, record]);
    }
  };

  // Generate Document
  const handleGenerate = async () => {
    if (!issueText.trim() || issueText.trim().length < 6) {
      Alert.alert('Incomplete Description', 'Please describe your grievance/inquiry in at least 6 characters.');
      return;
    }

    setLoading(true);
    setGeneratedResult(null);
    setSaveSuccessMsg(false);

    const userDetails = prefillEnabled ? userProfile : {};

    try {
      if (activeTab === 'civic') {
        const res = await generateComplaintLetter({
          issue: issueText,
          category: selectedDept?.category,
          department: selectedDept,
          city: selectedCity,
          userDetails,
          language: draftLanguage,
          incidentLocation: incidentLocation.trim() || `${selectedCity.toUpperCase()} Jurisdiction`,
          tenderWorkOrder: tenderWorkOrder.trim(),
        });
        setGeneratedResult(res.letter);
      } else {
        const res = await generateRTIDraft({
          issue: issueText,
          department: selectedDept,
          city: selectedCity,
          userDetails,
          language: draftLanguage,
          siteLocation: incidentLocation.trim() || `${selectedCity.toUpperCase()} Ward Jurisdiction`,
          tenderWorkOrder: tenderWorkOrder.trim(),
          timePeriod: timePeriod.trim(),
          recordsRequested: selectedRecords,
          emergency48Hr: emergency48Hr,
        });
        setGeneratedResult(res.rtiDraft);
      }
    } catch (e) {
      Alert.alert('Draft Error', e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyToClipboard = async () => {
    if (generatedResult) {
      await Clipboard.setStringAsync(generatedResult);
      Alert.alert('Copied', 'Document copied to clipboard!');
    }
  };

  const handleShareDocument = async () => {
    if (generatedResult) {
      await Share.share({
        message: generatedResult,
        title: activeTab === 'civic' ? 'Civic Complaint Draft' : 'RTI Application Draft',
      });
    }
  };

  const handleSaveToTracker = async () => {
    if (generatedResult) {
      setAiResult(null);
      const res = await addComplaint({
        title: `${selectedDept?.name || 'Grievance'}: ${issueText.slice(0, 35)}...`,
        category: selectedDept?.category || 'Civic Infrastructure',
        department: selectedDept?.name || 'Municipal Corporation',
        departmentId: selectedDept?.id || 'bbmp_roads',
        issue: issueText,
        letterText: generatedResult,
        type: activeTab,
        tenderNo: tenderWorkOrder || null,
        targetEmail: selectedDept?.email || 'pio@gov.in',
        // Phase 3 — evidence photo + precise location (civic complaints only;
        // all four are optional, so RTI submissions and complaints filed
        // without photo/GPS behave exactly as before).
        imageAsset: activeTab === 'civic' ? imageAsset : null,
        lat: coords?.lat ?? null,
        lng: coords?.lng ?? null,
        address: address.trim() || null,
        wardNumber: wardNumber.trim() || null,
        city: cityText.trim() || selectedCity,
      });

      if (res.success) {
        setSaveSuccessMsg(true);
        setTimeout(() => setSaveSuccessMsg(false), 4000);
        // Surface the backend's AI classification/priority if it came
        // back. It is absent when the complaint saved offline-only or
        // when the AI step failed server-side (which never blocks the
        // save) — in that case nothing is shown rather than a guess.
        const g = res.grievance || {};
        if (g.aiClassification || g.priority || g.priorityReasoning) {
          setAiResult({
            classification: g.aiClassification,
            priority: g.priority,
            severity: g.severity,
            reasoning: g.priorityReasoning,
            confirmed: g.aiClassificationConfirmed,
            duplicates: g.duplicateRelationships,
          });
        }
      }
    }
  };

  const handleExportPdf = async () => {
    if (!generatedResult || pdfExporting) return;
    setPdfExporting(true);
    try {
      const res = await exportLetterToPdf({
        letterText: generatedResult,
        docType: activeTab === 'civic' ? 'Civic Grievance Petition' : 'RTI Application',
        department: selectedDept,
        city: selectedCity,
      });
      if (!res.success) {
        Alert.alert('Export Failed', res.error || 'Could not generate PDF.');
      }
    } catch (e) {
      Alert.alert('Export Failed', e.message);
    } finally {
      setPdfExporting(false);
    }
  };

  // Direct Send Official Email Action — tries a real automatic send with
  // the PDF attached first, falls back to opening the person's own email
  // app (no attachment possible that way) if the real send isn't
  // configured or fails.
  const handleLaunchEmailClient = async () => {
    if (!generatedResult || isSendingEmail) return;
    setIsSendingEmail(true);
    const recipient = selectedDept?.email || 'nodal.officer@gov.in';
    const subject =
      activeTab === 'civic'
        ? `Statutory Grievance: ${issueText.slice(0, 40)} [${selectedCity.toUpperCase()}]`
        : `RTI Application under Section 6(1): ${issueText.slice(0, 35)}`;

    try {
      const pdfResult = await generatePdfBase64({
        letterText: generatedResult,
        docType: activeTab === 'civic' ? 'Civic Grievance Petition' : 'RTI Application',
        department: selectedDept,
        city: selectedCity,
      });

      const result = await sendEmail({
        to: recipient,
        subject,
        body: generatedResult,
        attachmentBase64: pdfResult.success ? pdfResult.base64 : undefined,
        attachmentFilename: pdfResult.success ? pdfResult.filename : undefined,
      });

      setEmailModalVisible(false);
      if (result.sentAutomatically) {
        Alert.alert(
          'Email Sent',
          `Statutory draft automatically sent to ${selectedDept?.name || 'Department'} (${recipient})${pdfResult.success ? ' with the PDF attached.' : '.'}`
        );
      } else {
        Alert.alert(
          'Email Opened in Your App',
          `Real automatic sending isn't connected yet, so this opened a pre-filled draft to ${recipient} in your own email app instead — please attach the exported PDF manually if needed, and hit send.`
        );
      }
    } catch (e) {
      Alert.alert('Notice', 'Unable to send or open email. You can use the Copy button instead.');
    } finally {
      setIsSendingEmail(false);
    }
  };

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
        style={{ flex: 1 }}
      >
        <ScrollView
          showsVerticalScrollIndicator={false}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          {/* Header Title */}
          <View style={styles.header}>
            <Text style={[styles.screenTitle, { color: theme.text }]}>
              {activeTab === 'civic' ? '📝 ' + t('fileComplaint') : '🏛️ ' + t('fileRTI')}
            </Text>
            <Text style={[styles.screenSubtitle, { color: theme.textSecondary }]}>
              {activeTab === 'civic' ? t('fileComplaintSub') : t('fileRTISub')}
            </Text>
          </View>

          {/* Segmented Tab Switcher (Civic vs RTI) */}
          <View style={[styles.tabContainer, { backgroundColor: theme.surface, borderColor: theme.border }]}>
            <TouchableOpacity
              style={[styles.tabButton, activeTab === 'civic' && { backgroundColor: theme.primary }]}
              onPress={() => {
                setActiveTab('civic');
                setGeneratedResult(null);
              }}
              activeOpacity={0.8}
            >
              <Ionicons
                name="document-text-outline"
                size={16}
                color={activeTab === 'civic' ? '#FFFFFF' : theme.textMuted}
              />
              <Text style={[styles.tabButtonText, { color: activeTab === 'civic' ? '#FFFFFF' : theme.textSecondary }]}>
                {t('tabCivic')}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.tabButton, activeTab === 'rti' && { backgroundColor: theme.accentSaffron }]}
              onPress={() => {
                setActiveTab('rti');
                setGeneratedResult(null);
                if (issueText) triggerDynamicAnalysis(issueText);
              }}
              activeOpacity={0.8}
            >
              <Ionicons
                name="business-outline"
                size={16}
                color={activeTab === 'rti' ? '#FFFFFF' : theme.textMuted}
              />
              <Text style={[styles.tabButtonText, { color: activeTab === 'rti' ? '#FFFFFF' : theme.textSecondary }]}>
                {t('tabRTI')} (2005)
              </Text>
            </TouchableOpacity>
          </View>

          {/* STEP 1: GRIEVANCE INTAKE INPUT CARD */}
          <View style={[styles.inputCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
            <View style={styles.inputHeaderRow}>
              <Text style={[styles.stepBadge, { backgroundColor: theme.primaryGlow, color: theme.primaryLight }]}>
                STEP 1
              </Text>
              <Text style={[styles.inputLabel, { color: theme.text, flex: 1, marginLeft: 8 }]}>
                {t('describeIssue')}
              </Text>
              <TouchableOpacity
                style={[styles.voiceInputBtn, { backgroundColor: theme.primary }]}
                onPress={() => setVoiceModalVisible(true)}
                activeOpacity={0.85}
              >
                <Ionicons name="mic" size={14} color="#FFFFFF" />
                <Text style={styles.voiceInputText}>{t('voiceRecording')}</Text>
              </TouchableOpacity>
            </View>

            <TextInput
              style={[
                styles.textArea,
                { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border },
              ]}
              placeholder={t('issuePlaceholder')}
              placeholderTextColor={theme.textMuted}
              value={issueText}
              onChangeText={handleIssueChange}
              multiline
              numberOfLines={4}
            />

            {/* Quick Example Chips */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.exampleScroll}>
              {QUICK_EXAMPLES.map((ex, i) => (
                <TouchableOpacity
                  key={i}
                  style={[styles.exampleChip, { backgroundColor: theme.surface, borderColor: theme.border }]}
                  onPress={() => handleIssueChange(ex)}
                  activeOpacity={0.75}
                >
                  <Text style={[styles.exampleText, { color: theme.textSecondary }]}>
                    💡 {ex}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            {/* Incident Location Landmark Input */}
            <View style={{ marginTop: 10 }}>
              <Text style={[styles.subFieldLabel, { color: theme.textSecondary }]}>
                📍 Specific Site / Landmark / Ward:
              </Text>
              <TextInput
                style={[styles.singleLineInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                placeholder="e.g. 27th Main HSR Layout, near Police Station"
                placeholderTextColor={theme.textMuted}
                value={incidentLocation}
                onChangeText={setIncidentLocation}
              />
            </View>
          </View>

          {/* ========================================================= */}
          {/* PHOTO EVIDENCE + PRECISE LOCATION (Phase 3, civic only)     */}
          {/* ========================================================= */}
          {activeTab === 'civic' && (
            <View style={[styles.inputCard, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
              <Text style={[styles.inputLabel, { color: theme.text, marginBottom: 8 }]}>
                📷 Photo Evidence (optional)
              </Text>

              {imageAsset ? (
                <View style={styles.evidencePreviewRow}>
                  <Image source={{ uri: imageAsset.uri }} style={styles.evidencePreviewImage} />
                  <View style={{ flex: 1, gap: 6 }}>
                    <TouchableOpacity
                      style={[styles.evidenceSmallBtn, { backgroundColor: theme.surface, borderColor: theme.border }]}
                      onPress={() => handlePickEvidenceImage(false)}
                      activeOpacity={0.8}
                    >
                      <Ionicons name="swap-horizontal-outline" size={14} color={theme.text} />
                      <Text style={[styles.evidenceSmallBtnText, { color: theme.text }]}>Replace</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.evidenceSmallBtn, { backgroundColor: 'rgba(194, 69, 69, 0.12)', borderColor: '#C24545' }]}
                      onPress={handleRemoveEvidenceImage}
                      activeOpacity={0.8}
                    >
                      <Ionicons name="trash-outline" size={14} color="#C24545" />
                      <Text style={[styles.evidenceSmallBtnText, { color: '#C24545' }]}>Remove</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ) : (
                <View style={styles.evidenceBtnRow}>
                  <TouchableOpacity
                    style={[styles.evidenceBtn, { backgroundColor: theme.surface, borderColor: theme.border }]}
                    onPress={() => handlePickEvidenceImage(true)}
                    activeOpacity={0.8}
                  >
                    <Ionicons name="camera-outline" size={16} color={theme.text} />
                    <Text style={[styles.evidenceBtnText, { color: theme.text }]}>Take Photo</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.evidenceBtn, { backgroundColor: theme.surface, borderColor: theme.border }]}
                    onPress={() => handlePickEvidenceImage(false)}
                    activeOpacity={0.8}
                  >
                    <Ionicons name="images-outline" size={16} color={theme.text} />
                    <Text style={[styles.evidenceBtnText, { color: theme.text }]}>Choose from Gallery</Text>
                  </TouchableOpacity>
                </View>
              )}

              <View style={{ height: 1, backgroundColor: theme.border, marginVertical: 14 }} />

              <Text style={[styles.inputLabel, { color: theme.text, marginBottom: 8 }]}>
                📍 Precise Location
              </Text>

              <TouchableOpacity
                style={[styles.evidenceBtn, { backgroundColor: coords ? 'rgba(46, 158, 99, 0.12)' : theme.surface, borderColor: coords ? theme.accentEmerald : theme.border, alignSelf: 'flex-start' }]}
                onPress={handleUseCurrentLocation}
                activeOpacity={0.8}
                disabled={locationLoading}
              >
                {locationLoading ? (
                  <ActivityIndicator size="small" color={theme.text} />
                ) : (
                  <Ionicons name="locate" size={16} color={coords ? theme.accentEmerald : theme.text} />
                )}
                <Text style={[styles.evidenceBtnText, { color: coords ? theme.accentEmerald : theme.text }]}>
                  {locationLoading ? 'Getting location…' : coords ? 'Location Captured — Refresh' : 'Use Current Location'}
                </Text>
              </TouchableOpacity>

              {coords && (
                <Text style={[styles.subFieldLabel, { color: theme.textMuted, marginTop: 6 }]}>
                  📌 Lat: {coords.lat.toFixed(6)}, Lng: {coords.lng.toFixed(6)}
                  {!reverseGeocodeAvailable ? ' — address not auto-detected, please enter it below' : ''}
                </Text>
              )}

              <View style={{ marginTop: 10 }}>
                <Text style={[styles.subFieldLabel, { color: theme.textSecondary }]}>Address:</Text>
                <TextInput
                  style={[styles.singleLineInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                  placeholder="Street / area, as precisely as possible"
                  placeholderTextColor={theme.textMuted}
                  value={address}
                  onChangeText={setAddress}
                />
              </View>

              <View style={styles.formRow}>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.subFieldLabel, { color: theme.textSecondary }]}>City:</Text>
                  <TextInput
                    style={[styles.singleLineInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                    placeholder={getCityName ? getCityName(selectedCity) : selectedCity}
                    placeholderTextColor={theme.textMuted}
                    value={cityText}
                    onChangeText={setCityText}
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.subFieldLabel, { color: theme.textSecondary }]}>Ward Number:</Text>
                  <TextInput
                    style={[styles.singleLineInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                    placeholder="e.g. 174 (verify/enter manually)"
                    placeholderTextColor={theme.textMuted}
                    value={wardNumber}
                    onChangeText={setWardNumber}
                  />
                </View>
              </View>
              <Text style={[styles.subFieldLabel, { color: theme.textMuted, marginTop: 4, fontStyle: 'italic' }]}>
                Ward number is not auto-detected in this build — please enter or verify it yourself.
              </Text>
            </View>
          )}

          {/* DEPARTMENT PICKER ROW */}
          <View style={styles.pickerSection}>
            <Text style={[styles.subFieldLabel, { color: theme.textSecondary }]}>
              Target Authority ({filteredDepartments.length} available):
            </Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.deptScroll}>
              {filteredDepartments.map((dept) => {
                const isSelected = selectedDept?.id === dept.id;
                return (
                  <TouchableOpacity
                    key={dept.id}
                    style={[
                      styles.deptChip,
                      {
                        backgroundColor: isSelected ? theme.primaryGlow : theme.card,
                        borderColor: isSelected ? theme.primary : theme.cardBorder,
                      },
                    ]}
                    onPress={() => setSelectedDept(dept)}
                    activeOpacity={0.8}
                  >
                    <Text style={styles.deptEmoji}>{dept.icon || '🏛️'}</Text>
                    <View>
                      <Text
                        style={[
                          styles.deptChipText,
                          { color: isSelected ? theme.primaryLight : theme.text, fontWeight: isSelected ? '700' : '600' },
                        ]}
                      >
                        {dept.name}
                      </Text>
                      <Text style={[styles.deptEmailSub, { color: theme.textMuted }]}>
                        ✉️ {dept.email}
                      </Text>
                    </View>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </View>

          {/* ========================================================= */}
          {/* STEP 2: DYNAMIC AI CLARIFICATION & FACT FORMULATION */}
          {/* (Only shown in RTI tab or when analyzed) */}
          {/* ========================================================= */}
          {activeTab === 'rti' && (
            <View style={[styles.questionnaireCard, { backgroundColor: theme.card, borderColor: theme.accentSaffron }]}>
              <View style={styles.qHeader}>
                <Text style={[styles.stepBadge, { backgroundColor: 'rgba(191, 107, 61, 0.2)', color: '#BF6B3D' }]}>
                  STEP 2 (AI-DRIVEN)
                </Text>
                <View style={{ flex: 1, marginLeft: 8 }}>
                  <Text style={[styles.qTitle, { color: theme.text }]}>
                    {aiAnalysisResult ? `🎯 RTI Strategy: ${aiAnalysisResult.category}` : '🎯 Tailored RTI Questionnaire'}
                  </Text>
                  <Text style={[styles.qSub, { color: theme.textMuted }]}>
                    {aiAnalysisResult ? aiAnalysisResult.promptTip : 'AI dynamically extracts required statutory records for your complaint'}
                  </Text>
                </View>
              </View>

              <View style={styles.qBody}>
                {/* Specific Record Checklist */}
                <View style={styles.qField}>
                  <Text style={[styles.subFieldLabel, { color: theme.textSecondary }]}>
                    Select Technical Documents to Demand under RTI 2005:
                  </Text>
                  <View style={styles.recordChipsWrap}>
                    {(aiAnalysisResult?.defaultRecords || [
                      'Measurement Book (MB Book) entries',
                      'Quality Test & Lab Strength Reports',
                      'Daily Progress Logs & Deadlines',
                      'Sanctioned vs Utilized Fund Ledger',
                    ]).map((rec, idx) => {
                      const isSelected = selectedRecords.includes(rec);
                      return (
                        <TouchableOpacity
                          key={idx}
                          style={[
                            styles.recordChip,
                            isSelected
                              ? [styles.recordChipActive, { backgroundColor: 'rgba(191, 107, 61, 0.18)', borderColor: theme.accentSaffron }]
                              : [styles.recordChipInactive, { backgroundColor: theme.surface, borderColor: theme.border }],
                          ]}
                          onPress={() => toggleRecordSelection(rec)}
                          activeOpacity={0.8}
                        >
                          <Ionicons
                            name={isSelected ? 'checkbox' : 'square-outline'}
                            size={14}
                            color={isSelected ? theme.accentSaffron : theme.textMuted}
                            style={{ marginRight: 6 }}
                          />
                          <Text
                            style={[
                              styles.recordChipText,
                              {
                                color: isSelected ? theme.text : theme.textSecondary,
                                fontWeight: isSelected ? '700' : '500',
                              },
                            ]}
                          >
                            {rec}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>

                {/* Tender / Work Order Ref */}
                <View style={styles.formRow}>
                  <View style={[styles.qField, { flex: 1 }]}>
                    <Text style={[styles.subFieldLabel, { color: theme.textSecondary }]}>
                      Tender / Work Order No:
                    </Text>
                    <TextInput
                      style={[styles.singleLineInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                      placeholder={aiAnalysisResult?.tenderPlaceholder || 'e.g. WO/2024-25/104 or "Unknown"'}
                      placeholderTextColor={theme.textMuted}
                      value={tenderWorkOrder}
                      onChangeText={setTenderWorkOrder}
                    />
                  </View>

                  <View style={[styles.qField, { flex: 1 }]}>
                    <Text style={[styles.subFieldLabel, { color: theme.textSecondary }]}>
                      Time Period:
                    </Text>
                    <TextInput
                      style={[styles.singleLineInput, { backgroundColor: theme.surface, color: theme.text, borderColor: theme.border }]}
                      placeholder="e.g. FY 2024-25"
                      placeholderTextColor={theme.textMuted}
                      value={timePeriod}
                      onChangeText={setTimePeriod}
                    />
                  </View>
                </View>

                {/* Section 7(1) 48-Hour Emergency Clause */}
                <View
                  style={[
                    styles.emergencyClauseBox,
                    {
                      backgroundColor: emergency48Hr ? 'rgba(194, 69, 69, 0.12)' : theme.surface,
                      borderColor: emergency48Hr ? '#C24545' : theme.border,
                    },
                  ]}
                >
                  <View style={{ flex: 1, paddingRight: 8 }}>
                    <Text style={[styles.emergencyTitle, { color: emergency48Hr ? '#C24545' : theme.text }]}>
                      🚨 48-Hour Emergency Proviso (Section 7(1))
                    </Text>
                    <Text style={[styles.emergencyDesc, { color: theme.textMuted }]}>
                      Mandates PIO reply within 48 hours for life & safety risks instead of 30 days
                    </Text>
                  </View>
                  <Switch
                    value={emergency48Hr}
                    onValueChange={setEmergency48Hr}
                    trackColor={{ false: theme.border, true: '#C24545' }}
                    thumbColor="#FFFFFF"
                  />
                </View>
              </View>
            </View>
          )}

          {/* Citizen Verification Profile Toggle */}
          <View style={[styles.toggleRow, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
            <View style={{ flex: 1, paddingRight: 8 }}>
              <Text style={[styles.toggleTitle, { color: theme.text }]}>
                {t('prefillProfile')}
              </Text>
              <Text style={[styles.toggleSub, { color: theme.textMuted }]}>
                {userProfile.name} • {userProfile.phone}
              </Text>
            </View>
            <Switch
              value={prefillEnabled}
              onValueChange={setPrefillEnabled}
              trackColor={{ false: theme.border, true: theme.primary }}
              thumbColor="#FFFFFF"
            />
          </View>

          {/* STEP 3: GENERATE DOCUMENT BUTTON */}
          <TouchableOpacity
            style={[styles.generateBtn, { backgroundColor: activeTab === 'civic' ? theme.primary : theme.accentSaffron }]}
            onPress={handleGenerate}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading ? (
              <>
                <ActivityIndicator color="#FFFFFF" size="small" />
                <Text style={styles.generateBtnText}>{t('generating')}</Text>
              </>
            ) : (
              <>
                <Ionicons name="sparkles" size={18} color="#FFFFFF" />
                <Text style={styles.generateBtnText}>
                  {activeTab === 'civic' ? 'Generate Statutory Letter with AI' : 'Generate Section 6(1) RTI Draft'}
                </Text>
              </>
            )}
          </TouchableOpacity>

          {/* ========================================================= */}
          {/* STEP 4: GENERATED RESULT OUTPUT & DIRECT PIO ACTIONS */}
          {/* ========================================================= */}
          {generatedResult && (
            <View style={[styles.outputContainer, { backgroundColor: theme.card, borderColor: theme.primary }]}>
              <View style={styles.outputHeader}>
                <View style={styles.outputTitleRow}>
                  <Ionicons name="document-text" size={20} color={theme.primary} />
                  <Text style={[styles.outputHeading, { color: theme.text }]}>
                    Legal Document Preview
                  </Text>
                </View>
                <View style={[styles.readyBadge, { backgroundColor: 'rgba(46, 158, 99, 0.15)' }]}>
                  <Text style={[styles.readyBadgeText, { color: theme.accentEmerald }]}>
                    Submission Ready
                  </Text>
                </View>
              </View>

              <View style={[styles.letterPaper, { backgroundColor: theme.surface, borderColor: theme.border }]}>
                <ScrollView nestedScrollEnabled style={styles.letterScroll}>
                  <Text style={[styles.letterContent, { color: theme.text }]}>
                    {generatedResult}
                  </Text>
                </ScrollView>
              </View>

              {/* DIRECT ACTION 1: SEND OFFICIAL EMAIL TO PIO / COMMISSIONER */}
              <TouchableOpacity
                style={[styles.sendEmailBtn, { backgroundColor: '#3547A8' }]}
                onPress={() => setEmailModalVisible(true)}
                activeOpacity={0.85}
              >
                <Ionicons name="mail" size={18} color="#FFFFFF" />
                <Text style={styles.sendEmailBtnText}>
                  📧 Send Official Email to {selectedDept?.name || 'PIO'}
                </Text>
              </TouchableOpacity>

              {/* Action Buttons Row */}
              <View style={styles.outputActionRow}>
                <TouchableOpacity
                  style={[styles.actionBtn, { backgroundColor: theme.surface, borderColor: theme.border }]}
                  onPress={handleCopyToClipboard}
                  activeOpacity={0.8}
                >
                  <Ionicons name="copy-outline" size={16} color={theme.text} />
                  <Text style={[styles.actionBtnText, { color: theme.text }]}>{t('copyLetter')}</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.actionBtn, { backgroundColor: theme.surface, borderColor: theme.border }]}
                  onPress={handleShareDocument}
                  activeOpacity={0.8}
                >
                  <Ionicons name="share-social-outline" size={16} color={theme.text} />
                  <Text style={[styles.actionBtnText, { color: theme.text }]}>{t('shareLetter')}</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.actionBtn, { backgroundColor: theme.surface, borderColor: theme.border }]}
                  onPress={handleExportPdf}
                  activeOpacity={0.8}
                  disabled={pdfExporting}
                >
                  {pdfExporting ? (
                    <ActivityIndicator size="small" color={theme.text} />
                  ) : (
                    <Ionicons name="document-attach-outline" size={16} color={theme.text} />
                  )}
                  <Text style={[styles.actionBtnText, { color: theme.text }]}>
                    {pdfExporting ? 'Exporting…' : 'Export PDF'}
                  </Text>
                </TouchableOpacity>
              </View>

              {/* Save to Grievance Tracker */}
              <TouchableOpacity
                style={[styles.saveTrackerBtn, { backgroundColor: theme.accentEmerald }]}
                onPress={handleSaveToTracker}
                activeOpacity={0.85}
              >
                <Ionicons name="bookmark" size={18} color="#FFFFFF" />
                <Text style={styles.saveTrackerBtnText}>{t('saveToTracker')}</Text>
              </TouchableOpacity>

              {saveSuccessMsg && (
                <View style={[styles.successBanner, { backgroundColor: 'rgba(46, 158, 99, 0.2)' }]}>
                  <Ionicons name="checkmark-circle" size={16} color={theme.accentEmerald} />
                  <Text style={[styles.successText, { color: theme.accentEmerald }]}>
                    {t('letterSavedSuccess')}
                  </Text>
                </View>
              )}

              {/* ---- AI classification & priority (from the backend) ---- */}
              {aiResult && (
                <View style={[styles.aiCard, { backgroundColor: theme.card, borderColor: theme.primary }]}>
                  <View style={styles.aiCardHeader}>
                    <Ionicons name="sparkles-outline" size={15} color={theme.primary} />
                    <Text style={[styles.aiCardTitle, { color: theme.primary }]}>AI assessment</Text>
                    <View style={[styles.aiReviewBadge, { backgroundColor: aiResult.confirmed ? 'rgba(46,158,99,0.18)' : 'rgba(214,158,46,0.18)' }]}>
                      <Text style={[styles.aiReviewBadgeText, { color: aiResult.confirmed ? theme.accentEmerald : theme.accentAmber }]}>
                        {aiResult.confirmed ? 'Reviewed by official' : 'Awaiting official review'}
                      </Text>
                    </View>
                  </View>

                  <Text style={[styles.aiDisclaimer, { color: theme.textMuted }]}>
                    Automatically suggested to help route your complaint. An official can change any of this.
                  </Text>

                  <View style={styles.aiRowWrap}>
                    {aiResult.classification?.category ? (
                      <View style={[styles.aiPill, { backgroundColor: theme.inputBg, borderColor: theme.border }]}>
                        <Text style={[styles.aiPillLabel, { color: theme.textMuted }]}>Category</Text>
                        <Text style={[styles.aiPillValue, { color: theme.text }]}>{aiResult.classification.category}</Text>
                      </View>
                    ) : null}
                    {aiResult.classification?.department ? (
                      <View style={[styles.aiPill, { backgroundColor: theme.inputBg, borderColor: theme.border }]}>
                        <Text style={[styles.aiPillLabel, { color: theme.textMuted }]}>Department</Text>
                        <Text style={[styles.aiPillValue, { color: theme.text }]}>{aiResult.classification.department}</Text>
                      </View>
                    ) : null}
                    {aiResult.priority ? (
                      <View style={[styles.aiPill, { backgroundColor: theme.inputBg, borderColor: theme.border }]}>
                        <Text style={[styles.aiPillLabel, { color: theme.textMuted }]}>Priority</Text>
                        <Text style={[styles.aiPillValue, { color: theme.text }]}>{String(aiResult.priority).toUpperCase()}</Text>
                      </View>
                    ) : null}
                    {aiResult.severity ? (
                      <View style={[styles.aiPill, { backgroundColor: theme.inputBg, borderColor: theme.border }]}>
                        <Text style={[styles.aiPillLabel, { color: theme.textMuted }]}>Severity</Text>
                        <Text style={[styles.aiPillValue, { color: theme.text }]}>{String(aiResult.severity).toUpperCase()}</Text>
                      </View>
                    ) : null}
                  </View>

                  {/* Transparent, factor-by-factor reasoning — never an opaque score */}
                  {aiResult.reasoning?.factors ? (
                    <View style={styles.aiFactorList}>
                      <Text style={[styles.aiFactorHeading, { color: theme.textSecondary }]}>
                        Why this priority{typeof aiResult.reasoning.totalPoints === 'number' ? ` (${aiResult.reasoning.totalPoints} pts)` : ''}:
                      </Text>
                      {Object.entries(aiResult.reasoning.factors).map(([key, factor]) => (
                        <View key={key} style={styles.aiFactorRow}>
                          <Text style={[styles.aiFactorPoints, { color: theme.primary }]}>+{factor.points}</Text>
                          <Text style={[styles.aiFactorText, { color: theme.textSecondary }]}>
                            {factor.reason || key}
                          </Text>
                        </View>
                      ))}
                    </View>
                  ) : null}

                  {aiResult.duplicates > 0 ? (
                    <View style={[styles.aiDuplicateNote, { borderTopColor: theme.border }]}>
                      <Ionicons name="copy-outline" size={13} color={theme.accentAmber} />
                      <Text style={[styles.aiDuplicateText, { color: theme.textSecondary }]}>
                        {aiResult.duplicates} similar complaint{aiResult.duplicates === 1 ? '' : 's'} flagged for an official to review. Nothing is merged automatically.
                      </Text>
                    </View>
                  ) : null}
                </View>
              )}
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>

      {/* QUICK EMAIL DISPATCH MODAL */}
      {emailModalVisible && (
        <Modal
          animationType="slide"
          transparent={true}
          visible={emailModalVisible}
          onRequestClose={() => setEmailModalVisible(false)}
        >
          <View style={styles.modalOverlay}>
            <View style={[styles.emailModalCard, { backgroundColor: theme.card, borderColor: theme.primary }]}>
              <View style={styles.modalHeader}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="mail" size={20} color={theme.primary} />
                  <Text style={[styles.modalTitle, { color: theme.text }]}>Direct Official Email Dispatch</Text>
                </View>
                <TouchableOpacity onPress={() => setEmailModalVisible(false)}>
                  <Ionicons name="close-circle" size={24} color={theme.textMuted} />
                </TouchableOpacity>
              </View>

              <View style={styles.emailField}>
                <Text style={[styles.emailLabel, { color: theme.textSecondary }]}>To Official Recipient:</Text>
                <Text style={[styles.emailVal, { color: theme.primaryLight }]}>
                  {selectedDept?.email || 'pio@gov.in'} ({selectedDept?.name})
                </Text>
              </View>

              <View style={styles.emailField}>
                <Text style={[styles.emailLabel, { color: theme.textSecondary }]}>Subject:</Text>
                <Text style={[styles.emailVal, { color: theme.text }]}>
                  {activeTab === 'civic' ? `Statutory Grievance: ${issueText.slice(0, 40)}` : `RTI Application under Section 6(1): ${issueText.slice(0, 35)}`}
                </Text>
              </View>

              <TouchableOpacity
                style={[styles.launchMailBtn, { backgroundColor: '#3547A8' }]}
                onPress={handleLaunchEmailClient}
                activeOpacity={0.85}
                disabled={isSendingEmail}
              >
                {isSendingEmail ? (
                  <ActivityIndicator color="#FFFFFF" size="small" />
                ) : (
                  <Ionicons name="send" size={18} color="#FFFFFF" />
                )}
                <Text style={styles.launchMailBtnText}>
                  {isSendingEmail ? 'Sending…' : 'Send Email (with PDF, or opens your email app)'}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.copyEmailBtn, { borderColor: theme.border }]}
                onPress={async () => {
                  await Clipboard.setStringAsync(selectedDept?.email || 'pio@gov.in');
                  Alert.alert('Copied', 'Official email address copied to clipboard!');
                }}
                activeOpacity={0.8}
              >
                <Ionicons name="copy" size={14} color={theme.textSecondary} />
                <Text style={[styles.copyEmailText, { color: theme.textSecondary }]}>
                  Copy Official Email Address ({selectedDept?.email || 'pio@gov.in'})
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>
      )}

      {/* Voice Dictation Hub Modal */}
      <VoiceListeningModal
        visible={voiceModalVisible}
        onClose={() => setVoiceModalVisible(false)}
        onSpeechResult={handleVoiceResult}
        language={draftLanguage}
        title="Civic Grievance Voice Dictation"
      />
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
  tabContainer: {
    flexDirection: 'row',
    borderRadius: RADIUS.lg,
    padding: 4,
    marginBottom: SPACING.md,
    borderWidth: 1,
  },
  tabButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: RADIUS.md,
    gap: 6,
  },
  tabButtonText: {
    fontSize: FONT_SIZE.xs,
    fontWeight: '700',
  },
  inputCard: {
    borderRadius: RADIUS.xl,
    padding: SPACING.md,
    marginBottom: SPACING.md,
    borderWidth: 1,
  },
  inputHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: SPACING.xs,
  },
  stepBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: RADIUS.full,
    fontSize: 10,
    fontWeight: '800',
  },
  inputLabel: {
    fontSize: FONT_SIZE.xs,
    fontWeight: '700',
  },
  voiceInputBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: RADIUS.full,
  },
  voiceInputText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '700',
  },
  textArea: {
    borderRadius: RADIUS.lg,
    padding: SPACING.sm,
    fontSize: FONT_SIZE.sm,
    borderWidth: 1,
    minHeight: 85,
    textAlignVertical: 'top',
  },
  exampleScroll: {
    marginTop: 8,
  },
  exampleChip: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: RADIUS.md,
    marginRight: 6,
    borderWidth: 1,
  },
  exampleText: {
    fontSize: 11,
  },
  subFieldLabel: {
    fontSize: 11,
    fontWeight: '700',
    marginBottom: 4,
  },
  singleLineInput: {
    borderRadius: RADIUS.md,
    paddingHorizontal: SPACING.sm,
    paddingVertical: 8,
    fontSize: FONT_SIZE.xs,
    borderWidth: 1,
  },
  pickerSection: {
    marginBottom: SPACING.md,
  },
  deptScroll: {
    flexDirection: 'row',
    marginTop: 4,
  },
  deptChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: RADIUS.lg,
    marginRight: 8,
    borderWidth: 1,
    gap: 8,
  },
  deptEmoji: {
    fontSize: 20,
  },
  deptChipText: {
    fontSize: FONT_SIZE.xs,
  },
  deptEmailSub: {
    fontSize: 10,
    marginTop: 2,
  },
  questionnaireCard: {
    borderRadius: RADIUS.xl,
    padding: SPACING.md,
    marginBottom: SPACING.md,
    borderWidth: 1.5,
  },
  qHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: SPACING.sm,
  },
  qTitle: {
    fontSize: FONT_SIZE.xs,
    fontWeight: '800',
  },
  qSub: {
    fontSize: 10,
    marginTop: 1,
  },
  qBody: {
    gap: 10,
  },
  qField: {},
  formRow: {
    flexDirection: 'row',
    gap: 8,
  },
  recordChipsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 4,
  },
  recordChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: RADIUS.md,
    borderWidth: 1,
  },
  recordChipActive: {},
  recordChipInactive: {},
  recordChipText: {
    fontSize: 11,
  },
  emergencyClauseBox: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: SPACING.sm,
    borderRadius: RADIUS.lg,
    borderWidth: 1,
    marginTop: 4,
  },
  emergencyTitle: {
    fontSize: 11,
    fontWeight: '800',
    marginBottom: 2,
  },
  emergencyDesc: {
    fontSize: 10,
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: SPACING.md,
    borderRadius: RADIUS.xl,
    marginBottom: SPACING.md,
    borderWidth: 1,
  },
  toggleTitle: {
    fontSize: FONT_SIZE.xs,
    fontWeight: '700',
  },
  toggleSub: {
    fontSize: 11,
    marginTop: 2,
  },
  generateBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: RADIUS.xl,
    gap: 8,
    marginBottom: SPACING.lg,
  },
  generateBtnText: {
    color: '#FFFFFF',
    fontSize: FONT_SIZE.xs,
    fontWeight: '800',
  },
  outputContainer: {
    borderRadius: RADIUS.xl,
    padding: SPACING.md,
    borderWidth: 1,
    marginBottom: SPACING.xl,
  },
  outputHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.sm,
  },
  outputTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  outputHeading: {
    fontSize: FONT_SIZE.sm,
    fontWeight: '800',
  },
  readyBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: RADIUS.full,
  },
  readyBadgeText: {
    fontSize: 10,
    fontWeight: '800',
  },
  letterPaper: {
    borderRadius: RADIUS.lg,
    padding: SPACING.md,
    borderWidth: 1,
    marginBottom: SPACING.md,
  },
  letterScroll: {
    maxHeight: 260,
  },
  letterContent: {
    fontSize: 12,
    lineHeight: 18,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  sendEmailBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: RADIUS.lg,
    gap: 8,
    marginBottom: 10,
  },
  sendEmailBtnText: {
    color: '#FFFFFF',
    fontSize: FONT_SIZE.xs,
    fontWeight: '800',
  },
  outputActionRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 10,
  },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: RADIUS.lg,
    borderWidth: 1,
    gap: 6,
  },
  actionBtnText: {
    fontSize: FONT_SIZE.xs,
    fontWeight: '700',
  },
  saveTrackerBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: RADIUS.lg,
    gap: 6,
  },
  saveTrackerBtnText: {
    color: '#FFFFFF',
    fontSize: FONT_SIZE.xs,
    fontWeight: '800',
  },
  evidenceBtnRow: { flexDirection: 'row', gap: 8 },
  evidenceBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: RADIUS.lg,
    borderWidth: 1,
    flex: 1,
  },
  evidenceBtnText: { fontSize: 12, fontWeight: '700' },
  evidencePreviewRow: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  evidencePreviewImage: { width: 96, height: 96, borderRadius: RADIUS.md },
  evidenceSmallBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: RADIUS.md,
    borderWidth: 1,
  },
  evidenceSmallBtnText: { fontSize: 11, fontWeight: '700' },
  aiCard: { borderRadius: RADIUS.md, borderWidth: 1, padding: 12, marginTop: 12, gap: 8 },
  aiCardHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' },
  aiCardTitle: { fontSize: 12, fontWeight: '800', textTransform: 'uppercase' },
  aiReviewBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 },
  aiReviewBadgeText: { fontSize: 9, fontWeight: '800' },
  aiDisclaimer: { fontSize: 10, lineHeight: 15, fontStyle: 'italic' },
  aiRowWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  aiPill: { borderRadius: RADIUS.sm, borderWidth: 1, paddingHorizontal: 8, paddingVertical: 5, gap: 1 },
  aiPillLabel: { fontSize: 8, textTransform: 'uppercase', fontWeight: '700' },
  aiPillValue: { fontSize: 11, fontWeight: '700' },
  aiFactorList: { gap: 3, marginTop: 2 },
  aiFactorHeading: { fontSize: 10, fontWeight: '800' },
  aiFactorRow: { flexDirection: 'row', gap: 6, alignItems: 'flex-start' },
  aiFactorPoints: { fontSize: 10, fontWeight: '800', minWidth: 24 },
  aiFactorText: { fontSize: 10, lineHeight: 15, flex: 1 },
  aiDuplicateNote: { flexDirection: 'row', gap: 6, alignItems: 'flex-start', borderTopWidth: 1, paddingTop: 8, marginTop: 2 },
  aiDuplicateText: { fontSize: 10, lineHeight: 15, flex: 1 },
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
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.75)',
    justifyContent: 'center',
    padding: SPACING.md,
  },
  emailModalCard: {
    borderRadius: RADIUS.xxl,
    padding: SPACING.lg,
    borderWidth: 1,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.md,
  },
  modalTitle: {
    fontSize: 14,
    fontWeight: '800',
  },
  emailField: {
    marginBottom: 10,
  },
  emailLabel: {
    fontSize: 11,
    fontWeight: '700',
    marginBottom: 2,
  },
  emailVal: {
    fontSize: 12,
    fontWeight: '600',
  },
  launchMailBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: RADIUS.lg,
    gap: 6,
    marginTop: 10,
    marginBottom: 8,
  },
  launchMailBtnText: {
    color: '#FFFFFF',
    fontSize: FONT_SIZE.xs,
    fontWeight: '800',
  },
  copyEmailBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: RADIUS.lg,
    borderWidth: 1,
    gap: 6,
  },
  copyEmailText: {
    fontSize: 11,
    fontWeight: '700',
  },
});
