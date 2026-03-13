/**
 * Device authentication — "remember this device" + local biometric/PIN unlock.
 *
 * After the first OTP verification we mark the device as trusted by storing a
 * trust token and the member's phone in SecureStore.  On subsequent app opens
 * we check for the trust token and, if present, prompt the device's own lock
 * screen (Face ID / fingerprint / phone PIN) instead of requiring a new OTP.
 *
 * Trust expires after 90 days of inactivity (no app opens).
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

let LocalAuthentication = null;
let SecureStore = null;

try {
  LocalAuthentication = require('expo-local-authentication');
} catch {
  // Not available (web or missing native module)
}
try {
  SecureStore = require('expo-secure-store');
} catch {
  // Not available
}

// Keys
const TRUST_KEY = '@device_trusted';          // AsyncStorage — "1" if trusted
const TRUST_PHONE_KEY = 'iny_trust_phone';    // SecureStore — phone number
const LAST_ACTIVITY_KEY = '@device_last_activity'; // AsyncStorage — epoch ms

const TRUST_EXPIRY_DAYS = 90;
const TRUST_EXPIRY_MS = TRUST_EXPIRY_DAYS * 24 * 60 * 60 * 1000;

// ── Trust management ────────────────────────────────────────────

/**
 * Mark this device as trusted after successful OTP verification.
 * Stores the member's phone so we can auto-login on return.
 */
export async function markDeviceTrusted(phone) {
  await AsyncStorage.setItem(TRUST_KEY, '1');
  await AsyncStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()));
  if (SecureStore) {
    await SecureStore.setItemAsync(TRUST_PHONE_KEY, phone);
  }
}

/**
 * Update the last-activity timestamp (call on each app foreground).
 */
export async function touchActivity() {
  await AsyncStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()));
}

/**
 * Check if the device is still trusted (token exists + not expired).
 * Returns { trusted: boolean, phone: string | null }.
 */
export async function getDeviceTrust() {
  try {
    const trusted = await AsyncStorage.getItem(TRUST_KEY);
    if (trusted !== '1') return { trusted: false, phone: null };

    // Check expiry
    const lastActivity = await AsyncStorage.getItem(LAST_ACTIVITY_KEY);
    if (lastActivity) {
      const elapsed = Date.now() - parseInt(lastActivity, 10);
      if (elapsed > TRUST_EXPIRY_MS) {
        await clearDeviceTrust();
        return { trusted: false, phone: null };
      }
    }

    // Get stored phone
    let phone = null;
    if (SecureStore) {
      phone = await SecureStore.getItemAsync(TRUST_PHONE_KEY);
    }

    return { trusted: !!phone, phone };
  } catch {
    return { trusted: false, phone: null };
  }
}

/**
 * Clear device trust completely (used for "Sign out of this device").
 */
export async function clearDeviceTrust() {
  await AsyncStorage.multiRemove([TRUST_KEY, LAST_ACTIVITY_KEY]);
  if (SecureStore) {
    await SecureStore.deleteItemAsync(TRUST_PHONE_KEY).catch(() => {});
  }
}

// ── Local authentication (biometric / device PIN) ───────────────

/**
 * Check if the device supports any form of local authentication.
 */
export async function isDeviceAuthAvailable() {
  if (!LocalAuthentication) return false;
  try {
    const hasHardware = await LocalAuthentication.hasHardwareAsync();
    if (!hasHardware) return false;
    const isEnrolled = await LocalAuthentication.isEnrolledAsync();
    return isEnrolled;
  } catch {
    return false;
  }
}

/**
 * Prompt the user for device authentication (Face ID / fingerprint / PIN).
 * Returns true if authenticated, false if cancelled or failed.
 */
export async function authenticateWithDevice() {
  if (!LocalAuthentication) return false;
  try {
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: 'Unlock to access your benefits',
      fallbackLabel: 'Use phone passcode',
      disableDeviceFallback: false,  // Allow phone PIN as fallback
      cancelLabel: 'Use phone number',
    });
    return result.success;
  } catch {
    return false;
  }
}
