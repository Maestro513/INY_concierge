import { useState, useRef, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Animated,
  Linking, Platform, ScrollView, TextInput, KeyboardAvoidingView, Keyboard,
  ActivityIndicator,
} from 'react-native';
import { ExpoSpeechRecognitionModule, useSpeechRecognitionEvent } from 'expo-speech-recognition';
import * as Speech from 'expo-speech';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SPACING, SHADOWS, TYPE, MOTION } from '../constants/theme';
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
    if (lower.includes(key)) return SPECIALTY_KEYWORDS[key];
  }
  if (lower.includes('doctor') || lower.includes('specialist')) return 'primary care';
  return null;
}


// --- Drug detection and CMS lookup ---

const DRUG_PATTERNS = [
  /how much (?:does|is|will) (.+?) cost/i,
  /how much (?:does|is|will) (.+)/i,
  /how much (?:do i|would i|will i) pay for (.+)/i,
  /what(?:'s| is| does) (.+?) cost/i,
  /what(?:'s| is) the (?:cost|copay|price) (?:of|for) (.+)/i,
  /is (.+?) (?:covered|on my plan|on the formulary|in my plan)/i,
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
  if (data.deductible_applies) parts.push('Your deductible applies to this drug.');
  const restrictions = [];
  if (data.prior_auth) restrictions.push('prior authorization');
  if (data.step_therapy) restrictions.push('step therapy');
  if (data.quantity_limit) {
    restrictions.push(`quantity limit of ${data.quantity_limit_amount} per ${data.quantity_limit_days} days`);
  }
  if (restrictions.length > 0) parts.push(`Restrictions: ${restrictions.join(', ')}.`);
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


// --- Benefit detection and CMS lookup ---

const BENEFIT_PATTERNS = {
  vision: { keywords: ['vision', 'eye exam', 'eyeglasses', 'glasses', 'eyewear', 'contacts', 'contact lenses', 'eye care', 'optometrist visit'], endpoint: 'vision', format: formatVisionResponse },
  dental: { keywords: ['dental', 'dentist', 'teeth', 'tooth', 'cleaning', 'crown', 'root canal', 'filling', 'denture', 'oral'], endpoint: 'dental', format: formatDentalResponse },
  hearing: { keywords: ['hearing', 'hearing aid', 'hearing aids', 'hearing exam', 'hearing test', 'audiologist', 'ear exam'], endpoint: 'hearing', format: formatHearingResponse },
  otc: { keywords: ['otc', 'over the counter', 'over-the-counter', 'otc allowance', 'otc benefit'], endpoint: 'otc', format: formatOTCResponse },
  flex: { keywords: ['flex card', 'flex benefit', 'ssbci', 'supplemental benefit', 'food benefit', 'grocery'], endpoint: 'flex', format: formatFlexResponse },
  giveback: { keywords: ['part b', 'part b giveback', 'premium reduction', 'giveback', 'part b premium'], endpoint: 'giveback', format: formatGivebackResponse },
};

function detectBenefitQuestion(text) {
  const lower = text.toLowerCase();
  if (detectDoctorSearch(text)) return null;
  for (const [category, config] of Object.entries(BENEFIT_PATTERNS)) {
    const sorted = [...config.keywords].sort((a, b) => b.length - a.length);
    for (const kw of sorted) {
      if (lower.includes(kw)) return config;
    }
  }
  return null;
}

function formatVisionResponse(data) {
  const parts = [];
  if (data.has_eye_exam) { const exam = data.eye_exam; parts.push(`Your eye exam copay is ${exam.copay || '$0'}.`); if (exam.exams_per_year) parts.push(`You get ${exam.exams_per_year} exam per year.`); }
  if (data.has_eyewear) { const ew = data.eyewear; const max = ew.max_benefit; if (max) { parts.push(`For eyewear, you have a ${max} per year allowance with a ${ew.copay || '$0'} copay.`); } else { parts.push(`Eyewear copay is ${ew.copay || '$0'}.`); } }
  return parts.length > 0 ? parts.join(' ') : "I don't see vision benefits on your plan. Call us at (844) 463-2931 and we'll look into it.";
}

function formatDentalResponse(data) {
  const parts = [];
  if (data.has_preventive) { const pv = data.preventive; const max = pv.max_benefit; if (max) { parts.push(`Preventive dental like cleanings and exams is ${pv.copay || '$0'} copay with a ${max} per year maximum.`); } else { parts.push(`Preventive dental is ${pv.copay || '$0'} copay.`); } }
  if (data.has_comprehensive) { const cmp = data.comprehensive; if (cmp.max_benefit) parts.push(`Comprehensive dental has a ${cmp.max_benefit} per year maximum.`); }
  return parts.length > 0 ? parts.join(' ') : "I don't see dental benefits on your plan. Call us at (844) 463-2931 and we'll look into it.";
}

function formatHearingResponse(data) {
  const parts = [];
  if (data.has_hearing_exam) { const exam = data.hearing_exam; parts.push(`Your hearing exam copay is ${exam.copay || '$0'}.`); if (exam.exams_per_year) parts.push(`You get ${exam.exams_per_year} exam per year.`); }
  if (data.has_hearing_aids) { const aids = data.hearing_aids; const details = []; if (aids.max_benefit) details.push(`up to ${aids.max_benefit}`); if (aids.copay && aids.copay !== '$0') details.push(`${aids.copay} copay`); if (aids.aids_allowed) details.push(`${aids.aids_allowed} hearing aids`); if (aids.period) details.push(aids.period); parts.push(details.length > 0 ? `For hearing aids, your plan covers ${details.join(', ')}.` : 'Hearing aids are covered.'); }
  return parts.length > 0 ? parts.join(' ') : "I don't see hearing benefits on your plan. Call us at (844) 463-2931 and we'll look into it.";
}

function formatOTCResponse(data) {
  if (!data.has_otc) return "I don't see an OTC benefit on your plan. Call us at (844) 463-2931 and we'll look into it.";
  return `Your plan includes ${data.amount || ''} ${data.period || ''} for over-the-counter items.`.trim();
}

function formatFlexResponse(data) {
  if (!data.has_ssbci || !data.benefits || data.benefits.length === 0) return "I don't see a flex card benefit on your plan. Call us at (844) 463-2931 and we'll look into it.";
  const cats = data.benefits.map(b => b.amount && b.amount !== 'Included' ? `${b.category} (${b.amount})` : b.category);
  return `Your plan has a flex card that covers: ${cats.join(', ')}.`;
}

function formatGivebackResponse(data) {
  if (!data.has_giveback) return "Your plan does not include a Part B premium giveback.";
  return `Your plan gives back ${data.monthly_amount} per month on your Part B premium.`;
}

async function lookupBenefit(planNumber, config) {
  try {
    const res = await fetch(`${API_URL}/cms/benefits/${encodeURIComponent(planNumber)}/${config.endpoint}`);
    if (!res.ok) return null;
    return config.format(await res.json());
  } catch (err) { console.log('Benefit lookup error:', err); return null; }
}


// --- General ask ---

async function askBackend(question, planId) {
  try {
    const res = await fetch(`${API_URL}/ask`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, plan_number: planId }) });
    const data = await res.json();
    return data.answer;
  } catch (err) { console.log('API error:', err); return "I'm having trouble connecting right now. Please try again or call us at (844) 463-2931."; }
}

function speakResponse(text) {
  Speech.stop();
  Speech.speak(text, { language: 'en-US', rate: 0.9, pitch: 1.0 });
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
      if (liveText.trim().length > 0) processQuestion(liveText.trim());
      else { setMode('idle'); setLiveText(''); }
    }
  });

  useSpeechRecognitionEvent('error', (event) => {
    console.log('Speech error:', event.error, event.message);
    if (event.error === 'aborted') return;
    if (mode === 'listening') { setMode('idle'); setLiveText(''); }
  });

  // --- Pulse animation (3-ring ripple) ---
  useEffect(() => {
    if (mode === 'listening') {
      Animated.loop(Animated.parallel([
        Animated.sequence([
          Animated.timing(pulse, { toValue: 1.6, duration: 1400, useNativeDriver: true }),
          Animated.timing(pulse, { toValue: 1, duration: 0, useNativeDriver: true }),
        ]),
        Animated.sequence([
          Animated.timing(pulseOp, { toValue: 0, duration: 1400, useNativeDriver: true }),
          Animated.timing(pulseOp, { toValue: 0.6, duration: 0, useNativeDriver: true }),
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
      Animated.timing(fade, { toValue: 1, duration: MOTION.slow, useNativeDriver: true }).start();
    }
  }, [mode, answer]);

  // --- Actions ---
  const processQuestion = async (q) => {
    Speech.stop(); setIsSpeaking(false);
    setQuestion(q); setLiveText(''); setTypedText('');
    Keyboard.dismiss();

    const specialty = detectDoctorSearch(q);
    if (specialty) {
      speakResponse(`Searching for a ${specialty} near you.`);
      setIsSpeaking(true); setMode('idle');
      setTimeout(() => {
        router.push({ pathname: '/doctor-results', params: { specialty, zipCode: zipCode || '33434', planName: planName || '' } });
      }, 800);
      return;
    }

    setMode('thinking');
    let response;

    const benefitConfig = detectBenefitQuestion(q);
    if (benefitConfig && planNumber) response = await lookupBenefit(planNumber, benefitConfig);

    if (!response && isDrugQuestion(q)) {
      const drugName = extractDrugName(q);
      if (drugName && planNumber) response = await lookupDrug(planNumber, drugName);
    }

    if (!response) response = await askBackend(q, planNumber);

    setMode('answer'); setAnswer(response);
    speakResponse(response); setIsSpeaking(true);
  };

  const toggleSpeech = async () => {
    const speaking = await Speech.isSpeakingAsync();
    if (speaking) { Speech.stop(); setIsSpeaking(false); }
    else if (answer) { speakResponse(answer); setIsSpeaking(true); }
  };

  const startListening = async () => {
    Speech.stop(); setIsSpeaking(false);
    const { granted } = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
    if (!granted) return;
    setMode('listening'); setLiveText('');
    Keyboard.dismiss();
    ExpoSpeechRecognitionModule.start({ lang: 'en-US', interimResults: true, continuous: true });
  };

  const stopListening = () => ExpoSpeechRecognitionModule.stop();

  const handleMic = () => {
    if (mode === 'listening') stopListening();
    else startListening();
  };

  const handleSend = () => {
    const q = typedText.trim();
    if (q.length > 0) processQuestion(q);
  };

  return (
    <KeyboardAvoidingView
      style={s.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
    >
      {/* Header */}
      <View style={s.header}>
        <View style={s.headerLeft}>
          <View style={s.headerIcon}>
            <Ionicons name="chatbubble-ellipses" size={16} color={COLORS.accent} />
          </View>
          <Text style={s.headerTitle}>Ask anything</Text>
        </View>
        <TouchableOpacity style={s.callBtn} onPress={() => Linking.openURL('tel:' + CALL_NUMBER)} activeOpacity={0.7}>
          <Ionicons name="call" size={14} color="#fff" />
          <Text style={s.callText}>Call Us</Text>
        </TouchableOpacity>
      </View>

      {/* Answer / Status Area */}
      <ScrollView style={s.answerScroll} contentContainerStyle={s.answerArea}>
        {mode === 'idle' && (
          <View style={s.idleWrap}>
            <View style={s.idleIconCircle}>
              <Ionicons name="mic-outline" size={32} color={COLORS.accent} />
            </View>
            <Text style={s.idleTitle}>How can I help?</Text>
            <Text style={s.idleText}>Ask about your benefits, find a{'\n'}doctor, or check drug costs.</Text>
            {/* Suggestion chips */}
            <View style={s.chipRow}>
              <TouchableOpacity style={s.chip} onPress={() => processQuestion('What is my PCP copay?')} activeOpacity={0.7}>
                <Ionicons name="medical-outline" size={13} color={COLORS.accent} />
                <Text style={s.chipText}>My copays</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.chip} onPress={() => processQuestion('Find me a cardiologist')} activeOpacity={0.7}>
                <Ionicons name="search-outline" size={13} color={COLORS.accent} />
                <Text style={s.chipText}>Find a doctor</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.chip} onPress={() => processQuestion('What is my dental benefit?')} activeOpacity={0.7}>
                <Ionicons name="sparkles-outline" size={13} color={COLORS.accent} />
                <Text style={s.chipText}>Dental</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
        {mode === 'answer' && (
          <Animated.View style={{ opacity: fade }}>
            <View style={s.questionBubble}>
              <Ionicons name="chatbubble-outline" size={14} color={COLORS.textSecondary} />
              <Text style={s.qText}>{question}</Text>
            </View>
            <View style={s.answerCard}>
              <View style={s.answerAccent} />
              <Text style={s.aText}>{answer}</Text>
            </View>
            <View style={s.answerActions}>
              <TouchableOpacity style={s.speakerBtn} onPress={toggleSpeech} activeOpacity={0.7}>
                <Ionicons
                  name={isSpeaking ? 'volume-mute-outline' : 'volume-high-outline'}
                  size={16}
                  color={COLORS.accent}
                />
                <Text style={s.speakerText}>{isSpeaking ? 'Stop' : 'Listen'}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.newQuestionBtn} onPress={() => { Speech.stop(); setIsSpeaking(false); setMode('idle'); setAnswer(''); setQuestion(''); }} activeOpacity={0.7}>
                <Ionicons name="refresh-outline" size={16} color={COLORS.textSecondary} />
                <Text style={s.newQuestionText}>New question</Text>
              </TouchableOpacity>
            </View>
          </Animated.View>
        )}
        {mode === 'thinking' && (
          <Animated.View style={{ opacity: fade, alignItems: 'center' }}>
            <View style={s.questionBubble}>
              <Ionicons name="chatbubble-outline" size={14} color={COLORS.textSecondary} />
              <Text style={s.qText}>{question}</Text>
            </View>
            <View style={s.thinkingWrap}>
              <ActivityIndicator size="small" color={COLORS.accent} />
              <Text style={s.thinkingText}>Looking that up...</Text>
            </View>
          </Animated.View>
        )}
        {mode === 'listening' && (
          <Animated.View style={{ opacity: fade, alignItems: 'center' }}>
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
              width: 160, height: 160, borderRadius: 80,
              backgroundColor: COLORS.micRing3,
              transform: [{ scale: pulse }], opacity: pulseOp,
            }]} />
            <Animated.View style={[s.ring, {
              width: 130, height: 130, borderRadius: 65,
              backgroundColor: COLORS.micRing2,
              transform: [{ scale: pulse }], opacity: pulseOp,
            }]} />
            <Animated.View style={[s.ring, {
              width: 108, height: 108, borderRadius: 54,
              backgroundColor: COLORS.micRing1,
              transform: [{ scale: pulse }], opacity: pulseOp,
            }]} />
            <TouchableOpacity
              style={[s.mic, mode === 'listening' && s.micActive]}
              onPress={handleMic}
              activeOpacity={0.7}
            >
              <Ionicons name={mode === 'listening' ? 'pause' : 'mic'} size={34} color="#fff" />
            </TouchableOpacity>
          </View>
          <Text style={s.status}>
            {mode === 'idle' ? 'Tap mic or type below' :
             mode === 'listening' ? 'Listening...' :
             mode === 'thinking' ? 'Thinking...' :
             'Tap mic to ask another'}
          </Text>
        </>
      )}

      {/* Chat Input Bar */}
      <View style={s.inputBar}>
        <TextInput
          style={s.textInput}
          placeholder="Type your question..."
          placeholderTextColor={COLORS.textTertiary}
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
          activeOpacity={0.7}
        >
          <Ionicons name="arrow-up" size={20} color="#fff" />
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  container: {
    flex: 1, backgroundColor: COLORS.white,
    borderTopLeftRadius: RADII.xxl, borderTopRightRadius: RADII.xxl,
    ...SHADOWS.container,
  },

  // Header
  header: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 20, paddingTop: 18, paddingBottom: 8, width: '100%',
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerIcon: {
    width: 30, height: 30, borderRadius: 10,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center', alignItems: 'center',
  },
  headerTitle: { ...TYPE.h3, color: COLORS.text },
  callBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: COLORS.accent, borderRadius: RADII.full,
    paddingHorizontal: 16, paddingVertical: 9,
    ...SHADOWS.button,
  },
  callText: { color: '#fff', fontSize: 14, fontWeight: '600' },

  // Content area
  answerScroll: { flex: 1, width: '100%' },
  answerArea: { justifyContent: 'center', paddingHorizontal: 24, flexGrow: 1 },

  // Idle state
  idleWrap: { alignItems: 'center' },
  idleIconCircle: {
    width: 64, height: 64, borderRadius: 20,
    backgroundColor: COLORS.accentLighter,
    justifyContent: 'center', alignItems: 'center',
    marginBottom: 16,
  },
  idleTitle: { ...TYPE.h2, color: COLORS.text, marginBottom: 8 },
  idleText: { fontSize: 16, color: COLORS.textSecondary, textAlign: 'center', lineHeight: 24, marginBottom: 20 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 8 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    backgroundColor: COLORS.accentLighter, borderRadius: RADII.full,
    paddingHorizontal: 14, paddingVertical: 8,
    borderWidth: 1, borderColor: COLORS.accentLight,
  },
  chipText: { fontSize: 13, fontWeight: '600', color: COLORS.accent },

  // Question bubble
  questionBubble: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 8,
    alignSelf: 'center',
    backgroundColor: COLORS.bg,
    borderRadius: RADII.md,
    paddingHorizontal: 14, paddingVertical: 10,
    marginBottom: 14, maxWidth: '95%',
  },
  qText: { fontSize: 14, color: COLORS.textSecondary, fontStyle: 'italic', flex: 1 },

  // Answer card
  answerCard: {
    backgroundColor: COLORS.accentLighter,
    borderRadius: RADII.lg,
    padding: 18,
    paddingLeft: 22,
    marginBottom: 4,
    overflow: 'hidden',
  },
  answerAccent: {
    position: 'absolute', left: 0, top: 8, bottom: 8,
    width: 4, borderRadius: 2,
    backgroundColor: COLORS.accent,
  },
  aText: { fontSize: 16, color: COLORS.text, lineHeight: 25, fontWeight: '500' },
  answerActions: {
    flexDirection: 'row', justifyContent: 'center', gap: 12,
    marginTop: 14,
  },

  // Thinking state
  thinkingWrap: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: COLORS.accentLighter,
    borderRadius: RADII.md,
    paddingHorizontal: 20, paddingVertical: 14,
  },
  thinkingText: { fontSize: 15, color: COLORS.accent, fontWeight: '600' },

  // Listening
  listenText: { fontSize: 20, color: COLORS.accent, fontWeight: '600', textAlign: 'center', lineHeight: 30 },

  // Speaker button
  speakerBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 16, paddingVertical: 8,
    backgroundColor: COLORS.white, borderRadius: RADII.full,
    borderWidth: 1.5, borderColor: COLORS.accentLight,
  },
  speakerText: { fontSize: 13, fontWeight: '600', color: COLORS.accent },
  newQuestionBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 16, paddingVertical: 8,
    backgroundColor: COLORS.bg, borderRadius: RADII.full,
    borderWidth: 1, borderColor: COLORS.borderLight,
  },
  newQuestionText: { fontSize: 13, fontWeight: '600', color: COLORS.textSecondary },

  // Mic button
  micWrap: { width: 100, height: 100, justifyContent: 'center', alignItems: 'center', alignSelf: 'center' },
  ring: { position: 'absolute' },
  mic: {
    width: 82, height: 82, borderRadius: 41, backgroundColor: COLORS.accent,
    justifyContent: 'center', alignItems: 'center',
    ...SHADOWS.glow,
  },
  micActive: { backgroundColor: COLORS.accentDark, transform: [{ scale: 1.06 }] },
  status: { ...TYPE.caption, color: COLORS.textTertiary, marginTop: 12, marginBottom: 4, textAlign: 'center' },

  // Input bar
  inputBar: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 14, paddingVertical: 12,
    borderTopWidth: 1, borderTopColor: COLORS.borderLight,
    backgroundColor: COLORS.white,
  },
  textInput: {
    flex: 1, backgroundColor: COLORS.bg, borderRadius: RADII.full,
    paddingHorizontal: 18, paddingVertical: 12,
    fontSize: 15, color: COLORS.text,
    borderWidth: 1, borderColor: COLORS.borderLight,
    maxHeight: 80,
  },
  sendBtn: {
    width: 38, height: 38, borderRadius: 19,
    backgroundColor: COLORS.accent, justifyContent: 'center', alignItems: 'center',
    marginLeft: 10,
    ...SHADOWS.button,
  },
  sendBtnDisabled: { backgroundColor: COLORS.border, shadowOpacity: 0 },
});
