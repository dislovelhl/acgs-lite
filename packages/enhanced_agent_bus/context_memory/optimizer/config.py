"""
ACGS-2 Context Optimizer - Configuration
Constitutional Hash: 608508a9bd224290

Configuration dataclasses and enums for context window optimization.
"""

from dataclasses import dataclass
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"


class OptimizationStrategy(str, Enum):
    """Strategy for context window optimization."""

    LATENCY_FIRST = "latency_first"  # Minimize latency
    THROUGHPUT_FIRST = "throughput_first"  # Maximize throughput
    MEMORY_EFFICIENT = "memory_efficient"  # Minimize memory usage
    BALANCED = "balanced"  # Balance all factors
    CONSTITUTIONAL_STRICT = "constitutional_strict"  # Prioritize constitutional


@dataclass
class OptimizerConfig:
    """Configuration for context optimizer.

    Constitutional Hash: 608508a9bd224290
    """

    # Parallel processing
    max_parallel_chunks: int = 32
    batch_size: int = 64
    enable_parallel_processing: bool = True

    # Adaptive caching
    enable_adaptive_ttl: bool = True
    min_ttl_seconds: int = 60
    max_ttl_seconds: int = 3600
    ttl_access_multiplier: float = 1.5

    # Vectorized scoring
    enable_vectorized_scoring: bool = True
    score_batch_size: int = 256

    # Streaming optimization
    enable_streaming_overlap: bool = True
    overlap_ratio: float = 0.1  # 10% overlap between chunks
    stream_buffer_size: int = 8192

    # Prefetching
    enable_prefetching: bool = True
    prefetch_threshold: float = 0.7
    max_prefetch_entries: int = 100

    # Performance targets
    p99_latency_target_ms: float = 5.0
    target_context_multiplier: int = 30  # 30x context length

    # Strategy
    optimization_strategy: OptimizationStrategy = OptimizationStrategy.BALANCED

    # Constitutional compliance
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self) -> None:
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {self.constitutional_hash}")


__all__ = [
    "CONSTITUTIONAL_HASH",
    "OptimizationStrategy",
    "OptimizerConfig",
]
