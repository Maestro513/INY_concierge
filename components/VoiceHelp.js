import { useState, useRef, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Animated,
  Linking,
  Platform,
  Modal,
  TextInput,
  KeyboardAvoidingView,
  TouchableWithoutFeedback,
} from 'react-native';
import { COLORS, RADII, SPACING } from '../constants/theme';
import { API_BASE } from '../constants/api';
import { CALL_NUMBER } from '../constants/data';

const QUICK_QUESTIONS = [
  "What's my specialist copay?",
  'Is Eliquis covered?',
  'Do I have dental?',
];

/* -----------------------------------------------------------
   Detect whether the Web Speech API is available.
   Only meaningful on web; always false on native platforms.
   ----------------------------------------------------------- */
function getSpeechRecognitionClass() {
  if (Platform.OS !== 'web') return null;
  if (typeof window === 'undefined') return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

const SpeechRecognition = getSpeechRecognitionClass();
const hasSpeechSupport = !!SpeechRecognition;

export default function VoiceHelp() {
  const [mode, setMode] = useState('idle');          // idle | listening | typing | thinking | answer
  const [answer, setAnswer] = useState('');
  const [question, setQuestion] = useState('');
  const [typedText, setTypedText] = useState('');     // for native text-input modal
  const [showTypingModal, setShowTypingModal] = useState(false);

  const pulse = useRef(new Animated.Value(1)).current;
  const pulseOp = useRef(new Animated.Value(0)).current;
  const fade = useRef(new Animated.Value(0)).current;
  const recognitionRef = useRef(null);

  /* -------------------------------------------------------
     Pulse animation — active during "listening" on web
     ------------------------------------------------------- */
  useEffect(() => {
    if (mode === 'listening') {
      const anim = Animated.loop(Animated.parallel([
        Animated.sequence([
          Animated.timing(pulse, { toValue: 1.5, duration: 1200, useNativeDriver: true }),
          Animated.timing(pulse, { toValue: 1, duration: 0, useNativeDriver: true }),
        ]),
        Animated.sequence([
          Animated.timing(pulseOp, { toValue: 0, duration: 1200, useNativeDriver: true }),
          Animated.timing(pulseOp, { toValue: 0.5, duration: 0, useNativeDriver: true }),
        ]),
      ]));
      anim.start();
      return () => anim.stop();
    } else {
      pulse.stopAnimation();
      pulseOp.stopAnimation();
      pulse.setValue(1);
      pulseOp.setValue(0);
    }
  }, [mode]);

  /* Fade-in whenever mode or answer changes */
  useEffect(() => {
    if (mode !== 'idle') {
      fade.setValue(0);
      Animated.timing(fade, { toValue: 1, duration: 300, useNativeDriver: true }).start();
    }
  }, [mode, answer]);

  /* Cleanup: stop any active recognition session on unmount */
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch (_) { /* ignore */ }
        recognitionRef.current = null;
      }
    };
  }, []);

  /* -------------------------------------------------------
     Ask the backend
     ------------------------------------------------------- */
  const askBackend = async (q) => {
    setMode('thinking');
    setQuestion(q);
    try {
      const res = await fetch(`${API_BASE}/api/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      });
      const data = await res.json();
      setMode('answer');
      setAnswer(data.answer || "I'm not sure about that.");
    } catch {
      setMode('answer');
      setAnswer("Couldn't reach the server. Please try again or call us.");
    }
  };

  /* -------------------------------------------------------
     Web Speech API helpers
     ------------------------------------------------------- */
  const startWebSpeech = useCallback(() => {
    if (!SpeechRecognition) return false;

    /* Stop any previous session */
    if (recognitionRef.current) {
      try { recognitionRef.current.abort(); } catch (_) { /* ignore */ }
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.continuous = false;
    recognitionRef.current = recognition;

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      if (transcript && transcript.trim().length > 0) {
        recognitionRef.current = null;
        askBackend(transcript.trim());
      }
    };

    recognition.onerror = (event) => {
      recognitionRef.current = null;
      if (event.error === 'no-speech') {
        /* User didn't say anything; return to idle */
        setMode('idle');
      } else if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        /* Microphone permission denied — fall back to typing modal */
        setMode('idle');
        openTypingModal();
      } else {
        setMode('answer');
        setAnswer('Voice recognition failed. Please try again or tap a question below.');
      }
    };

    recognition.onend = () => {
      /* If we're still in listening mode when recognition ends without a result,
         return to idle so the user can try again. */
      setMode((prev) => (prev === 'listening' ? 'idle' : prev));
      recognitionRef.current = null;
    };

    try {
      recognition.start();
      return true;
    } catch {
      recognitionRef.current = null;
      return false;
    }
  }, []);

  const stopWebSpeech = useCallback(() => {
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch (_) { /* ignore */ }
    }
  }, []);

  /* -------------------------------------------------------
     Native text-input modal helpers
     ------------------------------------------------------- */
  const openTypingModal = useCallback(() => {
    setTypedText('');
    setShowTypingModal(true);
    setMode('typing');
  }, []);

  const closeTypingModal = useCallback(() => {
    setShowTypingModal(false);
    setTypedText('');
    setMode('idle');
  }, []);

  const submitTypedQuestion = useCallback(() => {
    const q = typedText.trim();
    setShowTypingModal(false);
    setTypedText('');
    if (q.length > 0) {
      askBackend(q);
    } else {
      setMode('idle');
    }
  }, [typedText]);

  /* -------------------------------------------------------
     Mic button handler — branches on platform
     ------------------------------------------------------- */
  const handleMic = () => {
    if (mode === 'idle' || mode === 'answer') {
      if (Platform.OS === 'web' && hasSpeechSupport) {
        /* Web: use real speech recognition */
        setMode('listening');
        const started = startWebSpeech();
        if (!started) {
          /* Speech API failed to start — fall back to typing */
          openTypingModal();
        }
      } else {
        /* Native (or web without speech support): open text input */
        openTypingModal();
      }
    } else if (mode === 'listening') {
      /* Tap again while listening on web = stop and submit whatever was heard */
      stopWebSpeech();
    }
  };

  /* -------------------------------------------------------
     Status text
     ------------------------------------------------------- */
  const status = {
    idle: 'Tap to ask a question',
    listening: 'Listening...',
    typing: 'Type your question',
    thinking: 'Looking that up...',
    answer: 'Tap to ask another question',
  };

  /* -------------------------------------------------------
     Render
     ------------------------------------------------------- */
  return (
    <View style={s.container}>
      {/* Header */}
      <View style={s.header}>
        <Text style={s.headerTitle}>Help</Text>
        <TouchableOpacity style={s.callBtn} onPress={() => Linking.openURL('tel:' + CALL_NUMBER)}>
          <Text style={s.callText}>Call Us</Text>
        </TouchableOpacity>
      </View>

      {/* Answer / status area */}
      <View style={s.answerArea}>
        {mode === 'answer' && (
          <Animated.View style={{ opacity: fade }}>
            <Text style={s.qText}>"{question}"</Text>
            <Text style={s.aText}>{answer}</Text>
          </Animated.View>
        )}
        {mode === 'thinking' && (
          <Animated.View style={{ opacity: fade, alignItems: 'center' }}>
            <Text style={s.qText}>"{question}"</Text>
            <Text style={s.dots}>...</Text>
          </Animated.View>
        )}
        {mode === 'listening' && (
          <Animated.View style={{ opacity: fade }}>
            <Text style={s.listenText}>Go ahead, I'm listening...</Text>
          </Animated.View>
        )}
        {mode === 'typing' && (
          <Animated.View style={{ opacity: fade }}>
            <Text style={s.listenText}>Type your question below</Text>
          </Animated.View>
        )}
      </View>

      {/* Mic button + pulse rings */}
      <View style={s.micWrap}>
        <Animated.View
          style={[
            s.ring,
            {
              width: 150, height: 150, borderRadius: 75,
              backgroundColor: COLORS.micRing2,
              transform: [{ scale: pulse }],
              opacity: pulseOp,
            },
          ]}
        />
        <Animated.View
          style={[
            s.ring,
            {
              width: 120, height: 120, borderRadius: 60,
              backgroundColor: COLORS.micRing1,
              transform: [{ scale: pulse }],
              opacity: pulseOp,
            },
          ]}
        />
        <TouchableOpacity
          style={[s.mic, mode === 'listening' && s.micActive]}
          onPress={handleMic}
          activeOpacity={0.7}
        >
          <Text style={{ fontSize: 40 }}>{mode === 'listening' ? '⏸' : '🎙'}</Text>
        </TouchableOpacity>
      </View>

      <Text style={s.status}>{status[mode]}</Text>

      {/* Quick-tap question chips */}
      {(mode === 'idle' || mode === 'answer') && (
        <View style={s.quickWrap}>
          <Text style={s.quickLabel}>Or tap a question:</Text>
          <View style={s.quickRow}>
            {QUICK_QUESTIONS.map((q, i) => (
              <TouchableOpacity key={i} style={s.chip} onPress={() => askBackend(q)}>
                <Text style={s.chipText}>{q}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      )}

      {/* -------------------------------------------------------
           Native typing modal (also used as web fallback)
           ------------------------------------------------------- */}
      <Modal
        visible={showTypingModal}
        transparent
        animationType="slide"
        onRequestClose={closeTypingModal}
      >
        <TouchableWithoutFeedback onPress={closeTypingModal}>
          <View style={s.modalOverlay}>
            <TouchableWithoutFeedback onPress={() => {}}>
              <KeyboardAvoidingView
                behavior={Platform.OS === 'ios' ? 'padding' : undefined}
                style={s.modalContent}
              >
                <Text style={s.modalTitle}>Ask a question</Text>
                <TextInput
                  style={s.modalInput}
                  placeholder="Type your question here..."
                  placeholderTextColor={COLORS.textSecondary}
                  value={typedText}
                  onChangeText={setTypedText}
                  autoFocus
                  multiline={false}
                  returnKeyType="send"
                  onSubmitEditing={submitTypedQuestion}
                />
                <View style={s.modalButtons}>
                  <TouchableOpacity style={s.modalCancelBtn} onPress={closeTypingModal}>
                    <Text style={s.modalCancelText}>Cancel</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[s.modalSubmitBtn, !typedText.trim() && s.modalSubmitBtnDisabled]}
                    onPress={submitTypedQuestion}
                    disabled={!typedText.trim()}
                  >
                    <Text style={s.modalSubmitText}>Submit</Text>
                  </TouchableOpacity>
                </View>
              </KeyboardAvoidingView>
            </TouchableWithoutFeedback>
          </View>
        </TouchableWithoutFeedback>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.white,
    borderTopLeftRadius: RADII.xl,
    borderTopRightRadius: RADII.xl,
    shadowColor: COLORS.accent,
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.08,
    shadowRadius: 20,
    elevation: 8,
    alignItems: 'center',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: SPACING.md,
    paddingBottom: 6,
    width: '100%',
  },
  headerTitle: { fontSize: 17, fontWeight: '600', color: COLORS.text },
  callBtn: { backgroundColor: COLORS.accent, borderRadius: 20, paddingHorizontal: 16, paddingVertical: 8 },
  callText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  answerArea: { flex: 1, justifyContent: 'center', paddingHorizontal: 24, width: '100%' },
  qText: { fontSize: 14, color: COLORS.textSecondary, fontStyle: 'italic', textAlign: 'center', marginBottom: 10 },
  aText: { fontSize: 17, color: COLORS.text, lineHeight: 26, textAlign: 'center', fontWeight: '500' },
  listenText: { fontSize: 18, color: COLORS.accent, fontWeight: '600', textAlign: 'center' },
  dots: { fontSize: 24, color: COLORS.accent, textAlign: 'center', letterSpacing: 4 },
  micWrap: { width: 100, height: 100, justifyContent: 'center', alignItems: 'center' },
  ring: { position: 'absolute' },
  mic: {
    width: 88, height: 88, borderRadius: 44,
    backgroundColor: COLORS.accent,
    justifyContent: 'center', alignItems: 'center',
    shadowColor: COLORS.accent, shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.3, shadowRadius: 16, elevation: 10,
  },
  micActive: { backgroundColor: COLORS.accentDark, transform: [{ scale: 1.08 }] },
  status: { fontSize: 14, color: COLORS.textSecondary, fontWeight: '500', marginTop: 10 },
  quickWrap: { width: '100%', paddingHorizontal: 20, paddingTop: 12, paddingBottom: 28 },
  quickLabel: { fontSize: 13, color: COLORS.textSecondary, textAlign: 'center', marginBottom: 8 },
  quickRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 6 },
  chip: {
    backgroundColor: COLORS.accentLight, borderRadius: 20,
    paddingHorizontal: 14, paddingVertical: 8,
    borderWidth: 1, borderColor: 'rgba(123,63,191,0.12)',
  },
  chipText: { fontSize: 13, fontWeight: '500', color: COLORS.accentDark },

  /* Modal styles */
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: RADII.xl,
    borderTopRightRadius: RADII.xl,
    paddingHorizontal: 24,
    paddingTop: 24,
    paddingBottom: 36,
    shadowColor: COLORS.accent,
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.12,
    shadowRadius: 20,
    elevation: 12,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.text,
    textAlign: 'center',
    marginBottom: 16,
  },
  modalInput: {
    backgroundColor: COLORS.inputBg,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 16,
    color: COLORS.text,
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: 16,
  },
  modalButtons: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
  },
  modalCancelBtn: {
    flex: 1,
    backgroundColor: COLORS.inputBg,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  modalCancelText: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.textSecondary,
  },
  modalSubmitBtn: {
    flex: 1,
    backgroundColor: COLORS.accent,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
  },
  modalSubmitBtnDisabled: {
    opacity: 0.5,
  },
  modalSubmitText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
});
