# Constitutional Hash: 608508a9bd224290
"""Optional Cognee Knowledge Graph Integration."""

try:
    from .context_memory.cognee_ltm_adapter import (
        CogneeLongTermMemory,
        CogneeLTMConfig,
    )
    from .context_memory.cognee_memory import (
        HAS_COGNEE,
        CogneeConfig,
        ComplianceResult,
        ConstitutionalKnowledgeGraph,
    )

    COGNEE_AVAILABLE = HAS_COGNEE
except ImportError:
    COGNEE_AVAILABLE = False
    CogneeConfig = object  # type: ignore[assignment, misc]
    ComplianceResult = object  # type: ignore[assignment, misc]
    ConstitutionalKnowledgeGraph = object  # type: ignore[assignment, misc]
    CogneeLongTermMemory = object  # type: ignore[assignment, misc]
    CogneeLTMConfig = object  # type: ignore[assignment, misc]

_EXT_ALL = [
    "COGNEE_AVAILABLE",
    "CogneeConfig",
    "ComplianceResult",
    "ConstitutionalKnowledgeGraph",
    "CogneeLongTermMemory",
    "CogneeLTMConfig",
]
