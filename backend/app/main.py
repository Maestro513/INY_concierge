"""
INY Concierge API  --  FastAPI backend.

Serves member profiles, benefits, doctors, medications, pharmacies, and Q&A.
When Zoho CRM credentials are configured the member/benefits endpoints pull
live data; otherwise they fall back to the hardcoded sample data in data.py.
"""

import logging
import random
import string
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .data import (
    SAMPLE_MEMBER, SAMPLE_BENEFITS, EXTRA_BENEFITS, SAMPLE_SOB,
    SAMPLE_DOCTORS, SAMPLE_MEDICATIONS, SAMPLE_PHARMACIES,
    QUICK_QUESTIONS, SAMPLE_ANSWERS, CALL_NUMBER, otp_store,
)
from . import zoho

# ── Load .env (before anything reads os.getenv) ────────────────────
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# ── Logging ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("iny_concierge")


# ── Lifespan (startup / shutdown) ──────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if zoho.zoho_enabled():
        logger.info("Zoho CRM credentials detected -- live data enabled.")
    else:
        logger.info("Zoho CRM credentials NOT configured -- using sample data.")
    yield
    # Shutdown
    await zoho.close_http_client()
    logger.info("Zoho HTTP client closed.")


# ── App ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="INY Concierge API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── In-memory session store ────────────────────────────────────────
# Maps a phone-digits string to the Zoho contact data fetched at login.
# In production this would be a Redis/DB-backed session or a JWT claim.
_member_cache: dict[str, dict] = {}


# ── Helpers ─────────────────────────────────────────────────────────

def _strip_phone(raw: str) -> str:
    """Normalise a phone string to bare digits."""
    return raw.replace("-", "").replace("(", "").replace(")", "").replace(" ", "").replace("+", "")


def _zoho_ok() -> bool:
    """Shorthand check for whether Zoho integration is active."""
    return zoho.zoho_enabled()


# ====================================================================
#  HEALTH
# ====================================================================

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ====================================================================
#  ZOHO STATUS
# ====================================================================

@app.get("/api/zoho/status")
async def zoho_status():
    """Report whether Zoho CRM is configured and reachable.

    Response shape::

        {
          "configured": bool,
          "connected":  bool,
          "message":    str,
          "orgName":    str | undefined,
          "orgId":      str | undefined,
        }
    """
    return await zoho.test_connection()


# ====================================================================
#  AUTH
# ====================================================================

class SendOTPRequest(BaseModel):
    phone: str


class VerifyOTPRequest(BaseModel):
    phone: str
    code: str


@app.post("/api/auth/send-otp")
def send_otp(body: SendOTPRequest):
    digits = _strip_phone(body.phone)
    # Accept 10-digit US numbers or 11-digit with leading 1
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or not digits.isdigit():
        raise HTTPException(status_code=400, detail="Invalid phone number")

    code = "".join(random.choices(string.digits, k=6))
    otp_store[digits] = code
    # In production: send via Twilio / SNS
    logger.info("[OTP] %s -> %s", digits, code)
    return {"success": True, "message": "OTP sent"}


@app.post("/api/auth/verify-otp")
async def verify_otp(body: VerifyOTPRequest):
    digits = _strip_phone(body.phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    stored = otp_store.get(digits)
    if not stored:
        raise HTTPException(status_code=400, detail="No OTP found. Request a new one.")
    if stored != body.code:
        raise HTTPException(status_code=401, detail="Invalid code")
    del otp_store[digits]

    # ------------------------------------------------------------------
    # Zoho lookup: resolve the phone number to a CRM Contact so that
    # subsequent /api/member/* calls can serve live data.
    # ------------------------------------------------------------------
    zoho_contact: Optional[dict] = None
    zoho_contact_id: Optional[str] = None

    if _zoho_ok():
        try:
            contact = await zoho.search_contact_by_phone(digits)
            if contact:
                zoho_contact = contact
                zoho_contact_id = contact.get("id")
                _member_cache[digits] = {
                    "contact_id": zoho_contact_id,
                    "contact": zoho_contact,
                }
                logger.info(
                    "Zoho member found for %s: %s %s (id=%s)",
                    digits,
                    contact.get("First_Name", ""),
                    contact.get("Last_Name", ""),
                    zoho_contact_id,
                )
            else:
                logger.info("No Zoho contact for phone %s -- will use sample data.", digits)
        except Exception:
            logger.exception("Zoho lookup failed during OTP verify for %s", digits)

    return {
        "success": True,
        "token": "demo-jwt-token",
        "zohoMember": zoho_contact_id is not None,
    }


# ====================================================================
#  MEMBER  -- profile & benefits
# ====================================================================

@app.get("/api/member/profile")
async def get_profile(phone: str = Query(default="")):
    """Return the member profile, benefit tiles, and extra benefits.

    When ``phone`` is provided and a matching Zoho contact was cached at
    login, live CRM data is returned.  Otherwise the hardcoded sample
    data is served.
    """
    digits = _strip_phone(phone) if phone else ""
    if digits and len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    # --- Try Zoho first ---------------------------------------------------
    if _zoho_ok() and digits and digits in _member_cache:
        try:
            cached = _member_cache[digits]
            contact = cached.get("contact")
            if contact:
                member = zoho._extract_member_from_contact(contact)
                benefits = zoho._extract_benefits_from_contact(contact)
                extra = zoho._extract_extra_benefits_from_contact(contact)

                # Only use Zoho data if the contact had meaningful fields.
                # If the CRM record is sparse we fall through to sample data.
                if member.get("firstName") or member.get("lastName"):
                    # Fill empty benefit values with sample-data defaults so
                    # the UI always has something to show.
                    if not zoho._has_any_value(benefits):
                        benefits = SAMPLE_BENEFITS
                    if not zoho._has_any_value(extra):
                        extra = EXTRA_BENEFITS

                    return {
                        "member": member,
                        "benefits": benefits,
                        "extraBenefits": extra,
                        "callNumber": CALL_NUMBER,
                        "source": "zoho",
                    }
        except Exception:
            logger.exception("Zoho profile fetch failed for %s", digits)

    # --- Fallback to sample data ------------------------------------------
    return {
        "member": SAMPLE_MEMBER,
        "benefits": SAMPLE_BENEFITS,
        "extraBenefits": EXTRA_BENEFITS,
        "callNumber": CALL_NUMBER,
        "source": "sample",
    }


@app.get("/api/member/benefits")
async def get_benefits(phone: str = Query(default="")):
    """Return the Schedule of Benefits (medical + drug tiers).

    Tries Zoho first (via the contact's related Benefits records or
    plan-level lookup), then falls back to sample SOB data.
    """
    digits = _strip_phone(phone) if phone else ""
    if digits and len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    # --- Try Zoho ---------------------------------------------------------
    if _zoho_ok() and digits and digits in _member_cache:
        try:
            cached = _member_cache[digits]
            contact_id = cached.get("contact_id")
            contact = cached.get("contact")

            sob: Optional[dict] = None

            # Strategy 1 -- look up by contact_id related Benefits
            if contact_id:
                sob = await zoho.get_member_benefits_by_contact(contact_id)

            # Strategy 2 -- look up by plan_id
            if not sob and contact:
                plan_id = (
                    contact.get("Plan_ID")
                    or contact.get("Plan_Id")
                    or contact.get("Contract_ID")
                    or ""
                )
                if plan_id:
                    sob = await zoho.get_member_benefits(plan_id)

            if sob:
                return {"sob": sob, "source": "zoho"}
        except Exception:
            logger.exception("Zoho benefits fetch failed for %s", digits)

    # --- Fallback ---------------------------------------------------------
    return {"sob": SAMPLE_SOB, "source": "sample"}


# ====================================================================
#  DOCTORS
# ====================================================================

@app.get("/api/doctors")
def get_doctors(query: str = ""):
    if not query:
        return {"doctors": SAMPLE_DOCTORS}
    q = query.lower()
    filtered = [
        d for d in SAMPLE_DOCTORS
        if q in d["name"].lower() or q in d["specialty"].lower()
    ]
    return {"doctors": filtered}


# ====================================================================
#  MEDICATIONS
# ====================================================================

@app.get("/api/medications")
def get_medications():
    return {"medications": SAMPLE_MEDICATIONS}


# ====================================================================
#  PHARMACIES
# ====================================================================

@app.get("/api/pharmacies")
def get_pharmacies():
    return {"pharmacies": SAMPLE_PHARMACIES}


# ====================================================================
#  ASK  (Q&A)
# ====================================================================

class AskRequest(BaseModel):
    question: str


@app.post("/api/ask")
def ask_question(body: AskRequest):
    q = body.question.strip()
    # Exact match first
    if q in SAMPLE_ANSWERS:
        return {"answer": SAMPLE_ANSWERS[q]}
    # Fuzzy keyword match
    q_lower = q.lower()
    for key, answer in SAMPLE_ANSWERS.items():
        if any(word in q_lower for word in key.lower().split()):
            return {"answer": answer}
    return {"answer": "I'm not sure about that. Please call us for help."}


@app.get("/api/ask/suggestions")
def ask_suggestions():
    return {"questions": QUICK_QUESTIONS}
