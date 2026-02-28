"""
Tests for OTP generation, verification, and JWT token management.
"""

import time
import pytest
from unittest.mock import patch
from fastapi import HTTPException

from app.auth import (
    generate_otp,
    verify_otp,
    create_tokens,
    decode_token,
    _hash_code,
    _otp_store,
    _otp_send_log,
)


class TestOTPGeneration:
    def setup_method(self):
        _otp_store.clear()
        _otp_send_log.clear()

    def test_generates_6_digit_code(self):
        code = generate_otp("5551234567")
        assert code is not None
        assert len(code) == 6
        assert code.isdigit()
        assert 100000 <= int(code) <= 999999

    def test_stores_hash_not_raw(self):
        code = generate_otp("5551234567")
        entry = _otp_store["5551234567"]
        assert entry["code_hash"] != code
        assert entry["code_hash"] == _hash_code(code)

    def test_rate_limiting(self):
        phone = "5550001111"
        for i in range(4):
            code = generate_otp(phone, max_sends=4, send_window=600)
            assert code is not None
        # 5th should be rate-limited
        code = generate_otp(phone, max_sends=4, send_window=600)
        assert code is None

    def test_rate_limit_window_reset(self):
        phone = "5550002222"
        for i in range(4):
            generate_otp(phone, max_sends=4, send_window=1)
        # Wait for window to expire
        time.sleep(1.1)
        code = generate_otp(phone, max_sends=4, send_window=1)
        assert code is not None


class TestOTPVerification:
    def setup_method(self):
        _otp_store.clear()
        _otp_send_log.clear()

    def test_correct_code(self):
        code = generate_otp("5551234567")
        assert verify_otp("5551234567", code) is True

    def test_wrong_code(self):
        generate_otp("5551234567")
        assert verify_otp("5551234567", "000000") is False

    def test_single_use(self):
        code = generate_otp("5551234567")
        assert verify_otp("5551234567", code) is True
        # Second use should fail
        assert verify_otp("5551234567", code) is False

    def test_expiration(self):
        code = generate_otp("5551234567", otp_ttl=1)
        time.sleep(1.1)
        assert verify_otp("5551234567", code) is False

    def test_lockout_after_max_attempts(self):
        code = generate_otp("5551234567")
        for _ in range(5):
            verify_otp("5551234567", "000000", max_attempts=5)
        # Even correct code should fail during lockout
        assert verify_otp("5551234567", code) is False

    def test_nonexistent_phone(self):
        assert verify_otp("0000000000", "123456") is False


class TestJWTTokens:
    def test_create_tokens(self, jwt_secret, sample_member):
        tokens = create_tokens("5551234567", sample_member, jwt_secret=jwt_secret)
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"
        assert tokens["expires_in"] > 0

    def test_decode_access_token(self, jwt_secret, sample_member):
        tokens = create_tokens("5551234567", sample_member, jwt_secret=jwt_secret)
        payload = decode_token(tokens["access_token"], jwt_secret=jwt_secret, expected_type="access")
        assert payload["sub"] == "5551234567"
        assert payload["type"] == "access"
        assert payload["first_name"] == "Jane"

    def test_decode_refresh_token(self, jwt_secret, sample_member):
        tokens = create_tokens("5551234567", sample_member, jwt_secret=jwt_secret)
        payload = decode_token(tokens["refresh_token"], jwt_secret=jwt_secret, expected_type="refresh")
        assert payload["sub"] == "5551234567"
        assert payload["type"] == "refresh"

    def test_wrong_token_type(self, jwt_secret, sample_member):
        tokens = create_tokens("5551234567", sample_member, jwt_secret=jwt_secret)
        with pytest.raises(HTTPException) as exc_info:
            decode_token(tokens["access_token"], jwt_secret=jwt_secret, expected_type="refresh")
        assert exc_info.value.status_code == 401

    def test_expired_token(self, jwt_secret, sample_member):
        tokens = create_tokens("5551234567", sample_member, jwt_secret=jwt_secret, access_ttl=1)
        time.sleep(1.1)
        with pytest.raises(HTTPException) as exc_info:
            decode_token(tokens["access_token"], jwt_secret=jwt_secret)
        assert exc_info.value.status_code == 401

    def test_invalid_token(self, jwt_secret):
        with pytest.raises(HTTPException) as exc_info:
            decode_token("not.a.valid.token", jwt_secret=jwt_secret)
        assert exc_info.value.status_code == 401

    def test_wrong_secret(self, sample_member):
        tokens = create_tokens("5551234567", sample_member, jwt_secret="secret-A")
        with pytest.raises(HTTPException):
            decode_token(tokens["access_token"], jwt_secret="secret-B")
