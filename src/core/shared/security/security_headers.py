"""
ACGS-2 Security Headers Middleware
Constitutional Hash: 608508a9bd224290

Security headers middleware for FastAPI applications providing defense-in-depth
against common web attacks including XSS, clickjacking, MIME sniffing, and downgrade attacks.

Implements enterprise-grade security headers:
- Content-Security-Policy: Controls resource loading to prevent XSS
- X-Content-Type-Options: Prevents MIME sniffing attacks
- X-Frame-Options: Prevents clickjacking attacks
- Strict-Transport-Security: Enforces HTTPS connections
- X-XSS-Protection: Enables browser XSS filtering
- Referrer-Policy: Controls referrer information leakage

Environment Support:
- Development: Relaxed CSP, shorter HSTS max-age
- Staging: Moderate security, testing-friendly
- Production: Strict security headers, long HSTS max-age

Usage:
    from src.core.shared.security.security_headers import SecurityHeadersMiddleware, SecurityHeadersConfig

    # Basic usage with defaults
    app.add_middleware(SecurityHeadersMiddleware)

    # Custom configuration for production
    config = SecurityHeadersConfig(
        environment="production",
        custom_csp_directives={"connect-src": ["'self'", "wss://example.com"]}
    )
    app.add_middleware(SecurityHeadersMiddleware, config=config)

    # WebSocket-enabled configuration
    config = SecurityHeadersConfig.for_websocket_service()
    app.add_middleware(SecurityHeadersMiddleware, config=config)
"""

import os
from dataclasses import dataclass

from starlette.datastructures import MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.shared.config import settings
from src.core.shared.config.runtime_environment import resolve_runtime_environment
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

# Constitutional hash for governance compliance

logger = get_logger(__name__)


def _detect_environment() -> str:
    configured_env = getattr(settings, "env", None)
    if configured_env and configured_env not in ("development",):
        return configured_env
    return resolve_runtime_environment(configured_env)


@dataclass
class SecurityHeadersConfig:
    """
    Configuration for security headers middleware.

    Attributes:
        environment: Deployment environment (development, staging, production)
        enable_hsts: Enable Strict-Transport-Security header
        hsts_max_age: HSTS max-age in seconds
        hsts_include_subdomains: Include subdomains in HSTS
        hsts_preload: Enable HSTS preload
        custom_csp_directives: Custom Content-Security-Policy directives
        frame_options: X-Frame-Options value (DENY, SAMEORIGIN)
        referrer_policy: Referrer-Policy value
        enable_xss_protection: Enable X-XSS-Protection header
    """

    environment: str = "production"
    enable_hsts: bool = True
    hsts_max_age: int = 31536000  # 1 year in seconds
    hsts_include_subdomains: bool = True
    hsts_preload: bool = False
    custom_csp_directives: dict[str, list[str]] | None = None
    frame_options: str = "DENY"
    referrer_policy: str = "strict-origin-when-cross-origin"
    enable_xss_protection: bool = True

    @classmethod
    def from_env(cls) -> "SecurityHeadersConfig":
        """
        Create configuration from environment variables.

        Environment Variables:
            APP_ENV: Application environment (development, staging, production)
            SECURITY_HSTS_ENABLED: Enable HSTS (default: true for production)
            SECURITY_HSTS_MAX_AGE: HSTS max-age in seconds
            SECURITY_FRAME_OPTIONS: X-Frame-Options value

        Returns:
            SecurityHeadersConfig instance
        """
        environment = _detect_environment()

        # Environment-specific defaults
        if environment == "development":
            hsts_enabled = os.getenv("SECURITY_HSTS_ENABLED", "false").lower() == "true"
            hsts_max_age = int(os.getenv("SECURITY_HSTS_MAX_AGE", "300"))  # 5 minutes
        elif environment == "staging":
            hsts_enabled = os.getenv("SECURITY_HSTS_ENABLED", "true").lower() == "true"
            hsts_max_age = int(os.getenv("SECURITY_HSTS_MAX_AGE", "86400"))  # 1 day
        else:  # production
            hsts_enabled = os.getenv("SECURITY_HSTS_ENABLED", "true").lower() == "true"
            hsts_max_age = int(os.getenv("SECURITY_HSTS_MAX_AGE", "31536000"))  # 1 year

        frame_options = os.getenv("SECURITY_FRAME_OPTIONS", "DENY")

        return cls(
            environment=environment,
            enable_hsts=hsts_enabled,
            hsts_max_age=hsts_max_age,
            frame_options=frame_options,
        )

    @classmethod
    def for_development(cls) -> "SecurityHeadersConfig":
        """
        Create development-friendly configuration.

        Features:
        - Relaxed CSP allowing localhost and eval (for dev tools)
        - Short HSTS max-age (5 minutes)
        - HSTS disabled by default

        Returns:
            SecurityHeadersConfig for development
        """
        return cls(
            environment="development",
            enable_hsts=False,
            hsts_max_age=300,  # 5 minutes
            hsts_include_subdomains=False,
            custom_csp_directives={
                "default-src": ["'self'"],
                "script-src": ["'self'", "'unsafe-inline'", "'unsafe-eval'", "localhost:*"],
                "connect-src": ["'self'", "localhost:*", "ws://localhost:*"],
            },
        )

    @classmethod
    def for_production(cls, strict: bool = True) -> "SecurityHeadersConfig":
        """
        Create production-grade configuration.

        Args:
            strict: Use strict CSP settings

        Features:
        - Strict CSP with minimal allowed sources
        - Long HSTS max-age (1 year)
        - HSTS with subdomains and preload
        - Frame options DENY

        Returns:
            SecurityHeadersConfig for production
        """
        csp_directives = None
        if strict:
            csp_directives = {
                "default-src": ["'self'"],
                "script-src": ["'self'"],
                "style-src": ["'self'"],
                "img-src": ["'self'", "data:"],
                "font-src": ["'self'"],
                "connect-src": ["'self'"],
                "frame-ancestors": ["'none'"],
            }

        return cls(
            environment="production",
            enable_hsts=True,
            hsts_max_age=31536000,  # 1 year
            hsts_include_subdomains=True,
            hsts_preload=True,
            custom_csp_directives=csp_directives,
            frame_options="DENY",
        )

    @classmethod
    def for_websocket_service(cls) -> "SecurityHeadersConfig":
        """
        Create configuration for services using WebSockets.

        Features:
        - CSP allows WebSocket connections (ws:// and wss://)
        - Production-grade HSTS
        - Suitable for real-time dashboards and observability tools

        Returns:
            SecurityHeadersConfig for WebSocket services
        """
        return cls(
            environment="production",
            enable_hsts=True,
            hsts_max_age=31536000,
            custom_csp_directives={
                "default-src": ["'self'"],
                "script-src": ["'self'"],
                "style-src": ["'self'", "'unsafe-inline'"],  # Allow inline styles for UI
                "connect-src": ["'self'", "ws:", "wss:"],  # Allow WebSocket connections
                "img-src": ["'self'", "data:"],
            },
        )

    @classmethod
    def for_integration_service(cls) -> "SecurityHeadersConfig":
        """
        Create configuration for integration services.

        Features:
        - CSP allows external API connections
        - Suitable for webhook handlers and third-party integrations
        - Production-grade security with integration flexibility

        Returns:
            SecurityHeadersConfig for integration services
        """
        return cls(
            environment="production",
            enable_hsts=True,
            hsts_max_age=31536000,
            custom_csp_directives={
                "default-src": ["'self'"],
                "script-src": ["'self'"],
                "connect-src": ["'self'", "https:"],  # Allow HTTPS external connections
                "img-src": ["'self'", "data:", "https:"],
            },
        )

    def get_csp_header_value(self) -> str:
        """
        Build Content-Security-Policy header value.

        Returns:
            CSP header value string
        """
        # Default CSP directives
        default_directives = {
            "default-src": ["'self'"],
            "script-src": ["'self'"],
            "style-src": ["'self'"],
            "img-src": ["'self'", "data:"],
            "font-src": ["'self'"],
            "connect-src": ["'self'"],
            "frame-ancestors": ["'none'"],
            "base-uri": ["'self'"],
            "form-action": ["'self'"],
        }

        # Merge custom directives
        directives = default_directives.copy()
        if self.custom_csp_directives:
            directives.update(self.custom_csp_directives)

        # Build CSP string
        csp_parts = []
        for directive, sources in directives.items():
            sources_str = " ".join(sources)
            csp_parts.append(f"{directive} {sources_str}")

        return "; ".join(csp_parts)

    def get_hsts_header_value(self) -> str | None:
        """
        Build Strict-Transport-Security header value.

        Returns:
            HSTS header value string or None if disabled
        """
        if not self.enable_hsts:
            return None

        hsts_parts = [f"max-age={self.hsts_max_age}"]

        if self.hsts_include_subdomains:
            hsts_parts.append("includeSubDomains")

        if self.hsts_preload:
            hsts_parts.append("preload")

        return "; ".join(hsts_parts)


class SecurityHeadersMiddleware:
    """
    Pure ASGI middleware for adding security headers to all HTTP responses.

    ~50-80% faster than the previous BaseHTTPMiddleware implementation by
    avoiding per-request Request object cloning and coroutine boundary overhead.

    Implements:
    - Content-Security-Policy: Controls resource loading
    - X-Content-Type-Options: Prevents MIME sniffing
    - X-Frame-Options: Prevents clickjacking
    - Strict-Transport-Security: Enforces HTTPS
    - X-XSS-Protection: Enables XSS filtering
    - Referrer-Policy: Controls referrer information

    Usage:
        app.add_middleware(SecurityHeadersMiddleware)

        # With custom config
        config = SecurityHeadersConfig.for_production()
        app.add_middleware(SecurityHeadersMiddleware, config=config)
    """

    def __init__(self, app: ASGIApp, config: SecurityHeadersConfig | None = None):
        """
        Initialize security headers middleware.

        Args:
            app: FastAPI application instance
            config: SecurityHeadersConfig instance (default: from environment)
        """
        self.app = app
        self.config = config or SecurityHeadersConfig.from_env()

        logger.info(
            "Security headers middleware initialized for environment: %s (constitutional_hash=%s)",
            self.config.environment,
            CONSTITUTIONAL_HASH,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process ASGI request and inject security headers into response."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                self._set_security_headers(headers)
            await send(message)

        await self.app(scope, receive, send_with_security_headers)

    def _set_security_headers(self, headers: MutableHeaders) -> None:
        """
        Set all security headers on a MutableHeaders-compatible object.

        Args:
            headers: MutableHeaders (or Response.headers) to modify
        """
        # Content-Security-Policy
        headers["Content-Security-Policy"] = self.config.get_csp_header_value()

        # X-Content-Type-Options
        headers["X-Content-Type-Options"] = "nosniff"

        # X-Frame-Options
        headers["X-Frame-Options"] = self.config.frame_options

        # Strict-Transport-Security (if enabled)
        hsts_value = self.config.get_hsts_header_value()
        if hsts_value:
            headers["Strict-Transport-Security"] = hsts_value

        # X-XSS-Protection
        if self.config.enable_xss_protection:
            headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer-Policy
        headers["Referrer-Policy"] = self.config.referrer_policy

        # Permissions-Policy — restrict unnecessary browser features for API surfaces
        headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"

    def _add_security_headers(self, response: Response) -> None:
        """
        Add all security headers to a Response object.

        Backward-compatible helper used by direct callers.

        Args:
            response: HTTP response to modify
        """
        self._set_security_headers(response.headers)


def add_security_headers(
    app: ASGIApp,
    environment: str | None = None,
    config: SecurityHeadersConfig | None = None,
) -> None:
    """
    Convenience function to add security headers middleware to a FastAPI app.

    Args:
        app: FastAPI application instance
        environment: Environment name (development, staging, production)
        config: Custom SecurityHeadersConfig (overrides environment)

    Example:
        from src.core.shared.security.security_headers import add_security_headers

        app = FastAPI()
        add_security_headers(app, environment="production")
    """
    if config is None:
        if environment == "development":
            config = SecurityHeadersConfig.for_development()
        elif environment == "production":
            config = SecurityHeadersConfig.for_production()
        else:
            config = SecurityHeadersConfig.from_env()

    app.add_middleware(SecurityHeadersMiddleware, config=config)

    logger.info(
        "Added security headers middleware with environment: %s (constitutional_hash=%s)",
        config.environment,
        CONSTITUTIONAL_HASH,
    )
