"""
Permission Controller for Collaborative Editing.

Manages role-based editing rights, read-only vs edit access,
approval workflows, and audit logging of edits.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.collaboration.models import (
    CollaborationSession,
    PermissionDeniedError,
    UserPermissions,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

_AUDIT_LOG_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class PermissionController:
    """
    Controls access to collaborative editing features.

    Enforces MACI role separation - agents never validate their own output.
    All permission checks go through independent validation.
    """

    def __init__(self, audit_client: object | None = None):
        self.audit_client = audit_client
        self._lock = asyncio.Lock()
        self._document_permissions: dict[str, dict[str, UserPermissions]] = {}
        self._edit_approvals: dict[str, dict[str, bool]] = {}  # document_id -> user_id -> approved

    async def check_permission(
        self,
        user_id: str,
        document_id: str,
        required_permission: UserPermissions,
        tenant_id: str | None = None,
    ) -> bool:
        """
        Check if user has required permission for document.

        Args:
            user_id: User to check
            document_id: Target document
            required_permission: Minimum permission level needed
            tenant_id: Optional tenant for validation

        Returns:
            True if permission granted

        Raises:
            PermissionDeniedError: If permission check fails
        """
        async with self._lock:
            user_perm = await self._get_user_permission(user_id, document_id)

            permission_hierarchy = {
                UserPermissions.READ: 0,
                UserPermissions.WRITE: 1,
                UserPermissions.ADMIN: 2,
            }

            if permission_hierarchy[user_perm] < permission_hierarchy[required_permission]:
                logger.warning(
                    "Permission denied",
                    extra={
                        "user_id": user_id,
                        "document_id": document_id,
                        "required": required_permission.value,
                        "actual": user_perm.value,
                    },
                )
                raise PermissionDeniedError(
                    f"User {user_id} lacks {required_permission.value} permission for {document_id}"
                )

            # Log permission check for audit
            await self._log_permission_check(user_id, document_id, required_permission, True)
            return True

    async def _get_user_permission(self, user_id: str, document_id: str) -> UserPermissions:
        """Get user's permission level for a document."""
        if document_id not in self._document_permissions:
            # Default: users have read permission
            return UserPermissions.READ

        user_perms = self._document_permissions[document_id]
        return user_perms.get(user_id, UserPermissions.READ)

    async def set_permission(
        self,
        document_id: str,
        user_id: str,
        permission: UserPermissions,
        granted_by: str,
    ) -> None:
        """
        Set permission level for a user on a document.

        Args:
            document_id: Target document
            user_id: User to set permission for
            permission: Permission level to grant
            granted_by: User granting the permission
        """
        async with self._lock:
            if document_id not in self._document_permissions:
                self._document_permissions[document_id] = {}

            old_permission = self._document_permissions[document_id].get(user_id)
            self._document_permissions[document_id][user_id] = permission

            logger.info(
                "Permission updated",
                extra={
                    "document_id": document_id,
                    "user_id": user_id,
                    "old_permission": old_permission.value if old_permission else None,
                    "new_permission": permission.value,
                    "granted_by": granted_by,
                },
            )

            await self._log_permission_change(document_id, user_id, permission, granted_by)

    async def can_edit(self, user_id: str, document_id: str) -> bool:
        """Check if user can edit the document."""
        try:
            await self.check_permission(user_id, document_id, UserPermissions.WRITE)
            return True
        except PermissionDeniedError:
            return False

    async def can_admin(self, user_id: str, document_id: str) -> bool:
        """Check if user has admin rights on the document."""
        try:
            await self.check_permission(user_id, document_id, UserPermissions.ADMIN)
            return True
        except PermissionDeniedError:
            return False

    async def require_edit_permission(self, user_id: str, document_id: str) -> None:
        """Require write permission, raising if not present."""
        await self.check_permission(user_id, document_id, UserPermissions.WRITE)

    async def require_admin_permission(self, user_id: str, document_id: str) -> None:
        """Require admin permission, raising if not present."""
        await self.check_permission(user_id, document_id, UserPermissions.ADMIN)

    async def lock_document(
        self, document_id: str, user_id: str, session: CollaborationSession
    ) -> bool:
        """
        Lock document for exclusive editing.

        Args:
            document_id: Document to lock
            user_id: User requesting lock
            session: Current collaboration session

        Returns:
            True if lock acquired

        Raises:
            PermissionDeniedError: If user lacks admin permission
        """
        await self.require_admin_permission(user_id, document_id)

        async with self._lock:
            if session.is_locked and session.locked_by != user_id:
                logger.warning(
                    "Lock denied - document already locked",
                    extra={
                        "document_id": document_id,
                        "requested_by": user_id,
                        "locked_by": session.locked_by,
                    },
                )
                return False

            session.is_locked = True
            session.locked_by = user_id

            await self._log_document_lock(document_id, user_id, locked=True)
            return True

    async def unlock_document(
        self, document_id: str, user_id: str, session: CollaborationSession
    ) -> bool:
        """
        Unlock a document.

        Args:
            document_id: Document to unlock
            user_id: User requesting unlock
            session: Current collaboration session

        Returns:
            True if unlocked
        """
        await self.require_admin_permission(user_id, document_id)

        async with self._lock:
            if not session.is_locked:
                return True

            # Only the locker or an admin can unlock
            if session.locked_by != user_id:
                # Still need admin to override another admin's lock
                pass  # Already checked admin above

            session.is_locked = False
            session.locked_by = None

            await self._log_document_lock(document_id, user_id, locked=False)
            return True

    async def request_edit_approval(self, document_id: str, user_id: str) -> str:
        """
        Request approval for editing a protected document.

        Returns:
            Approval request ID
        """
        approval_id = f"approval:{document_id}:{user_id}:{datetime.now(UTC).timestamp()}"

        if document_id not in self._edit_approvals:
            self._edit_approvals[document_id] = {}

        self._edit_approvals[document_id][user_id] = False  # Pending approval

        logger.info(
            "Edit approval requested",
            extra={
                "approval_id": approval_id,
                "document_id": document_id,
                "user_id": user_id,
            },
        )

        await self._log_approval_request(approval_id, document_id, user_id)
        return approval_id

    async def approve_edit(self, document_id: str, user_id: str, approved_by: str) -> bool:
        """
        Approve edit request for a user.

        Args:
            document_id: Document being edited
            user_id: User being approved
            approved_by: Admin approving the request

        Returns:
            True if approved
        """
        await self.require_admin_permission(approved_by, document_id)

        if document_id not in self._edit_approvals:
            self._edit_approvals[document_id] = {}

        self._edit_approvals[document_id][user_id] = True

        # Grant write permission temporarily
        await self.set_permission(document_id, user_id, UserPermissions.WRITE, approved_by)

        logger.info(
            "Edit approved",
            extra={
                "document_id": document_id,
                "user_id": user_id,
                "approved_by": approved_by,
            },
        )

        await self._log_approval_grant(document_id, user_id, approved_by)
        return True

    async def is_edit_approved(self, document_id: str, user_id: str) -> bool:
        """Check if user has pending edit approval."""
        if document_id not in self._edit_approvals:
            return False
        return self._edit_approvals[document_id].get(user_id, False)

    async def validate_operation(
        self,
        user_id: str,
        document_id: str,
        operation_type: str,
        operation_data: JSONDict,
    ) -> bool:
        """
        Validate an edit operation before application.

        Performs MACI-compliant validation - independent of operation source.

        Args:
            user_id: User performing the operation
            document_id: Target document
            operation_type: Type of operation
            operation_data: Operation details

        Returns:
            True if valid

        Raises:
            PermissionDeniedError: If operation not allowed
            CollaborationError: If validation fails
        """
        # Check basic edit permission
        await self.require_edit_permission(user_id, document_id)

        # Validate based on operation type
        validation_rules = {
            "delete": UserPermissions.ADMIN,  # Deletes require admin
            "move": UserPermissions.WRITE,
            "replace": UserPermissions.WRITE,
            "insert": UserPermissions.WRITE,
        }

        required_perm = validation_rules.get(operation_type, UserPermissions.WRITE)
        await self.check_permission(user_id, document_id, required_perm)

        # Log validation success
        await self._log_operation_validation(user_id, document_id, operation_type, True)

        return True

    async def _log_permission_check(
        self,
        user_id: str,
        document_id: str,
        permission: UserPermissions,
        granted: bool,
    ) -> None:
        """Log permission check to audit trail."""
        if self.audit_client:
            try:
                await self.audit_client.log_event(
                    event_type="collaboration.permission_check",
                    details={
                        "user_id": user_id,
                        "document_id": document_id,
                        "permission": permission.value,
                        "granted": granted,
                    },
                )
            except _AUDIT_LOG_ERRORS as e:
                logger.error(f"Failed to log permission check: {e}")

    async def _log_permission_change(
        self,
        document_id: str,
        user_id: str,
        permission: UserPermissions,
        granted_by: str,
    ) -> None:
        """Log permission change to audit trail."""
        if self.audit_client:
            try:
                await self.audit_client.log_event(
                    event_type="collaboration.permission_change",
                    details={
                        "document_id": document_id,
                        "user_id": user_id,
                        "permission": permission.value,
                        "granted_by": granted_by,
                    },
                )
            except _AUDIT_LOG_ERRORS as e:
                logger.error(f"Failed to log permission change: {e}")

    async def _log_document_lock(self, document_id: str, user_id: str, locked: bool) -> None:
        """Log document lock/unlock to audit trail."""
        if self.audit_client:
            try:
                await self.audit_client.log_event(
                    event_type=f"collaboration.document_{'locked' if locked else 'unlocked'}",
                    details={
                        "document_id": document_id,
                        "user_id": user_id,
                    },
                )
            except _AUDIT_LOG_ERRORS as e:
                logger.error(f"Failed to log document lock: {e}")

    async def _log_approval_request(self, approval_id: str, document_id: str, user_id: str) -> None:
        """Log approval request to audit trail."""
        if self.audit_client:
            try:
                await self.audit_client.log_event(
                    event_type="collaboration.approval_requested",
                    details={
                        "approval_id": approval_id,
                        "document_id": document_id,
                        "user_id": user_id,
                    },
                )
            except _AUDIT_LOG_ERRORS as e:
                logger.error(f"Failed to log approval request: {e}")

    async def _log_approval_grant(self, document_id: str, user_id: str, approved_by: str) -> None:
        """Log approval grant to audit trail."""
        if self.audit_client:
            try:
                await self.audit_client.log_event(
                    event_type="collaboration.approval_granted",
                    details={
                        "document_id": document_id,
                        "user_id": user_id,
                        "approved_by": approved_by,
                    },
                )
            except _AUDIT_LOG_ERRORS as e:
                logger.error(f"Failed to log approval grant: {e}")

    async def _log_operation_validation(
        self,
        user_id: str,
        document_id: str,
        operation_type: str,
        valid: bool,
    ) -> None:
        """Log operation validation to audit trail."""
        if self.audit_client:
            try:
                await self.audit_client.log_event(
                    event_type="collaboration.operation_validation",
                    details={
                        "user_id": user_id,
                        "document_id": document_id,
                        "operation_type": operation_type,
                        "valid": valid,
                    },
                )
            except _AUDIT_LOG_ERRORS as e:
                logger.error(f"Failed to log operation validation: {e}")

    def get_document_permissions(self, document_id: str) -> dict[str, UserPermissions]:
        """Get all permissions for a document."""
        return self._document_permissions.get(document_id, {}).copy()

    async def remove_user_permissions(self, document_id: str, user_id: str) -> None:
        """Remove all permissions for a user on a document."""
        async with self._lock:
            if document_id in self._document_permissions:
                self._document_permissions[document_id].pop(user_id, None)
