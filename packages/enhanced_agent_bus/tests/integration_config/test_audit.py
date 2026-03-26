"""
Tests for Delete with Audit Archival.
Constitutional Hash: 608508a9bd224290

Task 7.7: DELETE /tenants/{tenant_id}/integrations/{integration_id} with audit archival
"""

from .conftest import (
    CONSTITUTIONAL_HASH,
    IntegrationType,
)


class TestDeleteWithAuditArchival:
    """Tests for integration deletion with audit archival."""

    async def test_delete_creates_audit_log(self, integration_service):
        """Test that deletion creates an audit log entry."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="To Delete",
            config={"server_url": "ldap://example.com"},
        )

        await integration_service.delete_integration(
            integration.id,
            "tenant-1",
            deleted_by="admin@example.com",
        )

        logs = integration_service.get_audit_logs("tenant-1", integration.id)
        delete_logs = [log for log in logs if log["action"] == "delete"]

        assert len(delete_logs) == 1
        assert delete_logs[0]["actor"] == "admin@example.com"

    async def test_delete_archives_config(self, integration_service):
        """Test that deletion archives the configuration."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="Archived Integration",
            config={"server_url": "ldap://example.com"},
        )

        await integration_service.delete_integration(
            integration.id,
            "tenant-1",
        )

        logs = integration_service.get_audit_logs("tenant-1", integration.id)
        delete_log = next(log for log in logs if log["action"] == "delete")

        assert "archived_config" in delete_log["details"]
        assert delete_log["details"]["name"] == "Archived Integration"

    async def test_delete_archives_with_redacted_sensitive(self, integration_service):
        """Test that archived config has redacted sensitive fields."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="With Secrets",
            config={"bind_password": "secret"},
        )

        await integration_service.delete_integration(integration.id, "tenant-1")

        logs = integration_service.get_audit_logs("tenant-1", integration.id)
        delete_log = next(log for log in logs if log["action"] == "delete")

        archived_config = delete_log["details"]["archived_config"]["config"]
        assert archived_config["bind_password"] == "********"

    async def test_all_crud_operations_audited(self, integration_service):
        """Test that all CRUD operations are audited."""
        # Create
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="Audited",
            config={},
        )

        # Update
        await integration_service.update_integration(
            integration.id,
            "tenant-1",
            {"name": "Updated"},
        )

        # Delete
        await integration_service.delete_integration(integration.id, "tenant-1")

        logs = integration_service.get_audit_logs("tenant-1", integration.id)
        actions = {log["action"] for log in logs}

        assert "create" in actions
        assert "update" in actions
        assert "delete" in actions

    async def test_audit_includes_constitutional_hash(self, integration_service):
        """Test that audit logs include constitutional hash."""
        integration = await integration_service.create_integration(
            tenant_id="tenant-1",
            integration_type=IntegrationType.LDAP,
            name="Test",
            config={},
        )

        logs = integration_service.get_audit_logs("tenant-1")

        for log in logs:
            assert log["constitutional_hash"] == CONSTITUTIONAL_HASH
