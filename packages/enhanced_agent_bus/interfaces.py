"""
ACGS-2 Enhanced Agent Bus - Protocol Interfaces
Constitutional Hash: cdd01ef066bc6cf2

Abstract protocol definitions for dependency injection support.
These protocols enable loose coupling and testability.
"""

from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    runtime_checkable,
)

if TYPE_CHECKING:
    from .validators import ValidationResult as ValidationResultType

from enhanced_agent_bus.bus_types import JSONDict, MetadataDict

try:
    from src.core.shared.types import AgentInfo
except ImportError:
    AgentInfo = JSONDict  # type: ignore[misc, assignment]

try:
    from .core_models import AgentMessage
except ImportError:
    from enhanced_agent_bus.core_models import AgentMessage  # type: ignore[import-untyped]


@runtime_checkable
class AgentRegistry(Protocol):
    """Protocol for agent registration and discovery.

    Implementations must provide thread-safe agent management.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def register(
        self,
        agent_id: str,
        capabilities: list[str] | None = None,
        metadata: MetadataDict | None = None,
    ) -> bool:
        """Register an agent with the bus.

        Args:
            agent_id: Unique identifier for the agent
            capabilities: Agent capabilities for routing decisions
            metadata: Additional agent metadata

        Returns:
            True if registration successful, False if agent already exists
        """
        ...

    async def unregister(self, agent_id: str) -> bool:
        """Unregister an agent from the bus.

        Args:
            agent_id: The agent to unregister

        Returns:
            True if unregistration successful, False if agent not found
        """
        ...

    async def get(self, agent_id: str) -> AgentInfo | None:
        """Get agent information by ID.

        Args:
            agent_id: The agent to look up

        Returns:
            Agent info dict or None if not found
        """
        ...

    async def list_agents(self) -> list[str]:
        """List all registered agent IDs.

        Returns:
            List of registered agent IDs
        """
        ...

    async def exists(self, agent_id: str) -> bool:
        """Check if an agent is registered.

        Args:
            agent_id: The agent to check

        Returns:
            True if agent is registered
        """
        ...

    async def update_metadata(self, agent_id: str, metadata: MetadataDict) -> bool:
        """Update agent metadata.

        Args:
            agent_id: The agent to update
            metadata: New metadata to merge

        Returns:
            True if update successful
        """
        ...


@runtime_checkable
class MessageRouter(Protocol):
    """Protocol for message routing decisions.

    Implementations determine how messages are delivered to agents.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def route(self, message: AgentMessage, registry: AgentRegistry) -> str | None:
        """Determine the target agent for a message.

        Args:
            message: The message to route
            registry: Agent registry for lookups

        Returns:
            Target agent ID or None if no suitable target
        """
        ...

    async def broadcast(
        self, message: AgentMessage, registry: AgentRegistry, exclude: list[str] | None = None
    ) -> list[str]:
        """Get list of agents to broadcast a message to.

        Args:
            message: The message to broadcast
            registry: Agent registry for lookups
            exclude: Agent IDs to exclude from broadcast

        Returns:
            List of target agent IDs
        """
        ...


@runtime_checkable
class ValidationStrategy(Protocol):
    """Protocol for message validation.

    Implementations define how messages are validated before processing.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def validate(self, message: AgentMessage) -> tuple[bool, str | None]:
        """Validate a message.

        Args:
            message: The message to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        ...


@runtime_checkable
class ProcessingStrategy(Protocol):
    """Protocol for message processing strategies.

    Implementations define how messages are validated and processed.
    Each strategy handles a different processing mode (Rust, Dynamic Policy, Python).
    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def process(
        self, message: AgentMessage, handlers: dict[object, list[Callable]]
    ) -> "ValidationResultType":  # Returns ValidationResult
        """Process a message through validation and handlers.

        Args:
            message: The message to process
            handlers: Dict mapping message types to handler lists

        Returns:
            ValidationResult indicating success/failure with details
        """
        ...

    def is_available(self) -> bool:
        """Check if this strategy is available for use.

        Returns:
            True if the strategy can be used (e.g., Rust backend loaded)
        """
        ...

    def get_name(self) -> str:
        """Get the strategy name for logging/metrics.

        Returns:
            Strategy identifier string
        """
        ...


@runtime_checkable
class MessageHandler(Protocol):
    """Protocol for message handlers.

    Implementations process messages for specific message types.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def handle(self, message: AgentMessage) -> AgentMessage | None:
        """Handle a message.

        Args:
            message: The message to handle

        Returns:
            Response message or None
        """
        ...

    def can_handle(self, message: AgentMessage) -> bool:
        """Check if this handler can process the message.

        Args:
            message: The message to check

        Returns:
            True if handler can process this message
        """
        ...


@runtime_checkable
class MetricsCollector(Protocol):
    """Protocol for metrics collection.

    Implementations gather performance and operational metrics.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    def record_message_processed(
        self, message_type: str, duration_ms: float, success: bool
    ) -> None:
        """Record a processed message metric.

        Args:
            message_type: Type of message processed
            duration_ms: Processing duration in milliseconds
            success: Whether processing was successful
        """
        ...

    def record_agent_registered(self, agent_id: str) -> None:
        """Record an agent registration.

        Args:
            agent_id: The registered agent ID
        """
        ...

    def record_agent_unregistered(self, agent_id: str) -> None:
        """Record an agent unregistration.

        Args:
            agent_id: The unregistered agent ID
        """
        ...

    def get_metrics(self) -> JSONDict:
        """Get current metrics snapshot.

        Returns:
            Dict of metric names to values
        """
        ...


@runtime_checkable
class MessageProcessorProtocol(Protocol):
    """Protocol for message processing implementations.

    Implementations handle message validation and processing through the bus.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def process(self, message: AgentMessage) -> "ValidationResultType":
        """Process a message through validation and handlers.

        Args:
            message: The message to process

        Returns:
            ValidationResult indicating success/failure with details
        """
        ...


@runtime_checkable
class MACIRegistryProtocol(Protocol):
    """Protocol for MACI agent role registry.

    Implementations manage agent role assignments for constitutional governance.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    def register_agent(self, agent_id: str, role: str) -> bool:
        """Register an agent with a MACI role.

        Args:
            agent_id: Unique identifier for the agent
            role: MACI role (executive, legislative, judicial, etc.)

        Returns:
            True if registration successful
        """
        ...

    def get_role(self, agent_id: str) -> str | None:
        """Get the MACI role for an agent.

        Args:
            agent_id: The agent to look up

        Returns:
            Role name or None if not found
        """
        ...

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the MACI registry.

        Args:
            agent_id: The agent to unregister

        Returns:
            True if unregistration successful
        """
        ...


@runtime_checkable
class MACIEnforcerProtocol(Protocol):
    """Protocol for MACI action enforcement.

    Implementations enforce separation of powers in constitutional governance.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def validate_action(
        self,
        agent_id: str,
        action: str,
        target_output_id: str | None = None,
    ) -> JSONDict:
        """Validate whether an agent can perform an action.

        Args:
            agent_id: The agent attempting the action
            action: The action being attempted
            target_output_id: Optional target output for cross-role validation

        Returns:
            Dict with validation result and any violations
        """
        ...


# =============================================================================
# Infrastructure Protocols (Phase 2 Consolidation)
# Constitutional Hash: cdd01ef066bc6cf2
# =============================================================================


@runtime_checkable
class TransportProtocol(Protocol):
    """Protocol for message transport implementations.

    Enables swapping between in-process, Kafka, and other transports
    without changing bus logic. Constitutional Hash: cdd01ef066bc6cf2
    """

    async def start(self) -> None:
        """Start the transport layer."""
        ...

    async def stop(self) -> None:
        """Stop the transport layer."""
        ...

    async def send(self, message: AgentMessage, topic: str | None = None) -> bool:
        """Send a message through this transport.

        Args:
            message: The agent message to send
            topic: Optional topic/channel for routing

        Returns:
            True if message was accepted for delivery
        """
        ...

    async def subscribe(self, topic: str, handler: Callable[..., object]) -> None:
        """Subscribe to messages on a topic.

        Args:
            topic: Topic/channel to subscribe to
            handler: Async callable invoked for each message
        """
        ...


@runtime_checkable
class OrchestratorProtocol(Protocol):
    """Protocol for orchestrator lifecycle and health.

    All orchestrators should implement this for unified health aggregation
    and lifecycle management. Constitutional Hash: cdd01ef066bc6cf2
    """

    async def start(self) -> None:
        """Start the orchestrator."""
        ...

    async def stop(self) -> None:
        """Stop the orchestrator gracefully."""
        ...

    def get_status(self) -> JSONDict:
        """Get orchestrator health/status information.

        Returns:
            Dict with at minimum 'status' and 'constitutional_hash' keys
        """
        ...


@runtime_checkable
class CircuitBreakerProtocol(Protocol):
    """Protocol for circuit breaker implementations.

    Minimal interface covering state tracking and result recording.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def record_success(self) -> None:
        """Record a successful operation."""
        ...

    async def record_failure(
        self,
        error: Exception | None = None,
        error_type: str = "unknown",
    ) -> None:
        """Record a failed operation.

        Args:
            error: The exception that occurred
            error_type: Classification string for the error
        """
        ...

    async def can_execute(self) -> bool:
        """Check if the circuit allows execution.

        Returns:
            True if the circuit is closed or half-open
        """
        ...

    async def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        ...


try:
    from .deliberation_layer.interfaces import (
        AdaptiveRouterProtocol,
        DeliberationQueueProtocol,
        ImpactScorerProtocol,
        LLMAssistantProtocol,
        OPAGuardProtocol,
        RedisQueueProtocol,
        RedisVotingProtocol,
    )
except (ImportError, ValueError):
    try:
        from deliberation_layer.interfaces import (  # type: ignore[import-untyped]
            AdaptiveRouterProtocol,
            DeliberationQueueProtocol,
            ImpactScorerProtocol,
            LLMAssistantProtocol,
            OPAGuardProtocol,
            RedisQueueProtocol,
            RedisVotingProtocol,
        )
    except (ImportError, ValueError):
        ImpactScorerProtocol: object = object  # type: ignore[no-redef]
        AdaptiveRouterProtocol: object = object  # type: ignore[no-redef]
        DeliberationQueueProtocol: object = object  # type: ignore[no-redef]
        LLMAssistantProtocol: object = object  # type: ignore[no-redef]
        OPAGuardProtocol: object = object  # type: ignore[no-redef]
        RedisQueueProtocol: object = object  # type: ignore[no-redef]
        RedisVotingProtocol: object = object  # type: ignore[no-redef]

__all__ = [
    # Core Protocols
    "AgentRegistry",
    "CircuitBreakerProtocol",
    "ConstitutionalVerificationResultProtocol",
    "ConstitutionalVerifierProtocol",
    "ConstitutionalHashValidatorProtocol",
    "GovernanceDecisionValidatorProtocol",
    "MACIEnforcerProtocol",
    "MACIRegistryProtocol",
    "MessageHandler",
    "MessageProcessorProtocol",
    "MessageRouter",
    "MetricsCollector",
    "OPAClientProtocol",
    "OrchestratorProtocol",
    "PQCValidatorProtocol",
    "PolicyClientProtocol",
    # Validation Strategy Protocol Types
    "PolicyValidationResultProtocol",
    "ProcessingStrategy",
    "RustProcessorProtocol",
    # Infrastructure Protocols (Phase 2)
    "TransportProtocol",
    "ValidationResultProtocol",
    "ValidationStrategy",
]

# ============================================================================
# Validation Strategy Dependencies - Protocol Types
# Constitutional Hash: cdd01ef066bc6cf2
# ============================================================================


@runtime_checkable
class PolicyValidationResultProtocol(Protocol):
    """Protocol for policy validation results.

    Used by DynamicPolicyValidationStrategy for type safety.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    @property
    def is_valid(self) -> bool:
        """Whether the validation passed."""
        ...

    @property
    def errors(self) -> list[str]:
        """List of validation errors."""
        ...


@runtime_checkable
class PolicyClientProtocol(Protocol):
    """Protocol for dynamic policy clients.

    Used by DynamicPolicyValidationStrategy for type safety.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def validate_message_signature(
        self, message: AgentMessage
    ) -> PolicyValidationResultProtocol:
        """Validate a message signature against the policy server.

        Args:
            message: The agent message to validate

        Returns:
            PolicyValidationResultProtocol with is_valid and errors
        """
        ...


@runtime_checkable
class OPAClientProtocol(Protocol):
    """Protocol for OPA (Open Policy Agent) clients.

    Used by OPAValidationStrategy for type safety.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def validate_constitutional(self, message: JSONDict) -> "ValidationResultProtocol":
        """Validate a message against constitutional policies.

        Args:
            message: Message data as a dictionary

        Returns:
            ValidationResult with is_valid and errors
        """
        ...


@runtime_checkable
class ValidationResultProtocol(Protocol):
    """Protocol for validation results.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    @property
    def is_valid(self) -> bool:
        """Whether the validation passed."""
        ...

    @property
    def errors(self) -> list[str]:
        """List of validation errors."""
        ...


@runtime_checkable
class RustProcessorProtocol(Protocol):
    """Protocol for Rust validation processors.

    Used by RustValidationStrategy for type safety.
    Supports multiple validation method signatures.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    # At least one of these methods should be available
    # We use optional methods with hasattr checks in the strategy

    def validate(self, message: JSONDict) -> bool | JSONDict:
        """Synchronous validation method.

        Args:
            message: Message data as a dictionary

        Returns:
            bool or dict with is_valid key
        """
        ...


@runtime_checkable
class PQCValidatorProtocol(Protocol):
    """Protocol for Post-Quantum Cryptographic validators.

    Used by PQCValidationStrategy for type safety.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    def verify_governance_decision(
        self,
        decision: JSONDict,
        signature: object,  # PQCSignature type
        public_key: bytes,
    ) -> bool:
        """Verify a governance decision signature.

        Args:
            decision: Decision data dictionary
            signature: PQC signature object
            public_key: Public key bytes

        Returns:
            True if signature is valid
        """
        ...


@runtime_checkable
class ConstitutionalVerifierProtocol(Protocol):
    """Protocol for constitutional verifiers using Z3.

    Used by ConstitutionalValidationStrategy for type safety.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    async def verify_constitutional_compliance(
        self,
        action_data: JSONDict,
        context: JSONDict,
        session_id: str | None = None,
    ) -> "ConstitutionalVerificationResultProtocol":
        """Verify constitutional compliance of an action.

        Args:
            action_data: Action data dictionary
            context: Contextual information
            session_id: Optional session for per-session overrides

        Returns:
            Verification result with is_valid and failure_reason
        """
        ...


@runtime_checkable
class ConstitutionalVerificationResultProtocol(Protocol):
    """Protocol for constitutional verification results.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    @property
    def is_valid(self) -> bool:
        """Whether the verification passed."""
        ...

    @property
    def failure_reason(self) -> str | None:
        """Reason for verification failure, if any."""
        ...


@runtime_checkable
class ConstitutionalHashValidatorProtocol(Protocol):
    """Independent validator for constitutional hash checks (MACI: Validator role)."""

    async def validate_hash(
        self,
        *,
        provided_hash: str,
        expected_hash: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """Validate constitutional hash. Returns (is_valid, error_message)."""
        ...


@runtime_checkable
class GovernanceDecisionValidatorProtocol(Protocol):
    """Independent validator for governance decisions (MACI: Validator role)."""

    async def validate_decision(
        self,
        *,
        decision: dict[str, Any],
        context: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Validate a governance decision. Returns (is_valid, errors)."""
        ...


@runtime_checkable
class ApprovalsValidatorProtocol(Protocol):
    """Independent validator for approval requirements (MACI: Validator role)."""

    def validate_approvals(
        self,
        *,
        policy: Any,
        decisions: list[Any],
        approvers: dict[str, Any],
        requester_id: str,
    ) -> tuple[bool, str]:
        """Validate approval requirements. Returns (is_valid, reason)."""
        ...


@runtime_checkable
class RecommendationPlannerProtocol(Protocol):
    """Independent recommendation planner separated from verifier logic."""

    def generate_recommendations(
        self,
        *,
        judgment: dict[str, Any],
        decision: dict[str, Any],
    ) -> list[str]:
        """Generate remediation/recommendation steps from verification output."""
        ...


@runtime_checkable
class RoleMatrixValidatorProtocol(Protocol):
    """Independent validator for MACI role matrix integrity."""

    def validate(self, *, violations: list[str], strict_mode: bool) -> None:
        """Validate MACI role matrix or raise on strict-mode violations."""
        ...
