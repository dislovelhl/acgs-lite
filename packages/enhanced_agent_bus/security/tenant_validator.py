"""
ACGS-2 Enhanced Agent Bus - Tenant Validator
Constitutional Hash: 608508a9bd224290

Provides strict normalization and validation for tenant IDs to ensure consistent isolation.
"""

import re

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


class TenantValidator:
    """Utility for sanitizing and validating tenant identities."""

    # Allow alphanumeric, underscores, and hyphens. 3-64 characters.
    TENANT_ID_PATTERN = re.compile(r"^[a-z0-9_\-]{3,64}$")

    @classmethod
    def normalize(cls, tenant_id: str | None) -> str | None:
        """Normalize tenant_id to a consistent representative form.

        Empty strings and whitespace-only strings are treated as None
        for consistent tenant isolation behavior.
        """
        if tenant_id is None:
            return None

        # 1. Strip whitespace
        normalized = tenant_id.strip()

        # 2. Treat empty strings as None for consistent isolation
        if not normalized:
            return None

        # 3. Convert to lowercase for consistent casing
        normalized = normalized.lower()

        return normalized

    @classmethod
    def validate(cls, tenant_id: str | None) -> bool:
        """Validate that the tenant_id follows strict format rules."""
        if not tenant_id:
            return False

        # Check against regex pattern
        if not cls.TENANT_ID_PATTERN.match(tenant_id):
            logger.warning(
                f"Tenant isolation breach attempt: invalid tenant_id format '{tenant_id}'"
            )
            return False

        return True

    @classmethod
    def sanitize_and_validate(cls, tenant_id: str | None) -> tuple[str | None, bool]:
        """Normalize and then validate the tenant_id."""
        normalized = cls.normalize(tenant_id)
        is_valid = cls.validate(normalized)
        return normalized, is_valid
