"""
App configuration from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Zoho CRM
ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")

# Google APIs (Geocoding + Places)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDFS_DIR = os.path.join(BASE_DIR, "pdfs")
EXTRACTED_DIR = os.path.join(BASE_DIR, "extracted")