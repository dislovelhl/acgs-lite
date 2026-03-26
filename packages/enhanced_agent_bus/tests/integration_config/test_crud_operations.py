"""
Tests for Integration CRUD Operations.
Constitutional Hash: 608508a9bd224290

Task 7.1: API integration tests for CRUD operations
"""

from .conftest import (
    CONSTITUTIONAL_HASH,
    IntegrationStatus,
    IntegrationType,
)


class TestIntegrationCRUD:
    """Tests for integration CRUD operations."""

    async def test_create_ldap_integration(self, integration_service):
        """Test creating an LDAP integration."""
        config = {
            "server_url": "ldap://ldap.example.com:389",
            "base_dn": "dc=example,dc=com",
            "bind_dn": "cn=admin,dc=example,dc=com",
            "bind_password": "secret123",  # Sensitive
        }

        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="Corporate LDAP",
            config=config,
            created_by="admin@example.com",
        )

        assert integration.id is not None
        assert integration.tenant_id == "tenant-1"
        assert integration.integration_type == IntegrationType.LDAP
        assert integration.name == "Corporate LDAP"
        assert integration.status == IntegrationStatus.PENDING
        assert integration.created_by == "admin@example.com"

    async def test_create_saml_integration(self, integration_service):
        """Test creating a SAML integration."""
        config = {
            "idp_metadata_url": "https://idp.example.com/metadata",
            "entity_id": "acgs-sp",
            "certificate": "-----BEGIN CERTIFICATE-----...",  # Sensitive
        }

        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.SAML,
            name="Corporate SAML IdP",
            config=config,
        )

        assert integration.integration_type == IntegrationType.SAML
        assert "certificate" in integration.encrypted_fields

    async def test_create_oidc_integration(self, integration_service):
        """Test creating an OIDC integration."""
        config = {
            "issuer": "https://auth.example.com",
            "client_id": "acgs-client",
            "client_secret": "super-secret",  # Sensitive
            "redirect_uri": "https://acgs.example.com/callback",
        }

        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.OIDC,
            name="Corporate OIDC",
            config=config,
        )

        assert integration.integration_type == IntegrationType.OIDC
        assert "client_secret" in integration.encrypted_fields

    async def test_get_integration(self, integration_service):
        """Test getting an integration by ID."""
        created = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="Test LDAP",
            config={"server_url": "ldap://localhost"},
        )

        retrieved = integration_service.get_integration(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Test LDAP"

    async def test_get_integration_tenant_isolation(self, integration_service):
        """Test tenant isolation when getting integrations."""
        created = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="Test LDAP",
            config={"server_url": "ldap://localhost"},
        )

        # Should not find with wrong tenant
        result = integration_service.get_integration(created.id, tenant_id="tenant-2")
        assert result is None

    async def test_list_integrations(self, integration_service):
        """Test listing integrations for a tenant."""
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
        await integration_service.create_integration(
            tenant_id="tenant-2",
            integration_type=IntegrationType.OIDC,
            name="OIDC 1",
            config={},
        )

        tenant1_integrations = integration_service.list_integrations("tenant-1")
        assert len(tenant1_integrations) == 2

        tenant2_integrations = integration_service.list_integrations("tenant-2")
        assert len(tenant2_integrations) == 1

    async def test_list_integrations_by_type(self, integration_service):
        """Test filtering integrations by type."""
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

        ldap_integrations = integration_service.list_integrations(
            "tenant-1", integration_type=IntegrationType.LDAP
        )
        assert len(ldap_integrations) == 1
        assert ldap_integrations[0].integration_type == IntegrationType.LDAP

    async def test_list_integrations_by_status(self, integration_service):
        """Test filtering integrations by status."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="LDAP 1",
            config={},
        )
        integration.status = IntegrationStatus.ACTIVE

        active = integration_service.list_integrations("tenant-1", status=IntegrationStatus.ACTIVE)
        assert len(active) == 1

        pending = integration_service.list_integrations(
            "tenant-1", status=IntegrationStatus.PENDING
        )
        assert len(pending) == 0

    async def test_update_integration(self, integration_service):
        """Test updating an integration."""
        created = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="Original Name",
            config={"server_url": "ldap://old.example.com"},
        )

        original_updated_at = created.updated_at

        updated = await integration_service.update_integration(
            integration_id=created.id,
            tenant_id="tenant-1",
            updates={
                "name": "New Name",
                "config": {"server_url": "ldap://new.example.com"},
            },
            updated_by="admin@example.com",
        )

        assert updated is not None
        assert updated.name == "New Name"
        assert updated.config["server_url"] == "ldap://new.example.com"
        assert updated.updated_at >= original_updated_at

    async def test_update_integration_wrong_tenant(self, integration_service):
        """Test update fails for wrong tenant."""
        created = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="Test",
            config={},
        )

        result = await integration_service.update_integration(
            integration_id=created.id,
            tenant_id="tenant-2",  # Wrong tenant
            updates={"name": "Hacked"},
        )

        assert result is None

    async def test_delete_integration(self, integration_service):
        """Test deleting an integration."""
        created = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="To Delete",
            config={},
        )

        result = await integration_service.delete_integration(
            integration_id=created.id,
            tenant_id="tenant-1",
            deleted_by="admin@example.com",
        )

        assert result is True
        assert integration_service.get_integration(created.id) is None

    async def test_delete_integration_wrong_tenant(self, integration_service):
        """Test delete fails for wrong tenant."""
        created = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="Test",
            config={},
        )

        result = await integration_service.delete_integration(
            integration_id=created.id,
            tenant_id="tenant-2",  # Wrong tenant
        )

        assert result is False
        assert integration_service.get_integration(created.id) is not None
