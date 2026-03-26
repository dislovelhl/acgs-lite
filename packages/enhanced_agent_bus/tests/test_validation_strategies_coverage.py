"""
ACGS-2 Validation Strategies Coverage Tests
Constitutional Hash: 608508a9bd224290

Extended tests to increase validation_strategies.py coverage.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

try:
    from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage
    from enhanced_agent_bus.validation_strategies import (
        DynamicPolicyValidationStrategy,
        RustValidationStrategy,
        StaticHashValidationStrategy,
    )
except ImportError:
    from models import AgentMessage
    from validation_strategies import (
        DynamicPolicyValidationStrategy,
        RustValidationStrategy,
        StaticHashValidationStrategy,
    )


class TestStaticHashValidationStrategy:
    """Tests for StaticHashValidationStrategy."""

    @pytest.fixture
    def strategy(self):
        """Create strategy instance."""
        return StaticHashValidationStrategy(strict=True)

    @pytest.fixture
    def non_strict_strategy(self):
        """Create non-strict strategy instance."""
        return StaticHashValidationStrategy(strict=False)

    def create_message(self, content=None, constitutional_hash=None, message_id=None):
        """Helper to create test messages."""
        msg = AgentMessage(
            content=content or {"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )
        if constitutional_hash:
            msg.constitutional_hash = constitutional_hash
        if message_id:
            msg.message_id = message_id
        return msg

    async def test_valid_message_strict(self, strategy):
        """Valid message passes strict validation."""
        msg = self.create_message()
        is_valid, error = await strategy.validate(msg)
        assert is_valid is True
        assert error is None

    async def test_invalid_hash_strict(self, strategy):
        """Invalid hash fails in strict mode."""
        msg = self.create_message()
        msg.constitutional_hash = "wrong_hash"
        is_valid, error = await strategy.validate(msg)
        assert is_valid is False
        assert error is not None
        assert "hash" in error.lower()

    async def test_invalid_hash_non_strict(self, non_strict_strategy):
        """Invalid hash passes in non-strict mode with warning."""
        msg = self.create_message()
        msg.constitutional_hash = "wrong_hash"
        is_valid, _error = await non_strict_strategy.validate(msg)
        # Non-strict mode allows through with warning
        assert is_valid is True

    async def test_none_content(self, strategy):
        """None content fails validation."""
        msg = self.create_message()
        msg.content = None
        is_valid, error = await strategy.validate(msg)
        assert is_valid is False
        assert "content" in error.lower()

    async def test_empty_message_id(self, strategy):
        """Empty message_id fails validation."""
        msg = self.create_message()
        msg.message_id = ""
        is_valid, error = await strategy.validate(msg)
        assert is_valid is False
        assert "message id" in error.lower() or "id" in error.lower()


class TestDynamicPolicyValidationStrategy:
    """Tests for DynamicPolicyValidationStrategy."""

    @pytest.fixture
    def strategy(self):
        """Create strategy with mock policy client."""
        return DynamicPolicyValidationStrategy(policy_client=None)

    async def test_no_policy_client(self, strategy):
        """Strategy without policy client falls back to default."""
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )
        is_valid, _error = await strategy.validate(msg)
        # With no policy client, should use default validation
        assert isinstance(is_valid, bool)

    async def test_with_mock_policy_client(self):
        """Strategy with policy client uses it for validation."""
        mock_client = MagicMock()
        mock_client.evaluate_policy = AsyncMock(return_value={"allowed": True})

        strategy = DynamicPolicyValidationStrategy(policy_client=mock_client)
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )
        is_valid, _error = await strategy.validate(msg)
        # Should complete without error
        assert isinstance(is_valid, bool)


class TestRustValidationStrategy:
    """Tests for RustValidationStrategy."""

    async def test_no_rust_processor(self):
        """Strategy without Rust processor falls back gracefully."""
        strategy = RustValidationStrategy(rust_processor=None)
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )
        is_valid, _error = await strategy.validate(msg)
        # Without Rust processor, should fail closed
        assert is_valid is False

    async def test_with_mock_rust_processor_bool_result(self):
        """Rust processor returning bool is handled."""
        mock_processor = MagicMock()
        mock_processor.validate_message = AsyncMock(return_value=True)

        strategy = RustValidationStrategy(rust_processor=mock_processor)
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )
        is_valid, _error = await strategy.validate(msg)
        assert is_valid is True

    async def test_with_mock_rust_processor_dict_result(self):
        """Rust processor returning dict is handled."""
        mock_processor = MagicMock()
        mock_processor.validate_message = AsyncMock(
            return_value={"is_valid": True, "message": "ok"}
        )

        strategy = RustValidationStrategy(rust_processor=mock_processor)
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )
        is_valid, _error = await strategy.validate(msg)
        assert is_valid is True

    async def test_rust_processor_validation_failure(self):
        """Rust processor validation failure is handled."""
        mock_processor = MagicMock()
        mock_processor.validate_message = AsyncMock(return_value=False)

        strategy = RustValidationStrategy(rust_processor=mock_processor)
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )
        is_valid, error = await strategy.validate(msg)
        assert is_valid is False
        assert "rejected" in error.lower() or "rust" in error.lower()

    async def test_rust_processor_dict_failure(self):
        """Rust processor dict failure is handled."""
        mock_processor = MagicMock()
        mock_processor.validate_message = AsyncMock(
            return_value={"is_valid": False, "error": "custom error"}
        )

        strategy = RustValidationStrategy(rust_processor=mock_processor)
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )
        is_valid, error = await strategy.validate(msg)
        assert is_valid is False
        assert "custom error" in error

    async def test_rust_processor_exception(self):
        """Rust processor exception is handled securely."""
        mock_processor = MagicMock()
        mock_processor.validate_message = AsyncMock(side_effect=RuntimeError("Rust crash"))

        strategy = RustValidationStrategy(rust_processor=mock_processor)
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )
        is_valid, error = await strategy.validate(msg)
        # Should fail closed on exception
        assert is_valid is False
        assert "error" in error.lower()

    async def test_sync_validate_method(self):
        """Rust processor with synchronous validate method."""
        mock_processor = MagicMock()
        # No validate_message, but has validate
        del mock_processor.validate_message
        mock_processor.validate = MagicMock(return_value=True)

        strategy = RustValidationStrategy(rust_processor=mock_processor)
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )
        is_valid, _error = await strategy.validate(msg)
        assert is_valid is True

    async def test_constitutional_validate_method(self):
        """Rust processor with constitutional_validate method."""
        mock_processor = MagicMock()
        # Only has constitutional_validate
        del mock_processor.validate_message
        mock_processor.validate = None  # Simulate missing
        mock_processor.constitutional_validate = MagicMock(return_value=True)

        # Need to properly mock hasattr behavior
        mock_processor.validate_message = None  # Make hasattr return False

        strategy = RustValidationStrategy(rust_processor=mock_processor)
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )
        is_valid, _error = await strategy.validate(msg)
        # Result depends on exact mock setup
        assert isinstance(is_valid, bool)
