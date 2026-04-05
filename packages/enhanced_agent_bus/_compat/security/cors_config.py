"""Shim for src.core.shared.security.cors_config."""
from __future__ import annotations

from typing import Any

try:
    from src.core.shared.security.cors_config import *  # noqa: F403
except ImportError:

    def get_cors_config() -> dict[str, Any]:
        """Return permissive CORS defaults for standalone / dev mode."""
        return {
            "allow_origins": ["*"],
            "allow_methods": ["*"],
            "allow_headers": ["*"],
            "allow_credentials": False,
        }

    def apply_cors(app: Any) -> None:
        """No-op CORS application stub."""
