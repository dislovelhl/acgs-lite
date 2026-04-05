"""ACGS deliberation compatibility package.

This package is the first extraction target from ``enhanced_agent_bus``.
For now it re-exports the stable deliberation surface from the existing
``enhanced_agent_bus.deliberation_layer`` package so new imports can start
moving without forcing an immediate code move.
"""

from enhanced_agent_bus.deliberation_layer import (
    REDIS_AVAILABLE,
    DeliberationQueue,
    DeliberationTask,
    Election,
    EventDrivenVoteCollector,
    GraphRAGContextEnricher,
    RedisDeliberationQueue,
    RedisVotingSystem,
    Vote,
    VoteEvent,
    VoteSession,
    VotingService,
    VotingStrategy,
    calculate_message_impact,
    get_impact_scorer,
    get_redis_deliberation_queue,
    get_redis_voting_system,
    get_vote_collector,
    multi_approver,
    reset_vote_collector,
)
from enhanced_agent_bus.deliberation_layer.integration import DeliberationLayer

__all__ = [
    "REDIS_AVAILABLE",
    "DeliberationLayer",
    "DeliberationQueue",
    "DeliberationTask",
    "Election",
    "EventDrivenVoteCollector",
    "GraphRAGContextEnricher",
    "RedisDeliberationQueue",
    "RedisVotingSystem",
    "Vote",
    "VoteEvent",
    "VoteSession",
    "VotingService",
    "VotingStrategy",
    "calculate_message_impact",
    "get_impact_scorer",
    "get_redis_deliberation_queue",
    "get_redis_voting_system",
    "get_vote_collector",
    "multi_approver",
    "reset_vote_collector",
]
