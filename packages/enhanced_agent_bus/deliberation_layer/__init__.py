"""
ACGS-2 Deliberation Layer
Constitutional Hash: 608508a9bd224290

High-performance deliberation layer with:
- ML-powered impact scoring (ONNX/PyTorch with fallback cascade)
- Event-driven vote collection via Redis pub/sub
- Multi-stakeholder consensus with weighted voting
- Enterprise-scale support (100+ concurrent sessions, >6000 RPS)
"""

import sys

from . import integration, multi_approver
from .deliberation_queue import DeliberationQueue, DeliberationTask
from .graphrag_integration import GraphRAGContextEnricher
from .redis_integration import (
    REDIS_AVAILABLE,
    RedisDeliberationQueue,
    RedisVotingSystem,
    get_redis_deliberation_queue,
    get_redis_voting_system,
)
from .vote_collector import (
    EventDrivenVoteCollector,
    VoteEvent,
    VoteSession,
    get_vote_collector,
    reset_vote_collector,
)
from .voting_service import Election, Vote, VotingService, VotingStrategy

# Ensure module aliasing across package import paths
_module = sys.modules.get(__name__)
if _module is not None:
    sys.modules.setdefault("enhanced_agent_bus.deliberation_layer", _module)
    sys.modules.setdefault("enhanced_agent_bus.deliberation_layer", _module)
    sys.modules.setdefault("core.enhanced_agent_bus.deliberation_layer", _module)
    sys.modules.setdefault("enhanced_agent_bus.deliberation_layer.integration", integration)
    sys.modules.setdefault("enhanced_agent_bus.deliberation_layer.integration", integration)
    sys.modules.setdefault("core.enhanced_agent_bus.deliberation_layer.integration", integration)

# Lazy import for impact_scorer - requires numpy (optional ml dependency)
_impact_scorer_module = None


def _get_impact_scorer_module():
    """Lazy load impact_scorer module to avoid numpy import errors."""
    global _impact_scorer_module
    if _impact_scorer_module is None:
        try:
            from . import impact_scorer as _module

            _impact_scorer_module = _module
        except ImportError as e:
            raise ImportError(
                f"impact_scorer requires numpy. Install with: pip install enhanced-agent-bus[ml]. Error: {e}"
            ) from e
    return _impact_scorer_module


def __getattr__(name):
    """Lazy attribute access for impact_scorer exports."""
    if name in ("ImpactScorer", "calculate_message_impact", "get_impact_scorer"):
        module = _get_impact_scorer_module()
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Redis Integration
    "REDIS_AVAILABLE",
    # Deliberation Queue
    "DeliberationQueue",
    "DeliberationTask",
    "Election",
    "EventDrivenVoteCollector",
    # Impact Scorer (lazy loaded)
    "ImpactScorer",
    "RedisDeliberationQueue",
    "RedisVotingSystem",
    "Vote",
    # Event-Driven Vote Collector
    "VoteEvent",
    "VoteSession",
    # Voting Service
    "VotingService",
    "VotingStrategy",
    "calculate_message_impact",
    "get_impact_scorer",
    "get_redis_deliberation_queue",
    "get_redis_voting_system",
    "get_vote_collector",
    # Multi-approver workflow
    "multi_approver",
    "reset_vote_collector",
    # GraphRAG context enrichment
    "GraphRAGContextEnricher",
]
