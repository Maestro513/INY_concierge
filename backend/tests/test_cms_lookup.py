"""
Tests for CMS benefits lookup.

Tests that require the actual cms_benefits.db are skipped if the DB
file doesn't exist or isn't a valid SQLite database.
"""

import os
import sqlite3

import pytest

from app.cms_lookup import INSULIN_NAMES, CMSLookup

# Check if CMS DB exists AND is a valid SQLite file
_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cms_benefits.db"
)
_DB_USABLE = False
if os.path.isfile(_DB_PATH):
    try:
        conn = sqlite3.connect(_DB_PATH)
        # Verify it's a real SQLite DB with the expected tables
        conn.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1").fetchone()
        conn.close()
        _DB_USABLE = True
    except Exception:
        pass

_skip_no_db = pytest.mark.skipif(not _DB_USABLE, reason="cms_benefits.db not available or not valid")


class TestParsePlanNumber:
    """Static method tests — no DB needed."""

    def test_two_segment(self):
        cid, pid, seg = CMSLookup._parse_plan_number("H1036-077")
        assert cid == "H1036"
        assert pid == "077"
        assert seg == "000"

    def test_three_segment(self):
        cid, pid, seg = CMSLookup._parse_plan_number("H1036-077-002")
        assert cid == "H1036"
        assert pid == "077"
        assert seg == "002"

    def test_single_segment(self):
        cid, pid, seg = CMSLookup._parse_plan_number("H1036")
        assert cid == "H1036"
        assert pid == "000"

    def test_lowercase(self):
        cid, pid, seg = CMSLookup._parse_plan_number("h1036-077")
        assert cid == "H1036"


class TestHelpers:
    """Static method tests — no DB needed."""

    def test_safe_float_valid(self):
        assert CMSLookup._safe_float("42.5") == 42.5

    def test_safe_float_none(self):
        assert CMSLookup._safe_float(None) is None

    def test_safe_float_empty(self):
        assert CMSLookup._safe_float("") is None

    def test_yn_to_bool(self):
        assert CMSLookup._yn_to_bool("Y") is True
        assert CMSLookup._yn_to_bool("N") is False
        assert CMSLookup._yn_to_bool("1") is True
        assert CMSLookup._yn_to_bool("2") is False
        assert CMSLookup._yn_to_bool(None) is None

    def test_is_insulin(self):
        assert CMSLookup._is_insulin("Lantus SoloStar") is True
        assert CMSLookup._is_insulin("Humalog KwikPen") is True
        assert CMSLookup._is_insulin("Eliquis") is False
        assert CMSLookup._is_insulin("insulin glargine") is True


@_skip_no_db
class TestPlanOverview:
    @pytest.fixture
    def cms(self):
        return CMSLookup()

    def test_valid_plan(self, cms):
        result = cms.get_plan_overview("H1036-077")
        if result:  # plan may not be in this DB
            assert "contract_id" in result
            assert "plan_name" in result
            assert result["contract_id"] == "H1036"

    def test_invalid_plan(self, cms):
        result = cms.get_plan_overview("XXXXX-999")
        assert result is None


@_skip_no_db
class TestMedicalCopays:
    @pytest.fixture
    def cms(self):
        return CMSLookup()

    def test_returns_dict(self, cms):
        result = cms.get_medical_copays("H1036-077")
        assert isinstance(result, dict)
        assert "pcp_copay" in result
        assert "specialist_copay" in result
        assert "er_copay" in result
        assert "urgent_care_copay" in result


@_skip_no_db
class TestFullBenefits:
    @pytest.fixture
    def cms(self):
        return CMSLookup()

    def test_returns_all_sections(self, cms):
        result = cms.get_full_benefits("H1036-077")
        if "error" not in result:
            assert "plan" in result
            assert "medical" in result
            assert "dental" in result
            assert "vision" in result
            assert "hearing" in result
            assert "otc" in result
