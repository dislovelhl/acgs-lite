# Constitutional Hash: 608508a9bd224290
"""Optional Context & Memory Module (Phase 2.1 Layer 1 - Mamba-2 Hybrid Processor)."""

try:
    from .context_memory import (
        CacheConfig,
        CacheEntry,  # noqa: F401
        CacheStats,
        ConsolidationStrategy,
        ConstitutionalContextCache,
        ContextPriority,
        ContextRetrievalResult,
        ContextType,
        CriticalSectionMarker,
        EpisodicMemoryEntry,
        HybridContextConfig,
        HybridContextManager,
        JRTConfig,
        JRTContextPreparer,
        JRTRetrievalStrategy,
        LongTermMemoryConfig,
        LongTermMemoryStore,
        Mamba2SSMLayer,
        MambaConfig,
        MambaProcessor,
        MambaProcessorConfig,
        MemoryConsolidationResult,
        MemoryOperation,
        MemoryOperationType,
        MemoryQuery,
        MemoryTier,
        ProcessingMode,
        SemanticMemoryEntry,
    )
    from .context_memory import CacheEntry as ContextMemoryCacheEntry
    from .context_memory import ContextChunk as ContextMemoryChunk
    from .context_memory import ContextWindow as ContextMemoryWindow

    CONTEXT_MEMORY_AVAILABLE = True
except ImportError:
    CONTEXT_MEMORY_AVAILABLE = False
    ContextMemoryChunk = object  # type: ignore[assignment, misc]
    ContextPriority = object  # type: ignore[assignment, misc]
    ContextRetrievalResult = object  # type: ignore[assignment, misc]
    ContextType = object  # type: ignore[assignment, misc]
    ContextMemoryWindow = object  # type: ignore[assignment, misc]
    EpisodicMemoryEntry = object  # type: ignore[assignment, misc]
    JRTConfig = object  # type: ignore[assignment, misc]
    MambaConfig = object  # type: ignore[assignment, misc]
    MemoryConsolidationResult = object  # type: ignore[assignment, misc]
    MemoryOperation = object  # type: ignore[assignment, misc]
    MemoryOperationType = object  # type: ignore[assignment, misc]
    MemoryQuery = object  # type: ignore[assignment, misc]
    SemanticMemoryEntry = object  # type: ignore[assignment, misc]
    MambaProcessor = object  # type: ignore[assignment, misc]
    Mamba2SSMLayer = object  # type: ignore[assignment, misc]
    MambaProcessorConfig = object  # type: ignore[assignment, misc]
    HybridContextManager = object  # type: ignore[assignment, misc]
    HybridContextConfig = object  # type: ignore[assignment, misc]
    ProcessingMode = object  # type: ignore[assignment, misc]
    JRTContextPreparer = object  # type: ignore[assignment, misc]
    JRTRetrievalStrategy = object  # type: ignore[assignment, misc]
    CriticalSectionMarker = object  # type: ignore[assignment, misc]
    LongTermMemoryStore = object  # type: ignore[assignment, misc]
    LongTermMemoryConfig = object  # type: ignore[assignment, misc]
    MemoryTier = object  # type: ignore[assignment, misc]
    ConsolidationStrategy = object  # type: ignore[assignment, misc]
    ConstitutionalContextCache = object  # type: ignore[assignment, misc]
    CacheConfig = object  # type: ignore[assignment, misc]
    ContextMemoryCacheEntry = object  # type: ignore[assignment, misc]
    CacheStats = object  # type: ignore[assignment, misc]

_EXT_ALL = [
    "CONTEXT_MEMORY_AVAILABLE",
    "ContextMemoryChunk",
    "ContextPriority",
    "ContextRetrievalResult",
    "ContextType",
    "ContextMemoryWindow",
    "EpisodicMemoryEntry",
    "JRTConfig",
    "MambaConfig",
    "MemoryConsolidationResult",
    "MemoryOperation",
    "MemoryOperationType",
    "MemoryQuery",
    "SemanticMemoryEntry",
    "MambaProcessor",
    "Mamba2SSMLayer",
    "MambaProcessorConfig",
    "HybridContextManager",
    "HybridContextConfig",
    "ProcessingMode",
    "JRTContextPreparer",
    "JRTRetrievalStrategy",
    "CriticalSectionMarker",
    "LongTermMemoryStore",
    "LongTermMemoryConfig",
    "MemoryTier",
    "ConsolidationStrategy",
    "ConstitutionalContextCache",
    "CacheConfig",
    "ContextMemoryCacheEntry",
    "CacheStats",
]
