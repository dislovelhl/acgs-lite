"""
ACGS-2 Enhanced Agent Bus Middleware
Constitutional Hash: 608508a9bd224290

This module provides middleware configuration for the API,
including CORS, security headers, tenant context, and API versioning.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from enhanced_agent_bus.observability.structured_logging import get_logger

# Initialize logging
try:
    from src.core.shared.acgs_logging import (
        create_correlation_middleware,
        init_service_logging,
    )

    logger = init_service_logging("enhanced-agent-bus", level="INFO", json_format=True)
except ImportError:
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO)
    logger = get_logger(__name__)  # type: ignore[assignment]
    create_correlation_middleware = None  # type: ignore[assignment]

# Security imports
try:
    from src.core.shared.security.cors_config import get_cors_config
    from src.core.shared.security.security_headers import (
        SecurityHeadersConfig,
        SecurityHeadersMiddleware,
    )
    from src.core.shared.security.tenant_context import (
        TenantContextConfig,
        TenantContextMiddleware,
    )

    SECURITY_HEADERS_AVAILABLE = True
except ImportError:
    SECURITY_HEADERS_AVAILABLE = False
    from ..fallback_stubs import (  # type: ignore[assignment]
        SecurityHeadersConfig,
        SecurityHeadersMiddleware,
        TenantContextConfig,
        TenantContextMiddleware,
        get_cors_config,
    )

# API Versioning Middleware
API_VERSIONING_AVAILABLE = False
try:
    from src.core.shared.api_versioning import (
        APIVersioningMiddleware,
        VersioningConfig,
        get_api_version,
    )

    API_VERSIONING_AVAILABLE = True
except ImportError:
    APIVersioningMiddleware = None  # type: ignore[misc, assignment]
    VersioningConfig = None  # type: ignore[misc, assignment]
    get_api_version = None  # type: ignore[misc, assignment]

# Correlation ID middleware from api_exceptions
from ..api_exceptions import (
    correlation_id_middleware,
)


def setup_cors_middleware(app: FastAPI) -> None:
    """Configure CORS middleware for the application."""
    app.add_middleware(CORSMiddleware, **get_cors_config())


def setup_tenant_context_middleware(app: FastAPI) -> None:
    """Configure tenant context middleware for the application."""
    tenant_config = TenantContextConfig.from_env()
    if os.environ.get("ENVIRONMENT") == "development":
        tenant_config.required = False
    app.add_middleware(TenantContextMiddleware, config=tenant_config)
    logger.info(
        "Tenant context middleware enabled",
        extra={
            "required": tenant_config.required,
            "exempt_paths": tenant_config.exempt_paths,
        },
    )


def setup_security_headers_middleware(app: FastAPI) -> None:
    """Configure security headers middleware for the application."""
    if not SECURITY_HEADERS_AVAILABLE:
        logger.warning("Security headers middleware not available - missing import")
        return

    environment = os.environ.get("ENVIRONMENT", "production").lower()
    security_config = (
        SecurityHeadersConfig.for_development()
        if environment == "development"
        else SecurityHeadersConfig.for_production()
    )
    app.add_middleware(SecurityHeadersMiddleware, config=security_config)
    logger.info(
        "Security headers middleware enabled",
        extra={"environment": environment},
    )


def setup_api_versioning_middleware(app: FastAPI) -> None:
    """Configure API versioning middleware for the application."""
    if not API_VERSIONING_AVAILABLE or APIVersioningMiddleware is None:
        logger.warning("API versioning middleware not available - missing import")
        return

    versioning_config = VersioningConfig(
        default_version="v1",
        supported_versions={"v1", "v2"},
        deprecated_versions=set(),
        exempt_paths={
            "/health",
            "/health/live",
            "/health/ready",
            "/ready",
            "/live",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
        },
        enable_metrics=True,
        strict_versioning=False,
        log_version_usage=True,
    )
    app.add_middleware(APIVersioningMiddleware, config=versioning_config)
    logger.info(
        "API versioning middleware enabled",
        extra={
            "default_version": versioning_config.default_version,
            "supported_versions": list(versioning_config.supported_versions),
        },
    )


def setup_correlation_id_middleware(app: FastAPI) -> None:
    """Configure correlation ID middleware for the application."""
    if create_correlation_middleware is None:
        return
    if correlation_mw := create_correlation_middleware():
        app.middleware("http")(correlation_mw)


def setup_all_middleware(app: FastAPI) -> None:
    """Configure all middleware for the application."""
    setup_correlation_id_middleware(app)
    setup_cors_middleware(app)
    setup_tenant_context_middleware(app)
    setup_security_headers_middleware(app)
    setup_api_versioning_middleware(app)


__all__ = [
    "API_VERSIONING_AVAILABLE",
    "SECURITY_HEADERS_AVAILABLE",
    "correlation_id_middleware",
    "logger",
    "setup_all_middleware",
    "setup_api_versioning_middleware",
    "setup_correlation_id_middleware",
    "setup_cors_middleware",
    "setup_security_headers_middleware",
    "setup_tenant_context_middleware",
]
