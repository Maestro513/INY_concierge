#!/usr/bin/env python3
"""
INY Retention Pipeline
----------------------
Takes CMS_Results output from v28 script and does everything:
  1. Converts CMS results -> clean mismatches (fixes PBP padding, filters ACA)
  2. Extracts plan benefits from SOB JSONs via Claude API (cached)
  3. Compares old plan vs new plan -> generates agent cheat sheets
  4. Pushes status + comparison notes to Zoho CRM
Usage:
  python retention_pipeline.py CMS_Results_20260223_031947.csv
  python retention_pipeline.py CMS_Results.csv --skip-zoho
  python retention_pipeline.py CMS_Results.csv --zoho-file active_clients.csv
  python retention_pipeline.py CMS_Results.csv --dry-run
Environment Variables:
  ANTHROPIC_API_KEY    Claude API key for benefit extraction
  ZOHO_ACCESS_TOKEN    Zoho OAuth token
  ZOHO_MODULE          Zoho module name (default: Clients)
  RENDER_API_URL       Render backend URL (default: https://iny-concierge.onrender.com)
"""
import json, csv, os, re, sys, logging, requests
import pandas as pd
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"pipeline_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger(__name__)
# =============================================================================
# CONFIG
# =============================================================================
RENDER_API_URL = os.environ.get("RENDER_API_URL", "https://iny-concierge.onrender.com")
BENEFITS_CACHE = os.environ.get("BENEFITS_CACHE", "./benefits_cache.json")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
ZOHO_ACCESS_TOKEN = os.environ.get("ZOHO_ACCESS_TOKEN", "")
ZOHO_REFRESH_TOKEN = os.environ.get("ZOHO_REFRESH_TOKEN", "")
ZOHO_CLIENT_ID = os.environ.get("ZOHO_CLIENT_ID", "")
ZOHO_CLIENT_SECRET = os.environ.get("ZOHO_CLIENT_SECRET", "")
ZOHO_API_BASE = os.environ.get("ZOHO_API_BASE", "https://www.zohoapis.com/crm/v2")
ZOHO_MODULE = "Contacts"
STATUS_MISMATCH = "Mismatch - Pending Review"
COMPARISON_FIELD = "Plan_Comparison_Notes"
RETENTION_SCORE_FIELD = "Retention_Score"
LOSING_BENEFITS_FIELD = "Losing_Benefits"
OUTPUT_DIR = "./pipeline_output"
# =============================================================================
# STEP 1: CONVERT CMS RESULTS
# =============================================================================
def pad_pbp(pbp_val):
    pbp_str = str(pbp_val).strip()
    if pbp_str.endswith('.0'): pbp_str = pbp_str[:-2]
    return pbp_str.zfill(3)
def normalize_plan_id(plan_id):
    pid = str(plan_id).strip().upper()
    if pid in ('NAN', '', 'NONE', 'ACA'): return ''
    if pid.endswith('-000'): pid = pid[:-4]
    return pid
def convert_cms_results(cms_file, zoho_file=None):
    logger.info(f"Loading CMS results from {cms_file}")
    df = pd.read_csv(cms_file, dtype={'PBP': str, 'Contract': str, 'Plan_Number': str})
    logger.info(f"Total records: {len(df)}")
    mismatches = df[df['Match'] == 'X'].copy()
    logger.info(f"Mismatches found: {len(mismatches)}")
    if mismatches.empty: return []
    record_id_map = {}
    if zoho_file and os.path.exists(zoho_file):
        zoho_df = pd.read_csv(zoho_file, dtype=str)
        medicare_col = record_col = None
        for col in zoho_df.columns:
            cl = col.lower()
            if 'medicare' in cl or 'mbi' in cl: medicare_col = col
            if 'record' in cl and 'id' in cl: record_col = col
        if medicare_col and record_col:
            for _, row in zoho_df.iterrows():
                mbi = str(row.get(medicare_col, '')).strip().upper()
                rid = str(row.get(record_col, '')).strip()
                if mbi and rid and mbi != 'NAN': record_id_map[mbi] = rid
            logger.info(f"Loaded {len(record_id_map)} record ID mappings from {zoho_file}")
    results, dropped = [], 0
    for _, row in mismatches.iterrows():
        current_plan = normalize_plan_id(row['Plan_Number'])
        contract = str(row['Contract']).strip().upper()
        pbp = pad_pbp(row['PBP'])
        new_plan = f"{contract}-{pbp}" if contract and contract not in ('NAN', '') else ''
        if not current_plan or not new_plan:
            dropped += 1
            logger.warning(f"  Skipped: {row['Client_Name']} -- current: {row['Plan_Number']}, CMS: {contract}-{row.get('PBP', '?')}")
            continue
        medicare_num = str(row.get('MediCARE_Number', '')).strip().upper()
        results.append({
            'record_id': record_id_map.get(medicare_num, ''),
            'client_name': row['Client_Name'],
            'medicare_number': medicare_num,
            'current_plan': current_plan,
            'new_plan': new_plan,
        })
    if dropped: logger.warning(f"Dropped {dropped} mismatches with missing plan IDs (ACA/nan)")
    matched = sum(1 for r in results if r['record_id'])
    logger.info(f"Valid mismatches: {len(results)} ({matched} matched to Zoho record IDs)")
    if not matched and record_id_map:
        logger.warning("No Medicare numbers matched! Check if MediCARE Number column matches between files.")
    return results
# =============================================================================
# STEP 2: EXTRACT PLAN BENEFITS FROM SOB JSONS (via Render API)
# =============================================================================
BENEFIT_KEYWORDS = [
    'giveback', 'give back', 'part b premium', 'premium reduction',
    'over-the-counter', 'over the counter', 'otc', 'spending card', 'allowance',
    'out-of-pocket', 'moop', 'maximum out',
    'copay', 'copayment', 'coinsurance', 'cost sharing',
    'primary care', 'specialist', 'pcp', 'doctor visit',
    'deductible', 'inpatient', 'emergency',
]
EXTRACTION_PROMPT = """You are extracting Medicare Advantage plan benefit data from a Summary of Benefits document.
Given the following text chunks from plan {plan_id} ({carrier}), extract EXACTLY these fields.
Return ONLY valid JSON -- no markdown, no explanation, no extra text.
Fields to extract:
- part_b_giveback: Monthly Part B premium reduction/giveback amount in dollars. "$0" if not mentioned or not offered.
- otc_allowance: Over-the-counter allowance amount AND frequency (monthly/quarterly/yearly). Include the dollar amount and period. "$0" if not offered.
- moop: Maximum Out-of-Pocket amount (in-network). Dollar amount only.
- pcp_copay: Primary care provider office visit copay. Dollar amount like "$0" or "$20". If coinsurance, write like "$0 or 20% coinsurance".
- specialist_copay: Specialist office visit copay. Dollar amount like "$40". If coinsurance, write like "$40 or 20% coinsurance".
- monthly_premium: Monthly plan premium. "$0" if zero premium plan.
- drug_deductible: Part D pharmacy deductible amount. "$0" if none.
- inpatient_copay: Inpatient hospital copay per day or per admission. Include the dollar amount like "$275 per day" or "$350 per admission".
- emergency_copay: Emergency room copay. Dollar amount like "$90".
IMPORTANT: Always include a dollar amount even if there are conditions. For example write "$0 with referral" not just "with referral".
If a value has multiple tiers, include both values separated by " or ".
If a field truly cannot be found anywhere in the text, use "not found".
PLAN TEXT CHUNKS:
{chunks_text}
Return ONLY the JSON object:"""
def load_cache():
    if os.path.exists(BENEFITS_CACHE):
        with open(BENEFITS_CACHE, 'r') as f: return json.load(f)
    return {}
def save_cache(cache):
    with open(BENEFITS_CACHE, 'w') as f: json.dump(cache, f, indent=2)
def cache_key(plan_id):
    pid = plan_id.strip().upper()
    if re.match(r'^[HR]\d{3,4}-\d{3}-000$', pid): pid = pid[:-4]
    return pid
def load_plan_json(plan_id):
    """Fetch plan SOB JSON from the Render backend API."""
    pid = normalize_plan_id(plan_id)
    # Try normalized ID first, then with -000 suffix
    for variant in [pid, f"{pid}-000"]:
        url = f"{RENDER_API_URL}/sob/raw/{variant}"
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                logger.info(f"  Fetched {variant} from Render")
                return resp.json()
        except requests.RequestException as e:
            logger.warning(f"  Request failed for {variant}: {e}")
    logger.warning(f"  Not found on Render: {plan_id}")
    return None
def filter_chunks(chunks, max_n=15):
    scored = []
    for i, c in enumerate(chunks):
        text = c if isinstance(c, str) else c.get("text", "")
        cl = text.lower()
        score = sum(1 for kw in BENEFIT_KEYWORDS if kw in cl)
        if score > 0: scored.append((score, i, text))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = sorted(scored[:max_n], key=lambda x: x[1])
    return [c for _, _, c in selected]
def extract_benefits(plan_id, force=False):
    cache = load_cache()
    key = cache_key(plan_id)
    if key in cache and not force: return cache[key]
    data = load_plan_json(plan_id)
    if not data:
        logger.warning(f"No SOB JSON found for {plan_id}")
        return None
    carrier = data.get("carrier", "Unknown")
    chunks = data.get("chunks", [])
    if not chunks: return None
    relevant = filter_chunks(chunks) or chunks[:15]
    chunks_text = "\n\n---CHUNK BREAK---\n\n".join(relevant)
    if len(chunks_text) > 50000: chunks_text = chunks_text[:50000]
    logger.info(f"Extracting benefits for {plan_id} ({carrier}) -- {len(relevant)} chunks")
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=ANTHROPIC_MODEL, max_tokens=1000,
        messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(
            plan_id=plan_id, carrier=carrier, chunks_text=chunks_text)}]
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    try:
        benefits = json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse response for {plan_id}: {text[:200]}")
        benefits = {"error": "parse_failed"}
    benefits["_meta"] = {"plan_id": plan_id, "carrier": carrier}
    cache[key] = benefits
    save_cache(cache)
    return benefits
# =============================================================================
# STEP 3: COMPARE PLANS
# =============================================================================
COMPARE_FIELDS = {
    "part_b_giveback":  {"label": "Part B Giveback",   "lower_better": False, "mult": 12},
    "otc_allowance":    {"label": "OTC Allowance",     "lower_better": False, "mult": None, "is_otc": True},
    "moop":             {"label": "Max Out-of-Pocket", "lower_better": True,  "mult": 1},
    "pcp_copay":        {"label": "PCP Copay",         "lower_better": True,  "mult": None},
    "specialist_copay": {"label": "Specialist Copay",  "lower_better": True,  "mult": None},
    "monthly_premium":  {"label": "Monthly Premium",   "lower_better": True,  "mult": 12},
    "drug_deductible":  {"label": "Drug Deductible",   "lower_better": True,  "mult": 1},
    "inpatient_copay":  {"label": "Inpatient Copay",   "lower_better": True,  "mult": None},
    "emergency_copay":  {"label": "Emergency Copay",   "lower_better": True,  "mult": None},
}
def parse_dollar(value):
    if not value or str(value).lower() in ('not found', 'n/a', 'none', ''): return None
    m = re.search(r'\$[\d,]+(?:\.\d{2})?', str(value))
    if m:
        try: return float(m.group().replace('$','').replace(',',''))
        except: return None
    # Also try bare numbers like "0" or "275"
    m2 = re.match(r'^\s*(\d+(?:\.\d{2})?)\s*$', str(value).strip())
    if m2:
        try: return float(m2.group(1))
        except: return None
    return None
def parse_otc(value):
    amt = parse_dollar(value)
    if amt is None: return None
    vl = str(value).lower()
    if 'month' in vl: return {"annual": amt * 12}
    elif any(q in vl for q in ['quarter', '/qtr', 'qtr']): return {"annual": amt * 4}
    elif any(y in vl for y in ['year', 'annual']): return {"annual": amt}
    return {"annual": amt * 12}
def compare_plans(current_id, new_id):
    cur = extract_benefits(current_id)
    new = extract_benefits(new_id)
    result = {
        "current_plan": current_id, "new_plan": new_id,
        "cur_carrier": cur.get("_meta",{}).get("carrier","?") if cur else "?",
        "new_carrier": new.get("_meta",{}).get("carrier","?") if new else "?",
        "fields": {}, "gains": [], "losses": [], "neutral": [], "review": [],
        "annual_impact": 0, "errors": [],
    }
    if not cur: result["errors"].append(f"No SOB data for {current_id}")
    if not new: result["errors"].append(f"No SOB data for {new_id}")
    if not cur or not new:
        result["retention_score"] = "UNKNOWN"
        result["agent_summary"] = build_summary(result)
        return result
    for key, cfg in COMPARE_FIELDS.items():
        cr, nr = cur.get(key, "not found"), new.get(key, "not found")
        field = {"label": cfg["label"], "current": cr, "new": nr, "impact": "unknown"}
        if cfg.get("is_otc"):
            co, no = parse_otc(cr), parse_otc(nr)
            if co and no:
                delta = no["annual"] - co["annual"]
                field["delta"] = f"{'+'if delta>=0 else ''}{delta:,.0f}/yr"
                if delta > 0:
                    field["impact"] = "gain"
                    result["gains"].append(f"{cfg['label']}: {cr} -> {nr} (+${delta:,.0f}/yr)")
                elif delta < 0:
                    field["impact"] = "loss"
                    result["losses"].append(f"{cfg['label']}: {cr} -> {nr} (-${abs(delta):,.0f}/yr)")
                else:
                    field["impact"] = "neutral"
                    result["neutral"].append(f"{cfg['label']}: {cr} (no change)")
                result["annual_impact"] += delta
            else:
                cr_d = cr if str(cr).lower() != "not found" else "not found"
                nr_d = nr if str(nr).lower() != "not found" else "not found"
                if cr_d != "not found" or nr_d != "not found":
                    result["review"].append(f"{cfg['label']}: \"{cr_d}\" vs \"{nr_d}\"")
        else:
            cv, nv = parse_dollar(cr), parse_dollar(nr)
            if cv is not None and nv is not None:
                rd = nv - cv
                sfx = "/mo" if cfg.get("mult") == 12 else ""
                field["delta"] = f"{'+'if rd>=0 else ''}${rd:,.0f}{sfx}"
                if cfg["lower_better"]:
                    field["impact"] = "gain" if rd < 0 else ("loss" if rd > 0 else "neutral")
                else:
                    field["impact"] = "gain" if rd > 0 else ("loss" if rd < 0 else "neutral")
                if cfg.get("mult"):
                    ann = rd * cfg["mult"]
                    result["annual_impact"] += (-ann if cfg["lower_better"] else ann)
                if field["impact"] == "gain":
                    result["gains"].append(f"{cfg['label']}: {cr} -> {nr} ({field['delta']})")
                elif field["impact"] == "loss":
                    result["losses"].append(f"{cfg['label']}: {cr} -> {nr} ({field['delta']})")
                else:
                    result["neutral"].append(f"{cfg['label']}: {cr} (no change)")
            else:
                cr_d = cr if str(cr).lower() != "not found" else "not found"
                nr_d = nr if str(nr).lower() != "not found" else "not found"
                if cr_d != "not found" or nr_d != "not found":
                    result["review"].append(f"{cfg['label']}: \"{cr_d}\" vs \"{nr_d}\"")
        result["fields"][key] = field
    l, g, a = len(result["losses"]), len(result["gains"]), result["annual_impact"]
    if l > g and a < -500: result["retention_score"] = "HIGH"
    elif l > g or a < 0: result["retention_score"] = "MEDIUM"
    elif g > l and a > 500: result["retention_score"] = "LOW"
    else: result["retention_score"] = "MEDIUM"
    result["agent_summary"] = build_summary(result)
    return result
def build_summary(c):
    lines = [f"Switching from {c['current_plan']} ({c['cur_carrier']}) -> {c['new_plan']} ({c['new_carrier']})", ""]
    for e in c.get("errors", []): lines.append(f"WARNING: {e}"); lines.append("")
    if c["losses"]:
        lines.append("CLIENT LOSES:")
        for l in c["losses"]: lines.append(f"  - {l}")
        lines.append("")
    if c["gains"]:
        lines.append("CLIENT GAINS:")
        for g in c["gains"]: lines.append(f"  - {g}")
        lines.append("")
    if c.get("neutral"):
        lines.append("NO CHANGE:")
        for n in c["neutral"]: lines.append(f"  - {n}")
        lines.append("")
    if c.get("review"):
        lines.append("REVIEW MANUALLY:")
        for r in c["review"]: lines.append(f"  - {r}")
        lines.append("")
    a = c.get("annual_impact", 0)
    if a != 0: lines.append(f"Estimated annual impact: ${abs(a):,.0f} {'WORSE' if a < 0 else 'BETTER'} off")
    s = c.get("retention_score", "UNKNOWN")
    if s == "HIGH": lines.append("STRONG RETENTION CASE - client loses significantly by switching")
    elif s == "MEDIUM": lines.append("MIXED - review details with client")
    elif s == "LOW": lines.append("WEAK RETENTION - client may be upgrading")
    else: lines.append("UNKNOWN - could not extract one or both plans")
    return "\n".join(lines)
def build_losing_benefits(comp):
    """Build natural-language string of benefits the client loses by switching."""
    fields = comp.get("fields", {})
    parts = []
    for key, fdata in fields.items():
        if fdata.get("impact") != "loss":
            continue
        cur_raw = fdata.get("current", "not found")
        new_raw = fdata.get("new", "not found")
        cv = parse_dollar(cur_raw)
        nv = parse_dollar(new_raw)
        label = fdata.get("label", key)
        if key == "part_b_giveback":
            if cv is not None and nv is not None:
                lost = cv - nv
                parts.append(f"losing ${lost:,.0f}/mo in Part B giveback")
            else:
                parts.append(f"losing Part B giveback")
        elif key == "otc_allowance":
            co = parse_otc(cur_raw)
            no = parse_otc(new_raw)
            if co and no:
                lost = co["annual"] - no["annual"]
                parts.append(f"losing ${lost:,.0f}/yr in OTC")
            else:
                parts.append(f"losing OTC")
        elif key == "moop":
            if cv is not None and nv is not None:
                increase = nv - cv
                parts.append(f"MOOP going up ${increase:,.0f}")
            else:
                parts.append(f"MOOP going up")
        elif key == "pcp_copay":
            if cv is not None and nv is not None:
                parts.append(f"PCP going from ${cv:,.0f} to ${nv:,.0f}")
            else:
                parts.append(f"PCP copay going up")
        elif key == "specialist_copay":
            if cv is not None and nv is not None:
                parts.append(f"specialist going from ${cv:,.0f} to ${nv:,.0f}")
            else:
                parts.append(f"specialist copay going up")
        elif key == "emergency_copay":
            if cv is not None and nv is not None:
                parts.append(f"ER going from ${cv:,.0f} to ${nv:,.0f}")
            else:
                parts.append(f"ER copay going up")
        elif key == "monthly_premium":
            if cv is not None and nv is not None:
                increase = nv - cv
                parts.append(f"premium going up ${increase:,.0f}/mo")
            else:
                parts.append(f"premium going up")
        elif key == "drug_deductible":
            if cv is not None and nv is not None:
                increase = nv - cv
                parts.append(f"drug deductible going up ${increase:,.0f}")
            else:
                parts.append(f"drug deductible going up")
        elif key == "inpatient_copay":
            if cv is not None and nv is not None:
                parts.append(f"inpatient going from ${cv:,.0f} to ${nv:,.0f}")
            else:
                parts.append(f"inpatient copay going up")
    if not parts:
        return ""
    parts[0] = parts[0][0].upper() + parts[0][1:]
    return ", ".join(parts)
# =============================================================================
# STEP 4: PUSH TO ZOHO
# =============================================================================
def refresh_zoho_token():
    global ZOHO_ACCESS_TOKEN
    try:
        resp = requests.post("https://accounts.zoho.com/oauth/v2/token", data={
            "grant_type": "refresh_token", "client_id": ZOHO_CLIENT_ID,
            "client_secret": ZOHO_CLIENT_SECRET, "refresh_token": ZOHO_REFRESH_TOKEN,
        })
        data = resp.json()
        if "access_token" in data:
            ZOHO_ACCESS_TOKEN = data["access_token"]
            return True
    except: pass
    return False
def find_zoho_record_by_medicare(medicare_number):
    """Search Zoho for a contact by Medicare_Number. Returns record_id or None."""
    if not ZOHO_ACCESS_TOKEN or not medicare_number: return None
    headers = {"Authorization": f"Zoho-oauthtoken {ZOHO_ACCESS_TOKEN}", "Content-Type": "application/json"}
    try:
        url = f"{ZOHO_API_BASE}/{ZOHO_MODULE}/search"
        params = {"criteria": f"(Medicare_Number:equals:{medicare_number})"}
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code == 401:
            if refresh_zoho_token():
                headers["Authorization"] = f"Zoho-oauthtoken {ZOHO_ACCESS_TOKEN}"
                resp = requests.get(url, headers=headers, params=params)
        if resp.status_code == 204: return None
        data = resp.json()
        records = data.get("data", [])
        if records:
            return str(records[0]["id"])
    except Exception as e:
        logger.error(f"Zoho search failed for Medicare {medicare_number}: {e}")
    return None
def update_zoho(medicare_number, note, score, losing_benefits="", cms_found_plan=""):
    if not ZOHO_ACCESS_TOKEN or not medicare_number: return False
    headers = {"Authorization": f"Zoho-oauthtoken {ZOHO_ACCESS_TOKEN}", "Content-Type": "application/json"}
    # Find record by Medicare number
    record_id = find_zoho_record_by_medicare(medicare_number)
    if not record_id:
        logger.warning(f"No Zoho record found for Medicare {medicare_number}")
        return False
    try:
        url = f"{ZOHO_API_BASE}/{ZOHO_MODULE}/{record_id}"
        update_data = {"id": record_id, "Sale_Status": STATUS_MISMATCH, COMPARISON_FIELD: note, RETENTION_SCORE_FIELD: score, LOSING_BENEFITS_FIELD: losing_benefits, "CMS_Found_Plan_Number": cms_found_plan}
        resp = requests.put(url, headers=headers, json={"data": [update_data]})
        if resp.status_code == 401:
            if refresh_zoho_token():
                headers["Authorization"] = f"Zoho-oauthtoken {ZOHO_ACCESS_TOKEN}"
                resp = requests.put(url, headers=headers, json={"data": [update_data]})
        requests.post(f"{url}/Notes", headers=headers, json={"data": [{"Note_Title": "Plan Mismatch - Retention Comparison", "Note_Content": note}]})
        return True
    except Exception as e:
        logger.error(f"Zoho update failed for Medicare {medicare_number}: {e}"); return False
# =============================================================================
# ORCHESTRATOR
# =============================================================================
def run_pipeline(cms_file, zoho_file=None, skip_zoho=False, dry_run=False):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    print(f"\n{'='*60}\nINY RETENTION PIPELINE\n{'='*60}")
    # Wake up Render (free tier spins down)
    print("\nWaking up Render backend...")
    try:
        resp = requests.get(f"{RENDER_API_URL}/health", timeout=60)
        print(f"  Backend is up ({resp.status_code})")
    except requests.RequestException:
        print("  WARNING: Backend may be cold-starting. Continuing anyway...")
    print("\nStep 1: Converting CMS results...")
    mismatches = convert_cms_results(cms_file, zoho_file)
    if not mismatches: print("No mismatches found!"); return
    print(f"\n{len(mismatches)} mismatches:")
    for m in mismatches: print(f"  {m['client_name']:30s} {m['current_plan']:12s} -> {m['new_plan']}")
    if dry_run: print("\n--dry-run. Stopping."); return
    print(f"\nStep 2: Extracting plan benefits...")
    all_ids = set()
    for m in mismatches: all_ids.add(m['current_plan']); all_ids.add(m['new_plan'])
    print(f"  {len(all_ids)} unique plans")
    ok, bad = 0, []
    for pid in sorted(all_ids):
        r = extract_benefits(pid)
        if r and 'error' not in r: ok += 1
        else: bad.append(pid)
    print(f"  {ok} extracted/cached")
    if bad: print(f"  WARNING: {len(bad)} not found: {', '.join(bad)}")
    print(f"\nStep 3: Comparing plans...")
    comparisons = []
    for i, m in enumerate(mismatches, 1):
        comp = compare_plans(m['current_plan'], m['new_plan'])
        losing = build_losing_benefits(comp)
        comparisons.append({**m, "comparison": comp, "agent_summary": comp["agent_summary"], "retention_score": comp["retention_score"], "losing_benefits": losing})
    h = sum(1 for c in comparisons if c["retention_score"]=="HIGH")
    med = sum(1 for c in comparisons if c["retention_score"]=="MEDIUM")
    lo = sum(1 for c in comparisons if c["retention_score"]=="LOW")
    unk = sum(1 for c in comparisons if c["retention_score"]=="UNKNOWN")
    print(f"  Scores: {h} HIGH | {med} MEDIUM | {lo} LOW | {unk} UNKNOWN")
    csv_path = os.path.join(OUTPUT_DIR, f"comparisons_{ts}.csv")
    json_path = os.path.join(OUTPUT_DIR, f"comparisons_{ts}.json")
    with open(json_path, 'w') as f: json.dump(comparisons, f, indent=2, default=str)
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(["Client Name","Record ID","Current Plan","New Plan","Retention Score","Losing Benefits","Losses","Gains","Annual Impact","Agent Summary"])
        for c in comparisons:
            cp = c["comparison"]
            w.writerow([c["client_name"],c["record_id"],c["current_plan"],c["new_plan"],c["retention_score"],
                c.get("losing_benefits",""),
                " | ".join(cp.get("losses",[])), " | ".join(cp.get("gains",[])),
                f"${cp.get('annual_impact',0):,.0f}", c["agent_summary"].replace("\n"," | ")])
    print(f"\nSaved: {csv_path}")
    if not skip_zoho:
        print(f"\nStep 4: Pushing to Zoho...")
        if not ZOHO_ACCESS_TOKEN: print("  No ZOHO_ACCESS_TOKEN -- skipping")
        else:
            s = sum(1 for c in comparisons if c.get("medicare_number") and update_zoho(
                c["medicare_number"], c["agent_summary"], c["retention_score"],
                c.get("losing_benefits",""), c.get("new_plan","")))
            print(f"  {s}/{len(comparisons)} updated")
    else:
        print(f"\nZoho push skipped (--skip-zoho)")
    print(f"\n{'='*60}\nDONE: {len(mismatches)} mismatches, {h} high priority\n{'='*60}")
    if h:
        print(f"\nHIGH PRIORITY CASES:")
        for c in comparisons:
            if c["retention_score"] == "HIGH":
                print(f"\n  {c['client_name']}"); [print(f"    {l}") for l in c["agent_summary"].split("\n")]
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("""
INY RETENTION PIPELINE
======================
Usage:
  python retention_pipeline.py <CMS_Results.csv>                                Full run
  python retention_pipeline.py <CMS_Results.csv> --skip-zoho                    Compare only
  python retention_pipeline.py <CMS_Results.csv> --dry-run                      Just show mismatches
  python retention_pipeline.py <CMS_Results.csv> --zoho-file active_clients.csv Include record IDs
Environment Variables:
  ANTHROPIC_API_KEY    Claude API key
  ZOHO_ACCESS_TOKEN    Zoho OAuth token
  ZOHO_REFRESH_TOKEN   Zoho refresh token
  ZOHO_CLIENT_ID       Zoho client ID
  ZOHO_CLIENT_SECRET   Zoho client secret
  RENDER_API_URL       Backend URL (default: https://iny-concierge.onrender.com)
Full workflow:
  1. python zoho_puller.py
  2. python cms_beneficiary_lookup_v28.py
  3. python retention_pipeline.py CMS_Results_*.csv
        """)
        sys.exit(1)
    cms_file = sys.argv[1]
    skip_zoho = "--skip-zoho" in sys.argv
    dry_run = "--dry-run" in sys.argv
    zoho_file = None
    if "--zoho-file" in sys.argv:
        idx = sys.argv.index("--zoho-file")
        if idx + 1 < len(sys.argv): zoho_file = sys.argv[idx + 1]
    run_pipeline(cms_file, zoho_file=zoho_file, skip_zoho=skip_zoho, dry_run=dry_run)
