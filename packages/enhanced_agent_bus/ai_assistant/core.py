"""
ACGS-2 AI Assistant - Core Orchestrator
Constitutional Hash: 608508a9bd224290

Main orchestrator class that ties together all AI assistant components:
NLU, Dialog Management, Response Generation, and Agent Bus Integration.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Protocol, TypeAlias

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

from enhanced_agent_bus.observability.structured_logging import get_logger

from .context import ContextManager, ConversationContext, Message, MessageRole
from .dialog import ActionType, DialogAction, DialogManager
from .integration import AgentBusIntegration, IntegrationConfig
from .nlu import NLUEngine
from .response import ResponseConfig, ResponseGenerator, TemplateResponseGenerator

logger = get_logger(__name__)
_ASSISTANT_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class AssistantState(Enum):
    """States of the AI assistant."""

    INITIALIZED = "initialized"
    READY = "ready"
    PROCESSING = "processing"
    ERROR = "error"
    SHUTDOWN = "shutdown"


@dataclass
class AssistantConfig:
    """Configuration for the AI Assistant."""

    name: str = "ACGS-2 Assistant"
    description: str = "Constitutional AI governance assistant"
    version: str = "1.0.0"
    max_conversation_turns: int = 100
    session_timeout_minutes: int = 30
    enable_learning: bool = False
    enable_governance: bool = True
    enable_metering: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH

    # Component configurations
    response_config: ResponseConfig | None = None
    integration_config: IntegrationConfig | None = None

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "description": self.description,
            "max_conversation_turns": self.max_conversation_turns,
            "session_timeout_minutes": self.session_timeout_minutes,
            "enable_learning": self.enable_learning,
            "enable_governance": self.enable_governance,
            "enable_metering": self.enable_metering,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class ProcessingResult:
    """Result of processing a user message."""

    success: bool
    response_text: str
    intent: str | None = None
    confidence: float = 0.0
    entities: JSONDict = field(default_factory=dict)
    action_taken: str | None = None
    governance_decision: JSONDict | None = None
    processing_time_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH
    metadata: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        return {
            "success": self.success,
            "response_text": self.response_text,
            "intent": self.intent,
            "confidence": self.confidence,
            "entities": self.entities,
            "action_taken": self.action_taken,
            "governance_decision": self.governance_decision,
            "processing_time_ms": self.processing_time_ms,
            "constitutional_hash": self.constitutional_hash,
            "metadata": self.metadata,
        }


class ConversationListener(Protocol):
    """Protocol for conversation event listeners."""

    async def on_message_received(
        self,
        context: ConversationContext,
        message: str,
    ) -> None:
        """Called when a message is received."""
        ...

    async def on_response_generated(
        self,
        context: ConversationContext,
        response: str,
        result: ProcessingResult,
    ) -> None:
        """Called when a response is generated."""
        ...

    async def on_error(
        self,
        context: ConversationContext,
        error: Exception,
    ) -> None:
        """Called when an error occurs."""
        ...


class AIAssistant:
    """
    Main AI Assistant orchestrator.

    Coordinates all components to provide a complete conversational AI experience:
    - NLU for understanding user intent
    - Dialog management for conversation flow
    - Response generation for natural replies
    - Agent Bus integration for governance and compliance

    Example usage:
        assistant = AIAssistant()
        await assistant.initialize()

        result = await assistant.process_message(
            user_id="user123",
            message="What is my order status?"
        )

        logger.info(result.response_text)

        await assistant.shutdown()
    """

    def __init__(
        self,
        config: AssistantConfig | None = None,
        nlu_engine: NLUEngine | None = None,
        dialog_manager: DialogManager | None = None,
        response_generator: ResponseGenerator | None = None,
        integration: AgentBusIntegration | None = None,
    ):
        """
        Initialize the AI Assistant.

        Args:
            config: Assistant configuration
            nlu_engine: Custom NLU engine (defaults to built-in)
            dialog_manager: Custom dialog manager (defaults to built-in)
            response_generator: Custom response generator (defaults to template-based)
            integration: Custom Agent Bus integration (defaults to built-in)
        """
        self.config = config or AssistantConfig()
        self._state = AssistantState.INITIALIZED

        # Initialize lightweight components
        self._response_generator = response_generator or self._create_default_response_generator()
        self._integration = integration or AgentBusIntegration(
            config=self.config.integration_config
        )

        # Lazy-loaded components (initialized in initialize() or on first access)
        self._nlu_engine = nlu_engine
        self._dialog_manager = dialog_manager

        # Context management
        self._context_manager = ContextManager()
        self._active_sessions: dict[str, ConversationContext] = {}

        # Event listeners
        self._listeners: list[ConversationListener] = []

        # Metrics
        self._total_messages_processed = 0
        self._total_errors = 0
        self._start_time: datetime | None = None

    def _create_default_response_generator(self) -> ResponseGenerator:
        """Create the default response generator."""
        response_config = self.config.response_config or ResponseConfig()
        return TemplateResponseGenerator(config=response_config)

    @property
    def state(self) -> AssistantState:
        """Get current assistant state."""
        return self._state

    @property
    def is_ready(self) -> bool:
        """Check if assistant is ready to process messages."""
        return self._state == AssistantState.READY

    async def _ensure_components_loaded(self) -> None:
        """Lazy load heavy components if they haven't been initialized yet."""
        if self._nlu_engine is None:
            logger.info("Lazy loading NLU Engine...")
            try:
                from .nlu import NLUEngine

                self._nlu_engine = NLUEngine()
            except ImportError:
                logger.error("Failed to import NLUEngine for lazy loading")

        if self._dialog_manager is None:
            logger.info("Lazy loading Dialog Manager...")
            try:
                from .dialog import DialogManager

                self._dialog_manager = DialogManager()
            except ImportError:
                logger.error("Failed to import DialogManager for lazy loading")

    async def initialize(self) -> bool:
        """
        Initialize the AI Assistant.
        Does not eagerly load heavy components to maintain fast startup.
        """
        try:
            logger.info(f"Initializing AI Assistant: {self.config.name} (v{self.config.version})")

            # Initialize Agent Bus integration
            if self.config.enable_governance:
                await self._integration.initialize()

            # Trigger lazy loading of heavy components
            await self._ensure_components_loaded()

            self._state = AssistantState.READY
            self._start_time = datetime.now(UTC)

            logger.info("AI Assistant initialized successfully")
            return True

        except _ASSISTANT_OPERATION_ERRORS as e:
            logger.error(f"Failed to initialize AI Assistant: {e}")
            self._state = AssistantState.ERROR
            return False

    async def shutdown(self) -> None:
        """Shutdown the assistant and cleanup resources."""
        logger.info("Shutting down AI Assistant...")

        try:
            # Shutdown integration
            if self.config.enable_governance:
                await self._integration.shutdown()

            # Clear active sessions
            self._active_sessions.clear()

            self._state = AssistantState.SHUTDOWN
            logger.info("AI Assistant shutdown complete")

        except _ASSISTANT_OPERATION_ERRORS as e:
            logger.error(f"Error during shutdown: {e}")

    async def process_message(
        self,
        user_id: str,
        message: str,
        session_id: str | None = None,
        metadata: JSONDict | None = None,
    ) -> ProcessingResult:
        """
        Process a user message and generate a response.

        This is the main entry point for the assistant. It coordinates:
        1. Context management (get or create session)
        2. NLU processing (intent, entities, sentiment)
        3. Governance checks (if enabled)
        4. Dialog management (action selection)
        5. Response generation

        Args:
            user_id: Unique user identifier
            message: User's input message
            session_id: Optional session ID (auto-generated if not provided)
            metadata: Optional metadata to attach to the message

        Returns:
            ProcessingResult with response and metadata
        """
        if not self.is_ready:
            return ProcessingResult(
                success=False,
                response_text="I'm sorry, I'm not ready to help right now. Please try again later.",
                constitutional_hash=self.config.constitutional_hash,
            )

        start_time = datetime.now(UTC)
        self._state = AssistantState.PROCESSING

        try:
            # Ensure components are loaded (double-check pattern)
            await self._ensure_components_loaded()

            # Get or create conversation context
            context = await self._get_or_create_context(user_id, session_id)

            # Validate message (governance check)
            if self.config.enable_governance:
                validation = await self._integration.validate_message(message, context)
                if not validation.is_valid:
                    return ProcessingResult(
                        success=False,
                        response_text="I'm sorry, I couldn't process your message. "
                        "Please try rephrasing.",
                        constitutional_hash=self.config.constitutional_hash,
                        metadata={"validation_errors": validation.errors},
                    )

            # Notify listeners
            await self._notify_message_received(context, message)

            # Add user message to context
            user_message = Message(
                role=MessageRole.USER,
                content=message,
                metadata=metadata or {},
            )
            context.add_message(user_message)

            # NLU processing
            nlu_result = await self._nlu_engine.process(
                message,
                context={"entities": context.entities, "slots": context.slots},
            )

            # Dialog management
            dialog_result = await self._dialog_manager.process_turn(context, nlu_result)
            action = dialog_result.get("action")

            # Governance check for action
            governance_decision = None
            if self.config.enable_governance and action:
                governance_decision = await self._integration.check_governance(
                    action,
                    context,
                    nlu_result,  # type: ignore[call-arg]
                )

                if not governance_decision.is_allowed:
                    return ProcessingResult(
                        success=False,
                        response_text="I'm sorry, I can't perform that action right now.",
                        intent=(
                            nlu_result.primary_intent.name if nlu_result.primary_intent else None
                        ),
                        confidence=nlu_result.confidence,
                        governance_decision=governance_decision.to_dict(),
                        constitutional_hash=self.config.constitutional_hash,
                    )

            # Execute action if needed
            action_result = None
            if action and action.action_type == ActionType.EXECUTE_TASK:
                action_result = await self._execute_action(action, context)

            # Generate response
            response_data = {
                **nlu_result.to_dict(),
                "action_result": action_result,
                "dialog_result": dialog_result,
            }

            # Get intent name for response generation
            intent_name = nlu_result.primary_intent.name if nlu_result.primary_intent else "unknown"

            response_text = await self._response_generator.generate(
                intent_name,
                context,
                response_data,
            )

            # Add assistant response to context
            assistant_message = Message(
                role=MessageRole.ASSISTANT,
                content=response_text,
                metadata={
                    "intent": nlu_result.primary_intent,
                    "confidence": nlu_result.confidence,
                },
            )
            context.add_message(assistant_message)

            # Update context state
            context.last_activity = datetime.now(UTC)

            # Calculate processing time
            processing_time = (datetime.now(UTC) - start_time).total_seconds() * 1000

            # Create result
            result = ProcessingResult(
                success=True,
                response_text=response_text,
                intent=nlu_result.primary_intent.name if nlu_result.primary_intent else None,
                confidence=nlu_result.confidence,
                entities=(
                    nlu_result.entities
                    if isinstance(nlu_result.entities, dict)
                    else {e.type: e.value for e in nlu_result.entities}
                ),
                action_taken=action.action_type.value if action else None,
                governance_decision=governance_decision.to_dict() if governance_decision else None,
                processing_time_ms=processing_time,
                constitutional_hash=self.config.constitutional_hash,
                metadata={
                    "session_id": context.session_id,
                    "turn_count": len(context.messages) // 2,
                    "sentiment": nlu_result.sentiment,
                },
            )

            # Notify listeners
            await self._notify_response_generated(context, response_text, result)

            self._total_messages_processed += 1
            self._state = AssistantState.READY

            return result

        except _ASSISTANT_OPERATION_ERRORS as e:
            logger.error(f"Error processing message: {e}")
            self._total_errors += 1
            self._state = AssistantState.READY

            # Notify error listeners
            if "context" in locals():
                await self._notify_error(context, e)

            return ProcessingResult(
                success=False,
                response_text="I'm sorry, something went wrong. Please try again.",
                constitutional_hash=self.config.constitutional_hash,
                metadata={"error": str(e)},
            )

    async def _get_or_create_context(
        self,
        user_id: str,
        session_id: str | None = None,
    ) -> ConversationContext:
        """Get existing or create new conversation context."""
        # Generate session ID if not provided
        if not session_id:
            session_id = f"{user_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

        # Check for existing session
        if session_id in self._active_sessions:
            context = self._active_sessions[session_id]

            # Check if session expired
            session_age = (datetime.now(UTC) - context.last_activity).total_seconds() / 60
            if session_age > self.config.session_timeout_minutes:
                # Create new session
                del self._active_sessions[session_id]
            else:
                return context

        # Create new context
        context = ConversationContext(
            user_id=user_id,
            session_id=session_id,
            constitutional_hash=self.config.constitutional_hash,
        )

        self._active_sessions[session_id] = context
        return context

    async def _execute_action(
        self,
        action: DialogAction,
        context: ConversationContext,
    ) -> JSONDict | None:
        """Execute a dialog action."""
        if not action.parameters:
            return None

        task_type = action.parameters.get("task_type")
        if task_type and self.config.enable_governance:
            result = await self._integration.execute_task(
                task_type=task_type,
                parameters=action.parameters,
                context=context,
            )
            return result

        return None

    # Event listener methods
    def add_listener(self, listener: ConversationListener) -> None:
        """Add a conversation event listener."""
        self._listeners.append(listener)

    def remove_listener(self, listener: ConversationListener) -> None:
        """Remove a conversation event listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def _notify_message_received(
        self,
        context: ConversationContext,
        message: str,
    ) -> None:
        """Notify listeners of received message."""
        for listener in self._listeners:
            try:
                await listener.on_message_received(context, message)
            except _ASSISTANT_OPERATION_ERRORS as e:
                logger.warning(f"Listener error on message_received: {e}")

    async def _notify_response_generated(
        self,
        context: ConversationContext,
        response: str,
        result: ProcessingResult,
    ) -> None:
        """Notify listeners of generated response."""
        for listener in self._listeners:
            try:
                await listener.on_response_generated(context, response, result)
            except _ASSISTANT_OPERATION_ERRORS as e:
                logger.warning(f"Listener error on response_generated: {e}")

    async def _notify_error(
        self,
        context: ConversationContext,
        error: Exception,
    ) -> None:
        """Notify listeners of error."""
        for listener in self._listeners:
            try:
                await listener.on_error(context, error)
            except _ASSISTANT_OPERATION_ERRORS as e:
                logger.warning(f"Listener error on error: {e}")

    # Session management
    def get_session(self, session_id: str) -> ConversationContext | None:
        """Get an active session by ID."""
        return self._active_sessions.get(session_id)

    def get_user_sessions(self, user_id: str) -> list[ConversationContext]:
        """Get all active sessions for a user."""
        return [ctx for ctx in self._active_sessions.values() if ctx.user_id == user_id]

    def end_session(self, session_id: str) -> bool:
        """End and remove a session."""
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
            return True
        return False

    def clear_expired_sessions(self) -> int:
        """Clear all expired sessions. Returns count of cleared sessions."""
        now = datetime.now(UTC)
        expired = []

        for session_id, context in self._active_sessions.items():
            session_age = (now - context.last_activity).total_seconds() / 60
            if session_age > self.config.session_timeout_minutes:
                expired.append(session_id)

        for session_id in expired:
            del self._active_sessions[session_id]

        return len(expired)

    # Metrics
    def get_metrics(self) -> JSONDict:
        """Get assistant metrics."""
        uptime = None
        if self._start_time:
            uptime = (datetime.now(UTC) - self._start_time).total_seconds()

        return {
            "state": self._state.value,
            "active_sessions": len(self._active_sessions),
            "total_messages_processed": self._total_messages_processed,
            "total_errors": self._total_errors,
            "uptime_seconds": uptime,
            "constitutional_hash": self.config.constitutional_hash,
        }

    def get_health(self) -> JSONDict:
        """Get assistant health status."""
        return {
            "status": "healthy" if self.is_ready else "unhealthy",
            "state": self._state.value,
            "active_sessions": len(self._active_sessions),
            "constitutional_hash": self.config.constitutional_hash,
        }


# Convenience factory function
async def create_assistant(
    name: str = "ACGS-2 Assistant",
    enable_governance: bool = True,
    agent_bus: object | None = None,
) -> AIAssistant:
    """
    Factory function to create and initialize an AI Assistant.

    Args:
        name: Assistant name
        enable_governance: Whether to enable governance checks
        agent_bus: Optional Agent Bus instance for integration

    Returns:
        Initialized AIAssistant instance
    """
    config = AssistantConfig(
        name=name,
        enable_governance=enable_governance,
    )

    integration = None
    if agent_bus:
        integration = AgentBusIntegration(agent_bus=agent_bus)

    assistant = AIAssistant(config=config, integration=integration)
    await assistant.initialize()

    return assistant
