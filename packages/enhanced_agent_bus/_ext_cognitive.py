# Constitutional Hash: 608508a9bd224290
"""Optional Cognitive Orchestration Module (Phase 11).

When unavailable, all exported names are stubbed to ``None`` or ``object``
(mirroring the pattern used by the other ``_ext_*`` lazy-load modules) so
that callers can guard with ``if COGNITIVE_AVAILABLE`` without hitting
``NameError``.  All names are listed in ``_EXT_ALL`` so the bus ``__init__``
can re-export them unconditionally.
"""

import importlib

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

# Constitutional Hash: 608508a9bd224290
"""Optional Cognitive Orchestration Module (Phase 11).

When unavailable, all exported names are stubbed to ``None`` or ``object``
(mirroring the pattern used by the other ``_ext_*`` lazy-load modules) so
that callers can guard with ``if COGNITIVE_AVAILABLE`` without hitting
``NameError``.  All names are listed in ``_EXT_ALL`` so the bus ``__init__``
can re-export them unconditionally.
"""

# Defensive dynamic import to sever static coupling with core.cognitive
try:
    _cog_mod = importlib.import_module("src.core.cognitive")

    AgentCapability = _cog_mod.AgentCapability
    CapabilityMatcher = _cog_mod.CapabilityMatcher
    ContextChunk = _cog_mod.ContextChunk
    ContextWindow = _cog_mod.ContextWindow
    ExecutionPlan = _cog_mod.ExecutionPlan
    GovernanceKnowledgeGraph = _cog_mod.GovernanceKnowledgeGraph
    GraphSimilaritySearch = _cog_mod.GraphSimilaritySearch
    IncrementalContextUpdater = _cog_mod.IncrementalContextUpdater
    LongContextManager = _cog_mod.LongContextManager
    MultiAgentPlanner = _cog_mod.MultiAgentPlanner
    MultiTurnReasoner = _cog_mod.MultiTurnReasoner
    PlanStep = _cog_mod.PlanStep
    PlanVerifier = _cog_mod.PlanVerifier
    PolicyGraphExtractor = _cog_mod.PolicyGraphExtractor
    TaskDecomposer = _cog_mod.TaskDecomposer

    CognitiveEdgeType = _cog_mod.EdgeType
    CognitiveGraphEdge = _cog_mod.GraphEdge
    CognitiveGraphNode = _cog_mod.GraphNode
    CognitiveNodeType = _cog_mod.NodeType

    COGNITIVE_AVAILABLE = True
except (ImportError, AttributeError):
    COGNITIVE_AVAILABLE = False
    AgentCapability = object  # type: ignore[assignment, misc]
    CapabilityMatcher = object  # type: ignore[assignment, misc]
    ContextChunk = object  # type: ignore[assignment, misc]
    ContextWindow = object  # type: ignore[assignment, misc]
    CognitiveEdgeType = object  # type: ignore[assignment, misc]
    ExecutionPlan = object  # type: ignore[assignment, misc]
    GovernanceKnowledgeGraph = object  # type: ignore[assignment, misc]
    CognitiveGraphEdge = object  # type: ignore[assignment, misc]
    CognitiveGraphNode = object  # type: ignore[assignment, misc]
    GraphSimilaritySearch = object  # type: ignore[assignment, misc]
    IncrementalContextUpdater = object  # type: ignore[assignment, misc]
    LongContextManager = object  # type: ignore[assignment, misc]
    MultiAgentPlanner = object  # type: ignore[assignment, misc]
    MultiTurnReasoner = object  # type: ignore[assignment, misc]
    CognitiveNodeType = object  # type: ignore[assignment, misc]
    PlanStep = object  # type: ignore[assignment, misc]
    PlanVerifier = object  # type: ignore[assignment, misc]
    PolicyGraphExtractor = object  # type: ignore[assignment, misc]
    TaskDecomposer = object  # type: ignore[assignment, misc]

_EXT_ALL = [
    "COGNITIVE_AVAILABLE",
    "AgentCapability",
    "CapabilityMatcher",
    "ContextChunk",
    "ContextWindow",
    "CognitiveEdgeType",
    "ExecutionPlan",
    "GovernanceKnowledgeGraph",
    "CognitiveGraphEdge",
    "CognitiveGraphNode",
    "GraphSimilaritySearch",
    "IncrementalContextUpdater",
    "LongContextManager",
    "MultiAgentPlanner",
    "MultiTurnReasoner",
    "CognitiveNodeType",
    "PlanStep",
    "PlanVerifier",
    "PolicyGraphExtractor",
    "TaskDecomposer",
]


_EXT_ALL = [
    "COGNITIVE_AVAILABLE",
    "AgentCapability",
    "CapabilityMatcher",
    "ContextChunk",
    "ContextWindow",
    "CognitiveEdgeType",
    "ExecutionPlan",
    "GovernanceKnowledgeGraph",
    "CognitiveGraphEdge",
    "CognitiveGraphNode",
    "GraphSimilaritySearch",
    "IncrementalContextUpdater",
    "LongContextManager",
    "MultiAgentPlanner",
    "MultiTurnReasoner",
    "CognitiveNodeType",
    "PlanStep",
    "PlanVerifier",
    "PolicyGraphExtractor",
    "TaskDecomposer",
]
