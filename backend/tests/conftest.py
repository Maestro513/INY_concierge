"""
Shared fixtures for backend tests.
"""

import os
import sys

import pytest

# Ensure the backend package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force development mode so auth is bypassed in integration tests
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-production")
os.environ.setdefault("SMS_PROVIDER", "console")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", "tTpyb5AShevzMaryxDyxNWqd4wh86vTda5aOHAH5eA8=")
os.environ.setdefault("ADMIN_SECRET", "test-admin-secret-for-tests")


@pytest.fixture
def jwt_secret():
    return "test-secret-do-not-use-in-production"


@pytest.fixture
def sample_member():
    return {
        "first_name": "Jane",
        "last_name": "Doe",
        "plan_name": "Humana Gold Plus",
        "plan_number": "H1036-077",
        "agent": "Test Agent",
        "medicare_number": "1EG4-TE5-MK72",
        "phone": "5551234567",
        "medications": "Eliquis, Lantus 90 day, Ventolin",
        "zip_code": "33012",
    }


@pytest.fixture
def sample_drugs():
    """Drug list formatted for the cost engine."""
    return [
        {
            "name": "Eliquis",
            "tier": 3,
            "cost_type": "copay",
            "copay_amount": 47.0,
            "coinsurance_pct": None,
            "estimated_full_cost": 600.0,
            "is_insulin": False,
            "deductible_applies": True,
        },
        {
            "name": "Lantus",
            "tier": 3,
            "cost_type": "copay",
            "copay_amount": 35.0,
            "coinsurance_pct": None,
            "estimated_full_cost": 350.0,
            "is_insulin": True,
            "deductible_applies": True,
        },
        {
            "name": "Ventolin",
            "tier": 1,
            "cost_type": "copay",
            "copay_amount": 0.0,
            "coinsurance_pct": None,
            "estimated_full_cost": 30.0,
            "is_insulin": False,
            "deductible_applies": False,
        },
    ]
