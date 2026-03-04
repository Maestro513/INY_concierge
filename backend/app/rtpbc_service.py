"""
Aetna Real-Time Pharmacy Benefit Check (RTPBC) Service.

Uses the CARIN RTPBC FHIR IG (hl7.org/fhir/us/carin-rtpbc) to query
real-time drug cost and coverage info for a member at a specific pharmacy.

Flow:
  1. Build a FHIR Claim (use="predetermination") with:
     - Patient (member ID)
     - Coverage (plan/group info)
     - MedicationRequest (drug NDC or RxNorm)
     - Organization (pharmacy NCPDP ID)
     - Practitioner (prescriber NPI, optional)
  2. POST to Aetna's RTPBC $submit endpoint
  3. Parse ClaimResponse for copay, coinsurance, restrictions, alternatives

Auth: OAuth2 client credentials (same pattern as Provider Directory).
      May require Authorization Code flow for member-specific data —
      configurable via AETNA_RTPBC_AUTH_FLOW env var.
"""

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Config from env ──────────────────────────────────────────────────────────

AETNA_RTPBC_CLIENT_ID = os.getenv("AETNA_RTPBC_CLIENT_ID", "")
AETNA_RTPBC_CLIENT_SECRET = os.getenv("AETNA_RTPBC_CLIENT_SECRET", "")

# Sandbox: https://vteapif1.aetna.com/fhirdemo/v1/realtimepharmacybenefitcheckapi
# Production: https://apif1.aetna.com/fhir/v1/realtimepharmacybenefitcheckapi
AETNA_RTPBC_BASE = os.getenv(
    "AETNA_RTPBC_BASE_URL",
    "https://vteapif1.aetna.com/fhirdemo/v1/realtimepharmacybenefitcheckapi",
)
AETNA_RTPBC_TOKEN_URL = os.getenv(
    "AETNA_RTPBC_TOKEN_URL",
    "https://vteapif1.aetna.com/fhirdemo/v1/fhirserver_auth/oauth2/token",
)

HEADERS = {
    "Accept": "application/fhir+json",
    "Content-Type": "application/fhir+json",
}
TIMEOUT = 30.0

# Token cache
_token_cache: dict = {"access_token": "", "expires_at": 0}


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class DrugCostResult:
    """Result from an RTPBC query."""
    drug_name: str = ""
    ndc: str = ""
    rxnorm: str = ""
    pharmacy_name: str = ""
    # Pricing
    patient_pay: float | None = None
    plan_pay: float | None = None
    total_cost: float | None = None
    copay: float | None = None
    coinsurance_pct: float | None = None
    # Coverage
    tier: str = ""
    formulary_status: str = ""  # "formulary", "non-formulary", "not-covered"
    prior_auth_required: bool = False
    step_therapy_required: bool = False
    quantity_limit: str = ""
    # Alternatives
    alternatives: list[dict] = field(default_factory=list)
    # Raw response for debugging
    raw_response: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "drug_name": self.drug_name,
            "ndc": self.ndc,
            "rxnorm": self.rxnorm,
            "pharmacy_name": self.pharmacy_name,
            "patient_pay": self.patient_pay,
            "plan_pay": self.plan_pay,
            "total_cost": self.total_cost,
            "copay": self.copay,
            "coinsurance_pct": self.coinsurance_pct,
            "tier": self.tier,
            "formulary_status": self.formulary_status,
            "prior_auth_required": self.prior_auth_required,
            "step_therapy_required": self.step_therapy_required,
            "quantity_limit": self.quantity_limit,
            "alternatives": self.alternatives,
        }


# ── Auth ─────────────────────────────────────────────────────────────────────

async def _get_access_token(client: httpx.AsyncClient) -> str:
    """Get OAuth2 token via client credentials. Caches until near expiry."""
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["access_token"]

    client_id = os.getenv("AETNA_RTPBC_CLIENT_ID", "") or AETNA_RTPBC_CLIENT_ID
    client_secret = os.getenv("AETNA_RTPBC_CLIENT_SECRET", "") or AETNA_RTPBC_CLIENT_SECRET

    if not client_id or not client_secret:
        raise ValueError("AETNA_RTPBC_CLIENT_ID and AETNA_RTPBC_CLIENT_SECRET must be set")

    token_url = os.getenv("AETNA_RTPBC_TOKEN_URL", "") or AETNA_RTPBC_TOKEN_URL

    print(f"[RTPBC] Fetching OAuth token from {token_url}")

    resp = await client.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "scope": "Public NonPII",
        },
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15.0,
    )
    if resp.status_code != 200:
        print(f"[RTPBC] Token error {resp.status_code}: {resp.text[:500]}")
    resp.raise_for_status()
    token_data = resp.json()

    _token_cache["access_token"] = token_data["access_token"]
    _token_cache["expires_at"] = now + token_data.get("expires_in", 3600)

    print(f"[RTPBC] Token acquired, expires in {token_data.get('expires_in', '?')}s")
    return _token_cache["access_token"]


# ── FHIR Resource Builders ──────────────────────────────────────────────────

def _build_patient(member_id: str, first_name: str = "", last_name: str = "", dob: str = "") -> dict:
    """Build a contained Patient resource."""
    patient = {
        "resourceType": "Patient",
        "id": "patient-1",
        "identifier": [
            {
                "type": {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MB"}]
                },
                "value": member_id,
            }
        ],
    }
    if first_name or last_name:
        name = {}
        if last_name:
            name["family"] = last_name
        if first_name:
            name["given"] = [first_name]
        patient["name"] = [name]
    if dob:
        patient["birthDate"] = dob
    return patient


def _build_coverage(
    member_id: str,
    plan_id: str = "",
    group_id: str = "",
    payer_name: str = "Aetna",
    bin_number: str = "",
    pcn: str = "",
) -> dict:
    """Build a contained Coverage resource."""
    coverage = {
        "resourceType": "Coverage",
        "id": "coverage-1",
        "status": "active",
        "subscriber": {"reference": "#patient-1"},
        "beneficiary": {"reference": "#patient-1"},
        "payor": [{"display": payer_name}],
    }
    identifiers = []
    if plan_id:
        coverage["class"] = [
            {
                "type": {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/coverage-class", "code": "plan"}]
                },
                "value": plan_id,
            }
        ]
    if group_id:
        coverage.setdefault("class", []).append(
            {
                "type": {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/coverage-class", "code": "group"}]
                },
                "value": group_id,
            }
        )
    if bin_number:
        identifiers.append({"type": {"text": "BIN"}, "value": bin_number})
    if pcn:
        identifiers.append({"type": {"text": "PCN"}, "value": pcn})
    if identifiers:
        coverage["identifier"] = identifiers
    return coverage


def _build_medication_request(
    drug_ndc: str = "",
    drug_rxnorm: str = "",
    drug_name: str = "",
    quantity: float = 30.0,
    days_supply: int = 30,
) -> dict:
    """Build a contained MedicationRequest resource."""
    coding = []
    if drug_ndc:
        coding.append({
            "system": "http://hl7.org/fhir/sid/ndc",
            "code": drug_ndc,
            "display": drug_name or drug_ndc,
        })
    if drug_rxnorm:
        coding.append({
            "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
            "code": drug_rxnorm,
            "display": drug_name or drug_rxnorm,
        })

    med_request = {
        "resourceType": "MedicationRequest",
        "id": "med-1",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": coding,
            "text": drug_name,
        },
        "subject": {"reference": "#patient-1"},
        "dosageInstruction": [
            {
                "timing": {
                    "repeat": {
                        "boundsPeriod": {
                            "start": "2026-01-01",  # placeholder
                        }
                    }
                }
            }
        ],
        "dispenseRequest": {
            "quantity": {
                "value": quantity,
                "unit": "each",
            },
            "expectedSupplyDuration": {
                "value": days_supply,
                "unit": "days",
                "system": "http://unitsofmeasure.org",
                "code": "d",
            },
        },
    }
    return med_request


def _build_pharmacy_org(
    ncpdp_id: str = "",
    pharmacy_name: str = "",
    pharmacy_npi: str = "",
) -> dict:
    """Build a contained Organization resource for the pharmacy."""
    org = {
        "resourceType": "Organization",
        "id": "pharmacy-1",
        "type": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/organization-type",
                        "code": "prov",
                        "display": "Healthcare Provider",
                    }
                ]
            }
        ],
    }
    if pharmacy_name:
        org["name"] = pharmacy_name

    identifiers = []
    if ncpdp_id:
        identifiers.append({
            "system": "http://terminology.hl7.org/NamingSystem/NCPDPProviderIdentificationNumber",
            "value": ncpdp_id,
        })
    if pharmacy_npi:
        identifiers.append({
            "system": "http://hl7.org/fhir/sid/us-npi",
            "value": pharmacy_npi,
        })
    if identifiers:
        org["identifier"] = identifiers
    return org


def _build_prescriber(prescriber_npi: str = "", prescriber_name: str = "") -> dict:
    """Build a contained Practitioner for the prescriber."""
    prac = {
        "resourceType": "Practitioner",
        "id": "prescriber-1",
    }
    if prescriber_npi:
        prac["identifier"] = [
            {
                "system": "http://hl7.org/fhir/sid/us-npi",
                "value": prescriber_npi,
            }
        ]
    if prescriber_name:
        parts = prescriber_name.strip().split()
        name = {"family": parts[-1]}
        if len(parts) > 1:
            name["given"] = parts[:-1]
        prac["name"] = [name]
    return prac


def _build_rtpbc_claim(
    member_id: str,
    drug_ndc: str = "",
    drug_rxnorm: str = "",
    drug_name: str = "",
    quantity: float = 30.0,
    days_supply: int = 30,
    pharmacy_ncpdp: str = "",
    pharmacy_name: str = "",
    pharmacy_npi: str = "",
    prescriber_npi: str = "",
    prescriber_name: str = "",
    plan_id: str = "",
    group_id: str = "",
    bin_number: str = "",
    pcn: str = "",
    first_name: str = "",
    last_name: str = "",
    dob: str = "",
) -> dict:
    """
    Build the full FHIR Claim resource for RTPBC predetermination.

    Per CARIN RTPBC IG:
    - Claim.use = "predetermination"
    - Claim.type = pharmacy
    - Claim.provider = Organization (pharmacy)
    - Claim.prescription = MedicationRequest
    - Claim.insurance.coverage = Coverage
    - Claim.careTeam = Practitioner (prescriber)
    """
    # Build contained resources
    patient = _build_patient(member_id, first_name, last_name, dob)
    coverage = _build_coverage(member_id, plan_id, group_id, "Aetna", bin_number, pcn)
    med_request = _build_medication_request(drug_ndc, drug_rxnorm, drug_name, quantity, days_supply)
    pharmacy = _build_pharmacy_org(pharmacy_ncpdp, pharmacy_name, pharmacy_npi)
    prescriber = _build_prescriber(prescriber_npi, prescriber_name)

    # Build medication coding for item.productOrService
    product_coding = []
    if drug_ndc:
        product_coding.append({
            "system": "http://hl7.org/fhir/sid/ndc",
            "code": drug_ndc,
        })
    if drug_rxnorm:
        product_coding.append({
            "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
            "code": drug_rxnorm,
        })

    claim = {
        "resourceType": "Claim",
        "id": str(uuid.uuid4()),
        "meta": {
            "profile": [
                "http://hl7.org/fhir/us/carin-rtpbc/StructureDefinition/rtpbc-request-claim"
            ]
        },
        "status": "active",
        "type": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                    "code": "pharmacy",
                    "display": "Pharmacy",
                }
            ]
        },
        "use": "predetermination",
        "patient": {"reference": "#patient-1"},
        "created": "2026-01-01",
        "provider": {"reference": "#pharmacy-1"},
        "priority": {
            "coding": [
                {"system": "http://terminology.hl7.org/CodeSystem/processpriority", "code": "normal"}
            ]
        },
        "prescription": {"reference": "#med-1"},
        "insurance": [
            {
                "sequence": 1,
                "focal": True,
                "coverage": {"reference": "#coverage-1"},
            }
        ],
        "careTeam": [
            {
                "sequence": 1,
                "provider": {"reference": "#prescriber-1"},
                "role": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/claimcareteamrole",
                            "code": "primary",
                        }
                    ]
                },
            }
        ],
        "item": [
            {
                "sequence": 1,
                "careTeamSequence": [1],
                "productOrService": {
                    "coding": product_coding,
                    "text": drug_name,
                },
                "quantity": {
                    "value": quantity,
                    "unit": "each",
                },
            }
        ],
        "contained": [patient, coverage, med_request, pharmacy, prescriber],
    }

    return claim


# ── Response Parsing ─────────────────────────────────────────────────────────

def _parse_claim_response(response: dict, drug_name: str = "") -> DrugCostResult:
    """Parse a FHIR ClaimResponse into a DrugCostResult."""
    result = DrugCostResult(drug_name=drug_name, raw_response=response)

    # Parse adjudication from items
    items = response.get("item", [])
    for item in items:
        for adj in item.get("adjudication", []):
            category = adj.get("category", {})
            code = ""
            for coding in category.get("coding", []):
                code = coding.get("code", "")
                break

            amount = adj.get("amount", {})
            value = amount.get("value")

            if code in ("submitted", "drugcost"):
                result.total_cost = value
            elif code in ("benefit", "paidtoprovider"):
                result.plan_pay = value
            elif code in ("copay",):
                result.copay = value
            elif code in ("coinsurance",):
                result.coinsurance_pct = value
            elif code in ("patientpay", "deductible"):
                if result.patient_pay is None:
                    result.patient_pay = value
                elif value is not None:
                    result.patient_pay += value

        # Check for benefit restrictions in extensions
        for ext in item.get("extension", []):
            url = ext.get("url", "")
            if "benefitRestriction" in url:
                restriction_coding = ext.get("valueCodeableConcept", {}).get("coding", [])
                for rc in restriction_coding:
                    rc_code = rc.get("code", "")
                    if rc_code == "prior-auth":
                        result.prior_auth_required = True
                    elif rc_code == "step-therapy":
                        result.step_therapy_required = True
                    elif "quantity" in rc_code:
                        result.quantity_limit = rc.get("display", "Quantity limit applies")

    # Parse addItem for alternatives
    for add_item in response.get("addItem", []):
        alt = {}
        product = add_item.get("productOrService", {})
        alt["drug_name"] = product.get("text", "")
        for coding in product.get("coding", []):
            if "ndc" in coding.get("system", ""):
                alt["ndc"] = coding.get("code", "")
            elif "rxnorm" in coding.get("system", ""):
                alt["rxnorm"] = coding.get("code", "")

        for adj in add_item.get("adjudication", []):
            category = adj.get("category", {})
            code = ""
            for coding in category.get("coding", []):
                code = coding.get("code", "")
                break
            amount = adj.get("amount", {})
            value = amount.get("value")
            if code in ("patientpay", "copay"):
                alt["patient_pay"] = value
            elif code in ("submitted", "drugcost"):
                alt["total_cost"] = value

        if alt.get("drug_name"):
            result.alternatives.append(alt)

    # Check top-level extensions for formulary tier
    for ext in response.get("extension", []):
        url = ext.get("url", "")
        if "tier" in url.lower():
            result.tier = ext.get("valueString", ext.get("valueCodeableConcept", {}).get("text", ""))

    # Determine formulary status from response outcome
    outcome = response.get("outcome", "")
    if outcome == "complete":
        result.formulary_status = "formulary"
    elif outcome == "error":
        result.formulary_status = "not-covered"

    return result


# ── Main API ─────────────────────────────────────────────────────────────────

async def check_drug_cost(
    member_id: str,
    drug_ndc: str = "",
    drug_rxnorm: str = "",
    drug_name: str = "",
    quantity: float = 30.0,
    days_supply: int = 30,
    pharmacy_ncpdp: str = "",
    pharmacy_name: str = "",
    pharmacy_npi: str = "",
    prescriber_npi: str = "",
    prescriber_name: str = "",
    plan_id: str = "",
    group_id: str = "",
    bin_number: str = "",
    pcn: str = "",
    first_name: str = "",
    last_name: str = "",
    dob: str = "",
) -> DrugCostResult | None:
    """
    Check real-time drug cost for a member at a specific pharmacy.

    Args:
        member_id: Aetna member ID
        drug_ndc: NDC code (11-digit)
        drug_rxnorm: RxNorm code (alternative to NDC)
        drug_name: Display name of the drug
        quantity: Number of units
        days_supply: Days supply for the fill
        pharmacy_ncpdp: Pharmacy NCPDP ID
        pharmacy_name: Pharmacy display name
        pharmacy_npi: Pharmacy NPI
        prescriber_npi: Prescriber NPI (optional but recommended)
        prescriber_name: Prescriber name
        plan_id: Insurance plan ID
        group_id: Insurance group number
        bin_number: Rx BIN number
        pcn: Processor Control Number
        first_name: Member first name
        last_name: Member last name
        dob: Member date of birth (YYYY-MM-DD)

    Returns:
        DrugCostResult with pricing and coverage info, or None on failure.
    """
    if not drug_ndc and not drug_rxnorm:
        logger.error("Either drug_ndc or drug_rxnorm is required")
        return None

    claim = _build_rtpbc_claim(
        member_id=member_id,
        drug_ndc=drug_ndc,
        drug_rxnorm=drug_rxnorm,
        drug_name=drug_name,
        quantity=quantity,
        days_supply=days_supply,
        pharmacy_ncpdp=pharmacy_ncpdp,
        pharmacy_name=pharmacy_name,
        pharmacy_npi=pharmacy_npi,
        prescriber_npi=prescriber_npi,
        prescriber_name=prescriber_name,
        plan_id=plan_id,
        group_id=group_id,
        bin_number=bin_number,
        pcn=pcn,
        first_name=first_name,
        last_name=last_name,
        dob=dob,
    )

    base_url = os.getenv("AETNA_RTPBC_BASE_URL", "") or AETNA_RTPBC_BASE

    print(f"[RTPBC] Checking cost: drug={drug_name or drug_ndc}, pharmacy={pharmacy_name or pharmacy_ncpdp}")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            token = await _get_access_token(client)
            auth_headers = {
                **HEADERS,
                "Authorization": f"Bearer {token}",
            }

            # POST Claim to $submit or /Claim endpoint
            # Try $submit first (CARIN IG standard), fall back to /Claim
            submit_url = f"{base_url}/Claim/$submit"
            print(f"[RTPBC] POST {submit_url}")

            resp = await client.post(
                submit_url,
                json=claim,
                headers=auth_headers,
            )

            if resp.status_code == 404:
                # Fallback: POST to /Claim directly
                fallback_url = f"{base_url}/Claim"
                print(f"[RTPBC] $submit not found, trying {fallback_url}")
                resp = await client.post(
                    fallback_url,
                    json=claim,
                    headers=auth_headers,
                )

            if resp.status_code != 200:
                print(f"[RTPBC] Error {resp.status_code}: {resp.text[:500]}")
                resp.raise_for_status()

            response_data = resp.json()
            resource_type = response_data.get("resourceType", "")

            print(f"[RTPBC] Response: {resource_type}")

            if resource_type == "ClaimResponse":
                result = _parse_claim_response(response_data, drug_name)
                result.ndc = drug_ndc
                result.rxnorm = drug_rxnorm
                result.pharmacy_name = pharmacy_name
                print(
                    f"[RTPBC] Result: patient_pay=${result.patient_pay}, "
                    f"formulary={result.formulary_status}, "
                    f"prior_auth={result.prior_auth_required}"
                )
                return result

            elif resource_type == "Bundle":
                # Response might be a Bundle containing ClaimResponse
                for entry in response_data.get("entry", []):
                    resource = entry.get("resource", {})
                    if resource.get("resourceType") == "ClaimResponse":
                        result = _parse_claim_response(resource, drug_name)
                        result.ndc = drug_ndc
                        result.rxnorm = drug_rxnorm
                        result.pharmacy_name = pharmacy_name
                        return result

            elif resource_type == "OperationOutcome":
                issues = response_data.get("issue", [])
                for issue in issues:
                    severity = issue.get("severity", "")
                    details = issue.get("diagnostics", issue.get("details", {}).get("text", ""))
                    print(f"[RTPBC] OperationOutcome: {severity} — {details}")
                return None

            print(f"[RTPBC] Unexpected response type: {resource_type}")
            return None

    except httpx.HTTPStatusError as e:
        # Try to parse OperationOutcome from error response
        try:
            error_body = e.response.json()
            if error_body.get("resourceType") == "OperationOutcome":
                for issue in error_body.get("issue", []):
                    print(f"[RTPBC] Error: {issue.get('diagnostics', issue.get('details', {}).get('text', ''))}")
        except Exception:
            pass
        logger.error(f"RTPBC request failed: {e}")
        print(f"[RTPBC] HTTP error: {e}")
        return None
    except Exception as e:
        logger.error(f"RTPBC request failed: {e}")
        print(f"[RTPBC] Error: {e}")
        return None


async def check_drug_costs_batch(
    member_id: str,
    drugs: list[dict],
    pharmacy_ncpdp: str = "",
    pharmacy_name: str = "",
    pharmacy_npi: str = "",
    plan_id: str = "",
    group_id: str = "",
    bin_number: str = "",
    pcn: str = "",
    first_name: str = "",
    last_name: str = "",
    dob: str = "",
) -> list[DrugCostResult]:
    """
    Check costs for multiple drugs at the same pharmacy.

    Each drug dict should have: ndc, rxnorm (optional), name, quantity, days_supply.
    """
    import asyncio

    results = []
    for drug in drugs:
        result = await check_drug_cost(
            member_id=member_id,
            drug_ndc=drug.get("ndc", ""),
            drug_rxnorm=drug.get("rxnorm", ""),
            drug_name=drug.get("name", ""),
            quantity=drug.get("quantity", 30.0),
            days_supply=drug.get("days_supply", 30),
            pharmacy_ncpdp=pharmacy_ncpdp,
            pharmacy_name=pharmacy_name,
            pharmacy_npi=pharmacy_npi,
            plan_id=plan_id,
            group_id=group_id,
            bin_number=bin_number,
            pcn=pcn,
            first_name=first_name,
            last_name=last_name,
            dob=dob,
        )
        if result:
            results.append(result)

    return results
