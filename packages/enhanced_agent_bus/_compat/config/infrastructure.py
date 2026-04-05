"""Shim for src.core.shared.config.infrastructure."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.config.infrastructure import *  # noqa: F403
except ImportError:

    class RedisSettings:
        url: str = "redis://localhost:6379"
        db: int = 0
        max_connections: int = 10
        socket_timeout: float = 5.0

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    class DatabaseSettings:
        url: str = "sqlite:///acgs.db"
        echo: bool = False
        pool_size: int = 5
        max_overflow: int = 10

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    class KafkaSettings:
        bootstrap_servers: str = "localhost:9092"
        group_id: str = "enhanced-agent-bus"
        auto_offset_reset: str = "latest"

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
