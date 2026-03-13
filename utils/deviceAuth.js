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

// Keys — all stored in SecureStore to prevent tampering on rooted devices
const TRUST_KEY = 'iny_trust_flag';            // SecureStore — "1" if trusted
const TRUST_PHONE_KEY = 'iny_trust_phone';     // SecureStore — phone number
const LAST_ACTIVITY_KEY = 'iny_trust_activity'; // SecureStore — epoch ms

const TRUST_EXPIRY_DAYS = 90;
const TRUST_EXPIRY_MS = TRUST_EXPIRY_DAYS * 24 * 60 * 60 * 1000;

// ── Trust management ────────────────────────────────────────────

/**
 * Mark this device as trusted after successful OTP verification.
 * Stores the member's phone so we can auto-login on return.
 */
export async function markDeviceTrusted(phone) {
  if (!SecureStore) return;
  await SecureStore.setItemAsync(TRUST_KEY, '1');
  await SecureStore.setItemAsync(LAST_ACTIVITY_KEY, String(Date.now()));
  await SecureStore.setItemAsync(TRUST_PHONE_KEY, phone);
}

/**
 * Update the last-activity timestamp (call on each app foreground).
 */
export async function touchActivity() {
  if (!SecureStore) return;
  await SecureStore.setItemAsync(LAST_ACTIVITY_KEY, String(Date.now()));
}

/**
 * Check if the device is still trusted (token exists + not expired).
 * Returns { trusted: boolean, phone: string | null }.
 */
export async function getDeviceTrust() {
  if (!SecureStore) return { trusted: false, phone: null };
  try {
    const trusted = await SecureStore.getItemAsync(TRUST_KEY);
    if (trusted !== '1') return { trusted: false, phone: null };

    // Check expiry
    const lastActivity = await SecureStore.getItemAsync(LAST_ACTIVITY_KEY);
    if (lastActivity) {
      const elapsed = Date.now() - parseInt(lastActivity, 10);
      if (elapsed > TRUST_EXPIRY_MS) {
        await clearDeviceTrust();
        return { trusted: false, phone: null };
      }
    }

    // Get stored phone
    const phone = await SecureStore.getItemAsync(TRUST_PHONE_KEY);
    return { trusted: !!phone, phone };
  } catch {
    return { trusted: false, phone: null };
  }
}

/**
 * Clear device trust completely (used for "Sign out of this device").
 */
export async function clearDeviceTrust() {
  if (!SecureStore) return;
  await SecureStore.deleteItemAsync(TRUST_KEY).catch(() => {});
  await SecureStore.deleteItemAsync(LAST_ACTIVITY_KEY).catch(() => {});
  await SecureStore.deleteItemAsync(TRUST_PHONE_KEY).catch(() => {});
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
