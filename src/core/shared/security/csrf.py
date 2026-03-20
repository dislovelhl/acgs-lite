"""
ACGS-2 Shared Security - CSRF Protection Middleware
Constitutional Hash: cdd01ef066bc6cf2

Provides double-submit cookie CSRF protection for cookie-based sessions.
Automatically skips enforcement for Bearer-token (JWT API) requests.

Usage::

    from fastapi import FastAPI
    from src.core.shared.security.csrf import CSRFMiddleware, CSRFConfig

    app = FastAPI()
    app.add_middleware(CSRFMiddleware, config=CSRFConfig())
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sys
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.core.shared.config import settings
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_NON_PRODUCTION_ENVS = frozenset({"development", "dev", "test", "testing", "local", "ci"})


def _is_production_like_environment() -> bool:
    return settings.env not in _NON_PRODUCTION_ENVS


def _parse_bool_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"true", "1", "yes", "on"}


@dataclass(frozen=True)
class CSRFConfig:
    """CSRF middleware configuration.

    Attributes:
        enabled: Master switch for CSRF enforcement.
        cookie_name: Name of the CSRF double-submit cookie.
        header_name: Expected request header carrying the token.
        cookie_secure: Mark cookie as ``Secure`` (HTTPS only).
        cookie_samesite: ``SameSite`` cookie attribute.
        cookie_path: Cookie path.
        token_length: Byte-length of generated tokens (hex-encoded).
        secret: HMAC key for token signing.  Auto-generated when empty.
        exempt_paths: Path prefixes that skip CSRF checks.
        session_cookie_name: Optional session cookie name. When set, CSRF is
            only enforced for requests that actually carry that session cookie.
    """

    enabled: bool = True
    cookie_name: str = "csrf_token"
    header_name: str = "X-CSRF-Token"
    cookie_secure: bool = True
    cookie_samesite: str = "Lax"
    cookie_path: str = "/"
    token_length: int = 32
    secret: str = ""
    exempt_paths: tuple[str, ...] = field(
        default_factory=lambda: ("/health", "/readiness", "/metrics")
    )
    session_cookie_name: str | None = None

    def get_secret(self) -> str:
        """Return the HMAC secret, falling back to env var or random.

        SECURITY: The random fallback generates an ephemeral key that does
        not survive restarts — all existing CSRF tokens will be invalidated.
        Always set CSRF_SECRET in production.
        """
        if self.secret:
            return self.secret
        env_secret = os.getenv("CSRF_SECRET")
        if env_secret:
            if _is_production_like_environment():
                logger.info(
                    "CSRF_SECRET loaded from environment. Rotate this secret periodically "
                    "via the secret rotation system to limit exposure from key compromise."
                )
            return env_secret
        if _is_production_like_environment():
            raise OSError(
                "CSRF_SECRET environment variable is required in production-like environments. "
                f"Current environment: {settings.env!r}"
            )
        if not (
            _parse_bool_env(os.getenv("CSRF_ALLOW_EPHEMERAL_SECRET"))
            or os.getenv("PYTEST_CURRENT_TEST")
            or "pytest" in sys.modules
        ):
            raise OSError(
                "CSRF_SECRET is not configured. Set CSRF_ALLOW_EPHEMERAL_SECRET=true to allow "
                "ephemeral key usage in non-production runtime."
            )
        logger.warning(
            "CSRF_SECRET not configured — using ephemeral random key. "
            "CSRF tokens will not survive application restarts. "
            "Set CSRF_SECRET environment variable in production."
        )
        return secrets.token_hex(32)


def _generate_token(secret: str, length: int = 32) -> str:
    """Generate a signed CSRF token."""
    raw = secrets.token_hex(length)
    sig = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def _verify_token(token: str, secret: str) -> bool:
    """Verify a signed CSRF token."""
    parts = token.split(".", 1)
    if len(parts) != 2:
        return False
    raw, sig = parts
    expected = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF middleware.

    Skips enforcement for:
    - Safe HTTP methods (GET, HEAD, OPTIONS, TRACE).
    - Requests carrying a ``Bearer`` Authorization header (JWT API).
    - Paths in ``config.exempt_paths``.
    """

    def __init__(self, app: object, config: CSRFConfig | None = None) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.config = config or CSRFConfig()
        self._secret = self.config.get_secret()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Validate CSRF token on state-mutating requests; set cookie on safe requests."""
        if not self.config.enabled:
            return await call_next(request)

        # Skip safe methods
        if request.method in _SAFE_METHODS:
            response = await call_next(request)
            self._ensure_cookie(request, response)
            return response

        # Skip Bearer-token requests (JWT API)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return await call_next(request)

        # Skip exempt paths
        path = request.url.path
        for exempt in self.config.exempt_paths:
            if path.startswith(exempt):
                return await call_next(request)

        # Only enforce CSRF when the request is actually using a browser session.
        session_cookie_name = self.config.session_cookie_name
        if session_cookie_name and session_cookie_name not in request.cookies:
            return await call_next(request)

        # Validate double-submit
        cookie_token = request.cookies.get(self.config.cookie_name)
        header_token = request.headers.get(self.config.header_name)

        if not cookie_token or not header_token:
            logger.warning("CSRF token missing for %s %s", request.method, path)
            return JSONResponse({"detail": "CSRF token missing"}, status_code=403)

        if not _verify_token(cookie_token, self._secret):
            logger.warning("CSRF cookie token invalid for %s %s", request.method, path)
            return JSONResponse({"detail": "CSRF token invalid"}, status_code=403)

        if not hmac.compare_digest(cookie_token, header_token):
            logger.warning("CSRF token mismatch for %s %s", request.method, path)
            return JSONResponse({"detail": "CSRF token mismatch"}, status_code=403)

        response = await call_next(request)
        self._ensure_cookie(request, response)
        return response

    def _ensure_cookie(self, request: Request, response: Response) -> None:
        """Set the CSRF cookie if not already present."""
        if self.config.cookie_name not in request.cookies:
            token = _generate_token(self._secret, self.config.token_length)
            response.set_cookie(
                key=self.config.cookie_name,
                value=token,
                httponly=False,  # JS must read this cookie
                secure=self.config.cookie_secure,
                samesite=self.config.cookie_samesite,
                path=self.config.cookie_path,
            )
