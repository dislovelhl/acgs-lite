"""
ACGS-2 Context & Memory - Context Window Optimizer
Constitutional Hash: 608508a9bd224290

BACKWARD COMPATIBILITY SHIM

This file re-exports all components from the refactored optimizer module.
The implementation has been split into multiple files under:
    context_memory/optimizer/

All original imports continue to work:
    from .context_optimizer import ContextWindowOptimizer
    from .context_optimizer import OptimizerConfig, OptimizationStrategy
    etc.

For new code, prefer importing from the optimizer subpackage directly:
    from .optimizer import ContextWindowOptimizer
    from .optimizer.config import OptimizerConfig
"""

# Re-export everything from the optimizer package
from .optimizer import (
    # Constants
    CONSTITUTIONAL_HASH,
    NUMPY_AVAILABLE,
    AdaptiveCacheEntry,
    # Result models
    BatchProcessingResult,
    # Main optimizer
    ContextWindowOptimizer,
    OptimizationStrategy,
    # Configuration
    OptimizerConfig,
    ParallelBatchProcessor,
    PrefetchManager,
    ScoringResult,
    StreamingProcessor,
    StreamingResult,
    # Component classes
    VectorizedScorer,
)

__all__ = [
    "CONSTITUTIONAL_HASH",
    "NUMPY_AVAILABLE",
    "AdaptiveCacheEntry",
    "BatchProcessingResult",
    "ContextWindowOptimizer",
    "OptimizationStrategy",
    "OptimizerConfig",
    "ParallelBatchProcessor",
    "PrefetchManager",
    "ScoringResult",
    "StreamingProcessor",
    "StreamingResult",
    "VectorizedScorer",
]
