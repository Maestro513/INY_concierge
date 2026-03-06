"""
Aetna Provider Directory FHIR Adapter.

Uses Aetna's DaVinci PDEX Plan Net 1.1.0 implementation.
Supports _include queries similar to UHC — single call for PractitionerRole
with included Practitioner and Location resources.

Auth: OAuth2 client credentials (Basic Auth header) → Bearer token.
Base: https://apif1.aetna.com/fhir/v1/providerdirectorydata
Token: https://apif1.aetna.com/fhir/v1/fhirserver_auth/oauth2/token
Scope: Public NonPII
"""

import logging
import os
import time

import httpx

from .base import BaseAdapter, ProviderResult, resolve_specialty

logger = logging.getLogger(__name__)

# Config from env
AETNA_CLIENT_ID = os.getenv("AETNA_CLIENT_ID", "")
AETNA_CLIENT_SECRET = os.getenv("AETNA_CLIENT_SECRET", "")

AETNA_BASE = os.getenv(
    "AETNA_BASE_URL",
    "https://apif1.aetna.com/fhir/v1/providerdirectorydata",
)
AETNA_TOKEN_URL = os.getenv(
    "AETNA_TOKEN_URL",
    "https://apif1.aetna.com/fhir/v1/fhirserver_auth/oauth2/token",
)

HEADERS = {"Accept": "application/fhir+json"}
TIMEOUT = 30.0

# Cache the OAuth token in memory
_token_cache = {"access_token": "", "expires_at": 0}


async def _get_access_token(client: httpx.AsyncClient) -> str:
    """Get OAuth2 token via client credentials grant with Basic Auth. Caches until expiry."""
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["access_token"]

    # Re-read at runtime so dotenv has a chance to load
    client_id = os.getenv("AETNA_CLIENT_ID", "") or AETNA_CLIENT_ID
    client_secret = os.getenv("AETNA_CLIENT_SECRET", "") or AETNA_CLIENT_SECRET

    if not client_id or not client_secret:
        raise ValueError("AETNA_CLIENT_ID and AETNA_CLIENT_SECRET must be set")

    logger.debug(f"[AETNA] Fetching OAuth token from {AETNA_TOKEN_URL}")

    resp = await client.post(
        AETNA_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "scope": "Public NonPII",
        },
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15.0,
    )
    if resp.status_code != 200:
        logger.warning(f"[AETNA] Token error {resp.status_code}: {resp.text[:500]}")
    resp.raise_for_status()
    token_data = resp.json()

    _token_cache["access_token"] = token_data["access_token"]
    _token_cache["expires_at"] = now + token_data.get("expires_in", 3600)

    logger.debug(f"[AETNA] Token acquired, expires in {token_data.get('expires_in', '?')}s")
    return _token_cache["access_token"]


class AetnaAdapter(BaseAdapter):
    carrier_name = "Aetna"
    base_url = AETNA_BASE

    async def search_providers(
        self,
        specialty: str,
        zip_code: str,
        plan_name: str = "",
        limit: int = 50,
    ) -> list[ProviderResult]:
        """
        Find providers by specialty near a zip code.

        Uses PractitionerRole with _include to get Practitioner + Location
        in a single bundle (DaVinci Plan Net style).
        Falls back to state-level search if zip returns nothing.
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
                token = await _get_access_token(client)
                auth_headers = {
                    **HEADERS,
                    "Authorization": f"Bearer {token}",
                }

                # Primary: search by zip with _include
                results = await self._search_with_include(
                    client, auth_headers, nucc_code, zip5, specialty_display, limit
                )

                # Fallback: search by state if zip returned nothing
                if not results:
                    results = await self._search_by_state(
                        client, auth_headers, nucc_code, zip5, specialty_display, limit
                    )

                results = self._deduplicate(results, limit)
                logger.debug(f"[AETNA] Final: {len(results)} providers")
                return results

        except Exception as e:
            logger.error(f"Aetna search failed: {e}")
            logger.warning(f"[AETNA] Search failed: {e}")
            return []

    async def _search_with_include(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        nucc_code: str,
        zip_code: str,
        specialty_display: str,
        limit: int,
    ) -> list[ProviderResult]:
        """
        Primary search: PractitionerRole with specialty + location zip + _include.
        Returns Practitioner and Location resources in the same bundle.
        """
        logger.debug(f"[AETNA] Searching PractitionerRole: specialty={nucc_code}, zip={zip_code}")

        params = [
            ("specialty", nucc_code),
            ("location.address-postalcode", zip_code),
            ("_include", "PractitionerRole:practitioner"),
            ("_include", "PractitionerRole:location"),
            ("_count", str(min(limit, 100))),
        ]

        try:
            resp = await client.get(
                f"{AETNA_BASE}/PractitionerRole",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            bundle = resp.json() or {}
            return self._parse_bundle(bundle, specialty_display)

        except httpx.HTTPStatusError as e:
            logger.warning(f"[AETNA] PractitionerRole search failed: {e.response.status_code} {e.response.text[:200]}")
            # Fallback: try without _include (some endpoints don't support it)
            return await self._search_without_include(
                client, headers, nucc_code, zip_code, specialty_display, limit
            )
        except Exception as e:
            logger.warning(f"[AETNA] PractitionerRole search error: {e}")
            return []

    async def _search_without_include(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        nucc_code: str,
        zip_code: str,
        specialty_display: str,
        limit: int,
    ) -> list[ProviderResult]:
        """
        Fallback: search PractitionerRole without _include, then fetch
        referenced Practitioner and Location resources individually.
        Similar to Humana's multi-step approach.
        """
        logger.debug("[AETNA] Fallback: searching without _include")

        params = [
            ("specialty", nucc_code),
            ("location.address-postalcode", zip_code),
            ("_count", str(min(limit, 100))),
        ]

        try:
            resp = await client.get(
                f"{AETNA_BASE}/PractitionerRole",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            bundle = resp.json() or {}
            entries = bundle.get("entry", []) or []

            if not entries:
                return []

            # Collect references to fetch
            roles = []
            prac_refs = set()
            loc_refs = set()

            for entry in entries:
                resource = (entry or {}).get("resource", {}) or {}
                if resource.get("resourceType") == "PractitionerRole":
                    roles.append(resource)
                    prac_ref = resource.get("practitioner", {}).get("reference", "")
                    if prac_ref:
                        prac_refs.add(prac_ref)
                    for loc in resource.get("location", []):
                        loc_ref = loc.get("reference", "")
                        if loc_ref:
                            loc_refs.add(loc_ref)

            logger.debug(f"[AETNA] Got {len(roles)} roles, fetching {len(prac_refs)} practitioners and {len(loc_refs)} locations")

            # Fetch practitioners and locations
            practitioners = {}
            locations = {}

            import asyncio

            async def fetch_resource(ref: str) -> tuple[str, dict | None]:
                url = ref if ref.startswith("http") else f"{AETNA_BASE}/{ref}"
                try:
                    r = await client.get(url, headers=headers)
                    r.raise_for_status()
                    return ref, r.json()
                except Exception:
                    return ref, None

            # Fetch in batches of 10
            for refs, target in [(prac_refs, practitioners), (loc_refs, locations)]:
                ref_list = list(refs)
                for i in range(0, len(ref_list), 10):
                    batch = ref_list[i:i + 10]
                    tasks = [fetch_resource(ref) for ref in batch]
                    results = await asyncio.gather(*tasks)
                    for ref, data in results:
                        if data:
                            target[ref] = data
                            res_id = data.get("id", "")
                            res_type = data.get("resourceType", "")
                            if res_id:
                                target[f"{res_type}/{res_id}"] = data

            return self._build_results_from_roles(roles, practitioners, locations, specialty_display)

        except Exception as e:
            logger.warning(f"[AETNA] Fallback search failed: {e}")
            return []

    async def _search_by_state(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        nucc_code: str,
        zip_code: str,
        specialty_display: str,
        limit: int,
    ) -> list[ProviderResult]:
        """Fallback: search by state instead of zip."""
        state = self._zip_to_state(zip_code)
        if not state:
            return []

        logger.debug(f"[AETNA] Fallback: searching by state {state}")

        params = [
            ("specialty", nucc_code),
            ("location.address-state", state),
            ("_include", "PractitionerRole:practitioner"),
            ("_include", "PractitionerRole:location"),
            ("_count", str(min(limit, 50))),
        ]

        try:
            resp = await client.get(
                f"{AETNA_BASE}/PractitionerRole",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            bundle = resp.json() or {}
            return self._parse_bundle(bundle, specialty_display)

        except Exception as e:
            logger.warning(f"[AETNA] State search failed: {e}")
            return []

    # ─────────────────────────────────────────────
    # Bundle parsing
    # ─────────────────────────────────────────────

    def _parse_bundle(self, bundle: dict, specialty_display: str) -> list[ProviderResult]:
        """
        Parse a FHIR bundle with _include'd resources.
        Indexes Practitioner and Location by reference, then builds
        results from PractitionerRole entries.
        """
        entries = bundle.get("entry", []) or []
        total = bundle.get("total", len(entries))
        logger.debug(f"[AETNA] Bundle: {len(entries)} entries (total available: {total})")

        if not entries:
            return []

        # Index included resources by reference
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

        logger.debug(
            f"[AETNA] Parsed: {len(roles)} roles, "
            f"{len(set(id(v) for v in practitioners.values()))} practitioners, "
            f"{len(set(id(v) for v in locations.values()))} locations"
        )

        return self._build_results_from_roles(roles, practitioners, locations, specialty_display)

    def _build_results_from_roles(
        self,
        roles: list[dict],
        practitioners: dict,
        locations: dict,
        specialty_display: str,
    ) -> list[ProviderResult]:
        """Build ProviderResult list from roles + indexed resources."""
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
        provider = ProviderResult(carrier="Aetna", specialty=specialty_display)

        # ── Practitioner (name, NPI, gender) ──
        prac_ref = role.get("practitioner", {}).get("reference", "")
        prac = practitioners.get(prac_ref)

        # Try short reference if full URL didn't match
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

            # NPI from identifiers
            for ident in prac.get("identifier", []):
                system = ident.get("system", "")
                if "npi" in system.lower() or system == "http://hl7.org/fhir/sid/us-npi":
                    provider.npi = ident.get("value", "")
                    break

            provider.gender = prac.get("gender", "")

            # Qualifications as fallback credentials
            if not provider.credentials:
                for qual in prac.get("qualification", []):
                    code = qual.get("code", {})
                    text = code.get("text", "")
                    if text:
                        provider.credentials = text
                        break
        else:
            # Fallback: display name from reference
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

        # Also check extensions for network
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
                # Nested extension style
                for sub_ext in ext.get("extension", []):
                    if sub_ext.get("url") == "acceptingPatients":
                        concept = sub_ext.get("valueCodeableConcept", {})
                        codings = concept.get("coding", [])
                        if codings:
                            return codings[0].get("code", "") == "newpt"
                # Direct value style
                val = ext.get("valueBoolean")
                if val is not None:
                    return val
        return None

    def _zip_to_state(self, zip_code: str) -> str | None:
        """Zip prefix → state. Reuses Humana's mapping."""
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
