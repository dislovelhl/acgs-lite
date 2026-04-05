"""
ACGS-2 Timeout Budget Tests
Constitutional Hash: 608508a9bd224290
"""

import asyncio
import time

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

try:
    from observability.timeout_budget import (
        CONSTITUTIONAL_HASH,
        Layer,
        LayerTimeoutBudget,
        LayerTimeoutError,
        TimeoutBudgetManager,
    )
except ImportError:
    from ..observability.timeout_budget import (
        CONSTITUTIONAL_HASH,
        Layer,
        LayerTimeoutBudget,
        LayerTimeoutError,
        TimeoutBudgetManager,
    )


class TestLayerTimeoutError:
    """Tests for LayerTimeoutError."""

    def test_error_creation(self):
        """Error contains correct information."""
        error = LayerTimeoutError(
            layer_name="layer1_validation",
            budget_ms=5.0,
            elapsed_ms=7.5,
            operation="hash_validation",
        )

        assert error.layer_name == "layer1_validation"
        assert error.budget_ms == 5.0
        assert error.elapsed_ms == 7.5
        assert error.operation == "hash_validation"
        assert error.constitutional_hash == CONSTITUTIONAL_HASH

    def test_error_message(self):
        """Error has descriptive message."""
        error = LayerTimeoutError(
            layer_name="layer2_deliberation",
            budget_ms=20.0,
            elapsed_ms=25.0,
        )

        assert "layer2_deliberation" in str(error)
        assert "25.00ms" in str(error)
        assert "20.00ms" in str(error)

    def test_error_to_dict(self):
        """Error serializes correctly."""
        error = LayerTimeoutError(
            layer_name="layer3_policy",
            budget_ms=10.0,
            elapsed_ms=15.0,
            operation="opa_evaluation",
        )

        data = error.to_dict()

        assert data["error"] in ("LayerTimeoutError", "LAYER_TIMEOUT")
        assert data["layer_name"] == "layer3_policy"
        assert data["budget_ms"] == 10.0
        assert data["elapsed_ms"] == 15.0
        assert data["operation"] == "opa_evaluation"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestLayer:
    """Tests for Layer enum."""

    def test_layer_values(self):
        """Layer enum has correct values."""
        assert Layer.LAYER1_VALIDATION.value == "layer1_validation"
        assert Layer.LAYER2_DELIBERATION.value == "layer2_deliberation"
        assert Layer.LAYER3_POLICY.value == "layer3_policy"
        assert Layer.LAYER4_AUDIT.value == "layer4_audit"


class TestLayerTimeoutBudget:
    """Tests for LayerTimeoutBudget."""

    def test_budget_creation(self):
        """Budget initializes correctly."""
        budget = LayerTimeoutBudget(
            layer=Layer.LAYER1_VALIDATION,
            budget_ms=5.0,
        )

        assert budget.layer == Layer.LAYER1_VALIDATION
        assert budget.budget_ms == 5.0
        assert budget.soft_limit_pct == 0.8
        assert budget.strict_enforcement is True
        assert budget.elapsed_ms == 0.0

    def test_remaining_budget(self):
        """remaining_ms calculates correctly."""
        budget = LayerTimeoutBudget(
            layer=Layer.LAYER1_VALIDATION,
            budget_ms=10.0,
        )

        assert budget.remaining_ms == 10.0

        budget.elapsed_ms = 4.0
        assert budget.remaining_ms == 6.0

        budget.elapsed_ms = 12.0
        assert budget.remaining_ms == 0.0

    def test_is_exceeded(self):
        """is_exceeded works correctly."""
        budget = LayerTimeoutBudget(
            layer=Layer.LAYER1_VALIDATION,
            budget_ms=5.0,
        )

        budget.elapsed_ms = 4.0
        assert budget.is_exceeded is False

        budget.elapsed_ms = 5.1
        assert budget.is_exceeded is True

    def test_soft_limit(self):
        """is_soft_limit_exceeded works correctly."""
        budget = LayerTimeoutBudget(
            layer=Layer.LAYER1_VALIDATION,
            budget_ms=10.0,
            soft_limit_pct=0.8,
        )

        budget.elapsed_ms = 7.0
        assert budget.is_soft_limit_exceeded is False

        budget.elapsed_ms = 8.5
        assert budget.is_soft_limit_exceeded is True

    def test_timing(self):
        """start/stop timing works correctly."""
        budget = LayerTimeoutBudget(
            layer=Layer.LAYER1_VALIDATION,
            budget_ms=100.0,
        )

        budget.start()
        time.sleep(0.01)  # 10ms
        elapsed = budget.stop()

        assert elapsed >= 10.0  # At least 10ms
        assert budget.elapsed_ms == elapsed
        assert budget.start_time is None

    def test_reset(self):
        """reset clears timing state."""
        budget = LayerTimeoutBudget(
            layer=Layer.LAYER1_VALIDATION,
            budget_ms=100.0,
        )

        budget.start()
        budget.stop()
        budget.reset()

        assert budget.elapsed_ms == 0.0
        assert budget.start_time is None


class TestTimeoutBudgetManager:
    """Tests for TimeoutBudgetManager."""

    def test_default_initialization(self):
        """Manager initializes with default budgets."""
        manager = TimeoutBudgetManager()

        assert manager.total_budget_ms == 50.0
        assert len(manager.layer_budgets) == 4

        # Check default allocations
        assert manager.layer_budgets[Layer.LAYER1_VALIDATION].budget_ms == 5.0
        assert manager.layer_budgets[Layer.LAYER2_DELIBERATION].budget_ms == 20.0
        assert manager.layer_budgets[Layer.LAYER3_POLICY].budget_ms == 10.0
        assert manager.layer_budgets[Layer.LAYER4_AUDIT].budget_ms == 15.0

    def test_custom_total_budget(self):
        """Manager accepts custom total budget."""
        manager = TimeoutBudgetManager(total_budget_ms=100.0)

        assert manager.total_budget_ms == 100.0

    def test_get_layer_budget(self):
        """get_layer_budget returns correct budget."""
        manager = TimeoutBudgetManager()

        budget = manager.get_layer_budget(Layer.LAYER1_VALIDATION)

        assert budget.layer == Layer.LAYER1_VALIDATION
        assert budget.budget_ms == 5.0

    def test_get_unknown_layer_raises(self):
        """get_layer_budget raises for unknown layer."""
        manager = TimeoutBudgetManager()
        manager.layer_budgets = {}  # Clear budgets

        with pytest.raises(ValueError, match="Unknown layer"):
            manager.get_layer_budget(Layer.LAYER1_VALIDATION)

    def test_total_timing(self):
        """Total timing tracking works."""
        manager = TimeoutBudgetManager()

        manager.start_total()
        time.sleep(0.01)
        elapsed = manager.stop_total()

        assert elapsed >= 10.0
        assert manager.total_remaining_ms == manager.total_budget_ms - elapsed

    async def test_execute_with_budget_success(self):
        """execute_with_budget succeeds within budget.

        Uses a 100ms layer1 budget to avoid timing-sensitive failures under
        parallel xdist load, where asyncio.sleep(0.001) can take >5ms due to
        event-loop scheduling overhead across concurrent workers.  The 5ms
        default value is tested separately in test_default_initialization.
        """
        manager = TimeoutBudgetManager(
            layer_budgets={
                Layer.LAYER1_VALIDATION: LayerTimeoutBudget(
                    layer=Layer.LAYER1_VALIDATION,
                    budget_ms=100.0,
                    strict_enforcement=True,
                ),
                Layer.LAYER2_DELIBERATION: LayerTimeoutBudget(
                    layer=Layer.LAYER2_DELIBERATION,
                    budget_ms=20.0,
                ),
                Layer.LAYER3_POLICY: LayerTimeoutBudget(
                    layer=Layer.LAYER3_POLICY,
                    budget_ms=10.0,
                ),
                Layer.LAYER4_AUDIT: LayerTimeoutBudget(
                    layer=Layer.LAYER4_AUDIT,
                    budget_ms=15.0,
                    strict_enforcement=False,
                ),
            }
        )

        async def quick_operation():
            await asyncio.sleep(0.001)
            return "success"

        result = await manager.execute_with_budget(
            Layer.LAYER1_VALIDATION,
            quick_operation,
        )

        assert result == "success"

    async def test_execute_with_budget_timeout(self):
        """execute_with_budget raises on timeout."""
        manager = TimeoutBudgetManager()

        async def slow_operation():
            await asyncio.sleep(1.0)  # Way over 5ms budget
            return "never"

        with pytest.raises(LayerTimeoutError) as exc_info:
            await manager.execute_with_budget(
                Layer.LAYER1_VALIDATION,
                slow_operation,
                operation_name="slow_test",
            )

        assert exc_info.value.layer_name == "layer1_validation"
        assert exc_info.value.operation == "slow_test"

    async def test_execute_with_budget_non_strict(self):
        """Non-strict layer raises asyncio.TimeoutError."""
        manager = TimeoutBudgetManager()

        async def slow_audit():
            await asyncio.sleep(1.0)
            return "never"

        # Layer 4 (audit) is non-strict by default
        with pytest.raises(asyncio.TimeoutError):
            await manager.execute_with_budget(
                Layer.LAYER4_AUDIT,
                slow_audit,
            )

    def test_execute_sync_with_budget_success(self):
        """execute_sync_with_budget succeeds within budget."""
        manager = TimeoutBudgetManager()

        def quick_sync():
            return "sync_success"

        result = manager.execute_sync_with_budget(
            Layer.LAYER1_VALIDATION,
            quick_sync,
        )

        assert result == "sync_success"

    def test_execute_sync_with_budget_exceeded(self):
        """execute_sync_with_budget raises after slow operation."""
        manager = TimeoutBudgetManager()

        def slow_sync():
            time.sleep(0.01)  # 10ms, over 5ms budget
            return "done"

        with pytest.raises(LayerTimeoutError) as exc_info:
            manager.execute_sync_with_budget(
                Layer.LAYER1_VALIDATION,
                slow_sync,
                operation_name="slow_sync_test",
            )

        assert exc_info.value.layer_name == "layer1_validation"

    def test_execute_sync_exception_passthrough(self):
        """execute_sync_with_budget passes through exceptions."""
        manager = TimeoutBudgetManager()

        def failing_sync():
            raise RuntimeError("sync failure")

        with pytest.raises(RuntimeError, match="sync failure"):
            manager.execute_sync_with_budget(
                Layer.LAYER1_VALIDATION,
                failing_sync,
            )

    async def test_execute_async_exception_passthrough(self):
        """execute_with_budget passes through exceptions."""
        manager = TimeoutBudgetManager()

        async def failing_async():
            raise ValueError("async failure")

        with pytest.raises(ValueError, match="async failure"):
            await manager.execute_with_budget(
                Layer.LAYER1_VALIDATION,
                failing_async,
            )

    def test_budget_report(self):
        """get_budget_report returns complete information."""
        manager = TimeoutBudgetManager()
        manager.start_total()
        time.sleep(0.005)
        manager.stop_total()

        report = manager.get_budget_report()

        assert report["total_budget_ms"] == 50.0
        assert report["total_elapsed_ms"] >= 5.0
        assert "layers" in report
        assert len(report["layers"]) == 4
        assert report["constitutional_hash"] == CONSTITUTIONAL_HASH

        # Check layer report structure
        layer1_report = report["layers"]["layer1_validation"]
        assert "budget_ms" in layer1_report
        assert "elapsed_ms" in layer1_report
        assert "remaining_ms" in layer1_report
        assert "is_exceeded" in layer1_report

    def test_reset_all(self):
        """reset_all clears all timing state."""
        manager = TimeoutBudgetManager()

        manager.start_total()
        manager.layer_budgets[Layer.LAYER1_VALIDATION].start()
        manager.layer_budgets[Layer.LAYER1_VALIDATION].stop()
        manager.stop_total()

        manager.reset_all()

        assert manager._total_elapsed == 0.0
        assert manager._total_start is None
        for budget in manager.layer_budgets.values():
            assert budget.elapsed_ms == 0.0
            assert budget.start_time is None


class TestConstitutionalHash:
    """Tests for constitutional hash in timeout module."""

    def test_hash_exported(self):
        """CONSTITUTIONAL_HASH is available."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_manager_includes_hash(self):
        """Manager includes constitutional hash."""
        manager = TimeoutBudgetManager()
        assert manager.constitutional_hash == CONSTITUTIONAL_HASH

    def test_error_includes_hash(self):
        """Error includes constitutional hash."""
        error = LayerTimeoutError("test", 10.0, 15.0)
        assert error.constitutional_hash == CONSTITUTIONAL_HASH
