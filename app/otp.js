import { useState, useRef, useEffect } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, Animated, ActivityIndicator } from 'react-native';
import GradientBg from '../components/GradientBg';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SPACING, SHADOWS, TYPE, MOTION } from '../constants/theme';
import { API_URL, fetchWithTimeout, setTokens } from '../constants/api';

export default function OTPScreen() {
  const { phone, firstName } = useLocalSearchParams();
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [resending, setResending] = useState(false);
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
    setError('');
  };
  const handleKey = (i, k) => { if (k === 'Backspace' && !otp[i] && i > 0) refs.current[i - 1]?.focus(); };
  const filled = otp.every((d) => d !== '');

  // Format phone for display
  const displayPhone = phone
    ? `(${phone.slice(0, 3)}) ${phone.slice(3, 6)}-${phone.slice(6)}`
    : '';

  const handleVerify = async () => {
    if (!filled) return;
    setLoading(true);
    setError('');

    try {
      const code = otp.join('');
      const res = await fetchWithTimeout(`${API_URL}/auth/verify-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, code }),
      });

      if (res.status === 401) {
        setError('Invalid or expired code. Please try again.');
        setOtp(['', '', '', '', '', '']);
        refs.current[0]?.focus();
        return;
      }

      const data = await res.json();

      if (data.access_token) {
        // Store JWT tokens
        await setTokens(data.access_token, data.refresh_token);

        // Navigate to home with member data
        router.replace({
          pathname: '/home',
          params: {
            firstName: data.first_name,
            lastName: data.last_name,
            planName: data.plan_name,
            planNumber: data.plan_number,
            agent: data.agent || '',
            medicareNumber: data.medicare_number || '',
            sessionId: data.session_id || '',
            zipCode: data.zip_code || '',
          },
        });
      } else {
        setError('Verification failed. Please try again.');
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        setError('Request timed out. Please try again.');
      } else {
        setError("Can't connect right now. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setResending(true);
    setError('');
    try {
      const res = await fetchWithTimeout(`${API_URL}/auth/lookup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone }),
      });
      if (res.status === 429) {
        setError('Too many attempts. Please wait a few minutes.');
      } else {
        setOtp(['', '', '', '', '', '']);
        refs.current[0]?.focus();
      }
    } catch {
      setError("Couldn't resend code. Please try again.");
    } finally {
      setResending(false);
    }
  };

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
              <Text style={{ fontWeight: '700', color: COLORS.text }}>{displayPhone}</Text>
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
                    editable={!loading}
                  />
                ))}
              </View>
            </View>

            {error ? (
              <View style={s.errorWrap}>
                <Ionicons name="alert-circle-outline" size={16} color={COLORS.error} />
                <Text style={s.errorText}>{error}</Text>
              </View>
            ) : null}

            <TouchableOpacity
              style={[s.button, (!filled || loading) && s.buttonDisabled]}
              onPress={handleVerify}
              disabled={!filled || loading}
              activeOpacity={0.8}
            >
              {loading ? (
                <ActivityIndicator color={COLORS.white} />
              ) : (
                <>
                  <Text style={s.buttonText}>Verify</Text>
                  <Ionicons name="checkmark" size={18} color={COLORS.white} style={{ marginLeft: 6 }} />
                </>
              )}
            </TouchableOpacity>

            <TouchableOpacity style={s.resendWrap} activeOpacity={0.7} onPress={handleResend} disabled={resending}>
              <Text style={s.resendText}>
                Didn't get it? <Text style={s.resendLink}>{resending ? 'Sending...' : 'Resend code'}</Text>
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
    paddingHorizontal: 12, paddingVertical: 20, marginBottom: 24,
    ...SHADOWS.card,
  },
  otpRow: { flexDirection: 'row', justifyContent: 'space-between' },
  otpInput: {
    flex: 1, marginHorizontal: 4, height: 56, borderWidth: 2, borderColor: COLORS.border,
    borderRadius: 12, backgroundColor: COLORS.bg, textAlign: 'center',
    fontSize: 24, fontWeight: '600', color: COLORS.text,
  },
  otpInputFilled: {
    borderColor: COLORS.accent,
    backgroundColor: COLORS.accentLighter,
  },

  // Error
  errorWrap: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: COLORS.errorBg,
    borderRadius: RADII.sm,
    paddingHorizontal: 14, paddingVertical: 12,
    marginBottom: 16,
  },
  errorText: { fontSize: 14, color: COLORS.error, flex: 1, lineHeight: 20 },

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
