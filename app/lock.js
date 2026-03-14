/**
 * Lock screen — prompts device authentication (Face ID / fingerprint / phone PIN)
 * for returning users on a trusted device.
 *
 * If auth succeeds → auto-login with stored phone and go to /home.
 * If user cancels  → fall back to phone number entry (full OTP flow).
 */

import { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Animated,
  Platform,
  Image,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { COLORS, RADII, MOTION } from '../constants/theme';
import { API_URL, fetchWithTimeout, setTokens, loadTokens } from '../constants/api';
import { authenticateWithDevice, getDeviceTrust, touchActivity } from '../utils/deviceAuth';

const logo = require('../assets/images/logo.png');

export default function LockScreen() {
  const router = useRouter();
  const [status, setStatus] = useState('prompting'); // prompting | authenticating | error
  const [error, setError] = useState('');

  // Animations
  const fadeIn = useRef(new Animated.Value(0)).current;
  const slideUp = useRef(new Animated.Value(30)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeIn, { toValue: 1, duration: MOTION.slow, useNativeDriver: true }),
      Animated.timing(slideUp, { toValue: 0, duration: MOTION.slow, useNativeDriver: true }),
    ]).start();

    // Auto-prompt on mount
    handleUnlock();
  }, []);

  const handleUnlock = async () => {
    setStatus('authenticating');
    setError('');

    // Step 1: Verify device is still trusted
    const { trusted, phone } = await getDeviceTrust();
    if (!trusted || !phone) {
      // Trust expired or missing — go to full login
      router.replace('/');
      return;
    }

    // Step 2: Prompt device auth (Face ID / fingerprint / phone PIN)
    const authenticated = await authenticateWithDevice();
    if (!authenticated) {
      setStatus('prompting');
      setError('Authentication cancelled. Try again or use your phone number.');
      return;
    }

    // Step 3: Re-authenticate with backend using stored refresh token
    const { refresh } = await loadTokens();
    if (refresh) {
      try {
        const res = await fetchWithTimeout(`${API_URL}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refresh }),
        });
        const data = await res.json();

        if (data.access_token) {
          await setTokens(data.access_token, data.refresh_token);
          await touchActivity();
          router.replace('/home');
          return;
        }
      } catch {
        // Token refresh failed — try phone lookup below
      }
    }

    // Step 4: Tokens expired — do a fresh lookup + auto-send OTP
    try {
      const lookupRes = await fetchWithTimeout(`${API_URL}/auth/lookup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone }),
      });

      if (lookupRes.ok) {
        const data = await lookupRes.json();
        if (data.otp_sent) {
          // M9: Backend returns otp_sent (no first_name pre-auth).
          const { setPendingOtp } = require('../constants/session');
          setPendingOtp(phone, '');
          router.replace('/otp');
          return;
        }
      }
    } catch {
      // Network error
    }

    // All else failed — clear trust and go to full login
    setError('Session expired. Please log in with your phone number.');
    setStatus('error');
  };

  const handleUsePhoneNumber = () => {
    router.replace('/');
  };

  return (
    <View style={s.container}>
      <LinearGradient
        colors={['#FFFFFF', '#F7F5FA', '#EDE7F6']}
        locations={[0, 0.5, 1]}
        style={StyleSheet.absoluteFillObject}
      />
      <SafeAreaView style={s.safe}>
        <Animated.View
          style={[s.content, { opacity: fadeIn, transform: [{ translateY: slideUp }] }]}
        >
          <Image
            source={logo}
            style={s.logo}
            resizeMode="contain"
            accessibilityLabel="InsuranceNYou Concierge logo"
          />

          <Text style={s.title}>Welcome back</Text>
          <Text style={s.subtitle}>
            Unlock with {Platform.OS === 'ios' ? 'Face ID, Touch ID,' : 'fingerprint,'} or your
            phone passcode
          </Text>

          {status === 'authenticating' ? (
            <View style={s.statusWrap}>
              <ActivityIndicator size="large" color={COLORS.accent} />
              <Text style={s.statusText}>Verifying...</Text>
            </View>
          ) : (
            <>
              {error ? (
                <View style={s.errorWrap}>
                  <Ionicons name="alert-circle-outline" size={18} color="#C0392B" />
                  <Text style={s.errorText}>{error}</Text>
                </View>
              ) : null}

              <TouchableOpacity
                style={s.unlockBtn}
                onPress={handleUnlock}
                activeOpacity={0.7}
                accessibilityRole="button"
                accessibilityLabel="Unlock with device authentication"
              >
                <Ionicons
                  name={Platform.OS === 'ios' ? 'finger-print' : 'finger-print'}
                  size={24}
                  color="#fff"
                />
                <Text style={s.unlockText}>Unlock</Text>
              </TouchableOpacity>
            </>
          )}

          <TouchableOpacity
            style={s.fallbackBtn}
            onPress={handleUsePhoneNumber}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel="Use phone number instead"
          >
            <Text style={s.fallbackText}>Use phone number instead</Text>
          </TouchableOpacity>
        </Animated.View>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1 },
  safe: { flex: 1, justifyContent: 'center' },

  content: {
    alignItems: 'center',
    paddingHorizontal: 32,
  },
  logo: {
    width: 140,
    height: 140,
    marginBottom: 20,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: COLORS.text,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    fontWeight: '400',
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: 24,
    marginBottom: 36,
    paddingHorizontal: 20,
  },

  // Status
  statusWrap: {
    alignItems: 'center',
    gap: 12,
    marginBottom: 30,
  },
  statusText: {
    fontSize: 16,
    fontWeight: '500',
    color: COLORS.textSecondary,
  },

  // Error
  errorWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#FEF2F2',
    borderRadius: RADII.md,
    paddingHorizontal: 16,
    paddingVertical: 12,
    marginBottom: 20,
    maxWidth: '100%',
  },
  errorText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#991B1B',
    flex: 1,
    lineHeight: 20,
  },

  // Unlock button
  unlockBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    backgroundColor: COLORS.accent,
    borderRadius: RADII.full || 24,
    paddingVertical: 18,
    paddingHorizontal: 48,
    marginBottom: 16,
    shadowColor: COLORS.accent,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 6,
  },
  unlockText: {
    fontSize: 18,
    fontWeight: '700',
    color: '#fff',
  },

  // Fallback
  fallbackBtn: {
    paddingVertical: 12,
    marginTop: 8,
  },
  fallbackText: {
    fontSize: 15,
    fontWeight: '500',
    color: COLORS.textTertiary,
  },
});
