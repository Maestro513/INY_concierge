"""
UHC (UnitedHealthcare) Provider Directory FHIR Adapter.

Uses Optum's FLEX platform (DaVinci PDEX Plan Net).
Much simpler than Humana — supports chained queries and _include:

Single call:
  GET /PractitionerRole?specialty=NUCC&location.address-postalcode=ZIP
      &_include=PractitionerRole:practitioner
      &_include=PractitionerRole:location

Returns PractitionerRole + Practitioner + Location all in one bundle.

Auth: OAuth2 client credentials → Bearer token.
Base: https://flex.optum.com/fhirpublic/R4
Token: https://flex.optum.com/authz/{payer}/oauth/token
"""

import asyncio
import logging
import os
import time

import httpx

from .base import BaseAdapter, ProviderResult, resolve_specialty

logger = logging.getLogger(__name__)

# Config from env
UHC_PAYER_ID = os.getenv("UHC_PAYER_ID", "hsid")
UHC_CLIENT_ID = os.getenv("UHC_CLIENT_ID", "")
UHC_CLIENT_SECRET = os.getenv("UHC_CLIENT_SECRET", "")

UHC_BASE = os.getenv("UHC_BASE_URL", "https://flex.optum.com/fhirpublic/R4")
UHC_TOKEN_URL = f"https://flex.optum.com/authz/{UHC_PAYER_ID}/oauth/token"

HEADERS = {"Accept": "application/fhir+json"}
TIMEOUT = 30.0

# Cache the OAuth token in memory (with lock to prevent concurrent refresh storms)
_token_cache = {"access_token": "", "expires_at": 0}
_token_lock = asyncio.Lock()


async def _get_access_token(client: httpx.AsyncClient) -> str:
    """Get OAuth2 token via client credentials grant. Caches until expiry."""
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["access_token"]

    async with _token_lock:
        # Double-check after acquiring lock
        now = time.time()
        if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
            return _token_cache["access_token"]

        if not UHC_CLIENT_ID or not UHC_CLIENT_SECRET:
            raise ValueError("UHC_CLIENT_ID and UHC_CLIENT_SECRET must be set")

        logger.debug(f"[UHC] Fetching OAuth token from {UHC_TOKEN_URL}")
        scope = os.getenv(
            "UHC_SCOPE",
            "public/HealthcareService.read public/InsurancePlan.read "
            "public/Location.read public/Organization.read "
            "public/OrganizationAffiliation.read public/Practitioner.read "
            "public/PractitionerRole.read public/Network.read "
            "public/Endpoint.read",
        )
        resp = await client.post(
            UHC_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": UHC_CLIENT_ID,
                "client_secret": UHC_CLIENT_SECRET,
                "scope": scope,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15.0,
        )
        if resp.status_code != 200:
            logger.warning(f"[UHC] Token error {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
        token_data = resp.json()

        _token_cache["access_token"] = token_data["access_token"]
        _token_cache["expires_at"] = now + token_data.get("expires_in", 3600)

        logger.debug(f"[UHC] Token acquired, expires in {token_data.get('expires_in', '?')}s")
        return _token_cache["access_token"]


class UHCAdapter(BaseAdapter):
    carrier_name = "UHC"
    base_url = UHC_BASE

    async def search_providers(
        self,
        specialty: str,
        zip_code: str,
        plan_name: str = "",
        limit: int = 50,
    ) -> list[ProviderResult]:
        """
        Find providers by specialty near a zip code.

        Single-call flow using chained queries + _include:
        PractitionerRole?specialty=X&location.address-postalcode=ZIP
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
                token = await _get_access_token(client)
                auth_headers = {
                    **HEADERS,
                    "Authorization": f"Bearer {token}",
                }

                # Single call with _include — gets everything in one bundle
                results = await self._search_with_include(
                    client, auth_headers, nucc_code, zip5, specialty_display, limit
                )

                # Fallback: try state-level search if zip returned nothing
                if not results:
                    results = await self._search_by_state(
                        client, auth_headers, nucc_code, zip5, specialty_display, limit
                    )

                results = self._deduplicate(results, limit)
                logger.debug(f"[UHC] Final: {len(results)} providers")
                return results

        except Exception as e:
            logger.error(f"UHC search failed: {e}")
            logger.warning(f"[UHC] Search failed: {e}")
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
        Primary search: PractitionerRole with chained location + _include.
        Returns all data in a single bundle.
        """
        logger.debug(f"[UHC] Searching PractitionerRole: specialty={nucc_code}, zip={zip_code}")

        params = [
            ("specialty", nucc_code),
            ("location.address-postalcode", zip_code),
            ("_include", "PractitionerRole:practitioner"),
            ("_include", "PractitionerRole:location"),
            ("_count", str(min(limit, 100))),
        ]

        try:
            resp = await client.get(
                f"{UHC_BASE}/PractitionerRole",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            bundle = resp.json() or {}
            return self._parse_bundle(bundle, specialty_display)

        except httpx.HTTPStatusError as e:
            logger.warning(f"[UHC] PractitionerRole search failed: {e.response.status_code} {e.response.text[:200]}")
            return []
        except Exception as e:
            logger.warning(f"[UHC] PractitionerRole search error: {e}")
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

        logger.debug(f"[UHC] Fallback: searching by state {state}")

        params = [
            ("specialty", nucc_code),
            ("location.address-state", state),
            ("_include", "PractitionerRole:practitioner"),
            ("_include", "PractitionerRole:location"),
            ("_count", str(min(limit, 50))),
        ]

        try:
            resp = await client.get(
                f"{UHC_BASE}/PractitionerRole",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            bundle = resp.json() or {}
            return self._parse_bundle(bundle, specialty_display)

        except Exception as e:
            logger.warning(f"[UHC] State search failed: {e}")
            return []

    # ─────────────────────────────────────────────
    # Bundle parsing
    # ─────────────────────────────────────────────

    def _parse_bundle(self, bundle: dict, specialty_display: str) -> list[ProviderResult]:
        """
        Parse a FHIR bundle with _include'd resources.
        The bundle contains PractitionerRole, Practitioner, and Location
        entries all mixed together. We index the included resources first,
        then build results from the PractitionerRole entries.
        """
        entries = bundle.get("entry", []) or []
        total = bundle.get("total", len(entries))
        logger.debug(f"[UHC] Bundle: {len(entries)} entries (total available: {total})")

        if not entries:
            return []

        # Index included resources by reference
        practitioners = {}  # "Practitioner/{id}" → resource
        locations = {}      # "Location/{id}" → resource

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

        logger.debug(f"[UHC] Parsed: {len(roles)} roles, {len(set(id(v) for v in practitioners.values()))} practitioners, {len(set(id(v) for v in locations.values()))} locations")

        # Build results from roles
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
        provider = ProviderResult(carrier="UHC", specialty=specialty_display)

        # ── Practitioner (name, NPI, gender) ──
        prac_ref = role.get("practitioner", {}).get("reference", "")
        prac = practitioners.get(prac_ref)

        # Try just the reference path if full URL didn't match
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
