"""
ACGS-2 JIT Provisioning Service for SSO Authentication
Constitutional Hash: 608508a9bd224290

Provides Just-In-Time (JIT) user provisioning for SSO authentication flows.
Creates new users on first SSO login and updates existing users on subsequent logins.

Usage:
    from src.core.shared.auth.provisioning import JITProvisioner

    # Create provisioner with default settings
    provisioner = JITProvisioner()

    # Provision a user from SSO login
    user = await provisioner.get_or_create_user(
        email="user@example.com",
        name="John Doe",
        sso_provider="oidc",
        idp_user_id="google-12345",
        provider_id="google-workspace-uuid",
        roles=["developer", "viewer"],
    )

    # Provision with SAML-specific fields
    user = await provisioner.get_or_create_user(
        email="user@example.com",
        name="Jane Smith",
        sso_provider="saml",
        idp_user_id="okta-67890",
        provider_id="okta-uuid",
        roles=["admin"],
        name_id="user@example.com",
        session_index="_abc123def456",
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.core.shared.errors.exceptions import ACGSBaseError
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
# Constitutional hash constant
from src.core.shared.constants import CONSTITUTIONAL_HASH


@dataclass
class ProvisioningResult:
    """Result of a JIT provisioning operation.

    Attributes:
        user: The provisioned user object (dict representation for non-ORM usage).
        created: Whether a new user was created (True) or existing user updated (False).
        roles_updated: Whether the user's roles were updated.
        provider_id: The SSO provider ID used for provisioning.
    """

    user: JSONDict
    created: bool
    roles_updated: bool
    provider_id: str | None = None


class ProvisioningError(ACGSBaseError):
    """Base exception for provisioning errors (Q-H4 migration)."""

    http_status_code = 500
    error_code = "PROVISIONING_ERROR"


class DomainNotAllowedError(ProvisioningError):
    """User's email domain is not allowed by the SSO provider."""

    pass


class ProvisioningDisabledError(ProvisioningError):
    """Auto-provisioning is disabled for the SSO provider."""

    pass


class JITProvisioner:
    """Just-In-Time user provisioning service for SSO authentication.

    Handles automatic user creation and updates during SSO login flows.
    Supports both OIDC and SAML 2.0 authentication protocols.

    Features:
    - Creates new users on first SSO login (JIT provisioning)
    - Updates existing users with SSO metadata on subsequent logins
    - Syncs roles from IdP groups on every login
    - Validates email domains against provider restrictions
    - Updates last_login timestamp on every authentication
    - Stores SAML name_id and session_index for SLO support

    Example:
        provisioner = JITProvisioner()

        # Basic provisioning
        result = await provisioner.get_or_create_user(
            email="test-user@example.com",  # Test data only
            name="User Name",
            sso_provider="oidc",
            idp_user_id="sub-123",
        )

        if result.created:

        else:

    Attributes:
        auto_provision_enabled: Whether to allow automatic user creation.
        default_roles: Roles to assign to newly provisioned users.
        allowed_domains: If set, only allow users from these email domains.
    """

    def __init__(
        self,
        auto_provision_enabled: bool = True,
        default_roles: list[str] | None = None,
        allowed_domains: list[str] | None = None,
    ) -> None:
        """Initialize the JIT provisioner.

        Args:
            auto_provision_enabled: Whether to create new users automatically.
            default_roles: Default roles to assign to new users.
            allowed_domains: List of allowed email domains (None = all allowed).
        """
        self.auto_provision_enabled = auto_provision_enabled
        self.default_roles = default_roles or []
        self.allowed_domains = allowed_domains

        logger.debug(
            "JITProvisioner initialized",
            extra={
                "auto_provision_enabled": auto_provision_enabled,
                "default_roles": default_roles,
                "allowed_domains": allowed_domains,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    def _validate_email_domain(self, email: str) -> bool:
        """Validate that the email domain is allowed.

        Args:
            email: Email address to validate.

        Returns:
            True if domain is allowed, False otherwise.
        """
        if not self.allowed_domains:
            return True

        domain = email.split("@")[-1].lower()
        allowed = [d.lower() for d in self.allowed_domains]
        return domain in allowed

    def _normalize_email(self, email: str) -> str:
        """Normalize email address for consistent lookups.

        Args:
            email: Email address to normalize.

        Returns:
            Lowercase, trimmed email address.
        """
        return email.strip().lower()

    def _merge_roles(
        self,
        existing_roles: list[str],
        new_roles: list[str],
        default_roles: list[str] | None = None,
    ) -> tuple[list[str], bool]:
        """Merge roles from different sources.

        IdP-provided roles take precedence. If no IdP roles are provided,
        existing roles are preserved (not cleared). Default roles are only
        applied for new users (when existing_roles is empty).

        Args:
            existing_roles: Current user roles.
            new_roles: Roles from IdP group mapping.
            default_roles: Default roles for new users.

        Returns:
            Tuple of (merged_roles, roles_changed).
        """
        defaults = default_roles or self.default_roles

        # If IdP provides roles, use them (they are authoritative)
        if new_roles:
            merged = sorted(set(new_roles))
        # If no IdP roles and user has no existing roles, use defaults
        elif not existing_roles and defaults:
            merged = sorted(set(defaults))
        # Otherwise preserve existing roles
        else:
            merged = sorted(set(existing_roles))

        changed = merged != sorted(set(existing_roles))
        return merged, changed

    async def get_or_create_user(
        self,
        email: str,
        name: str | None = None,
        sso_provider: str = "oidc",
        idp_user_id: str | None = None,
        provider_id: str | None = None,
        roles: list[str] | None = None,
        name_id: str | None = None,
        session_index: str | None = None,
        session: AsyncSession | None = None,
    ) -> ProvisioningResult:
        """Get existing user or create a new one from SSO authentication.

        This is the main entry point for JIT provisioning. It:
        1. Validates the email domain
        2. Looks up existing user by email
        3. Creates new user if not found (and auto_provision_enabled)
        4. Updates SSO metadata on existing users
        5. Syncs roles from IdP groups
        6. Updates last_login timestamp

        Args:
            email: User's email address (required, primary identifier).
            name: User's display name.
            sso_provider: SSO protocol type ("oidc" or "saml").
            idp_user_id: User's unique ID from the identity provider.
            provider_id: Reference to the SSO provider configuration.
            roles: Roles mapped from IdP groups.
            name_id: SAML NameID for Single Logout (SAML only).
            session_index: SAML SessionIndex for Single Logout (SAML only).
            session: Optional database session for ORM-based provisioning.

        Returns:
            ProvisioningResult with user data and provisioning status.

        Raises:
            DomainNotAllowedError: If email domain is not allowed.
            ProvisioningDisabledError: If auto-provisioning is disabled and user
                                       doesn't exist.
            ProvisioningError: For other provisioning failures.
        """
        normalized_email = self._normalize_email(email)

        # Validate email domain
        if not self._validate_email_domain(normalized_email):
            domain = normalized_email.split("@")[-1]
            logger.warning(
                "SSO login rejected: domain not allowed",
                extra={
                    "email_domain": domain,
                    "provider_id": provider_id,
                    "allowed_domains": self.allowed_domains,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )
            raise DomainNotAllowedError(
                f"Email domain '{domain}' is not allowed for this SSO provider"
            )

        # Try database-backed provisioning if session provided
        if session is not None:
            return await self._provision_with_orm(
                session=session,
                email=normalized_email,
                name=name,
                sso_provider=sso_provider,
                idp_user_id=idp_user_id,
                provider_id=provider_id,
                roles=roles,
                name_id=name_id,
                session_index=session_index,
            )

        # In-memory provisioning for testing or stateless operation
        return await self._provision_in_memory(
            email=normalized_email,
            name=name,
            sso_provider=sso_provider,
            idp_user_id=idp_user_id,
            provider_id=provider_id,
            roles=roles,
            name_id=name_id,
            session_index=session_index,
        )

    async def _provision_with_orm(
        self,
        session: AsyncSession,
        email: str,
        name: str | None,
        sso_provider: str,
        idp_user_id: str | None,
        provider_id: str | None,
        roles: list[str] | None,
        name_id: str | None,
        session_index: str | None,
    ) -> ProvisioningResult:
        """Provision user using SQLAlchemy ORM session.

        Args:
            session: SQLAlchemy AsyncSession.
            email: Normalized email address.
            name: User display name.
            sso_provider: SSO protocol type.
            idp_user_id: IdP user identifier.
            provider_id: SSO provider configuration ID.
            roles: Roles from IdP group mapping.
            name_id: SAML NameID.
            session_index: SAML SessionIndex.

        Returns:
            ProvisioningResult with user data.
        """
        # Import here to avoid circular dependencies
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        from src.core.shared.models.user import SSOProviderType, User

        # Look up existing user by email with eager loading
        stmt = (
            select(User)
            .options(
                joinedload(User.tenant),
                joinedload(User.sso_provider),
                joinedload(User.role_mappings),
            )
            .where(User.email == email)
        )
        result = await session.execute(stmt)
        user = result.unique().scalar_one_or_none()

        created = False
        roles_updated = False

        if user is None:
            # User doesn't exist - check if auto-provisioning is enabled
            if not self.auto_provision_enabled:
                logger.warning(
                    "SSO login rejected: auto-provisioning disabled",
                    extra={
                        "email": email,
                        "provider_id": provider_id,
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                )
                raise ProvisioningDisabledError(
                    "Auto-provisioning is disabled. User must be created by an administrator."
                )

            # Create new user
            provider_type = (
                SSOProviderType.SAML if sso_provider.lower() == "saml" else SSOProviderType.OIDC
            )

            user = User(
                email=email,
                name=name,
                sso_enabled=True,
                sso_provider=provider_type,
                sso_idp_user_id=idp_user_id,
                sso_provider_id=provider_id,
                sso_name_id=name_id,
                sso_session_index=session_index,
                last_login=datetime.now(UTC),
            )

            # Set roles (IdP roles or defaults)
            merged_roles, _ = self._merge_roles([], roles or [], self.default_roles)
            user.set_roles(merged_roles)
            roles_updated = bool(merged_roles)

            session.add(user)
            created = True

            logger.info(
                "JIT provisioning: new user created",
                extra={
                    "user_id": user.id,
                    "email": email,
                    "sso_provider": sso_provider,
                    "provider_id": provider_id,
                    "roles": merged_roles,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        else:
            # Existing user - update SSO metadata
            provider_type = (
                SSOProviderType.SAML if sso_provider.lower() == "saml" else SSOProviderType.OIDC
            )

            # Update SSO info
            user.update_sso_info(
                provider=provider_type,
                idp_user_id=idp_user_id or user.sso_idp_user_id,
                provider_id=provider_id,
                name_id=name_id,
                session_index=session_index,
            )

            # Update name if provided and different
            if name and name != user.name:
                user.name = name

            # Sync roles from IdP
            existing_roles = user.role_list
            merged_roles, roles_updated = self._merge_roles(existing_roles, roles or [])
            if roles_updated:
                user.set_roles(merged_roles)

            logger.info(
                "JIT provisioning: existing user updated",
                extra={
                    "user_id": user.id,
                    "email": email,
                    "sso_provider": sso_provider,
                    "provider_id": provider_id,
                    "roles_updated": roles_updated,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        # Build result dict
        user_dict = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "sso_enabled": user.sso_enabled,
            "sso_provider": user.sso_provider.value if user.sso_provider else None,
            "sso_idp_user_id": user.sso_idp_user_id,
            "sso_provider_id": user.sso_provider_id,
            "sso_name_id": user.sso_name_id,
            "sso_session_index": user.sso_session_index,
            "roles": user.role_list,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }

        return ProvisioningResult(
            user=user_dict,
            created=created,
            roles_updated=roles_updated,
            provider_id=provider_id,
        )

    async def _provision_in_memory(
        self,
        email: str,
        name: str | None,
        sso_provider: str,
        idp_user_id: str | None,
        provider_id: str | None,
        roles: list[str] | None,
        name_id: str | None,
        session_index: str | None,
    ) -> ProvisioningResult:
        """Provision user in-memory (for testing or stateless operation).

        Creates a user dict representation without database persistence.
        Useful for testing, validation, or stateless token-based flows.

        Args:
            email: Normalized email address.
            name: User display name.
            sso_provider: SSO protocol type.
            idp_user_id: IdP user identifier.
            provider_id: SSO provider configuration ID.
            roles: Roles from IdP group mapping.
            name_id: SAML NameID.
            session_index: SAML SessionIndex.

        Returns:
            ProvisioningResult with user data.
        """
        import uuid

        now = datetime.now(UTC)

        # Merge roles (for in-memory, treat as new user)
        merged_roles, _ = self._merge_roles([], roles or [], self.default_roles)

        user_dict = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": name,
            "sso_enabled": True,
            "sso_provider": sso_provider.lower(),
            "sso_idp_user_id": idp_user_id,
            "sso_provider_id": provider_id,
            "sso_name_id": name_id,
            "sso_session_index": session_index,
            "roles": merged_roles,
            "created_at": now.isoformat(),
            "last_login": now.isoformat(),
        }

        logger.debug(
            "JIT provisioning: in-memory user created",
            extra={
                "email": email,
                "sso_provider": sso_provider,
                "provider_id": provider_id,
                "roles": merged_roles,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

        return ProvisioningResult(
            user=user_dict,
            created=True,
            roles_updated=bool(merged_roles),
            provider_id=provider_id,
        )

    async def update_user_roles(
        self,
        user_id: str,
        roles: list[str],
        session: AsyncSession,
    ) -> bool:
        """Update a user's roles.

        Args:
            user_id: User's unique identifier.
            roles: New roles to assign.
            session: SQLAlchemy AsyncSession.

        Returns:
            True if roles were updated, False if no change.

        Raises:
            ProvisioningError: If user not found.
        """
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        from src.core.shared.models.user import User

        stmt = (
            select(User)
            .options(joinedload(User.tenant), joinedload(User.role_mappings))
            .where(User.id == user_id)
        )
        result = await session.execute(stmt)
        user = result.unique().scalar_one_or_none()

        if user is None:
            raise ProvisioningError(f"User not found: {user_id}")

        existing_roles = user.role_list
        merged_roles, changed = self._merge_roles(existing_roles, roles)

        if changed:
            user.set_roles(merged_roles)
            logger.info(
                "User roles updated",
                extra={
                    "user_id": user_id,
                    "old_roles": existing_roles,
                    "new_roles": merged_roles,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        return changed

    async def clear_sso_session(
        self,
        user_id: str,
        session: AsyncSession,
    ) -> None:
        """Clear SSO session data for a user (for logout).

        Clears the SAML name_id and session_index fields while
        preserving the SSO account link.

        Args:
            user_id: User's unique identifier.
            session: SQLAlchemy AsyncSession.

        Raises:
            ProvisioningError: If user not found.
        """
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        from src.core.shared.models.user import User

        stmt = select(User).options(joinedload(User.tenant)).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.unique().scalar_one_or_none()

        if user is None:
            raise ProvisioningError(f"User not found: {user_id}")

        user.clear_sso_session()

        logger.info(
            "SSO session cleared for user",
            extra={
                "user_id": user_id,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )


# Module-level singleton for convenience
_default_provisioner: JITProvisioner | None = None


def get_provisioner(
    auto_provision_enabled: bool = True,
    default_roles: list[str] | None = None,
    allowed_domains: list[str] | None = None,
) -> JITProvisioner:
    """Get or create the default JIT provisioner.

    Creates a singleton instance if not already initialized.
    Subsequent calls return the same instance unless reset.

    Args:
        auto_provision_enabled: Whether to create new users automatically.
        default_roles: Default roles to assign to new users.
        allowed_domains: List of allowed email domains.

    Returns:
        JITProvisioner instance.
    """
    global _default_provisioner

    if _default_provisioner is None:
        _default_provisioner = JITProvisioner(
            auto_provision_enabled=auto_provision_enabled,
            default_roles=default_roles,
            allowed_domains=allowed_domains,
        )

    return _default_provisioner


def reset_provisioner() -> None:
    """Reset the default provisioner singleton.

    Useful for testing or reconfiguration.
    """
    global _default_provisioner
    _default_provisioner = None
