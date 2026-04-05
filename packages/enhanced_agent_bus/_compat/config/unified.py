"""Shim for src.core.shared.config.unified."""
from __future__ import annotations

from typing import Any

try:
    from src.core.shared.config.unified import *  # noqa: F403
except ImportError:

    class UnifiedSettings:
        """Minimal unified settings for standalone mode."""

        debug: bool = False
        environment: str = "development"
        service_name: str = "enhanced-agent-bus"

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

        def get(self, key: str, default: Any = None) -> Any:
            return getattr(self, key, default)

    _settings: UnifiedSettings | None = None

    def get_settings() -> UnifiedSettings:
        global _settings  # noqa: PLW0603
        if _settings is None:
            _settings = UnifiedSettings()
        return _settings
