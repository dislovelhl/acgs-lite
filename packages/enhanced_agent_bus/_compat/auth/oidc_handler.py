"""Shim for src.core.shared.auth.oidc_handler."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.auth.oidc_handler import *  # noqa: F403
    from src.core.shared.auth.oidc_handler import _normalize_secret_sentinel  # noqa: F401
except ImportError:
    import re

    def _normalize_secret_sentinel(secret: str) -> str:
        """Normalize a secret for comparison (strip, lowercase, remove non-alnum)."""
        return re.sub(r"[^a-z0-9]", "", secret.strip().lower())

    class OIDCConfig:
        issuer: str = ""
        client_id: str = ""
        client_secret: str = ""
        redirect_uri: str = ""
        scopes: list[str] = ["openid", "profile", "email"]

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    class OIDCHandler:
        """Stub OIDC handler that raises on real operations."""

        def __init__(self, config: OIDCConfig | None = None, **kwargs: Any) -> None:
            self.config = config or OIDCConfig()

        async def get_authorization_url(self, **kwargs: Any) -> str:
            raise NotImplementedError("OIDC not available in standalone mode")

        async def exchange_code(self, code: str, **kwargs: Any) -> dict[str, Any]:
            raise NotImplementedError("OIDC not available in standalone mode")

        async def validate_token(self, token: str, **kwargs: Any) -> dict[str, Any]:
            raise NotImplementedError("OIDC not available in standalone mode")

        async def refresh_token(self, refresh_token: str, **kwargs: Any) -> dict[str, Any]:
            raise NotImplementedError("OIDC not available in standalone mode")

    def get_oidc_handler(**kwargs: Any) -> OIDCHandler:
        return OIDCHandler(**kwargs)
