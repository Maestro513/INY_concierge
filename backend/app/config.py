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

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDFS_DIR = os.getenv("PDFS_DIR", os.path.join(BASE_DIR, "pdfs"))
EXTRACTED_DIR = os.getenv("EXTRACTED_DIR", os.path.join(BASE_DIR, "extracted"))