"""
ACGS-2 Enhanced Agent Bus - Context Optimization Extension Exports
Constitutional Hash: 608508a9bd224290

Extension module for Phase 4: Context Window Optimization.
Provides clean import interface for context optimization components.
"""

try:
    from .context_optimization import (
        # Feature flag
        CONTEXT_OPTIMIZATION_AVAILABLE,
        CachedGovernanceValidator,
        CompressionResult,
        # Task 4.1: Spec Delta Compression
        CompressionStrategy,
        # Task 4.2: Cached Governance Validator
        GovernanceDecision,
        GovernanceValidatorProtocol,
        OptimizedAgentBus,
        PartitionBroker,
        PartitionedMessage,
        SpecBaseline,
        SpecDeltaCompressor,
        TopicConfig,
        # Task 4.3: Optimized Agent Bus
        TopicPriority,
        ValidationContext,
        create_cached_validator,
        create_optimized_bus,
        create_spec_compressor,
    )
except ImportError:
    # Graceful fallback if context optimization not available

    CONTEXT_OPTIMIZATION_AVAILABLE = False
    # Task 4.1 stubs
    CompressionStrategy = object  # type: ignore[assignment, misc]
    CompressionResult = object  # type: ignore[assignment, misc]
    SpecBaseline = object  # type: ignore[assignment, misc]
    SpecDeltaCompressor = object  # type: ignore[assignment, misc]
    create_spec_compressor = None  # type: ignore[assignment]
    # Task 4.2 stubs
    GovernanceDecision = object  # type: ignore[assignment, misc]
    ValidationContext = object  # type: ignore[assignment, misc]
    GovernanceValidatorProtocol = object  # type: ignore[assignment, misc]
    CachedGovernanceValidator = object  # type: ignore[assignment, misc]
    create_cached_validator = None  # type: ignore[assignment]
    # Task 4.3 stubs
    TopicPriority = object  # type: ignore[assignment, misc]
    TopicConfig = object  # type: ignore[assignment, misc]
    PartitionedMessage = object  # type: ignore[assignment, misc]
    PartitionBroker = object  # type: ignore[assignment, misc]
    OptimizedAgentBus = object  # type: ignore[assignment, misc]
    create_optimized_bus = None  # type: ignore[assignment]

__all__ = [
    "CONTEXT_OPTIMIZATION_AVAILABLE",
    "CachedGovernanceValidator",
    "CompressionResult",
    # Task 4.1
    "CompressionStrategy",
    # Task 4.2
    "GovernanceDecision",
    "GovernanceValidatorProtocol",
    "OptimizedAgentBus",
    "PartitionBroker",
    "PartitionedMessage",
    "SpecBaseline",
    "SpecDeltaCompressor",
    "TopicConfig",
    # Task 4.3
    "TopicPriority",
    "ValidationContext",
    "create_cached_validator",
    "create_optimized_bus",
    "create_spec_compressor",
]

_EXT_ALL = __all__
