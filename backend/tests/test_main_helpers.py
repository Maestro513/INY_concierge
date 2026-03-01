"""
Tests for helper functions in main.py.
"""

import pytest

from app.main import normalize_plan_id, parse_medications


class TestNormalizePlanId:
    def test_strips_segment(self):
        assert normalize_plan_id("H1036-077-000") == "H1036-077"

    def test_no_segment(self):
        assert normalize_plan_id("H1036-077") == "H1036-077"

    def test_non_zero_segment_kept(self):
        assert normalize_plan_id("H1036-077-002") == "H1036-077-002"

    def test_whitespace_stripped(self):
        assert normalize_plan_id("  H1036-077-000  ") == "H1036-077"


class TestParseMedications:
    def test_comma_separated(self):
        meds = parse_medications("Eliquis, Lantus, Ventolin")
        assert len(meds) == 3
        assert meds[0]["name"] == "Eliquis"
        assert meds[1]["name"] == "Lantus"

    def test_newline_separated(self):
        meds = parse_medications("Eliquis\nLantus\nVentolin")
        assert len(meds) == 3

    def test_90_day_detection(self):
        meds = parse_medications("Lantus 90 day")
        assert meds[0]["days_supply"] == 90
        assert meds[0]["is_mail"] is True  # 90-day implies mail

    def test_mail_order_detection(self):
        meds = parse_medications("Eliquis (mail order)")
        assert meds[0]["is_mail"] is True
        assert "mail" not in meds[0]["name"].lower()

    def test_empty_string(self):
        assert parse_medications("") == []

    def test_none(self):
        assert parse_medications(None) == []

    def test_default_30_day(self):
        meds = parse_medications("Eliquis")
        assert meds[0]["days_supply"] == 30
        assert meds[0]["is_mail"] is False

    def test_mixed_formats(self):
        meds = parse_medications("Eliquis, Lantus 90 day, Ventolin (mail)")
        assert len(meds) == 3
        assert meds[0]["days_supply"] == 30
        assert meds[1]["days_supply"] == 90
        assert meds[2]["is_mail"] is True
