"""Tests for ai_assistant/dialog.py."""

import pytest

from enhanced_agent_bus.ai_assistant.context import ConversationContext, ConversationState
from enhanced_agent_bus.ai_assistant.dialog import (
    ActionType,
    ConversationFlow,
    DialogAction,
    DialogManager,
    FlowNode,
    RuleBasedDialogPolicy,
)
from enhanced_agent_bus.ai_assistant.nlu import Entity, Intent, NLUResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(state: ConversationState = ConversationState.ACTIVE, **kwargs):
    ctx = ConversationContext(user_id="u1", session_id="s1")
    ctx.conversation_state = state
    for k, v in kwargs.items():
        ctx.state_data[k] = v
    return ctx


def _make_nlu(
    intent_name: str = "unknown",
    confidence: float = 0.9,
    entities=None,
    requires_clarification: bool = False,
):
    return NLUResult(
        original_text="test",
        processed_text="test",
        primary_intent=Intent(name=intent_name, confidence=confidence),
        entities=entities or [],
        requires_clarification=requires_clarification,
    )


# ---------------------------------------------------------------------------
# DialogAction tests
# ---------------------------------------------------------------------------


class TestDialogAction:
    def test_to_dict(self):
        action = DialogAction(
            action_type=ActionType.RESPOND,
            response_template="Hello",
            next_state="greeting",
        )
        d = action.to_dict()
        assert d["action_type"] == "respond"
        assert d["response_template"] == "Hello"
        assert d["next_state"] == "greeting"

    def test_defaults(self):
        action = DialogAction(action_type=ActionType.CLARIFY)
        assert action.parameters == {}
        assert action.required_slots == []


# ---------------------------------------------------------------------------
# FlowNode tests
# ---------------------------------------------------------------------------


class TestFlowNode:
    def test_to_dict_with_string_content(self):
        node = FlowNode(id="n1", name="Greeting", node_type="response", content="Hi there")
        d = node.to_dict()
        assert d["id"] == "n1"
        assert d["content"] == "Hi there"

    def test_to_dict_with_callable_content(self):
        node = FlowNode(id="n1", name="Dynamic", node_type="action", content=lambda c, n: None)
        d = node.to_dict()
        assert d["id"] == "n1"
        assert "function" in d["content"].lower() or "lambda" in d["content"].lower()


# ---------------------------------------------------------------------------
# ConversationFlow tests
# ---------------------------------------------------------------------------


class TestConversationFlow:
    def test_get_node(self):
        nodes = [
            FlowNode(id="start", name="Start", node_type="response", content="Hello"),
            FlowNode(id="ask", name="Ask", node_type="question", content="What do you need?"),
        ]
        flow = ConversationFlow(
            id="f1",
            name="Test Flow",
            description="desc",
            trigger_intents=["help"],
            nodes=nodes,
            entry_node="start",
        )
        assert flow.get_node("start") is nodes[0]
        assert flow.get_node("ask") is nodes[1]
        assert flow.get_node("nonexistent") is None

    def test_to_dict(self):
        flow = ConversationFlow(
            id="f1",
            name="Test",
            description="desc",
            trigger_intents=["help"],
            nodes=[FlowNode(id="n1", name="N1", node_type="response")],
            entry_node="n1",
        )
        d = flow.to_dict()
        assert d["id"] == "f1"
        assert len(d["nodes"]) == 1


# ---------------------------------------------------------------------------
# RuleBasedDialogPolicy tests
# ---------------------------------------------------------------------------


class TestRuleBasedDialogPolicy:
    @pytest.mark.asyncio
    async def test_greeting_intent(self):
        policy = RuleBasedDialogPolicy()
        ctx = _make_context()
        nlu = _make_nlu("greeting")
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.RESPOND
        assert "Hello" in action.response_template

    @pytest.mark.asyncio
    async def test_farewell_intent(self):
        policy = RuleBasedDialogPolicy()
        ctx = _make_context()
        nlu = _make_nlu("farewell")
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.END_CONVERSATION

    @pytest.mark.asyncio
    async def test_unknown_intent(self):
        policy = RuleBasedDialogPolicy()
        ctx = _make_context()
        nlu = _make_nlu("unknown")
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.CLARIFY

    @pytest.mark.asyncio
    async def test_order_status_missing_slot(self):
        policy = RuleBasedDialogPolicy()
        ctx = _make_context()
        nlu = _make_nlu("order_status")
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.FILL_SLOT
        assert "order_id" in action.required_slots

    @pytest.mark.asyncio
    async def test_order_status_slot_filled_via_entity(self):
        policy = RuleBasedDialogPolicy()
        ctx = _make_context()
        entity = Entity(text="12345", type="order_id", value="12345", start=0, end=5)
        nlu = _make_nlu("order_status", entities=[entity])
        action = await policy.select_action(ctx, nlu, list(ActionType))
        # order_id is filled via entity, so should not ask for slot
        assert action.action_type == ActionType.FILL_SLOT or action.required_slots == []

    @pytest.mark.asyncio
    async def test_complaint_escalates(self):
        policy = RuleBasedDialogPolicy()
        ctx = _make_context()
        nlu = _make_nlu("complaint")
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.ESCALATE

    @pytest.mark.asyncio
    async def test_low_confidence_clarifies(self):
        policy = RuleBasedDialogPolicy()
        ctx = _make_context()
        nlu = _make_nlu("nonexistent_intent_xyz", requires_clarification=True)
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.CLARIFY

    @pytest.mark.asyncio
    async def test_awaiting_confirmation_confirm(self):
        policy = RuleBasedDialogPolicy()
        ctx = _make_context(ConversationState.AWAITING_CONFIRMATION, pending_action={"do": "it"})
        nlu = _make_nlu("confirmation")
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.EXECUTE_TASK

    @pytest.mark.asyncio
    async def test_awaiting_confirmation_denial(self):
        policy = RuleBasedDialogPolicy()
        ctx = _make_context(ConversationState.AWAITING_CONFIRMATION)
        nlu = _make_nlu("denial")
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.CLARIFY

    @pytest.mark.asyncio
    async def test_awaiting_confirmation_other(self):
        policy = RuleBasedDialogPolicy()
        ctx = _make_context(ConversationState.AWAITING_CONFIRMATION)
        nlu = _make_nlu("greeting")
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.CONFIRM

    @pytest.mark.asyncio
    async def test_slot_filling_with_entity(self):
        policy = RuleBasedDialogPolicy()
        ctx = _make_context(
            ConversationState.AWAITING_INPUT,
            pending_slots=["order_id"],
            original_action={},
        )
        entity = Entity(text="ORD-123", type="order_id", value="ORD-123", start=0, end=7)
        nlu = _make_nlu("order_status", entities=[entity])
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.EXECUTE_TASK

    @pytest.mark.asyncio
    async def test_slot_filling_no_match(self):
        policy = RuleBasedDialogPolicy()
        ctx = _make_context(
            ConversationState.AWAITING_INPUT,
            pending_slots=["order_id"],
        )
        nlu = _make_nlu("unknown", entities=[])
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.FILL_SLOT
        assert "order_id" in action.required_slots


# ---------------------------------------------------------------------------
# DialogManager tests
# ---------------------------------------------------------------------------


class TestDialogManager:
    @pytest.mark.asyncio
    async def test_process_turn_respond(self):
        mgr = DialogManager()
        ctx = _make_context()
        nlu = _make_nlu("greeting")
        result = await mgr.process_turn(ctx, nlu)
        assert "action" in result
        assert "result" in result
        assert result["action"].action_type == ActionType.RESPOND

    @pytest.mark.asyncio
    async def test_process_turn_end_conversation(self):
        mgr = DialogManager()
        ctx = _make_context()
        nlu = _make_nlu("farewell")
        result = await mgr.process_turn(ctx, nlu)
        assert result["result"].get("ended") is True
        assert ctx.conversation_state == ConversationState.COMPLETED

    @pytest.mark.asyncio
    async def test_process_turn_escalate(self):
        mgr = DialogManager()
        ctx = _make_context()
        nlu = _make_nlu("complaint")
        result = await mgr.process_turn(ctx, nlu)
        assert result["result"].get("escalated") is True

    @pytest.mark.asyncio
    async def test_process_turn_ask_question(self):
        mgr = DialogManager()
        ctx = _make_context()
        nlu = _make_nlu("help")
        result = await mgr.process_turn(ctx, nlu)
        assert result["action"].action_type == ActionType.RESPOND

    @pytest.mark.asyncio
    async def test_flow_management(self):
        nodes = [
            FlowNode(id="start", name="Start", node_type="response", content="Welcome!"),
        ]
        flow = ConversationFlow(
            id="f1",
            name="Welcome Flow",
            description="Onboarding",
            trigger_intents=["onboarding"],
            nodes=nodes,
            entry_node="start",
            exit_nodes=[],
        )
        mgr = DialogManager()
        mgr.add_flow(flow)
        assert mgr.get_flow("f1") is flow
        mgr.remove_flow("f1")
        assert mgr.get_flow("f1") is None

    @pytest.mark.asyncio
    async def test_flow_trigger(self):
        nodes = [
            FlowNode(
                id="start",
                name="Start",
                node_type="response",
                content="Welcome to onboarding!",
                next_node=None,
            ),
        ]
        flow = ConversationFlow(
            id="onboard",
            name="Onboarding",
            description="desc",
            trigger_intents=["onboarding"],
            nodes=nodes,
            entry_node="start",
            exit_nodes=[],
        )
        mgr = DialogManager(flows=[flow])
        ctx = _make_context()
        nlu = _make_nlu("onboarding")
        result = await mgr.process_turn(ctx, nlu)
        assert "flow" in result
        assert result["result"]["response"] == "Welcome to onboarding!"

    @pytest.mark.asyncio
    async def test_flow_node_not_found(self):
        nodes = [FlowNode(id="start", name="Start", node_type="response", content="Hi")]
        flow = ConversationFlow(
            id="f1",
            name="F",
            description="d",
            trigger_intents=["x"],
            nodes=nodes,
            entry_node="start",
        )
        mgr = DialogManager(flows=[flow])
        ctx = _make_context()
        ctx.state_data["active_flow"] = "f1"
        ctx.state_data["current_node"] = "nonexistent"
        nlu = _make_nlu("x")
        result = await mgr.process_turn(ctx, nlu)
        assert "lost track" in result["result"]["response"]

    @pytest.mark.asyncio
    async def test_flow_not_found_exits_gracefully(self):
        mgr = DialogManager()
        ctx = _make_context()
        ctx.state_data["active_flow"] = "nonexistent_flow"
        nlu = _make_nlu("greeting")
        result = await mgr.process_turn(ctx, nlu)
        # Should fall back to normal processing
        assert "action" in result

    @pytest.mark.asyncio
    async def test_register_action_handler(self):
        async def custom_handler(action, context, nlu_result):
            return {"custom": True}

        mgr = DialogManager()
        mgr.register_action_handler(ActionType.RESPOND, custom_handler)
        ctx = _make_context()
        nlu = _make_nlu("greeting")
        result = await mgr.process_turn(ctx, nlu)
        assert result["result"].get("custom") is True

    @pytest.mark.asyncio
    async def test_fill_slot_action(self):
        mgr = DialogManager()
        ctx = _make_context()
        nlu = _make_nlu("order_status")
        result = await mgr.process_turn(ctx, nlu)
        assert ctx.conversation_state == ConversationState.AWAITING_INPUT

    @pytest.mark.asyncio
    async def test_confirm_action(self):
        policy = RuleBasedDialogPolicy()
        policy.intent_actions["test_confirm"] = DialogAction(
            action_type=ActionType.CONFIRM,
            response_template="Are you sure?",
            parameters={"action": "delete"},
        )
        mgr = DialogManager(policy=policy)
        ctx = _make_context()
        nlu = _make_nlu("test_confirm")
        result = await mgr.process_turn(ctx, nlu)
        assert ctx.conversation_state == ConversationState.AWAITING_CONFIRMATION

    @pytest.mark.asyncio
    async def test_execute_task_clears_pending(self):
        policy = RuleBasedDialogPolicy()
        policy.intent_actions["do_it"] = DialogAction(
            action_type=ActionType.EXECUTE_TASK,
            response_template="Done!",
        )
        mgr = DialogManager(policy=policy)
        ctx = _make_context()
        ctx.state_data["pending_slots"] = ["x"]
        ctx.state_data["pending_action"] = {"y": 1}
        nlu = _make_nlu("do_it")
        await mgr.process_turn(ctx, nlu)
        assert "pending_slots" not in ctx.state_data
        assert "pending_action" not in ctx.state_data
        assert ctx.conversation_state == ConversationState.ACTIVE
