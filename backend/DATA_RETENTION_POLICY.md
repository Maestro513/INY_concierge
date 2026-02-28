# Data Retention & Deletion Policy

**Effective Date:** 2026-02-28
**Applies to:** InsuranceNYou Med Concierge application

## Data Categories

### 1. Session Data (In-Memory)
- **What:** Phone number, member lookup data, plan info
- **Retention:** 2 hours (auto-expired)
- **Deletion:** Automatic TTL cleanup on each request
- **Storage:** Server memory only — lost on restart

### 2. OTP Codes (In-Memory)
- **What:** Hashed verification codes
- **Retention:** 3 minutes from generation
- **Deletion:** Auto-deleted on successful verification or expiry
- **Storage:** Server memory only

### 3. Medication Reminders (user_data.db)
- **What:** Phone number, drug names, reminder times
- **Retention:** Until deleted by the member
- **Deletion:** Member can delete via app; admin can purge via API
- **PHI Classification:** Yes — medication names are PHI

### 4. Benefits Usage Tracking (user_data.db)
- **What:** Phone number, spending category, amounts, dates
- **Retention:** Current benefit year + 1 year
- **Deletion:** Auto-purge records older than 2 years
- **PHI Classification:** Indirect — spending categories linked to phone

### 5. Audit Logs (audit.db)
- **What:** Masked actor, action, resource, timestamp, IP
- **Retention:** 7 years (HIPAA minimum for audit trails)
- **Deletion:** Manual purge only after retention period
- **PHI Classification:** No — actors are masked, no raw PHI stored

### 6. CMS Benefits Data (cms_benefits.db)
- **What:** Plan formularies, copays, benefits — public CMS data
- **Retention:** Updated annually with new CMS PUF releases
- **Deletion:** Replaced during annual import
- **PHI Classification:** No — no member-specific data

### 7. JWT Tokens (Client-Side)
- **What:** Signed tokens with member name, plan number
- **Retention:** Access: 2 hours, Refresh: 30 days
- **Deletion:** Cleared on logout; expire automatically
- **PHI Classification:** Contains plan info (encrypted in transit)

## Member Rights

### Right to Deletion
Members can request deletion of all their data by contacting support.
Upon request, the following will be purged within 30 days:
- All medication reminders
- All benefits usage records
- Any active sessions

### Right to Access
Members can export their data via the app (reminders, usage history).

## Technical Controls

| Control | Status |
|---------|--------|
| Field-level encryption (medications, Medicare #) | Enabled via FIELD_ENCRYPTION_KEY |
| Audit logging for PHI access | Enabled (audit.db) |
| PII masking in application logs | Enabled (phone, Medicare) |
| Encrypted transport (HTTPS/TLS) | Enforced by Render |
| OTP hashing (SHA-256) | Enabled |
| JWT signing (HS256) | Enabled |
