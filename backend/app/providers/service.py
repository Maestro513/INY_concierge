"""
Provider Search Service — the main orchestrator.
Detects carrier from plan name, routes to the correct adapter,
enriches results with NPPES/Google data, calculates distances.
"""

import asyncio
import logging

from .adapters.aetna import AetnaAdapter
from .adapters.base import ProviderResult, resolve_specialty
from .adapters.healthspring import HealthspringAdapter
from .adapters.humana import HumanaAdapter
from .adapters.uhc import UHCAdapter
from .enrichment.geocoding import geocode_address, geocode_zip, haversine_miles
from .enrichment.google_places import enrich_providers
from .enrichment.nppes import bulk_lookup_npis

log = logging.getLogger(__name__)

# Carrier detection keywords → adapter class
CARRIER_MAP = {
    "humana": HumanaAdapter,
    "uhc": UHCAdapter,
    "united": UHCAdapter,
    "aarp": UHCAdapter,
    "healthspring": HealthspringAdapter,
    "aetna": AetnaAdapter,
    # "devoted": DevotedAdapter,
    # "wellcare": WellcareAdapter,
    # "centene": WellcareAdapter,
    # "zing": ZingAdapter,
}


def detect_carrier(plan_name: str) -> str | None:
    """Detect carrier from a plan name string."""
    plan_lower = plan_name.lower()
    for keyword, _ in CARRIER_MAP.items():
        if keyword in plan_lower:
            return keyword
    return None


def get_adapter(carrier_key: str):
    """Get the adapter instance for a carrier."""
    adapter_class = CARRIER_MAP.get(carrier_key)
    if not adapter_class:
        return None
    return adapter_class()


async def search_providers(
    plan_name: str,
    specialty: str,
    zip_code: str,
    radius_miles: float = 25.0,
    limit: int = 25,
    enrich_google: bool = True,
    max_google_enrich: int = 25,
) -> dict:
    """
    Main provider search function.

    Args:
        plan_name: Member's plan name (from Zoho CRM)
        specialty: Natural language specialty (e.g., "cardiologist")
        zip_code: Member's zip code for proximity search
        radius_miles: Search radius in miles (default 25)
        limit: Max results to return from carrier
        enrich_google: Whether to add Google ratings
        max_google_enrich: Max providers to enrich with Google (cost control)

    Returns:
        dict with providers list and metadata
    """
    # Step 1: Detect carrier
    carrier_key = detect_carrier(plan_name)
    if not carrier_key:
        return {
            "success": False,
            "error": f"Could not identify carrier from plan: {plan_name}",
            "providers": [],
        }

    adapter = get_adapter(carrier_key)
    if not adapter:
        return {
            "success": False,
            "error": f"No adapter available for carrier: {carrier_key}",
            "providers": [],
        }

    # Step 2: Resolve specialty
    specialty_info = resolve_specialty(specialty)
    if not specialty_info["nucc"] and not specialty_info["centene"]:
        return {
            "success": False,
            "error": f"Could not resolve specialty: {specialty}. Try terms like 'cardiologist', 'primary care', 'dermatologist'.",
            "providers": [],
        }

    # Step 3: Geocode member's zip
    member_coords = await geocode_zip(zip_code)
    if not member_coords:
        return {
            "success": False,
            "error": f"Could not geocode zip code: {zip_code}",
            "providers": [],
        }

    member_lat, member_lon = member_coords

    log.debug(f"[SERVICE] Carrier: {carrier_key}, Specialty: {specialty}, Zip: {zip_code} -> ({member_lat}, {member_lon})")

    # Step 4: Query carrier FHIR API
    log.info(
        f"Searching {adapter.carrier_name} for {specialty} near {zip_code}"
    )
    providers = await adapter.search_providers(
        specialty=specialty,
        zip_code=zip_code,
        plan_name=plan_name,
        limit=limit,
    )

    log.debug(f"[SERVICE] Raw results from adapter: {len(providers)}")

    if not providers:
        return {
            "success": True,
            "carrier": adapter.carrier_name,
            "specialty": specialty_info["display"],
            "zip_code": zip_code,
            "radius_miles": radius_miles,
            "total": 0,
            "providers": [],
        }

    # Step 5: Calculate distances & geocode providers without coordinates
    needs_geocode = []
    for provider in providers:
        if provider.latitude and provider.longitude:
            provider.distance_miles = haversine_miles(
                member_lat, member_lon,
                provider.latitude, provider.longitude,
            )
        elif provider.zip_code:
            needs_geocode.append(provider)

    # Geocode missing coordinates concurrently in batches of 10
    if needs_geocode:
        async def _geocode_provider(p):
            coords = await geocode_zip(p.zip_code[:5])
            if coords:
                p.latitude, p.longitude = coords
                p.distance_miles = haversine_miles(
                    member_lat, member_lon, coords[0], coords[1],
                )

        BATCH = 10
        for i in range(0, len(needs_geocode), BATCH):
            await asyncio.gather(*[
                _geocode_provider(p) for p in needs_geocode[i:i + BATCH]
            ])

    # Step 6: Filter by radius and sort by distance
    providers = [
        p for p in providers
        if p.distance_miles is not None and p.distance_miles <= radius_miles
    ]
    providers.sort(key=lambda p: p.distance_miles or 999)

    log.debug(f"[SERVICE] After distance filter ({radius_miles}mi): {len(providers)}")

    # Step 7: NPPES enrichment (for carriers that need it)
    npis_needing_enrichment = [
        p.npi for p in providers
        if p.npi and not p.specialty
    ]
    if npis_needing_enrichment:
        nppes_data = await bulk_lookup_npis(npis_needing_enrichment)
        for provider in providers:
            if provider.npi in nppes_data:
                data = nppes_data[provider.npi]
                if not provider.specialty:
                    provider.specialty = data.get("specialty", "")
                if provider.accepting_new_patients is None:
                    # NPPES doesn't have this directly, but specialty is the main gap
                    pass

    # Step 8: Google Places enrichment (concurrent via asyncio.gather)
    if enrich_google and providers:
        providers = await enrich_providers(
            providers,
            max_enrich=max_google_enrich,
        )

    # Step 9: Build response
    return {
        "success": True,
        "carrier": adapter.carrier_name,
        "specialty": specialty_info["display"],
        "zip_code": zip_code,
        "radius_miles": radius_miles,
        "total": len(providers),
        "providers": [p.to_dict() for p in providers],
    }
