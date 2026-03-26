"""
Tests for Health Monitoring.
Constitutional Hash: 608508a9bd224290

Task 7.8: Health monitoring for all integration types
"""

from datetime import UTC, datetime, timezone

from .conftest import (
    CONSTITUTIONAL_HASH,
    IntegrationType,
)


class TestHealthMonitoring:
    """Tests for integration health monitoring."""

    async def test_check_all_health(self, integration_service):
        """Test checking health of all integrations."""
        await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP 1",
            config={},
        )
        await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.SAML,
            name="SAML 1",
            config={},
        )

        results = await integration_service.check_all_health("tenant-1")

        assert len(results) == 2
        assert all(r["success"] for r in results)

    async def test_check_all_health_only_enabled(self, integration_service):
        """Test that health check only includes enabled integrations."""
        enabled = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="Enabled",
            config={},
        )

        disabled = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.SAML,
            name="Disabled",
            config={},
        )
        disabled.enabled = False

        results = await integration_service.check_all_health("tenant-1")

        assert len(results) == 1
        assert results[0]["name"] == "Enabled"

    async def test_health_summary(self, integration_service):
        """Test health summary generation."""
        integration1 = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP 1",
            config={},
        )
        integration1.health_status = "healthy"

        integration2 = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.SAML,
            name="SAML 1",
            config={},
        )
        integration2.health_status = "unhealthy"

        summary = integration_service.get_health_summary("tenant-1")

        assert summary["total"] == 2
        assert summary["healthy"] == 1
        assert summary["unhealthy"] == 1
        assert summary["unknown"] == 0

    async def test_health_summary_includes_constitutional_hash(self, integration_service):
        """Test that health summary includes constitutional hash."""
        summary = integration_service.get_health_summary("tenant-1")
        assert summary["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_health_check_updates_last_check_time(self, integration_service):
        """Test that health check updates last check timestamp."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={},
        )

        before_check = datetime.now(UTC)
        await integration_service.test_connectivity(integration.id, "tenant-1")

        assert integration.last_health_check is not None
        assert integration.last_health_check >= before_check
