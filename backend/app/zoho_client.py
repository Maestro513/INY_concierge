"""
Zoho CRM client for looking up members by phone number.
"""

import requests
from .config import (
    ZOHO_CLIENT_ID,
    ZOHO_CLIENT_SECRET,
    ZOHO_REFRESH_TOKEN,
)

TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"
API_BASE = "https://www.zohoapis.com/crm/v2"

# Cache access token in memory
_access_token = None


def get_access_token() -> str:
    """Get a fresh access token using the refresh token."""
    global _access_token

    resp = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "refresh_token": ZOHO_REFRESH_TOKEN,
    }, timeout=15)
    data = resp.json()

    if "access_token" not in data:
        raise Exception(f"Zoho token error: {data}")

    _access_token = data["access_token"]
    return _access_token


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
        "medications": contact.get("Medications", ""),
        "zip_code": contact.get("Mailing_Zip", ""),
    }


def search_contact_by_phone(phone: str) -> dict | None:
    """
    Search Zoho Contacts module for a member by phone number.
    Returns member data dict or None if not found.
    """
    token = get_access_token()

    # Clean phone number — remove spaces, dashes, parens, +1 prefix
    clean = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("+1", "")

    # Remove leading 1 if 11 digits
    if len(clean) == 11 and clean.startswith("1"):
        clean = clean[1:]

    headers = {"Authorization": f"Zoho-oauthtoken {token}"}

    # Search by phone and mobile fields
    for field in ["Phone", "Mobile"]:
        search_url = f"{API_BASE}/Contacts/search?criteria=({field}:equals:{clean})"
        resp = requests.get(search_url, headers=headers, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            if data.get("data") and len(data["data"]) > 0:
                return _extract_contact(data["data"][0])

    # Try with formatted number (XXX) XXX-XXXX
    if len(clean) == 10:
        formatted = f"({clean[:3]}) {clean[3:6]}-{clean[6:]}"
        for field in ["Phone", "Mobile"]:
            search_url = f"{API_BASE}/Contacts/search?criteria=({field}:equals:{formatted})"
            resp = requests.get(search_url, headers=headers, timeout=15)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("data") and len(data["data"]) > 0:
                    return _extract_contact(data["data"][0])

    return None