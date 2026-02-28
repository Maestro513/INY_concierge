"""
HealthSpring Provider Directory FHIR Adapter.

Uses HCSC's HealthLX platform (DaVinci PDEX Plan Net v1.2.0).
No authentication required — publicly accessible per CMS mandate.

Two-step flow (no chained location queries supported):
1. GET /Location?address-postalcode=ZIP → get location IDs
2. GET /PractitionerRole?specialty=NUCC&location=Location/{id}
       &_include=PractitionerRole:practitioner
       &_include=PractitionerRole:location

Returns PractitionerRole + Practitioner + Location in one bundle (step 2).

Base: https://data.healthspring.healthlx.com:8000
Auth: None (public directory)
"""

import asyncio
import httpx
import logging
from .base import BaseAdapter, ProviderResult, resolve_specialty

logger = logging.getLogger(__name__)

HS_BASE = "https://data.healthspring.healthlx.com:8000"
HEADERS = {"Accept": "application/fhir+json"}
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

        Two-step flow:
        1. Location?address-postalcode=ZIP → location IDs
        2. PractitionerRole?specialty=X&location=Location/{id}
           &_include=PractitionerRole:practitioner
           &_include=PractitionerRole:location
        """
        codes = resolve_specialty(specialty)
        nucc_code = codes.get("nucc")
        specialty_display = codes.get("display") or specialty

        if not nucc_code:
            logger.warning(f"No NUCC code for: {specialty}")
            return []

        zip5 = zip_code.strip()[:5]

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                # Step 1: find locations by zip
                location_ids = await self._find_locations(
                    client, "address-postalcode", zip5
                )

                # Fallback: search by state if zip returned nothing
                if not location_ids:
                    state = self._zip_to_state(zip5)
                    if state:
                        print(f"[HealthSpring] Fallback: searching by state {state}")
                        location_ids = await self._find_locations(
                            client, "address-state", state
                        )

                if not location_ids:
                    print("[HealthSpring] No locations found")
                    return []

                # Step 2: find practitioner roles at those locations
                results = await self._search_roles_at_locations(
                    client, nucc_code, location_ids, specialty_display, limit
                )

                results = self._deduplicate(results, limit)
                print(f"[HealthSpring] Final: {len(results)} providers")
                return results

        except Exception as e:
            logger.error(f"HealthSpring search failed: {e}")
            print(f"[HealthSpring] Search failed: {e}")
            return []

    async def _find_locations(
        self,
        client: httpx.AsyncClient,
        param_name: str,
        param_value: str,
    ) -> list[str]:
        """Search Location by address param, return list of Location IDs."""
        print(f"[HealthSpring] Searching Location: {param_name}={param_value}")

        try:
            resp = await client.get(
                f"{HS_BASE}/Location",
                params={param_name: param_value, "_count": "50"},
                headers=HEADERS,
            )
            resp.raise_for_status()
            bundle = resp.json() or {}
        except httpx.HTTPStatusError as e:
            print(f"[HealthSpring] Location search failed: {e.response.status_code} {e.response.text[:200]}")
            return []
        except Exception as e:
            print(f"[HealthSpring] Location search error: {e}")
            return []

        entries = bundle.get("entry", []) or []
        location_ids = []
        for entry in entries:
            resource = (entry or {}).get("resource", {}) or {}
            if resource.get("resourceType") == "Location":
                loc_id = resource.get("id", "")
                if loc_id:
                    location_ids.append(loc_id)

        print(f"[HealthSpring] Found {len(location_ids)} locations")
        return location_ids

    async def _search_roles_at_locations(
        self,
        client: httpx.AsyncClient,
        nucc_code: str,
        location_ids: list[str],
        specialty_display: str,
        limit: int,
    ) -> list[ProviderResult]:
        """
        Search PractitionerRole by specialty at each location with _include.
        Runs searches concurrently for speed, caps at limit.
        """
        # Batch locations to avoid too many concurrent requests
        batch_size = 10
        all_results: list[ProviderResult] = []

        for i in range(0, len(location_ids), batch_size):
            if len(all_results) >= limit:
                break

            batch = location_ids[i : i + batch_size]
            tasks = [
                self._search_roles_for_location(
                    client, nucc_code, loc_id, specialty_display, limit
                )
                for loc_id in batch
            ]
            batch_results = await asyncio.gather(*tasks)

            for results in batch_results:
                all_results.extend(results)

        return all_results

    async def _search_roles_for_location(
        self,
        client: httpx.AsyncClient,
        nucc_code: str,
        location_id: str,
        specialty_display: str,
        limit: int,
    ) -> list[ProviderResult]:
        """Search PractitionerRole at a single location with _include."""
        params = [
            ("specialty", nucc_code),
            ("location", f"Location/{location_id}"),
            ("_include", "PractitionerRole:practitioner"),
            ("_include", "PractitionerRole:location"),
            ("_count", str(min(limit, 50))),
        ]

        try:
            resp = await client.get(
                f"{HS_BASE}/PractitionerRole",
                params=params,
                headers=HEADERS,
            )
            resp.raise_for_status()
            bundle = resp.json() or {}
            return self._parse_bundle(bundle, specialty_display)

        except httpx.HTTPStatusError as e:
            print(f"[HealthSpring] PractitionerRole search failed for Location/{location_id}: {e.response.status_code}")
            return []
        except Exception as e:
            print(f"[HealthSpring] PractitionerRole search error: {e}")
            return []

    # ─────────────────────────────────────────────
    # Bundle parsing (same DaVinci Plan-Net format as UHC)
    # ─────────────────────────────────────────────

    def _parse_bundle(self, bundle: dict, specialty_display: str) -> list[ProviderResult]:
        """Parse a FHIR bundle with _include'd resources."""
        entries = bundle.get("entry", []) or []
        if not entries:
            return []

        practitioners = {}
        locations = {}
        roles = []

        for entry in entries:
            resource = (entry or {}).get("resource", {}) or {}
            res_type = resource.get("resourceType", "")
            res_id = resource.get("id", "")

            if res_type == "PractitionerRole":
                roles.append(resource)
            elif res_type == "Practitioner":
                practitioners[f"Practitioner/{res_id}"] = resource
                full_url = entry.get("fullUrl", "")
                if full_url:
                    practitioners[full_url] = resource
            elif res_type == "Location":
                locations[f"Location/{res_id}"] = resource
                full_url = entry.get("fullUrl", "")
                if full_url:
                    locations[full_url] = resource

        results = []
        for role in roles:
            result = self._build_result(role, practitioners, locations, specialty_display)
            if result:
                results.append(result)

        return results

    def _build_result(
        self,
        role: dict,
        practitioners: dict,
        locations: dict,
        specialty_display: str,
    ) -> ProviderResult | None:
        """Build a ProviderResult from a PractitionerRole + included resources."""
        provider = ProviderResult(carrier="HealthSpring", specialty=specialty_display)

        # ── Practitioner (name, NPI, gender) ──
        prac_ref = role.get("practitioner", {}).get("reference", "")
        prac = practitioners.get(prac_ref)

        if not prac and "/" in prac_ref:
            short_ref = "/".join(prac_ref.split("/")[-2:])
            prac = practitioners.get(short_ref)

        if prac:
            names = prac.get("name", [{}])
            name = names[0] if names else {}
            provider.first_name = " ".join(name.get("given", []))
            provider.last_name = name.get("family", "")
            suffixes = name.get("suffix", [])
            provider.credentials = ", ".join(
                s for s in suffixes if s and s.strip() != "\\n"
            )

            for ident in prac.get("identifier", []):
                system = ident.get("system", "")
                if "npi" in system.lower() or system == "http://hl7.org/fhir/sid/us-npi":
                    provider.npi = ident.get("value", "")
                    break

            provider.gender = prac.get("gender", "")

            if not provider.credentials:
                for qual in prac.get("qualification", []):
                    code = qual.get("code", {})
                    text = code.get("text", "")
                    if text:
                        provider.credentials = text
                        break
        else:
            prac_display = role.get("practitioner", {}).get("display", "")
            if prac_display:
                parts = prac_display.strip().split()
                if len(parts) >= 2:
                    provider.first_name = parts[0]
                    provider.last_name = parts[-1]
                elif parts:
                    provider.last_name = parts[0]
            else:
                return None

        # NPI fallback from role identifiers
        if not provider.npi:
            for ident in role.get("identifier", []):
                system = ident.get("system", "")
                if "npi" in system.lower() or system == "http://hl7.org/fhir/sid/us-npi":
                    provider.npi = ident.get("value", "")
                    break

        # ── Location (address, coords, phone) ──
        loc_refs = role.get("location", [])
        loc = None
        for loc_ref_obj in loc_refs:
            loc_ref = loc_ref_obj.get("reference", "")
            loc = locations.get(loc_ref)
            if not loc and "/" in loc_ref:
                short_ref = "/".join(loc_ref.split("/")[-2:])
                loc = locations.get(short_ref)
            if loc:
                break

        if loc:
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

        # ── Telecom from role ──
        for telecom in role.get("telecom", []):
            system = telecom.get("system", "")
            value = telecom.get("value", "")
            if system == "phone" and not provider.phone:
                provider.phone = value
            elif system == "fax" and not provider.fax:
                provider.fax = value

        # ── Network name ──
        for network_ref in role.get("network", []):
            display = network_ref.get("display", "")
            if display:
                provider.network_name = display
                break

        if not provider.network_name:
            for ext in role.get("extension", []):
                if "network" in ext.get("url", "").lower():
                    provider.network_name = ext.get("valueReference", {}).get("display", "")
                    if provider.network_name:
                        break

        # ── Accepting new patients ──
        provider.accepting_new_patients = self._parse_accepting_patients(role)

        if not provider.last_name:
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
