"""
Admin portal authentication — completely separate from mobile OTP auth.

- Email + password (bcrypt)
- Separate ADMIN_JWT_SECRET
- Role-based access: super_admin, admin, viewer
"""

import logging
import os
import time

import bcrypt
import jwt
from fastapi import HTTPException, Request

from . import admin_db
from .config import APP_ENV

log = logging.getLogger(__name__)

# Admin JWT secret — MUST be different from mobile JWT_SECRET (H7)
ADMIN_JWT_SECRET = os.getenv("ADMIN_JWT_SECRET", "")

if APP_ENV == "production":
    if not ADMIN_JWT_SECRET:
        raise RuntimeError("ADMIN_JWT_SECRET must be set in production.")
    # Ensure admin and mobile secrets are different so tokens can't cross boundaries
    _mobile_secret = os.getenv("JWT_SECRET", "")
    if ADMIN_JWT_SECRET == _mobile_secret:
        raise RuntimeError(
            "ADMIN_JWT_SECRET must be different from JWT_SECRET. "
            "A shared secret allows mobile tokens to be used as admin tokens."
        )
elif not ADMIN_JWT_SECRET:
    log.warning("ADMIN_JWT_SECRET not set — using insecure default for development only")
    ADMIN_JWT_SECRET = "admin-dev-secret-change-me"
ADMIN_ACCESS_TTL = int(os.getenv("ADMIN_ACCESS_TTL", "28800"))    # 8 hours
ADMIN_REFRESH_TTL = int(os.getenv("ADMIN_REFRESH_TTL", "2592000"))  # 30 days


# ── Password hashing ────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Bcrypt hash a plaintext password."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# ── JWT tokens ───────────────────────────────────────────────────────────────

def create_admin_tokens(user: dict) -> dict:
    """Create access + refresh tokens for an admin user."""
    now = time.time()
    access_payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "type": "admin_access",
        "iat": now,
        "exp": now + ADMIN_ACCESS_TTL,
    }
    refresh_payload = {
        "sub": str(user["id"]),
        "type": "admin_refresh",
        "iat": now,
        "exp": now + ADMIN_REFRESH_TTL,
    }
    return {
        "access_token": jwt.encode(access_payload, ADMIN_JWT_SECRET, algorithm="HS256"),
        "refresh_token": jwt.encode(refresh_payload, ADMIN_JWT_SECRET, algorithm="HS256"),
        "user": {
            "id": user["id"],
            "email": user["email"],
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "role": user["role"],
        },
    }


def decode_admin_token(token: str, expected_type: str = "admin_access") -> dict:
    """Decode and validate an admin JWT."""
    try:
        payload = jwt.decode(token, ADMIN_JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Admin token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid admin token.")
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail="Invalid admin token type.")
    return payload


# ── Auth dependencies ────────────────────────────────────────────────────────

def require_admin(request: Request) -> dict:
    """FastAPI dependency — verify admin Bearer token. Returns decoded payload."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing admin authentication.")
    token = auth_header[7:]
    return decode_admin_token(token)


def require_role(*roles: str):
    """
    FastAPI dependency factory — require specific admin roles.
    Usage: Depends(require_role("super_admin", "admin"))
    """
    def _check(request: Request) -> dict:
        payload = require_admin(request)
        if payload.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
        return payload
    return _check


# ── Login flow ───────────────────────────────────────────────────────────────

def authenticate_admin(email: str, password: str) -> dict:
    """
    Validate admin email + password, return tokens.
    Raises HTTPException on failure.
    """
    user = admin_db.get_admin_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account deactivated.")
    if not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return create_admin_tokens(user)


# ── Bootstrap CLI ────────────────────────────────────────────────────────────

def bootstrap_super_admin(email: str, password: str, first_name: str = "Admin",
                          last_name: str = "User") -> dict:
    """Create the first super_admin account. Used from CLI."""
    existing = admin_db.get_admin_user_by_email(email)
    if existing:
        log.info(f"Admin user {email} already exists (id={existing['id']})")
        return existing
    pw_hash = hash_password(password)
    user = admin_db.create_admin_user(
        email=email, password_hash=pw_hash,
        first_name=first_name, last_name=last_name, role="super_admin",
    )
    log.info(f"Created super_admin: {email} (id={user['id']})")
    return user
