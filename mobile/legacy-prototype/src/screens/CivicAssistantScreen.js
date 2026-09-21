// CivicLens - AI Civic Assistant Screen
//
// This is the grounded, retrieval-backed civic assistant — distinct from
// ChatbotScreen (the rule-based Legal Guide). It calls the real backend
// pipeline (server/src/services/ragAssistant.js) via
// civicIntelligenceService.askCivicAssistant, which combines SQL facts
// (ward spending, complaint stats, delayed projects, ...) with hybrid
// document retrieval (semantic + BM25 + RRF + LLM rerank) and returns a
// single structured response. Per the spec, this screen keeps three
// things visually distinct so nothing gets conflated:
//   1. The AI's plain-language explanation
//   2. Database facts (verifiable, real-time query results)
//   3. Document evidence (retrieved excerpts with citations)
// plus explicit loading, error, and "insufficient evidence" states — the
// assistant is designed to say "I don't know" rather than invent a civic
// fact, and this screen must not paper over that by hiding the signal.

import React, { useState, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  SafeAreaView,
  Keyboard,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useApp } from '../context/AppContext';
import { SPACING, RADIUS } from '../constants/theme';
import { askCivicAssistant } from '../services/civicIntelligenceService';
import HoverChip from '../components/HoverChip';

const EXAMPLE_QUESTIONS = [
  'How much was spent on road repairs in my ward this year?',
  'Why hasn\u2019t the pothole complaint in my ward been resolved?',
  'Which projects in my ward are delayed?',
  'How many complaints are still pending in my ward?',
];

function timestamp() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/** Renders the "DATABASE FACTS" block — raw, verifiable query results,
 *  kept visually separate from anything the model wrote in prose. */
function DatabaseFactsCard({ theme, sqlUsed, sqlData }) {
  if (!sqlData) return null;
  const rows = Array.isArray(sqlData) ? sqlData : [sqlData];

  return (
    <View style={[styles.evidenceCard, { backgroundColor: theme.surface, borderColor: theme.accent }]}>
      <View style={styles.evidenceHeader}>
        <Ionicons name="server-outline" size={14} color={theme.accent} />
        <Text style={[styles.evidenceHeaderText, { color: theme.accent }]}>
          Database facts{sqlUsed ? ` \u00b7 ${sqlUsed}` : ''}
        </Text>
      </View>
      {rows.slice(0, 8).map((row, i) => (
        <View key={i} style={[styles.factRow, i > 0 && { borderTopColor: theme.border, borderTopWidth: 1 }]}>
          {Object.entries(row || {}).map(([key, value]) => (
            <Text key={key} style={[styles.factLine, { color: theme.textSecondary }]}>
              <Text style={{ fontWeight: '700', color: theme.text }}>{key}: </Text>
              {typeof value === 'object' ? JSON.stringify(value) : String(value)}
            </Text>
          ))}
        </View>
      ))}
      {rows.length > 8 && (
        <Text style={[styles.factMoreText, { color: theme.textMuted }]}>+{rows.length - 8} more rows</Text>
      )}
    </View>
  );
}

/** Renders "DOCUMENT EXCERPTS" — retrieved evidence with citations, kept
 *  separate from database facts and from the AI's own prose. */
function DocumentEvidenceCard({ theme, evidence }) {
  if (!evidence || evidence.length === 0) return null;

  return (
    <View style={[styles.evidenceCard, { backgroundColor: theme.surface, borderColor: theme.primary }]}>
      <View style={styles.evidenceHeader}>
        <Ionicons name="document-text-outline" size={14} color={theme.primary} />
        <Text style={[styles.evidenceHeaderText, { color: theme.primary }]}>
          Document evidence ({evidence.length})
        </Text>
      </View>
      {evidence.map((ev, i) => (
        <View key={i} style={[styles.citationBlock, i > 0 && { borderTopColor: theme.border, borderTopWidth: 1 }]}>
          <Text style={[styles.citationSource, { color: theme.text }]}>
            {ev.documentName || 'Unknown document'}
            {ev.pageNumber ? ` \u00b7 p.${ev.pageNumber}` : ''}
            {ev.section ? ` \u00b7 ${ev.section}` : ''}
          </Text>
          <Text style={[styles.citationExcerpt, { color: theme.textSecondary }]} numberOfLines={4}>
            {'\u201c'}{ev.excerpt}{'\u201d'}
          </Text>
        </View>
      ))}
    </View>
  );
}

export default function CivicAssistantScreen({ navigation, route }) {
  const { theme, userProfile } = useApp();
  const defaultWard = route?.params?.ward || userProfile?.ward || null;

  const [messages, setMessages] = useState([
    {
      id: 'welcome_1',
      sender: 'bot',
      text: `Namaste ${userProfile?.name || 'Citizen'}! I'm the CivicLens Civic Assistant. I answer using your civic database (spending, complaints, projects) and official documents \u2014 never by guessing. If I don't have enough evidence, I'll say so instead of making something up. Ask me anything about your ward, a complaint, or a project.`,
      timestamp: timestamp(),
    },
  ]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const scrollViewRef = useRef();

  const scrollToEnd = () => setTimeout(() => scrollViewRef.current?.scrollToEnd({ animated: true }), 100);

  const handleSend = async (customText = null) => {
    const textToSend = (customText || inputText).trim();
    if (!textToSend || isLoading) return;

    const userMsg = { id: `user_${Date.now()}`, sender: 'user', text: textToSend, timestamp: timestamp() };
    setMessages((prev) => [...prev, userMsg]);
    if (!customText) setInputText('');
    Keyboard.dismiss();
    setIsLoading(true);
    scrollToEnd();

    try {
      const result = await askCivicAssistant(textToSend, { ward: defaultWard });

      if (result.error) {
        setMessages((prev) => [
          ...prev,
          {
            id: `err_${Date.now()}`,
            sender: 'bot',
            isError: true,
            text: `I couldn't reach the assistant service: ${result.error}. Please try again in a moment.`,
            timestamp: timestamp(),
          },
        ]);
        return;
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `bot_${Date.now()}`,
          sender: 'bot',
          text: result.answer || 'I could not find enough reliable information to answer this.',
          insufficientEvidence: Boolean(result.insufficientEvidence),
          sqlUsed: result.sqlUsed,
          sqlData: result.sqlData,
          evidence: result.evidence,
          timestamp: timestamp(),
        },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err_${Date.now()}`,
          sender: 'bot',
          isError: true,
          text: 'Something went wrong reaching the assistant. Please check your connection and try again.',
          timestamp: timestamp(),
        },
      ]);
      console.log('CivicAssistant error:', e?.message);
    } finally {
      setIsLoading(false);
      scrollToEnd();
    }
  };

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
      <View style={{ flex: 1 }}>
        <View style={[styles.header, { borderBottomColor: theme.border }]}>
          <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="chevron-back" size={22} color={theme.text} />
          </TouchableOpacity>
          <View style={styles.headerLeft}>
            <View style={[styles.botAvatar, { backgroundColor: theme.primary, shadowColor: theme.primary, shadowOpacity: 0.4, shadowRadius: 8, elevation: 4 }]}>
              <Ionicons name="shield-checkmark" size={18} color="#FFFFFF" />
            </View>
            <View>
              <Text style={[styles.botName, { color: theme.text }]}>Civic Assistant</Text>
              <View style={styles.onlineStatusRow}>
                <View style={styles.onlineDot} />
                <Text style={styles.onlineStatusText}>Grounded in your civic database & documents</Text>
              </View>
            </View>
          </View>
        </View>

        <View style={styles.quickChipsContainer}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.quickChipsContent}>
            {EXAMPLE_QUESTIONS.map((q, i) => (
              <HoverChip key={i} activeColor={theme.primary} onPress={() => handleSend(q)}>
                <Text style={[styles.topicChipText, { color: theme.textSecondary }]}>{q}</Text>
              </HoverChip>
            ))}
          </ScrollView>
        </View>

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
              <View key={msg.id} style={[styles.messageWrapper, isBot ? styles.botMessageWrapper : styles.userMessageWrapper]}>
                {isBot && (
                  <View style={[styles.messageBotIcon, { backgroundColor: msg.isError ? 'rgba(176,67,92,0.15)' : theme.primaryGlow }]}>
                    <Ionicons
                      name={msg.isError ? 'alert-circle' : 'shield-checkmark'}
                      size={14}
                      color={msg.isError ? theme.accentRose : theme.primary}
                    />
                  </View>
                )}
                <View style={{ maxWidth: '88%' }}>
                  <View
                    style={[
                      styles.messageBubble,
                      {
                        backgroundColor: isBot ? theme.card : theme.primary,
                        borderColor: msg.isError ? theme.accentRose : isBot ? theme.cardBorder : theme.primary,
                      },
                    ]}
                  >
                    {msg.insufficientEvidence && (
                      <View style={styles.insufficientBadge}>
                        <Ionicons name="information-circle-outline" size={12} color={theme.accentAmber} />
                        <Text style={[styles.insufficientBadgeText, { color: theme.accentAmber }]}>Insufficient evidence</Text>
                      </View>
                    )}
                    <Text style={[styles.messageText, { color: isBot ? theme.text : '#FFFFFF' }]}>{msg.text}</Text>
                    <Text style={[styles.timestampText, { color: isBot ? theme.textMuted : 'rgba(255,255,255,0.7)' }]}>
                      {msg.timestamp}
                    </Text>
                  </View>

                  {isBot && <DatabaseFactsCard theme={theme} sqlUsed={msg.sqlUsed} sqlData={msg.sqlData} />}
                  {isBot && <DocumentEvidenceCard theme={theme} evidence={msg.evidence} />}
                </View>
              </View>
            );
          })}

          {isLoading && (
            <View style={styles.botMessageWrapper}>
              <View style={[styles.messageBotIcon, { backgroundColor: theme.primaryGlow }]}>
                <Ionicons name="shield-checkmark" size={14} color={theme.primary} />
              </View>
              <View style={[styles.messageBubble, { backgroundColor: theme.card, borderColor: theme.cardBorder, flexDirection: 'row', alignItems: 'center', gap: 8 }]}>
                <ActivityIndicator size="small" color={theme.primary} />
                <Text style={[styles.typingText, { color: theme.textMuted }]}>{'Checking records & documents\u2026'}</Text>
              </View>
            </View>
          )}
        </ScrollView>

        <View style={[styles.inputBarContainer, { backgroundColor: theme.card, borderTopColor: theme.border }]}>
          <TextInput
            style={[styles.chatInput, { backgroundColor: theme.inputBg, color: theme.text, borderColor: theme.border }]}
            placeholder={'Ask about spending, complaints, or a project\u2026'}
            placeholderTextColor={theme.textMuted}
            value={inputText}
            onChangeText={setInputText}
            onSubmitEditing={() => handleSend()}
            editable={!isLoading}
          />
          <TouchableOpacity
            style={[styles.sendBtn, { backgroundColor: isLoading ? theme.border : theme.primary }]}
            onPress={() => handleSend()}
            activeOpacity={0.75}
            disabled={isLoading}
          >
            <Ionicons name="send" size={18} color="#FFFFFF" />
          </TouchableOpacity>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: SPACING.md, paddingVertical: 12, borderBottomWidth: 1 },
  backBtn: { padding: 2 },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  botAvatar: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  botName: { fontSize: 14, fontWeight: '800' },
  onlineStatusRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 },
  onlineDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#2E9E63' },
  onlineStatusText: { fontSize: 10, color: '#2E9E63', fontWeight: '600' },
  quickChipsContainer: { paddingVertical: 4, paddingHorizontal: SPACING.md },
  quickChipsContent: { paddingVertical: 6, paddingHorizontal: 2, gap: 8 },
  topicChipText: { fontSize: 11 },
  messagesContainer: { flex: 1 },
  messagesContent: { paddingHorizontal: SPACING.md, paddingVertical: 10, gap: 12 },
  messageWrapper: { flexDirection: 'row', gap: 8, maxWidth: '95%' },
  botMessageWrapper: { alignSelf: 'flex-start' },
  userMessageWrapper: { alignSelf: 'flex-end', flexDirection: 'row-reverse' },
  messageBotIcon: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  messageBubble: { borderRadius: RADIUS.lg, padding: 12, borderWidth: 1 },
  messageText: { fontSize: 13, lineHeight: 19 },
  timestampText: { fontSize: 9, marginTop: 6, textAlign: 'right' },
  typingText: { fontSize: 12, fontStyle: 'italic' },
  insufficientBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 6 },
  insufficientBadgeText: { fontSize: 10, fontWeight: '800', textTransform: 'uppercase' },
  evidenceCard: { borderRadius: RADIUS.md, padding: 10, marginTop: 8, borderWidth: 1 },
  evidenceHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 },
  evidenceHeaderText: { fontSize: 11, fontWeight: '800', textTransform: 'uppercase' },
  factRow: { paddingVertical: 4, gap: 2 },
  factLine: { fontSize: 11, lineHeight: 16 },
  factMoreText: { fontSize: 10, marginTop: 4, fontStyle: 'italic' },
  citationBlock: { paddingVertical: 6, gap: 2 },
  citationSource: { fontSize: 11, fontWeight: '700' },
  citationExcerpt: { fontSize: 11, lineHeight: 16, fontStyle: 'italic' },
  inputBarContainer: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: SPACING.md, paddingVertical: 10, borderTopWidth: 1, gap: 8 },
  chatInput: { flex: 1, height: 44, borderRadius: RADIUS.md, paddingHorizontal: 12, fontSize: 13, borderWidth: 1 },
  sendBtn: { width: 44, height: 44, borderRadius: RADIUS.md, alignItems: 'center', justifyContent: 'center' },
});
