"""
ACGS-2 Enhanced Agent Bus - Performance Optimization Extension Exports
Constitutional Hash: cdd01ef066bc6cf2

Extension module for Phase 6: Performance Optimization.
Provides clean import interface with graceful fallback when the
performance_optimization module is unavailable.
"""

try:
    from .performance_optimization import (
        # Feature flag
        PERFORMANCE_OPTIMIZATION_AVAILABLE,
        # Task 6.1: Async Pipeline Optimizer
        AsyncPipelineOptimizer,
        BatchConfig,
        # Task 6.4: Latency Reducer
        BatchFlushResult,
        BatchProcessor,
        # Factory functions
        LatencyReducer,
        MemoryOptimizer,
        PipelineResult,
        # Task 6.1
        PipelineStage,
        PooledResource,
        # Task 6.2: Resource Pool
        ResourceFactory,
        ResourcePool,
        create_async_pipeline,
        create_latency_reducer,
        create_memory_optimizer,
        create_resource_pool,
    )
    from .performance_optimization import (
        # Task 6.3: Memory Optimizer
        CacheEntry as PerformanceCacheEntry,
    )
except ImportError:
    # Graceful fallback if performance optimization module is not available

    PERFORMANCE_OPTIMIZATION_AVAILABLE = False  # type: ignore[assignment]

    # Task 6.1 stubs
    PipelineStage = object  # type: ignore[assignment, misc]
    PipelineResult = object  # type: ignore[assignment, misc]
    AsyncPipelineOptimizer = object  # type: ignore[assignment, misc]
    create_async_pipeline = None  # type: ignore[assignment]

    # Task 6.2 stubs
    PooledResource = object  # type: ignore[assignment, misc]
    ResourceFactory = object  # type: ignore[assignment, misc]
    ResourcePool = object  # type: ignore[assignment, misc]
    create_resource_pool = None  # type: ignore[assignment]

    # Task 6.3 stubs
    PerformanceCacheEntry = object  # type: ignore[assignment, misc]
    MemoryOptimizer = object  # type: ignore[assignment, misc]
    create_memory_optimizer = None  # type: ignore[assignment]

    # Task 6.4 stubs
    BatchConfig = object  # type: ignore[assignment, misc]
    BatchFlushResult = object  # type: ignore[assignment, misc]
    BatchProcessor = object  # type: ignore[assignment, misc]
    LatencyReducer = object  # type: ignore[assignment, misc]
    create_latency_reducer = None  # type: ignore[assignment]

__all__ = [
    "PERFORMANCE_OPTIMIZATION_AVAILABLE",
    "AsyncPipelineOptimizer",
    # Task 6.4: Latency Reducer
    "BatchConfig",
    "BatchFlushResult",
    "BatchProcessor",
    "LatencyReducer",
    "MemoryOptimizer",
    # Task 6.3: Memory Optimizer
    "PerformanceCacheEntry",
    "PipelineResult",
    # Task 6.1: Async Pipeline Optimizer
    "PipelineStage",
    # Task 6.2: Resource Pool
    "PooledResource",
    "ResourceFactory",
    "ResourcePool",
    "create_async_pipeline",
    "create_latency_reducer",
    "create_memory_optimizer",
    "create_resource_pool",
]

_EXT_ALL = __all__
