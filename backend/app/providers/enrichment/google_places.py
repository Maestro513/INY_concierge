"""
Google Places enrichment service.
Looks up providers by name + location to get ratings, reviews, and Maps links.
Uses Places API (New) for better data and lower cost.
"""

import logging
from urllib.parse import quote

import httpx

from app.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
TIMEOUT = 10.0


async def enrich_provider(
    name: str,
    city: str,
    state: str,
) -> dict | None:
    """
    Search Google Places for a healthcare provider.
    Returns rating, review count, maps URL, and place ID.
    """
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY not configured")
        return None

    # Build search query like "Dr. Jane Smith Coral Springs FL doctor"
    query = f"{name} {city} {state} doctor"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.rating,places.userRatingCount,places.googleMapsUri,places.id,places.formattedAddress",
    }

    body = {
        "textQuery": query,
        "maxResultCount": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                PLACES_SEARCH_URL,
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        places = data.get("places", [])
        if not places:
            return None

        place = places[0]
        return {
            "google_rating": place.get("rating"),
            "google_review_count": place.get("userRatingCount"),
            "google_maps_url": place.get("googleMapsUri", ""),
            "google_place_id": place.get("id", ""),
            "google_name": place.get("displayName", {}).get("text", ""),
            "google_address": place.get("formattedAddress", ""),
        }

    except Exception as e:
        logger.error(f"Google Places lookup failed for {name}: {e}")
        return None


async def enrich_providers(
    providers: list,
    max_enrich: int = 15,
) -> list:
    """
    Enrich a list of ProviderResult objects with Google Places data.
    Only enriches the top N (closest/most relevant) to control API costs.
    """
    enriched_count = 0

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for provider in providers:
            if enriched_count >= max_enrich:
                break

            if not provider.last_name or not provider.city:
                continue

            query = f"{provider.full_name} {provider.city} {provider.state} doctor"

            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": GOOGLE_API_KEY,
                "X-Goog-FieldMask": "places.rating,places.userRatingCount,places.googleMapsUri,places.id",
            }

            body = {
                "textQuery": query,
                "maxResultCount": 1,
            }

            try:
                resp = await client.post(
                    PLACES_SEARCH_URL,
                    json=body,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

                places = data.get("places", [])
                if places:
                    place = places[0]
                    provider.google_rating = place.get("rating")
                    provider.google_review_count = place.get("userRatingCount")
                    provider.google_maps_url = place.get("googleMapsUri", "")
                    provider.google_place_id = place.get("id", "")
                    enriched_count += 1

            except Exception as e:
                logger.warning(f"Places enrichment failed for {provider.full_name}: {e}")
                continue

    return providers
