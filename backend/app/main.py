import random
import string
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .data import (
    SAMPLE_MEMBER, SAMPLE_BENEFITS, EXTRA_BENEFITS, SAMPLE_SOB,
    SAMPLE_DOCTORS, SAMPLE_MEDICATIONS, SAMPLE_PHARMACIES,
    QUICK_QUESTIONS, SAMPLE_ANSWERS, CALL_NUMBER, otp_store,
)

app = FastAPI(title="INY Concierge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ──────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


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
def verify_otp(body: VerifyOTPRequest):
    digits = body.phone.replace("-", "").replace("(", "").replace(")", "").replace(" ", "")
    stored = otp_store.get(digits)
    if not stored:
        raise HTTPException(status_code=400, detail="No OTP found. Request a new one.")
    if stored != body.code:
        raise HTTPException(status_code=401, detail="Invalid code")
    del otp_store[digits]
    return {"success": True, "token": "demo-jwt-token"}


# ── Member ──────────────────────────────────────────────────────────

@app.get("/api/member/profile")
def get_profile():
    return {
        "member": SAMPLE_MEMBER,
        "benefits": SAMPLE_BENEFITS,
        "extraBenefits": EXTRA_BENEFITS,
        "callNumber": CALL_NUMBER,
    }

@app.get("/api/member/benefits")
def get_benefits():
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
