"""
ACGS-2 Enhanced Agent Bus - OPA Guard Mixin Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the OPAGuardMixin class.
"""

from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

from enhanced_agent_bus.deliberation_layer.opa_guard_mixin import OPAGuardMixin

# =============================================================================
# Test Class Implementation
# =============================================================================


class _OPAGuardMixinImpl(OPAGuardMixin):
    """Concrete implementation of OPAGuardMixin for testing.

    Note: Prefixed with underscore to avoid pytest collection warning.
    """

    def __init__(self, opa_guard: Any | None = None, deliberation_timeout: int = 30):
        self.opa_guard = opa_guard
        self.deliberation_timeout = deliberation_timeout


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_opa_guard() -> MagicMock:
    """Create a mock OPA guard."""
    guard = MagicMock()
    guard.verify_action = AsyncMock()
    guard.collect_signatures = AsyncMock()
    guard.submit_signature = AsyncMock(return_value=True)
    guard.submit_for_review = AsyncMock()
    guard.submit_review = AsyncMock(return_value=True)
    guard.register_critic_agent = MagicMock()
    guard.unregister_critic_agent = MagicMock()
    guard.get_audit_log = MagicMock(return_value=[])
    return guard


@pytest.fixture
def mixin_with_guard(mock_opa_guard: MagicMock) -> _OPAGuardMixinImpl:
    """Create mixin with guard enabled."""
    return _OPAGuardMixinImpl(opa_guard=mock_opa_guard, deliberation_timeout=60)


@pytest.fixture
def mixin_without_guard() -> _OPAGuardMixinImpl:
    """Create mixin without guard (disabled)."""
    return _OPAGuardMixinImpl(opa_guard=None, deliberation_timeout=30)


# =============================================================================
# verify_action Tests
# =============================================================================


class TestVerifyAction:
    """Tests for verify_action method."""

    async def test_verify_action_with_guard(
        self, mixin_with_guard: _OPAGuardMixinImpl, mock_opa_guard: MagicMock
    ) -> None:
        """Test verify_action forwards to guard."""
        mock_result = MagicMock()
        mock_opa_guard.verify_action.return_value = mock_result

        action = {"type": "create", "resource": "policy"}
        context = {"priority": "high"}

        result = await mixin_with_guard.verify_action(
            agent_id="agent-1",
            action=action,
            context=context,
        )

        assert result is mock_result
        mock_opa_guard.verify_action.assert_called_once_with(
            agent_id="agent-1",
            action=action,
            context=context,
        )

    async def test_verify_action_without_context(
        self, mixin_with_guard: _OPAGuardMixinImpl, mock_opa_guard: MagicMock
    ) -> None:
        """Test verify_action with None context."""
        action = {"type": "delete"}

        await mixin_with_guard.verify_action(agent_id="agent-1", action=action, context=None)

        mock_opa_guard.verify_action.assert_called_once_with(
            agent_id="agent-1",
            action=action,
            context={},  # Default empty dict
        )

    async def test_verify_action_guard_disabled(
        self, mixin_without_guard: _OPAGuardMixinImpl
    ) -> None:
        """Test verify_action returns None when guard disabled."""
        result = await mixin_without_guard.verify_action(
            agent_id="agent-1",
            action={"type": "test"},
        )

        assert result is None


# =============================================================================
# collect_signatures Tests
# =============================================================================


class TestCollectSignatures:
    """Tests for collect_signatures method."""

    async def test_collect_signatures_with_guard(
        self, mixin_with_guard: _OPAGuardMixinImpl, mock_opa_guard: MagicMock
    ) -> None:
        """Test collect_signatures forwards to guard."""
        mock_result = MagicMock()
        mock_opa_guard.collect_signatures.return_value = mock_result

        result = await mixin_with_guard.collect_signatures(
            decision_id="dec-123",
            required_signers=["agent-1", "agent-2"],
            threshold=0.75,
            timeout=45,
        )

        assert result is mock_result
        mock_opa_guard.collect_signatures.assert_called_once_with(
            decision_id="dec-123",
            required_signers=["agent-1", "agent-2"],
            threshold=0.75,
            timeout=45,
        )

    async def test_collect_signatures_default_timeout(
        self, mixin_with_guard: _OPAGuardMixinImpl, mock_opa_guard: MagicMock
    ) -> None:
        """Test collect_signatures uses deliberation_timeout as default."""
        await mixin_with_guard.collect_signatures(
            decision_id="dec-123",
            required_signers=["agent-1"],
            timeout=None,
        )

        mock_opa_guard.collect_signatures.assert_called_once()
        call_args = mock_opa_guard.collect_signatures.call_args
        assert call_args.kwargs["timeout"] == 60  # deliberation_timeout

    async def test_collect_signatures_guard_disabled(
        self, mixin_without_guard: _OPAGuardMixinImpl
    ) -> None:
        """Test collect_signatures returns None when guard disabled."""
        result = await mixin_without_guard.collect_signatures(
            decision_id="dec-123",
            required_signers=["agent-1"],
        )

        assert result is None


# =============================================================================
# submit_signature Tests
# =============================================================================


class TestSubmitSignature:
    """Tests for submit_signature method."""

    async def test_submit_signature_with_guard(
        self, mixin_with_guard: _OPAGuardMixinImpl, mock_opa_guard: MagicMock
    ) -> None:
        """Test submit_signature forwards to guard."""
        result = await mixin_with_guard.submit_signature(
            decision_id="dec-123",
            signer_id="agent-1",
            reasoning="Approved after review",
            confidence=0.95,
        )

        assert result is True
        mock_opa_guard.submit_signature.assert_called_once_with(
            decision_id="dec-123",
            signer_id="agent-1",
            reasoning="Approved after review",
            confidence=0.95,
        )

    async def test_submit_signature_guard_disabled(
        self, mixin_without_guard: _OPAGuardMixinImpl
    ) -> None:
        """Test submit_signature returns False when guard disabled."""
        result = await mixin_without_guard.submit_signature(
            decision_id="dec-123",
            signer_id="agent-1",
        )

        assert result is False


# =============================================================================
# submit_for_review Tests
# =============================================================================


class TestSubmitForReview:
    """Tests for submit_for_review method."""

    async def test_submit_for_review_with_guard(
        self, mixin_with_guard: _OPAGuardMixinImpl, mock_opa_guard: MagicMock
    ) -> None:
        """Test submit_for_review forwards to guard."""
        mock_result = MagicMock()
        mock_opa_guard.submit_for_review.return_value = mock_result

        decision = {"action": "deploy", "environment": "production"}
        critic_agents = ["critic-1", "critic-2"]
        review_types = ["security", "compliance"]

        result = await mixin_with_guard.submit_for_review(
            decision=decision,
            critic_agents=critic_agents,
            review_types=review_types,
            timeout=120,
        )

        assert result is mock_result
        mock_opa_guard.submit_for_review.assert_called_once_with(
            decision=decision,
            critic_agents=critic_agents,
            review_types=review_types,
            timeout=120,
        )

    async def test_submit_for_review_default_timeout(
        self, mixin_with_guard: _OPAGuardMixinImpl, mock_opa_guard: MagicMock
    ) -> None:
        """Test submit_for_review uses deliberation_timeout as default."""
        await mixin_with_guard.submit_for_review(
            decision={"action": "test"},
            critic_agents=["critic-1"],
            timeout=None,
        )

        call_args = mock_opa_guard.submit_for_review.call_args
        assert call_args.kwargs["timeout"] == 60  # deliberation_timeout

    async def test_submit_for_review_guard_disabled(
        self, mixin_without_guard: _OPAGuardMixinImpl
    ) -> None:
        """Test submit_for_review returns None when guard disabled."""
        result = await mixin_without_guard.submit_for_review(
            decision={"action": "test"},
            critic_agents=["critic-1"],
        )

        assert result is None


# =============================================================================
# submit_critic_review Tests
# =============================================================================


class TestSubmitCriticReview:
    """Tests for submit_critic_review method."""

    async def test_submit_critic_review_with_guard(
        self, mixin_with_guard: _OPAGuardMixinImpl, mock_opa_guard: MagicMock
    ) -> None:
        """Test submit_critic_review forwards to guard."""
        result = await mixin_with_guard.submit_critic_review(
            decision_id="dec-123",
            critic_id="critic-1",
            verdict="approve",
            reasoning="No issues found",
            concerns=["minor performance impact"],
            recommendations=["add monitoring"],
            confidence=0.9,
        )

        assert result is True
        mock_opa_guard.submit_review.assert_called_once_with(
            decision_id="dec-123",
            critic_id="critic-1",
            verdict="approve",
            reasoning="No issues found",
            concerns=["minor performance impact"],
            recommendations=["add monitoring"],
            confidence=0.9,
        )

    async def test_submit_critic_review_minimal_args(
        self, mixin_with_guard: _OPAGuardMixinImpl, mock_opa_guard: MagicMock
    ) -> None:
        """Test submit_critic_review with minimal arguments."""
        await mixin_with_guard.submit_critic_review(
            decision_id="dec-123",
            critic_id="critic-1",
            verdict="reject",
        )

        mock_opa_guard.submit_review.assert_called_once()
        call_args = mock_opa_guard.submit_review.call_args
        assert call_args.kwargs["reasoning"] == ""
        assert call_args.kwargs["concerns"] is None
        assert call_args.kwargs["recommendations"] is None
        assert call_args.kwargs["confidence"] == 1.0

    async def test_submit_critic_review_guard_disabled(
        self, mixin_without_guard: _OPAGuardMixinImpl
    ) -> None:
        """Test submit_critic_review returns False when guard disabled."""
        result = await mixin_without_guard.submit_critic_review(
            decision_id="dec-123",
            critic_id="critic-1",
            verdict="approve",
        )

        assert result is False


# =============================================================================
# register_critic_agent Tests
# =============================================================================


class TestRegisterCriticAgent:
    """Tests for register_critic_agent method."""

    def test_register_critic_agent_with_guard(
        self, mixin_with_guard: _OPAGuardMixinImpl, mock_opa_guard: MagicMock
    ) -> None:
        """Test register_critic_agent forwards to guard."""
        callback = MagicMock()
        metadata = {"role": "security-reviewer"}

        mixin_with_guard.register_critic_agent(
            critic_id="critic-1",
            review_types=["security", "compliance"],
            callback=callback,
            metadata=metadata,
        )

        mock_opa_guard.register_critic_agent.assert_called_once_with(
            critic_id="critic-1",
            review_types=["security", "compliance"],
            callback=callback,
            metadata=metadata,
        )

    def test_register_critic_agent_guard_disabled(
        self, mixin_without_guard: _OPAGuardMixinImpl
    ) -> None:
        """Test register_critic_agent does nothing when guard disabled."""
        # Should not raise
        mixin_without_guard.register_critic_agent(
            critic_id="critic-1",
            review_types=["test"],
        )


# =============================================================================
# unregister_critic_agent Tests
# =============================================================================


class TestUnregisterCriticAgent:
    """Tests for unregister_critic_agent method."""

    def test_unregister_critic_agent_with_guard(
        self, mixin_with_guard: _OPAGuardMixinImpl, mock_opa_guard: MagicMock
    ) -> None:
        """Test unregister_critic_agent forwards to guard."""
        mixin_with_guard.unregister_critic_agent(critic_id="critic-1")

        mock_opa_guard.unregister_critic_agent.assert_called_once_with("critic-1")

    def test_unregister_critic_agent_guard_disabled(
        self, mixin_without_guard: _OPAGuardMixinImpl
    ) -> None:
        """Test unregister_critic_agent does nothing when guard disabled."""
        # Should not raise
        mixin_without_guard.unregister_critic_agent(critic_id="critic-1")


# =============================================================================
# get_guard_audit_log Tests
# =============================================================================


class TestGetGuardAuditLog:
    """Tests for get_guard_audit_log method."""

    def test_get_guard_audit_log_with_guard(
        self, mixin_with_guard: _OPAGuardMixinImpl, mock_opa_guard: MagicMock
    ) -> None:
        """Test get_guard_audit_log forwards to guard."""
        mock_entries = [{"id": "1", "action": "verify"}, {"id": "2", "action": "sign"}]
        mock_opa_guard.get_audit_log.return_value = mock_entries

        result = mixin_with_guard.get_guard_audit_log(
            limit=50,
            offset=10,
            agent_id="agent-1",
        )

        assert result == mock_entries
        mock_opa_guard.get_audit_log.assert_called_once_with(
            limit=50,
            offset=10,
            agent_id="agent-1",
        )

    def test_get_guard_audit_log_defaults(
        self, mixin_with_guard: _OPAGuardMixinImpl, mock_opa_guard: MagicMock
    ) -> None:
        """Test get_guard_audit_log with default arguments."""
        mixin_with_guard.get_guard_audit_log()

        mock_opa_guard.get_audit_log.assert_called_once_with(
            limit=100,
            offset=0,
            agent_id=None,
        )

    def test_get_guard_audit_log_guard_disabled(
        self, mixin_without_guard: _OPAGuardMixinImpl
    ) -> None:
        """Test get_guard_audit_log returns empty list when guard disabled."""
        result = mixin_without_guard.get_guard_audit_log()

        assert result == []


# =============================================================================
# Integration Tests
# =============================================================================


class TestOPAGuardMixinIntegration:
    """Integration tests for OPAGuardMixin."""

    async def test_full_verification_workflow(self, mock_opa_guard: MagicMock) -> None:
        """Test complete verification workflow."""
        mixin = _OPAGuardMixinImpl(opa_guard=mock_opa_guard, deliberation_timeout=30)

        # Setup mock return values
        mock_opa_guard.verify_action.return_value = MagicMock(allowed=True)
        mock_opa_guard.collect_signatures.return_value = MagicMock(
            collected=2, required=2, complete=True
        )

        # Verify action
        verify_result = await mixin.verify_action(
            agent_id="agent-1",
            action={"type": "deploy"},
        )
        assert verify_result.allowed is True

        # Collect signatures
        sig_result = await mixin.collect_signatures(
            decision_id="dec-123",
            required_signers=["agent-1", "agent-2"],
        )
        assert sig_result.complete is True

        # Submit signatures
        for signer in ["agent-1", "agent-2"]:
            result = await mixin.submit_signature(
                decision_id="dec-123",
                signer_id=signer,
            )
            assert result is True

    def test_all_methods_disabled_gracefully(self) -> None:
        """Test all methods handle disabled guard gracefully."""
        mixin = _OPAGuardMixinImpl(opa_guard=None)

        # None of these should raise
        mixin.register_critic_agent("critic-1", ["test"])
        mixin.unregister_critic_agent("critic-1")

        audit_log = mixin.get_guard_audit_log()
        assert audit_log == []
