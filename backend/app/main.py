"""
InsuranceNYou Backend API
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from .claude_client import ask_claude, load_plan_chunks, find_relevant_chunks, _find_extracted_file
from .zoho_client import search_contact_by_phone
from .providers.service import search_providers
from .sob_parser import extract_tier_copays, load_plan_text

import json
import os
import re
import logging
import time
import uuid
import anthropic
from starlette.requests import Request
from starlette.responses import JSONResponse
from .config import ANTHROPIC_API_KEY, EXTRACTED_DIR, PDFS_DIR, APP_ENV, CORS_ORIGINS, LOG_LEVEL, ADMIN_SECRET, GDRIVE_FOLDER_ID
from .user_data import UserDataDB

# ── Structured logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

app = FastAPI(title="InsuranceNYou API", version="0.6.0")

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
        allow_headers=["*"],
    )
else:
    # Dev: allow any localhost origin
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(?:localhost|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ── Request timing + metrics middleware ──────────────────────────────────────
_request_metrics: dict = {"total": 0, "errors": 0, "latency_sum": 0.0}

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
    except Exception:
        _request_metrics["errors"] += 1
        raise
    elapsed = time.time() - start
    _request_metrics["total"] += 1
    _request_metrics["latency_sum"] += elapsed
    if response.status_code >= 500:
        _request_metrics["errors"] += 1
    log.info(f"{request.method} {request.url.path} → {response.status_code} ({elapsed:.3f}s)")
    return response

# ── Session store (in-memory with TTL) ───────────────────────────────────────
_sessions: dict[str, dict] = {}
SESSION_TTL = 7200  # 2 hours

def create_session(phone: str, member_data: dict) -> str:
    """Create a session and return the session ID."""
    sid = uuid.uuid4().hex
    _sessions[sid] = {"phone": phone, "data": member_data, "ts": time.time()}
    _cleanup_sessions()
    return sid

def get_session(sid: str) -> dict | None:
    """Get session data, or None if expired/missing."""
    entry = _sessions.get(sid)
    if not entry:
        return None
    if time.time() - entry["ts"] > SESSION_TTL:
        _sessions.pop(sid, None)
        return None
    return entry

def _cleanup_sessions():
    """Remove expired sessions (called lazily)."""
    now = time.time()
    expired = [k for k, v in _sessions.items() if now - v["ts"] > SESSION_TTL]
    for k in expired:
        _sessions.pop(k, None)

# In-memory cache for parsed SOB summaries: {plan_id: {"data": {...}, "ts": float}}
_sob_cache: dict[str, dict] = {}
SOB_CACHE_TTL = 3600  # 1 hour

# User Data DB — lazy init
_user_db = None


def get_user_db() -> UserDataDB:
    global _user_db
    if _user_db is None:
        _user_db = UserDataDB()
        log.info("User data DB loaded")
    return _user_db


def _session_phone(session_id: str) -> str:
    """Resolve session_id → phone, or raise 401."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    # Touch timestamp to extend TTL on activity
    session["ts"] = time.time()
    return session["phone"]


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
            log.warning(f"CMS database not available: {e}")
            raise HTTPException(status_code=503, detail="CMS database not loaded")
    return _cms


# SOB tier copays cache: {plan_id: {"data": dict, "ts": float}}
_sob_tier_cache: dict[str, dict] = {}
SOB_TIER_CACHE_TTL = 3600  # 1 hour


def get_sob_tier_copays(plan_id: str) -> dict | None:
    """
    Load structured per-tier copay data from the SOB PDF for a plan.
    Returns dict keyed by tier number (1-5) with retail_30, retail_90, mail costs, etc.
    Returns None if SOB text not available for this plan.
    Cached in memory for 1 hour.
    """
    pid = normalize_plan_id(plan_id)
    cached = _sob_tier_cache.get(pid)
    if cached and (time.time() - cached["ts"]) < SOB_TIER_CACHE_TTL:
        return cached["data"]

    text = load_plan_text(pid)
    if text is None:
        return None

    try:
        tier_copays = extract_tier_copays(text)
        _sob_tier_cache[pid] = {"data": tier_copays, "ts": time.time()}
        log.info(f"SOB tier copays loaded for {pid}: tiers={[k for k in tier_copays if isinstance(k, int)]}")
        return tier_copays
    except Exception as e:
        log.warning(f"SOB tier copay extraction failed for {pid}: {e}")
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
    question: str
    plan_number: str

class AskResponse(BaseModel):
    answer: str
    plan_number: str
    has_context: bool

class LookupRequest(BaseModel):
    phone: str

class LookupResponse(BaseModel):
    found: bool
    first_name: str = ""
    last_name: str = ""
    plan_name: str = ""
    plan_number: str = ""
    agent: str = ""
    medicare_number: str = ""
    phone: str = ""
    medications: str = ""
    zip_code: str = ""
    session_id: str = ""

class ProviderSearchRequest(BaseModel):
    plan_name: str
    specialty: str
    zip_code: str
    radius_miles: float = 25.0
    limit: int = 200
    enrich_google: bool = True

class PharmacySearchRequest(BaseModel):
    plan_number: str = ""
    zip_code: str
    radius_miles: int = 10
    limit: int = 30

class SOBRequest(BaseModel):
    plan_number: str

class DrugLookupRequest(BaseModel):
    plan_number: str
    drug_name: str


# --- Reminder / Usage Models ---

class ReminderCreate(BaseModel):
    drug_name: str
    dose_label: str = ""
    time_hour: int          # 0-23
    time_minute: int = 0
    days_supply: int = 30
    refill_reminder: bool = False
    last_refill_date: Optional[str] = None

class ReminderUpdate(BaseModel):
    enabled: Optional[bool] = None
    time_hour: Optional[int] = None
    time_minute: Optional[int] = None
    refill_reminder: Optional[bool] = None
    last_refill_date: Optional[str] = None
    dose_label: Optional[str] = None

class BulkReminderCreate(BaseModel):
    reminders: list[ReminderCreate]
    created_by: str = "member"

class UsageCreate(BaseModel):
    category: str           # otc, dental, flex, vision, hearing
    amount: float
    description: str = ""
    usage_date: Optional[str] = None  # defaults to today
    benefit_period: str = "Monthly"   # Monthly, Quarterly, Yearly


# --- Endpoints ---

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    """Basic request metrics for monitoring."""
    total = _request_metrics["total"]
    return {
        "total_requests": total,
        "total_errors": _request_metrics["errors"],
        "avg_latency_ms": round((_request_metrics["latency_sum"] / total) * 1000, 1) if total > 0 else 0,
        "active_sessions": len(_sessions),
        "sob_cache_size": len(_sob_cache),
    }


@app.post("/auth/lookup", response_model=LookupResponse)
def lookup_member(req: LookupRequest):
    """Look up a member by phone number in Zoho CRM."""
    try:
        member = search_contact_by_phone(req.phone)
    except Exception as e:
        log.error(f"Zoho lookup failed: {e}")
        raise HTTPException(status_code=500, detail="Unable to verify your account right now. Please try again.")

    if member is None:
        return LookupResponse(found=False)

    # Create session so frontend doesn't need to pass phone around
    sid = create_session(req.phone, member)

    return LookupResponse(
        found=True,
        first_name=member["first_name"],
        last_name=member["last_name"],
        plan_name=member["plan_name"],
        plan_number=member["plan_number"],
        agent=member["agent"] or "",
        medicare_number=member.get("medicare_number", "") or "",
        phone=member["phone"] or member["mobile"],
        medications=member.get("medications", "") or "",
        zip_code=member.get("zip_code", "") or "",
        session_id=sid,
    )


@app.post("/ask", response_model=AskResponse)
def ask_question(req: AskRequest):
    """Ask a question about a member's plan benefits."""
    plan_id = normalize_plan_id(req.plan_number)
    result = ask_claude(question=req.question, plan_number=plan_id)
    return AskResponse(**result)


@app.post("/providers/search")
async def provider_search(req: ProviderSearchRequest):
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
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@app.post("/pharmacies/search")
async def pharmacy_search(req: PharmacySearchRequest):
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
        raise HTTPException(status_code=400, detail=result["error"])

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
    """Supplement Claude's SOB extraction with authoritative CMS data."""
    try:
        cms = get_cms()
    except Exception:
        return result

    medical = result.get("medical", [])
    label_map = {}
    for i, item in enumerate(medical):
        lbl = (item.get("label") or "").lower()
        label_map[lbl] = i

    # ── Dental (ALWAYS override — CMS is authoritative) ──
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

            _upsert_medical(medical, label_map, "Dental (preventive)", pv_value, force=True)
            if dental.get("has_comprehensive") and cmp_value:
                _upsert_medical(medical, label_map, "Dental (comprehensive)", cmp_value, force=True)
    except Exception as e:
        log.warning(f"CMS dental enrichment failed: {e}")

    # ── Medical copays (CMS is authoritative) ──
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
                _upsert_medical(medical, label_map, label, value, force=True)
    except Exception as e:
        log.warning(f"CMS medical copay enrichment failed: {e}")

    # ── Vision (CMS is authoritative) ──
    try:
        vision = cms.get_vision_benefits(plan_number)
        if vision.get("has_eye_exam"):
            exam = vision["eye_exam"]
            copay = exam.get("copay", "$0")
            max_b = exam.get("max_benefit")
            exams = exam.get("exams_per_year")
            parts = [copay + " copay"]
            if exams:
                parts.append(f"{exams}/yr")
            _upsert_medical(medical, label_map, "Vision (exam)", ", ".join(parts), force=True)

        if vision.get("has_eyewear"):
            ew = vision["eyewear"]
            copay = ew.get("copay", "$0")
            max_b = ew.get("max_benefit")
            if max_b:
                ew_value = f"{copay} copay ({max_b}/yr allowance)"
            else:
                ew_value = f"{copay} copay"
            _upsert_medical(medical, label_map, "Vision (eyewear)", ew_value, force=True)
    except Exception as e:
        log.warning(f"CMS vision enrichment failed: {e}")

    # ── Hearing (CMS is authoritative) ──
    try:
        hearing = cms.get_hearing_benefits(plan_number)
        if hearing.get("has_hearing_exam"):
            exam = hearing["hearing_exam"]
            copay = exam.get("copay", "$0")
            exams = exam.get("exams_per_year")
            parts = [copay + " copay"]
            if exams:
                parts.append(f"{exams}/yr")
            _upsert_medical(medical, label_map, "Hearing (exam)", ", ".join(parts), force=True)

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
            _upsert_medical(medical, label_map, "Hearing (aids)", ", ".join(parts) if parts else "Covered", force=True)
    except Exception as e:
        log.warning(f"CMS hearing enrichment failed: {e}")

    # ── OTC allowance (only fill if Claude missed it) ──
    try:
        otc = cms.get_otc_allowance(plan_number)
        if otc.get("has_otc"):
            amt = otc.get("amount", "")
            period = otc.get("period", "")
            otc_value = f"{amt} {period}".strip() if amt else "Included"
            _upsert_medical(medical, label_map, "OTC allowance", otc_value)
    except Exception as e:
        log.warning(f"CMS OTC enrichment failed: {e}")

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
        log.warning(f"CMS flex enrichment failed: {e}")

    # ── Part B giveback (only fill if Claude missed it) ──
    try:
        giveback = cms.get_part_b_giveback(plan_number)
        if giveback.get("has_giveback"):
            gb_value = f"{giveback['monthly_amount']}/mo reduction"
            _upsert_medical(medical, label_map, "Part B giveback", gb_value)
    except Exception as e:
        log.warning(f"CMS giveback enrichment failed: {e}")

    result["medical"] = medical
    return result


SOB_EXTRACTION_PROMPT = """You are extracting benefits from a Medicare Summary of Benefits PDF. Your job is to pull EVERY dollar amount and cost-share from this document.

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

Return ONLY valid JSON:
{
  "plan_name": "Full official plan name from document",
  "plan_type": "HMO or PPO or PFFS etc",
  "monthly_premium": "$X.XX",
  "annual_deductible_in": "In-network deductible",
  "annual_deductible_out": "Out-of-network deductible",
  "moop_in": "In-network max out of pocket",
  "moop_out": "Out-of-network max out of pocket",
  "medical": [
    {"label": "Short name", "in_network": "$X", "out_of_network": "$X"}
  ],
  "drugs": [
    {"label": "Tier/phase name", "value": "$X"}
  ]
}

For medical, include ALL of these if in the document:
- PCP visit
- Specialist visit
- Preventive care
- Urgent care
- Emergency room
- Inpatient hospital
- Outpatient surgery
- Ambulance
- Lab services
- X-rays/imaging
- Mental health (outpatient)
- Mental health (inpatient)
- Skilled nursing
- Home health care
- Dental (preventive)
- Dental (comprehensive)
- Vision (exam)
- Vision (eyewear)
- Hearing (exam)
- Hearing (aids)
- Chiropractic
- Podiatry
- Physical/occupational therapy
- Telehealth

For drugs, extract every tier shown. Common tiers:
- Preferred retail pharmacy (30-day, 90-day)
- Standard retail pharmacy (30-day, 90-day)
- Mail order (90-day)
Each with: Tier 1 (Preferred Generic), Tier 2 (Generic), Tier 3 (Preferred Brand), Tier 4 (Non-Preferred), Tier 5 (Specialty)

Return ONLY the JSON. No markdown fences, no explanation."""


@app.post("/sob/summary")
def get_sob_summary(req: SOBRequest):
    """
    Get structured SOB benefits for a plan.
    Uses Claude to parse raw SOB text into medical/drug categories
    with in-network and out-of-network columns.
    Results are cached in memory so it only parses once per plan.
    """
    plan_id = normalize_plan_id(req.plan_number)

    # Check cache first (with TTL)
    cached = _sob_cache.get(plan_id)
    if cached and (time.time() - cached["ts"]) < SOB_CACHE_TTL:
        return cached["data"]

    # Load extracted chunks
    chunks = load_plan_chunks(plan_id)
    if chunks is None:
        raise HTTPException(
            status_code=404,
            detail=f"No SOB document found for plan {plan_id}",
        )

    # Use MORE chunks — we need the full document for in/out of network
    context = "\n\n---\n\n".join(chunks[:12])

    # Ask Claude to extract structured benefits
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

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
        print(f"[SOB] JSON parse failed: {e}")
        print(f"[SOB] Raw response: {raw[:500]}")
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
        result = _enrich_sob_with_cms(result, req.plan_number)
    except Exception as e:
        log.warning(f"CMS enrichment failed (non-fatal): {e}")

    # Cache it with timestamp
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
def get_sob_pdf(plan_number: str):
    """Serve the actual SOB PDF file for download."""
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


# --- Admin: sync PDFs from Google Drive ---

class SyncRequest(BaseModel):
    secret: str = ""

_sync_status: dict = {"running": False, "last_result": None}

def _run_sync_background():
    """Run the full sync + process pipeline in a background thread."""
    from .gdrive_sync import sync_folder
    from .pdf_processor import process_pdf_list
    try:
        _sync_status["running"] = True
        _sync_status["last_result"] = None
        result = sync_folder(GDRIVE_FOLDER_ID, PDFS_DIR)
        # Only process newly downloaded PDFs, not all 3600+
        if result["downloaded"] > 0 and result.get("new_files"):
            process_pdf_list(result["new_files"])
        result.pop("new_files", None)  # Don't include file paths in status
        _sync_status["last_result"] = result
    except Exception as exc:
        _sync_status["last_result"] = {"error": str(exc)}
    finally:
        _sync_status["running"] = False

@app.post("/admin/sync-pdfs")
def sync_pdfs_from_gdrive(body: SyncRequest):
    """Download latest PDFs from the shared Google Drive folder (background)."""
    if not ADMIN_SECRET or body.secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    if _sync_status["running"]:
        return {"status": "already running — check /admin/sync-status"}
    import threading
    t = threading.Thread(target=_run_sync_background, daemon=True)
    t.start()
    return {"status": "sync started in background — check /admin/sync-status for progress"}

@app.post("/admin/sync-status")
def sync_status(body: SyncRequest):
    """Check progress of a background sync."""
    if not ADMIN_SECRET or body.secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    if _sync_status["running"]:
        return {"status": "running"}
    if _sync_status["last_result"] is None:
        return {"status": "no sync has been run yet"}
    return {"status": "complete", "result": _sync_status["last_result"]}


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
        log.warning(f"OTC SOB fallback failed for {pid}: {e}")
    return None


# --- CMS Benefits Endpoints ---

@app.get("/cms/benefits/{plan_number}")
def cms_benefits(plan_number: str):
    """Full plan benefits from CMS data."""
    cms = get_cms()
    result = cms.get_full_benefits(plan_number)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    # OTC fallback: if CMS says plan has OTC but no dollar amount, check SOB text
    otc = result.get("otc", {})
    if otc.get("has_otc") and not otc.get("amount"):
        sob_otc = _otc_from_sob_text(plan_number)
        if sob_otc:
            otc["amount"] = sob_otc["amount"]
            otc["period"] = sob_otc["period"]

    return result


@app.get("/cms/benefits/{plan_number}/medical")
def cms_medical(plan_number: str):
    """PCP, specialist, ER, urgent care copays."""
    cms = get_cms()
    return cms.get_medical_copays(plan_number)


@app.get("/cms/benefits/{plan_number}/dental")
def cms_dental(plan_number: str):
    """Dental preventive + comprehensive benefits."""
    cms = get_cms()
    return cms.get_dental_benefits(plan_number)


@app.get("/cms/benefits/{plan_number}/otc")
def cms_otc(plan_number: str):
    """OTC allowance amount and delivery method."""
    cms = get_cms()
    return cms.get_otc_allowance(plan_number)


@app.get("/cms/benefits/{plan_number}/vision")
def cms_vision(plan_number: str):
    """Eye exam + eyewear vision benefits."""
    cms = get_cms()
    return cms.get_vision_benefits(plan_number)


@app.get("/cms/benefits/{plan_number}/hearing")
def cms_hearing(plan_number: str):
    """Hearing exam + hearing aid benefits."""
    cms = get_cms()
    return cms.get_hearing_benefits(plan_number)


@app.get("/cms/benefits/{plan_number}/flex")
def cms_flex(plan_number: str):
    """Flex card / SSBCI supplemental benefits."""
    cms = get_cms()
    return cms.get_flex_ssbci(plan_number)


@app.get("/cms/benefits/{plan_number}/giveback")
def cms_giveback(plan_number: str):
    """Part B premium giveback amount."""
    cms = get_cms()
    return cms.get_part_b_giveback(plan_number)


@app.post("/cms/drug")
def cms_drug_lookup(req: DrugLookupRequest):
    """Look up drug by name — returns tier, copay, restrictions."""
    cms = get_cms()
    result = cms.get_drug_by_name(req.plan_number, req.drug_name)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/cms/drug/{plan_number}/{drug_name}")
def cms_drug_lookup_get(plan_number: str, drug_name: str):
    """GET version for easy browser testing. Example: /cms/drug/H1036-077/Eliquis"""
    cms = get_cms()
    result = cms.get_drug_by_name(plan_number, drug_name)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
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
def cms_my_drugs_session(session_id: str):
    """Session-based drug lookup — no phone in URL."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    return _my_drugs_impl(session["data"])


@app.get("/cms/my-drugs/{phone}")
def cms_my_drugs(phone: str):
    """
    Pull member's medications from Zoho, look up each in CMS formulary.
    SOB (Summary of Benefits) governs over CMS for tier copays.
    Returns individual drug costs + estimated monthly total.
    """
    # 1. Look up member in Zoho
    try:
        member = search_contact_by_phone(phone)
    except Exception as e:
        log.error(f"Zoho lookup failed in my-drugs: {e}")
        raise HTTPException(status_code=500, detail="Unable to look up your account right now.")

    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    return _my_drugs_impl(member)


def _my_drugs_impl(member: dict):
    """Shared implementation for drug lookup."""
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

    drugs = []
    monthly_total = 0.0

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
        monthly_cost = 0.0
        best_option = f"{actual_days}-day"
        copay_retail = None
        copay_mail = None
        cost_source = "cms"  # track which source we used

        # Try SOB first (SOB governs over CMS)
        sob_cost = None
        if sob_tiers and tier is not None:
            sob_cost = _resolve_sob_cost(sob_tiers, tier, is_mail, actual_days)
        elif sob_tiers and not found_in_formulary:
            # Drug not on formulary — use Tier 4 (Non-Preferred) from SOB as proxy
            # Non-formulary drugs typically cost the non-preferred tier amount
            sob_cost = _resolve_sob_cost(sob_tiers, 4, is_mail, actual_days)
            if sob_cost:
                tier = 4  # Assign non-preferred tier for display
                found_in_formulary = True  # We have a cost to show
                cost_source = "sob-nonformulary"

        if sob_cost and sob_cost.get("type") == "copay" and sob_cost.get("amount") is not None:
            # SOB has a flat dollar copay — use it
            copay_retail = sob_cost["amount"]
            cost_type = "copay"
            cost_source = cost_source if cost_source == "sob-nonformulary" else "sob"

            if is_mail:
                copay_mail = copay_retail
                fill_cost = float(copay_retail)
                months_per_fill = actual_days / 30.0
                monthly_cost = fill_cost / months_per_fill
                best_option = f"{actual_days}-day mail"
            else:
                fill_cost = float(copay_retail)
                months_per_fill = actual_days / 30.0
                monthly_cost = fill_cost / months_per_fill

        elif sob_cost and sob_cost.get("type") == "coinsurance":
            # SOB has percentage — use it, with cap if available
            cost_type = "coinsurance"
            cost_source = cost_source if cost_source == "sob-nonformulary" else "sob"
            copay_retail = sob_cost.get("raw", "N/A")
            if sob_cost.get("cap") is not None:
                # "25% up to $35" → use the cap as the cost
                monthly_cost = float(sob_cost["cap"]) / (actual_days / 30.0)
            else:
                # Pure percentage without cap — can't calculate exact dollar amount
                monthly_cost = 0.0

        elif found_in_formulary and result:
            # SOB not available or no data for this tier — fall back to CMS
            cost_source = "cms"
            copay_retail = result.get("copay_preferred") or result.get("copay_30day_preferred")
            copay_mail = result.get("copay_mail") or result.get("copay_90day_mail")
            cost_type_retail = result.get("cost_type", result.get("cost_type_30day", "copay"))
            cost_type_mail = result.get("cost_type_90day", "copay")
            cost_max = result.get("cost_max_30day")

            if is_mail and copay_mail is not None and isinstance(copay_mail, (int, float)):
                fill_cost = float(copay_mail)
                months_per_fill = actual_days / 30.0
                monthly_cost = fill_cost / months_per_fill
                cost_type = cost_type_mail
                best_option = f"{actual_days}-day mail"
            elif cost_type_retail == "copay" and isinstance(copay_retail, (int, float)):
                fill_cost = float(copay_retail)
                months_per_fill = actual_days / 30.0
                monthly_cost = fill_cost / months_per_fill
                cost_type = cost_type_retail
            elif cost_type_retail == "coinsurance":
                cost_type = "coinsurance"
                if cost_max is not None and cost_max > 0:
                    monthly_cost = float(cost_max) / (actual_days / 30.0)
                else:
                    monthly_cost = 0.0

        # IRA insulin cap: $35/month (or SOB insulin_cap) is the MAX, not a minimum
        if is_insulin and monthly_cost > float(sob_insulin_cap):
            monthly_cost = float(sob_insulin_cap)

        # Build display string
        if found_in_formulary or cost_source == "sob-nonformulary":
            if cost_type == "coinsurance" and not is_insulin and sob_cost and sob_cost.get("cap") is None:
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
                "is_insulin": is_insulin,
                "monthly_cost": round(monthly_cost, 2),
                "best_option": best_option,
                "copay_display": copay_display,
                "prior_auth": result.get("prior_auth", False) if result and "error" not in result else False,
                "step_therapy": result.get("step_therapy", False) if result and "error" not in result else False,
                "quantity_limit": result.get("quantity_limit", False) if result and "error" not in result else False,
                "deductible_applies": result.get("deductible_applies", False) if result and "error" not in result else False,
                "found": True,
                "cost_source": cost_source,
            })
            monthly_total += monthly_cost
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

    return {
        "plan_number": plan_number,
        "medications": drugs,
        "monthly_total": monthly_total,
        "monthly_display": "$" + str(int(monthly_total)),
        "has_medications": True,
        "cost_source": "sob" if sob_source else "cms",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MEDICATION REMINDERS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/reminders/{session_id}")
def list_reminders(session_id: str):
    """List all medication reminders for this member."""
    phone = _session_phone(session_id)
    db = get_user_db()
    return {"reminders": db.get_reminders(phone)}


@app.post("/reminders/{session_id}")
def create_reminder(session_id: str, req: ReminderCreate):
    """Create a single medication reminder."""
    phone = _session_phone(session_id)
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
    return {"reminder": reminder}


@app.post("/reminders/{session_id}/bulk")
def create_reminders_bulk(session_id: str, req: BulkReminderCreate):
    """Create multiple reminders at once (agent onboarding)."""
    phone = _session_phone(session_id)
    db = get_user_db()
    reminders = db.create_reminders_bulk(
        phone=phone,
        reminders=[r.model_dump() for r in req.reminders],
        created_by=req.created_by,
    )
    return {"reminders": reminders, "count": len(reminders)}


@app.put("/reminders/{session_id}/{reminder_id}")
def update_reminder(session_id: str, reminder_id: int, req: ReminderUpdate):
    """Update a reminder (toggle, reschedule, etc.)."""
    phone = _session_phone(session_id)
    db = get_user_db()
    reminder = db.update_reminder(phone, reminder_id, **req.model_dump(exclude_none=True))
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"reminder": reminder}


@app.delete("/reminders/{session_id}/{reminder_id}")
def delete_reminder(session_id: str, reminder_id: int):
    """Delete a medication reminder."""
    phone = _session_phone(session_id)
    db = get_user_db()
    deleted = db.delete_reminder(phone, reminder_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"deleted": True}


# ═══════════════════════════════════════════════════════════════════════════════
# BENEFITS USAGE TRACKING
# ═══════════════════════════════════════════════════════════════════════════════

VALID_USAGE_CATEGORIES = {"otc", "dental", "flex", "vision", "hearing"}


@app.post("/usage/{session_id}")
def log_usage(session_id: str, req: UsageCreate):
    """Log a benefits usage entry (e.g. OTC purchase, dental visit)."""
    phone = _session_phone(session_id)
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
    return {"usage": entry}


@app.get("/usage/{session_id}")
def get_usage(session_id: str, category: Optional[str] = None):
    """Get all usage entries for this member, optionally filtered by category."""
    phone = _session_phone(session_id)
    db = get_user_db()
    entries = db.get_usage(phone, category)
    return {"usage": entries}


@app.delete("/usage/{session_id}/{usage_id}")
def delete_usage(session_id: str, usage_id: int):
    """Delete a usage entry (undo mistake)."""
    phone = _session_phone(session_id)
    db = get_user_db()
    deleted = db.delete_usage(phone, usage_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Usage entry not found")
    return {"deleted": True}


@app.get("/usage/{session_id}/summary")
def usage_summary(session_id: str):
    """
    Get per-category spending summary: spent vs. cap for current period.
    Cross-references CMS benefit caps with logged usage.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    session["ts"] = time.time()

    phone = session["phone"]
    plan_number = session["data"].get("plan_number", "")
    if not plan_number:
        return {"summary": []}

    db = get_user_db()
    cms = get_cms()

    # Gather benefit caps from CMS
    categories = []

    # OTC
    try:
        otc = cms.get_otc_allowance(*_split_plan(plan_number))
        if otc and otc.get("has_otc") and otc.get("amount"):
            amt = otc["amount"]
            # amount may be string with $ — normalize to float
            if isinstance(amt, str):
                amt = float(amt.replace("$", "").replace(",", "").strip())
            period = otc.get("period", "Monthly")
            categories.append({"category": "otc", "cap": amt, "period": period, "label": "OTC Allowance"})
    except Exception:
        pass

    # Dental
    try:
        dental = cms.get_dental_benefits(*_split_plan(plan_number))
        if dental and dental.get("has_preventive"):
            prev = dental.get("preventive", {})
            max_ben = prev.get("max_benefit")
            if max_ben:
                cap = float(str(max_ben).replace("$", "").replace(",", ""))
                categories.append({"category": "dental", "cap": cap, "period": "Yearly", "label": "Dental"})
    except Exception:
        pass

    # Flex / SSBCI
    try:
        flex = cms.get_flex_ssbci(*_split_plan(plan_number))
        if flex and flex.get("has_ssbci") and flex.get("benefits"):
            total = sum(b.get("max_amount", 0) for b in flex["benefits"] if b.get("max_amount"))
            if total > 0:
                categories.append({"category": "flex", "cap": total, "period": "Yearly", "label": "Flex Card"})
    except Exception:
        pass

    # Vision
    try:
        vision = cms.get_vision_benefits(*_split_plan(plan_number))
        if vision and vision.get("has_exams"):
            exams = vision.get("exams", {})
            max_amt = exams.get("max_benefit")
            if max_amt:
                cap = float(str(max_amt).replace("$", "").replace(",", ""))
                categories.append({"category": "vision", "cap": cap, "period": "Yearly", "label": "Vision"})
    except Exception:
        pass

    # Hearing
    try:
        hearing = cms.get_hearing_benefits(*_split_plan(plan_number))
        if hearing and hearing.get("has_aids"):
            aids = hearing.get("aids", {})
            max_amt = aids.get("max_benefit")
            if max_amt:
                cap = float(str(max_amt).replace("$", "").replace(",", ""))
                categories.append({"category": "hearing", "cap": cap, "period": "Yearly", "label": "Hearing"})
    except Exception:
        pass

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


def _split_plan(plan_number: str) -> tuple[str, str]:
    """Split 'H1234-567' or 'H1234-567-000' into (contract_id, plan_id)."""
    pid = normalize_plan_id(plan_number)
    parts = pid.split("-")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return pid, ""


# ═══════════════════════════════════════════════════════════════════════════════
# DIGITAL ID CARD
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/cms/id-card/{plan_number}")
def get_id_card_data(plan_number: str):
    """Return all data needed to render a digital insurance ID card."""
    from .carrier_config import detect_carrier, get_carrier_config

    cms = get_cms()
    overview = cms.get_plan_overview(plan_number)
    if not overview:
        raise HTTPException(status_code=404, detail=f"Plan {plan_number} not found")

    medical = cms.get_medical_copays(plan_number)

    carrier_key = detect_carrier(
        overview.get("plan_name", ""),
        overview.get("org_name", ""),
    )
    rx = get_carrier_config(carrier_key) if carrier_key else {}

    return {
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

