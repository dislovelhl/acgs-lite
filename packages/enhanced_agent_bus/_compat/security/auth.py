"""Shim for src.core.shared.security.auth."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    from src.core.shared.security.auth import *  # noqa: F403
except ImportError:

    @dataclass
    class UserClaims:
        sub: str = "anonymous"
        email: str = ""
        roles: list[str] = field(default_factory=list)
        tenant_id: str = "default"
        permissions: set[str] = field(default_factory=set)
        metadata: dict[str, Any] = field(default_factory=dict)

    async def get_current_user(**kwargs: Any) -> UserClaims:
        """Stub: always returns anonymous user claims."""
        return UserClaims()

    async def require_auth(**kwargs: Any) -> UserClaims:
        """Stub: always returns anonymous user claims."""
        return UserClaims()

    def verify_token(token: str) -> UserClaims:
        """Stub: always returns anonymous user claims."""
        return UserClaims()
