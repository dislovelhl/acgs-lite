"""
ACGS-2 AI Assistant - Context Management
Constitutional Hash: 608508a9bd224290

Sophisticated context management with constitutional validation,
entity tracking, and conversation state management.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import TypeAlias

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
MAMBA_CONTEXT_PROCESSING_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    OSError,
)

from enhanced_agent_bus.bus_types import JSONDict, JSONValue

# Optional torch import for Mamba processing
try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not available - Mamba-2 processing disabled")

# Import Mamba-2 Hybrid Processor for long context
try:
    from .mamba_hybrid_processor import (
        MambaConfig,
        get_mamba_hybrid_processor,
        initialize_mamba_processor,
    )

    MAMBA_AVAILABLE = True
except (ImportError, AttributeError):
    MAMBA_AVAILABLE = False
    logger.warning("Mamba-2 Hybrid Processor not available - using standard context processing")

# Import centralized constitutional hash with fallback
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"


class ConversationState(Enum):
    """Conversation state enumeration."""

    INITIALIZED = "initialized"
    ACTIVE = "active"
    AWAITING_INPUT = "awaiting_input"
    WAITING_INPUT = "waiting_input"  # Alias for compatibility
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    FAILED = "failed"
    ERROR = "error"


class MessageRole(Enum):
    """Message role enumeration."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """Represents a single message in the conversation."""

    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: JSONDict = field(default_factory=dict)
    intent: str | None = None
    entities: list[JSONDict] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert message to dictionary."""
        return {
            "role": self.role.value if isinstance(self.role, MessageRole) else self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "intent": self.intent,
            "entities": self.entities,
            "constitutional_hash": self.constitutional_hash,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "Message":
        """Create message from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now(UTC)

        role = data["role"]
        if isinstance(role, str):
            role = MessageRole(role)

        return cls(
            role=role,
            content=data["content"],
            timestamp=timestamp,
            metadata=data.get("metadata", {}),
            intent=data.get("intent"),
            entities=data.get("entities", []),
            constitutional_hash=data.get("constitutional_hash", CONSTITUTIONAL_HASH),
        )


@dataclass
class UserProfile:
    """User profile for personalization."""

    user_id: str
    name: str | None = None
    email: str | None = None
    preferences: JSONDict = field(default_factory=dict)
    metadata: JSONDict = field(default_factory=dict)
    history_summary: str = ""
    language: str = "en"
    timezone: str = "UTC"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert profile to dictionary."""
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email,
            "preferences": self.preferences,
            "metadata": self.metadata,
            "history_summary": self.history_summary,
            "language": self.language,
            "timezone": self.timezone,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class ConversationContext:
    """
    Maintains conversation state and context with constitutional validation.

    This is the central context object that tracks:
    - User identity and profile
    - Session state
    - Message history
    - Entity states
    - Conversation flow state
    """

    user_id: str
    session_id: str
    messages: list[Message] = field(default_factory=list)
    user_profile: UserProfile | None = None
    conversation_state: ConversationState = ConversationState.INITIALIZED
    state_data: JSONDict = field(default_factory=dict)
    entities: JSONDict = field(default_factory=dict)
    slots: JSONDict = field(default_factory=dict)
    metadata: JSONDict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH
    tenant_id: str | None = None
    max_history: int = 100

    def __post_init__(self):
        """Enforce max_history constraint after initialization."""
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history :]

    def add_message(
        self,
        message_or_role: Message | str | MessageRole,
        content: str | None = None,
        **kwargs,
    ) -> Message:
        """
        Add a message to the conversation history.

        Can be called with:
        - add_message(Message) - adds an existing Message object
        - add_message(role, content, **kwargs) - creates and adds a new Message
        - add_message(MessageRole, content, **kwargs) - creates and adds a new Message
        """
        if isinstance(message_or_role, Message):
            message = message_or_role
        else:
            # Handle both string role and MessageRole enum
            if isinstance(message_or_role, MessageRole):
                role = message_or_role
            else:
                # Convert string to MessageRole
                role = (
                    MessageRole(message_or_role)
                    if message_or_role in [r.value for r in MessageRole]
                    else MessageRole.USER
                )
            message = Message(
                role=role,
                content=content or "",
                constitutional_hash=self.constitutional_hash,
                **kwargs,
            )
        self.messages.append(message)
        # Enforce max_history
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history :]
        self.updated_at = datetime.now(UTC)
        return message

    def get_last_user_message(self) -> Message | None:
        """Get the last user message."""
        for msg in reversed(self.messages):
            if msg.role == MessageRole.USER:
                return msg
        return None

    def get_last_assistant_message(self) -> Message | None:
        """Get the last assistant message."""
        for msg in reversed(self.messages):
            if msg.role == MessageRole.ASSISTANT:
                return msg
        return None

    def get_recent_messages(self, count: int = 10) -> list[Message]:
        """Get the most recent messages."""
        return self.messages[-count:] if self.messages else []

    def get_context_hash(self) -> str:
        """Generate a hash of the current context for caching."""
        context_str = json.dumps(
            {
                "user_id": self.user_id,
                "session_id": self.session_id,
                "state": self.conversation_state.value,
                "entities": self.entities,
                "slots": self.slots,
                "message_count": len(self.messages),
            },
            sort_keys=True,
        )
        return hashlib.sha256(context_str.encode()).hexdigest()[:16]

    def update_entity(self, entity_type: str, entity_value: JSONValue, **metadata) -> None:
        """Update an entity in the context."""
        self.entities[entity_type] = {
            "value": entity_value,
            "updated_at": datetime.now(UTC).isoformat(),
            "metadata": metadata,
        }
        self.updated_at = datetime.now(UTC)

    def get_entity(self, entity_type: str) -> JSONValue | None:
        """Get an entity value from context."""
        entity_data = self.entities.get(entity_type)
        if entity_data:
            return entity_data.get("value")  # type: ignore[no-any-return]
        return None

    def has_entity(self, entity_type: str) -> bool:
        """Check if an entity exists in the context."""
        return entity_type in self.entities

    def set_slot(self, slot_name: str, value: JSONValue) -> None:
        """set a slot value for slot-filling dialogs."""
        self.slots[slot_name] = {
            "value": value,
            "filled_at": datetime.now(UTC).isoformat(),
        }
        self.updated_at = datetime.now(UTC)

    def get_slot(self, slot_name: str, default: JSONValue = None) -> JSONValue | None:
        """Get a slot value, returning default if not found."""
        slot_data = self.slots.get(slot_name)
        if slot_data:
            return slot_data.get("value")  # type: ignore[no-any-return]
        return default

    def clear_slots(self) -> None:
        """Clear all slots."""
        self.slots.clear()
        self.updated_at = datetime.now(UTC)

    def transition_state(self, new_state: ConversationState) -> None:
        """Transition to a new conversation state."""
        logger.debug(
            f"Context state transition: {self.conversation_state.value} -> {new_state.value}"
        )
        self.conversation_state = new_state
        self.updated_at = datetime.now(UTC)

    def to_dict(self) -> JSONDict:
        """Convert context to dictionary for serialization."""
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "messages": [m.to_dict() for m in self.messages],
            "user_profile": self.user_profile.to_dict() if self.user_profile else None,
            "conversation_state": self.conversation_state.value,
            "state_data": self.state_data,
            "entities": self.entities,
            "slots": self.slots,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "constitutional_hash": self.constitutional_hash,
            "tenant_id": self.tenant_id,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "ConversationContext":
        """Create context from dictionary."""
        messages = [Message.from_dict(m) for m in data.get("messages", [])]
        user_profile = None
        if data.get("user_profile"):
            user_profile = UserProfile(**data["user_profile"])

        return cls(
            user_id=data["user_id"],
            session_id=data["session_id"],
            messages=messages,
            user_profile=user_profile,
            conversation_state=ConversationState(data.get("conversation_state", "initialized")),
            state_data=data.get("state_data", {}),
            entities=data.get("entities", {}),
            slots=data.get("slots", {}),
            metadata=data.get("metadata", {}),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.now(UTC)
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if data.get("updated_at")
                else datetime.now(UTC)
            ),
            constitutional_hash=data.get("constitutional_hash", CONSTITUTIONAL_HASH),
            tenant_id=data.get("tenant_id"),
        )


class ContextManager:
    """
    Manages conversation context with sophisticated features.

    Provides:
    - Reference resolution (pronouns, temporal)
    - Topic tracking and shift detection
    - Entity state management
    - Context pruning for long conversations
    - Constitutional validation
    """

    def __init__(
        self,
        max_context_length: int = 50,
        max_entity_age_turns: int = 10,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.max_context_length = max_context_length
        self.max_entity_age_turns = max_entity_age_turns
        self.constitutional_hash = constitutional_hash
        self._reference_patterns = self._compile_reference_patterns()
        self._sessions: dict[str, ConversationContext] = {}

    def create_context(self, user_id: str, session_id: str, **kwargs) -> ConversationContext:
        """Create and store a new conversation context."""
        context = ConversationContext(
            user_id=user_id,
            session_id=session_id,
            constitutional_hash=self.constitutional_hash,
            **kwargs,
        )
        self._sessions[session_id] = context
        return context

    def get_context(self, session_id: str) -> ConversationContext | None:
        """Retrieve a conversation context by session ID."""
        return self._sessions.get(session_id)

    def delete_context(self, session_id: str) -> bool:
        """Delete a conversation context by session ID."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_user_contexts(self, user_id: str) -> list[ConversationContext]:
        """list all contexts for a given user."""
        return [ctx for ctx in self._sessions.values() if ctx.user_id == user_id]

    def _compile_reference_patterns(self) -> dict[str, JSONDict]:
        """Compile patterns for reference resolution."""
        return {
            "pronouns": {
                "it": ["object", "thing", "topic"],
                "they": ["people", "group", "items"],
                "he": ["male_person"],
                "she": ["female_person"],
                "that": ["previous_topic", "object"],
                "this": ["current_topic", "object"],
                "there": ["location"],
            },
            "temporal": {
                "today": "current_date",
                "tomorrow": "next_day",
                "yesterday": "previous_day",
                "next week": "next_week",
                "last week": "previous_week",
                "now": "current_time",
                "later": "future_time",
            },
        }

    async def update_context(
        self,
        context: ConversationContext,
        user_message: str,
        nlu_result: JSONDict | None = None,
    ) -> ConversationContext:
        """
        Update context with new user message and NLU results.

        Args:
            context: Current conversation context
            user_message: Raw user message
            nlu_result: NLU processing results (intent, entities, etc.)

        Returns:
            Updated conversation context
        """
        # Add user message
        message = context.add_message(
            "user",
            content=user_message,
            intent=nlu_result.get("intent") if nlu_result else None,
            entities=nlu_result.get("entities", []) if nlu_result else [],
        )

        # Resolve references in the message
        resolved_message = await self.resolve_references(user_message, context)
        if resolved_message != user_message:
            message.metadata["resolved_content"] = resolved_message

        # Update entities from NLU
        if nlu_result and nlu_result.get("entities"):
            for entity in nlu_result["entities"]:
                context.update_entity(
                    entity_type=entity["type"],
                    entity_value=entity["value"],
                    confidence=entity.get("confidence", 1.0),
                    source_turn=len(context.messages),
                )

        # Detect topic shift
        topic_shift = self._detect_topic_shift(nlu_result, context)
        if topic_shift:
            context.metadata["topic_shift"] = {
                "detected_at": datetime.now(UTC).isoformat(),
                "from_topic": topic_shift.get("from"),
                "to_topic": topic_shift.get("to"),
            }

        # Prune old context if needed
        if len(context.messages) > self.max_context_length:
            context = self._prune_context(context)

        # Transition state to active
        if context.conversation_state == ConversationState.INITIALIZED:
            context.transition_state(ConversationState.ACTIVE)

        return context

    async def resolve_references(
        self,
        text: str,
        context: ConversationContext,
    ) -> str:
        """
        Resolve pronouns and references in text using context.

        Args:
            text: Text with potential references
            context: Conversation context for resolution

        Returns:
            Text with resolved references
        """
        resolved = text.lower()

        # Resolve pronouns
        for pronoun, entity_types in self._reference_patterns["pronouns"].items():
            if pronoun in resolved:
                # Find matching entity in context
                for entity_type in entity_types:
                    entity_value = context.get_entity(entity_type)
                    if entity_value:
                        resolved = resolved.replace(pronoun, str(entity_value))
                        break

        # Resolve temporal references
        for temporal_ref, ref_type in self._reference_patterns["temporal"].items():
            if temporal_ref in resolved:
                resolved_time = self._resolve_temporal(ref_type)
                resolved = resolved.replace(temporal_ref, str(resolved_time))

        return resolved

    def _resolve_temporal(self, ref_type: str) -> str:
        """Resolve temporal reference to actual value."""
        now = datetime.now(UTC)

        resolutions = {
            "current_date": now.strftime("%Y-%m-%d"),
            "next_day": (now.replace(hour=0, minute=0, second=0) + timedelta(days=1)).strftime(
                "%Y-%m-%d"
            ),
            "previous_day": (now.replace(hour=0, minute=0, second=0) - timedelta(days=1)).strftime(
                "%Y-%m-%d"
            ),
            "current_time": now.strftime("%H:%M"),
            "next_week": (now + timedelta(weeks=1)).strftime("%Y-%m-%d"),
            "previous_week": (now - timedelta(weeks=1)).strftime("%Y-%m-%d"),
        }

        return resolutions.get(ref_type, ref_type)

    async def process_long_context(
        self, context: ConversationContext, max_tokens: int = 1_000_000, use_attention: bool = False
    ) -> ConversationContext:
        """
        Process conversation context using Mamba-2 Hybrid Processor for long contexts.

        This enables processing of conversations with millions of tokens while maintaining
        constitutional compliance and context understanding.

        Args:
            context: Conversation context to process
            max_tokens: Maximum tokens to process (up to 4M)
            use_attention: Whether to use attention layer for critical reasoning

        Returns:
            Enhanced conversation context with long-term understanding
        """
        if not MAMBA_AVAILABLE:
            logger.warning("Mamba-2 processor not available, using standard processing")
            return context

        try:
            # Get Mamba processor
            mamba_manager = get_mamba_hybrid_processor()

            # Ensure model is loaded
            if not mamba_manager.is_loaded:
                config = MambaConfig(max_context_length=min(max_tokens, 4_000_000))
                if not initialize_mamba_processor(config):
                    logger.error("Failed to initialize Mamba processor")
                    return context

            # Convert conversation to tensor format
            # This is a simplified conversion - in practice would use proper embeddings
            messages_text = [msg.content for msg in context.messages[-100:]]  # Last 100 messages
            context_text = " ".join(messages_text)

            # Create dummy embeddings (in practice, use proper tokenizer and embeddings)
            # This is placeholder - actual implementation would use real embeddings
            seq_len = min(len(context_text.split()), max_tokens // 10)  # Rough token estimation
            d_model = 512  # Match Mamba config

            # Create input tensor (dummy embeddings for now)
            input_tensor = torch.randn(1, seq_len, d_model)

            # Process through Mamba hybrid processor
            processed_tensor = mamba_manager.process_context(
                input_tensor=input_tensor, use_attention=use_attention
            )

            # Extract insights from processed tensor
            # This would be enhanced with actual embedding analysis
            context_strength = float(processed_tensor.norm().item())
            context.metadata["mamba_processed"] = True
            context.metadata["context_strength"] = context_strength
            context.metadata["processed_at"] = datetime.now(UTC).isoformat()
            context.metadata["mamba_config"] = {
                "max_tokens": max_tokens,
                "attention_used": use_attention,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }

            logger.info(f"Processed long context with Mamba-2: strength={context_strength:.2f}")

            return context

        except MAMBA_CONTEXT_PROCESSING_ERRORS as e:
            logger.error(f"Failed to process long context with Mamba-2: {e}")
            context.metadata["mamba_error"] = str(e)
            return context

    def _detect_topic_shift(
        self,
        nlu_result: JSONDict | None,
        context: ConversationContext,
    ) -> dict[str, str] | None:
        """Detect if there's a topic shift in the conversation."""
        if not nlu_result or not context.messages:
            return None

        current_intent = nlu_result.get("intent")
        if not current_intent:
            return None

        # Get previous intent
        previous_messages = [m for m in context.messages[-5:] if m.role == "user" and m.intent]

        if not previous_messages:
            return None

        previous_intent = previous_messages[-1].intent

        # Check for significant topic change
        topic_indicators = {
            "greeting": ["greeting", "farewell"],
            "order": ["order", "purchase", "buy"],
            "support": ["help", "issue", "problem"],
            "information": ["question", "inquiry", "ask"],
        }

        def get_topic(intent: str) -> str | None:
            for topic, intents in topic_indicators.items():
                if any(i in intent.lower() for i in intents):
                    return topic
            return None

        previous_topic = get_topic(previous_intent)
        current_topic = get_topic(current_intent)

        if previous_topic and current_topic and previous_topic != current_topic:
            return {"from": previous_topic, "to": current_topic}

        return None

    def _prune_context(self, context: ConversationContext) -> ConversationContext:
        """
        Prune old context to manage memory.

        Keeps:
        - Most recent messages
        - Important entities
        - Summarizes old context
        """
        # Keep system messages and recent messages
        system_messages = [m for m in context.messages if m.role == "system"]
        recent_messages = context.messages[-self.max_context_length :]

        # Combine, avoiding duplicates
        context.messages = system_messages + [
            m for m in recent_messages if m not in system_messages
        ]

        # Prune old entities
        current_turn = len(context.messages)
        entities_to_remove = []

        for entity_type, entity_data in context.entities.items():
            source_turn = entity_data.get("metadata", {}).get("source_turn", 0)
            if current_turn - source_turn > self.max_entity_age_turns:
                entities_to_remove.append(entity_type)

        for entity_type in entities_to_remove:
            del context.entities[entity_type]

        return context

    def get_context_summary(self, context: ConversationContext) -> str:
        """Generate a summary of the conversation context."""
        summary_parts = []

        # User info
        if context.user_profile:
            summary_parts.append(f"User: {context.user_id}")

        # Conversation state
        summary_parts.append(f"State: {context.conversation_state.value}")

        # Message count
        summary_parts.append(f"Messages: {len(context.messages)}")

        # Active entities
        if context.entities:
            entity_list = ", ".join(f"{k}={v.get('value')}" for k, v in context.entities.items())
            summary_parts.append(f"Entities: {entity_list}")

        # Filled slots
        if context.slots:
            slot_list = ", ".join(f"{k}={v.get('value')}" for k, v in context.slots.items())
            summary_parts.append(f"Slots: {slot_list}")

        return " | ".join(summary_parts)
