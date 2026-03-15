import { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TextInput,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, RADII, SHADOWS, TYPE } from '../constants/theme';
import { API_URL, authFetch } from '../constants/api';

export default function MessagesScreen() {
  const router = useRouter();
  const flatListRef = useRef(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [text, setText] = useState('');

  const loadMessages = useCallback(async () => {
    try {
      const res = await authFetch(`${API_URL}/messages`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      }
    } catch {
      // Network error — keep showing what we have
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMessages();
    // Poll for new messages every 15 seconds
    const interval = setInterval(loadMessages, 15000);
    return () => clearInterval(interval);
  }, [loadMessages]);

  async function handleSend() {
    const body = text.trim();
    if (!body || sending) return;
    setSending(true);
    try {
      const res = await authFetch(`${API_URL}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body }),
      });
      if (res.ok) {
        const data = await res.json();
        setMessages((prev) => [...prev, data.message]);
        setText('');
      }
    } catch {
      // Could show error toast
    } finally {
      setSending(false);
    }
  }

  function formatTime(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr + 'Z');
    const now = new Date();
    const diffDays = Math.floor((now - d) / 86400000);
    const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    if (diffDays === 0) return time;
    if (diffDays === 1) return `Yesterday ${time}`;
    if (diffDays < 7) {
      return `${d.toLocaleDateString([], { weekday: 'short' })} ${time}`;
    }
    return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${time}`;
  }

  function renderMessage({ item }) {
    const isAgent = item.sender_type === 'agent';
    return (
      <View style={[styles.bubble, isAgent ? styles.bubbleAgent : styles.bubbleMember]}>
        <Text style={[styles.senderName, isAgent ? styles.senderAgent : styles.senderMember]}>
          {item.sender_name || (isAgent ? 'Your Agent' : 'You')}
        </Text>
        <Text style={[styles.msgBody, isAgent ? styles.bodyAgent : styles.bodyMember]}>
          {item.body}
        </Text>
        <Text style={[styles.timestamp, isAgent ? styles.tsAgent : styles.tsMember]}>
          {formatTime(item.created_at)}
        </Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={COLORS.accent} />
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Ionicons name="chatbubbles-outline" size={20} color={COLORS.accent} />
          <Text style={styles.headerTitle}>Messages</Text>
        </View>
        <View style={{ width: 40 }} />
      </View>

      {loading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={COLORS.accent} />
          <Text style={styles.loadingText}>Loading messages...</Text>
        </View>
      ) : (
        <KeyboardAvoidingView
          style={styles.flex}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          keyboardVerticalOffset={90}
        >
          {messages.length === 0 ? (
            <View style={styles.emptyContainer}>
              <Ionicons name="chatbubble-ellipses-outline" size={48} color={COLORS.textTertiary} />
              <Text style={styles.emptyTitle}>No messages yet</Text>
              <Text style={styles.emptySubtitle}>
                Send a message to your concierge agent. They can help with benefits, appointments, medications, and more.
              </Text>
            </View>
          ) : (
            <FlatList
              ref={flatListRef}
              data={messages}
              keyExtractor={(item) => String(item.id)}
              renderItem={renderMessage}
              contentContainerStyle={styles.messagesList}
              onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: false })}
              onLayout={() => flatListRef.current?.scrollToEnd({ animated: false })}
            />
          )}

          {/* Compose bar */}
          <View style={styles.composeBar}>
            <TextInput
              style={styles.input}
              value={text}
              onChangeText={setText}
              placeholder="Type a message..."
              placeholderTextColor={COLORS.textTertiary}
              multiline
              maxLength={2000}
              editable={!sending}
            />
            <TouchableOpacity
              style={[styles.sendBtn, (!text.trim() || sending) && styles.sendBtnDisabled]}
              onPress={handleSend}
              disabled={!text.trim() || sending}
            >
              {sending ? (
                <ActivityIndicator size="small" color={COLORS.white} />
              ) : (
                <Ionicons name="send" size={18} color={COLORS.white} />
              )}
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.sm + 2,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
    backgroundColor: COLORS.card,
  },
  backBtn: { width: 40, alignItems: 'flex-start' },
  headerCenter: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerTitle: { ...TYPE.h3, color: COLORS.text },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12 },
  loadingText: { ...TYPE.body, color: COLORS.textSecondary },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: SPACING.xl,
    gap: 12,
  },
  emptyTitle: { ...TYPE.h3, color: COLORS.textSecondary },
  emptySubtitle: { ...TYPE.body, color: COLORS.textTertiary, textAlign: 'center', lineHeight: 22 },
  messagesList: { padding: SPACING.md, paddingBottom: SPACING.sm },
  bubble: {
    maxWidth: '80%',
    borderRadius: RADII.md,
    padding: SPACING.sm + 4,
    marginBottom: SPACING.sm,
  },
  bubbleAgent: {
    alignSelf: 'flex-start',
    backgroundColor: COLORS.card,
    ...SHADOWS.card,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
  },
  bubbleMember: {
    alignSelf: 'flex-end',
    backgroundColor: COLORS.accent,
  },
  senderName: { ...TYPE.labelSmall, marginBottom: 4 },
  senderAgent: { color: COLORS.accent },
  senderMember: { color: 'rgba(255,255,255,0.7)' },
  msgBody: { ...TYPE.body, lineHeight: 22 },
  bodyAgent: { color: COLORS.text },
  bodyMember: { color: COLORS.white },
  timestamp: { ...TYPE.caption, marginTop: 6 },
  tsAgent: { color: COLORS.textTertiary },
  tsMember: { color: 'rgba(255,255,255,0.5)' },
  composeBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.sm,
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    backgroundColor: COLORS.card,
    gap: SPACING.sm,
  },
  input: {
    flex: 1,
    minHeight: 40,
    maxHeight: 120,
    backgroundColor: COLORS.inputBg,
    borderRadius: RADII.sm,
    paddingHorizontal: SPACING.sm + 4,
    paddingVertical: SPACING.sm,
    ...TYPE.body,
    color: COLORS.text,
  },
  sendBtn: {
    width: 40,
    height: 40,
    borderRadius: RADII.full,
    backgroundColor: COLORS.accent,
    alignItems: 'center',
    justifyContent: 'center',
    ...SHADOWS.button,
  },
  sendBtnDisabled: {
    backgroundColor: COLORS.textTertiary,
    ...SHADOWS.soft,
  },
});
