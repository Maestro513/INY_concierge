"""
Tests for the drug cost simulation engine.
"""

from app.drug_cost_engine import (
    compute_monthly_drug_costs,
    estimate_current_month_costs,
    _calc_drug_month,
    _calc_initial_coverage_cost,
)


class TestInitialCoverageCost:
    def test_flat_copay(self):
        cost = _calc_initial_coverage_cost("copay", 47.0, None, 600.0)
        assert cost == 47.0

    def test_coinsurance(self):
        cost = _calc_initial_coverage_cost("coinsurance", None, 25.0, 400.0)
        assert cost == 100.0  # 25% of 400

    def test_zero_copay(self):
        cost = _calc_initial_coverage_cost("copay", 0.0, None, 30.0)
        assert cost == 0.0

    def test_missing_copay_returns_zero(self):
        cost = _calc_initial_coverage_cost("copay", None, None, 600.0)
        assert cost == 0.0

    def test_coinsurance_no_full_cost(self):
        cost = _calc_initial_coverage_cost("coinsurance", None, 25.0, None)
        assert cost == 0.0


class TestCalcDrugMonth:
    def test_non_insulin_initial_coverage(self):
        drug = {
            "name": "Eliquis",
            "tier": 3,
            "cost_type": "copay",
            "copay_amount": 47.0,
            "coinsurance_pct": None,
            "estimated_full_cost": 600.0,
            "is_insulin": False,
            "deductible_applies": False,
        }
        result = _calc_drug_month(drug, deductible_remaining=0, deductible_tiers=[], insulin_cap=35)
        assert result["member_cost"] == 47.0
        assert result["phase"] == "initial"
        assert result["deductible_spend"] == 0.0

    def test_non_insulin_in_deductible(self):
        drug = {
            "name": "Eliquis",
            "tier": 3,
            "cost_type": "copay",
            "copay_amount": 47.0,
            "coinsurance_pct": None,
            "estimated_full_cost": 600.0,
            "is_insulin": False,
            "deductible_applies": True,
        }
        result = _calc_drug_month(drug, deductible_remaining=1000, deductible_tiers=[], insulin_cap=35)
        assert result["member_cost"] == 600.0  # pays full retail during deductible
        assert result["phase"] == "deductible"
        assert result["deductible_spend"] == 600.0

    def test_non_insulin_deductible_straddle(self):
        drug = {
            "name": "Eliquis",
            "tier": 3,
            "cost_type": "copay",
            "copay_amount": 47.0,
            "coinsurance_pct": None,
            "estimated_full_cost": 600.0,
            "is_insulin": False,
            "deductible_applies": True,
        }
        result = _calc_drug_month(drug, deductible_remaining=100, deductible_tiers=[], insulin_cap=35)
        assert result["member_cost"] == 100.0  # pays remaining deductible
        assert result["phase"] == "deductible_to_initial"
        assert result["deductible_spend"] == 100.0

    def test_insulin_always_pays_ic_rate(self):
        """Insulin pays IC rate regardless of deductible phase (IRA rule)."""
        drug = {
            "name": "Lantus",
            "tier": 3,
            "cost_type": "copay",
            "copay_amount": 50.0,
            "coinsurance_pct": None,
            "estimated_full_cost": 350.0,
            "is_insulin": True,
            "deductible_applies": True,
        }
        result = _calc_drug_month(drug, deductible_remaining=1000, deductible_tiers=[], insulin_cap=35)
        assert result["member_cost"] == 35.0  # capped at insulin_cap
        assert result["deductible_spend"] == 35.0  # counts toward deductible

    def test_insulin_below_cap(self):
        drug = {
            "name": "Novolin",
            "tier": 1,
            "cost_type": "copay",
            "copay_amount": 10.0,
            "coinsurance_pct": None,
            "estimated_full_cost": 100.0,
            "is_insulin": True,
            "deductible_applies": False,
        }
        result = _calc_drug_month(drug, deductible_remaining=0, deductible_tiers=[], insulin_cap=35)
        assert result["member_cost"] == 10.0  # below cap, not capped

    def test_deductible_tiers_list(self):
        """Drug's tier in deductible_tiers triggers deductible even if deductible_applies=False."""
        drug = {
            "name": "BrandDrug",
            "tier": 3,
            "cost_type": "copay",
            "copay_amount": 47.0,
            "coinsurance_pct": None,
            "estimated_full_cost": 500.0,
            "is_insulin": False,
            "deductible_applies": False,
        }
        result = _calc_drug_month(drug, deductible_remaining=1000, deductible_tiers=[3, 4, 5], insulin_cap=35)
        assert result["phase"] == "deductible"
        assert result["member_cost"] == 500.0


class TestComputeMonthlyDrugCosts:
    def test_basic_annual_simulation(self, sample_drugs):
        result = compute_monthly_drug_costs(sample_drugs, drug_deductible=0.0)
        assert len(result["monthly_breakdown"]) == 12
        assert result["annual_total"] > 0
        assert result["average_monthly"] > 0
        assert len(result["drugs_summary"]) == 3

    def test_with_deductible(self, sample_drugs):
        result = compute_monthly_drug_costs(
            sample_drugs,
            drug_deductible=250.0,
            deductible_tiers=[3, 4, 5],
        )
        # First month should be higher due to deductible
        month1 = result["monthly_breakdown"][0]["total"]
        month12 = result["monthly_breakdown"][11]["total"]
        assert month1 > month12  # deductible makes early months more expensive

    def test_zero_drugs(self):
        result = compute_monthly_drug_costs([], drug_deductible=0.0)
        assert result["annual_total"] == 0.0
        assert len(result["monthly_breakdown"]) == 12

    def test_custom_months(self, sample_drugs):
        result = compute_monthly_drug_costs(sample_drugs, months=6)
        assert len(result["monthly_breakdown"]) == 6


class TestEstimateCurrentMonthCosts:
    def test_month_1(self, sample_drugs):
        result = estimate_current_month_costs(sample_drugs, current_month=1)
        assert result["month"] == 1
        assert result["current_month_costs"] is not None
        assert result["ytd_total"] >= 0

    def test_month_6(self, sample_drugs):
        result = estimate_current_month_costs(
            sample_drugs, drug_deductible=250.0, deductible_tiers=[3], current_month=6
        )
        assert result["month"] == 6
        assert result["ytd_total"] > 0
