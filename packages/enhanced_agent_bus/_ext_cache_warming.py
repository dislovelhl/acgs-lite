# Constitutional Hash: cdd01ef066bc6cf2
"""Optional cache warming integration for FastAPI startup."""

try:
    from src.core.shared.cache_warming import (
        CacheWarmer,
        WarmingConfig,
        WarmingProgress,
        WarmingResult,
        WarmingStatus,
        get_cache_warmer,
        reset_cache_warmer,
        warm_cache_on_startup,
    )

    CACHE_WARMING_AVAILABLE = True
except ImportError:
    try:
        from src.core.shared.cache_warming import (  # pragma: no cover
            CacheWarmer,
            WarmingConfig,
            WarmingProgress,
            WarmingResult,
            WarmingStatus,
            get_cache_warmer,
            reset_cache_warmer,
            warm_cache_on_startup,
        )

        CACHE_WARMING_AVAILABLE = True
    except ImportError:
        CACHE_WARMING_AVAILABLE = False
        CacheWarmer = object  # type: ignore[assignment, misc]
        WarmingConfig = object  # type: ignore[assignment, misc]
        WarmingProgress = object  # type: ignore[assignment, misc]
        WarmingResult = object  # type: ignore[assignment, misc]
        WarmingStatus = object  # type: ignore[assignment, misc]
        get_cache_warmer = object  # type: ignore[assignment, misc]
        reset_cache_warmer = object  # type: ignore[assignment, misc]
        warm_cache_on_startup = object  # type: ignore[assignment, misc]

_EXT_ALL = [
    "CACHE_WARMING_AVAILABLE",
    "CacheWarmer",
    "WarmingConfig",
    "WarmingProgress",
    "WarmingResult",
    "WarmingStatus",
    "get_cache_warmer",
    "reset_cache_warmer",
    "warm_cache_on_startup",
]
