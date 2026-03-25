"""Minimal API versioning stubs for gateway import compatibility.

This module intentionally provides only lightweight defaults so services and tests can
import API versioning symbols without pulling in the historical implementation.
It is not a full versioning system.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.core.shared.constants import CONSTITUTIONAL_HASH

SUPPORTED_VERSIONS: tuple[str, ...] = ("v1",)
DEPRECATED_VERSIONS: tuple[str, ...] = ()
DEPRECATED_ROUTES: frozenset[str] = frozenset()


@dataclass(slots=True)
class VersioningConfig:
    """Minimal configuration container for stub middleware."""

    default_version: str = "v1"
    supported_versions: tuple[str, ...] = SUPPORTED_VERSIONS
    deprecated_versions: tuple[str, ...] = DEPRECATED_VERSIONS
    exempt_paths: set[str] = field(default_factory=set)
    enable_metrics: bool = False
    strict_versioning: bool = False
    log_version_usage: bool = False


class APIVersioningMiddleware(BaseHTTPMiddleware):
    """Pass-through middleware that annotates responses with version headers."""

    def __init__(self, app: object, config: VersioningConfig | None = None) -> None:
        super().__init__(app)
        self.config = config or VersioningConfig()

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        requested_version = (
            _extract_version_from_path(request.url.path) or self.config.default_version
        )
        response.headers.setdefault("X-API-Version", requested_version)
        response.headers.setdefault("X-Constitutional-Hash", CONSTITUTIONAL_HASH)
        if requested_version in self.config.deprecated_versions:
            response.headers.setdefault("X-API-Deprecated", "true")
        return response


class DeprecationNoticeMiddleware(BaseHTTPMiddleware):
    """Pass-through middleware that adds a basic deprecation header when needed."""

    def __init__(
        self, app: object, deprecated_routes: frozenset[str] | set[str] | None = None
    ) -> None:
        super().__init__(app)
        self.deprecated_routes = set(deprecated_routes or ())

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        if request.url.path in self.deprecated_routes:
            response.headers.setdefault("X-API-Deprecated", "true")
        return response


def create_versioned_router(
    *,
    prefix: str,
    version: str = "v1",
    **kwargs: object,
) -> APIRouter:
    """Create an APIRouter mounted under /api/<version>."""

    normalized_prefix = prefix if prefix.startswith("/") else f"/{prefix}"
    return APIRouter(prefix=f"/api/{version}{normalized_prefix}", **kwargs)


def create_version_info_endpoint(router: APIRouter) -> APIRouter:
    """Attach a lightweight version info endpoint to a router."""

    @router.get("/version", include_in_schema=False)
    async def version_info() -> dict[str, object]:
        return {
            "default_version": SUPPORTED_VERSIONS[0],
            "supported_versions": list(SUPPORTED_VERSIONS),
            "deprecated_versions": list(DEPRECATED_VERSIONS),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    return router


def create_version_metrics_endpoint(router: APIRouter) -> APIRouter:
    """Attach a lightweight version metrics endpoint to a router."""

    @router.get("/version/metrics", include_in_schema=False)
    async def version_metrics() -> dict[str, object]:
        return {
            "enabled": False,
            "supported_versions": list(SUPPORTED_VERSIONS),
            "counts": {},
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    return router


def get_versioning_documentation() -> dict[str, object]:
    """Return minimal static versioning documentation."""

    return {
        "strategy": "stub",
        "default_version": SUPPORTED_VERSIONS[0],
        "supported_versions": list(SUPPORTED_VERSIONS),
        "deprecated_versions": list(DEPRECATED_VERSIONS),
        "notes": [
            "This is a minimal compatibility layer for tests.",
            "No production-grade version negotiation is implemented.",
        ],
        "constitutional_hash": CONSTITUTIONAL_HASH,
    }


def _extract_version_from_path(path: str) -> str | None:
    """Return /api/<version>/ path segment when present."""

    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "api":
        return parts[1]
    return None


__all__ = [
    "DEPRECATED_ROUTES",
    "DEPRECATED_VERSIONS",
    "SUPPORTED_VERSIONS",
    "APIVersioningMiddleware",
    "DeprecationNoticeMiddleware",
    "VersioningConfig",
    "create_version_info_endpoint",
    "create_version_metrics_endpoint",
    "create_versioned_router",
    "get_versioning_documentation",
]
