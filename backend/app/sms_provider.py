"""
Pluggable SMS provider for OTP delivery.

Swap providers by setting SMS_PROVIDER env var:
  - "twilio"  → Twilio SMS (production)
  - "console" → Prints OTP to server logs (development)
"""

import logging
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)


class SMSProvider(ABC):
    """Base class — implement send_otp() for each provider."""

    @abstractmethod
    def send_otp(self, phone: str, code: str) -> bool:
        """Send a 6-digit OTP to the given phone number. Returns True on success."""
        ...


class TwilioProvider(SMSProvider):
    """Production SMS via Twilio."""

    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        from twilio.rest import Client
        self.client = Client(account_sid, auth_token)
        self.from_number = from_number

    def send_otp(self, phone: str, code: str) -> bool:
        try:
            msg = self.client.messages.create(
                body=f"Your InsuranceNYou Concierge verification code is: {code}",
                from_=self.from_number,
                to=f"+1{phone}",
            )
            log.info(f"Twilio SMS sent to +1{phone[-4:]}: sid={msg.sid}")
            return True
        except Exception as e:
            log.error(f"Twilio send failed for +1{phone[-4:]}: {e}")
            return False


class ConsoleProvider(SMSProvider):
    """Dev-only — prints OTP to server logs instead of sending SMS."""

    def send_otp(self, phone: str, code: str) -> bool:
        log.info(f"[DEV OTP] Phone: ***-***-{phone[-4:]} → Code: {code}")
        return True


def create_sms_provider() -> SMSProvider:
    """Factory — reads env vars and returns the configured provider."""
    from .config import SMS_PROVIDER, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER

    if SMS_PROVIDER == "twilio":
        if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER]):
            raise RuntimeError("Twilio credentials not set. Need TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER.")
        return TwilioProvider(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER)

    # Default: console
    log.warning("Using console SMS provider — OTP codes will be printed to logs")
    return ConsoleProvider()
