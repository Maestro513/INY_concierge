# Conci (INY Concierge) — Full Codebase Review

**Date:** 2026-03-13
**Scope:** Every source file in the project — backend, mobile app, admin dashboard, infra, tests, scripts
**Agents deployed:** 6 parallel reviewers, 2 sweeps (front-to-back)
**Total findings:** 120+

---

## EXECUTIVE SUMMARY

This is a HIPAA-regulated healthcare application handling Medicare beneficiary data, health screening PHI, medication records, and insurance plan information. The review uncovered **serious security vulnerabilities** that require immediate action, particularly around credential exposure, authentication bypasses, and PHI handling.

**Immediate action items (do these TODAY):**
1. Rotate ALL credentials in `backend/.env` — they are committed/on disk
2. Remove hardcoded OTP bypass `'123456'` in `app/otp.js`
3. Remove hardcoded upload secret in `upload_pdfs.py`
4. Fix auth bypass in development mode (`main.py:516`)
5. Wire the admin Sign Out button (`Sidebar.tsx:67`)
6. Add role-based access control to `ProtectedRoute.tsx`

---

## FINDINGS BY SEVERITY

### CRITICAL (17 findings)

| # | Area | File:Line | Finding |
|---|------|-----------|---------|
| C1 | **SECRETS** | `backend/.env` | **5 live production credentials committed** — Anthropic API key, Zoho client ID/secret/refresh token, Google API key. ROTATE IMMEDIATELY. |
| C2 | **SECRETS** | `upload_pdfs.py:8` | Hardcoded upload secret `"iny-migrate-2025"` + local filesystem path in committed source |
| C3 | **AUTH** | `app/otp.js:138` | Hardcoded backdoor OTP `'123456'` bypasses authentication in production builds — no `__DEV__` guard |
| C4 | **AUTH** | `main.py:516-517` | Authentication completely bypassed when `APP_ENV == "development"` — misconfigured deploy = full PHI access |
| C5 | **AUTH** | `app/lock.js:80-83` | Magic string `'__device_reauth__'` sent as OTP code to verify-otp endpoint — authentication bypass vector |
| C6 | **AUTH** | `admin/ProtectedRoute.tsx:20` | No role or `is_active` check — any authenticated user (including `viewer`) gets full admin access |
| C7 | **AUTH** | `admin/Sidebar.tsx:67` | Sign Out button has no `onClick` handler — admin sessions cannot be terminated via UI |
| C8 | **SECURITY** | `utils/deviceAuth.js:29-31` | Device trust flag stored in unencrypted AsyncStorage — tamperable to bypass lock screen |
| C9 | **SECURITY** | `persistent_store.py:159-200` | OTP verification race condition (TOCTOU) — concurrent requests can double-spend attempt counter |
| C10 | **PHI** | `admin_db.py:144-169` | Plaintext admin emails + IP addresses written to login_events table |
| C11 | **PHI** | `claude_client.py:264` | PHI-containing question used in chunk scoring/logging; scrubbed version never used for intermediate processing |
| C12 | **INFRA** | `backend/*.db` | SQLite database files (audit.db, admin.db, cms_benefits.db) present on disk — may contain PHI |
| C13 | **INFRA** | `ci.yml` | Zero security scanning (no pip audit, npm audit, SAST, secret scanning) for a HIPAA application |
| C14 | **API** | `rtpbc_service.py:41-44` | Production defaults to Aetna sandbox/demo URL — real drug cost queries go to fake endpoint |
| C15 | **API** | `healthspring.py:145-172` | Unbounded concurrent HTTP fetches can block the entire FastAPI event loop |
| C16 | **CODE** | `db_migrate.py:44-118` | SQLite connections leaked on exception in all 3 migration functions (no try/finally) |
| C17 | **CODE** | `admin/MemberDetailPage.tsx:71` | URL `id` param ignored; hardcoded mock `'1'`; will crash (`Cannot read properties of undefined`) on real data |

---

### HIGH (36 findings)

| # | Area | File:Line | Finding |
|---|------|-----------|---------|
| H1 | AUTH | `admin_router.py:247-252` | Admin logout only clears cookies — doesn't invalidate server-side sessions/tokens |
| H2 | AUTH | `main.py:2876-2957` | 4 PHI endpoints use `require_auth` instead of `get_current_user` — stolen JWT works after logout |
| H3 | AUTH | `admin_router.py:666-753` | Upload endpoint uses static `X-Admin-Secret` instead of JWT — no audit trail of uploader |
| H4 | AUTH | `main.py:2885-2900` | Health screening endpoint always returns 401 — dead code path (session lookup logic broken) |
| H5 | SECURITY | `constants/api.js:20-26` | No HTTPS enforcement on `EXPO_PUBLIC_API_URL` override — PHI can transmit over HTTP |
| H6 | SECURITY | `main.py:207-215` | CORS allows any `localhost` origin for `staging` env — staging with real data is exposed |
| H7 | SECURITY | `admin_db.py:45-53` | Plaintext phone numbers stored in `search_events` analytics table |
| H8 | SECURITY | `admin_router.py:1038-1061` | No ownership check on appointment request PATCH — viewer role can modify any request (IDOR) |
| H9 | PHI | `retention_pipeline.py:94,443` | Medicare numbers and client names logged in plain text to log files |
| H10 | PHI | `.gitignore` | `pipeline_output/` (contains PHI CSVs), `benefits_cache.json`, `pipeline_run_*.log` not in .gitignore |
| H11 | PHI | `components/SOBModal.js:41-50` | SOB PDF (PHI) written to device cache and never deleted |
| H12 | PHI | `main.py:2681-2682` | Audit log `detail` field has no PII scrubbing — PHI can leak into audit records |
| H13 | PHI | `utils/notifications.js` | 5 unconditional `console.log` calls in production — medication data in messages |
| H14 | PHI | `app/sdoh-screening.js:95-116` | SDoH answers silently discarded if sessionId missing; wrong-member attribution risk on shared devices |
| H15 | API | `pharmacy_service.py:163` | Google API key passed as URL query parameter — exposed in access logs (use header instead) |
| H16 | API | `zoho_client.py:127` | Formatted phone `(XXX) XXX-XXXX` not URL-encoded in COQL criteria — breaks Zoho search |
| H17 | API | `drug_cost_engine.py:66-80` | Drug deductible calculation is order-dependent — produces incorrect annual cost estimates |
| H18 | API | `drug_cost_engine.py:264-265` | `deductible_remaining` uses total YTD cost instead of actual deductible spend |
| H19 | API | `plan_search.py:205-208` | Dynamic SQL with up to 50 OR conditions — no cap, causes full table scans |
| H20 | API | `cms_lookup.py:78-85` | Thread-local SQLite connections never closed — file descriptor leak under load |
| H21 | CODE | `circuit_breaker.py:72-76` | Race condition: `_opened_at` read without lock after state property releases lock |
| H22 | CODE | `components/VoiceHelp.js:904-1013` | Race condition: concurrent `processQuestion` calls overwrite each other's results |
| H23 | CODE | `components/VoiceHelp.js:936-1003` | Voice input sent to backend without sanitization — injection risk via speech |
| H24 | CODE | `components/MedReminders.js` | 448-line dead-code duplicate of ProfileCard.js reminder UI — never imported |
| H25 | CODE | `app/home.js:69` | `benefitsError` type mismatch — reset to `false` (boolean) vs `''`/`'server'` (string) |
| H26 | CODE | `app/digital-id.js:8` | Wrong `SafeAreaView` import — inconsistent with project pattern, bugs on Android |
| H27 | ADMIN | All admin mutation handlers | ALL write actions (assign plan, create member, send OTP) are `setTimeout` stubs — no API calls |
| H28 | ADMIN | `DashboardPage.tsx`, `SystemPage.tsx` | All dashboard/system metrics are hardcoded mock data — "All Systems Operational" is a lie |
| H29 | ADMIN | `Topbar.tsx:31` | User identity hardcoded to "Admin"/"Super Admin" — not from auth context |
| H30 | ADMIN | `App.tsx` | No React error boundary anywhere — any crash shows blank screen |
| H31 | ADMIN | `ScreeningGapsPage.tsx:76` | Real API calls bypass TanStack Query — no caching, retry, or cancellation |
| H32 | ADMIN | `MembersPage.tsx:362`, `PlansPage.tsx:153` | Pagination buttons have no handlers — only first page viewable |
| H33 | INFRA | `render.yaml` | No health check, no disk backup, free tier (spins down) for a healthcare app |
| H34 | INFRA | `alembic/env.py` | Only migrates 1 of 2+ databases; admin.db has no migration coverage at all |
| H35 | INFRA | `retention_pipeline.py:154` | Unauthenticated read on `/sob/raw/{variant}` production endpoint |
| H36 | TESTS | `conftest.py:13-14` | Auth bypass hardcoded — integration tests never validate production auth behavior |

---

### MEDIUM (38 findings)

| # | Area | File:Line | Finding |
|---|------|-----------|---------|
| M1 | SECURITY | `persistent_store.py:115-117` | OTP hash uses unsalted SHA-256 — 900K space is trivially precomputable |
| M2 | SECURITY | `admin_auth.py:183-199` | `bootstrap_super_admin` silently resets existing admin passwords with no audit |
| M3 | SECURITY | `admin_router.py:581-585` | Path traversal check edge case inconsistency |
| M4 | SECURITY | `conftest.py:17` | Hardcoded Fernet encryption key in test config |
| M5 | PHI | `admin/MembersPage.tsx:278` | Full PHI phone numbers displayed without masking (other pages mask correctly) |
| M6 | PHI | `admin/types/index.ts:85` | `LoginEvent` type exposes full phone + IP without masking guidance |
| M7 | PHI | `test_rtpbc.py:35-38` | Realistic DOB in FHIR test fixtures printed to stdout |
| M8 | PHI | `admin/index.html:8-10` | Google Fonts loaded from CDN without SRI in healthcare admin portal |
| M9 | API | `plan_search.py:376-388` | Gender hardcoded as Male/Female — incorrect ACA premium estimates |
| M10 | API | `rtpbc_service.py:263` | Hardcoded `"2026-01-01"` prescription start date — will break in 2027 |
| M11 | API | `carrier_config.py:85-86` | Two separate carrier detection implementations return different results |
| M12 | API | `extract_benefits.py:68-77` | `_repair_json` brace counter includes braces inside string values |
| M13 | API | `geocoding.py:36` | New `httpx.AsyncClient` per geocoding call — no TLS connection reuse |
| M14 | API | `cms_lookup.py:392` | Strategy 2 (approximateTerm) failures silently swallowed |
| M15 | API | `pharmacy_service.py:143-145` | DB errors silently treated as "no data" in network status check |
| M16 | CODE | `main.py` (multiple) | Session IDs exposed in URL paths — appear in access logs and Referer headers |
| M17 | CODE | `claude_client.py:61-67` | No error handling for malformed JSON or missing `chunks` key |
| M18 | CODE | `sob_parser.py:40-45` | Same `KeyError` on `data["chunks"]` propagates uncaught |
| M19 | CODE | `pdf_processor.py:178-183` | `fitz.Document` not closed on exception — file handle leak |
| M20 | CODE | `AdminAuthProvider.tsx:12,38` | `logout` typed as `() => void` but implementation is `async` |
| M21 | CODE | `MembersPage.tsx:63`, `MemberDetailPage.tsx:50` | `CARRIER_COLORS` duplicated verbatim across two files |
| M22 | CODE | `SettingsPage.tsx:66,98` | Profile and password form buttons have no submit handlers |
| M23 | CODE | `SettingsPage.tsx:15` | Dark mode toggle not persisted — resets on refresh |
| M24 | CODE | `MembersPage.tsx:341` | Multiple dropdown menu items silently do nothing |
| M25 | CODE | `app/lock.js:45-53` | `handleUnlock` called in useEffect before const declaration |
| M26 | CODE | `app/home.js`, `health-screening.js` | Multiple `_`-prefixed dead variables throughout |
| M27 | CODE | `components/GradientBg.js:9` | `_topHeight` prop accepted but never used |
| M28 | CODE | `components/MedReminders.js:114` | Close button missing accessibility attributes |
| M29 | CODE | `app/index.js:51-82` | Animations start during trust-check splash — wasted work |
| M30 | INFRA | `package.json:11` | `--passWithNoTests` masks missing frontend tests in CI |
| M31 | INFRA | `ci.yml` | No branch protection enforcement — direct push to main |
| M32 | INFRA | `package.json:29` | `@modelcontextprotocol/sdk` in production mobile deps (should be devDep) |
| M33 | INFRA | `cms_import.py:136` | Unconditional `DROP TABLE` on import with no confirmation |
| M34 | INFRA | `alembic/env.py:28` | `target_metadata = None` disables autogenerate |
| M35 | INFRA | `render.yaml:11` vs `ci.yml:22` | Python 3.11 in CI, 3.12 in production |
| M36 | INFRA | `retention_pipeline.py:412` | Global variable mutation for Zoho token refresh + silent `except: pass` |
| M37 | TESTS | `test_admin_router.py:39`, `test_api.py:16` | Module-scoped client causes rate-limit state leakage between tests |
| M38 | TESTS | `test_admin_router.py:48-61` | CSRF protection never tested in production mode |

---

### LOW (28 findings)

| # | Area | File:Line | Finding |
|---|------|-----------|---------|
| L1 | CODE | `encryption.py:85-87` | Decryption failure returns raw ciphertext silently instead of raising |
| L2 | CODE | `user_data.py:81` | HMAC fallback key `"dev-key"` hardcoded |
| L3 | CODE | `config.py:26` | `APP_ENV` default inconsistency |
| L4 | CODE | `cms_lookup.py:436` | Static method called via `self.` |
| L5 | CODE | `drug_cost_engine.py:102` | `ZeroDivisionError` if `months=0` |
| L6 | CODE | `plan_search.py:425-441` | Year fallback triggers on all HTTP errors including 401/429 |
| L7 | CODE | All adapters | `_deduplicate` copy-pasted across 4 adapter files |
| L8 | CODE | `sob_parser.py:22`, `claude_client.py:32` | `normalize_plan_id` duplicated in two modules |
| L9 | CODE | `google_places.py:9` | Unused `quote` import |
| L10 | CODE | `plan_search.py:53` | `import time as _time` not at module top |
| L11 | CODE | `extract_benefits.py:99` | No timeout on Anthropic client in batch extraction |
| L12 | CODE | `rtpbc_service.py:715-720` | Same exception logged twice at two severity levels |
| L13 | CODE | `aetna.py:245` | `import asyncio` inside method body (already imported at top) |
| L14 | CODE | `app/lock.js:31` | `clearDeviceTrust` imported but never used |
| L15 | CODE | `app/lock.js:121-122` | Dynamic `require()` inside conditional block |
| L16 | CODE | `constants/theme.js:191` | `'er '` key has trailing space — dead icon map entry |
| L17 | CODE | `app/index.js:272` | "No data stored" trust badge is factually false |
| L18 | ADMIN | `package.json:26` | `zustand` is an unused production dependency |
| L19 | ADMIN | `MemberDetailPage.tsx:342` | Array index as React list key |
| L20 | ADMIN | `ScreeningGapsPage.tsx:292` | Silent 50-row cap with no pagination or UI notice |
| L21 | ADMIN | `package.json:3` | Version is `0.0.0` |
| L22 | ADMIN | `vite.config.ts:17` | Dev proxy target hardcoded to `localhost:8000` |
| L23 | ADMIN | `admin/config/api.ts:1` | Production URL hardcoded as fallback |
| L24 | INFRA | `.gitignore` | `user_data.db` not explicitly ignored |
| L25 | INFRA | `pytest.ini` | No coverage threshold configured |
| L26 | INFRA | `backend/.dockerignore` | .dockerignore present without a Dockerfile |
| L27 | INFRA | `.eslintrc.js:19` | `no-console: off` allows PHI to reach device logs |
| L28 | TESTS | `test_auth.py:49` | 100ms sleep margin for time-based tests — flaky on slow CI |

---

## TEST COVERAGE GAPS

The following critical code paths have **no test coverage**:

1. **Production auth enforcement** — all tests run with `APP_ENV=development` (auth bypassed)
2. **Refresh token rotation/reuse detection** — no test that old tokens are rejected
3. **Admin role escalation** — no test that viewer/admin cannot promote themselves to super_admin
4. **CSRF protection in production mode** — only tested in dev mode (where it's disabled)
5. **SQL injection on input fields** — no fuzzing or negative input tests
6. **SecureStore error handling** — no tests for when device secure storage fails
7. **Input validation on health screening/SDoH endpoints** — raw `request.json()` with no Pydantic model

---

## PRIORITY ACTION PLAN

### Phase 1: Emergency (Today)
- [ ] Rotate all 5 credentials in `backend/.env`
- [ ] Run `git log --all -- backend/.env` — if ever committed, purge with `git filter-repo` and force-push
- [ ] Remove `'123456'` OTP bypass from `app/otp.js`
- [ ] Remove `SECRET = "iny-migrate-2025"` from `upload_pdfs.py`
- [ ] Verify `backend/*.db` files are not tracked: `git ls-files backend/*.db`

### Phase 2: Critical Security (This Week)
- [ ] Fix dev-mode auth bypass in `main.py:516` — use explicit `DISABLE_AUTH` env var
- [ ] Wire admin Sign Out button in `Sidebar.tsx`
- [ ] Add role/`is_active` checks to `ProtectedRoute.tsx`
- [ ] Remove `'__device_reauth__'` magic string from `lock.js` — use proper token refresh
- [ ] Move device trust flag to SecureStore (`utils/deviceAuth.js`)
- [ ] Fix OTP verification race condition with `BEGIN EXCLUSIVE` transaction
- [ ] Add server-side session invalidation to admin logout
- [ ] Remove sandbox default URL from `rtpbc_service.py`
- [ ] Add HTTPS enforcement check in `constants/api.js`

### Phase 3: Security Hardening (This Sprint)
- [ ] Add `pip audit` and `npm audit` to CI pipeline
- [ ] Add secret scanning (gitleaks/trufflehog) to CI
- [ ] Fix CORS to restrict staging environment
- [ ] Switch `require_auth` to `get_current_user` on 4 PHI endpoints
- [ ] Add input validation (Pydantic model) for health screening endpoint
- [ ] Move Google API key from URL params to header
- [ ] Add PHI masking to audit log `detail` field
- [ ] Add pipeline output directories to .gitignore
- [ ] Hash phone numbers in `search_events` table
- [ ] Salt OTP hashes with HMAC
- [ ] Add health check to `render.yaml`
- [ ] Match Python version between CI (3.11) and production (3.12)

### Phase 4: Code Quality (Next Sprint)
- [ ] Delete dead `MedReminders.js` component
- [ ] Fix drug cost deductible calculation order-dependency
- [ ] Add error boundaries to admin dashboard
- [ ] Replace admin mock data with real API calls
- [ ] Wire pagination, search, settings, and dropdown handlers in admin
- [ ] Fix all unused imports and dead variables
- [ ] Close SQLite connections properly (try/finally) in migrations
- [ ] Add SOB PDF cache cleanup in `SOBModal.js`
- [ ] Add `console.log` guard (`__DEV__` or remove) in production paths
- [ ] Write tests for auth enforcement in production mode
- [ ] Write tests for role escalation prevention
- [ ] Cap unbounded batch fetches in Healthspring adapter

---

*Generated by 6 parallel Claude review agents — full individual reports available in agent output files.*
