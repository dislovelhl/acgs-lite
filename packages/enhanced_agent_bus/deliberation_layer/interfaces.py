"""
ACGS-2 Deliberation Layer - Interfaces
Constitutional Hash: cdd01ef066bc6cf2

Protocol definitions for dependency injection in the deliberation layer.
"""

from collections.abc import Callable
from importlib import import_module
from typing import (
    TYPE_CHECKING,
    Protocol,
    TypeAlias,
    runtime_checkable,
)

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import (
        JSONDict,
        JSONValue,
    )  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONValue = object  # type: ignore[misc,assignment]


def _load_guard_models() -> tuple[object, object, object]:
    """Load guard result models from available package paths."""
    candidates = (
        "enhanced_agent_bus.deliberation_layer.opa_guard_models",
        "enhanced_agent_bus.deliberation_layer.opa_guard_models",
        ".opa_guard_models",
    )
    for candidate in candidates:
        try:
            module = import_module(candidate, package=__package__)
            return (
                module.GuardResult,
                module.ReviewResult,
                module.SignatureResult,
            )
        except (ImportError, AttributeError):
            continue
    return object, object, object


def _load_agent_message() -> object:
    """Load AgentMessage model from available package paths."""
    candidates = (
        "enhanced_agent_bus.models",
        "enhanced_agent_bus.models",
        "..models",
    )
    for candidate in candidates:
        try:
            module = import_module(candidate, package=__package__)
            return module.AgentMessage
        except (ImportError, AttributeError):
            continue
    return object


if TYPE_CHECKING:
    from enhanced_agent_bus.deliberation_layer.opa_guard_models import (
        GuardResult,
        ReviewResult,
        SignatureResult,
    )
    from enhanced_agent_bus.models import AgentMessage
else:
    GuardResult, ReviewResult, SignatureResult = _load_guard_models()
    AgentMessage = _load_agent_message()


@runtime_checkable
class ImpactScorerProtocol(Protocol):
    """Protocol for impact scoring implementations.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def calculate_impact_score(self, content: JSONDict, context: JSONDict | None = None) -> float:
        """Calculate impact score for message content.

        Args:
            content: Message content to analyze
            context: Optional context (agent_id, tenant_id, etc.)

        Returns:
            Impact score between 0.0 and 1.0
        """
        ...


@runtime_checkable
class AdaptiveRouterProtocol(Protocol):
    """Protocol for adaptive routing implementations.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def route_message(
        self,
        message: AgentMessage,
        context: JSONDict | None = None,
    ) -> JSONDict:
        """Route a message based on impact assessment.

        Args:
            message: The message to route
            context: Optional routing context

        Returns:
            Routing decision with 'lane' key ('fast' or 'deliberation')
        """
        ...

    async def force_deliberation(self, message: AgentMessage, reason: str) -> JSONDict:
        """Force a message into deliberation.

        Args:
            message: The message to route
            reason: Reason for forcing deliberation

        Returns:
            Routing result
        """
        ...

    async def update_performance_feedback(
        self,
        message_id: str,
        actual_outcome: str,
        processing_time: float,
        feedback_score: float | None = None,
    ) -> None:
        """Update performance feedback for learning.

        Args:
            message_id: ID of the processed message
            actual_outcome: Actual outcome of processing
            processing_time: Time taken to process
            feedback_score: Optional feedback score
        """
        ...

    def get_routing_stats(self) -> JSONDict:
        """Get routing statistics.

        Returns:
            Dictionary of routing statistics
        """
        ...


@runtime_checkable
class DeliberationQueueProtocol(Protocol):
    """Protocol for deliberation queue implementations.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def enqueue_for_deliberation(
        self,
        message: AgentMessage,
        requires_human_review: bool = False,
        requires_multi_agent_vote: bool = False,
        timeout_seconds: int = 300,
    ) -> str:
        """Enqueue a message for deliberation.

        Args:
            message: The message to enqueue
            requires_human_review: Whether human review is required
            requires_multi_agent_vote: Whether multi-agent vote is required
            timeout_seconds: Timeout for deliberation

        Returns:
            Item ID for the enqueued message
        """
        ...

    async def submit_human_decision(
        self,
        item_id: str,
        reviewer: str,
        decision: JSONValue,
        reasoning: str,  # DeliberationStatus
    ) -> bool:
        """Submit a human decision for a deliberation item.

        Args:
            item_id: ID of the deliberation item
            reviewer: ID of the human reviewer
            decision: The decision made
            reasoning: Reasoning for the decision

        Returns:
            True if decision was submitted successfully
        """
        ...

    async def submit_agent_vote(
        self,
        item_id: str,
        agent_id: str,
        vote: JSONValue,  # VoteType
        reasoning: str,
        confidence: float = 1.0,
    ) -> bool:
        """Submit an agent vote for a deliberation item.

        Args:
            item_id: ID of the deliberation item
            agent_id: ID of the voting agent
            vote: The vote
            reasoning: Reasoning for the vote
            confidence: Confidence level

        Returns:
            True if vote was submitted successfully
        """
        ...

    def get_item_details(self, item_id: str) -> JSONDict | None:
        """Get details of a deliberation item.

        Args:
            item_id: ID of the deliberation item

        Returns:
            Item details or None if not found
        """
        ...

    def get_queue_status(self) -> JSONDict:
        """Get queue status.

        Returns:
            Dictionary with queue stats, queue_size, processing_count
        """
        ...


@runtime_checkable
class LLMAssistantProtocol(Protocol):
    """Protocol for LLM assistant implementations.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def analyze_deliberation_trends(self, history: list[JSONDict]) -> JSONDict:
        """Analyze deliberation trends.

        Args:
            history: Historical deliberation data

        Returns:
            Analysis results
        """
        ...


@runtime_checkable
class RedisQueueProtocol(Protocol):
    """Protocol for Redis queue implementations.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def connect(self) -> bool:
        """Connect to Redis."""
        ...

    async def close(self) -> None:
        """Close the Redis connection."""
        ...

    async def enqueue_deliberation_item(
        self, message: AgentMessage, item_id: str, metadata: JSONDict | None = None
    ) -> bool:
        """Enqueue a deliberation item in Redis.

        Args:
            message: The message to enqueue
            item_id: ID of the deliberation item
            metadata: Optional metadata

        Returns:
            True if item was enqueued successfully
        """
        ...

    async def get_stream_info(self) -> JSONDict:
        """Get stream information.

        Returns:
            Stream info dictionary
        """
        ...


@runtime_checkable
class RedisVotingProtocol(Protocol):
    """Protocol for Redis voting implementations.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def connect(self) -> bool:
        """Connect to Redis."""
        ...

    async def close(self) -> None:
        """Close the Redis connection."""
        ...

    async def submit_vote(
        self, item_id: str, agent_id: str, vote: str, reasoning: str, confidence: float = 1.0
    ) -> bool:
        """Submit a vote.

        Args:
            item_id: ID of the deliberation item
            agent_id: ID of the voting agent
            vote: The vote
            reasoning: Reasoning for the vote
            confidence: Confidence level

        Returns:
            True if vote was submitted successfully
        """
        ...


@runtime_checkable
class OPAGuardProtocol(Protocol):
    """Protocol for OPA Guard implementations.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def initialize(self) -> None:
        """Initialize the OPA Guard."""
        ...

    async def close(self) -> None:
        """Close the OPA Guard."""
        ...

    async def verify_action(
        self, agent_id: str, action: JSONDict, context: JSONDict | None = None
    ) -> GuardResult:
        """Verify an action with OPA Guard.

        Args:
            agent_id: ID of the agent performing the action
            action: Action details
            context: Additional context

        Returns:
            GuardResult with verification outcome
        """
        ...

    async def collect_signatures(
        self,
        decision_id: str,
        required_signers: list[str],
        threshold: float = 1.0,
        timeout: int = 300,
    ) -> SignatureResult:
        """Collect multi-signatures for a decision.

        Args:
            decision_id: Unique ID for the decision
            required_signers: list of required signer IDs
            threshold: Percentage of signatures required
            timeout: Timeout in seconds

        Returns:
            SignatureResult
        """
        ...

    async def submit_signature(
        self, decision_id: str, signer_id: str, reasoning: str = "", confidence: float = 1.0
    ) -> bool:
        """Submit a signature for a pending decision."""
        ...

    async def submit_for_review(
        self,
        decision: JSONDict,
        critic_agents: list[str],
        review_types: list[str] | None = None,
        timeout: int = 300,
    ) -> ReviewResult:
        """Submit a decision for critic agent review."""
        ...

    async def submit_review(
        self,
        decision_id: str,
        critic_id: str,
        verdict: str,
        reasoning: str = "",
        concerns: list[str] | None = None,
        recommendations: list[str] | None = None,
        confidence: float = 1.0,
    ) -> bool:
        """Submit a critic review for a pending decision."""
        ...

    def register_critic_agent(
        self,
        critic_id: str,
        review_types: list[str],
        callback: Callable | None = None,
        metadata: JSONDict | None = None,
    ) -> None:
        """Register a critic agent for reviews."""
        ...

    def unregister_critic_agent(self, critic_id: str) -> None:
        """Unregister a critic agent."""
        ...

    def get_stats(self) -> JSONDict:
        """Get OPA Guard statistics."""
        ...

    def get_audit_log(
        self, limit: int = 100, offset: int = 0, agent_id: str | None = None
    ) -> list[JSONDict]:
        """Get audit log entries."""
        ...


__all__ = [
    "CONSTITUTIONAL_HASH",
    "AdaptiveRouterProtocol",
    "DeliberationQueueProtocol",
    "ImpactScorerProtocol",
    "LLMAssistantProtocol",
    "OPAGuardProtocol",
    "RedisQueueProtocol",
    "RedisVotingProtocol",
]
