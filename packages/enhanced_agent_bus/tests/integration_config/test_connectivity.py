"""
Tests for Integration Connectivity Testing.
Constitutional Hash: 608508a9bd224290

Task 7.5: POST /tenants/{tenant_id}/integrations/{integration_id}/test for connectivity testing
"""

from unittest.mock import AsyncMock

from .conftest import (
    IntegrationStatus,
    IntegrationType,
)


class TestConnectivityTesting:
    """Tests for integration connectivity testing."""

    async def test_ldap_connectivity_test(self, integration_service):
        """Test LDAP connectivity check."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={"server_url": "ldap://example.com"},
        )

        result = await integration_service.test_connectivity(integration.id, "tenant-1")

        assert result["success"] is True
        assert "latency_ms" in result
        assert result["integration_id"] == integration.id

    async def test_saml_connectivity_test(self, integration_service):
        """Test SAML connectivity check."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.SAML,
            name="SAML",
            config={"metadata_url": "https://idp.example.com/metadata"},
        )

        result = await integration_service.test_connectivity(integration.id, "tenant-1")

        assert result["success"] is True

    async def test_oidc_connectivity_test(self, integration_service):
        """Test OIDC connectivity check."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.OIDC,
            name="OIDC",
            config={"issuer": "https://auth.example.com"},
        )

        result = await integration_service.test_connectivity(integration.id, "tenant-1")

        assert result["success"] is True

    async def test_connectivity_updates_health_status(self, integration_service):
        """Test that connectivity check updates health status."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={},
        )

        assert integration.health_status is None
        assert integration.last_health_check is None

        await integration_service.test_connectivity(integration.id, "tenant-1")

        assert integration.health_status == "healthy"
        assert integration.last_health_check is not None

    async def test_connectivity_updates_status_to_active(self, integration_service):
        """Test that successful connectivity sets status to ACTIVE."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={},
        )

        assert integration.status == IntegrationStatus.PENDING

        await integration_service.test_connectivity(integration.id, "tenant-1")

        assert integration.status == IntegrationStatus.ACTIVE

    async def test_connectivity_not_found(self, integration_service):
        """Test connectivity check for non-existent integration."""
        result = await integration_service.test_connectivity("non-existent", "tenant-1")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    async def test_connectivity_tenant_isolation(self, integration_service):
        """Test that connectivity check respects tenant isolation."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={},
        )

        result = await integration_service.test_connectivity(
            integration.id,
            "tenant-2",  # Wrong tenant
        )

        assert result["success"] is False

    async def test_connectivity_failure_handling(self, integration_service, health_checker):
        """Test handling of connectivity failures."""
        health_checker.check_ldap = AsyncMock(side_effect=RuntimeError("Connection timeout"))

        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={},
        )

        result = await integration_service.test_connectivity(integration.id, "tenant-1")

        assert result["success"] is False
        assert "error" in result
        assert integration.status == IntegrationStatus.ERROR
