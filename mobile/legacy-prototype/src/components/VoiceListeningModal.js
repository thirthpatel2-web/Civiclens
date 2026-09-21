// CivicLens - Interactive Voice Dictation & Multilingual Speech Hub Modal

import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  ScrollView,
  Animated,
  TextInput,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS } from '../constants/theme';
import {
  startLiveSpeechRecognition,
  stopLiveSpeechRecognition,
  cancelLiveSpeechRecognition,
} from '../services/voiceService';

const DISPUTE_CATEGORIES = [
  {
    id: 'civic',
    name: 'Civic Grievances',
    icon: '🛣️',
    color: '#3547A8',
    queries: [
      'Severe pothole on main market road junction causing accidents for 2 weeks',
      'Garbage has not been collected in our ward for 10 days',
      'Contaminated dirty drinking water supply with low pressure',
      'Streetlights completely non-functional for past 3 weeks',
      'Illegal commercial sewage dumping into residential stormwater drain',
    ],
  },
  {
    id: 'police',
    name: 'Police & Criminal',
    icon: '🚨',
    color: '#C24545',
    queries: [
      'Police station refusing to register Zero FIR for phone theft and assault',
      'Cyber criminal threatened extortion over WhatsApp messages',
      'Neighbor encroached public road and physically threatened my family',
      'Police issued unlawful vehicle seizure without proper seizure memo',
    ],
  },
  {
    id: 'property',
    name: 'Property & Land',
    icon: '⚖️',
    color: '#7A5FB0',
    queries: [
      'Father giving all ancestral property to brother and refusing my equal share',
      'Illegal encroachment and boundary dispute on my registered farmland',
      'Builder delayed flat possession by 2 years and refusing interest or refund',
      'Landlord refusing to refund ₹1.2 Lakh security deposit after lease ended',
    ],
  },
  {
    id: 'financial',
    name: 'Cheque & Banking',
    icon: '💳',
    color: '#2E9E63',
    queries: [
      'Friend issued ₹3.5 Lakh cheque which bounced due to insufficient funds',
      'Unauthorized ₹45,000 UPI debit from bank account through phishing link',
      'Bank deducted unauthorized hidden charges and loan processing penalty',
      'Online e-commerce platform delivered damaged laptop and rejected refund',
    ],
  },
  {
    id: 'labour',
    name: 'Salary & Employment',
    icon: '💼',
    color: '#BF6B3D',
    queries: [
      'Employer terminated me without notice and withheld 3 months salary and PF',
      'Company refusing to release experience letter and gratuity dues',
      'Employer enforcing illegal non-compete clause and withholding FNF settlement',
    ],
  },
  {
    id: 'rti',
    name: 'RTI & Govt Scheme',
    icon: '🏛️',
    color: '#3B8FA8',
    queries: [
      'How do I file an RTI for delayed government road tender funds',
      'RTI application to check municipal ward fund allocation and contractor logs',
      'Pension application delayed by 8 months without written justification',
    ],
  },
];

export default function VoiceListeningModal({
  visible,
  onClose,
  onSpeechResult,
  title = 'Civic Voice Search',
  language = 'en',
}) {
  const { theme, t } = useApp();
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [transcriptText, setTranscriptText] = useState('');
  const [selectedCat, setSelectedCat] = useState(DISPUTE_CATEGORIES[0]);
  const [speechStatus, setSpeechStatus] = useState('Listening to your microphone...');
  const [recordingMode, setRecordingMode] = useState(null); // 'web_speech' | 'expo_audio'
  const [isTranscribing, setIsTranscribing] = useState(false);

  const pulseScale = useRef(new Animated.Value(1)).current;
  const wave1 = useRef(new Animated.Value(8)).current;
  const wave2 = useRef(new Animated.Value(16)).current;
  const wave3 = useRef(new Animated.Value(12)).current;
  const wave4 = useRef(new Animated.Value(24)).current;
  const timerRef = useRef(null);
  const loopAnimsRef = useRef([]);

  useEffect(() => {
    if (visible) {
      setTranscriptText('');
      setRecordingSeconds(0);
      setIsRecording(false);
      setSpeechStatus('🎙️ Listening... Speak clearly into your microphone:');
      startRecordingSession();
    } else {
      stopRecordingSession();
    }

    return () => {
      stopRecordingSession();
    };
  }, [visible]);

  // Drives the wave bars from REAL microphone volume on web (via
  // AnalyserNode in voiceService). On native, where we don't get a live
  // volume stream, falls back to a gentle looping animation so the UI still
  // shows the mic is active — clearly a decorative fallback, not fake data
  // pretending to be a real waveform reading.
  const applyVolumeToWaves = (level) => {
    const norm = Math.max(6, Math.min(44, level * 0.4 + 6));
    wave1.setValue(norm * 0.8);
    wave2.setValue(norm);
    wave3.setValue(norm * 0.6);
    wave4.setValue(norm * 0.9);
  };

  const startDecorativeWaveLoop = () => {
    const loops = [
      [wave1, 32, 8, 250], [wave2, 40, 12, 300], [wave3, 28, 10, 220], [wave4, 36, 14, 280],
    ].map(([anim, hi, lo, duration]) =>
      Animated.loop(
        Animated.sequence([
          Animated.timing(anim, { toValue: hi, duration, useNativeDriver: false }),
          Animated.timing(anim, { toValue: lo, duration, useNativeDriver: false }),
        ])
      )
    );
    loops.forEach((l) => l.start());
    loopAnimsRef.current = loops;
  };

  const stopDecorativeWaveLoop = () => {
    loopAnimsRef.current.forEach((l) => l.stop());
    loopAnimsRef.current = [];
  };

  const startRecordingSession = async () => {
    setIsRecording(true);
    setRecordingSeconds(0);
    setSpeechStatus('🎙️ Listening... Speak clearly in your language:');

    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseScale, { toValue: 1.15, duration: 400, useNativeDriver: true }),
        Animated.timing(pulseScale, { toValue: 1.0, duration: 400, useNativeDriver: true }),
      ])
    ).start();

    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setRecordingSeconds((s) => s + 1);
    }, 1000);

    // Call live speech recognition — onVolumeChange gives REAL mic amplitude
    // on web and (via onSpeechVolumeChanged) on native too. Only the
    // 'unavailable' case (no dev client built) uses the decorative fallback.
    const result = await startLiveSpeechRecognition(
      language,
      (spokenWords) => {
        if (spokenWords && spokenWords.trim().length > 0) {
          setTranscriptText(spokenWords.trim());
          setSpeechStatus('✅ Speech captured in real-time:');
        }
      },
      (err) => {
        console.log('Speech API Notice:', err);
        if (result?.mode === 'unavailable') {
          setSpeechStatus('⚠️ On-device voice needs a dev client build (Expo Go can\'t run it) — type below or pick a preset:');
        } else {
          setSpeechStatus('🎙️ Listening... (You can also select a preset below)');
        }
      },
      (volumeLevel) => applyVolumeToWaves(volumeLevel)
    );

    setRecordingMode(result?.mode || null);
    if (result?.mode === 'unavailable') {
      setIsRecording(false);
      setSpeechStatus('⚠️ On-device voice recognition needs a dev client build (see README) — Expo Go can\'t run it. Type below or pick a preset:');
    } else if (result?.mode !== 'web_speech' && result?.mode !== 'native_voice') {
      startDecorativeWaveLoop();
    }
  };

  const stopRecordingSession = async () => {
    setIsRecording(false);
    stopDecorativeWaveLoop();
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    await stopLiveSpeechRecognition();
  };

  const toggleMic = () => {
    if (isRecording) {
      stopRecordingSession();
      setSpeechStatus('⏹️ Mic paused. Tap to record again or click "Submit Query":');
    } else {
      startRecordingSession();
    }
  };

  const handleSelectPreset = (text) => {
    setTranscriptText(text);
    setSpeechStatus('📝 Query selected! Tap "Submit Query" or edit:');
  };

  const handleSubmit = () => {
    const finalText = transcriptText.trim();
    if (!finalText) {
      const defaultQuery = selectedCat.queries[0];
      setTranscriptText(defaultQuery);
      onSpeechResult(defaultQuery);
      onClose();
      return;
    }
    stopRecordingSession();
    onSpeechResult(finalText);
    onClose();
  };

  if (!visible) return null;

  const formatSeconds = (sec) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  return (
    <Modal
      animationType="slide"
      transparent={true}
      visible={visible}
      onRequestClose={onClose}
    >
      <View style={styles.modalOverlay}>
        <View style={[styles.modalContent, { backgroundColor: theme.card, borderColor: theme.primary }]}>
          {/* Header */}
          <View style={styles.modalHeader}>
            <View style={styles.headerLeft}>
              <Ionicons name="mic-circle" size={24} color={theme.primary} />
              <Text style={[styles.modalTitle, { color: theme.text }]}>{title}</Text>
            </View>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
              <Ionicons name="close-circle" size={24} color={theme.textMuted} />
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.scrollArea} showsVerticalScrollIndicator={false}>
            {/* Visualizer & Big Mic Button */}
            <View style={[styles.micVisualizerCard, { backgroundColor: theme.surface, borderColor: theme.border }]}>
              {/* Audio Wave Frequency Bars */}
              <View style={styles.waveBarContainer}>
                <Animated.View
                  style={[styles.waveBar, { height: wave1, backgroundColor: isRecording ? '#C24545' : theme.textMuted }]}
                />
                <Animated.View
                  style={[styles.waveBar, { height: wave2, backgroundColor: isRecording ? '#BF6B3D' : theme.textMuted }]}
                />
                <Animated.View
                  style={[styles.waveBar, { height: wave4, backgroundColor: isRecording ? '#2E9E63' : theme.textMuted }]}
                />
                <Animated.View
                  style={[styles.waveBar, { height: wave3, backgroundColor: isRecording ? '#5568D6' : theme.textMuted }]}
                />
              </View>

              {/* Central Pulsating Mic Button */}
              <Animated.View style={{ transform: [{ scale: isRecording ? pulseScale : 1 }] }}>
                <TouchableOpacity
                  style={[
                    styles.bigMicButton,
                    { backgroundColor: isRecording ? '#C24545' : theme.primary },
                  ]}
                  onPress={toggleMic}
                  activeOpacity={0.8}
                  disabled={isTranscribing}
                >
                  {isTranscribing ? (
                    <ActivityIndicator color="#FFFFFF" size="small" />
                  ) : (
                    <Ionicons name={isRecording ? 'stop' : 'mic'} size={32} color="#FFFFFF" />
                  )}
                </TouchableOpacity>
              </Animated.View>

              {/* Timer & Status Label */}
              <View style={styles.timerRow}>
                {isRecording && <View style={styles.recordDot} />}
                <Text style={[styles.timerText, { color: isRecording ? '#C24545' : theme.textMuted }]}>
                  {isRecording ? `Recording (${formatSeconds(recordingSeconds)})` : 'Tap Mic to Start Speaking'}
                </Text>
              </View>

              <Text style={[styles.speechStatusText, { color: theme.textSecondary }]}>
                {speechStatus}
              </Text>
            </View>

            {/* Live Editable Transcript Input */}
            <View style={[styles.transcriptBox, { backgroundColor: theme.surface, borderColor: theme.border }]}>
              <View style={styles.transcriptHeader}>
                <Text style={[styles.transcriptLabel, { color: theme.textSecondary }]}>
                  Live Transcript / Recognized Query:
                </Text>
                {transcriptText.length > 0 && (
                  <TouchableOpacity onPress={() => setTranscriptText('')}>
                    <Text style={[styles.clearLink, { color: theme.accentRose }]}>Clear</Text>
                  </TouchableOpacity>
                )}
              </View>
              <TextInput
                style={[styles.transcriptInput, { color: theme.text }]}
                value={transcriptText}
                onChangeText={setTranscriptText}
                placeholder="Spoken words will stream live here, or type/edit manually..."
                placeholderTextColor={theme.textMuted}
                multiline
                numberOfLines={3}
              />
            </View>

            {/* Quick One-Tap Dispute Categories & Presets */}
            <View style={styles.presetSection}>
              <Text style={[styles.presetSectionTitle, { color: theme.text }]}>
                ⚡ 1-Tap Quick Legal & Civic Presets:
              </Text>

              {/* Category Pills */}
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.catScroll}>
                {DISPUTE_CATEGORIES.map((cat) => {
                  const isSelected = selectedCat.id === cat.id;
                  return (
                    <TouchableOpacity
                      key={cat.id}
                      style={[
                        styles.catPill,
                        {
                          backgroundColor: isSelected ? cat.color : theme.surface,
                          borderColor: isSelected ? cat.color : theme.border,
                        },
                      ]}
                      onPress={() => setSelectedCat(cat)}
                      activeOpacity={0.8}
                    >
                      <Text style={styles.catEmoji}>{cat.icon}</Text>
                      <Text
                        style={[
                          styles.catPillText,
                          { color: isSelected ? '#FFFFFF' : theme.textSecondary, fontWeight: isSelected ? '700' : '500' },
                        ]}
                      >
                        {cat.name}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>

              {/* Query Buttons under active category */}
              <View style={styles.queriesList}>
                {selectedCat.queries.map((q, idx) => (
                  <TouchableOpacity
                    key={idx}
                    style={[styles.queryOptionBtn, { backgroundColor: theme.surface, borderColor: theme.border }]}
                    onPress={() => handleSelectPreset(q)}
                    activeOpacity={0.75}
                  >
                    <Ionicons name="chatbubble-ellipses-outline" size={14} color={selectedCat.color} style={{ marginRight: 6 }} />
                    <Text style={[styles.queryOptionText, { color: theme.text }]} numberOfLines={2}>
                      {q}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          </ScrollView>

          {/* Action Buttons */}
          <View style={styles.modalFooter}>
            <TouchableOpacity
              style={[styles.cancelBtn, { borderColor: theme.border }]}
              onPress={onClose}
              activeOpacity={0.8}
            >
              <Text style={[styles.cancelBtnText, { color: theme.textSecondary }]}>Cancel</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.submitBtn, { backgroundColor: theme.primary }]}
              onPress={handleSubmit}
              activeOpacity={0.85}
            >
              <Ionicons name="checkmark-circle" size={18} color="#FFFFFF" />
              <Text style={styles.submitBtnText}>Submit Query</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.75)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    borderTopLeftRadius: RADIUS.xxl,
    borderTopRightRadius: RADIUS.xxl,
    borderTopWidth: 2,
    padding: SPACING.md,
    maxHeight: '88%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.sm,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  modalTitle: {
    fontSize: 16,
    fontWeight: '800',
  },
  closeBtn: {
    padding: 4,
  },
  scrollArea: {
    maxHeight: 480,
  },
  micVisualizerCard: {
    borderRadius: RADIUS.xl,
    padding: SPACING.md,
    alignItems: 'center',
    borderWidth: 1,
    marginBottom: SPACING.md,
  },
  waveBarContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    height: 40,
    gap: 8,
    marginBottom: SPACING.sm,
  },
  waveBar: {
    width: 6,
    borderRadius: 3,
  },
  bigMicButton: {
    width: 70,
    height: 70,
    borderRadius: 35,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 6,
    marginBottom: SPACING.sm,
  },
  timerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  recordDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#C24545',
  },
  timerText: {
    fontSize: 12,
    fontWeight: '700',
  },
  speechStatusText: {
    fontSize: 11,
    textAlign: 'center',
  },
  transcriptBox: {
    borderRadius: RADIUS.lg,
    padding: SPACING.sm,
    borderWidth: 1,
    marginBottom: SPACING.md,
  },
  transcriptHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  transcriptLabel: {
    fontSize: 11,
    fontWeight: '700',
  },
  clearLink: {
    fontSize: 11,
    fontWeight: '700',
  },
  transcriptInput: {
    fontSize: 13,
    minHeight: 55,
    textAlignVertical: 'top',
  },
  presetSection: {
    marginBottom: SPACING.md,
  },
  presetSectionTitle: {
    fontSize: 12,
    fontWeight: '800',
    marginBottom: 8,
  },
  catScroll: {
    flexDirection: 'row',
    marginBottom: 8,
  },
  catPill: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: RADIUS.full,
    marginRight: 6,
    borderWidth: 1,
    gap: 4,
  },
  catEmoji: {
    fontSize: 14,
  },
  catPillText: {
    fontSize: 11,
  },
  queriesList: {
    gap: 6,
  },
  queryOptionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 8,
    borderRadius: RADIUS.md,
    borderWidth: 1,
  },
  queryOptionText: {
    fontSize: 11,
    flex: 1,
    lineHeight: 15,
  },
  modalFooter: {
    flexDirection: 'row',
    gap: 10,
    marginTop: SPACING.sm,
  },
  cancelBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: RADIUS.lg,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cancelBtnText: {
    fontSize: 13,
    fontWeight: '700',
  },
  submitBtn: {
    flex: 2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: RADIUS.lg,
    gap: 6,
  },
  submitBtnText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '800',
  },
});
