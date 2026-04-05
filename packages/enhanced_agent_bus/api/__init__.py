"""
ACGS-2 Enhanced Agent Bus API Package
Constitutional Hash: 608508a9bd224290

This package exposes the FastAPI API surface for the Enhanced Agent Bus.
Exports are resolved lazily so test collection can import the package without
eagerly importing the entire application module tree.
"""

from __future__ import annotations

from importlib import import_module

_EXPORT_TO_MODULE = {
    "app": ".app",
    "create_app": ".app",
    "agent_bus": ".app",
    "batch_processor": ".app",
    "message_circuit_breaker": ".app",
    "CIRCUIT_BREAKER_AVAILABLE": ".app",
    "API_RATE_LIMIT_PER_MINUTE": ".config",
    "API_VERSION": ".config",
    "BATCH_PROCESSOR_ITEM_TIMEOUT_SECONDS": ".config",
    "BATCH_PROCESSOR_MAX_CONCURRENCY": ".config",
    "BATCH_PROCESSOR_SLOW_ITEM_THRESHOLD_SECONDS": ".config",
    "BATCH_RATE_LIMIT_BASE": ".config",
    "BYTES_PER_MB": ".config",
    "CACHE_WARMING_RATE_LIMIT": ".config",
    "CIRCUIT_BREAKER_FAIL_MAX": ".config",
    "CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS": ".config",
    "DEFAULT_API_PORT": ".config",
    "DEFAULT_BATCH_RATE_LIMIT_BASE": ".config",
    "DEFAULT_MAX_ITEM_CONTENT_SIZE_BYTES": ".config",
    "DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE": ".config",
    "DEFAULT_WORKERS": ".config",
    "MAX_ITEM_CONTENT_SIZE": ".config",
    "MAX_VIOLATIONS_TO_DISPLAY": ".config",
    "MS_PER_SECOND": ".config",
    "RATE_LIMIT_COST_DIVISOR": ".config",
    "RATE_LIMIT_REQUESTS_PER_MINUTE": ".config",
    "RATE_LIMIT_WINDOW_CLEANUP_MINUTES": ".config",
    "RATE_LIMIT_WINDOW_DURATION_MINUTES": ".config",
    "API_VERSIONING_AVAILABLE": ".middleware",
    "SECURITY_HEADERS_AVAILABLE": ".middleware",
    "correlation_id_middleware": ".middleware",
    "logger": ".middleware",
    "setup_all_middleware": ".middleware",
    "setup_api_versioning_middleware": ".middleware",
    "setup_correlation_id_middleware": ".middleware",
    "setup_cors_middleware": ".middleware",
    "setup_security_headers_middleware": ".middleware",
    "setup_tenant_context_middleware": ".middleware",
    "RATE_LIMITING_AVAILABLE": ".rate_limiting",
    "RateLimitExceeded": ".rate_limiting",
    "check_batch_rate_limit": ".rate_limiting",
    "get_remote_address": ".rate_limiting",
    "limiter": ".rate_limiting",
    "validate_item_sizes": ".rate_limiting",
    "get_tenant_id": ".routes._tenant_auth",
    "get_latency_tracker": ".routes.health",
    "MESSAGE_HANDLERS": ".routes.messages",
}

__all__ = sorted(_EXPORT_TO_MODULE)


def __getattr__(name: str) -> object:
    """Resolve public exports on demand."""
    module_name = _EXPORT_TO_MODULE.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    return getattr(module, name)
