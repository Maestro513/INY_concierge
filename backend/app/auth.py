"""
OTP + JWT authentication module.

P0: Phone-based OTP verification → JWT access + refresh tokens
P1: Rate limiting, expiration, max attempts, lockout
"""

import hashlib
import hmac
import logging
import secrets
import time

import jwt
from fastapi import HTTPException, Request

log = logging.getLogger(__name__)

# ── OTP Store (in-memory) ────────────────────────────────────────────────────
# Key: phone number → {code_hash, created_at, attempts, locked_until}
_otp_store: dict[str, dict] = {}

# ── Rate limit store ─────────────────────────────────────────────────────────
# Key: phone number → list of timestamps (send times)
_otp_send_log: dict[str, list[float]] = {}


def _hash_code(code: str) -> str:
    """SHA-256 hash so we never store raw OTP in memory."""
    return hashlib.sha256(code.encode()).hexdigest()


def generate_otp(phone: str, *, otp_ttl: int = 300, max_sends: int = 5, send_window: int = 600) -> str | None:
    """
    Generate a 6-digit OTP for the given phone number.

    P1 rate limiting:
      - Max `max_sends` OTP sends per phone per `send_window` seconds.
      - Returns None if rate-limited.

    The OTP is stored hashed with a TTL of `otp_ttl` seconds (default 5 min).
    """
    now = time.time()

    # ── P1: Rate limiting ────────────────────────────────────────────────
    sends = _otp_send_log.get(phone, [])
    # Prune old entries
    sends = [t for t in sends if now - t < send_window]
    if len(sends) >= max_sends:
        log.warning(f"OTP rate limit hit for phone ending {phone[-4:]}")
        return None
    sends.append(now)
    _otp_send_log[phone] = sends

    # ── Generate code ────────────────────────────────────────────────────
    code = f"{secrets.randbelow(900000) + 100000}"  # 100000–999999

    _otp_store[phone] = {
        "code_hash": _hash_code(code),
        "created_at": now,
        "ttl": otp_ttl,
        "attempts": 0,
        "locked_until": 0,
    }
    return code


def verify_otp(phone: str, code: str, *, max_attempts: int = 5, lockout_seconds: int = 300) -> bool:
    """
    Verify the OTP for a phone number.

    P1 security:
      - Max `max_attempts` wrong guesses before lockout.
      - Lockout lasts `lockout_seconds` (default 5 min).
      - OTP is single-use — deleted after successful verification.
    """
    entry = _otp_store.get(phone)
    if not entry:
        return False

    now = time.time()

    # Check lockout
    if now < entry["locked_until"]:
        remaining = int(entry["locked_until"] - now)
        log.warning(f"OTP locked for phone ending {phone[-4:]}, {remaining}s remaining")
        return False

    # Check expiration
    if now - entry["created_at"] > entry["ttl"]:
        _otp_store.pop(phone, None)
        return False

    # Check code
    if not hmac.compare_digest(_hash_code(code), entry["code_hash"]):
        entry["attempts"] += 1
        if entry["attempts"] >= max_attempts:
            entry["locked_until"] = now + lockout_seconds
            log.warning(f"OTP locked out for phone ending {phone[-4:]} after {max_attempts} attempts")
        return False

    # Success — delete OTP (single-use)
    _otp_store.pop(phone, None)
    return True


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
