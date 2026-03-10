/**
 * In-memory session store — keeps PHI out of URL params.
 */

let _memberData = null;
let _sessionId = '';
let _pendingOtp = null;

// OTP flow: store phone + firstName before navigating to OTP screen
export function setPendingOtp({ phone, firstName }) {
  _pendingOtp = { phone, firstName };
}

export function getPendingOtp() {
  return _pendingOtp;
}

export function clearPendingOtp() {
  _pendingOtp = null;
}

// After OTP verify: store member data in memory
export function setMemberSession(data, sessionId) {
  _memberData = data;
  _sessionId = sessionId;
}

export function getMemberSession() {
  return { data: _memberData, sessionId: _sessionId };
}

export function clearMemberSession() {
  _memberData = null;
  _sessionId = '';
}
