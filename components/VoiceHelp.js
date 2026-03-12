import { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Animated,
  Linking,
  Platform,
  ScrollView,
  TextInput,
  KeyboardAvoidingView,
  Keyboard,
  ActivityIndicator,
  Vibration,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ExpoSpeechRecognitionModule, useSpeechRecognitionEvent } from 'expo-speech-recognition';
import * as Speech from 'expo-speech';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { COLORS, RADII, SHADOWS, MOTION } from '../constants/theme';
import { CALL_NUMBER } from '../constants/data';
import { API_URL, authFetch } from '../constants/api';

const ONBOARDING_KEY = 'iny_voice_onboarding_seen';

// --- Pharmacy search detection ---

const PHARMACY_TRIGGERS = [
  'find a pharmacy',
  'find me a pharmacy',
  'pharmacy near',
  'pharmacies near',
  'where is a pharmacy',
  'nearest pharmacy',
  'in-network pharmacy',
  'preferred pharmacy',
  'find pharmacy',
  'pharmacy finder',
  'drug store',
  'drugstore',
  'find a drugstore',
  'where can i fill',
  'where do i fill',
  'fill my prescription',
];

function detectPharmacySearch(text) {
  const lower = text.toLowerCase();
  return PHARMACY_TRIGGERS.some((t) => lower.includes(t));
}

// --- Appointment request detection ---

const APPOINTMENT_TRIGGERS = [
  'make an appointment',
  'schedule an appointment',
  'book an appointment',
  'set up an appointment',
  'set an appointment',
  'need an appointment',
  'want an appointment',
  'schedule a visit',
  'book a visit',
  'make a visit',
  'see my doctor',
  'see dr',
  'visit dr',
  'appointment with dr',
  'appointment with doctor',
  'schedule with dr',
  'schedule with doctor',
  'book with dr',
  'book with doctor',
];

function detectAppointmentRequest(text) {
  const lower = text.toLowerCase();
  return APPOINTMENT_TRIGGERS.some((t) => lower.includes(t));
}

function extractDoctorName(text) {
  const lower = text.toLowerCase();
  // Match "Dr. Smith", "Dr Smith", "Doctor Smith", "doctor johnson"
  const drMatch = text.match(/\b(?:dr\.?\s+|doctor\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/i);
  if (drMatch) return 'Dr. ' + drMatch[1];
  // Check for "my doctor" / "my pcp" — no specific name
  if (lower.includes('my doctor') || lower.includes('my pcp') || lower.includes('my physician'))
    return 'Primary Care Doctor';
  return null;
}

function extractAppointmentReason(text) {
  const lower = text.toLowerCase();
  const reasons = [
    'check up',
    'checkup',
    'follow up',
    'follow-up',
    'annual visit',
    'physical',
    'sick',
    'pain',
    'refill',
    'prescription',
    'lab work',
    'blood work',
    'test results',
    'screening',
  ];
  for (const r of reasons) {
    if (lower.includes(r)) return r;
  }
  return '';
}

// --- Doctor search keywords and specialty extraction ---

const DOCTOR_TRIGGERS = [
  'find me a',
  'find a',
  'look for a',
  'search for a',
  'i need a',
  'find me an',
  'find an',
  'look for an',
  'search for an',
  'i need an',
  'where is a',
  'where can i find',
  'doctor near',
  'doctors near',
  'any',
  'are there any',
];

const SPECIALTY_KEYWORDS = {
  dermatologist: 'dermatologist',
  dermatology: 'dermatologist',
  'skin doctor': 'dermatologist',
  cardiologist: 'cardiologist',
  cardiology: 'cardiologist',
  'heart doctor': 'cardiologist',
  'primary care': 'primary care',
  pcp: 'primary care',
  'general doctor': 'primary care',
  'family doctor': 'family medicine',
  'family medicine': 'family medicine',
  'eye doctor': 'ophthalmologist',
  ophthalmologist: 'ophthalmologist',
  ophthalmology: 'ophthalmologist',
  'foot doctor': 'podiatrist',
  podiatrist: 'podiatrist',
  podiatry: 'podiatrist',
  ent: 'ent',
  'ear nose throat': 'ent',
  'ear nose and throat': 'ent',
  orthopedic: 'orthopedic',
  orthopedist: 'orthopedic',
  'bone doctor': 'orthopedic',
  neurologist: 'neurologist',
  neurology: 'neurologist',
  'brain doctor': 'neurologist',
  urologist: 'urologist',
  urology: 'urologist',
  psychiatrist: 'psychiatrist',
  psychiatry: 'psychiatrist',
  'mental health': 'psychiatrist',
  pulmonologist: 'pulmonologist',
  'lung doctor': 'pulmonologist',
  pulmonology: 'pulmonologist',
  gastroenterologist: 'gastroenterologist',
  'stomach doctor': 'gastroenterologist',
  'gi doctor': 'gastroenterologist',
  endocrinologist: 'endocrinologist',
  endocrinology: 'endocrinologist',
  'diabetes doctor': 'endocrinologist',
  rheumatologist: 'rheumatologist',
  rheumatology: 'rheumatologist',
  oncologist: 'oncologist',
  oncology: 'oncologist',
  'cancer doctor': 'oncologist',
  surgeon: 'surgeon',
  surgery: 'surgeon',
  'pain doctor': 'pain management',
  'pain management': 'pain management',
  'physical therapist': 'physical therapist',
  'physical therapy': 'physical therapist',
  pt: 'physical therapist',
  dentist: 'dentist',
  dental: 'dentist',
  optometrist: 'optometrist',
  nephrologist: 'nephrologist',
  'kidney doctor': 'nephrologist',
  obgyn: 'obgyn',
  'ob gyn': 'obgyn',
  gynecologist: 'obgyn',
  pediatrician: 'pediatrician',
  pediatrics: 'pediatrician',
  doctor: 'primary care',
  doctors: 'primary care',
};

function detectDoctorSearch(text) {
  const lower = text.toLowerCase();
  const hasTrigger =
    DOCTOR_TRIGGERS.some((t) => lower.includes(t)) ||
    lower.includes('doctor') ||
    lower.includes('specialist') ||
    lower.includes('near me') ||
    lower.includes('nearby');
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
  'cost',
  'copay',
  'cover',
  'tier',
  'drug',
  'medication',
  'medicine',
  'prescription',
  'rx',
  'generic',
  'brand',
  'how much',
  'formulary',
  'pay for',
];

function isDrugQuestion(text) {
  const lower = text.toLowerCase();
  if (detectDoctorSearch(text)) return false;
  return DRUG_KEYWORDS.some((kw) => lower.includes(kw));
}

function extractDrugName(question) {
  for (const pattern of DRUG_PATTERNS) {
    const match = question.match(pattern);
    if (match && match[1]) {
      let name = match[1]
        .trim()
        .replace(/\?$/, '')
        .replace(/^(my|the|a|an)\b\s*/i, '')
        .replace(/ ?(pill|tablet|capsule|medication|medicine|drug|prescription|cost|copay)s?$/i, '')
        .replace(/ ?(on my plan|on the formulary|in my plan|for me)$/i, '')
        .trim();
      // Skip common filler / non-drug words
      const skip = [
        'it',
        'that',
        'this',
        'me',
        'i',
        'much',
        'about',
        'for',
        'my',
        'your',
        'benefits',
        'plan',
        'insurance',
        'premium',
        'coverage',
        'deductible',
        'options',
        'something',
        'anything',
        'everything',
      ];
      if (name.length > 1 && name.length < 50 && !skip.includes(name.toLowerCase())) return name;
    }
  }
  return null;
}

function formatDrugResponse(data) {
  if (!data || !data.drug_name || data.tier == null) {
    return "I found some information but couldn't read it properly. Please call us at (844) 463-2931.";
  }
  const parts = [];
  parts.push(
    `${String(data.drug_name)} is on Tier ${data.tier}, ${data.tier_label || 'unknown tier'}.`,
  );
  if (data.copay_30day_preferred !== null && data.copay_30day_preferred !== undefined) {
    if (typeof data.copay_30day_preferred === 'number') {
      parts.push(
        `Your copay is $${data.copay_30day_preferred} for a 30-day supply at a preferred pharmacy.`,
      );
    } else {
      parts.push(
        `Your cost is ${String(data.copay_30day_preferred)} for a 30-day supply at a preferred pharmacy.`,
      );
    }
  }
  if (data.deductible_applies) parts.push('Your deductible applies to this drug.');
  const restrictions = [];
  if (data.prior_auth) restrictions.push('prior authorization');
  if (data.step_therapy) restrictions.push('step therapy');
  if (data.quantity_limit) {
    restrictions.push(
      `quantity limit of ${data.quantity_limit_amount || '?'} per ${data.quantity_limit_days || '?'} days`,
    );
  }
  if (restrictions.length > 0) parts.push(`Restrictions: ${restrictions.join(', ')}.`);
  return parts.join(' ');
}

async function lookupDrug(planNumber, drugName) {
  try {
    const res = await authFetch(
      `${API_URL}/cms/drug/${encodeURIComponent(planNumber)}/${encodeURIComponent(drugName)}`,
    );
    if (!res.ok) return null;
    const data = await res.json();
    if (data.error) return null;
    return formatDrugResponse(data);
  } catch (err) {
    if (__DEV__) console.log('Drug lookup error:', err);
    return null;
  }
}

// --- Benefit detection and CMS lookup ---

const BENEFIT_PATTERNS = {
  vision: {
    keywords: [
      'vision',
      'eye exam',
      'eyeglasses',
      'glasses',
      'eyewear',
      'contacts',
      'contact lenses',
      'eye care',
      'optometrist visit',
    ],
    endpoint: 'vision',
    format: formatVisionResponse,
  },
  dental: {
    keywords: [
      'dental',
      'dentist',
      'teeth',
      'tooth',
      'cleaning',
      'crown',
      'root canal',
      'filling',
      'denture',
      'oral',
    ],
    endpoint: 'dental',
    format: formatDentalResponse,
  },
  hearing: {
    keywords: [
      'hearing',
      'hearing aid',
      'hearing aids',
      'hearing exam',
      'hearing test',
      'audiologist',
      'ear exam',
    ],
    endpoint: 'hearing',
    format: formatHearingResponse,
  },
  otc: {
    keywords: ['otc', 'over the counter', 'over-the-counter', 'otc allowance', 'otc benefit'],
    endpoint: 'otc',
    format: formatOTCResponse,
  },
  flex: {
    keywords: [
      'flex card',
      'flex benefit',
      'ssbci',
      'supplemental benefit',
      'food benefit',
      'grocery',
    ],
    endpoint: 'flex',
    format: formatFlexResponse,
  },
  giveback: {
    keywords: ['part b', 'part b giveback', 'premium reduction', 'giveback', 'part b premium'],
    endpoint: 'giveback',
    format: formatGivebackResponse,
  },
};

function detectBenefitQuestion(text) {
  const lower = text.toLowerCase();
  if (detectDoctorSearch(text)) return null;
  for (const [_category, config] of Object.entries(BENEFIT_PATTERNS)) {
    const sorted = [...config.keywords].sort((a, b) => b.length - a.length);
    for (const kw of sorted) {
      if (lower.includes(kw)) return config;
    }
  }
  return null;
}

function formatVisionResponse(data) {
  const parts = [];
  if (data.has_eye_exam) {
    const exam = data.eye_exam;
    parts.push(`Your eye exam copay is ${exam.copay || '$0'}.`);
    if (exam.exams_per_year) parts.push(`You get ${exam.exams_per_year} exam per year.`);
  }
  if (data.has_eyewear) {
    const ew = data.eyewear;
    const max = ew.max_benefit;
    if (max) {
      parts.push(
        `For eyewear, you have a ${max} per year allowance with a ${ew.copay || '$0'} copay.`,
      );
    } else {
      parts.push(`Eyewear copay is ${ew.copay || '$0'}.`);
    }
  }
  return parts.length > 0
    ? parts.join(' ')
    : "I don't see vision benefits on your plan. Call us at (844) 463-2931 and we'll look into it.";
}

function formatDentalResponse(data) {
  const parts = [];
  if (data.has_preventive) {
    const pv = data.preventive;
    const max = pv.max_benefit;
    if (max) {
      parts.push(
        `Preventive dental like cleanings and exams is ${pv.copay || '$0'} copay with a ${max} per year maximum.`,
      );
    } else {
      parts.push(`Preventive dental is ${pv.copay || '$0'} copay.`);
    }
  }
  if (data.has_comprehensive) {
    const cmp = data.comprehensive;
    if (cmp.max_benefit)
      parts.push(`Comprehensive dental has a ${cmp.max_benefit} per year maximum.`);
  }
  return parts.length > 0
    ? parts.join(' ')
    : "I don't see dental benefits on your plan. Call us at (844) 463-2931 and we'll look into it.";
}

function formatHearingResponse(data) {
  const parts = [];
  if (data.has_hearing_exam) {
    const exam = data.hearing_exam;
    parts.push(`Your hearing exam copay is ${exam.copay || '$0'}.`);
    if (exam.exams_per_year) parts.push(`You get ${exam.exams_per_year} exam per year.`);
  }
  if (data.has_hearing_aids) {
    const aids = data.hearing_aids;
    const details = [];
    if (aids.max_benefit) details.push(`up to ${aids.max_benefit}`);
    if (aids.copay && aids.copay !== '$0') details.push(`${aids.copay} copay`);
    if (aids.aids_allowed) details.push(`${aids.aids_allowed} hearing aids`);
    if (aids.period) details.push(aids.period);
    parts.push(
      details.length > 0
        ? `For hearing aids, your plan covers ${details.join(', ')}.`
        : 'Hearing aids are covered.',
    );
  }
  return parts.length > 0
    ? parts.join(' ')
    : "I don't see hearing benefits on your plan. Call us at (844) 463-2931 and we'll look into it.";
}

function formatOTCResponse(data) {
  if (!data.has_otc)
    return "I don't see an OTC benefit on your plan. Call us at (844) 463-2931 and we'll look into it.";
  return `Your plan includes ${data.amount || ''} ${data.period || ''} for over-the-counter items.`.trim();
}

function formatFlexResponse(data) {
  if (!data.has_ssbci || !data.benefits || data.benefits.length === 0)
    return "I don't see a flex card benefit on your plan. Call us at (844) 463-2931 and we'll look into it.";
  const cats = data.benefits.map((b) =>
    b.amount && b.amount !== 'Included' ? `${b.category} (${b.amount})` : b.category,
  );
  return `Your plan has a flex card that covers: ${cats.join(', ')}.`;
}

function formatGivebackResponse(data) {
  if (!data.has_giveback) return 'Your plan does not include a Part B premium giveback.';
  return `Your plan gives back ${data.monthly_amount} per month on your Part B premium.`;
}

async function lookupBenefit(planNumber, config) {
  try {
    const res = await authFetch(
      `${API_URL}/cms/benefits/${encodeURIComponent(planNumber)}/${config.endpoint}`,
    );
    if (!res.ok) return null;
    return config.format(await res.json());
  } catch (err) {
    if (__DEV__) console.log('Benefit lookup error:', err);
    return null;
  }
}

// --- Reminder intent detection ---

const REMINDER_TRIGGERS = [
  'remind me',
  'set a reminder',
  'set reminder',
  'medication reminder',
  'pill reminder',
  'take my',
  'remind me to take',
  'set up reminder',
  'add a reminder',
  'add reminder',
  'reminder for',
];

const TIME_WORD_MAP = {
  morning: { hour: 8, minute: 0 },
  afternoon: { hour: 13, minute: 0 },
  evening: { hour: 18, minute: 0 },
  night: { hour: 21, minute: 0 },
  noon: { hour: 12, minute: 0 },
  bedtime: { hour: 21, minute: 0 },
};

function detectReminderIntent(text) {
  const lower = text.toLowerCase();
  const hasTrigger = REMINDER_TRIGGERS.some((t) => lower.includes(t));
  if (!hasTrigger) return null;

  // Extract time: "at 8am", "at 8:30 PM", "in the morning"
  let timeHour = null;
  let timeMinute = 0;

  // Pattern: "at 8:30 am"
  const timeMatch = lower.match(/at\s+(\d{1,2}):(\d{2})\s*(am|pm|a\.m\.|p\.m\.)?/i);
  if (timeMatch) {
    let h = parseInt(timeMatch[1], 10);
    timeMinute = parseInt(timeMatch[2], 10);
    const meridiem = (timeMatch[3] || '').replace(/\./g, '').toLowerCase();
    if (meridiem === 'pm' && h < 12) h += 12;
    if (meridiem === 'am' && h === 12) h = 0;
    timeHour = h;
  }

  // Pattern: "at 8 am" or "at 8am"
  if (timeHour === null) {
    const simpleMatch = lower.match(/at\s+(\d{1,2})\s*(am|pm|a\.m\.|p\.m\.)/i);
    if (simpleMatch) {
      let h = parseInt(simpleMatch[1], 10);
      const meridiem = simpleMatch[2].replace(/\./g, '').toLowerCase();
      if (meridiem === 'pm' && h < 12) h += 12;
      if (meridiem === 'am' && h === 12) h = 0;
      timeHour = h;
    }
  }

  // Pattern: "in the morning", "at night", "at bedtime"
  if (timeHour === null) {
    for (const [word, time] of Object.entries(TIME_WORD_MAP)) {
      if (lower.includes(word)) {
        timeHour = time.hour;
        timeMinute = time.minute;
        break;
      }
    }
  }

  // Extract drug name — look for patterns like "take my X", "reminder for X"
  let drugName = null;
  const drugPatterns = [
    /(?:take|taking)\s+(?:my\s+)?(.+?)(?:\s+at\s+|\s+every\s+|\s+in the\s+|$)/i,
    /reminder\s+for\s+(?:my\s+)?(.+?)(?:\s+at\s+|\s+every\s+|\s+in the\s+|$)/i,
    /remind\s+me\s+(?:to take\s+)?(?:my\s+)?(.+?)(?:\s+at\s+|\s+every\s+|\s+in the\s+|$)/i,
  ];
  for (const pat of drugPatterns) {
    const m = text.match(pat);
    if (m && m[1]) {
      let name = m[1]
        .trim()
        .replace(/\s*(every day|daily|each day|tonight|tomorrow)\s*/i, '')
        .trim();
      if (name.length > 1 && name.length < 50) {
        drugName = name;
        break;
      }
    }
  }

  if (!drugName && !timeHour) return null; // Need at least one piece of info

  return { drug_name: drugName, time_hour: timeHour, time_minute: timeMinute };
}

// --- Usage intent detection ---

const USAGE_TRIGGERS = [
  'i spent',
  'i used',
  'i bought',
  'i purchased',
  'log',
  'spent',
  'used my otc',
  'used my flex',
  'used my dental',
  'went to the dentist',
  'dental visit',
  'otc purchase',
  'bought otc',
  'bought over the counter',
];

const USAGE_CATEGORY_MAP = {
  otc: ['otc', 'over the counter', 'cvs', 'walgreens', 'rite aid', 'pharmacy'],
  dental: ['dental', 'dentist', 'cleaning', 'crown', 'filling', 'root canal'],
  flex: ['flex', 'grocery', 'food', 'produce', 'meals', 'pest control'],
  vision: ['vision', 'eyeglasses', 'glasses', 'eye exam', 'contacts', 'optical'],
  hearing: ['hearing', 'hearing aid'],
};

function detectUsageIntent(text) {
  const lower = text.toLowerCase();
  const hasTrigger = USAGE_TRIGGERS.some((t) => lower.includes(t));
  if (!hasTrigger) return null;

  // Extract amount
  const amountMatch = lower.match(/\$?\s*(\d+(?:\.\d{1,2})?)/);
  const amount = amountMatch ? parseFloat(amountMatch[1]) : null;

  // Detect category
  let category = null;
  for (const [cat, keywords] of Object.entries(USAGE_CATEGORY_MAP)) {
    if (keywords.some((kw) => lower.includes(kw))) {
      category = cat;
      break;
    }
  }

  if (!amount && !category) return null;

  // Build description from the original text
  return { amount, category, description: text.trim() };
}

// --- General ask ---

async function askBackend(question, planId) {
  try {
    const res = await authFetch(
      `${API_URL}/ask`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, plan_number: planId }),
      },
      30000,
    );
    const data = await res.json();
    return data.answer;
  } catch (err) {
    if (__DEV__) console.log('API error:', err);
    if (err.name === 'AbortError')
      return "That's taking longer than usual. Please try again or call us at (844) 463-2931.";
    if (err.message === 'Network request failed')
      return 'No internet connection. Please check your WiFi and try again.';
    return "I'm having trouble connecting right now. Please try again or call us at (844) 463-2931.";
  }
}

function speakResponse(text) {
  Speech.stop();
  Speech.speak(text, { language: 'en-US', rate: 0.9, pitch: 1.0 });
}

// --- Voice handlers for reminders and usage ---

async function handleReminderVoice(intent, sessionId, onCreated) {
  const { drug_name, time_hour, time_minute } = intent;

  if (!drug_name) {
    return "I heard you want to set a reminder, but I didn't catch the medication name. Try saying something like: remind me to take my metformin at 8 AM.";
  }
  if (time_hour === null || time_hour === undefined) {
    return `I heard ${drug_name}, but what time should I remind you? Try saying: remind me to take my ${drug_name} at 8 AM.`;
  }

  try {
    const res = await authFetch(`${API_URL}/reminders/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        drug_name,
        time_hour,
        time_minute: time_minute || 0,
      }),
    });
    if (!res.ok) throw new Error('Failed to create reminder');

    // Refresh the reminders list in home screen
    if (onCreated) onCreated();

    const ampm = time_hour >= 12 ? 'PM' : 'AM';
    const displayHour = time_hour === 0 ? 12 : time_hour > 12 ? time_hour - 12 : time_hour;
    const displayMin = String(time_minute || 0).padStart(2, '0');
    return `Done! I'll remind you to take your ${drug_name} every day at ${displayHour}:${displayMin} ${ampm}.`;
  } catch (err) {
    if (__DEV__) console.log('Reminder voice error:', err);
    return 'I had trouble saving that reminder. Please try again.';
  }
}

async function handleUsageVoice(intent, sessionId, onLogged) {
  const { amount, category, description } = intent;

  if (!amount || amount <= 0) {
    return "I heard you want to log spending, but I didn't catch the amount. Try saying: I spent $45 on OTC at CVS.";
  }
  if (!category) {
    return `I heard $${amount}, but which benefit? Try saying: I spent $${amount} on OTC, or dental, or flex card.`;
  }

  const categoryLabels = {
    otc: 'OTC',
    dental: 'Dental',
    flex: 'Flex Card',
    vision: 'Vision',
    hearing: 'Hearing',
  };

  try {
    const res = await authFetch(`${API_URL}/usage/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        category,
        amount,
        description: description || '',
        benefit_period: category === 'otc' ? 'Monthly' : 'Yearly',
      }),
    });
    if (!res.ok) throw new Error('Failed to log usage');

    // Refresh the usage summary in home screen
    if (onLogged) onLogged();

    return `Got it! I logged $${amount.toFixed(0)} for ${categoryLabels[category] || category}. You can see your updated balance on the home screen.`;
  } catch (err) {
    if (__DEV__) console.log('Usage voice error:', err);
    return 'I had trouble logging that. Please try again.';
  }
}

export default function VoiceHelp({
  planNumber,
  planName,
  zipCode,
  sessionId,
  memberName,
  onReminderCreated,
  onUsageLogged,
}) {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [mode, setMode] = useState('idle');
  const [answer, setAnswer] = useState('');
  const [question, setQuestion] = useState('');
  const [liveText, setLiveText] = useState('');
  const [typedText, setTypedText] = useState('');
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const pulse = useRef(new Animated.Value(1)).current;
  const pulseOp = useRef(new Animated.Value(0)).current;
  const fade = useRef(new Animated.Value(0)).current;
  const onboardFade = useRef(new Animated.Value(0)).current;

  // Refs to avoid stale closures in speech recognition event handlers
  const modeRef = useRef(mode);
  const liveTextRef = useRef(liveText);
  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);
  useEffect(() => {
    liveTextRef.current = liveText;
  }, [liveText]);

  // --- Keyboard tracking ---
  useEffect(() => {
    const showSub = Keyboard.addListener('keyboardDidShow', () => setKeyboardVisible(true));
    const hideSub = Keyboard.addListener('keyboardDidHide', () => setKeyboardVisible(false));
    return () => {
      showSub.remove();
      hideSub.remove();
    };
  }, []);

  // --- First-launch onboarding tooltip ---
  useEffect(() => {
    AsyncStorage.getItem(ONBOARDING_KEY).then((val) => {
      if (!val) {
        setShowOnboarding(true);
        Animated.timing(onboardFade, { toValue: 1, duration: 600, delay: 800, useNativeDriver: true }).start();
      }
    });
  }, []);

  const dismissOnboarding = () => {
    Animated.timing(onboardFade, { toValue: 0, duration: 300, useNativeDriver: true }).start(() => {
      setShowOnboarding(false);
      AsyncStorage.setItem(ONBOARDING_KEY, '1').catch(() => {});
    });
  };

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
    if (modeRef.current === 'listening') {
      const text = liveTextRef.current.trim();
      if (text.length > 0) processQuestion(text);
      else {
        setMode('idle');
        setLiveText('');
      }
    }
  });

  useSpeechRecognitionEvent('error', (event) => {
    if (__DEV__) console.log('Speech error:', event.error, event.message);
    if (event.error === 'aborted') return;
    if (modeRef.current === 'listening') {
      setMode('idle');
      setLiveText('');
    }
  });

  // --- Pulse animation (3-ring ripple) ---
  useEffect(() => {
    if (mode === 'listening') {
      Animated.loop(
        Animated.parallel([
          Animated.sequence([
            Animated.timing(pulse, { toValue: 1.6, duration: 1400, useNativeDriver: true }),
            Animated.timing(pulse, { toValue: 1, duration: 0, useNativeDriver: true }),
          ]),
          Animated.sequence([
            Animated.timing(pulseOp, { toValue: 0, duration: 1400, useNativeDriver: true }),
            Animated.timing(pulseOp, { toValue: 0.6, duration: 0, useNativeDriver: true }),
          ]),
        ]),
      ).start();
    } else {
      pulse.stopAnimation();
      pulseOp.stopAnimation();
      pulse.setValue(1);
      pulseOp.setValue(0);
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
    Speech.stop();
    setIsSpeaking(false);
    setQuestion(q);
    setLiveText('');
    setTypedText('');
    Keyboard.dismiss();

    // Pharmacy search
    if (detectPharmacySearch(q)) {
      speakResponse('Searching for pharmacies near you.');
      setIsSpeaking(true);
      setMode('idle');
      setTimeout(() => {
        router.push({
          pathname: '/pharmacy-results',
          params: {
            zipCode: zipCode || '',
            planNumber: planNumber || '',
            planName: planName || '',
          },
        });
      }, 800);
      return;
    }

    // Appointment request (check before doctor search)
    if (detectAppointmentRequest(q)) {
      const drName = extractDoctorName(q) || 'Doctor';
      const reason = extractAppointmentReason(q);
      setMode('thinking');
      try {
        const res = await authFetch(`${API_URL}/appointment-request`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            doctor_name: drName,
            member_name: memberName || '',
            reason,
          }),
        });
        if (res.ok) {
          const msg = `I've submitted your appointment request with ${drName}. Our team will call you to confirm the details.`;
          setMode('answer');
          setAnswer(msg);
          speakResponse(msg);
          setIsSpeaking(true);
        } else {
          throw new Error('Request failed');
        }
      } catch {
        const msg =
          "I wasn't able to submit your appointment request right now. Please try again or call us for help.";
        setMode('answer');
        setAnswer(msg);
        speakResponse(msg);
        setIsSpeaking(true);
      }
      return;
    }

    // Doctor search
    const specialty = detectDoctorSearch(q);
    if (specialty) {
      speakResponse(`Searching for a ${specialty} near you.`);
      setIsSpeaking(true);
      setMode('idle');
      setTimeout(() => {
        router.push({ pathname: '/doctor-results', params: { specialty } });
      }, 800);
      return;
    }

    setMode('thinking');
    let response;

    // 1. Benefit questions (vision, dental, OTC, etc.)
    const benefitConfig = detectBenefitQuestion(q);
    if (benefitConfig && planNumber) response = await lookupBenefit(planNumber, benefitConfig);

    // 2. Medication reminder intent
    if (!response) {
      const reminderIntent = detectReminderIntent(q);
      if (reminderIntent && sessionId) {
        response = await handleReminderVoice(reminderIntent, sessionId, onReminderCreated);
      }
    }

    // 3. Usage logging intent
    if (!response) {
      const usageIntent = detectUsageIntent(q);
      if (usageIntent && sessionId) {
        response = await handleUsageVoice(usageIntent, sessionId, onUsageLogged);
      }
    }

    // 4. Drug cost question
    if (!response && isDrugQuestion(q)) {
      const drugName = extractDrugName(q);
      if (drugName && planNumber) response = await lookupDrug(planNumber, drugName);
    }

    // 5. Fallback — ask Claude
    if (!response) response = await askBackend(q, planNumber);

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
    ExpoSpeechRecognitionModule.start({ lang: 'en-US', interimResults: true, continuous: true });
  };

  const stopListening = () => ExpoSpeechRecognitionModule.stop();

  const handleMic = () => {
    Vibration.vibrate(50);
    if (showOnboarding) dismissOnboarding();
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
      {/* Purple gradient background */}
      <LinearGradient
        colors={['#9B6BD4', '#7B3FBF', '#6B2FAF']}
        locations={[0, 0.5, 1]}
        style={StyleSheet.absoluteFillObject}
      />

      {/* Answer / Status Area */}
      {mode !== 'idle' && (
        <ScrollView style={s.answerScroll} contentContainerStyle={s.answerArea}>
          {mode === 'answer' && (
            <Animated.View style={{ opacity: fade }}>
              <View style={s.questionBubble}>
                <Ionicons name="chatbubble-outline" size={14} color="rgba(255,255,255,0.6)" />
                <Text style={s.qText}>{question}</Text>
              </View>
              <View style={s.answerCard}>
                <View style={s.answerAccent} />
                <Text style={s.aText}>{answer}</Text>
              </View>
              <View style={s.answerActions}>
                <TouchableOpacity
                  style={s.speakerBtn}
                  onPress={toggleSpeech}
                  activeOpacity={0.7}
                  accessibilityRole="button"
                  accessibilityLabel={isSpeaking ? 'Stop speaking' : 'Read answer aloud'}
                >
                  <Ionicons
                    name={isSpeaking ? 'volume-mute-outline' : 'volume-high-outline'}
                    size={16}
                    color={COLORS.accent}
                  />
                  <Text style={s.speakerText}>{isSpeaking ? 'Stop' : 'Listen'}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={s.newQuestionBtn}
                  onPress={() => {
                    Speech.stop();
                    setIsSpeaking(false);
                    setMode('idle');
                    setAnswer('');
                    setQuestion('');
                  }}
                  activeOpacity={0.7}
                  accessibilityRole="button"
                  accessibilityLabel="Ask a new question"
                >
                  <Ionicons name="refresh-outline" size={16} color="rgba(255,255,255,0.7)" />
                  <Text style={s.newQuestionText}>New question</Text>
                </TouchableOpacity>
              </View>
            </Animated.View>
          )}
          {mode === 'thinking' && (
            <Animated.View style={{ opacity: fade, alignItems: 'center' }}>
              <View style={s.questionBubble}>
                <Ionicons name="chatbubble-outline" size={14} color="rgba(255,255,255,0.6)" />
                <Text style={s.qText}>{question}</Text>
              </View>
              <View style={s.thinkingWrap}>
                <ActivityIndicator size="small" color="#fff" />
                <Text style={s.thinkingText}>Looking that up...</Text>
              </View>
            </Animated.View>
          )}
          {mode === 'listening' && (
            <Animated.View style={{ opacity: fade, alignItems: 'center' }}>
              <Text style={s.listenText}>{liveText || "Go ahead, I'm listening..."}</Text>
            </Animated.View>
          )}
        </ScrollView>
      )}

      {/* Centered Mic Button — hide when keyboard is up */}
      {!keyboardVisible && (
        <View style={s.micSection}>
          <View style={s.micWrap}>
            <Animated.View
              style={[
                s.ring,
                {
                  width: 140,
                  height: 140,
                  borderRadius: 70,
                  backgroundColor: 'rgba(255,255,255,0.06)',
                  transform: [{ scale: pulse }],
                  opacity: pulseOp,
                },
              ]}
            />
            <Animated.View
              style={[
                s.ring,
                {
                  width: 115,
                  height: 115,
                  borderRadius: 57.5,
                  backgroundColor: 'rgba(255,255,255,0.10)',
                  transform: [{ scale: pulse }],
                  opacity: pulseOp,
                },
              ]}
            />
            <Animated.View
              style={[
                s.ring,
                {
                  width: 96,
                  height: 96,
                  borderRadius: 48,
                  backgroundColor: 'rgba(255,255,255,0.15)',
                  transform: [{ scale: pulse }],
                  opacity: pulseOp,
                },
              ]}
            />
            <TouchableOpacity
              style={[s.mic, mode === 'listening' && s.micActive]}
              onPress={handleMic}
              activeOpacity={0.7}
              accessibilityRole="button"
              accessibilityLabel={mode === 'listening' ? 'Stop listening' : 'Start voice input'}
            >
              <Ionicons
                name={mode === 'listening' ? 'pause' : 'mic'}
                size={34}
                color={COLORS.accent}
              />
            </TouchableOpacity>
          </View>
          <Text style={s.status}>
            {mode === 'idle'
              ? 'Just say what you need — I can look up benefits, find doctors, set medication reminders, and more'
              : mode === 'listening'
                ? 'Listening...'
                : mode === 'thinking'
                  ? 'Thinking...'
                  : 'Tap mic to ask another'}
          </Text>
        </View>
      )}

      {/* First-launch onboarding tooltip */}
      {showOnboarding && mode === 'idle' && (
        <Animated.View style={[s.onboardOverlay, { opacity: onboardFade }]}>
          <TouchableOpacity
            style={s.onboardCard}
            onPress={dismissOnboarding}
            activeOpacity={0.95}
            accessibilityRole="button"
            accessibilityLabel="Dismiss voice help tip"
          >
            <View style={s.onboardArrow} />
            <Ionicons name="mic" size={22} color={COLORS.accent} style={{ marginBottom: 6 }} />
            <Text style={s.onboardTitle}>Tap here to talk to me!</Text>
            <Text style={s.onboardBody}>Try saying:</Text>
            <Text style={s.onboardExample}>"What's my copay for a specialist?"</Text>
            <Text style={s.onboardExample}>"Find me a dentist nearby"</Text>
            <Text style={s.onboardExample}>"Remind me to take my medicine at 8 AM"</Text>
            <Text style={s.onboardDismiss}>Tap to dismiss</Text>
          </TouchableOpacity>
        </Animated.View>
      )}

      {/* Bottom bar: text input left, Need help? + Call Us right */}
      <View style={[s.inputBar, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        <TextInput
          style={s.textInput}
          placeholder="Type your question..."
          placeholderTextColor="rgba(255,255,255,0.4)"
          value={typedText}
          onChangeText={setTypedText}
          onSubmitEditing={handleSend}
          returnKeyType="send"
          editable={mode !== 'thinking' && mode !== 'listening'}
          accessibilityLabel="Type your question"
        />
        <View style={s.bottomRight}>
          <Text style={s.needHelpLabel}>NEED HELP?</Text>
          <TouchableOpacity
            style={s.callBtn}
            onPress={() => Linking.openURL('tel:' + CALL_NUMBER)}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel="Call us for help"
          >
            <Ionicons name="call" size={14} color={COLORS.accent} />
            <Text style={s.callText}>Call Us</Text>
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  container: {
    flex: 1,
    borderTopLeftRadius: RADII.xxl,
    borderTopRightRadius: RADII.xxl,
    overflow: 'hidden',
    ...SHADOWS.container,
  },

  // Content area
  answerScroll: { flex: 1, width: '100%', zIndex: 1 },
  answerArea: {
    justifyContent: 'flex-end',
    paddingHorizontal: 24,
    flexGrow: 1,
    paddingBottom: 8,
    paddingTop: 16,
  },

  // Idle state
  idleWrap: { alignItems: 'center', zIndex: 1 },
  idleTitle: { fontSize: 22, fontWeight: '700', color: '#fff', marginBottom: 4 },
  idleText: {
    fontSize: 15,
    color: 'rgba(255,255,255,0.75)',
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 12,
  },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 6 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: 'rgba(255,255,255,0.15)',
    borderRadius: RADII.full,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.2)',
  },
  chipText: { fontSize: 13, fontWeight: '600', color: '#fff' },

  // Question bubble (on purple bg)
  questionBubble: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    alignSelf: 'center',
    backgroundColor: 'rgba(255,255,255,0.12)',
    borderRadius: RADII.md,
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginBottom: 14,
    maxWidth: '95%',
  },
  qText: { fontSize: 14, color: 'rgba(255,255,255,0.85)', fontStyle: 'italic', flex: 1 },

  // Answer card (white card on purple bg)
  answerCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: RADII.lg,
    padding: 18,
    paddingLeft: 22,
    marginBottom: 4,
    overflow: 'hidden',
  },
  answerAccent: {
    position: 'absolute',
    left: 0,
    top: 8,
    bottom: 8,
    width: 4,
    borderRadius: 2,
    backgroundColor: COLORS.accent,
  },
  aText: { fontSize: 18, color: COLORS.text, lineHeight: 28, fontWeight: '500' },
  answerActions: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 12,
    marginTop: 14,
  },

  // Thinking state
  thinkingWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: 'rgba(255,255,255,0.15)',
    borderRadius: RADII.md,
    paddingHorizontal: 20,
    paddingVertical: 14,
  },
  thinkingText: { fontSize: 15, color: '#fff', fontWeight: '600' },

  // Listening
  listenText: {
    fontSize: 26,
    color: '#fff',
    fontWeight: '600',
    textAlign: 'center',
    lineHeight: 36,
  },

  // Speaker button
  speakerBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: COLORS.white,
    borderRadius: RADII.full,
    borderWidth: 1.5,
    borderColor: COLORS.accentLight,
  },
  speakerText: { fontSize: 13, fontWeight: '600', color: COLORS.accent },
  newQuestionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: 'rgba(255,255,255,0.15)',
    borderRadius: RADII.full,
  },
  newQuestionText: { fontSize: 13, fontWeight: '600', color: 'rgba(255,255,255,0.8)' },

  // Mic section (centered)
  micSection: { alignItems: 'center', zIndex: 1, paddingBottom: 4 },
  micWrap: { width: 130, height: 90, justifyContent: 'center', alignItems: 'center' },
  ring: { position: 'absolute' },
  mic: {
    width: 92,
    height: 68,
    borderRadius: 34,
    backgroundColor: '#FFFFFF',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 12,
    elevation: 6,
  },
  micActive: { backgroundColor: '#F0E8F8', transform: [{ scale: 1.08 }] },
  status: {
    fontSize: 15,
    fontWeight: '500',
    color: 'rgba(255,255,255,0.85)',
    marginTop: 8,
    marginBottom: 4,
    textAlign: 'center',
    lineHeight: 22,
    paddingHorizontal: 30,
  },

  // Bottom bar: text input left, Need help? + Call Us right
  inputBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 10,
    zIndex: 1,
  },
  textInput: {
    flex: 1,
    backgroundColor: 'rgba(255,255,255,0.15)',
    borderRadius: RADII.full,
    paddingHorizontal: 18,
    paddingVertical: 12,
    fontSize: 15,
    color: '#fff',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.2)',
    maxHeight: 80,
  },
  bottomRight: { alignItems: 'center', marginLeft: 14 },
  needHelpLabel: {
    fontSize: 15,
    fontWeight: '700',
    color: 'rgba(255,255,255,0.8)',
    marginBottom: 6,
  },
  callBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#FFFFFF',
    borderRadius: RADII.full,
    paddingHorizontal: 22,
    paddingVertical: 12,
  },
  callText: { color: COLORS.accent, fontSize: 17, fontWeight: '700' },

  // Onboarding tooltip
  onboardOverlay: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 140,
    alignItems: 'center',
    zIndex: 10,
  },
  onboardCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: RADII.lg,
    paddingHorizontal: 22,
    paddingVertical: 18,
    width: 280,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.25,
    shadowRadius: 16,
    elevation: 10,
  },
  onboardArrow: {
    position: 'absolute',
    bottom: -10,
    width: 0,
    height: 0,
    borderLeftWidth: 12,
    borderRightWidth: 12,
    borderTopWidth: 12,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    borderTopColor: '#FFFFFF',
  },
  onboardTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.text,
    textAlign: 'center',
    marginBottom: 8,
  },
  onboardBody: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.textSecondary,
    marginBottom: 6,
  },
  onboardExample: {
    fontSize: 14,
    fontWeight: '500',
    color: COLORS.accent,
    fontStyle: 'italic',
    textAlign: 'center',
    marginBottom: 3,
  },
  onboardDismiss: {
    fontSize: 12,
    fontWeight: '500',
    color: COLORS.textTertiary,
    marginTop: 10,
  },
});
