"""
InsuranceNYou Backend API
"""

import hashlib
import json
import logging
import os
import re
import time
import uuid
from typing import Annotated, Optional

import anthropic
import jwt
from fastapi import Depends, FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .admin_router import router as admin_router
from .audit import get_audit_log, mask_phone, mask_pii_in_string
from .auth import create_tokens, decode_token, require_auth
from .claude_client import _find_extracted_file, ask_claude, find_relevant_chunks, load_plan_chunks
from .config import (
    ANTHROPIC_API_KEY,
    APP_ENV,
    CORS_ORIGINS,
    EXTRACTED_DIR,
    JWT_ACCESS_TTL,
    JWT_REFRESH_TTL,
    JWT_SECRET,
    LOG_LEVEL,
    OTP_MAX_ATTEMPTS,
    OTP_MAX_SENDS,
    OTP_SEND_WINDOW,
    OTP_TTL,
    PDFS_DIR,
    SENTRY_DSN,
    TEST_OTP,
    TEST_PHONE,
)
from .drug_cost_engine import compute_monthly_drug_costs
from .persistent_store import PersistentStore
from .providers.service import search_providers
from .sms_provider import create_sms_provider
from .sob_parser import extract_tier_copays, load_plan_text
from .user_data import UserDataDB
from .zoho_client import search_contact_by_phone

# ── Sentry error monitoring ──────────────────────────────────────────────────

def _scrub_pii(text: str) -> str:
    """Remove phone numbers and Medicare numbers from a string."""
    text = re.sub(r'\b\d{10}\b', '***PHONE***', text)
    text = re.sub(r'\b\d[A-Z0-9]{2}\d-[A-Z0-9]{3}-[A-Z0-9]{4}\b', '***MEDICARE***', text)
    return text


def _scrub_dict(obj):
    """Recursively scrub PII from strings in dicts/lists."""
    if isinstance(obj, str):
        return _scrub_pii(obj)
    if isinstance(obj, dict):
        return {k: _scrub_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub_dict(item) for item in obj]
    return obj


def _sentry_before_send(event, hint):
    """Strip PII from Sentry events before sending."""
    # Scrub log messages
    if "logentry" in event and "message" in event["logentry"]:
        event["logentry"]["message"] = _scrub_pii(event["logentry"]["message"])

    # Scrub exception frames (variable values in stack traces)
    for exc_info in (event.get("exception") or {}).get("values", []):
        for frame in (exc_info.get("stacktrace") or {}).get("frames", []):
            if "vars" in frame:
                frame["vars"] = _scrub_dict(frame["vars"])

    # Scrub breadcrumbs
    for crumb in (event.get("breadcrumbs") or {}).get("values", []):
        if "message" in crumb:
            crumb["message"] = _scrub_pii(crumb["message"])
        if "data" in crumb:
            crumb["data"] = _scrub_dict(crumb["data"])

    # Scrub request data (URLs, query strings, body)
    req = event.get("request")
    if req:
        for key in ("url", "query_string"):
            if key in req:
                req[key] = _scrub_pii(req[key])
        if "data" in req:
            req["data"] = _scrub_dict(req["data"])

    return event

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=APP_ENV,
        traces_sample_rate=0.2 if APP_ENV == "production" else 1.0,
        profiles_sample_rate=0.1 if APP_ENV == "production" else 0.0,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
        before_send=_sentry_before_send,
        send_default_pii=False,
    )

# ── Structured logging (PR15) ────────────────────────────────────────────────

class _JSONFormatter(logging.Formatter):
    """JSON log formatter — one JSON object per line for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


_handler = logging.StreamHandler()
if APP_ENV in ("production", "staging"):
    _handler.setFormatter(_JSONFormatter())
else:
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    handlers=[_handler],
)
log = logging.getLogger(__name__)

from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(application):
    # Startup — nothing extra needed
    yield
    # Shutdown — clean up resources
    log.info("Shutting down — cleaning up resources...")
    try:
        store = get_store()
        store.cleanup_all()
    except Exception:
        pass
    log.info("Shutdown complete.")

app = FastAPI(
    title="InsuranceNYou API",
    version="0.7.0",
    docs_url="/docs" if APP_ENV == "development" else None,
    redoc_url="/redoc" if APP_ENV == "development" else None,
    openapi_url="/openapi.json" if APP_ENV == "development" else None,
    lifespan=_lifespan,
)

# ── JWT Secret validation ────────────────────────────────────────────────────
if APP_ENV in ("production", "staging"):
    if not os.getenv("JWT_SECRET"):
        raise RuntimeError("JWT_SECRET must be set in production/staging. Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\"")
elif not os.getenv("JWT_SECRET"):
    log.warning("JWT_SECRET not set — using random per-startup key (dev only, tokens won't survive restarts)")

# ── PHI encryption validation ────────────────────────────────────────────────
if APP_ENV in ("production", "staging") and not os.getenv("FIELD_ENCRYPTION_KEY"):
    raise RuntimeError(
        "FIELD_ENCRYPTION_KEY must be set in production/staging to encrypt PHI at rest. "
        "Generate one with: python -c \"from app.encryption import generate_key; print(generate_key())\""
    )

# ── CORS — env-based ─────────────────────────────────────────────────────────
_default_prod_origins = [
    "https://insurancenyou.com",
    "https://www.insurancenyou.com",
    "https://api.insurancenyou.com",
]
if APP_ENV == "production":
    _extra = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()] if CORS_ORIGINS else []
    _origins = _default_prod_origins + _extra
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID", "X-Admin-Secret"],
    )
else:
    # Dev: allow any localhost origin
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(?:localhost|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+)(:\d+)?",
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID", "X-Admin-Secret"],
    )

# ── Security headers middleware ──────────────────────────────────────────────
@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )
    if APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response

# ── PHI access audit middleware ───────────────────────────────────────────────
# Logs every request to endpoints that touch Protected Health Information.
_PHI_PATH_PREFIXES = (
    "/cms/", "/sob/", "/reminders/", "/usage/", "/ask",
    "/providers/search", "/pharmacies/search",
)

@app.middleware("http")
async def phi_audit_middleware(request: Request, call_next) -> Response:
    response = await call_next(request)
    path = request.url.path
    if any(path.startswith(p) for p in _PHI_PATH_PREFIXES):
        actor = "anonymous"
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer ") and APP_ENV != "development":
            try:
                payload = jwt.decode(auth_header[7:], JWT_SECRET, algorithms=["HS256"])
                actor = payload.get("sub", "unknown")
            except Exception:
                actor = "invalid_token"
        elif APP_ENV == "development":
            actor = "dev"
        action = "read" if request.method == "GET" else "write"
        try:
            get_audit_log().record(
                actor=actor,
                action=f"phi_{action}",
                resource=path,
                ip_address=request.client.host if request.client else "",
                detail=f"{request.method} {response.status_code}",
            )
        except Exception as exc:
            log.warning("PHI audit write failed: %s", exc)  # PR12: visible in prod logs
    return response

# ── Admin router ─────────────────────────────────────────────────────────────
app.include_router(admin_router)

# ── Admin SPA static files ───────────────────────────────────────────────────
# Serves the Vite-built admin portal at /admin/*
_admin_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "admin", "dist")
# On Render, admin dist may be at /opt/render/project/src/admin/dist
if not os.path.isdir(_admin_dist):
    _admin_dist = "/opt/render/project/src/admin/dist"

if os.path.isdir(_admin_dist):
    from starlette.responses import FileResponse as StarletteFileResponse
    from starlette.staticfiles import StaticFiles

    # Mount static assets (JS, CSS, images)
    _assets_dir = os.path.join(_admin_dist, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/admin/assets", StaticFiles(directory=_assets_dir), name="admin-assets")

    # Catch-all for SPA routing — serves index.html for any /admin/* route
    _admin_real = os.path.realpath(_admin_dist)

    @app.get("/admin/{full_path:path}")
    async def admin_spa(full_path: str):
        # If requesting a real file (favicon, etc.), serve it
        file_path = os.path.realpath(os.path.join(_admin_dist, full_path))
        if not file_path.startswith(_admin_real + os.sep) and file_path != _admin_real:
            raise HTTPException(status_code=400, detail="Invalid path")
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        # Otherwise serve index.html for client-side routing
        return FileResponse(os.path.join(_admin_dist, "index.html"))

    @app.get("/admin")
    async def admin_root():
        return FileResponse(os.path.join(_admin_dist, "index.html"))

    log.info("Admin portal mounted at /admin/")
else:
    log.warning("Admin dist not found — /admin/ routes will 404")

# ── Static widget files ─────────────────────────────────────────────────────
_static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if not os.path.isdir(_static_dir):
    _static_dir = "/opt/render/project/src/static"
if not os.path.isdir(_static_dir):
    _static_dir = "/opt/render/project/src/backend/static"
log.info("Static dir resolved (exists=%s)", os.path.isdir(_static_dir))

# Serve widget JS with CORS headers (StaticFiles mount doesn't inherit CORS middleware)
_widget_js_path = os.path.join(_static_dir, "quote-widget.js")

@app.get("/static/quote-widget.js")
async def serve_widget_js(request: Request):
    """Serve widget JS with scoped CORS for cross-origin embedding."""
    from starlette.responses import FileResponse as _FR
    if not os.path.isfile(_widget_js_path):
        log.error("Widget JS not found")
        return JSONResponse({"error": "widget not found"}, status_code=404)
    resp = _FR(_widget_js_path, media_type="application/javascript")
    # Restrict CORS to known embedding domains in production
    origin = request.headers.get("origin", "")
    _WIDGET_ALLOWED_ORIGINS = {
        "https://insurancenyou.com",
        "https://www.insurancenyou.com",
        "https://webflow.insurancenyou.com",
    }
    if APP_ENV == "production" and origin:
        if origin in _WIDGET_ALLOWED_ORIGINS:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
        # else: no CORS header → browser blocks cross-origin use
    else:
        resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp

if os.path.isdir(_static_dir):
    from starlette.staticfiles import StaticFiles as _SF2
    app.mount("/static", _SF2(directory=_static_dir), name="static-files")
    log.info("Static files mounted at /static/")

# ── Request ID correlation middleware ─────────────────────────────────────────
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attach a unique X-Request-ID to every request/response for log correlation."""
    req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    request.state.request_id = req_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response

# ── Request timing + metrics middleware ──────────────────────────────────────
import threading as _threading

_metrics_lock = _threading.Lock()
_request_metrics: dict = {"total": 0, "errors": 0, "latency_sum": 0.0}

# Cross-worker metrics: each worker flushes its local counters to a shared
# SQLite table periodically, and /metrics reads the aggregate.
_METRICS_FLUSH_INTERVAL = 10  # seconds
_metrics_last_flush = 0.0
_WORKER_PID = os.getpid()


def _flush_metrics_to_db() -> None:
    """Flush local in-memory metrics to the shared persistent store."""
    global _metrics_last_flush
    now = time.time()
    if now - _metrics_last_flush < _METRICS_FLUSH_INTERVAL:
        return
    _metrics_last_flush = now
    try:
        store = get_store()
        with _metrics_lock:
            total = _request_metrics["total"]
            errors = _request_metrics["errors"]
            latency_sum = _request_metrics["latency_sum"]
        store.upsert_worker_metrics(str(os.getpid()), total, errors, latency_sum)
    except Exception:
        pass  # metrics are best-effort


def _read_aggregate_metrics() -> dict:
    """Read aggregated metrics across all workers from the persistent store."""
    try:
        store = get_store()
        return store.read_aggregate_metrics()
    except Exception:
        # Fall back to local-only metrics
        with _metrics_lock:
            return {
                "total": _request_metrics["total"],
                "errors": _request_metrics["errors"],
                "latency_sum": _request_metrics["latency_sum"],
            }


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
    except Exception:
        with _metrics_lock:
            _request_metrics["errors"] += 1
        raise
    elapsed = time.time() - start
    with _metrics_lock:
        _request_metrics["total"] += 1
        _request_metrics["latency_sum"] += elapsed
        if response.status_code >= 500:
            _request_metrics["errors"] += 1
    # Periodically flush to shared DB for cross-worker visibility
    _flush_metrics_to_db()
    # Mask PII from URL paths before logging (e.g. /cms/my-drugs/5551234567)
    path = mask_pii_in_string(str(request.url.path))
    req_id = getattr(request.state, "request_id", "")
    log.info(f"[{req_id}] {request.method} {path} → {response.status_code} ({elapsed:.3f}s)")
    return response

# ── Persistent store (OTP + sessions in SQLite) ─────────────────────────────
_store = None
SESSION_TTL = 7200  # 2 hours


def get_store() -> PersistentStore:
    global _store
    if _store is None:
        _store = PersistentStore()
        _store.cleanup_all()
        log.info("Persistent store loaded")
    return _store


def create_session(phone: str, member_data: dict) -> str:
    """Create a session and return the session ID."""
    return get_store().create_session(phone, member_data)

def get_session(sid: str) -> dict | None:
    """Get session data, or None if expired/missing."""
    return get_store().get_session(sid, ttl=SESSION_TTL)

# In-memory cache for parsed SOB summaries: {plan_id: {"data": {...}, "ts": float}}
_sob_cache: dict[str, dict] = {}
_sob_cache_lock = _threading.Lock()
SOB_CACHE_TTL = 3600  # 1 hour
SOB_CACHE_MAX = 500   # max entries — evict oldest when full

# Per-plan locks to prevent cache stampede (multiple concurrent requests for the
# same plan all missing cache and all calling Claude API simultaneously)
_sob_inflight: dict[str, _threading.Lock] = {}
_sob_inflight_lock = _threading.Lock()

# User Data DB — lazy init
_user_db = None


def get_user_db() -> UserDataDB:
    global _user_db
    if _user_db is None:
        _user_db = UserDataDB()
        log.info("User data DB loaded")
    return _user_db


def _session_phone(session_id: str, user: dict | None = None) -> str:
    """Resolve session_id → phone, or raise 401.
    If *user* (JWT payload) is provided, verifies the session belongs to that user.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    phone = session["phone"]
    # Cross-user check: JWT subject must match the session's phone
    if user and user.get("sub") not in (None, "dev") and user["sub"] != phone:
        raise HTTPException(status_code=403, detail="Not authorized for this session")
    # Touch timestamp to extend TTL on activity
    get_store().touch_session(session_id)
    return phone


# ── SMS Provider — lazy init ─────────────────────────────────────────────────
_sms = None


def get_sms():
    global _sms
    if _sms is None:
        _sms = create_sms_provider()
        log.info(f"SMS provider loaded: {type(_sms).__name__}")
    return _sms


# ── JWT Auth Dependency ──────────────────────────────────────────────────────
def get_current_user(request: Request) -> dict:
    """FastAPI dependency — validates Bearer token, returns JWT payload.
    Also verifies the session still exists (enables logout/revocation).
    Skipped entirely in development so you don't need to auth while editing the app."""
    if APP_ENV == "development":
        return {"sub": "dev", "type": "access"}
    payload = require_auth(request, jwt_secret=JWT_SECRET)
    # Session-based revocation: verify the user still has an active session
    phone = payload.get("sub")
    if phone:
        session = get_store().find_session_by_phone(phone, ttl=SESSION_TTL)
        if not session:
            raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    return payload


def _authorize_plan(user: dict, plan_number: str) -> None:
    """Verify the authenticated user owns the requested plan_number (IDOR prevention).
    Raises 403 if the user's session plan doesn't match."""
    if APP_ENV == "development":
        return  # Skip in dev mode
    phone = user.get("sub")
    if not phone or phone == "dev":
        return
    session = get_store().find_session_by_phone(phone, ttl=SESSION_TTL)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    user_plan = normalize_plan_id(session["data"].get("plan_number", ""))
    requested = normalize_plan_id(plan_number)
    if user_plan and requested and user_plan != requested:
        log.warning("IDOR attempt: user plan %s tried to access %s", user_plan[:5], requested[:5])
        raise HTTPException(status_code=403, detail="Not authorized for this plan.")


# CMS Lookup — lazy init so server starts even if DB missing
_cms = None


def get_cms():
    global _cms
    if _cms is None:
        try:
            from .cms_lookup import CMSLookup
            _cms = CMSLookup()
            log.info("CMS database loaded")
        except Exception as e:
            log.warning("CMS database not available: %s", type(e).__name__)
            raise HTTPException(status_code=503, detail="CMS database not loaded")
    return _cms


def _evict_oldest(cache: dict, max_size: int) -> None:
    """Evict expired entries, then oldest if still over max_size."""
    now = time.time()
    expired = [k for k, v in cache.items() if now - v.get("ts", 0) > SOB_CACHE_TTL]
    for k in expired:
        del cache[k]
    if len(cache) >= max_size:
        oldest = min(cache, key=lambda k: cache[k].get("ts", 0))
        del cache[oldest]

# SOB tier copays cache: {plan_id: {"data": dict, "ts": float}}
_sob_tier_cache: dict[str, dict] = {}
_sob_tier_cache_lock = _threading.Lock()
SOB_TIER_CACHE_TTL = 3600  # 1 hour


def get_sob_tier_copays(plan_id: str) -> dict | None:
    """
    Load structured per-tier copay data from the SOB PDF for a plan.
    Returns dict keyed by tier number (1-5) with retail_30, retail_90, mail costs, etc.
    Returns None if SOB text not available for this plan.
    Cached in memory for 1 hour.
    """
    pid = normalize_plan_id(plan_id)
    with _sob_tier_cache_lock:
        cached = _sob_tier_cache.get(pid)
        if cached and (time.time() - cached["ts"]) < SOB_TIER_CACHE_TTL:
            return cached["data"]

    text = load_plan_text(pid)
    if text is None:
        return None

    try:
        tier_copays = extract_tier_copays(text)
        with _sob_tier_cache_lock:
            _evict_oldest(_sob_tier_cache, SOB_CACHE_MAX)
            _sob_tier_cache[pid] = {"data": tier_copays, "ts": time.time()}
        log.info(f"SOB tier copays loaded for {pid}: tiers={[k for k in tier_copays if isinstance(k, int)]}")
        return tier_copays
    except Exception as e:
        log.warning("SOB tier copay extraction failed for %s: %s", pid, type(e).__name__)
        return None


def normalize_plan_id(plan_id: str) -> str:
    """
    H1234-567-000 → H1234-567
    Zoho stores the full 3-segment ID but SOB files are keyed by 2 segments.
    """
    pid = plan_id.strip()
    if pid.endswith("-000"):
        pid = pid[:-4]
    return pid


def parse_medications(raw: str) -> list[dict]:
    """
    Parse medications from a multi-line or comma-separated string.
    Returns list of {name, days_supply, is_mail} dicts.
    Detects "90 day" patterns like "Ventolin 90 day" → days_supply=90.
    Detects "mail" or "mail order" → is_mail=True.
    """
    if not raw or not raw.strip():
        return []
    parts = re.split(r'[,\n]+', raw)
    meds = []
    for part in parts:
        text = part.strip()
        if not text or len(text) < 2:
            continue
        # Detect mail order
        is_mail = bool(re.search(r'\bmail\s*(?:order)?\b', text, re.IGNORECASE))
        name = re.sub(r'\(?\s*mail\s*(?:order)?\s*\)?', '', text, flags=re.IGNORECASE).strip()
        # Detect days supply pattern
        days_match = re.search(r'(\d+)\s*-?\s*days?\s*(?:supply)?', name, re.IGNORECASE)
        if days_match:
            days = int(days_match.group(1))
            name = re.sub(r'\(?\s*\d+\s*-?\s*days?\s*(?:supply)?\s*\)?', '', name,
                          flags=re.IGNORECASE).strip()
        else:
            days = 30
        # 90-day supply implies mail order
        if days >= 90:
            is_mail = True
        if name:
            meds.append({"name": name, "days_supply": days, "is_mail": is_mail})
    return meds


# --- Models ---

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    plan_number: str = Field(..., pattern=r"^[A-Za-z]\d{4}-\d{3}(-\d{3})?$")

class AskResponse(BaseModel):
    answer: str
    plan_number: str
    has_context: bool

class LookupRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\d{10}$")

class LookupResponse(BaseModel):
    found: bool
    first_name: str = ""

class ProviderSearchRequest(BaseModel):
    plan_name: str = Field(..., min_length=1, max_length=200)
    specialty: str = Field(..., min_length=1, max_length=200)
    zip_code: str = Field(..., pattern=r"^\d{5}$")
    radius_miles: float = Field(25.0, ge=1, le=100)
    limit: int = Field(200, ge=1, le=500)
    enrich_google: bool = True

class PharmacySearchRequest(BaseModel):
    plan_number: str = Field("", max_length=20)
    zip_code: str = Field(..., pattern=r"^\d{5}$")
    radius_miles: int = Field(10, ge=1, le=100)
    limit: int = Field(30, ge=1, le=200)

class SOBRequest(BaseModel):
    plan_number: str = Field(..., pattern=r"^[A-Za-z]\d{4}-\d{3}(-\d{3})?$")

class DrugLookupRequest(BaseModel):
    plan_number: str = Field(..., pattern=r"^[A-Za-z]\d{4}-\d{3}(-\d{3})?$")
    drug_name: str = Field(..., min_length=1, max_length=200)


# --- OTP / Auth Models ---

class OTPVerifyRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\d{10}$")
    code: str = Field(..., pattern=r"^\d{4,8}$")

class RefreshRequest(BaseModel):
    refresh_token: str


# --- Reminder / Usage Models ---

class ReminderCreate(BaseModel):
    drug_name: str = Field(..., min_length=1, max_length=200)
    dose_label: str = Field("", max_length=200)
    time_hour: int = Field(..., ge=0, le=23)
    time_minute: int = Field(0, ge=0, le=59)
    days_supply: int = Field(30, ge=1, le=365)
    refill_reminder: bool = False
    last_refill_date: Optional[str] = Field(None, max_length=20)

class ReminderUpdate(BaseModel):
    enabled: Optional[bool] = None
    time_hour: Optional[int] = Field(None, ge=0, le=23)
    time_minute: Optional[int] = Field(None, ge=0, le=59)
    refill_reminder: Optional[bool] = None
    last_refill_date: Optional[str] = Field(None, max_length=20)
    dose_label: Optional[str] = Field(None, max_length=200)

class BulkReminderCreate(BaseModel):
    reminders: list[ReminderCreate] = Field(..., max_length=50)
    created_by: str = Field("member", pattern=r"^(member|agent|admin)$")

class UsageCreate(BaseModel):
    category: str = Field(..., max_length=50)
    amount: float = Field(..., gt=0, le=100000)
    description: str = Field("", max_length=500)
    usage_date: Optional[str] = Field(None, max_length=20)
    benefit_period: str = Field("Monthly", pattern=r"^(Monthly|Quarterly|Yearly)$")


# Validated plan_number path parameter for GET endpoints (H3: prevent injection)
_PLAN_NUMBER_PATTERN = r"^[A-Za-z]\d{4}-\d{3}(-\d{3})?$"
ValidPlanNumber = Annotated[str, Path(pattern=_PLAN_NUMBER_PATTERN)]


# --- IP-based rate limiter for public endpoints (persistent) ─────────────────
def _check_ip_rate(request: Request, *, max_hits: int, window: int, label: str = "endpoint") -> None:
    """Raise 429 if the client IP exceeds max_hits within window seconds."""
    ip = request.client.host if request.client else "unknown"
    key = f"{label}:{ip}"
    if not get_store().check_rate_limit(key, max_hits, window):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait before trying again.")


# --- Endpoints ---

@app.get("/health")
def health():
    """Deep health check — verifies DB connectivity, CMS data, and critical config."""
    checks = {}

    # 1. Persistent store DB writable
    try:
        store = get_store()
        store.count_active_sessions(ttl=SESSION_TTL)
        checks["persistent_store"] = "ok"
    except Exception as e:
        checks["persistent_store"] = f"error: {type(e).__name__}"

    # 2. CMS benefits DB loaded
    try:
        cms = get_cms()
        checks["cms_db"] = "ok" if cms is not None else "not loaded"
    except Exception as e:
        checks["cms_db"] = f"error: {type(e).__name__}"

    # 3. Extracted plan data present
    try:
        json_count = len([f for f in os.listdir(EXTRACTED_DIR) if f.endswith(".json")]) if os.path.isdir(EXTRACTED_DIR) else 0
        checks["extracted_plans"] = json_count
    except Exception as e:
        checks["extracted_plans"] = f"error: {type(e).__name__}"

    # 4. Critical API keys configured
    checks["anthropic_key"] = "configured" if ANTHROPIC_API_KEY else "missing"

    # CMS is optional (only used for benefits gap-fill, not auth).
    # Don't let it drag the health check to 503 and trigger Render restarts.
    _critical_keys = ("persistent_store", "anthropic_key")
    healthy = all(
        checks.get(k) in ("ok", "configured")
        for k in _critical_keys
    ) and checks.get("extracted_plans", 0) > 0

    return JSONResponse(
        content={"status": "ok" if healthy else "degraded", "checks": checks},
        status_code=200 if healthy else 503,
    )


# --- Public Quote/Plan Search Endpoints (no auth — for Webflow widget) ---

from .plan_search import MedicarePlanSearch, get_counties_by_zip, search_marketplace_plans

_medicare_search: MedicarePlanSearch | None = None


def get_medicare_search() -> MedicarePlanSearch:
    global _medicare_search
    if _medicare_search is None:
        _medicare_search = MedicarePlanSearch()
    return _medicare_search


@app.get("/quote/counties/{zipcode}")
def quote_counties(zipcode: str, request: Request):
    """Get counties for a zip code (public, no auth)."""
    _check_ip_rate(request, max_hits=30, window=60, label="quote")
    if not re.fullmatch(r"\d{5}", zipcode):
        raise HTTPException(status_code=400, detail="Zip code must be exactly 5 digits.")
    counties = get_counties_by_zip(zipcode)
    if not counties:
        raise HTTPException(status_code=404, detail="No counties found for this zip code")
    return {"counties": counties}


@app.get("/quote/medicare")
def quote_medicare(
    request: Request,
    zip: str = None,
    state: str = None,
    county: str = None,
    fips: str = None,
    limit: int = 50,
):
    """
    Search Medicare Advantage plans (public, no auth).
    Either provide zip (auto-resolves to state/county) or state + county code.
    """
    _check_ip_rate(request, max_hits=20, window=60, label="quote")
    search = get_medicare_search()
    if zip:
        if not re.fullmatch(r"\d{5}", zip):
            raise HTTPException(status_code=400, detail="Zip code must be exactly 5 digits.")
        result = search.search_by_zip(zip, limit=limit)
    elif state:
        result = {
            "plans": search.search_by_state(state, county_code=county, limit=limit),
        }
    else:
        raise HTTPException(status_code=400, detail="Provide zip or state parameter")
    if "error" in result:
        log.warning("Medicare plan search error: %s", result["error"])
        raise HTTPException(status_code=404, detail="No plans found for the given criteria.")
    return result


@app.get("/quote/marketplace")
def quote_marketplace(
    request: Request,
    zip: str = "",
    fips: str = None,
    age: int = 30,
    income: int = None,
    household_size: int = 1,
    limit: int = 50,
):
    """
    Search ACA Marketplace plans for under-65 (public, no auth).
    Proxies to CMS Marketplace API (marketplace.api.healthcare.gov).
    """
    _check_ip_rate(request, max_hits=20, window=60, label="quote")
    if not re.fullmatch(r"\d{5}", zip):
        raise HTTPException(status_code=400, detail="Zip code must be exactly 5 digits.")
    result = search_marketplace_plans(
        zipcode=zip,
        fips=fips,
        age=age,
        household_income=income,
        household_size=household_size,
        limit=limit,
    )
    if "error" in result:
        log.warning("Marketplace plan search error: %s", result["error"])
        raise HTTPException(status_code=404, detail="No plans found for the given criteria.")
    return result


@app.get("/metrics")
def metrics(_user: dict = Depends(get_current_user)):
    """Aggregated request metrics across all workers (requires auth)."""
    # Flush current worker's metrics before reading aggregate
    _flush_metrics_to_db()
    agg = _read_aggregate_metrics()
    total = agg["total"]
    errors = agg["errors"]
    latency_sum = agg["latency_sum"]
    return {
        "total_requests": total,
        "total_errors": errors,
        "avg_latency_ms": round((latency_sum / total) * 1000, 1) if total > 0 else 0,
        "active_sessions": get_store().count_active_sessions(ttl=SESSION_TTL),
        "sob_cache_size": len(_sob_cache),
    }


@app.post("/auth/lookup")
def lookup_member(req: LookupRequest, request: Request):
    """
    Step 1: Look up member by phone, send OTP.
    Returns only {found, first_name} — no sensitive data until OTP verified.
    """
    _check_ip_rate(request, max_hits=5, window=60, label="auth_lookup")

    # Test account — still fetch real data from Zoho, just skip SMS
    is_test = TEST_PHONE and req.phone == TEST_PHONE

    try:
        member = search_contact_by_phone(req.phone)
    except Exception as e:
        log.error("Zoho lookup failed: %s", type(e).__name__)
        if is_test:
            # Fallback for test account if Zoho is unreachable
            member = {
                "first_name": "Test",
                "last_name": "User",
                "plan_name": "Demo Plan",
                "plan_number": "H0000-000-000",
                "agent": "",
                "medicare_number": "",
                "medications": "",
                "zip_code": "10001",
            }
        else:
            raise HTTPException(status_code=500, detail="Unable to verify your account right now. Please try again.")

    if member is None:
        get_audit_log().record(
            actor=req.phone, action="auth_lookup", resource="member",
            ip_address=request.client.host if request.client else "",
            detail="not_found",
        )
        return {"found": False}

    # H1: Session creation deferred to /auth/verify-otp — no PHI materialized pre-auth.
    # The verify-otp endpoint will re-fetch from Zoho if needed.

    if not is_test:
        # Generate + send OTP (skipped for test account — uses TEST_OTP instead)
        code = get_store().generate_otp(
            req.phone,
            otp_ttl=OTP_TTL,
            max_sends=OTP_MAX_SENDS,
            send_window=OTP_SEND_WINDOW,
        )
        if code is None:
            raise HTTPException(status_code=429, detail="Too many verification attempts. Please wait a few minutes.")

        sms = get_sms()
        if not sms.send_otp(req.phone, code):
            raise HTTPException(status_code=500, detail="Unable to send verification code. Please try again.")

    get_audit_log().record(
        actor=req.phone, action="auth_lookup", resource="member",
        ip_address=request.client.host if request.client else "",
        detail="otp_sent" if not is_test else "test_account",
    )

    return {
        "found": True,
        "first_name": member["first_name"],
        "otp_sent": True,
    }


@app.post("/auth/verify-otp")
def verify_otp_endpoint(req: OTPVerifyRequest, request: Request):
    """
    Step 2: Verify OTP → return JWT tokens + full member data.
    """
    _check_ip_rate(request, max_hits=10, window=60, label="auth_verify")

    # Test account — accept TEST_OTP without going through the OTP store
    is_test = TEST_PHONE and TEST_OTP and req.phone == TEST_PHONE
    otp_valid = (is_test and req.code == TEST_OTP) or get_store().verify_otp(req.phone, req.code, max_attempts=OTP_MAX_ATTEMPTS)

    if not otp_valid:
        get_audit_log().record(
            actor=req.phone, action="auth_verify_otp", resource="member",
            ip_address=request.client.host if request.client else "",
            detail="failed",
        )
        raise HTTPException(status_code=401, detail="Invalid or expired code. Please try again.")

    # Find the pending session with this phone's member data
    member_data = None
    pending = get_store().find_session_by_phone(req.phone, ttl=SESSION_TTL)
    if pending:
        member_data = pending["data"]

    if not member_data:
        # Session expired between lookup and verify — re-fetch from Zoho
        try:
            member_data = search_contact_by_phone(req.phone)
        except Exception as e:
            log.error("Zoho re-fetch failed after OTP verify: %s", type(e).__name__)
            raise HTTPException(status_code=500, detail="Verification succeeded but couldn't load your account. Please try again.")
        if not member_data:
            raise HTTPException(status_code=404, detail="Account not found.")

    # Create a real session — store only needed fields (H4: minimize PHI)
    _SESSION_FIELDS = ("first_name", "last_name", "plan_name", "plan_number",
                       "agent", "medications", "zip_code")
    session_member = {k: member_data.get(k, "") for k in _SESSION_FIELDS}
    sid = create_session(req.phone, session_member)

    # Generate JWT tokens
    tokens = create_tokens(
        req.phone, member_data,
        jwt_secret=JWT_SECRET,
        access_ttl=JWT_ACCESS_TTL,
        refresh_ttl=JWT_REFRESH_TTL,
    )

    log.info(f"OTP verified, JWT issued for phone ending ***{req.phone[-4:]}")

    get_audit_log().record(
        actor=req.phone, action="auth_verify_otp", resource="member",
        ip_address=request.client.host if request.client else "",
        detail="success",
    )

    return {
        **tokens,
        "first_name": member_data["first_name"],
        "last_name": member_data["last_name"],
        "plan_name": member_data["plan_name"],
        "plan_number": member_data["plan_number"],
        "agent": member_data.get("agent", "") or "",
        "zip_code": member_data.get("zip_code", "") or "",
        "session_id": sid,
    }


@app.post("/auth/refresh")
def refresh_token_endpoint(req: RefreshRequest, request: Request):
    """Exchange a refresh token for a new access token."""
    _check_ip_rate(request, max_hits=10, window=60, label="auth_refresh")
    payload = decode_token(req.refresh_token, jwt_secret=JWT_SECRET, expected_type="refresh")
    phone = payload["sub"]

    # Refresh token rotation — each token can only be used once
    jti = payload.get("jti")
    if jti and not get_store().consume_refresh_jti(jti, phone):
        log.warning("Refresh token replay detected for phone ending ***%s", phone[-4:])
        raise HTTPException(status_code=401, detail="Token already used. Please log in again.")

    # Find member data from an active session
    member_data = None
    active = get_store().find_session_by_phone(phone, ttl=SESSION_TTL)
    if active:
        member_data = active["data"]

    if not member_data:
        # Session gone — re-fetch from Zoho
        try:
            member_data = search_contact_by_phone(phone)
        except Exception:
            raise HTTPException(status_code=401, detail="Unable to refresh. Please log in again.")
        if not member_data:
            raise HTTPException(status_code=401, detail="Account not found. Please log in again.")

    tokens = create_tokens(
        phone, member_data,
        jwt_secret=JWT_SECRET,
        access_ttl=JWT_ACCESS_TTL,
        refresh_ttl=JWT_REFRESH_TTL,
    )
    return tokens


@app.post("/auth/logout")
def logout(request: Request, user: dict = Depends(get_current_user)):
    """Invalidate all sessions for this user, effectively revoking their tokens."""
    phone = user.get("sub")
    if phone and phone != "dev":
        count = get_store().delete_sessions_by_phone(phone)
        log.info(f"Logout: deleted {count} session(s) for phone ending ***{phone[-4:]}")
        get_audit_log().record(
            actor=phone, action="auth_logout", resource="session",
            ip_address=request.client.host if request.client else "",
            detail=f"deleted {count} sessions",
        )
    return {"success": True}


# Per-phone rate limiter for /ask
_ASK_MAX = int(os.getenv("ASK_RATE_MAX", "10"))
_ASK_WINDOW = int(os.getenv("ASK_RATE_WINDOW", "60"))


@app.post("/ask", response_model=AskResponse)
def ask_question(req: AskRequest, _user: dict = Depends(get_current_user)):
    """Ask a question about a member's plan benefits."""
    phone = _user.get("sub", "anon")
    if not get_store().check_rate_limit(f"ask:{phone}", _ASK_MAX, _ASK_WINDOW):
        raise HTTPException(status_code=429, detail="Too many questions. Please wait a minute.")

    plan_id = normalize_plan_id(req.plan_number)
    result = ask_claude(question=req.question, plan_number=plan_id)
    return AskResponse(**result)


@app.post("/providers/search")
async def provider_search(req: ProviderSearchRequest, _user: dict = Depends(get_current_user)):
    """
    Search for in-network providers by specialty near a zip code.
    Returns providers enriched with Google ratings and reviews.
    """
    result = await search_providers(
        plan_name=req.plan_name,
        specialty=req.specialty,
        zip_code=req.zip_code,
        radius_miles=req.radius_miles,
        limit=req.limit,
        enrich_google=req.enrich_google,
    )

    if not result["success"]:
        log.warning("Provider search error: %s", result.get("error", "unknown"))
        raise HTTPException(status_code=400, detail="Provider search failed. Please check your criteria and try again.")

    return result


@app.post("/pharmacies/search")
async def pharmacy_search(req: PharmacySearchRequest, _user: dict = Depends(get_current_user)):
    """
    Search for pharmacies near a zip code.
    Returns pharmacies sorted by: preferred first, then in-network, then distance.
    """
    from .pharmacy_service import search_pharmacies

    result = await search_pharmacies(
        plan_number=req.plan_number,
        zip_code=req.zip_code,
        radius_miles=req.radius_miles,
        limit=req.limit,
    )

    if not result["success"]:
        log.warning("Pharmacy search error: %s", result.get("error", "unknown"))
        raise HTTPException(status_code=400, detail="Pharmacy search failed. Please check your criteria and try again.")

    return result


# --- SOB Enrichment with CMS data ---

def _upsert_medical(medical: list, label_map: dict, label: str,
                    in_network_value: str, force: bool = False):
    """Update or insert a medical benefit row with fuzzy label matching."""
    lbl_lower = label.lower()
    matched_idx = None
    for existing_lbl, idx in label_map.items():
        if lbl_lower in existing_lbl or existing_lbl in lbl_lower:
            matched_idx = idx
            break

    if matched_idx is not None:
        if force:
            medical[matched_idx]["in_network"] = in_network_value
        else:
            existing_val = (medical[matched_idx].get("in_network") or
                            medical[matched_idx].get("value") or "")
            if (not existing_val or existing_val in ("$0", "0", "Not specified", "Not found", "\u2014")
                    or "$0 copay" == existing_val.strip()):
                medical[matched_idx]["in_network"] = in_network_value
    else:
        medical.append({"label": label, "in_network": in_network_value, "out_of_network": "\u2014"})
        label_map[lbl_lower] = len(medical) - 1


def _enrich_sob_with_cms(result: dict, plan_number: str) -> dict:
    """Fill gaps in SOB extraction with CMS data. SOB is the source of truth —
    CMS only fills in benefits the SOB extraction missed (force=False)."""
    try:
        cms = get_cms()
    except Exception:
        return result

    medical = result.get("medical", [])
    label_map = {}
    for i, item in enumerate(medical):
        lbl = (item.get("label") or "").lower()
        label_map[lbl] = i

    # ── Dental (only fill if SOB missed it) ──
    try:
        dental = cms.get_dental_benefits(plan_number)
        if dental.get("has_preventive") or dental.get("has_comprehensive"):
            pv = dental.get("preventive", {})
            cmp = dental.get("comprehensive", {})
            pv_copay = pv.get("copay", "$0")
            pv_max = pv.get("max_benefit")

            if pv_max:
                pv_value = f"$0 copay ({pv_max}/yr max)"
            else:
                pv_value = f"{pv_copay} copay"

            cmp_value = ""
            cmp_max = cmp.get("max_benefit")
            if cmp_max:
                if "combined" in str(cmp_max).lower():
                    cmp_value = cmp_max
                else:
                    cmp_value = f"{cmp_max}/yr max"

            _upsert_medical(medical, label_map, "Dental (preventive)", pv_value)
            if dental.get("has_comprehensive") and cmp_value:
                _upsert_medical(medical, label_map, "Dental (comprehensive)", cmp_value)
    except Exception as e:
        log.warning("CMS dental enrichment failed: %s", type(e).__name__)

    # ── Medical copays (only fill if SOB missed them) ──
    try:
        med_copays = cms.get_medical_copays(plan_number)
        copay_map = {
            "PCP visit": med_copays.get("pcp_copay"),
            "Specialist visit": med_copays.get("specialist_copay"),
            "Emergency room": med_copays.get("er_copay"),
            "Urgent care": med_copays.get("urgent_care_copay"),
        }
        for label, value in copay_map.items():
            if value:
                _upsert_medical(medical, label_map, label, value)
    except Exception as e:
        log.warning("CMS medical copay enrichment failed: %s", type(e).__name__)

    # ── Vision (only fill if SOB missed it) ──
    try:
        vision = cms.get_vision_benefits(plan_number)
        if vision.get("has_eye_exam"):
            exam = vision["eye_exam"]
            copay = exam.get("copay", "$0")
            exams = exam.get("exams_per_year")
            parts = [copay + " copay"]
            if exams:
                parts.append(f"{exams}/yr")
            _upsert_medical(medical, label_map, "Vision (exam)", ", ".join(parts))

        if vision.get("has_eyewear"):
            ew = vision["eyewear"]
            copay = ew.get("copay", "$0")
            max_b = ew.get("max_benefit")
            if max_b:
                ew_value = f"{copay} copay ({max_b}/yr allowance)"
            else:
                ew_value = f"{copay} copay"
            _upsert_medical(medical, label_map, "Vision (eyewear)", ew_value)
    except Exception as e:
        log.warning("CMS vision enrichment failed: %s", type(e).__name__)

    # ── Hearing (only fill if SOB missed it) ──
    try:
        hearing = cms.get_hearing_benefits(plan_number)
        if hearing.get("has_hearing_exam"):
            exam = hearing["hearing_exam"]
            copay = exam.get("copay", "$0")
            exams = exam.get("exams_per_year")
            parts = [copay + " copay"]
            if exams:
                parts.append(f"{exams}/yr")
            _upsert_medical(medical, label_map, "Hearing (exam)", ", ".join(parts))

        if hearing.get("has_hearing_aids"):
            aids = hearing["hearing_aids"]
            copay = aids.get("copay", "$0")
            max_b = aids.get("max_benefit")
            period = aids.get("period")
            aids_num = aids.get("aids_allowed")
            parts = []
            if max_b:
                parts.append(f"{max_b} max")
            if copay:
                parts.append(f"{copay} copay")
            if aids_num:
                parts.append(f"{aids_num} aids")
            if period:
                parts.append(period)
            _upsert_medical(medical, label_map, "Hearing (aids)", ", ".join(parts) if parts else "Covered")
    except Exception as e:
        log.warning("CMS hearing enrichment failed: %s", type(e).__name__)

    # ── OTC allowance (only fill if Claude missed it) ──
    try:
        otc = cms.get_otc_allowance(plan_number)
        if otc.get("has_otc"):
            amt = otc.get("amount", "")
            period = otc.get("period", "")
            otc_value = f"{amt} {period}".strip() if amt else "Included"
            _upsert_medical(medical, label_map, "OTC allowance", otc_value)
    except Exception as e:
        log.warning("CMS OTC enrichment failed: %s", type(e).__name__)

    # ── Flex card / SSBCI (only fill if Claude missed it) ──
    try:
        flex = cms.get_flex_ssbci(plan_number)
        if flex.get("has_ssbci") and flex.get("benefits"):
            total = 0
            cats = []
            for b in flex["benefits"]:
                cats.append(b["category"])
                amt_str = b.get("amount", "")
                if amt_str.startswith("$"):
                    try:
                        total += float(amt_str.replace("$", "").replace(",", ""))
                    except ValueError:
                        pass
            if total > 0:
                flex_value = f"${total:.0f} ({', '.join(cats[:3])})"
            else:
                flex_value = ", ".join(cats[:3])
            _upsert_medical(medical, label_map, "Flex card / SSBCI", flex_value)
    except Exception as e:
        log.warning("CMS flex enrichment failed: %s", type(e).__name__)

    # ── Part B giveback (only fill if Claude missed it) ──
    try:
        giveback = cms.get_part_b_giveback(plan_number)
        if giveback.get("has_giveback"):
            gb_value = f"{giveback['monthly_amount']}/mo reduction"
            _upsert_medical(medical, label_map, "Part B giveback", gb_value)
    except Exception as e:
        log.warning("CMS giveback enrichment failed: %s", type(e).__name__)

    result["medical"] = medical
    return result


SOB_EXTRACTION_PROMPT = """You are extracting benefits from a Medicare Summary of Benefits PDF. Your job is to pull EVERY benefit, dollar amount, cost-share, and supplemental benefit from this document.

CRITICAL RULES:
- The document has TWO columns: In-Network and Out-of-Network. You MUST extract BOTH.
- NEVER return "Not specified" or "Not found". If a benefit exists in the document, the cost is there — look harder.
- Copays look like: "$0 copay", "$40 per visit", "$0 copay per visit"
- Coinsurance looks like: "20% coinsurance", "30% of the cost"
- Hospital stays have per-day costs like: "$345 per day for days 1-6, $0 per day for days 7-90"
- Deductibles are stated as: "$0 deductible", "$250 annual deductible"
- If a benefit says "$0" that means no cost to the member.
- If a benefit says "Not covered" for out-of-network, write "Not covered".
- Drug tiers: extract the actual copay/coinsurance for EACH tier at EACH phase (initial, coverage gap, catastrophic) if shown.
- Keep values SHORT: "$0", "$40/visit", "20%", "$345/day days 1-6", "$250 deductible"
- For allowance benefits (OTC, flex card, meals, etc.) include the dollar amount AND frequency (per month, per quarter, per year).

Return ONLY valid JSON:
{
  "plan_name": "Full official plan name from document",
  "plan_type": "HMO or PPO or PFFS etc",
  "monthly_premium": "$X.XX",
  "part_b_premium_reduction": "$X.XX or null if not offered",
  "annual_deductible_in": "In-network deductible",
  "annual_deductible_out": "Out-of-network deductible",
  "moop_in": "In-network max out of pocket",
  "moop_out": "Out-of-network max out of pocket",
  "medical": [
    {"label": "Short name", "in_network": "$X", "out_of_network": "$X"}
  ],
  "drugs": [
    {"label": "Tier/phase name", "value": "$X"}
  ],
  "supplemental": [
    {"label": "Benefit name", "value": "Description with dollar amounts and limits"}
  ]
}

For medical, include ALL of these if in the document:
- PCP visit
- Specialist visit
- Preventive care
- Urgent care
- Emergency room
- Inpatient hospital (include per-day breakdown)
- Outpatient surgery/services
- Ambulance
- Lab services
- X-rays/diagnostic imaging
- Advanced imaging (CT/MRI/PET)
- Mental health (outpatient)
- Mental health (inpatient)
- Substance abuse (outpatient)
- Substance abuse (inpatient)
- Skilled nursing facility
- Home health care
- Hospice
- Dental (preventive)
- Dental (comprehensive/restorative)
- Vision (routine exam)
- Vision (eyewear/contacts allowance)
- Hearing (routine exam)
- Hearing (aids/fitting)
- Chiropractic
- Podiatry/foot care
- Physical therapy
- Occupational therapy
- Speech therapy
- Cardiac rehabilitation
- Pulmonary rehabilitation
- Telehealth/virtual visits
- Durable medical equipment (DME)
- Prosthetics/orthotics
- Diabetic supplies/monitoring
- Kidney disease/dialysis
- Outpatient rehabilitation

For drugs, extract every tier shown. Common tiers:
- Preferred retail pharmacy (30-day, 90-day)
- Standard retail pharmacy (30-day, 90-day)
- Mail order (90-day)
Each with: Tier 1 (Preferred Generic), Tier 2 (Generic), Tier 3 (Preferred Brand), Tier 4 (Non-Preferred Drug), Tier 5 (Specialty), Tier 6 (Select Care Drugs) if present
Also extract:
- Drug deductible (if any)
- Coverage gap/donut hole costs per tier
- Catastrophic coverage costs per tier
- Part B drugs (chemotherapy, immunosuppressants, etc.)

For supplemental, include ALL extra benefits if in the document:
- OTC allowance (amount per quarter/month/year)
- Flex card / benefit allowance (amount and what it covers)
- Meal benefit (number of meals, duration after hospital stay)
- Transportation (number of one-way trips per year)
- Fitness/gym (SilverSneakers, gym membership, fitness allowance)
- Nurse hotline / 24-hour nurse line
- Personal emergency response system (PERS)
- Caregiver support
- In-home support services
- Bathroom safety devices
- Worldwide emergency coverage
- Acupuncture (number of visits)
- Weight management / obesity counseling
- Nutritional counseling
- Smoking cessation
- Over-the-counter insulin
- Part B premium giveback (monthly reduction amount)
- Any other supplemental benefits with dollar amounts or visit limits

Return ONLY the JSON. No markdown fences, no explanation."""


def _load_pre_extracted_benefits(plan_id: str) -> dict | None:
    """Check for pre-extracted _benefits.json (created by extract_benefits.py)."""
    path = os.path.join(EXTRACTED_DIR, f"{plan_id}_benefits.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log.warning("Failed to load pre-extracted benefits for %s: %s", plan_id, type(e).__name__)
        return None


def _chunks_to_context(chunks: list, max_chunks: int = 12) -> str:
    """Join chunks into a single context string for Claude.
    Handles both old format (list of strings) and new format (list of dicts).
    """
    parts = []
    for c in chunks[:max_chunks]:
        if isinstance(c, dict):
            parts.append(f"[{c['section']}]\n{c['text']}")
        else:
            parts.append(c)
    return "\n\n---\n\n".join(parts)


@app.post("/sob/summary")
def get_sob_summary(req: SOBRequest, _user: dict = Depends(get_current_user)):
    """
    Get structured SOB benefits for a plan.
    1. Check for pre-extracted _benefits.json (instant, no API cost)
    2. Fall back to on-demand Claude extraction if no pre-extracted file
    Results are cached in memory so it only parses once per plan.
    """
    _authorize_plan(_user, req.plan_number)
    plan_id = normalize_plan_id(req.plan_number)

    # Check cache first (with TTL)
    with _sob_cache_lock:
        cached = _sob_cache.get(plan_id)
        if cached and (time.time() - cached["ts"]) < SOB_CACHE_TTL:
            return cached["data"]

    # Per-plan lock prevents cache stampede: only one request does the
    # extraction while others wait and then read from cache.
    with _sob_inflight_lock:
        plan_lock = _sob_inflight.setdefault(plan_id, _threading.Lock())
    with plan_lock:
        # Re-check cache — another thread may have populated it while we waited
        with _sob_cache_lock:
            cached = _sob_cache.get(plan_id)
            if cached and (time.time() - cached["ts"]) < SOB_CACHE_TTL:
                return cached["data"]

        return _extract_sob_benefits(plan_id, req.plan_number)


def _extract_sob_benefits(plan_id: str, plan_number: str) -> dict:
    """Extract SOB benefits (pre-extracted file or Claude API), cache the result."""
    # --- Try pre-extracted benefits first (instant, no API cost) ---
    pre = _load_pre_extracted_benefits(plan_id)
    if pre is not None:
        result = {
            "success": True,
            "plan_id": plan_id,
            "plan_name": pre.get("plan_name", plan_id),
            "plan_type": pre.get("plan_type", ""),
            "monthly_premium": pre.get("monthly_premium", ""),
            "annual_deductible_in": pre.get("annual_deductible_in", ""),
            "annual_deductible_out": pre.get("annual_deductible_out", ""),
            "moop_in": pre.get("moop_in", ""),
            "moop_out": pre.get("moop_out", ""),
            "medical": pre.get("medical", []),
            "drugs": pre.get("drugs", []),
        }
        # Enrich with CMS authoritative data
        try:
            result = _enrich_sob_with_cms(result, plan_number)
        except Exception as e:
            log.warning("CMS enrichment failed (non-fatal): %s", type(e).__name__)
        with _sob_cache_lock:
            _evict_oldest(_sob_cache, SOB_CACHE_MAX)
            _sob_cache[plan_id] = {"data": result, "ts": time.time()}
        log.info(f"[SOB] {plan_id}: served from pre-extracted benefits")
        return result

    # --- Fall back to on-demand Claude extraction ---
    chunks = load_plan_chunks(plan_id)
    if chunks is None:
        raise HTTPException(
            status_code=404,
            detail=f"No SOB document found for plan {plan_id}",
        )

    context = _chunks_to_context(chunks)

    from .circuit_breaker import anthropic_breaker

    with anthropic_breaker:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=60.0)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            system=SOB_EXTRACTION_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Plan: {plan_id}\n\nFull document text:\n\n{context}",
                }
            ],
        )

    # Parse Claude's response
    try:
        raw = message.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()
        parsed = json.loads(raw)
    except (json.JSONDecodeError, IndexError) as e:
        log.warning("[SOB] JSON parse failed: %s", e)
        log.debug("[SOB] Raw response: %s", raw[:500])
        raise HTTPException(
            status_code=500,
            detail="Failed to parse SOB benefits. Try again.",
        )

    result = {
        "success": True,
        "plan_id": plan_id,
        "plan_name": parsed.get("plan_name", plan_id),
        "plan_type": parsed.get("plan_type", ""),
        "monthly_premium": parsed.get("monthly_premium", ""),
        "annual_deductible_in": parsed.get("annual_deductible_in", ""),
        "annual_deductible_out": parsed.get("annual_deductible_out", ""),
        "moop_in": parsed.get("moop_in", ""),
        "moop_out": parsed.get("moop_out", ""),
        "medical": parsed.get("medical", []),
        "drugs": parsed.get("drugs", []),
    }

    # Enrich with CMS authoritative data
    try:
        result = _enrich_sob_with_cms(result, plan_number)
    except Exception as e:
        log.warning(f"CMS enrichment failed (non-fatal): {e}")

    # Cache it with timestamp
    with _sob_cache_lock:
        _evict_oldest(_sob_cache, SOB_CACHE_MAX)
        _sob_cache[plan_id] = {"data": result, "ts": time.time()}
    return result


def _find_sob_pdf(plan_number: str) -> str | None:
    """Find the actual SOB PDF file for a plan across all carrier folders.

    Different carriers use different naming:
      Humana:  H1036077000SB26.PDF
      UHC:     2026 English SB- ... H1045-057-000.pdf
      Aetna:   H1610_001_DS17_SB2026_M.pdf
      Devoted: 2026-DEVOTED-...-H9888-001-ENG.pdf
      Wellcare: Wellcare ... H5590-008.pdf

    Common thread: all filenames contain the H-number.
    """
    pid = normalize_plan_id(plan_number)          # H1036-077
    parts = pid.split("-")                         # ['H1036', '077']
    if len(parts) != 2:
        return None
    h_num, plan_id = parts                         # 'H1036', '077'
    # Patterns to match: H1036-077, H1036_077, H1036077
    search_patterns = [
        f"{h_num}-{plan_id}",                      # H1036-077
        f"{h_num}_{plan_id}",                      # H1036_077
        f"{h_num}{plan_id}",                       # H1036077
    ]

    for root, dirs, files in os.walk(PDFS_DIR):
        # Skip CMS data folder
        if "CMS" in root or "cms" in root:
            continue
        for fname in files:
            if not fname.lower().endswith(".pdf"):
                continue
            fname_upper = fname.upper()
            for pat in search_patterns:
                if pat.upper() in fname_upper:
                    return os.path.join(root, fname)
    return None


@app.get("/sob/pdf/{plan_number}")
def get_sob_pdf(plan_number: ValidPlanNumber, _user: dict = Depends(get_current_user)):
    """Serve the SOB PDF file for download."""
    _authorize_plan(_user, plan_number)
    path = _find_sob_pdf(plan_number)
    if not path:
        raise HTTPException(status_code=404, detail="SOB PDF not found for this plan.")
    filename = f"SOB_{normalize_plan_id(plan_number)}.pdf"
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/sob/raw/{plan_number}")
def get_sob_raw(plan_number: str):
    """Return the raw extracted JSON (chunks + carrier) for a plan."""
    path = _find_extracted_file(normalize_plan_id(plan_number))
    if not path:
        raise HTTPException(status_code=404, detail=f"No extracted data for {plan_number}")
    with open(path, "r") as f:
        return json.load(f)


@app.get("/debug/files")
def list_disk_files():
    """List files on the persistent disk (dev only)."""
    files = {}
    for folder in [EXTRACTED_DIR, PDFS_DIR]:
        if os.path.exists(folder):
            files[folder] = os.listdir(folder)
    return files


# --- OTC fallback from SOB extracted text ---

def _otc_from_sob_text(plan_number: str) -> dict | None:
    """
    Fast regex extraction of OTC amount from pre-extracted SOB text.
    Used when CMS has the OTC flag but no dollar amount stored.
    No Claude call — just reads the local JSON + regex.
    """
    sob_path = _find_extracted_file(plan_number)
    if sob_path is None:
        return None
    try:
        with open(sob_path) as f:
            data = json.load(f)
        chunks = data if isinstance(data, list) else data.get("chunks", [])
        for chunk in chunks:
            text = chunk if isinstance(chunk, str) else str(chunk)
            up = text.upper()
            if "OTC" not in up and "OVER-THE-COUNTER" not in up:
                continue
            m = re.findall(
                r"\$(\d+)\s+(?:per\s+)?(month|quarter|year|annual|monthly|quarterly|yearly)",
                text, re.IGNORECASE,
            )
            if m:
                amt, period_word = m[0]
                pw = period_word.lower()
                if pw in ("month", "monthly"):
                    period = "Monthly"
                elif pw in ("quarter", "quarterly"):
                    period = "Quarterly"
                else:
                    period = "Yearly"
                return {"amount": f"${amt}", "period": period}
    except Exception as e:
        log.warning(f"OTC SOB fallback failed for {plan_number}: {e}")
    return None


# --- Response Caching Helper ─────────────────────────────────────────────────

def _cached_json_response(data: dict, request: Request, max_age: int = 3600) -> JSONResponse:
    """Return a JSONResponse with Cache-Control and ETag headers.
    If the client sends a matching If-None-Match, returns 304."""
    body = json.dumps(data, sort_keys=True, separators=(",", ":"))
    etag = '"' + hashlib.sha256(body.encode()).hexdigest()[:32] + '"'

    client_etag = request.headers.get("If-None-Match")
    if client_etag and client_etag == etag:
        return JSONResponse(status_code=304, content=None, headers={"ETag": etag})

    return JSONResponse(
        content=data,
        headers={
            "Cache-Control": f"private, max-age={max_age}, stale-while-revalidate=600",
            "ETag": etag,
        },
    )


# --- Benefits Endpoint (SOB-first, CMS fallback) ---

def _sob_to_benefits_shape(sob: dict) -> dict:
    """
    Convert SOB extraction data (medical array, supplemental array)
    into the structured shape that buildBenefitCards expects:
      { medical: {pcp_copay, ...}, dental: {...}, otc: {...}, ... }
    """
    medical_list = sob.get("medical", [])
    supplemental = sob.get("supplemental", [])

    # Build lookup from SOB medical array
    def _find(label_fragment: str) -> str | None:
        frag = label_fragment.lower()
        for item in medical_list:
            lbl = (item.get("label") or "").lower()
            if frag in lbl or lbl in frag:
                return item.get("in_network") or item.get("value")
        for item in supplemental:
            lbl = (item.get("label") or "").lower()
            if frag in lbl or lbl in frag:
                return item.get("in_network") or item.get("value")
        return None

    # Medical copays
    medical = {}
    pcp = _find("pcp")
    if pcp:
        medical["pcp_copay"] = pcp
    spec = _find("specialist")
    if spec:
        medical["specialist_copay"] = spec
    uc = _find("urgent care")
    if uc:
        medical["urgent_care_copay"] = uc
    er = _find("emergency")
    if er:
        medical["er_copay"] = er

    # Dental
    dental = {}
    dental_prev = _find("dental") or _find("preventive dental")
    if dental_prev:
        dental["has_preventive"] = True
        dental["preventive"] = {"copay": dental_prev, "max_benefit": None}
        # Try to extract max benefit from value like "$0 copay ($2000/yr max)"
        import re as _re
        m = _re.search(r"\$[\d,]+(?:/yr)?\s*max", dental_prev, _re.IGNORECASE)
        if m:
            dental["preventive"]["max_benefit"] = m.group(0).replace("/yr max", "").strip()
    dental_comp = _find("comprehensive dental") or _find("dental (comprehensive)")
    if dental_comp:
        dental["has_comprehensive"] = True
        dental["comprehensive"] = {"max_benefit": dental_comp}

    # OTC
    otc = {}
    otc_val = _find("otc") or _find("over-the-counter")
    if otc_val:
        otc["has_otc"] = True
        otc["amount"] = otc_val
        # Try to detect period
        v = otc_val.lower()
        if "month" in v:
            otc["period"] = "Monthly"
        elif "quarter" in v:
            otc["period"] = "Quarterly"
        else:
            otc["period"] = "Yearly"

    # Part B giveback
    giveback = {}
    gb_val = _find("part b") or _find("giveback") or sob.get("part_b_premium_reduction")
    if gb_val and gb_val not in ("null", "None", "$0", "$0.00", ""):
        giveback["has_giveback"] = True
        import re as _re
        m = _re.search(r"\$[\d,.]+", str(gb_val))
        giveback["monthly_amount"] = m.group(0) if m else gb_val

    # Flex / SSBCI
    flex = {}
    flex_val = _find("flex") or _find("ssbci")
    if flex_val:
        flex["has_ssbci"] = True
        flex["benefits"] = [{"category": "Flex card", "amount": flex_val}]

    return {
        "plan": {
            "plan_name": sob.get("plan_name", ""),
            "plan_type": sob.get("plan_type", ""),
            "monthly_premium": sob.get("monthly_premium", ""),
        },
        "medical": medical,
        "dental": dental,
        "otc": otc,
        "flex_ssbci": flex,
        "part_b_giveback": giveback,
    }


def _cms_fill_gaps(result: dict, plan_number: str) -> dict:
    """Fill empty fields with CMS data — never overwrite existing SOB values."""
    try:
        cms = get_cms()
    except Exception:
        return result

    med = result.get("medical", {})
    dental = result.get("dental", {})
    otc = result.get("otc", {})
    flex = result.get("flex_ssbci", {})
    giveback = result.get("part_b_giveback", {})

    # Medical copays — only fill if SOB didn't have them
    try:
        cms_med = cms.get_medical_copays(plan_number)
        if not med.get("pcp_copay") and cms_med.get("pcp_copay"):
            med["pcp_copay"] = cms_med["pcp_copay"]
        if not med.get("specialist_copay") and cms_med.get("specialist_copay"):
            med["specialist_copay"] = cms_med["specialist_copay"]
        if not med.get("urgent_care_copay") and cms_med.get("urgent_care_copay"):
            med["urgent_care_copay"] = cms_med["urgent_care_copay"]
        if not med.get("er_copay") and cms_med.get("er_copay"):
            med["er_copay"] = cms_med["er_copay"]
    except Exception:
        pass

    # Dental — only fill if SOB didn't have it
    if not dental.get("has_preventive"):
        try:
            cms_dental = cms.get_dental_benefits(plan_number)
            if cms_dental.get("has_preventive") or cms_dental.get("has_comprehensive"):
                result["dental"] = cms_dental
        except Exception:
            pass

    # OTC — only fill if SOB didn't have it
    if not otc.get("has_otc"):
        try:
            cms_otc = cms.get_otc_allowance(plan_number)
            if cms_otc.get("has_otc"):
                result["otc"] = cms_otc
        except Exception:
            pass

    # Flex — only fill if SOB didn't have it
    if not flex.get("has_ssbci"):
        try:
            cms_flex = cms.get_flex_ssbci(plan_number)
            if cms_flex.get("has_ssbci"):
                result["flex_ssbci"] = cms_flex
        except Exception:
            pass

    # Part B giveback — only fill if SOB didn't have it
    if not giveback.get("has_giveback"):
        try:
            cms_gb = cms.get_part_b_giveback(plan_number)
            if cms_gb.get("has_giveback"):
                result["part_b_giveback"] = cms_gb
        except Exception:
            pass

    result["medical"] = med
    return result


@app.get("/benefits/{plan_number}")
def get_benefits(plan_number: ValidPlanNumber, request: Request, _user: dict = Depends(get_current_user)):
    """
    Benefits for home screen cards.
    Source of truth: SOB extraction (parsed PDFs).
    Fallback: CMS database (gap-fill only, never overrides SOB).
    """
    _authorize_plan(_user, plan_number)
    plan_id = normalize_plan_id(plan_number)

    # 1. Try SOB extraction (pre-extracted JSON or cached)
    sob = None
    pre = _load_pre_extracted_benefits(plan_id)
    if pre is not None:
        sob = {
            "plan_name": pre.get("plan_name", plan_id),
            "plan_type": pre.get("plan_type", ""),
            "monthly_premium": pre.get("monthly_premium", ""),
            "part_b_premium_reduction": pre.get("part_b_premium_reduction"),
            "medical": pre.get("medical", []),
            "supplemental": pre.get("supplemental", []),
        }
    else:
        # Check SOB cache
        with _sob_cache_lock:
            cached = _sob_cache.get(plan_id)
            if cached and (time.time() - cached["ts"]) < SOB_CACHE_TTL:
                sob = cached["data"]

    if sob is None:
        # Try on-demand extraction (loads PDF text, calls Claude)
        try:
            chunks = load_plan_chunks(plan_id)
            if chunks is not None:
                context = _chunks_to_context(chunks)
                from .circuit_breaker import anthropic_breaker
                with anthropic_breaker:
                    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=60.0)
                    message = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=3000,
                        system=SOB_EXTRACTION_PROMPT,
                        messages=[{"role": "user", "content": f"Plan: {plan_id}\n\nFull document text:\n\n{context}"}],
                    )
                raw = message.content[0].text.strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw.rsplit("```", 1)[0]
                sob = json.loads(raw.strip())
                # Cache it
                with _sob_cache_lock:
                    _evict_oldest(_sob_cache, SOB_CACHE_MAX)
                    _sob_cache[plan_id] = {"data": sob, "ts": time.time()}
        except Exception as e:
            log.warning("SOB extraction failed for %s: %s", plan_id, type(e).__name__)

    # 2. Convert SOB to the shape buildBenefitCards expects
    if sob:
        result = _sob_to_benefits_shape(sob)
    else:
        # 3. Last resort: try CMS directly
        try:
            cms = get_cms()
            result = cms.get_full_benefits(plan_number)
            if "error" in result:
                raise HTTPException(status_code=404, detail="No benefits data found for this plan.")
            return _cached_json_response(result, request)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=404, detail="No benefits data found for this plan.")

    # 4. Fill gaps with CMS (never override SOB)
    result = _cms_fill_gaps(result, plan_number)

    return _cached_json_response(result, request)


# --- CMS Benefits Endpoints ---

@app.get("/cms/benefits/{plan_number}")
def cms_benefits(plan_number: ValidPlanNumber, request: Request, _user: dict = Depends(get_current_user)):
    """Full plan benefits from CMS data."""
    _authorize_plan(_user, plan_number)
    cms = get_cms()
    result = cms.get_full_benefits(plan_number)
    if "error" in result:
        raise HTTPException(status_code=404, detail="Plan not found.")

    # OTC fallback: if CMS says plan has OTC but no dollar amount, check SOB text
    otc = result.get("otc", {})
    if otc.get("has_otc") and not otc.get("amount"):
        sob_otc = _otc_from_sob_text(plan_number)
        if sob_otc:
            otc["amount"] = sob_otc["amount"]
            otc["period"] = sob_otc["period"]

    return _cached_json_response(result, request)


@app.get("/cms/benefits/{plan_number}/medical")
def cms_medical(plan_number: ValidPlanNumber, request: Request, _user: dict = Depends(get_current_user)):
    """PCP, specialist, ER, urgent care copays."""
    _authorize_plan(_user, plan_number)
    cms = get_cms()
    return _cached_json_response(cms.get_medical_copays(plan_number), request)


@app.get("/cms/benefits/{plan_number}/dental")
def cms_dental(plan_number: ValidPlanNumber, request: Request, _user: dict = Depends(get_current_user)):
    """Dental preventive + comprehensive benefits."""
    _authorize_plan(_user, plan_number)
    cms = get_cms()
    return _cached_json_response(cms.get_dental_benefits(plan_number), request)


@app.get("/cms/benefits/{plan_number}/otc")
def cms_otc(plan_number: ValidPlanNumber, request: Request, _user: dict = Depends(get_current_user)):
    """OTC allowance amount and delivery method."""
    _authorize_plan(_user, plan_number)
    cms = get_cms()
    return _cached_json_response(cms.get_otc_allowance(plan_number), request)


@app.get("/cms/benefits/{plan_number}/vision")
def cms_vision(plan_number: ValidPlanNumber, request: Request, _user: dict = Depends(get_current_user)):
    """Eye exam + eyewear vision benefits."""
    _authorize_plan(_user, plan_number)
    cms = get_cms()
    return _cached_json_response(cms.get_vision_benefits(plan_number), request)


@app.get("/cms/benefits/{plan_number}/hearing")
def cms_hearing(plan_number: ValidPlanNumber, request: Request, _user: dict = Depends(get_current_user)):
    """Hearing exam + hearing aid benefits."""
    _authorize_plan(_user, plan_number)
    cms = get_cms()
    return _cached_json_response(cms.get_hearing_benefits(plan_number), request)


@app.get("/cms/benefits/{plan_number}/flex")
def cms_flex(plan_number: ValidPlanNumber, request: Request, _user: dict = Depends(get_current_user)):
    """Flex card / SSBCI supplemental benefits."""
    _authorize_plan(_user, plan_number)
    cms = get_cms()
    return _cached_json_response(cms.get_flex_ssbci(plan_number), request)


@app.get("/cms/benefits/{plan_number}/giveback")
def cms_giveback(plan_number: ValidPlanNumber, request: Request, _user: dict = Depends(get_current_user)):
    """Part B premium giveback amount."""
    _authorize_plan(_user, plan_number)
    cms = get_cms()
    return _cached_json_response(cms.get_part_b_giveback(plan_number), request)


@app.post("/cms/drug")
def cms_drug_lookup(req: DrugLookupRequest, _user: dict = Depends(get_current_user)):
    """Look up drug by name — returns tier, copay, restrictions."""
    _authorize_plan(_user, req.plan_number)
    cms = get_cms()
    result = cms.get_drug_by_name(req.plan_number, req.drug_name)
    if "error" in result:
        raise HTTPException(status_code=404, detail="Drug not found on this plan's formulary.")
    return result


@app.get("/cms/drug/{plan_number}/{drug_name}")
def cms_drug_lookup_get(plan_number: ValidPlanNumber, drug_name: str, _user: dict = Depends(get_current_user)):
    """GET version. Example: /cms/drug/H1036-077/Eliquis"""
    _authorize_plan(_user, plan_number)
    cms = get_cms()
    result = cms.get_drug_by_name(plan_number, drug_name)
    if "error" in result:
        raise HTTPException(status_code=404, detail="Drug not found on this plan's formulary.")
    return result


def _resolve_sob_cost(tier_copays: dict, tier: int, is_mail: bool, days_supply: int) -> dict | None:
    """
    Look up cost from SOB tier_copays for a given tier.
    Returns {"amount": float, "type": "copay"|"coinsurance", "pct": float|None, "cap": float|None, "raw": str}
    or None if SOB doesn't have data for this tier.

    Priority: SOB governs over CMS.
    """
    tier_data = tier_copays.get(tier)
    if not tier_data:
        return None

    # Pick the right column based on mail/days_supply
    if is_mail:
        # Prefer preferred mail, fall back to standard mail
        if days_supply >= 90:
            raw = tier_data.get("pref_mail_90") or tier_data.get("mail_90")
        else:
            raw = tier_data.get("pref_mail_30") or tier_data.get("mail_30")
    else:
        if days_supply >= 90:
            raw = tier_data.get("retail_90")
        else:
            raw = tier_data.get("retail_30")

    if not raw or raw.upper() == "N/A":
        # Fall back to retail_30 as default
        raw = tier_data.get("retail_30")

    if not raw or raw.upper() == "N/A":
        return None

    from .sob_parser import _parse_cost_value
    parsed = _parse_cost_value(raw)
    return parsed


@app.get("/cms/my-drugs-session/{session_id}")
def cms_my_drugs_session(session_id: str, _user: dict = Depends(get_current_user)):
    """Session-based drug lookup — no phone in URL."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    # Cross-user check: JWT subject must match the session's phone
    phone = session["phone"]
    if _user and _user.get("sub") not in (None, "dev") and _user["sub"] != phone:
        raise HTTPException(status_code=403, detail="Not authorized for this session")
    try:
        return _my_drugs_impl(session["data"])
    except HTTPException:
        raise
    except Exception as e:
        log.error("Drug lookup failed: %s: %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail=f"Drug lookup error: {type(e).__name__}: {e}")


@app.get("/cms/my-drugs/{phone}")
def cms_my_drugs(phone: str, _user: dict = Depends(get_current_user)):
    """Deprecated — use /cms/my-drugs-session/{session_id} instead."""
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Use /cms/my-drugs-session/{session_id} instead.",
    )


def _my_drugs_impl(member: dict):
    """
    Shared implementation for drug lookup.

    Runs a month-by-month simulation (SunFire-style) through:
      Deductible → Initial Coverage → Catastrophic
    to compute accurate monthly drug costs.

    Handles both flat copay plans (e.g. Florida Blue $35/drug) and
    coinsurance plans (e.g. UHC 16% × estimated full drug cost).
    """
    plan_number = member.get("plan_number", "")
    if not plan_number:
        raise HTTPException(status_code=400, detail="Member has no plan number")

    # 2. Parse medications
    raw_meds = member.get("medications", "") or ""
    meds = parse_medications(raw_meds)

    if not meds:
        return {
            "plan_number": plan_number,
            "medications": [],
            "monthly_total": 0,
            "monthly_display": "$0",
            "has_medications": False,
        }

    # 3. Load SOB tier copays (primary source) + CMS (fallback)
    cms = get_cms()
    sob_tiers = get_sob_tier_copays(plan_number)
    sob_insulin_cap = sob_tiers.get("insulin_cap", 35) if sob_tiers else 35
    sob_source = sob_tiers is not None

    # Deductible info from SOB
    drug_deductible = float(sob_tiers.get("deductible_amount", 0)) if sob_tiers else 0.0
    deductible_tiers = sob_tiers.get("deductible_tiers", []) if sob_tiers else []

    # Parse optional estimated full drug costs from member data
    # Format in Zoho: "Lantus:65,Ventolin:65.48,Humalog:160"
    raw_drug_costs = member.get("drug_costs", "") or ""
    drug_cost_map = _parse_drug_cost_map(raw_drug_costs)

    drugs = []
    engine_drugs = []  # Input for the simulation engine

    for med in meds:
        name = med["name"]
        days_supply = med["days_supply"]
        is_mail = med.get("is_mail", False)

        # Check if drug is insulin (independent of formulary lookup)
        from .cms_lookup import INSULIN_NAMES
        is_insulin = any(ins in name.lower() for ins in INSULIN_NAMES)

        # CMS lookup — gives us tier + restrictions (even if we override cost with SOB)
        result = cms.get_drug_by_name(plan_number, name, days_supply=days_supply)
        found_in_formulary = result and "error" not in result

        if found_in_formulary:
            tier = result.get("tier")
            actual_days = result.get("days_supply", days_supply)
            is_insulin = result.get("is_insulin", is_insulin)
        else:
            tier = None
            actual_days = days_supply

        # ── Resolve cost: SOB first, CMS fallback ──
        cost_type = "copay"
        best_option = f"{actual_days}-day"
        copay_retail = None
        copay_mail = None
        copay_amount = None       # flat $ for IC phase
        coinsurance_pct = None    # percentage for IC phase
        estimated_full_cost = None
        cost_source = "cms"

        # Look up estimated full drug cost from member data
        estimated_full_cost = _lookup_estimated_full_cost(name, drug_cost_map)

        # Try SOB first (SOB governs over CMS)
        sob_cost = None
        if sob_tiers and tier is not None:
            sob_cost = _resolve_sob_cost(sob_tiers, tier, is_mail, actual_days)
        elif sob_tiers and not found_in_formulary:
            sob_cost = _resolve_sob_cost(sob_tiers, 4, is_mail, actual_days)
            if sob_cost:
                tier = 4
                found_in_formulary = True
                cost_source = "sob-nonformulary"

        if sob_cost and sob_cost.get("type") == "copay" and sob_cost.get("amount") is not None:
            # SOB has a flat dollar copay
            copay_retail = sob_cost["amount"]
            copay_amount = float(sob_cost["amount"])
            cost_type = "copay"
            cost_source = cost_source if cost_source == "sob-nonformulary" else "sob"
            if is_mail:
                copay_mail = copay_retail
                best_option = f"{actual_days}-day mail"

        elif sob_cost and sob_cost.get("type") == "coinsurance":
            # SOB has percentage (e.g. 16% for UHC Tier 3)
            cost_type = "coinsurance"
            coinsurance_pct = sob_cost.get("pct")
            cost_source = cost_source if cost_source == "sob-nonformulary" else "sob"
            copay_retail = sob_cost.get("raw", "N/A")

            if sob_cost.get("cap") is not None:
                # "25% up to $35" — cap acts as max copay
                copay_amount = float(sob_cost["cap"])
                cost_type = "copay"  # effectively a capped copay

        elif found_in_formulary and result:
            # Fall back to CMS
            cost_source = "cms"
            copay_retail = result.get("copay_preferred") or result.get("copay_30day_preferred")
            copay_mail = result.get("copay_mail") or result.get("copay_90day_mail")
            cost_type_retail = result.get("cost_type", result.get("cost_type_30day", "copay"))
            cost_type_mail = result.get("cost_type_90day", "copay")
            cost_max = result.get("cost_max_30day")

            if is_mail and copay_mail is not None and isinstance(copay_mail, (int, float)):
                copay_amount = float(copay_mail)
                cost_type = cost_type_mail
                best_option = f"{actual_days}-day mail"
            elif cost_type_retail == "copay" and isinstance(copay_retail, (int, float)):
                copay_amount = float(copay_retail)
                cost_type = cost_type_retail
            elif cost_type_retail == "coinsurance":
                cost_type = "coinsurance"
                pct_str = str(copay_retail or "")
                pct_match = re.match(r'([\d.]+)%?', pct_str)
                if pct_match:
                    coinsurance_pct = float(pct_match.group(1))
                if cost_max is not None and cost_max > 0:
                    copay_amount = float(cost_max)

        # Compute the monthly IC (Initial Coverage) cost
        monthly_cost = _compute_ic_monthly_cost(
            cost_type=cost_type,
            copay_amount=copay_amount,
            coinsurance_pct=coinsurance_pct,
            estimated_full_cost=estimated_full_cost,
            days_supply=actual_days,
            is_insulin=is_insulin,
            insulin_cap=float(sob_insulin_cap),
        )

        # Determine deductible applicability
        ded_applies = result.get("deductible_applies", False) if result and "error" not in result else False
        if tier is not None and tier in deductible_tiers:
            ded_applies = True

        # Build engine input for simulation
        engine_drugs.append({
            "name": name,
            "tier": tier,
            "cost_type": cost_type,
            "copay_amount": copay_amount,
            "coinsurance_pct": coinsurance_pct,
            "estimated_full_cost": estimated_full_cost,
            "is_insulin": is_insulin,
            "deductible_applies": ded_applies,
        })

        # Build display string
        if found_in_formulary or cost_source == "sob-nonformulary":
            if cost_type == "coinsurance" and monthly_cost > 0:
                # We computed the coinsurance dollar amount — show it
                copay_display = "$" + str(int(round(monthly_cost)))
            elif cost_type == "coinsurance" and monthly_cost == 0:
                # No estimated full cost — show percentage
                copay_display = str(copay_retail or "N/A")
            else:
                copay_display = "$" + str(int(round(monthly_cost)))

            tier_labels = {1: "Preferred Generic", 2: "Generic", 3: "Preferred Brand",
                           4: "Non-Preferred Drug", 5: "Specialty", 6: "Select Care"}

            drugs.append({
                "drug_name": name,
                "tier": tier,
                "tier_label": tier_labels.get(tier, f"Tier {tier}") if tier else "",
                "copay_30day": copay_retail,
                "copay_90day_mail": copay_mail,
                "cost_type": cost_type,
                "coinsurance_pct": coinsurance_pct,
                "estimated_full_cost": estimated_full_cost,
                "is_insulin": is_insulin,
                "monthly_cost": round(monthly_cost, 2),
                "best_option": best_option,
                "copay_display": copay_display,
                "prior_auth": result.get("prior_auth", False) if result and "error" not in result else False,
                "step_therapy": result.get("step_therapy", False) if result and "error" not in result else False,
                "quantity_limit": result.get("quantity_limit", False) if result and "error" not in result else False,
                "deductible_applies": ded_applies,
                "found": True,
                "cost_source": cost_source,
            })
        else:
            drugs.append({
                "drug_name": name,
                "tier": None,
                "tier_label": "",
                "copay_30day": None,
                "copay_display": "Not found",
                "prior_auth": False,
                "step_therapy": False,
                "quantity_limit": False,
                "deductible_applies": False,
                "found": False,
                "cost_source": "none",
            })

    # ── Run month-by-month simulation ──
    # This models Deductible → Initial Coverage → Catastrophic across 12 months
    simulation = compute_monthly_drug_costs(
        drugs=engine_drugs,
        drug_deductible=drug_deductible,
        deductible_tiers=deductible_tiers,
        insulin_cap=float(sob_insulin_cap),
    )

    # Use current month from simulation (accounts for deductible phase)
    import datetime
    current_month = datetime.date.today().month
    current_month_data = simulation["monthly_breakdown"][current_month - 1] if simulation["monthly_breakdown"] else None
    sim_monthly_total = current_month_data["total"] if current_month_data else 0.0

    # Update per-drug monthly_cost with simulation-aware values
    if current_month_data:
        for i, drug_entry in enumerate(drugs):
            if drug_entry.get("found") and i < len(current_month_data["drugs"]):
                sim_drug = current_month_data["drugs"][i]
                drug_entry["monthly_cost"] = sim_drug["member_cost"]
                drug_entry["coverage_phase"] = sim_drug["phase"]
                # Update display
                if sim_drug["member_cost"] > 0:
                    drug_entry["copay_display"] = "$" + str(int(round(sim_drug["member_cost"])))
                elif drug_entry["cost_type"] == "coinsurance" and drug_entry.get("coinsurance_pct"):
                    drug_entry["copay_display"] = f"{drug_entry['coinsurance_pct']:.0f}%"

    # Calculate totals from simulation
    monthly_total = sim_monthly_total

    return {
        "plan_number": plan_number,
        "medications": drugs,
        "monthly_total": round(monthly_total, 2),
        "monthly_display": "$" + str(int(round(monthly_total))),
        "estimated_annual_drug_cost": simulation["annual_total"],
        "annual_display": "$" + str(int(round(simulation["annual_total"]))),
        "has_medications": True,
        "cost_source": "sob" if sob_source else "cms",
        "current_month": current_month,
        "drug_deductible": drug_deductible,
        "deductible_tiers": deductible_tiers,
        "simulation": {
            "annual_total": simulation["annual_total"],
            "average_monthly": simulation["average_monthly"],
            "monthly_breakdown": simulation["monthly_breakdown"],
        },
    }


def _parse_drug_cost_map(raw: str) -> dict:
    """
    Parse estimated full drug costs from a string.
    Format: "Lantus:65,Ventolin:65.48,Humalog:160"
    Returns dict mapping lowercase drug name fragments to float costs.
    """
    cost_map = {}
    if not raw or not raw.strip():
        return cost_map
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" not in pair:
            continue
        name_part, cost_part = pair.split(":", 1)
        try:
            cost_map[name_part.strip().lower()] = float(cost_part.strip())
        except ValueError:
            continue
    return cost_map


def _lookup_estimated_full_cost(drug_name: str, cost_map: dict) -> float | None:
    """
    Look up estimated full drug cost from the cost map.
    Matches on partial name (e.g. "lantus" matches "Lantus SOLN 100UNIT/ML").
    """
    lower_name = drug_name.lower()
    for key, cost in cost_map.items():
        if key in lower_name or lower_name in key:
            return cost
    return None


def _compute_ic_monthly_cost(
    cost_type: str,
    copay_amount: float | None,
    coinsurance_pct: float | None,
    estimated_full_cost: float | None,
    days_supply: int,
    is_insulin: bool,
    insulin_cap: float,
) -> float:
    """
    Compute the monthly cost in the Initial Coverage phase.

    For flat copay: monthly = copay / (days_supply / 30)
    For coinsurance: monthly = (pct/100 × estimated_full_cost) / (days_supply / 30)
    """
    months_per_fill = days_supply / 30.0
    monthly_cost = 0.0

    if cost_type == "copay" and copay_amount is not None:
        monthly_cost = float(copay_amount) / months_per_fill
    elif cost_type == "coinsurance" and coinsurance_pct is not None:
        if estimated_full_cost is not None and estimated_full_cost > 0:
            fill_cost = (coinsurance_pct / 100.0) * estimated_full_cost
            monthly_cost = fill_cost / months_per_fill

    # IRA insulin cap
    if is_insulin and monthly_cost > insulin_cap:
        monthly_cost = insulin_cap

    return round(monthly_cost, 2)


# ═══════════════════════════════════════════════════════════════════════════════
# MEDICATION REMINDERS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/reminders/{session_id}")
def list_reminders(session_id: str, _user: dict = Depends(get_current_user)):
    """List all medication reminders for this member."""
    phone = _session_phone(session_id, _user)
    db = get_user_db()
    return {"reminders": db.get_reminders(phone)}


@app.post("/reminders/{session_id}")
def create_reminder(session_id: str, req: ReminderCreate, _user: dict = Depends(get_current_user)):
    """Create a single medication reminder."""
    phone = _session_phone(session_id, _user)
    if not 0 <= req.time_hour <= 23:
        raise HTTPException(status_code=400, detail="time_hour must be 0-23")
    if not 0 <= req.time_minute <= 59:
        raise HTTPException(status_code=400, detail="time_minute must be 0-59")
    db = get_user_db()
    reminder = db.create_reminder(
        phone=phone,
        drug_name=req.drug_name,
        time_hour=req.time_hour,
        time_minute=req.time_minute,
        dose_label=req.dose_label,
        days_supply=req.days_supply,
        refill_reminder=req.refill_reminder,
        last_refill_date=req.last_refill_date,
    )
    get_audit_log().record(
        actor=phone, action="create", resource="reminder",
        resource_id=str(reminder.get("id", "")), detail="reminder_create",
    )
    return {"reminder": reminder}


@app.post("/reminders/{session_id}/bulk")
def create_reminders_bulk(session_id: str, req: BulkReminderCreate, _user: dict = Depends(get_current_user)):
    """Create multiple reminders at once (agent onboarding)."""
    phone = _session_phone(session_id, _user)
    db = get_user_db()
    reminders = db.create_reminders_bulk(
        phone=phone,
        reminders=[r.model_dump() for r in req.reminders],
        created_by=req.created_by,
    )
    get_audit_log().record(
        actor=phone, action="create", resource="reminder",
        detail=f"bulk_create:{len(reminders)}",
    )
    return {"reminders": reminders, "count": len(reminders)}


@app.put("/reminders/{session_id}/{reminder_id}")
def update_reminder(session_id: str, reminder_id: int, req: ReminderUpdate, _user: dict = Depends(get_current_user)):
    """Update a reminder (toggle, reschedule, etc.)."""
    phone = _session_phone(session_id, _user)
    db = get_user_db()
    reminder = db.update_reminder(phone, reminder_id, **req.model_dump(exclude_none=True))
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    get_audit_log().record(
        actor=phone, action="update", resource="reminder",
        resource_id=str(reminder_id), detail="reminder_update",
    )
    return {"reminder": reminder}


@app.delete("/reminders/{session_id}/{reminder_id}")
def delete_reminder(session_id: str, reminder_id: int, _user: dict = Depends(get_current_user)):
    """Delete a medication reminder."""
    phone = _session_phone(session_id, _user)
    db = get_user_db()
    deleted = db.delete_reminder(phone, reminder_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Reminder not found")
    get_audit_log().record(
        actor=phone, action="delete", resource="reminder",
        resource_id=str(reminder_id), detail="reminder_delete",
    )
    return {"deleted": True}


# ═══════════════════════════════════════════════════════════════════════════════
# BENEFITS USAGE TRACKING
# ═══════════════════════════════════════════════════════════════════════════════

VALID_USAGE_CATEGORIES = {"otc", "dental", "flex", "vision", "hearing"}


@app.post("/usage/{session_id}")
def log_usage(session_id: str, req: UsageCreate, _user: dict = Depends(get_current_user)):
    """Log a benefits usage entry (e.g. OTC purchase, dental visit)."""
    phone = _session_phone(session_id, _user)
    cat = req.category.lower()
    if cat not in VALID_USAGE_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {', '.join(VALID_USAGE_CATEGORIES)}")
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    db = get_user_db()
    entry = db.log_usage(
        phone=phone,
        category=cat,
        amount=req.amount,
        benefit_period=req.benefit_period,
        description=req.description,
        usage_date=req.usage_date,
    )
    get_audit_log().record(
        actor=phone, action="create", resource="usage",
        detail=f"category:{cat},amount:{req.amount}",
    )
    return {"usage": entry}


@app.get("/usage/{session_id}")
def get_usage(session_id: str, category: Optional[str] = None, _user: dict = Depends(get_current_user)):
    """Get all usage entries for this member, optionally filtered by category."""
    phone = _session_phone(session_id, _user)
    db = get_user_db()
    entries = db.get_usage(phone, category)
    return {"usage": entries}


@app.delete("/usage/{session_id}/{usage_id}")
def delete_usage(session_id: str, usage_id: int, _user: dict = Depends(get_current_user)):
    """Delete a usage entry (undo mistake)."""
    phone = _session_phone(session_id, _user)
    db = get_user_db()
    deleted = db.delete_usage(phone, usage_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Usage entry not found")
    return {"deleted": True}


@app.get("/usage/{session_id}/summary")
def usage_summary(session_id: str, _user: dict = Depends(get_current_user)):
    """
    Get per-category spending summary: spent vs. cap for current period.
    Cross-references CMS benefit caps with logged usage.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    phone = session["phone"]
    # Cross-user check: JWT subject must match the session's phone
    if _user and _user.get("sub") not in (None, "dev") and _user["sub"] != phone:
        raise HTTPException(status_code=403, detail="Not authorized for this session")
    get_store().touch_session(session_id)

    plan_number = session["data"].get("plan_number", "")
    if not plan_number:
        return {"summary": []}

    db = get_user_db()
    cms = get_cms()

    # Gather benefit caps from CMS
    categories = []

    # OTC
    try:
        otc = cms.get_otc_allowance(plan_number)
        if otc and otc.get("has_otc") and otc.get("amount"):
            amt = otc["amount"]
            # amount may be string with $ — normalize to float
            if isinstance(amt, str):
                amt = float(amt.replace("$", "").replace(",", "").strip())
            period = otc.get("period", "Monthly")
            categories.append({"category": "otc", "cap": amt, "period": period, "label": "OTC Allowance"})
    except (ValueError, TypeError, KeyError) as e:
        log.debug("OTC category parse error: %s", e)

    # Dental
    try:
        dental = cms.get_dental_benefits(plan_number)
        if dental and dental.get("has_preventive"):
            prev = dental.get("preventive", {})
            max_ben = prev.get("max_benefit")
            if max_ben:
                cap = float(str(max_ben).replace("$", "").replace(",", ""))
                categories.append({"category": "dental", "cap": cap, "period": "Yearly", "label": "Dental"})
    except (ValueError, TypeError, KeyError) as e:
        log.debug("Dental category parse error: %s", e)

    # Flex / SSBCI
    try:
        flex = cms.get_flex_ssbci(plan_number)
        if flex and flex.get("has_ssbci") and flex.get("benefits"):
            total = 0
            for b in flex["benefits"]:
                raw = b.get("amount", "0")
                if isinstance(raw, str):
                    raw = raw.replace("$", "").replace(",", "").strip()
                    if raw and raw != "Included":
                        total += float(raw)
                elif isinstance(raw, (int, float)):
                    total += float(raw)
            if total > 0:
                categories.append({"category": "flex", "cap": total, "period": "Yearly", "label": "Flex Card"})
    except (ValueError, TypeError, KeyError) as e:
        log.debug("Flex category parse error: %s", e)

    # Vision
    try:
        vision = cms.get_vision_benefits(plan_number)
        if vision and vision.get("has_eye_exam"):
            exams = vision.get("eye_exam", {})
            max_amt = exams.get("max_benefit")
            if max_amt:
                cap = float(str(max_amt).replace("$", "").replace(",", ""))
                categories.append({"category": "vision", "cap": cap, "period": "Yearly", "label": "Vision"})
    except (ValueError, TypeError, KeyError) as e:
        log.debug("Vision category parse error: %s", e)

    # Hearing
    try:
        hearing = cms.get_hearing_benefits(plan_number)
        if hearing and hearing.get("has_hearing_aids"):
            aids = hearing.get("hearing_aids", {})
            max_amt = aids.get("max_benefit")
            if max_amt:
                cap = float(str(max_amt).replace("$", "").replace(",", ""))
                categories.append({"category": "hearing", "cap": cap, "period": "Yearly", "label": "Hearing"})
    except (ValueError, TypeError, KeyError) as e:
        log.debug("Hearing category parse error: %s", e)

    if not categories:
        return {"summary": []}

    # Get current-period spending for each category
    benefit_periods = {c["category"]: c["period"] for c in categories}
    totals = db.get_current_period_totals(phone, benefit_periods)

    summary = []
    for c in categories:
        spent = totals.get(c["category"], 0.0)
        cap = c["cap"]
        remaining = max(0, cap - spent)
        pct = round((spent / cap) * 100, 1) if cap > 0 else 0
        summary.append({
            "category": c["category"],
            "label": c["label"],
            "cap": cap,
            "period": c["period"],
            "spent": spent,
            "remaining": remaining,
            "pct_used": pct,
        })

    return {"summary": summary}



# ═══════════════════════════════════════════════════════════════════════════════
# DIGITAL ID CARD
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/cms/id-card/{plan_number}")
def get_id_card_data(plan_number: ValidPlanNumber, request: Request, _user: dict = Depends(get_current_user)):
    """Return all data needed to render a digital insurance ID card."""
    _authorize_plan(_user, plan_number)
    from .carrier_config import detect_carrier, get_carrier_config

    cms = get_cms()
    overview = cms.get_plan_overview(plan_number)
    if not overview:
        raise HTTPException(status_code=404, detail="Plan not found.")

    medical = cms.get_medical_copays(plan_number)

    carrier_key = detect_carrier(
        overview.get("plan_name", ""),
        overview.get("org_name", ""),
    )
    rx = get_carrier_config(carrier_key) if carrier_key else {}

    result = {
        "plan_name": overview.get("plan_name", ""),
        "org_name": overview.get("org_name", ""),
        "contract_id": overview.get("contract_id", ""),
        "plan_id": overview.get("plan_id", ""),
        "carrier": carrier_key or "",
        "effective_date": "01/01/2026",
        "pcp_copay": medical.get("pcp_copay"),
        "specialist_copay": medical.get("specialist_copay"),
        "er_copay": medical.get("er_copay"),
        "urgent_care_copay": medical.get("urgent_care_copay"),
        "rx_bin": rx.get("rx_bin", ""),
        "rx_pcn": rx.get("rx_pcn", ""),
        "rx_group": rx.get("rx_group", ""),
        "customer_service": rx.get("customer_service", ""),
        "customer_service_tty": rx.get("customer_service_tty", "711"),
        "pharmacy_help": rx.get("pharmacy_help", ""),
        "prior_auth_phone": rx.get("prior_auth", ""),
        "website": rx.get("website", ""),
    }
    return _cached_json_response(result, request)

