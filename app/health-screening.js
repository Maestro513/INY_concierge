import { useState, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { COLORS, RADII, SHADOWS, TYPE } from '../constants/theme';
import { getMemberSession } from '../constants/session';
import { API_URL, authFetch } from '../constants/api';

const SCREENING_KEY = '@health_screening_complete';

// Default screenings — overridden by backend if admin has configured them
const DEFAULT_SHARED = [
  { id: 'awv', label: 'Annual Wellness Visit', timeframe: 'in the past year', frequency: 'yearly' },
  { id: 'flu', label: 'Flu Shot', timeframe: 'this season', frequency: 'yearly' },
  {
    id: 'colonoscopy',
    label: 'Colonoscopy',
    timeframe: 'in the past 5 years',
    frequency: '5 years',
  },
  {
    id: 'cholesterol',
    label: 'Cholesterol / Blood Work',
    timeframe: 'in the past year',
    frequency: 'yearly',
  },
  {
    id: 'a1c',
    label: 'Diabetes Screening (A1C)',
    timeframe: 'in the past year',
    frequency: 'yearly',
  },
  {
    id: 'fall_risk',
    label: 'Fall Risk Assessment',
    timeframe: 'in the past year',
    frequency: 'yearly',
  },
];

const DEFAULT_MALE = [
  {
    id: 'prostate',
    label: 'Prostate (PSA) Screening',
    timeframe: 'in the past year',
    frequency: 'yearly',
  },
];

const DEFAULT_FEMALE = [
  { id: 'mammogram', label: 'Mammogram', timeframe: 'in the past 1-2 years', frequency: 'yearly' },
  {
    id: 'bone_density',
    label: 'Bone Density Scan (DEXA)',
    timeframe: 'in the past 2 years',
    frequency: '2 years',
  },
];

export default function HealthScreeningScreen() {
  const router = useRouter();
  const { sessionId } = getMemberSession();
  const [step, setStep] = useState('gender'); // 'gender' | 'screenings'
  const [gender, setGender] = useState(null);
  const [answers, setAnswers] = useState({});
  const [saving, setSaving] = useState(false);
  const [sharedScreenings, setSharedScreenings] = useState(DEFAULT_SHARED);
  const [maleScreenings, setMaleScreenings] = useState(DEFAULT_MALE);
  const [femaleScreenings, setFemaleScreenings] = useState(DEFAULT_FEMALE);
  const [loadingScreenings, setLoadingScreenings] = useState(true);

  // Fetch admin-configured screenings (fall back to defaults)
  useEffect(() => {
    (async () => {
      try {
        const res = await authFetch(`${API_URL}/health-screenings/config`);
        if (res.ok) {
          const data = await res.json();
          if (data.shared?.length) setSharedScreenings(data.shared);
          if (data.male?.length) setMaleScreenings(data.male);
          if (data.female?.length) setFemaleScreenings(data.female);
        }
      } catch {
        // Use defaults silently
      } finally {
        setLoadingScreenings(false);
      }
    })();
  }, []);

  const screenings =
    gender === 'male'
      ? [...sharedScreenings, ...maleScreenings]
      : [...sharedScreenings, ...femaleScreenings];

  const handleSubmit = async () => {
    setSaving(true);
    try {
      // Build reminders from "no" answers
      const reminders = screenings
        .filter((s) => !answers[s.id])
        .map((s) => ({
          screening_id: s.id,
          label: s.label,
          frequency: s.frequency,
        }));

      // Save to backend
      if (sessionId) {
        try {
          await authFetch(`${API_URL}/health-screenings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gender, answers, reminders }),
          });
        } catch {
          // Non-fatal — still mark as complete locally
          if (__DEV__) console.log('Health screening save to backend failed');
        }
      }

      // Mark as complete so we don't show again
      await AsyncStorage.setItem(SCREENING_KEY, 'true');
      router.replace('/home');
    } catch {
      Alert.alert('Error', 'Could not save your responses. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // ── Gender selection ──
  if (step === 'gender') {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.genderContainer}>
          <View style={s.iconWrap}>
            <Ionicons name="heart-circle" size={72} color={COLORS.accent} />
          </View>
          <Text style={s.genderTitle}>Preventive Health Check</Text>
          <Text style={s.genderSubtitle}>
            Let's make sure you're up to date on important screenings covered by your plan.
          </Text>

          <TouchableOpacity
            style={s.genderBtn}
            onPress={() => {
              setGender('male');
              setStep('screenings');
            }}
            activeOpacity={0.7}
          >
            <Ionicons name="man" size={32} color={COLORS.accent} />
            <Text style={s.genderBtnText}>Male</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={s.genderBtn}
            onPress={() => {
              setGender('female');
              setStep('screenings');
            }}
            activeOpacity={0.7}
          >
            <Ionicons name="woman" size={32} color={COLORS.accent} />
            <Text style={s.genderBtnText}>Female</Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => router.replace('/home')}
            style={s.skipBtn}
            activeOpacity={0.7}
          >
            <Text style={s.skipText}>Skip for now</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // ── Screenings checklist ──
  const _answeredCount = Object.keys(answers).length;

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => setStep('gender')} style={s.backBtn} activeOpacity={0.7}>
          <Ionicons name="chevron-back" size={24} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.headerTitle}>Health Screenings</Text>
        <View style={{ width: 40 }} />
      </View>

      <Text style={s.instructions}>
        Have you had any of the following?{'\n'}
        <Text style={s.instructionsSub}>Select Yes or No for each screening.</Text>
      </Text>

      <ScrollView
        style={s.list}
        contentContainerStyle={s.listContent}
        showsVerticalScrollIndicator={false}
      >
        {screenings.map((item) => {
          const answered = answers[item.id];
          const isYes = answered === true;
          const isNo = answered === false;
          // undefined means not answered yet — treat visually as unanswered
          const _notAnswered = answered === undefined;

          return (
            <View key={item.id} style={s.screeningCard}>
              <View style={s.screeningInfo}>
                <Text style={s.screeningLabel}>{item.label}</Text>
                <Text style={s.screeningTime}>{item.timeframe}</Text>
              </View>
              <View style={s.btnRow}>
                <TouchableOpacity
                  style={[s.yesNoBtn, isYes && s.yesActive]}
                  onPress={() => setAnswers((prev) => ({ ...prev, [item.id]: true }))}
                  activeOpacity={0.7}
                >
                  <Text style={[s.yesNoText, isYes && s.yesNoTextActive]}>Yes</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.yesNoBtn, isNo && s.noActive]}
                  onPress={() => setAnswers((prev) => ({ ...prev, [item.id]: false }))}
                  activeOpacity={0.7}
                >
                  <Text style={[s.yesNoText, isNo && s.noTextActive]}>No</Text>
                </TouchableOpacity>
              </View>
            </View>
          );
        })}
        <View style={{ height: 100 }} />
      </ScrollView>

      <View style={s.footer}>
        <TouchableOpacity
          style={[s.submitBtn, saving && s.submitBtnDisabled]}
          onPress={handleSubmit}
          activeOpacity={0.7}
          disabled={saving}
        >
          <Text style={s.submitText}>{saving ? 'Saving...' : 'Continue'}</Text>
          {!saving && <Ionicons name="arrow-forward" size={18} color="#fff" />}
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },

  // Gender step
  genderContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 32,
  },
  iconWrap: { marginBottom: 20 },
  genderTitle: {
    ...TYPE.h1,
    fontSize: 28,
    color: COLORS.text,
    textAlign: 'center',
    marginBottom: 10,
  },
  genderSubtitle: {
    fontSize: 18,
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: 26,
    marginBottom: 36,
  },
  genderBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    width: '100%',
    backgroundColor: COLORS.white,
    borderRadius: RADII.md,
    paddingVertical: 22,
    paddingHorizontal: 28,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
    ...SHADOWS.card,
  },
  genderBtnText: { fontSize: 22, fontWeight: '600', color: COLORS.text },
  skipBtn: { marginTop: 24 },
  skipText: { fontSize: 17, color: COLORS.textTertiary, fontWeight: '500' },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  backBtn: { width: 40, height: 40, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { ...TYPE.h2, color: COLORS.text },

  // Instructions
  instructions: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.text,
    paddingHorizontal: 20,
    marginBottom: 16,
    lineHeight: 24,
  },
  instructionsSub: { fontSize: 14, fontWeight: '400', color: COLORS.textSecondary },

  // List
  list: { flex: 1 },
  listContent: { paddingHorizontal: 16 },

  // Screening card
  screeningCard: {
    backgroundColor: COLORS.white,
    borderRadius: RADII.md,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  screeningInfo: { flex: 1, marginRight: 12 },
  screeningLabel: { fontSize: 15, fontWeight: '600', color: COLORS.text, marginBottom: 2 },
  screeningTime: { fontSize: 13, color: COLORS.textTertiary },

  // Yes/No buttons
  btnRow: { flexDirection: 'row', gap: 8 },
  yesNoBtn: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: RADII.full,
    borderWidth: 1.5,
    borderColor: COLORS.border,
    backgroundColor: COLORS.bg,
  },
  yesNoText: { fontSize: 14, fontWeight: '600', color: COLORS.textSecondary },
  yesActive: { backgroundColor: '#E8F5E9', borderColor: '#4CAF50' },
  yesNoTextActive: { color: '#2E7D32' },
  noActive: { backgroundColor: '#FFF3E0', borderColor: '#FF9800' },
  noTextActive: { color: '#E65100' },

  // Footer
  footer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    paddingHorizontal: 20,
    paddingVertical: 16,
    paddingBottom: 32,
    backgroundColor: COLORS.bg,
    borderTopWidth: 1,
    borderTopColor: COLORS.borderLight,
  },
  submitBtn: {
    backgroundColor: COLORS.accent,
    borderRadius: RADII.full,
    paddingVertical: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    ...SHADOWS.button,
  },
  submitBtnDisabled: { opacity: 0.6 },
  submitText: { color: '#fff', fontSize: 16, fontWeight: '700' },
});
