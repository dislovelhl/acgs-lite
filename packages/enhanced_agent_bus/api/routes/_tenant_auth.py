"""Tenant authentication helpers. Constitutional Hash: 608508a9bd224290"""

from __future__ import annotations

import os
import re
import warnings
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import Header, HTTPException, Request

DEV_ENVIRONMENTS = frozenset(("development", "dev", "test", "testing", "ci"))
_FALLBACK_TENANT_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


def _get_environment() -> str:
    """Read environment at call time, not import time."""
    return os.environ.get("ENVIRONMENT", "").lower()


def _validate_fallback_tenant_id(raw_tenant_id: str) -> str:
    cleaned = raw_tenant_id.strip().lower()
    if not cleaned:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header is required")
    if len(cleaned) > 128:
        raise HTTPException(status_code=400, detail="X-Tenant-ID too long (max 128)")
    if not _FALLBACK_TENANT_PATTERN.fullmatch(cleaned):
        raise HTTPException(
            status_code=400,
            detail="X-Tenant-ID contains invalid characters",
        )
    return cleaned


try:
    from enhanced_agent_bus._compat.security.tenant_context import (
        get_tenant_id as _shared_get_tenant_id,
    )

    _USE_FALLBACK = False
except ImportError:
    _USE_FALLBACK = True
    _shared_get_tenant_id = None  # type: ignore[assignment]

get_tenant_id: Callable[..., Awaitable[str]]

if _USE_FALLBACK:
    warnings.warn(
        "Using fallback get_tenant_id - NOT SAFE FOR PRODUCTION. "
        "Install src.core.shared.security.tenant_context for proper validation.",
        RuntimeWarning,
        stacklevel=2,
    )

    async def _fallback_get_tenant_id(
        request: Request,
        x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
    ) -> str:
        if _get_environment() not in DEV_ENVIRONMENTS:
            raise HTTPException(
                status_code=503,
                detail="Security dependency not available in this environment",
            )
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id:
            return cast(str, tenant_id)
        if not x_tenant_id:
            raise HTTPException(
                status_code=400,
                detail="X-Tenant-ID header is required",
            )
        return _validate_fallback_tenant_id(x_tenant_id)

    get_tenant_id = _fallback_get_tenant_id
else:
    get_tenant_id = cast(Callable[..., Awaitable[str]], _shared_get_tenant_id)


__all__ = ["DEV_ENVIRONMENTS", "get_tenant_id"]
