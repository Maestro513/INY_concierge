"""
Admin portal API router.

All endpoints under /api/admin/* — separate auth from mobile app.
"""

import glob
import json
import logging
import os
import re as _re
import shutil
import tarfile
import tempfile
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator

from . import admin_db
from .admin_auth import (
    authenticate_admin,
    bootstrap_super_admin,
    clear_auth_cookies,
    create_admin_tokens,
    decode_admin_token,
    hash_password,
    require_admin,
    require_role,
    revoke_admin_token,
    set_auth_cookies,
)
from .audit import get_audit_log
from .caregiver import CaregiverDB
from .config import ADMIN_SECRET, APP_ENV, EXTRACTED_DIR, PDFS_DIR
from .persistent_store import PersistentStore
from .sms_provider import create_sms_provider
from .zoho_client import search_contact_by_phone

log = logging.getLogger(__name__)
_ALLOWED_ADMIN_ORIGINS = {
    "https://insurancenyou.com",
    "https://www.insurancenyou.com",
    "https://admin.insurancenyou.com",
    "https://api.insurancenyou.com",
}
_CSRF_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def check_csrf_origin(request: Request):
    """FastAPI dependency — validate Origin on mutating admin requests (H9)."""
    if APP_ENV != "production":
        return
    if request.method not in _CSRF_METHODS:
        return
    origin = request.headers.get("origin", "")
    if origin:
        if origin not in _ALLOWED_ADMIN_ORIGINS:
            raise HTTPException(
                status_code=403,
                detail="Origin is not allowed for admin operations.",
            )
        return
    # No Origin header — fall back to Referer check
    referer = request.headers.get("referer", "")
    if referer:
        from urllib.parse import urlparse
        ref_origin = f"{urlparse(referer).scheme}://{urlparse(referer).netloc}"
        if ref_origin not in _ALLOWED_ADMIN_ORIGINS:
            raise HTTPException(
                status_code=403,
                detail="Request origin not allowed for admin operations.",
            )
        return
    # Neither Origin nor Referer — reject (non-browser API clients use Bearer auth,
    # but we still block to prevent CSRF from tools that strip these headers)
    raise HTTPException(
        status_code=403,
        detail="Missing Origin or Referer header on mutating request.",
    )


router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(check_csrf_origin)],
)

# Lazy singleton — shares the same SQLite DB as the mobile OTP store
_store = None

def _get_store() -> PersistentStore:
    global _store
    if _store is None:
        _store = PersistentStore()
    return _store


def _check_admin_rate(request: Request, *, max_hits: int, window: int, label: str) -> None:
    """Raise 429 if the client IP exceeds max_hits within window seconds."""
    ip = request.client.host if request.client else "unknown"
    key = f"admin_{label}:{ip}"
    if not _get_store().check_rate_limit(key, max_hits, window):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait before trying again.")


# ── Request / Response models ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


def _validate_password_complexity(password: str) -> str:
    """Enforce password complexity: 8+ chars, upper, lower, digit, special."""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if not _re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not _re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not _re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit.")
    if not _re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must contain at least one special character.")
    return password


class CreateAdminRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field("", max_length=100)
    last_name: str = Field("", max_length=100)
    role: str = Field("viewer", pattern=r"^(super_admin|admin|viewer)$")

    @field_validator("password")
    @classmethod
    def check_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)


class UpdateAdminRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = Field(None, pattern=r"^(super_admin|admin|viewer)$")
    is_active: Optional[bool] = None
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def check_complexity(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_password_complexity(v)
        return v


class CreateMemberRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., pattern=r"^[\d\-\+\(\)\s]{7,20}$")  # Normalized in handler
    medicare_number: str = Field("", pattern=r"^([A-Za-z0-9]{4}-[A-Za-z0-9]{3}-[A-Za-z0-9]{4})?$")
    zip_code: str = Field("", pattern=r"^(\d{5})?$")
    carrier: str = Field("", max_length=100)
    plan_name: str = Field("", max_length=200)
    plan_number: str = Field("", max_length=20)
    send_verification: bool = True


class SendOTPRequest(BaseModel):
    phone: str = Field(..., pattern=r"^[\d\-\+\(\)\s]{7,20}$")


# ════════════════════════════════════════════════════════════════════════════
#  AUTH ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@router.post("/auth/login")
async def admin_login(body: LoginRequest, request: Request):
    """Admin email + password login with brute-force protection."""
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")

    # H10: Check for too many recent failed attempts (lockout)
    failed_count = admin_db.count_recent_failed_logins(body.email)
    if failed_count >= 5:
        admin_db.record_login_event(
            phone=body.email, ip_address=ip, user_agent=ua, success=False,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Please try again in 15 minutes.",
        )

    # H11: Record failed attempts, not just successes
    try:
        result = authenticate_admin(body.email, body.password)
    except HTTPException:
        admin_db.record_login_event(
            phone=body.email, ip_address=ip, user_agent=ua, success=False,
        )
        raise

    admin_db.record_login_event(
        phone=body.email, ip_address=ip, user_agent=ua, success=True,
    )
    admin_db.clear_failed_logins(body.email)
    response = JSONResponse(content={"user": result["user"]})
    set_auth_cookies(response, result["access_token"], result["refresh_token"])
    return response


@router.post("/auth/refresh")
async def admin_refresh(request: Request):
    """Refresh admin access token using refresh token (with rotation)."""
    # Read refresh token from cookie first, fall back to Authorization header
    token = request.cookies.get("admin_refresh", "")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing refresh token.")
        token = auth_header[7:]
    payload = decode_admin_token(token, expected_type="admin_refresh")

    # Refresh token rotation — each token can only be used once
    jti = payload.get("jti")
    if jti and not _get_store().consume_refresh_jti(jti, f"admin:{payload['sub']}"):
        log.warning("Admin refresh token replay detected for user %s", payload["sub"])
        raise HTTPException(status_code=401, detail="Token already used. Please log in again.")

    user = admin_db.get_admin_user_by_id(int(payload["sub"]))
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Account not found or deactivated.")
    result = create_admin_tokens(user)
    response = JSONResponse(content={"user": result["user"]})
    set_auth_cookies(response, result["access_token"], result["refresh_token"])
    return response


@router.get("/auth/me")
async def admin_me(payload: dict = Depends(require_admin)):
    """Get current admin user profile."""
    user = admin_db.get_admin_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=404, detail="Admin user not found.")
    return {
        "id": user["id"],
        "email": user["email"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "role": user["role"],
        "is_active": bool(user["is_active"]),
    }


@router.post("/auth/logout")
async def admin_logout(request: Request):
    """Revoke tokens server-side and clear auth cookies."""
    # Revoke the access token
    access_token = request.cookies.get("admin_token", "")
    if access_token:
        revoke_admin_token(access_token)
    # Revoke the refresh token
    refresh_token = request.cookies.get("admin_refresh", "")
    if refresh_token:
        revoke_admin_token(refresh_token)
    response = JSONResponse(content={"success": True})
    clear_auth_cookies(response)
    return response


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN USER MANAGEMENT (super_admin only)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/users")
async def list_admins(payload: dict = Depends(require_role("super_admin"))):
    """List all admin users."""
    return admin_db.list_admin_users()


@router.post("/users")
async def create_admin(body: CreateAdminRequest,
                       request: Request,
                       payload: dict = Depends(require_role("super_admin"))):
    """Create a new admin user."""
    existing = admin_db.get_admin_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered.")
    pw_hash = hash_password(body.password)
    user = admin_db.create_admin_user(
        email=body.email, password_hash=pw_hash,
        first_name=body.first_name, last_name=body.last_name, role=body.role,
    )
    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="create",
        resource="admin_user",
        resource_id=str(user["id"]),
        ip_address=request.client.host if request.client else "",
        detail=f"email={body.email} role={body.role}",
    )
    return {"id": user["id"], "email": user["email"], "role": user["role"]}


@router.patch("/users/{user_id}")
async def update_admin(user_id: int, body: UpdateAdminRequest,
                       request: Request,
                       payload: dict = Depends(require_role("super_admin"))):
    """Update an admin user."""
    fields = body.model_dump(exclude_none=True)
    changed_fields = list(fields.keys())
    if "password" in fields:
        fields["password_hash"] = hash_password(fields.pop("password"))
    user = admin_db.update_admin_user(user_id, **fields)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="update",
        resource="admin_user",
        resource_id=str(user_id),
        ip_address=request.client.host if request.client else "",
        detail=f"fields={','.join(changed_fields)}",
    )
    return {"id": user["id"], "email": user["email"], "role": user["role"],
            "is_active": bool(user["is_active"])}


# ════════════════════════════════════════════════════════════════════════════
#  MEMBER MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════


def _normalize_phone(raw: str) -> str:
    """Strip to digits only, ensure 10-digit US phone."""
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


@router.post("/members/create")
async def create_member(body: CreateMemberRequest,
                        request: Request,
                        payload: dict = Depends(require_admin)):
    """
    Create a new member account.
    - Saves to Zoho CRM (or local store if Zoho unavailable)
    - Optionally sends OTP verification code to member's phone
    """
    _check_admin_rate(request, max_hits=10, window=60, label="member_create")
    phone = _normalize_phone(body.phone)
    if len(phone) != 10:
        raise HTTPException(status_code=400, detail="Phone must be a valid 10-digit US number.")

    # Check if member already exists
    existing = None
    try:
        existing = search_contact_by_phone(phone)
    except Exception:
        log.warning("Zoho lookup failed for ***%s, continuing with creation", phone[-4:])

    if existing:
        raise HTTPException(status_code=409, detail="A member with this phone number already exists.")

    member_data = {
        "phone": phone,
        "first_name": body.first_name,
        "last_name": body.last_name,
        "medicare_number": body.medicare_number,  # Will be encrypted by zoho_client
        "zip_code": body.zip_code,
        "carrier": body.carrier,
        "plan_name": body.plan_name,
        "plan_number": body.plan_number,
    }
    # Persist member data via a session so they can log in after OTP
    _get_store().create_session(phone, member_data)

    log.info("Admin %s created member: ***%s",
             payload.get("sub"), phone[-4:])
    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="create",
        resource="member",
        resource_id=f"***{phone[-4:]}",
        ip_address=request.client.host if request.client else "",
        detail="admin_member_create",
    )

    # Send OTP verification if requested
    otp_sent = False
    if body.send_verification:
        try:
            code = _get_store().generate_otp(phone)
            if code:
                sms = create_sms_provider()
                otp_sent = sms.send_otp(phone, code)
                log.info("OTP sent to new member ***%s: %s", phone[-4:], "success" if otp_sent else "failed")
        except Exception as e:
            log.error("Failed to send OTP to ***%s: %s", phone[-4:], type(e).__name__)

    return {
        "success": True,
        "member": {
            "first_name": member_data["first_name"],
            "last_name": member_data["last_name"],
            "phone": f"***{phone[-4:]}",
            "plan_number": member_data.get("plan_number", ""),
        },
        "otp_sent": otp_sent,
        "message": f"Member created. {'Verification code sent.' if otp_sent else 'OTP send failed — member can request code from the app.'}",
    }


@router.post("/members/send-otp")
async def admin_send_otp(body: SendOTPRequest,
                         request: Request,
                         payload: dict = Depends(require_admin)):
    """Send OTP login code to a member's phone (triggered by admin)."""
    _check_admin_rate(request, max_hits=5, window=60, label="send_otp")
    phone = _normalize_phone(body.phone)
    if len(phone) != 10:
        raise HTTPException(status_code=400, detail="Invalid phone number.")

    try:
        code = _get_store().generate_otp(phone)
        if not code:
            raise HTTPException(status_code=429, detail="Too many OTP requests. Try again later.")
        sms = create_sms_provider()
        sent = sms.send_otp(phone, code)
        if not sent:
            raise HTTPException(status_code=500, detail="SMS delivery failed.")
    except HTTPException:
        raise
    except Exception as e:
        log.error("OTP send error for ***%s: %s", phone[-4:], type(e).__name__)
        raise HTTPException(status_code=500, detail="Failed to send OTP.")

    log.info("Admin %s sent OTP to member ***%s", payload.get("sub"), phone[-4:])
    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="create",
        resource="otp",
        resource_id=f"***{phone[-4:]}",
        ip_address=request.client.host if request.client else "",
        detail="admin_send_otp",
    )
    return {"success": True, "message": "Verification code sent."}


# ════════════════════════════════════════════════════════════════════════════
#  ANALYTICS ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@router.get("/analytics/logins")
async def analytics_logins(days: int = 30, payload: dict = Depends(require_admin)):
    """Login statistics for the given period."""
    days = max(1, min(days, 365))  # L4: cap to prevent expensive queries
    return admin_db.get_login_stats(days)


@router.get("/analytics/enrollments")
async def analytics_enrollments(days: int = 30, payload: dict = Depends(require_admin)):
    """Enrollment stats (placeholder — will pull from Zoho)."""
    days = max(1, min(days, 365))
    return {"total_new": 0, "days": days, "note": "Coming soon — Zoho CRM integration"}


@router.get("/analytics/features")
async def analytics_features(days: int = 30, payload: dict = Depends(require_admin)):
    """Feature usage from search_events table."""
    days = max(1, min(days, 365))
    return admin_db.get_search_stats(days)


@router.get("/analytics/carriers")
async def analytics_carriers(payload: dict = Depends(require_admin)):
    """Carrier distribution from extracted JSONs."""
    carrier_counts: dict[str, int] = {}
    if os.path.isdir(EXTRACTED_DIR):
        for fname in os.listdir(EXTRACTED_DIR):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(EXTRACTED_DIR, fname)) as f:
                    data = json.load(f)
                org = data.get("organization_name", "Other")
                # Simplify carrier name
                for c in ["Humana", "Aetna", "UHC", "UnitedHealthcare", "Wellcare",
                           "Devoted", "Cigna", "Molina", "Centene", "Elevance", "BCBS"]:
                    if c.lower() in org.lower():
                        org = c
                        break
                carrier_counts[org] = carrier_counts.get(org, 0) + 1
            except Exception:
                continue
    sorted_carriers = sorted(carrier_counts.items(), key=lambda x: x[1], reverse=True)
    total = sum(v for _, v in sorted_carriers)
    return [
        {"carrier": c, "count": n, "percentage": round(n / total * 100, 1) if total else 0}
        for c, n in sorted_carriers[:20]
    ]


@router.get("/analytics/states")
async def analytics_states(payload: dict = Depends(require_admin)):
    """State distribution — placeholder until Zoho CRM enrichment."""
    return {"note": "Coming soon — requires Zoho CRM address data"}


@router.get("/analytics/age-groups")
async def analytics_age_groups(payload: dict = Depends(require_admin)):
    """Age group distribution — placeholder."""
    return {"note": "Coming soon — requires Zoho CRM DOB data"}


# ════════════════════════════════════════════════════════════════════════════
#  PLANS & EXTRACTION ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@router.get("/plans")
async def list_plans(search: str = "", page: int = 1, per_page: int = 50,
                     payload: dict = Depends(require_admin)):
    """List all plans with extraction status."""
    per_page = max(1, min(per_page, 200))  # M16: cap pagination
    page = max(1, page)
    plans = []
    if not os.path.isdir(EXTRACTED_DIR):
        return {"data": [], "total": 0, "page": page, "per_page": per_page}

    for fname in sorted(os.listdir(EXTRACTED_DIR)):
        if not fname.endswith(".json") or fname.endswith("_benefits.json"):
            continue
        # Skip non-plan files
        if fname in ("AGREEMENT-FOR-USE.json",):
            continue
        plan_number = fname.replace(".json", "")
        try:
            with open(os.path.join(EXTRACTED_DIR, fname)) as f:
                data = json.load(f)
        except Exception:
            data = {}

        plan_name = data.get("plan_name", plan_number)
        carrier = data.get("organization_name", "Unknown")

        # Check if benefits file exists (naming: {plan_number}_benefits.json)
        benefits_path = os.path.join(EXTRACTED_DIR, f"{plan_number}_benefits.json")
        has_benefits = os.path.isfile(benefits_path)

        # Check if PDF exists (search all carrier subdirs)
        has_pdf = False
        if os.path.isdir(PDFS_DIR):
            for carrier_dir in os.listdir(PDFS_DIR):
                carrier_path = os.path.join(PDFS_DIR, carrier_dir)
                if os.path.isdir(carrier_path):
                    for pdf in os.listdir(carrier_path):
                        if plan_number in pdf:
                            has_pdf = True
                            break
                if has_pdf:
                    break

        entry = {
            "plan_number": plan_number,
            "plan_name": plan_name,
            "carrier": carrier,
            "plan_type": data.get("plan_type", ""),
            "has_extraction": True,
            "has_benefits": has_benefits,
            "has_pdf": has_pdf,
        }

        # Search filter
        if search:
            q = search.lower()
            if not (q in plan_number.lower() or q in plan_name.lower() or q in carrier.lower()):
                continue

        plans.append(entry)

    total = len(plans)
    start = (page - 1) * per_page
    return {
        "data": plans[start:start + per_page],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/plans/{plan_number}")
async def get_plan_detail(plan_number: str, payload: dict = Depends(require_admin)):
    """Get full plan data including extracted JSON and benefits."""
    extracted_path = os.path.join(EXTRACTED_DIR, f"{plan_number}.json")
    benefits_path = os.path.join(EXTRACTED_DIR, f"{plan_number}_benefits.json")

    # Path traversal prevention: resolved path must stay within EXTRACTED_DIR
    extract_real = os.path.realpath(EXTRACTED_DIR)
    if not os.path.realpath(extracted_path).startswith(extract_real + os.sep):
        raise HTTPException(status_code=400, detail="Invalid plan number.")
    if not os.path.realpath(benefits_path).startswith(extract_real + os.sep):
        raise HTTPException(status_code=400, detail="Invalid plan number.")

    if not os.path.isfile(extracted_path):
        raise HTTPException(status_code=404, detail=f"Plan {plan_number} not found.")

    with open(extracted_path) as f:
        extracted = json.load(f)

    benefits = None
    if os.path.isfile(benefits_path):
        with open(benefits_path) as f:
            benefits = json.load(f)

    return {"plan_number": plan_number, "extracted": extracted, "benefits": benefits}


@router.get("/extractions/stats")
async def extraction_stats(payload: dict = Depends(require_admin)):
    """Overview of extraction pipeline status."""
    total_extracted = 0
    total_benefits = 0
    total_pdfs = 0

    if os.path.isdir(EXTRACTED_DIR):
        for f in os.listdir(EXTRACTED_DIR):
            if f.endswith(".json"):
                if f.endswith("_benefits.json"):
                    total_benefits += 1
                elif f not in ("AGREEMENT-FOR-USE.json",):
                    total_extracted += 1

    if os.path.isdir(PDFS_DIR):
        for carrier_dir in os.listdir(PDFS_DIR):
            carrier_path = os.path.join(PDFS_DIR, carrier_dir)
            if os.path.isdir(carrier_path):
                total_pdfs += len([f for f in os.listdir(carrier_path) if f.endswith(".pdf")])

    return {
        "total_pdfs": total_pdfs,
        "total_extracted": total_extracted,
        "total_benefits": total_benefits,
        "missing_extraction": max(0, total_pdfs - total_extracted),
        "missing_benefits": max(0, total_extracted - total_benefits),
    }


# ════════════════════════════════════════════════════════════════════════════
#  SYSTEM HEALTH
# ════════════════════════════════════════════════════════════════════════════

_start_time = time.time()


@router.get("/system/health")
async def system_health(payload: dict = Depends(require_admin)):
    """System health check."""
    disk = shutil.disk_usage(EXTRACTED_DIR if os.path.isdir(EXTRACTED_DIR) else "/")
    return {
        "status": "healthy",
        "uptime_seconds": int(time.time() - _start_time),
        "disk_usage_gb": round(disk.used / (1024**3), 1),
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "extracted_dir": EXTRACTED_DIR,
        "pdfs_dir": PDFS_DIR,
    }


@router.get("/system/metrics")
async def system_metrics(payload: dict = Depends(require_admin)):
    """Basic system metrics."""
    return {
        "uptime_seconds": int(time.time() - _start_time),
        "login_stats": admin_db.get_login_stats(1),
        "search_stats": admin_db.get_search_stats(1),
    }


# ════════════════════════════════════════════════════════════════════════════
#  DATA UPLOAD (one-time migration — upload extracted JSONs to Render disk)
# ════════════════════════════════════════════════════════════════════════════

@router.post("/upload/extracted")
async def upload_extracted_tar(request: Request, file: UploadFile = File(...)):
    """
    Upload a tar.gz of extracted JSON files to EXTRACTED_DIR.

    Auth: JWT (admin/super_admin role required).

    Usage:
        curl -X POST https://iny-concierge.onrender.com/api/admin/upload/extracted \
             -H "Authorization: Bearer $ADMIN_JWT" \
             -F "file=@extracted_jsons.tar.gz"
    """
    # Require JWT auth — static secret fallback removed for security (per-user audit trail)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required.")
    payload = decode_admin_token(auth_header[7:])
    if payload.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions.")
    uploader = payload.get("email", payload.get("sub", "unknown"))

    if not file.filename or not file.filename.endswith((".tar.gz", ".tgz")):
        raise HTTPException(status_code=400, detail="File must be a .tar.gz archive.")

    os.makedirs(EXTRACTED_DIR, exist_ok=True)

    # Save to temp file first — cap at 500 MB
    MAX_TAR_BYTES = 500 * 1024 * 1024
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
    try:
        total_bytes = 0
        while chunk := await file.read(1024 * 1024):  # 1MB chunks
            total_bytes += len(chunk)
            if total_bytes > MAX_TAR_BYTES:
                tmp.close()
                os.unlink(tmp.name)
                raise HTTPException(status_code=413, detail=f"File too large (max {MAX_TAR_BYTES // (1024*1024)} MB).")
            tmp.write(chunk)
        tmp.close()

        log.info("Received %d MB tar.gz — extracting to %s",
                 total_bytes // (1024 * 1024), EXTRACTED_DIR)

        # M17: Validate gzip magic bytes before extraction
        with open(tmp.name, "rb") as f:
            magic = f.read(2)
        if magic != b"\x1f\x8b":
            raise HTTPException(status_code=400, detail="File is not a valid gzip archive.")

        # Extract — with path validation to prevent zip-slip attacks
        count = 0
        extract_real = os.path.realpath(EXTRACTED_DIR)
        with tarfile.open(tmp.name, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() or not member.name.endswith(".json"):
                    continue
                # Flatten — strip any directory prefix
                member.name = os.path.basename(member.name)
                # Reject symlinks and verify resolved path stays within target dir
                if member.issym() or member.islnk():
                    log.warning("Skipping symlink in tar: %s", member.name)
                    continue
                dest = os.path.realpath(os.path.join(EXTRACTED_DIR, member.name))
                if not dest.startswith(extract_real + os.sep):
                    log.warning("Skipping tar member outside target dir: %s", member.name)
                    continue
                tar.extract(member, EXTRACTED_DIR)
                count += 1

        log.info("Extracted %d JSON files to %s", count, EXTRACTED_DIR)

        # Count what's on disk now
        total_json = len([f for f in os.listdir(EXTRACTED_DIR) if f.endswith(".json")])
        benefits_json = len([f for f in os.listdir(EXTRACTED_DIR)
                             if f.endswith(".json") and f.startswith("benefits_")])
        # Handle the _benefits.json naming convention too
        benefits_alt = len([f for f in os.listdir(EXTRACTED_DIR)
                            if f.endswith("_benefits.json")])
        benefits_count = max(benefits_json, benefits_alt)

        get_audit_log().record(
            actor=uploader,
            action="upload",
            resource="extracted_data",
            ip_address=request.client.host if request.client else "",
            detail=f"files={count} size={round(total_bytes / (1024 * 1024), 1)}MB",
        )

        return {
            "success": True,
            "files_extracted": count,
            "total_json_on_disk": total_json,
            "benefits_files": benefits_count,
            "extracted_dir": EXTRACTED_DIR,
            "upload_size_mb": round(total_bytes / (1024 * 1024), 1),
        }
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


# ════════════════════════════════════════════════════════════════════════════
#  HEALTH SCREENING CONFIG (admin manages which screenings members see)
# ════════════════════════════════════════════════════════════════════════════

class ScreeningItem(BaseModel):
    id: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=200)
    timeframe: str = Field(..., min_length=1, max_length=200)
    frequency: str = Field(..., min_length=1, max_length=50)


class ScreeningConfigRequest(BaseModel):
    shared: list[ScreeningItem] = Field(default_factory=list)
    male: list[ScreeningItem] = Field(default_factory=list)
    female: list[ScreeningItem] = Field(default_factory=list)


@router.get("/screening-config")
async def get_screening_config(payload: dict = Depends(require_admin)):
    """Get the current screening questionnaire configuration."""
    config = _get_store().get_screening_config()
    return config or {"shared": [], "male": [], "female": []}


@router.put("/screening-config")
async def set_screening_config(body: ScreeningConfigRequest,
                               request: Request,
                               payload: dict = Depends(require_admin)):
    """Set the screening questionnaire configuration (replaces all)."""
    config = body.model_dump()
    _get_store().set_screening_config(config)

    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="update",
        resource="screening_config",
        resource_id="global",
        ip_address=request.client.host if request.client else "",
        detail=f"shared={len(config['shared'])} male={len(config['male'])} female={len(config['female'])}",
    )
    log.info("Admin %s updated screening config: %d shared, %d male, %d female",
             payload.get("sub"), len(config["shared"]), len(config["male"]), len(config["female"]))
    return {"success": True, "config": config}


# ════════════════════════════════════════════════════════════════════════════
#  HEALTH SCREENING GAP REPORT (admin views screening completion data)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/screening-gap-report")
async def screening_gap_report(payload: dict = Depends(require_admin)):
    """
    Get aggregated screening gap data for all members who completed the checklist.
    Shows per-screening completion rates and identifies members with gaps.
    """
    from .user_data import UserDataDB
    udb = UserDataDB()
    results = udb.get_all_screening_results()

    if not results:
        return {
            "total_members": 0,
            "screenings": [],
            "members_with_gaps": [],
            "summary": {"completed_rate": 0, "avg_gaps_per_member": 0,
                        "members_all_complete": 0, "members_with_gaps_count": 0},
        }

    # Get screening config for labels
    config = _get_store().get_screening_config() or {}
    shared = config.get("shared", [])
    male_screenings = config.get("male", [])
    female_screenings = config.get("female", [])

    # Fall back to default screening IDs if no admin config
    if not shared:
        shared = [
            {"id": "awv", "label": "Annual Wellness Visit"},
            {"id": "flu", "label": "Flu Shot"},
            {"id": "colonoscopy", "label": "Colonoscopy"},
            {"id": "cholesterol", "label": "Cholesterol / Blood Work"},
            {"id": "a1c", "label": "Diabetes Screening (A1C)"},
            {"id": "fall_risk", "label": "Fall Risk Assessment"},
        ]
    if not male_screenings:
        male_screenings = [{"id": "prostate", "label": "Prostate (PSA) Screening"}]
    if not female_screenings:
        female_screenings = [
            {"id": "mammogram", "label": "Mammogram"},
            {"id": "bone_density", "label": "Bone Density Scan (DEXA)"},
        ]

    # Aggregate per-screening stats
    screening_stats = {}
    members_with_gaps = []

    for member in results:
        answers = member.get("answers", {})
        gender = member.get("gender", "")

        applicable = list(shared)
        if gender == "male":
            applicable += male_screenings
        elif gender == "female":
            applicable += female_screenings

        gap_count = 0
        gap_labels = []
        for screening in applicable:
            sid = screening.get("id", "") if isinstance(screening, dict) else ""
            label = screening.get("label", sid) if isinstance(screening, dict) else str(screening)
            if sid not in screening_stats:
                screening_stats[sid] = {"id": sid, "label": label, "yes": 0, "no": 0, "total": 0}
            screening_stats[sid]["total"] += 1
            if answers.get(sid) is True:
                screening_stats[sid]["yes"] += 1
            else:
                screening_stats[sid]["no"] += 1
                gap_count += 1
                gap_labels.append(label)

        if gap_count > 0:
            members_with_gaps.append({
                "phone_last4": member.get("phone_last4", "****"),
                "gender": gender,
                "gap_count": gap_count,
                "gaps": gap_labels,
                "screened_at": member.get("created_at", ""),
            })

    screenings_list = []
    for _sid, stats in screening_stats.items():
        pct = round((stats["yes"] / stats["total"]) * 100, 1) if stats["total"] > 0 else 0
        screenings_list.append({
            "id": stats["id"],
            "label": stats["label"],
            "completed": stats["yes"],
            "not_completed": stats["no"],
            "total": stats["total"],
            "completion_pct": pct,
        })
    screenings_list.sort(key=lambda x: x["completion_pct"])

    members_with_gaps.sort(key=lambda x: -x["gap_count"])

    total_members = len(results)
    total_gaps = sum(m["gap_count"] for m in members_with_gaps)
    avg_gaps = round(total_gaps / total_members, 1) if total_members > 0 else 0
    members_all_done = total_members - len(members_with_gaps)
    completed_rate = round((members_all_done / total_members) * 100, 1) if total_members > 0 else 0

    return {
        "total_members": total_members,
        "screenings": screenings_list,
        "members_with_gaps": members_with_gaps[:100],
        "summary": {
            "completed_rate": completed_rate,
            "avg_gaps_per_member": avg_gaps,
            "members_all_complete": members_all_done,
            "members_with_gaps_count": len(members_with_gaps),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
#  SDOH REPORT (admin views social determinants flags for outreach)
# ════════════════════════════════════════════════════════════════════════════

SDOH_BENEFIT_MAP = {
    "transportation": {
        "label": "Transportation Barrier",
        "benefit": "Non-Emergency Medical Transportation (NEMT)",
        "action": "Help member schedule free rides to appointments",
    },
    "food_insecurity": {
        "label": "Food Insecurity",
        "benefit": "Grocery/Meal Allowance (OTC Card)",
        "action": "Walk member through OTC grocery benefit usage",
    },
    "social_isolation": {
        "label": "Social Isolation",
        "benefit": "SilverSneakers / Community Programs",
        "action": "Connect member with fitness & social programs",
    },
    "housing_stability": {
        "label": "Housing Instability",
        "benefit": "Case Management / Utility Assistance",
        "action": "Refer to plan case manager for housing support",
    },
}


@router.get("/sdoh-report")
async def sdoh_report(payload: dict = Depends(require_admin)):
    """Get aggregated SDoH screening data for all members."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    results = udb.get_all_sdoh_results()

    if not results:
        return {
            "total_screened": 0,
            "flag_summary": [],
            "members": [],
            "benefit_recommendations": list(SDOH_BENEFIT_MAP.values()),
        }

    # Aggregate flag counts
    flag_counts = {
        "transportation": 0,
        "food_insecurity": 0,
        "social_isolation": 0,
        "housing_stability": 0,
    }
    for m in results:
        for flag in m["flags"]:
            if flag in flag_counts:
                flag_counts[flag] += 1

    total = len(results)
    flag_summary = []
    for key, count in flag_counts.items():
        info = SDOH_BENEFIT_MAP.get(key, {})
        pct = round((count / total) * 100, 1) if total > 0 else 0
        flag_summary.append({
            "flag": key,
            "label": info.get("label", key),
            "count": count,
            "total": total,
            "pct": pct,
            "benefit": info.get("benefit", ""),
            "action": info.get("action", ""),
        })
    flag_summary.sort(key=lambda x: -x["count"])

    # Members with any flags, sorted by most flags
    flagged_members = [m for m in results if m["flag_count"] > 0]
    flagged_members.sort(key=lambda x: -x["flag_count"])

    return {
        "total_screened": total,
        "total_with_flags": len(flagged_members),
        "flag_summary": flag_summary,
        "members": flagged_members[:100],
        "benefit_recommendations": list(SDOH_BENEFIT_MAP.values()),
    }


# ════════════════════════════════════════════════════════════════════════════
#  APPOINTMENT REQUESTS (agent views and manages member requests)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/appointment-requests")
async def list_appointment_requests(
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    payload: dict = Depends(require_admin),
):
    """List appointment requests with optional status filter."""
    from .user_data import UserDataDB
    per_page = max(1, min(per_page, 200))
    page = max(1, page)
    udb = UserDataDB()
    total = udb.count_appointment_requests(status)
    requests = udb.list_appointment_requests(
        status=status, limit=per_page, offset=(page - 1) * per_page,
    )
    return {
        "data": requests,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pending_count": udb.count_appointment_requests("pending"),
    }


class UpdateAppointmentRequest(BaseModel):
    status: Optional[str] = Field(None, pattern=r"^(pending|in_progress|completed|cancelled)$")
    agent_notes: Optional[str] = Field(None, max_length=1000)


@router.patch("/appointment-requests/{request_id}")
async def update_appointment_request(
    request_id: int,
    body: UpdateAppointmentRequest,
    request: Request,
    payload: dict = Depends(require_role("admin", "super_admin")),
):
    """Update appointment request status or add agent notes."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    updated = udb.update_appointment_request(
        request_id, status=body.status, agent_notes=body.agent_notes,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Appointment request not found.")
    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="update",
        resource="appointment_request",
        resource_id=str(request_id),
        ip_address=request.client.host if request.client else "",
        detail=f"status={body.status or 'unchanged'}",
    )
    return {"success": True, "request": updated}


# ════════════════════════════════════════════════════════════════════════════
#  AGENT PHONE INTAKE — submit screening / SDOH on behalf of a member
# ════════════════════════════════════════════════════════════════════════════

class AgentHealthScreeningRequest(BaseModel):
    gender: str = Field("", max_length=20)
    answers: dict = Field(default_factory=dict)
    reminders: list = Field(default_factory=list)

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        allowed = {"male", "female", "other", ""}
        if v.lower() not in allowed:
            raise ValueError(f"gender must be one of {allowed}")
        return v.lower()

    @field_validator("reminders")
    @classmethod
    def limit_reminders(cls, v: list) -> list:
        if len(v) > 100:
            raise ValueError("Too many reminders (max 100).")
        return v


@router.post("/members/{phone}/health-screening")
async def admin_submit_health_screening(
    phone: str,
    body: AgentHealthScreeningRequest,
    request: Request,
    payload: dict = Depends(require_role("admin", "super_admin")),
):
    """Agent submits a health-screening on behalf of a member (phone intake)."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    data = body.model_dump()
    data["submitted_by"] = "agent"
    data["agent_username"] = payload.get("sub", "unknown")
    udb.save_health_screenings(phone, data)
    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="create",
        resource="health_screening",
        resource_id=phone[-4:],
        ip_address=request.client.host if request.client else "",
        detail=f"agent_phone_intake gender={body.gender} answers={len(body.answers)}",
    )
    log.info("Agent %s submitted health screening for member ***%s", payload.get("sub"), phone[-4:])
    return {"success": True}


class AgentSDoHScreeningRequest(BaseModel):
    transportation: str = Field("no", pattern=r"^(yes|no)$")
    food_insecurity: str = Field("no", pattern=r"^(yes|no)$")
    social_isolation: str = Field("never", pattern=r"^(never|rarely|sometimes|often|always)$")
    housing_stability: str = Field("no", pattern=r"^(yes|no)$")


@router.post("/members/{phone}/sdoh-screening")
async def admin_submit_sdoh_screening(
    phone: str,
    body: AgentSDoHScreeningRequest,
    request: Request,
    payload: dict = Depends(require_role("admin", "super_admin")),
):
    """Agent submits an SDOH screening on behalf of a member (phone intake)."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    udb.save_sdoh_screening(phone, body.model_dump())
    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="create",
        resource="sdoh_screening",
        resource_id=phone[-4:],
        ip_address=request.client.host if request.client else "",
        detail="agent_phone_intake",
    )
    log.info("Agent %s submitted SDOH screening for member ***%s", payload.get("sub"), phone[-4:])
    return {"success": True}


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN REMINDER CRUD (manage reminders on behalf of a member)
# ════════════════════════════════════════════════════════════════════════════


class AdminReminderCreate(BaseModel):
    drug_name: str = Field(..., min_length=1, max_length=200)
    dose_label: str = Field("", max_length=200)
    time_hour: int = Field(..., ge=0, le=23)
    time_minute: int = Field(0, ge=0, le=59)


class AdminReminderUpdate(BaseModel):
    enabled: Optional[bool] = None
    time_hour: Optional[int] = Field(None, ge=0, le=23)
    time_minute: Optional[int] = Field(None, ge=0, le=59)
    dose_label: Optional[str] = Field(None, max_length=200)


@router.get("/members/{phone}/reminders")
async def admin_list_reminders(
    phone: str,
    payload: dict = Depends(require_admin),
):
    """List all medication reminders for a member."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    return {"reminders": udb.get_reminders(phone)}


@router.post("/members/{phone}/reminders")
async def admin_create_reminder(
    phone: str,
    body: AdminReminderCreate,
    request: Request,
    payload: dict = Depends(require_role("admin", "super_admin")),
):
    """Create a medication reminder for a member."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    reminder = udb.create_reminder(
        phone=phone,
        drug_name=body.drug_name,
        time_hour=body.time_hour,
        time_minute=body.time_minute,
        dose_label=body.dose_label,
    )
    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="create",
        resource="reminder",
        resource_id=f"***{phone[-4:]}:{reminder.get('id', '')}",
        ip_address=request.client.host if request.client else "",
        detail=f"admin_create_reminder drug={body.drug_name}",
    )
    return {"reminder": reminder}


@router.put("/members/{phone}/reminders/{reminder_id}")
async def admin_update_reminder(
    phone: str,
    reminder_id: int,
    body: AdminReminderUpdate,
    request: Request,
    payload: dict = Depends(require_role("admin", "super_admin")),
):
    """Update a medication reminder (toggle enabled, change time, etc.)."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    reminder = udb.update_reminder(phone, reminder_id, **body.model_dump(exclude_none=True))
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="update",
        resource="reminder",
        resource_id=f"***{phone[-4:]}:{reminder_id}",
        ip_address=request.client.host if request.client else "",
        detail="admin_update_reminder",
    )
    return {"reminder": reminder}


@router.delete("/members/{phone}/reminders/{reminder_id}")
async def admin_delete_reminder(
    phone: str,
    reminder_id: int,
    request: Request,
    payload: dict = Depends(require_role("admin", "super_admin")),
):
    """Delete a medication reminder."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    deleted = udb.delete_reminder(phone, reminder_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="delete",
        resource="reminder",
        resource_id=f"***{phone[-4:]}:{reminder_id}",
        ip_address=request.client.host if request.client else "",
        detail="admin_delete_reminder",
    )
    return {"deleted": True}


# ════════════════════════════════════════════════════════════════════════════
#  MEMBER DETAIL — GET /api/admin/members/{phone}
# ════════════════════════════════════════════════════════════════════════════


@router.get("/members/{phone}")
async def admin_get_member(
    phone: str,
    payload: dict = Depends(require_admin),
):
    """
    Fetch full member detail: Zoho CRM data merged with local DB
    (reminders, screenings, SDOH, activity).
    """
    from .user_data import UserDataDB

    clean = _normalize_phone(phone)
    if len(clean) != 10:
        raise HTTPException(status_code=400, detail="Invalid phone number.")

    # 1) Try Zoho CRM for core member profile
    zoho_data = None
    try:
        zoho_data = search_contact_by_phone(clean)
    except Exception:
        log.warning("Zoho lookup failed for ***%s, falling back to local", clean[-4:])

    # 2) Check local session store for members created locally
    session = _get_store().find_session_by_phone(clean)

    if not zoho_data and not session:
        raise HTTPException(status_code=404, detail="Member not found.")

    # Merge: Zoho takes precedence, local session fills gaps
    zoho = zoho_data or {}
    local = session.get("data", {}) if session else {}

    # 3) Pull local DB data
    udb = UserDataDB()
    reminders_raw = udb.get_reminders(clean)
    reminders = [
        {
            "id": r["id"],
            "drug_name": r["drug_name"],
            "dose": r.get("dose_label", ""),
            "time": f"{r['time_hour']:02d}:{r['time_minute']:02d}",
            "enabled": bool(r.get("enabled", 1)),
        }
        for r in reminders_raw
    ]

    # 4) Activity from session timestamps
    from datetime import datetime as _dt

    activity = []
    if session:
        ts = session.get("ts", 0)
        if ts:
            activity.append({
                "type": "login",
                "desc": "Logged in via OTP",
                "time": _dt.utcfromtimestamp(ts).strftime("%b %d, %Y %I:%M %p"),
            })

    # 5) Build unified response
    member = {
        "id": clean,
        "first_name": zoho.get("first_name") or local.get("first_name", ""),
        "last_name": zoho.get("last_name") or local.get("last_name", ""),
        "phone": clean,
        "email": zoho.get("email", local.get("email", "")),
        "zip_code": zoho.get("zip_code") or local.get("zip_code", ""),
        "dob": zoho.get("dob", local.get("dob", "")),
        "address": zoho.get("address", local.get("address", "")),
        "carrier": zoho.get("carrier", local.get("carrier", "")),
        "plan_name": zoho.get("plan_name") or local.get("plan_name", ""),
        "plan_number": zoho.get("plan_number") or local.get("plan_number", ""),
        "agent": zoho.get("agent") or local.get("agent", ""),
        "status": "active" if session else "active",
        "created_at": _dt.utcfromtimestamp(session["ts"]).strftime("%b %d, %Y") if session else "",
        "last_login": _dt.utcfromtimestamp(session["ts"]).strftime("%b %d, %Y %I:%M %p") if session else "",
        "reminders": reminders,
        "activity": activity,
    }

    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="read",
        resource="member",
        resource_id=f"***{clean[-4:]}",
        ip_address="",
        detail="admin_get_member",
    )

    return member


# ════════════════════════════════════════════════════════════════════════════
#  NOTIFICATIONS — agent-to-member push notifications
# ════════════════════════════════════════════════════════════════════════════


class NotificationSend(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=1000)
    category: str = Field("general", max_length=50)


class PushTokenRegister(BaseModel):
    push_token: str = Field(..., min_length=10, max_length=200)


def _ensure_notification_tables():
    """Create notification + push_token tables if they don't exist."""
    store = _get_store()
    conn = store._conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS notifications (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            phone           TEXT NOT NULL,
            phone_hash      TEXT NOT NULL,
            title           TEXT NOT NULL,
            body            TEXT NOT NULL,
            category        TEXT NOT NULL DEFAULT 'general',
            read            INTEGER NOT NULL DEFAULT 0,
            sent_by         TEXT NOT NULL DEFAULT '',
            created_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_notif_phone_hash
            ON notifications(phone_hash);

        CREATE TABLE IF NOT EXISTS push_tokens (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            phone           TEXT NOT NULL,
            phone_hash      TEXT NOT NULL,
            push_token      TEXT NOT NULL,
            platform        TEXT NOT NULL DEFAULT 'expo',
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_push_phone_hash
            ON push_tokens(phone_hash);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_push_token_unique
            ON push_tokens(push_token);
    """)
    conn.commit()


# Ensure tables on module load
try:
    _ensure_notification_tables()
except Exception:
    pass  # Tables created lazily on first use if startup fails


def _phone_hash(phone: str) -> str:
    """Consistent phone hashing matching PersistentStore."""
    import hashlib
    import hmac as _hmac
    key = os.environ.get("FIELD_ENCRYPTION_KEY", "dev-key").encode()
    return _hmac.new(key, phone.encode(), hashlib.sha256).hexdigest()


@router.post("/members/{phone}/notifications")
async def admin_send_notification(
    phone: str,
    body: NotificationSend,
    request: Request,
    payload: dict = Depends(require_role("admin", "super_admin")),
):
    """Send a push notification to a member from the admin panel."""
    clean = _normalize_phone(phone)
    if len(clean) != 10:
        raise HTTPException(status_code=400, detail="Invalid phone number.")

    _ensure_notification_tables()
    store = _get_store()
    conn = store._conn()
    ph = _phone_hash(clean)

    # 1) Persist notification record
    cursor = conn.execute(
        """INSERT INTO notifications (phone, phone_hash, title, body, category, sent_by)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (clean, ph, body.title, body.body, body.category, payload.get("sub", "admin")),
    )
    notif_id = cursor.lastrowid
    conn.commit()

    # 2) Try to deliver via Expo Push (best-effort)
    push_sent = False
    rows = conn.execute(
        "SELECT push_token FROM push_tokens WHERE phone_hash = ?", (ph,)
    ).fetchall()

    if rows:
        import httpx
        tokens = [r["push_token"] for r in rows]
        messages = [
            {
                "to": t,
                "title": body.title,
                "body": body.body,
                "data": {"type": "admin_notification", "notification_id": notif_id, "category": body.category},
                "sound": "default",
            }
            for t in tokens
        ]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://exp.host/--/api/v2/push/send",
                    json=messages,
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                )
                push_sent = resp.status_code == 200
                if not push_sent:
                    log.warning("Expo push failed for ***%s: %s", clean[-4:], resp.text[:200])
        except Exception as e:
            log.warning("Expo push error for ***%s: %s", clean[-4:], type(e).__name__)

    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="send_notification",
        resource="notification",
        resource_id=f"***{clean[-4:]}:{notif_id}",
        ip_address=request.client.host if request.client else "",
        detail=f"category={body.category} push_sent={push_sent}",
    )

    return {
        "success": True,
        "notification_id": notif_id,
        "push_delivered": push_sent,
        "push_tokens_found": len(rows),
    }


@router.get("/members/{phone}/notifications")
async def admin_get_notifications(
    phone: str,
    payload: dict = Depends(require_admin),
):
    """Get notification history for a member."""
    clean = _normalize_phone(phone)
    _ensure_notification_tables()
    conn = _get_store()._conn()
    ph = _phone_hash(clean)
    rows = conn.execute(
        "SELECT * FROM notifications WHERE phone_hash = ? ORDER BY created_at DESC LIMIT 50",
        (ph,),
    ).fetchall()
    return {"notifications": [dict(r) for r in rows]}


# ════════════════════════════════════════════════════════════════════════════
#  C: SCREENING / SDOH HISTORY
# ════════════════════════════════════════════════════════════════════════════


@router.get("/members/{phone}/health-screening")
async def admin_get_health_screening(
    phone: str,
    payload: dict = Depends(require_admin),
):
    """Get a member's most recent health screening (for pre-populating the form)."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    result = udb.get_health_screenings(phone)
    return {"screening": result}


@router.get("/members/{phone}/sdoh-screening")
async def admin_get_sdoh_screening(
    phone: str,
    payload: dict = Depends(require_admin),
):
    """Get a member's most recent SDOH screening (for pre-populating the form)."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    result = udb.get_sdoh_screening(phone)
    return {"screening": result}


@router.get("/members/{phone}/screening-history")
async def admin_get_screening_history(
    phone: str,
    payload: dict = Depends(require_admin),
):
    """Get full screening + SDOH history timeline for a member."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    clean = _normalize_phone(phone)
    screenings = udb.get_health_screening_history(clean)
    sdoh = udb.get_sdoh_screening_history(clean)
    return {
        "screenings": screenings,
        "sdoh": sdoh,
    }


# ════════════════════════════════════════════════════════════════════════════
#  E: BENEFITS UTILIZATION ALERTS
# ════════════════════════════════════════════════════════════════════════════


@router.get("/members/{phone}/utilization-alerts")
async def admin_get_utilization_alerts(
    phone: str,
    payload: dict = Depends(require_admin),
):
    """
    Check a member's benefits utilization and return alerts for:
    - OTC/flex allowance expiring unused
    - Screening gaps approaching deadlines
    - Medication refill alerts
    """
    from datetime import date as _date

    from .user_data import UserDataDB

    clean = _normalize_phone(phone)
    if len(clean) != 10:
        raise HTTPException(status_code=400, detail="Invalid phone number.")

    udb = UserDataDB()
    alerts = []

    # 1) Screening gaps — check latest health screening
    latest_screening = udb.get_health_screenings(clean)
    if latest_screening:
        answers = latest_screening.get("answers", {})
        SCREENING_LABELS = {
            "awv": "Annual Wellness Visit",
            "flu": "Flu Shot",
            "colonoscopy": "Colonoscopy",
            "cholesterol": "Cholesterol / Blood Work",
            "a1c": "Diabetes Screening (A1C)",
            "fall_risk": "Fall Risk Assessment",
            "mammogram": "Mammogram",
            "bone_density": "Bone Density Scan",
            "prostate": "Prostate (PSA) Screening",
        }
        gaps = [
            SCREENING_LABELS.get(k, k)
            for k, v in answers.items()
            if v is False or v == "no"
        ]
        if gaps:
            alerts.append({
                "type": "screening_gap",
                "severity": "warning",
                "title": f"{len(gaps)} screening gap{'s' if len(gaps) != 1 else ''}",
                "body": f"Missing: {', '.join(gaps[:4])}{'...' if len(gaps) > 4 else ''}",
                "gaps": gaps,
                "screened_at": latest_screening.get("created_at", ""),
            })
    else:
        alerts.append({
            "type": "screening_gap",
            "severity": "info",
            "title": "No screening on file",
            "body": "This member has never completed a health screening.",
            "gaps": [],
        })

    # 2) SDOH risk flags
    latest_sdoh = udb.get_sdoh_screening(clean)
    if latest_sdoh:
        sdoh_flags = []
        if latest_sdoh.get("transportation") == "yes":
            sdoh_flags.append("Transportation barrier")
        if latest_sdoh.get("food_insecurity") == "yes":
            sdoh_flags.append("Food insecurity")
        if latest_sdoh.get("social_isolation") in ("sometimes", "often", "always"):
            sdoh_flags.append("Social isolation")
        if latest_sdoh.get("housing_stability") == "yes":
            sdoh_flags.append("Housing instability")
        if sdoh_flags:
            alerts.append({
                "type": "sdoh_risk",
                "severity": "warning",
                "title": f"{len(sdoh_flags)} SDOH risk factor{'s' if len(sdoh_flags) != 1 else ''}",
                "body": ", ".join(sdoh_flags),
                "flags": sdoh_flags,
            })

    # 3) Benefits usage — check if member has plan, then check utilization
    zoho_data = None
    try:
        zoho_data = search_contact_by_phone(clean)
    except Exception:
        pass

    plan_number = None
    if zoho_data:
        plan_number = zoho_data.get("plan_number")
    if not plan_number:
        session = _get_store().find_session_by_phone(clean)
        if session:
            plan_number = session.get("data", {}).get("plan_number")

    if plan_number:
        try:
            from .cms_lookup import CMSLookup
            cms = CMSLookup()
            today = _date.today()

            # OTC allowance check
            otc = cms.get_otc_allowance(plan_number)
            if otc and otc.get("has_otc") and otc.get("amount"):
                amount_str = otc["amount"].replace("$", "").replace(",", "")
                try:
                    otc_cap = float(amount_str)
                    period = otc.get("period", "Monthly")
                    totals = udb.get_current_period_totals(clean, {"otc": period})
                    spent = totals.get("otc", 0)
                    remaining = otc_cap - spent
                    pct_used = round(spent / otc_cap * 100) if otc_cap > 0 else 0

                    if pct_used < 25:
                        alerts.append({
                            "type": "otc_underuse",
                            "severity": "info",
                            "title": f"${remaining:.0f} OTC allowance unused",
                            "body": f"Only {pct_used}% of ${otc_cap:.0f}/{period.lower()} OTC benefit used. Remind member to order health essentials.",
                            "cap": otc_cap,
                            "spent": spent,
                            "remaining": remaining,
                            "period": period,
                        })
                except (ValueError, TypeError):
                    pass

            # Flu shot season check (Sept-Mar)
            if today.month >= 9 or today.month <= 3:
                if latest_screening:
                    flu_done = latest_screening.get("answers", {}).get("flu")
                    if not flu_done:
                        alerts.append({
                            "type": "flu_season",
                            "severity": "warning",
                            "title": "Flu season — no flu shot recorded",
                            "body": "It's flu season and this member hasn't reported getting their flu shot. Covered at $0 under most plans.",
                        })
        except Exception as e:
            log.warning("Utilization alert check failed for ***%s: %s", clean[-4:], type(e).__name__)

    # 4) Medication refill alerts
    refill_alerts = udb.get_refill_alerts(clean)
    for ra in refill_alerts:
        alerts.append({
            "type": "refill_due",
            "severity": "warning",
            "title": f"{ra['drug_name']} refill due",
            "body": f"Due in {ra.get('days_until_refill', '?')} days ({ra.get('refill_due_date', 'unknown')})",
        })

    return {"alerts": alerts}


# ════════════════════════════════════════════════════════════════════════════
#  F: SECURE MESSAGING (agent ↔ member)
# ════════════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════════════
#  K: BULK OUTREACH / CAMPAIGN MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    cohort_type: str = Field(..., pattern=r"^(screening_gap|otc_underuse|sdoh_flag|custom)$")
    cohort_filter: dict = Field(default_factory=dict)
    message_template: str = Field(..., min_length=1, max_length=1600)


@router.get("/campaigns")
async def list_campaigns(
    payload: dict = Depends(require_role("admin", "super_admin")),
):
    """List all campaigns."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    campaigns = udb.get_campaigns()
    return {"campaigns": campaigns}


@router.post("/campaigns")
async def create_campaign(
    body: CampaignCreate,
    request: Request,
    payload: dict = Depends(require_role("admin", "super_admin")),
):
    """Create a new campaign (draft status)."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    campaign = udb.create_campaign(
        name=body.name,
        cohort_type=body.cohort_type,
        cohort_filter=body.cohort_filter,
        message_template=body.message_template,
        created_by=payload.get("sub", "unknown"),
    )
    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="create_campaign",
        resource="campaign",
        resource_id=str(campaign.get("id", "")),
        ip_address=request.client.host if request.client else "",
        detail=f"cohort={body.cohort_type}",
    )
    return {"campaign": campaign}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: int,
    payload: dict = Depends(require_role("admin", "super_admin")),
):
    """Get campaign details."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    campaign = udb.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return {"campaign": campaign}


@router.get("/campaigns/{campaign_id}/preview")
async def preview_campaign_cohort(
    campaign_id: int,
    payload: dict = Depends(require_role("admin", "super_admin")),
):
    """Preview the cohort that will receive the campaign. Returns count and sample."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    campaign = udb.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    cohort = _resolve_cohort(udb, campaign["cohort_type"], campaign["cohort_filter"])
    return {
        "total": len(cohort),
        "sample": [{"phone_last4": p[-4:]} for p in cohort[:10]],
    }


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(
    campaign_id: int,
    request: Request,
    payload: dict = Depends(require_role("admin", "super_admin")),
):
    """Send the campaign SMS to all cohort members."""
    from .user_data import UserDataDB
    udb = UserDataDB()
    campaign = udb.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    if campaign["status"] == "sent":
        raise HTTPException(status_code=400, detail="Campaign already sent.")

    # Resolve cohort
    cohort = _resolve_cohort(udb, campaign["cohort_type"], campaign["cohort_filter"])
    if not cohort:
        raise HTTPException(status_code=400, detail="No recipients match the cohort criteria.")

    # Store recipients
    udb.set_campaign_recipients(campaign_id, cohort)

    # Send SMS via Twilio
    sms = create_sms_provider()
    sent = 0
    failed = 0
    for phone in cohort:
        try:
            success = _send_campaign_sms(sms, phone, campaign["message_template"])
            if success:
                sent += 1
            else:
                failed += 1
        except Exception as e:
            log.warning("Campaign SMS failed for ...%s: %s", phone[-4:], e)
            failed += 1

    udb.update_campaign_status(campaign_id, "sent", sent, failed)

    get_audit_log().record(
        actor=payload.get("sub", "unknown"),
        action="send_campaign",
        resource="campaign",
        resource_id=str(campaign_id),
        ip_address=request.client.host if request.client else "",
        detail=f"sent={sent} failed={failed} total={len(cohort)}",
    )

    return {
        "status": "sent",
        "total_recipients": len(cohort),
        "sent": sent,
        "failed": failed,
    }


def _resolve_cohort(udb, cohort_type: str, cohort_filter: dict) -> list[str]:
    """Resolve a cohort type + filter to a list of phone numbers."""
    if cohort_type == "screening_gap":
        gap_type = cohort_filter.get("gap_type")
        members = udb.get_cohort_screening_gaps(gap_type)
        return [m["phone"] for m in members]
    elif cohort_type == "otc_underuse":
        min_unused = cohort_filter.get("min_unused", 100.0)
        members = udb.get_cohort_otc_underuse(min_unused)
        return [m["phone"] for m in members]
    elif cohort_type == "sdoh_flag":
        flag_type = cohort_filter.get("flag_type")
        members = udb.get_cohort_sdoh_flags(flag_type)
        return [m["phone"] for m in members]
    elif cohort_type == "custom":
        # Custom phone list provided directly
        return cohort_filter.get("phones", [])
    return []


def _send_campaign_sms(sms, phone: str, message: str) -> bool:
    """Send a campaign SMS message (not OTP — uses general messaging)."""
    try:
        from twilio.rest import Client
        if hasattr(sms, 'client') and isinstance(sms.client, Client):
            msg = sms.client.messages.create(
                body=message,
                from_=sms.from_number,
                to=f"+1{phone}",
            )
            log.info("Campaign SMS sent to ...%s: sid=%s", phone[-4:], msg.sid)
            return True
        else:
            # Console provider — just log
            log.info("[DEV CAMPAIGN SMS] To: ...%s Message: %s", phone[-4:], message[:50])
            return True
    except Exception as e:
        log.error("Campaign SMS failed for ...%s: %s", phone[-4:], e)
        return False


# ════════════════════════════════════════════════════════════════════════════
#  L: AGENT CALL NOTES / CRM INTEGRATION
# ════════════════════════════════════════════════════════════════════════════


class CallNoteCreate(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=5000)
    call_type: str = Field("outbound", pattern=r"^(inbound|outbound|follow_up)$")
    duration_minutes: int = Field(0, ge=0, le=999)
    sync_to_zoho: bool = True


@router.get("/members/{phone}/call-notes")
async def get_call_notes(
    phone: str,
    payload: dict = Depends(require_admin),
):
    """Get all call notes for a member."""
    from .user_data import UserDataDB
    clean = _normalize_phone(phone)
    udb = UserDataDB()
    notes = udb.get_call_notes(clean)
    return {"notes": notes}


@router.post("/members/{phone}/call-notes")
async def create_call_note(
    phone: str,
    body: CallNoteCreate,
    request: Request,
    payload: dict = Depends(require_role("admin", "super_admin")),
):
    """Create a call note for a member, optionally syncing to Zoho CRM."""
    from .user_data import UserDataDB
    clean = _normalize_phone(phone)
    if len(clean) != 10:
        raise HTTPException(status_code=400, detail="Invalid phone number.")

    udb = UserDataDB()
    agent_name = payload.get("sub", "Agent")
    note = udb.create_call_note(
        phone=clean,
        subject=body.subject,
        body=body.body,
        call_type=body.call_type,
        duration_minutes=body.duration_minutes,
        agent_name=agent_name,
    )

    # Sync to Zoho if requested
    zoho_synced = False
    zoho_error = ""
    if body.sync_to_zoho:
        try:
            zoho_synced = _sync_note_to_zoho(clean, body.subject, body.body, agent_name)
        except Exception as e:
            zoho_error = str(e)
            log.warning("Zoho note sync failed for ...%s: %s", clean[-4:], e)

    if zoho_synced:
        udb.mark_note_synced(note["id"])

    get_audit_log().record(
        actor=agent_name,
        action="create_call_note",
        resource="call_note",
        resource_id=f"***{clean[-4:]}:{note.get('id', '')}",
        ip_address=request.client.host if request.client else "",
        detail=f"type={body.call_type} zoho_synced={zoho_synced}",
    )

    return {
        "note": note,
        "zoho_synced": zoho_synced,
        "zoho_error": zoho_error,
    }


def _sync_note_to_zoho(phone: str, subject: str, body: str, agent_name: str) -> bool:
    """Push a call note to the Zoho CRM contact record."""
    from .zoho_client import API_BASE, _http, get_access_token

    # First find the contact
    contact = search_contact_by_phone(phone)
    if not contact or not contact.get("id"):
        log.warning("Zoho sync: no contact found for ...%s", phone[-4:])
        return False

    token = get_access_token()
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type": "application/json",
    }

    # Create a note on the contact
    note_data = {
        "data": [{
            "Note_Title": subject,
            "Note_Content": f"[{agent_name}] {body}",
            "Parent_Id": contact["id"],
            "se_module": "Contacts",
        }]
    }

    resp = _http.post(
        f"{API_BASE}/Notes",
        headers=headers,
        json=note_data,
        timeout=15,
    )

    if resp.status_code in (200, 201):
        log.info("Zoho note synced for contact %s", contact["id"])
        return True
    else:
        log.warning("Zoho note sync returned %s: %s", resp.status_code, resp.text[:200])
        return False


# ── Caregiver Management (Admin) ────────────────────────────────────────────

_caregiver_db = None


def _get_caregiver_db() -> CaregiverDB:
    global _caregiver_db
    if _caregiver_db is None:
        _caregiver_db = CaregiverDB()
    return _caregiver_db


@router.get("/caregivers")
def admin_list_caregivers(
    status: Optional[str] = None,
    limit: int = 100,
    admin: dict = Depends(require_admin),
):
    """List all caregiver links, optionally filtered by status."""
    db = _get_caregiver_db()
    links = db.admin_get_all_links(status=status, limit=limit)

    get_audit_log().record(
        actor=admin.get("email", "admin"),
        action="admin_list_caregivers",
        resource="caregiver",
        detail=f"status={status}, count={len(links)}",
    )

    return {"caregivers": links, "total": len(links)}


@router.post("/caregivers/{invite_id}/revoke")
def admin_revoke_caregiver(
    invite_id: int,
    request: Request,
    admin: dict = Depends(require_admin),
):
    """Admin revokes a caregiver link."""
    db = _get_caregiver_db()
    success = db.admin_revoke(invite_id)

    if not success:
        raise HTTPException(status_code=404, detail="Invite not found or already revoked.")

    get_audit_log().record(
        actor=admin.get("email", "admin"),
        action="admin_revoke_caregiver",
        resource="caregiver",
        detail=f"invite_{invite_id}_revoked",
        ip_address=request.client.host if request.client else "",
    )

    return {"success": True}


@router.get("/caregivers/access-log")
def admin_caregiver_access_log(
    member_phone: str = "",
    limit: int = 50,
    admin: dict = Depends(require_admin),
):
    """View caregiver access logs for a specific member."""
    if not member_phone:
        return {"logs": [], "message": "Provide member_phone query parameter."}

    db = _get_caregiver_db()
    logs = db.get_access_log(member_phone, limit=limit)

    return {"logs": logs, "total": len(logs)}
