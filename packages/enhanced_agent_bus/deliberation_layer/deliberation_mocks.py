"""
ACGS-2 Deliberation Layer - Mock Components
Mock implementations for testing and fallback scenarios.
Constitutional Hash: 608508a9bd224290

Provides fallback implementations when actual dependencies are unavailable,
allowing the deliberation layer to function in isolated testing or degraded mode.
"""

import sys
import uuid
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import cast

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

# type-safe global storage for mocks across module reloads
# Using getattr/setattr to avoid mypy attr-defined errors on sys module
_MOCK_STORAGE_KEY = "_ACGS_MOCK_STORAGE"
if not hasattr(sys.modules[__name__], _MOCK_STORAGE_KEY):
    _storage: JSONDict = {"tasks": {}, "stats": {}}
    setattr(sys.modules[__name__], _MOCK_STORAGE_KEY, _storage)
MOCK_STORAGE: JSONDict = cast(JSONDict, getattr(sys.modules[__name__], _MOCK_STORAGE_KEY))


class MockMagicMock:
    """Minimal MagicMock replacement when unittest.mock unavailable."""

    def __init__(self, *_args, **_kwargs):
        pass

    def __call__(self, *_args, **_kwargs):
        return self

    def __getattr__(self, name):
        return self


# Try to import real MagicMock, fall back to minimal implementation
try:
    from unittest.mock import AsyncMock, MagicMock
except ImportError:
    MagicMock = MockMagicMock  # type: ignore[misc, assignment]
    AsyncMock = MockMagicMock  # type: ignore[misc, assignment]


class MockDeliberationStatus(Enum):
    """Mock DeliberationStatus enum for fallback scenarios."""

    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    CONSENSUS_REACHED = "consensus_reached"


class MockVoteType(Enum):
    """Mock VoteType enum for fallback scenarios."""

    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


class MockItem:
    """Mock deliberation item for queue operations."""

    def __init__(self):
        self.current_votes = []
        self.status = "pending"
        self.item_id = None
        self.task_id = None
        self.message = None
        self.created_at = datetime.now(UTC)


class MockVote:
    """Mock vote for deliberation voting."""

    def __init__(self):
        self.vote = None
        self.agent_id = None


class MockComponent:
    """
    Mock component for testing deliberation layer dependencies.

    Provides sensible default behavior for all expected methods,
    allowing tests to run without real implementations.
    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, *_args, **_kwargs):
        self.queue = MOCK_STORAGE["tasks"]
        self.tasks = self.queue
        self.stats = MOCK_STORAGE["stats"] or {
            "total_queued": 0,
            "approved": 0,
            "rejected": 0,
            "timed_out": 0,
            "consensus_reached": 0,
            "avg_processing_time": 0.0,
        }
        MOCK_STORAGE["stats"] = self.stats
        self.processing_tasks = []

    def __getattr__(self, name):
        """Dynamic attribute handler for async mock methods."""

        # Synchronous getter methods
        if name.startswith("get_"):
            return self._create_getter_method(name)

        # All other methods are async
        return self._create_async_mock(name)

    def _create_getter_method(self, name: str):
        """Create synchronous getter methods."""
        getter_methods = {
            "get_routing_stats": lambda *_args, **_kwargs: {},
            "get_queue_status": lambda *_args, **_kwargs: {
                "stats": self.stats,
                "queue_size": len(self.queue),
                "processing_count": 0,
            },
            "get_stats": lambda *_args, **_kwargs: {},
            "get_task": lambda tid: self.queue.get(tid),
        }

        return getter_methods.get(name, lambda *_args, **_kwargs: None)

    def _create_async_mock(self, name: str):
        """Create async mock methods."""

        async def async_mock(*args, **kwargs):
            return self._handle_async_method(name, args, kwargs)

        return async_mock

    def _handle_async_method(self, name: str, args: tuple, kwargs: dict):
        """Handle async method calls with simplified routing."""

        def get_arg(idx, key, default=None):
            if len(args) > idx:
                return args[idx]
            return kwargs.get(key, default)

        # Route to specific handlers
        if name in ["route_message", "route"]:
            return self._mock_routing_methods(get_arg)

        if name in ["enqueue_for_deliberation", "enqueue"]:
            return self._mock_queue_enqueue(get_arg)

        if name in ["submit_agent_vote", "submit_human_decision"]:
            return self._mock_voting_methods(name, get_arg)

        if name in ["force_deliberation", "process_message"]:
            return self._mock_processing_methods(name, get_arg)

        if name.startswith("submit_") or name.startswith("resolve_"):
            return True

        return {}

    def _mock_routing_methods(self, get_arg):
        """Handle routing method mocks."""
        msg = get_arg(0, "message")
        score = getattr(msg, "impact_score", 0.0)
        lane = "deliberation" if (score and score >= 0.5) else "fast"
        return {"lane": lane, "decision": "mock", "status": "routed"}

    def _mock_queue_enqueue(self, get_arg):
        """Handle queue enqueue method mocks."""
        tid = str(uuid.uuid4())
        item = MockItem()
        item.item_id = tid
        item.task_id = tid
        item.message = get_arg(0, "message")
        self.queue[tid] = item
        return tid

    def _mock_voting_methods(self, name: str, get_arg):
        """Handle voting method mocks."""
        tid = get_arg(0, "item_id")
        if tid not in self.queue:
            return False

        if name == "submit_agent_vote":
            vote = MockVote()
            vote.vote = get_arg(2, "vote")
            vote.agent_id = get_arg(1, "agent_id")
            self.queue[tid].current_votes.append(vote)
        elif name == "submit_human_decision":
            self.queue[tid].status = get_arg(2, "decision")

        return True

    def _mock_processing_methods(self, name: str, get_arg):
        """Handle processing method mocks."""
        if name == "process_message":
            return {
                "success": True,
                "lane": "fast",
                "status": "delivered",
                "processing_time": 0.1,
            }
        elif name == "force_deliberation":
            return {
                "lane": "deliberation",
                "forced": True,
                "force_reason": get_arg(1, "reason", "manual"),
            }
        return {}

    # Explicit method implementations for common operations
    def get_routing_stats(self) -> JSONDict:
        return {}

    def get_queue_status(self) -> JSONDict:
        return {"stats": self.stats, "queue_size": len(self.queue), "processing_count": 0}

    def get_stats(self) -> JSONDict:
        return {}

    def get_task(self, task_id: str) -> MockItem | None:
        return cast(MockItem | None, self.queue.get(task_id))

    async def initialize(self):
        """Initialize the mock component."""
        pass

    async def close(self):
        """Close the mock component."""
        pass

    def set_impact_threshold(self, threshold: float):
        """set impact threshold (no-op for mock)."""
        pass


# Factory functions for creating mock instances
def create_mock_impact_scorer(*_args, **_kwargs) -> MockComponent:
    """Create a mock impact scorer."""
    return MockComponent()


def create_mock_adaptive_router(*_args, **_kwargs) -> MockComponent:
    """Create a mock adaptive router."""
    return MockComponent()


def create_mock_deliberation_queue(*_args, **_kwargs) -> MockComponent:
    """Create a mock deliberation queue."""
    return MockComponent()


def create_mock_llm_assistant(*_args, **_kwargs) -> MockComponent:
    """Create a mock LLM assistant."""
    return MockComponent()


def create_mock_redis_queue(*_args, **_kwargs) -> MockComponent:
    """Create a mock Redis queue."""
    return MockComponent()


def create_mock_redis_voting(*_args, **_kwargs) -> MockComponent:
    """Create a mock Redis voting system."""
    return MockComponent()


def create_mock_opa_guard(*_args, **_kwargs) -> MockComponent:
    """Create a mock OPA guard."""
    return MockComponent()


def mock_calculate_message_impact(*_args, **_kwargs) -> float:
    """Mock impact calculation returning 0.0."""
    return 0.0


__all__ = [
    "MOCK_STORAGE",
    "AsyncMock",
    "MagicMock",
    "MockComponent",
    "MockDeliberationStatus",
    "MockItem",
    "MockVote",
    "MockVoteType",
    "create_mock_adaptive_router",
    "create_mock_deliberation_queue",
    "create_mock_impact_scorer",
    "create_mock_llm_assistant",
    "create_mock_opa_guard",
    "create_mock_redis_queue",
    "create_mock_redis_voting",
    "mock_calculate_message_impact",
]
