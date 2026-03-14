"""
HealthSpring Provider Directory FHIR Adapter.

HealthSpring (HCSC, formerly Cigna Medicare) uses Cigna's FHIR server.
DaVinci PDEX Plan Net v1.2.0. No authentication required.

Flow (zip-first, matching Humana pattern):
1. GET /Location?address-postalcode=ZIP → locations near the member
2. GET /PractitionerRole?specialty=NUCC&location=Location/{id} → roles at those locations
3. GET /Practitioner/{id} → names, credentials

Base: https://fhir.cigna.com/ProviderDirectory/v1
Auth: None (public directory)
Accept: application/json
"""

import asyncio
import logging

import httpx

from .base import BaseAdapter, ProviderResult, resolve_specialty

logger = logging.getLogger(__name__)

HS_BASE = "https://fhir.cigna.com/ProviderDirectory/v1"
HEADERS = {"Accept": "application/json"}
TIMEOUT = 30.0
MAX_LOCATIONS = 20
MAX_BATCH_REFS = 100


class HealthspringAdapter(BaseAdapter):
    carrier_name = "HealthSpring"
    base_url = HS_BASE

    async def search_providers(
        self,
        specialty: str,
        zip_code: str,
        plan_name: str = "",
        limit: int = 50,
    ) -> list[ProviderResult]:
        """
        Find providers by specialty near a zip code.

        Uses a zip-first approach:
        1. Search Location by zip code to get nearby locations
        2. Search PractitionerRole by specialty + location
        3. Batch fetch Practitioner resources for names/NPIs
        """
        codes = resolve_specialty(specialty)
        nucc_code = codes.get("nucc")
        specialty_display = codes.get("display") or specialty

        if not nucc_code:
            logger.warning(f"No NUCC code for: {specialty}")
            return []

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                # Step 1: find locations near the zip code
                location_ids = await self._search_locations_by_zip(client, zip_code)
                if not location_ids:
                    logger.debug(f"[HealthSpring] No locations found for zip {zip_code}")
                    return []

                # Step 2: search PractitionerRole by specialty + location
                roles = []
                for loc_id in location_ids[:MAX_LOCATIONS]:
                    batch = await self._search_roles_at_location(client, nucc_code, loc_id, limit)
                    roles.extend(batch)
                    if len(roles) >= limit:
                        break

                if not roles:
                    logger.debug("[HealthSpring] No PractitionerRole results for locations")
                    return []

                # Collect unique Practitioner refs to fetch (locations already known)
                prac_refs = set()
                loc_refs = set()
                for role in roles:
                    prac_ref = role.get("practitioner", {}).get("reference", "")
                    if prac_ref:
                        prac_refs.add(prac_ref)
                    for loc in role.get("location", []):
                        loc_ref = loc.get("reference", "")
                        if loc_ref:
                            loc_refs.add(loc_ref)

                logger.debug(f"[HealthSpring] Fetching {len(prac_refs)} practitioners, {len(loc_refs)} locations")

                # Step 3: fetch Practitioner and Location in parallel (capped)
                prac_map, loc_map = await asyncio.gather(
                    self._batch_fetch(client, list(prac_refs)[:MAX_BATCH_REFS]),
                    self._batch_fetch(client, list(loc_refs)[:MAX_BATCH_REFS]),
                )

                # Step 4: build results
                results = []
                for role in roles:
                    result = self._build_result(role, prac_map, loc_map, specialty_display)
                    if result:
                        results.append(result)

                results = self._deduplicate(results, limit)
                logger.debug(f"[HealthSpring] Final: {len(results)} providers")
                return results

        except Exception as e:
            logger.error(f"HealthSpring search failed: {e}")
            return []

    async def _search_locations_by_zip(
        self,
        client: httpx.AsyncClient,
        zip_code: str,
    ) -> list[str]:
        """Search Location by zip code, return list of Location resource IDs."""
        try:
            resp = await client.get(
                f"{HS_BASE}/Location",
                params={
                    "address-postalcode": zip_code,
                    "_count": str(MAX_LOCATIONS),
                },
                headers=HEADERS,
            )
            resp.raise_for_status()
            bundle = resp.json() or {}
        except httpx.HTTPStatusError as e:
            logger.warning(f"[HealthSpring] Location search failed: {e.response.status_code}")
            return []
        except Exception as e:
            logger.warning(f"[HealthSpring] Location search error: {e}")
            return []

        location_ids = []
        for entry in bundle.get("entry", []) or []:
            resource = (entry or {}).get("resource", {}) or {}
            if resource.get("resourceType") == "Location" and resource.get("id"):
                location_ids.append(resource["id"])

        logger.debug(f"[HealthSpring] Found {len(location_ids)} locations for zip {zip_code}")
        return location_ids

    async def _search_roles_at_location(
        self,
        client: httpx.AsyncClient,
        nucc_code: str,
        location_id: str,
        limit: int,
    ) -> list[dict]:
        """Search PractitionerRole by specialty at a specific location."""
        try:
            resp = await client.get(
                f"{HS_BASE}/PractitionerRole",
                params={
                    "specialty": nucc_code,
                    "location": f"Location/{location_id}",
                    "_count": str(min(limit, 50)),
                },
                headers=HEADERS,
            )
            resp.raise_for_status()
            bundle = resp.json() or {}
        except httpx.HTTPStatusError as e:
            logger.debug(f"[HealthSpring] Role search at {location_id} failed: {e.response.status_code}")
            return []
        except Exception as e:
            logger.debug(f"[HealthSpring] Role search at {location_id} error: {e}")
            return []

        roles = []
        for entry in bundle.get("entry", []) or []:
            resource = (entry or {}).get("resource", {}) or {}
            if resource.get("resourceType") == "PractitionerRole":
                roles.append(resource)
        return roles

    async def _batch_fetch(
        self,
        client: httpx.AsyncClient,
        refs: list[str],
    ) -> dict[str, dict]:
        """Fetch multiple resources by reference, return {ref: resource}."""
        result_map: dict[str, dict] = {}
        if not refs:
            return result_map

        # Limit concurrent fetches
        semaphore = asyncio.Semaphore(10)

        async def fetch_one(ref: str):
            async with semaphore:
                try:
                    resp = await client.get(
                        f"{HS_BASE}/{ref}",
                        headers=HEADERS,
                    )
                    if resp.status_code == 200:
                        resource = resp.json()
                        result_map[ref] = resource
                except Exception:
                    pass  # Skip failures silently

        await asyncio.gather(*[fetch_one(ref) for ref in refs])
        return result_map

    # ─────────────────────────────────────────────
    # Result building
    # ─────────────────────────────────────────────

    def _build_result(
        self,
        role: dict,
        practitioners: dict,
        locations: dict,
        specialty_display: str,
    ) -> ProviderResult | None:
        """Build a ProviderResult from a PractitionerRole + fetched resources."""
        provider = ProviderResult(carrier="HealthSpring", specialty=specialty_display)

        # ── NPI from role identifiers ──
        for ident in role.get("identifier", []):
            system = ident.get("system", "")
            if "npi" in system.lower() or system == "http://hl7.org/fhir/sid/us-npi":
                provider.npi = ident.get("value", "")
                break

        # ── Credentials from qualification extension ──
        for ext in role.get("extension", []):
            url = ext.get("url", "")
            if "qualification" in url.lower():
                for sub_ext in ext.get("extension", []):
                    if sub_ext.get("url") == "code":
                        concept = sub_ext.get("valueCodeableConcept", {})
                        codings = concept.get("coding", [])
                        if codings:
                            provider.credentials = codings[0].get("display", "")
                            break
                if provider.credentials:
                    break

        # ── Practitioner (name, gender) ──
        prac_ref = role.get("practitioner", {}).get("reference", "")
        prac = practitioners.get(prac_ref)

        if prac:
            names = prac.get("name", [{}])
            name = names[0] if names else {}
            provider.first_name = " ".join(name.get("given", []))
            provider.last_name = name.get("family", "")

            # Override credentials from Practitioner if not set
            if not provider.credentials:
                suffixes = name.get("suffix", [])
                provider.credentials = ", ".join(
                    s for s in suffixes if s and s.strip() != "\\n"
                )

            # NPI fallback from Practitioner
            if not provider.npi:
                for ident in prac.get("identifier", []):
                    system = ident.get("system", "")
                    if "npi" in system.lower() or system == "http://hl7.org/fhir/sid/us-npi":
                        provider.npi = ident.get("value", "")
                        break

            provider.gender = prac.get("gender", "")
        else:
            # Without Practitioner data we can't get a name — skip
            prac_display = role.get("practitioner", {}).get("display", "")
            if prac_display:
                parts = prac_display.strip().split()
                if len(parts) >= 2:
                    provider.first_name = parts[0]
                    provider.last_name = parts[-1]
                elif parts:
                    provider.last_name = parts[0]

        # ── Location (address, coords, phone) — use first available ──
        for loc_ref_obj in role.get("location", []):
            loc_ref = loc_ref_obj.get("reference", "")
            loc = locations.get(loc_ref)
            if not loc:
                continue

            addr = loc.get("address", {})
            lines = addr.get("line", [])
            provider.address_line = lines[0] if lines else ""
            provider.suite = lines[1] if len(lines) > 1 else ""
            provider.city = addr.get("city", "")
            provider.state = addr.get("state", "")
            provider.zip_code = addr.get("postalCode", "")

            position = loc.get("position", {})
            if position:
                provider.latitude = position.get("latitude")
                provider.longitude = position.get("longitude")

            for telecom in loc.get("telecom", []):
                if telecom.get("system") == "phone" and not provider.phone:
                    provider.phone = telecom.get("value", "")
                    break

            break  # Use first location with data

        # ── Telecom from role (phone/fax) — take first of each ──
        for telecom in role.get("telecom", []):
            system = telecom.get("system", "")
            value = telecom.get("value", "")
            if system == "phone" and not provider.phone:
                provider.phone = value
            elif system == "fax" and not provider.fax:
                provider.fax = value

        # ── Network name from extensions ──
        for ext in role.get("extension", []):
            if "network-reference" in ext.get("url", ""):
                display = ext.get("valueReference", {}).get("display", "")
                if display:
                    provider.network_name = display
                    break

        # ── Accepting new patients ──
        provider.accepting_new_patients = self._parse_accepting_patients(role)

        if not provider.last_name and not provider.npi:
            return None

        return provider

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────

    def _parse_accepting_patients(self, resource: dict) -> bool | None:
        """Check newpatients extension (DaVinci Plan Net style)."""
        for ext in resource.get("extension", []):
            url = ext.get("url", "")
            if "newpatients" in url.lower():
                for sub_ext in ext.get("extension", []):
                    if sub_ext.get("url") == "acceptingPatients":
                        concept = sub_ext.get("valueCodeableConcept", {})
                        codings = concept.get("coding", [])
                        if codings:
                            return codings[0].get("code", "") == "newpt"
                val = ext.get("valueBoolean")
                if val is not None:
                    return val
        return None

    def _zip_to_state(self, zip_code: str) -> str | None:
        """Zip prefix → state."""
        from .humana import ZIP_PREFIX_TO_STATE
        if not zip_code or len(zip_code) < 3:
            return None
        return ZIP_PREFIX_TO_STATE.get(zip_code[:3])

    def _deduplicate(self, results: list[ProviderResult], limit: int) -> list[ProviderResult]:
        """Deduplicate by NPI or name+zip."""
        seen: set[str] = set()
        unique: list[ProviderResult] = []
        for r in results:
            key = r.npi or f"{r.first_name}_{r.last_name}_{r.zip_code}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(r)
        return unique[:limit]
