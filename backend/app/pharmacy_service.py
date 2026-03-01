"""
Pharmacy finder service.

Uses Google Places Nearby Search to find pharmacies near a zip code,
then cross-references with CMS pharmacy network data to show
in-network / preferred status for the member's plan.
"""

import logging
import os
import sqlite3
from functools import lru_cache

import httpx

from .config import BASE_DIR, GOOGLE_API_KEY
from .providers.enrichment.geocoding import geocode_zip, haversine_miles

logger = logging.getLogger(__name__)

PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
TIMEOUT = 15.0

# ── CMS pharmacy network DB ──────────────────────────────────────────────────

_DB_PATH = os.path.join(BASE_DIR, "cms_benefits.db")


def _get_db():
    """Get a read-only connection to cms_benefits.db."""
    if not os.path.exists(_DB_PATH):
        return None
    conn = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, table_name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cur.fetchone() is not None


def _parse_plan_number(plan_number: str) -> tuple:
    """Parse 'H1036-077' into (contract_id, plan_id, segment_id)."""
    parts = plan_number.strip().upper().replace(" ", "").split("-")
    contract_id = parts[0] if len(parts) > 0 else ""
    plan_id = parts[1] if len(parts) > 1 else "000"
    segment_id = parts[2] if len(parts) > 2 else "000"
    return contract_id, plan_id, segment_id


def get_plan_pharmacy_zips(plan_number: str) -> dict:
    """
    Get all pharmacy zip codes in a plan's network from CMS data.
    Returns dict: { zip_code: { preferred_retail: bool, preferred_mail: bool } }
    """
    conn = _get_db()
    if not conn:
        return {}
    try:
        if not _table_exists(conn, "pharmacy_network"):
            return {}
        contract_id, plan_id, segment_id = _parse_plan_number(plan_number)
        cur = conn.execute(
            """SELECT pharmacy_zipcode, preferred_status_retail, preferred_status_mail,
                      pharmacy_retail, pharmacy_mail
               FROM pharmacy_network
               WHERE contract_id = ? AND plan_id = ?
               AND pharmacy_retail = 'Y'""",
            (contract_id, plan_id),
        )
        zips = {}
        for row in cur:
            z = row["pharmacy_zipcode"]
            zips[z] = {
                "preferred": row["preferred_status_retail"] == "Y",
                "mail_order": row["pharmacy_mail"] == "Y",
            }
        return zips
    except Exception as e:
        logger.warning(f"Pharmacy network lookup failed: {e}")
        return {}
    finally:
        conn.close()


def get_plan_pharmacy_ncpdp_ids(plan_number: str) -> set:
    """
    Get all NCPDP pharmacy IDs for a plan from CMS data.
    Returns set of pharmacy_number strings.
    """
    conn = _get_db()
    if not conn:
        return set()
    try:
        if not _table_exists(conn, "pharmacy_network"):
            return set()
        contract_id, plan_id, _ = _parse_plan_number(plan_number)
        cur = conn.execute(
            """SELECT DISTINCT pharmacy_number
               FROM pharmacy_network
               WHERE contract_id = ? AND plan_id = ?
               AND pharmacy_retail = 'Y'""",
            (contract_id, plan_id),
        )
        return {row["pharmacy_number"] for row in cur}
    except Exception as e:
        logger.warning(f"NCPDP lookup failed: {e}")
        return set()
    finally:
        conn.close()


def check_pharmacy_in_network(plan_number: str, pharmacy_zip: str) -> dict | None:
    """
    Check if a pharmacy zip is in the plan's network.
    Returns status dict or None if no CMS data available.
    """
    conn = _get_db()
    if not conn:
        return None
    try:
        if not _table_exists(conn, "pharmacy_network"):
            return None
        contract_id, plan_id, _ = _parse_plan_number(plan_number)
        cur = conn.execute(
            """SELECT preferred_status_retail, pharmacy_mail
               FROM pharmacy_network
               WHERE contract_id = ? AND plan_id = ? AND pharmacy_zipcode = ?
               AND pharmacy_retail = 'Y'
               LIMIT 1""",
            (contract_id, plan_id, pharmacy_zip),
        )
        row = cur.fetchone()
        if not row:
            return {"in_network": False, "preferred": False}
        return {
            "in_network": True,
            "preferred": row["preferred_status_retail"] == "Y",
        }
    except Exception:
        return None
    finally:
        conn.close()


# ── Google Places search ──────────────────────────────────────────────────────

async def search_pharmacies_google(
    lat: float, lng: float, radius_meters: int = 16093
) -> list:
    """
    Search for pharmacies near lat/lng using Google Places Nearby Search.
    Default radius: 10 miles (16093 meters).
    """
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY not configured")
        return []

    params = {
        "location": f"{lat},{lng}",
        "radius": radius_meters,
        "type": "pharmacy",
        "key": GOOGLE_API_KEY,
    }

    results = []
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(PLACES_NEARBY_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "OK":
            logger.warning(f"Places API status: {data.get('status')}")
            return []

        for place in data.get("results", []):
            loc = place.get("geometry", {}).get("location", {})
            pharmacy = {
                "place_id": place.get("place_id", ""),
                "name": place.get("name", ""),
                "address": place.get("vicinity", ""),
                "lat": loc.get("lat"),
                "lng": loc.get("lng"),
                "google_rating": place.get("rating"),
                "google_review_count": place.get("user_ratings_total"),
                "open_now": place.get("opening_hours", {}).get("open_now"),
                "business_status": place.get("business_status", ""),
            }
            results.append(pharmacy)

    except Exception as e:
        logger.error(f"Google Places search failed: {e}")

    return results


# ── Main search function ─────────────────────────────────────────────────────

async def search_pharmacies(
    plan_number: str,
    zip_code: str,
    radius_miles: int = 10,
    limit: int = 30,
) -> dict:
    """
    Find pharmacies near a zip code.
    Cross-references with CMS data for in-network/preferred status.
    """
    # 1. Geocode the zip code
    coords = await geocode_zip(zip_code)
    if not coords:
        return {
            "success": False,
            "error": f"Could not locate zip code {zip_code}",
            "pharmacies": [],
        }

    user_lat, user_lng = coords
    radius_meters = int(radius_miles * 1609.34)

    # 2. Search Google Places for pharmacies
    pharmacies = await search_pharmacies_google(user_lat, user_lng, radius_meters)

    if not pharmacies:
        return {
            "success": True,
            "total": 0,
            "zip_code": zip_code,
            "pharmacies": [],
        }

    # 3. Calculate distances and check network status
    network_zips = get_plan_pharmacy_zips(plan_number) if plan_number else {}
    has_network_data = len(network_zips) > 0

    enriched = []
    for pharm in pharmacies:
        if pharm.get("business_status") == "CLOSED_PERMANENTLY":
            continue

        # Calculate distance
        dist = None
        if pharm.get("lat") and pharm.get("lng"):
            dist = haversine_miles(user_lat, user_lng, pharm["lat"], pharm["lng"])

        # Extract pharmacy zip from address (rough match)
        pharm_zip = _extract_zip(pharm.get("address", ""))

        # Check CMS network status (all results are in-network; preferred is a tier above)
        is_preferred = False
        in_network = None  # None = no CMS data available
        if has_network_data and pharm_zip:
            if pharm_zip in network_zips:
                in_network = True
                is_preferred = network_zips[pharm_zip].get("preferred", False)
            else:
                in_network = True  # all pharmacies shown are in-network

        enriched.append({
            "name": pharm["name"],
            "address": pharm["address"],
            "distance_miles": dist,
            "google_rating": pharm.get("google_rating"),
            "google_review_count": pharm.get("google_review_count"),
            "open_now": pharm.get("open_now"),
            "lat": pharm.get("lat"),
            "lng": pharm.get("lng"),
            "place_id": pharm.get("place_id"),
            "in_network": in_network,
            "preferred": is_preferred,
        })

    # Sort: preferred first, then non-preferred in-network, then distance
    # (preferred are always in-network — no out-of-network results shown)
    enriched.sort(key=lambda p: (
        not (p.get("preferred") or False),
        p.get("distance_miles") or 999,
    ))

    # Limit results
    enriched = enriched[:limit]

    return {
        "success": True,
        "total": len(enriched),
        "zip_code": zip_code,
        "has_network_data": has_network_data,
        "pharmacies": enriched,
    }


def _extract_zip(address: str) -> str | None:
    """Try to extract a 5-digit zip from an address string."""
    import re
    match = re.search(r'\b(\d{5})(?:\-\d{4})?\b', address)
    return match.group(1) if match else None
