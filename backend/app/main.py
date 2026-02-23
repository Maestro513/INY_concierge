"""
InsuranceNYou Backend API
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from .claude_client import ask_claude, load_plan_chunks, find_relevant_chunks
from .zoho_client import search_contact_by_phone
from .providers.service import search_providers

import json
import os
import re
import logging
import time
import anthropic
from .config import ANTHROPIC_API_KEY, EXTRACTED_DIR, PDFS_DIR
import glob

log = logging.getLogger(__name__)

app = FastAPI(title="InsuranceNYou API", version="0.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache for parsed SOB summaries: {plan_id: {"data": {...}, "ts": float}}
_sob_cache: dict[str, dict] = {}
SOB_CACHE_TTL = 3600  # 1 hour

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


def normalize_plan_id(plan_id: str) -> str:
    """
    H1234-567-000 → H1234-567
    Zoho stores the full 3-segment ID but SOB files are keyed by 2 segments.
    """
    pid = plan_id.strip()
    if pid.endswith("-000"):
        pid = pid[:-4]
    return pid


def parse_medications(raw: str) -> list[str]:
    """
    Parse medications from a multi-line or comma-separated string.
    Handles: 'Eliquis, Metformin, Jardiance'
         or: 'Eliquis\nMetformin\nJardiance'
         or: 'Eliquis, Metformin\nJardiance, Lisinopril'
    """
    if not raw or not raw.strip():
        return []
    parts = re.split(r'[,\n]+', raw)
    meds = []
    for part in parts:
        name = part.strip()
        if name and len(name) > 1:
            meds.append(name)
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
    phone: str = ""
    medications: str = ""
    zip_code: str = ""

class ProviderSearchRequest(BaseModel):
    plan_name: str
    specialty: str
    zip_code: str
    radius_miles: float = 25.0
    limit: int = 200
    enrich_google: bool = True

class SOBRequest(BaseModel):
    plan_number: str

class DrugLookupRequest(BaseModel):
    plan_number: str
    drug_name: str


# --- Endpoints ---

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/lookup", response_model=LookupResponse)
def lookup_member(req: LookupRequest):
    """Look up a member by phone number in Zoho CRM."""
    try:
        member = search_contact_by_phone(req.phone)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Zoho error: {str(e)}")

    if member is None:
        return LookupResponse(found=False)

    return LookupResponse(
        found=True,
        first_name=member["first_name"],
        last_name=member["last_name"],
        plan_name=member["plan_name"],
        plan_number=member["plan_number"],
        agent=member["agent"] or "",
        phone=member["phone"] or member["mobile"],
        medications=member.get("medications", "") or "",
        zip_code=member.get("zip_code", "") or "",
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

    # Send ALL chunks — drug tiers, dental, vision, hearing, mental health,
    # OTC, etc. are often in the latter half of the document
    context = "\n\n---\n\n".join(chunks)

    # Ask Claude to extract structured benefits
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
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

    # Cache it with timestamp
    _sob_cache[plan_id] = {"data": result, "ts": time.time()}
    return result


# --- SOB PDF Download ---

@app.get("/sob/pdf/{plan_number}")
def get_sob_pdf(plan_number: str):
    """Serve the original SOB PDF file for download."""
    plan_id = normalize_plan_id(plan_number)

    # Build multiple search patterns to handle different filename conventions:
    #   H0028-007  →  H0028_007  (underscore)   e.g. H0028_007_SB.pdf
    #   H7617-107  →  H7617107   (no separator)  e.g. H7617107000SB26.PDF
    #   H7617-107  →  H7617-107  (dash kept)     e.g. H7617-107.PDF
    underscore = plan_id.replace("-", "_")
    nosep = plan_id.replace("-", "")
    patterns = [
        f"*{underscore}*SB*.[pP][dD][fF]",
        f"*{nosep}*SB*.[pP][dD][fF]",
        f"*{plan_id}*SB*.[pP][dD][fF]",
        f"*{underscore}*.[pP][dD][fF]",
        f"*{nosep}*.[pP][dD][fF]",
        f"*{plan_id}*.[pP][dD][fF]",
    ]

    matches = []
    for pat in patterns:
        matches = glob.glob(os.path.join(PDFS_DIR, "**", pat), recursive=True)
        if matches:
            break

    if not matches:
        raise HTTPException(status_code=404, detail=f"No PDF found for plan {plan_id}")

    return FileResponse(
        matches[0],
        media_type="application/pdf",
        filename=f"SOB_{plan_id}.pdf",
    )


# --- CMS Benefits Endpoints ---

@app.get("/cms/benefits/{plan_number}")
def cms_benefits(plan_number: str):
    """Full plan benefits from CMS data."""
    cms = get_cms()
    result = cms.get_full_benefits(plan_number)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
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


@app.get("/cms/my-drugs/{phone}")
def cms_my_drugs(phone: str):
    """
    Pull member's medications from Zoho, look up each in CMS formulary.
    Returns individual drug costs + estimated monthly total.
    """
    # 1. Look up member in Zoho
    try:
        member = search_contact_by_phone(phone)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Zoho error: {str(e)}")

    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    plan_number = member.get("plan_number", "")
    if not plan_number:
        raise HTTPException(status_code=400, detail="Member has no plan number")

    # 2. Parse medications
    raw_meds = member.get("medications", "") or ""
    med_names = parse_medications(raw_meds)

    if not med_names:
        return {
            "plan_number": plan_number,
            "medications": [],
            "monthly_total": 0,
            "monthly_display": "$0",
            "has_medications": False,
        }

    # 3. Look up each drug in CMS
    cms = get_cms()
    drugs = []
    monthly_total = 0.0

    for name in med_names:
        result = cms.get_drug_by_name(plan_number, name)
        if result and "error" not in result:
            # Determine cost type and handle coinsurance vs copay
            cost_type_30 = result.get("cost_type_30day", "copay")
            cost_type_90 = result.get("cost_type_90day", "copay")
            is_insulin = result.get("is_insulin", False)

            copay_30 = result.get("copay_30day_preferred")
            copay_90 = result.get("copay_90day_mail")
            cost_max_30 = result.get("cost_max_30day")
            cost_max_90 = result.get("cost_max_90day")

            # Calculate 30-day monthly cost
            if cost_type_30 == "copay" and isinstance(copay_30, (int, float)):
                cost_30 = float(copay_30)
            elif cost_type_30 == "coinsurance":
                # For coinsurance: use cap if available, or IRA $35 for insulin
                if is_insulin:
                    cost_30 = 35.0  # IRA insulin cap per fill
                elif cost_max_30 is not None and cost_max_30 > 0:
                    cost_30 = float(cost_max_30)
                else:
                    cost_30 = None  # Can't calculate without drug price
            else:
                cost_30 = None

            # Calculate 90-day monthly cost (÷ 3)
            if cost_type_90 == "copay" and isinstance(copay_90, (int, float)) and copay_90 > 0:
                cost_90_monthly = float(copay_90) / 3.0
            elif cost_type_90 == "coinsurance":
                if is_insulin:
                    cost_90_monthly = 35.0 / 3.0  # ~$11.67/mo for 90-day insulin
                elif cost_max_90 is not None and cost_max_90 > 0:
                    cost_90_monthly = float(cost_max_90) / 3.0
                else:
                    cost_90_monthly = None
            else:
                cost_90_monthly = None

            # Pick the best option
            if cost_30 is not None and cost_90_monthly is not None:
                if cost_90_monthly < cost_30:
                    monthly_cost = cost_90_monthly
                    best_option = "90-day mail"
                else:
                    monthly_cost = cost_30
                    best_option = "30-day retail"
            elif cost_30 is not None:
                monthly_cost = cost_30
                best_option = "30-day retail"
            elif cost_90_monthly is not None:
                monthly_cost = cost_90_monthly
                best_option = "90-day mail"
            else:
                monthly_cost = 0.0
                best_option = "unknown"

            # Build display string
            if cost_type_30 == "coinsurance" and not is_insulin and cost_max_30 is None:
                copay_display = str(copay_30 or "N/A")  # Show "25%" as-is
            else:
                copay_display = "$" + str(int(round(monthly_cost)))

            drugs.append({
                "drug_name": name,
                "tier": result.get("tier"),
                "tier_label": result.get("tier_label", ""),
                "copay_30day": copay_30,
                "copay_90day_mail": copay_90,
                "cost_type": cost_type_30,
                "is_insulin": is_insulin,
                "monthly_cost": round(monthly_cost, 2),
                "best_option": best_option,
                "copay_display": copay_display,
                "prior_auth": result.get("prior_auth", False),
                "step_therapy": result.get("step_therapy", False),
                "quantity_limit": result.get("quantity_limit", False),
                "deductible_applies": result.get("deductible_applies", False),
                "found": True,
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
            })

    return {
        "plan_number": plan_number,
        "medications": drugs,
        "monthly_total": monthly_total,
        "monthly_display": "$" + str(int(monthly_total)),
        "has_medications": True,
    }