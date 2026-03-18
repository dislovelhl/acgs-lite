"""
ACGS-2 Security Testing Helpers
Constitutional Hash: cdd01ef066bc6cf2
"""

from datetime import timedelta

from src.core.shared.security.auth import create_access_token


def create_test_token(
    user_id: str = "test-user",
    tenant_id: str = "test-tenant",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> str:
    """Create a test JWT token for testing purposes."""
    return create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles or ["user"],
        permissions=permissions or ["read"],
        expires_delta=timedelta(hours=24),
    )


__all__ = ["create_test_token"]
