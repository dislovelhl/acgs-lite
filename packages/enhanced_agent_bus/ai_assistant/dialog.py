"""
ACGS-2 AI Assistant - Dialog Management
Constitutional Hash: 608508a9bd224290

Dialog management with conversation flows, state machine,
and policy-based action selection.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias

# Import centralized constitutional hash with fallback
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.bus_types import JSONDict, JSONValue
from enhanced_agent_bus.observability.structured_logging import get_logger

from .context import ConversationContext, ConversationState
from .nlu import Entity, NLUResult

logger = get_logger(__name__)


class ActionType(Enum):
    """Types of dialog actions."""

    RESPOND = "respond"
    ASK_QUESTION = "ask_question"
    CONFIRM = "confirm"
    EXECUTE_TASK = "execute_task"
    CLARIFY = "clarify"
    ESCALATE = "escalate"
    END_CONVERSATION = "end_conversation"
    WAIT_FOR_INPUT = "wait_for_input"
    FILL_SLOT = "fill_slot"


@dataclass
class DialogAction:
    """Represents a dialog action to be executed."""

    action_type: ActionType
    parameters: JSONDict = field(default_factory=dict)
    response_template: str | None = None
    next_state: str | None = None
    required_slots: list[str] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        return {
            "action_type": self.action_type.value,
            "parameters": self.parameters,
            "response_template": self.response_template,
            "next_state": self.next_state,
            "required_slots": self.required_slots,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class FlowNode:
    """Represents a node in a conversation flow."""

    id: str
    name: str
    node_type: str  # 'response', 'question', 'validation', 'action', 'condition'
    content: str | Callable | None = None
    next_node: str | None = None
    transitions: dict[str, str] = field(default_factory=dict)  # condition -> next_node_id
    timeout_seconds: int = 30
    timeout_action: str | None = None
    required_entities: list[str] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        return {
            "id": self.id,
            "name": self.name,
            "node_type": self.node_type,
            "content": str(self.content) if callable(self.content) else self.content,
            "next_node": self.next_node,
            "transitions": self.transitions,
            "timeout_seconds": self.timeout_seconds,
            "timeout_action": self.timeout_action,
            "required_entities": self.required_entities,
            "metadata": self.metadata,
        }


@dataclass
class ConversationFlow:
    """Defines a complete conversation flow."""

    id: str
    name: str
    description: str
    trigger_intents: list[str]
    nodes: list[FlowNode]
    entry_node: str
    exit_nodes: list[str] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)

    def get_node(self, node_id: str) -> FlowNode | None:
        """Get a node by ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def to_dict(self) -> JSONDict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger_intents": self.trigger_intents,
            "nodes": [n.to_dict() for n in self.nodes],
            "entry_node": self.entry_node,
            "exit_nodes": self.exit_nodes,
            "metadata": self.metadata,
        }


class DialogPolicy(ABC):
    """Abstract base class for dialog policies."""

    @abstractmethod
    async def select_action(
        self,
        context: ConversationContext,
        nlu_result: NLUResult,
        available_actions: list[ActionType],
    ) -> DialogAction:
        """Select the next dialog action."""
        pass


class RuleBasedDialogPolicy(DialogPolicy):
    """
    Rule-based dialog policy using intent-to-action mapping.

    Simple but effective for well-defined conversation patterns.
    """

    def __init__(self):
        self.intent_actions: dict[str, DialogAction] = self._default_intent_actions()
        self.fallback_responses = self._default_fallback_responses()

    def _default_intent_actions(self) -> dict[str, DialogAction]:
        """Default intent to action mappings."""
        return {
            "greeting": DialogAction(
                action_type=ActionType.RESPOND,
                response_template="Hello! How can I help you today?",
            ),
            "farewell": DialogAction(
                action_type=ActionType.END_CONVERSATION,
                response_template="Goodbye! Have a great day!",
            ),
            "help": DialogAction(
                action_type=ActionType.RESPOND,
                response_template="I'm here to help! You can ask me about orders, "
                "get support, or ask general questions. What do you need?",
            ),
            "confirmation": DialogAction(
                action_type=ActionType.EXECUTE_TASK,
                response_template="Great, I'll proceed with that.",
            ),
            "denial": DialogAction(
                action_type=ActionType.CLARIFY,
                response_template="I understand. What would you like to do instead?",
            ),
            "order_status": DialogAction(
                action_type=ActionType.FILL_SLOT,
                required_slots=["order_id"],
                response_template="I can help with that. What's your order number?",
            ),
            "complaint": DialogAction(
                action_type=ActionType.ESCALATE,
                response_template="I'm sorry to hear you're having trouble. "
                "Let me connect you with someone who can help.",
            ),
            "unknown": DialogAction(
                action_type=ActionType.CLARIFY,
                response_template="I'm not sure I understood that. Could you rephrase?",
            ),
        }

    def _default_fallback_responses(self) -> list[str]:
        """Default fallback responses for unknown intents."""
        return [
            "I'm not sure I understand. Could you rephrase that?",
            "I didn't quite catch that. Can you try saying it differently?",
            "I'm having trouble understanding. Could you be more specific?",
        ]

    async def select_action(
        self,
        context: ConversationContext,
        nlu_result: NLUResult,
        available_actions: list[ActionType],
    ) -> DialogAction:
        """Select action based on intent and context."""
        intent_name = nlu_result.primary_intent.name if nlu_result.primary_intent else "unknown"

        # Check for slot filling in progress
        if context.conversation_state == ConversationState.AWAITING_INPUT:
            pending_slots = context.state_data.get("pending_slots", [])
            if pending_slots:
                return self._handle_slot_filling(context, nlu_result, pending_slots)

        # Check for confirmation pending
        if context.conversation_state == ConversationState.AWAITING_CONFIRMATION:
            return self._handle_confirmation(context, nlu_result)

        # Get action for intent
        action = self.intent_actions.get(intent_name)
        if action:
            # Check if required slots are filled
            if action.required_slots:
                missing_slots = self._get_missing_slots(action.required_slots, nlu_result, context)
                if missing_slots:
                    return self._create_slot_filling_action(missing_slots, action)
            return action

        # Use clarification for low confidence
        if nlu_result.requires_clarification:
            return DialogAction(
                action_type=ActionType.CLARIFY,
                response_template=self.fallback_responses[0],
            )

        # Default fallback
        return self.intent_actions.get(
            "unknown",
            DialogAction(
                action_type=ActionType.CLARIFY,
                response_template="I'm not sure how to help with that.",
            ),
        )

    def _get_missing_slots(
        self,
        required_slots: list[str],
        nlu_result: NLUResult,
        context: ConversationContext,
    ) -> list[str]:
        """Get list of missing required slots."""
        missing = []
        for slot in required_slots:
            # Check if slot is filled from entities
            entity_filled = any(
                (e.type if hasattr(e, "type") else None) == slot for e in nlu_result.entities
            )
            # Check if slot is in context
            context_filled = context.get_slot(slot) is not None

            if not entity_filled and not context_filled:
                missing.append(slot)

        return missing

    def _create_slot_filling_action(
        self,
        missing_slots: list[str],
        original_action: DialogAction,
    ) -> DialogAction:
        """Create action to fill missing slots."""
        slot_prompts = {
            "order_id": "What's your order number?",
            "email": "What's your email address?",
            "phone": "What's your phone number?",
            "date": "What date are you looking for?",
            "product": "Which product are you interested in?",
        }

        first_slot = missing_slots[0]
        prompt = slot_prompts.get(first_slot, f"Please provide the {first_slot}.")

        return DialogAction(
            action_type=ActionType.FILL_SLOT,
            required_slots=missing_slots,
            response_template=prompt,
            parameters={"filling_slot": first_slot, "original_action": original_action.to_dict()},
        )

    def _handle_slot_filling(
        self,
        context: ConversationContext,
        nlu_result: NLUResult,
        pending_slots: list[str],
    ) -> DialogAction:
        """Handle slot filling state."""
        # Try to extract slot value from entities or text
        current_slot = pending_slots[0]

        # Check entities for matching slot
        for entity in nlu_result.entities:
            # Entity can be str or Entity object - narrow to Entity
            if isinstance(entity, str):
                continue
            if entity.type == current_slot or self._entity_matches_slot(entity, current_slot):
                context.set_slot(current_slot, entity.value)
                remaining_slots = pending_slots[1:]

                if not remaining_slots:
                    # All slots filled, execute original action
                    original_action = context.state_data.get("original_action", {})
                    return DialogAction(
                        action_type=ActionType.EXECUTE_TASK,
                        parameters={"slots": context.slots, "original_action": original_action},
                        response_template="Got it! Let me help you with that.",
                    )
                else:
                    # More slots to fill
                    return self._create_slot_filling_action(
                        remaining_slots,
                        DialogAction(
                            action_type=ActionType.EXECUTE_TASK,
                            **context.state_data.get("original_action", {}),
                        ),
                    )

        # Couldn't extract slot value, ask again
        return DialogAction(
            action_type=ActionType.FILL_SLOT,
            required_slots=pending_slots,
            response_template=f"I need a valid {current_slot}. Please try again.",
        )

    def _entity_matches_slot(self, entity, slot: str) -> bool:
        """Check if entity type matches expected slot."""
        type_mappings = {
            "order_id": ["order_id", "product_code", "number"],
            "email": ["email"],
            "phone": ["phone"],
            "date": ["date"],
        }
        expected_types = type_mappings.get(slot, [slot])
        return entity.type in expected_types

    def _handle_confirmation(
        self,
        context: ConversationContext,
        nlu_result: NLUResult,
    ) -> DialogAction:
        """Handle confirmation state."""
        intent = nlu_result.primary_intent.name if nlu_result.primary_intent else None

        if intent == "confirmation":
            # User confirmed, execute pending action
            pending_action = context.state_data.get("pending_action", {})
            return DialogAction(
                action_type=ActionType.EXECUTE_TASK,
                parameters=pending_action,
                response_template="Processing your request now.",
            )
        elif intent == "denial":
            return DialogAction(
                action_type=ActionType.CLARIFY,
                response_template="No problem. What would you like to do instead?",
            )
        else:
            return DialogAction(
                action_type=ActionType.CONFIRM,
                response_template="I need you to confirm with 'yes' or 'no'. Should I proceed?",
            )


class DialogManager:
    """
    Main dialog manager for conversation handling.

    Manages conversation flows, state machine, and action selection
    with constitutional governance integration.
    """

    def __init__(
        self,
        policy: DialogPolicy | None = None,
        flows: list[ConversationFlow] | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.policy = policy or RuleBasedDialogPolicy()
        self.flows = {f.id: f for f in (flows or [])}
        self.constitutional_hash = constitutional_hash
        self._action_handlers: dict[ActionType, Callable] = {}

    async def process_turn(
        self,
        context: ConversationContext,
        nlu_result: NLUResult,
    ) -> JSONDict:
        """
        Process a conversation turn.

        Args:
            context: Current conversation context
            nlu_result: NLU processing result

        Returns:
            Turn result with action and response data
        """
        # Check if we're in an active flow
        active_flow_id = context.state_data.get("active_flow")
        if active_flow_id:
            return await self._process_flow_turn(context, nlu_result, active_flow_id)

        # Check for flow trigger
        flow = self._find_matching_flow(nlu_result)
        if flow:
            return await self._start_flow(context, nlu_result, flow)

        # Use policy to select action
        action = await self.policy.select_action(
            context=context,
            nlu_result=nlu_result,
            available_actions=list(ActionType),
        )

        # Execute action
        result = await self._execute_action(action, context, nlu_result)

        # Update context state
        self._update_context_state(context, action, result)

        return {
            "action": action,
            "result": result,
            "context_state": context.conversation_state.value,
        }

    def _find_matching_flow(self, nlu_result: NLUResult) -> ConversationFlow | None:
        """Find a flow matching the current intent."""
        if not nlu_result.primary_intent:
            return None

        intent_name = nlu_result.primary_intent.name
        for flow in self.flows.values():
            if intent_name in flow.trigger_intents:
                return flow

        return None

    async def _start_flow(
        self,
        context: ConversationContext,
        nlu_result: NLUResult,
        flow: ConversationFlow,
    ) -> JSONDict:
        """Start a new conversation flow."""
        logger.info(f"Starting flow: {flow.name}")

        context.state_data["active_flow"] = flow.id
        context.state_data["current_node"] = flow.entry_node
        context.transition_state(ConversationState.PROCESSING)

        return await self._process_flow_node(context, nlu_result, flow, flow.entry_node)

    async def _process_flow_turn(
        self,
        context: ConversationContext,
        nlu_result: NLUResult,
        flow_id: str,
    ) -> JSONDict:
        """Process a turn within an active flow."""
        flow = self.flows.get(flow_id)
        if not flow:
            # Flow not found, exit gracefully
            context.state_data.pop("active_flow", None)
            return await self.process_turn(context, nlu_result)

        current_node_id = context.state_data.get("current_node")
        return await self._process_flow_node(context, nlu_result, flow, current_node_id)

    async def _process_flow_node(
        self,
        context: ConversationContext,
        nlu_result: NLUResult,
        flow: ConversationFlow,
        node_id: str,
    ) -> JSONDict:
        """Process a specific flow node."""
        node = flow.get_node(node_id)
        if not node:
            # Node not found, exit flow
            context.state_data.pop("active_flow", None)
            context.state_data.pop("current_node", None)
            return {
                "action": DialogAction(action_type=ActionType.RESPOND),
                "result": {"response": "I seem to have lost track. How can I help?"},
                "context_state": context.conversation_state.value,
            }

        # Execute node based on type
        result = await self._execute_node(node, context, nlu_result)

        # Determine next node
        next_node_id = self._determine_next_node(node, result, nlu_result)

        if next_node_id in flow.exit_nodes or next_node_id is None:
            # Exit flow
            context.state_data.pop("active_flow", None)
            context.state_data.pop("current_node", None)
            context.transition_state(ConversationState.ACTIVE)
        else:
            context.state_data["current_node"] = next_node_id

        # Map node_type to ActionType
        node_type_map = {
            "response": ActionType.RESPOND,
            "question": ActionType.ASK_QUESTION,
            "validation": ActionType.CONFIRM,
            "action": ActionType.EXECUTE_TASK,
            "condition": ActionType.RESPOND,
        }
        action_type = node_type_map.get(node.node_type, ActionType.RESPOND)

        return {
            "action": DialogAction(action_type=action_type),
            "result": result,
            "context_state": context.conversation_state.value,
            "flow": {"id": flow.id, "node": node_id, "next_node": next_node_id},
        }

    async def _execute_node(
        self,
        node: FlowNode,
        context: ConversationContext,
        nlu_result: NLUResult,
    ) -> JSONDict:
        """Execute a flow node."""
        if node.node_type == "response":
            content = node.content
            if callable(content):
                content = await content(context, nlu_result)
            return {"response": content, "type": "response"}

        elif node.node_type == "question":
            context.transition_state(ConversationState.AWAITING_INPUT)
            return {"response": node.content, "type": "question"}

        elif node.node_type == "validation":
            if callable(node.content):
                is_valid = await node.content(context, nlu_result)
                return {"valid": is_valid, "type": "validation"}
            return {"valid": True, "type": "validation"}

        elif node.node_type == "action":
            if callable(node.content):
                action_result = await node.content(context, nlu_result)
                return {"result": action_result, "type": "action"}
            return {"result": None, "type": "action"}

        elif node.node_type == "condition":
            if callable(node.content):
                condition_result = await node.content(context, nlu_result)
                return {"condition": condition_result, "type": "condition"}
            return {"condition": True, "type": "condition"}

        return {"type": "unknown"}

    def _determine_next_node(
        self,
        node: FlowNode,
        result: JSONDict,
        nlu_result: NLUResult,
    ) -> str | None:
        """Determine the next node based on result."""
        # Check transitions based on conditions
        if node.transitions:
            # For validation nodes
            if result.get("type") == "validation":
                if result.get("valid"):
                    return node.transitions.get("success", node.next_node)
                else:
                    return node.transitions.get("failure", node.next_node)

            # For condition nodes
            if result.get("type") == "condition":
                condition_key = str(result.get("condition", "default"))
                return node.transitions.get(condition_key, node.next_node)

            # For intent-based transitions
            if nlu_result.primary_intent:
                intent_name = nlu_result.primary_intent.name
                if intent_name in node.transitions:
                    return node.transitions[intent_name]

        return node.next_node

    async def _execute_action(
        self,
        action: DialogAction,
        context: ConversationContext,
        nlu_result: NLUResult,
    ) -> JSONDict:
        """Execute a dialog action."""
        # Check for registered handler
        if action.action_type in self._action_handlers:
            handler = self._action_handlers[action.action_type]
            return await handler(action, context, nlu_result)  # type: ignore[no-any-return]

        # Use lookup table for default action handlers
        action_handlers = {
            ActionType.RESPOND: self._handle_respond_action,
            ActionType.ASK_QUESTION: self._handle_ask_question_action,
            ActionType.CONFIRM: self._handle_confirm_action,
            ActionType.CLARIFY: self._handle_clarify_action,
            ActionType.FILL_SLOT: self._handle_fill_slot_action,
            ActionType.EXECUTE_TASK: self._handle_execute_task_action,
            ActionType.ESCALATE: self._handle_escalate_action,
            ActionType.END_CONVERSATION: self._handle_end_conversation_action,
        }

        handler = action_handlers.get(action.action_type)
        if handler:
            return handler(action, context)

        return {"response": action.response_template or ""}

    def _handle_respond_action(
        self, action: DialogAction, context: ConversationContext
    ) -> JSONDict:
        """Handle RESPOND action type."""
        return {"response": action.response_template}

    def _handle_ask_question_action(
        self, action: DialogAction, context: ConversationContext
    ) -> JSONDict:
        """Handle ASK_QUESTION action type."""
        context.transition_state(ConversationState.AWAITING_INPUT)
        return {"response": action.response_template, "awaiting": "answer"}

    def _handle_confirm_action(
        self, action: DialogAction, context: ConversationContext
    ) -> JSONDict:
        """Handle CONFIRM action type."""
        context.transition_state(ConversationState.AWAITING_CONFIRMATION)
        context.state_data["pending_action"] = action.parameters
        return {"response": action.response_template, "awaiting": "confirmation"}

    def _handle_clarify_action(
        self, action: DialogAction, context: ConversationContext
    ) -> JSONDict:
        """Handle CLARIFY action type."""
        return {"response": action.response_template}

    def _handle_fill_slot_action(
        self, action: DialogAction, context: ConversationContext
    ) -> JSONDict:
        """Handle FILL_SLOT action type."""
        context.transition_state(ConversationState.AWAITING_INPUT)
        context.state_data["pending_slots"] = action.required_slots
        if "original_action" in action.parameters:
            context.state_data["original_action"] = action.parameters["original_action"]
        return {"response": action.response_template, "awaiting": "slot_value"}

    def _handle_execute_task_action(
        self, action: DialogAction, context: ConversationContext
    ) -> JSONDict:
        """Handle EXECUTE_TASK action type."""
        return {"response": action.response_template, "task_executed": True}

    def _handle_escalate_action(
        self, action: DialogAction, context: ConversationContext
    ) -> JSONDict:
        """Handle ESCALATE action type."""
        context.transition_state(ConversationState.ESCALATED)
        return {"response": action.response_template, "escalated": True}

    def _handle_end_conversation_action(
        self, action: DialogAction, context: ConversationContext
    ) -> JSONDict:
        """Handle END_CONVERSATION action type."""
        context.transition_state(ConversationState.COMPLETED)
        return {"response": action.response_template, "ended": True}

    def _update_context_state(
        self,
        context: ConversationContext,
        action: DialogAction,
        result: JSONDict,
    ) -> None:
        """Update context state after action execution."""
        # Clear pending states on successful action completion
        if action.action_type == ActionType.EXECUTE_TASK:
            context.state_data.pop("pending_slots", None)
            context.state_data.pop("pending_action", None)
            context.transition_state(ConversationState.ACTIVE)

    def register_action_handler(
        self,
        action_type: ActionType,
        handler: Callable,
    ) -> None:
        """Register a custom action handler."""
        self._action_handlers[action_type] = handler

    def add_flow(self, flow: ConversationFlow) -> None:
        """Add a conversation flow."""
        self.flows[flow.id] = flow

    def get_flow(self, flow_id: str) -> ConversationFlow | None:
        """Get a conversation flow by ID."""
        return self.flows.get(flow_id)

    def remove_flow(self, flow_id: str) -> None:
        """Remove a conversation flow."""
        self.flows.pop(flow_id, None)
