import { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  Image,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Animated,
  Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { RADII, MOTION } from '../constants/theme';
import { API_URL, fetchWithTimeout } from '../constants/api';
import { CALL_NUMBER } from '../constants/data';
import { setPendingOtp } from '../constants/session';
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
  const cardSlide = useRef(new Animated.Value(40)).current;
  const cardOpacity = useRef(new Animated.Value(0)).current;
  const borderColor = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.parallel([
      Animated.spring(logoScale, { toValue: 1, tension: 50, friction: 8, useNativeDriver: true }),
      Animated.timing(logoOpacity, { toValue: 1, duration: MOTION.slow, useNativeDriver: true }),
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
  useEffect(() => {
    Animated.timing(borderColor, {
      toValue: focused ? 1 : 0,
      duration: MOTION.fast,
      useNativeDriver: false,
    }).start();
  }, [focused]);
  const _inputBorderColor = borderColor.interpolate({
    inputRange: [0, 1],
    outputRange: ['#F0EDF4', '#7B3FBF'],
  });
  const _inputBgColor = borderColor.interpolate({
    inputRange: [0, 1],
    outputRange: ['#F7F5FA', '#FAF5FF'],
  });
  const formatPhone = (val) => {
    const digits = val.replace(/\D/g, '').slice(0, 10);
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return '(' + digits.slice(0, 3) + ') ' + digits.slice(3);
    return '(' + digits.slice(0, 3) + ') ' + digits.slice(3, 6) + '-' + digits.slice(6);
  };
  const rawDigits = phone.replace(/\D/g, '');
  const isValid =
    rawDigits.length === 10 &&
    !/^(\d)\1{9}$/.test(rawDigits) &&
    !rawDigits.startsWith('000') &&
    !rawDigits.startsWith('1');
  const handleSubmit = async () => {
    if (!isValid) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetchWithTimeout(`${API_URL}/auth/lookup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: rawDigits }),
      });
      const data = await res.json();
      if (res.status === 429) {
        setError('Too many attempts. Please wait a few minutes and try again.');
      } else if (data.found) {
        setPendingOtp(rawDigits, data.first_name);
        router.push('/otp');
      } else {
        setError("We couldn't find an account with that number. Please call us at (844) 463-2931.");
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        setError('Request timed out. Please check your connection and try again.');
      } else {
        setError("Can't connect right now. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };
  return (
    <View style={styles.container}>
      {/* ── Top Section: White with logo ── */}
      <SafeAreaView edges={['top']} style={styles.topSection}>
        <Animated.View
          style={{
            alignItems: 'center',
            opacity: logoOpacity,
            transform: [{ scale: logoScale }],
          }}
        >
          <Image
            source={logo}
            style={styles.logo}
            resizeMode="contain"
            accessible={true}
            accessibilityLabel="InsuranceNYou Concierge logo"
          />
          <Text style={styles.poweredBy}>Powered by</Text>
          <Text style={styles.poweredBrand}>Insurance 'n You</Text>
        </Animated.View>
      </SafeAreaView>
      {/* ── Bottom Section: Purple gradient card ── */}
      <KeyboardAvoidingView
        style={styles.cardSection}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <LinearGradient
          colors={['#9B6BD4', '#7B3FBF', '#6B2FAF']}
          locations={[0, 0.5, 1]}
          style={StyleSheet.absoluteFillObject}
        />
        <Animated.View
          style={[
            styles.cardInner,
            {
              opacity: cardOpacity,
              transform: [{ translateY: cardSlide }],
            },
          ]}
        >
          <Text style={styles.cardTitle}>Welcome to better Medicare</Text>
          <Text style={styles.cardSub}>
            Enter your phone number to access{'\n'}your plan benefits and concierge.
          </Text>
          <Text style={styles.fieldLabel}>PHONE NUMBER</Text>
          <Animated.View
            style={[
              styles.inputWrap,
              {
                borderColor: focused ? 'rgba(255,255,255,0.6)' : 'rgba(255,255,255,0.25)',
                backgroundColor: focused ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.12)',
              },
            ]}
          >
            <Ionicons
              name="call-outline"
              size={20}
              color={focused ? '#fff' : 'rgba(255,255,255,0.6)'}
              style={{ marginLeft: 2 }}
            />
            <TextInput
              style={styles.phoneInput}
              value={phone}
              onChangeText={(val) => {
                setPhone(formatPhone(val));
                setError('');
              }}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              placeholder="(555) 123-4567"
              placeholderTextColor="rgba(255,255,255,0.4)"
              keyboardType="phone-pad"
              autoFocus
              editable={!loading}
              accessible={true}
              accessibilityLabel="Phone number input"
              accessibilityHint="Enter your 10-digit phone number to look up your plan"
            />
            {isValid && !loading ? (
              <Ionicons name="checkmark-circle" size={22} color="#6EE7B7" />
            ) : null}
          </Animated.View>
          <Text style={styles.hint}>We'll send a one-time verification code.</Text>
          {error ? (
            <View
              style={styles.errorWrap}
              accessibilityRole="alert"
              accessibilityLiveRegion="assertive"
            >
              <Ionicons name="alert-circle-outline" size={16} color="#FCA5A5" />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}
          <TouchableOpacity
            style={[
              styles.btn,
              isValid && !loading && styles.btnActive,
              (!isValid || loading) && styles.btnDisabled,
            ]}
            onPress={handleSubmit}
            disabled={!isValid || loading}
            activeOpacity={0.8}
            accessible={true}
            accessibilityRole="button"
            accessibilityLabel="Continue"
            accessibilityState={{ disabled: !isValid || loading }}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Text style={styles.btnText}>Continue</Text>
                <Ionicons name="arrow-forward" size={20} color="#fff" style={{ marginLeft: 6 }} />
              </>
            )}
          </TouchableOpacity>
          {/* Trust signals */}
          <View style={styles.trustRow}>
            <View style={styles.trustItem}>
              <Ionicons name="lock-closed-outline" size={14} color="rgba(255,255,255,0.5)" />
              <Text style={styles.trustText}>HIPAA Secure</Text>
            </View>
            <View style={styles.trustItem}>
              <Ionicons name="shield-checkmark-outline" size={14} color="rgba(255,255,255,0.5)" />
              <Text style={styles.trustText}>256-bit Encrypted</Text>
            </View>
            <View style={styles.trustItem}>
              <Ionicons name="checkmark-circle-outline" size={14} color="rgba(255,255,255,0.5)" />
              <Text style={styles.trustText}>No data stored</Text>
            </View>
          </View>
        </Animated.View>
        {/* Footer */}
        <View style={styles.footer}>
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
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff' },
  // ── Top white section ──
  topSection: {
    alignItems: 'center',
    paddingTop: 30,
    paddingBottom: 40,
    backgroundColor: '#fff',
  },
  logo: { width: 198, height: 198, marginBottom: 0 },
  poweredBy: {
    fontSize: 15,
    fontWeight: '400',
    color: 'rgba(74,20,140,0.45)',
    marginBottom: 2,
    marginTop: -16,
  },
  poweredBrand: {
    fontSize: 18,
    fontWeight: '600',
    color: 'rgba(74,20,140,0.7)',
    marginBottom: 0,
  },
  // ── Purple gradient card section ──
  cardSection: {
    flex: 1,
    borderTopLeftRadius: 32,
    borderTopRightRadius: 32,
    marginTop: -20,
    paddingHorizontal: 28,
    paddingTop: 32,
    overflow: 'hidden',
  },
  cardInner: { flex: 1 },
  cardTitle: {
    fontFamily: Platform.OS === 'ios' ? 'System' : 'sans-serif',
    fontSize: 26,
    fontWeight: '700',
    color: '#fff',
    marginBottom: 6,
  },
  cardSub: {
    fontSize: 15,
    color: '#fff',
    marginBottom: 28,
    lineHeight: 22,
  },
  // ── Input ──
  fieldLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: '#fff',
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  inputWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 16,
    borderWidth: 2,
    paddingHorizontal: 16,
    marginBottom: 10,
  },
  phoneInput: {
    flex: 1,
    paddingHorizontal: 10,
    paddingVertical: 18,
    fontSize: 22,
    fontWeight: '600',
    color: '#fff',
    letterSpacing: 1,
  },
  hint: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.9)',
    marginBottom: 24,
  },
  // ── Error ──
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
  // ── Button ──
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
  // ── Trust row ──
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
  // ── Footer ──
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
