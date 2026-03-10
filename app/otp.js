import { useState, useRef, useEffect, useCallback } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, Animated, ActivityIndicator } from 'react-native';
import GradientBg from '../components/GradientBg';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SPACING, SHADOWS, TYPE, MOTION } from '../constants/theme';
import { API_URL, fetchWithTimeout, setTokens } from '../constants/api';
import { setMemberSession, getPendingOtp, clearPendingOtp } from '../constants/session';

const RESEND_COOLDOWN = 30; // seconds

export default function OTPScreen() {
  const pending = getPendingOtp();
  const phone = pending?.phone || '';
  const firstName = pending?.firstName || '';
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [resending, setResending] = useState(false);
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN);
  const refs = useRef([]);
  const router = useRouter();

  // Animations
  const contentOpacity = useRef(new Animated.Value(0)).current;
  const contentSlide = useRef(new Animated.Value(24)).current;
  const shieldScale = useRef(new Animated.Value(0.6)).current;
  const shieldOpacity = useRef(new Animated.Value(0)).current;
  const boxAnims = useRef(otp.map(() => new Animated.Value(0))).current;

  useEffect(() => {
    // Shield entrance
    Animated.parallel([
      Animated.spring(shieldScale, { toValue: 1, tension: 50, friction: 8, useNativeDriver: true }),
      Animated.timing(shieldOpacity, { toValue: 1, duration: MOTION.slow, useNativeDriver: true }),
    ]).start();

    // Content slide up
    Animated.parallel([
      Animated.timing(contentOpacity, { toValue: 1, duration: MOTION.slow, delay: 150, useNativeDriver: true }),
      Animated.timing(contentSlide, { toValue: 0, duration: MOTION.slow, delay: 150, useNativeDriver: true }),
    ]).start();

    // Staggered OTP box entrance
    Animated.stagger(MOTION.staggerDelay, boxAnims.map((a) =>
      Animated.spring(a, { toValue: 1, tension: 60, friction: 8, useNativeDriver: true })
    )).start();
  }, []);

  // Resend cooldown timer
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setInterval(() => setCooldown((c) => c - 1), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  // Format phone for display
  const displayPhone = phone
    ? `(${phone.slice(0, 3)}) ${phone.slice(3, 6)}-${phone.slice(6)}`
    : '';

  const handleChange = (i, v) => {
    if (!/^\d?$/.test(v)) return;
    const n = [...otp]; n[i] = v; setOtp(n);
    if (v && i < 5) refs.current[i + 1]?.focus();
    setError('');
  };

  const handleKey = (i, k) => {
    if (k === 'Backspace' && !otp[i] && i > 0) refs.current[i - 1]?.focus();
  };

  const filled = otp.every((d) => d !== '');

  // Auto-submit when all digits filled
  const handleVerify = useCallback(async (code) => {
    if (!phone) {
      setError('Phone number missing. Please go back and try again.');
      return;
    }
    setLoading(true);
    setError('');

    try {
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
        await setTokens(data.access_token, data.refresh_token);
        setMemberSession(
          {
            firstName: data.first_name,
            lastName: data.last_name,
            planName: data.plan_name,
            planNumber: data.plan_number,
            agent: data.agent || '',
            zipCode: data.zip_code || '',
          },
          data.session_id || '',
        );
        clearPendingOtp();
        router.replace('/home');
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
  }, [phone, router]);

  // Trigger auto-submit when last digit entered (once)
  const autoSubmitted = useRef(false);
  useEffect(() => {
    if (filled && !loading && !autoSubmitted.current) {
      autoSubmitted.current = true;
      handleVerify(otp.join(''));
    }
    if (!filled) autoSubmitted.current = false;
  }, [otp, filled, loading, handleVerify]);

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
        setCooldown(RESEND_COOLDOWN);
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
          {/* Back button */}
          <View style={s.topBar}>
            <TouchableOpacity onPress={() => router.back()} style={s.backBtn} activeOpacity={0.7}>
              <View style={s.backIconWrap}>
                <Ionicons name="chevron-back" size={18} color={COLORS.accent} />
              </View>
              <Text style={s.backText}>Back</Text>
            </TouchableOpacity>
          </View>

          <Animated.View style={[s.content, { opacity: contentOpacity, transform: [{ translateY: contentSlide }] }]}>
            {/* Shield icon */}
            <Animated.View style={[s.iconCircle, { opacity: shieldOpacity, transform: [{ scale: shieldScale }] }]}>
              <Ionicons name="shield-checkmark" size={30} color={COLORS.accent} />
            </Animated.View>

            {/* Greeting + instructions */}
            <Text style={s.title}>
              {firstName ? `Hey ${firstName}, ` : ''}verify your number
            </Text>
            <Text style={s.subtitle}>
              We sent a 6-digit code to{'\n'}
              <Text style={s.phoneHighlight}>{displayPhone}</Text>
            </Text>

            {/* OTP Input Card */}
            <View style={s.otpCard}>
              <View style={s.otpCardHeader}>
                <Ionicons name="lock-closed" size={14} color={COLORS.accent} />
                <Text style={s.otpCardLabel}>Secure verification</Text>
              </View>
              <View style={s.otpRow}>
                {otp.map((d, i) => (
                  <Animated.View
                    key={i}
                    style={{
                      flex: 1,
                      marginHorizontal: 4,
                      opacity: boxAnims[i],
                      transform: [{ scale: boxAnims[i].interpolate({ inputRange: [0, 1], outputRange: [0.7, 1] }) }],
                    }}
                  >
                    <TextInput
                      ref={(el) => (refs.current[i] = el)}
                      style={[s.otpInput, d ? s.otpInputFilled : null]}
                      value={d}
                      onChangeText={(v) => handleChange(i, v)}
                      onKeyPress={({ nativeEvent }) => handleKey(i, nativeEvent.key)}
                      keyboardType="number-pad"
                      maxLength={1}
                      selectTextOnFocus
                      editable={!loading}
                      accessible
                      accessibilityLabel={`Digit ${i + 1} of 6`}
                    />
                  </Animated.View>
                ))}
              </View>
            </View>

            {/* Error */}
            {error ? (
              <View style={s.errorWrap} accessibilityRole="alert" accessibilityLiveRegion="assertive">
                <Ionicons name="alert-circle-outline" size={16} color={COLORS.error} />
                <Text style={s.errorText}>{error}</Text>
              </View>
            ) : null}

            {/* Verify button */}
            <TouchableOpacity
              style={[s.button, (!filled || loading) && s.buttonDisabled]}
              onPress={() => handleVerify(otp.join(''))}
              disabled={!filled || loading}
              activeOpacity={0.8}
              accessible
              accessibilityRole="button"
              accessibilityLabel="Verify code"
              accessibilityState={{ disabled: !filled || loading }}
            >
              {loading ? (
                <ActivityIndicator color={COLORS.white} />
              ) : (
                <>
                  <Text style={s.buttonText}>Verify</Text>
                  <Ionicons name="checkmark-circle" size={20} color={COLORS.white} style={{ marginLeft: 8 }} />
                </>
              )}
            </TouchableOpacity>

            {/* Resend */}
            <View style={s.resendWrap}>
              {cooldown > 0 ? (
                <Text style={s.resendText}>
                  Resend code in <Text style={s.cooldownNum}>{cooldown}s</Text>
                </Text>
              ) : (
                <TouchableOpacity activeOpacity={0.7} onPress={handleResend} disabled={resending}>
                  <Text style={s.resendText}>
                    Didn't get it?{' '}
                    <Text style={s.resendLink}>{resending ? 'Sending...' : 'Resend code'}</Text>
                  </Text>
                </TouchableOpacity>
              )}
            </View>

            {/* Trust footer */}
            <View style={s.trustRow}>
              <Ionicons name="lock-closed-outline" size={13} color={COLORS.textTertiary} />
              <Text style={s.trustText}>End-to-end encrypted. Your data stays private.</Text>
            </View>
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

  // Top bar
  topBar: { position: 'absolute', top: 0, left: 0, right: 0, paddingHorizontal: SPACING.xl, paddingTop: SPACING.sm, zIndex: 10 },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start' },
  backIconWrap: {
    width: 32, height: 32, borderRadius: 10,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center', alignItems: 'center',
  },
  backText: { ...TYPE.label, fontSize: 15, color: COLORS.accent },

  // Shield icon
  iconCircle: {
    width: 64, height: 64, borderRadius: 20,
    backgroundColor: COLORS.accentLighter,
    borderWidth: 1, borderColor: COLORS.accentLight,
    justifyContent: 'center', alignItems: 'center',
    marginBottom: SPACING.md,
  },

  // Typography
  title: { ...TYPE.h1, fontSize: 26, color: COLORS.text, marginBottom: SPACING.sm },
  subtitle: { ...TYPE.body, fontSize: 16, color: COLORS.textSecondary, lineHeight: 24, marginBottom: 28 },
  phoneHighlight: { fontWeight: '700', color: COLORS.text },

  // OTP card
  otpCard: {
    backgroundColor: COLORS.white, borderRadius: RADII.lg,
    paddingHorizontal: 12, paddingTop: 14, paddingBottom: 20, marginBottom: 24,
    ...SHADOWS.card,
  },
  otpCardHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginBottom: 14, paddingHorizontal: 4,
  },
  otpCardLabel: { ...TYPE.labelSmall, color: COLORS.accent, letterSpacing: 0.5 },
  otpRow: { flexDirection: 'row', justifyContent: 'space-between' },
  otpInput: {
    height: 56, borderWidth: 2, borderColor: COLORS.border,
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
  cooldownNum: { color: COLORS.accent, fontWeight: '700' },

  // Trust footer
  trustRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, marginTop: SPACING.xl, opacity: 0.7,
  },
  trustText: { ...TYPE.caption, fontSize: 12, color: COLORS.textTertiary },
});
