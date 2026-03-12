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
    set_auth_cookies,
)
from .audit import get_audit_log
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
    medicare_number: str = Field("", max_length=20)
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
async def admin_logout():
    """Clear auth cookies."""
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

    Auth: ADMIN_SECRET header (same as sync endpoints) — no JWT needed
    so we can curl from CLI without logging in.

    Usage:
        curl -X POST https://iny-concierge.onrender.com/api/admin/upload/extracted \
             -H "X-Admin-Secret: $ADMIN_SECRET" \
             -F "file=@extracted_jsons.tar.gz"
    """
    secret = request.headers.get("X-Admin-Secret", "")
    import hmac
    if not ADMIN_SECRET or not hmac.compare_digest(secret, ADMIN_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden — invalid admin secret.")

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
    payload: dict = Depends(require_admin),
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
