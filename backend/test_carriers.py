"""Test extract_tier_copays on all 5 carriers"""
import sys, json
sys.path.insert(0, '.')
from app.sob_parser import extract_tier_copays, load_plan_text

plans = {
    'Humana': 'H7617-107',
    'Aetna': 'H2663-067',
    'Devoted': 'H1290-067',
    'UHC': 'H0543-255',
    'Wellcare': 'H0351-053',
}

for carrier, plan_id in plans.items():
    print(f'\n=== {carrier} ({plan_id}) ===')
    text = load_plan_text(plan_id)
    if not text:
        print(f'  No SOB text found')
        continue

    result = extract_tier_copays(text)

    for tier in [1, 2, 3, 4, 5, 6]:
        td = result.get(tier)
        if td:
            r30 = td.get('retail_30', '?')
            r90 = td.get('retail_90', '?')
            m30 = td.get('mail_30', '?')
            parsed = td.get('parsed_retail_30', {})
            ptype = parsed.get('type', '?')
            pamt = parsed.get('amount', parsed.get('pct', '?'))
            print(f'  Tier {tier}: retail_30={r30}, retail_90={r90}, mail_30={m30} | type={ptype}, val={pamt}')
        else:
            print(f'  Tier {tier}: NOT FOUND')

    cap = result.get('insulin_cap')
    ded = result.get('deductible_amount')
    ded_tiers = result.get('deductible_tiers')
    print(f'  Insulin cap: ${cap}' if cap else '  Insulin cap: not found')
    print(f'  Deductible: ${ded} for tiers {ded_tiers}' if ded else '  Deductible: not found')
