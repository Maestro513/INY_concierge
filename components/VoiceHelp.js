import { useState, useRef, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Animated,
  Linking, Platform, ScrollView, TextInput, KeyboardAvoidingView, Keyboard,
} from 'react-native';
import { ExpoSpeechRecognitionModule, useSpeechRecognitionEvent } from 'expo-speech-recognition';
import * as Speech from 'expo-speech';
import { useRouter } from 'expo-router';
import { COLORS, RADII, SPACING } from '../constants/theme';
import { CALL_NUMBER } from '../constants/data';
import { API_URL } from '../constants/api';

// --- Doctor search keywords and specialty extraction ---

const DOCTOR_TRIGGERS = [
  'find me a', 'find a', 'look for a', 'search for a', 'i need a',
  'find me an', 'find an', 'look for an', 'search for an', 'i need an',
  'where is a', 'where can i find', 'doctor near', 'doctors near',
  'any', 'are there any',
];

const SPECIALTY_KEYWORDS = {
  'dermatologist': 'dermatologist', 'dermatology': 'dermatologist', 'skin doctor': 'dermatologist',
  'cardiologist': 'cardiologist', 'cardiology': 'cardiologist', 'heart doctor': 'cardiologist',
  'primary care': 'primary care', 'pcp': 'primary care', 'general doctor': 'primary care',
  'family doctor': 'family medicine', 'family medicine': 'family medicine',
  'eye doctor': 'ophthalmologist', 'ophthalmologist': 'ophthalmologist', 'ophthalmology': 'ophthalmologist',
  'foot doctor': 'podiatrist', 'podiatrist': 'podiatrist', 'podiatry': 'podiatrist',
  'ent': 'ent', 'ear nose throat': 'ent', 'ear nose and throat': 'ent',
  'orthopedic': 'orthopedic', 'orthopedist': 'orthopedic', 'bone doctor': 'orthopedic',
  'neurologist': 'neurologist', 'neurology': 'neurologist', 'brain doctor': 'neurologist',
  'urologist': 'urologist', 'urology': 'urologist',
  'psychiatrist': 'psychiatrist', 'psychiatry': 'psychiatrist', 'mental health': 'psychiatrist',
  'pulmonologist': 'pulmonologist', 'lung doctor': 'pulmonologist', 'pulmonology': 'pulmonologist',
  'gastroenterologist': 'gastroenterologist', 'stomach doctor': 'gastroenterologist', 'gi doctor': 'gastroenterologist',
  'endocrinologist': 'endocrinologist', 'endocrinology': 'endocrinologist', 'diabetes doctor': 'endocrinologist',
  'rheumatologist': 'rheumatologist', 'rheumatology': 'rheumatologist',
  'oncologist': 'oncologist', 'oncology': 'oncologist', 'cancer doctor': 'oncologist',
  'surgeon': 'surgeon', 'surgery': 'surgeon',
  'pain doctor': 'pain management', 'pain management': 'pain management',
  'physical therapist': 'physical therapist', 'physical therapy': 'physical therapist', 'pt': 'physical therapist',
  'dentist': 'dentist', 'dental': 'dentist',
  'optometrist': 'optometrist',
  'nephrologist': 'nephrologist', 'kidney doctor': 'nephrologist',
  'obgyn': 'obgyn', 'ob gyn': 'obgyn', 'gynecologist': 'obgyn',
  'pediatrician': 'pediatrician', 'pediatrics': 'pediatrician',
  'doctor': 'primary care', 'doctors': 'primary care',
};

function detectDoctorSearch(text) {
  const lower = text.toLowerCase();

  const hasTrigger = DOCTOR_TRIGGERS.some(t => lower.includes(t))
    || lower.includes('doctor') || lower.includes('specialist')
    || lower.includes('near me') || lower.includes('nearby');

  if (!hasTrigger) return null;

  const sortedKeys = Object.keys(SPECIALTY_KEYWORDS).sort((a, b) => b.length - a.length);
  for (const key of sortedKeys) {
    if (lower.includes(key)) {
      return SPECIALTY_KEYWORDS[key];
    }
  }

  if (lower.includes('doctor') || lower.includes('specialist')) {
    return 'primary care';
  }

  return null;
}


// --- Drug detection and CMS lookup ---

const DRUG_PATTERNS = [
  /how much (?:does|is|will) (.+?) cost/i,
  /how much (?:does|is|will) (.+)/i,
  /how much (?:do i|would i|will i) pay for (.+)/i,
  /what(?:'s| is) the (?:cost|copay|price) (?:of|for) (.+)/i,
  /what(?:'s| is| does) (.+?) cost/i,
  /is (.+?) (?:covered|on my plan|on the formulary|in my plan)/i,
  /is (.+?) covered/i,
  /what tier is (.+)/i,
  /(?:cost|copay|price|tier) (?:of|for) (.+)/i,
  /(?:do i|does my plan) cover (.+)/i,
  /(?:look up|check|check on|find) (.+)/i,
  /tell me about (.+?) (?:coverage|cost|copay|tier|prescription|medication)/i,
  /tell me about (.+)/i,
  /(.+?) (?:copay|cost|tier|coverage)/i,
];

const DRUG_KEYWORDS = [
  'cost', 'copay', 'cover', 'tier', 'drug', 'medication',
  'medicine', 'prescription', 'rx', 'generic', 'brand',
  'how much', 'formulary', 'pay for',
];

function isDrugQuestion(text) {
  const lower = text.toLowerCase();
  // Don't trigger on doctor searches
  if (detectDoctorSearch(text)) return false;
  return DRUG_KEYWORDS.some(kw => lower.includes(kw));
}

function extractDrugName(question) {
  for (const pattern of DRUG_PATTERNS) {
    const match = question.match(pattern);
    if (match && match[1]) {
      let name = match[1].trim()
        .replace(/\?$/, '')
        .replace(/^(my|the|a|an)\b\s*/i, '')
        .replace(/ ?(pill|tablet|capsule|medication|medicine|drug|prescription|cost|copay)s?$/i, '')
        .replace(/ ?(on my plan|on the formulary|in my plan|for me)$/i, '')
        .trim();
      // Skip common filler / non-drug words
      const skip = [
        'it', 'that', 'this', 'me', 'i', 'much', 'about', 'for', 'my', 'your',
        'benefits', 'plan', 'insurance', 'premium', 'coverage', 'deductible',
        'options', 'something', 'anything', 'everything',
      ];
      if (name.length > 1 && name.length < 50 && !skip.includes(name.toLowerCase())) return name;
    }
  }
  return null;
}

function formatDrugResponse(data) {
  const parts = [];
  parts.push(`${data.drug_name} is on Tier ${data.tier}, ${data.tier_label}.`);

  if (data.copay_30day_preferred !== null && data.copay_30day_preferred !== undefined) {
    if (typeof data.copay_30day_preferred === 'number') {
      parts.push(`Your copay is $${data.copay_30day_preferred} for a 30-day supply at a preferred pharmacy.`);
    } else {
      parts.push(`Your cost is ${data.copay_30day_preferred} for a 30-day supply at a preferred pharmacy.`);
    }
  }

  if (data.deductible_applies) {
    parts.push('Your deductible applies to this drug.');
  }

  const restrictions = [];
  if (data.prior_auth) restrictions.push('prior authorization');
  if (data.step_therapy) restrictions.push('step therapy');
  if (data.quantity_limit) {
    restrictions.push(`quantity limit of ${data.quantity_limit_amount} per ${data.quantity_limit_days} days`);
  }
  if (restrictions.length > 0) {
    parts.push(`Restrictions: ${restrictions.join(', ')}.`);
  }

  return parts.join(' ');
}

async function lookupDrug(planNumber, drugName) {
  try {
    const res = await fetch(`${API_URL}/cms/drug/${encodeURIComponent(planNumber)}/${encodeURIComponent(drugName)}`);
    if (!res.ok) return null;
    const data = await res.json();
    if (data.error) return null;
    return formatDrugResponse(data);
  } catch (err) {
    console.log('Drug lookup error:', err);
    return null;
  }
}


// --- General ask ---

async function askBackend(question, planId) {
  try {
    const res = await fetch(`${API_URL}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, plan_number: planId }),
    });
    const data = await res.json();
    return data.answer;
  } catch (err) {
    console.log('API error:', err);
    return "I'm having trouble connecting right now. Please try again or call us at (844) 463-2931.";
  }
}

function speakResponse(text) {
  Speech.stop();
  Speech.speak(text, {
    language: 'en-US',
    rate: 0.9,
    pitch: 1.0,
  });
}

export default function VoiceHelp({ planNumber, planName, zipCode }) {
  const router = useRouter();
  const [mode, setMode] = useState('idle');
  const [answer, setAnswer] = useState('');
  const [question, setQuestion] = useState('');
  const [liveText, setLiveText] = useState('');
  const [typedText, setTypedText] = useState('');
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const pulse = useRef(new Animated.Value(1)).current;
  const pulseOp = useRef(new Animated.Value(0)).current;
  const fade = useRef(new Animated.Value(0)).current;

  // --- Keyboard tracking ---
  useEffect(() => {
    const showSub = Keyboard.addListener('keyboardDidShow', () => setKeyboardVisible(true));
    const hideSub = Keyboard.addListener('keyboardDidHide', () => setKeyboardVisible(false));
    return () => { showSub.remove(); hideSub.remove(); };
  }, []);

  // --- Track speech ending ---
  useEffect(() => {
    let interval;
    if (isSpeaking) {
      interval = setInterval(async () => {
        const speaking = await Speech.isSpeakingAsync();
        if (!speaking) setIsSpeaking(false);
      }, 500);
    }
    return () => clearInterval(interval);
  }, [isSpeaking]);

  // --- Speech Recognition Events ---
  useSpeechRecognitionEvent('result', (event) => {
    const transcript = event.results[0]?.transcript || '';
    setLiveText(transcript);
    if (event.isFinal && transcript.trim().length > 0) {
      ExpoSpeechRecognitionModule.stop();
      processQuestion(transcript.trim());
    }
  });

  useSpeechRecognitionEvent('end', () => {
    if (mode === 'listening') {
      if (liveText.trim().length > 0) {
        processQuestion(liveText.trim());
      } else {
        setMode('idle');
        setLiveText('');
      }
    }
  });

  useSpeechRecognitionEvent('error', (event) => {
    console.log('Speech error:', event.error, event.message);
    // Ignore 'aborted' — we trigger it intentionally via stop()
    if (event.error === 'aborted') return;
    if (mode === 'listening') {
      setMode('idle');
      setLiveText('');
    }
  });

  // --- Pulse animation ---
  useEffect(() => {
    if (mode === 'listening') {
      Animated.loop(Animated.parallel([
        Animated.sequence([
          Animated.timing(pulse, { toValue: 1.5, duration: 1200, useNativeDriver: true }),
          Animated.timing(pulse, { toValue: 1, duration: 0, useNativeDriver: true }),
        ]),
        Animated.sequence([
          Animated.timing(pulseOp, { toValue: 0, duration: 1200, useNativeDriver: true }),
          Animated.timing(pulseOp, { toValue: 0.5, duration: 0, useNativeDriver: true }),
        ]),
      ])).start();
    } else {
      pulse.stopAnimation(); pulseOp.stopAnimation();
      pulse.setValue(1); pulseOp.setValue(0);
    }
  }, [mode]);

  useEffect(() => {
    if (mode !== 'idle') {
      fade.setValue(0);
      Animated.timing(fade, { toValue: 1, duration: 300, useNativeDriver: true }).start();
    }
  }, [mode, answer]);

  // --- Actions ---
  const processQuestion = async (q) => {
    Speech.stop();
    setIsSpeaking(false);
    setQuestion(q);
    setLiveText('');
    setTypedText('');
    Keyboard.dismiss();

    // 1. Check if this is a doctor search request
    const specialty = detectDoctorSearch(q);
    if (specialty) {
      speakResponse(`Searching for a ${specialty} near you.`);
      setIsSpeaking(true);
      setMode('idle');

      setTimeout(() => {
        router.push({
          pathname: '/doctor-results',
          params: {
            specialty,
            zipCode: zipCode || '33434',
            planName: planName || '',
          },
        });
      }, 800);
      return;
    }

    // 2. Try to extract a drug name and look it up in CMS first
    setMode('thinking');
    let response;
    const drugName = extractDrugName(q);

    if (drugName && planNumber) {
      response = await lookupDrug(planNumber, drugName);
    }

    // 3. Fall back to Claude with SOB PDF context
    if (!response) {
      if (drugName || isDrugQuestion(q)) {
        // Drug query — enhance the prompt so Claude pulls the right SOB sections
        const drugRef = drugName || 'the medication asked about';
        const enhanced = `Regarding prescription drug coverage and formulary: ${q}. `
          + `What tier is ${drugRef} on and what is the copay? `
          + `Check the drug tier and prescription cost information.`;
        response = await askBackend(enhanced, planNumber);
      } else {
        response = await askBackend(q, planNumber);
      }
    }

    setMode('answer');
    setAnswer(response);
    speakResponse(response);
    setIsSpeaking(true);
  };

  const toggleSpeech = async () => {
    const speaking = await Speech.isSpeakingAsync();
    if (speaking) {
      Speech.stop();
      setIsSpeaking(false);
    } else if (answer) {
      speakResponse(answer);
      setIsSpeaking(true);
    }
  };

  const startListening = async () => {
    Speech.stop();
    setIsSpeaking(false);
    const { granted } = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
    if (!granted) return;
    setMode('listening');
    setLiveText('');
    Keyboard.dismiss();
    ExpoSpeechRecognitionModule.start({
      lang: 'en-US',
      interimResults: true,
      continuous: true,
    });
  };

  const stopListening = () => {
    ExpoSpeechRecognitionModule.stop();
  };

  const handleMic = () => {
    if (mode === 'listening') stopListening();
    else startListening();
  };

  const handleSend = () => {
    const q = typedText.trim();
    if (q.length > 0) processQuestion(q);
  };

  const statusText = {
    idle: 'Tap mic or type your question',
    listening: 'Listening...',
    thinking: 'Looking that up...',
    answer: 'Tap mic to ask another question',
  };

  return (
    <KeyboardAvoidingView
      style={s.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
    >
      {/* Header */}
      <View style={s.header}>
        <Text style={s.headerTitle}>💬 Help</Text>
        <TouchableOpacity style={s.callBtn} onPress={() => Linking.openURL('tel:' + CALL_NUMBER)}>
          <Text style={s.callText}>📞 Call Us</Text>
        </TouchableOpacity>
      </View>

      {/* Answer / Status Area */}
      <ScrollView style={s.answerScroll} contentContainerStyle={s.answerArea}>
        {mode === 'idle' && (
          <View style={s.idleWrap}>
            <Text style={s.idleEmoji}>🎙</Text>
            <Text style={s.idleText}>Ask me anything about{'\n'}your plan or find a doctor.</Text>
          </View>
        )}
        {mode === 'answer' && (
          <Animated.View style={{ opacity: fade }}>
            <Text style={s.qText}>"{question}"</Text>
            <Text style={s.aText}>{answer}</Text>
            <TouchableOpacity style={s.speakerBtn} onPress={toggleSpeech}>
              <Text style={s.speakerText}>{isSpeaking ? '🔇 Stop' : '🔊 Listen again'}</Text>
            </TouchableOpacity>
          </Animated.View>
        )}
        {mode === 'thinking' && (
          <Animated.View style={{ opacity: fade, alignItems: 'center' }}>
            <Text style={s.qText}>"{question}"</Text>
            <Text style={s.dots}>● ● ●</Text>
          </Animated.View>
        )}
        {mode === 'listening' && (
          <Animated.View style={{ opacity: fade }}>
            <Text style={s.listenText}>
              {liveText || "Go ahead, I'm listening..."}
            </Text>
          </Animated.View>
        )}
      </ScrollView>

      {/* Mic Button — hide when keyboard is up */}
      {!keyboardVisible && (
        <>
          <View style={s.micWrap}>
            <Animated.View style={[s.ring, {
              width: 150, height: 150, borderRadius: 75,
              backgroundColor: COLORS.micRing2,
              transform: [{ scale: pulse }], opacity: pulseOp,
            }]} />
            <Animated.View style={[s.ring, {
              width: 120, height: 120, borderRadius: 60,
              backgroundColor: COLORS.micRing1,
              transform: [{ scale: pulse }], opacity: pulseOp,
            }]} />
            <TouchableOpacity
              style={[s.mic, mode === 'listening' && s.micActive]}
              onPress={handleMic}
              activeOpacity={0.7}
            >
              <Text style={{ fontSize: 40 }}>{mode === 'listening' ? '⏸' : '🎙'}</Text>
            </TouchableOpacity>
          </View>
          <Text style={s.status}>{statusText[mode]}</Text>
        </>
      )}

      {/* Chat Input Bar */}
      <View style={s.inputBar}>
        <TextInput
          style={s.textInput}
          placeholder="Type your question..."
          placeholderTextColor={COLORS.textSecondary}
          value={typedText}
          onChangeText={setTypedText}
          onSubmitEditing={handleSend}
          returnKeyType="send"
          editable={mode !== 'thinking' && mode !== 'listening'}
        />
        <TouchableOpacity
          style={[s.sendBtn, typedText.trim().length === 0 && s.sendBtnDisabled]}
          onPress={handleSend}
          disabled={typedText.trim().length === 0 || mode === 'thinking'}
        >
          <Text style={s.sendText}>↑</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  container: {
    flex: 1, backgroundColor: COLORS.white,
    borderTopLeftRadius: RADII.xl, borderTopRightRadius: RADII.xl,
    shadowColor: COLORS.accent, shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.08, shadowRadius: 20, elevation: 8,
  },
  header: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 20, paddingTop: SPACING.md, paddingBottom: 6, width: '100%',
  },
  headerTitle: { fontSize: 17, fontWeight: '600', color: COLORS.text },
  callBtn: { backgroundColor: COLORS.accent, borderRadius: 20, paddingHorizontal: 16, paddingVertical: 8 },
  callText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  answerScroll: { flex: 1, width: '100%' },
  answerArea: { justifyContent: 'center', paddingHorizontal: 24, flexGrow: 1 },
  idleWrap: { alignItems: 'center' },
  idleEmoji: { fontSize: 48, marginBottom: 12 },
  idleText: { fontSize: 18, color: COLORS.textSecondary, textAlign: 'center', lineHeight: 26 },
  qText: { fontSize: 14, color: COLORS.textSecondary, fontStyle: 'italic', textAlign: 'center', marginBottom: 10 },
  aText: { fontSize: 17, color: COLORS.text, lineHeight: 26, textAlign: 'center', fontWeight: '500' },
  listenText: { fontSize: 18, color: COLORS.accent, fontWeight: '600', textAlign: 'center' },
  dots: { fontSize: 16, color: COLORS.accent, textAlign: 'center', letterSpacing: 4 },
  speakerBtn: { alignSelf: 'center', marginTop: 16, paddingHorizontal: 16, paddingVertical: 8, backgroundColor: COLORS.accentLight, borderRadius: 20 },
  speakerText: { fontSize: 14, fontWeight: '600', color: COLORS.accentDark },
  micWrap: { width: 100, height: 100, justifyContent: 'center', alignItems: 'center', alignSelf: 'center' },
  ring: { position: 'absolute' },
  mic: {
    width: 88, height: 88, borderRadius: 44, backgroundColor: COLORS.accent,
    justifyContent: 'center', alignItems: 'center',
    shadowColor: COLORS.accent, shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.3, shadowRadius: 16, elevation: 10,
  },
  micActive: { backgroundColor: COLORS.accentDark, transform: [{ scale: 1.08 }] },
  status: { fontSize: 14, color: COLORS.textSecondary, fontWeight: '500', marginTop: 10, textAlign: 'center' },
  inputBar: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 12, paddingVertical: 10,
    borderTopWidth: 1, borderTopColor: COLORS.border,
    backgroundColor: COLORS.white,
  },
  textInput: {
    flex: 1, backgroundColor: COLORS.bg, borderRadius: 22,
    paddingHorizontal: 16, paddingVertical: 10,
    fontSize: 15, color: COLORS.text,
    borderWidth: 1, borderColor: COLORS.border,
    maxHeight: 80,
  },
  sendBtn: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: COLORS.accent, justifyContent: 'center', alignItems: 'center',
    marginLeft: 8,
  },
  sendBtnDisabled: { backgroundColor: COLORS.border },
  sendText: { color: '#fff', fontSize: 18, fontWeight: '700', marginTop: -1 },
});