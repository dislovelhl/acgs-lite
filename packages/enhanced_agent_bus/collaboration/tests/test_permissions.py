"""
Tests for Permission Controller.

Constitutional Hash: 608508a9bd224290
"""

import asyncio

import pytest

from enhanced_agent_bus.collaboration.models import (
    CollaborationSession,
    DocumentLockedError,
    DocumentType,
    PermissionDeniedError,
    UserPermissions,
)
from enhanced_agent_bus.collaboration.permissions import PermissionController


class TestPermissionController:
    """Test Permission Controller."""

    @pytest.fixture
    def permission_controller(self):
        return PermissionController()

    @pytest.fixture
    def sample_session(self):
        return CollaborationSession(
            document_id="doc-123",
            document_type=DocumentType.POLICY,
            tenant_id="tenant-1",
        )

    async def test_check_permission_read(self, permission_controller):
        # Default permission is READ
        result = await permission_controller.check_permission(
            "user-1", "doc-123", UserPermissions.READ
        )
        assert result is True

    async def test_check_permission_write_denied(self, permission_controller):
        # Default permission is READ, so WRITE should fail
        with pytest.raises(PermissionDeniedError):
            await permission_controller.check_permission("user-1", "doc-123", UserPermissions.WRITE)

    async def test_set_permission(self, permission_controller):
        await permission_controller.set_permission(
            "doc-123", "user-1", UserPermissions.WRITE, "admin"
        )

        # Now write should succeed
        result = await permission_controller.check_permission(
            "user-1", "doc-123", UserPermissions.WRITE
        )
        assert result is True

    async def test_permission_hierarchy(self, permission_controller):
        # Admin should have all permissions
        await permission_controller.set_permission(
            "doc-123", "user-admin", UserPermissions.ADMIN, "system"
        )

        # Admin can read
        assert await permission_controller.check_permission(
            "user-admin", "doc-123", UserPermissions.READ
        )

        # Admin can write
        assert await permission_controller.check_permission(
            "user-admin", "doc-123", UserPermissions.WRITE
        )

        # Admin can admin
        assert await permission_controller.check_permission(
            "user-admin", "doc-123", UserPermissions.ADMIN
        )

    async def test_can_edit_helper(self, permission_controller):
        assert await permission_controller.can_edit("user-1", "doc-123") is False

        await permission_controller.set_permission(
            "doc-123", "user-1", UserPermissions.WRITE, "admin"
        )

        assert await permission_controller.can_edit("user-1", "doc-123") is True

    async def test_lock_document(self, permission_controller, sample_session):
        # Set admin permission
        await permission_controller.set_permission(
            "doc-123", "admin-user", UserPermissions.ADMIN, "system"
        )

        # Lock document
        result = await permission_controller.lock_document("doc-123", "admin-user", sample_session)
        assert result is True
        assert sample_session.is_locked is True
        assert sample_session.locked_by == "admin-user"

    async def test_lock_document_already_locked(self, permission_controller, sample_session):
        await permission_controller.set_permission(
            "doc-123", "admin-1", UserPermissions.ADMIN, "system"
        )
        await permission_controller.set_permission(
            "doc-123", "admin-2", UserPermissions.ADMIN, "system"
        )

        # First lock
        await permission_controller.lock_document("doc-123", "admin-1", sample_session)

        # Second lock should fail
        result = await permission_controller.lock_document("doc-123", "admin-2", sample_session)
        assert result is False

    async def test_unlock_document(self, permission_controller, sample_session):
        await permission_controller.set_permission(
            "doc-123", "admin-user", UserPermissions.ADMIN, "system"
        )

        # Lock then unlock
        await permission_controller.lock_document("doc-123", "admin-user", sample_session)
        result = await permission_controller.unlock_document(
            "doc-123", "admin-user", sample_session
        )

        assert result is True
        assert sample_session.is_locked is False
        assert sample_session.locked_by is None

    async def test_edit_approval_workflow(self, permission_controller):
        # Request approval
        approval_id = await permission_controller.request_edit_approval("doc-123", "user-1")
        assert approval_id is not None
        assert "approval:" in approval_id

        # Not approved yet
        assert await permission_controller.is_edit_approved("doc-123", "user-1") is False

        # Set admin
        await permission_controller.set_permission(
            "doc-123", "admin", UserPermissions.ADMIN, "system"
        )

        # Approve
        result = await permission_controller.approve_edit("doc-123", "user-1", "admin")
        assert result is True

        # Now approved
        assert await permission_controller.is_edit_approved("doc-123", "user-1") is True

    async def test_validate_operation(self, permission_controller):
        # Without permission
        with pytest.raises(PermissionDeniedError):
            await permission_controller.validate_operation(
                "user-1", "doc-123", "insert", {"path": "/test"}
            )

        # Grant write permission
        await permission_controller.set_permission(
            "doc-123", "user-1", UserPermissions.WRITE, "admin"
        )

        # Now should succeed
        result = await permission_controller.validate_operation(
            "user-1", "doc-123", "insert", {"path": "/test"}
        )
        assert result is True

    async def test_validate_operation_delete_requires_admin(self, permission_controller):
        # Grant write permission
        await permission_controller.set_permission(
            "doc-123", "user-1", UserPermissions.WRITE, "admin"
        )

        # Delete requires admin
        with pytest.raises(PermissionDeniedError):
            await permission_controller.validate_operation(
                "user-1", "doc-123", "delete", {"path": "/test"}
            )

        # Grant admin
        await permission_controller.set_permission(
            "doc-123", "user-1", UserPermissions.ADMIN, "system"
        )

        # Now delete should succeed
        result = await permission_controller.validate_operation(
            "user-1", "doc-123", "delete", {"path": "/test"}
        )
        assert result is True

    async def test_get_document_permissions(self, permission_controller):
        await permission_controller.set_permission(
            "doc-123", "user-1", UserPermissions.READ, "admin"
        )
        await permission_controller.set_permission(
            "doc-123", "user-2", UserPermissions.WRITE, "admin"
        )
        await permission_controller.set_permission(
            "doc-123", "user-3", UserPermissions.ADMIN, "system"
        )

        perms = permission_controller.get_document_permissions("doc-123")

        assert len(perms) == 3
        assert perms["user-1"] == UserPermissions.READ
        assert perms["user-2"] == UserPermissions.WRITE
        assert perms["user-3"] == UserPermissions.ADMIN

    async def test_remove_user_permissions(self, permission_controller):
        await permission_controller.set_permission(
            "doc-123", "user-1", UserPermissions.WRITE, "admin"
        )

        assert await permission_controller.can_edit("user-1", "doc-123") is True

        await permission_controller.remove_user_permissions("doc-123", "user-1")

        assert await permission_controller.can_edit("user-1", "doc-123") is False
