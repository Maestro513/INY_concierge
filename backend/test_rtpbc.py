"""
Test script for Aetna RTPBC (Real-Time Pharmacy Benefit Check) service.

Usage:
    python test_rtpbc.py

Requires AETNA_RTPBC_CLIENT_ID and AETNA_RTPBC_CLIENT_SECRET in .env
(or environment variables).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.rtpbc_service import check_drug_cost, check_drug_costs_batch


async def test_single_drug():
    """Test a single drug cost check."""
    print("=" * 60)
    print("Test 1: Single drug cost check")
    print("=" * 60)

    result = await check_drug_cost(
        member_id="TEST_MEMBER_001",
        drug_ndc="00002771001",       # Atorvastatin 20mg (example NDC)
        drug_name="Atorvastatin 20mg",
        quantity=30,
        days_supply=30,
        pharmacy_ncpdp="0000001",     # Test pharmacy
        pharmacy_name="CVS Pharmacy",
        plan_id="TEST_PLAN",
        first_name="Jane",
        last_name="Doe",
        dob="1955-01-15",
    )

    if result:
        d = result.to_dict()
        print(f"\n  Drug: {d['drug_name']}")
        print(f"  Patient Pay: ${d['patient_pay']}")
        print(f"  Plan Pay: ${d['plan_pay']}")
        print(f"  Total Cost: ${d['total_cost']}")
        print(f"  Copay: ${d['copay']}")
        print(f"  Formulary: {d['formulary_status']}")
        print(f"  Prior Auth: {d['prior_auth_required']}")
        print(f"  Step Therapy: {d['step_therapy_required']}")
        if d['alternatives']:
            print(f"  Alternatives:")
            for alt in d['alternatives']:
                print(f"    - {alt.get('drug_name', '?')}: ${alt.get('patient_pay', '?')}")
    else:
        print("\n  No result returned (check credentials and sandbox access)")

    return result


async def test_batch_drugs():
    """Test batch drug cost check."""
    print("\n" + "=" * 60)
    print("Test 2: Batch drug cost check")
    print("=" * 60)

    drugs = [
        {
            "ndc": "00002771001",
            "name": "Atorvastatin 20mg",
            "quantity": 30,
            "days_supply": 30,
        },
        {
            "ndc": "00002140280",
            "name": "Insulin Lispro 100 units/mL",
            "quantity": 10,
            "days_supply": 30,
        },
        {
            "ndc": "00003089421",
            "name": "Eliquis 5mg",
            "quantity": 60,
            "days_supply": 30,
        },
    ]

    results = await check_drug_costs_batch(
        member_id="TEST_MEMBER_001",
        drugs=drugs,
        pharmacy_ncpdp="0000001",
        pharmacy_name="CVS Pharmacy",
        plan_id="TEST_PLAN",
        first_name="Jane",
        last_name="Doe",
        dob="1955-01-15",
    )

    print(f"\n  Got {len(results)} results:")
    for r in results:
        d = r.to_dict()
        print(f"    {d['drug_name']}: patient_pay=${d['patient_pay']}, formulary={d['formulary_status']}")

    return results


async def test_claim_structure():
    """Test that the FHIR Claim resource is built correctly."""
    print("\n" + "=" * 60)
    print("Test 3: Verify Claim resource structure")
    print("=" * 60)

    from app.rtpbc_service import _build_rtpbc_claim
    import json

    claim = _build_rtpbc_claim(
        member_id="TEST123",
        drug_ndc="00002771001",
        drug_rxnorm="259255",
        drug_name="Atorvastatin 20mg",
        quantity=30,
        days_supply=30,
        pharmacy_ncpdp="1234567",
        pharmacy_name="CVS Pharmacy",
        prescriber_npi="1234567890",
        prescriber_name="Dr. Smith",
        plan_id="H1036-077",
        group_id="GRP001",
        first_name="Jane",
        last_name="Doe",
        dob="1955-01-15",
    )

    # Validate structure
    assert claim["resourceType"] == "Claim", "resourceType should be Claim"
    assert claim["use"] == "predetermination", "use should be predetermination"
    assert claim["type"]["coding"][0]["code"] == "pharmacy", "type should be pharmacy"
    assert claim["patient"]["reference"] == "#patient-1", "patient ref"
    assert claim["provider"]["reference"] == "#pharmacy-1", "provider should be pharmacy"
    assert claim["prescription"]["reference"] == "#med-1", "prescription ref"
    assert len(claim["insurance"]) == 1, "should have 1 insurance"
    assert len(claim["careTeam"]) == 1, "should have 1 careTeam"
    assert len(claim["item"]) == 1, "should have 1 item"
    assert len(claim["contained"]) == 5, "should have 5 contained resources"

    # Check contained resource types
    contained_types = {r["resourceType"] for r in claim["contained"]}
    expected = {"Patient", "Coverage", "MedicationRequest", "Organization", "Practitioner"}
    assert contained_types == expected, f"Expected {expected}, got {contained_types}"

    print("  All structural validations passed!")
    print(f"\n  Full Claim JSON ({len(json.dumps(claim))} bytes):")
    print(json.dumps(claim, indent=2)[:2000])
    if len(json.dumps(claim)) > 2000:
        print("  ... (truncated)")


async def main():
    # Always run structure test (no API call needed)
    await test_claim_structure()

    # Only run API tests if credentials are configured
    client_id = os.getenv("AETNA_RTPBC_CLIENT_ID", "")
    client_secret = os.getenv("AETNA_RTPBC_CLIENT_SECRET", "")

    if client_id and client_secret:
        await test_single_drug()
        await test_batch_drugs()
    else:
        print("\n" + "=" * 60)
        print("Skipping API tests — AETNA_RTPBC_CLIENT_ID/SECRET not set")
        print("Set these in .env to test against the sandbox")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
