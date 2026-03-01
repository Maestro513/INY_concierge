"""
Tests for UserDataDB — medication reminders + benefits usage tracking.
"""

import os
import tempfile

import pytest

from app.user_data import UserDataDB


@pytest.fixture
def db():
    """Create a fresh in-memory-like temp DB for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        yield UserDataDB(db_path=db_path)
    finally:
        os.unlink(db_path)


class TestMedicationReminders:
    def test_create_reminder(self, db):
        r = db.create_reminder("5551234567", "Eliquis", 8, time_minute=30)
        assert r["drug_name"] == "Eliquis"
        assert r["time_hour"] == 8
        assert r["time_minute"] == 30
        assert r["enabled"] == 1
        assert r["phone"] == "5551234567"

    def test_get_reminders(self, db):
        db.create_reminder("5551234567", "Eliquis", 8)
        db.create_reminder("5551234567", "Lantus", 20)
        reminders = db.get_reminders("5551234567")
        assert len(reminders) == 2
        assert reminders[0]["drug_name"] == "Eliquis"  # sorted by time

    def test_get_reminders_empty(self, db):
        reminders = db.get_reminders("0000000000")
        assert reminders == []

    def test_update_reminder(self, db):
        r = db.create_reminder("5551234567", "Eliquis", 8)
        updated = db.update_reminder("5551234567", r["id"], time_hour=9, enabled=False)
        assert updated["time_hour"] == 9
        assert updated["enabled"] == 0

    def test_delete_reminder(self, db):
        r = db.create_reminder("5551234567", "Eliquis", 8)
        assert db.delete_reminder("5551234567", r["id"]) is True
        assert db.get_reminders("5551234567") == []

    def test_delete_nonexistent(self, db):
        assert db.delete_reminder("5551234567", 99999) is False

    def test_bulk_create(self, db):
        reminders = [
            {"drug_name": "Eliquis", "time_hour": 8},
            {"drug_name": "Lantus", "time_hour": 20, "time_minute": 30},
        ]
        result = db.create_reminders_bulk("5551234567", reminders)
        assert len(result) == 2

    def test_phone_isolation(self, db):
        db.create_reminder("1111111111", "DrugA", 8)
        db.create_reminder("2222222222", "DrugB", 9)
        assert len(db.get_reminders("1111111111")) == 1
        assert len(db.get_reminders("2222222222")) == 1
        assert db.get_reminders("1111111111")[0]["drug_name"] == "DrugA"


class TestBenefitsUsage:
    def test_log_usage(self, db):
        entry = db.log_usage("5551234567", "otc", 25.50, description="Vitamins")
        assert entry["category"] == "otc"
        assert entry["amount"] == 25.50

    def test_get_usage(self, db):
        db.log_usage("5551234567", "otc", 25.00)
        db.log_usage("5551234567", "dental", 100.00)
        all_usage = db.get_usage("5551234567")
        assert len(all_usage) == 2

    def test_get_usage_by_category(self, db):
        db.log_usage("5551234567", "otc", 25.00)
        db.log_usage("5551234567", "dental", 100.00)
        otc_only = db.get_usage("5551234567", category="otc")
        assert len(otc_only) == 1
        assert otc_only[0]["category"] == "otc"

    def test_usage_totals(self, db):
        db.log_usage("5551234567", "otc", 25.00, usage_date="2026-01-15")
        db.log_usage("5551234567", "otc", 30.00, usage_date="2026-01-20")
        totals = db.get_usage_totals("5551234567")
        assert "otc" in totals
        assert totals["otc"] == 55.00

    def test_delete_usage(self, db):
        entry = db.log_usage("5551234567", "otc", 25.00)
        assert db.delete_usage("5551234567", entry["id"]) is True
        assert db.get_usage("5551234567") == []

    def test_period_key_monthly(self, db):
        key = UserDataDB._compute_period_key("2026-03-15", "Monthly")
        assert key == "2026-03"

    def test_period_key_quarterly(self, db):
        key = UserDataDB._compute_period_key("2026-03-15", "Quarterly")
        assert key == "2026-Q1"
        key2 = UserDataDB._compute_period_key("2026-07-01", "Quarterly")
        assert key2 == "2026-Q3"

    def test_period_key_yearly(self, db):
        key = UserDataDB._compute_period_key("2026-06-15", "Yearly")
        assert key == "2026"
