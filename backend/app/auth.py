"""
JWT authentication module.

P0: Phone-based OTP verification → JWT access + refresh tokens
P1: Rate limiting, expiration, max attempts, lockout

Note: OTP generation/verification is handled by PersistentStore (persistent_store.py).
This module only handles JWT token management and request authentication.
"""

import logging
import secrets
import time

import jwt
from fastapi import HTTPException, Request

log = logging.getLogger(__name__)


# ── JWT Token Management ─────────────────────────────────────────────────────

def create_tokens(phone: str, member_data: dict = None, *, jwt_secret: str, access_ttl: int = 7200, refresh_ttl: int = 2592000) -> dict:
    """
    Create access + refresh JWT tokens.

    Access token: short-lived (default 2 hours), contains only phone + type.
    Refresh token: long-lived (default 30 days), only carries phone.
    No PHI is embedded in tokens — member data is served from the session.
    """
    now = time.time()

    access_payload = {
        "sub": phone,
        "type": "access",
        "iat": now,
        "exp": now + access_ttl,
    }

    refresh_payload = {
        "sub": phone,
        "type": "refresh",
        "jti": secrets.token_urlsafe(24),
        "iat": now,
        "exp": now + refresh_ttl,
    }

    access_token = jwt.encode(access_payload, jwt_secret, algorithm="HS256")
    refresh_token = jwt.encode(refresh_payload, jwt_secret, algorithm="HS256")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": access_ttl,
    }


def decode_token(token: str, *, jwt_secret: str, expected_type: str = "access") -> dict:
    """
    Decode and validate a JWT token.
    Raises HTTPException on invalid/expired tokens.
    """
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")

    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail="Invalid token type.")

    return payload


def require_auth(request: Request, *, jwt_secret: str) -> dict:
    """
    FastAPI dependency — extracts and validates the Bearer token.
    Returns the decoded JWT payload (contains phone, name, plan info).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authentication token.")

    token = auth_header[7:]  # Strip "Bearer "
    return decode_token(token, jwt_secret=jwt_secret)
