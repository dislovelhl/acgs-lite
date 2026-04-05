"""
Coverage tests for:
  - ai_assistant/integration.py (47 missing lines)
  - ai_assistant/dialog.py (45 missing lines)
  - constitutional/review_api.py (46 missing lines)

asyncio_mode = "auto" -- no @pytest.mark.asyncio decorator needed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_context(
    state: str = "initialized",
    state_data: dict | None = None,
    slots: dict | None = None,
):
    """Build a ConversationContext without triggering heavy imports at module top."""
    from enhanced_agent_bus.ai_assistant.context import (
        ConversationContext,
        ConversationState,
    )

    return ConversationContext(
        user_id="user-1",
        session_id="sess-1",
        conversation_state=ConversationState(state),
        state_data=state_data or {},
        slots=slots or {},
    )


def _make_nlu(
    intent_name: str = "greeting",
    confidence: float = 0.95,
    entities: list | None = None,
    requires_clarification: bool = False,
):
    from enhanced_agent_bus.ai_assistant.nlu import Entity, Intent, NLUResult

    return NLUResult(
        original_text="test",
        primary_intent=Intent(name=intent_name, confidence=confidence),
        entities=entities or [],
        requires_clarification=requires_clarification,
    )


def _make_nlu_no_intent():
    from enhanced_agent_bus.ai_assistant.nlu import NLUResult

    return NLUResult(original_text="test", primary_intent=None)


# ===================================================================
# 1. ai_assistant/integration.py
# ===================================================================


class TestGovernanceDecision:
    """GovernanceDecision.to_dict() coverage."""

    def test_to_dict_fields(self):
        from enhanced_agent_bus.ai_assistant.integration import GovernanceDecision

        gd = GovernanceDecision(
            is_allowed=True,
            reason="ok",
            policy_id="pol-1",
            verification_status="verified",
            confidence=0.9,
            metadata={"k": "v"},
        )
        d = gd.to_dict()
        assert d["is_allowed"] is True
        assert d["reason"] == "ok"
        assert d["policy_id"] == "pol-1"
        assert d["confidence"] == 0.9
        assert "timestamp" in d

    def test_to_dict_defaults(self):
        from enhanced_agent_bus.ai_assistant.integration import GovernanceDecision

        gd = GovernanceDecision(is_allowed=False, reason="nope")
        d = gd.to_dict()
        assert d["policy_id"] is None
        assert d["confidence"] == 0.0


class TestAgentBusIntegrationInitialize:
    """AgentBusIntegration.initialize() branches."""

    async def test_initialize_no_bus_available(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        with patch("enhanced_agent_bus.ai_assistant.integration.AGENT_BUS_AVAILABLE", False):
            integration = AgentBusIntegration()
            result = await integration.initialize()
            assert result is False

    async def test_initialize_no_agent_bus_instance(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        with patch("enhanced_agent_bus.ai_assistant.integration.AGENT_BUS_AVAILABLE", True):
            integration = AgentBusIntegration(agent_bus=None)
            result = await integration.initialize()
            assert result is False

    async def test_initialize_success(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        with patch("enhanced_agent_bus.ai_assistant.integration.AGENT_BUS_AVAILABLE", True):
            integration = AgentBusIntegration(agent_bus=MagicMock())
            result = await integration.initialize()
            assert result is True


class TestAgentBusIntegrationHandleIncoming:
    """handle_incoming_message branches."""

    async def test_hash_mismatch_governance_enabled(self):
        from enhanced_agent_bus.ai_assistant.integration import (
            AgentBusIntegration,
            IntegrationConfig,
        )

        config = IntegrationConfig(enable_governance=True)
        integration = AgentBusIntegration(config=config)

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "bad_hash"
        mock_msg.from_agent = "other"
        mock_msg.priority = MagicMock()
        mock_msg.conversation_id = "conv-1"
        mock_msg.message_type = MagicMock(value="command")

        mock_vr = MagicMock(is_valid=False)
        with patch(
            "enhanced_agent_bus.ai_assistant.integration.validate_constitutional_hash",
            return_value=mock_vr,
        ):
            result = await integration.handle_incoming_message(mock_msg)
            # Should return error response
            assert result is not None

    async def test_hash_valid_with_handler(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()

        handler = AsyncMock(return_value=MagicMock())
        integration.register_handler("command", handler)

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "valid"
        mock_msg.message_type = MagicMock(value="command")

        mock_vr = MagicMock(is_valid=True)
        with patch(
            "enhanced_agent_bus.ai_assistant.integration.validate_constitutional_hash",
            return_value=mock_vr,
        ):
            result = await integration.handle_incoming_message(mock_msg)
            handler.assert_awaited_once_with(mock_msg)

    async def test_hash_valid_no_handler(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "valid"
        mock_msg.message_type = MagicMock(value="unknown_type")

        mock_vr = MagicMock(is_valid=True)
        with patch(
            "enhanced_agent_bus.ai_assistant.integration.validate_constitutional_hash",
            return_value=mock_vr,
        ):
            result = await integration.handle_incoming_message(mock_msg)
            assert result is None

    async def test_message_type_str_fallback(self):
        """When message_type has no .value attr, uses str()."""
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "valid"
        # message_type without .value
        mock_msg.message_type = "raw_string"

        mock_vr = MagicMock(is_valid=True)
        with patch(
            "enhanced_agent_bus.ai_assistant.integration.validate_constitutional_hash",
            return_value=mock_vr,
        ):
            result = await integration.handle_incoming_message(mock_msg)
            assert result is None


class TestValidateUserMessage:
    """validate_user_message branches."""

    async def test_valid_message_dict_content(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        ctx = _make_context()

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "valid"
        mock_msg.content = {"text": "Hello world"}

        mock_vr = MagicMock(is_valid=True)
        with patch(
            "enhanced_agent_bus.ai_assistant.integration.validate_constitutional_hash",
            return_value=mock_vr,
        ):
            result = await integration.validate_user_message(mock_msg, ctx)
            assert result.is_valid is True

    async def test_empty_message(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        ctx = _make_context()

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "valid"
        mock_msg.content = {"text": ""}

        mock_vr = MagicMock(is_valid=True)
        with patch(
            "enhanced_agent_bus.ai_assistant.integration.validate_constitutional_hash",
            return_value=mock_vr,
        ):
            result = await integration.validate_user_message(mock_msg, ctx)
            assert result.is_valid is False
            assert "Empty message" in result.errors

    async def test_message_too_long(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        ctx = _make_context()

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "valid"
        mock_msg.content = {"text": "x" * 10001}

        mock_vr = MagicMock(is_valid=True)
        with patch(
            "enhanced_agent_bus.ai_assistant.integration.validate_constitutional_hash",
            return_value=mock_vr,
        ):
            result = await integration.validate_user_message(mock_msg, ctx)
            assert result.is_valid is False
            assert "Message too long" in result.errors

    async def test_content_is_string(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        ctx = _make_context()

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "valid"
        mock_msg.content = "plain string content"

        mock_vr = MagicMock(is_valid=True)
        with patch(
            "enhanced_agent_bus.ai_assistant.integration.validate_constitutional_hash",
            return_value=mock_vr,
        ):
            result = await integration.validate_user_message(mock_msg, ctx)
            assert result.is_valid is True

    async def test_hash_mismatch(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        ctx = _make_context()

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "bad"
        mock_msg.content = {"text": "hello"}

        mock_vr = MagicMock(is_valid=False)
        with patch(
            "enhanced_agent_bus.ai_assistant.integration.validate_constitutional_hash",
            return_value=mock_vr,
        ):
            result = await integration.validate_user_message(mock_msg, ctx)
            assert result.is_valid is False
            assert "Constitutional hash mismatch" in result.errors


class TestProcessNLUResult:
    """process_nlu_result branches."""

    async def test_governance_blocked(self):
        """When governance blocks, DialogAction constructor gets metadata= kwarg which
        is not a valid field. This is a known bug in the source (type: ignore comment).
        The TypeError propagates since process_nlu_result has no try/except."""
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        ctx = _make_context()
        nlu = _make_nlu("some_intent")

        with patch.object(
            integration,
            "_check_governance",
            new_callable=AsyncMock,
            return_value={"is_allowed": False, "reason": "blocked"},
        ):
            with pytest.raises(TypeError, match="metadata"):
                await integration.process_nlu_result(nlu, ctx)

    async def test_governance_disabled(self):
        from enhanced_agent_bus.ai_assistant.integration import (
            AgentBusIntegration,
            IntegrationConfig,
        )

        config = IntegrationConfig(enable_governance=False)
        integration = AgentBusIntegration(config=config)
        ctx = _make_context()
        nlu = _make_nlu("help")

        result = await integration.process_nlu_result(nlu, ctx)
        assert result.action_type.value == "respond"
        assert "help" in result.response_template.lower()

    async def test_unknown_intent(self):
        from enhanced_agent_bus.ai_assistant.integration import (
            AgentBusIntegration,
            IntegrationConfig,
        )

        config = IntegrationConfig(enable_governance=False)
        integration = AgentBusIntegration(config=config)
        ctx = _make_context()
        nlu = _make_nlu("random_intent")

        result = await integration.process_nlu_result(nlu, ctx)
        assert result.response_template == "I'm processing your request."

    async def test_no_intent(self):
        from enhanced_agent_bus.ai_assistant.integration import (
            AgentBusIntegration,
            IntegrationConfig,
        )

        config = IntegrationConfig(enable_governance=False)
        integration = AgentBusIntegration(config=config)
        ctx = _make_context()
        nlu = _make_nlu_no_intent()

        result = await integration.process_nlu_result(nlu, ctx)
        assert result.response_template == "I'm processing your request."


class TestSendMessage:
    """send_message branches."""

    async def test_bus_not_available(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        with patch("enhanced_agent_bus.ai_assistant.integration.AGENT_BUS_AVAILABLE", False):
            integration = AgentBusIntegration()
            result = await integration.send_message("target", "hello")
            assert result is None

    async def test_bus_no_instance(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        with patch("enhanced_agent_bus.ai_assistant.integration.AGENT_BUS_AVAILABLE", True):
            integration = AgentBusIntegration(agent_bus=None)
            result = await integration.send_message("target", "hello")
            assert result is None

    async def test_send_string_content_success(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        mock_bus = AsyncMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"ok": True}
        mock_bus.send_message.return_value = mock_result

        with patch("enhanced_agent_bus.ai_assistant.integration.AGENT_BUS_AVAILABLE", True):
            integration = AgentBusIntegration(agent_bus=mock_bus)
            result = await integration.send_message("target", "hello")
            assert result == {"ok": True}

    async def test_send_dict_content_with_context(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        mock_bus = AsyncMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"ok": True}
        mock_bus.send_message.return_value = mock_result
        ctx = _make_context(state="active")

        with patch("enhanced_agent_bus.ai_assistant.integration.AGENT_BUS_AVAILABLE", True):
            integration = AgentBusIntegration(agent_bus=mock_bus)
            result = await integration.send_message("target", {"data": 1}, context=ctx)
            assert result == {"ok": True}

    async def test_send_returns_none_when_result_none(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        mock_bus = AsyncMock()
        mock_bus.send_message.return_value = None

        with patch("enhanced_agent_bus.ai_assistant.integration.AGENT_BUS_AVAILABLE", True):
            integration = AgentBusIntegration(agent_bus=mock_bus)
            result = await integration.send_message("target", "hello")
            assert result is None

    async def test_send_error_handling(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        mock_bus = AsyncMock()
        mock_bus.send_message.side_effect = RuntimeError("bus down")

        with patch("enhanced_agent_bus.ai_assistant.integration.AGENT_BUS_AVAILABLE", True):
            integration = AgentBusIntegration(agent_bus=mock_bus)
            result = await integration.send_message("target", "hello")
            assert result is None


class TestCheckGovernance:
    """_check_governance and check_governance branches."""

    async def test_governance_disabled(self):
        from enhanced_agent_bus.ai_assistant.integration import (
            AgentBusIntegration,
            IntegrationConfig,
        )

        config = IntegrationConfig(enable_governance=False)
        integration = AgentBusIntegration(config=config)
        ctx = _make_context()
        nlu = _make_nlu()

        result = await integration._check_governance(nlu, ctx)
        assert result["is_allowed"] is True

    async def test_governance_verified(self):
        from enhanced_agent_bus._compat.policy.models import VerificationStatus
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        mock_policy = MagicMock()
        mock_policy.verification_status = VerificationStatus.VERIFIED
        mock_policy.policy_id = "pol-123"
        mock_policy.confidence_score = 0.95
        mock_policy.smt_formulation = "smt"

        integration = AgentBusIntegration()
        ctx = _make_context()
        nlu = _make_nlu()

        with (
            patch.object(
                integration.policy_generator,
                "generate_verified_policy",
                new_callable=AsyncMock,
                return_value=mock_policy,
            ),
            patch("enhanced_agent_bus.ai_assistant.integration.get_audit_ledger", None),
        ):
            result = await integration._check_governance(nlu, ctx)
            assert result["is_allowed"] is True
            assert result["confidence"] == 0.95

    async def test_governance_failed_verification(self):
        from enhanced_agent_bus._compat.policy.models import VerificationStatus
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        mock_policy = MagicMock()
        mock_policy.verification_status = VerificationStatus.FAILED
        mock_policy.policy_id = "pol-fail"
        mock_policy.confidence_score = 0.2
        mock_policy.smt_formulation = "smt"

        integration = AgentBusIntegration()
        ctx = _make_context()
        nlu = _make_nlu()

        with (
            patch.object(
                integration.policy_generator,
                "generate_verified_policy",
                new_callable=AsyncMock,
                return_value=mock_policy,
            ),
            patch("enhanced_agent_bus.ai_assistant.integration.get_audit_ledger", None),
        ):
            result = await integration._check_governance(nlu, ctx)
            assert result["is_allowed"] is False

    async def test_governance_with_audit_ledger(self):
        from enhanced_agent_bus._compat.policy.models import VerificationStatus
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        mock_policy = MagicMock()
        mock_policy.verification_status = VerificationStatus.VERIFIED
        mock_policy.policy_id = "pol-aud"
        mock_policy.confidence_score = 0.9
        mock_policy.smt_formulation = "smt"

        mock_ledger = AsyncMock()
        mock_get_ledger = AsyncMock(return_value=mock_ledger)

        integration = AgentBusIntegration()
        ctx = _make_context()
        nlu = _make_nlu()

        with (
            patch.object(
                integration.policy_generator,
                "generate_verified_policy",
                new_callable=AsyncMock,
                return_value=mock_policy,
            ),
            patch(
                "enhanced_agent_bus.ai_assistant.integration.get_audit_ledger",
                mock_get_ledger,
            ),
        ):
            result = await integration._check_governance(nlu, ctx)
            assert result["is_allowed"] is True
            mock_ledger.add_validation_result.assert_awaited_once()

    async def test_governance_audit_ledger_failure(self):
        from enhanced_agent_bus._compat.policy.models import VerificationStatus
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        mock_policy = MagicMock()
        mock_policy.verification_status = VerificationStatus.VERIFIED
        mock_policy.policy_id = "pol-aud2"
        mock_policy.confidence_score = 0.9
        mock_policy.smt_formulation = "smt"

        mock_ledger = AsyncMock()
        mock_ledger.add_validation_result.side_effect = RuntimeError("audit fail")
        mock_get_ledger = AsyncMock(return_value=mock_ledger)

        integration = AgentBusIntegration()
        ctx = _make_context()
        nlu = _make_nlu()

        with (
            patch.object(
                integration.policy_generator,
                "generate_verified_policy",
                new_callable=AsyncMock,
                return_value=mock_policy,
            ),
            patch(
                "enhanced_agent_bus.ai_assistant.integration.get_audit_ledger",
                mock_get_ledger,
            ),
        ):
            # Should not raise, audit error is logged and swallowed
            result = await integration._check_governance(nlu, ctx)
            assert result["is_allowed"] is True

    async def test_governance_exception_fail_closed(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        ctx = _make_context()
        nlu = _make_nlu()

        with patch.object(
            integration.policy_generator,
            "generate_verified_policy",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            result = await integration._check_governance(nlu, ctx)
            assert result["is_allowed"] is False
            assert "Governance system error" in result["reason"]

    async def test_check_governance_public_alias(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        ctx = _make_context()
        nlu = _make_nlu()

        with patch.object(
            integration,
            "_check_governance",
            new_callable=AsyncMock,
            return_value={"is_allowed": True, "reason": "ok", "confidence": 0.8},
        ):
            decision = await integration.check_governance(nlu, ctx)
            assert decision.is_allowed is True
            assert decision.reason == "ok"


class TestValidateMessageAlias:
    """validate_message backwards-compat alias."""

    async def test_validate_message_string(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        ctx = _make_context()

        mock_vr = MagicMock(is_valid=True)
        with patch(
            "enhanced_agent_bus.ai_assistant.integration.validate_constitutional_hash",
            return_value=mock_vr,
        ):
            result = await integration.validate_message("hello world", ctx)
            assert result.is_valid is True


class TestShutdown:
    async def test_shutdown_no_handlers(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        await integration.shutdown()

    async def test_shutdown_with_handlers(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        integration._handlers = {"a": 1}
        await integration.shutdown()
        assert len(integration._handlers) == 0


class TestExecuteTask:
    async def test_execute_task_success(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        mock_result = MagicMock()
        mock_result.content = {"data": "ok"}

        mock_vr = MagicMock(is_valid=True)
        handler = AsyncMock(return_value=mock_result)
        integration.register_handler("command", handler)

        with patch(
            "enhanced_agent_bus.ai_assistant.integration.validate_constitutional_hash",
            return_value=mock_vr,
        ):
            result = await integration.execute_task("test_task", {"param": "val"}, context=None)
            # handler should have been called through handle_incoming_message
            assert result["success"] is True

    async def test_execute_task_no_result(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        mock_vr = MagicMock(is_valid=True)

        with patch(
            "enhanced_agent_bus.ai_assistant.integration.validate_constitutional_hash",
            return_value=mock_vr,
        ):
            result = await integration.execute_task("test_task", {"param": "val"})
            assert result["success"] is False

    async def test_execute_task_exception(self):
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()

        with patch.object(
            integration,
            "handle_incoming_message",
            new_callable=AsyncMock,
            side_effect=RuntimeError("task error"),
        ):
            result = await integration.execute_task("test_task", {"param": "val"})
            assert result["success"] is False
            assert "task error" in result["error"]


# ===================================================================
# 2. ai_assistant/dialog.py
# ===================================================================


class TestFlowNodeToDict:
    def test_callable_content(self):
        from enhanced_agent_bus.ai_assistant.dialog import FlowNode

        def my_func():
            pass

        node = FlowNode(id="n1", name="Node1", node_type="action", content=my_func)
        d = node.to_dict()
        assert "my_func" in d["content"]

    def test_string_content(self):
        from enhanced_agent_bus.ai_assistant.dialog import FlowNode

        node = FlowNode(id="n1", name="Node1", node_type="response", content="Hello")
        d = node.to_dict()
        assert d["content"] == "Hello"

    def test_none_content(self):
        from enhanced_agent_bus.ai_assistant.dialog import FlowNode

        node = FlowNode(id="n1", name="Node1", node_type="response", content=None)
        d = node.to_dict()
        assert d["content"] is None


class TestConversationFlow:
    def test_get_node_found(self):
        from enhanced_agent_bus.ai_assistant.dialog import ConversationFlow, FlowNode

        n1 = FlowNode(id="n1", name="Node1", node_type="response")
        n2 = FlowNode(id="n2", name="Node2", node_type="question")
        flow = ConversationFlow(
            id="f1",
            name="Flow1",
            description="test",
            trigger_intents=["greeting"],
            nodes=[n1, n2],
            entry_node="n1",
        )
        assert flow.get_node("n2") is n2

    def test_get_node_not_found(self):
        from enhanced_agent_bus.ai_assistant.dialog import ConversationFlow, FlowNode

        n1 = FlowNode(id="n1", name="Node1", node_type="response")
        flow = ConversationFlow(
            id="f1",
            name="Flow1",
            description="test",
            trigger_intents=["greeting"],
            nodes=[n1],
            entry_node="n1",
        )
        assert flow.get_node("missing") is None

    def test_to_dict(self):
        from enhanced_agent_bus.ai_assistant.dialog import ConversationFlow, FlowNode

        n1 = FlowNode(id="n1", name="Node1", node_type="response", content="Hi")
        flow = ConversationFlow(
            id="f1",
            name="Flow1",
            description="test",
            trigger_intents=["greeting"],
            nodes=[n1],
            entry_node="n1",
            exit_nodes=["n1"],
        )
        d = flow.to_dict()
        assert d["id"] == "f1"
        assert len(d["nodes"]) == 1


class TestRuleBasedDialogPolicy:
    async def test_select_action_greeting(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(state="active")
        nlu = _make_nlu("greeting")

        result = await policy.select_action(ctx, nlu, [])
        assert result.action_type.value == "respond"
        assert "Hello" in result.response_template

    async def test_select_action_farewell(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(state="active")
        nlu = _make_nlu("farewell")

        result = await policy.select_action(ctx, nlu, [])
        assert result.action_type.value == "end_conversation"

    async def test_select_action_unknown_intent(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(state="active")
        nlu = _make_nlu("totally_unknown_xyz")

        result = await policy.select_action(ctx, nlu, [])
        assert result.action_type.value == "clarify"

    async def test_select_action_requires_clarification(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(state="active")
        nlu = _make_nlu("totally_unknown_xyz", requires_clarification=True)

        result = await policy.select_action(ctx, nlu, [])
        assert result.action_type.value == "clarify"

    async def test_select_action_order_status_missing_slot(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(state="active")
        nlu = _make_nlu("order_status")

        result = await policy.select_action(ctx, nlu, [])
        assert result.action_type.value == "fill_slot"
        assert "order_id" in result.required_slots

    async def test_select_action_order_status_slot_filled_by_entity(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy
        from enhanced_agent_bus.ai_assistant.nlu import Entity

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(state="active")
        entity = Entity(text="12345", type="order_id", value="12345", start=0, end=5)
        nlu = _make_nlu("order_status", entities=[entity])

        result = await policy.select_action(ctx, nlu, [])
        # Slot is filled by entity, so should proceed (not fill_slot)
        assert result.action_type.value == "fill_slot"  # Original action is fill_slot type

    async def test_select_action_order_status_slot_filled_by_context(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(state="active")
        ctx.set_slot("order_id", "ORD-123")
        nlu = _make_nlu("order_status")

        result = await policy.select_action(ctx, nlu, [])
        # Slot is filled in context
        assert result.action_type.value == "fill_slot"

    async def test_awaiting_input_slot_filling(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy
        from enhanced_agent_bus.ai_assistant.nlu import Entity

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(
            state="awaiting_input",
            state_data={"pending_slots": ["order_id"], "original_action": {}},
        )
        entity = Entity(text="12345", type="order_id", value="12345", start=0, end=5)
        nlu = _make_nlu("order_status", entities=[entity])

        result = await policy.select_action(ctx, nlu, [])
        assert result.action_type.value == "execute_task"

    async def test_awaiting_input_slot_filling_multiple_slots(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy
        from enhanced_agent_bus.ai_assistant.nlu import Entity

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(
            state="awaiting_input",
            state_data={
                "pending_slots": ["order_id", "email"],
                "original_action": {},
            },
        )
        entity = Entity(text="12345", type="order_id", value="12345", start=0, end=5)
        nlu = _make_nlu("order_status", entities=[entity])

        result = await policy.select_action(ctx, nlu, [])
        assert result.action_type.value == "fill_slot"
        assert "email" in result.required_slots

    async def test_awaiting_input_no_matching_entity(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(
            state="awaiting_input",
            state_data={"pending_slots": ["order_id"]},
        )
        nlu = _make_nlu("greeting")

        result = await policy.select_action(ctx, nlu, [])
        assert result.action_type.value == "fill_slot"
        assert "valid" in result.response_template.lower()

    async def test_awaiting_input_string_entity_skipped(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(
            state="awaiting_input",
            state_data={"pending_slots": ["order_id"]},
        )
        # entities as strings should be skipped
        nlu = _make_nlu("greeting", entities=["string_entity"])

        result = await policy.select_action(ctx, nlu, [])
        assert result.action_type.value == "fill_slot"

    async def test_awaiting_confirmation_confirm(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(
            state="awaiting_confirmation",
            state_data={"pending_action": {"task": "do_something"}},
        )
        nlu = _make_nlu("confirmation")

        result = await policy.select_action(ctx, nlu, [])
        assert result.action_type.value == "execute_task"

    async def test_awaiting_confirmation_denial(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(state="awaiting_confirmation")
        nlu = _make_nlu("denial")

        result = await policy.select_action(ctx, nlu, [])
        assert result.action_type.value == "clarify"

    async def test_awaiting_confirmation_neither(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(state="awaiting_confirmation")
        nlu = _make_nlu("greeting")

        result = await policy.select_action(ctx, nlu, [])
        assert result.action_type.value == "confirm"

    async def test_no_intent(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        ctx = _make_context(state="active")
        nlu = _make_nlu_no_intent()

        result = await policy.select_action(ctx, nlu, [])
        assert result.action_type.value == "clarify"

    def test_entity_matches_slot_known(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        entity = MagicMock()
        entity.type = "email"
        assert policy._entity_matches_slot(entity, "email") is True

    def test_entity_matches_slot_fallback(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        entity = MagicMock()
        entity.type = "custom_type"
        assert policy._entity_matches_slot(entity, "custom_type") is True

    def test_entity_matches_slot_no_match(self):
        from enhanced_agent_bus.ai_assistant.dialog import RuleBasedDialogPolicy

        policy = RuleBasedDialogPolicy()
        entity = MagicMock()
        entity.type = "phone"
        assert policy._entity_matches_slot(entity, "email") is False

    def test_create_slot_filling_action_known_slot(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ActionType,
            DialogAction,
            RuleBasedDialogPolicy,
        )

        policy = RuleBasedDialogPolicy()
        original = DialogAction(action_type=ActionType.EXECUTE_TASK)
        result = policy._create_slot_filling_action(["email"], original)
        assert "email" in result.response_template.lower()

    def test_create_slot_filling_action_unknown_slot(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ActionType,
            DialogAction,
            RuleBasedDialogPolicy,
        )

        policy = RuleBasedDialogPolicy()
        original = DialogAction(action_type=ActionType.EXECUTE_TASK)
        result = policy._create_slot_filling_action(["widget_id"], original)
        assert "widget_id" in result.response_template


class TestDialogManager:
    async def test_process_turn_no_flow_respond(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager

        mgr = DialogManager()
        ctx = _make_context(state="active")
        nlu = _make_nlu("greeting")

        result = await mgr.process_turn(ctx, nlu)
        assert "action" in result
        assert "result" in result

    async def test_process_turn_triggers_flow(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ConversationFlow,
            DialogManager,
            FlowNode,
        )

        node = FlowNode(id="n1", name="Greet", node_type="response", content="Hi!")
        flow = ConversationFlow(
            id="f1",
            name="Greeting Flow",
            description="test",
            trigger_intents=["greeting"],
            nodes=[node],
            entry_node="n1",
            exit_nodes=["n1"],
        )
        mgr = DialogManager(flows=[flow])
        ctx = _make_context(state="active")
        nlu = _make_nlu("greeting")

        result = await mgr.process_turn(ctx, nlu)
        assert "flow" in result
        assert result["flow"]["id"] == "f1"

    async def test_process_turn_active_flow(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ConversationFlow,
            DialogManager,
            FlowNode,
        )

        node = FlowNode(id="n1", name="Question", node_type="question", content="What?")
        flow = ConversationFlow(
            id="f1",
            name="Q Flow",
            description="test",
            trigger_intents=["ask"],
            nodes=[node],
            entry_node="n1",
        )
        mgr = DialogManager(flows=[flow])
        ctx = _make_context(
            state="active",
            state_data={"active_flow": "f1", "current_node": "n1"},
        )
        nlu = _make_nlu("ask")

        result = await mgr.process_turn(ctx, nlu)
        assert "flow" in result

    async def test_process_flow_turn_flow_not_found(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager

        mgr = DialogManager()
        ctx = _make_context(
            state="active",
            state_data={"active_flow": "nonexistent", "current_node": "n1"},
        )
        nlu = _make_nlu("greeting")

        result = await mgr.process_turn(ctx, nlu)
        # Should exit flow gracefully and use policy
        assert "action" in result

    async def test_process_flow_node_not_found(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ConversationFlow,
            DialogManager,
            FlowNode,
        )

        node = FlowNode(id="n1", name="N1", node_type="response", content="Hi")
        flow = ConversationFlow(
            id="f1",
            name="F1",
            description="test",
            trigger_intents=[],
            nodes=[node],
            entry_node="n1",
        )
        mgr = DialogManager(flows=[flow])
        ctx = _make_context(
            state="active",
            state_data={"active_flow": "f1", "current_node": "missing_node"},
        )
        nlu = _make_nlu("test")

        result = await mgr.process_turn(ctx, nlu)
        assert "lost track" in result["result"]["response"]

    async def test_execute_node_response_callable(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager, FlowNode

        async def my_content(ctx, nlu):
            return "dynamic response"

        node = FlowNode(id="n1", name="N1", node_type="response", content=my_content)
        mgr = DialogManager()
        ctx = _make_context()
        nlu = _make_nlu()

        result = await mgr._execute_node(node, ctx, nlu)
        assert result["response"] == "dynamic response"

    async def test_execute_node_validation_callable(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager, FlowNode

        async def validate(ctx, nlu):
            return False

        node = FlowNode(id="n1", name="N1", node_type="validation", content=validate)
        mgr = DialogManager()
        ctx = _make_context()
        nlu = _make_nlu()

        result = await mgr._execute_node(node, ctx, nlu)
        assert result["valid"] is False

    async def test_execute_node_validation_not_callable(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager, FlowNode

        node = FlowNode(id="n1", name="N1", node_type="validation", content="not callable")
        mgr = DialogManager()
        ctx = _make_context()
        nlu = _make_nlu()

        result = await mgr._execute_node(node, ctx, nlu)
        assert result["valid"] is True

    async def test_execute_node_action_callable(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager, FlowNode

        async def action_fn(ctx, nlu):
            return {"done": True}

        node = FlowNode(id="n1", name="N1", node_type="action", content=action_fn)
        mgr = DialogManager()
        ctx = _make_context()
        nlu = _make_nlu()

        result = await mgr._execute_node(node, ctx, nlu)
        assert result["result"] == {"done": True}

    async def test_execute_node_action_not_callable(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager, FlowNode

        node = FlowNode(id="n1", name="N1", node_type="action", content="not callable")
        mgr = DialogManager()
        ctx = _make_context()
        nlu = _make_nlu()

        result = await mgr._execute_node(node, ctx, nlu)
        assert result["result"] is None

    async def test_execute_node_condition_callable(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager, FlowNode

        async def cond_fn(ctx, nlu):
            return "branch_a"

        node = FlowNode(id="n1", name="N1", node_type="condition", content=cond_fn)
        mgr = DialogManager()
        ctx = _make_context()
        nlu = _make_nlu()

        result = await mgr._execute_node(node, ctx, nlu)
        assert result["condition"] == "branch_a"

    async def test_execute_node_condition_not_callable(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager, FlowNode

        node = FlowNode(id="n1", name="N1", node_type="condition", content="not callable")
        mgr = DialogManager()
        ctx = _make_context()
        nlu = _make_nlu()

        result = await mgr._execute_node(node, ctx, nlu)
        assert result["condition"] is True

    async def test_execute_node_unknown_type(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager, FlowNode

        node = FlowNode(id="n1", name="N1", node_type="unknown_xyz")
        mgr = DialogManager()
        ctx = _make_context()
        nlu = _make_nlu()

        result = await mgr._execute_node(node, ctx, nlu)
        assert result["type"] == "unknown"

    def test_determine_next_node_validation_success(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager, FlowNode

        mgr = DialogManager()
        node = FlowNode(
            id="n1",
            name="N1",
            node_type="validation",
            transitions={"success": "n2", "failure": "n3"},
        )
        result = {"type": "validation", "valid": True}
        nlu = _make_nlu()

        next_id = mgr._determine_next_node(node, result, nlu)
        assert next_id == "n2"

    def test_determine_next_node_validation_failure(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager, FlowNode

        mgr = DialogManager()
        node = FlowNode(
            id="n1",
            name="N1",
            node_type="validation",
            transitions={"success": "n2", "failure": "n3"},
        )
        result = {"type": "validation", "valid": False}
        nlu = _make_nlu()

        next_id = mgr._determine_next_node(node, result, nlu)
        assert next_id == "n3"

    def test_determine_next_node_condition(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager, FlowNode

        mgr = DialogManager()
        node = FlowNode(
            id="n1",
            name="N1",
            node_type="condition",
            transitions={"branch_a": "n2", "branch_b": "n3"},
        )
        result = {"type": "condition", "condition": "branch_a"}
        nlu = _make_nlu()

        next_id = mgr._determine_next_node(node, result, nlu)
        assert next_id == "n2"

    def test_determine_next_node_intent_transition(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager, FlowNode

        mgr = DialogManager()
        node = FlowNode(
            id="n1",
            name="N1",
            node_type="response",
            transitions={"greeting": "n2"},
        )
        result = {"type": "response"}
        nlu = _make_nlu("greeting")

        next_id = mgr._determine_next_node(node, result, nlu)
        assert next_id == "n2"

    def test_determine_next_node_fallback(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager, FlowNode

        mgr = DialogManager()
        node = FlowNode(id="n1", name="N1", node_type="response", next_node="n_default")
        result = {"type": "response"}
        nlu = _make_nlu("greeting")

        next_id = mgr._determine_next_node(node, result, nlu)
        assert next_id == "n_default"

    async def test_execute_action_custom_handler(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ActionType,
            DialogAction,
            DialogManager,
        )

        mgr = DialogManager()
        custom_handler = AsyncMock(return_value={"custom": True})
        mgr.register_action_handler(ActionType.RESPOND, custom_handler)

        action = DialogAction(action_type=ActionType.RESPOND, response_template="test")
        ctx = _make_context()
        nlu = _make_nlu()

        result = await mgr._execute_action(action, ctx, nlu)
        assert result == {"custom": True}

    async def test_execute_action_ask_question(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ActionType,
            DialogAction,
            DialogManager,
        )

        mgr = DialogManager()
        action = DialogAction(action_type=ActionType.ASK_QUESTION, response_template="What?")
        ctx = _make_context(state="active")
        nlu = _make_nlu()

        result = await mgr._execute_action(action, ctx, nlu)
        assert result["awaiting"] == "answer"

    async def test_execute_action_confirm(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ActionType,
            DialogAction,
            DialogManager,
        )

        mgr = DialogManager()
        action = DialogAction(
            action_type=ActionType.CONFIRM,
            response_template="Sure?",
            parameters={"task": "x"},
        )
        ctx = _make_context(state="active")
        nlu = _make_nlu()

        result = await mgr._execute_action(action, ctx, nlu)
        assert result["awaiting"] == "confirmation"

    async def test_execute_action_fill_slot(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ActionType,
            DialogAction,
            DialogManager,
        )

        mgr = DialogManager()
        action = DialogAction(
            action_type=ActionType.FILL_SLOT,
            response_template="Provide order_id",
            required_slots=["order_id"],
            parameters={"original_action": {"task": "lookup"}},
        )
        ctx = _make_context(state="active")
        nlu = _make_nlu()

        result = await mgr._execute_action(action, ctx, nlu)
        assert result["awaiting"] == "slot_value"

    async def test_execute_action_execute_task(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ActionType,
            DialogAction,
            DialogManager,
        )

        mgr = DialogManager()
        action = DialogAction(action_type=ActionType.EXECUTE_TASK, response_template="Done")
        ctx = _make_context(state="active")
        nlu = _make_nlu()

        result = await mgr._execute_action(action, ctx, nlu)
        assert result["task_executed"] is True

    async def test_execute_action_escalate(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ActionType,
            DialogAction,
            DialogManager,
        )

        mgr = DialogManager()
        action = DialogAction(action_type=ActionType.ESCALATE, response_template="Escalating")
        ctx = _make_context(state="active")
        nlu = _make_nlu()

        result = await mgr._execute_action(action, ctx, nlu)
        assert result["escalated"] is True

    async def test_execute_action_end_conversation(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ActionType,
            DialogAction,
            DialogManager,
        )

        mgr = DialogManager()
        action = DialogAction(action_type=ActionType.END_CONVERSATION, response_template="Bye")
        ctx = _make_context(state="active")
        nlu = _make_nlu()

        result = await mgr._execute_action(action, ctx, nlu)
        assert result["ended"] is True

    async def test_execute_action_wait_for_input_fallback(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ActionType,
            DialogAction,
            DialogManager,
        )

        mgr = DialogManager()
        action = DialogAction(action_type=ActionType.WAIT_FOR_INPUT, response_template="Waiting...")
        ctx = _make_context(state="active")
        nlu = _make_nlu()

        result = await mgr._execute_action(action, ctx, nlu)
        assert result["response"] == "Waiting..."

    def test_update_context_state_execute_task(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ActionType,
            DialogAction,
            DialogManager,
        )

        mgr = DialogManager()
        ctx = _make_context(
            state="awaiting_input",
            state_data={"pending_slots": ["x"], "pending_action": {"y": 1}},
        )
        action = DialogAction(action_type=ActionType.EXECUTE_TASK)
        mgr._update_context_state(ctx, action, {})
        assert "pending_slots" not in ctx.state_data
        assert "pending_action" not in ctx.state_data

    def test_update_context_state_non_execute(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ActionType,
            DialogAction,
            DialogManager,
        )

        mgr = DialogManager()
        ctx = _make_context(state="active", state_data={"pending_slots": ["x"]})
        action = DialogAction(action_type=ActionType.RESPOND)
        mgr._update_context_state(ctx, action, {})
        assert "pending_slots" in ctx.state_data

    def test_add_get_remove_flow(self):
        from enhanced_agent_bus.ai_assistant.dialog import (
            ConversationFlow,
            DialogManager,
            FlowNode,
        )

        mgr = DialogManager()
        node = FlowNode(id="n1", name="N1", node_type="response")
        flow = ConversationFlow(
            id="f1",
            name="F1",
            description="test",
            trigger_intents=[],
            nodes=[node],
            entry_node="n1",
        )
        mgr.add_flow(flow)
        assert mgr.get_flow("f1") is flow
        mgr.remove_flow("f1")
        assert mgr.get_flow("f1") is None
        mgr.remove_flow("nonexistent")  # no error

    def test_find_matching_flow_no_intent(self):
        from enhanced_agent_bus.ai_assistant.dialog import DialogManager

        mgr = DialogManager()
        nlu = _make_nlu_no_intent()
        assert mgr._find_matching_flow(nlu) is None


# ===================================================================
# 3. constitutional/review_api.py
# ===================================================================


class TestReviewAPIHealthCheck:
    async def test_health_check(self):
        from enhanced_agent_bus.constitutional.review_api import health_check

        result = await health_check()
        assert result["status"] == "healthy"
        assert "constitutional_hash" in result


def _make_test_app():
    """Create a minimal FastAPI app with the review_api router for testing."""
    from fastapi import FastAPI

    from enhanced_agent_bus.constitutional.review_api import router

    app = FastAPI()
    app.include_router(router)
    return app


def _make_amendment_fixture(**kwargs):
    from enhanced_agent_bus.constitutional.amendment_model import (
        AmendmentProposal,
        AmendmentStatus,
    )

    defaults = {
        "proposed_changes": {"key": "value"},
        "justification": "This is a sufficient justification",
        "proposer_agent_id": "agent-1",
        "target_version": "1.0.0",
        "status": AmendmentStatus.PROPOSED,
        "approval_chain": [],
        "requires_deliberation": False,
        "governance_metrics_before": {},
        "governance_metrics_after": {},
    }
    defaults.update(kwargs)
    # Allow passing status as string
    if isinstance(defaults["status"], str):
        defaults["status"] = AmendmentStatus(defaults["status"])
    return AmendmentProposal(**defaults)


class TestListAmendments:
    async def test_list_amendments_success(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.list_amendments.return_value = ([], 0)
        mock_storage_cls.return_value = mock_storage

        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            mock_storage_cls,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/v1/constitutional/amendments")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 0

    async def test_list_amendments_with_status_filter(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.list_amendments.return_value = ([], 0)
        mock_storage_cls.return_value = mock_storage

        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            mock_storage_cls,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/v1/constitutional/amendments?status=proposed")
            assert resp.status_code == 200

    async def test_list_amendments_invalid_status(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage_cls.return_value = mock_storage

        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            mock_storage_cls,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/v1/constitutional/amendments?status=invalid_xyz")
            assert resp.status_code == 400

    async def test_list_amendments_invalid_order_by(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage_cls.return_value = mock_storage

        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            mock_storage_cls,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/v1/constitutional/amendments?order_by=invalid_field")
            assert resp.status_code == 400

    async def test_list_amendments_invalid_order(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage_cls.return_value = mock_storage

        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            mock_storage_cls,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/v1/constitutional/amendments?order=invalid_dir")
            assert resp.status_code == 400

    async def test_list_amendments_storage_error(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.list_amendments.side_effect = RuntimeError("db error")
        mock_storage_cls.return_value = mock_storage

        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            mock_storage_cls,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/v1/constitutional/amendments")
            assert resp.status_code == 500


class TestGetAmendment:
    async def test_get_amendment_not_found(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = None
        mock_storage_cls.return_value = mock_storage

        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            mock_storage_cls,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/v1/constitutional/amendments/nonexistent-id")
            assert resp.status_code == 404

    async def test_get_amendment_success_no_diff(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        amendment = _make_amendment_fixture()

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = None
        mock_storage_cls.return_value = mock_storage

        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            mock_storage_cls,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/v1/constitutional/amendments/test-id?include_diff=false")
            assert resp.status_code == 200
            data = resp.json()
            assert data["diff"] is None

    async def test_get_amendment_with_governance_metrics(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        amendment = _make_amendment_fixture(
            governance_metrics_before={"accuracy": 0.8, "fairness": 0.9},
            governance_metrics_after={"accuracy": 0.85, "fairness": 0.88},
        )

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = None
        mock_storage_cls.return_value = mock_storage

        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            mock_storage_cls,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/v1/constitutional/amendments/test-id?include_diff=false")
            assert resp.status_code == 200
            data = resp.json()
            assert data["governance_metrics_delta"]["accuracy"] == pytest.approx(0.05)
            assert data["governance_metrics_delta"]["fairness"] == pytest.approx(-0.02)

    async def test_get_amendment_with_diff_dict_changes(self):
        from httpx import ASGITransport, AsyncClient

        from enhanced_agent_bus.constitutional.diff_engine import SemanticDiff
        from enhanced_agent_bus.constitutional.version_model import (
            ConstitutionalVersion,
        )

        app = _make_test_app()
        amendment = _make_amendment_fixture(
            proposed_changes={"section": "new content"},
        )

        mock_version = ConstitutionalVersion(
            version_id="v1", version="1.0.0", content={"data": "old"}
        )
        mock_diff = SemanticDiff(
            from_version="1.0.0",
            to_version="1.0.1",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="abc",
            to_hash="def",
            hash_changed=True,
        )

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = mock_version
        mock_storage_cls.return_value = mock_storage

        mock_diff_engine_cls = MagicMock()
        mock_diff_engine = AsyncMock()
        mock_diff_engine.compute_diff_from_content.return_value = mock_diff
        mock_diff_engine_cls.return_value = mock_diff_engine

        with (
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalDiffEngine",
                mock_diff_engine_cls,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/v1/constitutional/amendments/test-id")
            assert resp.status_code == 200
            data = resp.json()
            assert data["diff"] is not None

    async def test_get_amendment_with_diff_string_changes(self):
        from httpx import ASGITransport, AsyncClient

        from enhanced_agent_bus.constitutional.diff_engine import SemanticDiff
        from enhanced_agent_bus.constitutional.version_model import (
            ConstitutionalVersion,
        )

        app = _make_test_app()
        amendment = _make_amendment_fixture(proposed_changes={"_raw": "version-2"})
        # Override proposed_changes to a string type for this branch
        amendment.proposed_changes = "2.0.0"  # type: ignore[assignment]

        mock_version = ConstitutionalVersion(
            version_id="v1", version="1.0.0", content={"data": "old"}
        )
        mock_diff = SemanticDiff(
            from_version="1.0.0",
            to_version="2.0.0",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="abc",
            to_hash="def",
            hash_changed=True,
        )

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = mock_version
        mock_storage_cls.return_value = mock_storage

        mock_diff_engine_cls = MagicMock()
        mock_diff_engine = AsyncMock()
        mock_diff_engine.compute_diff.return_value = mock_diff
        mock_diff_engine_cls.return_value = mock_diff_engine

        with (
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalDiffEngine",
                mock_diff_engine_cls,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/v1/constitutional/amendments/test-id")
            assert resp.status_code == 200
            data = resp.json()
            assert data["diff"] is not None

    async def test_get_amendment_storage_error(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.side_effect = RuntimeError("db fail")
        mock_storage_cls.return_value = mock_storage

        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            mock_storage_cls,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/v1/constitutional/amendments/test-id")
            assert resp.status_code == 500


class TestApproveAmendment:
    async def test_approve_maci_denied(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": False}

        with patch(
            "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
            return_value=mock_enforcer,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/amendments/amend-1/approve",
                    json={"approver_agent_id": "agent-1"},
                )
            assert resp.status_code == 403

    async def test_approve_not_found(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": True}

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = None
        mock_storage_cls.return_value = mock_storage

        with (
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/amendments/amend-1/approve",
                    json={"approver_agent_id": "agent-1"},
                )
            assert resp.status_code == 404

    async def test_approve_wrong_status(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        amendment = _make_amendment_fixture(status="approved")

        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": True}

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage_cls.return_value = mock_storage

        with (
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/amendments/amend-1/approve",
                    json={"approver_agent_id": "agent-1"},
                )
            assert resp.status_code == 400

    async def test_approve_success_fully_approved(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        amendment = _make_amendment_fixture(status="under_review")

        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": True}

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage_cls.return_value = mock_storage

        mock_hitl_cls = MagicMock()
        mock_hitl = MagicMock()
        chain_config = MagicMock()
        chain_config.required_approvals = 1
        mock_hitl._determine_approval_chain.return_value = chain_config
        mock_hitl_cls.return_value = mock_hitl

        mock_audit_cls = MagicMock()
        mock_audit = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        with (
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalHITLIntegration",
                mock_hitl_cls,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.AuditClient",
                mock_audit_cls,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.AuditClientConfig",
                MagicMock(),
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/amendments/amend-1/approve",
                    json={"approver_agent_id": "judge-1", "comments": "LGTM"},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "approved" in data["next_steps"][0].lower()

    async def test_approve_success_pending(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        amendment = _make_amendment_fixture(status="under_review")

        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": True}

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage_cls.return_value = mock_storage

        mock_hitl_cls = MagicMock()
        mock_hitl = MagicMock()
        chain_config = MagicMock()
        chain_config.required_approvals = 3
        mock_hitl._determine_approval_chain.return_value = chain_config
        mock_hitl_cls.return_value = mock_hitl

        mock_audit_cls = MagicMock()
        mock_audit = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        with (
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalHITLIntegration",
                mock_hitl_cls,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.AuditClient",
                mock_audit_cls,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.AuditClientConfig",
                MagicMock(),
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/amendments/amend-1/approve",
                    json={"approver_agent_id": "judge-1"},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert "waiting" in data["next_steps"][0].lower()

    async def test_approve_storage_error(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": True}

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.side_effect = RuntimeError("db error")
        mock_storage_cls.return_value = mock_storage

        with (
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/amendments/amend-1/approve",
                    json={"approver_agent_id": "judge-1"},
                )
            assert resp.status_code == 500


class TestRejectAmendment:
    async def test_reject_maci_denied(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": False}

        with patch(
            "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
            return_value=mock_enforcer,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/amendments/amend-1/reject",
                    json={
                        "rejector_agent_id": "agent-1",
                        "reason": "Not good enough for the constitution",
                    },
                )
            assert resp.status_code == 403

    async def test_reject_not_found(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": True}

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = None
        mock_storage_cls.return_value = mock_storage

        with (
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/amendments/amend-1/reject",
                    json={
                        "rejector_agent_id": "judge-1",
                        "reason": "Not good enough for the constitution",
                    },
                )
            assert resp.status_code == 404

    async def test_reject_wrong_status(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        amendment = _make_amendment_fixture(status="approved")

        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": True}

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage_cls.return_value = mock_storage

        with (
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/amendments/amend-1/reject",
                    json={
                        "rejector_agent_id": "judge-1",
                        "reason": "Not good enough for the constitution",
                    },
                )
            assert resp.status_code == 400

    async def test_reject_success(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        amendment = _make_amendment_fixture(status="under_review")

        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": True}

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage_cls.return_value = mock_storage

        mock_audit_cls = MagicMock()
        mock_audit = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        with (
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.AuditClient",
                mock_audit_cls,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.AuditClientConfig",
                MagicMock(),
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/amendments/amend-1/reject",
                    json={
                        "rejector_agent_id": "judge-1",
                        "reason": "Not good enough for the constitution",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "rejected" in data["next_steps"][0].lower()

    async def test_reject_storage_error(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": True}

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.side_effect = RuntimeError("db error")
        mock_storage_cls.return_value = mock_storage

        with (
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/amendments/amend-1/reject",
                    json={
                        "rejector_agent_id": "judge-1",
                        "reason": "Not good enough for the constitution",
                    },
                )
            assert resp.status_code == 500


class TestRollbackToVersion:
    async def test_rollback_not_available(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()

        with patch("enhanced_agent_bus.constitutional.review_api.ROLLBACK_AVAILABLE", False):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/versions/v-1/rollback",
                    json={
                        "requester_agent_id": "judge-1",
                        "justification": "Emergency rollback needed due to governance degradation",
                    },
                )
            assert resp.status_code == 501

    async def test_rollback_maci_denied(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": False}

        with (
            patch("enhanced_agent_bus.constitutional.review_api.ROLLBACK_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/versions/v-1/rollback",
                    json={
                        "requester_agent_id": "judge-1",
                        "justification": "Emergency rollback needed due to governance degradation",
                    },
                )
            assert resp.status_code == 403

    async def test_rollback_target_not_found(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": True}

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_version.return_value = None
        mock_storage_cls.return_value = mock_storage

        with (
            patch("enhanced_agent_bus.constitutional.review_api.ROLLBACK_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/versions/v-missing/rollback",
                    json={
                        "requester_agent_id": "judge-1",
                        "justification": "Emergency rollback needed due to governance degradation",
                    },
                )
            assert resp.status_code == 404

    async def test_rollback_no_active_version(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": True}

        mock_target = MagicMock()
        mock_target.version_id = "v-target"

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_version.return_value = mock_target
        mock_storage.get_active_version.return_value = None
        mock_storage_cls.return_value = mock_storage

        with (
            patch("enhanced_agent_bus.constitutional.review_api.ROLLBACK_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/versions/v-target/rollback",
                    json={
                        "requester_agent_id": "judge-1",
                        "justification": "Emergency rollback needed due to governance degradation",
                    },
                )
            assert resp.status_code == 500

    async def test_rollback_same_version(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.return_value = {"allowed": True}

        mock_version = MagicMock()
        mock_version.version_id = "v-same"

        mock_storage_cls = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.get_version.return_value = mock_version
        mock_storage.get_active_version.return_value = mock_version
        mock_storage_cls.return_value = mock_storage

        with (
            patch("enhanced_agent_bus.constitutional.review_api.ROLLBACK_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
                mock_storage_cls,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/versions/v-same/rollback",
                    json={
                        "requester_agent_id": "judge-1",
                        "justification": "Emergency rollback needed due to governance degradation",
                    },
                )
            assert resp.status_code == 400

    async def test_rollback_general_error(self):
        from httpx import ASGITransport, AsyncClient

        app = _make_test_app()
        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.side_effect = RuntimeError("unexpected")

        with (
            patch("enhanced_agent_bus.constitutional.review_api.ROLLBACK_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.constitutional.review_api.MACIEnforcer",
                return_value=mock_enforcer,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/constitutional/versions/v-1/rollback",
                    json={
                        "requester_agent_id": "judge-1",
                        "justification": "Emergency rollback needed due to governance degradation",
                    },
                )
            assert resp.status_code == 500
