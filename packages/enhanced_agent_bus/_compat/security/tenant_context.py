"""Shim for src.core.shared.security.tenant_context."""
from __future__ import annotations

from typing import Any

try:
    from src.core.shared.security.tenant_context import *  # noqa: F403
except ImportError:

    class TenantContext:
        """Minimal tenant context stub."""

        def __init__(self, tenant_id: str = "default", **kwargs: Any) -> None:
            self.tenant_id = tenant_id
            self.metadata: dict[str, Any] = kwargs

        def __repr__(self) -> str:
            return f"TenantContext(tenant_id={self.tenant_id!r})"

    _current_tenant: str = "default"

    def get_tenant_id() -> str:
        return _current_tenant

    def set_tenant_id(tenant_id: str) -> None:
        global _current_tenant  # noqa: PLW0603
        _current_tenant = tenant_id

    def get_tenant_context() -> TenantContext:
        return TenantContext(tenant_id=_current_tenant)
