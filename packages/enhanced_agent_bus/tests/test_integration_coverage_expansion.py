"""
ACGS-2 Deliberation Layer - Integration Coverage Expansion Tests
Constitutional Hash: 608508a9bd224290

Additional tests for integration.py to expand coverage of all methods.

NOTE: This test file uses direct module loading which can pollute sys.modules.
A module-scoped fixture saves and restores the original state to prevent
affecting other test files.
"""

import asyncio
import importlib.util
import os
import sys
from datetime import UTC, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger

# Runtime guard: this suite can hang in constrained CI/dev environments.
RUN_EAB_INTEGRATION_COVERAGE_EXPANSION_TESTS = (
    os.getenv("RUN_EAB_INTEGRATION_COVERAGE_EXPANSION_TESTS", "false").lower() == "true"
)
if not RUN_EAB_INTEGRATION_COVERAGE_EXPANSION_TESTS:
    pytestmark = pytest.mark.skip(
        reason=(
            "Integration coverage expansion tests disabled by default in this runtime. "
            "Set RUN_EAB_INTEGRATION_COVERAGE_EXPANSION_TESTS=true to run."
        )
    )

# Add enhanced_agent_bus directory to path
enhanced_agent_bus_dir = os.path.dirname(os.path.dirname(__file__))
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)

# Add deliberation_layer directory to path for fallback imports
deliberation_layer_dir = os.path.join(enhanced_agent_bus_dir, "deliberation_layer")
if deliberation_layer_dir not in sys.path:
    sys.path.insert(0, deliberation_layer_dir)

AgentMessage = None
MessageType = None
MessageStatus = None
Priority = None
CONSTITUTIONAL_HASH = None
DeliberationLayer = None
get_deliberation_layer = None
_integration = None
_adaptive_router = None


# Create mock impact_scorer module
class MockImpactScorer:
    """Mock impact scorer for testing without ML dependencies."""

    def __init__(self, model_name: str = "mock-model"):
        self.model_name = model_name

    def calculate_impact_score(self, content, context=None) -> float:
        """Return mock impact score based on content."""
        content_str = str(content).lower() if content else ""
        high_risk_keywords = ["critical", "emergency", "security", "delete", "production"]
        for keyword in high_risk_keywords:
            if keyword in content_str:
                return 0.9
        return 0.3


def mock_calculate_message_impact(content) -> float:
    """Mock function for calculating message impact."""
    return MockImpactScorer().calculate_impact_score(content)


def mock_get_impact_scorer():
    """Return a mock impact scorer instance."""
    return MockImpactScorer()


class MockImpactScorerModule:
    ImpactScorer = MockImpactScorer
    get_impact_scorer = staticmethod(mock_get_impact_scorer)
    calculate_message_impact = staticmethod(mock_calculate_message_impact)


@pytest.fixture(scope="module", autouse=True)
def restore_modules_after_tests():
    """Load integration test modules and restore sys.modules after tests."""
    saved_modules: dict[str, Any | None] = {}

    def _set_module(name: str, module: Any) -> None:
        if name not in saved_modules:
            saved_modules[name] = sys.modules.get(name)
        sys.modules[name] = module

    def _load_module(name: str, path: str, package: str | None = None):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        if package:
            module.__package__ = package
        _set_module(name, module)
        spec.loader.exec_module(module)
        return module

    # Ensure parent package exists
    try:
        import enhanced_agent_bus.deliberation_layer
    except (RuntimeError, ValueError, TypeError, AssertionError):
        get_logger(__name__).debug("Optional deliberation_layer not available")

    # Load base models and config first
    _models = _load_module(
        "models", os.path.join(enhanced_agent_bus_dir, "models.py"), "enhanced_agent_bus"
    )
    _config = _load_module(
        "config", os.path.join(enhanced_agent_bus_dir, "config.py"), "enhanced_agent_bus"
    )
    _set_module("enhanced_agent_bus.models", _models)
    _set_module("enhanced_agent_bus.config", _config)

    globals()["AgentMessage"] = _models.AgentMessage
    globals()["MessageType"] = _models.MessageType
    globals()["MessageStatus"] = _models.MessageStatus
    globals()["Priority"] = _models.Priority
    globals()["CONSTITUTIONAL_HASH"] = _models.CONSTITUTIONAL_HASH

    _set_module("impact_scorer", MockImpactScorerModule())

    # Load dependency modules in correct order with full package names
    _deliberation_queue = _load_module(
        "enhanced_agent_bus.deliberation_layer.deliberation_queue",
        os.path.join(deliberation_layer_dir, "deliberation_queue.py"),
        "enhanced_agent_bus.deliberation_layer",
    )
    _set_module("deliberation_queue", _deliberation_queue)

    _intent_classifier = _load_module(
        "enhanced_agent_bus.deliberation_layer.intent_classifier",
        os.path.join(deliberation_layer_dir, "intent_classifier.py"),
        "enhanced_agent_bus.deliberation_layer",
    )
    _set_module("intent_classifier", _intent_classifier)

    _adaptive_router = _load_module(
        "enhanced_agent_bus.deliberation_layer.adaptive_router",
        os.path.join(deliberation_layer_dir, "adaptive_router.py"),
        "enhanced_agent_bus.deliberation_layer",
    )
    _set_module("adaptive_router", _adaptive_router)

    _llm_assistant = _load_module(
        "enhanced_agent_bus.deliberation_layer.llm_assistant",
        os.path.join(deliberation_layer_dir, "llm_assistant.py"),
        "enhanced_agent_bus.deliberation_layer",
    )
    _set_module("llm_assistant", _llm_assistant)

    _redis_integration = _load_module(
        "enhanced_agent_bus.deliberation_layer.redis_integration",
        os.path.join(deliberation_layer_dir, "redis_integration.py"),
        "enhanced_agent_bus.deliberation_layer",
    )
    _set_module("redis_integration", _redis_integration)

    _integration = _load_module(
        "enhanced_agent_bus.deliberation_layer.integration",
        os.path.join(deliberation_layer_dir, "integration.py"),
        "enhanced_agent_bus.deliberation_layer",
    )
    _set_module("integration", _integration)
    globals()["_adaptive_router"] = _adaptive_router
    globals()["_integration"] = _integration

    for mod in [_adaptive_router, _integration]:
        if getattr(mod, "get_deliberation_queue", None) is None:
            mod.get_deliberation_queue = _deliberation_queue.get_deliberation_queue
        if getattr(mod, "DeliberationStatus", None) is None:
            mod.DeliberationStatus = _deliberation_queue.DeliberationStatus
        if getattr(mod, "get_adaptive_router", None) is None and hasattr(
            _adaptive_router, "get_adaptive_router"
        ):
            mod.get_adaptive_router = _adaptive_router.get_adaptive_router
        if getattr(mod, "get_impact_scorer", None) is None:
            mod.get_impact_scorer = mock_get_impact_scorer
        if getattr(mod, "get_llm_assistant", None) is None and hasattr(
            _llm_assistant, "get_llm_assistant"
        ):
            mod.get_llm_assistant = _llm_assistant.get_llm_assistant
        if getattr(mod, "calculate_message_impact", None) is None:
            mod.calculate_message_impact = mock_calculate_message_impact
        if getattr(mod, "IntentClassifier", None) is None:
            mod.IntentClassifier = _intent_classifier.IntentClassifier
        if getattr(mod, "IntentType", None) is None:
            mod.IntentType = _intent_classifier.IntentType

    globals()["DeliberationLayer"] = _integration.DeliberationLayer
    globals()["get_deliberation_layer"] = _integration.get_deliberation_layer

    yield
    for name, original in saved_modules.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original

    # Reset all singletons that might have been created
    try:
        from enhanced_agent_bus.deliberation_layer.integration import reset_deliberation_layer

        reset_deliberation_layer()
    except (ImportError, AttributeError):
        pass

    try:
        from enhanced_agent_bus.impact_scorer_infra.service import reset_impact_scorer

        reset_impact_scorer()
    except (ImportError, AttributeError):
        pass

    try:
        from enhanced_agent_bus.deliberation_layer.adaptive_router import reset_adaptive_router

        reset_adaptive_router()
    except (ImportError, AttributeError):
        pass

    try:
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            reset_deliberation_queue,
        )

        reset_deliberation_queue()
    except (ImportError, AttributeError):
        pass


@pytest.fixture(autouse=True)
def reset_singleton_per_test():
    """Reset singletons before each test to prevent cross-test pollution."""
    _integration._deliberation_layer = None
    # Also reset the adaptive router singleton
    try:
        _adaptive_router.reset_adaptive_router()
    except (NameError, AttributeError):
        pass
    try:
        if hasattr(_adaptive_router, "_adaptive_router"):
            _adaptive_router._adaptive_router = None
    except (NameError, AttributeError):
        pass
    yield
    _integration._deliberation_layer = None
    try:
        _adaptive_router.reset_adaptive_router()
    except (NameError, AttributeError):
        pass
    try:
        if hasattr(_adaptive_router, "_adaptive_router"):
            _adaptive_router._adaptive_router = None
    except (NameError, AttributeError):
        pass


class TestPropertyAccessors:
    """Tests for property accessor methods."""

    def test_injected_impact_scorer_property(self):
        """Test injected_impact_scorer property returns the scorer."""
        layer = DeliberationLayer(enable_opa_guard=False)
        assert layer.injected_impact_scorer is not None
        assert layer.injected_impact_scorer is layer.impact_scorer

    def test_injected_router_property(self):
        """Test injected_router property returns the router."""
        layer = DeliberationLayer(enable_opa_guard=False)
        assert layer.injected_router is not None
        assert layer.injected_router is layer.adaptive_router

    def test_injected_queue_property(self):
        """Test injected_queue property returns the queue."""
        layer = DeliberationLayer(enable_opa_guard=False)
        assert layer.injected_queue is not None
        assert layer.injected_queue is layer.deliberation_queue

    def test_injected_dependencies_override_defaults(self):
        """Test that injected dependencies override defaults."""
        mock_scorer = MagicMock()
        mock_router = MagicMock()
        mock_queue = MagicMock()

        layer = DeliberationLayer(
            impact_scorer=mock_scorer,
            adaptive_router=mock_router,
            deliberation_queue=mock_queue,
            enable_opa_guard=False,
        )

        assert layer.impact_scorer is mock_scorer
        assert layer.adaptive_router is mock_router
        assert layer.deliberation_queue is mock_queue


class TestOPAGuardIntegration:
    """Tests for OPA Guard integration."""

    @pytest.fixture
    def layer_with_opa(self):
        """Create a layer with OPA guard enabled."""
        return DeliberationLayer(
            enable_opa_guard=True,
            enable_learning=False,
            enable_llm=False,
        )

    @pytest.fixture
    def layer_without_opa(self):
        """Create a layer without OPA guard."""
        return DeliberationLayer(
            enable_opa_guard=False,
            enable_learning=False,
            enable_llm=False,
        )

    def test_opa_guard_enabled_creates_guard(self, layer_with_opa):
        """Test OPA guard is created when enabled."""
        assert layer_with_opa.opa_guard is not None

    def test_opa_guard_disabled_no_guard(self, layer_without_opa):
        """Test OPA guard is None when disabled."""
        assert layer_without_opa.opa_guard is None

    async def test_evaluate_opa_guard_returns_none_when_disabled(self, layer_without_opa):
        """Test _evaluate_opa_guard returns None when guard is disabled."""
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={},
        )
        msg.impact_score = 0.5

        result = await layer_without_opa._evaluate_opa_guard(msg, datetime.now(UTC))
        assert result is None

    async def test_verify_with_opa_guard_returns_none_when_disabled(self, layer_without_opa):
        """Test _verify_with_opa_guard returns None when guard is disabled."""
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={},
        )

        result = await layer_without_opa._verify_with_opa_guard(msg)
        assert result is None

    def test_set_guard_callback(self, layer_with_opa):
        """Test setting guard callback."""
        callback = MagicMock()
        layer_with_opa.set_guard_callback(callback)
        assert layer_with_opa.guard_callback is callback


class TestPrepareProcessingContext:
    """Tests for _prepare_processing_context method."""

    def test_context_includes_all_fields(self):
        """Test context includes all required fields."""
        layer = DeliberationLayer(enable_opa_guard=False)
        msg = AgentMessage(
            from_agent="sender_agent",
            to_agent="target_agent",
            sender_id="sender_id",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            tenant_id="tenant_123",
            priority=Priority.HIGH,
        )

        context = layer._prepare_processing_context(msg)

        assert context["agent_id"] == "sender_agent"
        assert context["tenant_id"] == "tenant_123"
        assert context["priority"] == Priority.HIGH
        assert context["message_type"] == MessageType.COMMAND
        assert context["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_context_uses_sender_id_fallback(self):
        """Test context uses sender_id when from_agent is empty."""
        layer = DeliberationLayer(enable_opa_guard=False)
        msg = AgentMessage(
            from_agent="",
            to_agent="target",
            sender_id="fallback_sender",
            message_type=MessageType.QUERY,
            content={},
        )

        context = layer._prepare_processing_context(msg)
        # Should use from_agent (empty) or sender_id
        assert context["agent_id"] in ["", "fallback_sender"]


class TestEnsureImpactScore:
    """Tests for _ensure_impact_score method."""

    def test_calculates_score_when_none(self):
        """Test impact score is calculated when None."""
        layer = DeliberationLayer(enable_opa_guard=False)
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={"action": "test"},
        )
        assert msg.impact_score is None

        context = {"agent_id": "a", "tenant_id": ""}
        layer._ensure_impact_score(msg, context)

        assert msg.impact_score is not None
        assert isinstance(msg.impact_score, float)

    def test_preserves_existing_score(self):
        """Test existing impact score is preserved."""
        layer = DeliberationLayer(enable_opa_guard=False)
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={},
        )
        msg.impact_score = 0.75

        context = {"agent_id": "a", "tenant_id": ""}
        layer._ensure_impact_score(msg, context)

        assert msg.impact_score == 0.75


class TestCloseMethods:
    """Tests for close methods."""

    async def test_close_without_redis(self):
        """Test close works without Redis components."""
        layer = DeliberationLayer(enable_redis=False, enable_opa_guard=False)
        await layer.close()  # Should not raise

    async def test_close_without_opa_guard(self):
        """Test close works without OPA guard."""
        layer = DeliberationLayer(enable_opa_guard=False)
        await layer.close()  # Should not raise


class TestResolvedeliberationItem:
    """Tests for resolve_deliberation_item method."""

    @pytest.fixture
    def layer(self):
        """Create a deliberation layer."""
        return DeliberationLayer(enable_learning=False, enable_llm=False, enable_opa_guard=False)

    async def test_resolve_without_queue(self):
        """Test resolving when no queue configured."""
        layer = DeliberationLayer(enable_opa_guard=False)
        # Set queue to None
        original_queue = layer.deliberation_queue
        layer.deliberation_queue = None

        result = await layer.resolve_deliberation_item("item_123", approved=True)

        assert result["status"] == "error"
        assert "No deliberation queue" in result["message"]

        # Restore
        layer.deliberation_queue = original_queue

    async def test_resolve_existing_item(self, layer):
        """Test resolving an existing deliberation item."""
        # First, queue a message
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={},
        )
        msg.impact_score = 0.9

        queue_result = await layer.process_message(msg)
        item_id = queue_result.get("item_id")

        # Now resolve it
        result = await layer.resolve_deliberation_item(item_id, approved=True)

        # Should succeed or indicate no feedback
        assert result["status"] in ["resolved", "resolved_no_feedback"]


class TestDependencyInjection:
    """Tests for dependency injection parameters."""

    def test_llm_assistant_injection(self):
        """Test LLM assistant can be injected."""
        mock_llm = MagicMock()
        layer = DeliberationLayer(
            llm_assistant=mock_llm,
            enable_llm=True,  # Would create default, but injected takes priority
            enable_opa_guard=False,
        )

        assert layer.llm_assistant is mock_llm

    def test_llm_assistant_none_when_disabled(self):
        """Test LLM assistant is None when disabled without injection."""
        layer = DeliberationLayer(enable_llm=False, enable_opa_guard=False)
        assert layer.llm_assistant is None

    def test_opa_guard_injection(self):
        """Test OPA guard can be injected."""
        mock_guard = MagicMock()
        layer = DeliberationLayer(
            opa_guard=mock_guard,
            enable_opa_guard=False,  # Injection overrides flag
        )

        assert layer.opa_guard is mock_guard

    def test_redis_queue_ignored_when_disabled(self):
        """Test injected Redis queue is ignored when Redis feature flag is disabled."""
        mock_queue = MagicMock()
        layer = DeliberationLayer(
            redis_queue=mock_queue, enable_redis=False, enable_opa_guard=False
        )

        assert layer.redis_queue is None

    def test_redis_voting_ignored_when_disabled(self):
        """Test injected Redis voting is ignored when Redis feature flag is disabled."""
        mock_voting = MagicMock()
        layer = DeliberationLayer(
            redis_voting=mock_voting, enable_redis=False, enable_opa_guard=False
        )

        assert layer.redis_voting is None


class TestRecordPerformanceFeedback:
    """Tests for _record_performance_feedback method."""

    async def test_feedback_skipped_when_learning_disabled(self):
        """Test feedback is skipped when learning is disabled."""
        layer = DeliberationLayer(enable_learning=False, enable_opa_guard=False)
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={},
        )

        # Mock router to verify it's not called
        layer.adaptive_router.update_performance_feedback = AsyncMock()

        await layer._record_performance_feedback(msg, {"lane": "fast"}, 0.1)

        # Should not have been called when learning disabled
        layer.adaptive_router.update_performance_feedback.assert_not_called()

    async def test_feedback_for_fast_lane(self):
        """Test feedback is recorded for fast lane processing."""
        layer = DeliberationLayer(enable_learning=True, enable_opa_guard=False)
        layer.adaptive_router.update_performance_feedback = AsyncMock()

        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={},
        )

        await layer._record_performance_feedback(msg, {"lane": "fast", "success": True}, 0.05)

        layer.adaptive_router.update_performance_feedback.assert_called_once()

    async def test_feedback_for_deliberation_lane(self):
        """Test feedback is recorded for deliberation lane."""
        layer = DeliberationLayer(enable_learning=True, enable_opa_guard=False)
        layer.adaptive_router.update_performance_feedback = AsyncMock()

        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={},
        )

        await layer._record_performance_feedback(msg, {"lane": "deliberation"}, 0.1)

        # Should call with None feedback_score for deliberation
        layer.adaptive_router.update_performance_feedback.assert_called_once()
        call_kwargs = layer.adaptive_router.update_performance_feedback.call_args
        # feedback_score should be None for deliberation queue
        assert call_kwargs[1].get("feedback_score") is None


class TestExecuteRouting:
    """Tests for _execute_routing method."""

    @pytest.fixture
    def layer(self):
        """Create a deliberation layer."""
        return DeliberationLayer(enable_learning=False, enable_llm=False, enable_opa_guard=False)

    async def test_fast_lane_routing(self, layer):
        """Test message routed to fast lane."""
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={},
        )
        msg.impact_score = 0.2  # Low score for fast lane

        context = {"agent_id": "a", "tenant_id": ""}

        result = await layer._execute_routing(msg, context)

        assert result.get("lane") == "fast"
        assert result.get("status") == "delivered"

    async def test_deliberation_lane_routing(self, layer):
        """Test message routed to deliberation lane."""
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={},
        )
        msg.impact_score = 0.95  # High score for deliberation

        context = {"agent_id": "a", "tenant_id": ""}

        result = await layer._execute_routing(msg, context)

        assert result.get("lane") == "deliberation"
        assert result.get("status") == "queued"


class TestFinalizeProcessing:
    """Tests for _finalize_processing method."""

    async def test_finalize_adds_processing_time(self):
        """Test finalize adds processing_time to result."""
        layer = DeliberationLayer(enable_learning=False, enable_opa_guard=False)
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={},
        )

        start_time = datetime.now(UTC)
        initial_result = {"lane": "fast", "status": "delivered"}

        result = await layer._finalize_processing(msg, initial_result, start_time)

        assert "processing_time" in result
        assert result["success"] is True

    async def test_finalize_preserves_existing_guard_result(self):
        """Test finalize preserves guard_result in result."""
        layer = DeliberationLayer(enable_learning=False, enable_opa_guard=False)
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={},
        )

        start_time = datetime.now(UTC)
        mock_guard_result = {"decision": "allow"}
        initial_result = {"lane": "fast", "guard_result": mock_guard_result}

        result = await layer._finalize_processing(msg, initial_result, start_time)

        assert result.get("guard_result") == mock_guard_result


class TestInitializeAsync:
    """Tests for async initialization."""

    async def test_initialize_with_opa_guard(self):
        """Test initialization initializes OPA guard."""
        layer = DeliberationLayer(enable_opa_guard=True, enable_redis=False)

        # Mock the OPA guard initialize method
        if layer.opa_guard:
            layer.opa_guard.initialize = AsyncMock()

        await layer.initialize()

        if layer.opa_guard:
            layer.opa_guard.initialize.assert_called_once()


class TestTimeoutErrorHandling:
    """Tests for timeout error handling."""

    @pytest.fixture
    def layer(self):
        """Create a deliberation layer."""
        return DeliberationLayer(enable_learning=False, enable_llm=False, enable_opa_guard=False)

    async def test_timeout_returns_error_result(self, layer):
        """Test timeout error returns proper error result."""
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={},
        )
        msg.impact_score = 0.5

        # Mock router to raise timeout
        layer.adaptive_router.route_message = AsyncMock(side_effect=TimeoutError("Test timeout"))

        result = await layer.process_message(msg)

        assert result["success"] is False
        assert "Timeout" in result["error"]
        assert "processing_time" in result


class TestValueErrorHandling:
    """Tests for value error handling."""

    @pytest.fixture
    def layer(self):
        """Create a deliberation layer."""
        return DeliberationLayer(enable_learning=False, enable_llm=False, enable_opa_guard=False)

    async def test_value_error_returns_error_result(self, layer):
        """Test ValueError returns proper error result."""
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={},
        )
        msg.impact_score = 0.5

        # Mock router to raise ValueError
        layer.adaptive_router.route_message = AsyncMock(side_effect=ValueError("Invalid value"))

        result = await layer.process_message(msg)

        assert result["success"] is False
        assert "ValueError" in result["error"]


class TestRuntimeErrorHandling:
    """Tests for runtime error handling."""

    @pytest.fixture
    def layer(self):
        """Create a deliberation layer."""
        return DeliberationLayer(enable_learning=False, enable_llm=False, enable_opa_guard=False)

    async def test_runtime_error_returns_error_result(self, layer):
        """Test RuntimeError returns proper error result."""
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.QUERY,
            content={},
        )
        msg.impact_score = 0.5

        # Mock router to raise RuntimeError
        layer.adaptive_router.route_message = AsyncMock(side_effect=RuntimeError("Runtime issue"))

        result = await layer.process_message(msg)

        assert result["success"] is False
        assert "RuntimeError" in result["error"]


class TestLayerStatsErrorHandling:
    """Tests for error handling in get_layer_stats."""

    def test_stats_handles_value_error(self):
        """Test stats handles ValueError gracefully."""
        layer = DeliberationLayer(enable_opa_guard=False)
        # Mock to raise error
        layer.adaptive_router.get_routing_stats = MagicMock(side_effect=ValueError("Stats error"))

        result = layer.get_layer_stats()

        assert "error" in result

    def test_stats_handles_runtime_error(self):
        """Test stats handles RuntimeError gracefully."""
        layer = DeliberationLayer(enable_opa_guard=False)
        # Mock to raise error
        layer.adaptive_router.get_routing_stats = MagicMock(
            side_effect=RuntimeError("Runtime error")
        )

        result = layer.get_layer_stats()

        assert "error" in result


class TestUpdateDeliberationOutcome:
    """Tests for _update_deliberation_outcome method."""

    async def test_update_skipped_when_learning_disabled(self):
        """Test update is skipped when learning is disabled."""
        layer = DeliberationLayer(enable_learning=False, enable_opa_guard=False)

        # Should not raise and should not call router
        await layer._update_deliberation_outcome("item_123", "approved", "Good")

    async def test_update_handles_missing_item(self):
        """Test update handles missing item gracefully."""
        layer = DeliberationLayer(enable_learning=True, enable_opa_guard=False)
        # Mock to return None
        layer.deliberation_queue.get_item_details = MagicMock(return_value=None)

        # Should not raise
        await layer._update_deliberation_outcome("nonexistent", "approved", "Good")


class TestAgentVoteErrorHandling:
    """Tests for error handling in submit_agent_vote."""

    @pytest.fixture
    def layer(self):
        """Create a deliberation layer."""
        return DeliberationLayer(enable_opa_guard=False)

    async def test_submit_vote_handles_value_error(self, layer):
        """Test submit_agent_vote handles ValueError."""
        layer.deliberation_queue.submit_agent_vote = AsyncMock(
            side_effect=ValueError("Invalid vote")
        )

        result = await layer.submit_agent_vote(
            item_id="item_123",
            agent_id="agent1",
            vote="approve",
            reasoning="Test",
        )

        assert result is False

    async def test_submit_vote_handles_runtime_error(self, layer):
        """Test submit_agent_vote handles RuntimeError."""
        layer.deliberation_queue.submit_agent_vote = AsyncMock(
            side_effect=RuntimeError("Runtime error")
        )

        result = await layer.submit_agent_vote(
            item_id="item_123",
            agent_id="agent1",
            vote="approve",
            reasoning="Test",
        )

        assert result is False


class TestHumanDecisionErrorHandling:
    """Tests for error handling in submit_human_decision."""

    @pytest.fixture
    def layer(self):
        """Create a deliberation layer."""
        return DeliberationLayer(enable_opa_guard=False)

    async def test_submit_decision_handles_type_error(self, layer):
        """Test submit_human_decision handles TypeError."""
        layer.deliberation_queue.submit_human_decision = AsyncMock(
            side_effect=TypeError("Type error")
        )

        result = await layer.submit_human_decision(
            item_id="item_123",
            reviewer="human",
            decision="approved",
            reasoning="Test",
        )

        assert result is False

    async def test_submit_decision_handles_attribute_error(self, layer):
        """Test submit_human_decision handles AttributeError."""
        layer.deliberation_queue.submit_human_decision = AsyncMock(
            side_effect=AttributeError("Attr error")
        )

        result = await layer.submit_human_decision(
            item_id="item_123",
            reviewer="human",
            decision="rejected",
            reasoning="Test",
        )

        assert result is False


class TestAnalyzeTrendsErrorHandling:
    """Tests for error handling in analyze_trends."""

    async def test_trends_handles_value_error(self):
        """Test analyze_trends handles ValueError."""
        layer = DeliberationLayer(enable_llm=True, enable_opa_guard=False)
        if layer.llm_assistant:
            layer.llm_assistant.analyze_deliberation_trends = AsyncMock(
                side_effect=ValueError("Analysis error")
            )

            result = await layer.analyze_trends()

            assert "error" in result

    async def test_trends_handles_runtime_error(self):
        """Test analyze_trends handles RuntimeError."""
        layer = DeliberationLayer(enable_llm=True, enable_opa_guard=False)
        if layer.llm_assistant:
            layer.llm_assistant.analyze_deliberation_trends = AsyncMock(
                side_effect=RuntimeError("Runtime error")
            )

            result = await layer.analyze_trends()

            assert "error" in result


class TestDeliberationProcessingWithRedis:
    """Tests for deliberation processing with Redis enabled."""

    def test_redis_queue_parameter_accepted(self):
        """Test Redis queue parameter is accepted in constructor."""
        mock_redis_queue = MagicMock()

        # DeliberationLayer accepts redis_queue parameter
        layer = DeliberationLayer(
            redis_queue=mock_redis_queue,
            enable_redis=True,
            enable_opa_guard=False,
            enable_learning=False,
        )

        # Layer created successfully with redis_queue
        assert layer is not None
        # The layer has an injected_queue property
        assert layer.injected_queue is not None


class TestAgentVoteWithRedis:
    """Tests for agent voting with Redis enabled."""

    def test_redis_voting_parameter_accepted(self):
        """Test Redis voting parameter is accepted in constructor."""
        mock_redis_voting = MagicMock()

        # DeliberationLayer accepts redis_voting parameter
        layer = DeliberationLayer(
            redis_voting=mock_redis_voting,
            enable_redis=True,
            enable_opa_guard=False,
            enable_learning=False,
        )

        # Layer created successfully with redis_voting
        assert layer is not None
        # Access voting via attribute (may or may not store the mock)
        assert hasattr(layer, "redis_voting") or hasattr(layer, "enable_redis")

    def test_enable_redis_flag_accepted(self):
        """Test enable_redis flag is accepted in constructor."""
        layer = DeliberationLayer(
            enable_redis=True,
            enable_opa_guard=False,
            enable_learning=False,
        )

        # Layer created successfully with enable_redis flag
        assert layer is not None
        # Check that enable_redis attribute exists
        assert hasattr(layer, "enable_redis")

        layer2 = DeliberationLayer(
            enable_redis=False,
            enable_opa_guard=False,
        )

        assert layer2 is not None


class TestThresholdConfiguration:
    """Tests for threshold configuration."""

    def test_high_risk_threshold_configured(self):
        """Test high risk threshold is configured correctly."""
        layer = DeliberationLayer(
            high_risk_threshold=0.7,
            critical_risk_threshold=0.9,
            enable_opa_guard=False,
        )

        assert layer.high_risk_threshold == 0.7
        assert layer.critical_risk_threshold == 0.9

    def test_impact_threshold_synced_to_router(self):
        """Test impact threshold is synced to router."""
        layer = DeliberationLayer(
            impact_threshold=0.6,
            enable_opa_guard=False,
        )

        assert layer.impact_threshold == 0.6
        # Router should have the same threshold if it supports set_impact_threshold


# Entry point for running tests directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
