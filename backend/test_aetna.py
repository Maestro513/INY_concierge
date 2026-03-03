"""Quick test for the Aetna FHIR adapter."""

import asyncio
import sys
import os

# Ensure app is importable
sys.path.insert(0, os.path.dirname(__file__))

from app.providers.adapters.aetna import AetnaAdapter


async def test():
    adapter = AetnaAdapter()
    results = await adapter.search_providers(
        specialty="cardiologist",
        zip_code="33012",
        limit=10,
    )
    print(f"\nGot {len(results)} providers")
    for r in results[:3]:
        d = r.to_dict()
        print(f"  {d['first_name']} {d['last_name']}, {d['credentials']} — {d['city']}, {d['state']} {d['zip_code']}")
        print(f"    NPI: {d['npi']}  Phone: {d['phone']}  Network: {d['network_name']}")


if __name__ == "__main__":
    asyncio.run(test())
