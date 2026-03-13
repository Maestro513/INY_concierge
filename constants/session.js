/**
 * In-memory session store for member data.
 *
 * After OTP verification the server returns member info (name, plan, etc.).
 * Rather than passing PHI through Expo Router URL params (visible in logs,
 * deep links, Sentry breadcrumbs), we keep it in memory here.
 */

let _member = null;
let _sessionId = null;

// Pending OTP context — avoids passing phone via URL params
let _pendingOtp = null;

export function setPendingOtp(phone, firstName) {
  _pendingOtp = { phone, firstName };
}

export function getPendingOtp() {
  return _pendingOtp;
}

export function clearPendingOtp() {
  _pendingOtp = null;
}

export function setMemberSession(member, sessionId) {
  _member = { ...member };
  _sessionId = sessionId;
}

export function getMemberSession() {
  return { member: _member, sessionId: _sessionId };
}

export function clearMemberSession() {
  _member = null;
  _sessionId = null;
}

/**
 * Full logout: clear all in-memory state, tokens, and cached PHI.
 * Call this from the logout button to ensure nothing persists.
 */
export async function logout() {
  // Clear in-memory state
  clearMemberSession();
  clearPendingOtp();

  // Clear auth tokens (SecureStore or AsyncStorage)
  const { clearTokens } = require('./api');
  await clearTokens();

  // Clear encrypted offline cache (API responses)
  const { clearAllCache } = require('../utils/offlineCache');
  await clearAllCache();

  // Clear screening flags so screenings show again on next login
  const AsyncStorage = require('@react-native-async-storage/async-storage').default;
  await AsyncStorage.multiRemove(['@health_screening_complete', '@sdoh_screening_complete']);

  // Destroy encryption key so any remaining cached data is unreadable
  const { destroyEncryptionKey } = require('../utils/secureCache');
  await destroyEncryptionKey();
}
