"""
ACGS-2 Shared Configuration - Redis HA
Constitutional Hash: cdd01ef066bc6cf2

Pydantic model supporting standalone, Sentinel, and cluster Redis topologies.
No deployment changes — config-only; enables HA when Redis Sentinel or
Cluster is available.
"""

from __future__ import annotations

import os
from enum import StrEnum

from pydantic import BaseModel, field_validator

from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)


class RedisTopology(StrEnum):
    """Supported Redis deployment topologies."""

    STANDALONE = "standalone"
    SENTINEL = "sentinel"
    CLUSTER = "cluster"


class RedisConfig(BaseModel):
    """Redis connection configuration with HA support.

    Examples::

        # Standalone (default)
        cfg = RedisConfig()

        # Sentinel
        cfg = RedisConfig(
            topology=RedisTopology.SENTINEL,
            sentinel_master="mymaster",
            sentinel_nodes=["sentinel-0:26379", "sentinel-1:26379"],
        )

        # Cluster
        cfg = RedisConfig(
            topology=RedisTopology.CLUSTER,
            cluster_nodes=["redis-0:6379", "redis-1:6379", "redis-2:6379"],
        )

        # From environment
        cfg = RedisConfig.from_env()
    """

    # Topology
    topology: RedisTopology = RedisTopology.STANDALONE

    # Standalone settings
    url: str = "redis://localhost:6379"
    db: int = 0

    # Sentinel settings
    sentinel_master: str | None = None
    sentinel_nodes: list[str] = []
    sentinel_password: str | None = None

    # Cluster settings
    cluster_nodes: list[str] = []

    # Common settings
    password: str | None = None
    ssl: bool = False
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    retry_on_timeout: bool = True
    max_connections: int = 50
    health_check_interval: int = 30

    @field_validator("sentinel_nodes", "cluster_nodes", mode="before")
    @classmethod
    def _parse_csv(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [n.strip() for n in v.split(",") if n.strip()]
        if isinstance(v, list):
            return v
        return []

    @classmethod
    def from_env(cls) -> RedisConfig:
        """Load Redis configuration from environment variables.

        Environment variables:
            REDIS_TOPOLOGY: standalone | sentinel | cluster
            REDIS_URL: Connection URL (standalone mode)
            REDIS_DB: Database number
            REDIS_PASSWORD: Auth password
            REDIS_SSL: Enable TLS (true/false)
            REDIS_SENTINEL_MASTER: Sentinel master name
            REDIS_SENTINEL_NODES: Comma-separated sentinel host:port list
            REDIS_SENTINEL_PASSWORD: Sentinel auth password
            REDIS_CLUSTER_NODES: Comma-separated cluster host:port list
            REDIS_MAX_CONNECTIONS: Connection pool size
            REDIS_SOCKET_TIMEOUT: Socket timeout in seconds
            REDIS_HEALTH_CHECK_INTERVAL: Health check interval in seconds
        """
        topology_str = os.getenv("REDIS_TOPOLOGY", "standalone").lower()
        try:
            topology = RedisTopology(topology_str)
        except ValueError:
            logger.warning(
                "Unknown REDIS_TOPOLOGY=%s, falling back to standalone",
                topology_str,
            )
            topology = RedisTopology.STANDALONE

        return cls(
            topology=topology,
            url=os.getenv("REDIS_URL", "redis://localhost:6379"),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD"),
            ssl=os.getenv("REDIS_SSL", "false").lower() in ("true", "1"),
            sentinel_master=os.getenv("REDIS_SENTINEL_MASTER"),
            sentinel_nodes=os.getenv("REDIS_SENTINEL_NODES", ""),
            sentinel_password=os.getenv("REDIS_SENTINEL_PASSWORD"),
            cluster_nodes=os.getenv("REDIS_CLUSTER_NODES", ""),
            max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "50")),
            socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0")),
            socket_connect_timeout=float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5.0")),
            retry_on_timeout=os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() in ("true", "1"),
            health_check_interval=int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30")),
        )

    def get_connection_kwargs(self) -> JSONDict:
        """Return kwargs suitable for ``redis.Redis()`` or similar."""
        base: JSONDict = {
            "socket_timeout": self.socket_timeout,
            "socket_connect_timeout": self.socket_connect_timeout,
            "retry_on_timeout": self.retry_on_timeout,
            "health_check_interval": self.health_check_interval,
        }
        if self.password:
            base["password"] = self.password
        if self.ssl:
            base["ssl"] = True
        return base
