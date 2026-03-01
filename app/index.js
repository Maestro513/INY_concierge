import { useState, useRef, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, Image,
  StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator, Animated, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SPACING, SHADOWS, TYPE, MOTION } from '../constants/theme';
import { API_URL, fetchWithTimeout, setTokens } from '../constants/api';
import { CALL_NUMBER } from '../constants/data';
import GradientBg from '../components/GradientBg';

const logo = require('../assets/images/logo.png');

export default function PhoneScreen() {
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [focused, setFocused] = useState(false);
  const router = useRouter();

  // Entrance animations
  const logoScale = useRef(new Animated.Value(0.8)).current;
  const logoOpacity = useRef(new Animated.Value(0)).current;
  const contentSlide = useRef(new Animated.Value(30)).current;
  const contentOpacity = useRef(new Animated.Value(0)).current;
  const footerOpacity = useRef(new Animated.Value(0)).current;
  const borderColor = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.spring(logoScale, { toValue: 1, tension: 50, friction: 8, useNativeDriver: true }),
      Animated.timing(logoOpacity, { toValue: 1, duration: MOTION.slow, useNativeDriver: true }),
    ]).start();

    Animated.parallel([
      Animated.timing(contentSlide, { toValue: 0, duration: MOTION.slow, delay: 200, useNativeDriver: true }),
      Animated.timing(contentOpacity, { toValue: 1, duration: MOTION.slow, delay: 200, useNativeDriver: true }),
    ]).start();

    Animated.timing(footerOpacity, { toValue: 1, duration: 600, delay: 500, useNativeDriver: true }).start();
  }, []);

  // Input focus border animation
  useEffect(() => {
    Animated.timing(borderColor, {
      toValue: focused ? 1 : 0,
      duration: MOTION.fast,
      useNativeDriver: false,
    }).start();
  }, [focused]);

  const inputBorderColor = borderColor.interpolate({
    inputRange: [0, 1],
    outputRange: [COLORS.borderLight, COLORS.accentSoft],
  });

  const formatPhone = (val) => {
    const digits = val.replace(/\D/g, '').slice(0, 10);
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return '(' + digits.slice(0, 3) + ') ' + digits.slice(3);
    return '(' + digits.slice(0, 3) + ') ' + digits.slice(3, 6) + '-' + digits.slice(6);
  };

  const rawDigits = phone.replace(/\D/g, '');
  const isValid = rawDigits.length === 10;

  const handleSubmit = async () => {
    if (!isValid) return;
    setLoading(true);
    setError('');

    try {
      // In dev mode, skip OTP — call dev-login to get tokens directly
      if (__DEV__) {
        const res = await fetchWithTimeout(`${API_URL}/auth/dev-login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ phone: rawDigits }),
        });
        const data = await res.json();

        if (res.status === 429) {
          setError("Too many attempts. Please wait a few minutes and try again.");
        } else if (data.found && data.access_token) {
          await setTokens(data.access_token, data.refresh_token);
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
        } else if (data.found === false) {
          setError("We couldn't find an account with that number. Please call us at (844) 463-2931.");
        } else {
          // dev-login not available, fall through to normal flow
          await handleNormalLookup();
        }
        return;
      }

      await handleNormalLookup();
    } catch (err) {
      if (err.name === 'AbortError') {
        setError("Request timed out. Please check your connection and try again.");
      } else {
        setError("Can't connect right now. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleNormalLookup = async () => {
    const res = await fetchWithTimeout(`${API_URL}/auth/lookup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: rawDigits }),
    });
    const data = await res.json();

    if (res.status === 429) {
      setError("Too many attempts. Please wait a few minutes and try again.");
    } else if (data.found) {
      router.push({
        pathname: '/otp',
        params: {
          phone: rawDigits,
          firstName: data.first_name,
        },
      });
    } else {
      setError("We couldn't find an account with that number. Please call us at (844) 463-2931.");
    }
  };

  return (
    <GradientBg style={styles.gradient}>
      <SafeAreaView style={styles.container}>
        <KeyboardAvoidingView
          style={styles.inner}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
          <View style={styles.content}>
            {/* Logo + Branding */}
            <Animated.View style={[styles.logoWrap, {
              opacity: logoOpacity,
              transform: [{ scale: logoScale }],
            }]}>
              <View style={styles.logoCircle}>
                <Image
                  source={logo}
                  style={styles.logo}
                  resizeMode="contain"
                  accessible={true}
                  accessibilityLabel="Med Concierge logo"
                />
              </View>
            </Animated.View>

            <Animated.View style={{
              opacity: contentOpacity,
              transform: [{ translateY: contentSlide }],
            }}>
              <Text style={styles.title} accessibilityRole="header">Med Concierge</Text>
              <Text style={styles.subtitle}>
                Your health plan, simplified.{'\n'}
                <Text style={styles.brandName}>Powered by Insurance 'n You</Text>
              </Text>

              {/* Phone Input Card */}
              <View style={styles.inputCard}>
                <Text style={styles.label} nativeID="phoneLabel">Enter your phone number</Text>
                <Animated.View style={[styles.inputRow, { borderColor: inputBorderColor }]}>
                  <View style={styles.inputIconWrap}>
                    <Ionicons name="call-outline" size={18} color={focused ? COLORS.accent : COLORS.textTertiary} />
                  </View>
                  <TextInput
                    style={styles.phoneInput}
                    value={phone}
                    onChangeText={(val) => { setPhone(formatPhone(val)); setError(''); }}
                    onFocus={() => setFocused(true)}
                    onBlur={() => setFocused(false)}
                    placeholder="(555) 123-4567"
                    placeholderTextColor={COLORS.textTertiary}
                    keyboardType="phone-pad"
                    autoFocus
                    editable={!loading}
                    accessible={true}
                    accessibilityLabel="Phone number input"
                    accessibilityLabelledBy="phoneLabel"
                    accessibilityHint="Enter your 10-digit phone number to look up your plan"
                  />
                  {isValid && !loading ? (
                    <View style={styles.checkWrap}>
                      <Ionicons name="checkmark-circle" size={22} color={COLORS.success} />
                    </View>
                  ) : null}
                </Animated.View>
                <Text style={styles.hint}>We'll look up your plan instantly.</Text>
              </View>

              {error ? (
                <View style={styles.errorWrap} accessibilityRole="alert" accessibilityLiveRegion="assertive">
                  <Ionicons name="alert-circle-outline" size={16} color={COLORS.error} />
                  <Text style={styles.errorText}>{error}</Text>
                </View>
              ) : null}

              <TouchableOpacity
                style={[styles.button, (!isValid || loading) && styles.buttonDisabled]}
                onPress={handleSubmit}
                disabled={!isValid || loading}
                activeOpacity={0.8}
                accessible={true}
                accessibilityRole="button"
                accessibilityLabel="Look up my plan"
                accessibilityState={{ disabled: !isValid || loading }}
              >
                {loading ? (
                  <ActivityIndicator color={COLORS.white} />
                ) : (
                  <>
                    <Text style={styles.buttonText}>Look up my plan</Text>
                    <Ionicons name="arrow-forward" size={18} color={COLORS.white} style={{ marginLeft: 8 }} />
                  </>
                )}
              </TouchableOpacity>
            </Animated.View>
          </View>

          {/* Footer — call for help */}
          <Animated.View style={[styles.footer, { opacity: footerOpacity }]}>
            <Text style={styles.footerText}>Need help? </Text>
            <TouchableOpacity
              onPress={() => Linking.openURL('tel:' + CALL_NUMBER)}
              activeOpacity={0.7}
              accessible={true}
              accessibilityRole="link"
              accessibilityLabel="Call (844) 463-2931 for help"
            >
              <Text style={styles.footerLink}>Call (844) 463-2931</Text>
            </TouchableOpacity>
          </Animated.View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </GradientBg>
  );
}

const styles = StyleSheet.create({
  gradient: { flex: 1 },
  container: { flex: 1 },
  inner: { flex: 1, justifyContent: 'center' },
  content: { paddingHorizontal: SPACING.xl },

  // Logo
  logoWrap: { alignItems: 'flex-start', marginBottom: SPACING.lg },
  logoCircle: {
    width: 80, height: 80, borderRadius: 22,
    backgroundColor: COLORS.white,
    justifyContent: 'center', alignItems: 'center',
    ...SHADOWS.cardLifted,
  },
  logo: { width: 56, height: 56 },

  // Typography
  title: { ...TYPE.hero, color: COLORS.text, marginBottom: SPACING.xs },
  subtitle: {
    ...TYPE.body, fontSize: 17, color: COLORS.textSecondary,
    lineHeight: 26, marginBottom: 32,
  },
  brandName: { fontSize: 15, fontWeight: '600', color: COLORS.accent },

  // Input card
  inputCard: {
    backgroundColor: COLORS.white,
    borderRadius: RADII.lg,
    padding: 20,
    marginBottom: 20,
    ...SHADOWS.card,
  },
  label: { ...TYPE.label, color: COLORS.text, marginBottom: SPACING.sm },
  inputRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: COLORS.bg, borderRadius: RADII.md,
    borderWidth: 1.5, borderColor: COLORS.borderLight,
    overflow: 'hidden',
  },
  inputIconWrap: {
    paddingLeft: 14, paddingRight: 4,
  },
  phoneInput: {
    flex: 1, paddingHorizontal: 10, paddingVertical: 16,
    fontSize: 20, fontWeight: '500', color: COLORS.text, letterSpacing: 0.5,
  },
  checkWrap: { paddingRight: 14 },
  hint: {
    ...TYPE.caption, fontSize: 13, color: COLORS.textTertiary, marginTop: 10,
  },

  // Error
  errorWrap: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: COLORS.errorBg,
    borderRadius: RADII.sm,
    paddingHorizontal: 14, paddingVertical: 12,
    marginBottom: 16,
  },
  errorText: { ...TYPE.bodyMedium, fontSize: 14, color: COLORS.error, flex: 1, lineHeight: 20 },

  // Button
  button: {
    backgroundColor: COLORS.accent, borderRadius: RADII.md,
    paddingVertical: 18, alignItems: 'center', justifyContent: 'center',
    flexDirection: 'row',
    ...SHADOWS.button,
  },
  buttonDisabled: { opacity: 0.35 },
  buttonText: { fontSize: 18, fontWeight: '600', color: COLORS.white, letterSpacing: 0.2 },

  // Footer
  footer: {
    flexDirection: 'row', justifyContent: 'center', alignItems: 'center',
    paddingBottom: SPACING.md, paddingTop: SPACING.sm,
  },
  footerText: { ...TYPE.caption, color: COLORS.textTertiary },
  footerLink: { ...TYPE.caption, color: COLORS.accent, fontWeight: '600' },
});
