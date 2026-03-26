"""
Tests for ACGS-2 Audit Data Encryption

Constitutional Hash: 608508a9bd224290
"""

import base64

import pytest

from src.core.shared.errors.exceptions import ConfigurationError
from src.core.shared.security import encryption as encryption_module
from src.core.shared.security.encryption import EncryptionManager


class TestEncryptionManager:
    """Test payload encryption and decryption."""

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encryption followed by decryption returns the original payload."""
        payload = {
            "user_id": "user-123",
            "action": "login",
            "timestamp": "2026-01-04T12:00:00Z",
            "metadata": {"ip": "127.0.0.1"},
        }

        encrypted = EncryptionManager.encrypt_payload(payload)
        assert isinstance(encrypted, str)
        assert len(encrypted) > 0

        decrypted = EncryptionManager.decrypt_payload(encrypted)
        assert decrypted == payload

    def test_encryption_uniqueness(self):
        """Test that encrypting the same payload twice results in different ciphertexts (due to nonce)."""
        payload = {"data": "secret"}

        enc1 = EncryptionManager.encrypt_payload(payload)
        enc2 = EncryptionManager.encrypt_payload(payload)

        assert enc1 != enc2

    def test_tampered_ciphertext(self):
        """Test that tampering with the ciphertext causes decryption failure."""
        payload = {"data": "secret"}
        encrypted = EncryptionManager.encrypt_payload(payload)

        # Tamper with the encrypted string (base64)
        encrypted_bytes = list(base64.b64decode(encrypted))
        encrypted_bytes[-1] ^= 0xFF  # Flip bits in the last byte
        tampered = base64.b64encode(bytes(encrypted_bytes)).decode("utf-8")

        with pytest.raises((ValueError, ConfigurationError), match="Decryption failure"):
            EncryptionManager.decrypt_payload(tampered)

    def test_invalid_payload_type(self):
        """Test that non-dict payloads cause encryption failure if they can't be JSON serialized."""
        # EncryptionManager.encrypt_payload expects a dict
        import datetime

        invalid_payload = {
            "date": datetime.datetime.now()
        }  # Not JSON serializable by default json.dumps

        with pytest.raises((RuntimeError, ConfigurationError), match="Encryption failure"):
            EncryptionManager.encrypt_payload(invalid_payload)

    def test_master_key_missing_fails_closed_in_production_like_env(self, monkeypatch):
        monkeypatch.delenv("ACGS2_ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("AGENT_RUNTIME_ENVIRONMENT", "production")
        monkeypatch.setenv("ACGS2_ALLOW_EPHEMERAL_ENCRYPTION_KEY", "true")
        monkeypatch.setattr(encryption_module, "_MASTER_KEY_CACHE", None)

        with pytest.raises(OSError, match="required in production-like environments"):
            encryption_module._load_master_key()

    def test_master_key_must_decode_to_32_bytes(self, monkeypatch):
        monkeypatch.setenv("ACGS2_ENCRYPTION_KEY", base64.b64encode(b"short-key").decode())
        monkeypatch.setenv("AGENT_RUNTIME_ENVIRONMENT", "development")
        monkeypatch.setattr(encryption_module, "_MASTER_KEY_CACHE", None)

        with pytest.raises(OSError, match="exactly 32 bytes"):
            encryption_module._load_master_key()
