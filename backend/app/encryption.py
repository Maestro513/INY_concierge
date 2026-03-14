"""
Field-level encryption for PHI/PII at rest.

Uses AES-256-GCM for new encryptions (authenticated encryption with
256-bit key strength). Retains Fernet (AES-128-CBC + HMAC-SHA256) as a
read-only fallback so existing data can be decrypted without a bulk
migration — re-encrypting lazily on next write.

Key derivation:
    The existing FIELD_ENCRYPTION_KEY (Fernet-format, 32 bytes base64)
    is fed through HKDF-SHA256 to derive a 256-bit AES-GCM key.  No env
    var changes are needed.

Encrypted values are base64-encoded and prefixed:
    "enc2:" → AES-256-GCM  (new)
    "enc:"  → Fernet/AES-128-CBC  (legacy, read-only)

Usage:
    cipher = FieldCipher(key)
    encrypted = cipher.encrypt("1EG4-TE5-MK72")   # "enc2:..."
    plaintext = cipher.decrypt(encrypted)           # "1EG4-TE5-MK72"
    plaintext = cipher.decrypt("enc:gAAAAA...")     # legacy Fernet → still works
    plaintext = cipher.decrypt("already plain")     # "already plain" (no-op)
"""

import base64
import logging
import os

log = logging.getLogger(__name__)

_ENC_PREFIX_LEGACY = "enc:"   # Fernet AES-128-CBC (read-only)
_ENC_PREFIX = "enc2:"         # AES-256-GCM (current)

# Try to import cryptography; if not available, fall back to no-op
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False
    log.warning("cryptography package not installed — field encryption disabled")


def _derive_aes256_key(fernet_key_b64: str) -> bytes:
    """Derive a 32-byte AES-256 key from the existing Fernet key via HKDF."""
    raw = base64.urlsafe_b64decode(fernet_key_b64.encode())
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"iny-concierge-aes256-gcm",
    ).derive(raw)


def generate_key() -> str:
    """Generate a new Fernet-format key. Store this as FIELD_ENCRYPTION_KEY env var.

    The Fernet key is used as source material; AES-256-GCM key is derived
    from it via HKDF at runtime.
    """
    if not _HAS_CRYPTO:
        raise RuntimeError("cryptography package required: pip install cryptography")
    return Fernet.generate_key().decode()


class FieldCipher:
    """Encrypt/decrypt individual field values for PHI at rest.

    New writes use AES-256-GCM.  Old Fernet-encrypted values are still
    readable (decrypted via legacy fallback).
    """

    def __init__(self, key: str = None):
        self.key = key or os.getenv("FIELD_ENCRYPTION_KEY", "")
        self._aesgcm = None
        self._fernet = None  # legacy read-only fallback
        if self.key and _HAS_CRYPTO:
            try:
                derived = _derive_aes256_key(self.key)
                self._aesgcm = AESGCM(derived)
                # Keep Fernet around for decrypting legacy "enc:" values
                self._fernet = Fernet(self.key.encode() if isinstance(self.key, str) else self.key)
            except Exception as e:
                log.error(f"Invalid FIELD_ENCRYPTION_KEY: {e}")

    @property
    def enabled(self) -> bool:
        return self._aesgcm is not None

    def encrypt(self, value: str) -> str:
        """Encrypt a plaintext value using AES-256-GCM. Returns prefixed ciphertext.

        Raises RuntimeError if encryption is not configured, to prevent
        silent storage of PHI as plaintext.
        """
        if not value:
            return ""
        if value.startswith(_ENC_PREFIX) or value.startswith(_ENC_PREFIX_LEGACY):
            return value  # already encrypted
        if not self._aesgcm:
            raise RuntimeError(
                "PHI encryption required but FIELD_ENCRYPTION_KEY is not configured. "
                "Generate a key with: python -c \"from app.encryption import generate_key; print(generate_key())\""
            )
        # AES-GCM needs a 12-byte nonce (96-bit, NIST recommended)
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, value.encode(), None)
        # Store as: enc2:<base64(nonce + ciphertext)>
        payload = base64.urlsafe_b64encode(nonce + ciphertext).decode()
        return _ENC_PREFIX + payload

    def decrypt(self, value: str) -> str:
        """Decrypt an encrypted value. Handles both AES-256-GCM and legacy Fernet.

        Passes through plaintext unchanged.
        """
        if not value:
            return ""

        # AES-256-GCM (current format)
        if value.startswith(_ENC_PREFIX):
            if not self._aesgcm:
                log.warning("Cannot decrypt: FIELD_ENCRYPTION_KEY not configured")
                return value
            try:
                payload = base64.urlsafe_b64decode(value[len(_ENC_PREFIX):])
                nonce = payload[:12]
                ciphertext = payload[12:]
                return self._aesgcm.decrypt(nonce, ciphertext, None).decode()
            except Exception:
                log.error("Decryption failed for AES-256-GCM field — data may be corrupted")
                raise ValueError(
                    "Failed to decrypt field value. The encryption key may have changed or data is corrupted."
                )

        # Legacy Fernet (AES-128-CBC) — read-only fallback
        if value.startswith(_ENC_PREFIX_LEGACY):
            if not self._fernet:
                log.warning("Cannot decrypt legacy Fernet: FIELD_ENCRYPTION_KEY not configured")
                return value
            try:
                token = value[len(_ENC_PREFIX_LEGACY):]
                return self._fernet.decrypt(token.encode()).decode()
            except Exception:
                log.error("Decryption failed for legacy Fernet field — data may be corrupted")
                raise ValueError(
                    "Failed to decrypt field value. The encryption key may have changed or data is corrupted."
                )

        # Plaintext — pass through
        return value


# Singleton — configured from env
_cipher = None


def get_cipher() -> FieldCipher:
    global _cipher
    if _cipher is None:
        _cipher = FieldCipher()
        if _cipher.enabled:
            log.info("Field encryption enabled (AES-256-GCM)")
        else:
            log.warning("Field encryption disabled — set FIELD_ENCRYPTION_KEY to enable")
    return _cipher
