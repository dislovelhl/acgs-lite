"""
ACGS-2 Enhanced Agent Bus API Package
Constitutional Hash: cdd01ef066bc6cf2

This package provides the FastAPI-based API for the Enhanced Agent Bus.
All exports are maintained for backward compatibility with the original api.py module.

Usage:
    from enhanced_agent_bus.api import app, create_app
    # or for backward compatibility:
    from enhanced_agent_bus.api import (
        RATE_LIMIT_REQUESTS_PER_MINUTE,
        check_batch_rate_limit,
        validate_item_sizes,
        MESSAGE_HANDLERS,
        ...
    )
"""

from __future__ import annotations

# App and factory
from .app import (
    CIRCUIT_BREAKER_AVAILABLE,
    agent_bus,
    app,
    batch_processor,
    create_app,
    message_circuit_breaker,
)

# Configuration constants
from .config import (
    API_RATE_LIMIT_PER_MINUTE,
    API_VERSION,
    BATCH_PROCESSOR_ITEM_TIMEOUT_SECONDS,
    BATCH_PROCESSOR_MAX_CONCURRENCY,
    BATCH_PROCESSOR_SLOW_ITEM_THRESHOLD_SECONDS,
    BATCH_RATE_LIMIT_BASE,
    BYTES_PER_MB,
    CACHE_WARMING_RATE_LIMIT,
    CIRCUIT_BREAKER_FAIL_MAX,
    CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS,
    DEFAULT_API_PORT,
    DEFAULT_BATCH_RATE_LIMIT_BASE,
    DEFAULT_MAX_ITEM_CONTENT_SIZE_BYTES,
    DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE,
    DEFAULT_WORKERS,
    MAX_ITEM_CONTENT_SIZE,
    MAX_VIOLATIONS_TO_DISPLAY,
    MS_PER_SECOND,
    RATE_LIMIT_COST_DIVISOR,
    RATE_LIMIT_REQUESTS_PER_MINUTE,
    RATE_LIMIT_WINDOW_CLEANUP_MINUTES,
    RATE_LIMIT_WINDOW_DURATION_MINUTES,
)

# Middleware
from .middleware import (
    API_VERSIONING_AVAILABLE,
    SECURITY_HEADERS_AVAILABLE,
    correlation_id_middleware,
    logger,
    setup_all_middleware,
    setup_api_versioning_middleware,
    setup_correlation_id_middleware,
    setup_cors_middleware,
    setup_security_headers_middleware,
    setup_tenant_context_middleware,
)

# Rate limiting
from .rate_limiting import (
    RATE_LIMITING_AVAILABLE,
    RateLimitExceeded,
    check_batch_rate_limit,
    get_remote_address,
    limiter,
    validate_item_sizes,
)

# Routes
from .routes._tenant_auth import get_tenant_id
from .routes.health import get_latency_tracker
from .routes.messages import MESSAGE_HANDLERS

_APP_EXPORTS: tuple[str, ...] = (
    "app",
    "create_app",
    "agent_bus",
    "batch_processor",
    "message_circuit_breaker",
    "CIRCUIT_BREAKER_AVAILABLE",
)

_CONFIG_EXPORTS: tuple[str, ...] = (
    "RATE_LIMIT_REQUESTS_PER_MINUTE",
    "BATCH_RATE_LIMIT_BASE",
    "MAX_ITEM_CONTENT_SIZE",
    "DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE",
    "DEFAULT_BATCH_RATE_LIMIT_BASE",
    "DEFAULT_MAX_ITEM_CONTENT_SIZE_BYTES",
    "RATE_LIMIT_COST_DIVISOR",
    "RATE_LIMIT_WINDOW_CLEANUP_MINUTES",
    "RATE_LIMIT_WINDOW_DURATION_MINUTES",
    "BYTES_PER_MB",
    "MAX_VIOLATIONS_TO_DISPLAY",
    "CIRCUIT_BREAKER_FAIL_MAX",
    "CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS",
    "API_RATE_LIMIT_PER_MINUTE",
    "BATCH_PROCESSOR_MAX_CONCURRENCY",
    "BATCH_PROCESSOR_ITEM_TIMEOUT_SECONDS",
    "BATCH_PROCESSOR_SLOW_ITEM_THRESHOLD_SECONDS",
    "CACHE_WARMING_RATE_LIMIT",
    "API_VERSION",
    "DEFAULT_API_PORT",
    "DEFAULT_WORKERS",
    "MS_PER_SECOND",
)

_RATE_LIMITING_EXPORTS: tuple[str, ...] = (
    "RATE_LIMITING_AVAILABLE",
    "RateLimitExceeded",
    "get_remote_address",
    "check_batch_rate_limit",
    "validate_item_sizes",
    "limiter",
)

_MIDDLEWARE_EXPORTS: tuple[str, ...] = (
    "SECURITY_HEADERS_AVAILABLE",
    "API_VERSIONING_AVAILABLE",
    "setup_cors_middleware",
    "setup_tenant_context_middleware",
    "setup_security_headers_middleware",
    "setup_api_versioning_middleware",
    "setup_correlation_id_middleware",
    "setup_all_middleware",
    "correlation_id_middleware",
    "logger",
)

_ROUTE_EXPORTS: tuple[str, ...] = (
    "MESSAGE_HANDLERS",
    "get_tenant_id",
    "get_latency_tracker",
)

__all__ = [
    *_APP_EXPORTS,
    *_CONFIG_EXPORTS,
    *_RATE_LIMITING_EXPORTS,
    *_MIDDLEWARE_EXPORTS,
    *_ROUTE_EXPORTS,
]
