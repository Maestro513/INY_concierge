"""
Humana Provider Directory FHIR Adapter.

Simple 3-step flow (confirmed by live API testing):
1. /Location?address-postalcode=ZIP → get location IDs near member
2. /PractitionerRole?specialty=X&location=Location/{id} → get doctor roles at those locations
3. /Practitioner/{id} → get doctor names and NPIs

Humana's API doesn't support joining these in one call, so we do it manually.
Chained params (location.address-postalcode) timeout — do NOT use them.
"""

import asyncio
import httpx
import logging
from .base import BaseAdapter, ProviderResult, resolve_specialty

logger = logging.getLogger(__name__)

HUMANA_BASE = "https://fhir.humana.com/api"
HEADERS = {"Accept": "application/fhir+json"}
TIMEOUT = 30.0

# Zip prefix → state (first 3 digits)
ZIP_PREFIX_TO_STATE = {
    "005": "NY", "006": "PR", "007": "PR", "008": "PR", "009": "PR",
    "010": "MA", "011": "MA", "012": "MA", "013": "MA", "014": "MA",
    "015": "MA", "016": "MA", "017": "MA", "018": "MA", "019": "MA",
    "020": "MA", "021": "MA", "022": "MA", "023": "MA", "024": "MA",
    "025": "MA", "026": "MA", "027": "MA",
    "028": "RI", "029": "RI",
    "030": "NH", "031": "NH", "032": "NH", "033": "NH", "034": "NH",
    "035": "NH", "036": "NH", "037": "NH", "038": "NH",
    "039": "ME", "040": "ME", "041": "ME", "042": "ME", "043": "ME",
    "044": "ME", "045": "ME", "046": "ME", "047": "ME", "048": "ME",
    "049": "ME",
    "050": "VT", "051": "VT", "052": "VT", "053": "VT", "054": "VT",
    "055": "VT", "056": "VT", "057": "VT", "058": "VT", "059": "VT",
    "060": "CT", "061": "CT", "062": "CT", "063": "CT", "064": "CT",
    "065": "CT", "066": "CT", "067": "CT", "068": "CT", "069": "CT",
    "070": "NJ", "071": "NJ", "072": "NJ", "073": "NJ", "074": "NJ",
    "075": "NJ", "076": "NJ", "077": "NJ", "078": "NJ", "079": "NJ",
    "080": "NJ", "081": "NJ", "082": "NJ", "083": "NJ", "084": "NJ",
    "085": "NJ", "086": "NJ", "087": "NJ", "088": "NJ", "089": "NJ",
    "100": "NY", "101": "NY", "102": "NY", "103": "NY", "104": "NY",
    "105": "NY", "106": "NY", "107": "NY", "108": "NY", "109": "NY",
    "110": "NY", "111": "NY", "112": "NY", "113": "NY", "114": "NY",
    "115": "NY", "116": "NY", "117": "NY", "118": "NY", "119": "NY",
    "120": "NY", "121": "NY", "122": "NY", "123": "NY", "124": "NY",
    "125": "NY", "126": "NY", "127": "NY", "128": "NY", "129": "NY",
    "130": "NY", "131": "NY", "132": "NY", "133": "NY", "134": "NY",
    "135": "NY", "136": "NY", "137": "NY", "138": "NY", "139": "NY",
    "140": "NY", "141": "NY", "142": "NY", "143": "NY", "144": "NY",
    "145": "NY", "146": "NY", "147": "NY", "148": "NY", "149": "NY",
    "150": "PA", "151": "PA", "152": "PA", "153": "PA", "154": "PA",
    "155": "PA", "156": "PA", "157": "PA", "158": "PA", "159": "PA",
    "160": "PA", "161": "PA", "162": "PA", "163": "PA", "164": "PA",
    "165": "PA", "166": "PA", "167": "PA", "168": "PA", "169": "PA",
    "170": "PA", "171": "PA", "172": "PA", "173": "PA", "174": "PA",
    "175": "PA", "176": "PA", "177": "PA", "178": "PA", "179": "PA",
    "180": "PA", "181": "PA", "182": "PA", "183": "PA", "184": "PA",
    "185": "PA", "186": "PA", "187": "PA", "188": "PA", "189": "PA",
    "190": "PA", "191": "PA", "192": "PA", "193": "PA", "194": "PA",
    "195": "PA", "196": "PA",
    "197": "DE", "198": "DE", "199": "DE",
    "200": "DC", "201": "VA", "202": "DC", "203": "DC", "204": "DC",
    "205": "DC",
    "206": "MD", "207": "MD", "208": "MD", "209": "MD", "210": "MD",
    "211": "MD", "212": "MD", "214": "MD", "215": "MD", "216": "MD",
    "217": "MD", "218": "MD", "219": "MD",
    "220": "VA", "221": "VA", "222": "VA", "223": "VA", "224": "VA",
    "225": "VA", "226": "VA", "227": "VA", "228": "VA", "229": "VA",
    "230": "VA", "231": "VA", "232": "VA", "233": "VA", "234": "VA",
    "235": "VA", "236": "VA", "237": "VA", "238": "VA", "239": "VA",
    "240": "VA", "241": "VA", "242": "VA", "243": "VA", "244": "VA",
    "245": "VA", "246": "VA",
    "247": "WV", "248": "WV", "249": "WV", "250": "WV", "251": "WV",
    "252": "WV", "253": "WV", "254": "WV", "255": "WV", "256": "WV",
    "257": "WV", "258": "WV", "259": "WV", "260": "WV", "261": "WV",
    "262": "WV", "263": "WV", "264": "WV", "265": "WV", "266": "WV",
    "267": "WV", "268": "WV",
    "270": "NC", "271": "NC", "272": "NC", "273": "NC", "274": "NC",
    "275": "NC", "276": "NC", "277": "NC", "278": "NC", "279": "NC",
    "280": "NC", "281": "NC", "282": "NC", "283": "NC", "284": "NC",
    "285": "NC", "286": "NC", "287": "NC", "288": "NC", "289": "NC",
    "290": "SC", "291": "SC", "292": "SC", "293": "SC", "294": "SC",
    "295": "SC", "296": "SC",
    "297": "GA", "298": "GA", "299": "GA",
    "300": "GA", "301": "GA", "302": "GA", "303": "GA", "304": "GA",
    "305": "GA", "306": "GA", "307": "GA", "308": "GA", "309": "GA",
    "310": "GA", "311": "GA", "312": "GA", "313": "GA", "314": "GA",
    "315": "GA", "316": "GA", "317": "GA", "318": "GA", "319": "GA",
    "320": "FL", "321": "FL", "322": "FL", "323": "FL", "324": "FL",
    "325": "FL", "326": "FL", "327": "FL", "328": "FL", "329": "FL",
    "330": "FL", "331": "FL", "332": "FL", "333": "FL", "334": "FL",
    "335": "FL", "336": "FL", "337": "FL", "338": "FL", "339": "FL",
    "340": "FL", "341": "FL", "342": "FL", "344": "FL", "346": "FL",
    "347": "FL", "349": "FL",
    "350": "AL", "351": "AL", "352": "AL", "354": "AL", "355": "AL",
    "356": "AL", "357": "AL", "358": "AL", "359": "AL", "360": "AL",
    "361": "AL", "362": "AL", "363": "AL", "364": "AL", "365": "AL",
    "366": "AL", "367": "AL", "368": "AL", "369": "AL",
    "370": "TN", "371": "TN", "372": "TN", "373": "TN", "374": "TN",
    "375": "TN", "376": "TN", "377": "TN", "378": "TN", "379": "TN",
    "380": "TN", "381": "TN", "382": "TN", "383": "TN", "384": "TN",
    "385": "TN",
    "386": "MS", "387": "MS", "388": "MS", "389": "MS", "390": "MS",
    "391": "MS", "392": "MS", "393": "MS", "394": "MS", "395": "MS",
    "396": "MS", "397": "MS",
    "398": "GA", "399": "GA",
    "400": "KY", "401": "KY", "402": "KY", "403": "KY", "404": "KY",
    "405": "KY", "406": "KY", "407": "KY", "408": "KY", "409": "KY",
    "410": "KY", "411": "KY", "412": "KY", "413": "KY", "414": "KY",
    "415": "KY", "416": "KY", "417": "KY", "418": "KY",
    "420": "KY", "421": "KY", "422": "KY", "423": "KY", "424": "KY",
    "425": "KY", "426": "KY", "427": "KY",
    "430": "OH", "431": "OH", "432": "OH", "433": "OH", "434": "OH",
    "435": "OH", "436": "OH", "437": "OH", "438": "OH", "439": "OH",
    "440": "OH", "441": "OH", "442": "OH", "443": "OH", "444": "OH",
    "445": "OH", "446": "OH", "447": "OH", "448": "OH", "449": "OH",
    "450": "OH", "451": "OH", "452": "OH", "453": "OH", "454": "OH",
    "455": "OH", "456": "OH", "457": "OH", "458": "OH",
    "460": "IN", "461": "IN", "462": "IN", "463": "IN", "464": "IN",
    "465": "IN", "466": "IN", "467": "IN", "468": "IN", "469": "IN",
    "470": "IN", "471": "IN", "472": "IN", "473": "IN", "474": "IN",
    "475": "IN", "476": "IN", "477": "IN", "478": "IN", "479": "IN",
    "480": "MI", "481": "MI", "482": "MI", "483": "MI", "484": "MI",
    "485": "MI", "486": "MI", "487": "MI", "488": "MI", "489": "MI",
    "490": "MI", "491": "MI", "492": "MI", "493": "MI", "494": "MI",
    "495": "MI", "496": "MI", "497": "MI", "498": "MI", "499": "MI",
    "500": "IA", "501": "IA", "502": "IA", "503": "IA", "504": "IA",
    "505": "IA", "506": "IA", "507": "IA", "508": "IA", "509": "IA",
    "510": "IA", "511": "IA", "512": "IA", "513": "IA", "514": "IA",
    "515": "IA", "516": "IA",
    "520": "WI", "521": "WI", "522": "WI", "523": "WI", "524": "WI",
    "525": "WI", "526": "WI", "527": "WI", "528": "WI", "529": "WI",
    "530": "WI", "531": "WI", "532": "WI", "534": "WI", "535": "WI",
    "537": "WI", "538": "WI", "539": "WI",
    "540": "MN", "541": "MN", "542": "MN", "543": "MN", "544": "MN",
    "545": "MN", "546": "MN", "547": "MN", "548": "MN", "549": "MN",
    "550": "MN", "551": "MN", "553": "MN", "554": "MN", "555": "MN",
    "556": "MN", "557": "MN", "558": "MN", "559": "MN",
    "560": "SD", "561": "SD", "562": "SD", "563": "SD", "564": "SD",
    "565": "SD", "566": "SD", "567": "SD",
    "570": "ND", "571": "ND", "572": "ND", "573": "ND", "574": "ND",
    "575": "ND", "576": "ND", "577": "ND", "578": "ND", "579": "ND",
    "580": "ND", "581": "ND", "582": "ND", "583": "ND", "584": "ND",
    "585": "ND", "586": "ND", "587": "ND", "588": "ND",
    "590": "MT", "591": "MT", "592": "MT", "593": "MT", "594": "MT",
    "595": "MT", "596": "MT", "597": "MT", "598": "MT", "599": "MT",
    "600": "IL", "601": "IL", "602": "IL", "603": "IL", "604": "IL",
    "605": "IL", "606": "IL", "607": "IL", "608": "IL", "609": "IL",
    "610": "IL", "611": "IL", "612": "IL", "613": "IL", "614": "IL",
    "615": "IL", "616": "IL", "617": "IL", "618": "IL", "619": "IL",
    "620": "IL", "622": "IL", "623": "IL", "624": "IL", "625": "IL",
    "626": "IL", "627": "IL", "628": "IL", "629": "IL",
    "630": "MO", "631": "MO", "633": "MO", "634": "MO", "635": "MO",
    "636": "MO", "637": "MO", "638": "MO", "639": "MO", "640": "MO",
    "641": "MO", "644": "MO", "645": "MO", "646": "MO", "647": "MO",
    "648": "MO", "649": "MO", "650": "MO", "651": "MO", "652": "MO",
    "653": "MO", "654": "MO", "655": "MO", "656": "MO", "657": "MO",
    "658": "MO",
    "660": "KS", "661": "KS", "662": "KS", "664": "KS", "665": "KS",
    "666": "KS", "667": "KS", "668": "KS", "669": "KS", "670": "KS",
    "671": "KS", "672": "KS", "673": "KS", "674": "KS", "675": "KS",
    "676": "KS", "677": "KS", "678": "KS", "679": "KS",
    "680": "NE", "681": "NE", "683": "NE", "684": "NE", "685": "NE",
    "686": "NE", "687": "NE", "688": "NE", "689": "NE", "690": "NE",
    "691": "NE", "692": "NE", "693": "NE",
    "700": "LA", "701": "LA", "703": "LA", "704": "LA", "705": "LA",
    "706": "LA", "707": "LA", "708": "LA", "710": "LA", "711": "LA",
    "712": "LA", "713": "LA", "714": "LA",
    "716": "AR", "717": "AR", "718": "AR", "719": "AR", "720": "AR",
    "721": "AR", "722": "AR", "723": "AR", "724": "AR", "725": "AR",
    "726": "AR", "727": "AR", "728": "AR", "729": "AR",
    "730": "OK", "731": "OK", "734": "OK", "735": "OK", "736": "OK",
    "737": "OK", "738": "OK", "739": "OK", "740": "OK", "741": "OK",
    "743": "OK", "744": "OK", "745": "OK", "746": "OK", "747": "OK",
    "748": "OK", "749": "OK",
    "750": "TX", "751": "TX", "752": "TX", "753": "TX", "754": "TX",
    "755": "TX", "756": "TX", "757": "TX", "758": "TX", "759": "TX",
    "760": "TX", "761": "TX", "762": "TX", "763": "TX", "764": "TX",
    "765": "TX", "766": "TX", "767": "TX", "768": "TX", "769": "TX",
    "770": "TX", "771": "TX", "772": "TX", "773": "TX", "774": "TX",
    "775": "TX", "776": "TX", "777": "TX", "778": "TX", "779": "TX",
    "780": "TX", "781": "TX", "782": "TX", "783": "TX", "784": "TX",
    "785": "TX", "786": "TX", "787": "TX", "788": "TX", "789": "TX",
    "790": "TX", "791": "TX", "792": "TX", "793": "TX", "794": "TX",
    "795": "TX", "796": "TX", "797": "TX", "798": "TX", "799": "TX",
    "800": "CO", "801": "CO", "802": "CO", "803": "CO", "804": "CO",
    "805": "CO", "806": "CO", "807": "CO", "808": "CO", "809": "CO",
    "810": "CO", "811": "CO", "812": "CO", "813": "CO", "814": "CO",
    "815": "CO", "816": "CO",
    "820": "WY", "821": "WY", "822": "WY", "823": "WY", "824": "WY",
    "825": "WY", "826": "WY", "827": "WY", "828": "WY", "829": "WY",
    "830": "WY", "831": "WY",
    "832": "ID", "833": "ID", "834": "ID", "835": "ID", "836": "ID",
    "837": "ID", "838": "ID",
    "840": "UT", "841": "UT", "842": "UT", "843": "UT", "844": "UT",
    "845": "UT", "846": "UT", "847": "UT",
    "850": "AZ", "851": "AZ", "852": "AZ", "853": "AZ", "855": "AZ",
    "856": "AZ", "857": "AZ", "860": "AZ", "863": "AZ", "864": "AZ",
    "865": "AZ",
    "870": "NM", "871": "NM", "872": "NM", "873": "NM", "874": "NM",
    "875": "NM", "877": "NM", "878": "NM", "879": "NM", "880": "NM",
    "881": "NM", "882": "NM", "883": "NM", "884": "NM",
    "889": "NV", "890": "NV", "891": "NV", "893": "NV", "894": "NV",
    "895": "NV", "897": "NV", "898": "NV",
    "900": "CA", "901": "CA", "902": "CA", "903": "CA", "904": "CA",
    "905": "CA", "906": "CA", "907": "CA", "908": "CA", "910": "CA",
    "911": "CA", "912": "CA", "913": "CA", "914": "CA", "915": "CA",
    "916": "CA", "917": "CA", "918": "CA", "919": "CA", "920": "CA",
    "921": "CA", "922": "CA", "923": "CA", "924": "CA", "925": "CA",
    "926": "CA", "927": "CA", "928": "CA", "930": "CA", "931": "CA",
    "932": "CA", "933": "CA", "934": "CA", "935": "CA", "936": "CA",
    "937": "CA", "938": "CA", "939": "CA", "940": "CA", "941": "CA",
    "942": "CA", "943": "CA", "944": "CA", "945": "CA", "946": "CA",
    "947": "CA", "948": "CA", "949": "CA", "950": "CA", "951": "CA",
    "952": "CA", "953": "CA", "954": "CA", "955": "CA", "956": "CA",
    "957": "CA", "958": "CA", "959": "CA", "960": "CA", "961": "CA",
    "970": "OR", "971": "OR", "972": "OR", "973": "OR", "974": "OR",
    "975": "OR", "976": "OR", "977": "OR", "978": "OR", "979": "OR",
    "980": "WA", "981": "WA", "982": "WA", "983": "WA", "984": "WA",
    "985": "WA", "986": "WA", "988": "WA", "989": "WA", "990": "WA",
    "991": "WA", "992": "WA", "993": "WA", "994": "WA",
    "995": "AK", "996": "AK", "997": "AK", "998": "AK", "999": "AK",
    "967": "HI", "968": "HI",
}


class HumanaAdapter(BaseAdapter):
    carrier_name = "Humana"
    base_url = HUMANA_BASE

    async def search_providers(
        self,
        specialty: str,
        zip_code: str,
        plan_name: str = "",
        limit: int = 50,
    ) -> list[ProviderResult]:
        """
        Find doctors by specialty near a zip code.

        3-step flow (confirmed by live API testing 2/21/2026):
        1. Get all locations in the zip code
        2. For each location, check if a doctor with that specialty works there
        3. Fetch doctor names/NPIs from Practitioner resources
        """
        codes = resolve_specialty(specialty)
        nucc_code = codes.get("nucc")
        specialty_display = codes.get("display") or specialty

        if not nucc_code:
            logger.warning(f"No NUCC code for: {specialty}")
            return []

        zip5 = zip_code.strip()[:5]

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:

                # ── STEP 1: Get locations in this zip code ──
                loc_ids, locations = await self._get_locations(client, zip5)

                # Fallback: try state if zip returned nothing
                if not loc_ids:
                    state = self._zip_to_state(zip5)
                    if state:
                        print(f"[HUMANA] No locations for zip {zip5}, trying state {state}")
                        loc_ids, locations = await self._get_locations_by_state(client, state)

                if not loc_ids:
                    print(f"[HUMANA] No locations found at all")
                    return []

                # ── STEP 2: Find PractitionerRoles at those locations ──
                roles, prac_refs = await self._get_roles_at_locations(
                    client, loc_ids, nucc_code, limit
                )

                if not roles:
                    print(f"[HUMANA] No {specialty_display} found at any location")
                    return []

                print(f"[HUMANA] Found {len(roles)} roles, {len(prac_refs)} unique practitioners to fetch")

                # ── STEP 3: Fetch Practitioner resources for names/NPIs ──
                practitioners = await self._get_practitioners(client, list(prac_refs))

                # ── BUILD RESULTS ──
                results = []
                for role in roles:
                    result = self._build_result(role, practitioners, locations, specialty_display)
                    if result:
                        results.append(result)

                results = self._deduplicate(results, limit)
                print(f"[HUMANA] Final: {len(results)} providers")
                return results

        except Exception as e:
            logger.error(f"Humana search failed: {e}")
            return []

    # ─────────────────────────────────────────────
    # STEP 1: Locations
    # ─────────────────────────────────────────────

    async def _get_locations(self, client: httpx.AsyncClient, zip_code: str):
        """Get all locations in a zip code."""
        print(f"[HUMANA] Step 1: Locations for zip {zip_code}")
        params = {"address-postalcode": zip_code, "_count": "200"}
        try:
            resp = await client.get(f"{HUMANA_BASE}/Location", params=params, headers=HEADERS)
            resp.raise_for_status()
            return self._parse_location_bundle(resp.json() or {})
        except Exception as e:
            print(f"[HUMANA] Location fetch failed: {e}")
            return [], {}

    async def _get_locations_by_state(self, client: httpx.AsyncClient, state: str):
        """Fallback: get locations by state."""
        print(f"[HUMANA] Step 1 fallback: Locations for state {state}")
        params = {"address-state": state, "_count": "200"}
        try:
            resp = await client.get(f"{HUMANA_BASE}/Location", params=params, headers=HEADERS)
            resp.raise_for_status()
            return self._parse_location_bundle(resp.json() or {})
        except Exception as e:
            print(f"[HUMANA] State location fetch failed: {e}")
            return [], {}

    def _parse_location_bundle(self, bundle: dict):
        """Parse Location bundle → (loc_ids, locations_dict)."""
        entries = bundle.get("entry", []) or []
        total = bundle.get("total", len(entries))
        print(f"[HUMANA] Got {len(entries)} locations (total available: {total})")

        locations = {}
        loc_ids = []
        for entry in entries:
            res = (entry or {}).get("resource", {}) or {}
            if res.get("resourceType") != "Location":
                continue
            loc_id = res.get("id", "")
            if not loc_id:
                continue
            loc_ids.append(loc_id)
            locations[loc_id] = res
            full_url = entry.get("fullUrl", "")
            if full_url:
                locations[full_url] = res

        return loc_ids, locations

    # ─────────────────────────────────────────────
    # STEP 2: PractitionerRoles at locations
    # ─────────────────────────────────────────────

    async def _get_roles_at_locations(
        self,
        client: httpx.AsyncClient,
        loc_ids: list[str],
        nucc_code: str,
        limit: int,
    ):
        """
        For each location, ask: does a doctor with this specialty work here?
        Returns (roles_list, practitioner_refs_set).
        """
        NUCC_SYSTEM = "http://nucc.org/provider-taxonomy"
        all_roles = []
        prac_refs = set()

        max_locs = min(len(loc_ids), 100)
        print(f"[HUMANA] Step 2: Checking {max_locs} locations for specialty {nucc_code}")

        hits = 0
        misses = 0

        for i, loc_id in enumerate(loc_ids[:max_locs]):
            params = [
                ("specialty", f"{NUCC_SYSTEM}|{nucc_code}"),
                ("location", f"Location/{loc_id}"),
                ("_count", "50"),
            ]

            try:
                resp = await client.get(
                    f"{HUMANA_BASE}/PractitionerRole",
                    params=params,
                    headers=HEADERS,
                )
                resp.raise_for_status()
                bundle = resp.json() or {}
                entries = bundle.get("entry", []) or []

                if entries:
                    hits += 1
                    for entry in entries:
                        res = entry.get("resource", {})
                        if res.get("resourceType") == "PractitionerRole":
                            res["_matched_location_id"] = loc_id
                            all_roles.append(res)
                            prac_ref = res.get("practitioner", {}).get("reference", "")
                            if prac_ref:
                                prac_refs.add(prac_ref)
                else:
                    misses += 1

            except httpx.TimeoutException:
                print(f"[HUMANA]   Timeout on location {i+1}/{max_locs}")
                continue
            except Exception:
                continue

            if len(all_roles) >= limit:
                break

            if (i + 1) % 20 == 0:
                print(f"[HUMANA]   Progress: {i+1}/{max_locs} checked, {hits} hits, {len(all_roles)} roles")

        print(f"[HUMANA] Step 2 done: {hits} hits / {hits + misses} checked, {len(all_roles)} roles")
        return all_roles, prac_refs

    # ─────────────────────────────────────────────
    # STEP 3: Fetch Practitioners (names, NPIs)
    # ─────────────────────────────────────────────

    async def _get_practitioners(self, client: httpx.AsyncClient, prac_refs: list[str]):
        """
        Fetch Practitioner resources for names and NPIs.
        Refs are full URLs: https://fhir.humana.com/api/Practitioner/{hash}
        Fetches concurrently in batches of 10.
        """
        practitioners = {}
        if not prac_refs:
            return practitioners

        print(f"[HUMANA] Step 3: Fetching {len(prac_refs)} practitioners")

        batch_size = 10
        for i in range(0, len(prac_refs), batch_size):
            batch = prac_refs[i : i + batch_size]
            tasks = [self._fetch_one_practitioner(client, ref) for ref in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for ref, result in zip(batch, results):
                if isinstance(result, Exception) or result is None:
                    continue
                practitioners[ref] = result
                prac_id = result.get("id", "")
                if prac_id:
                    practitioners[prac_id] = result

        fetched = len(set(id(v) for v in practitioners.values()))
        print(f"[HUMANA] Step 3 done: got {fetched} practitioners")
        return practitioners

    async def _fetch_one_practitioner(self, client: httpx.AsyncClient, ref: str):
        """Fetch a single Practitioner. ref is a full URL or ID."""
        try:
            url = ref if ref.startswith("http") else f"{HUMANA_BASE}/Practitioner/{ref}"
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    # ─────────────────────────────────────────────
    # Build ProviderResult
    # ─────────────────────────────────────────────

    def _build_result(
        self,
        role: dict,
        practitioners: dict,
        locations: dict,
        specialty_display: str,
    ) -> ProviderResult | None:
        """Assemble a ProviderResult from PractitionerRole + Practitioner + Location."""
        provider = ProviderResult(carrier="Humana", specialty=specialty_display)

        # ── Practitioner (name, NPI, gender) ──
        prac_ref = role.get("practitioner", {}).get("reference", "")
        prac = practitioners.get(prac_ref) or {}

        if prac:
            names = prac.get("name", [{}])
            name = names[0] if names else {}
            provider.first_name = " ".join(name.get("given", []))
            provider.last_name = name.get("family", "")
            suffixes = name.get("suffix", [])
            provider.credentials = ", ".join(
                s for s in suffixes if s and s.strip() != "\\n"
            )
            for ident in prac.get("identifier", []):
                if ident.get("system") == "http://hl7.org/fhir/sid/us-npi":
                    provider.npi = ident.get("value", "")
                    break
            provider.gender = prac.get("gender", "")
        else:
            # Fallback: parse display name
            prac_display = role.get("practitioner", {}).get("display", "")
            if prac_display:
                name_parts, cred_parts = self._parse_display_name(prac_display)
                if len(name_parts) >= 2:
                    provider.first_name = name_parts[0]
                    provider.last_name = name_parts[-1]
                elif name_parts:
                    provider.last_name = name_parts[0]
                if cred_parts:
                    provider.credentials = ", ".join(cred_parts)
            else:
                return None

        # NPI fallback from role
        if not provider.npi:
            for ident in role.get("identifier", []):
                if ident.get("system", "") == "http://hl7.org/fhir/sid/us-npi":
                    provider.npi = ident.get("value", "")
                    break

        # ── Location (address, coords, phone) ──
        matched_loc_id = role.get("_matched_location_id", "")
        loc = locations.get(matched_loc_id) if matched_loc_id else None

        if not loc:
            loc_refs = role.get("location", [])
            if loc_refs:
                loc_ref = loc_refs[0].get("reference", "")
                loc = locations.get(loc_ref)
                if not loc:
                    loc_id = loc_ref.split("/")[-1] if loc_ref else ""
                    loc = locations.get(loc_id)

        if loc:
            addr = loc.get("address", {})
            lines = addr.get("line", [])
            provider.address_line = lines[0] if lines else ""
            provider.suite = lines[1] if len(lines) > 1 else ""
            provider.city = addr.get("city", "")
            provider.state = addr.get("state", "")
            provider.zip_code = addr.get("postalCode", "")

            position = loc.get("position", {})
            if position:
                provider.latitude = position.get("latitude")
                provider.longitude = position.get("longitude")

            for telecom in loc.get("telecom", []):
                if telecom.get("system") == "phone" and not provider.phone:
                    provider.phone = telecom.get("value", "")
                    break

        # ── Telecom from role ──
        for telecom in role.get("telecom", []):
            system = telecom.get("system", "")
            value = telecom.get("value", "")
            if system == "phone" and not provider.phone:
                provider.phone = value
            elif system == "fax" and not provider.fax:
                provider.fax = value

        # ── Network name ──
        for ext in role.get("extension", []):
            if ext.get("url", "").endswith("network-reference"):
                provider.network_name = ext.get("valueReference", {}).get("display", "")
                break

        # ── Accepting new patients ──
        provider.accepting_new_patients = self._parse_accepting_patients(role)

        if not provider.last_name:
            return None

        return provider

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────

    def _parse_display_name(self, display: str):
        """Parse 'John Smith MD' → ([name_parts], [cred_parts])."""
        CREDS = {
            "MD", "DO", "NP", "PA", "PhD", "DPM", "OD", "DDS",
            "DMD", "DC", "ARNP", "APRN", "RN", "BSN", "MSN",
            "FACC", "FACS", "FACEP", "MPH", "MBA", "MS", "MA",
        }
        parts = display.strip().split()
        name_parts, cred_parts = [], []
        for p in parts:
            clean = p.rstrip(".,")
            if clean.upper() in CREDS:
                cred_parts.append(clean)
            else:
                name_parts.append(p)
        return name_parts, cred_parts

    def _parse_accepting_patients(self, resource: dict) -> bool | None:
        """Check newpatients extension."""
        for ext in resource.get("extension", []):
            if "newpatients" in ext.get("url", ""):
                for sub_ext in ext.get("extension", []):
                    if sub_ext.get("url") == "acceptingPatients":
                        concept = sub_ext.get("valueCodeableConcept", {})
                        codings = concept.get("coding", [])
                        if codings:
                            return codings[0].get("code", "") == "newpt"
        return None

    def _zip_to_state(self, zip_code: str) -> str | None:
        """Zip → state abbreviation using first 3 digits."""
        if not zip_code or len(zip_code) < 3:
            return None
        return ZIP_PREFIX_TO_STATE.get(zip_code[:3])

    def _deduplicate(self, results: list[ProviderResult], limit: int) -> list[ProviderResult]:
        """Deduplicate by NPI or name+zip."""
        seen: set[str] = set()
        unique: list[ProviderResult] = []
        for r in results:
            key = r.npi or f"{r.first_name}_{r.last_name}_{r.zip_code}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(r)
        return unique[:limit]