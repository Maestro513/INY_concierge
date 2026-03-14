import { useState } from 'react';
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

const SDOH_KEY = '@sdoh_screening_complete';

const QUESTIONS = [
  {
    id: 'transportation',
    icon: 'car-outline',
    question:
      'In the past 12 months, has lack of reliable transportation kept you from medical appointments or getting things needed for daily living?',
    type: 'yesno',
    flagLabel: 'Transportation',
    benefitHint: 'Your plan may cover free rides to doctor appointments.',
  },
  {
    id: 'food_insecurity',
    icon: 'nutrition-outline',
    question:
      'Within the past 12 months, have you worried that your food would run out before you got money to buy more?',
    type: 'yesno',
    flagLabel: 'Food Access',
    benefitHint: 'Your OTC/grocery allowance may help with food costs.',
  },
  {
    id: 'social_isolation',
    icon: 'people-outline',
    question: 'How often do you feel lonely or isolated from those around you?',
    type: 'scale',
    options: [
      { value: 'never', label: 'Never' },
      { value: 'rarely', label: 'Rarely' },
      { value: 'sometimes', label: 'Sometimes' },
      { value: 'often', label: 'Often' },
      { value: 'always', label: 'Always' },
    ],
    flagLabel: 'Social Connection',
    benefitHint: 'Your plan may include fitness and community programs like SilverSneakers.',
  },
  {
    id: 'housing_stability',
    icon: 'home-outline',
    question:
      'Are you worried about losing your housing, or is your current housing situation unsafe?',
    type: 'yesno',
    flagLabel: 'Housing',
    benefitHint: 'Your plan may offer case management and support services.',
  },
];

const PAGE_SIZE = 2;
const TOTAL_PAGES = Math.ceil(QUESTIONS.length / PAGE_SIZE);

export default function SDoHScreeningScreen() {
  const router = useRouter();
  const { sessionId } = getMemberSession();
  const [answers, setAnswers] = useState({});
  const [saving, setSaving] = useState(false);
  const [pageIdx, setPageIdx] = useState(0);

  const pageQuestions = QUESTIONS.slice(pageIdx * PAGE_SIZE, (pageIdx + 1) * PAGE_SIZE);
  const isLastPage = pageIdx === TOTAL_PAGES - 1;
  const allPageAnswered = pageQuestions.every((q) => answers[q.id] !== undefined);

  const setAnswer = (id, value) => {
    setAnswers((prev) => ({ ...prev, [id]: value }));
  };

  const handleNext = () => {
    if (isLastPage) {
      handleSubmit();
    } else {
      setPageIdx((prev) => prev + 1);
    }
  };

  const handleBack = () => {
    if (pageIdx > 0) {
      setPageIdx((prev) => prev - 1);
    }
  };

  const handleSubmit = async () => {
    setSaving(true);
    try {
      if (!sessionId) {
        Alert.alert('Session expired', 'Please log in again to save your responses.');
        setSaving(false);
        return;
      }
      try {
        await authFetch(`${API_URL}/sdoh-screening`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(answers),
        });
      } catch {
        if (__DEV__) console.log('SDoH screening save failed');
      }
      await AsyncStorage.setItem(SDOH_KEY, 'true');
      router.replace('/home');
    } catch {
      Alert.alert('Error', 'Could not save your responses. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = async () => {
    await AsyncStorage.setItem(SDOH_KEY, 'true');
    router.replace('/home');
  };

  // Progress
  const progress = (pageIdx + 1) / TOTAL_PAGES;

  return (
    <SafeAreaView style={s.safe}>
      {/* Header */}
      <View style={s.header}>
        {pageIdx > 0 ? (
          <TouchableOpacity onPress={handleBack} style={s.backBtn} activeOpacity={0.7}>
            <Ionicons name="chevron-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
        ) : (
          <View style={{ width: 40 }} />
        )}
        <Text style={s.headerTitle}>Well-Being Check</Text>
        <TouchableOpacity onPress={handleSkip} activeOpacity={0.7}>
          <Text style={s.skipText}>Skip</Text>
        </TouchableOpacity>
      </View>

      {/* Progress bar */}
      <View style={s.progressTrack}>
        <View style={[s.progressFill, { width: `${progress * 100}%` }]} />
      </View>

      <ScrollView
        style={s.scroll}
        contentContainerStyle={s.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {pageQuestions.map((q, idx) => {
          const globalIdx = pageIdx * PAGE_SIZE + idx;
          const isAnswered = answers[q.id] !== undefined;

          return (
            <View key={q.id} style={s.questionCard}>
              <View style={s.questionIconWrap}>
                <Ionicons name={q.icon} size={32} color={COLORS.accent} />
              </View>

              <Text style={s.stepLabel}>
                Question {globalIdx + 1} of {QUESTIONS.length}
              </Text>

              <Text style={s.questionText}>{q.question}</Text>

              {/* Answer options */}
              {q.type === 'yesno' ? (
                <View style={s.optionsRow}>
                  <TouchableOpacity
                    style={[s.optionBtn, answers[q.id] === 'yes' && s.optionBtnYes]}
                    onPress={() => setAnswer(q.id, 'yes')}
                    activeOpacity={0.7}
                  >
                    <Text
                      style={[s.optionText, answers[q.id] === 'yes' && s.optionTextActive]}
                    >
                      Yes
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[s.optionBtn, answers[q.id] === 'no' && s.optionBtnNo]}
                    onPress={() => setAnswer(q.id, 'no')}
                    activeOpacity={0.7}
                  >
                    <Text
                      style={[s.optionText, answers[q.id] === 'no' && s.optionTextNoActive]}
                    >
                      No
                    </Text>
                  </TouchableOpacity>
                </View>
              ) : (
                <View style={s.scaleColumn}>
                  {q.options.map((opt) => {
                    const selected = answers[q.id] === opt.value;
                    return (
                      <TouchableOpacity
                        key={opt.value}
                        style={[s.scaleBtn, selected && s.scaleBtnActive]}
                        onPress={() => setAnswer(q.id, opt.value)}
                        activeOpacity={0.7}
                      >
                        <Text style={[s.scaleText, selected && s.scaleTextActive]}>
                          {opt.label}
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              )}

              {/* Benefit hint */}
              {q.benefitHint && isAnswered && (
                <View style={s.hintBox}>
                  <Ionicons name="information-circle-outline" size={16} color={COLORS.accent} />
                  <Text style={s.hintText}>{q.benefitHint}</Text>
                </View>
              )}
            </View>
          );
        })}

        {/* Privacy note */}
        <View style={s.privacyBox}>
          <Ionicons name="lock-closed-outline" size={14} color={COLORS.textTertiary} />
          <Text style={s.privacyText}>
            Your answers are private and help us connect you with plan benefits you may not know
            about.
          </Text>
        </View>
      </ScrollView>

      {/* Footer */}
      <View style={s.footer}>
        <TouchableOpacity
          style={[s.nextBtn, (!allPageAnswered || saving) && s.nextBtnDisabled]}
          onPress={handleNext}
          activeOpacity={0.7}
          disabled={!allPageAnswered || saving}
        >
          {saving ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <>
              <Text style={s.nextText}>{isLastPage ? 'Finish' : 'Next'}</Text>
              {!isLastPage && <Ionicons name="arrow-forward" size={18} color="#fff" />}
            </>
          )}
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  backBtn: { width: 40, height: 40, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { ...TYPE.h2, fontSize: 20, color: COLORS.text },
  skipText: { fontSize: 15, fontWeight: '500', color: COLORS.textTertiary },

  // Progress
  progressTrack: {
    height: 4,
    backgroundColor: COLORS.borderLight,
    marginHorizontal: 20,
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: COLORS.accent,
    borderRadius: 2,
  },

  // Scroll
  scroll: { flex: 1 },
  scrollContent: { padding: 20, paddingBottom: 100 },

  // Question card
  questionCard: {
    backgroundColor: COLORS.white,
    borderRadius: RADII.lg,
    padding: 24,
    ...SHADOWS.card,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
    marginBottom: 16,
  },
  questionIconWrap: {
    width: 56,
    height: 56,
    borderRadius: 16,
    backgroundColor: COLORS.accentLight || '#F0E8F8',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
    alignSelf: 'center',
  },
  stepLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: COLORS.accent,
    textAlign: 'center',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  questionText: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.text,
    textAlign: 'center',
    lineHeight: 26,
    marginBottom: 24,
  },

  // Yes/No options
  optionsRow: {
    flexDirection: 'row',
    gap: 12,
  },
  optionBtn: {
    flex: 1,
    paddingVertical: 16,
    borderRadius: RADII.md,
    borderWidth: 2,
    borderColor: COLORS.border,
    backgroundColor: COLORS.bg,
    alignItems: 'center',
  },
  optionBtnYes: { backgroundColor: '#FFF3E0', borderColor: '#FF9800' },
  optionBtnNo: { backgroundColor: '#E8F5E9', borderColor: '#4CAF50' },
  optionText: { fontSize: 18, fontWeight: '700', color: COLORS.textSecondary },
  optionTextActive: { color: '#E65100' },
  optionTextNoActive: { color: '#2E7D32' },

  // Scale options
  scaleColumn: { gap: 8 },
  scaleBtn: {
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderRadius: RADII.md,
    borderWidth: 2,
    borderColor: COLORS.border,
    backgroundColor: COLORS.bg,
    alignItems: 'center',
  },
  scaleBtnActive: {
    backgroundColor: COLORS.accentLight || '#F0E8F8',
    borderColor: COLORS.accent,
  },
  scaleText: { fontSize: 16, fontWeight: '600', color: COLORS.textSecondary },
  scaleTextActive: { color: COLORS.accent },

  // Hint
  hintBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    marginTop: 16,
    backgroundColor: COLORS.accentLight || '#F0E8F8',
    borderRadius: RADII.sm,
    padding: 12,
  },
  hintText: {
    flex: 1,
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.accent,
    lineHeight: 18,
  },

  // Privacy
  privacyBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    paddingHorizontal: 4,
  },
  privacyText: {
    flex: 1,
    fontSize: 12,
    fontWeight: '400',
    color: COLORS.textTertiary,
    lineHeight: 17,
  },

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
  nextBtn: {
    backgroundColor: COLORS.accent,
    borderRadius: RADII.full,
    paddingVertical: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    ...SHADOWS.button,
  },
  nextBtnDisabled: { opacity: 0.4 },
  nextText: { color: '#fff', fontSize: 18, fontWeight: '700' },
});
