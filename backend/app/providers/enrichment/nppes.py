"""
NPPES (National Plan & Provider Enumeration System) enrichment service.
Free, no auth required. Used to supplement carriers that don't provide
NUCC specialty codes or accepting patients data.
"""

import httpx
import logging

logger = logging.getLogger(__name__)

NPPES_URL = "https://npiregistry.cms.hhs.gov/api/"
TIMEOUT = 10.0


async def lookup_npi(npi: str) -> dict | None:
    """
    Look up a provider by NPI number in the NPPES registry.
    Returns dict with specialty, accepting patients, and other details.
    """
    if not npi:
        return None

    params = {
        "number": npi,
        "version": "2.1",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(NPPES_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            return None

        result = results[0]
        return _parse_nppes_result(result)

    except Exception as e:
        logger.error(f"NPPES lookup failed for NPI {npi}: {e}")
        return None


async def bulk_lookup_npis(npis: list[str]) -> dict[str, dict]:
    """
    Look up multiple NPIs. Returns dict keyed by NPI.
    NPPES doesn't support bulk queries, so we batch them.
    """
    results = {}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for npi in npis:
            if not npi:
                continue
            try:
                resp = await client.get(
                    NPPES_URL,
                    params={"number": npi, "version": "2.1"},
                )
                resp.raise_for_status()
                data = resp.json()
                api_results = data.get("results", [])
                if api_results:
                    results[npi] = _parse_nppes_result(api_results[0])
            except Exception as e:
                logger.warning(f"NPPES lookup failed for {npi}: {e}")
                continue

    return results


def _parse_nppes_result(result: dict) -> dict:
    """Parse a single NPPES result into a clean dict."""
    # Get primary taxonomy (specialty)
    taxonomies = result.get("taxonomies", [])
    primary_specialty = ""
    specialty_code = ""
    for tax in taxonomies:
        if tax.get("primary", False):
            primary_specialty = tax.get("desc", "")
            specialty_code = tax.get("code", "")
            break

    # If no primary, take the first one
    if not primary_specialty and taxonomies:
        primary_specialty = taxonomies[0].get("desc", "")
        specialty_code = taxonomies[0].get("code", "")

    # Basic info
    basic = result.get("basic", {})

    # Address (practice location)
    addresses = result.get("addresses", [])
    practice_addr = {}
    for addr in addresses:
        if addr.get("address_purpose") == "LOCATION":
            practice_addr = addr
            break
    if not practice_addr and addresses:
        practice_addr = addresses[0]

    return {
        "npi": str(result.get("number", "")),
        "specialty": primary_specialty,
        "specialty_code": specialty_code,
        "first_name": basic.get("first_name", ""),
        "last_name": basic.get("last_name", ""),
        "credentials": basic.get("credential", ""),
        "gender": basic.get("gender", ""),
        "address_line": practice_addr.get("address_1", ""),
        "suite": practice_addr.get("address_2", ""),
        "city": practice_addr.get("city", ""),
        "state": practice_addr.get("state", ""),
        "zip_code": practice_addr.get("postal_code", "")[:5],
        "phone": practice_addr.get("telephone_number", ""),
        "fax": practice_addr.get("fax_number", ""),
    }