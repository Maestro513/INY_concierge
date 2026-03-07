"""
Field-level encryption for PHI/PII at rest.

Uses Fernet (AES-128-CBC with HMAC) from the cryptography library.
Encrypted values are base64-encoded and prefixed with "enc:" so we can
distinguish them from plaintext during migration.

Usage:
    cipher = FieldCipher(key)
    encrypted = cipher.encrypt("1EG4-TE5-MK72")   # "enc:gAAAAA..."
    plaintext = cipher.decrypt(encrypted)           # "1EG4-TE5-MK72"
    plaintext = cipher.decrypt("already plain")     # "already plain" (no-op)
"""

import base64
import logging
import os

log = logging.getLogger(__name__)

_ENC_PREFIX = "enc:"

# Try to import cryptography; if not available, fall back to no-op
try:
    from cryptography.fernet import Fernet
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False
    log.warning("cryptography package not installed — field encryption disabled")


def generate_key() -> str:
    """Generate a new Fernet key. Store this as FIELD_ENCRYPTION_KEY env var."""
    if not _HAS_CRYPTO:
        raise RuntimeError("cryptography package required: pip install cryptography")
    return Fernet.generate_key().decode()


class FieldCipher:
    """Encrypt/decrypt individual field values for PHI at rest."""

    def __init__(self, key: str = None):
        self.key = key or os.getenv("FIELD_ENCRYPTION_KEY", "")
        self._fernet = None
        if self.key and _HAS_CRYPTO:
            try:
                self._fernet = Fernet(self.key.encode() if isinstance(self.key, str) else self.key)
            except Exception as e:
                log.error(f"Invalid FIELD_ENCRYPTION_KEY: {e}")

    @property
    def enabled(self) -> bool:
        return self._fernet is not None

    def encrypt(self, value: str) -> str:
        """Encrypt a plaintext value. Returns prefixed ciphertext.

        Raises RuntimeError if encryption is not configured, to prevent
        silent storage of PHI as plaintext.
        """
        if not value:
            return ""
        if value.startswith(_ENC_PREFIX):
            return value  # already encrypted
        if not self._fernet:
            raise RuntimeError(
                "PHI encryption required but FIELD_ENCRYPTION_KEY is not configured. "
                "Generate a key with: python -c \"from app.encryption import generate_key; print(generate_key())\""
            )
        token = self._fernet.encrypt(value.encode())
        return _ENC_PREFIX + token.decode()

    def decrypt(self, value: str) -> str:
        """Decrypt an encrypted value. Passes through plaintext unchanged."""
        if not value:
            return ""
        if not value.startswith(_ENC_PREFIX):
            return value  # plaintext — pass through
        if not self._fernet:
            log.warning("Cannot decrypt: FIELD_ENCRYPTION_KEY not configured")
            return value
        try:
            token = value[len(_ENC_PREFIX):]
            return self._fernet.decrypt(token.encode()).decode()
        except Exception as e:
            log.error(f"Decryption failed: {e}")
            return value  # return as-is on failure


# Singleton — configured from env
_cipher = None


def get_cipher() -> FieldCipher:
    global _cipher
    if _cipher is None:
        _cipher = FieldCipher()
        if _cipher.enabled:
            log.info("Field encryption enabled")
        else:
            log.warning("Field encryption disabled — set FIELD_ENCRYPTION_KEY to enable")
    return _cipher
