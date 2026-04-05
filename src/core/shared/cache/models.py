"""
ACGS-2 Tiered Cache Models
Constitutional Hash: 608508a9bd224290
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeVar

T = TypeVar("T")


class CacheTier(Enum):
    """Cache tier identifiers."""

    L1 = "L1"  # In-process cache (fastest)
    L2 = "L2"  # Redis cache (shared)
    L3 = "L3"  # Distributed/persistent cache (slowest)
    NONE = "NONE"  # Not cached in any tier


@dataclass
class TieredCacheConfig:
    """Configuration for tiered cache manager."""

    # L1 configuration
    l1_maxsize: int = 1024
    l1_ttl: int = 300  # 5 minutes (must be <= L2 TTL)

    # L2 configuration
    l2_ttl: int = 3600  # 1 hour
    redis_url: str | None = None

    # L3 configuration
    l3_ttl: int = 86400  # 24 hours
    l3_enabled: bool = True

    # Promotion/demotion thresholds
    promotion_threshold: int = 10  # Accesses per minute to promote to L1
    demotion_threshold_hours: float = 1.0  # Hours without access to demote to L3

    # Serialization
    serialize: bool = True  # JSON serialize for type consistency across tiers


@dataclass
class TieredCacheStats:
    """Statistics for tiered cache operations."""

    l1_hits: int = 0
    l1_misses: int = 0
    l2_hits: int = 0
    l2_misses: int = 0
    l3_hits: int = 0
    l3_misses: int = 0
    promotions: int = 0
    demotions: int = 0
    redis_failures: int = 0

    @property
    def total_hits(self) -> int:
        """Total hits across all tiers."""
        return self.l1_hits + self.l2_hits + self.l3_hits

    @property
    def total_misses(self) -> int:
        """Total misses across all tiers."""
        return self.l1_misses + self.l2_misses + self.l3_misses

    @property
    def hit_ratio(self) -> float:
        """Overall hit ratio."""
        total = self.total_hits + self.total_misses
        return self.total_hits / total if total > 0 else 0.0

    @property
    def l1_hit_ratio(self) -> float:
        """L1 hit ratio."""
        total = self.l1_hits + self.l1_misses
        return self.l1_hits / total if total > 0 else 0.0


@dataclass
class AccessRecord:
    """Tracks access patterns for a cache key."""

    key: str
    access_times: list[float] = field(default_factory=list)
    last_access: float = field(default_factory=time.time)
    current_tier: CacheTier = CacheTier.NONE

    def record_access(self) -> None:
        """Record a new access."""
        now = time.time()
        self.last_access = now
        # Keep only accesses from the last minute for promotion calculation
        cutoff = now - 60
        self.access_times = [t for t in self.access_times if t >= cutoff]
        self.access_times.append(now)

    @property
    def accesses_per_minute(self) -> int:
        """Count of accesses in the last minute."""
        now = time.time()
        cutoff = now - 60
        return sum(1 for t in self.access_times if t >= cutoff)

    @property
    def hours_since_access(self) -> float:
        """Hours since last access."""
        return (time.time() - self.last_access) / 3600
