"""
ACGS-2 Enhanced Agent Bus - Processing Strategies Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for processing strategy implementations.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.maci.enforcer import MACIEnforcer
from enhanced_agent_bus.maci.models import MACIRole
from enhanced_agent_bus.maci.registry import MACIRoleRegistry
from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage, MessageType
from enhanced_agent_bus.processing_strategies import (
    CompositeProcessingStrategy,
    DynamicPolicyProcessingStrategy,
    MACIProcessingStrategy,
    OPAProcessingStrategy,
    PythonProcessingStrategy,
    RustProcessingStrategy,
)
from enhanced_agent_bus.validators import ValidationResult

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
        message_type=MessageType.COMMAND,
    )


@pytest.fixture
def invalid_hash_message() -> AgentMessage:
    """Create a message with invalid constitutional hash."""
    return AgentMessage(
        from_agent="test-sender",
        to_agent="test-receiver",
        content={"action": "test"},
        constitutional_hash="invalid-hash-value",
        message_type=MessageType.COMMAND,
    )


@pytest.fixture
def mock_validation_strategy() -> AsyncMock:
    """Create a mock validation strategy that passes."""
    strategy = AsyncMock()
    strategy.validate = AsyncMock(return_value=(True, None))
    return strategy


@pytest.fixture
def mock_failing_validation_strategy() -> AsyncMock:
    """Create a mock validation strategy that fails."""
    strategy = AsyncMock()
    strategy.validate = AsyncMock(return_value=(False, "Validation failed"))
    return strategy


@pytest.fixture
def mock_handlers() -> dict[MessageType, list]:
    """Create mock message handlers."""
    sync_handler = MagicMock()
    async_handler = AsyncMock()
    return {
        MessageType.COMMAND: [sync_handler, async_handler],
    }


@pytest.fixture
def mock_rust_processor() -> MagicMock:
    """Create a mock Rust processor."""
    processor = MagicMock()
    result = MagicMock()
    result.is_valid = True
    result.errors = []
    result.warnings = []
    result.metadata = {}
    result.constitutional_hash = CONSTITUTIONAL_HASH
    processor.process = MagicMock(return_value=result)
    return processor


@pytest.fixture
def mock_rust_bus() -> MagicMock:
    """Create a mock Rust bus module."""
    bus = MagicMock()
    bus.AgentMessage = MagicMock
    bus.MessageType = MagicMock()
    bus.MessageType.Command = "Command"
    bus.Priority = MagicMock()
    bus.Priority.Normal = "Normal"
    bus.MessageStatus = MagicMock()
    bus.MessageStatus.Pending = "Pending"
    return bus


@pytest.fixture
def mock_policy_client() -> AsyncMock:
    """Create a mock policy client."""
    client = AsyncMock()
    result = MagicMock()
    result.is_valid = True
    result.errors = []
    client.validate_message_signature = AsyncMock(return_value=result)
    return client


@pytest.fixture
def mock_opa_client() -> AsyncMock:
    """Create a mock OPA client."""
    client = AsyncMock()
    result = MagicMock()
    result.is_valid = True
    result.errors = []
    client.validate_constitutional = AsyncMock(return_value=result)
    return client


# =============================================================================
# PythonProcessingStrategy Tests
# =============================================================================


class TestPythonProcessingStrategy:
    """Tests for PythonProcessingStrategy."""

    async def test_successful_processing(
        self, valid_message: AgentMessage, mock_handlers: dict
    ) -> None:
        """Test successful message processing."""
        strategy = PythonProcessingStrategy()
        result = await strategy.process(valid_message, mock_handlers)

        assert result.is_valid is True
        assert valid_message.status.value == "delivered"

    async def test_failed_validation(
        self, invalid_hash_message: AgentMessage, mock_handlers: dict
    ) -> None:
        """Test processing with failed validation."""
        strategy = PythonProcessingStrategy()
        result = await strategy.process(invalid_hash_message, mock_handlers)

        assert result.is_valid is False
        assert invalid_hash_message.status.value == "failed"

    async def test_with_custom_validation_strategy(
        self, valid_message: AgentMessage, mock_handlers: dict, mock_validation_strategy: AsyncMock
    ) -> None:
        """Test processing with custom validation strategy."""
        strategy = PythonProcessingStrategy(validation_strategy=mock_validation_strategy)
        result = await strategy.process(valid_message, mock_handlers)

        assert result.is_valid is True
        mock_validation_strategy.validate.assert_called_once()

    async def test_handler_execution(self, valid_message: AgentMessage) -> None:
        """Test that handlers are executed."""
        sync_handler = MagicMock()
        async_handler = AsyncMock()
        handlers = {MessageType.COMMAND: [sync_handler, async_handler]}

        strategy = PythonProcessingStrategy()
        result = await strategy.process(valid_message, handlers)

        assert result.is_valid is True
        sync_handler.assert_called_once_with(valid_message)
        async_handler.assert_called_once_with(valid_message)

    async def test_handler_error_type_error(self, valid_message: AgentMessage) -> None:
        """Test handling of TypeError in handlers."""

        def failing_handler(msg):
            raise TypeError("type error in handler")

        handlers = {MessageType.COMMAND: [failing_handler]}
        strategy = PythonProcessingStrategy()
        result = await strategy.process(valid_message, handlers)

        assert result.is_valid is False
        assert "TypeError" in result.errors[0]
        assert valid_message.status.value == "failed"

    async def test_handler_error_value_error(self, valid_message: AgentMessage) -> None:
        """Test handling of ValueError in handlers."""

        def failing_handler(msg):
            raise ValueError("Value error in handler")

        handlers = {MessageType.COMMAND: [failing_handler]}
        strategy = PythonProcessingStrategy()
        result = await strategy.process(valid_message, handlers)

        assert result.is_valid is False
        assert "ValueError" in result.errors[0]

    async def test_handler_runtime_error(self, valid_message: AgentMessage) -> None:
        """Test handling of RuntimeError in handlers."""

        def failing_handler(msg):
            raise RuntimeError("Runtime error in handler")

        handlers = {MessageType.COMMAND: [failing_handler]}
        strategy = PythonProcessingStrategy()
        result = await strategy.process(valid_message, handlers)

        assert result.is_valid is False
        assert "Runtime error" in result.errors[0]

    def test_is_available(self) -> None:
        """Test that Python strategy is always available."""
        strategy = PythonProcessingStrategy()
        assert strategy.is_available() is True

    def test_get_name(self) -> None:
        """Test get_name returns correct name."""
        strategy = PythonProcessingStrategy()
        assert strategy.get_name() == "python"

    async def test_no_handlers_for_message_type(self, valid_message: AgentMessage) -> None:
        """Test processing when no handlers exist for message type."""
        handlers: dict = {}
        strategy = PythonProcessingStrategy()
        result = await strategy.process(valid_message, handlers)

        assert result.is_valid is True
        assert valid_message.status.value == "delivered"


# =============================================================================
# RustProcessingStrategy Tests
# =============================================================================


class TestRustProcessingStrategy:
    """Tests for RustProcessingStrategy."""

    async def test_no_rust_processor_unavailable(
        self, valid_message: AgentMessage, mock_handlers: dict
    ) -> None:
        """Test that strategy is unavailable without Rust processor."""
        strategy = RustProcessingStrategy(rust_processor=None)

        assert strategy.is_available() is False
        result = await strategy.process(valid_message, mock_handlers)
        assert result.is_valid is False
        assert "not available" in result.errors[0]

    async def test_successful_rust_processing(
        self,
        valid_message: AgentMessage,
        mock_handlers: dict,
        mock_rust_processor: MagicMock,
        mock_rust_bus: MagicMock,
        mock_validation_strategy: AsyncMock,
    ) -> None:
        """Test successful processing with Rust backend."""
        strategy = RustProcessingStrategy(
            rust_processor=mock_rust_processor,
            rust_bus=mock_rust_bus,
            validation_strategy=mock_validation_strategy,
        )
        result = await strategy.process(valid_message, mock_handlers)

        assert result.is_valid is True
        assert valid_message.status.value == "delivered"

    async def test_rust_validation_failure(
        self,
        valid_message: AgentMessage,
        mock_handlers: dict,
        mock_rust_processor: MagicMock,
        mock_rust_bus: MagicMock,
        mock_failing_validation_strategy: AsyncMock,
    ) -> None:
        """Test processing with failed Rust validation."""
        strategy = RustProcessingStrategy(
            rust_processor=mock_rust_processor,
            rust_bus=mock_rust_bus,
            validation_strategy=mock_failing_validation_strategy,
        )
        result = await strategy.process(valid_message, mock_handlers)

        assert result.is_valid is False
        assert valid_message.status.value == "failed"

    async def test_rust_processing_exception(
        self,
        valid_message: AgentMessage,
        mock_handlers: dict,
        mock_rust_bus: MagicMock,
        mock_validation_strategy: AsyncMock,
    ) -> None:
        """Test handling of Rust processing exception."""
        processor = MagicMock()
        processor.process = MagicMock(side_effect=RuntimeError("Rust panic"))

        strategy = RustProcessingStrategy(
            rust_processor=processor,
            rust_bus=mock_rust_bus,
            validation_strategy=mock_validation_strategy,
        )
        result = await strategy.process(valid_message, mock_handlers)

        assert result.is_valid is False
        assert "Rust processing error" in result.errors[0]

    def test_circuit_breaker_trips_after_failures(
        self, mock_rust_processor: MagicMock, mock_rust_bus: MagicMock
    ) -> None:
        """Test circuit breaker trips after threshold failures."""
        strategy = RustProcessingStrategy(
            rust_processor=mock_rust_processor, rust_bus=mock_rust_bus
        )

        # Simulate max threshold failures
        for _ in range(3):
            strategy._record_failure()

        assert strategy._breaker_tripped is True
        assert strategy._failure_count == 3

    def test_circuit_breaker_reset_after_success(
        self, mock_rust_processor: MagicMock, mock_rust_bus: MagicMock
    ) -> None:
        """Test circuit breaker resets after consecutive successes."""
        strategy = RustProcessingStrategy(
            rust_processor=mock_rust_processor, rust_bus=mock_rust_bus
        )

        # Trip the breaker
        for _ in range(3):
            strategy._record_failure()
        assert strategy._breaker_tripped is True

        # Record enough successes to reset
        for _ in range(5):
            strategy._record_success()

        assert strategy._breaker_tripped is False
        assert strategy._failure_count == 0

    def test_get_name(self, mock_rust_processor: MagicMock, mock_rust_bus: MagicMock) -> None:
        """Test get_name returns correct name."""
        strategy = RustProcessingStrategy(
            rust_processor=mock_rust_processor, rust_bus=mock_rust_bus
        )
        assert strategy.get_name() == "rust"

    async def test_async_rust_process_method(
        self,
        valid_message: AgentMessage,
        mock_handlers: dict,
        mock_rust_bus: MagicMock,
        mock_validation_strategy: AsyncMock,
    ) -> None:
        """Test handling of async Rust process method."""
        processor = MagicMock()
        result = MagicMock()
        result.is_valid = True
        result.errors = []
        result.warnings = []
        result.metadata = {}

        async def async_process(msg):
            return result

        processor.process = async_process

        strategy = RustProcessingStrategy(
            rust_processor=processor,
            rust_bus=mock_rust_bus,
            validation_strategy=mock_validation_strategy,
        )
        proc_result = await strategy.process(valid_message, mock_handlers)

        assert proc_result.is_valid is True


# =============================================================================
# DynamicPolicyProcessingStrategy Tests
# =============================================================================


class TestDynamicPolicyProcessingStrategy:
    """Tests for DynamicPolicyProcessingStrategy."""

    async def test_no_policy_client_unavailable(
        self, valid_message: AgentMessage, mock_handlers: dict
    ) -> None:
        """Test strategy unavailable without policy client."""
        strategy = DynamicPolicyProcessingStrategy(policy_client=None)

        # Will try to get policy client, which may or may not be available
        if not strategy.is_available():
            result = await strategy.process(valid_message, mock_handlers)
            assert result.is_valid is False
            assert "not available" in result.errors[0]

    async def test_successful_policy_processing(
        self,
        valid_message: AgentMessage,
        mock_handlers: dict,
        mock_policy_client: AsyncMock,
        mock_validation_strategy: AsyncMock,
    ) -> None:
        """Test successful processing with policy client."""
        strategy = DynamicPolicyProcessingStrategy(
            policy_client=mock_policy_client, validation_strategy=mock_validation_strategy
        )
        result = await strategy.process(valid_message, mock_handlers)

        assert result.is_valid is True

    async def test_policy_validation_failure(
        self,
        valid_message: AgentMessage,
        mock_handlers: dict,
        mock_policy_client: AsyncMock,
        mock_failing_validation_strategy: AsyncMock,
    ) -> None:
        """Test processing with failed policy validation."""
        strategy = DynamicPolicyProcessingStrategy(
            policy_client=mock_policy_client, validation_strategy=mock_failing_validation_strategy
        )
        result = await strategy.process(valid_message, mock_handlers)

        assert result.is_valid is False
        assert valid_message.status.value == "failed"

    async def test_policy_validation_exception(
        self, valid_message: AgentMessage, mock_handlers: dict, mock_policy_client: AsyncMock
    ) -> None:
        """Test handling of policy validation exception."""
        failing_strategy = AsyncMock()
        failing_strategy.validate = AsyncMock(side_effect=RuntimeError("Policy error"))

        strategy = DynamicPolicyProcessingStrategy(
            policy_client=mock_policy_client, validation_strategy=failing_strategy
        )
        result = await strategy.process(valid_message, mock_handlers)

        assert result.is_valid is False
        assert "Policy validation error" in result.errors[0]

    def test_is_available_with_client(self, mock_policy_client: AsyncMock) -> None:
        """Test is_available returns True with policy client."""
        strategy = DynamicPolicyProcessingStrategy(policy_client=mock_policy_client)
        assert strategy.is_available() is True

    def test_get_name(self, mock_policy_client: AsyncMock) -> None:
        """Test get_name returns correct name."""
        strategy = DynamicPolicyProcessingStrategy(policy_client=mock_policy_client)
        assert strategy.get_name() == "dynamic_policy"


# =============================================================================
# OPAProcessingStrategy Tests
# =============================================================================


class TestOPAProcessingStrategy:
    """Tests for OPAProcessingStrategy."""

    async def test_no_opa_client_unavailable(
        self, valid_message: AgentMessage, mock_handlers: dict
    ) -> None:
        """Test strategy unavailable without OPA client."""
        strategy = OPAProcessingStrategy(opa_client=None)

        if not strategy.is_available():
            result = await strategy.process(valid_message, mock_handlers)
            assert result.is_valid is False
            assert "not available" in result.errors[0]

    async def test_successful_opa_processing(
        self,
        valid_message: AgentMessage,
        mock_handlers: dict,
        mock_opa_client: AsyncMock,
        mock_validation_strategy: AsyncMock,
    ) -> None:
        """Test successful processing with OPA client."""
        strategy = OPAProcessingStrategy(
            opa_client=mock_opa_client, validation_strategy=mock_validation_strategy
        )
        result = await strategy.process(valid_message, mock_handlers)

        assert result.is_valid is True

    async def test_opa_validation_failure(
        self,
        valid_message: AgentMessage,
        mock_handlers: dict,
        mock_opa_client: AsyncMock,
        mock_failing_validation_strategy: AsyncMock,
    ) -> None:
        """Test processing with failed OPA validation."""
        strategy = OPAProcessingStrategy(
            opa_client=mock_opa_client, validation_strategy=mock_failing_validation_strategy
        )
        result = await strategy.process(valid_message, mock_handlers)

        assert result.is_valid is False

    async def test_opa_validation_exception(
        self, valid_message: AgentMessage, mock_handlers: dict, mock_opa_client: AsyncMock
    ) -> None:
        """Test handling of OPA validation exception."""
        failing_strategy = AsyncMock()
        failing_strategy.validate = AsyncMock(side_effect=RuntimeError("OPA error"))

        strategy = OPAProcessingStrategy(
            opa_client=mock_opa_client, validation_strategy=failing_strategy
        )
        result = await strategy.process(valid_message, mock_handlers)

        assert result.is_valid is False
        assert "OPA validation error" in result.errors[0]

    def test_is_available_with_client(self, mock_opa_client: AsyncMock) -> None:
        """Test is_available returns True with OPA client."""
        strategy = OPAProcessingStrategy(opa_client=mock_opa_client)
        assert strategy.is_available() is True

    def test_get_name(self, mock_opa_client: AsyncMock) -> None:
        """Test get_name returns correct name."""
        strategy = OPAProcessingStrategy(opa_client=mock_opa_client)
        assert strategy.get_name() == "opa"


# =============================================================================
# CompositeProcessingStrategy Tests
# =============================================================================


class TestCompositeProcessingStrategy:
    """Tests for CompositeProcessingStrategy."""

    async def test_first_strategy_succeeds(
        self, valid_message: AgentMessage, mock_handlers: dict
    ) -> None:
        """Test that first available strategy is used."""
        mock_strategy = MagicMock()
        mock_strategy.is_available = MagicMock(return_value=True)
        mock_strategy.get_name = MagicMock(return_value="mock")
        mock_strategy.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        composite = CompositeProcessingStrategy(strategies=[mock_strategy])
        result = await composite.process(valid_message, mock_handlers)

        assert result.is_valid is True
        mock_strategy.process.assert_called_once()

    async def test_fallback_on_unavailable(
        self, valid_message: AgentMessage, mock_handlers: dict
    ) -> None:
        """Test fallback when first strategy is unavailable."""
        unavailable = MagicMock()
        unavailable.is_available = MagicMock(return_value=False)
        unavailable.get_name = MagicMock(return_value="unavailable")

        available = MagicMock()
        available.is_available = MagicMock(return_value=True)
        available.get_name = MagicMock(return_value="available")
        available.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        composite = CompositeProcessingStrategy(strategies=[unavailable, available])
        result = await composite.process(valid_message, mock_handlers)

        assert result.is_valid is True
        available.process.assert_called_once()

    async def test_fallback_on_exception(
        self, valid_message: AgentMessage, mock_handlers: dict
    ) -> None:
        """Test fallback when first strategy raises exception."""
        failing = MagicMock()
        failing.is_available = MagicMock(return_value=True)
        failing.get_name = MagicMock(return_value="failing")
        failing.process = AsyncMock(side_effect=RuntimeError("Strategy failed"))

        backup = MagicMock()
        backup.is_available = MagicMock(return_value=True)
        backup.get_name = MagicMock(return_value="backup")
        backup.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        composite = CompositeProcessingStrategy(strategies=[failing, backup])
        result = await composite.process(valid_message, mock_handlers)

        assert result.is_valid is True
        backup.process.assert_called_once()

    async def test_all_strategies_fail(
        self, valid_message: AgentMessage, mock_handlers: dict
    ) -> None:
        """Test when all strategies fail."""
        failing1 = MagicMock()
        failing1.is_available = MagicMock(return_value=True)
        failing1.get_name = MagicMock(return_value="failing1")
        failing1.process = AsyncMock(side_effect=RuntimeError("Strategy 1 failed"))

        failing2 = MagicMock()
        failing2.is_available = MagicMock(return_value=True)
        failing2.get_name = MagicMock(return_value="failing2")
        failing2.process = AsyncMock(side_effect=RuntimeError("Strategy 2 failed"))

        composite = CompositeProcessingStrategy(strategies=[failing1, failing2])
        result = await composite.process(valid_message, mock_handlers)

        assert result.is_valid is False
        assert "All processing strategies failed" in result.errors[0]

    async def test_record_failure_called_on_exception(
        self, valid_message: AgentMessage, mock_handlers: dict
    ) -> None:
        """Test that _record_failure is called when strategy has it."""
        failing = MagicMock()
        failing.is_available = MagicMock(return_value=True)
        failing.get_name = MagicMock(return_value="failing")
        failing.process = AsyncMock(side_effect=RuntimeError("Failed"))
        failing._record_failure = MagicMock()

        composite = CompositeProcessingStrategy(strategies=[failing])
        await composite.process(valid_message, mock_handlers)

        failing._record_failure.assert_called_once()

    def test_is_available_any_available(self) -> None:
        """Test is_available returns True if any strategy is available."""
        unavailable = MagicMock()
        unavailable.is_available = MagicMock(return_value=False)

        available = MagicMock()
        available.is_available = MagicMock(return_value=True)

        composite = CompositeProcessingStrategy(strategies=[unavailable, available])
        assert composite.is_available() is True

    def test_is_available_none_available(self) -> None:
        """Test is_available returns False if no strategy is available."""
        unavailable1 = MagicMock()
        unavailable1.is_available = MagicMock(return_value=False)

        unavailable2 = MagicMock()
        unavailable2.is_available = MagicMock(return_value=False)

        composite = CompositeProcessingStrategy(strategies=[unavailable1, unavailable2])
        assert composite.is_available() is False

    def test_get_name(self) -> None:
        """Test get_name returns composite name."""
        s1 = MagicMock()
        s1.get_name = MagicMock(return_value="s1")
        s2 = MagicMock()
        s2.get_name = MagicMock(return_value="s2")

        composite = CompositeProcessingStrategy(strategies=[s1, s2])
        assert composite.get_name() == "composite(s1+s2)"


# =============================================================================
# MACIProcessingStrategy Tests
# =============================================================================


class TestMACIProcessingStrategy:
    """Tests for MACIProcessingStrategy."""

    async def test_delegates_to_inner_strategy(
        self, valid_message: AgentMessage, mock_handlers: dict
    ) -> None:
        """Test that MACI strategy delegates to inner strategy."""
        inner = MagicMock()
        inner.is_available = MagicMock(return_value=True)
        inner.get_name = MagicMock(return_value="inner")
        inner.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        maci = MACIProcessingStrategy(inner_strategy=inner)
        result = await maci.process(valid_message, mock_handlers)

        # Result depends on whether MACI module is available
        # If MACI is not available, it delegates to inner
        if not maci._maci_available:
            inner.process.assert_called_once()

    def test_is_available_depends_on_inner(self) -> None:
        """Test is_available depends on inner strategy and MACI availability."""
        inner = MagicMock()
        inner.is_available = MagicMock(return_value=True)

        maci = MACIProcessingStrategy(inner_strategy=inner)
        # Available only if both MACI module and inner are available
        if maci._maci_available:
            assert maci.is_available() is True
        else:
            assert maci.is_available() is False

    def test_get_name_includes_inner(self) -> None:
        """Test get_name includes inner strategy name."""
        inner = MagicMock()
        inner.get_name = MagicMock(return_value="python")
        inner.is_available = MagicMock(return_value=True)

        maci = MACIProcessingStrategy(inner_strategy=inner)
        assert "python" in maci.get_name()
        assert "maci" in maci.get_name()

    def test_registry_property(self) -> None:
        """Test registry property access."""
        inner = MagicMock()
        inner.is_available = MagicMock(return_value=True)

        maci = MACIProcessingStrategy(inner_strategy=inner)
        # Registry may be None if MACI not available
        registry = maci.registry
        if maci._maci_available:
            assert registry is not None
        else:
            assert registry is None

    def test_enforcer_property(self) -> None:
        """Test enforcer property access."""
        inner = MagicMock()
        inner.is_available = MagicMock(return_value=True)

        maci = MACIProcessingStrategy(inner_strategy=inner)
        # Enforcer may be None if MACI not available
        enforcer = maci.enforcer
        if maci._maci_available:
            assert enforcer is not None
        else:
            assert enforcer is None

    async def test_strict_mode_error_handling(
        self, valid_message: AgentMessage, mock_handlers: dict
    ) -> None:
        """Test strict mode error handling."""
        inner = MagicMock()
        inner.is_available = MagicMock(return_value=True)
        inner.get_name = MagicMock(return_value="inner")
        inner.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        maci = MACIProcessingStrategy(inner_strategy=inner, strict_mode=True)

        if maci._maci_available:
            # If MACI is available, it will validate first
            result = await maci.process(valid_message, mock_handlers)
            # Result depends on MACI validation
        else:
            # If MACI not available, delegates to inner
            result = await maci.process(valid_message, mock_handlers)
            inner.process.assert_called_once()

    async def test_real_enforcer_denies_rejected_action(
        self, valid_message: AgentMessage, mock_handlers: dict
    ) -> None:
        """A raw MACIEnforcer must be adapted and deny invalid actions."""
        inner = MagicMock()
        inner.is_available = MagicMock(return_value=True)
        inner.get_name = MagicMock(return_value="inner")
        inner.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        registry = MACIRoleRegistry()
        await registry.register_agent(valid_message.from_agent, MACIRole.EXECUTIVE)
        enforcer = MACIEnforcer(registry=registry, strict_mode=True)
        maci = MACIProcessingStrategy(
            inner_strategy=inner,
            maci_registry=registry,
            maci_enforcer=enforcer,
            strict_mode=True,
        )
        valid_message.message_type = MessageType.CONSTITUTIONAL_VALIDATION

        result = await maci.process(valid_message, mock_handlers)

        assert result.is_valid is False
        inner.process.assert_not_called()


# =============================================================================
# Integration Tests
# =============================================================================


class TestProcessingStrategyIntegration:
    """Integration tests for processing strategies."""

    async def test_python_strategy_end_to_end(self, valid_message: AgentMessage) -> None:
        """Test complete Python strategy workflow."""
        results = []

        async def async_handler(msg):
            results.append(("async", msg.message_id))

        def sync_handler(msg):
            results.append(("sync", msg.message_id))

        handlers = {MessageType.COMMAND: [sync_handler, async_handler]}

        strategy = PythonProcessingStrategy()
        result = await strategy.process(valid_message, handlers)

        assert result.is_valid is True
        assert len(results) == 2
        assert valid_message.status.value == "delivered"

    async def test_composite_with_python_fallback(self, valid_message: AgentMessage) -> None:
        """Test composite with Python as fallback."""
        unavailable = MagicMock()
        unavailable.is_available = MagicMock(return_value=False)
        unavailable.get_name = MagicMock(return_value="unavailable")

        python_strategy = PythonProcessingStrategy()

        composite = CompositeProcessingStrategy(strategies=[unavailable, python_strategy])

        result = await composite.process(valid_message, {})

        assert result.is_valid is True
        assert valid_message.status.value == "delivered"

    async def test_maci_wrapping_python(self, valid_message: AgentMessage) -> None:
        """Test MACI strategy wrapping Python strategy."""
        python_strategy = PythonProcessingStrategy()
        maci_strategy = MACIProcessingStrategy(
            inner_strategy=python_strategy,
            strict_mode=False,  # Non-strict for testing
        )

        result = await maci_strategy.process(valid_message, {})

        # Should succeed whether MACI is available or not
        assert result.is_valid is True
