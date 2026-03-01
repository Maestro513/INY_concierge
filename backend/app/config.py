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

# Google Drive – service account credentials (JSON string from env var)
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# App environment
APP_ENV = os.getenv("APP_ENV", "development")  # development | staging | production
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# CORS — comma-separated extra origins (insurancenyou.com is always allowed in prod)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")  # e.g. "https://staging.insurancenyou.com"

# Google Drive – folder ID for SOB PDFs
GDRIVE_FOLDER_ID = os.getenv(
    "GDRIVE_FOLDER_ID", "1vLrYoIa3lmn9vEdZSXJ9s3p1qoomLHpO"
)

# Secret for admin endpoints (set in Render env vars)
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")

# JWT Authentication
JWT_SECRET = os.getenv("JWT_SECRET", "")  # MUST be set in production
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
OTP_SEND_WINDOW = int(os.getenv("OTP_SEND_WINDOW", "600"))   # 10 minute window

# Test account (works in any environment — for app review & admin access)
# Set these in Render env vars so you can always log in without a real phone
TEST_PHONE = os.getenv("TEST_PHONE", "")          # e.g. "5555550100"
TEST_OTP = os.getenv("TEST_OTP", "")              # e.g. "123456"

# Sentry
SENTRY_DSN = os.getenv("SENTRY_DSN", "")  # Set in Render env vars for production

# Field-level encryption for PHI at rest (medications, Medicare numbers)
# Generate with: python -c "from app.encryption import generate_key; print(generate_key())"
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "")

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDFS_DIR = os.getenv("PDFS_DIR", os.path.join(BASE_DIR, "pdfs"))
EXTRACTED_DIR = os.getenv("EXTRACTED_DIR", os.path.join(BASE_DIR, "extracted"))
