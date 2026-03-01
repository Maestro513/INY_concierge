"""
HealthSpring Provider Directory FHIR Adapter.

HealthSpring (HCSC, formerly Cigna Medicare) uses Cigna's FHIR server.
DaVinci PDEX Plan Net v1.2.0. No authentication required.

Flow:
1. GET /PractitionerRole?specialty=NUCC → roles with NPI, phone, location refs
2. GET /Practitioner/{id} → names, credentials
3. GET /Location/{id} → addresses, coordinates

_include is NOT supported — must fetch Practitioner and Location separately.

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

        Since _include is not supported and PractitionerRole doesn't
        have a location-address search param, we:
        1. Search PractitionerRole by specialty (nationwide)
        2. Batch fetch referenced Practitioner resources (names)
        3. Batch fetch referenced Location resources (addresses)
        4. Let the service layer filter by distance
        """
        codes = resolve_specialty(specialty)
        nucc_code = codes.get("nucc")
        specialty_display = codes.get("display") or specialty

        if not nucc_code:
            logger.warning(f"No NUCC code for: {specialty}")
            return []

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                # Step 1: search PractitionerRole by specialty
                roles = await self._search_roles(client, nucc_code, limit)
                if not roles:
                    print("[HealthSpring] No PractitionerRole results")
                    return []

                # Collect unique Practitioner and Location refs to fetch
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

                print(f"[HealthSpring] Fetching {len(prac_refs)} practitioners, {len(loc_refs)} locations")

                # Step 2 & 3: fetch Practitioner and Location in parallel
                prac_map, loc_map = await asyncio.gather(
                    self._batch_fetch(client, list(prac_refs)),
                    self._batch_fetch(client, list(loc_refs)),
                )

                # Step 4: build results
                results = []
                for role in roles:
                    result = self._build_result(role, prac_map, loc_map, specialty_display)
                    if result:
                        results.append(result)

                results = self._deduplicate(results, limit)
                print(f"[HealthSpring] Final: {len(results)} providers")
                return results

        except Exception as e:
            logger.error(f"HealthSpring search failed: {e}")
            print(f"[HealthSpring] Search failed: {e}")
            return []

    async def _search_roles(
        self,
        client: httpx.AsyncClient,
        nucc_code: str,
        limit: int,
    ) -> list[dict]:
        """Search PractitionerRole by specialty."""
        print(f"[HealthSpring] Searching PractitionerRole: specialty={nucc_code}")

        params = {
            "specialty": nucc_code,
            "_count": str(min(limit, 100)),
        }

        try:
            resp = await client.get(
                f"{HS_BASE}/PractitionerRole",
                params=params,
                headers=HEADERS,
            )
            resp.raise_for_status()
            bundle = resp.json() or {}
        except httpx.HTTPStatusError as e:
            print(f"[HealthSpring] PractitionerRole search failed: {e.response.status_code} {e.response.text[:300]}")
            return []
        except Exception as e:
            print(f"[HealthSpring] PractitionerRole search error: {e}")
            return []

        entries = bundle.get("entry", []) or []
        roles = []
        for entry in entries:
            resource = (entry or {}).get("resource", {}) or {}
            if resource.get("resourceType") == "PractitionerRole":
                roles.append(resource)

        print(f"[HealthSpring] Found {len(roles)} PractitionerRole entries")
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
