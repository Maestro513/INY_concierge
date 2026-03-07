"""
Tests for HIPAA compliance modules: encryption, audit logging, PII masking.
"""

import os
import tempfile

import pytest

from app.audit import AuditLog, mask_medicare, mask_phone, mask_pii_in_string
from app.encryption import FieldCipher, generate_key


class TestFieldEncryption:
    @pytest.fixture
    def cipher(self):
        key = generate_key()
        return FieldCipher(key=key)

    def test_encrypt_decrypt_roundtrip(self, cipher):
        original = "1EG4-TE5-MK72"
        encrypted = cipher.encrypt(original)
        assert encrypted != original
        assert encrypted.startswith("enc:")
        decrypted = cipher.decrypt(encrypted)
        assert decrypted == original

    def test_empty_string(self, cipher):
        assert cipher.encrypt("") == ""
        assert cipher.decrypt("") == ""

    def test_none_value(self, cipher):
        assert cipher.encrypt(None) == ""
        assert cipher.decrypt(None) == ""

    def test_already_encrypted_no_double_encrypt(self, cipher):
        original = "test-value"
        encrypted = cipher.encrypt(original)
        double = cipher.encrypt(encrypted)
        assert double == encrypted  # should not double-encrypt

    def test_plaintext_passthrough(self, cipher):
        """Decrypt of non-encrypted value returns it unchanged."""
        assert cipher.decrypt("plain text") == "plain text"

    def test_disabled_cipher(self):
        """No key = encrypt raises RuntimeError, decrypt passes through."""
        cipher = FieldCipher(key="")
        assert cipher.enabled is False
        with pytest.raises(RuntimeError, match="FIELD_ENCRYPTION_KEY is not configured"):
            cipher.encrypt("secret")
        assert cipher.decrypt("secret") == "secret"

    def test_different_keys_cannot_decrypt(self):
        key1 = generate_key()
        key2 = generate_key()
        cipher1 = FieldCipher(key=key1)
        cipher2 = FieldCipher(key=key2)
        encrypted = cipher1.encrypt("sensitive")
        decrypted = cipher2.decrypt(encrypted)
        # Should fail gracefully — returns the encrypted value as-is
        assert decrypted == encrypted


class TestPIIMasking:
    def test_mask_phone(self):
        assert mask_phone("5551234567") == "***-***-4567"

    def test_mask_phone_short(self):
        assert mask_phone("123") == "***"

    def test_mask_phone_none(self):
        assert mask_phone(None) == "***"

    def test_mask_phone_empty(self):
        assert mask_phone("") == "***"

    def test_mask_medicare(self):
        assert mask_medicare("1EG4-TE5-MK72") == "****-***-MK72"

    def test_mask_medicare_short(self):
        assert mask_medicare("AB") == "****"

    def test_mask_pii_in_string_phone(self):
        text = "User 5551234567 logged in"
        masked = mask_pii_in_string(text)
        assert "5551234567" not in masked
        assert "4567" in masked

    def test_mask_pii_in_string_medicare(self):
        text = "Medicare number: 1EG4-TE5-MK72"
        masked = mask_pii_in_string(text)
        assert "1EG4-TE5-MK72" not in masked
        assert "MK72" in masked

    def test_mask_pii_preserves_non_pii(self):
        text = "Plan H1036-077 has 5 tiers"
        masked = mask_pii_in_string(text)
        # H1036-077 is only 9 chars with a letter, should not be masked
        assert "H1036-077" in masked


class TestAuditLog:
    @pytest.fixture
    def audit(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            yield AuditLog(db_path=db_path)
        finally:
            os.unlink(db_path)

    def test_record_and_query(self, audit):
        audit.record(
            actor="5551234567",
            action="read",
            resource="member_data",
            ip_address="192.168.1.1",
        )
        logs = audit.query()
        assert len(logs) == 1
        assert logs[0]["action"] == "read"
        assert logs[0]["resource"] == "member_data"
        # Actor should be masked
        assert "5551234567" not in logs[0]["actor"]
        assert "4567" in logs[0]["actor"]

    def test_query_by_resource(self, audit):
        audit.record(actor="user1", action="read", resource="member_data")
        audit.record(actor="user1", action="read", resource="drug_lookup")
        logs = audit.query(resource="drug_lookup")
        assert len(logs) == 1
        assert logs[0]["resource"] == "drug_lookup"

    def test_query_limit(self, audit):
        for i in range(10):
            audit.record(actor="user1", action="read", resource="test")
        logs = audit.query(limit=5)
        assert len(logs) == 5

    def test_timestamp_present(self, audit):
        audit.record(actor="user1", action="read", resource="test")
        logs = audit.query()
        assert logs[0]["timestamp"].endswith("Z")

    def test_system_actor(self, audit):
        audit.record(actor="system", action="purge", resource="sessions")
        logs = audit.query()
        assert logs[0]["actor"] == "system"
