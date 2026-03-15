import { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Animated,
  ActivityIndicator,
  Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { RADII, MOTION } from '../constants/theme';
import { API_URL, fetchWithTimeout, setTokens } from '../constants/api';
import { setMemberSession, getPendingOtp, clearPendingOtp, setCaregiverInfo } from '../constants/session';
import { CALL_NUMBER } from '../constants/data';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { markDeviceTrusted } from '../utils/deviceAuth';

export default function OTPScreen() {
  const pending = getPendingOtp();
  const phone = pending?.phone || '';
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [resending, setResending] = useState(false);
  const refs = useRef([]);
  const router = useRouter();

  // Entrance animations
  const iconOpacity = useRef(new Animated.Value(0)).current;
  const iconScale = useRef(new Animated.Value(0.8)).current;
  const cardSlide = useRef(new Animated.Value(40)).current;
  const cardOpacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.spring(iconScale, {
        toValue: 1,
        tension: 50,
        friction: 8,
        useNativeDriver: true,
      }),
      Animated.timing(iconOpacity, {
        toValue: 1,
        duration: MOTION.slow,
        useNativeDriver: true,
      }),
    ]).start();
    Animated.parallel([
      Animated.timing(cardSlide, {
        toValue: 0,
        duration: MOTION.slow,
        delay: 200,
        useNativeDriver: true,
      }),
      Animated.timing(cardOpacity, {
        toValue: 1,
        duration: MOTION.slow,
        delay: 200,
        useNativeDriver: true,
      }),
    ]).start();
  }, []);

  const handleChange = (i, v) => {
    if (!/^\d?$/.test(v)) return;
    const n = [...otp];
    n[i] = v;
    setOtp(n);
    if (v && i < 5) refs.current[i + 1]?.focus();
    setError('');
  };
  const handleKey = (i, k) => {
    if (k === 'Backspace' && !otp[i] && i > 0) refs.current[i - 1]?.focus();
  };
  const filled = otp.every((d) => d !== '');

  // Format phone for display
  const displayPhone = phone ? `(${phone.slice(0, 3)}) ${phone.slice(3, 6)}-${phone.slice(6)}` : '';

  const handleVerify = async () => {
    if (!filled) return;
    if (!phone) {
      setError('Phone number missing. Please go back and try again.');
      return;
    }
    setLoading(true);
    setError('');

    const url = `${API_URL}/auth/verify-otp`;
    const MAX_RETRIES = 2;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const code = otp.join('');
        const res = await fetchWithTimeout(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ phone, code }),
        });

        if (res.status === 401) {
          setError('Invalid or expired code. Please try again.');
          setOtp(['', '', '', '', '', '']);
          refs.current[0]?.focus();
          setLoading(false);
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

          // Mark device as trusted so future logins use device auth
          await markDeviceTrusted(phone);

          // Check for caregiver-only user (not a member, just an invited caregiver)
          if (data.is_caregiver_only) {
            setCaregiverInfo({
              isCaregiverOnly: true,
              pendingInvite: data.pending_caregiver_invite,
            });
            router.replace('/caregiver-accept');
            return;
          }

          // Check if member also has a pending caregiver invite
          if (data.pending_caregiver_invite) {
            setCaregiverInfo({
              isCaregiverOnly: false,
              pendingInvite: true,
            });
          }

          // Check if member is also a caregiver for someone
          if (data.is_caregiver_for) {
            setCaregiverInfo({
              isCaregiverOnly: false,
              isCaregiverFor: data.is_caregiver_for,
            });
          }

          const isDev = code === '123456';
          const screeningDone = await AsyncStorage.getItem('@health_screening_complete');
          router.replace(!isDev && screeningDone ? '/home' : '/health-screening');
        } else {
          setError('Verification failed. Please try again.');
        }
        setLoading(false);
        return;
      } catch (err) {
        if (err.name === 'AbortError') {
          setError('Request timed out. Please try again.');
          setLoading(false);
          return;
        }
        if (attempt < MAX_RETRIES) {
          await new Promise((r) => setTimeout(r, (attempt + 1) * 2000));
          continue;
        }
        setError(
          "Can't reach the server right now. Please check your internet connection and try again.",
        );
      }
    }
    setLoading(false);
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
    <View style={s.container}>
      {/* ── Top Section: White with icon ── */}
      <SafeAreaView edges={['top']} style={s.topSection}>
        <Animated.View
          style={{
            alignItems: 'center',
            opacity: iconOpacity,
            transform: [{ scale: iconScale }],
          }}
        >
          <View style={s.iconCircle}>
            <Ionicons name="chatbubble-ellipses-outline" size={40} color="#7B3FBF" />
          </View>
          <Text style={s.topTitle}>Verify your number</Text>
          <Text style={s.topSub}>
            We sent a 6-digit code to{'\n'}
            <Text style={{ fontWeight: '700', color: '#4A148C' }}>{displayPhone}</Text>
          </Text>
        </Animated.View>
      </SafeAreaView>

      {/* ── Bottom Section: Purple gradient ── */}
      <KeyboardAvoidingView
        style={s.cardSection}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <LinearGradient
          colors={['#9B6BD4', '#7B3FBF', '#6B2FAF']}
          locations={[0, 0.5, 1]}
          style={StyleSheet.absoluteFillObject}
        />
        <Animated.View
          style={[
            s.cardInner,
            {
              opacity: cardOpacity,
              transform: [{ translateY: cardSlide }],
            },
          ]}
        >
          {/* Back button */}
          <TouchableOpacity
            onPress={() => router.back()}
            style={s.backBtn}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel="Go back"
          >
            <Ionicons name="chevron-back" size={18} color="rgba(255,255,255,0.8)" />
            <Text style={s.backText}>Back</Text>
          </TouchableOpacity>

          <Text style={s.fieldLabel}>ENTER VERIFICATION CODE</Text>

          {/* OTP Inputs */}
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
                accessibilityLabel={`Verification code digit ${i + 1} of 6`}
              />
            ))}
          </View>

          {error ? (
            <View style={s.errorWrap} accessibilityLiveRegion="assertive">
              <Ionicons name="alert-circle-outline" size={16} color="#FCA5A5" />
              <Text style={s.errorText} accessibilityRole="alert">
                {error}
              </Text>
            </View>
          ) : null}

          <TouchableOpacity
            style={[
              s.btn,
              filled && !loading && s.btnActive,
              (!filled || loading) && s.btnDisabled,
            ]}
            onPress={handleVerify}
            disabled={!filled || loading}
            activeOpacity={0.8}
            accessibilityRole="button"
            accessibilityLabel="Verify code"
            accessibilityState={{ disabled: !filled || loading }}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Text style={s.btnText}>Verify</Text>
                <Ionicons name="checkmark" size={20} color="#fff" style={{ marginLeft: 6 }} />
              </>
            )}
          </TouchableOpacity>

          {/* Resend */}
          <TouchableOpacity
            style={s.resendWrap}
            activeOpacity={0.7}
            onPress={handleResend}
            disabled={resending}
            accessibilityRole="button"
            accessibilityLabel={resending ? 'Sending new code' : 'Resend verification code'}
            accessibilityState={{ disabled: resending }}
          >
            <Text style={s.resendText}>
              {"Didn't get it? "}
              <Text style={s.resendLink}>{resending ? 'Sending...' : 'Resend code'}</Text>
            </Text>
          </TouchableOpacity>

          {/* Trust signals */}
          <View style={s.trustRow}>
            <View style={s.trustItem}>
              <Ionicons name="lock-closed-outline" size={14} color="rgba(255,255,255,0.5)" />
              <Text style={s.trustText}>HIPAA Secure</Text>
            </View>
            <View style={s.trustItem}>
              <Ionicons name="shield-checkmark-outline" size={14} color="rgba(255,255,255,0.5)" />
              <Text style={s.trustText}>256-bit Encrypted</Text>
            </View>
          </View>
        </Animated.View>

        {/* Footer */}
        <View style={s.footer}>
          <Text style={s.footerText}>Need help? </Text>
          <TouchableOpacity
            onPress={() => Linking.openURL('tel:' + CALL_NUMBER)}
            activeOpacity={0.7}
            accessibilityRole="link"
            accessibilityLabel="Call for help"
          >
            <Text style={s.footerLink}>Call (844) 463-2931</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff' },

  // ── Top white section ──
  topSection: {
    alignItems: 'center',
    paddingTop: 40,
    paddingBottom: 40,
    backgroundColor: '#fff',
  },
  iconCircle: {
    width: 80,
    height: 80,
    borderRadius: 24,
    backgroundColor: '#F3ECFA',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  topTitle: {
    fontFamily: Platform.OS === 'ios' ? 'System' : 'sans-serif',
    fontSize: 26,
    fontWeight: '700',
    color: '#1A1A2E',
    marginBottom: 8,
  },
  topSub: {
    fontSize: 16,
    color: 'rgba(74,20,140,0.6)',
    textAlign: 'center',
    lineHeight: 24,
  },

  // ── Purple gradient card section ──
  cardSection: {
    flex: 1,
    borderTopLeftRadius: 32,
    borderTopRightRadius: 32,
    marginTop: -20,
    paddingHorizontal: 28,
    paddingTop: 28,
    overflow: 'hidden',
  },
  cardInner: { flex: 1 },

  // Back button
  backBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginBottom: 24,
    alignSelf: 'flex-start',
  },
  backText: {
    fontSize: 15,
    fontWeight: '500',
    color: 'rgba(255,255,255,0.8)',
  },

  // Field label
  fieldLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: '#fff',
    letterSpacing: 0.5,
    marginBottom: 12,
  },

  // OTP inputs
  otpRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  otpInput: {
    flex: 1,
    marginHorizontal: 4,
    height: 58,
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.25)',
    borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.12)',
    textAlign: 'center',
    fontSize: 26,
    fontWeight: '700',
    color: '#fff',
  },
  otpInputFilled: {
    borderColor: 'rgba(255,255,255,0.6)',
    backgroundColor: 'rgba(255,255,255,0.2)',
  },

  // Error
  errorWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: 'rgba(255,255,255,0.15)',
    borderRadius: RADII.sm,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 16,
  },
  errorText: { fontSize: 14, color: '#FCA5A5', flex: 1, lineHeight: 20 },

  // Button
  btn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 16,
    paddingVertical: 20,
    backgroundColor: 'rgba(255,255,255,0.2)',
    shadowColor: 'rgba(0,0,0,0.1)',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 1,
    shadowRadius: 20,
    elevation: 6,
  },
  btnActive: {
    backgroundColor: '#10B981',
    shadowColor: 'rgba(16,185,129,0.3)',
  },
  btnDisabled: { opacity: 0.5 },
  btnText: {
    fontSize: 18,
    fontWeight: '700',
    color: '#fff',
    letterSpacing: 0.3,
  },

  // Resend
  resendWrap: { marginTop: 20, alignItems: 'center' },
  resendText: { fontSize: 15, color: 'rgba(255,255,255,0.7)' },
  resendLink: { color: '#fff', fontWeight: '600' },

  // Trust row
  trustRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 20,
    marginTop: 20,
    paddingTop: 20,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.15)',
  },
  trustItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  trustText: {
    fontSize: 14,
    fontWeight: '500',
    color: 'rgba(255,255,255,0.9)',
  },

  // Footer
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingBottom: 56,
    paddingTop: 12,
    marginTop: 'auto',
  },
  footerText: { fontSize: 17, color: 'rgba(255,255,255,0.95)' },
  footerLink: { fontSize: 17, color: '#fff', fontWeight: '600' },
});
