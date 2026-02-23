"""
SOB Text Parser v2 — deterministic extraction of benefits from SOB chunk text.

Fixes from v1:
- Expanded section boundaries to prevent bleed-over (SKILLED NURSING, DOCTOR VISITS, etc.)
- PCP/Specialist/Emergency use direct cost-near-label search instead of rigid patterns
- Drug tier windows truncated at next Tier label
- Dental/Hearing/Ambulance use targeted extraction
"""

import re
import json
import os

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
    path = os.path.join(EXTRACTED_DIR, f"{pid}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        data = json.load(f)
    return "\n\n".join(data["chunks"])


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
    if m: return m.group(1)
    m = re.search(r'\nPCP\s*\n\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r"PCP'?s?\s+office\s*\n\s*(\$\d+)\s*copay", text, re.IGNORECASE)
    if m: return m.group(1)
    return None


def _find_specialist(text: str) -> str | None:
    m = re.search(r'Specialist\s*:\s*(\$\d+)', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'\nSpecialist\s*\n\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r"Specialist'?s?\s+office\s*\n\s*(\$\d+)\s*copay", text, re.IGNORECASE)
    if m: return m.group(1)
    return None


def _find_emergency(text: str) -> str | None:
    # "$150 copay for emergency care" (Aetna) - most specific, try first
    m = re.search(r'(\$\d+)\s+copay\s+for\s+emergency\s+(?:care|services)', text, re.IGNORECASE)
    if m: return m.group(1)
    # "Emergency services at emergency room\n$100 copay" (Humana)
    m = re.search(r'Emergency\s+services\s+at\s+emergency\s+room\s*\n\s*(\$\d+)\s+copay', text, re.IGNORECASE)
    if m: return m.group(1)
    # "Emergency Care\n$150 copay per stay" (Devoted) - require start of line or after section break
    m = re.search(r'\nEmergency\s+Care\s*\n\s*(\$\d+)\s+copay', text, re.IGNORECASE)
    if m: return m.group(1)
    # "EMERGENCY CARE\n...\n$100 copay" section header
    m = re.search(r'EMERGENCY\s+CARE\s*\n[^\n]*?(\$\d+)\s+copay', text, re.IGNORECASE)
    if m: return m.group(1)
    return None


def _find_urgent(text: str) -> str | None:
    m = re.search(r'(\$\d+)\s+copay\s+for\s+urgent\s+care', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'Urgent\s+Care\s+Center[^\n]*?(\$\d+)\s*copay', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'Urgent\s+care\s+center\s*\n\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m: return m.group(1)
    return None


def _find_ambulance(text: str) -> str | None:
    m = re.search(r'Ground\s*\n\s*(\$\d+)\s+copay', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'Ground\s+Ambulance\s*:\s*\n?\s*(\$\d+)', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'(\$\d+)\s+copay\s+for\s+ground\s+ambulance', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'(\$\d+)\s+copay\s+for\s+ambulance', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'Ambulance\s*\n\s*\(ground[^)]*\)\s*\n\s*(\$\d+)', text, re.IGNORECASE)
    if m: return m.group(1)
    return None


def _find_hearing_exam(text: str) -> str | None:
    # "Routine hearing exam\n$0 copay" (Aetna - newline before cost)
    m = re.search(r'Routine\s+[Hh]earing\s+[Ee]xam\s*:?\s*\n?\s*(\$\d+)\s*copay', text)
    if m: return m.group(1)
    # "Routine Hearing Exam: $0 copay" (Devoted)
    m = re.search(r'Routine\s+Hearing\s+Exam\s*:\s*(\$\d+)', text, re.IGNORECASE)
    if m: return m.group(1)
    # "$0 copay for fitting/evaluation, routine hearing exams" (Humana)
    m = re.search(r'(\$\d+)\s+copay\s+for\s+(?:fitting/evaluation,\s+)?routine\s+hearing\s+exam', text, re.IGNORECASE)
    if m: return m.group(1)
    return None


def _find_hearing_aids(text: str) -> str | None:
    m = re.search(r'Hearing\s+aids.*?\$([0-9,]+)\s+per\s+ear', text, re.IGNORECASE | re.DOTALL)
    if m: return f"${m.group(1)}"
    m = re.search(r'Hearing\s+[Aa]ids\s*\n[^\n]*?(\$\d+)\s+copay', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'(\$[0-9,]+)\s+maximum\s+benefit\s+coverage\s+amount\s+for\s+each\s+(?:prescription\s+)?hearing\s+aid', text, re.IGNORECASE)
    if m: return m.group(1)
    return None


def _find_dental(text: str) -> str | None:
    m = re.search(r'(\$\d+)\s+copay\s+for\s+preventive\s+(?:dental\s+)?services', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'Medicare[\u2011\-]covered\s+dental\s*\n\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'dental\s+benefit.*?(\$\d+)\s+copay\s+for\s+(?:comprehensive\s+oral\s+exam|prophylaxis|cleaning)', text, re.IGNORECASE | re.DOTALL)
    if m: return m.group(1)
    m = re.search(r'\$([0-9,]+)\s+yearly\s+allowance\s+toward\s+(?:Preventive\s+)?Dental', text, re.IGNORECASE)
    if m: return f"${m.group(1)} allowance"
    return None


def _find_vision_exam(text: str) -> str | None:
    m = re.search(r'Routine\s+(?:[Ee]ye|[Vv]ision)\s+[Ee]xam[^\n]*?(\$\d+)\s*copay', text)
    if m: return m.group(1)
    m = re.search(r'Routine\s+(?:Eye|Vision)\s+Exam\s*:\s*(\$\d+)', text, re.IGNORECASE)
    if m: return m.group(1)
    return None


def _find_vision_eyewear(text: str) -> str | None:
    m = re.search(r'(\$[0-9,]+)\s+(?:for\s+covered\s+prescription\s+eyewear|each\s+year\s+for\s+eyeglasses)', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'(\$[0-9,]+)\s+maximum\s+benefit\s+coverage\s+amount\s+per\s+year\s+for\s+contact', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'Up\s+to\s+(\$[0-9,]+)\s+each\s+year\s+for\s+eyeglasses', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'(?:allowance\)?)\s+of\s+(\$[0-9,]+)\s+for\s+covered', text, re.IGNORECASE)
    if m: return m.group(1)
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
    if m: return m.group(1)

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
    if m: return m.group(1)

    return None


def _find_surgery(text: str) -> str | None:
    # "Ambulatory Surgical Center (ASC): $195 copay" (Devoted)
    m = re.search(r'Ambulatory\s+Surgical\s+Center\s*\(ASC\)\s*:\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m: return m.group(1)
    # "Ambulatory surgical center\n$0 copay" (Aetna)
    m = re.search(r'Ambulatory\s+[Ss]urgical\s+[Cc]enter\s*\n\s*(\$\d+)', text, re.IGNORECASE)
    if m: return m.group(1)
    # "AMBULATORY SURGERY CENTER\nSurgery services\n$20 copay" (Humana)
    m = re.search(r'AMBULATORY\s+SURGERY\s+CENTER\s*\n[^\n]*?\n\s*(\$\d+)', text, re.IGNORECASE)
    if m: return m.group(1)
    # Generic "Surgery services\n$60 copay"
    m = re.search(r'Surgery\s+services\s*\n\s*(\$\d+)', text, re.IGNORECASE)
    if m: return m.group(1)
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
    if m: return m.group(1)
    m = re.search(r'Mental\s+[Hh]ealth\s+[Tt]herapy\s+visits\s*\n\s*(\$\d+)\s*copay', text)
    if m: return m.group(1)
    m = re.search(r'Outpatient\s+Mental\s+Health\s+Services[^\n]*?\n?\s*:\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'Outpatient\s+Mental\s+Health\s+Services[^\n]*?\n\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m: return m.group(1)
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
    if m: return m.group(1)
    m = re.search(r'covers\s+many\s+preventive\s+services\s+at\s+no\s+cost', text, re.IGNORECASE)
    if m: return "$0"
    m = re.search(r'PREVENTIVE\s+CARE\s*\n\s*(\$\d+)\s*copay', text, re.IGNORECASE)
    if m: return m.group(1)
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

    # Tier costs
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
    }