"""
ACGS-2 Enhanced Agent Bus - Context & Memory (Layer 1)
Constitutional Hash: 608508a9bd224290

Mamba-2 Hybrid Processor for O(n) context handling with 4M+ token support.
Implements Phase 2.1 Layer 1 from ROADMAP_2025.md.

Key Components:
- MambaProcessor: Mamba-2 SSM layer implementation
- HybridContextManager: Attention + SSM hybrid handling
- JRTContextPreparer: Just-in-time retrieval preparation
- LongTermMemoryStore: Persistent memory management
- ConstitutionalContextCache: Fast constitutional context access

Performance Requirements:
- 30x context length increase target
- Sub-5ms P99 latency for context retrieval
- Efficient memory usage with streaming
"""

__version__ = "1.0.0"

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

__constitutional_hash__ = CONSTITUTIONAL_HASH

from .constitutional_context_cache import (
    CacheConfig,
    CacheEntry,
    CacheStats,
    ConstitutionalContextCache,
)
from .context_optimizer import (
    AdaptiveCacheEntry,
    BatchProcessingResult,
    ContextWindowOptimizer,
    OptimizationStrategy,
    OptimizerConfig,
    ParallelBatchProcessor,
    PrefetchManager,
    ScoringResult,
    StreamingProcessor,
    StreamingResult,
    VectorizedScorer,
)
from .hybrid_context_manager import (
    HybridContextConfig,
    HybridContextManager,
    ProcessingMode,
)
from .jrt_context_preparer import (
    CriticalSectionMarker,
    JRTContextPreparer,
    JRTRetrievalStrategy,
)
from .long_term_memory import (
    ConsolidationStrategy,
    LongTermMemoryConfig,
    LongTermMemoryStore,
    MemoryTier,
)
from .mamba_processor import (
    Mamba2SSMLayer,
    MambaProcessor,
    MambaProcessorConfig,
)
from .models import (
    ContextChunk,
    ContextPriority,
    ContextRetrievalResult,
    ContextType,
    ContextWindow,
    EpisodicMemoryEntry,
    JRTConfig,
    MambaConfig,
    MemoryConsolidationResult,
    MemoryOperation,
    MemoryOperationType,
    MemoryQuery,
    SemanticMemoryEntry,
)

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "AdaptiveCacheEntry",
    "BatchProcessingResult",
    "CacheConfig",
    "CacheEntry",
    "CacheStats",
    "ConsolidationStrategy",
    # Constitutional Context Cache
    "ConstitutionalContextCache",
    # Models
    "ContextChunk",
    "ContextPriority",
    "ContextRetrievalResult",
    "ContextType",
    "ContextWindow",
    # Context Optimizer (Phase 4)
    "ContextWindowOptimizer",
    "CriticalSectionMarker",
    "EpisodicMemoryEntry",
    "HybridContextConfig",
    # Hybrid Context Manager
    "HybridContextManager",
    "JRTConfig",
    # JRT Context Preparer
    "JRTContextPreparer",
    "JRTRetrievalStrategy",
    "LongTermMemoryConfig",
    # Long Term Memory
    "LongTermMemoryStore",
    "Mamba2SSMLayer",
    "MambaConfig",
    # Mamba Processor
    "MambaProcessor",
    "MambaProcessorConfig",
    "MemoryConsolidationResult",
    "MemoryOperation",
    "MemoryOperationType",
    "MemoryQuery",
    "MemoryTier",
    "OptimizationStrategy",
    "OptimizerConfig",
    "ParallelBatchProcessor",
    "PrefetchManager",
    "ProcessingMode",
    "ScoringResult",
    "SemanticMemoryEntry",
    "StreamingProcessor",
    "StreamingResult",
    "VectorizedScorer",
]
