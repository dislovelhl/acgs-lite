"""
Tests for Credential Redaction in API Responses.
Constitutional Hash: 608508a9bd224290

Task 7.4: GET /tenants/{tenant_id}/integrations with credential redaction
"""

from .conftest import (
    CONSTITUTIONAL_HASH,
    IntegrationType,
)


class TestCredentialRedaction:
    """Tests for credential redaction in API responses."""

    async def test_to_dict_redacts_sensitive_fields(self, integration_service):
        """Test that to_dict redacts sensitive fields."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={
                "server_url": "ldap://example.com",
                "bind_password": "secret",
            },
        )

        data = integration.to_dict(redact_sensitive=True)

        assert data["config"]["server_url"] == "ldap://example.com"
        assert data["config"]["bind_password"] == "********"

    async def test_to_dict_without_redaction(self, integration_service):
        """Test that to_dict can return encrypted values."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={"bind_password": "secret"},
        )

        data = integration.to_dict(redact_sensitive=False)

        # Should contain encrypted ciphertext, not redacted
        assert data["config"]["bind_password"] != "********"
        assert data["config"]["bind_password"] != "secret"

    async def test_multiple_sensitive_fields_redacted(self, integration_service):
        """Test that all sensitive fields are redacted."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.OIDC,
            name="OIDC",
            config={
                "client_id": "client-123",
                "client_secret": "secret-abc",
                "api_key": "key-xyz",
            },
        )

        data = integration.to_dict(redact_sensitive=True)

        assert data["config"]["client_id"] == "client-123"
        assert data["config"]["client_secret"] == "********"
        assert data["config"]["api_key"] == "********"

    async def test_redacted_response_includes_metadata(self, integration_service):
        """Test that redacted response includes all metadata."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="Test LDAP",
            config={"bind_password": "secret"},
            created_by="admin@example.com",
        )

        data = integration.to_dict(redact_sensitive=True)

        assert data["id"] is not None
        assert data["tenant_id"] == "tenant-1"
        assert data["integration_type"] == "ldap"
        assert data["name"] == "Test LDAP"
        assert data["status"] == "pending"
        assert data["created_by"] == "admin@example.com"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH
