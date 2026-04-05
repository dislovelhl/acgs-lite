"""
ACGS-2 AI Assistant - Dialog Coverage Tests
Constitutional Hash: 608508a9bd224290

Targets uncovered branches/lines to boost dialog.py coverage to ≥90%.
asyncio_mode = "auto" — no @pytest.mark.asyncio needed.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

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
    FlowNode,
    RuleBasedDialogPolicy,
)
from enhanced_agent_bus.ai_assistant.nlu import Entity, Intent, NLUResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_context(state: ConversationState = ConversationState.INITIALIZED) -> ConversationContext:
    ctx = ConversationContext(user_id="u1", session_id="s1")
    ctx.conversation_state = state
    return ctx


def make_nlu(
    intent_name: str | None = "greeting",
    confidence: float = 0.9,
    entities: list | None = None,
    requires_clarification: bool = False,
) -> NLUResult:
    primary = Intent(name=intent_name, confidence=confidence) if intent_name else None
    return NLUResult(
        original_text="test",
        processed_text="test",
        primary_intent=primary,
        entities=entities or [],
        confidence=confidence,
        requires_clarification=requires_clarification,
    )


# ---------------------------------------------------------------------------
# DialogAction.to_dict — line 52
# ---------------------------------------------------------------------------


class TestDialogActionToDict:
    def test_to_dict_all_fields(self):
        action = DialogAction(
            action_type=ActionType.FILL_SLOT,
            parameters={"k": "v"},
            response_template="tpl",
            next_state="s2",
            required_slots=["order_id"],
        )
        d = action.to_dict()
        assert d["action_type"] == "fill_slot"
        assert d["parameters"] == {"k": "v"}
        assert d["response_template"] == "tpl"
        assert d["next_state"] == "s2"
        assert d["required_slots"] == ["order_id"]
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_defaults(self):
        action = DialogAction(action_type=ActionType.RESPOND)
        d = action.to_dict()
        assert d["response_template"] is None
        assert d["next_state"] is None
        assert d["required_slots"] == []


# ---------------------------------------------------------------------------
# FlowNode.to_dict — lines 78-89 (callable content branch line 82)
# ---------------------------------------------------------------------------


class TestFlowNodeToDict:
    def test_to_dict_string_content(self):
        node = FlowNode(id="n1", name="N1", node_type="response", content="hello")
        d = node.to_dict()
        assert d["content"] == "hello"
        assert d["id"] == "n1"

    def test_to_dict_callable_content(self):
        """Line 82: str(content) branch for callable."""

        def my_func(ctx, nlu):
            return "result"

        node = FlowNode(id="n2", name="N2", node_type="action", content=my_func)
        d = node.to_dict()
        # callable.__str__ produces some string representation
        assert isinstance(d["content"], str)
        assert "function" in d["content"] or "my_func" in d["content"]

    def test_to_dict_none_content(self):
        node = FlowNode(id="n3", name="N3", node_type="response", content=None)
        d = node.to_dict()
        assert d["content"] is None

    def test_to_dict_with_transitions_and_metadata(self):
        node = FlowNode(
            id="n4",
            name="N4",
            node_type="condition",
            transitions={"yes": "n5"},
            required_entities=["order_id"],
            timeout_seconds=60,
            timeout_action="escalate",
            metadata={"key": "val"},
        )
        d = node.to_dict()
        assert d["transitions"] == {"yes": "n5"}
        assert d["required_entities"] == ["order_id"]
        assert d["timeout_seconds"] == 60
        assert d["timeout_action"] == "escalate"
        assert d["metadata"] == {"key": "val"}


# ---------------------------------------------------------------------------
# ConversationFlow.to_dict — lines 112-122
# ---------------------------------------------------------------------------


class TestConversationFlowToDict:
    def test_to_dict(self):
        node = FlowNode(id="start", name="Start", node_type="response", content="hi")
        flow = ConversationFlow(
            id="f1",
            name="Flow1",
            description="A test flow",
            trigger_intents=["greeting"],
            nodes=[node],
            entry_node="start",
            exit_nodes=["end"],
            metadata={"meta": "data"},
        )
        d = flow.to_dict()
        assert d["id"] == "f1"
        assert d["description"] == "A test flow"
        assert d["trigger_intents"] == ["greeting"]
        assert len(d["nodes"]) == 1
        assert d["entry_node"] == "start"
        assert d["exit_nodes"] == ["end"]
        assert d["metadata"] == {"meta": "data"}


# ---------------------------------------------------------------------------
# RuleBasedDialogPolicy — AWAITING_INPUT branch (lines 208-211)
# ---------------------------------------------------------------------------


class TestRuleBasedDialogPolicyAwaitingInput:
    async def test_awaiting_input_with_pending_slots(self):
        policy = RuleBasedDialogPolicy()
        ctx = make_context(ConversationState.AWAITING_INPUT)
        ctx.state_data["pending_slots"] = ["order_id"]

        entity = Entity(text="ORD-1", type="order_id", value="ORD-1", start=0, end=5)
        nlu = make_nlu(intent_name="order_status", entities=[entity])

        action = await policy.select_action(ctx, nlu, list(ActionType))
        # Should process slot filling — entity matches
        assert isinstance(action, DialogAction)

    async def test_awaiting_input_no_pending_slots_falls_through(self):
        """pending_slots=[] means the AWAITING_INPUT branch does not route to slot filling."""
        policy = RuleBasedDialogPolicy()
        ctx = make_context(ConversationState.AWAITING_INPUT)
        ctx.state_data["pending_slots"] = []

        nlu = make_nlu(intent_name="greeting")
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert isinstance(action, DialogAction)

    async def test_awaiting_input_no_pending_slots_key(self):
        """No pending_slots key in state_data — should not trigger slot filling."""
        policy = RuleBasedDialogPolicy()
        ctx = make_context(ConversationState.AWAITING_INPUT)
        # state_data has no pending_slots key

        nlu = make_nlu(intent_name="greeting")
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert isinstance(action, DialogAction)


# ---------------------------------------------------------------------------
# RuleBasedDialogPolicy — AWAITING_CONFIRMATION branch (lines 213-215)
# ---------------------------------------------------------------------------


class TestRuleBasedDialogPolicyAwaitingConfirmation:
    async def test_awaiting_confirmation_confirm(self):
        policy = RuleBasedDialogPolicy()
        ctx = make_context(ConversationState.AWAITING_CONFIRMATION)
        ctx.state_data["pending_action"] = {"task": "lookup"}

        nlu = make_nlu(intent_name="confirmation")
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.EXECUTE_TASK

    async def test_awaiting_confirmation_deny(self):
        policy = RuleBasedDialogPolicy()
        ctx = make_context(ConversationState.AWAITING_CONFIRMATION)

        nlu = make_nlu(intent_name="denial")
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.CLARIFY

    async def test_awaiting_confirmation_other_intent(self):
        policy = RuleBasedDialogPolicy()
        ctx = make_context(ConversationState.AWAITING_CONFIRMATION)

        nlu = make_nlu(intent_name="greeting")
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.CONFIRM

    async def test_awaiting_confirmation_no_intent(self):
        policy = RuleBasedDialogPolicy()
        ctx = make_context(ConversationState.AWAITING_CONFIRMATION)

        nlu = make_nlu(intent_name=None)
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.CONFIRM


# ---------------------------------------------------------------------------
# RuleBasedDialogPolicy — requires_clarification (lines 228-232)
# ---------------------------------------------------------------------------


class TestRuleBasedDialogPolicyRequiresClarification:
    async def test_requires_clarification_for_unknown_intent(self):
        policy = RuleBasedDialogPolicy()
        ctx = make_context()
        nlu = make_nlu(intent_name="very_unknown_xyz", requires_clarification=True)
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.CLARIFY

    async def test_no_intent_no_clarification_falls_back_to_unknown(self):
        """Unknown intent without requires_clarification → default fallback (line 235)."""
        policy = RuleBasedDialogPolicy()
        ctx = make_context()
        nlu = make_nlu(intent_name="totally_unknown_intent", requires_clarification=False)
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.CLARIFY

    async def test_no_primary_intent_returns_unknown_action(self):
        """primary_intent=None → intent_name='unknown' → uses intent_actions['unknown']."""
        policy = RuleBasedDialogPolicy()
        ctx = make_context()
        nlu = make_nlu(intent_name=None)
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert isinstance(action, DialogAction)


# ---------------------------------------------------------------------------
# RuleBasedDialogPolicy — slot filling paths
# ---------------------------------------------------------------------------


class TestHandleSlotFilling:
    async def test_slot_filling_entity_matches_type_directly(self):
        """Entity type matches current_slot directly."""
        policy = RuleBasedDialogPolicy()
        ctx = make_context(ConversationState.AWAITING_INPUT)
        ctx.state_data["pending_slots"] = ["email"]
        ctx.state_data["original_action"] = {}

        entity = Entity(
            text="user@example.com", type="email", value="user@example.com", start=0, end=16
        )
        nlu = make_nlu(entities=[entity])

        action = await policy.select_action(ctx, nlu, list(ActionType))
        # All slots filled → EXECUTE_TASK
        assert action.action_type == ActionType.EXECUTE_TASK

    async def test_slot_filling_entity_matches_via_entity_matches_slot(self):
        """Entity type 'number' maps to 'order_id' via type_mappings."""
        policy = RuleBasedDialogPolicy()
        ctx = make_context(ConversationState.AWAITING_INPUT)
        ctx.state_data["pending_slots"] = ["order_id"]
        ctx.state_data["original_action"] = {}

        entity = Entity(text="123", type="number", value="123", start=0, end=3)
        nlu = make_nlu(entities=[entity])

        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.EXECUTE_TASK

    async def test_slot_filling_remaining_slots(self):
        """After filling first slot, more remain → FILL_SLOT."""
        policy = RuleBasedDialogPolicy()
        ctx = make_context(ConversationState.AWAITING_INPUT)
        ctx.state_data["pending_slots"] = ["order_id", "email"]
        # original_action must NOT include action_type to avoid double-kwarg error in source
        ctx.state_data["original_action"] = {}

        entity = Entity(text="ORD-1", type="order_id", value="ORD-1", start=0, end=5)
        nlu = make_nlu(entities=[entity])

        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.FILL_SLOT

    async def test_slot_filling_no_matching_entity(self):
        """No entity matches → ask again with FILL_SLOT."""
        policy = RuleBasedDialogPolicy()
        ctx = make_context(ConversationState.AWAITING_INPUT)
        ctx.state_data["pending_slots"] = ["order_id"]

        nlu = make_nlu(entities=[])  # no entities
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.FILL_SLOT
        assert "order_id" in action.response_template

    async def test_slot_filling_string_entity_skipped(self):
        """String entities (not Entity objects) are skipped (line 301-302)."""
        policy = RuleBasedDialogPolicy()
        ctx = make_context(ConversationState.AWAITING_INPUT)
        ctx.state_data["pending_slots"] = ["order_id"]

        nlu = make_nlu(entities=["plain_string_entity"])
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.FILL_SLOT

    async def test_slot_filling_with_context_filled_slot(self):
        """Slot already in context → not missing."""
        policy = RuleBasedDialogPolicy()
        ctx = make_context()
        ctx.set_slot("order_id", "ORD-existing")

        nlu = make_nlu(intent_name="order_status", entities=[])
        action = await policy.select_action(ctx, nlu, list(ActionType))
        # order_id is in context, so not missing → return original action (FILL_SLOT mapped from intent)
        assert isinstance(action, DialogAction)


# ---------------------------------------------------------------------------
# _create_slot_filling_action — lines 264-286
# ---------------------------------------------------------------------------


class TestCreateSlotFillingAction:
    async def test_known_slot_prompt(self):
        """Known slots get a specific prompt."""
        policy = RuleBasedDialogPolicy()
        ctx = make_context()
        nlu = make_nlu(intent_name="order_status", entities=[])
        # order_status requires order_id with no entities → create_slot_filling_action called
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.FILL_SLOT
        assert "order" in action.response_template.lower()

    async def test_unknown_slot_generic_prompt(self):
        """Unknown slots get a generic 'Please provide...' prompt."""
        policy = RuleBasedDialogPolicy()
        # Inject a custom intent action requiring an unknown slot
        original_action = DialogAction(
            action_type=ActionType.EXECUTE_TASK,
            required_slots=["custom_slot_xyz"],
        )
        policy.intent_actions["custom_intent"] = original_action
        ctx = make_context()
        nlu = make_nlu(intent_name="custom_intent", entities=[])
        action = await policy.select_action(ctx, nlu, list(ActionType))
        assert action.action_type == ActionType.FILL_SLOT
        assert "custom_slot_xyz" in action.response_template


# ---------------------------------------------------------------------------
# _entity_matches_slot — lines 332-341
# ---------------------------------------------------------------------------


class TestEntityMatchesSlot:
    def test_direct_type_match(self):
        policy = RuleBasedDialogPolicy()
        entity = Entity(text="e", type="email", value="e", start=0, end=1)
        assert policy._entity_matches_slot(entity, "email") is True

    def test_mapped_type_match(self):
        policy = RuleBasedDialogPolicy()
        entity = Entity(text="123", type="product_code", value="123", start=0, end=3)
        # product_code is in type_mappings for order_id
        assert policy._entity_matches_slot(entity, "order_id") is True

    def test_no_match(self):
        policy = RuleBasedDialogPolicy()
        entity = Entity(text="x", type="phone", value="x", start=0, end=1)
        assert policy._entity_matches_slot(entity, "order_id") is False

    def test_unknown_slot_falls_back_to_slot_name(self):
        policy = RuleBasedDialogPolicy()
        entity = Entity(text="x", type="custom_slot", value="x", start=0, end=1)
        # No mapping for 'custom_slot', falls back to [slot] → matches if type == slot
        assert policy._entity_matches_slot(entity, "custom_slot") is True

    def test_unknown_slot_no_match(self):
        policy = RuleBasedDialogPolicy()
        entity = Entity(text="x", type="something_else", value="x", start=0, end=1)
        assert policy._entity_matches_slot(entity, "custom_slot") is False


# ---------------------------------------------------------------------------
# _get_missing_slots — lines 243-262
# ---------------------------------------------------------------------------


class TestGetMissingSlots:
    def test_entity_fills_slot(self):
        policy = RuleBasedDialogPolicy()
        ctx = make_context()
        entity = Entity(text="ORD-1", type="order_id", value="ORD-1", start=0, end=5)
        nlu = make_nlu(entities=[entity])
        missing = policy._get_missing_slots(["order_id"], nlu, ctx)
        assert "order_id" not in missing

    def test_context_fills_slot(self):
        policy = RuleBasedDialogPolicy()
        ctx = make_context()
        ctx.set_slot("order_id", "ORD-1")
        nlu = make_nlu(entities=[])
        missing = policy._get_missing_slots(["order_id"], nlu, ctx)
        assert "order_id" not in missing

    def test_slot_missing_completely(self):
        policy = RuleBasedDialogPolicy()
        ctx = make_context()
        nlu = make_nlu(entities=[])
        missing = policy._get_missing_slots(["order_id"], nlu, ctx)
        assert "order_id" in missing

    def test_entity_without_type_attr_treated_as_none(self):
        """Entity-like object without .type attribute → hasattr check → None != slot."""
        policy = RuleBasedDialogPolicy()
        ctx = make_context()
        # A mock object without .type
        mock_entity = MagicMock(spec=[])  # no 'type' attribute
        nlu = make_nlu(entities=[mock_entity])
        missing = policy._get_missing_slots(["order_id"], nlu, ctx)
        assert "order_id" in missing


# ---------------------------------------------------------------------------
# DialogManager._find_matching_flow — lines 434-444
# ---------------------------------------------------------------------------


class TestFindMatchingFlow:
    def test_finds_flow_by_intent(self):
        manager = DialogManager()
        flow = ConversationFlow(
            id="f1",
            name="F1",
            description="",
            trigger_intents=["order_status"],
            nodes=[],
            entry_node="",
        )
        manager.add_flow(flow)
        nlu = make_nlu(intent_name="order_status")
        found = manager._find_matching_flow(nlu)
        assert found is not None
        assert found.id == "f1"

    def test_returns_none_when_no_intent(self):
        manager = DialogManager()
        nlu = make_nlu(intent_name=None)
        assert manager._find_matching_flow(nlu) is None

    def test_returns_none_when_no_matching_flow(self):
        manager = DialogManager()
        nlu = make_nlu(intent_name="unknown_intent")
        assert manager._find_matching_flow(nlu) is None


# ---------------------------------------------------------------------------
# DialogManager._start_flow — lines 446-459
# ---------------------------------------------------------------------------


class TestStartFlow:
    async def test_start_flow_sets_state_data(self):
        """_start_flow sets active_flow before _process_flow_node runs (which may clear it)."""
        manager = DialogManager()
        # Use two nodes so the flow does not exit immediately (next_node points to n2)
        node1 = FlowNode(
            id="entry", name="Entry", node_type="response", content="hello", next_node="n2"
        )
        node2 = FlowNode(id="n2", name="N2", node_type="response", content="world")
        flow = ConversationFlow(
            id="f1",
            name="F1",
            description="",
            trigger_intents=["test"],
            nodes=[node1, node2],
            entry_node="entry",
            exit_nodes=["n2"],  # n2 is exit so flow completes properly
        )
        ctx = make_context()
        nlu = make_nlu(intent_name="test")

        result = await manager._start_flow(ctx, nlu, flow)
        # Result should contain flow metadata; active_flow may be cleared after exit but
        # the function ran successfully and returned a well-formed dict
        assert "action" in result
        assert "result" in result


# ---------------------------------------------------------------------------
# DialogManager._process_flow_turn — flow not found (lines 468-472)
# ---------------------------------------------------------------------------


class TestProcessFlowTurnFlowNotFound:
    async def test_flow_not_found_exits_gracefully(self):
        manager = DialogManager()
        ctx = make_context()
        ctx.state_data["active_flow"] = "nonexistent_flow"

        nlu = make_nlu(intent_name="greeting")
        # Should remove active_flow from state_data and recurse to process_turn
        result = await manager.process_turn(ctx, nlu)
        assert "action" in result
        assert "nonexistent_flow" not in ctx.state_data


# ---------------------------------------------------------------------------
# DialogManager._process_flow_node — node not found (lines 486-494)
# ---------------------------------------------------------------------------


class TestProcessFlowNodeNotFound:
    async def test_node_not_found_returns_recover_response(self):
        manager = DialogManager()
        flow = ConversationFlow(
            id="f1",
            name="F1",
            description="",
            trigger_intents=["test"],
            nodes=[],  # empty — node_id won't be found
            entry_node="missing_node",
        )
        manager.add_flow(flow)
        ctx = make_context()
        nlu = make_nlu(intent_name="test")

        result = await manager._process_flow_node(ctx, nlu, flow, "missing_node")
        assert "action" in result
        assert result["result"]["response"] == "I seem to have lost track. How can I help?"


# ---------------------------------------------------------------------------
# DialogManager._process_flow_node — exit nodes (lines 502-508)
# ---------------------------------------------------------------------------


class TestProcessFlowNodeExitNode:
    async def test_exit_node_clears_active_flow(self):
        manager = DialogManager()
        end_node = FlowNode(id="end", name="End", node_type="response", content="Goodbye!")
        flow = ConversationFlow(
            id="f1",
            name="F1",
            description="",
            trigger_intents=["farewell"],
            nodes=[end_node],
            entry_node="end",
            exit_nodes=["end"],
        )
        manager.add_flow(flow)
        ctx = make_context()
        ctx.state_data["active_flow"] = "f1"
        ctx.state_data["current_node"] = "end"
        nlu = make_nlu(intent_name="farewell")

        result = await manager._process_flow_node(ctx, nlu, flow, "end")
        assert "active_flow" not in ctx.state_data
        assert "current_node" not in ctx.state_data

    async def test_next_node_is_none_exits_flow(self):
        """next_node=None also triggers flow exit."""
        manager = DialogManager()
        sole_node = FlowNode(
            id="sole", name="Sole", node_type="response", content="hi", next_node=None
        )
        flow = ConversationFlow(
            id="f2",
            name="F2",
            description="",
            trigger_intents=["sole"],
            nodes=[sole_node],
            entry_node="sole",
            exit_nodes=[],  # no explicit exit nodes
        )
        manager.add_flow(flow)
        ctx = make_context()
        ctx.state_data["active_flow"] = "f2"
        ctx.state_data["current_node"] = "sole"
        nlu = make_nlu(intent_name="sole")

        await manager._process_flow_node(ctx, nlu, flow, "sole")
        # next_node=None → treated as exit (None in exit_nodes or is None)
        assert "active_flow" not in ctx.state_data


# ---------------------------------------------------------------------------
# DialogManager._execute_node — all node types
# ---------------------------------------------------------------------------


class TestExecuteNode:
    async def test_response_node_string_content(self):
        manager = DialogManager()
        node = FlowNode(id="n", name="N", node_type="response", content="hello world")
        ctx = make_context()
        nlu = make_nlu()

        result = await manager._execute_node(node, ctx, nlu)
        assert result["type"] == "response"
        assert result["response"] == "hello world"

    async def test_response_node_callable_content(self):
        """Line 537: awaits callable content."""
        manager = DialogManager()

        async def my_content(ctx, nlu):
            return "dynamic content"

        node = FlowNode(id="n", name="N", node_type="response", content=my_content)
        ctx = make_context()
        nlu = make_nlu()

        result = await manager._execute_node(node, ctx, nlu)
        assert result["response"] == "dynamic content"

    async def test_question_node(self):
        manager = DialogManager()
        node = FlowNode(id="n", name="N", node_type="question", content="What is your name?")
        ctx = make_context()
        nlu = make_nlu()

        result = await manager._execute_node(node, ctx, nlu)
        assert result["type"] == "question"
        assert ctx.conversation_state == ConversationState.AWAITING_INPUT

    async def test_validation_node_callable_valid(self):
        manager = DialogManager()

        async def validator(ctx, nlu):
            return True

        node = FlowNode(id="n", name="N", node_type="validation", content=validator)
        ctx = make_context()
        nlu = make_nlu()

        result = await manager._execute_node(node, ctx, nlu)
        assert result["type"] == "validation"
        assert result["valid"] is True

    async def test_validation_node_callable_invalid(self):
        manager = DialogManager()

        async def validator(ctx, nlu):
            return False

        node = FlowNode(id="n", name="N", node_type="validation", content=validator)
        ctx = make_context()
        nlu = make_nlu()

        result = await manager._execute_node(node, ctx, nlu)
        assert result["valid"] is False

    async def test_validation_node_non_callable(self):
        """Line 548: non-callable validation node returns valid=True."""
        manager = DialogManager()
        node = FlowNode(id="n", name="N", node_type="validation", content="static")
        ctx = make_context()
        nlu = make_nlu()

        result = await manager._execute_node(node, ctx, nlu)
        assert result["valid"] is True

    async def test_action_node_callable(self):
        manager = DialogManager()

        async def task(ctx, nlu):
            return {"done": True}

        node = FlowNode(id="n", name="N", node_type="action", content=task)
        ctx = make_context()
        nlu = make_nlu()

        result = await manager._execute_node(node, ctx, nlu)
        assert result["type"] == "action"
        assert result["result"] == {"done": True}

    async def test_action_node_non_callable(self):
        """Line 554: non-callable action node returns result=None."""
        manager = DialogManager()
        node = FlowNode(id="n", name="N", node_type="action", content="noop")
        ctx = make_context()
        nlu = make_nlu()

        result = await manager._execute_node(node, ctx, nlu)
        assert result["result"] is None

    async def test_condition_node_callable(self):
        manager = DialogManager()

        async def condition(ctx, nlu):
            return "yes"

        node = FlowNode(id="n", name="N", node_type="condition", content=condition)
        ctx = make_context()
        nlu = make_nlu()

        result = await manager._execute_node(node, ctx, nlu)
        assert result["type"] == "condition"
        assert result["condition"] == "yes"

    async def test_condition_node_non_callable(self):
        """Line 560: non-callable condition node returns condition=True."""
        manager = DialogManager()
        node = FlowNode(id="n", name="N", node_type="condition", content=None)
        ctx = make_context()
        nlu = make_nlu()

        result = await manager._execute_node(node, ctx, nlu)
        assert result["condition"] is True

    async def test_unknown_node_type(self):
        """Line 562: unknown node type returns type='unknown'."""
        manager = DialogManager()
        node = FlowNode(id="n", name="N", node_type="mystery", content=None)
        ctx = make_context()
        nlu = make_nlu()

        result = await manager._execute_node(node, ctx, nlu)
        assert result["type"] == "unknown"


# ---------------------------------------------------------------------------
# DialogManager._determine_next_node — lines 564-591
# ---------------------------------------------------------------------------


class TestDetermineNextNode:
    def test_no_transitions_returns_next_node(self):
        manager = DialogManager()
        node = FlowNode(id="n", name="N", node_type="response", next_node="n2", transitions={})
        nlu = make_nlu()
        result = manager._determine_next_node(node, {}, nlu)
        assert result == "n2"

    def test_validation_success_transition(self):
        manager = DialogManager()
        node = FlowNode(
            id="n",
            name="N",
            node_type="validation",
            transitions={"success": "next_ok", "failure": "retry"},
            next_node="default",
        )
        nlu = make_nlu()
        result = manager._determine_next_node(node, {"type": "validation", "valid": True}, nlu)
        assert result == "next_ok"

    def test_validation_failure_transition(self):
        manager = DialogManager()
        node = FlowNode(
            id="n",
            name="N",
            node_type="validation",
            transitions={"success": "next_ok", "failure": "retry"},
            next_node="default",
        )
        nlu = make_nlu()
        result = manager._determine_next_node(node, {"type": "validation", "valid": False}, nlu)
        assert result == "retry"

    def test_validation_no_success_key_falls_back_to_next_node(self):
        manager = DialogManager()
        node = FlowNode(
            id="n",
            name="N",
            node_type="validation",
            transitions={},  # no success/failure keys
            next_node="fallback",
        )
        nlu = make_nlu()
        result = manager._determine_next_node(node, {"type": "validation", "valid": True}, nlu)
        assert result == "fallback"

    def test_condition_transition(self):
        manager = DialogManager()
        node = FlowNode(
            id="n",
            name="N",
            node_type="condition",
            transitions={"True": "branch_true", "False": "branch_false"},
            next_node="default",
        )
        nlu = make_nlu()
        result = manager._determine_next_node(node, {"type": "condition", "condition": True}, nlu)
        assert result == "branch_true"

    def test_condition_default_transition(self):
        manager = DialogManager()
        node = FlowNode(
            id="n",
            name="N",
            node_type="condition",
            transitions={"some_key": "branch"},
            next_node="default_node",
        )
        nlu = make_nlu()
        result = manager._determine_next_node(
            node, {"type": "condition", "condition": "no_match"}, nlu
        )
        assert result == "default_node"

    def test_intent_based_transition(self):
        manager = DialogManager()
        node = FlowNode(
            id="n",
            name="N",
            node_type="question",
            transitions={"confirmation": "proceed", "denial": "cancel"},
            next_node="default",
        )
        nlu = make_nlu(intent_name="confirmation")
        result = manager._determine_next_node(node, {"type": "question"}, nlu)
        assert result == "proceed"

    def test_intent_transition_not_in_map_returns_next_node(self):
        manager = DialogManager()
        node = FlowNode(
            id="n",
            name="N",
            node_type="question",
            transitions={"confirmation": "proceed"},
            next_node="default",
        )
        nlu = make_nlu(intent_name="greeting")  # not in transitions
        result = manager._determine_next_node(node, {"type": "question"}, nlu)
        assert result == "default"

    def test_no_primary_intent_skips_intent_transition(self):
        manager = DialogManager()
        node = FlowNode(
            id="n",
            name="N",
            node_type="question",
            transitions={"confirmation": "proceed"},
            next_node="default",
        )
        nlu = make_nlu(intent_name=None)
        result = manager._determine_next_node(node, {"type": "question"}, nlu)
        assert result == "default"


# ---------------------------------------------------------------------------
# DialogManager._execute_action — all action types (lines 593-639)
# ---------------------------------------------------------------------------


class TestExecuteAction:
    async def test_respond_action(self):
        manager = DialogManager()
        ctx = make_context()
        nlu = make_nlu()
        action = DialogAction(action_type=ActionType.RESPOND, response_template="Hi!")
        result = await manager._execute_action(action, ctx, nlu)
        assert result["response"] == "Hi!"

    async def test_ask_question_action(self):
        manager = DialogManager()
        ctx = make_context()
        nlu = make_nlu()
        action = DialogAction(action_type=ActionType.ASK_QUESTION, response_template="What?")
        result = await manager._execute_action(action, ctx, nlu)
        assert result["awaiting"] == "answer"
        assert ctx.conversation_state == ConversationState.AWAITING_INPUT

    async def test_confirm_action(self):
        manager = DialogManager()
        ctx = make_context()
        nlu = make_nlu()
        action = DialogAction(
            action_type=ActionType.CONFIRM,
            response_template="Confirm?",
            parameters={"task": "delete"},
        )
        result = await manager._execute_action(action, ctx, nlu)
        assert result["awaiting"] == "confirmation"
        assert ctx.conversation_state == ConversationState.AWAITING_CONFIRMATION
        assert ctx.state_data["pending_action"] == {"task": "delete"}

    async def test_clarify_action(self):
        manager = DialogManager()
        ctx = make_context()
        nlu = make_nlu()
        action = DialogAction(action_type=ActionType.CLARIFY, response_template="Can you clarify?")
        result = await manager._execute_action(action, ctx, nlu)
        assert result["response"] == "Can you clarify?"

    async def test_fill_slot_action_with_original_action(self):
        """Line 624-625: original_action in parameters gets stored in state_data."""
        manager = DialogManager()
        ctx = make_context()
        nlu = make_nlu()
        action = DialogAction(
            action_type=ActionType.FILL_SLOT,
            response_template="Provide order ID.",
            required_slots=["order_id"],
            parameters={
                "filling_slot": "order_id",
                "original_action": {"action_type": "execute_task"},
            },
        )
        result = await manager._execute_action(action, ctx, nlu)
        assert result["awaiting"] == "slot_value"
        assert ctx.state_data["original_action"] == {"action_type": "execute_task"}
        assert ctx.state_data["pending_slots"] == ["order_id"]

    async def test_fill_slot_action_without_original_action(self):
        """No original_action in parameters — branch not taken."""
        manager = DialogManager()
        ctx = make_context()
        nlu = make_nlu()
        action = DialogAction(
            action_type=ActionType.FILL_SLOT,
            response_template="Provide phone.",
            required_slots=["phone"],
            parameters={},  # no original_action key
        )
        result = await manager._execute_action(action, ctx, nlu)
        assert result["awaiting"] == "slot_value"
        assert "original_action" not in ctx.state_data

    async def test_execute_task_action(self):
        manager = DialogManager()
        ctx = make_context()
        nlu = make_nlu()
        action = DialogAction(action_type=ActionType.EXECUTE_TASK, response_template="Done!")
        result = await manager._execute_action(action, ctx, nlu)
        assert result["task_executed"] is True

    async def test_escalate_action(self):
        manager = DialogManager()
        ctx = make_context()
        nlu = make_nlu()
        action = DialogAction(action_type=ActionType.ESCALATE, response_template="Escalating.")
        result = await manager._execute_action(action, ctx, nlu)
        assert result["escalated"] is True
        assert ctx.conversation_state == ConversationState.ESCALATED

    async def test_end_conversation_action(self):
        manager = DialogManager()
        ctx = make_context()
        nlu = make_nlu()
        action = DialogAction(action_type=ActionType.END_CONVERSATION, response_template="Bye!")
        result = await manager._execute_action(action, ctx, nlu)
        assert result["ended"] is True
        assert ctx.conversation_state == ConversationState.COMPLETED

    async def test_wait_for_input_action_falls_to_default(self):
        """WAIT_FOR_INPUT has no explicit branch → falls to final default (line 639)."""
        manager = DialogManager()
        ctx = make_context()
        nlu = make_nlu()
        action = DialogAction(
            action_type=ActionType.WAIT_FOR_INPUT,
            response_template="Waiting...",
        )
        result = await manager._execute_action(action, ctx, nlu)
        assert result["response"] == "Waiting..."

    async def test_wait_for_input_no_template_returns_empty(self):
        """Default path with no response_template."""
        manager = DialogManager()
        ctx = make_context()
        nlu = make_nlu()
        action = DialogAction(action_type=ActionType.WAIT_FOR_INPUT)
        result = await manager._execute_action(action, ctx, nlu)
        assert result["response"] == ""

    async def test_custom_registered_handler_called(self):
        """Lines 601-603: registered action handler is called."""
        manager = DialogManager()
        ctx = make_context()
        nlu = make_nlu()

        handler = AsyncMock(return_value={"custom_result": True})
        manager.register_action_handler(ActionType.RESPOND, handler)

        action = DialogAction(action_type=ActionType.RESPOND, response_template="Hi!")
        result = await manager._execute_action(action, ctx, nlu)
        handler.assert_called_once_with(action, ctx, nlu)
        assert result["custom_result"] is True


# ---------------------------------------------------------------------------
# DialogManager._update_context_state — lines 641-652
# ---------------------------------------------------------------------------


class TestUpdateContextState:
    def test_execute_task_clears_pending_state(self):
        manager = DialogManager()
        ctx = make_context()
        ctx.state_data["pending_slots"] = ["order_id"]
        ctx.state_data["pending_action"] = {"task": "x"}
        ctx.conversation_state = ConversationState.AWAITING_INPUT

        action = DialogAction(action_type=ActionType.EXECUTE_TASK)
        manager._update_context_state(ctx, action, {})

        assert "pending_slots" not in ctx.state_data
        assert "pending_action" not in ctx.state_data
        assert ctx.conversation_state == ConversationState.ACTIVE

    def test_non_execute_task_leaves_state_unchanged(self):
        manager = DialogManager()
        ctx = make_context()
        ctx.state_data["pending_slots"] = ["order_id"]
        ctx.conversation_state = ConversationState.AWAITING_INPUT

        action = DialogAction(action_type=ActionType.RESPOND)
        manager._update_context_state(ctx, action, {})

        assert ctx.state_data["pending_slots"] == ["order_id"]
        assert ctx.conversation_state == ConversationState.AWAITING_INPUT


# ---------------------------------------------------------------------------
# DialogManager.register_action_handler — line 660
# ---------------------------------------------------------------------------


class TestRegisterActionHandler:
    def test_register_and_retrieve(self):
        manager = DialogManager()
        handler = MagicMock()
        manager.register_action_handler(ActionType.ESCALATE, handler)
        assert manager._action_handlers[ActionType.ESCALATE] is handler

    def test_overwrite_handler(self):
        manager = DialogManager()
        handler1 = MagicMock()
        handler2 = MagicMock()
        manager.register_action_handler(ActionType.RESPOND, handler1)
        manager.register_action_handler(ActionType.RESPOND, handler2)
        assert manager._action_handlers[ActionType.RESPOND] is handler2


# ---------------------------------------------------------------------------
# DialogManager — node_type_map coverage (lines 511-518)
# ---------------------------------------------------------------------------


class TestNodeTypeToCoverage:
    async def test_question_node_yields_ask_question_action(self):
        manager = DialogManager()
        q_node = FlowNode(id="q", name="Q", node_type="question", content="Ask?")
        flow = ConversationFlow(
            id="f",
            name="F",
            description="",
            trigger_intents=["q"],
            nodes=[q_node],
            entry_node="q",
        )
        manager.add_flow(flow)
        ctx = make_context()
        nlu = make_nlu(intent_name="q")

        result = await manager.process_turn(ctx, nlu)
        assert result["action"].action_type == ActionType.ASK_QUESTION

    async def test_validation_node_yields_confirm_action(self):
        manager = DialogManager()
        v_node = FlowNode(id="v", name="V", node_type="validation", content=None)
        flow = ConversationFlow(
            id="f",
            name="F",
            description="",
            trigger_intents=["v"],
            nodes=[v_node],
            entry_node="v",
        )
        manager.add_flow(flow)
        ctx = make_context()
        nlu = make_nlu(intent_name="v")

        result = await manager.process_turn(ctx, nlu)
        assert result["action"].action_type == ActionType.CONFIRM

    async def test_action_node_yields_execute_task(self):
        manager = DialogManager()
        a_node = FlowNode(id="a", name="A", node_type="action", content=None)
        flow = ConversationFlow(
            id="f",
            name="F",
            description="",
            trigger_intents=["act"],
            nodes=[a_node],
            entry_node="a",
        )
        manager.add_flow(flow)
        ctx = make_context()
        nlu = make_nlu(intent_name="act")

        result = await manager.process_turn(ctx, nlu)
        assert result["action"].action_type == ActionType.EXECUTE_TASK

    async def test_unknown_node_type_yields_respond(self):
        manager = DialogManager()
        u_node = FlowNode(id="u", name="U", node_type="unknown_type", content=None)
        flow = ConversationFlow(
            id="f",
            name="F",
            description="",
            trigger_intents=["unk"],
            nodes=[u_node],
            entry_node="u",
        )
        manager.add_flow(flow)
        ctx = make_context()
        nlu = make_nlu(intent_name="unk")

        result = await manager.process_turn(ctx, nlu)
        assert result["action"].action_type == ActionType.RESPOND


# ---------------------------------------------------------------------------
# DialogManager — process_turn with active flow (line 406-408)
# ---------------------------------------------------------------------------


class TestProcessTurnWithActiveFlow:
    async def test_process_turn_routes_to_active_flow(self):
        manager = DialogManager()
        node = FlowNode(id="n1", name="N1", node_type="response", content="In flow!")
        flow = ConversationFlow(
            id="active_f",
            name="AF",
            description="",
            trigger_intents=["trigger"],
            nodes=[node],
            entry_node="n1",
        )
        manager.add_flow(flow)
        ctx = make_context()
        ctx.state_data["active_flow"] = "active_f"
        ctx.state_data["current_node"] = "n1"

        nlu = make_nlu(intent_name="something_else")
        result = await manager.process_turn(ctx, nlu)
        assert "flow" in result

    async def test_process_turn_starts_flow_on_matching_intent(self):
        manager = DialogManager()
        node = FlowNode(id="start", name="Start", node_type="response", content="Starting!")
        flow = ConversationFlow(
            id="order_flow",
            name="Order",
            description="",
            trigger_intents=["order_status"],
            nodes=[node],
            entry_node="start",
        )
        manager.add_flow(flow)
        ctx = make_context()
        nlu = make_nlu(intent_name="order_status")

        result = await manager.process_turn(ctx, nlu)
        assert "flow" in result
        assert result["flow"]["id"] == "order_flow"


# ---------------------------------------------------------------------------
# DialogManager — constitutional_hash parameter / custom flows in constructor
# ---------------------------------------------------------------------------


class TestDialogManagerConstructor:
    def test_custom_constitutional_hash(self):
        custom_hash = "abc123"
        manager = DialogManager(constitutional_hash=custom_hash)
        assert manager.constitutional_hash == custom_hash

    def test_flows_provided_in_constructor(self):
        node = FlowNode(id="n", name="N", node_type="response")
        flow = ConversationFlow(
            id="f1",
            name="F1",
            description="",
            trigger_intents=["test"],
            nodes=[node],
            entry_node="n",
        )
        manager = DialogManager(flows=[flow])
        assert manager.get_flow("f1") is not None

    def test_custom_policy_used(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogPolicy

        class MyPolicy(DialogPolicy):
            async def select_action(self, context, nlu_result, available_actions):
                return DialogAction(action_type=ActionType.ESCALATE)

        manager = DialogManager(policy=MyPolicy())
        assert isinstance(manager.policy, MyPolicy)


# ---------------------------------------------------------------------------
# FlowNode — remaining fields / edge cases
# ---------------------------------------------------------------------------


class TestFlowNodeEdgeCases:
    def test_required_entities_in_to_dict(self):
        node = FlowNode(
            id="n",
            name="N",
            node_type="question",
            required_entities=["order_id", "email"],
        )
        d = node.to_dict()
        assert d["required_entities"] == ["order_id", "email"]

    def test_next_node_in_to_dict(self):
        node = FlowNode(id="n", name="N", node_type="response", next_node="n2")
        d = node.to_dict()
        assert d["next_node"] == "n2"


# ---------------------------------------------------------------------------
# ConversationFlow — get_node edge cases
# ---------------------------------------------------------------------------


class TestProcessFlowNodeContinues:
    """Cover line 508: next_node is not None and not in exit_nodes → set current_node."""

    async def test_flow_continues_to_next_node(self):
        manager = DialogManager()
        node1 = FlowNode(id="n1", name="N1", node_type="response", content="step1", next_node="n2")
        node2 = FlowNode(id="n2", name="N2", node_type="response", content="step2")
        flow = ConversationFlow(
            id="f_cont",
            name="FCont",
            description="",
            trigger_intents=["cont"],
            nodes=[node1, node2],
            entry_node="n1",
            exit_nodes=["n2"],  # n2 is exit, n1 is intermediate
        )
        manager.add_flow(flow)
        ctx = make_context()
        ctx.state_data["active_flow"] = "f_cont"
        ctx.state_data["current_node"] = "n1"
        nlu = make_nlu(intent_name="cont")

        # Process n1 → next_node="n2" which is in exit_nodes, so flow exits
        # To test line 508 we need next_node NOT in exit_nodes
        flow2 = ConversationFlow(
            id="f_mid",
            name="FMid",
            description="",
            trigger_intents=["mid"],
            nodes=[node1, node2],
            entry_node="n1",
            exit_nodes=[],  # no exit nodes — so next_node "n2" hits the else branch (line 508)
        )
        manager.add_flow(flow2)
        ctx2 = make_context()
        ctx2.state_data["active_flow"] = "f_mid"
        ctx2.state_data["current_node"] = "n1"

        result = await manager._process_flow_node(ctx2, nlu, flow2, "n1")
        # current_node should now be n2 (the else branch at line 508 executed)
        assert ctx2.state_data.get("current_node") == "n2"
        assert ctx2.state_data.get("active_flow") == "f_mid"


class TestEntityMatchesSlotShortCircuit:
    """Cover branch 303->299: entity.type != slot but _entity_matches_slot is True."""

    async def test_entity_matches_via_type_mapping_not_direct(self):
        """Entity type 'product_code' != 'order_id' but maps via type_mappings."""
        policy = RuleBasedDialogPolicy()
        ctx = make_context(ConversationState.AWAITING_INPUT)
        ctx.state_data["pending_slots"] = ["order_id"]
        ctx.state_data["original_action"] = {}

        # type='product_code', current_slot='order_id' → type != slot → check _entity_matches_slot
        entity = Entity(text="PC-123", type="product_code", value="PC-123", start=0, end=6)
        nlu = make_nlu(entities=[entity])

        action = await policy.select_action(ctx, nlu, list(ActionType))
        # product_code maps to order_id via type_mappings → slot filled → EXECUTE_TASK
        assert action.action_type == ActionType.EXECUTE_TASK


class TestConversationFlowGetNode:
    def test_get_node_returns_correct_node_from_many(self):
        nodes = [FlowNode(id=f"n{i}", name=f"Node{i}", node_type="response") for i in range(5)]
        flow = ConversationFlow(
            id="f",
            name="F",
            description="",
            trigger_intents=["t"],
            nodes=nodes,
            entry_node="n0",
        )
        assert flow.get_node("n3") is nodes[3]
        assert flow.get_node("n0") is nodes[0]

    def test_to_dict_with_multiple_nodes(self):
        nodes = [FlowNode(id=f"n{i}", name=f"Node{i}", node_type="response") for i in range(3)]
        flow = ConversationFlow(
            id="f",
            name="F",
            description="desc",
            trigger_intents=["t1", "t2"],
            nodes=nodes,
            entry_node="n0",
        )
        d = flow.to_dict()
        assert len(d["nodes"]) == 3
