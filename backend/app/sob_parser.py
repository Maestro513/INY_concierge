"""
SOB Text Parser v2 — deterministic extraction of benefits from SOB chunk text.

Fixes from v1:
- Expanded section boundaries to prevent bleed-over (SKILLED NURSING, DOCTOR VISITS, etc.)
- PCP/Specialist/Emergency use direct cost-near-label search instead of rigid patterns
- Drug tier windows truncated at next Tier label
- Dental/Hearing/Ambulance use targeted extraction
"""

import json
import os
import re

# Try relative import for production, fallback for standalone test
try:
    from .config import EXTRACTED_DIR
except ImportError:
    EXTRACTED_DIR = "."


def normalize_plan_id(plan_id: str) -> str:
    pid = plan_id.strip()
    if pid.endswith("-000"):
        pid = pid[:-4]
    return pid


def load_plan_text(plan_id: str) -> str | None:
    pid = normalize_plan_id(plan_id)
    # Try normalized name first, then with -000 suffix (some carriers use it)
    for candidate in [f"{pid}.json", f"{pid}-000.json"]:
        path = os.path.join(EXTRACTED_DIR, candidate)
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
            return "\n\n".join(data["chunks"])
    return None


# ─── Section boundary detection ───
SECTION_BOUNDARY = re.compile(
    r'\n(?:'
    r'(?:PCP|Specialist|Preventive|Emergency|Urgent|Inpatient|Outpatient|Ambulatory|'
    r'Lab|Diagnostic|Hearing|Dental|Vision|Routine|SNF|Skilled|Physical|Occupational|'
    r'Ambulance|Home|Acupuncture|Chiropractic|Foot|Podiatry|Telehealth|Mental|'
    r'Medicare Part|Tier\s+\d|Contacts|Prosthetics|Durable|Substance|'
    r'24[\u2011\-]Hour|Resources|Fitness|Alternative|Diabetic|Other covered|'
    r'Doctor|DOCTOR|Surgery|SURGERY|Transportation|TRANSPORTATION|'
    r'CATASTROPHIC|Catastrophic|Initial|INITIAL|Prescription|'
    r'PLAN\s+COSTS|PLAN\s+HIGHLIGHTS|Plan\s+costs|'
    r'REHABILITATION|Rehabilitation|Cardiac|Pulmonary|Speech|'
    r'MEDICAL\s+EQUIPMENT|Medical\s+equipment|'
    r'Additional\s+Benefits|More\s+benefits|EXTRA\s+HELP|Extra\s+Help)\b'
    r'|Benefit\s*\n'
    r'|Your costs'
    r')',
    re.IGNORECASE
)


# ─── Cost extraction helpers ───

def extract_cost_from_window(window: str) -> str | None:
    simple_copay = re.search(
        r'\$[\d,]+(?:\.\d+)?(?=\s*(?:copay|copayment|per\s+stay|per\s+trip|\n|$|[,;]))',
        window, re.IGNORECASE
    )

    per_day_full = re.search(
        r'\$([\d,]+)\s+(?:copay\s+)?per\s+day[,;]?\s*(?:for\s+)?days?\s*(\d+[\u2011\-\u2013]\d+)'
        r'(?:[;,]\s*\$([\d,]+)\s+(?:copay\s+)?per\s+day[,;]?\s*(?:for\s+)?days?\s*(\d+[\u2011\-\u2013]\d+))?',
        window, re.IGNORECASE
    )

    days_first = re.search(
        r'Days?\s*(\d+)\s*[\u2011\-\u2013]\s*(\d+)\s*\n\s*\$([\d,]+)\s+copay\s+per\s+day'
        r'(?:\s*\n\s*Days?\s*(\d+)\s*\+?\s*\n\s*\$([\d,]+)\s+copay\s+per\s+day)?',
        window, re.IGNORECASE
    )

    if per_day_full:
        g = per_day_full.groups()
        d1 = g[1].replace('\u2011', '-').replace('\u2013', '-')
        result = f"${g[0]}/day days {d1}"
        if g[2] and g[3]:
            d2 = g[3].replace('\u2011', '-').replace('\u2013', '-')
            result += f", ${g[2]}/day days {d2}"
        return result

    if days_first:
        g = days_first.groups()
        result = f"${g[2]}/day days {g[0]}-{g[1]}"
        if g[3] and g[4]:
            result += f", ${g[4]}/day day {g[3]}+"
        return result

    if simple_copay:
        return simple_copay.group(0)

    plain = re.search(r'\$[\d,]+(?:\.\d+)?', window)
    if plain:
        return plain.group(0)

    pct = re.search(r'(\d+)%(?:\s*[\u2011\-\u2013]\s*(\d+)%)?', window)
    if pct:
        if pct.group(2):
            return f"{pct.group(1)}%-{pct.group(2)}%"
        return f"{pct.group(1)}%"

    return None


def find_cost(text: str, label_pattern: str, max_window: int = 400) -> str | None:
    match = re.search(label_pattern, text, re.IGNORECASE)
    if not match:
        return None
    start = match.end()
    window = text[start:start + max_window]
    boundary = SECTION_BOUNDARY.search(window)
    if boundary:
        window = window[:boundary.start()]
    return extract_cost_from_window(window)


# ─── Plan metadata extraction ───

def extract_plan_meta(text: str) -> dict:
    meta = {}

    type_match = re.search(r'\b(HMO[\u2011\-]?POS|HMO|PPO|PFFS|MSA)\b', text, re.IGNORECASE)
    if type_match:
        meta['plan_type'] = type_match.group(1).upper().replace('\u2011', '-')

    name_match = re.search(
        r'((?:Humana|Aetna|UHC|UnitedHealthcare|Devoted|Wellcare|Zing|Healthspring|'
        r'AARP|Cigna|CareOne|CarePlus|DEVOTED)\s+.+?(?:HMO[\u2011\-]?POS|HMO|PPO|PFFS|SNP)[^\n]*)',
        text, re.IGNORECASE
    )
    if name_match:
        meta['plan_name'] = name_match.group(1).strip()

    prem = re.search(
        r'(?:monthly\s+(?:plan\s+)?premium|plan\s+premium)\s*\n?\s*\$([0-9,.]+)',
        text, re.IGNORECASE
    )
    if prem:
        meta['monthly_premium'] = f"${prem.group(1)}"
    if 'monthly_premium' not in meta:
        hdr_prem = re.search(r'\|\s*\$([0-9,.]+)\s+Plan\s+Premium', text, re.IGNORECASE)
        if hdr_prem:
            meta['monthly_premium'] = f"${hdr_prem.group(1)}"

    no_ded = re.search(r'does\s+not\s+have\s+a\s+(?:medical\s+)?deductible', text, re.IGNORECASE)
    if no_ded:
        meta['annual_deductible_in'] = "$0"
    else:
        ded = re.search(r'(?:(?:Plan|Medical)\s+)?[Dd]eductible\s*\n?\s*\$([0-9,.]+)', text)
        if ded:
            meta['annual_deductible_in'] = f"${ded.group(1)}"

    moop = re.search(r'MOOP\s*\n?\s*\$([0-9,.]+)', text, re.IGNORECASE)
    if not moop:
        moop = re.search(
            r'[Mm]aximum\s+[Oo]ut[\u2011\-\u2013]of[\u2011\-\u2013][Pp]ocket'
            r'(?:\s+[Rr]esponsibility)?'
            r'[^\n$]*?\$([0-9,.]+)',
            text
        )
    if not moop:
        # "Maximum Out-of-Pocket Responsibility\n$3,900" (Devoted - newline before amount)
        moop = re.search(
            r'[Mm]aximum\s+[Oo]ut[\u2011\-\u2013]of[\u2011\-\u2013][Pp]ocket'
            r'(?:\s+[Rr]esponsibility)?\s*\n\s*\$([0-9,.]+)',
            text
        )
    if not moop:
        moop = re.search(r'\$([0-9,.]+)\s+(?:for\s+)?in[\u2011\-\u2013]network\s+services', text, re.IGNORECASE)
    if not moop:
        moop = re.search(r'\$([0-9,.]+)\s+in[\u2011\-\u2013]network', text, re.IGNORECASE)
    if moop:
        meta['moop_in'] = f"${moop.group(1)}"

    oon_moop = re.search(
        r'\$([0-9,.]+)\s+combined\s+in[\u2011\-]?\s*and\s+out[\u2011\-\u2013]of[\u2011\-\u2013]network',
        text, re.IGNORECASE
    )
    if oon_moop:
        meta['moop_out'] = f"${oon_moop.group(1)}"

    return meta


# ─── Direct benefit extractors ───

def _find_pcp(text: str) -> str | None:
    m = re.search(r'Primary\s+Care\s+Provider\s*\(PCP\)\s*:\s*(\$\d+)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'\nPCP\s*\n\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"PCP'?s?\s+office\s*\n\s*(\$\d+)\s*copay", text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _find_specialist(text: str) -> str | None:
    m = re.search(r'Specialist\s*:\s*(\$\d+)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'\nSpecialist\s*\n\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"Specialist'?s?\s+office\s*\n\s*(\$\d+)\s*copay", text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _find_emergency(text: str) -> str | None:
    # "$150 copay for emergency care" (Aetna) - most specific, try first
    m = re.search(r'(\$\d+)\s+copay\s+for\s+emergency\s+(?:care|services)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    # "Emergency services at emergency room\n$100 copay" (Humana)
    m = re.search(r'Emergency\s+services\s+at\s+emergency\s+room\s*\n\s*(\$\d+)\s+copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    # "Emergency Care\n$150 copay per stay" (Devoted) - require start of line or after section break
    m = re.search(r'\nEmergency\s+Care\s*\n\s*(\$\d+)\s+copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    # "EMERGENCY CARE\n...\n$100 copay" section header
    m = re.search(r'EMERGENCY\s+CARE\s*\n[^\n]*?(\$\d+)\s+copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _find_urgent(text: str) -> str | None:
    m = re.search(r'(\$\d+)\s+copay\s+for\s+urgent\s+care', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'Urgent\s+Care\s+Center[^\n]*?(\$\d+)\s*copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'Urgent\s+care\s+center\s*\n\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _find_ambulance(text: str) -> str | None:
    m = re.search(r'Ground\s*\n\s*(\$\d+)\s+copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'Ground\s+Ambulance\s*:\s*\n?\s*(\$\d+)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'(\$\d+)\s+copay\s+for\s+ground\s+ambulance', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'(\$\d+)\s+copay\s+for\s+ambulance', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'Ambulance\s*\n\s*\(ground[^)]*\)\s*\n\s*(\$\d+)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _find_hearing_exam(text: str) -> str | None:
    # "Routine hearing exam\n$0 copay" (Aetna - newline before cost)
    m = re.search(r'Routine\s+[Hh]earing\s+[Ee]xam\s*:?\s*\n?\s*(\$\d+)\s*copay', text)
    if m:
        return m.group(1)
    # "Routine Hearing Exam: $0 copay" (Devoted)
    m = re.search(r'Routine\s+Hearing\s+Exam\s*:\s*(\$\d+)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    # "$0 copay for fitting/evaluation, routine hearing exams" (Humana)
    m = re.search(r'(\$\d+)\s+copay\s+for\s+(?:fitting/evaluation,\s+)?routine\s+hearing\s+exam', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _find_hearing_aids(text: str) -> str | None:
    m = re.search(r'Hearing\s+aids.*?\$([0-9,]+)\s+per\s+ear', text, re.IGNORECASE | re.DOTALL)
    if m:
        return f"${m.group(1)}"
    m = re.search(r'Hearing\s+[Aa]ids\s*\n[^\n]*?(\$\d+)\s+copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'(\$[0-9,]+)\s+maximum\s+benefit\s+coverage\s+amount\s+for\s+each\s+(?:prescription\s+)?hearing\s+aid', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _find_dental(text: str) -> str | None:
    m = re.search(r'(\$\d+)\s+copay\s+for\s+preventive\s+(?:dental\s+)?services', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'Medicare[\u2011\-]covered\s+dental\s*\n\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'dental\s+benefit.*?(\$\d+)\s+copay\s+for\s+(?:comprehensive\s+oral\s+exam|prophylaxis|cleaning)', text, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r'\$([0-9,]+)\s+yearly\s+allowance\s+toward\s+(?:Preventive\s+)?Dental', text, re.IGNORECASE)
    if m:
        return f"${m.group(1)} allowance"
    return None


def _find_vision_exam(text: str) -> str | None:
    m = re.search(r'Routine\s+(?:[Ee]ye|[Vv]ision)\s+[Ee]xam[^\n]*?(\$\d+)\s*copay', text)
    if m:
        return m.group(1)
    m = re.search(r'Routine\s+(?:Eye|Vision)\s+Exam\s*:\s*(\$\d+)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _find_vision_eyewear(text: str) -> str | None:
    m = re.search(r'(\$[0-9,]+)\s+(?:for\s+covered\s+prescription\s+eyewear|each\s+year\s+for\s+eyeglasses)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'(\$[0-9,]+)\s+maximum\s+benefit\s+coverage\s+amount\s+per\s+year\s+for\s+contact', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'Up\s+to\s+(\$[0-9,]+)\s+each\s+year\s+for\s+eyeglasses', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'(?:allowance\)?)\s+of\s+(\$[0-9,]+)\s+for\s+covered', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _find_inpatient(text: str) -> str | None:
    m = re.search(
        r'(?:Inpatient(?:\s+Hospital)?\s*(?:\(unlimited|\n|Coverage)|INPATIENT\s+HOSPITAL\s+COVERAGE)',
        text, re.IGNORECASE
    )
    if not m:
        return None
    window = text[m.end():m.end() + 500]
    boundary = SECTION_BOUNDARY.search(window)
    if boundary:
        window = window[:boundary.start()]
    return extract_cost_from_window(window)


def _find_outpatient(text: str) -> str | None:
    # "Outpatient Hospital: $195 copay" (Devoted)
    m = re.search(r'Outpatient\s+Hospital\s*:\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m:
        return m.group(1)

    # Check if there's a section header (Humana uses OUTPATIENT HOSPITAL COVERAGE)
    section = re.search(
        r'(?:OUTPATIENT\s+HOSPITAL\s+COVERAGE|Outpatient\s+Hospital\s+Coverage)',
        text, re.IGNORECASE
    )

    if section:
        # Humana format: grab first copay in section before surgery/ambulatory
        window = text[section.end():section.end() + 200]
        first_cost = re.search(r'(\$\d+)\s*copay', window)
        if first_cost:
            return first_cost.group(1)

    # "Outpatient hospital\n$0 copay" or "Outpatient hospital Coverage...\n$0 copay" (Aetna)
    m = re.search(r'Outpatient\s+[Hh]ospital(?:\s+[Cc]overage[^\n]*)?\s*\n\s*(\$\d+)\s*copay', text)
    if m:
        return m.group(1)

    return None


def _find_surgery(text: str) -> str | None:
    # "Ambulatory Surgical Center (ASC): $195 copay" (Devoted)
    m = re.search(r'Ambulatory\s+Surgical\s+Center\s*\(ASC\)\s*:\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    # "Ambulatory surgical center\n$0 copay" (Aetna)
    m = re.search(r'Ambulatory\s+[Ss]urgical\s+[Cc]enter\s*\n\s*(\$\d+)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    # "AMBULATORY SURGERY CENTER\nSurgery services\n$20 copay" (Humana)
    m = re.search(r'AMBULATORY\s+SURGERY\s+CENTER\s*\n[^\n]*?\n\s*(\$\d+)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    # Generic "Surgery services\n$60 copay"
    m = re.search(r'Surgery\s+services\s*\n\s*(\$\d+)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _find_snf(text: str) -> str | None:
    # Try most specific match first: "SNF care\n$0 per day..."
    m = re.search(r'SNF\s+care\s*\n', text, re.IGNORECASE)
    if not m:
        # "SKILLED NURSING FACILITY (SNF)\nThis plan covers..."
        m = re.search(
            r'(?:SKILLED\s+NURSING\s+FACILITY|Skilled\s+Nursing\s+Facility)\s*(?:\(SNF\))?\s*\n',
            text, re.IGNORECASE
        )
    if not m:
        return None
    window = text[m.end():m.end() + 400]
    boundary = SECTION_BOUNDARY.search(window)
    if boundary:
        window = window[:boundary.start()]
    return extract_cost_from_window(window)


def _find_mental_outpatient(text: str) -> str | None:
    m = re.search(r'Outpatient\s+[Mm]ental\s+[Hh]ealth[^\n]*?\n\s*(\$\d+)\s*copay', text)
    if m:
        return m.group(1)
    m = re.search(r'Mental\s+[Hh]ealth\s+[Tt]herapy\s+visits\s*\n\s*(\$\d+)\s*copay', text)
    if m:
        return m.group(1)
    m = re.search(r'Outpatient\s+Mental\s+Health\s+Services[^\n]*?\n?\s*:\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'Outpatient\s+Mental\s+Health\s+Services[^\n]*?\n\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _find_mental_inpatient(text: str) -> str | None:
    m = re.search(
        r'(?:Inpatient\s+(?:[Pp]sychiatric|[Mm]ental\s+[Hh]ealth)\s*(?:hospital\s+stay|Care)?)',
        text, re.IGNORECASE
    )
    if not m:
        return None
    window = text[m.end():m.end() + 400]
    trunc = re.search(r'\n(?:Outpatient|SNF|Skilled|Physical|Substance)', window, re.IGNORECASE)
    if trunc:
        window = window[:trunc.start()]
    return extract_cost_from_window(window)


def _find_preventive(text: str) -> str | None:
    m = re.search(r'Preventive\s+[Cc]are\s*\n\s*(\$\d+)\s*copay', text)
    if m:
        return m.group(1)
    m = re.search(r'covers\s+many\s+preventive\s+services\s+at\s+no\s+cost', text, re.IGNORECASE)
    if m:
        return "$0"
    m = re.search(r'PREVENTIVE\s+CARE\s*\n\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


# ─── Medical extraction (assembled) ───

def extract_medical(text: str, is_ppo: bool) -> list[dict]:
    results = []

    def add(label, value):
        if value:
            results.append({"label": label, "in_network": value})

    add("PCP visit", _find_pcp(text))
    add("Specialist visit", _find_specialist(text))
    add("Preventive care", _find_preventive(text))
    add("Inpatient hospital", _find_inpatient(text))
    add("Outpatient hospital", _find_outpatient(text))
    add("Outpatient surgery", _find_surgery(text))
    add("Emergency room", _find_emergency(text))
    add("Urgent care", _find_urgent(text))

    add("Lab services", find_cost(text, r'Lab\s+[Ss]ervices'))
    add("X-rays / Imaging", find_cost(text, r'(?:Outpatient\s+[Xx][\u2011\-]rays|Diagnostic\s+[Rr]adiology|Basic\s+radiological|Advanced\s+imaging)'))

    add("Ambulance", _find_ambulance(text))
    add("Mental health (outpatient)", _find_mental_outpatient(text))
    add("Mental health (inpatient)", _find_mental_inpatient(text))
    add("Skilled nursing", _find_snf(text))
    add("Physical therapy", find_cost(text, r'Physical\s+(?:and\s+speech\s+)?[Tt]herapy'))
    add("Home health care", find_cost(text, r'Home\s+[Hh]ealth\s+[Cc]are'))

    add("Dental", _find_dental(text))
    add("Vision (exam)", _find_vision_exam(text))
    add("Vision (eyewear)", _find_vision_eyewear(text))
    add("Hearing (exam)", _find_hearing_exam(text))
    add("Hearing (aids)", _find_hearing_aids(text))
    add("Chiropractic", find_cost(text, r'Chiropractic\s+(?:[Ss]ervices|[Cc]are)'))
    add("Podiatry", find_cost(text, r'(?:Foot\s+(?:exams|care)|Podiatry\s+services|Routine\s+foot\s+care)'))
    add("Acupuncture", find_cost(text, r'Acupuncture'))

    return results


# ─── Drug tier extraction ───

def _parse_cost_value(raw: str):
    """Parse a cost value string like '$47', '41%', '25% up to $35', 'N/A'.
    Returns dict with keys: amount (float|None), pct (float|None), cap (float|None), raw (str), type ('copay'|'coinsurance'|'na').
    """
    raw = raw.strip()
    if not raw or raw.upper() == 'N/A':
        return {"amount": None, "pct": None, "cap": None, "raw": raw, "type": "na"}

    # "25% up to $35" pattern
    m = re.match(r'(\d+)%\s*up\s*to\s*\$(\d+(?:\.\d+)?)', raw)
    if m:
        return {"amount": None, "pct": float(m.group(1)), "cap": float(m.group(2)),
                "raw": raw, "type": "coinsurance"}

    # Pure percentage "41%"
    m = re.match(r'(\d+)%$', raw)
    if m:
        return {"amount": None, "pct": float(m.group(1)), "cap": None,
                "raw": raw, "type": "coinsurance"}

    # Dollar amount "$47"
    m = re.match(r'\$(\d+(?:[.,]\d+)?)', raw)
    if m:
        val = float(m.group(1).replace(',', ''))
        return {"amount": val, "pct": None, "cap": None, "raw": raw, "type": "copay"}

    return {"amount": None, "pct": None, "cap": None, "raw": raw, "type": "unknown"}


def extract_tier_copays(text: str) -> dict:
    """
    Extract structured per-tier copay data from SOB text.
    Handles multiple carrier formats: Humana, Aetna, Devoted, UHC, Wellcare.

    Returns dict like:
    {
        1: {"retail_30": "$0", "retail_90": "$0", "mail_30": "$10", ...},
        ...
        "insulin_cap": 35,
        "deductible_tiers": [4, 5],
        "deductible_amount": 615,
    }

    The "retail_30" value is the preferred retail 30-day copay — the primary value
    used for drug cost calculation (SOB governs over CMS).
    """
    tier_copays = {}

    # Tier patterns — flexible to handle multiple carrier formats:
    # "Tier 1: Preferred Generic" (Humana, Aetna)
    # "Tier 1:\nPreferred Generic" (UHC)
    # "Tier 1\n(Preferred Generic)" (Wellcare)
    # "Tier 1: Preferred Generic\nTier 2: Generic\n..." then costs below (Devoted)
    tier_patterns = [
        (1, r'Tier\s*1[:\s]*\(?\s*Preferred\s+Generic'),
        (2, r'Tier\s*2[:\s]*\(?\s*Generic'),
        (3, r'Tier\s*3[:\s]*\(?\s*Preferred\s+Brand'),
        (4, r'Tier\s*4[:\s]*\(?\s*Non[\u2011\-\u2013]?\s*Preferred(?:\s+Drug[s]?)?'),
        (5, r'Tier\s*5[:\s]*\(?\s*Specialty(?:\s+Tier)?'),
        (6, r'Tier\s*6[:\s]*\(?\s*Select\s+Care'),
    ]

    # ── Find the best table region ──
    # Some carriers (UHC, Wellcare) have tier data AFTER the first "Catastrophic
    # Coverage" mention, or split across multiple chunks.  Instead of a narrow
    # IC→Catastrophic window, we find ALL occurrences of each tier label and
    # pick the best cluster (the one with the most tiers together that's inside
    # or near an "Initial Coverage" section).

    # 1. Gather every tier-label position in the full text
    all_tier_hits = []  # list of (tier_num, start, end)
    for tier_num, pattern in tier_patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            all_tier_hits.append((tier_num, m.start(), m.end()))

    # 2. Group into clusters (hits within 3000 chars of each other)
    all_tier_hits.sort(key=lambda x: x[1])
    clusters = []
    current_cluster = []
    for hit in all_tier_hits:
        if current_cluster and hit[1] - current_cluster[-1][1] > 3000:
            clusters.append(current_cluster)
            current_cluster = [hit]
        else:
            current_cluster.append(hit)
    if current_cluster:
        clusters.append(current_cluster)

    # 3. Pick the best cluster: prefer the one with the most distinct tiers,
    #    and among ties, prefer the one closest to an "Initial Coverage" label
    #    that also has "Retail" or "30-day" nearby.
    ic_positions = [m.start() for m in re.finditer(
        r'Initial\s+Coverage', text, re.IGNORECASE)]

    def cluster_score(cluster):
        distinct = len(set(h[0] for h in cluster))
        # Proximity to an IC label (smaller is better, so negate)
        cluster_start = cluster[0][1]
        min_ic_dist = min((abs(cluster_start - ic) for ic in ic_positions), default=99999)
        # Check for "Retail" or "30-day" nearby the cluster (strong indicator)
        region_before = text[max(0, cluster_start - 300):cluster_start]
        has_retail = bool(re.search(r'Retail|30[\u2011\-]?day', region_before, re.IGNORECASE))
        return (distinct, has_retail, -min_ic_dist)

    if clusters:
        best_cluster = max(clusters, key=cluster_score)
    else:
        best_cluster = []

    # 4. Define table_text as a generous window around the best cluster
    if best_cluster:
        table_start = max(0, best_cluster[0][1] - 500)
        table_end = min(len(text), best_cluster[-1][2] + 2000)
    else:
        table_start = 0
        table_end = len(text)

    table_text = text[table_start:table_end]

    # ── Detect Devoted-style vertical format ──
    # Devoted lists all tier labels together, then all costs below.
    # Detect: if Tier 1 through Tier 5 labels appear within 300 chars of each other
    # and NO cost tokens appear between them, it's vertical format.
    tier_positions = []
    for tier_num, pattern in tier_patterns:
        m = re.search(pattern, table_text, re.IGNORECASE)
        if m:
            tier_positions.append((tier_num, m.start(), m.end()))

    is_vertical = False
    if len(tier_positions) >= 3:
        first_end = tier_positions[0][2]
        last_start = tier_positions[-1][1]
        between_text = table_text[first_end:last_start]
        # Check if there are NO cost values between first and last tier label
        cost_in_between = re.search(r'\$\d+|\d+%', between_text)
        if not cost_in_between and (last_start - first_end) < 500:
            is_vertical = True

    if is_vertical:
        # ── Devoted-style vertical parsing ──
        # All tier labels are together, then costs follow as a vertical list
        # Find the text AFTER all tier labels
        last_tier_end = max(tp[2] for tp in tier_positions)
        costs_text = table_text[last_tier_end:last_tier_end + 2000]

        # Look for "30-Day" section and "100-Day" or "Mail Order" section
        # Devoted: "30-Day Supply Network\nRetail Pharmacy\n$18 per...\n$20 per...\n23%..."
        retail_section = re.search(
            r'30[\u2011\-]?[Dd]ay\s+[Ss]upply.*?(?:Retail|Network)',
            costs_text, re.IGNORECASE
        )
        mail_section = re.search(
            r'100[\u2011\-]?[Dd]ay\s+[Ss]upply.*?(?:Mail|Network)',
            costs_text, re.IGNORECASE
        )

        def _extract_vertical_costs(section_text):
            """Extract sequential cost values from a vertical list."""
            # Normalize "X% of the total cost" → "X%"
            normalized = re.sub(r'(\d+)%\s+of\s+the\s+(?:total\s+)?cost', r'\1%', section_text)
            # Match: "$18 per prescription", "$0", "23%", "Not available"
            costs = []
            for cm in re.finditer(
                r'(\d+%\s*up\s*to\s*\$[\d,.]+|\$[\d,.]+|\d+%|Not\s+[Aa]vailable)',
                normalized
            ):
                val = cm.group(0)
                if 'not available' in val.lower():
                    val = 'N/A'
                costs.append(val)
            return costs

        # Extract retail costs
        retail_costs = []
        if retail_section:
            r_start = retail_section.end()
            r_end = mail_section.start() if mail_section and mail_section.start() > r_start else r_start + 800
            retail_costs = _extract_vertical_costs(costs_text[r_start - last_tier_end:r_end - last_tier_end]
                                                   if r_start > last_tier_end else costs_text[:r_end - last_tier_end])

        # If no explicit section header, just grab all costs after tier labels
        if not retail_costs:
            retail_costs = _extract_vertical_costs(costs_text)

        # Extract mail costs
        mail_costs = []
        if mail_section:
            m_start = mail_section.end()
            # Find end of mail section
            m_end_markers = [r'CATASTROPHIC', r'EXTRA\s+HELP', r'long[\u2011\-]term\s+care',
                            r'If\s+you\s+reside']
            m_end = m_start + 800
            for mpat in m_end_markers:
                mm = re.search(mpat, costs_text[m_start - last_tier_end:], re.IGNORECASE)
                if mm:
                    m_end = min(m_end, m_start + mm.start())
            mail_costs = _extract_vertical_costs(costs_text[m_start - last_tier_end:m_end - last_tier_end])

        # Map costs to tiers by position
        tier_order = [tp[0] for tp in tier_positions]
        for i, tier_num in enumerate(tier_order):
            tier_data = {
                "retail_30": retail_costs[i] if i < len(retail_costs) else None,
                "retail_90": None,
                "mail_30": None,
                "mail_90": mail_costs[i] if i < len(mail_costs) else None,
                "pref_mail_30": None,
                "pref_mail_90": None,
            }
            parsed = _parse_cost_value(tier_data["retail_30"] or "")
            tier_data["parsed_retail_30"] = parsed
            tier_copays[tier_num] = tier_data

    else:
        # ── Standard inline parsing (Humana, Aetna, UHC, Wellcare) ──
        for tier_num, pattern in tier_patterns:
            # Try ALL matches for this tier — some hits are in descriptive text
            # (e.g. deductible descriptions), not the actual cost table.
            # Pick the first match that has cost values CLOSE to it (within 80 chars),
            # and the cost value appears before any sentence-like text.
            best_match = None
            for match in re.finditer(pattern, table_text, re.IGNORECASE):
                peek = table_text[match.end():match.end() + 80]
                # Skip parenthesized suffix like ")" or "(Non-Preferred\nDrug)"
                peek_stripped = re.sub(r'^[^$%\d]*?[\)\n]\s*', '', peek)
                cost_hit = re.search(r'\$\d+|\d+%', peek_stripped)
                if cost_hit and cost_hit.start() < 40:
                    best_match = match
                    break

            if not best_match:
                continue

            row_start = best_match.end()
            row_end = row_start + 400

            # Truncate at next tier label
            for next_tier_num, next_pattern in tier_patterns:
                if next_tier_num <= tier_num:
                    continue
                next_match = re.search(next_pattern, table_text[row_start:row_end], re.IGNORECASE)
                if next_match:
                    row_end = row_start + next_match.start()
                    break

            # Truncate at section boundaries
            for boundary_pat in [r'CATASTROPHIC', r'Catastrophic\s+Coverage',
                                 r'Insulin\s+Cost', r'EXCLUDED\s+DRUG',
                                 r'EXTRA\s+HELP', r'DEDUCTIBLE\s+STAGE',
                                 r'Covered\s+Insulin', r'Mail[\u2011\-]?order\s+cost',
                                 r'Stage\s+2:\s+Initial',
                                 r'Long[\u2011\-]?term\s+Supply']:
                bm = re.search(boundary_pat, table_text[row_start:row_end], re.IGNORECASE)
                if bm:
                    row_end = min(row_end, row_start + bm.start())

            row_text = table_text[row_start:row_end]

            # ── Normalize cost text ──
            # Collapse "25% / 25%\ncoinsurance" → "25% / 25% coinsurance" (Wellcare newline split)
            normalized = re.sub(r'(\d+%)\s*\n\s*(coinsurance)', r'\1 \2', row_text)
            # Also handle "25% coinsurance \n/ Not Available" → "25% coinsurance / Not Available"
            normalized = re.sub(r'(coinsurance)\s*\n\s*(/)', r'\1 \2', normalized)
            # Normalize "25% up to\n$35" → "25% up to $35"
            normalized = re.sub(r'(\d+%)\s*up\s*to\s*\n?\s*(\$\d+)', r'\1 up to \2', normalized)
            # Normalize "17%, up to $35 copay" (UHC) → "17% up to $35"
            normalized = re.sub(r'(\d+)%\s*,?\s*up\s*to\s*\$(\d+)', r'\1% up to $\2', normalized)
            # Normalize "17% coinsurance" → "17%"
            normalized = re.sub(r'(\d+)%\s*(?:coinsurance|of\s+the\s+(?:total\s+)?cost)', r'\1%', normalized)
            # Handle "Not\nAvailable" or "Not Available" → "N/A"
            normalized = re.sub(r'Not\s+[Aa]vailable', 'N/A', normalized)
            # Handle Wellcare "$0 / $0 copay" → split as two values "$0" "$0"
            # and "$5 / $15 copay" → "$5" "$15"
            normalized = re.sub(r'\$(\d+)\s*/\s*\$(\d+)', r'$\1 $\2', normalized)
            # Handle Wellcare "25% / 25% ..." (already normalized coinsurance away) → "25% 25%"
            normalized = re.sub(r'(\d+)%\s*/\s*(\d+)%', r'\1% \2%', normalized)
            # Handle "25% / N/A" → "25% N/A"
            normalized = re.sub(r'(\d+)%\s*/\s*N/A', r'\1% N/A', normalized)

            cost_values = []
            for cm in re.finditer(r'(\d+%\s*up\s*to\s*\$[\d,.]+|\$[\d,.]+|\d+%|N/A)', normalized):
                cost_values.append(cm.group(0))

            tier_data = {
                "retail_30": cost_values[0] if len(cost_values) > 0 else None,
                "retail_90": cost_values[1] if len(cost_values) > 1 else None,
                "mail_30": cost_values[2] if len(cost_values) > 2 else None,
                "mail_90": cost_values[3] if len(cost_values) > 3 else None,
                "pref_mail_30": cost_values[4] if len(cost_values) > 4 else None,
                "pref_mail_90": cost_values[5] if len(cost_values) > 5 else None,
            }

            parsed = _parse_cost_value(tier_data["retail_30"] or "")
            tier_data["parsed_retail_30"] = parsed

            tier_copays[tier_num] = tier_data

    # ── Insulin cap ──
    # Pattern 1: "won't pay more than $35 for" (Humana, Aetna)
    insulin = re.search(
        r"(?:won[\u2019']t|will not)\s+pay\s+more\s+than\s+\$(\d+)\s+for",
        text, re.IGNORECASE
    )
    # Pattern 2: "no more than $35 for a 30-day supply" (Devoted)
    if not insulin:
        insulin = re.search(
            r'no\s+more\s+than\s+\$(\d+)\s+for\s+a\s+(?:30[\u2011\-]day|one[\u2011\-]month)\s+supply',
            text, re.IGNORECASE
        )
    # Pattern 3: "no more than 17% of the total drug cost or a $35 copay" (UHC)
    if not insulin:
        insulin = re.search(
            r'no\s+more\s+than\s+\d+%\s+of\s+the\s+total\s+drug\s+cost\s+or\s+a\s+\$(\d+)\s+copay',
            text, re.IGNORECASE
        )
    # Pattern 4: "won't pay more than the lesser of 25% ... or $35 for" (Wellcare)
    if not insulin:
        insulin = re.search(
            r"(?:won[\u2019']t|will not)\s+pay\s+more\s+than\s+the\s+lesser\s+of\s+\d+%.*?or\s+\$(\d+)\s+for",
            text, re.IGNORECASE | re.DOTALL
        )
    # Pattern 5: "up to $35 copay" in insulin-specific sections
    if not insulin:
        insulin = re.search(
            r'(?:Covered\s+Insulin|Insulin\s+Cost).*?up\s+to\s+\$(\d+)\s+copay',
            text, re.IGNORECASE | re.DOTALL
        )
    if insulin:
        tier_copays["insulin_cap"] = int(insulin.group(1))

    # ── Deductible tiers ──
    # Pattern 1: "$615 deductible for Tier 4 and Tier 5" (Humana)
    ded_match = re.search(
        r'\$(\d+)\s+deductible\s+for\s+Tier\s+(\d+)\s+and\s+Tier\s+(\d+)',
        text, re.IGNORECASE
    )
    if ded_match:
        tier_copays["deductible_amount"] = int(ded_match.group(1))
        tier_copays["deductible_tiers"] = [int(ded_match.group(2)), int(ded_match.group(3))]
    else:
        # Pattern 2: "$595 for Tiers 3-5" (Devoted)
        ded_match2 = re.search(
            r'\$(\d+)\s+(?:deductible\s+)?for\s+Tiers?\s+(\d)[\u2011\-\u2013](\d)',
            text, re.IGNORECASE
        )
        if ded_match2:
            tier_copays["deductible_amount"] = int(ded_match2.group(1))
            tier_copays["deductible_tiers"] = list(range(
                int(ded_match2.group(2)), int(ded_match2.group(3)) + 1
            ))
        else:
            # Pattern 3: "$355 deductible for drugs in Tier 3, 4 and 5" (UHC)
            ded_match3 = re.search(
                r'\$(\d+)\s+deductible\s+for\s+drugs\s+in\s+Tier\s+([\d,\s]+and\s+\d+)',
                text, re.IGNORECASE
            )
            if ded_match3:
                tier_copays["deductible_amount"] = int(ded_match3.group(1))
                # Parse "3, 4 and 5" → [3, 4, 5]
                tier_str = ded_match3.group(2)
                tier_nums = [int(d) for d in re.findall(r'\d+', tier_str)]
                tier_copays["deductible_tiers"] = tier_nums
            else:
                # Pattern 4: "deductible limit of $615...applies to drugs on Tiers 3, 4, and 5" (Aetna)
                # Use a tighter match: $amount must be >0 and within 200 chars of "applies to"
                ded_match4 = re.search(
                    r'deductible\s+(?:limit\s+of\s+)?\$(\d{2,})\b.{0,200}?(?:applies\s+to|for)\s+.*?drugs\s+on\s+Tiers?\s+([\d,\s]+and\s+\d+)',
                    text, re.IGNORECASE | re.DOTALL
                )
                if ded_match4:
                    tier_copays["deductible_amount"] = int(ded_match4.group(1))
                    tier_nums = [int(d) for d in re.findall(r'\d+', ded_match4.group(2))]
                    tier_copays["deductible_tiers"] = tier_nums
                else:
                    # Pattern 5: "$615 for Part D ... applies to drugs on Tier 3 ... Tier 4 ... Tier 5" (Wellcare)
                    ded_match5 = re.search(
                        r'\$(\d+)\s+for\s+Part\s+D\s+prescription\s+drugs',
                        text, re.IGNORECASE
                    )
                    if ded_match5:
                        # Find the tiers it applies to in nearby text
                        ded_context = text[ded_match5.start():ded_match5.start() + 500]
                        tier_refs = re.findall(r'Tier\s+(\d+)', ded_context)
                        if tier_refs:
                            tier_copays["deductible_amount"] = int(ded_match5.group(1))
                            tier_copays["deductible_tiers"] = sorted(set(int(t) for t in tier_refs))

    return tier_copays


def extract_drugs(text: str) -> list[dict]:
    results = []

    # Drug deductible
    drug_ded_range = re.search(
        r'deductible\s+(?:limit\s+of\s+)?\$?([0-9,.]+)\s*[\u2011\-\u2013]\s*\$?([0-9,.]+)',
        text, re.IGNORECASE
    )
    if drug_ded_range:
        val = f"${drug_ded_range.group(1)}-${drug_ded_range.group(2)}"
        # Strip trailing period if present
        val = val.rstrip('.')
        results.append({"label": "Drug deductible", "value": val})
    else:
        # "$615 deductible for Tier 4 and Tier 5" (Humana) — find the NON-ZERO deductible
        all_deds = re.findall(r'\$(\d+)\s+deductible\s+for\s+Tier', text, re.IGNORECASE)
        if all_deds:
            # Take the highest deductible value (non-zero tiers)
            max_ded = max(int(d) for d in all_deds)
            if max_ded > 0:
                # Find which tiers have this deductible
                m = re.search(rf'\${max_ded}\s+deductible\s+for\s+Tier\s+(\d+)\s+and\s+Tier\s+(\d+)', text, re.IGNORECASE)
                if m:
                    results.append({"label": "Drug deductible", "value": f"${max_ded} (Tiers {m.group(1)}-{m.group(2)})"})
                else:
                    results.append({"label": "Drug deductible", "value": f"${max_ded}"})
            else:
                results.append({"label": "Drug deductible", "value": "$0"})
        else:
            # "$595 for Tiers 3-5 only" (Devoted)
            m = re.search(r'\$(\d+)\s+for\s+Tiers?\s+(\d)[\u2011\-\u2013](\d)', text, re.IGNORECASE)
            if m:
                results.append({"label": "Drug deductible", "value": f"${m.group(1)} (Tiers {m.group(2)}-{m.group(3)})"})

    # Tier costs (legacy label/value format — kept for backward compat with SOB card display)
    tier_labels = [
        ("Tier 1 - Preferred Generic",  r'Tier\s*1:\s*Preferred\s+Generic'),
        ("Tier 2 - Generic",            r'Tier\s*2:\s*Generic'),
        ("Tier 3 - Preferred Brand",    r'Tier\s*3:\s*Preferred\s+Brand'),
        ("Tier 4 - Non-Preferred",      r'Tier\s*4:\s*Non[\u2011\-\u2013]?Preferred'),
        ("Tier 5 - Specialty",          r'Tier\s*5:\s*Specialty'),
    ]

    for i, (label, pattern) in enumerate(tier_labels):
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue

        start = match.end()
        window = text[start:start + 200]

        # Truncate at next tier label or section boundary
        next_tier = None
        if i + 1 < len(tier_labels):
            next_tier = re.search(tier_labels[i + 1][1], window, re.IGNORECASE)
        sect_bound = re.search(
            r'\n(?:CATASTROPHIC|Catastrophic|Out[\u2011\-\u2013]of[\u2011\-\u2013]pocket|'
            r'Long[\u2011\-\u2013]term|INITIAL|Initial|EXTRA|Extra|You\s+have|'
            r'You\s+won|Important|Insulin)',
            window, re.IGNORECASE
        )

        trunc = None
        if next_tier and sect_bound:
            trunc = min(next_tier.start(), sect_bound.start())
        elif next_tier:
            trunc = next_tier.start()
        elif sect_bound:
            trunc = sect_bound.start()

        if trunc:
            window = window[:trunc]

        costs = re.findall(r'(\$[\d,.]+|\d+%)', window)

        if len(costs) >= 2 and costs[0] != costs[1]:
            results.append({
                "label": label,
                "value": f"{costs[0]} preferred / {costs[1]} standard",
            })
        elif costs:
            results.append({"label": label, "value": costs[0]})

    # Part D OOP max
    oop = re.search(
        r'\$([0-9,]+)\s+is\s+the\s+maximum.*?Part\s*D\s+out[\u2011\-\u2013]of[\u2011\-\u2013]pocket',
        text, re.IGNORECASE
    )
    if not oop:
        oop = re.search(
            r'out[\u2011\-\u2013]of[\u2011\-\u2013]pocket\s+(?:drug\s+)?costs\s+reach\s+\$([0-9,]+)',
            text, re.IGNORECASE
        )
    if oop:
        results.append({"label": "Part D max OOP", "value": f"${oop.group(1)}"})

    # Catastrophic
    cat = re.search(
        r'(?:you\s+pay|pay)\s+\$(\d+)\s+for\s+(?:covered\s+)?(?:generic|brand|Part\s+D|plan[\u2011\-]?covered)',
        text, re.IGNORECASE
    )
    if cat:
        results.append({"label": "Catastrophic phase", "value": f"${cat.group(1)}"})

    # Insulin cap
    insulin = re.search(
        r"(?:won[\u2019']t|will not)\s+pay\s+more\s+than\s+\$(\d+)\s+for",
        text, re.IGNORECASE
    )
    if not insulin:
        insulin = re.search(
            r'no\s+more\s+than\s+\$(\d+)\s+for\s+a\s+(?:30[\u2011\-]day|one[\u2011\-]month)\s+supply',
            text, re.IGNORECASE
        )
    if insulin:
        results.append({"label": "Insulin cap", "value": f"${insulin.group(1)}"})

    return results


# ─── Main parse function ───

def parse_sob(plan_id: str) -> dict | None:
    text = load_plan_text(plan_id)
    if text is None:
        return None

    meta = extract_plan_meta(text)
    is_ppo = 'PPO' in meta.get('plan_type', '')
    medical = extract_medical(text, is_ppo)
    drugs = extract_drugs(text)
    tier_copays = extract_tier_copays(text)

    return {
        "success": True,
        "plan_id": normalize_plan_id(plan_id),
        "plan_name": meta.get("plan_name", plan_id),
        "plan_type": meta.get("plan_type", ""),
        "monthly_premium": meta.get("monthly_premium", ""),
        "annual_deductible_in": meta.get("annual_deductible_in", ""),
        "annual_deductible_out": meta.get("annual_deductible_out", ""),
        "moop_in": meta.get("moop_in", ""),
        "moop_out": meta.get("moop_out", ""),
        "medical": medical,
        "drugs": drugs,
        "tier_copays": tier_copays,
    }
