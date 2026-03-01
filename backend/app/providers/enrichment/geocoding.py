"""
Geocoding service for zip code → lat/long conversion and distance calculation.
Uses Google Geocoding API + haversine formula for distance.
"""

import logging
import math
from functools import lru_cache

import httpx

from app.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
TIMEOUT = 10.0


async def geocode_zip(zip_code: str) -> tuple[float, float] | None:
    """
    Convert a zip code to lat/long coordinates.
    Returns (latitude, longitude) or None if not found.
    """
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY not configured")
        return None

    params = {
        "address": zip_code,
        "components": "country:US",
        "key": GOOGLE_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(GEOCODING_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            logger.warning(f"No geocoding results for zip: {zip_code}")
            return None

        location = results[0]["geometry"]["location"]
        return (location["lat"], location["lng"])

    except Exception as e:
        logger.error(f"Geocoding failed for {zip_code}: {e}")
        return None


async def geocode_address(address: str) -> tuple[float, float] | None:
    """
    Convert a full address to lat/long coordinates.
    Returns (latitude, longitude) or None if not found.
    """
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY not configured")
        return None

    params = {
        "address": address,
        "key": GOOGLE_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(GEOCODING_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            return None

        location = results[0]["geometry"]["location"]
        return (location["lat"], location["lng"])

    except Exception as e:
        logger.error(f"Geocoding failed for address: {e}")
        return None


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance in miles between two lat/long points
    using the haversine formula. No API call needed.
    """
    R = 3958.8  # Earth radius in miles

    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return round(R * c, 1)
