import { useState, useRef, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Animated, Linking } from 'react-native';
import { COLORS, RADII, SPACING } from '../constants/theme';
import { API_BASE } from '../constants/api';
import { CALL_NUMBER } from '../constants/data';

const QUICK_QUESTIONS = [
  "What's my specialist copay?",
  'Is Eliquis covered?',
  'Do I have dental?',
];

export default function VoiceHelp() {
  const [mode, setMode] = useState('idle');
  const [answer, setAnswer] = useState('');
  const [question, setQuestion] = useState('');
  const pulse = useRef(new Animated.Value(1)).current;
  const pulseOp = useRef(new Animated.Value(0)).current;
  const fade = useRef(new Animated.Value(0)).current;
  const timers = useRef([]);

  useEffect(() => {
    if (mode === 'listening') {
      const anim = Animated.loop(Animated.parallel([
        Animated.sequence([Animated.timing(pulse, { toValue: 1.5, duration: 1200, useNativeDriver: true }), Animated.timing(pulse, { toValue: 1, duration: 0, useNativeDriver: true })]),
        Animated.sequence([Animated.timing(pulseOp, { toValue: 0, duration: 1200, useNativeDriver: true }), Animated.timing(pulseOp, { toValue: 0.5, duration: 0, useNativeDriver: true })]),
      ]));
      anim.start();
      return () => anim.stop();
    } else { pulse.stopAnimation(); pulseOp.stopAnimation(); pulse.setValue(1); pulseOp.setValue(0); }
  }, [mode]);

  useEffect(() => {
    if (mode !== 'idle') { fade.setValue(0); Animated.timing(fade, { toValue: 1, duration: 300, useNativeDriver: true }).start(); }
  }, [mode, answer]);

  useEffect(() => {
    return () => timers.current.forEach(clearTimeout);
  }, []);

  const delay = useCallback((fn, ms) => {
    const id = setTimeout(fn, ms);
    timers.current.push(id);
    return id;
  }, []);

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

  const handleMic = () => {
    if (mode === 'idle' || mode === 'answer') {
      setMode('listening');
      // Simulated voice — picks a random quick question after delay
      delay(() => {
        const q = QUICK_QUESTIONS[Math.floor(Math.random() * QUICK_QUESTIONS.length)];
        askBackend(q);
      }, 2500);
    } else if (mode === 'listening') {
      askBackend('Is Eliquis covered?');
    }
  };

  const status = { idle: 'Tap to ask a question', listening: 'Listening...', thinking: 'Looking that up...', answer: 'Tap to ask another question' };

  return (
    <View style={s.container}>
      <View style={s.header}>
        <Text style={s.headerTitle}>Help</Text>
        <TouchableOpacity style={s.callBtn} onPress={() => Linking.openURL('tel:' + CALL_NUMBER)}><Text style={s.callText}>Call Us</Text></TouchableOpacity>
      </View>
      <View style={s.answerArea}>
        {mode === 'answer' && <Animated.View style={{ opacity: fade }}><Text style={s.qText}>"{question}"</Text><Text style={s.aText}>{answer}</Text></Animated.View>}
        {mode === 'thinking' && <Animated.View style={{ opacity: fade, alignItems: 'center' }}><Text style={s.qText}>"{question}"</Text><Text style={s.dots}>...</Text></Animated.View>}
        {mode === 'listening' && <Animated.View style={{ opacity: fade }}><Text style={s.listenText}>Go ahead, I'm listening...</Text></Animated.View>}
      </View>
      <View style={s.micWrap}>
        <Animated.View style={[s.ring, { width: 150, height: 150, borderRadius: 75, backgroundColor: COLORS.micRing2, transform: [{ scale: pulse }], opacity: pulseOp }]} />
        <Animated.View style={[s.ring, { width: 120, height: 120, borderRadius: 60, backgroundColor: COLORS.micRing1, transform: [{ scale: pulse }], opacity: pulseOp }]} />
        <TouchableOpacity style={[s.mic, mode === 'listening' && s.micActive]} onPress={handleMic} activeOpacity={0.7}>
          <Text style={{ fontSize: 40 }}>{mode === 'listening' ? '⏸' : '🎙'}</Text>
        </TouchableOpacity>
      </View>
      <Text style={s.status}>{status[mode]}</Text>
      {(mode === 'idle' || mode === 'answer') && (
        <View style={s.quickWrap}>
          <Text style={s.quickLabel}>Or tap a question:</Text>
          <View style={s.quickRow}>
            {QUICK_QUESTIONS.map((q, i) => <TouchableOpacity key={i} style={s.chip} onPress={() => askBackend(q)}><Text style={s.chipText}>{q}</Text></TouchableOpacity>)}
          </View>
        </View>
      )}
    </View>
  );
}
const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.white, borderTopLeftRadius: RADII.xl, borderTopRightRadius: RADII.xl, shadowColor: COLORS.accent, shadowOffset: { width: 0, height: -4 }, shadowOpacity: 0.08, shadowRadius: 20, elevation: 8, alignItems: 'center' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 20, paddingTop: SPACING.md, paddingBottom: 6, width: '100%' },
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
  mic: { width: 88, height: 88, borderRadius: 44, backgroundColor: COLORS.accent, justifyContent: 'center', alignItems: 'center', shadowColor: COLORS.accent, shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.3, shadowRadius: 16, elevation: 10 },
  micActive: { backgroundColor: COLORS.accentDark, transform: [{ scale: 1.08 }] },
  status: { fontSize: 14, color: COLORS.textSecondary, fontWeight: '500', marginTop: 10 },
  quickWrap: { width: '100%', paddingHorizontal: 20, paddingTop: 12, paddingBottom: 28 },
  quickLabel: { fontSize: 13, color: COLORS.textSecondary, textAlign: 'center', marginBottom: 8 },
  quickRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 6 },
  chip: { backgroundColor: COLORS.accentLight, borderRadius: 20, paddingHorizontal: 14, paddingVertical: 8, borderWidth: 1, borderColor: 'rgba(123,63,191,0.12)' },
  chipText: { fontSize: 13, fontWeight: '500', color: COLORS.accentDark },
});
