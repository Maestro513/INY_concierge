"""
Base adapter class for carrier FHIR Provider Directory APIs.
All carrier adapters inherit from this and implement search_providers().
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProviderResult:
    """Standardized provider result across all carriers."""
    npi: str = ""
    first_name: str = ""
    last_name: str = ""
    credentials: str = ""
    specialty: str = ""
    specialty_code: str = ""
    phone: str = ""
    fax: str = ""
    address_line: str = ""
    suite: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gender: str = ""
    accepting_new_patients: Optional[bool] = None
    network_name: str = ""
    carrier: str = ""
    # Enrichment fields (filled later)
    distance_miles: Optional[float] = None
    google_rating: Optional[float] = None
    google_review_count: Optional[int] = None
    google_maps_url: str = ""
    google_place_id: str = ""

    @property
    def full_name(self) -> str:
        cred = f", {self.credentials}" if self.credentials else ""
        return f"{self.first_name} {self.last_name}{cred}".strip()

    @property
    def full_address(self) -> str:
        parts = [self.address_line]
        if self.suite:
            parts.append(self.suite)
        parts.append(f"{self.city}, {self.state} {self.zip_code}")
        return ", ".join(parts)

    def to_dict(self) -> dict:
        return {
            "npi": self.npi,
            "name": self.full_name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "credentials": self.credentials,
            "specialty": self.specialty,
            "phone": self.phone,
            "fax": self.fax,
            "address": self.full_address,
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "gender": self.gender,
            "accepting_new_patients": self.accepting_new_patients,
            "network_name": self.network_name,
            "carrier": self.carrier,
            "distance_miles": self.distance_miles,
            "google_rating": self.google_rating,
            "google_review_count": self.google_review_count,
            "google_maps_url": self.google_maps_url,
        }


# NUCC Taxonomy codes for common specialties
# Used by Humana, Aetna, UHC — others need mapping
SPECIALTY_MAP = {
    "cardiology": "207RC0000X",
    "cardiologist": "207RC0000X",
    "dermatology": "207N00000X",
    "dermatologist": "207N00000X",
    "endocrinology": "207RE0101X",
    "endocrinologist": "207RE0101X",
    "family medicine": "207Q00000X",
    "family doctor": "207Q00000X",
    "gastroenterology": "207RG0100X",
    "gastroenterologist": "207RG0100X",
    "general practice": "208D00000X",
    "general practitioner": "208D00000X",
    "internal medicine": "207R00000X",
    "internist": "207R00000X",
    "nephrology": "207RN0300X",
    "nephrologist": "207RN0300X",
    "neurology": "2084N0400X",
    "neurologist": "2084N0400X",
    "obstetrics": "207V00000X",
    "obgyn": "207V00000X",
    "ob/gyn": "207V00000X",
    "oncology": "207RX0202X",
    "oncologist": "207RX0202X",
    "ophthalmology": "207W00000X",
    "ophthalmologist": "207W00000X",
    "eye doctor": "207W00000X",
    "orthopedics": "207X00000X",
    "orthopedic": "207X00000X",
    "orthopedist": "207X00000X",
    "otolaryngology": "207Y00000X",
    "ent": "207Y00000X",
    "pain management": "208VP0014X",
    "pain doctor": "208VP0014X",
    "pediatrics": "208000000X",
    "pediatrician": "208000000X",
    "physical therapy": "225100000X",
    "physical therapist": "225100000X",
    "podiatry": "213E00000X",
    "podiatrist": "213E00000X",
    "foot doctor": "213E00000X",
    "primary care": "208D00000X",
    "pcp": "208D00000X",
    "psychiatry": "2084P0800X",
    "psychiatrist": "2084P0800X",
    "pulmonology": "207RP1001X",
    "pulmonologist": "207RP1001X",
    "lung doctor": "207RP1001X",
    "rheumatology": "207RR0500X",
    "rheumatologist": "207RR0500X",
    "surgery": "208600000X",
    "surgeon": "208600000X",
    "urology": "208800000X",
    "urologist": "208800000X",
}

# Centene/Wellcare uses their own specialty codes
CENTENE_SPECIALTY_MAP = {
    "cardiology": "CAR",
    "cardiologist": "CAR",
    "dermatology": "DER",
    "dermatologist": "DER",
    "endocrinology": "END",
    "endocrinologist": "END",
    "family medicine": "FP",
    "family doctor": "FP",
    "gastroenterology": "GAS",
    "gastroenterologist": "GAS",
    "general practice": "GP",
    "internal medicine": "IM",
    "internist": "IM",
    "nephrology": "NEP",
    "nephrologist": "NEP",
    "neurology": "NEU",
    "neurologist": "NEU",
    "oncology": "ONC",
    "oncologist": "ONC",
    "ophthalmology": "OPH",
    "ophthalmologist": "OPH",
    "eye doctor": "OPH",
    "orthopedics": "ORS",
    "orthopedist": "ORS",
    "pediatrics": "PED",
    "pediatrician": "PED",
    "podiatry": "POD",
    "podiatrist": "POD",
    "foot doctor": "POD",
    "primary care": "PCP",
    "pcp": "PCP",
    "psychiatry": "PSY",
    "psychiatrist": "PSY",
    "pulmonology": "PUL",
    "pulmonologist": "PUL",
    "lung doctor": "PUL",
    "rheumatology": "RHE",
    "rheumatologist": "RHE",
    "surgery": "SUR",
    "surgeon": "SUR",
    "urology": "URO",
    "urologist": "URO",
}


def resolve_specialty(query: str) -> dict:
    """
    Resolve a natural language specialty query to codes.
    Returns dict with 'nucc' and 'centene' codes + display name.
    """
    key = query.strip().lower()
    return {
        "nucc": SPECIALTY_MAP.get(key, ""),
        "centene": CENTENE_SPECIALTY_MAP.get(key, ""),
        "display": query.strip().title(),
        "raw": key,
    }


class BaseAdapter(ABC):
    """Base class for all carrier FHIR adapters."""

    carrier_name: str = ""
    base_url: str = ""

    @abstractmethod
    async def search_providers(
        self,
        specialty: str,
        zip_code: str,
        plan_name: str = "",
        limit: int = 50,
    ) -> list[ProviderResult]:
        """
        Search for providers by specialty within a carrier's network.
        Returns a list of standardized ProviderResult objects.
        """
        pass