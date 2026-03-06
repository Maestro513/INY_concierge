# INY Concierge - Comprehensive Code Review Report

**Date:** March 6, 2026
**Scope:** Every file on `main` branch, reviewed twice (Pass 1 + Pass 2)
**Files Reviewed:** 120+ files across backend, mobile app, admin panel, tests, and infrastructure

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Critical Findings (P0)](#critical-findings-p0)
3. [High-Severity Findings (P1)](#high-severity-findings-p1)
4. [Medium-Severity Findings (P2)](#medium-severity-findings-p2)
5. [Low-Severity Findings (P3)](#low-severity-findings-p3)
6. [Architecture & Production Readiness](#architecture--production-readiness)
7. [Positive Observations](#positive-observations)
8. [Recommended Priority Order](#recommended-priority-order)

---

## Executive Summary

This is a **Medicare member concierge application** consisting of:
- **FastAPI backend** (~5,000 lines Python) handling PHI, OTP auth, CMS data, AI Q&A
- **React Native / Expo mobile app** (~5,100 lines JS) for Medicare members
- **React admin panel** (~3,500 lines TypeScript) for member management
- **Provider search module** (~2,750 lines Python) with carrier FHIR adapters
- **Supporting infrastructure** (CI/CD, Alembic migrations, import scripts, tests)

### Overall Assessment

The codebase has **strong visual design**, **excellent accessibility**, and **thoughtful architecture** in many areas, but has **significant security and HIPAA compliance gaps** that must be resolved before production use with real patient data. The admin panel is a **polished visual prototype** with fake data operations. The provider search module has **critical data loss bugs** and extreme performance bottlenecks.

### Summary by Severity

| Severity | Count | Description |
|----------|-------|-------------|
| **CRITICAL (P0)** | 18 | Security vulnerabilities, HIPAA violations, data loss, runtime crashes |
| **HIGH (P1)** | 22 | PHI exposure, missing authorization, broken features, compliance gaps |
| **MEDIUM (P2)** | 30+ | Performance issues, logic bugs, code quality, UX problems |
| **LOW (P3)** | 25+ | Style issues, minor inefficiencies, cosmetic bugs |

---

## Critical Findings (P0)

### Security Vulnerabilities

**C1. Path Traversal - Arbitrary File Read**
- **File:** `backend/app/main.py:160-167`
- The admin SPA route joins user input directly into a file path. An attacker can request `/admin/../../etc/passwd` to read any file on the server.
- **Fix:** Validate the resolved path stays within the static directory using `os.path.realpath()`.

**C2. SQL Injection via CSV Headers**
- **File:** `backend/cms_import.py:135`
- Column names from external CSV files pass through a weak `sanitize_col()` and are interpolated into `CREATE TABLE` SQL via f-string. A crafted CSV header executes arbitrary SQL.
- **Fix:** Whitelist allowed column names or use parameterized DDL.

**C3. Path Traversal in Google Drive Sync**
- **File:** `backend/app/gdrive_sync.py:129,151`
- Filenames from Google Drive API used directly in `os.path.join()` without sanitization.
- **Fix:** `name = os.path.basename(name)`.

**C4. Tar Extraction Zip-Slip Vulnerability**
- **File:** `backend/app/admin_router.py:522-528`
- Tar file extraction does not protect against symlink attacks. A malicious archive can write files anywhere on disk.
- **Fix:** Validate all extracted paths remain within the target directory.

**C5. XSS in Quote Widget**
- **File:** `backend/static/quote-widget.js:~477`
- API error messages from `errData.detail` are rendered via `innerHTML` without sanitization. The `esc()` helper exists but is not applied to error output.
- **Fix:** Apply `esc()` to all dynamic content rendered via innerHTML.

### HIPAA Violations

**C6. Field Encryption Imported but Never Wired In - All PHI Plaintext at Rest**
- **Files:** `backend/app/main.py:48`, `backend/app/persistent_store.py:184`
- `get_cipher` is imported but **never called** anywhere. Zero calls to `cipher.encrypt()` or `cipher.decrypt()` exist. Medicare numbers, medications, phone numbers, and all PHI in all SQLite databases are stored in plaintext.
- **Fix:** Wire encryption into data storage paths; make it a hard failure if encryption key is missing in production.

**C7. OTP Store Split-Brain: Admin and Mobile Use Different Stores**
- **Files:** `backend/app/admin_router.py:30`, `backend/app/main.py:638`
- Admin panel imports `generate_otp` from `auth.py` (in-memory dict). Mobile uses `get_store().generate_otp()` (persistent SQLite). OTPs generated via admin never verify through mobile. Rate limiting is also split, doubling the effective OTP attempt budget.
- **Fix:** Use a single OTP store (the persistent one) for all flows.

### Data Loss & Runtime Crashes

**C8. Provider Enrichment Drops 185 of 200 Results**
- **File:** `backend/app/providers/service.py:182-189`
- `enrich_providers()` only processes the first 15 providers. All providers beyond index 15 are permanently discarded from search results.
- **Fix:** Append un-enriched providers back to the result list.

**C9. `usage_summary` Endpoint Crashes on Every Call**
- **File:** `backend/app/main.py:2043-2098`
- `_split_plan()` returns a 2-tuple, unpacked with `*` into CMS methods that accept a single string. Raises `TypeError` on every call. Additionally, response key names are wrong (`"has_exams"` vs `"has_eye_exam"`, `"max_amount"` vs `"amount"`), so 3 of 5 benefit categories silently return empty even if the crash were fixed.
- **Fix:** Pass `plan_number` directly; fix all key names to match CMS lookup return values.

**C10. Out-of-Network Pharmacies Falsely Marked In-Network**
- **File:** `backend/app/pharmacy_service.py:262`
- When a pharmacy's zip code is NOT in the CMS network data, `in_network = True` is set anyway. Members could visit out-of-network pharmacies and face unexpected costs.
- **Fix:** Set `in_network = False` or `None` when zip is not in network data.

**C11. Deductible Remaining Calculation Is Wrong**
- **File:** `backend/app/drug_cost_engine.py:265`
- Remaining deductible computed as `drug_deductible - ytd_total`, but `ytd_total` includes post-deductible copays. This understates remaining deductible shown to members.
- **Fix:** Track deductible-applicable spend separately from total spend.

### Authentication & Authorization

**C12. Empty JWT_SECRET Is a Valid Signing Key**
- **File:** `backend/app/config.py:44`
- `JWT_SECRET` defaults to `""`. Anyone who knows the secret is empty can forge tokens.
- **Fix:** Generate a random key at startup in non-production; require explicit setting in production.

**C13. Auth Bypass in Development Mode**
- **File:** `backend/app/main.py:303-304`
- When `APP_ENV == "development"`, all authenticated endpoints return a hardcoded user with no token check. A misconfigured env var in production exposes everything.
- **Fix:** Use a more robust guard; never default to development mode.

**C14. DEV Auth Bypass in Admin Panel**
- **File:** `admin/src/auth/ProtectedRoute.tsx:8-11`
- `if (import.meta.env.DEV) return <Outlet />` completely disables authentication in development and could leak into production with misconfigured builds.
- **Fix:** Remove or gate behind an explicit flag.

**C15. No JWT Token Revocation Mechanism**
- **Files:** `backend/app/auth.py`, `backend/app/admin_auth.py`
- No token blacklist or revocation exists. No logout endpoint on backend. Deactivating an admin account doesn't invalidate their existing access token (valid 8 hours). Mobile refresh tokens valid 30 days with no revocation path.
- **Fix:** Implement token blacklisting or short-lived tokens with server-side session validation.

**C16. Hardcoded Test Credentials Active in All Environments**
- **File:** `backend/.env.example:30-34`
- `TEST_PHONE=5555550100` and `TEST_OTP=123456` documented as working "in ANY environment."
- **Fix:** Disable test credentials in production; gate behind `APP_ENV == "development"`.

**C17. Zoho CRM Query Injection**
- **File:** `backend/app/zoho_client.py:74`
- Phone number interpolated directly into COQL search criteria. Input like `5551234567)or(Email:starts_with:a` could return other contacts' data.
- **Fix:** Validate input is digits-only before interpolation.

**C18. Admin Password Exposed in Shell History**
- **File:** `backend/create_admin.py:22`
- Admin password is a positional CLI argument visible in `ps`, shell history, and CI logs.
- **Fix:** Use `getpass.getpass()` or environment variable.

---

## High-Severity Findings (P1)

### PHI Exposure

**H1. PHI Stored in JWT Tokens**
- **File:** `backend/app/auth.py:118-126`
- Access tokens contain `first_name`, `last_name`, `plan_name`, `plan_number`. JWTs are base64-encoded, not encrypted.

**H2. PHI in Expo Router URL Parameters**
- **Files:** `app/otp.js:71-82`, `app/home.js:21`, `app/digital-id.js`
- Medicare numbers, plan numbers, session IDs passed as URL query params. Visible in logs, deep links, Sentry breadcrumbs.

**H3. Medicare Number Returned Unnecessarily at Login**
- **File:** `backend/app/main.py:723`
- Medicare number included in `/auth/verify-otp` response, broadcast through every navigation event. Should be fetched on-demand for the ID card screen only.

**H4. JWT Tokens in Unencrypted AsyncStorage**
- **File:** `constants/api.js:29-37`
- Tokens (containing PHI) stored via AsyncStorage (unencrypted SQLite on Android, plist on iOS). Should use `expo-secure-store`.

**H5. Phone Number in URL Path**
- **File:** `backend/app/main.py:1551`
- `/cms/my-drugs/{phone}` puts raw 10-digit phone in URL, captured by CDN/proxy logs. Session-based alternative already exists.

**H6. Sentry PII Scrubbing Is Incomplete**
- **File:** `backend/app/main.py:58-66`
- Only scrubs `logentry.message`. Misses exception traces, breadcrumbs, request URLs/bodies, and extra context. Phone regex misses formatted numbers.

### Missing Authorization

**H7. No Cross-User Authorization on Session Endpoints**
- **File:** `backend/app/main.py:1906+`
- Endpoints authenticate via JWT but resolve data via separate `session_id`. No check that authenticated user owns that session. A guessed session ID grants access to another user's PHI.

**H8. Unauthenticated `/metrics` Endpoint**
- **File:** `backend/app/main.py:584`
- Exposes request counts, error rates, active session counts to anyone.

**H9. SOB PDF Endpoint Serves Files Without Authentication**
- **File:** `backend/app/main.py:1291-1303`
- `/sob/pdf/{plan_number}` has no `get_current_user` dependency. Unauthenticated users can enumerate and download SOB PDFs.

**H10. No Admin Login Brute-Force Protection**
- **File:** `backend/app/admin_auth.py:117`
- Unlimited password attempts. Failed logins recorded but never checked for lockout.

**H11. Failed Admin Login Attempts Never Recorded**
- **File:** `backend/app/admin_router.py:83-90`
- `record_login_event()` called only after successful auth. Failed attempts generate no audit trail.

### Audit & Compliance

**H12. Audit Logging Covers Only Auth - Most PHI Access Unaudited**
- **File:** `backend/app/main.py`
- `get_audit_log().record()` called at only 4 points (all auth-related). No audit trail for: medication data, reminders, benefits usage, SOB summaries, CMS lookups, ID card data, or any admin data access.

**H13. Audit Logs Mask Actor Identity**
- **File:** `backend/app/audit.py:102`
- Phone numbers masked to last-4-digits before storage. Not unique, making it impossible to reliably identify who accessed what.

**H14. SQLite Database Files Have Default Permissions**
- **Files:** `persistent_store.py`, `user_data.py`, `audit.py`, `admin_db.py`
- Four databases containing PHI created with 0644 permissions. Any server user can read them.

### Broken Features

**H15. All Admin Save/Create/Send Operations Are Fake**
- **Files:** `admin/src/pages/members/*.tsx`
- `setTimeout` simulates success without persisting. UI misleads users into thinking actions succeeded.

**H16. Admin Sign Out Button Does Nothing**
- **File:** `admin/src/layout/Sidebar.tsx:63`
- No `onClick` handler, no call to `logout()`.

**H17. MemberDetailPage Ignores URL Params**
- **File:** `admin/src/pages/members/MemberDetailPage.tsx:67-71`
- `useParams()` captures `id` but always renders `MOCK_DETAIL['1']`. Every member URL shows same person.

### Performance

**H18. OAuth Token Cache Race Conditions**
- **Files:** `backend/app/providers/adapters/aetna.py:41`, `uhc.py:41`, `rtpbc_service.py:56`
- Module-level token dicts with no `asyncio.Lock`. Concurrent requests trigger duplicate fetches.

**H19. Sequential HTTP in Provider Search (~65 seconds worst case)**
- **Files:** `providers/service.py`, `humana.py`, `google_places.py`, `nppes.py`
- Geocoding (200 sequential calls), Humana location scan (100 sequential), Google Places (15 sequential), NPPES (sequential). Could be ~6 seconds with `asyncio.gather`.

**H20. Zoho OAuth Token Never Actually Cached**
- **File:** `backend/app/zoho_client.py:20-36`
- `_access_token` written but never read before making a new token request. Every CRM lookup makes a redundant OAuth round-trip.

**H21. RTPBC Drug Batch Processed Sequentially Despite asyncio Import**
- **File:** `backend/app/rtpbc_service.py:735-760`
- 8 medications = 240 seconds of sequential waiting. `import asyncio` present but `gather()` never used.

**H22. N+1 Query Problem in Plan Search**
- **File:** `backend/app/plan_search.py:166-258`
- 50 plan results = 250+ individual SQL queries. Should use JOINs.

---

## Medium-Severity Findings (P2)

### Backend Logic Bugs

- **M1.** Part B Giveback displays `$$174.70/mo` (doubled dollar sign) - CMS formats with `$`, frontend prepends another
- **M2.** `extract_benefits.py:91` crashes on chunks missing `'section'` key (uses `c['section']` instead of `.get()`)
- **M3.** `_compute_ic_monthly_cost` incorrect for 60/90-day supplies when CMS only has 30-day copay data
- **M4.** Google Geocoding API status not checked - `OVER_QUERY_LIMIT` returns HTTP 200, silently returns None
- **M5.** `nppes.py:117` - `None[:5]` TypeError when NPPES returns null postal_code
- **M6.** Primary care search maps only to General Practice, missing Family Medicine and Internal Medicine
- **M7.** `"\\n"` credential filter bug across all 4 carrier adapters - compares literal `\n` not newline
- **M8.** Catastrophic coverage phase never modeled in drug cost engine - costs overstated for specialty drugs
- **M9.** API key leaked in URL and missing from retry in `plan_search.py:360,377-386`
- **M10.** Circular import risk: `extract_benefits.py` imports from `main.py`
- **M11.** `_repair_json` in `extract_benefits.py` can produce semantically corrupt JSON
- **M12.** `zoho_client.py` uses synchronous `requests`, blocking the async event loop
- **M13.** Anthropic client created per request instead of reusing singleton
- **M14.** HealthSpring adapter has no geographic filtering - fetches 100 results nationwide

### Frontend Bugs

- **M15.** Token refresh race condition - concurrent 401s cause broken auth state with no recovery
- **M16.** No auth failure redirect - user stays on data screens with no data and no indication to re-auth
- **M17.** Unauthenticated SOB PDF download via `Linking.openURL()` - no Authorization header
- **M18.** Stale closure in reminder toggle - `handleToggleReminder` reads stale `reminders`
- **M19.** Wrong `SafeAreaView` import in `digital-id.js` - deprecated RN version instead of safe-area-context
- **M20.** Static dimensions at module level in `digital-id.js` - never updates on rotation
- **M21.** NaN bypasses usage amount validation in `UsageTracker.js`
- **M22.** Voice transcript race condition in `VoiceHelp.js` - final transcript can be lost
- **M23.** `res.json()` before status check in 4 files - crashes on non-JSON error responses
- **M24.** No logout button anywhere in the mobile app

### Infrastructure

- **M25.** Thread-unsafe global metrics `_request_metrics` - non-atomic `+=` from async middleware
- **M26.** Unbounded `_ask_rate` dict - memory leak over months of production
- **M27.** `touch_session` overwrites `created_at` - sessions can be kept alive indefinitely
- **M28.** Single uvicorn worker in production `start.sh` - bottleneck under load
- **M29.** Auth never tested in production mode - conftest.py forces `APP_ENV=development`
- **M30.** No Content-Security-Policy header on admin panel
- **M31.** Inconsistent paths between import scripts (`pdfs/CMS` vs `Pdfs/CMS`)
- **M32.** `persistent_store.db` and `cms_benefits.db` missing from `.gitignore`
- **M33.** `start.sh` does not run `alembic upgrade head` before starting
- **M34.** No admin password complexity validation
- **M35.** Unpinned `anthropic>=0.84.0` dependency - no upper bound

---

## Low-Severity Findings (P3)

### Code Quality
- Dead OTP code in `auth.py` (never called at runtime)
- `MedReminders.js` (405 lines) never imported anywhere
- ~500 lines of duplicated adapter code across 4 carrier adapters
- `VoiceHelp.js` (900 lines) needs decomposition
- `ProfileCard.js` (601 lines) contains 6 sub-components
- Carrier logo detection duplicated in `ProfileCard.js` and `digital-id.js`
- `ZIP_PREFIX_TO_STATE` (200+ lines) hardcoded in `humana.py` but imported by 3 adapters
- `datetime.utcnow()` deprecated in Python 3.12+
- Inconsistent error return types across services
- 3 copies of `normalize_plan_id` with divergent logic
- React Query installed in admin panel but never used
- `h-4.5`/`w-4.5` non-standard Tailwind classes
- Ruff ignores F401 globally instead of per-file
- No coverage tooling configured

### UX Issues
- Unrecoverable error boundary in mobile app (no retry button)
- Medications modal lacks ScrollView for long lists
- Greeting never updates if app stays open
- No pagination on doctor/pharmacy results
- No delete confirmation on reminder removal
- Admin pagination buttons have no onClick handlers
- Admin filter buttons are decorative
- Admin plans table rows show pointer cursor but aren't clickable
- No responsive admin layout below ~1024px
- No 404 page in admin panel

---

## Architecture & Production Readiness

### Critical Architecture Issues

1. **`main.py` is a 1,600+ line monolith** mixing routing, prompts, business logic, caching, and middleware. Should be split into route modules.

2. **SQLite as production database** with no write-retry, no connection pooling, and single-worker deployment. WAL mode helps but doesn't solve concurrent write contention.

3. **Dual schema management** - Alembic migrations exist alongside `CREATE TABLE IF NOT EXISTS` in `persistent_store.py`, `user_data.py`, `admin_db.py`, and `audit.py`. Schema drift is invisible.

4. **No graceful shutdown** - no lifespan handler to close SQLite connections, flush caches, or drain in-flight requests.

5. **Health check is trivially shallow** - no dependency checks for SQLite, CMS data, or external services.

6. **No rate limiting or circuit breaker** on any external API (Google, NPPES, carrier FHIR, Zoho, Claude).

7. **httpx client lifecycle anti-pattern** - nearly every function creates/destroys its own client instead of sharing application-scoped connections.

### Missing for Production

- [ ] HIPAA-compliant PHI encryption at rest
- [ ] Comprehensive audit logging for all PHI access
- [ ] Token revocation / logout mechanism
- [ ] Input validation at all API boundaries
- [ ] Session-to-user ownership verification
- [ ] Admin panel wired to real API (not fake data)
- [ ] Multi-worker deployment configuration
- [ ] Database backup and recovery procedures
- [ ] Error alerting and monitoring beyond Sentry
- [ ] Load testing results
- [ ] Security penetration testing
- [ ] BAA agreements with third-party services (Sentry, Anthropic, Google, Zoho)

---

## Positive Observations

### Backend
- HIPAA audit logging infrastructure exists (needs expansion)
- PII scrubbing in Sentry (needs completion)
- Security headers middleware (HSTS, X-Frame-Options)
- OTP rate limiting with persistent storage
- Clean separation of admin and member auth systems
- Field-level encryption design with migration-friendly `enc:` prefix
- Parameterized SQL throughout (no SQL injection via values)
- Well-crafted Claude system prompt for elderly Medicare audience
- Excellent FHIR resource construction in RTPBC service
- Comprehensive CMS PBP data coverage
- Smart section-aware document chunking with TF-IDF scoring
- IRA insulin cap rules faithfully modeled
- Atomic file downloads in gdrive_sync (write to .tmp, then os.replace)
- Good retry with exponential backoff in Google Drive sync
- Batch inserts in import scripts (10K-50K rows with WAL mode)

### Frontend Mobile
- **Accessibility is consistently excellent** - `accessibilityRole`, `accessibilityLabel`, `accessibilityState`, `accessibilityHint` on nearly every interactive element. Exceptional for the elderly Medicare audience.
- Offline-first architecture with ETag support
- Consistent error/loading/empty states with retry buttons
- Optimistic updates for reminders with automatic revert
- Comprehensive design system in `theme.js`
- Multimodal voice + text input with TTS read-back
- Graceful degradation for native modules

### Admin Panel
- Professional visual design with consistent polish
- Sound architecture (Vite + React Router + shadcn/ui)
- Proper route nesting, context-based auth
- Clean component hierarchy and idiomatic shadcn/ui usage
- `PaginatedResponse<T>` generic ready for real API integration

### Tests & Infrastructure
- Strong HIPAA-related test coverage (encryption, PII masking, audit)
- Persistent store tests verify restart survival
- Idempotent startup script
- Drug cost engine has good edge case coverage
- Clean 3-job CI pipeline with appropriate separation

---

## Recommended Priority Order

### Phase 1: Security Blockers (Week 1)
1. Fix path traversal in admin SPA route (C1)
2. Fix SQL injection in cms_import (C2)
3. Fix path traversal in gdrive_sync (C3)
4. Fix tar extraction vulnerability (C4)
5. Fix XSS in quote widget (C5)
6. Fix Zoho query injection (C17)
7. Enforce non-empty JWT_SECRET in production (C12)
8. Disable test credentials in production (C16)
9. Fix hardcoded admin password in CLI (C18)

### Phase 2: HIPAA Compliance (Week 2)
10. Wire in PHI encryption at rest (C6)
11. Unify OTP stores (C7)
12. Add session-to-user ownership check (H7)
13. Expand audit logging to all PHI access (H12)
14. Remove PHI from JWT tokens (H1)
15. Move to secure token storage on mobile (H4)
16. Stop passing PHI in URL params (H2, H5)
17. Complete Sentry PII scrubbing (H6)
18. Fix database file permissions (H14)
19. Implement token revocation (C15)

### Phase 3: Data Correctness (Week 3)
20. Fix pharmacy in-network false positives (C10)
21. Fix usage_summary crash and wrong keys (C9)
22. Fix provider enrichment data loss (C8)
23. Fix deductible calculation (C11)
24. Fix drug cost for 60/90-day supplies (M3)
25. Fix Part B giveback double dollar sign (M1)

### Phase 4: Performance & Reliability (Week 4)
26. Add asyncio.Lock to OAuth token caches (H18)
27. Implement concurrent provider search (H19)
28. Fix Zoho token caching (H20)
29. Parallelize RTPBC batch queries (H21)
30. Fix N+1 queries in plan search (H22)
31. Share httpx clients across calls
32. Add multi-worker deployment

### Phase 5: Admin Panel & Polish (Weeks 5-6)
33. Wire admin panel to real API
34. Fix sign out button
35. Fix MemberDetailPage URL params
36. Add real pagination and filtering
37. Add responsive layout
38. Address remaining medium/low issues

---

*This report was generated by reviewing every file in the repository twice with independent reviewers focusing on different aspects: security, HIPAA compliance, logic bugs, edge cases, architecture, and production readiness.*
