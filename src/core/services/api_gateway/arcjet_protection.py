"""Arcjet middleware integration for API Gateway.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)


class ArcjetReasonLike(Protocol):
    """Subset of Arcjet reason interface used by the gateway."""

    def is_rate_limit(self) -> bool:
        """Return True when denial reason is a rate limit."""

    def to_dict(self) -> dict[str, object] | None:
        """Serialize reason for structured API responses."""


class ArcjetDecisionLike(Protocol):
    """Subset of Arcjet decision interface used by the gateway."""

    reason: ArcjetReasonLike

    def is_denied(self) -> bool:
        """Return True when request should be denied."""


class ArcjetClientLike(Protocol):
    """Subset of Arcjet client interface used by middleware."""

    async def protect(self, request: Request) -> ArcjetDecisionLike:
        """Evaluate request against configured Arcjet rules."""


@dataclass(frozen=True)
class ArcjetMiddlewareConfig:
    """Runtime Arcjet middleware configuration."""

    client: ArcjetClientLike
    exempt_paths: tuple[str, ...]
    mode: str
    rate_limit_max: int
    rate_limit_window_seconds: int


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _is_exempt_path(path: str, exempt_paths: tuple[str, ...]) -> bool:
    return any(path == exempt or path.startswith(f"{exempt}/") for exempt in exempt_paths)


def create_arcjet_middleware_config() -> ArcjetMiddlewareConfig | None:
    """Create Arcjet middleware config from environment variables."""
    enabled = _parse_bool(os.getenv("ARCJET_ENABLED"), default=False)
    key = os.getenv("ARCJET_KEY")
    if not enabled:
        logger.info(
            "Arcjet protection disabled (ARCJET_ENABLED=false)",
            extra={"key_configured": bool(key)},
        )
        return None

    if not key:
        logger.warning("Arcjet protection disabled: ARCJET_KEY is not set")
        return None

    try:
        from arcjet import Mode, arcjet, fixed_window, shield
    except ImportError:
        logger.warning("Arcjet package not installed; skipping Arcjet protection middleware")
        return None

    mode_raw = os.getenv("ARCJET_MODE", "DRY_RUN").strip().upper()
    mode = Mode.LIVE if mode_raw == "LIVE" else Mode.DRY_RUN
    if mode_raw not in {"LIVE", "DRY_RUN"}:
        logger.warning(
            "Invalid ARCJET_MODE value; defaulting to DRY_RUN", extra={"value": mode_raw}
        )

    max_requests = _parse_int(os.getenv("ARCJET_RATE_LIMIT_MAX"), default=120)
    window_seconds = _parse_int(os.getenv("ARCJET_RATE_LIMIT_WINDOW_SECONDS"), default=60)

    client = arcjet(
        key=key,
        rules=[
            shield(mode=mode, characteristics=("ip.src",)),
            fixed_window(
                mode=mode,
                max=max_requests,
                window=window_seconds,
                characteristics=("ip.src",),
            ),
        ],
    )

    exempt_paths = (
        "/health",
        "/health/live",
        "/health/ready",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/favicon.ico",
    )

    logger.info(
        "Arcjet protection middleware configured",
        extra={
            "mode": mode.value,
            "rate_limit_max": max_requests,
            "rate_limit_window_seconds": window_seconds,
            "exempt_path_count": len(exempt_paths),
        },
    )
    return ArcjetMiddlewareConfig(
        client=client,
        exempt_paths=exempt_paths,
        mode=mode.value,
        rate_limit_max=max_requests,
        rate_limit_window_seconds=window_seconds,
    )


class ArcjetProtectionMiddleware(BaseHTTPMiddleware):
    """Evaluate incoming requests with Arcjet before route handling."""

    def __init__(
        self,
        app: FastAPI,
        client: ArcjetClientLike,
        exempt_paths: tuple[str, ...],
    ) -> None:
        super().__init__(app)
        self._client = client
        self._exempt_paths = exempt_paths

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        path = request.url.path
        if request.method == "OPTIONS" or _is_exempt_path(path, self._exempt_paths):
            return await call_next(request)

        try:
            decision = await self._client.protect(request)
        except Exception as exc:
            logger.error(
                "Arcjet protection check failed; allowing request (fail-open)",
                extra={"error_type": type(exc).__name__, "path": path},
                exc_info=True,
            )
            return await call_next(request)

        if decision.is_denied():
            reason = decision.reason.to_dict() if decision.reason else None
            status = 429 if decision.reason and decision.reason.is_rate_limit() else 403
            return JSONResponse(
                status_code=status,
                content={
                    "detail": "Request denied by Arcjet policy",
                    "reason": reason,
                },
            )

        return await call_next(request)


def get_arcjet_runtime_status(*, middleware_enabled: bool) -> dict[str, object]:
    """Return sanitized Arcjet runtime status for operational visibility."""
    enabled = _parse_bool(os.getenv("ARCJET_ENABLED"), default=False)
    key_configured = bool(os.getenv("ARCJET_KEY"))
    mode_raw = os.getenv("ARCJET_MODE", "DRY_RUN").strip().upper()
    mode = mode_raw if mode_raw in {"LIVE", "DRY_RUN"} else "DRY_RUN"

    return {
        "enabled": enabled,
        "key_configured": key_configured,
        "middleware_enabled": middleware_enabled,
        "mode": mode,
        "rate_limit_max": _parse_int(os.getenv("ARCJET_RATE_LIMIT_MAX"), default=120),
        "rate_limit_window_seconds": _parse_int(
            os.getenv("ARCJET_RATE_LIMIT_WINDOW_SECONDS"), default=60
        ),
    }


def configure_arcjet_protection(app: FastAPI) -> bool:
    """Add Arcjet middleware when enabled/configured."""
    if config := create_arcjet_middleware_config():
        app.add_middleware(
            ArcjetProtectionMiddleware,
            client=config.client,
            exempt_paths=config.exempt_paths,
        )
        return True
    return False
