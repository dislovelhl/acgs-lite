"""
ACGS-2 System Tenant Utilities
Constitutional Hash: cdd01ef066bc6cf2

Provides constants and utilities for working with the system tenant.
The system tenant is the default tenant for backward compatibility
and system-level resources.

Usage:
    from packages.enhanced_agent_bus.multi_tenancy.system_tenant import (
        SYSTEM_TENANT_ID,
        SYSTEM_TENANT_SLUG,
        is_system_tenant,
        get_system_tenant,
    )

    # Check if a tenant is the system tenant
    if is_system_tenant(tenant_id):
        # Handle system tenant case
        pass

    # Get the system tenant from the database
    system_tenant = await get_system_tenant(repository)
"""

from .context import CONSTITUTIONAL_HASH
from .models import Tenant, TenantConfig, TenantStatus

# Well-known system tenant identifiers
# These UUIDs are consistent across all deployments
SYSTEM_TENANT_ID = "00000000-0000-0000-0000-000000000001"
SYSTEM_TENANT_SLUG = "system"
SYSTEM_TENANT_NAME = "System"


def is_system_tenant(tenant_id: str | None) -> bool:
    """Check if the given tenant_id is the system tenant.

    Args:
        tenant_id: Tenant identifier to check.

    Returns:
        True if this is the system tenant, False otherwise.
    """
    return tenant_id == SYSTEM_TENANT_ID


def is_system_tenant_slug(slug: str | None) -> bool:
    """Check if the given slug is the system tenant slug.

    Args:
        slug: Tenant slug to check.

    Returns:
        True if this is the system tenant slug, False otherwise.
    """
    return slug == SYSTEM_TENANT_SLUG


def get_system_tenant_defaults() -> Tenant:
    """Get a Tenant instance with system tenant defaults.

    This returns a Pydantic Tenant model with the standard system
    tenant configuration. Use this for creating the system tenant
    if it doesn't exist.

    Returns:
        Tenant instance with system tenant configuration.
    """
    return Tenant(
        tenant_id=SYSTEM_TENANT_ID,
        name=SYSTEM_TENANT_NAME,
        slug=SYSTEM_TENANT_SLUG,
        status=TenantStatus.ACTIVE,
        config=TenantConfig(),
        quota={},
        metadata={
            "description": "Default system tenant for backward compatibility",
            "is_system": True,
        },
    )


async def get_system_tenant(repository) -> Tenant | None:
    """Get the system tenant from a repository.

    Args:
        repository: TenantRepository or DatabaseTenantRepository instance.

    Returns:
        System tenant if found, None otherwise.
    """
    return await repository.get_tenant(SYSTEM_TENANT_ID)  # type: ignore[no-any-return]


async def ensure_system_tenant(repository) -> Tenant:
    """Ensure the system tenant exists, creating it if necessary.

    Args:
        repository: TenantRepository or DatabaseTenantRepository instance.

    Returns:
        System tenant instance.
    """
    # First check by ID
    tenant = await repository.get_tenant(SYSTEM_TENANT_ID)
    if tenant:
        return tenant  # type: ignore[no-any-return]

    # Also check by slug in case it was created with a different ID
    tenant = await repository.get_tenant_by_slug(SYSTEM_TENANT_SLUG)
    if tenant:
        return tenant  # type: ignore[no-any-return]

    # Create the system tenant with the well-known ID
    defaults = get_system_tenant_defaults()
    return await repository.create_tenant(  # type: ignore[no-any-return]
        name=defaults.name,
        slug=defaults.slug,
        config=defaults.config,
        metadata=defaults.metadata,
        tenant_id=SYSTEM_TENANT_ID,
    )


def get_tenant_id_or_system(tenant_id: str | None) -> str:
    """Return the given tenant_id or fall back to system tenant.

    Args:
        tenant_id: Tenant identifier, may be None.

    Returns:
        The tenant_id if provided, otherwise SYSTEM_TENANT_ID.
    """
    return tenant_id if tenant_id else SYSTEM_TENANT_ID


__all__ = [
    "CONSTITUTIONAL_HASH",
    "SYSTEM_TENANT_ID",
    "SYSTEM_TENANT_NAME",
    "SYSTEM_TENANT_SLUG",
    "ensure_system_tenant",
    "get_system_tenant",
    "get_system_tenant_defaults",
    "get_tenant_id_or_system",
    "is_system_tenant",
    "is_system_tenant_slug",
]
