/**
 * In-memory session store for member data.
 *
 * After OTP verification the server returns member info (name, plan, etc.).
 * Rather than passing PHI through Expo Router URL params (visible in logs,
 * deep links, Sentry breadcrumbs), we keep it in memory here.
 */

let _member = null;
let _sessionId = null;

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
