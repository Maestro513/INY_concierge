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
 * Soft logout: clear session + tokens but keep device trust.
 * User can re-enter via device unlock (Face ID / fingerprint / PIN)
 * without going through OTP again.
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

  // Destroy encryption key so any remaining cached data is unreadable
  const { destroyEncryptionKey } = require('../utils/secureCache');
  await destroyEncryptionKey();

  // NOTE: Device trust is preserved — next app open will prompt device auth
  // instead of full OTP. Use fullLogout() to clear device trust too.
}

/**
 * Full logout: clear everything including device trust.
 * Next login will require a fresh OTP. Use for "Sign out of this device".
 */
export async function fullLogout() {
  await logout();
  const { clearDeviceTrust } = require('../utils/deviceAuth');
  await clearDeviceTrust();
}
