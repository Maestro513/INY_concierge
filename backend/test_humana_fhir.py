"""Explore Humana FHIR API - find available plans and test drug lookups"""
import requests
import json

url = 'https://fhir.humana.com/api/List'

# Get a small page and look at contracts
params = {'_count': 20, '_skip': 0}
resp = requests.get(url, params=params, timeout=60)
data = resp.json()
total = data.get('total', 0)
print(f'Total formulary lists: {total}')

contracts = {}
for e in data.get('entry', []):
    r = e.get('resource', {})
    if r.get('resourceType') != 'List':
        continue
    idents = r.get('identifier', [])
    for i in idents:
        v = i.get('value', '')
        if v.startswith('H') and '-' in v:
            prefix = v.split('-')[0]
            if prefix not in contracts:
                contracts[prefix] = set()
            contracts[prefix].add(v)

for c in sorted(contracts):
    plans = sorted(contracts[c])
    print(f'{c}: {len(plans)} plans - e.g. {plans[:3]}')

# Now try to find an H7617 plan by paging
print('\n--- Searching for H7617 plans ---')
found_h7617 = False
for skip in range(0, min(total, 200), 20):
    params = {'_count': 20, '_skip': skip}
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            continue
        data = resp.json()
        for e in data.get('entry', []):
            r = e.get('resource', {})
            if r.get('resourceType') != 'List':
                continue
            idents = r.get('identifier', [])
            for i in idents:
                v = i.get('value', '')
                if 'H7617' in v:
                    found_h7617 = True
                    list_entries = r.get('entry', [])
                    print(f'FOUND: {v} ({len(list_entries)} drugs)')
                    if list_entries:
                        ref = list_entries[0].get('item', {}).get('reference', '?')
                        print(f'  First drug ref: {ref}')
    except Exception as ex:
        print(f'  skip={skip} error: {ex}')
        continue

if not found_h7617:
    print('H7617 not found in first 200 entries. May only have 2025 data.')
    # Show what year the data is from
    params = {'_count': 5, '_skip': 0}
    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()
    for e in data.get('entry', [])[:3]:
        r = e.get('resource', {})
        idents = r.get('identifier', [])
        id_vals = [i.get('value', '') for i in idents]
        print(f'  Sample plan IDs: {id_vals}')
