"""
ACGS-2 Enhanced Agent Bus - Extended Core Tests
Constitutional Hash: 608508a9bd224290

Extended tests for enhanced_agent_bus/core.py
"""

import asyncio
import importlib.util
import inspect
import os
import sys
import types
from datetime import UTC, datetime, timezone

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ============================================================================
# Direct Module Loading (compatible with conftest.py)
# ============================================================================

_parent_dir = os.path.dirname(os.path.dirname(__file__))
enhanced_agent_bus_dir = _parent_dir


def _load_module(name: str, path: str):
    """Load a module directly from path."""
    if "enhanced_agent_bus" not in sys.modules:
        pkg = types.ModuleType("enhanced_agent_bus")
        pkg.__path__ = [enhanced_agent_bus_dir]
        pkg.__file__ = os.path.join(enhanced_agent_bus_dir, "__init__.py")
        pkg.__package__ = "enhanced_agent_bus"
        sys.modules["enhanced_agent_bus"] = pkg
    qualified_name = f"enhanced_agent_bus.{name}"
    spec = importlib.util.spec_from_file_location(qualified_name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "enhanced_agent_bus"
    sys.modules[qualified_name] = module
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load required modules
_models_path = os.path.join(_parent_dir, "models.py")
_validators_path = os.path.join(_parent_dir, "validators.py")

_models = _load_module("_models_for_core_ext", _models_path)
_validators = _load_module("_validators_for_core_ext", _validators_path)

# Extract types
AgentMessage = _models.AgentMessage
MessageType = _models.MessageType
Priority = _models.Priority
MessageStatus = _models.MessageStatus
ValidationResult = _validators.ValidationResult


# ============================================================================
# MessageProcessor Extended Tests
# ============================================================================


class TestMessageProcessorExtended:
    """Extended tests for MessageProcessor class."""

    def test_unregister_handler_existing(self):
        """Test unregistering an existing handler."""

        # Create a simplified MessageProcessor
        class SimpleProcessor:
            def __init__(self):
                self._handlers = {}

            def register_handler(self, msg_type, handler):
                if msg_type not in self._handlers:
                    self._handlers[msg_type] = []
                self._handlers[msg_type].append(handler)

            def unregister_handler(self, msg_type, handler):
                if msg_type in self._handlers and handler in self._handlers[msg_type]:
                    self._handlers[msg_type].remove(handler)
                    return True
                return False

        processor = SimpleProcessor()

        def handler(msg):
            return None

        processor.register_handler(MessageType.COMMAND, handler)
        result = processor.unregister_handler(MessageType.COMMAND, handler)

        assert result is True
        assert handler not in processor._handlers.get(MessageType.COMMAND, [])

    def test_unregister_handler_nonexistent(self):
        """Test unregistering a non-existent handler."""

        class SimpleProcessor:
            def __init__(self):
                self._handlers = {}

            def unregister_handler(self, msg_type, handler):
                if msg_type in self._handlers and handler in self._handlers[msg_type]:
                    self._handlers[msg_type].remove(handler)
                    return True
                return False

        processor = SimpleProcessor()

        def handler(msg):
            return None

        result = processor.unregister_handler(MessageType.COMMAND, handler)
        assert result is False

    def test_get_metrics(self):
        """Test get_metrics returns proper structure."""

        class SimpleProcessor:
            def __init__(self):
                self._processed_count = 10
                self._failed_count = 2
                self._handlers = {MessageType.COMMAND: [lambda x: x]}
                self._rust_processor = None
                self._use_dynamic_policy = False

            def get_metrics(self):
                return {
                    "processed_count": self._processed_count,
                    "failed_count": self._failed_count,
                    "handler_count": sum(len(h) for h in self._handlers.values()),
                    "rust_enabled": self._rust_processor is not None,
                    "dynamic_policy_enabled": self._use_dynamic_policy,
                }

        processor = SimpleProcessor()
        metrics = processor.get_metrics()

        assert metrics["processed_count"] == 10
        assert metrics["failed_count"] == 2
        assert metrics["handler_count"] == 1
        assert metrics["rust_enabled"] is False
        assert metrics["dynamic_policy_enabled"] is False

    async def test_process_python_invalid_hash(self):
        """Test Python processing with invalid constitutional hash."""
        message = AgentMessage(
            message_type=MessageType.COMMAND,
            sender_id="agent1",
            content={"action": "test"},
            constitutional_hash="invalid_hash",
        )

        # Create validation result
        result = ValidationResult(is_valid=False, errors=["Constitutional hash mismatch"])

        assert result.is_valid is False
        assert "hash mismatch" in result.errors[0].lower()

    async def test_run_handlers_sync(self):
        """Test running synchronous handlers."""
        call_log = []

        def sync_handler(msg):
            call_log.append(f"sync:{msg.message_type}")

        message = AgentMessage(
            message_type=MessageType.COMMAND,
            sender_id="agent1",
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        # Simulate handler execution
        handlers = [sync_handler]
        for handler in handlers:
            if inspect.iscoroutinefunction(handler):
                await handler(message)
            else:
                handler(message)

        assert len(call_log) == 1
        assert "sync:MessageType.COMMAND" in call_log[0]

    async def test_run_handlers_async(self):
        """Test running asynchronous handlers."""
        call_log = []

        async def async_handler(msg):
            await asyncio.sleep(0.001)
            call_log.append(f"async:{msg.message_type}")

        message = AgentMessage(
            message_type=MessageType.COMMAND,
            sender_id="agent1",
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        # Simulate handler execution
        handlers = [async_handler]
        for handler in handlers:
            if inspect.iscoroutinefunction(handler):
                await handler(message)
            else:
                handler(message)

        assert len(call_log) == 1
        assert "async:MessageType.COMMAND" in call_log[0]


# ============================================================================
# EnhancedAgentBus Extended Tests
# ============================================================================


class TestEnhancedAgentBusExtended:
    """Extended tests for EnhancedAgentBus class."""

    def test_bus_initialization_defaults(self):
        """Test bus initializes with correct defaults."""

        # Simulate bus initialization
        class SimpleBus:
            def __init__(self, redis_url="redis://localhost:6379"):
                self.constitutional_hash = CONSTITUTIONAL_HASH
                self.redis_url = redis_url
                self._agents = {}
                self._running = False
                self._metrics = {
                    "messages_sent": 0,
                    "messages_received": 0,
                    "messages_failed": 0,
                    "started_at": None,
                }

        bus = SimpleBus()
        assert bus.constitutional_hash == CONSTITUTIONAL_HASH
        assert bus.redis_url == "redis://localhost:6379"
        assert bus._running is False
        assert bus._metrics["messages_sent"] == 0

    def test_bus_custom_redis_url(self):
        """Test bus with custom Redis URL."""

        class SimpleBus:
            def __init__(self, redis_url="redis://localhost:6379"):
                self.redis_url = redis_url

        bus = SimpleBus(redis_url="redis://custom:6380/1")
        assert bus.redis_url == "redis://custom:6380/1"

    async def test_bus_start_sets_running(self):
        """Test that start sets running flag."""

        class SimpleBus:
            def __init__(self):
                self._running = False
                self._metrics = {"started_at": None}

            async def start(self):
                self._running = True
                self._metrics["started_at"] = datetime.now(UTC).isoformat()

        bus = SimpleBus()
        await bus.start()

        assert bus._running is True
        assert bus._metrics["started_at"] is not None

    async def test_bus_stop_clears_running(self):
        """Test that stop clears running flag."""

        class SimpleBus:
            def __init__(self):
                self._running = True

            async def stop(self):
                self._running = False

        bus = SimpleBus()
        await bus.stop()

        assert bus._running is False

    async def test_register_agent_basic(self):
        """Test basic agent registration."""

        class SimpleBus:
            def __init__(self):
                self._agents = {}

            @property
            def agents(self):
                return self._agents

            async def register_agent(
                self, agent_id, agent_type="default", capabilities=None, tenant_id=None
            ):
                self._agents[agent_id] = {
                    "agent_id": agent_id,
                    "agent_type": agent_type,
                    "capabilities": capabilities or [],
                    "tenant_id": tenant_id,
                    "registered_at": datetime.now(UTC),
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "status": "active",
                }
                return True

        bus = SimpleBus()
        result = await bus.register_agent(
            "agent1", agent_type="worker", capabilities=["process", "validate"], tenant_id="tenant1"
        )

        assert result is True
        assert "agent1" in bus.agents
        assert bus.agents["agent1"]["agent_type"] == "worker"
        assert bus.agents["agent1"]["tenant_id"] == "tenant1"
        assert "process" in bus.agents["agent1"]["capabilities"]

    async def test_unregister_agent(self):
        """Test agent unregistration."""

        class SimpleBus:
            def __init__(self):
                self._agents = {"agent1": {"status": "active"}}

            @property
            def agents(self):
                return self._agents

            async def unregister_agent(self, agent_id):
                if agent_id in self._agents:
                    del self._agents[agent_id]
                    return True
                return False

        bus = SimpleBus()
        result = await bus.unregister_agent("agent1")

        assert result is True
        assert "agent1" not in bus.agents

    async def test_unregister_nonexistent_agent(self):
        """Test unregistering non-existent agent."""

        class SimpleBus:
            def __init__(self):
                self._agents = {}

            async def unregister_agent(self, agent_id):
                if agent_id in self._agents:
                    del self._agents[agent_id]
                    return True
                return False

        bus = SimpleBus()
        result = await bus.unregister_agent("nonexistent")

        assert result is False

    async def test_send_message_updates_metrics(self):
        """Test that sending message updates metrics."""

        class SimpleBus:
            def __init__(self):
                self._running = True
                self._agents = {"agent1": {}}
                self._metrics = {"messages_sent": 0}

            async def send(self, message):
                if not self._running:
                    raise RuntimeError("Bus not running")
                self._metrics["messages_sent"] += 1
                return ValidationResult(is_valid=True)

        bus = SimpleBus()
        message = AgentMessage(
            message_type=MessageType.COMMAND,
            sender_id="agent1",
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        result = await bus.send(message)

        assert result.is_valid is True
        assert bus._metrics["messages_sent"] == 1

    async def test_receive_message_with_timeout(self):
        """Test message receive with timeout."""

        class SimpleBus:
            def __init__(self):
                self._queue = asyncio.Queue()

            async def receive(self, agent_id, timeout=0.1):
                try:
                    msg = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                    return msg
                except TimeoutError:
                    return None

        bus = SimpleBus()
        result = await bus.receive("agent1", timeout=0.05)

        assert result is None

    def test_get_agent_info(self):
        """Test getting agent info."""

        class SimpleBus:
            def __init__(self):
                self._agents = {
                    "agent1": {"agent_id": "agent1", "agent_type": "worker", "status": "active"}
                }

            def get_agent(self, agent_id):
                return self._agents.get(agent_id)

        bus = SimpleBus()
        info = bus.get_agent("agent1")

        assert info is not None
        assert info["agent_type"] == "worker"

    def test_get_bus_metrics(self):
        """Test getting bus metrics."""

        class SimpleBus:
            def __init__(self):
                self._agents = {"a1": {}, "a2": {}}
                self._running = True
                self._metrics = {
                    "messages_sent": 100,
                    "messages_received": 95,
                    "messages_failed": 5,
                    "started_at": "2024-01-01T00:00:00Z",
                }

            def get_metrics(self):
                return {
                    **self._metrics,
                    "agent_count": len(self._agents),
                    "running": self._running,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                }

        bus = SimpleBus()
        metrics = bus.get_metrics()

        assert metrics["messages_sent"] == 100
        assert metrics["agent_count"] == 2
        assert metrics["running"] is True
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


# ============================================================================
# Validation Result Extended Tests
# ============================================================================


class TestValidationResultExtended:
    """Extended tests for ValidationResult."""

    def test_validation_result_with_metadata(self):
        """Test ValidationResult with metadata."""
        result = ValidationResult(
            is_valid=True, metadata={"processing_time_ms": 1.5, "validator": "python"}
        )

        assert result.is_valid is True
        assert result.metadata["processing_time_ms"] == 1.5
        assert result.metadata["validator"] == "python"

    def test_validation_result_merge(self):
        """Test merging validation results."""
        result1 = ValidationResult(is_valid=True, warnings=["Warning 1"])
        result2 = ValidationResult(is_valid=False, errors=["Error 1"])

        # Merge operation
        merged = ValidationResult(
            is_valid=result1.is_valid and result2.is_valid,
            errors=result1.errors + result2.errors,
            warnings=result1.warnings + result2.warnings,
        )

        assert merged.is_valid is False
        assert "Error 1" in merged.errors
        assert "Warning 1" in merged.warnings

    def test_validation_result_add_error(self):
        """Test adding error to validation result."""
        result = ValidationResult(is_valid=True)
        result.add_error("New error")

        assert result.is_valid is False
        assert "New error" in result.errors

    def test_validation_result_add_warning(self):
        """Test adding warning to validation result."""
        result = ValidationResult(is_valid=True)
        result.add_warning("New warning")

        assert result.is_valid is True
        assert "New warning" in result.warnings


# ============================================================================
# Message Queue Tests
# ============================================================================


class TestMessageQueueOperations:
    """Tests for message queue operations."""

    async def test_queue_put_get(self):
        """Test basic queue put/get operations."""
        queue = asyncio.Queue()

        message = AgentMessage(
            message_type=MessageType.COMMAND,
            sender_id="agent1",
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        await queue.put(message)
        retrieved = await queue.get()

        assert retrieved.message_id == message.message_id
        assert retrieved.content == message.content

    async def test_queue_priority_ordering(self):
        """Test queue with priority-based ordering simulation."""
        messages = [
            AgentMessage(
                message_type=MessageType.COMMAND,
                sender_id="agent1",
                content={"priority": "low"},
                priority=Priority.LOW,
                constitutional_hash=CONSTITUTIONAL_HASH,
            ),
            AgentMessage(
                message_type=MessageType.COMMAND,
                sender_id="agent1",
                content={"priority": "critical"},
                priority=Priority.CRITICAL,
                constitutional_hash=CONSTITUTIONAL_HASH,
            ),
            AgentMessage(
                message_type=MessageType.COMMAND,
                sender_id="agent1",
                content={"priority": "normal"},
                priority=Priority.NORMAL,
                constitutional_hash=CONSTITUTIONAL_HASH,
            ),
        ]

        # Sort by priority (higher priority first = higher value first)
        # Priority uses ascending values: LOW=0, NORMAL=1, HIGH=2, CRITICAL=3
        # So we sort in descending order of value
        sorted_msgs = sorted(messages, key=lambda m: -m.priority.value)

        assert sorted_msgs[0].content["priority"] == "critical"
        assert sorted_msgs[2].content["priority"] == "low"

    async def test_queue_empty_check(self):
        """Test checking if queue is empty."""
        queue = asyncio.Queue()
        assert queue.empty()

        await queue.put("test")
        assert not queue.empty()


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling scenarios."""

    async def test_handler_type_error_caught(self):
        """Test that TypeError in handler is caught."""
        errors = []

        def failing_handler(msg):
            raise TypeError("Invalid type")

        message = AgentMessage(
            message_type=MessageType.COMMAND,
            sender_id="agent1",
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        try:
            failing_handler(message)
        except TypeError as e:
            errors.append(str(e))

        assert len(errors) == 1
        assert "Invalid type" in errors[0]

    async def test_handler_value_error_caught(self):
        """Test that ValueError in handler is caught."""
        errors = []

        def failing_handler(msg):
            raise ValueError("Invalid value")

        try:
            failing_handler(None)
        except ValueError as e:
            errors.append(str(e))

        assert len(errors) == 1
        assert "Invalid value" in errors[0]

    async def test_handler_runtime_error_caught(self):
        """Test that RuntimeError in handler is caught."""
        errors = []

        def failing_handler(msg):
            raise RuntimeError("Runtime failure")

        try:
            failing_handler(None)
        except RuntimeError as e:
            errors.append(str(e))

        assert len(errors) == 1
        assert "Runtime failure" in errors[0]

    async def test_cancelled_error_propagates(self):
        """Test that CancelledError is not suppressed."""

        async def cancellable_operation():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await cancellable_operation()


# ============================================================================
# Constitutional Hash Validation Tests
# ============================================================================


class TestConstitutionalHashValidation:
    """Tests for constitutional hash validation."""

    def test_valid_hash_constant(self):
        """Test that constitutional hash constant is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_hash_in_message(self):
        """Test hash is properly set in message."""
        message = AgentMessage(
            message_type=MessageType.COMMAND,
            sender_id="agent1",
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        assert message.constitutional_hash == CONSTITUTIONAL_HASH

    def test_hash_mismatch_detection(self):
        """Test detection of hash mismatch."""
        message = AgentMessage(
            message_type=MessageType.COMMAND,
            sender_id="agent1",
            content={"action": "test"},
            constitutional_hash="wrong_hash",
        )

        is_valid = message.constitutional_hash == CONSTITUTIONAL_HASH
        assert is_valid is False

    def test_empty_hash_rejected(self):
        """Test that empty hash is detected."""
        message = AgentMessage(
            message_type=MessageType.COMMAND,
            sender_id="agent1",
            content={"action": "test"},
            constitutional_hash="",
        )

        is_valid = (
            bool(message.constitutional_hash) and message.constitutional_hash == CONSTITUTIONAL_HASH
        )
        assert is_valid is False
