"""
Tests for Configuration Updates.
Constitutional Hash: 608508a9bd224290

Task 7.6: PATCH /tenants/{tenant_id}/integrations/{integration_id} for config updates
"""

from .conftest import (
    IntegrationStatus,
    IntegrationType,
)


class TestConfigurationUpdates:
    """Tests for updating integration configurations."""

    async def test_update_name(self, integration_service):
        """Test updating integration name."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="Old Name",
            config={},
        )

        updated = await integration_service.update_integration(
            integration.id,
            "tenant-1",
            {"name": "New Name"},
        )

        assert updated.name == "New Name"

    async def test_update_enabled_status(self, integration_service):
        """Test enabling/disabling integration."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={},
        )

        updated = await integration_service.update_integration(
            integration.id,
            "tenant-1",
            {"enabled": False},
        )

        assert updated.enabled is False

    async def test_update_status(self, integration_service):
        """Test updating integration status."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={},
        )

        updated = await integration_service.update_integration(
            integration.id,
            "tenant-1",
            {"status": "active"},
        )

        assert updated.status == IntegrationStatus.ACTIVE

    async def test_update_config_non_sensitive(self, integration_service):
        """Test updating non-sensitive config fields."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={"server_url": "ldap://old.example.com"},
        )

        updated = await integration_service.update_integration(
            integration.id,
            "tenant-1",
            {"config": {"server_url": "ldap://new.example.com"}},
        )

        assert updated.config["server_url"] == "ldap://new.example.com"

    async def test_update_config_sensitive(self, integration_service):
        """Test updating sensitive config fields encrypts them."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={"bind_password": "old-password"},
        )

        await integration_service.update_integration(
            integration.id,
            "tenant-1",
            {"config": {"bind_password": "new-password"}},
        )

        # New password should be encrypted
        assert integration.config["bind_password"] != "new-password"
        assert "bind_password" in integration.encrypted_fields

    async def test_update_updates_timestamp(self, integration_service):
        """Test that update modifies updated_at timestamp."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP",
            config={},
        )

        original_updated = integration.updated_at

        await integration_service.update_integration(
            integration.id,
            "tenant-1",
            {"name": "Updated"},
        )

        assert integration.updated_at >= original_updated

    async def test_update_nonexistent(self, integration_service):
        """Test updating non-existent integration returns None."""
        result = await integration_service.update_integration(
            "non-existent",
            "tenant-1",
            {"name": "New Name"},
        )

        assert result is None
