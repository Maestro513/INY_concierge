import logging
import os
import random
import string
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .data import (
    SAMPLE_MEMBER, SAMPLE_BENEFITS, EXTRA_BENEFITS, SAMPLE_SOB,
    SAMPLE_DOCTORS, SAMPLE_MEDICATIONS, SAMPLE_PHARMACIES,
    QUICK_QUESTIONS, SAMPLE_ANSWERS, CALL_NUMBER, otp_store,
)
from . import zoho

# ── Load .env ──────────────────────────────────────────────────────
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="INY Concierge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store: phone -> zoho contact_id (populated on login)
member_store: dict[str, dict] = {}


# ── Health ──────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Zoho Status ────────────────────────────────────────────────────

@app.on_event("shutdown")
async def shutdown_event():
    await zoho.close_http_client()

@app.get("/api/zoho/status")
async def zoho_status():
    return await zoho.test_connection()


# ── Auth ────────────────────────────────────────────────────────────

class SendOTPRequest(BaseModel):
    phone: str

class VerifyOTPRequest(BaseModel):
    phone: str
    code: str

@app.post("/api/auth/send-otp")
def send_otp(body: SendOTPRequest):
    digits = body.phone.replace("-", "").replace("(", "").replace(")", "").replace(" ", "")
    if len(digits) != 10 or not digits.isdigit():
        raise HTTPException(status_code=400, detail="Invalid phone number")
    code = "".join(random.choices(string.digits, k=6))
    otp_store[digits] = code
    # In production: send via Twilio / SNS
    print(f"[OTP] {digits} -> {code}")
    return {"success": True, "message": "OTP sent"}

@app.post("/api/auth/verify-otp")
async def verify_otp(body: VerifyOTPRequest):
    digits = body.phone.replace("-", "").replace("(", "").replace(")", "").replace(" ", "")
    stored = otp_store.get(digits)
    if not stored:
        raise HTTPException(status_code=400, detail="No OTP found. Request a new one.")
    if stored != body.code:
        raise HTTPException(status_code=401, detail="Invalid code")
    del otp_store[digits]

    # Look up the member in Zoho by phone
    if zoho.zoho_enabled():
        try:
            contact = await zoho.search_contact_by_phone(digits)
            if contact:
                contact_id = contact.get("id")
                member_store[digits] = {
                    "contact_id": contact_id,
                    "contact": contact,
                }
                logger.info(f"Zoho member found for {digits}: {contact.get('First_Name')} {contact.get('Last_Name')}")
        except Exception as e:
            logger.error(f"Zoho lookup failed for {digits}: {e}")

    return {"success": True, "token": "demo-jwt-token"}


# ── Member ──────────────────────────────────────────────────────────

@app.get("/api/member/profile")
async def get_profile(phone: str = ""):
    digits = phone.replace("-", "").replace("(", "").replace(")", "").replace(" ", "") if phone else ""

    # Try Zoho first
    if zoho.zoho_enabled() and digits and digits in member_store:
        try:
            contact = member_store[digits].get("contact")
            contact_id = member_store[digits].get("contact_id")
            if contact:
                member = zoho._extract_member_from_contact(contact)
                benefits = zoho._extract_benefits_from_contact(contact)
                extras = zoho._extract_extra_benefits_from_contact(contact)
                return {
                    "member": member,
                    "benefits": benefits,
                    "extraBenefits": extras,
                    "callNumber": CALL_NUMBER,
                }
        except Exception as e:
            logger.error(f"Zoho profile fetch failed: {e}")

    # Fallback to sample data
    return {
        "member": SAMPLE_MEMBER,
        "benefits": SAMPLE_BENEFITS,
        "extraBenefits": EXTRA_BENEFITS,
        "callNumber": CALL_NUMBER,
    }

@app.get("/api/member/benefits")
async def get_benefits(phone: str = ""):
    digits = phone.replace("-", "").replace("(", "").replace(")", "").replace(" ", "") if phone else ""

    # Try Zoho first
    if zoho.zoho_enabled() and digits and digits in member_store:
        try:
            contact_id = member_store[digits].get("contact_id")
            if contact_id:
                sob = await zoho.get_member_benefits_by_contact(contact_id)
                if sob:
                    return {"sob": sob}
        except Exception as e:
            logger.error(f"Zoho benefits fetch failed: {e}")

    # Fallback to sample data
    return {"sob": SAMPLE_SOB}


# ── Doctors ─────────────────────────────────────────────────────────

@app.get("/api/doctors")
def get_doctors(query: str = ""):
    if not query:
        return {"doctors": SAMPLE_DOCTORS}
    q = query.lower()
    filtered = [d for d in SAMPLE_DOCTORS if q in d["name"].lower() or q in d["specialty"].lower()]
    return {"doctors": filtered}


# ── Medications ─────────────────────────────────────────────────────

@app.get("/api/medications")
def get_medications():
    return {"medications": SAMPLE_MEDICATIONS}


# ── Pharmacies ──────────────────────────────────────────────────────

@app.get("/api/pharmacies")
def get_pharmacies():
    return {"pharmacies": SAMPLE_PHARMACIES}


# ── Ask (Q&A) ──────────────────────────────────────────────────────

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
