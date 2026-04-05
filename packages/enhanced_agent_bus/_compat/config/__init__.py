"""Shim for src.core.shared.config."""
from __future__ import annotations

from typing import Any

try:
    from src.core.shared.config import *  # noqa: F403
except ImportError:

    class Settings:
        """Minimal settings object for standalone mode."""

        debug: bool = False
        environment: str = "development"
        service_name: str = "enhanced-agent-bus"
        log_level: str = "INFO"
        constitutional_hash: str = "608508a9bd224290"

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

        def get(self, key: str, default: Any = None) -> Any:
            return getattr(self, key, default)

    _settings: Settings | None = None

    def get_settings() -> Settings:
        global _settings  # noqa: PLW0603
        if _settings is None:
            _settings = Settings()
        return _settings
