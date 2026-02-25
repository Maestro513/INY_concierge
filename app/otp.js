import { useState, useRef, useEffect } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, Animated } from 'react-native';
import GradientBg from '../components/GradientBg';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SPACING, SHADOWS, TYPE, MOTION } from '../constants/theme';

export default function OTPScreen() {
  const { phone } = useLocalSearchParams();
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const refs = useRef([]);
  const router = useRouter();

  // Entrance animation
  const contentOpacity = useRef(new Animated.Value(0)).current;
  const contentSlide = useRef(new Animated.Value(20)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(contentOpacity, { toValue: 1, duration: MOTION.slow, useNativeDriver: true }),
      Animated.timing(contentSlide, { toValue: 0, duration: MOTION.slow, useNativeDriver: true }),
    ]).start();
  }, []);

  const handleChange = (i, v) => {
    if (!/^\d?$/.test(v)) return;
    const n = [...otp]; n[i] = v; setOtp(n);
    if (v && i < 5) refs.current[i + 1]?.focus();
  };
  const handleKey = (i, k) => { if (k === 'Backspace' && !otp[i] && i > 0) refs.current[i - 1]?.focus(); };
  const filled = otp.every((d) => d !== '');

  return (
    <GradientBg style={s.gradient}>
      <SafeAreaView style={s.container}>
        <KeyboardAvoidingView style={s.inner} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
          <Animated.View style={[s.content, { opacity: contentOpacity, transform: [{ translateY: contentSlide }] }]}>
            <TouchableOpacity onPress={() => router.back()} style={s.backBtn} activeOpacity={0.7}>
              <View style={s.backIconWrap}>
                <Ionicons name="chevron-back" size={18} color={COLORS.accent} />
              </View>
              <Text style={s.back}>Back</Text>
            </TouchableOpacity>

            <View style={s.iconCircle}>
              <Ionicons name="chatbubble-ellipses-outline" size={32} color={COLORS.accent} />
            </View>
            <Text style={s.title}>Verify your number</Text>
            <Text style={s.subtitle}>
              We sent a 6-digit code to{'\n'}
              <Text style={{ fontWeight: '700', color: COLORS.text }}>{phone}</Text>
            </Text>

            {/* OTP Input Card */}
            <View style={s.otpCard}>
              <View style={s.otpRow}>
                {otp.map((d, i) => (
                  <TextInput
                    key={i}
                    ref={(el) => (refs.current[i] = el)}
                    style={[s.otpInput, d ? s.otpInputFilled : null]}
                    value={d}
                    onChangeText={(v) => handleChange(i, v)}
                    onKeyPress={({ nativeEvent }) => handleKey(i, nativeEvent.key)}
                    keyboardType="number-pad"
                    maxLength={1}
                    selectTextOnFocus
                  />
                ))}
              </View>
            </View>

            <TouchableOpacity
              style={[s.button, !filled && s.buttonDisabled]}
              onPress={() => filled && router.replace('/home')}
              disabled={!filled}
              activeOpacity={0.8}
            >
              <Text style={s.buttonText}>Verify</Text>
              <Ionicons name="checkmark" size={18} color={COLORS.white} style={{ marginLeft: 6 }} />
            </TouchableOpacity>

            <TouchableOpacity style={s.resendWrap} activeOpacity={0.7}>
              <Text style={s.resendText}>
                Didn't get it? <Text style={s.resendLink}>Resend code</Text>
              </Text>
            </TouchableOpacity>
          </Animated.View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </GradientBg>
  );
}

const s = StyleSheet.create({
  gradient: { flex: 1 },
  container: { flex: 1 },
  inner: { flex: 1, justifyContent: 'center' },
  content: { paddingHorizontal: SPACING.xl },

  // Back button
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: SPACING.xl },
  backIconWrap: {
    width: 32, height: 32, borderRadius: 10,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center', alignItems: 'center',
  },
  back: { ...TYPE.label, fontSize: 15, color: COLORS.accent },

  // Icon
  iconCircle: {
    width: 64, height: 64, borderRadius: 20,
    backgroundColor: COLORS.accentLighter,
    justifyContent: 'center', alignItems: 'center',
    marginBottom: SPACING.md,
  },

  // Typography
  title: { ...TYPE.h1, color: COLORS.text, marginBottom: SPACING.sm },
  subtitle: { ...TYPE.body, fontSize: 17, color: COLORS.textSecondary, lineHeight: 26, marginBottom: 28 },

  // OTP card
  otpCard: {
    backgroundColor: COLORS.white, borderRadius: RADII.lg,
    padding: 20, marginBottom: 24,
    ...SHADOWS.card,
  },
  otpRow: { flexDirection: 'row', justifyContent: 'center', gap: 10 },
  otpInput: {
    width: 48, height: 56, borderWidth: 2, borderColor: COLORS.border,
    borderRadius: 12, backgroundColor: COLORS.bg, textAlign: 'center',
    fontSize: 24, fontWeight: '600', color: COLORS.text,
  },
  otpInputFilled: {
    borderColor: COLORS.accent,
    backgroundColor: COLORS.accentLighter,
  },

  // Button
  button: {
    backgroundColor: COLORS.accent, borderRadius: RADII.md,
    paddingVertical: 18, alignItems: 'center', justifyContent: 'center',
    flexDirection: 'row',
    ...SHADOWS.button,
  },
  buttonDisabled: { opacity: 0.35 },
  buttonText: { fontSize: 18, fontWeight: '600', color: COLORS.white },

  // Resend
  resendWrap: { marginTop: SPACING.lg, alignItems: 'center' },
  resendText: { fontSize: 15, color: COLORS.textSecondary },
  resendLink: { color: COLORS.accent, fontWeight: '600' },
});
