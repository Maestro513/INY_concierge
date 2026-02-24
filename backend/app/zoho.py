"""
Zoho CRM integration service for INY Concierge.

Handles OAuth2 token management and provides async functions to query
Zoho CRM v2 for member contacts, plan details, and benefits data.

Configuration is read from environment variables:
    ZOHO_CLIENT_ID       - OAuth2 client ID from Zoho API console
    ZOHO_CLIENT_SECRET   - OAuth2 client secret
    ZOHO_REFRESH_TOKEN   - Long-lived refresh token (generated once via OAuth flow)
    ZOHO_API_DOMAIN      - CRM API base URL  (default: https://www.zohoapis.com)
    ZOHO_ACCOUNTS_URL    - Accounts/auth URL  (default: https://accounts.zoho.com)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger("zoho_crm")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "ZOHO_API_DOMAIN": "https://www.zohoapis.com",
    "ZOHO_ACCOUNTS_URL": "https://accounts.zoho.com",
}


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read an environment variable, stripping whitespace.  Returns the
    supplied *default* (or ``None``) when the variable is unset or blank."""
    val = os.getenv(name, default or _DEFAULTS.get(name, ""))
    if val is not None:
        val = val.strip()
    return val if val else (default or _DEFAULTS.get(name))


def zoho_enabled() -> bool:
    """Return ``True`` when the minimum Zoho credentials are present."""
    return bool(
        _env("ZOHO_CLIENT_ID")
        and _env("ZOHO_CLIENT_SECRET")
        and _env("ZOHO_REFRESH_TOKEN")
    )


# ---------------------------------------------------------------------------
# Token cache  (module-level singleton)
# ---------------------------------------------------------------------------

class _TokenCache:
    """In-memory cache for the Zoho OAuth access token."""

    def __init__(self) -> None:
        self.access_token: Optional[str] = None
        self.expires_at: float = 0.0  # epoch seconds

    def is_valid(self) -> bool:
        """Check whether the cached token is still usable.

        We consider it expired 60 seconds early so that in-flight requests
        don't hit the exact boundary.
        """
        return self.access_token is not None and time.time() < (self.expires_at - 60)

    def store(self, token: str, expires_in: int) -> None:
        self.access_token = token
        self.expires_at = time.time() + expires_in

    def clear(self) -> None:
        self.access_token = None
        self.expires_at = 0.0


_token_cache = _TokenCache()

# ---------------------------------------------------------------------------
# Shared async HTTP client  (reused for connection-pool efficiency)
# ---------------------------------------------------------------------------

_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    """Lazy-initialise a module-level ``httpx.AsyncClient``."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )
    return _http_client


async def close_http_client() -> None:
    """Gracefully close the HTTP client (call on app shutdown)."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class ZohoAuthError(Exception):
    """Raised when we cannot obtain a valid access token from Zoho."""


class ZohoAPIError(Exception):
    """Raised on non-auth Zoho CRM API errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        detail: Any = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


# ---------------------------------------------------------------------------
# OAuth2 token refresh
# ---------------------------------------------------------------------------

async def get_access_token() -> str:
    """Return a valid Zoho CRM access token, refreshing if needed.

    Uses the ``refresh_token`` grant against the Zoho Accounts server::

        POST {ZOHO_ACCOUNTS_URL}/oauth/v2/token
            ?refresh_token=...&client_id=...&client_secret=...&grant_type=refresh_token

    The response contains ``access_token`` and ``expires_in`` (typically 3600 s).
    The token is cached until 60 seconds before expiry.

    Raises
    ------
    ZohoAuthError
        If credentials are missing or the token endpoint returns an error.
    """
    # Fast path -- return cached token
    if _token_cache.is_valid():
        return _token_cache.access_token  # type: ignore[return-value]

    client_id = _env("ZOHO_CLIENT_ID")
    client_secret = _env("ZOHO_CLIENT_SECRET")
    refresh_token = _env("ZOHO_REFRESH_TOKEN")
    accounts_url = _env("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.com")

    if not all([client_id, client_secret, refresh_token]):
        raise ZohoAuthError(
            "Zoho credentials are not configured. "
            "Set ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, and ZOHO_REFRESH_TOKEN."
        )

    token_url = f"{accounts_url}/oauth/v2/token"
    params = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    }

    logger.info("Refreshing Zoho access token ...")
    client = _get_http_client()

    try:
        resp = await client.post(token_url, params=params)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        _token_cache.clear()
        logger.error(
            "Zoho token refresh HTTP error: %s - %s",
            exc.response.status_code,
            exc.response.text,
        )
        raise ZohoAuthError(
            f"Token refresh failed with HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        _token_cache.clear()
        logger.error("Zoho token refresh request error: %s", exc)
        raise ZohoAuthError(f"Token refresh request error: {exc}") from exc

    if "error" in data:
        _token_cache.clear()
        logger.error("Zoho token refresh returned error payload: %s", data)
        raise ZohoAuthError(f"Token refresh error: {data.get('error')}")

    access_token: str = data["access_token"]
    expires_in: int = int(data.get("expires_in", 3600))

    _token_cache.store(access_token, expires_in)
    logger.info("Zoho access token refreshed (expires in %ds)", expires_in)
    return access_token


# ---------------------------------------------------------------------------
# Generic CRM v2 request helper
# ---------------------------------------------------------------------------

async def _crm_request(
    method: str,
    path: str,
    *,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
    retry_on_401: bool = True,
) -> dict[str, Any]:
    """Execute an authenticated request against the Zoho CRM v2 REST API.

    Parameters
    ----------
    method : str
        HTTP verb (GET, POST, PUT, DELETE).
    path : str
        API path after ``/crm/v2/``, e.g. ``"Contacts/search"``.
    params : dict, optional
        Query-string parameters.
    json_body : dict, optional
        JSON request body.
    retry_on_401 : bool
        If True (default), force-refresh the token once on 401 and retry.

    Returns
    -------
    dict
        Parsed JSON response body.

    Raises
    ------
    ZohoAPIError
        On HTTP errors or unexpected responses.
    ZohoAuthError
        If the token refresh itself fails.
    """
    api_domain = _env("ZOHO_API_DOMAIN", "https://www.zohoapis.com")
    url = f"{api_domain}/crm/v2/{path.lstrip('/')}"

    token = await get_access_token()
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type": "application/json",
    }

    client = _get_http_client()

    try:
        resp = await client.request(
            method, url, headers=headers, params=params, json=json_body,
        )
    except httpx.RequestError as exc:
        logger.error("Zoho CRM request error [%s %s]: %s", method, url, exc)
        raise ZohoAPIError(f"Request to Zoho CRM failed: {exc}") from exc

    # Handle 401 -- token may have been revoked externally
    if resp.status_code == 401 and retry_on_401:
        logger.warning("Zoho CRM 401 -- forcing token refresh and retrying ...")
        _token_cache.clear()
        return await _crm_request(
            method, path, params=params, json_body=json_body, retry_on_401=False,
        )

    # 204 No Content -- typically empty search results
    if resp.status_code == 204:
        return {"data": []}

    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body_text = exc.response.text
        logger.error(
            "Zoho CRM HTTP error [%s %s]: %s - %s",
            method, url, exc.response.status_code, body_text,
        )
        raise ZohoAPIError(
            f"Zoho CRM returned HTTP {exc.response.status_code}",
            status_code=exc.response.status_code,
            detail=body_text,
        ) from exc

    return resp.json()


# ---------------------------------------------------------------------------
# Convenience search helper
# ---------------------------------------------------------------------------

async def _api_search(module: str, criteria: str) -> list[dict[str, Any]]:
    """Search a Zoho CRM module using criteria syntax.

    Returns a (possibly empty) list of matching records.
    """
    result = await _crm_request("GET", f"{module}/search", params={"criteria": criteria})
    return result.get("data", [])


# ---------------------------------------------------------------------------
# Contact / Member lookup
# ---------------------------------------------------------------------------

async def search_contact_by_phone(phone: str) -> Optional[dict[str, Any]]:
    """Find a Zoho CRM Contact by phone number.

    Searches the ``Phone`` and ``Mobile`` standard fields using multiple
    formatting variants (bare digits, dashed, parenthesised, +1-prefixed).

    Returns the first matching contact record or ``None``.
    """
    digits = "".join(c for c in phone if c.isdigit())
    if not digits:
        logger.warning("search_contact_by_phone called with empty phone")
        return None

    # Build a list of formatting variants to try
    variants: list[str] = [digits]

    if len(digits) == 10:
        variants.append(f"1{digits}")
        variants.append(f"+1{digits}")
        variants.append(f"({digits[:3]}) {digits[3:6]}-{digits[6:]}")
        variants.append(f"{digits[:3]}-{digits[3:6]}-{digits[6:]}")
        variants.append(f"({digits[:3]}){digits[3:6]}-{digits[6:]}")
    elif len(digits) == 11 and digits.startswith("1"):
        variants.append(digits[1:])
        d = digits[1:]
        variants.append(f"({d[:3]}) {d[3:6]}-{d[6:]}")

    for variant in variants:
        for field in ("Phone", "Mobile"):
            try:
                records = await _api_search("Contacts", f"({field}:equals:{variant})")
                if records:
                    logger.info(
                        "Found Zoho contact for phone=%s (variant=%s, field=%s): id=%s",
                        phone, variant, field, records[0].get("id"),
                    )
                    return records[0]
            except ZohoAPIError as exc:
                if exc.status_code == 404:
                    continue
                logger.warning("Zoho search error for variant %s: %s", variant, exc)
                continue

    logger.info("No Zoho contact found for phone=%s", phone)
    return None


async def get_contact(contact_id: str) -> Optional[dict[str, Any]]:
    """Fetch a single Zoho CRM Contact by record ID."""
    try:
        result = await _crm_request("GET", f"Contacts/{contact_id}")
        data = result.get("data")
        if data and len(data) > 0:
            return data[0]
    except ZohoAPIError as exc:
        logger.error("Failed to fetch contact %s: %s", contact_id, exc)
    return None


# ---------------------------------------------------------------------------
# Field extraction / mapping helpers
# ---------------------------------------------------------------------------

def _extract_member_from_contact(contact: dict[str, Any]) -> dict[str, Any]:
    """Map a Zoho CRM Contact to our member-profile shape.

    Handles both standard Zoho field names and common custom-field patterns
    used in Medicare / insurance CRM setups.
    """
    return {
        "firstName": contact.get("First_Name") or "",
        "lastName": contact.get("Last_Name") or "",
        "carrier": (
            contact.get("Carrier")
            or contact.get("Insurance_Carrier")
            or contact.get("carrier")
            or ""
        ),
        "planName": (
            contact.get("Plan_Name")
            or contact.get("Insurance_Plan")
            or contact.get("plan_name")
            or ""
        ),
        "planId": (
            contact.get("Plan_ID")
            or contact.get("Plan_Id")
            or contact.get("Contract_ID")
            or contact.get("plan_id")
            or ""
        ),
        "memberId": (
            contact.get("Member_ID")
            or contact.get("Member_Id")
            or contact.get("member_id")
            or ""
        ),
        "email": contact.get("Email") or "",
        "phone": contact.get("Phone") or contact.get("Mobile") or "",
        "zohoContactId": contact.get("id") or "",
    }


def _extract_benefits_from_contact(contact: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract quick-glance benefit tiles from Contact custom fields.

    Expected fields: PCP_Copay, Specialist_Copay, Drug_Deductible, Max_OOP.
    Falls back to empty strings so callers can tell whether data was populated.
    """
    return [
        {
            "label": "PCP Visit",
            "value": contact.get("PCP_Copay") or "",
            "icon": "stethoscope",
        },
        {
            "label": "Specialist",
            "value": contact.get("Specialist_Copay") or "",
            "icon": "doctor",
        },
        {
            "label": "Drug Deductible",
            "value": contact.get("Drug_Deductible") or "",
            "icon": "pill",
        },
        {
            "label": "Max Out-of-Pocket",
            "value": contact.get("Max_OOP") or "",
            "icon": "shield",
        },
    ]


def _extract_extra_benefits_from_contact(contact: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract supplemental/extra benefits from Contact custom fields.

    Expected fields: Dental_Benefit, OTC_Benefit, Flex_Card_Benefit,
    Part_B_Giveback, and their boolean Has_* counterparts.
    """
    return [
        {
            "label": "Dental",
            "value": contact.get("Dental_Benefit") or "",
            "icon": "tooth",
            "has": bool(contact.get("Has_Dental")),
        },
        {
            "label": "OTC",
            "value": contact.get("OTC_Benefit") or "",
            "icon": "cart",
            "has": bool(contact.get("Has_OTC")),
        },
        {
            "label": "Flex Card",
            "value": contact.get("Flex_Card_Benefit") or "",
            "icon": "card",
            "has": bool(contact.get("Has_Flex_Card")),
        },
        {
            "label": "Part B Giveback",
            "value": contact.get("Part_B_Giveback") or "",
            "icon": "money",
            "has": bool(contact.get("Has_Part_B_Giveback")),
        },
    ]


def _has_any_value(items: list[dict[str, Any]]) -> bool:
    """Return True if at least one item in the list has a non-empty value."""
    return any(item.get("value") for item in items)


# ---------------------------------------------------------------------------
# Plan / Benefits queries
# ---------------------------------------------------------------------------

async def get_member_plan(contact_id: str) -> Optional[dict[str, Any]]:
    """Retrieve insurance-plan details linked to a Contact.

    Strategy (tried in order):
      1. Related list on a custom ``Insurance_Plans`` module.
      2. Related list on a custom ``Plans`` module.
      3. Plan-related custom fields on the Contact record itself.

    Returns a plan dict or ``None``.
    """
    # -- Strategy 1 & 2: related-list lookup in custom plan modules ----------
    for related_module in ("Insurance_Plans", "Plans"):
        try:
            result = await _crm_request("GET", f"Contacts/{contact_id}/{related_module}")
            plans = result.get("data")
            if plans:
                plan = plans[0]
                return _normalise_plan(plan)
        except ZohoAPIError:
            logger.debug(
                "%s related-list lookup failed for contact %s; trying next",
                related_module,
                contact_id,
            )

    # -- Strategy 3: read plan fields directly from the Contact ---------------
    contact = await get_contact(contact_id)
    if contact:
        plan_name = (
            contact.get("Plan_Name")
            or contact.get("Insurance_Plan")
            or contact.get("plan_name")
        )
        if plan_name:
            return _normalise_plan(contact)

    return None


def _normalise_plan(record: dict[str, Any]) -> dict[str, Any]:
    """Normalise a Zoho record (from any module) into our plan shape."""
    return {
        "planName": (
            record.get("Plan_Name")
            or record.get("Name")
            or record.get("Insurance_Plan")
            or record.get("plan_name")
            or ""
        ),
        "planId": (
            record.get("Plan_ID")
            or record.get("Plan_Id")
            or record.get("Contract_ID")
            or record.get("plan_id")
            or ""
        ),
        "carrier": (
            record.get("Carrier")
            or record.get("Insurance_Carrier")
            or record.get("carrier")
            or ""
        ),
        "planType": record.get("Plan_Type") or record.get("plan_type") or "",
        "effectiveDate": record.get("Effective_Date") or record.get("effective_date") or "",
        "terminationDate": record.get("Termination_Date") or record.get("termination_date") or "",
    }


async def get_member_benefits(plan_id: str) -> Optional[dict[str, Any]]:
    """Retrieve the Schedule of Benefits for a given plan ID.

    Strategy:
      1. Search a custom ``Benefits`` or ``Plan_Benefits`` module by Plan_ID.
      2. Search ``Deals`` or ``Insurance_Plans`` by plan ID, then query their
         related Benefits records.

    Returns::

        {"medical": [{"label": "...", "value": "..."}, ...],
         "drugs":   [{"label": "...", "value": "..."}, ...]}

    or ``None``.
    """
    if not plan_id:
        return None

    # -- Strategy 1: direct search on a Benefits module -----------------------
    for module_name in ("Benefits", "Plan_Benefits"):
        criteria = f"(Plan_ID:equals:{plan_id})"
        try:
            records = await _api_search(module_name, criteria)
            if records:
                return _normalise_benefits(records)
        except ZohoAPIError:
            logger.debug(
                "Benefits lookup in module %s failed for plan_id=%s",
                module_name,
                plan_id,
            )

    # -- Strategy 2: parent Deal / Insurance_Plan -> related Benefits ---------
    for parent_module in ("Deals", "Insurance_Plans"):
        criteria = f"((Plan_ID:equals:{plan_id})or(Contract_ID:equals:{plan_id}))"
        try:
            parent_records = await _api_search(parent_module, criteria)
            if parent_records:
                parent_id = parent_records[0].get("id")
                try:
                    result = await _crm_request("GET", f"{parent_module}/{parent_id}/Benefits")
                    benefit_records = result.get("data")
                    if benefit_records:
                        return _normalise_benefits(benefit_records)
                except ZohoAPIError:
                    pass
        except ZohoAPIError:
            continue

    logger.info("No benefits found in Zoho CRM for plan_id=%s", plan_id)
    return None


async def get_member_benefits_by_contact(contact_id: str) -> Optional[dict[str, Any]]:
    """Retrieve SOB data via a Contact's related Benefits records, or from
    the Contact's own custom fields as a last resort.

    This is a convenience wrapper used when we already have a contact_id
    but may not yet know the plan_id.
    """
    # Try related Benefits module on the Contact
    try:
        result = await _crm_request("GET", f"Contacts/{contact_id}/Benefits")
        records = result.get("data")
        if records:
            return _normalise_benefits(records)
    except ZohoAPIError:
        logger.debug("Related Benefits lookup failed for contact %s", contact_id)

    # Fall back to SOB fields on the Contact itself
    contact = await get_contact(contact_id)
    if contact:
        sob = {
            "medical": [
                {"label": "Inpatient Hospital", "value": contact.get("Inpatient_Copay") or ""},
                {"label": "Outpatient Surgery", "value": contact.get("Outpatient_Copay") or ""},
                {"label": "Emergency Room", "value": contact.get("ER_Copay") or ""},
                {"label": "Urgent Care", "value": contact.get("Urgent_Care_Copay") or ""},
            ],
            "drugs": [
                {"label": "Tier 1 (Preferred Generic)", "value": contact.get("Tier1_Copay") or ""},
                {"label": "Tier 2 (Generic)", "value": contact.get("Tier2_Copay") or ""},
                {"label": "Tier 3 (Preferred Brand)", "value": contact.get("Tier3_Copay") or ""},
                {"label": "Tier 4 (Non-Preferred)", "value": contact.get("Tier4_Copay") or ""},
            ],
        }
        has_data = any(item["value"] for items in sob.values() for item in items)
        if has_data:
            return sob

    return None


def _normalise_benefits(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert a list of Zoho benefit records into our SOB shape.

    Each record is expected to have:
      - ``Name`` or ``Benefit_Name`` or ``Benefit_Label`` -- human-readable label
      - ``Value`` or ``Benefit_Value`` or ``Copay`` -- cost string
      - ``Category`` or ``Benefit_Category`` -- ``"medical"`` or ``"drugs"``
    """
    medical: list[dict[str, str]] = []
    drugs: list[dict[str, str]] = []

    for rec in records:
        label = (
            rec.get("Name")
            or rec.get("Benefit_Name")
            or rec.get("Benefit_Label")
            or rec.get("Label")
            or ""
        )
        value = (
            rec.get("Value")
            or rec.get("Benefit_Value")
            or rec.get("Copay")
            or ""
        )
        category = (
            rec.get("Category")
            or rec.get("Benefit_Category")
            or "medical"
        ).lower().strip()

        entry = {"label": label, "value": value}

        if category in ("drug", "drugs", "rx", "pharmacy", "prescription"):
            drugs.append(entry)
        else:
            medical.append(entry)

    return {"medical": medical, "drugs": drugs}


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

async def test_connection() -> dict[str, Any]:
    """Test the Zoho CRM connection by fetching org info.

    Returns a dict with ``connected``, ``configured``, ``message``, and
    optionally ``orgName`` / ``orgId``.
    """
    if not zoho_enabled():
        return {
            "connected": False,
            "configured": False,
            "message": "Zoho credentials are not configured.",
        }

    try:
        token = await get_access_token()
        api_domain = _env("ZOHO_API_DOMAIN", "https://www.zohoapis.com")
        client = _get_http_client()
        resp = await client.get(
            f"{api_domain}/crm/v2/org",
            headers={"Authorization": f"Zoho-oauthtoken {token}"},
        )
        resp.raise_for_status()
        org_data = resp.json()

        org_info: dict[str, str] = {}
        org_list = org_data.get("org")
        if isinstance(org_list, list) and org_list:
            org_info["orgName"] = org_list[0].get("company_name", "")
            org_info["orgId"] = str(org_list[0].get("id", ""))

        return {
            "connected": True,
            "configured": True,
            "message": "Successfully connected to Zoho CRM.",
            **org_info,
        }
    except ZohoAuthError as exc:
        return {
            "connected": False,
            "configured": True,
            "message": f"Authentication failed: {exc}",
        }
    except Exception as exc:
        logger.exception("Zoho connection test failed")
        return {
            "connected": False,
            "configured": True,
            "message": f"Connection error: {exc}",
        }
