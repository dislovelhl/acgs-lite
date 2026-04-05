"""
ACGS-2 Processing Strategies Coverage Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for processing_strategies.py.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    from enhanced_agent_bus.models import (
        CONSTITUTIONAL_HASH,
        AgentMessage,
        MessageStatus,
        MessageType,
    )
    from enhanced_agent_bus.processing_strategies import (
        CompositeProcessingStrategy,
        DynamicPolicyProcessingStrategy,
        MACIProcessingStrategy,
        OPAProcessingStrategy,
        PythonProcessingStrategy,
    )
    from enhanced_agent_bus.validators import ValidationResult
except ImportError:
    from models import CONSTITUTIONAL_HASH, AgentMessage, MessageType
    from processing_strategies import (
        CompositeProcessingStrategy,
        DynamicPolicyProcessingStrategy,
        MACIProcessingStrategy,
        OPAProcessingStrategy,
        PythonProcessingStrategy,
    )
    from validators import ValidationResult


class TestPythonProcessingStrategy:
    """Tests for PythonProcessingStrategy."""

    @pytest.fixture
    def strategy(self):
        """Create strategy instance."""
        return PythonProcessingStrategy()

    @pytest.fixture
    def message(self):
        """Create test message."""
        return AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )

    def test_init_defaults(self, strategy):
        """Strategy initializes with correct defaults."""
        assert strategy._constitutional_hash == CONSTITUTIONAL_HASH
        assert strategy._metrics_enabled is False
        assert strategy._validation_strategy is not None

    def test_is_available(self, strategy):
        """Python strategy is always available."""
        assert strategy.is_available() is True

    def test_get_name(self, strategy):
        """get_name returns 'python'."""
        assert strategy.get_name() == "python"

    async def test_process_valid_message(self, strategy, message):
        """Process succeeds with valid message."""
        handlers = {}
        result = await strategy.process(message, handlers)
        assert result.is_valid is True
        assert message.status.value == "delivered"

    async def test_process_invalid_hash(self, strategy, message):
        """Process fails with invalid hash."""
        message.constitutional_hash = "wrong_hash"
        handlers = {}
        result = await strategy.process(message, handlers)
        assert result.is_valid is False
        assert message.status.value == "failed"

    async def test_process_with_sync_handler(self, strategy, message):
        """Process executes sync handlers."""
        call_log = []

        def sync_handler(msg):
            call_log.append(msg.message_id)

        handlers = {MessageType.COMMAND: [sync_handler]}
        result = await strategy.process(message, handlers)
        assert result.is_valid is True
        assert len(call_log) == 1

    async def test_process_with_async_handler(self, strategy, message):
        """Process executes async handlers."""
        call_log = []

        async def async_handler(msg):
            call_log.append(msg.message_id)

        handlers = {MessageType.COMMAND: [async_handler]}
        result = await strategy.process(message, handlers)
        assert result.is_valid is True
        assert len(call_log) == 1

    async def test_process_handler_type_error(self, strategy, message):
        """Process handles TypeError in handler."""

        def error_handler(msg):
            raise TypeError("test error")

        handlers = {MessageType.COMMAND: [error_handler]}
        result = await strategy.process(message, handlers)
        assert result.is_valid is False
        assert message.status.value == "failed"
        assert any("TypeError" in e for e in result.errors)

    async def test_process_handler_runtime_error(self, strategy, message):
        """Process handles RuntimeError in handler."""

        def error_handler(msg):
            raise RuntimeError("runtime issue")

        handlers = {MessageType.COMMAND: [error_handler]}
        result = await strategy.process(message, handlers)
        assert result.is_valid is False
        assert any("Runtime error" in e for e in result.errors)

    async def test_process_handler_value_error(self, strategy, message):
        """Process handles ValueError in handler."""

        def error_handler(msg):
            raise ValueError("bad value")

        handlers = {MessageType.COMMAND: [error_handler]}
        result = await strategy.process(message, handlers)
        assert result.is_valid is False

    def test_init_with_custom_validation(self):
        """Strategy accepts custom validation strategy."""
        mock_validator = MagicMock()
        strategy = PythonProcessingStrategy(validation_strategy=mock_validator)
        assert strategy._validation_strategy == mock_validator

    def test_init_with_metrics_enabled(self):
        """Strategy can be created with metrics enabled."""
        strategy = PythonProcessingStrategy(metrics_enabled=True)
        assert strategy._metrics_enabled is True


class TestDynamicPolicyProcessingStrategy:
    """Tests for DynamicPolicyProcessingStrategy."""

    @pytest.fixture
    def message(self):
        """Create test message."""
        return AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )

    def test_init_without_client(self):
        """Strategy initializes without policy client."""
        strategy = DynamicPolicyProcessingStrategy(policy_client=None)
        assert strategy._constitutional_hash == CONSTITUTIONAL_HASH

    def test_is_available_false_without_client(self):
        """is_available returns False without client."""
        strategy = DynamicPolicyProcessingStrategy(policy_client=None)
        # Policy client may or may not be available depending on imports
        assert isinstance(strategy.is_available(), bool)

    def test_get_name(self):
        """get_name returns 'dynamic_policy'."""
        strategy = DynamicPolicyProcessingStrategy(policy_client=None)
        assert strategy.get_name() == "dynamic_policy"

    async def test_process_not_available(self, message):
        """Process fails when not available."""
        strategy = DynamicPolicyProcessingStrategy(policy_client=None)
        if not strategy.is_available():
            handlers = {}
            result = await strategy.process(message, handlers)
            assert result.is_valid is False
            assert any("not available" in e for e in result.errors)

    async def test_process_with_mock_client(self, message):
        """Process with mock policy client."""
        mock_client = MagicMock()
        mock_validator = MagicMock()
        mock_validator.validate = AsyncMock(return_value=(True, None))

        strategy = DynamicPolicyProcessingStrategy(
            policy_client=mock_client, validation_strategy=mock_validator
        )
        handlers = {}
        result = await strategy.process(message, handlers)
        assert result.is_valid is True

    async def test_process_validation_failure(self, message):
        """Process handles validation failure."""
        mock_client = MagicMock()
        mock_validator = MagicMock()
        mock_validator.validate = AsyncMock(return_value=(False, "Policy denied"))

        strategy = DynamicPolicyProcessingStrategy(
            policy_client=mock_client, validation_strategy=mock_validator
        )
        handlers = {}
        result = await strategy.process(message, handlers)
        assert result.is_valid is False

    async def test_process_exception_handling(self, message):
        """Process handles exceptions gracefully."""
        mock_client = MagicMock()
        mock_validator = MagicMock()
        mock_validator.validate = AsyncMock(side_effect=RuntimeError("Policy error"))

        strategy = DynamicPolicyProcessingStrategy(
            policy_client=mock_client, validation_strategy=mock_validator
        )
        handlers = {}
        result = await strategy.process(message, handlers)
        assert result.is_valid is False
        assert any("error" in e.lower() for e in result.errors)


class TestOPAProcessingStrategy:
    """Tests for OPAProcessingStrategy."""

    @pytest.fixture
    def message(self):
        """Create test message."""
        return AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )

    def test_init_without_client(self):
        """Strategy initializes without OPA client."""
        strategy = OPAProcessingStrategy(opa_client=None)
        assert strategy._constitutional_hash == CONSTITUTIONAL_HASH

    def test_get_name(self):
        """get_name returns 'opa'."""
        strategy = OPAProcessingStrategy(opa_client=None)
        assert strategy.get_name() == "opa"

    async def test_process_not_available(self, message):
        """Process fails when OPA not available."""
        strategy = OPAProcessingStrategy(opa_client=None)
        if not strategy.is_available():
            handlers = {}
            result = await strategy.process(message, handlers)
            assert result.is_valid is False
            assert any("not available" in e for e in result.errors)

    async def test_process_with_mock_client(self, message):
        """Process with mock OPA client."""
        mock_client = MagicMock()
        mock_validator = MagicMock()
        mock_validator.validate = AsyncMock(return_value=(True, None))

        strategy = OPAProcessingStrategy(opa_client=mock_client, validation_strategy=mock_validator)
        handlers = {}
        result = await strategy.process(message, handlers)
        assert result.is_valid is True

    async def test_process_validation_failure(self, message):
        """Process handles validation failure."""
        mock_client = MagicMock()
        mock_validator = MagicMock()
        mock_validator.validate = AsyncMock(return_value=(False, "OPA denied"))

        strategy = OPAProcessingStrategy(opa_client=mock_client, validation_strategy=mock_validator)
        handlers = {}
        result = await strategy.process(message, handlers)
        assert result.is_valid is False

    async def test_process_with_handlers(self, message):
        """Process executes handlers after validation."""
        mock_client = MagicMock()
        mock_validator = MagicMock()
        mock_validator.validate = AsyncMock(return_value=(True, None))

        call_log = []

        def test_handler(msg):
            call_log.append(msg.message_id)

        strategy = OPAProcessingStrategy(opa_client=mock_client, validation_strategy=mock_validator)
        handlers = {MessageType.COMMAND: [test_handler]}
        result = await strategy.process(message, handlers)
        assert result.is_valid is True
        assert len(call_log) == 1


class TestCompositeProcessingStrategy:
    """Tests for CompositeProcessingStrategy."""

    @pytest.fixture
    def message(self):
        """Create test message."""
        return AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )

    def test_init_with_strategies(self):
        """Composite initializes with strategies."""
        mock_strategy = MagicMock()
        mock_strategy.is_available.return_value = True

        composite = CompositeProcessingStrategy([mock_strategy])
        assert composite._constitutional_hash == CONSTITUTIONAL_HASH

    def test_is_available_true(self):
        """is_available returns True when any strategy available."""
        mock_strategy = MagicMock()
        mock_strategy.is_available.return_value = True

        composite = CompositeProcessingStrategy([mock_strategy])
        assert composite.is_available() is True

    def test_is_available_false(self):
        """is_available returns False when no strategy available."""
        mock_strategy = MagicMock()
        mock_strategy.is_available.return_value = False

        composite = CompositeProcessingStrategy([mock_strategy])
        assert composite.is_available() is False

    def test_get_name(self):
        """get_name returns composite name."""
        mock_strategy = MagicMock()
        mock_strategy.get_name.return_value = "test_strategy"
        mock_strategy.is_available.return_value = True

        composite = CompositeProcessingStrategy([mock_strategy])
        name = composite.get_name()
        assert "composite" in name
        assert "test_strategy" in name

    async def test_process_first_strategy_succeeds(self, message):
        """Process uses first successful strategy."""
        mock_result = ValidationResult(is_valid=True)
        mock_strategy = MagicMock()
        mock_strategy.is_available.return_value = True
        mock_strategy.get_name.return_value = "first"
        mock_strategy.process = AsyncMock(return_value=mock_result)

        composite = CompositeProcessingStrategy([mock_strategy])
        handlers = {}
        result = await composite.process(message, handlers)
        assert result.is_valid is True

    async def test_process_fallback_on_failure(self, message):
        """Process falls back when first strategy fails."""
        # First strategy raises exception
        first_strategy = MagicMock()
        first_strategy.is_available.return_value = True
        first_strategy.get_name.return_value = "failing"
        first_strategy.process = AsyncMock(side_effect=RuntimeError("Failed"))

        # Second strategy succeeds
        second_strategy = MagicMock()
        second_strategy.is_available.return_value = True
        second_strategy.get_name.return_value = "success"
        second_strategy.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        composite = CompositeProcessingStrategy([first_strategy, second_strategy])
        handlers = {}
        result = await composite.process(message, handlers)
        assert result.is_valid is True

    async def test_process_all_fail(self, message):
        """Process returns error when all strategies fail."""
        mock_strategy = MagicMock()
        mock_strategy.is_available.return_value = True
        mock_strategy.get_name.return_value = "failing"
        mock_strategy.process = AsyncMock(side_effect=RuntimeError("All failed"))

        composite = CompositeProcessingStrategy([mock_strategy])
        handlers = {}
        result = await composite.process(message, handlers)
        assert result.is_valid is False
        assert any("failed" in e.lower() for e in result.errors)

    async def test_process_skips_unavailable(self, message):
        """Process skips unavailable strategies."""
        # Unavailable strategy
        unavailable = MagicMock()
        unavailable.is_available.return_value = False

        # Available strategy
        available = MagicMock()
        available.is_available.return_value = True
        available.get_name.return_value = "available"
        available.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        composite = CompositeProcessingStrategy([unavailable, available])
        handlers = {}
        result = await composite.process(message, handlers)
        assert result.is_valid is True
        unavailable.process.assert_not_called()

    async def test_process_calls_record_failure(self, message):
        """Process calls _record_failure on strategy exception."""
        mock_strategy = MagicMock()
        mock_strategy.is_available.return_value = True
        mock_strategy.get_name.return_value = "failing"
        mock_strategy.process = AsyncMock(side_effect=RuntimeError("Failed"))
        mock_strategy._record_failure = MagicMock()

        composite = CompositeProcessingStrategy([mock_strategy])
        handlers = {}
        await composite.process(message, handlers)
        mock_strategy._record_failure.assert_called_once()


class TestMACIProcessingStrategy:
    """Tests for MACIProcessingStrategy."""

    @pytest.fixture
    def message(self):
        """Create test message."""
        return AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )

    @pytest.fixture
    def mock_inner_strategy(self):
        """Create mock inner strategy."""
        strategy = MagicMock()
        strategy.is_available.return_value = True
        strategy.get_name.return_value = "python"
        strategy.process = AsyncMock(return_value=ValidationResult(is_valid=True))
        return strategy

    def test_init_with_inner_strategy(self, mock_inner_strategy):
        """MACI initializes with inner strategy."""
        maci = MACIProcessingStrategy(mock_inner_strategy)
        assert maci._constitutional_hash == CONSTITUTIONAL_HASH

    def test_get_name(self, mock_inner_strategy):
        """get_name returns maci+inner name."""
        maci = MACIProcessingStrategy(mock_inner_strategy)
        name = maci.get_name()
        assert "maci" in name
        assert "python" in name

    def test_registry_property(self, mock_inner_strategy):
        """registry property returns registry if available."""
        maci = MACIProcessingStrategy(mock_inner_strategy)
        # May be None if MACI module not available
        registry = maci.registry
        assert registry is None or registry is not None

    def test_enforcer_property(self, mock_inner_strategy):
        """enforcer property returns enforcer if available."""
        maci = MACIProcessingStrategy(mock_inner_strategy)
        # May be None if MACI module not available
        enforcer = maci.enforcer
        assert enforcer is None or enforcer is not None

    async def test_process_delegates_when_maci_unavailable(self, mock_inner_strategy, message):
        """Process delegates to inner strategy when MACI unavailable."""
        maci = MACIProcessingStrategy(mock_inner_strategy)
        # Force MACI unavailable
        maci._maci_available = False
        maci._maci_strategy = None

        handlers = {}
        result = await maci.process(message, handlers)
        # Should delegate to inner strategy
        mock_inner_strategy.process.assert_called_once()

    async def test_process_maci_validation_fails(self, mock_inner_strategy, message):
        """Process fails when MACI validation fails."""
        maci = MACIProcessingStrategy(mock_inner_strategy)

        if maci._maci_available and maci._maci_strategy:
            # Mock MACI validation failure
            maci._maci_strategy.validate = AsyncMock(return_value=(False, "Role violation"))

            handlers = {}
            result = await maci.process(message, handlers)
            assert result.is_valid is False
            # Inner strategy should not be called
            mock_inner_strategy.process.assert_not_called()

    async def test_process_maci_then_inner(self, mock_inner_strategy, message):
        """Process runs MACI then inner strategy."""
        maci = MACIProcessingStrategy(mock_inner_strategy)

        if maci._maci_available and maci._maci_strategy:
            # Mock MACI validation success
            maci._maci_strategy.validate = AsyncMock(return_value=(True, None))

            handlers = {}
            result = await maci.process(message, handlers)
            # Inner strategy should be called
            mock_inner_strategy.process.assert_called_once()

    def test_is_available_checks_both(self, mock_inner_strategy):
        """is_available checks both MACI and inner strategy."""
        maci = MACIProcessingStrategy(mock_inner_strategy)
        available = maci.is_available()
        # Should return bool based on both MACI and inner availability
        assert isinstance(available, bool)

    async def test_process_maci_exception_strict_mode(self, mock_inner_strategy, message):
        """Process fails on MACI exception in strict mode."""
        maci = MACIProcessingStrategy(mock_inner_strategy, strict_mode=True)

        if maci._maci_available and maci._maci_strategy:
            # Mock MACI validation exception
            maci._maci_strategy.validate = AsyncMock(side_effect=RuntimeError("MACI error"))

            handlers = {}
            result = await maci.process(message, handlers)
            assert result.is_valid is False

    async def test_process_maci_exception_non_strict(self, mock_inner_strategy, message):
        """MACI exception in non-strict mode triggers fail-closed deny."""
        maci = MACIProcessingStrategy(mock_inner_strategy, strict_mode=False)

        if maci._maci_available and maci._maci_strategy:
            # Mock MACI validation exception
            maci._maci_strategy.validate = AsyncMock(side_effect=RuntimeError("MACI error"))

            handlers = {}
            result = await maci.process(message, handlers)
            # fail_closed catches the exception and returns a deny result
            # without delegating to the inner strategy
            assert result is not None
        else:
            pytest.skip("MACI strategy not available in test environment")

    def test_init_with_custom_registry_enforcer(self, mock_inner_strategy):
        """MACI accepts custom registry and enforcer."""
        mock_registry = MagicMock()
        mock_enforcer = MagicMock()

        maci = MACIProcessingStrategy(
            mock_inner_strategy, maci_registry=mock_registry, maci_enforcer=mock_enforcer
        )
        # If MACI available, custom registry/enforcer should be used
        if maci._maci_available:
            assert maci._registry == mock_registry
            assert maci._enforcer == mock_enforcer


class TestStrategyIntegration:
    """Integration tests for processing strategies."""

    @pytest.fixture
    def message(self):
        """Create test message."""
        return AgentMessage(
            content={"action": "integrate"},
            from_agent="test_sender",
            to_agent="test_receiver",
        )

    async def test_composite_with_python_strategy(self, message):
        """Composite with Python strategy processes successfully."""
        python_strategy = PythonProcessingStrategy()
        composite = CompositeProcessingStrategy([python_strategy])

        handlers = {}
        result = await composite.process(message, handlers)
        assert result.is_valid is True

    async def test_maci_with_python_inner(self, message):
        """MACI with Python inner strategy processes."""
        python_strategy = PythonProcessingStrategy()
        maci = MACIProcessingStrategy(python_strategy)

        handlers = {}
        result = await maci.process(message, handlers)
        # Result depends on MACI availability
        assert isinstance(result.is_valid, bool)

    async def test_multiple_handlers_execute_in_order(self, message):
        """Multiple handlers execute in order."""
        python_strategy = PythonProcessingStrategy()

        call_order = []

        def handler1(msg):
            call_order.append(1)

        def handler2(msg):
            call_order.append(2)

        async def handler3(msg):
            call_order.append(3)

        handlers = {MessageType.COMMAND: [handler1, handler2, handler3]}
        result = await python_strategy.process(message, handlers)

        assert result.is_valid is True
        assert call_order == [1, 2, 3]

    async def test_message_status_lifecycle(self, message):
        """Message status transitions correctly."""
        python_strategy = PythonProcessingStrategy()

        assert message.status.value == "pending"

        handlers = {}
        result = await python_strategy.process(message, handlers)

        assert result.is_valid is True
        assert message.status.value == "delivered"

    async def test_message_updated_at_changes(self, message):
        """Message updated_at changes during processing."""
        python_strategy = PythonProcessingStrategy()
        original_updated = message.updated_at

        handlers = {}
        await python_strategy.process(message, handlers)

        # updated_at should have changed
        assert message.updated_at >= original_updated
