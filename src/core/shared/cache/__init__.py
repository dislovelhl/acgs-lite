"""
ACGS-2 Tiered Cache Module
Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
import importlib
import threading

from src.core.shared.structured_logging import get_logger

# Singleton pattern
from .l1 import L1Cache, L1CacheConfig, L1CacheStats, get_l1_cache, reset_l1_cache
from .manager import TieredCacheManager
from .metrics import (
    CACHE_CAPACITY,
    CACHE_DEMOTIONS_TOTAL,
    CACHE_ENTRIES,
    CACHE_EVICTIONS_TOTAL,
    CACHE_FALLBACK_TOTAL,
    CACHE_HITS_TOTAL,
    CACHE_MISSES_TOTAL,
    CACHE_OPERATION_DURATION,
    CACHE_OPERATION_DURATION_L1,
    CACHE_OPERATION_DURATION_L2,
    CACHE_OPERATION_DURATION_L3,
    CACHE_PROMOTIONS_TOTAL,
    CACHE_SIZE,
    CACHE_TIER_HEALTH,
    CACHE_WARMING_DURATION,
    CACHE_WARMING_KEYS_LOADED,
    L1_LATENCY,
    L1_LATENCY_BUCKETS,
    L2_LATENCY,
    L2_LATENCY_BUCKETS,
    L3_LATENCY,
    L3_LATENCY_BUCKETS,
    record_cache_hit,
    record_cache_latency,
    record_cache_miss,
    record_demotion,
    record_eviction,
    record_fallback,
    record_promotion,
    set_tier_health,
    track_cache_operation,
    update_cache_size,
)
from .models import AccessRecord, CacheTier, TieredCacheConfig, TieredCacheStats
from .workflow_state import WorkflowStateCache, workflow_cache

logger = get_logger(__name__)
from src.core.shared.constants import CONSTITUTIONAL_HASH

_default_manager: TieredCacheManager | None = None
_singleton_lock = threading.Lock()


def get_tiered_cache(
    config: TieredCacheConfig | None = None,
    name: str = "default",
) -> TieredCacheManager:
    """Return the singleton TieredCacheManager, creating it on first call."""
    global _default_manager
    if _default_manager is None:
        with _singleton_lock:
            if _default_manager is None:
                _default_manager = TieredCacheManager(config=config, name=name)
                logger.info(f"[{CONSTITUTIONAL_HASH}] TieredCacheManager singleton created")
    return _default_manager


def reset_tiered_cache() -> None:
    """Close and discard the singleton TieredCacheManager."""
    global _default_manager
    with _singleton_lock:
        if _default_manager is not None:
            try:
                loop = asyncio.get_running_loop()
                _task = loop.create_task(_default_manager.close())
                _task.add_done_callback(
                    lambda t: (
                        logger.error("cache close task failed: %s", t.exception())
                        if not t.cancelled() and t.exception()
                        else None
                    )
                )
            except RuntimeError:
                asyncio.run(_default_manager.close())
            _default_manager = None
            logger.info(f"[{CONSTITUTIONAL_HASH}] TieredCacheManager singleton reset")


_WARMING_EXPORTS = {
    "WarmingStatus",
    "CacheWarmer",
    "WarmingConfig",
    "WarmingResult",
    "WarmingProgress",
    "RateLimiter",
    "get_cache_warmer",
    "reset_cache_warmer",
    "warm_cache_on_startup",
}


def __getattr__(name: str):
    if name in _WARMING_EXPORTS:
        warming_module = importlib.import_module(".warming", __name__)
        return getattr(warming_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CACHE_CAPACITY",
    "CACHE_DEMOTIONS_TOTAL",
    "CACHE_ENTRIES",
    "CACHE_EVICTIONS_TOTAL",
    "CACHE_FALLBACK_TOTAL",
    "CACHE_HITS_TOTAL",
    "CACHE_MISSES_TOTAL",
    "CACHE_OPERATION_DURATION",
    "CACHE_OPERATION_DURATION_L1",
    "CACHE_OPERATION_DURATION_L2",
    "CACHE_OPERATION_DURATION_L3",
    "CACHE_PROMOTIONS_TOTAL",
    "CACHE_SIZE",
    "CACHE_TIER_HEALTH",
    "CACHE_WARMING_DURATION",
    "CACHE_WARMING_KEYS_LOADED",
    "CONSTITUTIONAL_HASH",
    "L1_LATENCY",
    "L1_LATENCY_BUCKETS",
    "L2_LATENCY",
    "L2_LATENCY_BUCKETS",
    "L3_LATENCY",
    "L3_LATENCY_BUCKETS",
    "AccessRecord",
    "CacheTier",
    "CacheWarmer",
    "L1Cache",
    "L1CacheConfig",
    "L1CacheStats",
    "RateLimiter",
    "TieredCacheConfig",
    "TieredCacheManager",
    "TieredCacheStats",
    "WarmingConfig",
    "WarmingProgress",
    "WarmingResult",
    "WarmingStatus",
    "WorkflowStateCache",
    "get_cache_warmer",
    "get_l1_cache",
    "get_tiered_cache",
    "record_cache_hit",
    "record_cache_latency",
    "record_cache_miss",
    "record_demotion",
    "record_eviction",
    "record_fallback",
    "record_promotion",
    "reset_cache_warmer",
    "reset_l1_cache",
    "reset_tiered_cache",
    "set_tier_health",
    "track_cache_operation",
    "update_cache_size",
    "warm_cache_on_startup",
    "workflow_cache",
]
