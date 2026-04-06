"""Shim for src.core.shared.security.rbac."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.security.rbac import *  # noqa: F403
except ImportError:

    async def validate_operator_token(token: str = "", **kwargs: Any) -> str:
        """Stub: returns a dummy operator identity in standalone/dev mode."""
        return f"dev-operator:{token[:16]}" if token else "dev-operator:anonymous"

    async def check_permission(
        user_id: str = "",
        permission: str = "",
        resource: str = "",
        **kwargs: Any,
    ) -> bool:
        """Stub: always returns True in standalone mode."""
        return True

    class RBACEnforcer:
        """No-op RBAC enforcer stub."""

        def __init__(self, **kwargs: Any) -> None:
            pass

        async def enforce(self, subject: str, action: str, resource: str) -> bool:
            return True

        async def has_role(self, subject: str, role: str) -> bool:
            return True
