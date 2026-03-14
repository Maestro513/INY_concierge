"""
App configuration from environment variables.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the backend/ directory (parent of this file's directory)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path, override=True)

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Zoho CRM
ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")

# Google APIs (Geocoding + Places)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# App environment
APP_ENV = os.getenv("APP_ENV", "production")  # development | staging | production
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# CORS — comma-separated extra origins (insurancenyou.com is always allowed in prod)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")  # e.g. "https://staging.insurancenyou.com"

# Secret for admin endpoints (set in Render env vars)
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
if APP_ENV in ("production", "staging") and not ADMIN_SECRET:
    raise RuntimeError("ADMIN_SECRET must be set in production/staging.")

# JWT Authentication
JWT_SECRET = os.getenv("JWT_SECRET", "")  # MUST be set in production
if not JWT_SECRET:
    import secrets as _secrets
    JWT_SECRET = _secrets.token_urlsafe(32)  # random per-startup fallback for dev
JWT_ACCESS_TTL = int(os.getenv("JWT_ACCESS_TTL", "7200"))         # 2 hours
JWT_REFRESH_TTL = int(os.getenv("JWT_REFRESH_TTL", "2592000"))    # 30 days

# SMS Provider
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "console")  # "twilio" or "console"
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")

# OTP settings
OTP_TTL = int(os.getenv("OTP_TTL", "180"))                  # 3 minutes
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "4"))   # lockout after 4 wrong guesses
OTP_MAX_SENDS = int(os.getenv("OTP_MAX_SENDS", "4"))         # max 4 sends per window
OTP_SEND_WINDOW = int(os.getenv("OTP_SEND_WINDOW", "300"))   # 5 minute window

# Test account — enabled in all environments when env vars are set.
# Keep TEST_OTP strong and rotate regularly in production.
TEST_PHONE = os.getenv("TEST_PHONE", "")
TEST_OTP = os.getenv("TEST_OTP", "")

# Warn if well-known/predictable test credentials are being used
if TEST_PHONE and TEST_OTP:
    import logging as _log_cfg
    _KNOWN_WEAK = {("5555550100", "123456"), ("0000000000", "000000")}
    if (TEST_PHONE, TEST_OTP) in _KNOWN_WEAK:
        _log_cfg.getLogger(__name__).warning(
            "TEST_PHONE/TEST_OTP use well-known values — change them to unique values"
        )

# Sentry
SENTRY_DSN = os.getenv("SENTRY_DSN", "")  # Set in Render env vars for production

# Field-level encryption for PHI at rest (medications, Medicare numbers)
# Generate with: python -c "from app.encryption import generate_key; print(generate_key())"
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "")
if APP_ENV in ("production", "staging") and not FIELD_ENCRYPTION_KEY:
    raise RuntimeError("FIELD_ENCRYPTION_KEY must be set in production/staging — PHI would be stored unencrypted.")

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDFS_DIR = os.getenv("PDFS_DIR", os.path.join(BASE_DIR, "Pdfs"))
EXTRACTED_DIR = os.getenv("EXTRACTED_DIR", os.path.join(BASE_DIR, "extracted"))
