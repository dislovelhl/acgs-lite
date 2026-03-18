"""
Configuration for ACGS-2 Constitutional Storage.

Constitutional Hash: cdd01ef066bc6cf2
"""

from dataclasses import dataclass


@dataclass
class StorageConfig:
    """Configuration for constitutional storage service."""

    redis_url: str = "redis://localhost:6379"
    database_url: str = "postgresql+asyncpg://localhost/acgs2"
    cache_ttl: int = 3600
    lock_timeout: int = 30
    enable_multi_tenancy: bool = True
    default_tenant_id: str = "system"

    # Redis key prefixes (tenant-aware)
    version_prefix: str = "constitutional:version:"
    active_version_key: str = "constitutional:active_version"
    lock_key: str = "constitutional:lock:version_transition"
