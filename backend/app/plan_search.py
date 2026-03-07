"""
Plan Search Module
Searches Medicare Advantage plans from SQLite DB and ACA Marketplace plans
from the CMS Marketplace API (marketplace.api.healthcare.gov).

Medicare: Queries local plan_formulary + PBP benefit tables by state/county.
U65 (ACA): Proxies to CMS Marketplace API for under-65 individual/family plans.
"""

import logging
import os
import sqlite3
import threading
from typing import Optional

import requests

log = logging.getLogger(__name__)

# Reuse the same DB path logic from cms_lookup
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
DEFAULT_DB = None
for _candidate in [
    os.path.join(_THIS_DIR, "cms_benefits.db"),
    os.path.join(_PARENT_DIR, "cms_benefits.db"),
]:
    if os.path.isfile(_candidate):
        DEFAULT_DB = _candidate
        break
if DEFAULT_DB is None:
    DEFAULT_DB = os.path.join(_PARENT_DIR, "cms_benefits.db")

CMS_MARKETPLACE_API = "https://marketplace.api.healthcare.gov/api/v1"
CMS_MARKETPLACE_API_KEY = os.environ.get("CMS_MARKETPLACE_API_KEY", "")


# ── Zip-to-County via CMS Marketplace API ────────────────────────────────────

def get_counties_by_zip(zipcode: str) -> list[dict]:
    """
    Get counties for a zip code using the CMS Marketplace API.
    Returns list of {fips, name, state} dicts.
    Works for both Medicare and U65 flows.
    """
    try:
        params = {}
        headers = {"Accept": "application/json"}
        if CMS_MARKETPLACE_API_KEY:
            params["apikey"] = CMS_MARKETPLACE_API_KEY
        resp = requests.get(
            f"{CMS_MARKETPLACE_API}/counties/by/zip/{zipcode}",
            headers=headers,
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        counties = data.get("counties", [])
        return [
            {
                "fips": c.get("fips"),
                "name": c.get("name"),
                "state": c.get("state"),
            }
            for c in counties
        ]
    except Exception as e:
        log.warning("County lookup failed for zip %s: %s", zipcode, type(e).__name__)
        return []


# ── Medicare Plan Search ─────────────────────────────────────────────────────

class MedicarePlanSearch:
    """Search Medicare Advantage plans from the CMS SQLite database."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.environ.get("CMS_DB_PATH", DEFAULT_DB)
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            if not os.path.isfile(self.db_path):
                raise FileNotFoundError(f"CMS database not found: {self.db_path}")
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _query_all(self, sql: str, params: tuple) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def _query_one(self, sql: str, params: tuple) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        if val is None or str(val).strip() == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def search_by_state(self, state: str, county_code: str = None,
                        limit: int = 50) -> list[dict]:
        """
        Search Medicare Advantage plans by state (and optionally county).
        Returns plan cards with key benefit highlights.
        """
        state = state.upper().strip()

        if county_code:
            plans = self._query_all(
                """SELECT DISTINCT pf.contract_id, pf.plan_id, pf.contract_name,
                          pf.plan_name, pf.premium, pf.deductible, pf.state,
                          pf.county_code, pf.snp
                   FROM plan_formulary pf
                   WHERE pf.state = ? AND pf.county_code = ?
                   ORDER BY pf.premium ASC
                   LIMIT ?""",
                (state, county_code, limit),
            )
        else:
            plans = self._query_all(
                """SELECT DISTINCT pf.contract_id, pf.plan_id, pf.contract_name,
                          pf.plan_name, pf.premium, pf.deductible, pf.state,
                          pf.county_code, pf.snp
                   FROM plan_formulary pf
                   WHERE pf.state = ?
                   ORDER BY pf.premium ASC
                   LIMIT ?""",
                (state, limit),
            )

        # Deduplicate by contract_id + plan_id
        seen = set()
        unique_plans = []
        for p in plans:
            key = f"{p['contract_id']}-{p['plan_id']}"
            if key not in seen:
                seen.add(key)
                unique_plans.append(p)

        # Batch-fetch all benefit data in a single JOIN query
        # instead of 6 individual queries per plan (N+1 → 1)
        if not unique_plans:
            return []

        plan_keys = [(p["contract_id"], p["plan_id"]) for p in unique_plans]
        placeholders = " OR ".join(
            ["(sa.pbp_a_hnumber = ? AND sa.pbp_a_plan_identifier = ?)"] * len(plan_keys)
        )
        flat_params = [v for pair in plan_keys for v in pair]

        benefits_sql = f"""
            SELECT sa.pbp_a_hnumber AS contract_id,
                   sa.pbp_a_plan_identifier AS plan_id,
                   sa.pbp_a_org_marketing_name, sa.pbp_a_plan_name, sa.pbp_a_plan_type,
                   b7.pbp_b7a_copay_amt_mc_min, b7.pbp_b7b_copay_mc_amt_min,
                   sd.pbp_d_mplusc_bonly_premium,
                   b16.pbp_b16b_copay_ov_amt, b16.pbp_b16b_copay_ov_amt_min,
                   b16.pbp_b16c_maxplan_cmp_amt, b16.pbp_b16c_maxenr_cmp_amt,
                   b17.pbp_b17a_bendesc_yn,
                   b13.pbp_b13b_bendesc_otc, b13.pbp_b13b_maxplan_amt, b13.pbp_b13b_maxenr_amt
            FROM pbp_section_a sa
            LEFT JOIN pbp_b7_health_prof b7
                ON b7.pbp_a_hnumber = sa.pbp_a_hnumber
               AND b7.pbp_a_plan_identifier = sa.pbp_a_plan_identifier
            LEFT JOIN pbp_section_d sd
                ON sd.pbp_a_hnumber = sa.pbp_a_hnumber
               AND sd.pbp_a_plan_identifier = sa.pbp_a_plan_identifier
            LEFT JOIN pbp_b16_dental b16
                ON b16.pbp_a_hnumber = sa.pbp_a_hnumber
               AND b16.pbp_a_plan_identifier = sa.pbp_a_plan_identifier
            LEFT JOIN pbp_b17_vision b17
                ON b17.pbp_a_hnumber = sa.pbp_a_hnumber
               AND b17.pbp_a_plan_identifier = sa.pbp_a_plan_identifier
            LEFT JOIN pbp_b13_other_services b13
                ON b13.pbp_a_hnumber = sa.pbp_a_hnumber
               AND b13.pbp_a_plan_identifier = sa.pbp_a_plan_identifier
            WHERE {placeholders}
        """
        benefit_rows = self._query_all(benefits_sql, tuple(flat_params))

        # Index benefit rows by plan key
        benefits_by_key = {}
        for row in benefit_rows:
            key = f"{row['contract_id']}-{row['plan_id']}"
            if key not in benefits_by_key:
                benefits_by_key[key] = row

        plan_type_map = {
            "1": "HMO", "2": "HMOPOS", "3": "Local PPO",
            "4": "Regional PPO", "5": "PFFS", "6": "Cost",
            "9": "ESRD",
        }

        results = []
        for p in unique_plans:
            plan_number = f"{p['contract_id']}-{p['plan_id']}"
            card = {
                "plan_number": plan_number,
                "plan_name": p.get("plan_name", ""),
                "org_name": p.get("contract_name", ""),
                "monthly_premium": self._safe_float(p.get("premium")),
                "annual_deductible": self._safe_float(p.get("deductible")),
                "state": p.get("state", ""),
                "snp_type": p.get("snp", ""),
                "type": "medicare",
            }

            b = benefits_by_key.get(plan_number)
            if b:
                # Section A
                if b.get("pbp_a_org_marketing_name"):
                    card["org_name"] = b["pbp_a_org_marketing_name"]
                if b.get("pbp_a_plan_name"):
                    card["plan_name"] = b["pbp_a_plan_name"]
                pt = str(b.get("pbp_a_plan_type", "")).strip()
                card["plan_type"] = plan_type_map.get(pt, pt)

                # Medical copays (b7)
                pcp = self._safe_float(b.get("pbp_b7a_copay_amt_mc_min"))
                spec = self._safe_float(b.get("pbp_b7b_copay_mc_amt_min"))
                card["pcp_copay"] = f"${pcp:.0f}" if pcp is not None else None
                card["specialist_copay"] = f"${spec:.0f}" if spec is not None else None

                # Part B giveback (section_d)
                gb = self._safe_float(b.get("pbp_d_mplusc_bonly_premium"))
                if gb and gb > 0:
                    card["part_b_giveback"] = f"${gb:.2f}"

                # Dental (b16)
                if b.get("pbp_b16b_copay_ov_amt") is not None or b.get("pbp_b16c_maxplan_cmp_amt") is not None:
                    card["has_dental"] = True
                    cmp_max = self._safe_float(
                        b.get("pbp_b16c_maxplan_cmp_amt") or b.get("pbp_b16c_maxenr_cmp_amt")
                    )
                    if cmp_max:
                        card["dental_max"] = f"${cmp_max:.0f}"

                # Vision (b17)
                if str(b.get("pbp_b17a_bendesc_yn", "")).strip().upper() in ("Y", "1"):
                    card["has_vision"] = True

                # OTC (b13)
                if str(b.get("pbp_b13b_bendesc_otc", "")).strip().upper() in ("Y", "1"):
                    card["has_otc"] = True
                    otc_amt = self._safe_float(
                        b.get("pbp_b13b_maxplan_amt") or b.get("pbp_b13b_maxenr_amt")
                    )
                    if otc_amt and otc_amt > 0:
                        card["otc_amount"] = f"${otc_amt:.0f}"

            results.append(card)

        return results

    def search_by_zip(self, zipcode: str, limit: int = 50) -> dict:
        """
        Search Medicare plans by zip code.
        First resolves zip → county via CMS API, then queries local DB.
        """
        counties = get_counties_by_zip(zipcode)
        if not counties:
            return {"error": "No counties found for this zip code", "plans": []}

        # If multiple counties, use the first one (most common case)
        county = counties[0]
        state = county["state"]
        fips = county["fips"]

        # CMS county_code in the DB might be the 3-digit county portion of FIPS
        # FIPS is 5 digits: 2-digit state + 3-digit county
        county_code_3 = fips[-3:] if fips and len(fips) >= 3 else None

        # Try with county code first, fall back to state-only
        plans = self.search_by_state(state, county_code=county_code_3, limit=limit)
        if not plans:
            plans = self.search_by_state(state, limit=limit)

        return {
            "county": county,
            "all_counties": counties if len(counties) > 1 else None,
            "plans": plans,
            "total": len(plans),
        }


# ── U65 ACA Marketplace Search ──────────────────────────────────────────────

def search_marketplace_plans(
    zipcode: str,
    fips: str = None,
    age: int = 30,
    household_income: int = None,
    household_size: int = 1,
    market: str = "Individual",
    limit: int = 50,
) -> dict:
    """
    Search ACA Marketplace plans via CMS Marketplace API.
    Returns plan cards with premium, deductible, metal level.
    """
    # Step 1: Resolve zip to county if fips not provided
    if not fips:
        counties = get_counties_by_zip(zipcode)
        if not counties:
            return {"error": "No counties found for this zip code", "plans": []}
        fips = counties[0]["fips"]
        county_info = counties[0]
    else:
        county_info = {"fips": fips}

    # Step 2: Build the plan search request
    household = {
        "income": household_income or 50000,
        "people": [
            {
                "age": age,
                "aptc_eligible": True,
                "gender": "Male",
                "uses_tobacco": False,
            }
        ],
    }

    # Add additional household members if household_size > 1
    for _ in range(1, household_size):
        household["people"].append({
            "age": age,
            "aptc_eligible": True,
            "gender": "Female",
            "uses_tobacco": False,
        })

    search_body = {
        "household": household,
        "market": market,
        "place": {
            "countyfips": fips,
            "state": fips[:2] if fips else "",
            "zipcode": zipcode,
        },
        "year": 2026,
        "limit": limit,
        "offset": 0,
        "order": "asc",
        "sort": "premium",
    }

    try:
        url = f"{CMS_MARKETPLACE_API}/plans/search"
        _mkt_params = {"apikey": CMS_MARKETPLACE_API_KEY} if CMS_MARKETPLACE_API_KEY else {}
        _mkt_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        resp = requests.post(
            url,
            json=search_body,
            params=_mkt_params,
            headers=_mkt_headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.HTTPError as e:
        log.warning("Marketplace API error for zip %s: %s", zipcode, type(e).__name__)
        # Try with year 2025 if 2026 fails
        search_body["year"] = 2025
        try:
            resp = requests.post(
                f"{CMS_MARKETPLACE_API}/plans/search",
                json=search_body,
                params=_mkt_params,
                headers=_mkt_headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e2:
            log.error("Marketplace API fallback failed: %s", type(e2).__name__)
            return {"error": "Unable to search marketplace plans", "plans": []}
    except Exception as e:
        log.error("Marketplace API request failed: %s", type(e).__name__)
        return {"error": "Unable to search marketplace plans", "plans": []}

    # Step 3: Transform response into plan cards
    raw_plans = data.get("plans", [])
    plans = []
    for p in raw_plans:
        card = {
            "plan_id": p.get("id", ""),
            "plan_name": p.get("name", ""),
            "org_name": p.get("issuer", {}).get("name", ""),
            "monthly_premium": p.get("premium", None),
            "premium_with_credit": p.get("premium_w_credit", None),
            "annual_deductible": None,
            "metal_level": p.get("metal_level", ""),
            "plan_type": p.get("type", ""),
            "state": fips[:2] if fips else "",
            "type": "u65",
        }

        # Extract deductible from deductibles array
        deductibles = p.get("deductibles", [])
        for d in deductibles:
            if d.get("type") == "Medical EHB Deductible" and d.get("network_tier") == "In-Network":
                card["annual_deductible"] = d.get("amount")
                break
        if card["annual_deductible"] is None and deductibles:
            card["annual_deductible"] = deductibles[0].get("amount")

        # MOOP
        moops = p.get("moops", [])
        for m in moops:
            if m.get("network_tier") == "In-Network":
                card["moop"] = m.get("amount")
                break

        # Benefits highlights
        benefits = p.get("benefits", [])
        for b in benefits:
            name = b.get("name", "")
            if "Primary Care" in name:
                copay = b.get("cost_sharings", [{}])
                if copay:
                    amt = copay[0].get("copay_amount")
                    if amt is not None:
                        card["pcp_copay"] = f"${amt:.0f}"
            elif "Specialist" in name:
                copay = b.get("cost_sharings", [{}])
                if copay:
                    amt = copay[0].get("copay_amount")
                    if amt is not None:
                        card["specialist_copay"] = f"${amt:.0f}"

        # Quality rating
        card["quality_rating"] = p.get("quality_rating", {}).get("global_rating")

        # HSA eligible
        card["hsa_eligible"] = p.get("hsa_eligible", False)

        plans.append(card)

    return {
        "county": county_info,
        "plans": plans,
        "total": data.get("total", len(plans)),
    }
