# Security Audit Report — INY Concierge

**Date:** 2026-03-14
**Scope:** Full codebase sweep (backend, frontend, admin, infrastructure, dependencies)
**Method:** 10 parallel agents, each area reviewed twice from different angles
**Branch:** `claude/security-sweep-E8Skv`

---

## Executive Summary

10 agents swept the entire codebase front-to-back, twice. After deduplication, **47 unique findings** were identified across all severity levels. The codebase demonstrates strong foundational security (parameterized SQL, field-level encryption, audit logging, token rotation), but has several critical gaps that need immediate attention.

| Severity | Count |
|----------|-------|
| Critical | 7 |
| High | 14 |
| Medium | 16 |
| Low | 10 |

---

## CRITICAL — Fix Immediately

### C1. Hardcoded OTP Bypass `'123456'`
- **File:** `app/otp.js:138`
- **Issue:** `const isDev = code === '123456'` bypasses authentication with no `__DEV__` guard. Anyone can log into any account in production.
- **Fix:** Remove entirely. Use separate test/staging builds for dev access.

### C2. Development Mode Disables All Authentication
- **File:** `backend/app/main.py:527-528`
- **Issue:** `if APP_ENV == "development": return {"sub": "dev", "type": "access"}` — complete auth bypass. If production accidentally runs with `APP_ENV=development`, all PHI is exposed.
- **Fix:** Add startup guard preventing dev mode outside localhost. Never trust `APP_ENV` alone for security decisions.

### C3. `FIELD_ENCRYPTION_KEY` Missing Startup Validation
- **File:** `backend/app/config.py`
- **Issue:** `JWT_SECRET` and `ADMIN_SECRET` raise `RuntimeError` in production if unset, but `FIELD_ENCRYPTION_KEY` does not. If unset, PHI (medications, Medicare numbers) is stored unencrypted — HIPAA violation.
- **Fix:** Add `if APP_ENV in ("production", "staging") and not FIELD_ENCRYPTION_KEY: raise RuntimeError(...)` at startup.

### C4. Unvalidated JSON Input on Health Endpoints
- **File:** `backend/app/main.py:2896-2908`
- **Issue:** `/health-screenings` accepts `await request.json()` with no Pydantic model validation. Arbitrary JSON stored directly — mass assignment vulnerability.
- **Fix:** Define `HealthScreeningRequest(BaseModel)` with expected fields. Same for `/sdoh-screening`.

### C5. Missing CSRF Protection on Mobile POST/DELETE Endpoints
- **File:** `backend/app/main.py` (multiple endpoints)
- **Issue:** Admin endpoints have CSRF (origin/referer validation), but mobile state-changing endpoints do not: `POST /reminders`, `DELETE /reminders`, `POST /usage`, `POST /adherence`, `POST /health-screenings`, `POST /sdoh-screening`, `POST /appointment-request`.
- **Fix:** Require custom header (e.g., `X-Requested-With`) for all state-changing mobile requests.

### C6. Admin Static Secret Fallback (`X-Admin-Secret`)
- **File:** `backend/app/admin_router.py:696-699`
- **Issue:** Upload endpoint accepts `X-Admin-Secret` header as alternative to JWT. Shared credential with no per-user audit trail.
- **Fix:** Remove static secret auth. Require JWT for all admin operations. Use service accounts for CLI.

### C7. Infinite Loop in Admin Dialog Handler
- **File:** `admin/src/pages/members/MemberDetailPage.tsx:103`
- **Issue:** `handleOpenPlanDialog()` calls itself recursively → app crash.
- **Fix:** Replace recursive call with `setPlanDialogOpen(true)`.

---

## HIGH — Fix This Week

### H1. XOR Cipher for Cache Encryption
- **File:** `utils/secureCache.js:53-67`
- **Issue:** XOR is not cryptographically secure. Key generated with `Math.random()` (not CSPRNG). PHI cached with broken encryption.
- **Fix:** Replace with AES-256-GCM via `expo-crypto` or `tweetnacl`. Use `crypto.getRandomValues()` for key generation.

### H2. IDOR on Plan Endpoints
- **Files:** `backend/app/main.py` — 13+ endpoints accept `plan_number`
- **Issue:** Any authenticated user can query any plan's benefits, drug formulary, SOB PDF, and ID card (Rx BIN/PCN/Group) by guessing plan numbers.
- **Fix:** Verify authenticated user's session plan matches requested `plan_number` before returning data.

### H3. No Rate Limiting on Several Sensitive Endpoints
- **Files:** `backend/app/main.py`, `admin_router.py`
- **Issue:** Missing rate limits on: `POST /appointment-request`, `POST /members/create`, `POST /members/send-otp`, `POST /health-screenings`. Enables spam/DoS.
- **Fix:** Add `_check_ip_rate()` to all state-changing endpoints.

### H4. Token Refresh Race Condition
- **File:** `constants/api.js:113-126`
- **Issue:** Multiple concurrent 401s trigger parallel `_tryRefresh()` calls. Token mismatch possible.
- **Fix:** Use Promise-based lock:
  ```js
  let _refreshing = null;
  async function _tryRefresh() {
    if (_refreshing) return _refreshing;
    _refreshing = (async () => { /* ... */ })().finally(() => _refreshing = null);
    return _refreshing;
  }
  ```

### H5. Memory Leak in VoiceHelp Speech Detection
- **File:** `components/VoiceHelp.js:836-842`
- **Issue:** `setInterval` async callback can update state after unmount.
- **Fix:** Add `let mounted = true` ref, check before `setIsSpeaking(false)`, set `mounted = false` in cleanup.

### H6. Sensitive Data in Error Messages
- **File:** `app/otp.js:157-158`
- **Issue:** Error message exposes full API URL to user: `` `Can't reach server (${err.message}). URL: ${url}` ``
- **Fix:** Show generic message. Log details to Sentry only.

### H7. Unmasked PII in Admin Member Lists
- **File:** `admin/src/pages/members/MembersPage.tsx:278`
- **Issue:** Full phone numbers displayed in list view. No role-based masking. HIPAA concern.
- **Fix:** Mask to `***-***-1234`. Only show full in detail view for authorized roles.

### H8. No SSL Certificate Pinning on Mobile
- **File:** `constants/api.js`
- **Issue:** Standard `fetch()` with no cert pinning. MITM possible on shared WiFi (clinic, hospital).
- **Fix:** Implement `expo-ssl-pinning` for production API endpoints.

### H9. Admin Routes Missing Role Checks
- **File:** `admin/src/App.tsx:38-46`
- **Issue:** Dashboard, members, screening pages wrapped in `<ProtectedRoute />` with no `allowedRoles`. Viewers get same access as admins.
- **Fix:** Add explicit `allowedRoles={['super_admin', 'admin']}` for mutation pages.

### H10. Decryption Failure Returns Plaintext
- **File:** `backend/app/encryption.py:82-87`
- **Issue:** On decryption failure, returns ciphertext as-is. Could expose encrypted data in API responses.
- **Fix:** Raise `RuntimeError("Unable to decrypt protected field")` instead.

### H11. PHI Cached in Plaintext on Mobile
- **Files:** `utils/offlineCache.js`, `utils/notifications.js`
- **Issue:** Medication names, dosing, and cached API responses stored in AsyncStorage as plaintext JSON.
- **Fix:** Use `secureSet()` from secureCache for all health data. Clear on logout.

### H12. No Logout Flow in Mobile App
- **Files:** `constants/api.js`, `constants/session.js`
- **Issue:** `clearTokens()`, `clearMemberSession()`, `clearAllCache()` exist but are never called from UI. Tokens/PHI persist indefinitely.
- **Fix:** Add logout button that calls all clearing functions.

### H13. Admin Password Can Be Reset Without Current Password
- **File:** `backend/app/admin_auth.py:183-199`
- **Issue:** `bootstrap_super_admin()` silently resets existing admin passwords with no audit trail.
- **Fix:** Log password changes to audit. Require current password for HTTP-based changes.

### H14. `gdown` Dependency Unmaintained
- **File:** `backend/requirements.txt`
- **Issue:** `gdown==5.2.0` — no longer maintained as of late 2024. No security patches available.
- **Fix:** Replace with `google-api-python-client` (already in requirements).

---

## MEDIUM — Fix This Sprint

### M1. CORS Too Permissive in Dev/Staging
- **File:** `backend/app/main.py:207-215, 354-360`
- **Issue:** Dev allows `10.x.x.x` and `192.168.x.x` origins. Widget uses `Access-Control-Allow-Origin: *` in non-prod.
- **Fix:** Restrict to `localhost` only in dev. No wildcard CORS in any environment.

### M2. Session Ownership Bypass in Dev
- **File:** `backend/app/main.py:494-507`
- **Issue:** `user.get("sub") not in (None, "dev")` allows dev mode to bypass session ownership validation.
- **Fix:** Validate ownership for all non-dev tokens. Don't skip checks.

### M3. Weak Input Validation on Admin Forms
- **Files:** `admin/src/pages/members/MembersPage.tsx`, `MemberDetailPage.tsx`
- **Issue:** Phone, Medicare number, plan number fields have minimal validation (only `maxLength`).
- **Fix:** Add regex patterns for all fields. Validate on both client and server.

### M4. Error Messages Leak Internal Details
- **Files:** `backend/app/main.py:772, 779, 1544-1546`
- **Issue:** Health endpoint returns exception type names. Plan errors expose plan IDs.
- **Fix:** Generic messages in production. Detailed messages only in dev.

### M5. Unsalted OTP Hash
- **File:** `backend/app/persistent_store.py:115-117`
- **Issue:** OTP hash uses unsalted SHA-256. With 1M possible 6-digit codes, precomputation is trivial.
- **Fix:** Use bcrypt or PBKDF2 with per-OTP salt.

### M6. PHI Sent to Anthropic API Without Redaction
- **File:** `backend/app/claude_client.py:254-262`
- **Issue:** Member free-text questions sent to Claude API without PHI scrubbing. Users may include Medicare numbers, SSNs, DOBs.
- **Fix:** Strip PHI patterns before sending to third-party APIs.

### M7. Session Created Before OTP Verification
- **File:** `backend/app/main.py:802-806`
- **Issue:** `create_session()` called in `/auth/lookup` before OTP verified. PHI materialized before authentication completes.
- **Fix:** Defer session creation to `/auth/verify-otp`.

### M8. No Session Timeout in Admin Panel
- **File:** `admin/src/auth/AdminAuthProvider.tsx`
- **Issue:** No idle session timeout. Admin can leave browser unattended indefinitely.
- **Fix:** Implement idle timeout (15-30 min) with warning dialog.

### M9. Console Error Logging in Production
- **Files:** `admin/src/components/ErrorBoundary.tsx:24`, `app/digital-id.js:59`
- **Issue:** Stack traces logged to browser console without `__DEV__` guard.
- **Fix:** Gate behind environment check or send to Sentry only.

### M10. Phone Number Enumeration via Error Responses
- **Files:** `backend/app/admin_router.py:407-439`, `main.py:911-980`
- **Issue:** Different error responses for found vs not-found phones enables enumeration.
- **Fix:** Return identical response regardless of phone existence. Use timing-safe responses.

### M11. Hardcoded AUDIT_HMAC_KEY Fallback
- **File:** `backend/app/audit.py:45`
- **Issue:** Defaults to `"audit-actor-dev-key-not-for-production"`. Predictable key allows reversing actor pseudonyms.
- **Fix:** Generate random key per startup in dev: `secrets.token_urlsafe(32)`.

### M12. No Max Length on Text Fields
- **File:** `backend/app/main.py:617-624`
- **Issue:** `drug_name`, `dose_label`, `description` have no `max_length`. Attacker can submit 1MB strings.
- **Fix:** Add `max_length=200` to all user input text fields.

### M13. No Array Size Limit on Bulk Reminders
- **File:** `backend/app/main.py:634-636`
- **Issue:** `BulkReminderCreate.reminders` has no max length. Database bloat DoS vector.
- **Fix:** Add `@field_validator("reminders")` with `max_length=50`.

### M14. Database File Permissions World-Readable
- **Files:** `backend/*.db`
- **Issue:** Databases at `0644` (rw-r--r--). Any local user can read encrypted PHI.
- **Fix:** Set permissions to `0600` on all `.db` files.

### M15. Health Endpoint Information Disclosure
- **File:** `backend/app/main.py:762-802`
- **Issue:** `/health` (unauthenticated) exposes active session count, API key presence, plan counts.
- **Fix:** Return only `{"status": "ok"}` for unauthenticated checks. Detailed info behind auth.

### M16. Exact Dependency Pinning Blocks Security Patches
- **File:** `backend/requirements.txt`
- **Issue:** All packages pinned with `==`. Prevents automatic security patches for `pydantic`, `PyJWT`, `SQLAlchemy`, `cryptography`, etc.
- **Fix:** Use `>=X.Y.Z,<X+1.0.0` for most packages. Keep exact pin only for `cryptography`.

---

## LOW — Fix When Convenient

| # | Issue | File | Fix |
|---|-------|------|-----|
| L1 | Dynamic `require()` in lock.js | `app/lock.js:103` | Move to top-level import |
| L2 | Sentry DSN hardcoded as fallback | `app/_layout.js:20` | Load from env var only |
| L3 | Admin token revocation in-memory only | `backend/app/admin_auth.py:59-71` | Persist to database |
| L4 | WAL mode setup swallows errors | `backend/app/persistent_store.py:46-49` | Log and verify WAL enabled |
| L5 | Missing CSP report-uri | `backend/app/main.py:236-244` | Add violation reporting endpoint |
| L6 | Hardcoded call center number | `constants/data.js:6` | Fetch from backend config |
| L7 | No `.nvmrc` file | Project root | Create with `20.10.0` |
| L8 | GitHub Actions not pinned to patch | `.github/workflows/ci.yml` | Pin `actions/checkout@v4.1.0` etc. |
| L9 | `@modelcontextprotocol/sdk` in prod deps | `package.json` | Move to `devDependencies` |
| L10 | Render disk only 1GB | `render.yaml:26` | Increase to 10GB for healthcare app |

---

## Positive Security Findings

The codebase has strong security foundations in many areas:

- **SQL Injection:** All queries use parameterized `?` placeholders throughout
- **Password Hashing:** bcrypt with salt for admin passwords
- **PHI Encryption:** Fernet (AES-128-CBC + HMAC) field-level encryption at rest
- **JWT Security:** Separate secrets for mobile/admin, token expiration, refresh rotation with JTI tracking
- **Audit Logging:** Comprehensive trail with PII masking via HMAC pseudonymization
- **Path Traversal:** `os.path.realpath()` checks on file-serving endpoints
- **Tar Extraction:** Symlink rejection and zip-slip prevention
- **Admin CSRF:** Origin/Referer validation on all admin mutations
- **Secure Cookies:** HttpOnly, Secure, SameSite=Lax on admin tokens
- **PII Scrubbing:** Sentry before-send hook strips phone numbers and Medicare IDs
- **Rate Limiting:** IP-based throttling on auth endpoints
- **Admin Brute Force:** 5-attempt lockout on admin login
- **Debug Endpoints:** Properly gated to development environment only
- **OpenAPI Docs:** Disabled in production

---

## Recommended Priority Order

### Phase 1 — Immediate (Today)
1. Remove hardcoded OTP `'123456'` (C1)
2. Add `FIELD_ENCRYPTION_KEY` startup validation (C3)
3. Fix infinite loop in admin dialog (C7)
4. Add Pydantic validation to health screening endpoints (C4)

### Phase 2 — This Week
5. Add CSRF headers to mobile endpoints (C5)
6. Remove `X-Admin-Secret` fallback (C6)
7. Fix IDOR on plan endpoints (H2)
8. Replace XOR cipher with AES (H1)
9. Add rate limiting to unprotected endpoints (H3)
10. Fix token refresh race condition (H4)

### Phase 3 — This Sprint
11. Add role checks to admin routes (H9)
12. Mask PII in admin lists (H7)
13. Add mobile logout flow (H12)
14. Fix error message information leaks (H6, M4)
15. Add SSL certificate pinning (H8)
16. Strip PHI before Anthropic API calls (M6)

### Phase 4 — Next Sprint
17. Dependency version strategy (M16)
18. Replace `gdown` (H14)
19. Session timeout for admin (M8)
20. Phone enumeration fixes (M10)
21. Input validation improvements (M3, M12, M13)
