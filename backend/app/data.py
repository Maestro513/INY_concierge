"""Sample data mirroring the frontend constants/data.js for demo purposes."""

SAMPLE_MEMBER = {
    "firstName": "Dorothy",
    "lastName": "Johnson",
    "carrier": "UHC",
    "planName": "AARP Medicare Advantage (PPO)",
    "planId": "H0028-007",
}

SAMPLE_BENEFITS = [
    {"label": "PCP Visit", "value": "$0", "icon": "stethoscope"},
    {"label": "Specialist", "value": "$30", "icon": "doctor"},
    {"label": "Drug Deductible", "value": "$0", "icon": "pill"},
    {"label": "Max Out-of-Pocket", "value": "$3,900", "icon": "shield"},
]

EXTRA_BENEFITS = [
    {"label": "Dental", "value": "$1,500", "icon": "tooth", "has": True},
    {"label": "OTC", "value": "$75/qtr", "icon": "cart", "has": True},
    {"label": "Flex Card", "value": "$200", "icon": "card", "has": False},
    {"label": "Part B Giveback", "value": "$100/mo", "icon": "money", "has": True},
]

SAMPLE_SOB = {
    "medical": [
        {"label": "Inpatient Hospital", "value": "$325/day (days 1-5)"},
        {"label": "Outpatient Surgery", "value": "$250 copay"},
        {"label": "Emergency Room", "value": "$90 copay"},
        {"label": "Urgent Care", "value": "$40 copay"},
    ],
    "drugs": [
        {"label": "Tier 1 (Preferred Generic)", "value": "$0"},
        {"label": "Tier 2 (Generic)", "value": "$12"},
        {"label": "Tier 3 (Preferred Brand)", "value": "$47"},
        {"label": "Tier 4 (Non-Preferred)", "value": "$100"},
    ],
}

SAMPLE_DOCTORS = [
    {"id": "1", "name": "Dr. Sarah Chen", "specialty": "Primary Care", "distance": "0.8 mi", "address": "123 Main St, Suite 200", "rating": 4.8, "accepting": True},
    {"id": "2", "name": "Dr. Marcus Johnson", "specialty": "Primary Care", "distance": "1.2 mi", "address": "456 Oak Ave, Floor 3", "rating": 4.6, "accepting": True},
    {"id": "3", "name": "Dr. Priya Patel", "specialty": "Internal Medicine", "distance": "2.1 mi", "address": "789 Elm Blvd", "rating": 4.9, "accepting": False},
    {"id": "4", "name": "Dr. Robert Kim", "specialty": "Family Medicine", "distance": "2.5 mi", "address": "321 Pine Rd, Suite 100", "rating": 4.7, "accepting": True},
]

SAMPLE_MEDICATIONS = [
    {"id": "1", "name": "Eliquis (Apixaban)", "tier": "Tier 3", "copay": "$47", "daysSupply": "30-day", "pharmacy": "Preferred Retail"},
    {"id": "2", "name": "Lisinopril", "tier": "Tier 1", "copay": "$0", "daysSupply": "90-day", "pharmacy": "Mail Order"},
    {"id": "3", "name": "Atorvastatin", "tier": "Tier 1", "copay": "$0", "daysSupply": "90-day", "pharmacy": "Mail Order"},
    {"id": "4", "name": "Metformin", "tier": "Tier 1", "copay": "$0", "daysSupply": "30-day", "pharmacy": "Preferred Retail"},
]

SAMPLE_PHARMACIES = [
    {"id": "1", "name": "CVS Pharmacy", "address": "100 Broadway, New York, NY 10005", "distance": "0.3 mi", "phone": "2125551234", "preferred": True, "hours": "Open until 9 PM"},
    {"id": "2", "name": "Walgreens", "address": "250 Fulton St, New York, NY 10007", "distance": "0.5 mi", "phone": "2125555678", "preferred": True, "hours": "Open 24 hours"},
    {"id": "3", "name": "Rite Aid", "address": "55 Water St, New York, NY 10004", "distance": "0.7 mi", "phone": "2125559012", "preferred": False, "hours": "Open until 8 PM"},
    {"id": "4", "name": "Duane Reade", "address": "44 Wall St, New York, NY 10005", "distance": "0.9 mi", "phone": "2125553456", "preferred": True, "hours": "Open until 10 PM"},
]

QUICK_QUESTIONS = [
    "What's my specialist copay?",
    "Is Eliquis covered?",
    "Do I have dental?",
]

SAMPLE_ANSWERS = {
    "What's my specialist copay?": "Your specialist copay is $30 per visit with an in-network provider. Out-of-network visits are $70.",
    "Is Eliquis covered?": "Yes! Eliquis is on your formulary at Tier 3 (Preferred Brand). Your copay is $47 for a 30-day supply at a preferred retail pharmacy.",
    "Do I have dental?": "Yes! Your plan includes preventive dental — oral exams and cleanings at $0 copay, up to 2 per year. Comprehensive dental has a $1,500 annual max.",
}

CALL_NUMBER = "8444632931"

# OTP store (in-memory for demo — use Redis/DB in production)
otp_store: dict[str, str] = {}
