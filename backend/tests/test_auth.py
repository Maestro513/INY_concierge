"""
Tests for JWT token management.

Note: OTP generation/verification is tested in test_persistent_store.py
(which tests the production PersistentStore implementation).
"""

import time

import pytest
from fastapi import HTTPException

from app.auth import (
    create_tokens,
    decode_token,
)


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
        # H1: PHI should NOT be in JWT tokens
        assert "first_name" not in payload
        assert "plan_number" not in payload

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
