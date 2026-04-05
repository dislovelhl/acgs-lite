"""
ACGS-2 Enhanced Agent Bus - Integrations Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the Metering integration.
"""

import os
import sys
import time

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import metering integration module
try:
    from enhanced_agent_bus._compat.acgs_logging import get_logger
except ImportError:
    try:
        from shared.acgs_logging import get_logger
    except ImportError:
        from acgs_logging import get_logger  # type: ignore[import-not-found]

# Import metering components (noqa for path manipulation above)
try:
    from metering import (
        AsyncMeteringQueue,
        MeteringConfig,
        MeteringHooks,
        MeteringMixin,
        get_metering_hooks,
        get_metering_queue,
    )

    from metering_integration import (
        CONSTITUTIONAL_HASH,
        METERING_AVAILABLE,
        metered_operation,
        reset_metering,
    )

    METERING_MODULE_AVAILABLE = True
except ImportError:
    METERING_MODULE_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not METERING_MODULE_AVAILABLE,
    reason=(
        "Metering module not available in this runtime. "
        "Install/enable metering dependencies to run."
    ),
)

# Import models for testing
try:
    from models import AgentMessage, MessageType, Priority
    from validators import ValidationResult
except ImportError:
    from enhanced_agent_bus.models import AgentMessage, MessageType, Priority
    from enhanced_agent_bus.validators import ValidationResult

# Import metering models with fallback mocks
try:
    from src.core.services.metering.app.models import MeterableOperation, MeteringTier
except ImportError:
    # Create mock enums for testing when metering service not available
    from enum import Enum

    class MeterableOperation(Enum):
        """Mock MeterableOperation for testing."""

        CONSTITUTIONAL_VALIDATION = "constitutional_validation"
        POLICY_EVALUATION = "policy_evaluation"
        MESSAGE_PROCESSING = "message_processing"

    class MeteringTier(Enum):
        """Mock MeteringTier for testing."""

        STANDARD = "standard"
        PREMIUM = "premium"


# Test fixtures
@pytest.fixture
def metering_config():
    """Create a metering configuration for testing."""
    return MeteringConfig(
        enabled=True,
        aggregation_interval_seconds=1,
        max_queue_size=100,
        batch_size=10,
        flush_interval_seconds=0.1,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


@pytest.fixture
def disabled_metering_config():
    """Create a disabled metering configuration."""
    return MeteringConfig(enabled=False)


@pytest.fixture
async def metering_queue(metering_config):
    """Create and start a metering queue for testing."""
    reset_metering()
    queue = AsyncMeteringQueue(metering_config)
    # Don't start the service to avoid external dependencies
    queue._running = True
    queue.config.enabled = True
    yield queue
    queue._running = False


@pytest.fixture
def metering_hooks(metering_queue):
    """Create metering hooks for testing."""
    return MeteringHooks(metering_queue)


@pytest.fixture
def sample_message():
    """Create a sample message for testing."""
    return AgentMessage(
        message_id="test-msg-001",
        from_agent="test-agent-1",
        to_agent="test-agent-2",
        message_type=MessageType.GOVERNANCE_REQUEST,
        content="Test message content",
        tenant_id="test-tenant",
        priority=Priority.NORMAL,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


class TestMeteringConfig:
    """Test MeteringConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = MeteringConfig()
        assert config.enabled == METERING_AVAILABLE
        assert config.aggregation_interval_seconds == 60
        assert config.max_queue_size == 10000
        assert config.batch_size == 100
        assert config.flush_interval_seconds == 1.0
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_config(self, metering_config):
        """Test custom configuration values."""
        assert metering_config.enabled is True
        assert metering_config.aggregation_interval_seconds == 1
        assert metering_config.max_queue_size == 100
        assert metering_config.batch_size == 10
        assert metering_config.flush_interval_seconds == 0.1

    def test_disabled_config(self, disabled_metering_config):
        """Test disabled configuration."""
        assert disabled_metering_config.enabled is False


class TestAsyncMeteringQueue:
    """Test AsyncMeteringQueue class."""

    async def test_queue_initialization(self, metering_config):
        """Test queue initialization."""
        queue = AsyncMeteringQueue(metering_config)
        assert queue._running is False
        assert queue._events_queued == 0
        assert queue._events_flushed == 0
        assert queue._events_dropped == 0

    async def test_enqueue_nowait(self, metering_queue):
        """Test non-blocking event enqueue."""
        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        success = metering_queue.enqueue_nowait(
            tenant_id="test-tenant",
            operation=MeterableOperation.CONSTITUTIONAL_VALIDATION,
            tier=MeteringTier.STANDARD,
            agent_id="test-agent",
            latency_ms=1.5,
            compliance_score=1.0,
        )

        assert success is True
        assert metering_queue._events_queued == 1
        assert metering_queue._queue.qsize() == 1

    async def test_enqueue_when_disabled(self, disabled_metering_config):
        """Test enqueue when metering is disabled."""
        queue = AsyncMeteringQueue(disabled_metering_config)

        success = queue.enqueue_nowait(
            tenant_id="test-tenant",
            operation=None,
            latency_ms=1.0,
        )

        assert success is False
        assert queue._events_queued == 0

    async def test_queue_overflow_handling(self, metering_config):
        """Test queue overflow handling."""
        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        # Create a queue with very small max size
        small_config = MeteringConfig(
            enabled=True,
            max_queue_size=2,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        queue = AsyncMeteringQueue(small_config)
        queue._running = True
        queue.config.enabled = True

        # Fill the queue
        for _i in range(5):
            queue.enqueue_nowait(
                tenant_id="test-tenant",
                operation=MeterableOperation.CONSTITUTIONAL_VALIDATION,
                tier=MeteringTier.STANDARD,
                latency_ms=1.0,
            )

        # Should have 2 queued and 3 dropped
        assert queue._events_queued == 2
        assert queue._events_dropped == 3

    async def test_get_metrics(self, metering_queue):
        """Test getting queue metrics."""
        metrics = metering_queue.get_metrics()

        assert "events_queued" in metrics
        assert "events_flushed" in metrics
        assert "events_dropped" in metrics
        assert "queue_size" in metrics
        assert "running" in metrics
        assert "enabled" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestMeteringHooks:
    """Test MeteringHooks class."""

    def test_on_constitutional_validation(self, metering_hooks, metering_queue):
        """Test constitutional validation event recording."""
        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        metering_hooks.on_constitutional_validation(
            tenant_id="test-tenant",
            agent_id="test-agent",
            is_valid=True,
            latency_ms=0.5,
            metadata={"test": "value"},
        )

        assert metering_queue._events_queued == 1

    def test_on_agent_message(self, metering_hooks, metering_queue):
        """Test agent message event recording."""
        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        metering_hooks.on_agent_message(
            tenant_id="test-tenant",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type="governance",
            latency_ms=1.0,
            is_valid=True,
        )

        assert metering_queue._events_queued == 1

    def test_on_policy_evaluation(self, metering_hooks, metering_queue):
        """Test policy evaluation event recording."""
        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        metering_hooks.on_policy_evaluation(
            tenant_id="test-tenant",
            agent_id="test-agent",
            policy_name="constitutional_check",
            decision="allow",
            latency_ms=2.0,
        )

        assert metering_queue._events_queued == 1

    def test_on_deliberation_request(self, metering_hooks, metering_queue):
        """Test deliberation request event recording."""
        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        metering_hooks.on_deliberation_request(
            tenant_id="test-tenant",
            agent_id="test-agent",
            impact_score=0.85,
            latency_ms=5.0,
        )

        assert metering_queue._events_queued == 1

    def test_on_hitl_approval(self, metering_hooks, metering_queue):
        """Test HITL approval event recording."""
        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        metering_hooks.on_hitl_approval(
            tenant_id="test-tenant",
            agent_id="test-agent",
            approver_id="approver-1",
            approved=True,
            latency_ms=10.0,
        )

        assert metering_queue._events_queued == 1


class TestMeteringMixin:
    """Test MeteringMixin class."""

    def test_configure_metering(self):
        """Test metering configuration."""

        class TestClass(MeteringMixin):
            pass

        obj = TestClass()
        obj.configure_metering()

        assert obj._metering_config is not None
        assert obj._metering_queue is not None
        assert obj._metering_hooks is not None

    async def test_start_stop_metering(self):
        """Test starting and stopping metering."""

        class TestClass(MeteringMixin):
            pass

        obj = TestClass()
        obj.configure_metering(MeteringConfig(enabled=True))

        # Mock the metering service to avoid external dependencies
        obj._metering_queue._metering_service = None

        await obj.start_metering()
        assert obj._metering_queue._running is True

        await obj.stop_metering()
        assert obj._metering_queue._running is False

    def test_get_metering_metrics(self):
        """Test getting metering metrics."""

        class TestClass(MeteringMixin):
            pass

        obj = TestClass()
        obj.configure_metering()

        metrics = obj.get_metering_metrics()
        assert "enabled" in metrics


class TestSingletons:
    """Test singleton functions."""

    def test_get_metering_queue(self):
        """Test getting metering queue singleton."""
        reset_metering()
        queue1 = get_metering_queue()
        queue2 = get_metering_queue()
        assert queue1 is queue2

    def test_get_metering_hooks(self):
        """Test getting metering hooks singleton."""
        reset_metering()
        hooks1 = get_metering_hooks()
        hooks2 = get_metering_hooks()
        assert hooks1 is hooks2

    def test_reset_metering(self):
        """Test resetting metering singletons."""
        reset_metering()
        queue1 = get_metering_queue()
        reset_metering()
        queue2 = get_metering_queue()
        assert queue1 is not queue2


class TestMeteredOperationDecorator:
    """Test metered_operation decorator."""

    async def test_decorator_basic(self):
        """Test basic decorator functionality."""
        reset_metering()

        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def test_function(tenant_id: str) -> bool:
            return True

        result = await test_function(tenant_id="test-tenant")
        assert result is True

    async def test_decorator_with_validation_result(self):
        """Test decorator with ValidationResult return."""
        reset_metering()

        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def test_function() -> ValidationResult:
            return ValidationResult(is_valid=True)

        result = await test_function()
        assert result.is_valid is True

    async def test_decorator_with_exception(self):
        """Test decorator handling exceptions."""
        reset_metering()

        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def test_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await test_function()

    async def test_decorator_with_object_tenant_id(self):
        """Test decorator extracts tenant_id from object attribute."""
        reset_metering()

        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        class MessageLike:
            tenant_id = "extracted-tenant"
            from_agent = "test-agent"

        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def test_function(msg: MessageLike) -> bool:
            return True

        result = await test_function(MessageLike())
        assert result is True

    async def test_decorator_with_custom_extract_tenant(self):
        """Test decorator with custom extract_tenant callable."""
        reset_metering()

        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        def custom_extract_tenant(obj):
            return getattr(obj, "custom_tenant", "fallback")

        class CustomObject:
            custom_tenant = "custom-tenant-id"

        @metered_operation(
            MeterableOperation.CONSTITUTIONAL_VALIDATION,
            extract_tenant=custom_extract_tenant,
        )
        async def test_function(obj) -> bool:
            return True

        result = await test_function(CustomObject())
        assert result is True

    async def test_decorator_with_custom_extract_agent(self):
        """Test decorator with custom extract_agent callable."""
        reset_metering()

        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        def custom_extract_agent(obj):
            return getattr(obj, "agent_name", None)

        class AgentObject:
            agent_name = "custom-agent"

        @metered_operation(
            MeterableOperation.CONSTITUTIONAL_VALIDATION,
            extract_agent=custom_extract_agent,
        )
        async def test_function(obj) -> bool:
            return True

        result = await test_function(AgentObject())
        assert result is True

    async def test_decorator_extract_tenant_exception_handling(self):
        """Test decorator handles extract_tenant exceptions gracefully."""
        reset_metering()

        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        def failing_extract_tenant(obj):
            raise ValueError("Extraction failed")

        @metered_operation(
            MeterableOperation.CONSTITUTIONAL_VALIDATION,
            extract_tenant=failing_extract_tenant,
        )
        async def test_function(obj) -> bool:
            return True

        # Should not raise - exception is caught and defaults used
        result = await test_function(object())
        assert result is True

    async def test_decorator_extract_agent_exception_handling(self):
        """Test decorator handles extract_agent exceptions gracefully."""
        reset_metering()

        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        def failing_extract_agent(obj):
            raise RuntimeError("Agent extraction failed")

        @metered_operation(
            MeterableOperation.CONSTITUTIONAL_VALIDATION,
            extract_agent=failing_extract_agent,
        )
        async def test_function(obj) -> bool:
            return True

        # Should not raise - exception is caught and None used
        result = await test_function(object())
        assert result is True


class TestLatencyImpact:
    """Test that metering has minimal latency impact."""

    async def test_enqueue_latency(self, metering_queue):
        """Test that enqueue operation is fast."""
        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        # Measure enqueue latency
        iterations = 1000
        start = time.perf_counter()

        for _ in range(iterations):
            metering_queue.enqueue_nowait(
                tenant_id="test-tenant",
                operation=MeterableOperation.CONSTITUTIONAL_VALIDATION,
                tier=MeteringTier.STANDARD,
                latency_ms=1.0,
            )

        end = time.perf_counter()
        avg_latency_us = ((end - start) / iterations) * 1_000_000

        # Enqueue should be extremely fast (< 100 microseconds per operation)
        # This ensures minimal impact on P99 latency
        assert avg_latency_us < 100, f"Enqueue latency too high: {avg_latency_us:.2f}us"
        logger.info(f"\nAverage enqueue latency: {avg_latency_us:.2f}us")

    async def test_hooks_latency(self, metering_hooks, metering_queue):
        """Test that hooks have minimal latency."""
        if not METERING_AVAILABLE:
            pytest.skip("Metering service not available")

        # Measure hook call latency
        iterations = 1000
        start = time.perf_counter()

        for _ in range(iterations):
            metering_hooks.on_constitutional_validation(
                tenant_id="test-tenant",
                agent_id="test-agent",
                is_valid=True,
                latency_ms=1.0,
            )

        end = time.perf_counter()
        avg_latency_us = ((end - start) / iterations) * 1_000_000

        # Hook calls should be extremely fast (< 150 microseconds per operation)
        assert avg_latency_us < 150, f"Hook latency too high: {avg_latency_us:.2f}us"
        logger.info(f"\nAverage hook call latency: {avg_latency_us:.2f}us")


class TestConstitutionalCompliance:
    """Test constitutional compliance in metering."""

    def test_constitutional_hash_in_config(self, metering_config):
        """Test that constitutional hash is in config."""
        assert metering_config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_in_metrics(self, metering_queue):
        """Test that constitutional hash is in metrics."""
        metrics = metering_queue.get_metrics()
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestIntegrationWithMessageProcessor:
    """Test integration with MessageProcessor."""

    async def test_processor_with_metering(self, sample_message, metering_hooks):
        """Test MessageProcessor with metering hooks."""
        try:
            from message_processor import MessageProcessor
        except ImportError:
            from enhanced_agent_bus.message_processor import MessageProcessor

        # Create processor with metering hooks
        processor = MessageProcessor(
            metering_hooks=metering_hooks,
            enable_metering=True,
        )

        # Process a message
        result = await processor.process(sample_message)

        # Verify processing worked
        assert result is not None
        assert "validation_latency_ms" in result.metadata or result.is_valid is not None

    async def test_processor_metering_disabled(self, sample_message):
        """Test MessageProcessor with metering disabled."""
        try:
            from message_processor import MessageProcessor
        except ImportError:
            from enhanced_agent_bus.message_processor import MessageProcessor

        # Create processor without metering
        processor = MessageProcessor(
            enable_metering=False,
        )

        # Process a message
        result = await processor.process(sample_message)

        # Verify processing worked
        assert result is not None


class TestIntegrationWithAgentBus:
    """Test integration with EnhancedAgentBus."""

    async def test_bus_with_metering(self, sample_message):
        """Test EnhancedAgentBus with metering enabled."""
        try:
            from agent_bus import EnhancedAgentBus
        except ImportError:
            from enhanced_agent_bus.agent_bus import EnhancedAgentBus

        # Create bus with metering
        bus = EnhancedAgentBus(
            enable_metering=True,
            metering_config=MeteringConfig(enabled=True),
        )

        await bus.start()

        try:
            # Register an agent
            await bus.register_agent("test-agent-1", "test")
            await bus.register_agent("test-agent-2", "test")

            # Send a message
            await bus.send_message(sample_message)

            # Verify metering is enabled
            metrics = bus.get_metrics()
            assert "metering_enabled" in metrics

        finally:
            await bus.stop()

    async def test_bus_metering_disabled(self, sample_message):
        """Test EnhancedAgentBus with metering disabled."""
        try:
            from agent_bus import EnhancedAgentBus
        except ImportError:
            from enhanced_agent_bus.agent_bus import EnhancedAgentBus

        # Create bus without metering
        bus = EnhancedAgentBus(
            enable_metering=False,
        )

        await bus.start()

        try:
            metrics = bus.get_metrics()
            assert metrics["metering_enabled"] is False

        finally:
            await bus.stop()


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
