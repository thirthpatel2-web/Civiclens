// CivicLens - Legal Guide Screen (rule-based keyword matching over ~14
// static legal topics, not a generative AI — see generateChatbotReply in
// aiService.js) with real voice dictation input.

import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  SafeAreaView,
  KeyboardAvoidingView,
  Keyboard,
  Platform,
  Animated,
  Modal,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS, FONT_SIZE } from '../constants/theme';
import { generateChatbotReply } from '../services/aiService';
import VoiceListeningModal from '../components/VoiceListeningModal';
import HoverChip from '../components/HoverChip';
import HoverCard from '../components/HoverCard';

const QUICK_TOPICS = [
  'Police refusing to register Zero FIR',
  'Friend issued ₹3.5L cheque which bounced',
  'Builder delayed flat possession by 2 years',
  'Landlord refusing to return ₹1.2L deposit',
  'Unauthorized ₹45,000 UPI phishing debit',
  'Garbage not collected in ward for 10 days',
];

export default function ChatbotScreen({ navigation }) {
  const { theme, t, language, userProfile } = useApp();

  const [messages, setMessages] = useState([
    {
      id: 'welcome_1',
      sender: 'bot',
      text: `Namaste ${userProfile?.name || 'Citizen'}! I'm CivicLens's Legal Guide — a rule-based helper covering common topics like property inheritance, cheque bounce, builder RERA delays, landlord deposits, cyber fraud, and police FIRs, each with real statutory citations. I'm not a general-purpose AI, so I work best on those specific topics — for anything else, I'll point you toward filing a formal complaint or RTI. What's going on?`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }
  ]);

  const [inputText, setInputText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [voiceModalVisible, setVoiceModalVisible] = useState(false);
  const [keyboardHeight, setKeyboardHeight] = useState(0);

  const scrollViewRef = useRef();

  // Keyboard height tracking for Android & iOS
  useEffect(() => {
    const showEvent = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvent = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';

    const showSub = Keyboard.addListener(showEvent, (e) => {
      setKeyboardHeight(e.endCoordinates.height);
      setTimeout(() => scrollViewRef.current?.scrollToEnd({ animated: true }), 100);
    });

    const hideSub = Keyboard.addListener(hideEvent, () => {
      setKeyboardHeight(0);
    });

    return () => {
      showSub.remove();
      hideSub.remove();
    };
  }, []);

  const handleSend = async (customText = null) => {
    const textToSend = customText || inputText;
    if (!textToSend.trim()) return;

    const userMsg = {
      id: `user_${Date.now()}`,
      sender: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages(prev => [...prev, userMsg]);
    if (!customText) setInputText('');
    setIsTyping(true);

    setTimeout(() => scrollViewRef.current?.scrollToEnd({ animated: true }), 100);

    try {
      const response = await generateChatbotReply({
        message: textToSend,
        history: messages,
        language,
        userProfile,
      });

      const botMsg = {
        id: `bot_${Date.now()}`,
        sender: 'bot',
        text: response.text,
        actionCard: response.actionCard,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages(prev => [...prev, botMsg]);
    } catch (e) {
      console.log('Chatbot error:', e);
    } finally {
      setIsTyping(false);
      setTimeout(() => scrollViewRef.current?.scrollToEnd({ animated: true }), 100);
    }
  };

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
      <View style={{ flex: 1 }}>
        {/* Header with Glowing Status Dot */}
        <View style={[styles.header, { borderBottomColor: theme.border }]}>
          <View style={styles.headerLeft}>
            <View style={[styles.botAvatar, { backgroundColor: theme.primary, shadowColor: theme.primary, shadowOpacity: 0.4, shadowRadius: 8, elevation: 4 }]}>
              <Ionicons name="sparkles" size={18} color="#FFFFFF" />
            </View>
            <View>
              <Text style={[styles.botName, { color: theme.text }]}>
                CivicLens Legal Guide
              </Text>
              <View style={styles.onlineStatusRow}>
                <View style={styles.onlineDot} />
                <Text style={styles.onlineStatusText}>Rule-based · 14 common topics · not a generative AI</Text>
              </View>
            </View>
          </View>
        </View>

        {/* Quick Topic Chips with Hover Effect */}
        <View style={styles.quickChipsContainer}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.quickChipsScroll}
            contentContainerStyle={styles.quickChipsContent}
          >
            {QUICK_TOPICS.map((topic, i) => (
              <HoverChip
                key={i}
                activeColor={theme.primary}
                onPress={() => handleSend(topic)}
              >
                <Text style={[styles.topicChipText, { color: theme.textSecondary }]}>
                  {topic}
                </Text>
              </HoverChip>
            ))}
          </ScrollView>
        </View>

        {/* Messages List */}
        <ScrollView
          ref={scrollViewRef}
          style={styles.messagesContainer}
          contentContainerStyle={[styles.messagesContent, { paddingBottom: 20 }]}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          {messages.map((msg) => {
            const isBot = msg.sender === 'bot';
            return (
              <View
                key={msg.id}
                style={[
                  styles.messageWrapper,
                  isBot ? styles.botMessageWrapper : styles.userMessageWrapper,
                ]}
              >
                {isBot && (
                  <View style={[styles.messageBotIcon, { backgroundColor: theme.primaryGlow }]}>
                    <Ionicons name="shield-checkmark" size={14} color={theme.primary} />
                  </View>
                )}

                <View
                  style={[
                    styles.messageBubble,
                    {
                      backgroundColor: isBot ? theme.card : theme.primary,
                      borderColor: isBot ? theme.cardBorder : theme.primary,
                      shadowColor: '#000',
                      shadowOpacity: isBot ? 0.08 : 0.15,
                      shadowOffset: { width: 0, height: 2 },
                      shadowRadius: 4,
                      elevation: 3,
                    },
                  ]}
                >
                  <Text
                    style={[
                      styles.messageText,
                      { color: isBot ? theme.text : '#FFFFFF' },
                    ]}
                  >
                    {msg.text}
                  </Text>

                  {/* Embedded Smart Action Card with Hover Press */}
                  {msg.actionCard && (
                    <TouchableOpacity
                      style={[
                        styles.actionCard,
                        {
                          backgroundColor: theme.surface,
                          borderColor: theme.primary,
                          shadowColor: theme.primary,
                          shadowOpacity: 0.15,
                          shadowRadius: 6,
                          elevation: 3,
                        }
                      ]}
                      onPress={() => navigation.navigate(msg.actionCard.actionScreen, msg.actionCard.params)}
                      activeOpacity={0.8}
                    >
                      <View style={styles.actionCardContent}>
                        <Text style={[styles.actionCardTitle, { color: theme.text }]}>
                          {msg.actionCard.title}
                        </Text>
                        <Text style={[styles.actionCardBtnText, { color: theme.primaryLight }]}>
                          {msg.actionCard.buttonText} →
                        </Text>
                      </View>
                    </TouchableOpacity>
                  )}

                  <Text
                    style={[
                      styles.timestampText,
                      { color: isBot ? theme.textMuted : 'rgba(255,255,255,0.7)' },
                    ]}
                  >
                    {msg.timestamp}
                  </Text>
                </View>
              </View>
            );
          })}

          {isTyping && (
            <View style={styles.botMessageWrapper}>
              <View style={[styles.messageBotIcon, { backgroundColor: theme.primaryGlow }]}>
                <Ionicons name="sparkles" size={14} color={theme.primary} />
              </View>
              <View style={[styles.messageBubble, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
                <Text style={[styles.typingText, { color: theme.textMuted }]}>
                  AI is searching Supreme Court & statutory records...
                </Text>
              </View>
            </View>
          )}
        </ScrollView>

        {/* Input Bar — Locked & Elevated Directly Above Software Keyboard */}
        <View
          style={[
            styles.inputBarContainer,
            {
              backgroundColor: theme.card,
              borderTopColor: theme.border,
              marginBottom: Platform.OS === 'android' ? keyboardHeight : 0,
            }
          ]}
        >
          <TextInput
            style={[
              styles.chatInput,
              {
                backgroundColor: theme.inputBg,
                color: theme.text,
                borderColor: theme.border,
              }
            ]}
            placeholder={t('chatbotPlaceholder')}
            placeholderTextColor={theme.textMuted}
            value={inputText}
            onChangeText={setInputText}
            onSubmitEditing={() => handleSend()}
            onFocus={() => {
              setTimeout(() => scrollViewRef.current?.scrollToEnd({ animated: true }), 150);
            }}
          />

          <TouchableOpacity
            style={[
              styles.voiceMicBtn,
              {
                backgroundColor: theme.primaryGlow,
                shadowColor: theme.primary,
                shadowOpacity: 0.3,
                shadowRadius: 4,
                elevation: 2,
              }
            ]}
            onPress={() => setVoiceModalVisible(true)}
            activeOpacity={0.7}
          >
            <Ionicons
              name="mic"
              size={20}
              color={theme.primary}
            />
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.sendBtn,
              {
                backgroundColor: theme.primary,
                shadowColor: theme.primary,
                shadowOpacity: 0.35,
                shadowRadius: 4,
                elevation: 3,
              }
            ]}
            onPress={() => handleSend()}
            activeOpacity={0.75}
          >
            <Ionicons name="send" size={18} color="#FFFFFF" />
          </TouchableOpacity>
        </View>

        {/* Voice Dictation Hub Modal */}
        <VoiceListeningModal
          visible={voiceModalVisible}
          onClose={() => setVoiceModalVisible(false)}
          onSpeechResult={(text) => handleSend(text)}
          language={language}
          title="Civic & Legal Voice Copilot"
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: SPACING.md,
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  botAvatar: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  botName: { fontSize: 14, fontWeight: '800' },
  onlineStatusRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 },
  onlineDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#2E9E63' },
  onlineStatusText: { fontSize: 10, color: '#2E9E63', fontWeight: '600' },
  quickChipsContainer: { paddingVertical: 4, paddingHorizontal: SPACING.md, overflow: 'visible' },
  quickChipsScroll: { flexDirection: 'row', overflow: 'visible' },
  quickChipsContent: { paddingVertical: 6, paddingHorizontal: 2, overflow: 'visible' },
  topicChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: RADIUS.full,
    borderWidth: 1,
    marginRight: 8,
  },
  topicChipText: { fontSize: 11 },
  messagesContainer: { flex: 1 },
  messagesContent: { paddingHorizontal: SPACING.md, paddingVertical: 10, gap: 12 },
  messageWrapper: { flexDirection: 'row', gap: 8, maxWidth: '85%' },
  botMessageWrapper: { alignSelf: 'flex-start' },
  userMessageWrapper: { alignSelf: 'flex-end', flexDirection: 'row-reverse' },
  messageBotIcon: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  messageBubble: {
    borderRadius: RADIUS.lg,
    padding: 12,
    borderWidth: 1,
  },
  messageText: { fontSize: 13, lineHeight: 19 },
  actionCard: {
    borderRadius: RADIUS.md,
    padding: 10,
    marginTop: 8,
    borderWidth: 1,
  },
  actionCardContent: { gap: 4 },
  actionCardTitle: { fontSize: 12, fontWeight: '700' },
  actionCardBtnText: { fontSize: 12, fontWeight: '800' },
  timestampText: { fontSize: 9, marginTop: 6, textAlign: 'right' },
  typingText: { fontSize: 12, fontStyle: 'italic' },
  voiceBannerOverlay: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SPACING.md,
    paddingVertical: 10,
    borderWidth: 1.5,
    borderRadius: RADIUS.md,
    marginHorizontal: SPACING.md,
    marginBottom: 8,
    elevation: 4,
  },
  voiceWaveContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    height: 38,
    width: 32,
    justifyContent: 'center',
  },
  voiceBar: { width: 3.5, borderRadius: 2 },
  voiceBannerTitle: { fontSize: 13, fontWeight: '800' },
  voiceBannerSub: { fontSize: 10, marginTop: 1 },
  voiceStopBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: RADIUS.sm,
    gap: 4,
  },
  voiceStopText: { color: '#FFF', fontSize: 11, fontWeight: '800' },
  voiceCancelBtn: { padding: 6, borderRadius: RADIUS.full, borderWidth: 1, marginLeft: 6 },
  inputBarContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SPACING.md,
    paddingVertical: 10,
    borderTopWidth: 1,
    gap: 8,
  },
  chatInput: {
    flex: 1,
    height: 44,
    borderRadius: RADIUS.md,
    paddingHorizontal: 12,
    fontSize: 13,
    borderWidth: 1,
  },
  voiceMicBtn: {
    width: 44,
    height: 44,
    borderRadius: RADIUS.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtn: {
    width: 44,
    height: 44,
    borderRadius: RADIUS.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

