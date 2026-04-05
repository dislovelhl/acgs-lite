"""
ACGS-2 AI Assistant - Agent Bus Integration
Constitutional Hash: 608508a9bd224290

Integration layer between AI Assistant and the Enhanced Agent Bus.
Handles constitutional validation, message routing, and governance.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from typing import TypeAlias

# Policy imports
from enhanced_agent_bus._compat.policy.models import PolicySpecification, VerificationStatus
from enhanced_agent_bus._compat.policy.unified_generator import UnifiedVerifiedPolicyGenerator
from enhanced_agent_bus.observability.structured_logging import get_logger

from .context import ConversationContext
from .dialog import ActionType, DialogAction
from .nlu import NLUResult

# Audit imports
try:
    import importlib

    _m = importlib.import_module("src.core.services.audit_service.core.audit_ledger")
    get_audit_ledger = getattr(_m, "get_audit_ledger", None)
except ImportError:
    get_audit_ledger = None

# Import centralized constitutional hash with fallback
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        JSONValue,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONValue = object  # type: ignore[misc,assignment]

# Import from parent package with fallback
try:
    from enhanced_agent_bus.exceptions import (
        ConstitutionalValidationError,
        MessageValidationError,
    )
    from enhanced_agent_bus.models import AgentMessage, MessageType, Priority
    from enhanced_agent_bus.validators import (
        ValidationResult,
        validate_constitutional_hash,
    )

    AGENT_BUS_AVAILABLE = True
except ImportError:
    AGENT_BUS_AVAILABLE = False
    AgentMessage = object  # type: ignore[assignment]
    MessageType = object  # type: ignore[assignment]
    Priority = object  # type: ignore[assignment]
    ValidationResult = object  # type: ignore[assignment]

logger = get_logger(__name__)
_AI_ASSISTANT_INTEGRATION_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


@dataclass
class IntegrationConfig:
    """Configuration for Agent Bus integration."""

    agent_id: str = "ai_assistant"
    tenant_id: str | None = None
    enable_governance: bool = True
    governance_threshold: float = 0.8
    enable_audit: bool = True
    enable_metering: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class GovernanceDecision:
    """Represents a decision made by the governance system."""

    is_allowed: bool
    reason: str
    policy_id: str | None = None
    verification_status: str | None = None
    confidence: float = 0.0
    metadata: JSONDict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> JSONDict:
        return {
            "is_allowed": self.is_allowed,
            "reason": self.reason,
            "policy_id": self.policy_id,
            "verification_status": self.verification_status,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class AgentBusIntegration:
    """
    Integration layer for the Enhanced Agent Bus.
    """

    def __init__(self, config: IntegrationConfig | None = None, agent_bus=None):
        self.config = config or IntegrationConfig()
        self.agent_bus = agent_bus
        self.handlers: dict[str, Callable] = {}
        self.policy_generator = UnifiedVerifiedPolicyGenerator()

    async def initialize(self) -> bool:
        """Initialize the integration layer."""
        if not AGENT_BUS_AVAILABLE:
            logger.warning("Agent Bus not available, running in mock mode")
            return False

        if not self.agent_bus:
            logger.error("Agent Bus instance not provided")
            return False

        logger.info(f"Initialized Agent Bus integration for {self.config.agent_id}")
        return True

    def register_handler(self, message_type: str, handler: Callable):
        """Register a handler for a specific message type."""
        self.handlers[message_type] = handler

    async def handle_incoming_message(self, message: AgentMessage) -> AgentMessage | None:
        """
        Handle an incoming message from the Agent Bus.
        """
        # Validate constitutional hash
        hash_result = validate_constitutional_hash(message.constitutional_hash)
        if not hash_result.is_valid:
            logger.error(f"Constitutional hash mismatch: {message.constitutional_hash}")
            if self.config.enable_governance:
                return self._create_error_response(
                    message, "Constitutional hash mismatch", ConstitutionalValidationError
                )

        # Route based on message type
        message_type_val = (
            message.message_type.value
            if hasattr(message.message_type, "value")
            else str(message.message_type)
        )
        handler = self.handlers.get(message_type_val)
        if handler:
            return await handler(message)  # type: ignore[no-any-return]

        logger.warning(f"No handler registered for message type: {message_type_val}")
        return None

    async def validate_user_message(
        self,
        message: AgentMessage,
        context: ConversationContext,
    ) -> ValidationResult:
        """
        Validate an incoming user message.

        Performs constitutional validation and content checks.
        """
        # Create validation result structure
        errors = []
        is_valid = True

        # Validate constitutional hash
        hash_result = validate_constitutional_hash(message.constitutional_hash)
        if not hash_result.is_valid:
            errors.append("Constitutional hash mismatch")
            is_valid = False

        # Extract user message content
        user_message_content = (
            message.content.get("text", "")
            if isinstance(message.content, dict)
            else str(message.content)
        )

        # Content validation (basic)
        if not user_message_content or not user_message_content.strip():
            errors.append("Empty message")
            is_valid = False

        # Length validation
        if len(user_message_content) > 10000:
            errors.append("Message too long")
            is_valid = False

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    async def process_nlu_result(
        self,
        nlu_result: NLUResult,
        context: ConversationContext,
    ) -> DialogAction:
        """
        Process NLU result and determine the next action.
        """
        # Constitutional check on intent and entities
        if self.config.enable_governance:
            governance_result = await self._check_governance(nlu_result, context)
            if not governance_result.get("is_allowed", True):
                return DialogAction(
                    action_type=ActionType.CLARIFY,
                    response_template=governance_result.get(
                        "reason", "Action blocked by governance"
                    ),
                    metadata={"governance_blocked": True},  # type: ignore[arg-type]
                )

        # Map intent to action
        intent = nlu_result.primary_intent.name if nlu_result.primary_intent else "unknown"
        if intent == "help":
            return DialogAction(
                action_type=ActionType.RESPOND, response_template="How can I help you today?"
            )

        # Default action
        return DialogAction(
            action_type=ActionType.RESPOND, response_template="I'm processing your request."
        )

    async def send_message(
        self,
        to_agent: str,
        content: str | JSONDict,
        message_type: str = "command",
        priority: str = "medium",
        context: ConversationContext | None = None,
    ) -> JSONDict | None:
        """
        Send a message to another agent through the bus.

        Args:
            to_agent: Target agent ID
            content: Message content (string or dictionary)
            message_type: type of message (command, query, etc.)
            priority: Message priority (low, medium, high, critical)
            context: Optional conversation context

        Returns:
            Response from the target agent, or None if failed
        """
        if not AGENT_BUS_AVAILABLE or not self.agent_bus:
            logger.warning("Agent Bus not available for message sending")
            return None

        try:
            # Create agent message
            message_content = content if isinstance(content, dict) else {"text": content}
            message = AgentMessage(
                from_agent=self.config.agent_id,
                to_agent=to_agent,
                content=message_content,
                message_type=MessageType[message_type.upper()],
                priority=Priority[priority.upper()],
                tenant_id=self.config.tenant_id or "acgs-dev",
                constitutional_hash=self.config.constitutional_hash,
            )

            # Add context metadata if available
            if context:
                message.metadata = {
                    "session_id": context.session_id,
                    "user_id": context.user_id,
                    "conversation_state": (
                        context.conversation_state.value
                        if hasattr(context.conversation_state, "value")
                        else str(context.conversation_state)
                    ),
                }

            # Send through bus
            result = await self.agent_bus.send_message(message)

            return result.to_dict() if result and hasattr(result, "to_dict") else None

        except _AI_ASSISTANT_INTEGRATION_OPERATION_ERRORS as e:
            logger.error(f"Error sending message to {to_agent}: {e}")
            return None

    def _create_error_response(
        self,
        original_message: AgentMessage,
        reason: str,
        error_type: type,
    ) -> AgentMessage:
        """Create an error response message."""
        return AgentMessage(
            from_agent=self.config.agent_id,
            to_agent=original_message.from_agent,
            content={"error": reason, "type": error_type.__name__},
            message_type=MessageType.RESPONSE,
            priority=original_message.priority,
            conversation_id=original_message.conversation_id,
            constitutional_hash=self.config.constitutional_hash,
        )

    async def _check_governance(
        self,
        nlu_result: NLUResult,
        context: ConversationContext,
    ) -> JSONDict:
        """Perform governance check on intent and entities using unified policy generator."""
        if not self.config.enable_governance:
            return {"is_allowed": True}

        try:
            primary_intent = nlu_result.primary_intent
            intent_name = primary_intent.name if primary_intent else "unknown"

            # Create policy specification from NLU result
            spec = PolicySpecification(
                spec_id=f"gov_{uuid.uuid4().hex[:8]}",
                natural_language=f"Verify if intent '{intent_name}' is allowed for user {context.user_id}",
                context={
                    "user_id": context.user_id,
                    "session_id": context.session_id,
                    "entities": nlu_result.entities if hasattr(nlu_result, "entities") else [],
                },
            )

            # Generate verified policy
            policy = await self.policy_generator.generate_verified_policy(spec)

            # Check verification status
            is_allowed = policy.verification_status in (
                VerificationStatus.VERIFIED,
                VerificationStatus.PROVEN,
            )

            decision = GovernanceDecision(
                is_allowed=is_allowed,
                reason=(
                    "Action verified and proven correct"
                    if is_allowed
                    else "Formal verification failed"
                ),
                policy_id=policy.policy_id,
                confidence=policy.confidence_score,
                verification_status=policy.verification_status.value,
            )

            # Record to Audit Ledger if available for third-party auditing
            if get_audit_ledger:
                try:
                    ledger = await get_audit_ledger()
                    audit_vr = ValidationResult(
                        is_valid=is_allowed,
                        metadata={
                            "type": "governance_psv_verus",
                            "policy_id": policy.policy_id,
                            "verification_status": policy.verification_status.value,
                            "smt_log": policy.smt_formulation,
                            "user_id": context.user_id,
                            "intent": intent_name,
                        },
                    )
                    await ledger.add_validation_result(audit_vr)
                except _AI_ASSISTANT_INTEGRATION_OPERATION_ERRORS as audit_err:
                    logger.warning(f"Failed to record governance audit: {audit_err}")

            return decision.to_dict()
        except _AI_ASSISTANT_INTEGRATION_OPERATION_ERRORS as e:
            logger.error(f"Governance check failed: {e}")
            # Fail closed for safety in governance
            return {"is_allowed": False, "reason": f"Governance system error: {e!s}"}

    # Aliases for backwards compatibility
    async def validate_message(
        self,
        message: str,
        context: ConversationContext,
    ) -> ValidationResult:
        """Validate a user message string for backwards compatibility.

        Wraps the string in an AgentMessage for validation.
        """
        # Create a minimal AgentMessage from the string
        agent_message = AgentMessage(
            from_agent="user",
            to_agent=self.config.agent_id,
            content={"text": message},
            message_type=MessageType.COMMAND,  # Use COMMAND for user input
            priority=Priority.NORMAL if hasattr(Priority, "NORMAL") else Priority.MEDIUM,  # type: ignore[attr-defined]
            constitutional_hash=self.config.constitutional_hash,
        )
        return await self.validate_user_message(agent_message, context)

    async def check_governance(
        self,
        nlu_result: NLUResult,
        context: ConversationContext,
    ) -> "GovernanceDecision":
        """Public alias for _check_governance.

        Returns a GovernanceDecision object for compatibility.
        """
        result = await self._check_governance(nlu_result, context)
        # Return as GovernanceDecision object
        return GovernanceDecision(
            is_allowed=result.get("is_allowed", False),
            reason=result.get("reason", ""),
            policy_id=result.get("policy_id"),
            confidence=result.get("confidence", 0.0),
            verification_status=result.get("verification_status"),
        )

    async def shutdown(self) -> None:
        """Shutdown the integration and cleanup resources."""
        logger.info("Shutting down AgentBusIntegration...")
        # Cleanup any resources if needed
        if hasattr(self, "_handlers"):
            self._handlers.clear()

    async def execute_task(
        self,
        task_type: str,
        parameters: JSONDict,
        context: ConversationContext | None = None,
    ) -> JSONDict:
        """Execute a task through the agent bus.

        Args:
            task_type: type of task to execute
            parameters: Task parameters
            context: Optional conversation context

        Returns:
            Task execution result
        """
        try:
            # Create a task message
            message = AgentMessage(
                from_agent=self.config.agent_id,
                to_agent="task_executor",
                content={"task_type": task_type, "parameters": parameters},
                message_type=MessageType.COMMAND,
                priority=Priority.NORMAL,
                constitutional_hash=self.config.constitutional_hash,
            )

            # Handle the task through the bus
            result = await self.handle_incoming_message(message)

            if result:
                return {"success": True, "result": result.content}
            return {"success": False, "error": "Task execution failed"}

        except _AI_ASSISTANT_INTEGRATION_OPERATION_ERRORS as e:
            logger.error(f"Task execution failed: {e}")
            return {"success": False, "error": str(e)}
