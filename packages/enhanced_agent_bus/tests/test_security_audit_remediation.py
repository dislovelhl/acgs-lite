"""
Security Audit Remediation Regression Tests
Focus: VULN-001 (Rust Validation Bypass) and VULN-002 (OPA Fail-Open)

Constitutional Hash: 608508a9bd224290
"""

import pytest

pytest.importorskip("enhanced_agent_bus.sdpc")


from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage

from ..deliberation_layer.integration import DeliberationLayer
from ..deliberation_layer.opa_guard import GuardDecision, GuardResult
from ..validation_strategies import RustValidationStrategy


class TestSecurityRemediation:
    async def test_vuln_001_rust_validation_fail_closed_on_error(self):
        """
        VULN-001 Regression Test:
        Verify RustValidationStrategy fails closed (returns False) when logic raises exception.
        """
        # Setup mock processor that raises exception
        mock_processor = MagicMock()
        mock_processor.validate_message = AsyncMock(side_effect=RuntimeError("Rust panic!"))

        strategy = RustValidationStrategy(rust_processor=mock_processor, fail_closed=True)
        message = AgentMessage(
            message_id="msg-123",
            content="test",
            sender_id="agent-1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        # Execute
        is_valid, error = await strategy.validate(message)

        # Assert Fail-Closed
        assert is_valid is False
        assert "Rust validation error" in error

    async def test_vuln_001_rust_validation_fail_closed_missing_method(self):
        """
        VULN-001 Regression Test:
        Verify RustValidationStrategy fails closed when no validation method exists.
        """
        # Setup mock processor with NO validation methods
        mock_processor = MagicMock(spec=[])

        strategy = RustValidationStrategy(rust_processor=mock_processor, fail_closed=True)
        message = AgentMessage(
            message_id="msg-124",
            content="test",
            sender_id="agent-1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        # Execute
        is_valid, error = await strategy.validate(message)

        # Assert Fail-Closed
        assert is_valid is False
        assert "fail closed" in error

    async def test_vuln_002_opa_fail_closed_on_error(self):
        """
        VULN-002 Regression Test:
        Verify DeliberationLayer returns GuardDecision.DENY when OPA Guard raises exception.
        """
        # Setup mock OPA Guard that raises exception
        mock_opa_guard = AsyncMock()
        mock_opa_guard.verify_action.side_effect = RuntimeError("OPA Connection Refused")

        layer = DeliberationLayer(
            enable_opa_guard=True,
            opa_guard=mock_opa_guard,
            # Mock other dependencies to avoid complexity
            impact_scorer=MagicMock(),
            adaptive_router=MagicMock(),
            deliberation_queue=MagicMock(),
        )

        message = AgentMessage(
            message_id="msg-125",
            content="dangerous_action",
            sender_id="rogue_agent",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        # Execute - this calls _verify_with_opa_guard internally
        # We need to test _verify_with_opa_guard directly or process_message
        # Attempting process_message which captures the exception and returns dict
        # Wait, process_message catches Exceptions?
        # Let's look at integration.py code.
        # _verify_with_opa_guard catches Exception and returns GuardResult.
        # So we should call _verify_with_opa_guard directly to see the GuardResult.

        result = await layer._verify_with_opa_guard(message)

        # Assert Fail-Closed
        assert isinstance(result, GuardResult)
        assert result.decision == GuardDecision.DENY
        assert result.is_allowed is False
        assert len(result.validation_errors) > 0
        assert "OPA Connection Refused" in result.validation_errors[0]
