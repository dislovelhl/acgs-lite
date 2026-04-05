"""
ACGS-2 Enhanced Agent Bus - Validation Strategies Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for validation strategy implementations.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage
from enhanced_agent_bus.validation_strategies import (
    CompositeValidationStrategy,
    DynamicPolicyValidationStrategy,
    OPAValidationStrategy,
    RustValidationStrategy,
    StaticHashValidationStrategy,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def valid_message() -> AgentMessage:
    """Create a valid test message."""
    return AgentMessage(
        from_agent="test-sender",
        to_agent="test-receiver",
        content={"action": "test", "data": "hello"},
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


@pytest.fixture
def invalid_hash_message() -> AgentMessage:
    """Create a message with invalid constitutional hash."""
    return AgentMessage(
        from_agent="test-sender",
        to_agent="test-receiver",
        content={"action": "test"},
        constitutional_hash="invalid-hash-value",
    )


@pytest.fixture
def mock_policy_client() -> AsyncMock:
    """Create a mock policy client."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_opa_client() -> AsyncMock:
    """Create a mock OPA client."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_rust_processor() -> MagicMock:
    """Create a mock Rust processor."""
    processor = MagicMock()
    return processor


# =============================================================================
# StaticHashValidationStrategy Tests
# =============================================================================


class TestStaticHashValidationStrategy:
    """Tests for StaticHashValidationStrategy."""

    async def test_valid_message_passes(self, valid_message: AgentMessage) -> None:
        """Test that a valid message passes validation."""
        strategy = StaticHashValidationStrategy(strict=True)
        is_valid, error = await strategy.validate(valid_message)
        assert is_valid is True
        assert error is None

    async def test_invalid_hash_fails_in_strict_mode(
        self, invalid_hash_message: AgentMessage
    ) -> None:
        """Test that invalid hash fails in strict mode."""
        strategy = StaticHashValidationStrategy(strict=True)
        is_valid, error = await strategy.validate(invalid_hash_message)
        assert is_valid is False
        assert "Constitutional hash mismatch" in error

    async def test_invalid_hash_passes_in_non_strict_mode(
        self, invalid_hash_message: AgentMessage
    ) -> None:
        """Test that invalid hash passes in non-strict mode."""
        strategy = StaticHashValidationStrategy(strict=False)
        is_valid, error = await strategy.validate(invalid_hash_message)
        assert is_valid is True
        assert error is None

    async def test_missing_message_id_fails(self) -> None:
        """Test that missing message ID fails validation."""
        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            content={"action": "test"},
        )
        message.message_id = ""  # Clear the message ID

        strategy = StaticHashValidationStrategy()
        is_valid, error = await strategy.validate(message)
        assert is_valid is False
        assert "Message ID is required" in error

    async def test_none_content_fails(self) -> None:
        """Test that None content fails validation."""
        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
        )
        message.content = None  # Set content to None

        strategy = StaticHashValidationStrategy()
        is_valid, error = await strategy.validate(message)
        assert is_valid is False
        assert "content cannot be None" in error


# =============================================================================
# DynamicPolicyValidationStrategy Tests
# =============================================================================


class TestDynamicPolicyValidationStrategy:
    """Tests for DynamicPolicyValidationStrategy."""

    async def test_no_policy_client_fails(self, valid_message: AgentMessage) -> None:
        """Test that missing policy client fails."""
        strategy = DynamicPolicyValidationStrategy(policy_client=None)
        is_valid, error = await strategy.validate(valid_message)
        assert is_valid is False
        assert "Policy client not available" in error

    async def test_valid_policy_response(
        self, valid_message: AgentMessage, mock_policy_client: AsyncMock
    ) -> None:
        """Test successful policy validation."""
        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.errors = []
        mock_policy_client.validate_message_signature.return_value = mock_result

        strategy = DynamicPolicyValidationStrategy(policy_client=mock_policy_client)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is True
        assert error is None
        mock_policy_client.validate_message_signature.assert_called_once()

    async def test_invalid_policy_response(
        self, valid_message: AgentMessage, mock_policy_client: AsyncMock
    ) -> None:
        """Test failed policy validation."""
        mock_result = MagicMock()
        mock_result.is_valid = False
        mock_result.errors = ["Policy violation: unauthorized action"]
        mock_policy_client.validate_message_signature.return_value = mock_result

        strategy = DynamicPolicyValidationStrategy(policy_client=mock_policy_client)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is False
        assert "unauthorized action" in error

    async def test_policy_client_exception(
        self, valid_message: AgentMessage, mock_policy_client: AsyncMock
    ) -> None:
        """Test handling of policy client exception."""
        mock_policy_client.validate_message_signature.side_effect = ConnectionError(
            "Connection failed"
        )

        strategy = DynamicPolicyValidationStrategy(policy_client=mock_policy_client)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is False
        assert "Dynamic validation error" in error
        assert "Connection failed" in error


# =============================================================================
# OPAValidationStrategy Tests
# =============================================================================


class TestOPAValidationStrategy:
    """Tests for OPAValidationStrategy."""

    async def test_no_opa_client_fails(self, valid_message: AgentMessage) -> None:
        """Test that missing OPA client fails."""
        strategy = OPAValidationStrategy(opa_client=None)
        is_valid, error = await strategy.validate(valid_message)
        assert is_valid is False
        assert "OPA client not available" in error

    async def test_valid_opa_response(
        self, valid_message: AgentMessage, mock_opa_client: AsyncMock
    ) -> None:
        """Test successful OPA validation."""
        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.errors = []
        mock_opa_client.validate_constitutional.return_value = mock_result

        strategy = OPAValidationStrategy(opa_client=mock_opa_client)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is True
        assert error is None
        mock_opa_client.validate_constitutional.assert_called_once()

    async def test_invalid_opa_response(
        self, valid_message: AgentMessage, mock_opa_client: AsyncMock
    ) -> None:
        """Test failed OPA validation."""
        mock_result = MagicMock()
        mock_result.is_valid = False
        mock_result.errors = ["OPA policy denied: role not authorized"]
        mock_opa_client.validate_constitutional.return_value = mock_result

        strategy = OPAValidationStrategy(opa_client=mock_opa_client)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is False
        assert "role not authorized" in error

    async def test_opa_client_exception(
        self, valid_message: AgentMessage, mock_opa_client: AsyncMock
    ) -> None:
        """Test handling of OPA client exception."""
        mock_opa_client.validate_constitutional.side_effect = RuntimeError("OPA timeout")

        strategy = OPAValidationStrategy(opa_client=mock_opa_client)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is False
        assert "OPA validation error" in error
        assert "OPA timeout" in error


# =============================================================================
# RustValidationStrategy Tests
# =============================================================================


class TestRustValidationStrategy:
    """Tests for RustValidationStrategy."""

    async def test_no_rust_processor_fails(self, valid_message: AgentMessage) -> None:
        """Test that missing Rust processor fails."""
        strategy = RustValidationStrategy(rust_processor=None)
        is_valid, error = await strategy.validate(valid_message)
        assert is_valid is False
        assert "Rust processor not available" in error

    async def test_validate_message_returns_true(
        self, valid_message: AgentMessage, mock_rust_processor: MagicMock
    ) -> None:
        """Test successful validation with validate_message returning True."""
        mock_rust_processor.validate_message = AsyncMock(return_value=True)

        strategy = RustValidationStrategy(rust_processor=mock_rust_processor)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is True
        assert error is None

    async def test_validate_message_returns_false(
        self, valid_message: AgentMessage, mock_rust_processor: MagicMock
    ) -> None:
        """Test failed validation with validate_message returning False."""
        mock_rust_processor.validate_message = AsyncMock(return_value=False)

        strategy = RustValidationStrategy(rust_processor=mock_rust_processor)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is False
        assert "rejected message" in error

    async def test_validate_message_returns_dict_valid(
        self, valid_message: AgentMessage, mock_rust_processor: MagicMock
    ) -> None:
        """Test successful validation with dict result."""
        mock_rust_processor.validate_message = AsyncMock(return_value={"is_valid": True})

        strategy = RustValidationStrategy(rust_processor=mock_rust_processor)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is True
        assert error is None

    async def test_validate_message_returns_dict_invalid(
        self, valid_message: AgentMessage, mock_rust_processor: MagicMock
    ) -> None:
        """Test failed validation with dict result containing error."""
        mock_rust_processor.validate_message = AsyncMock(
            return_value={"is_valid": False, "error": "Custom error message"}
        )

        strategy = RustValidationStrategy(rust_processor=mock_rust_processor)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is False
        assert "Custom error message" in error

    async def test_sync_validate_method(
        self, valid_message: AgentMessage, mock_rust_processor: MagicMock
    ) -> None:
        """Test validation using synchronous validate method."""
        # Remove async method, add sync method
        del mock_rust_processor.validate_message
        mock_rust_processor.validate = MagicMock(return_value=True)

        strategy = RustValidationStrategy(rust_processor=mock_rust_processor)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is True
        assert error is None

    async def test_constitutional_validate_method(
        self, valid_message: AgentMessage, mock_rust_processor: MagicMock
    ) -> None:
        """Test validation using constitutional_validate method."""
        # Remove other methods
        del mock_rust_processor.validate_message
        mock_rust_processor.validate = None  # Set to None to not have the attr
        if hasattr(mock_rust_processor, "validate"):
            delattr(mock_rust_processor, "validate")
        mock_rust_processor.constitutional_validate = MagicMock(return_value=True)

        strategy = RustValidationStrategy(rust_processor=mock_rust_processor)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is True
        assert error is None

    async def test_no_validation_method_fails_closed(self, valid_message: AgentMessage) -> None:
        """Test that missing validation methods fail closed."""
        # Create processor with no validation methods
        mock_processor = MagicMock(spec=[])  # Empty spec means no methods

        strategy = RustValidationStrategy(rust_processor=mock_processor)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is False
        assert "fail closed" in error.lower()

    async def test_exception_fails_closed(
        self, valid_message: AgentMessage, mock_rust_processor: MagicMock
    ) -> None:
        """Test that exceptions fail closed."""
        mock_rust_processor.validate_message = AsyncMock(side_effect=RuntimeError("Rust panic"))

        strategy = RustValidationStrategy(rust_processor=mock_rust_processor)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is False
        assert "Rust validation error" in error
        assert "Rust panic" in error


# =============================================================================
# CompositeValidationStrategy Tests
# =============================================================================


class TestCompositeValidationStrategy:
    """Tests for CompositeValidationStrategy."""

    async def test_empty_strategies_passes(self, valid_message: AgentMessage) -> None:
        """Test that empty strategy list passes."""
        strategy = CompositeValidationStrategy(strategies=[])
        is_valid, error = await strategy.validate(valid_message)
        assert is_valid is True
        assert error is None

    async def test_all_strategies_pass(self, valid_message: AgentMessage) -> None:
        """Test that all passing strategies result in success."""
        mock_strategy1 = AsyncMock()
        mock_strategy1.validate = AsyncMock(return_value=(True, None))

        mock_strategy2 = AsyncMock()
        mock_strategy2.validate = AsyncMock(return_value=(True, None))

        strategy = CompositeValidationStrategy(strategies=[mock_strategy1, mock_strategy2])
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is True
        assert error is None

    async def test_one_strategy_fails(self, valid_message: AgentMessage) -> None:
        """Test that one failing strategy causes overall failure."""
        mock_strategy1 = AsyncMock()
        mock_strategy1.validate = AsyncMock(return_value=(True, None))

        mock_strategy2 = AsyncMock()
        mock_strategy2.validate = AsyncMock(return_value=(False, "Strategy 2 failed"))

        strategy = CompositeValidationStrategy(strategies=[mock_strategy1, mock_strategy2])
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is False
        assert "Strategy 2 failed" in error

    async def test_multiple_strategies_fail(self, valid_message: AgentMessage) -> None:
        """Test that multiple failures are aggregated."""
        mock_strategy1 = AsyncMock()
        mock_strategy1.validate = AsyncMock(return_value=(False, "Error 1"))

        mock_strategy2 = AsyncMock()
        mock_strategy2.validate = AsyncMock(return_value=(False, "Error 2"))

        strategy = CompositeValidationStrategy(strategies=[mock_strategy1, mock_strategy2])
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is False
        assert "Error 1" in error
        assert "Error 2" in error
        assert ";" in error  # Errors are joined with semicolon

    async def test_add_strategy(self, valid_message: AgentMessage) -> None:
        """Test adding a strategy dynamically."""
        strategy = CompositeValidationStrategy()

        mock_strategy = AsyncMock()
        mock_strategy.validate = AsyncMock(return_value=(True, None))

        strategy.add_strategy(mock_strategy)
        is_valid, _error = await strategy.validate(valid_message)

        assert is_valid is True
        mock_strategy.validate.assert_called_once()

    async def test_with_real_static_strategy(self, valid_message: AgentMessage) -> None:
        """Test composite with real StaticHashValidationStrategy."""
        static_strategy = StaticHashValidationStrategy(strict=True)

        composite = CompositeValidationStrategy(strategies=[static_strategy])
        is_valid, error = await composite.validate(valid_message)

        assert is_valid is True
        assert error is None

    async def test_with_real_static_strategy_invalid(
        self, invalid_hash_message: AgentMessage
    ) -> None:
        """Test composite with real StaticHashValidationStrategy - invalid case."""
        static_strategy = StaticHashValidationStrategy(strict=True)

        composite = CompositeValidationStrategy(strategies=[static_strategy])
        is_valid, error = await composite.validate(invalid_hash_message)

        assert is_valid is False
        assert "Constitutional hash mismatch" in error
