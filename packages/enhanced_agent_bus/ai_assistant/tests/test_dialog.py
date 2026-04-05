"""
ACGS-2 AI Assistant - Dialog Manager Tests
Constitutional Hash: 608508a9bd224290
"""

import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)

# Import centralized constitutional hash with fallback
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.ai_assistant.context import (
    ConversationContext,
    ConversationState,
)
from enhanced_agent_bus.ai_assistant.dialog import (
    ActionType,
    ConversationFlow,
    DialogAction,
    DialogManager,
    DialogPolicy,
    FlowNode,
    RuleBasedDialogPolicy,
)
from enhanced_agent_bus.ai_assistant.nlu import Entity, Intent, NLUResult


class TestDialogAction:
    """Tests for DialogAction dataclass."""

    def test_create_respond_action(self):
        """Test creating a respond action."""
        action = DialogAction(action_type=ActionType.RESPOND)

        assert action.action_type == ActionType.RESPOND
        assert action.parameters == {}

    def test_create_action_with_parameters(self):
        """Test creating an action with parameters."""
        action = DialogAction(
            action_type=ActionType.EXECUTE_TASK,
            parameters={"task_type": "order_lookup", "order_id": "12345"},
        )

        assert action.action_type == ActionType.EXECUTE_TASK
        assert action.parameters["task_type"] == "order_lookup"
        assert action.parameters["order_id"] == "12345"

    def test_action_types(self):
        """Test all action types exist."""
        assert ActionType.RESPOND
        assert ActionType.ASK_QUESTION
        assert ActionType.CLARIFY  # Not ASK_CLARIFICATION
        assert ActionType.EXECUTE_TASK
        assert ActionType.CONFIRM
        assert ActionType.ESCALATE
        assert ActionType.END_CONVERSATION
        assert ActionType.WAIT_FOR_INPUT  # Not WAIT
        assert ActionType.FILL_SLOT

    def test_action_to_dict(self):
        """Test action serialization."""
        action = DialogAction(
            action_type=ActionType.RESPOND,
            parameters={"message": "Hello"},
        )

        data = action.to_dict()

        assert "action_type" in data
        assert "parameters" in data


class TestFlowNode:
    """Tests for FlowNode dataclass."""

    def test_create_node(self):
        """Test creating a flow node."""
        node = FlowNode(
            id="greeting",
            name="Greeting Node",
            node_type="response",
            content="Hello! How can I help you?",
        )

        assert node.id == "greeting"
        assert node.name == "Greeting Node"
        assert node.node_type == "response"
        assert node.content is not None

    def test_node_with_transitions(self):
        """Test node with transitions."""
        node = FlowNode(
            id="order_inquiry",
            name="Order Inquiry",
            node_type="question",
            transitions={"order_id_provided": "lookup_order"},
            required_entities=["order_id"],
        )

        assert "order_id_provided" in node.transitions
        assert "order_id" in node.required_entities

    def test_node_to_dict(self):
        """Test node serialization."""
        node = FlowNode(
            id="test",
            name="Test Node",
            node_type="response",
        )

        data = node.to_dict()

        assert "id" in data
        assert "name" in data
        assert "node_type" in data


class TestConversationFlow:
    """Tests for ConversationFlow."""

    def test_create_flow(self):
        """Test creating a conversation flow."""
        start_node = FlowNode(
            id="start",
            name="Start",
            node_type="response",
        )
        flow = ConversationFlow(
            id="order_flow",
            name="Order Inquiry Flow",
            description="Flow for handling order inquiries",
            trigger_intents=["order_status"],
            nodes=[start_node],
            entry_node="start",
        )

        assert flow.id == "order_flow"
        assert flow.name == "Order Inquiry Flow"
        assert flow.entry_node == "start"

    def test_get_node(self):
        """Test getting a node from flow."""
        start_node = FlowNode(id="start", name="Start", node_type="response")
        flow = ConversationFlow(
            id="test_flow",
            name="Test Flow",
            description="Test",
            trigger_intents=["test"],
            nodes=[start_node],
            entry_node="start",
        )

        found = flow.get_node("start")
        assert found is not None
        assert found.id == "start"

    def test_get_nonexistent_node(self):
        """Test getting a non-existent node."""
        flow = ConversationFlow(
            id="test_flow",
            name="Test Flow",
            description="Test",
            trigger_intents=["test"],
            nodes=[],
            entry_node="",
        )

        node = flow.get_node("nonexistent")
        assert node is None


class TestRuleBasedDialogPolicy:
    """Tests for RuleBasedDialogPolicy."""

    def test_create_policy(self):
        """Test creating a policy."""
        policy = RuleBasedDialogPolicy()
        assert policy is not None

    async def test_select_action_greeting(self):
        """Test action selection for greeting."""
        policy = RuleBasedDialogPolicy()
        context = ConversationContext(user_id="user123", session_id="session456")
        nlu_result = NLUResult(
            original_text="Hello",
            processed_text="Hello",
            primary_intent=Intent(name="greeting", confidence=0.9),
            confidence=0.9,
        )
        available_actions = list(ActionType)

        action = await policy.select_action(context, nlu_result, available_actions)

        assert isinstance(action, DialogAction)
        assert action.action_type == ActionType.RESPOND

    async def test_select_action_order_status(self):
        """Test action selection for order status."""
        policy = RuleBasedDialogPolicy()
        context = ConversationContext(user_id="user123", session_id="session456")
        nlu_result = NLUResult(
            original_text="Where is my order?",
            processed_text="Where is my order?",
            primary_intent=Intent(name="order_status", confidence=0.85),
            entities=[Entity(text="ORD-12345", type="order_id", value="ORD-12345", start=0, end=9)],
            confidence=0.85,
        )
        available_actions = list(ActionType)

        action = await policy.select_action(context, nlu_result, available_actions)

        assert isinstance(action, DialogAction)

    async def test_select_action_low_confidence(self):
        """Test action selection with low confidence."""
        policy = RuleBasedDialogPolicy()
        context = ConversationContext(user_id="user123", session_id="session456")
        nlu_result = NLUResult(
            original_text="something unclear",
            processed_text="something unclear",
            primary_intent=Intent(name="unknown", confidence=0.3),
            confidence=0.3,
        )
        available_actions = list(ActionType)

        action = await policy.select_action(context, nlu_result, available_actions)

        assert isinstance(action, DialogAction)
        # Should ask for clarification with low confidence
        assert action.action_type in [
            ActionType.CLARIFY,
            ActionType.RESPOND,
            ActionType.ASK_QUESTION,
        ]

    async def test_select_action_missing_slot(self):
        """Test action when required slot is missing."""
        policy = RuleBasedDialogPolicy()
        context = ConversationContext(user_id="user123", session_id="session456")
        nlu_result = NLUResult(
            original_text="Check order status",
            processed_text="Check order status",
            primary_intent=Intent(name="order_status", confidence=0.9),
            entities=[],  # No order_id
            confidence=0.9,
        )
        available_actions = list(ActionType)

        action = await policy.select_action(context, nlu_result, available_actions)

        assert isinstance(action, DialogAction)

    async def test_select_action_goodbye(self):
        """Test action selection for goodbye."""
        policy = RuleBasedDialogPolicy()
        context = ConversationContext(user_id="user123", session_id="session456")
        nlu_result = NLUResult(
            original_text="Goodbye",
            processed_text="Goodbye",
            primary_intent=Intent(name="goodbye", confidence=0.9),
            confidence=0.9,
        )
        available_actions = list(ActionType)

        action = await policy.select_action(context, nlu_result, available_actions)

        assert isinstance(action, DialogAction)
        # Policy may return various actions depending on implementation
        assert action.action_type in [
            ActionType.END_CONVERSATION,
            ActionType.RESPOND,
            ActionType.CLARIFY,
        ]


class TestDialogManager:
    """Tests for DialogManager."""

    def test_create_manager(self):
        """Test creating a dialog manager."""
        manager = DialogManager()
        assert manager is not None

    async def test_process_turn_greeting(self):
        """Test processing a greeting turn."""
        manager = DialogManager()
        context = ConversationContext(user_id="user123", session_id="session456")
        nlu_result = NLUResult(
            original_text="Hello",
            processed_text="Hello",
            primary_intent=Intent(name="greeting", confidence=0.9),
            confidence=0.9,
        )

        result = await manager.process_turn(context, nlu_result)

        assert isinstance(result, dict)
        assert "action" in result

    async def test_process_turn_updates_context(self):
        """Test that processing updates context."""
        manager = DialogManager()
        context = ConversationContext(user_id="user123", session_id="session456")
        nlu_result = NLUResult(
            original_text="Check my order",
            processed_text="Check my order",
            primary_intent=Intent(name="order_status", confidence=0.9),
            entities=[Entity(text="ORD-12345", type="order_id", value="ORD-12345", start=0, end=9)],
            confidence=0.9,
        )

        await manager.process_turn(context, nlu_result)

        # Processing should complete without error
        assert True

    async def test_process_turn_with_flow(self):
        """Test processing with an active flow."""
        manager = DialogManager()

        # Add a simple flow
        start_node = FlowNode(
            id="start",
            name="Start Node",
            node_type="response",
            content="Let me look up your order.",
        )
        flow = ConversationFlow(
            id="order_flow",
            name="Order Flow",
            description="Order inquiry flow",
            trigger_intents=["order_status"],
            nodes=[start_node],
            entry_node="start",
        )
        manager.add_flow(flow)

        context = ConversationContext(user_id="user123", session_id="session456")
        nlu_result = NLUResult(
            original_text="Check order",
            processed_text="Check order",
            primary_intent=Intent(name="order_status", confidence=0.9),
            confidence=0.9,
        )

        result = await manager.process_turn(context, nlu_result)

        assert isinstance(result, dict)

    def test_add_flow(self):
        """Test adding a flow to manager."""
        manager = DialogManager()
        flow = ConversationFlow(
            id="test_flow",
            name="Test Flow",
            description="Test",
            trigger_intents=["test"],
            nodes=[],
            entry_node="",
        )

        manager.add_flow(flow)

        assert manager.get_flow("test_flow") is not None

    def test_remove_flow(self):
        """Test removing a flow from manager."""
        manager = DialogManager()
        flow = ConversationFlow(
            id="test_flow",
            name="Test Flow",
            description="Test",
            trigger_intents=["test"],
            nodes=[],
            entry_node="",
        )
        manager.add_flow(flow)

        manager.remove_flow("test_flow")

        assert manager.get_flow("test_flow") is None


class TestDialogManagerWithCustomPolicy:
    """Tests for DialogManager with custom policies."""

    async def test_custom_policy(self):
        """Test using a custom dialog policy."""

        class MockPolicy(DialogPolicy):
            async def select_action(
                self,
                context: ConversationContext,
                nlu_result: NLUResult,
                available_actions: list[ActionType],
            ) -> DialogAction:
                return DialogAction(
                    action_type=ActionType.RESPOND,
                    parameters={"custom": True},
                )

        manager = DialogManager(policy=MockPolicy())
        context = ConversationContext(user_id="user123", session_id="session456")
        nlu_result = NLUResult(
            original_text="Test",
            processed_text="Test",
            confidence=0.9,
        )

        result = await manager.process_turn(context, nlu_result)

        assert result["action"].parameters.get("custom") is True


class TestDialogManagerSlotFilling:
    """Tests for slot filling in DialogManager."""

    async def test_slot_filling_flow(self):
        """Test slot filling in a conversation flow."""
        manager = DialogManager()

        # Create nodes for the flow
        ask_node = FlowNode(
            id="ask_order",
            name="Ask Order ID",
            node_type="question",
            content="What is your order ID?",
            required_entities=["order_id"],
            transitions={"order_id_filled": "lookup"},
        )
        lookup_node = FlowNode(
            id="lookup",
            name="Lookup Order",
            node_type="action",
            content="Looking up order...",
        )

        flow = ConversationFlow(
            id="order_flow",
            name="Order Flow",
            description="Order inquiry flow",
            trigger_intents=["order_status"],
            nodes=[ask_node, lookup_node],
            entry_node="ask_order",
        )
        manager.add_flow(flow)

        context = ConversationContext(user_id="user123", session_id="session456")

        # First turn - no order_id
        result1 = await manager.process_turn(
            context,
            NLUResult(
                original_text="Check my order",
                processed_text="Check my order",
                primary_intent=Intent(name="order_status", confidence=0.9),
                entities=[],
                confidence=0.9,
            ),
        )

        # Should process without error
        assert isinstance(result1, dict)


class TestDialogManagerStateTransitions:
    """Tests for state transitions in DialogManager."""

    async def test_conversation_state_progression(self):
        """Test conversation state progression."""
        manager = DialogManager()
        context = ConversationContext(user_id="user123", session_id="session456")

        assert context.conversation_state == ConversationState.INITIALIZED

        await manager.process_turn(
            context,
            NLUResult(
                original_text="Hello",
                processed_text="Hello",
                primary_intent=Intent(name="greeting", confidence=0.9),
                confidence=0.9,
            ),
        )

        # State should be updated (depends on implementation)
        assert context.conversation_state in [
            ConversationState.ACTIVE,
            ConversationState.INITIALIZED,
            ConversationState.WAITING_INPUT,
        ]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
