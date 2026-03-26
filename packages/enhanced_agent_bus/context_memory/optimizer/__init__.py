"""
ACGS-2 Context Optimizer Module
Constitutional Hash: 608508a9bd224290

Re-exports all optimizer components for backward compatibility.
"""

from .batch_processor import ParallelBatchProcessor
from .config import CONSTITUTIONAL_HASH, OptimizationStrategy, OptimizerConfig
from .models import (
    AdaptiveCacheEntry,
    BatchProcessingResult,
    ScoringResult,
    StreamingResult,
)
from .optimizer import NUMPY_AVAILABLE, ContextWindowOptimizer
from .prefetch import PrefetchManager
from .scorer import VectorizedScorer
from .streaming import StreamingProcessor

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "NUMPY_AVAILABLE",
    "AdaptiveCacheEntry",
    # Result models
    "BatchProcessingResult",
    # Main optimizer
    "ContextWindowOptimizer",
    "OptimizationStrategy",
    # Configuration
    "OptimizerConfig",
    "ParallelBatchProcessor",
    "PrefetchManager",
    "ScoringResult",
    "StreamingProcessor",
    "StreamingResult",
    # Component classes
    "VectorizedScorer",
]
