"""
Carrier-specific constants for Digital ID Card.
RxBIN, RxPCN, RxGroup, customer service numbers, etc.
"""

CARRIER_RX_CONFIG = {
    "humana": {
        "rx_bin": "600428",
        "rx_pcn": "05",
        "rx_group": "HUMRX",
        "customer_service": "1-800-457-4708",
        "customer_service_tty": "711",
        "pharmacy_help": "1-800-379-0092",
        "prior_auth": "1-800-555-2546",
        "website": "www.humana.com",
    },
    "uhc": {
        "rx_bin": "610494",
        "rx_pcn": "9999",
        "rx_group": "RXGRP",
        "customer_service": "1-877-596-3258",
        "customer_service_tty": "711",
        "pharmacy_help": "1-877-889-6358",
        "prior_auth": "1-800-711-4555",
        "website": "www.uhc.com",
    },
    "aetna": {
        "rx_bin": "004336",
        "rx_pcn": "ADV",
        "rx_group": "RX",
        "customer_service": "1-855-338-7027",
        "customer_service_tty": "711",
        "pharmacy_help": "1-866-693-2211",
        "prior_auth": "1-855-338-7027",
        "website": "www.aetna.com",
    },
    "devoted": {
        "rx_bin": "610020",
        "rx_pcn": "HDI",
        "rx_group": "DEVOTED",
        "customer_service": "1-800-338-6833",
        "customer_service_tty": "711",
        "pharmacy_help": "1-800-338-6833",
        "prior_auth": "1-800-338-6833",
        "website": "www.devoted.com",
    },
    "wellcare": {
        "rx_bin": "600428",
        "rx_pcn": "06",
        "rx_group": "WCRX",
        "customer_service": "1-866-530-9491",
        "customer_service_tty": "711",
        "pharmacy_help": "1-866-530-9491",
        "prior_auth": "1-866-530-9491",
        "website": "www.wellcare.com",
    },
    "zing": {
        "rx_bin": "610494",
        "rx_pcn": "ZING",
        "rx_group": "ZINGRX",
        "customer_service": "1-855-950-9464",
        "customer_service_tty": "711",
        "pharmacy_help": "1-855-950-9464",
        "prior_auth": "1-855-950-9464",
        "website": "www.zinghealthplan.com",
    },
    "healthspring": {
        "rx_bin": "610494",
        "rx_pcn": "HSRX",
        "rx_group": "HSRX",
        "customer_service": "1-800-668-3813",
        "customer_service_tty": "711",
        "pharmacy_help": "1-800-668-3813",
        "prior_auth": "1-800-668-3813",
        "website": "www.myhealthspring.com",
    },
}


def detect_carrier(plan_name: str, org_name: str = "") -> str | None:
    """Detect carrier key from plan or org name."""
    combined = (plan_name + " " + org_name).lower()
    if "humana" in combined:
        return "humana"
    if "uhc" in combined or "unitedhealthcare" in combined or "aarp" in combined:
        return "uhc"
    if "aetna" in combined:
        return "aetna"
    if "devoted" in combined:
        return "devoted"
    if "wellcare" in combined:
        return "wellcare"
    if "zing" in combined:
        return "zing"
    if "healthspring" in combined:
        return "healthspring"
    return None


def get_carrier_config(carrier_key: str) -> dict:
    """Get carrier Rx config, or empty dict if unknown."""
    return CARRIER_RX_CONFIG.get(carrier_key, {})
