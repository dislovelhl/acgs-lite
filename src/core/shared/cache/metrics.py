"""
ACGS-2 Cache Metrics Module with Per-Tier Instrumentation
Constitutional Hash: 608508a9bd224290

This module provides Prometheus metrics for tiered cache instrumentation (L1/L2/L3).
All cache metrics include tier labels for accurate per-tier tracking.
"""

import inspect
import time
from collections.abc import Callable
from functools import wraps

from src.core.shared.metrics._registry import (
    _get_or_create_counter,
    _get_or_create_gauge,
    _get_or_create_histogram,
)

# ============================================================================
# Tier-Specific Histogram Buckets
# Optimized for each tier's latency profile as per spec
# ============================================================================

# L1 In-Process Cache: Sub-millisecond precision (<0.1ms target)
L1_LATENCY_BUCKETS = [0.00001, 0.00005, 0.0001, 0.0005, 0.001]

# L2 Redis Cache: 1-100ms range
L2_LATENCY_BUCKETS = [0.001, 0.005, 0.01, 0.025, 0.05, 0.1]

# L3 Distributed Cache: 10-1000ms range
L3_LATENCY_BUCKETS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0]

# ============================================================================
# Cache Hit/Miss Counters with Tier Labels
# ============================================================================

CACHE_HITS_TOTAL = _get_or_create_counter(
    "tiered_cache_hits_total",
    "Total cache hits by tier",
    ["tier", "cache_name", "operation"],
)

CACHE_MISSES_TOTAL = _get_or_create_counter(
    "tiered_cache_misses_total",
    "Total cache misses by tier",
    ["tier", "cache_name", "operation"],
)

# ============================================================================
# Cache Latency Histograms - Per-Tier with Optimized Buckets
# ============================================================================

CACHE_OPERATION_DURATION_L1 = _get_or_create_histogram(
    "cache_operation_duration_l1_seconds",
    "L1 in-process cache operation latency in seconds",
    ["cache_name", "operation"],
    buckets=L1_LATENCY_BUCKETS,
)

CACHE_OPERATION_DURATION_L2 = _get_or_create_histogram(
    "cache_operation_duration_l2_seconds",
    "L2 Redis cache operation latency in seconds",
    ["cache_name", "operation"],
    buckets=L2_LATENCY_BUCKETS,
)

CACHE_OPERATION_DURATION_L3 = _get_or_create_histogram(
    "cache_operation_duration_l3_seconds",
    "L3 distributed cache operation latency in seconds",
    ["cache_name", "operation"],
    buckets=L3_LATENCY_BUCKETS,
)

# Map tier names to their respective histogram metrics
CACHE_OPERATION_DURATION = {
    "L1": CACHE_OPERATION_DURATION_L1,
    "L2": CACHE_OPERATION_DURATION_L2,
    "L3": CACHE_OPERATION_DURATION_L3,
}

# Convenient aliases for tier-specific latency histograms
# These provide a simpler naming convention for direct tier access
L1_LATENCY = CACHE_OPERATION_DURATION_L1
L2_LATENCY = CACHE_OPERATION_DURATION_L2
L3_LATENCY = CACHE_OPERATION_DURATION_L3

# ============================================================================
# Cache Size and Capacity Gauges
# ============================================================================

CACHE_SIZE = _get_or_create_gauge(
    "tiered_cache_size_bytes",
    "Current cache size in bytes by tier",
    ["tier", "cache_name"],
)

CACHE_ENTRIES = _get_or_create_gauge(
    "tiered_cache_entries_total",
    "Current number of entries in cache by tier",
    ["tier", "cache_name"],
)

CACHE_CAPACITY = _get_or_create_gauge(
    "tiered_cache_capacity_entries",
    "Maximum capacity in entries by tier",
    ["tier", "cache_name"],
)

# ============================================================================
# Tier Promotion/Demotion Counters
# ============================================================================

CACHE_PROMOTIONS_TOTAL = _get_or_create_counter(
    "tiered_cache_promotions_total",
    "Total cache entry promotions between tiers",
    ["from_tier", "to_tier", "cache_name"],
)

CACHE_DEMOTIONS_TOTAL = _get_or_create_counter(
    "tiered_cache_demotions_total",
    "Total cache entry demotions between tiers",
    ["from_tier", "to_tier", "cache_name"],
)

CACHE_EVICTIONS_TOTAL = _get_or_create_counter(
    "tiered_cache_evictions_total",
    "Total cache entry evictions by tier",
    ["tier", "cache_name", "reason"],
)

# ============================================================================
# Cache Warming Metrics
# ============================================================================

CACHE_WARMING_KEYS_LOADED = _get_or_create_counter(
    "tiered_cache_warming_keys_loaded_total",
    "Total keys loaded during cache warming",
    ["tier", "cache_name"],
)

CACHE_WARMING_DURATION = _get_or_create_histogram(
    "tiered_cache_warming_duration_seconds",
    "Cache warming duration in seconds",
    ["tier", "cache_name"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

# ============================================================================
# Redis Health / Fallback Metrics
# ============================================================================

CACHE_FALLBACK_TOTAL = _get_or_create_counter(
    "tiered_cache_fallback_total",
    "Total fallback events when a tier is unavailable",
    ["unavailable_tier", "fallback_tier", "cache_name"],
)

CACHE_TIER_HEALTH = _get_or_create_gauge(
    "tiered_cache_tier_health",
    "Health status of cache tier (1=healthy, 0=unhealthy)",
    ["tier"],
)

# ============================================================================
# Helper Functions for Recording Metrics
# ============================================================================


def record_cache_hit(tier: str, cache_name: str, operation: str = "get") -> None:
    """Record a cache hit for the specified tier."""
    CACHE_HITS_TOTAL.labels(tier=tier, cache_name=cache_name, operation=operation).inc()


def record_cache_miss(tier: str, cache_name: str, operation: str = "get") -> None:
    """Record a cache miss for the specified tier."""
    CACHE_MISSES_TOTAL.labels(tier=tier, cache_name=cache_name, operation=operation).inc()


def record_cache_latency(tier: str, cache_name: str, operation: str, duration: float) -> None:
    """Record cache operation latency for the specified tier."""
    if tier in CACHE_OPERATION_DURATION:
        CACHE_OPERATION_DURATION[tier].labels(cache_name=cache_name, operation=operation).observe(
            duration
        )


def record_promotion(from_tier: str, to_tier: str, cache_name: str) -> None:
    """Record a cache entry promotion between tiers."""
    CACHE_PROMOTIONS_TOTAL.labels(from_tier=from_tier, to_tier=to_tier, cache_name=cache_name).inc()


def record_demotion(from_tier: str, to_tier: str, cache_name: str) -> None:
    """Record a cache entry demotion between tiers."""
    CACHE_DEMOTIONS_TOTAL.labels(from_tier=from_tier, to_tier=to_tier, cache_name=cache_name).inc()


def record_eviction(tier: str, cache_name: str, reason: str = "lru") -> None:
    """Record a cache entry eviction."""
    CACHE_EVICTIONS_TOTAL.labels(tier=tier, cache_name=cache_name, reason=reason).inc()


def update_cache_size(tier: str, cache_name: str, size_bytes: int, entries: int) -> None:
    """Update cache size metrics for a tier."""
    CACHE_SIZE.labels(tier=tier, cache_name=cache_name).set(size_bytes)
    CACHE_ENTRIES.labels(tier=tier, cache_name=cache_name).set(entries)


def set_tier_health(tier: str, healthy: bool) -> None:
    """Set the health status of a cache tier."""
    CACHE_TIER_HEALTH.labels(tier=tier).set(1 if healthy else 0)


def record_fallback(unavailable_tier: str, fallback_tier: str, cache_name: str) -> None:
    """Record a fallback event when a tier is unavailable."""
    CACHE_FALLBACK_TOTAL.labels(
        unavailable_tier=unavailable_tier,
        fallback_tier=fallback_tier,
        cache_name=cache_name,
    ).inc()


# ============================================================================
# Decorators for Cache Operation Instrumentation
# ============================================================================


def track_cache_operation(tier: str, cache_name: str, operation: str):
    """
    Decorator to track cache operation metrics including latency.

    Usage:
        @track_cache_operation('L1', 'policy_cache', 'get')
        def get_from_cache(key):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                # Determine hit or miss based on result
                if result is not None:
                    record_cache_hit(tier, cache_name, operation)
                else:
                    record_cache_miss(tier, cache_name, operation)
                return result
            finally:
                duration = time.perf_counter() - start_time
                record_cache_latency(tier, cache_name, operation, duration)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                # Determine hit or miss based on result
                if result is not None:
                    record_cache_hit(tier, cache_name, operation)
                else:
                    record_cache_miss(tier, cache_name, operation)
                return result
            finally:
                duration = time.perf_counter() - start_time
                record_cache_latency(tier, cache_name, operation, duration)

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


__all__ = [
    "CACHE_CAPACITY",
    "CACHE_DEMOTIONS_TOTAL",
    "CACHE_ENTRIES",
    "CACHE_EVICTIONS_TOTAL",
    # Health/Fallback Metrics
    "CACHE_FALLBACK_TOTAL",
    # Hit/Miss Counters
    "CACHE_HITS_TOTAL",
    "CACHE_MISSES_TOTAL",
    "CACHE_OPERATION_DURATION",
    # Latency Histograms
    "CACHE_OPERATION_DURATION_L1",
    "CACHE_OPERATION_DURATION_L2",
    "CACHE_OPERATION_DURATION_L3",
    # Promotion/Demotion Counters
    "CACHE_PROMOTIONS_TOTAL",
    # Size/Capacity Gauges
    "CACHE_SIZE",
    "CACHE_TIER_HEALTH",
    "CACHE_WARMING_DURATION",
    # Warming Metrics
    "CACHE_WARMING_KEYS_LOADED",
    # Tier-specific latency histogram aliases
    "L1_LATENCY",
    # Tier-specific bucket configurations
    "L1_LATENCY_BUCKETS",
    "L2_LATENCY",
    "L2_LATENCY_BUCKETS",
    "L3_LATENCY",
    "L3_LATENCY_BUCKETS",
    # Helper Functions
    "record_cache_hit",
    "record_cache_latency",
    "record_cache_miss",
    "record_demotion",
    "record_eviction",
    "record_fallback",
    "record_promotion",
    "set_tier_health",
    # Decorators
    "track_cache_operation",
    "update_cache_size",
]
