"""
Tests for Sensitive Data Encryption and Vault Integration.
Constitutional Hash: 608508a9bd224290

Task 7.2: POST /tenants/{tenant_id}/integrations with encryption
Task 7.3: HashiCorp Vault integration for encryption key storage
"""

import base64
from unittest.mock import AsyncMock

from .conftest import (
    CONSTITUTIONAL_HASH,
    EncryptionService,
    IntegrationType,
)


class TestSensitiveDataEncryption:
    """Tests for encryption of sensitive configuration data."""

    async def test_password_field_encrypted(self, integration_service):
        """Test that password fields are encrypted."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={"bind_password": "secret123"},
        )

        assert "bind_password" in integration.encrypted_fields
        # The stored value should be encrypted (base64)
        assert integration.config["bind_password"] != "secret123"

    async def test_secret_field_encrypted(self, integration_service):
        """Test that secret fields are encrypted."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.OIDC,
            name="OIDC",
            config={"client_secret": "super-secret-value"},
        )

        assert "client_secret" in integration.encrypted_fields

    async def test_api_key_field_encrypted(self, integration_service):
        """Test that api_key fields are encrypted."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.SIEM,
            name="Splunk",
            config={"api_key": "splunk-api-key-123"},
        )

        assert "api_key" in integration.encrypted_fields

    async def test_certificate_field_encrypted(self, integration_service):
        """Test that certificate fields are encrypted."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.SAML,
            name="SAML",
            config={"private_key": "test-key-placeholder-for-unit-testing"},
        )

        assert "private_key" in integration.encrypted_fields

    async def test_non_sensitive_fields_not_encrypted(self, integration_service):
        """Test that non-sensitive fields are not encrypted."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={
                "server_url": "ldap://example.com",
                "base_dn": "dc=example,dc=com",
            },
        )

        assert "server_url" not in integration.encrypted_fields
        assert "base_dn" not in integration.encrypted_fields
        assert integration.config["server_url"] == "ldap://example.com"

    async def test_encryption_service_roundtrip(self, encryption_service):
        """Test that encryption/decryption roundtrip works."""
        original = "super-secret-password"

        encrypted = await encryption_service.encrypt(original)
        decrypted = await encryption_service.decrypt(encrypted["ciphertext"])

        assert decrypted == original

    async def test_update_encrypts_new_sensitive_fields(self, integration_service):
        """Test that updates encrypt new sensitive fields."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={"server_url": "ldap://example.com"},
        )

        await integration_service.update_integration(
            integration_id=integration.id,
            tenant_id="tenant-1",
            updates={"config": {"bind_password": "new-secret"}},
        )

        assert "bind_password" in integration.encrypted_fields


class TestVaultIntegration:
    """Tests for HashiCorp Vault integration."""

    async def test_vault_encrypt_called(self):
        """Test that Vault transit engine is used when available."""
        mock_vault = AsyncMock()
        mock_vault.secrets.transit.encrypt_data = AsyncMock(
            return_value={"data": {"ciphertext": "vault:v1:encrypted-data"}}
        )

        encryption = EncryptionService(vault_client=mock_vault)
        result = await encryption.encrypt("secret-data")

        mock_vault.secrets.transit.encrypt_data.assert_called_once()
        assert result["ciphertext"] == "vault:v1:encrypted-data"

    async def test_vault_decrypt_called(self):
        """Test that Vault transit engine is used for decryption."""
        mock_vault = AsyncMock()
        mock_vault.secrets.transit.decrypt_data = AsyncMock(
            return_value={"data": {"plaintext": base64.b64encode(b"secret-data").decode()}}
        )

        encryption = EncryptionService(vault_client=mock_vault)
        result = await encryption.decrypt("vault:v1:encrypted-data")

        mock_vault.secrets.transit.decrypt_data.assert_called_once()
        assert result == "secret-data"

    async def test_vault_custom_key_id(self):
        """Test using custom key ID with Vault."""
        mock_vault = AsyncMock()
        mock_vault.secrets.transit.encrypt_data = AsyncMock(
            return_value={"data": {"ciphertext": "vault:v1:encrypted"}}
        )

        encryption = EncryptionService(vault_client=mock_vault)
        await encryption.encrypt("data", key_id="custom-key")

        mock_vault.secrets.transit.encrypt_data.assert_called_with(
            name="custom-key",
            plaintext=base64.b64encode(b"data").decode(),
        )

    def test_fallback_to_local_encryption(self):
        """Test fallback to local encryption when Vault unavailable."""
        encryption = EncryptionService(vault_client=None)
        assert encryption._vault_client is None
        assert encryption._local_key is not None
