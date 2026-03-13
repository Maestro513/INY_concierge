"""
Zoho CRM client for looking up members by phone number.
"""

import logging
import threading
import time
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

from .config import (
    ZOHO_CLIENT_ID,
    ZOHO_CLIENT_SECRET,
    ZOHO_REFRESH_TOKEN,
)

TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"
API_BASE = "https://www.zohoapis.com/crm/v2"

# Cache access token in memory with expiry tracking and thread safety
_token_cache = {"access_token": "", "expires_at": 0}
_token_lock = threading.Lock()

# Retry-capable session for transient network errors
_retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[500, 502, 503, 504],  # PR16: exclude 429 to avoid retry storms
    allowed_methods=["GET", "POST"],
)
_http = requests.Session()
_http.mount("https://", HTTPAdapter(max_retries=_retry_strategy))


def get_access_token() -> str:
    """Get an access token using the refresh token. Caches until near expiry."""
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["access_token"]

    with _token_lock:
        # Double-check after acquiring lock
        now = time.time()
        if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
            return _token_cache["access_token"]

        resp = _http.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": ZOHO_CLIENT_ID,
            "client_secret": ZOHO_CLIENT_SECRET,
            "refresh_token": ZOHO_REFRESH_TOKEN,
        }, timeout=15)
        data = resp.json()

        if "access_token" not in data:
            raise Exception(f"Zoho token error: {data}")

        _token_cache["access_token"] = data["access_token"]
        # Zoho tokens typically expire in 3600s
        _token_cache["expires_at"] = now + data.get("expires_in", 3600)
        return _token_cache["access_token"]


def _extract_contact(contact: dict) -> dict:
    """Extract member data from a Zoho contact record."""
    return {
        "id": contact.get("id"),
        "first_name": contact.get("First_Name", ""),
        "last_name": contact.get("Last_Name", ""),
        "phone": contact.get("Phone", ""),
        "mobile": contact.get("Mobile", ""),
        "plan_name": contact.get("Plan_Name", ""),
        "plan_number": contact.get("Plan_Number", ""),
        "agent": contact.get("Agent", ""),
        "medicare_number": contact.get("Medicare_Number", ""),
        "medications": contact.get("Medications", ""),
        "zip_code": contact.get("Mailing_Zip", ""),
    }


def search_contact_by_phone(phone: str) -> dict | None:
    """
    Search Zoho Contacts module for a member by phone number.
    Returns member data dict or None if not found.
    """
    from .circuit_breaker import zoho_breaker

    with zoho_breaker:
        return _search_contact_impl(phone)


def _search_contact_impl(phone: str) -> dict | None:
    token = get_access_token()

    # Clean phone number — remove spaces, dashes, parens, +1 prefix
    clean = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("+1", "")

    # Remove leading 1 if 11 digits
    if len(clean) == 11 and clean.startswith("1"):
        clean = clean[1:]

    # Prevent COQL injection — phone must be digits only
    if not clean.isdigit() or len(clean) != 10:
        return None

    headers = {"Authorization": f"Zoho-oauthtoken {token}"}

    # Search by phone and mobile fields
    for field in ["Phone", "Mobile"]:
        search_url = f"{API_BASE}/Contacts/search?criteria=({field}:equals:{clean})"
        resp = _http.get(search_url, headers=headers, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            if data.get("data") and len(data["data"]) > 0:
                return _extract_contact(data["data"][0])

    # Try with formatted number (XXX) XXX-XXXX
    if len(clean) == 10:
        formatted = f"({clean[:3]}) {clean[3:6]}-{clean[6:]}"
        encoded = quote(formatted, safe="")
        for field in ["Phone", "Mobile"]:
            search_url = f"{API_BASE}/Contacts/search?criteria=({field}:equals:{encoded})"
            resp = _http.get(search_url, headers=headers, timeout=15)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("data") and len(data["data"]) > 0:
                    return _extract_contact(data["data"][0])

    return None
