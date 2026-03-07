# INY Concierge — Pass 2 Security & Production Readiness Audit

**Date:** March 7, 2026
**Scope:** Full codebase re-review (backend, mobile, admin, tests, infra) — two-pass security + production readiness
**Method:** 5 parallel audit agents covering auth/crypto, API endpoints, external integrations, frontend/static, and production readiness

---

## Executive Summary

After fixing 40+ issues from Pass 1, a complete re-audit found **8 Critical**, **15 High**, **18 Medium**, and **7 Low** new or residual issues across the full stack. The most urgent are missing rate limiting on auth endpoints, IDOR on CMS/SOB endpoints, PHI cached plaintext on mobile devices, and no logout flow in the mobile app.

---

## Critical Findings (P0)

### Backend

**P2-C1. No Rate Limiting on `/auth/lookup` — Phone Enumeration + SMS Flood**
- **File:** `backend/app/main.py:766`
- No `_check_ip_rate()` call. Attacker can enumerate valid phone numbers (`found: true` vs `false`) and flood SMS to arbitrary numbers (per-phone OTP rate limit bypassed by iterating phone numbers).
- **Fix:** Add `_check_ip_rate(request, max_hits=5, window=60, label="auth_lookup")`.

**P2-C2. No Rate Limiting on `/auth/verify-otp` — Cross-Phone OTP Brute Force**
- **File:** `backend/app/main.py:836`
- Per-phone lockout exists but no IP-level throttle. Attacker knowing multiple phone numbers can try OTPs across different phones from the same IP.
- **Fix:** Add `_check_ip_rate(request, max_hits=10, window=60, label="auth_verify")`.

**P2-C3. IDOR on All CMS/SOB Endpoints — Any User Can Access Any Plan**
- **Files:** `backend/app/main.py:1335,1485,1562-1647,2280`
- 13+ endpoints accept arbitrary `plan_number` with authentication but no authorization. User A can query User B's plan benefits, drug formulary, SOB PDF, and ID card data.
- **Risk:** `/cms/id-card/{plan_number}` returns Rx BIN/PCN/Group numbers useful for insurance fraud.
- **Fix:** Verify authenticated user's plan matches requested plan, or scope endpoints to session-based access.

**P2-C4. Path Traversal in `/api/admin/plans/{plan_number}`**
- **File:** `backend/app/admin_router.py:542-559`
- `plan_number` used directly in `os.path.join(EXTRACTED_DIR, f"{plan_number}.json")` with no path validation. Any authenticated admin (including `viewer`) can read arbitrary `.json` files.
- **Fix:** Validate resolved path stays within `EXTRACTED_DIR` (same pattern as tar upload handler).

**P2-C5. `FIELD_ENCRYPTION_KEY` Not Enforced at Startup**
- **File:** `backend/app/config.py:75`
- Unlike `JWT_SECRET` and `ADMIN_SECRET`, no startup check that `FIELD_ENCRYPTION_KEY` is set in production. If accidentally unset, PHI stored in plaintext — a HIPAA violation.
- **Note:** `main.py:161-165` does check this. Verify this check is actually reached before any endpoint can be served.

### Frontend

**P2-C6. PHI Cached Plaintext in AsyncStorage (Mobile)**
- **Files:** `utils/offlineCache.js:48-60`, `utils/notifications.js:151-183`
- Medication reminders (drug names, dosing) and all cached API responses (benefits, ID card, drug costs) stored in AsyncStorage as plaintext JSON. Readable on rooted/jailbroken devices.
- **Fix:** Use `expo-secure-store` for sensitive items or encrypt before writing.

**P2-C7. No Logout / Session Termination / Cache Clearing in Mobile App**
- **Files:** `constants/session.js`, `constants/api.js`, `utils/offlineCache.js`
- `clearMemberSession()`, `clearTokens()`, and `clearAllCache()` functions exist but are **never called** from any screen. No logout button. JWT tokens and PHI persist indefinitely.
- **Fix:** Add logout button that calls all three clearing functions.

**P2-C8. Sentry DSN Hardcoded in Mobile App Source**
- **File:** `app/_layout.js:20`
- Sentry DSN hardcoded as fallback. Attacker can flood the Sentry project with fake errors, exhaust quota, and obscure real incidents.
- **Fix:** Only load from environment variables, no inline fallback.

---

## High Findings (P1)

### Backend

**P2-H1. Session Created Before OTP Verification**
- **File:** `backend/app/main.py:802-806`
- `create_session(req.phone, session_member)` called during `/auth/lookup` before OTP is verified. PHI (name, plan, medications, zip) materialized in SQLite before authentication completes.
- **Fix:** Defer session creation to `/auth/verify-otp`.

**P2-H2. Hardcoded HMAC Fallback Key for Audit Actor Hashing**
- **File:** `backend/app/audit.py:35`
- `"audit-actor-default-key"` is publicly visible. If `AUDIT_HMAC_KEY` not set in production, attacker can reverse actor pseudonyms by brute-forcing 10-digit phone space.
- **Fix:** Require `AUDIT_HMAC_KEY` in production/staging like other secrets.

**P2-H3. GET Endpoint `plan_number` Params Lack Regex Validation**
- **Files:** `backend/app/main.py:1486,1562,1582,1589,1596,1603,1610,1617,1624,1641,2281`
- POST models properly validate plan_number format, but all GET endpoints accept raw `str`. Arbitrary strings passed to database queries and external APIs.
- **Fix:** Add `Path(pattern=r"^[A-Za-z]\d{4}-\d{3}(-\d{3})?$")` to all `plan_number` path parameters.

**P2-H4. `UpdateAdminRequest` Missing Role Validation**
- **File:** `backend/app/admin_router.py:131-143`
- `role` accepts any string (no pattern constraint). Compare `CreateAdminRequest` which properly constrains to `^(super_admin|admin|viewer)$`.
- **Fix:** Add the same pattern to `UpdateAdminRequest.role`.

**P2-H5. PHI Returned in `create_member` Response**
- **File:** `backend/app/admin_router.py:363-368`
- Full `member_data` dict (including `medicare_number`, `phone`) returned in cleartext response body.
- **Fix:** Return only confirmation with masked identifiers.

**P2-H6. No Audit Logging on PHI-Mutating Reminder/Usage Endpoints**
- **Files:** `backend/app/main.py:2044-2154`
- Reminder CRUD and usage tracking endpoints modify health data with zero audit logging. HIPAA requires audit trail for all PHI mutations.
- **Fix:** Add `get_audit_log().record()` to all reminder and usage mutation endpoints.

**P2-H7. `BulkReminderCreate` Has No Array Size Limit**
- **File:** `backend/app/main.py:634-636`
- `reminders` list has no max length. Attacker can submit thousands in one request.
- **Fix:** Add `field_validator` to cap at 50.

**P2-H8. `ReminderCreate.drug_name` and `dose_label` Have No Length Limits**
- **File:** `backend/app/main.py:617-624`
- No `max_length` on `drug_name`, `dose_label`, or `UsageCreate.description`. DoS via database bloat.
- **Fix:** Add `max_length=200`.

**P2-H9. PHI Sent Unscrubbed to Anthropic Claude API**
- **File:** `backend/app/claude_client.py:254-262`
- Member's raw free-text question sent to Anthropic without PHI redaction. Members may include Medicare numbers, DOB, names.
- **Fix:** Strip PHI patterns (Medicare IDs, SSNs, DOBs, phone numbers) before sending to third-party API.

### Frontend

**P2-H10. Admin Tokens Stored in sessionStorage (XSS-Exfiltrable)**
- **Files:** `admin/src/api/client.ts:11,22`, `admin/src/auth/AdminAuthProvider.tsx:21,27`
- Any XSS can read `sessionStorage.getItem('admin_token')` and exfiltrate admin credentials.
- **Fix:** Use httpOnly cookies set by backend.

**P2-H11. No Certificate Pinning on Mobile API Calls**
- **Files:** `constants/api.js` (all `fetch` calls)
- Standard `fetch()` with no SSL pinning. MITM possible on shared WiFi (clinic/hospital).
- **Fix:** Consider `expo-ssl-pinning`.

**P2-H12. Admin Panel Clickjacking — Missing frame-ancestors in HTML**
- **File:** `admin/index.html`
- Backend sets `X-Frame-Options: DENY` and CSP `frame-ancestors 'none'` but only on API responses. Static HTML served via SPA catch-all may not get these headers.
- **Fix:** Verify security headers middleware covers `/admin/*` routes.

**P2-H13. Stale Closure Race in Reminder Toggle**
- **File:** `app/home.js:194-221`
- `handleToggleReminder` captures `reminders` from stale closure. Rapid toggling corrupts state.
- **Fix:** Use functional `setReminders(prev => ...)`.

**P2-H14. Dead OTP Code in `auth.py` — Confusion Risk**
- **File:** `backend/app/auth.py:21-104`
- Complete in-memory OTP implementation alongside persistent store. If accidentally used, OTPs lost on restart and rate limiting bypassed.
- **Fix:** Remove dead code or clearly mark as deprecated.

**P2-H15. `create_member` Never Persists Member Data**
- **File:** `backend/app/admin_router.py:307-368`
- Builds `member_data`, returns it, but never saves to any database. Data silently lost.
- **Fix:** Persist via appropriate store.

---

## Medium Findings (P2)

| # | File | Issue |
|---|------|-------|
| M1 | `main.py:829` | `/auth/lookup` returns first name to unauthenticated callers (social engineering aid) |
| M2 | `admin_router.py:173` | Admin lockout is per-email only, not per-IP. Successful login clears counter. |
| M3 | `admin_router.py:270` | No token revocation on admin deactivation — 8-hour window of continued access |
| M4 | `persistent_store.py:304` | `used_refresh_tokens` table grows unboundedly between cleanups |
| M5 | `admin_router.py:49` | CSRF protection disabled in staging (may have real PHI for QA) |
| M6 | `auth.py:29` | OTP hash uses unsalted SHA-256 — 6-digit codes reversible from DB in milliseconds |
| M7 | `zoho_client.py:60` | Full Zoho token error response (may contain credentials) in exception message |
| M8 | `rtpbc_service.py:142`, `aetna.py:77`, `uhc.py:82` | Raw token error responses logged (up to 500 chars, may contain secrets) |
| M9 | `aetna.py:248`, `rtpbc_service.py:630` | SSRF via FHIR reference URLs — no domain validation before following |
| M10 | `rtpbc_service.py:744` | Unbounded concurrent RTPBC batch requests (no semaphore) |
| M11 | `main.py:592` | `PharmacySearchRequest.plan_number` has weak validation (no regex pattern) |
| M12 | `main.py:623,642` | `last_refill_date`, `usage_date` accept any string (no date format validation) |
| M13 | `main.py:643` | `benefit_period` accepts any string (should be `Monthly|Quarterly|Yearly`) |
| M14 | `main.py:636` | `created_by` in `BulkReminderCreate` is user-controlled (mass assignment) |
| M15 | `app/home.js` + 8 files | 30+ `console.log` calls active in production may leak PHI |
| M16 | `app/_layout.js:26` | Mobile Sentry scrubbing only strips phone from breadcrumbs, not names/Medicare IDs |
| M17 | `components/SOBModal.js:20` | SOB PDF opened via `Linking.openURL` without JWT — unauthenticated download or broken auth |
| M18 | `admin/src/pages/members/*.tsx` | Mock data contains realistic PII (names, phones, DOBs) — compliance audit risk |

---

## Low Findings (P3)

| # | File | Issue |
|---|------|-------|
| L1 | `main.py:249` | PHI audit middleware silently swallows failures (`pass`) — should at minimum `log.error()` |
| L2 | `persistent_store.py:230` | Phone number stored as plaintext in sessions table (data column encrypted, phone not) |
| L3 | `admin_auth.py:148` | `bootstrap_super_admin` returns existing user without password verification |
| L4 | `admin_router.py:411` | `analytics/logins` `days` param has no upper bound (DoS via expensive query) |
| L5 | `admin/src/config/api.ts:1` | Admin `API_BASE` defaults to empty string if env var missing |
| L6 | Mobile app | No idle timeout / auto-lock — PHI accessible indefinitely on unlocked device |
| L7 | `app/doctor-results.js:14` | Deep link `specialty` param passed to API without validation |

---

## Priority Remediation Order

### Immediate (before production)
1. **P2-C1/C2** — Add rate limiting to `/auth/lookup` and `/auth/verify-otp` (5-minute fix)
2. **P2-C7** — Add logout button + cache clearing to mobile app
3. **P2-C6** — Encrypt cached PHI in AsyncStorage
4. **P2-C3** — Add plan authorization to CMS/SOB endpoints (or accept as design decision if plan data is considered semi-public)
5. **P2-C4** — Path validation on admin plans endpoint
6. **P2-H1** — Defer session creation to post-OTP
7. **P2-H6** — Add audit logging to reminder/usage mutations
8. **P2-H3** — Add regex validation to GET endpoint plan_number params
9. **P2-H7/H8** — Add input length bounds

### Short-term (first sprint)
10. **P2-H2** — Require AUDIT_HMAC_KEY in production
11. **P2-H9** — PHI scrubbing before Claude API calls
12. **P2-H14** — Remove dead OTP code in auth.py
13. **P2-M6** — Salt OTP hashes
14. **P2-M7/M8** — Sanitize credential-related error logs

### Medium-term
15. **P2-H10** — Move admin tokens to httpOnly cookies
16. **P2-H11** — Certificate pinning for mobile
17. **P2-M15** — Gate console.log behind `__DEV__`
18. **P2-M10** — Add semaphore to RTPBC batch

---

## What's Working Well (Positive Observations)

- CSP headers properly configured on all API responses
- Sentry PII scrubbing on backend is thorough (phone + Medicare patterns)
- JWT tokens don't contain PHI (only phone as subject)
- Session PHI minimization (no Medicare number in sessions)
- Field encryption at rest for PHI in persistent store
- CORS properly scoped (no wildcards in production)
- Refresh token rotation with JTI single-use enforcement
- Rate limiting on public quote endpoints
- Zoho query injection prevention (digits-only validation)
- Graceful shutdown with 30s timeout
- Multi-worker uvicorn deployment
- Thread-safe caches with locks
- Retry-capable HTTP sessions on all external APIs
- Geocoding cache reducing redundant API calls
- Concurrency semaphore preventing thundering herd
