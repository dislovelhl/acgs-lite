"""
ACGS-2 Tenant ID Normalizer
Constitutional Hash: 608508a9bd224290

Single source of truth for tenant ID normalization across the codebase.
Replaces scattered tenant normalization logic in 15+ locations.

Usage:
    from src.core.shared.utilities import TenantNormalizer

    normalized = TenantNormalizer.normalize("  TENANT-123  ")  # Returns "tenant-123"
    is_valid = TenantNormalizer.validate("tenant-123")  # Returns True
    normalized, valid = TenantNormalizer.normalize_and_validate("  TENANT-123  ")
"""

import re
import unicodedata

from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)


class TenantNormalizer:
    """
    Utility for normalizing and validating tenant identifiers.

    Provides consistent tenant ID handling across the codebase:
    - Strips whitespace
    - Converts to lowercase
    - Normalizes Unicode characters
    - Validates format (alphanumeric, underscores, hyphens, 3-64 chars)

    Thread-safe and stateless - all methods are classmethods.
    """

    # Allow alphanumeric, underscores, and hyphens. 3-64 characters.
    TENANT_ID_PATTERN = re.compile(r"^[a-z0-9_\-]{3,64}$")

    # Reserved tenant IDs that cannot be used
    RESERVED_TENANTS = frozenset(
        {
            "admin",
            "system",
            "root",
            "default",
            "public",
            "internal",
            "acgs",
            "acgs2",
            "test",
            "none",
            "null",
        }
    )

    # Default tenant ID when none is provided
    DEFAULT_TENANT = "default"

    @classmethod
    def normalize(cls, tenant_id: str | None) -> str | None:
        """
        Normalize tenant_id to a consistent canonical form.

        Args:
            tenant_id: The tenant ID to normalize (can be None)

        Returns:
            Normalized tenant ID string, or None if input is None/empty

        Notes:
            - Empty strings and whitespace-only are treated as None
            - Unicode is normalized to NFKC form to prevent bypasses
            - All values are lowercased for consistent comparison
        """
        if tenant_id is None:
            return None

        # 1. Strip whitespace
        normalized = tenant_id.strip()

        # 2. Treat empty strings as None
        if not normalized:
            return None

        # 3. Normalize Unicode to prevent bypass attacks
        normalized = unicodedata.normalize("NFKC", normalized)

        # 4. Convert to lowercase for consistent casing
        normalized = normalized.lower()

        return normalized

    @classmethod
    def validate(cls, tenant_id: str | None) -> bool:
        """
        Validate that a tenant_id follows strict format rules.

        Args:
            tenant_id: The tenant ID to validate (should already be normalized)

        Returns:
            True if valid, False otherwise

        Notes:
            - Must be 3-64 characters
            - Only alphanumeric, underscores, and hyphens allowed
            - Reserved tenant IDs are invalid
        """
        if not tenant_id:
            return False

        # Check against regex pattern
        if not cls.TENANT_ID_PATTERN.match(tenant_id):
            logger.warning(
                f"Tenant isolation breach attempt: invalid tenant_id format '{tenant_id[:20]}...'"
            )
            return False

        # Check reserved tenants
        if tenant_id in cls.RESERVED_TENANTS:
            logger.warning(f"Attempt to use reserved tenant ID: '{tenant_id}'")
            return False

        return True

    @classmethod
    def normalize_and_validate(cls, tenant_id: str | None) -> tuple[str | None, bool]:
        """
        Normalize and then validate the tenant_id in one operation.

        Args:
            tenant_id: The tenant ID to process

        Returns:
            Tuple of (normalized_tenant_id, is_valid)

        Example:
            tenant, valid = TenantNormalizer.normalize_and_validate("  ACME-Corp  ")
            if valid:
                process_for_tenant(tenant)
        """
        normalized = cls.normalize(tenant_id)
        is_valid = cls.validate(normalized)
        return normalized, is_valid

    @classmethod
    def get_safe_tenant(cls, tenant_id: str | None, default: str = DEFAULT_TENANT) -> str:
        """
        Get a safe tenant ID, falling back to default if invalid.

        Args:
            tenant_id: The tenant ID to process
            default: Default value if tenant is invalid

        Returns:
            Valid tenant ID or default value

        Example:
            tenant = TenantNormalizer.get_safe_tenant(request.tenant_id)
        """
        normalized, is_valid = cls.normalize_and_validate(tenant_id)
        if is_valid and normalized:
            return normalized
        return default

    @classmethod
    def tenants_match(cls, tenant_a: str | None, tenant_b: str | None) -> bool:
        """
        Check if two tenant IDs refer to the same tenant.

        Handles normalization automatically for accurate comparison.

        Args:
            tenant_a: First tenant ID
            tenant_b: Second tenant ID

        Returns:
            True if tenants match after normalization
        """
        norm_a = cls.normalize(tenant_a)
        norm_b = cls.normalize(tenant_b)

        # Both None = match (no tenant context)
        if norm_a is None and norm_b is None:
            return True

        # One None, one not = no match
        if norm_a is None or norm_b is None:
            return False

        return norm_a == norm_b

    @classmethod
    def is_reserved(cls, tenant_id: str | None) -> bool:
        """Check if a tenant ID is reserved."""
        normalized = cls.normalize(tenant_id)
        return normalized in cls.RESERVED_TENANTS if normalized else False
