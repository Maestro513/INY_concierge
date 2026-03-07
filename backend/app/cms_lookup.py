"""
CMS Benefits Lookup
Queries the SQLite database built by cms_import.py.

Key lookups:
  - get_plan_overview(contract_id, plan_id) → plan name, premium, deductible, MOOP
  - get_drug_coverage(contract_id, plan_id, rxcui) → tier, copay, restrictions
  - get_drug_by_name(drug_name) → RXCUI via NLM RxNorm API
  - get_medical_copays(contract_id, plan_id) → PCP, specialist, ER, urgent care
  - get_dental_benefits(contract_id, plan_id) → preventive + comprehensive dental
  - get_otc_allowance(contract_id, plan_id) → OTC benefit amount + delivery method
  - get_flex_ssbci(contract_id, plan_id) → flex card / SSBCI benefits
  - get_part_b_giveback(contract_id, plan_id) → Part B premium reduction
  - get_vision_benefits(contract_id, plan_id) → eye exams + eyewear
  - get_hearing_benefits(contract_id, plan_id) → hearing exams + hearing aids
  - get_full_benefits(contract_id, plan_id) → all of the above combined
"""

import logging
import os
import sqlite3
import threading
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

# Retry-capable session for transient network errors (RxNorm API)
_retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
_http = requests.Session()
_http.mount("https://", HTTPAdapter(max_retries=_retry_strategy))

# Default DB path — checks both same dir and parent dir
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
    DEFAULT_DB = os.path.join(_PARENT_DIR, "cms_benefits.db")  # fallback


# Known insulin brand names for IRA $35/month cap detection
INSULIN_NAMES = {
    "humalog", "humulin", "lantus", "levemir", "novolog", "novolin",
    "basaglar", "admelog", "apidra", "toujeo", "tresiba", "fiasp",
    "lyumjev", "semglee", "rezvoglar", "insulin lispro", "insulin aspart",
    "insulin glargine", "insulin detemir", "insulin degludec",
    "insulin regular", "insulin nph", "insulin isophane",
}


class CMSLookup:
    """Query CMS benefits data from SQLite."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.environ.get("CMS_DB_PATH", DEFAULT_DB)
        if not os.path.isfile(self.db_path):
            raise FileNotFoundError(f"CMS database not found: {self.db_path}")
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        """Thread-local connection pooling — one connection per thread, reused."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _query_one(self, sql: str, params: tuple) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def _query_all(self, sql: str, params: tuple) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_plan_number(plan_number: str) -> tuple[str, str, str]:
        """
        Parse plan number like 'H1036-077' or 'H1036-077-000' into
        (contract_id, plan_id, segment_id).
        """
        parts = plan_number.strip().upper().replace(" ", "").split("-")
        contract_id = parts[0] if len(parts) > 0 else ""
        plan_id = parts[1] if len(parts) > 1 else "000"
        segment_id = parts[2] if len(parts) > 2 else "000"

        # PBP files use '0' for segment, PUF uses '000'
        return contract_id, plan_id, segment_id

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        """Convert to float, return None if empty/invalid."""
        if val is None or str(val).strip() == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _yn_to_bool(val) -> Optional[bool]:
        """Convert Y/N/1/2 to bool. CMS uses 1=Yes, 2=No in PBP files."""
        if val is None or str(val).strip() == "":
            return None
        v = str(val).strip().upper()
        if v in ("Y", "1"):
            return True
        if v in ("N", "2"):
            return False
        return None

    @staticmethod
    def _is_insulin(drug_name: str) -> bool:
        """Check if a drug name is an insulin product (eligible for IRA $35 cap)."""
        name_lower = drug_name.strip().lower()
        return any(ins in name_lower for ins in INSULIN_NAMES)

    # ── Plan Overview ─────────────────────────────────────────────────────────

    def get_plan_overview(self, plan_number: str) -> Optional[dict]:
        """
        Get plan name, org, premium, deductible from plan_formulary + pbp_section_a.
        """
        cid, pid, seg = self._parse_plan_number(plan_number)

        # From formulary PUF
        puf = self._query_one(
            """SELECT contract_id, plan_id, contract_name, plan_name,
                      formulary_id, premium, deductible, state, county_code, snp
               FROM plan_formulary
               WHERE contract_id = ? AND plan_id = ?
               LIMIT 1""",
            (cid, pid)
        )

        # From PBP Section A (plan metadata)
        section_a = self._query_one(
            """SELECT pbp_a_org_name, pbp_a_org_marketing_name, pbp_a_plan_name,
                      pbp_a_special_need_flag, pbp_a_plan_type,
                      pbp_a_curmbr_phone, pbp_a_prombr_phone
               FROM pbp_section_a
               WHERE pbp_a_hnumber = ? AND pbp_a_plan_identifier = ?
               LIMIT 1""",
            (cid, pid)
        )

        if not puf and not section_a:
            return None

        result = {
            "contract_id": cid,
            "plan_id": pid,
            "plan_name": "",
            "org_name": "",
            "formulary_id": "",
            "monthly_premium": None,
            "annual_deductible": None,
            "snp_type": "",
            "state": "",
            "member_phone": "",
        }

        if puf:
            result["plan_name"] = puf.get("plan_name", "")
            result["org_name"] = puf.get("contract_name", "")
            result["formulary_id"] = puf.get("formulary_id", "")
            result["monthly_premium"] = self._safe_float(puf.get("premium"))
            result["annual_deductible"] = self._safe_float(puf.get("deductible"))
            result["snp_type"] = puf.get("snp", "")
            result["state"] = puf.get("state", "")

        if section_a:
            if not result["plan_name"]:
                result["plan_name"] = section_a.get("pbp_a_plan_name", "")
            if not result["org_name"]:
                result["org_name"] = (section_a.get("pbp_a_org_marketing_name") or
                                      section_a.get("pbp_a_org_name", ""))
            result["member_phone"] = section_a.get("pbp_a_curmbr_phone", "")

        return result

    # ── Drug Coverage ─────────────────────────────────────────────────────────

    def get_drug_coverage(self, plan_number: str, rxcui: str,
                          days_supply: int = 30) -> Optional[dict]:
        """
        Look up a drug by RXCUI for a given plan.
        Returns tier, copay, and restrictions.
        days_supply: 30/60/90 — maps to CMS codes 1/2/3.
        """
        cid, pid, _ = self._parse_plan_number(plan_number)

        # Step 1: Plan → Formulary ID
        puf = self._query_one(
            "SELECT formulary_id FROM plan_formulary WHERE contract_id = ? AND plan_id = ? LIMIT 1",
            (cid, pid)
        )
        if not puf:
            return None

        formulary_id = puf["formulary_id"]

        # Step 2: Formulary + RXCUI → tier + restrictions
        drug = self._query_one(
            """SELECT tier_level_value, prior_authorization_yn, step_therapy_yn,
                      quantity_limit_yn, quantity_limit_amount, quantity_limit_days
               FROM formulary_drugs
               WHERE formulary_id = ? AND rxcui = ?
               LIMIT 1""",
            (formulary_id, rxcui)
        )
        if not drug:
            return None

        tier = int(drug["tier_level_value"]) if drug["tier_level_value"] else None

        # Step 3: Tier → copay from beneficiary_cost
        # Map days_supply to CMS code: 30=1, 60=2, 90=3
        ds_code = '1'
        if days_supply >= 90:
            ds_code = '3'
        elif days_supply >= 60:
            ds_code = '2'

        # Try requested days_supply first, fall back to 30-day
        cost = None
        for try_ds in ([ds_code, '1'] if ds_code != '1' else ['1']):
            cost = self._query_one(
                """SELECT cost_type_pref, cost_amt_pref, cost_min_amt_pref, cost_max_amt_pref,
                          cost_type_nonpref, cost_amt_nonpref,
                          cost_type_mail_pref, cost_amt_mail_pref,
                          cost_min_amt_mail_pref, cost_max_amt_mail_pref,
                          cost_type_mail_nonpref, cost_amt_mail_nonpref,
                          ded_applies_yn, days_supply
                   FROM beneficiary_cost
                   WHERE contract_id = ? AND plan_id = ? AND tier = ? AND days_supply = ?
                         AND coverage_level = '1'
                   LIMIT 1""",
                (cid, pid, str(tier), try_ds)
            )
            if cost:
                break

        # Also try without coverage_level filter if nothing found
        if not cost:
            cost = self._query_one(
                """SELECT cost_type_pref, cost_amt_pref, cost_min_amt_pref, cost_max_amt_pref,
                          cost_type_nonpref, cost_amt_nonpref,
                          cost_type_mail_pref, cost_amt_mail_pref,
                          cost_min_amt_mail_pref, cost_max_amt_mail_pref,
                          cost_type_mail_nonpref, cost_amt_mail_nonpref,
                          ded_applies_yn, days_supply
                   FROM beneficiary_cost
                   WHERE contract_id = ? AND plan_id = ? AND tier = ? AND days_supply = '1'
                   LIMIT 1""",
                (cid, pid, str(tier))
            )

        # Track actual days_supply used
        actual_ds_code = cost.get("days_supply", ds_code) if cost else ds_code
        ds_map = {'1': 30, '2': 60, '3': 90}
        actual_days = ds_map.get(str(actual_ds_code), 30)

        # Build result
        tier_labels = {1: "Preferred Generic", 2: "Generic", 3: "Preferred Brand",
                       4: "Non-Preferred Drug", 5: "Specialty", 6: "Select Care"}

        result = {
            "formulary_id": formulary_id,
            "rxcui": rxcui,
            "tier": tier,
            "tier_label": tier_labels.get(tier, f"Tier {tier}"),
            "prior_auth": drug.get("prior_authorization_yn", "") == "Y",
            "step_therapy": drug.get("step_therapy_yn", "") == "Y",
            "quantity_limit": drug.get("quantity_limit_yn", "") == "Y",
            "quantity_limit_amount": self._safe_float(drug.get("quantity_limit_amount")),
            "quantity_limit_days": self._safe_float(drug.get("quantity_limit_days")),
            "copay_preferred": None,
            "copay_mail": None,
            "days_supply": actual_days,
            "cost_type": "copay",
            # Legacy backward compat keys
            "copay_30day_preferred": None,
            "copay_90day_mail": None,
            "cost_type_30day": "copay",
            "cost_type_90day": "copay",
            "cost_max_30day": None,
            "cost_max_90day": None,
            "deductible_applies": False,
        }

        if cost:
            # Preferred retail: cost_type 0=copay, 1=coinsurance
            cost_type = str(cost.get("cost_type_pref", "0")).strip()
            if cost_type == "0" or cost_type == "":
                retail_cost = self._safe_float(cost.get("cost_amt_pref"))
                result["copay_preferred"] = retail_cost
                result["copay_30day_preferred"] = retail_cost
                result["cost_type"] = "copay"
                result["cost_type_30day"] = "copay"
            else:
                pct = self._safe_float(cost.get("cost_amt_pref"))
                pct_str = f"{pct}%" if pct else None
                result["copay_preferred"] = pct_str
                result["copay_30day_preferred"] = pct_str
                result["cost_type"] = "coinsurance"
                result["cost_type_30day"] = "coinsurance"
                result["cost_max_30day"] = self._safe_float(cost.get("cost_max_amt_pref"))

            # Mail: use mail columns
            mail_type = str(cost.get("cost_type_mail_pref", "0")).strip()
            if mail_type == "0" or mail_type == "":
                mail_cost = self._safe_float(cost.get("cost_amt_mail_pref"))
                result["copay_mail"] = mail_cost
                result["copay_90day_mail"] = mail_cost
                result["cost_type_90day"] = "copay"
            else:
                pct = self._safe_float(cost.get("cost_amt_mail_pref"))
                pct_str = f"{pct}%" if pct else None
                result["copay_mail"] = pct_str
                result["copay_90day_mail"] = pct_str
                result["cost_type_90day"] = "coinsurance"
                result["cost_max_90day"] = self._safe_float(cost.get("cost_max_amt_mail_pref"))

            result["deductible_applies"] = cost.get("ded_applies_yn", "") == "Y"

        return result

    # ── Drug Name → RXCUI (via NLM RxNorm API) ───────────────────────────────

    @staticmethod
    def get_rxcui_by_name(drug_name: str) -> list[str]:
        """
        Look up RXCUIs from drug name using NLM's free RxNorm API.
        Uses multiple strategies for reliable matching:
        1. /drugs endpoint (product-level RXCUIs)
        2. /approximateTerm endpoint (fuzzy match — helps Humalog/insulin)
        3. /rxcui.json (ingredient-level fallback)
        No API key required.
        """
        rxcuis = []
        try:
            # Strategy 1: /drugs endpoint returns all products for a drug name
            resp = _http.get(
                "https://rxnav.nlm.nih.gov/REST/drugs.json",
                params={"name": drug_name},
                timeout=10,
            )
            data = resp.json()
            groups = data.get("drugGroup", {}).get("conceptGroup", [])
            for group in groups:
                for prop in group.get("conceptProperties", []):
                    rxcuis.append(prop["rxcui"])

            # Strategy 2: /approximateTerm for fuzzy matching (helps with
            # brand names like Humalog that may return inconsistent results)
            try:
                resp2 = _http.get(
                    "https://rxnav.nlm.nih.gov/REST/approximateTerm.json",
                    params={"term": drug_name, "maxEntries": 20},
                    timeout=10,
                )
                data2 = resp2.json()
                candidates = data2.get("approximateGroup", {}).get("candidate", [])
                for c in candidates:
                    rxcui = c.get("rxcui")
                    if rxcui and rxcui not in rxcuis:
                        rxcuis.append(rxcui)
            except Exception:
                pass

            if not rxcuis:
                # Strategy 3: try approximate name search for ingredient RXCUI
                resp3 = _http.get(
                    "https://rxnav.nlm.nih.gov/REST/rxcui.json",
                    params={"name": drug_name, "search": 2},
                    timeout=10,
                )
                data3 = resp3.json()
                ids = data3.get("idGroup", {}).get("rxnormId", [])
                rxcuis.extend(ids)

            # Deduplicate while preserving order
            seen = set()
            unique = []
            for r in rxcuis:
                if r not in seen:
                    seen.add(r)
                    unique.append(r)
            return unique

        except Exception as e:
            log.warning(f"RxNorm lookup failed for '{drug_name}': {e}")
            return rxcuis

    def get_drug_by_name(self, plan_number: str, drug_name: str,
                         days_supply: int = 30) -> Optional[dict]:
        """
        Look up drug by name. Tries RxNorm API first, then falls back to
        prefix matching in the formulary DB.
        """
        cid, pid, _ = self._parse_plan_number(plan_number)

        # Get formulary ID
        puf = self._query_one(
            "SELECT formulary_id FROM plan_formulary WHERE contract_id = ? AND plan_id = ? LIMIT 1",
            (cid, pid)
        )
        if not puf:
            return {"error": f"Plan {plan_number} not found"}

        # Try RxNorm API for RXCUIs
        rxcuis = self.get_rxcui_by_name(drug_name)

        # Try each RXCUI against the formulary
        for rxcui in rxcuis:
            result = self.get_drug_coverage(plan_number, rxcui, days_supply=days_supply)
            if result:
                result["drug_name"] = drug_name
                result["is_insulin"] = self._is_insulin(drug_name)
                return result

        # Drug not found in formulary — return not-found error
        return {
            "error": f"'{drug_name}' not on this plan's formulary",
            "rxcuis_checked": rxcuis[:5] if rxcuis else [],
        }

    # ── Medical Copays (PCP, Specialist, ER, Urgent Care) ─────────────────────

    def get_medical_copays(self, plan_number: str) -> dict:
        """Get PCP, specialist copays from B7, ER/urgent from B4."""
        cid, pid, _ = self._parse_plan_number(plan_number)

        result = {
            "pcp_copay": None,
            "specialist_copay": None,
            "er_copay": None,
            "urgent_care_copay": None,
        }

        # B7 — Health Professionals
        b7 = self._query_one(
            """SELECT pbp_b7a_copay_amt_mc_min, pbp_b7a_copay_amt_mc_max,
                      pbp_b7a_coins_pct_mc_min, pbp_b7a_coins_pct_mc_max,
                      pbp_b7b_copay_mc_amt_min, pbp_b7b_copay_mc_amt_max,
                      pbp_b7b_coins_pct_mc_min, pbp_b7b_coins_pct_mc_max
               FROM pbp_b7_health_prof
               WHERE pbp_a_hnumber = ? AND pbp_a_plan_identifier = ?
               LIMIT 1""",
            (cid, pid)
        )

        if b7:
            # PCP copay
            pcp = self._safe_float(b7.get("pbp_b7a_copay_amt_mc_min"))
            if pcp is not None:
                result["pcp_copay"] = f"${pcp:.0f}"
            else:
                pct = self._safe_float(b7.get("pbp_b7a_coins_pct_mc_min"))
                if pct is not None:
                    result["pcp_copay"] = f"{pct:.0f}%"

            # Specialist copay
            spec = self._safe_float(b7.get("pbp_b7b_copay_mc_amt_min"))
            if spec is not None:
                result["specialist_copay"] = f"${spec:.0f}"
            else:
                pct = self._safe_float(b7.get("pbp_b7b_coins_pct_mc_min"))
                if pct is not None:
                    result["specialist_copay"] = f"{pct:.0f}%"

        # B4 — ER + Urgent Care
        b4 = self._query_one(
            """SELECT pbp_b4a_copay_amt_mc_min, pbp_b4a_copay_amt_mc_max,
                      pbp_b4a_coins_pct_mc_min, pbp_b4a_coins_pct_mc_max,
                      pbp_b4b_copay_amt_mc_min, pbp_b4b_copay_amt_mc_max,
                      pbp_b4b_coins_pct_mc_min, pbp_b4b_coins_pct_mc_max
               FROM pbp_b4_emerg_urgent
               WHERE pbp_a_hnumber = ? AND pbp_a_plan_identifier = ?
               LIMIT 1""",
            (cid, pid)
        )

        if b4:
            # ER copay (b4a)
            er = self._safe_float(b4.get("pbp_b4a_copay_amt_mc_min"))
            if er is not None:
                result["er_copay"] = f"${er:.0f}"
            else:
                pct = self._safe_float(b4.get("pbp_b4a_coins_pct_mc_min"))
                if pct is not None:
                    result["er_copay"] = f"{pct:.0f}%"

            # Urgent care copay (b4b)
            uc = self._safe_float(b4.get("pbp_b4b_copay_amt_mc_min"))
            if uc is not None:
                result["urgent_care_copay"] = f"${uc:.0f}"
            else:
                pct = self._safe_float(b4.get("pbp_b4b_coins_pct_mc_min"))
                if pct is not None:
                    result["urgent_care_copay"] = f"{pct:.0f}%"

        return result

    # ── Dental ────────────────────────────────────────────────────────────────

    def get_dental_benefits(self, plan_number: str) -> dict:
        """Get dental preventive + comprehensive benefits from B16."""
        cid, pid, _ = self._parse_plan_number(plan_number)

        result = {
            "has_preventive": False,
            "has_comprehensive": False,
            "preventive": {},
            "comprehensive": {},
        }

        b16 = self._query_one(
            """SELECT
                pbp_b16b_copay_ov_amt, pbp_b16b_copay_ov_amt_min, pbp_b16b_copay_ov_amt_max,
                pbp_b16b_coins_ov_pct, pbp_b16b_coins_ov_pct_min, pbp_b16b_coins_ov_pct_max,
                pbp_b16b_maxplan_pv_amt, pbp_b16b_maxplan_pv_per, pbp_b16b_maxplan_pv_per_desc,
                pbp_b16b_maxenr_pv_amt, pbp_b16b_maxenr_pv_per, pbp_b16b_maxenr_pv_per_desc,
                pbp_b16b_bendesc_oe_num, pbp_b16b_bendesc_oe_per, pbp_b16b_bendesc_oe_desc,
                pbp_b16b_bendesc_dx_num, pbp_b16b_bendesc_dx_per,
                pbp_b16b_bendesc_pc_num, pbp_b16b_bendesc_pc_per,
                pbp_b16c_maxplan_cmp_amt, pbp_b16c_maxplan_cmp_per, pbp_b16c_maxplan_cmp_per_desc,
                pbp_b16c_maxenr_cmp_amt, pbp_b16c_maxenr_cmp_per, pbp_b16c_maxenr_cmp_per_desc,
                pbp_b16c_copay_rs_amt, pbp_b16c_coins_rs_pct,
                pbp_b16c_copay_end_amt, pbp_b16c_coins_end_pct,
                pbp_b16c_copay_prm_amt, pbp_b16c_coins_prm_pct,
                pbp_b16c_copay_impl_amt, pbp_b16c_coins_impl_pct
               FROM pbp_b16_dental
               WHERE pbp_a_hnumber = ? AND pbp_a_plan_identifier = ?
               LIMIT 1""",
            (cid, pid)
        )

        if not b16:
            return result

        # Preventive
        pv_copay = self._safe_float(b16.get("pbp_b16b_copay_ov_amt") or b16.get("pbp_b16b_copay_ov_amt_min"))
        pv_max = self._safe_float(b16.get("pbp_b16b_maxplan_pv_amt") or b16.get("pbp_b16b_maxenr_pv_amt"))
        if pv_copay is not None or pv_max is not None:
            result["has_preventive"] = True
            result["preventive"] = {
                "copay": f"${pv_copay:.0f}" if pv_copay is not None else "$0",
                "max_benefit": f"${pv_max:.0f}" if pv_max is not None else None,
                "oral_exams_per_year": b16.get("pbp_b16b_bendesc_oe_num", ""),
                "cleanings_per_year": b16.get("pbp_b16b_bendesc_pc_num", ""),
            }

        # Comprehensive
        cmp_max = self._safe_float(b16.get("pbp_b16c_maxplan_cmp_amt") or b16.get("pbp_b16c_maxenr_cmp_amt"))
        if cmp_max is not None:
            result["has_comprehensive"] = True
            result["comprehensive"] = {
                "max_benefit": f"${cmp_max:.0f}",
                "crowns_copay": self._format_cost(b16, "pbp_b16c_copay_prm_amt", "pbp_b16c_coins_prm_pct"),
                "root_canal_copay": self._format_cost(b16, "pbp_b16c_copay_end_amt", "pbp_b16c_coins_end_pct"),
                "fillings_copay": self._format_cost(b16, "pbp_b16c_copay_rs_amt", "pbp_b16c_coins_rs_pct"),
                "implants_copay": self._format_cost(b16, "pbp_b16c_copay_impl_amt", "pbp_b16c_coins_impl_pct"),
            }

        return result

    def _format_cost(self, row: dict, copay_key: str, coins_key: str) -> Optional[str]:
        """Format a copay or coinsurance value."""
        copay = self._safe_float(row.get(copay_key))
        if copay is not None:
            return f"${copay:.0f}"
        coins = self._safe_float(row.get(coins_key))
        if coins is not None:
            return f"{coins:.0f}%"
        return None

    # ── OTC Allowance ─────────────────────────────────────────────────────────

    def get_otc_allowance(self, plan_number: str) -> dict:
        """Get OTC benefit from B13 other services."""
        cid, pid, _ = self._parse_plan_number(plan_number)

        result = {
            "has_otc": False,
            "amount": None,
            "period": None,
            "delivery_method": None,
        }

        b13 = self._query_one(
            """SELECT pbp_b13b_bendesc_otc, pbp_b13b_bendesc_amo,
                      pbp_b13b_maxenr_amt, pbp_b13b_maxenr_per, pbp_b13b_maxenr_per_d,
                      pbp_b13b_maxplan_amt, pbp_b13b_otc_maxplan_per,
                      pbp_b13b_mode, pbp_b13b_mode_desc
               FROM pbp_b13_other_services
               WHERE pbp_a_hnumber = ? AND pbp_a_plan_identifier = ?
               LIMIT 1""",
            (cid, pid)
        )

        if not b13:
            return result

        # bendesc_otc = '1' means OTC benefit is offered
        if not self._yn_to_bool(b13.get("pbp_b13b_bendesc_otc")):
            return result

        result["has_otc"] = True

        # Get dollar amount — not all plans store it in CMS
        amt = self._safe_float(b13.get("pbp_b13b_maxplan_amt") or b13.get("pbp_b13b_maxenr_amt"))
        if amt and amt > 0:
            result["amount"] = f"${amt:.0f}"

        # Period: 5=Monthly, 7=Quarterly, 4=Monthly, 3=Yearly
        per_code = str(b13.get("pbp_b13b_otc_maxplan_per") or b13.get("pbp_b13b_maxenr_per") or "").strip()
        period_map = {"3": "Yearly", "4": "Monthly", "5": "Monthly", "7": "Quarterly"}
        period = period_map.get(per_code, "")
        result["period"] = period if period else None

        result["delivery_method"] = b13.get("pbp_b13b_mode_desc", "")

        return result

    # ── Flex Card / SSBCI ─────────────────────────────────────────────────────

    def get_flex_ssbci(self, plan_number: str) -> dict:
        """Get SSBCI (flex card) benefits from B13i."""
        cid, pid, _ = self._parse_plan_number(plan_number)

        result = {
            "has_ssbci": False,
            "benefits": [],
        }

        # May have multiple rows (one per VBID group)
        rows = self._query_all(
            """SELECT pbp_b13i_bendesc,
                      pbp_b13i_fd_maxenr_amt, pbp_b13i_fd_maxplan_amt,
                      pbp_b13i_ml_maxenr_amt, pbp_b13i_ml_maxplan_amt,
                      pbp_b13i_ps_maxenr_amt, pbp_b13i_ps_maxplan_amt,
                      pbp_b13i_t_maxenr_amt, pbp_b13i_t_maxplan_amt,
                      pbp_b13i_air_maxenr_amt, pbp_b13i_air_maxplan_amt,
                      pbp_b13i_socn_maxenr_amt, pbp_b13i_socn_maxplan_amt,
                      pbp_b13i_cmptx_maxenr_amt, pbp_b13i_cmptx_maxplan_amt,
                      pbp_b13i_selfd_maxenr_amt, pbp_b13i_selfd_maxplan_amt,
                      pbp_b13i_home_maxenr_amt, pbp_b13i_home_maxplan_amt,
                      pbp_b13i_suppt_maxenr_amt, pbp_b13i_suppt_maxplan_amt,
                      pbp_b13i_suppt_housing_yn, pbp_b13i_suppt_utility_yn
               FROM pbp_b13i_ssbci
               WHERE pbp_a_hnumber = ? AND pbp_a_plan_identifier = ?""",
            (cid, pid)
        )

        if not rows:
            return result

        # SSBCI benefit categories mapped to the bitmask positions
        ssbci_cats = [
            ("fd",    "Food & Produce"),
            ("ml",    "Meals"),
            ("ps",    "Pest Control"),
            ("t",     "Transportation"),
            ("air",   "Air Conditioning/Heating"),
            ("socn",  "Social Needs"),
            ("cmptx", "Complementary Therapies"),
            ("selfd", "Self-Direction"),
            ("home",  "Home Modifications"),
            ("suppt", "Support Services"),
        ]

        benefits = []
        for row in rows:
            bitmask = str(row.get("pbp_b13i_bendesc", "")).strip()

            for i, (key, label) in enumerate(ssbci_cats):
                # Check bitmask
                if i < len(bitmask) and bitmask[i] == "1":
                    amt = self._safe_float(
                        row.get(f"pbp_b13i_{key}_maxenr_amt") or
                        row.get(f"pbp_b13i_{key}_maxplan_amt")
                    )
                    benefit = {"category": label, "amount": f"${amt:.0f}" if amt else "Included"}

                    # Special flags for support services
                    if key == "suppt":
                        if self._yn_to_bool(row.get("pbp_b13i_suppt_housing_yn")):
                            benefit["includes_housing"] = True
                        if self._yn_to_bool(row.get("pbp_b13i_suppt_utility_yn")):
                            benefit["includes_utilities"] = True

                    benefits.append(benefit)

        if benefits:
            result["has_ssbci"] = True
            result["benefits"] = benefits

        return result

    # ── Part B Giveback ───────────────────────────────────────────────────────

    def get_part_b_giveback(self, plan_number: str) -> dict:
        """Get Part B premium reduction from Section D."""
        cid, pid, _ = self._parse_plan_number(plan_number)

        result = {"has_giveback": False, "monthly_amount": None}

        sd = self._query_one(
            """SELECT pbp_d_mplusc_premium, pbp_d_mplusc_bonly_premium
               FROM pbp_section_d
               WHERE pbp_a_hnumber = ? AND pbp_a_plan_identifier = ?
               LIMIT 1""",
            (cid, pid)
        )

        if sd:
            giveback = self._safe_float(sd.get("pbp_d_mplusc_bonly_premium"))
            if giveback and giveback > 0:
                result["has_giveback"] = True
                result["monthly_amount"] = f"${giveback:.2f}"

        return result

    # ── Vision Benefits ─────────────────────────────────────────────────────

    def get_vision_benefits(self, plan_number: str) -> dict:
        """Get vision exam + eyewear benefits from B17."""
        cid, pid, _ = self._parse_plan_number(plan_number)

        result = {
            "has_eye_exam": False,
            "has_eyewear": False,
            "eye_exam": {},
            "eyewear": {},
        }

        b17 = self._query_one(
            """SELECT
                pbp_b17a_bendesc_yn,
                pbp_b17a_copay_amt_mc_min, pbp_b17a_copay_amt_mc_max,
                pbp_b17a_coins_pct_mc_min, pbp_b17a_coins_pct_mc_max,
                pbp_b17a_maxplan_amt, pbp_b17a_maxenr_amt,
                pbp_b17a_bendesc_num_rex, pbp_b17a_bendesc_per_rex,
                pbp_b17b_bendesc_yn,
                pbp_b17b_copay_amt_mc_min, pbp_b17b_copay_amt_mc_max,
                pbp_b17b_coins_pct_mc_min, pbp_b17b_coins_pct_mc_max,
                pbp_b17b_comb_maxplan_amt, pbp_b17b_maxenr_amt,
                pbp_b17b_bendesc_numv_cl, pbp_b17b_bendesc_per_cl
               FROM pbp_b17_vision
               WHERE pbp_a_hnumber = ? AND pbp_a_plan_identifier = ?
               LIMIT 1""",
            (cid, pid)
        )

        if not b17:
            return result

        # Eye exams (17a)
        if self._yn_to_bool(b17.get("pbp_b17a_bendesc_yn")):
            result["has_eye_exam"] = True
            copay = self._safe_float(b17.get("pbp_b17a_copay_amt_mc_min"))
            coins = self._safe_float(b17.get("pbp_b17a_coins_pct_mc_min"))
            max_amt = self._safe_float(
                b17.get("pbp_b17a_maxplan_amt") or b17.get("pbp_b17a_maxenr_amt")
            )
            exam_num = b17.get("pbp_b17a_bendesc_num_rex", "")

            result["eye_exam"] = {
                "copay": f"${copay:.0f}" if copay is not None else None,
                "coinsurance": f"{coins:.0f}%" if coins is not None else None,
                "max_benefit": f"${max_amt:.0f}" if max_amt is not None else None,
                "exams_per_year": exam_num if exam_num else None,
            }

        # Eyewear (17b)
        if self._yn_to_bool(b17.get("pbp_b17b_bendesc_yn")):
            result["has_eyewear"] = True
            copay = self._safe_float(b17.get("pbp_b17b_copay_amt_mc_min"))
            coins = self._safe_float(b17.get("pbp_b17b_coins_pct_mc_min"))
            max_amt = self._safe_float(
                b17.get("pbp_b17b_comb_maxplan_amt") or b17.get("pbp_b17b_maxenr_amt")
            )

            result["eyewear"] = {
                "copay": f"${copay:.0f}" if copay is not None else None,
                "coinsurance": f"{coins:.0f}%" if coins is not None else None,
                "max_benefit": f"${max_amt:.0f}" if max_amt is not None else None,
            }

        return result

    # ── Hearing Benefits ─────────────────────────────────────────────────────

    def get_hearing_benefits(self, plan_number: str) -> dict:
        """Get hearing exam + hearing aid benefits from B18."""
        cid, pid, _ = self._parse_plan_number(plan_number)

        result = {
            "has_hearing_exam": False,
            "has_hearing_aids": False,
            "hearing_exam": {},
            "hearing_aids": {},
        }

        b18 = self._query_one(
            """SELECT
                pbp_b18a_bendesc_yn,
                pbp_b18a_copay_amt, pbp_b18a_med_copay_amt_max,
                pbp_b18a_med_coins_pct, pbp_b18a_med_coins_pct_max,
                pbp_b18a_maxplan_amt, pbp_b18a_maxenr_amt,
                pbp_b18a_bendesc_numv_cl,
                pbp_b18b_bendesc_yn,
                pbp_b18b_copay_at_min_amt, pbp_b18b_copay_at_max_amt,
                pbp_b18b_coins_pct_at_min, pbp_b18b_coins_pct_at_max,
                pbp_b18b_maxplan_amt, pbp_b18b_maxenr_amt,
                pbp_b18b_bendesc_numv_at, pbp_b18b_bendesc_per_at
               FROM pbp_b18_hearing
               WHERE pbp_a_hnumber = ? AND pbp_a_plan_identifier = ?
               LIMIT 1""",
            (cid, pid)
        )

        if not b18:
            return result

        # Hearing exams (18a)
        if self._yn_to_bool(b18.get("pbp_b18a_bendesc_yn")):
            result["has_hearing_exam"] = True
            copay = self._safe_float(b18.get("pbp_b18a_copay_amt"))
            coins = self._safe_float(b18.get("pbp_b18a_med_coins_pct"))
            max_amt = self._safe_float(
                b18.get("pbp_b18a_maxplan_amt") or b18.get("pbp_b18a_maxenr_amt")
            )
            exam_num = b18.get("pbp_b18a_bendesc_numv_cl", "")

            result["hearing_exam"] = {
                "copay": f"${copay:.0f}" if copay is not None else None,
                "coinsurance": f"{coins:.0f}%" if coins is not None else None,
                "max_benefit": f"${max_amt:.0f}" if max_amt is not None else None,
                "exams_per_year": exam_num if exam_num else None,
            }

        # Hearing aids (18b)
        if self._yn_to_bool(b18.get("pbp_b18b_bendesc_yn")):
            result["has_hearing_aids"] = True
            copay = self._safe_float(b18.get("pbp_b18b_copay_at_min_amt"))
            coins = self._safe_float(b18.get("pbp_b18b_coins_pct_at_min"))
            max_amt = self._safe_float(
                b18.get("pbp_b18b_maxplan_amt") or b18.get("pbp_b18b_maxenr_amt")
            )
            aid_num = b18.get("pbp_b18b_bendesc_numv_at", "")

            # Period mapping
            per_code = str(b18.get("pbp_b18b_bendesc_per_at", "")).strip()
            period_map = {"1": "per year", "2": "every 2 years", "3": "every 3 years"}
            period = period_map.get(per_code, "")

            result["hearing_aids"] = {
                "copay": f"${copay:.0f}" if copay is not None else None,
                "coinsurance": f"{coins:.0f}%" if coins is not None else None,
                "max_benefit": f"${max_amt:.0f}" if max_amt is not None else None,
                "aids_allowed": aid_num if aid_num else None,
                "period": period if period else None,
            }

        return result

    # ── Combined Full Benefits ────────────────────────────────────────────────

    def get_full_benefits(self, plan_number: str) -> dict:
        """Get everything for a plan in one call."""
        overview = self.get_plan_overview(plan_number)
        if not overview:
            return {"error": f"Plan {plan_number} not found"}

        return {
            "plan": overview,
            "medical": self.get_medical_copays(plan_number),
            "dental": self.get_dental_benefits(plan_number),
            "vision": self.get_vision_benefits(plan_number),
            "hearing": self.get_hearing_benefits(plan_number),
            "otc": self.get_otc_allowance(plan_number),
            "flex_ssbci": self.get_flex_ssbci(plan_number),
            "part_b_giveback": self.get_part_b_giveback(plan_number),
        }


# ── CLI for quick testing ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    import sys

    lookup = CMSLookup()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python cms_lookup.py H1036-077              # Full benefits")
        print("  python cms_lookup.py H1036-077 drug Eliquis # Drug lookup")
        sys.exit(1)

    plan = sys.argv[1]

    if len(sys.argv) >= 4 and sys.argv[2] == "drug":
        result = lookup.get_drug_by_name(plan, sys.argv[3])
    else:
        result = lookup.get_full_benefits(plan)

    print(json.dumps(result, indent=2, default=str))
