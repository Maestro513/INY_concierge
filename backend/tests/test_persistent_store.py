"""
Tests for the persistent OTP + session store.
"""

import os
import tempfile
import time

import pytest

from app.persistent_store import PersistentStore


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_store.db")
    return PersistentStore(db_path=db_path)


class TestOTPPersistent:
    def test_generate_and_verify(self, store):
        code = store.generate_otp("5551234567")
        assert code is not None
        assert len(code) == 6
        assert store.verify_otp("5551234567", code) is True

    def test_single_use(self, store):
        code = store.generate_otp("5551234567")
        assert store.verify_otp("5551234567", code) is True
        assert store.verify_otp("5551234567", code) is False

    def test_wrong_code(self, store):
        store.generate_otp("5551234567")
        assert store.verify_otp("5551234567", "000000") is False

    def test_expiration(self, store):
        code = store.generate_otp("5551234567", otp_ttl=1)
        time.sleep(1.1)
        assert store.verify_otp("5551234567", code) is False

    def test_rate_limiting(self, store):
        phone = "5550001111"
        for _ in range(4):
            code = store.generate_otp(phone, max_sends=4, send_window=600)
            assert code is not None
        code = store.generate_otp(phone, max_sends=4, send_window=600)
        assert code is None

    def test_lockout_after_max_attempts(self, store):
        code = store.generate_otp("5551234567")
        for _ in range(5):
            store.verify_otp("5551234567", "000000", max_attempts=5)
        assert store.verify_otp("5551234567", code) is False

    def test_nonexistent_phone(self, store):
        assert store.verify_otp("0000000000", "123456") is False

    def test_survives_new_instance(self, tmp_path):
        """OTP persists across store instances (simulating restart)."""
        db_path = str(tmp_path / "restart_test.db")
        store1 = PersistentStore(db_path=db_path)
        code = store1.generate_otp("5559998888")

        # Simulate restart — new instance, same DB
        store2 = PersistentStore(db_path=db_path)
        assert store2.verify_otp("5559998888", code) is True


class TestSessionPersistent:
    def test_create_and_get(self, store):
        sid = store.create_session("5551234567", {"name": "Jane"})
        session = store.get_session(sid)
        assert session is not None
        assert session["phone"] == "5551234567"
        assert session["data"]["name"] == "Jane"

    def test_expired_session(self, store):
        sid = store.create_session("5551234567", {"name": "Jane"})
        session = store.get_session(sid, ttl=0)
        assert session is None

    def test_find_by_phone(self, store):
        store.create_session("5551234567", {"plan": "Gold"})
        result = store.find_session_by_phone("5551234567")
        assert result is not None
        assert result["data"]["plan"] == "Gold"

    def test_touch_extends_session(self, store):
        sid = store.create_session("5551234567", {"name": "Jane"})
        time.sleep(0.1)
        store.touch_session(sid)
        session = store.get_session(sid)
        assert session is not None
        assert session["ts"] > time.time() - 1

    def test_count_active(self, store):
        store.create_session("5551111111", {"a": 1})
        store.create_session("5552222222", {"b": 2})
        assert store.count_active_sessions() == 2

    def test_survives_new_instance(self, tmp_path):
        """Session persists across store instances (simulating restart)."""
        db_path = str(tmp_path / "session_restart.db")
        store1 = PersistentStore(db_path=db_path)
        sid = store1.create_session("5559998888", {"plan": "Platinum"})

        store2 = PersistentStore(db_path=db_path)
        session = store2.get_session(sid)
        assert session is not None
        assert session["data"]["plan"] == "Platinum"

    def test_cleanup(self, store):
        sid = store.create_session("5551234567", {"name": "Jane"})
        # Force expire by setting TTL=0 in cleanup
        store._cleanup_sessions(ttl=0)
        assert store.get_session(sid, ttl=7200) is None
