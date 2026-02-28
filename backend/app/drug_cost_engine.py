"""
Drug Cost Engine — Month-by-month simulation of Medicare Part D drug costs.

Mirrors how SunFire calculates Estimated Annual Drug Cost:
  - Simulates 12 months through Deductible → Initial Coverage → Catastrophic
  - Handles both flat copay and coinsurance (pct × estimated full drug cost)
  - Accounts for deductible amount, which tiers it applies to, and insulin caps

How the deductible works (matching SunFire's model):
  - Non-insulin drugs during deductible: member pays full negotiated retail price.
  - Insulin drugs (IRA): member ALWAYS pays IC rate (coinsurance or copay,
    capped at insulin_cap), even during deductible. The amount the member
    pays still counts toward satisfying the deductible.
  - When a non-insulin drug's fill straddles the deductible boundary,
    the member pays the remaining deductible for that fill.
  - The member's actual out-of-pocket payment counts toward exhausting
    the deductible (not the drug's full negotiated cost).
"""

import math
from typing import Optional

# 2026 Part D parameters (CMS standard)
CATASTROPHIC_TROOP_THRESHOLD = 2000.0  # True Out-of-Pocket threshold


def compute_monthly_drug_costs(
    drugs: list[dict],
    drug_deductible: float = 0.0,
    deductible_tiers: list[int] | None = None,
    insulin_cap: float = 35.0,
    months: int = 12,
) -> dict:
    """
    Run a month-by-month simulation of Part D drug costs for a list of drugs.

    Each drug dict should contain:
        name: str
        tier: int
        cost_type: "copay" | "coinsurance"
        copay_amount: float | None          — flat $ copay in Initial Coverage
        coinsurance_pct: float | None       — percentage (e.g. 16.0 for 16%)
        estimated_full_cost: float | None   — plan's negotiated monthly retail price
        is_insulin: bool
        deductible_applies: bool            — whether deductible applies to this drug's tier

    Returns dict with:
        monthly_breakdown: list of dicts, each with per-drug costs and totals
        annual_total: float
        average_monthly: float
        drugs_summary: per-drug annual totals and cost details
    """
    if deductible_tiers is None:
        deductible_tiers = []

    # State: track how much deductible remains
    deductible_remaining = drug_deductible

    monthly_breakdown = []
    drug_annual_totals = [0.0] * len(drugs)

    for month_idx in range(months):
        month_costs = []
        month_total = 0.0

        for drug_idx, drug in enumerate(drugs):
            cost = _calc_drug_month(
                drug=drug,
                deductible_remaining=deductible_remaining,
                deductible_tiers=deductible_tiers,
                insulin_cap=insulin_cap,
            )

            # Reduce deductible by what the member actually paid toward it
            deductible_remaining -= cost["deductible_spend"]
            deductible_remaining = max(0.0, deductible_remaining)

            month_costs.append(cost)
            month_total += cost["member_cost"]
            drug_annual_totals[drug_idx] += cost["member_cost"]

        monthly_breakdown.append({
            "month": month_idx + 1,
            "drugs": month_costs,
            "total": round(month_total, 2),
        })

    annual_total = sum(m["total"] for m in monthly_breakdown)

    # Build per-drug summary
    drugs_summary = []
    for drug_idx, drug in enumerate(drugs):
        drugs_summary.append({
            "name": drug["name"],
            "annual_total": round(drug_annual_totals[drug_idx], 2),
            "average_monthly": round(drug_annual_totals[drug_idx] / months, 2),
        })

    return {
        "monthly_breakdown": monthly_breakdown,
        "annual_total": round(annual_total, 2),
        "average_monthly": round(annual_total / months, 2),
        "drugs_summary": drugs_summary,
    }


def _calc_drug_month(
    drug: dict,
    deductible_remaining: float,
    deductible_tiers: list[int],
    insulin_cap: float,
) -> dict:
    """
    Calculate one drug's cost for one month.

    Key rules (matching SunFire):
      - Insulin drugs always pay the IC rate, capped at insulin_cap,
        regardless of deductible phase. Their payment counts toward
        the deductible.
      - Non-insulin drugs in deductible pay full retail.
      - When the deductible clears on a non-insulin drug mid-month,
        member pays the remaining deductible amount for that fill.

    Returns dict:
        drug: str             — drug name
        member_cost: float    — what the member pays this month
        phase: str            — "deductible" | "initial" | "deductible_to_initial"
        deductible_spend: float — how much counted toward the deductible
    """
    name = drug.get("name", "")
    tier = drug.get("tier")
    cost_type = drug.get("cost_type", "copay")
    copay_amount = drug.get("copay_amount")
    coinsurance_pct = drug.get("coinsurance_pct")
    estimated_full_cost = drug.get("estimated_full_cost")
    is_insulin = drug.get("is_insulin", False)
    ded_applies = drug.get("deductible_applies", False)

    # Check if this drug's tier is in the deductible tiers list
    if tier is not None and tier in deductible_tiers:
        ded_applies = True

    # Calculate the Initial Coverage cost
    ic_cost = _calc_initial_coverage_cost(
        cost_type=cost_type,
        copay_amount=copay_amount,
        coinsurance_pct=coinsurance_pct,
        estimated_full_cost=estimated_full_cost,
    )

    # Apply insulin cap
    if is_insulin and ic_cost > insulin_cap:
        ic_cost = insulin_cap

    # ── INSULIN: always pays IC rate regardless of deductible phase ──
    # IRA (Inflation Reduction Act) caps insulin at $35/month in ALL phases.
    # The member's payment still counts toward satisfying the deductible.
    if is_insulin:
        member_cost = ic_cost
        ded_spend = member_cost if (ded_applies and deductible_remaining > 0) else 0.0
        ded_spend = min(ded_spend, deductible_remaining)
        phase = "deductible" if (ded_applies and deductible_remaining > 0) else "initial"
        return {
            "drug": name,
            "member_cost": round(member_cost, 2),
            "phase": phase,
            "deductible_spend": round(ded_spend, 2),
        }

    # ── NON-INSULIN ──

    # If no estimated_full_cost, we can't model deductible properly —
    # fall back to IC cost for every month
    if estimated_full_cost is None or estimated_full_cost <= 0:
        return {
            "drug": name,
            "member_cost": round(ic_cost, 2),
            "phase": "initial",
            "deductible_spend": 0.0,
        }

    # Deductible doesn't apply or already cleared
    if not ded_applies or deductible_remaining <= 0:
        return {
            "drug": name,
            "member_cost": round(ic_cost, 2),
            "phase": "initial",
            "deductible_spend": 0.0,
        }

    # ── Deductible applies, hasn't been met yet ──
    full_cost = estimated_full_cost

    if deductible_remaining >= full_cost:
        # Entire fill is in deductible phase — member pays full retail
        return {
            "drug": name,
            "member_cost": round(full_cost, 2),
            "phase": "deductible",
            "deductible_spend": round(full_cost, 2),
        }
    else:
        # Deductible clears on this fill — member pays the remaining
        # deductible amount (not the full retail)
        member_cost = deductible_remaining
        return {
            "drug": name,
            "member_cost": round(member_cost, 2),
            "phase": "deductible_to_initial",
            "deductible_spend": round(deductible_remaining, 2),
        }


def _calc_initial_coverage_cost(
    cost_type: str,
    copay_amount: float | None,
    coinsurance_pct: float | None,
    estimated_full_cost: float | None,
) -> float:
    """
    Calculate the member's cost in Initial Coverage phase.

    For flat copay: return copay_amount
    For coinsurance: return pct/100 × estimated_full_cost
    """
    if cost_type == "copay" and copay_amount is not None:
        return float(copay_amount)

    if cost_type == "coinsurance" and coinsurance_pct is not None:
        if estimated_full_cost is not None and estimated_full_cost > 0:
            return (coinsurance_pct / 100.0) * estimated_full_cost
        return 0.0

    return 0.0


def estimate_current_month_costs(
    drugs: list[dict],
    drug_deductible: float = 0.0,
    deductible_tiers: list[int] | None = None,
    insulin_cap: float = 35.0,
    current_month: int = 1,
) -> dict:
    """
    Estimate costs for a specific month by running the simulation up to that month.

    Returns the cost breakdown for the requested month plus cumulative info.
    """
    result = compute_monthly_drug_costs(
        drugs=drugs,
        drug_deductible=drug_deductible,
        deductible_tiers=deductible_tiers,
        insulin_cap=insulin_cap,
        months=current_month,
    )

    current = result["monthly_breakdown"][-1] if result["monthly_breakdown"] else None
    ytd_total = sum(m["total"] for m in result["monthly_breakdown"])

    return {
        "month": current_month,
        "current_month_costs": current,
        "ytd_total": round(ytd_total, 2),
        "deductible_amount": drug_deductible,
        "deductible_remaining": max(0.0, drug_deductible - ytd_total) if drug_deductible > 0 else 0.0,
    }
