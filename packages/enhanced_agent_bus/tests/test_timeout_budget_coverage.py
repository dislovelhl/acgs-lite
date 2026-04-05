# Constitutional Hash: 608508a9bd224290
"""
Additional coverage tests for
src/core/enhanced_agent_bus/observability/timeout_budget.py

Targets the uncovered lines identified in the 94% baseline run:
  - 124->127  LayerTimeoutBudget.stop() with start_time already None
  - 186->189  TimeoutBudgetManager.stop_total() with _total_start already None
  - 195       total_elapsed_ms property when _total_start is None (returns _total_elapsed)
  - 241       execute_with_budget soft-limit warning log path
  - 305->319  execute_sync_with_budget soft-limit warning (exceeded=False, soft=True)
  - 314       execute_sync_with_budget LayerTimeoutError re-raise branch

asyncio_mode = "auto" is set in pyproject.toml -- no @pytest.mark.asyncio needed.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.observability.timeout_budget import (
    Layer,
    LayerTimeoutBudget,
    LayerTimeoutError,
    TimeoutBudgetManager,
)

# ---------------------------------------------------------------------------
# LayerTimeoutBudget - edge-case paths
# ---------------------------------------------------------------------------


class TestLayerTimeoutBudgetStopWhenNotStarted:
    """stop() called without a preceding start() should be a no-op."""

    def test_stop_without_start_returns_zero_elapsed(self):
        budget = LayerTimeoutBudget(layer=Layer.LAYER1_VALIDATION, budget_ms=10.0)
        # start_time is None -- branch on line 124 is not taken
        elapsed = budget.stop()
        assert elapsed == 0.0
        assert budget.start_time is None

    def test_stop_without_start_leaves_elapsed_unchanged(self):
        budget = LayerTimeoutBudget(layer=Layer.LAYER1_VALIDATION, budget_ms=10.0)
        budget.elapsed_ms = 7.5  # simulate a prior measurement
        elapsed = budget.stop()
        # elapsed_ms must NOT be overwritten -- stop() skips the block
        assert elapsed == 7.5
        assert budget.elapsed_ms == 7.5


# ---------------------------------------------------------------------------
# TimeoutBudgetManager - stop_total when not running
# ---------------------------------------------------------------------------


class TestTimeoutBudgetManagerStopTotalNotRunning:
    """stop_total() called before start_total() should be a no-op."""

    def test_stop_total_without_start_returns_zero(self):
        manager = TimeoutBudgetManager()
        elapsed = manager.stop_total()
        assert elapsed == 0.0
        assert manager._total_start is None

    def test_stop_total_twice_returns_saved_value(self):
        """Second stop_total() after first should return the stored _total_elapsed."""
        manager = TimeoutBudgetManager()
        manager.start_total()
        first = manager.stop_total()
        # Now _total_start is None; second call returns stored value unchanged
        second = manager.stop_total()
        assert second == first


# ---------------------------------------------------------------------------
# TimeoutBudgetManager.total_elapsed_ms - static path
# ---------------------------------------------------------------------------


class TestTotalElapsedMsStaticPath:
    """total_elapsed_ms when _total_start is None should return _total_elapsed."""

    def test_returns_stored_elapsed_when_not_running(self):
        manager = TimeoutBudgetManager()
        manager._total_elapsed = 33.3
        # _total_start is None so property takes the else branch (line 195)
        assert manager.total_elapsed_ms == 33.3

    def test_returns_zero_when_never_started(self):
        manager = TimeoutBudgetManager()
        assert manager.total_elapsed_ms == 0.0


# ---------------------------------------------------------------------------
# execute_with_budget - soft-limit warning path (line 241)
# ---------------------------------------------------------------------------


class TestExecuteWithBudgetSoftLimitWarning:
    """When an operation completes within budget but past the soft limit,
    execute_with_budget should emit a warning log."""

    async def test_soft_limit_warning_is_logged(self, caplog):
        """Operation completes within hard limit but past 80% soft limit."""
        # Give a generous hard limit but a very tight soft limit so a trivially
        # fast coroutine still crosses the soft boundary.
        budget = LayerTimeoutBudget(
            layer=Layer.LAYER1_VALIDATION,
            budget_ms=5000.0,  # hard limit: 5 s -- will never be hit
            soft_limit_pct=0.0,  # soft limit at 0% → any elapsed > 0 triggers
            strict_enforcement=True,
        )
        manager = TimeoutBudgetManager(
            layer_budgets={
                Layer.LAYER1_VALIDATION: budget,
                Layer.LAYER2_DELIBERATION: LayerTimeoutBudget(
                    layer=Layer.LAYER2_DELIBERATION, budget_ms=20.0
                ),
                Layer.LAYER3_POLICY: LayerTimeoutBudget(layer=Layer.LAYER3_POLICY, budget_ms=10.0),
                Layer.LAYER4_AUDIT: LayerTimeoutBudget(
                    layer=Layer.LAYER4_AUDIT,
                    budget_ms=15.0,
                    strict_enforcement=False,
                ),
            }
        )

        async def quick():
            await asyncio.sleep(0)
            return "ok"

        with caplog.at_level(logging.WARNING):
            result = await manager.execute_with_budget(
                Layer.LAYER1_VALIDATION, quick, operation_name="soft_test"
            )

        assert result == "ok"
        # The warning log (line 241-243) should have fired
        assert any("approaching" in record.message for record in caplog.records), (
            f"Expected soft-limit warning; got: {[r.message for r in caplog.records]}"
        )

    async def test_soft_limit_warning_contains_layer_name(self, caplog):
        """Warning message includes the layer name."""
        budget = LayerTimeoutBudget(
            layer=Layer.LAYER2_DELIBERATION,
            budget_ms=5000.0,
            soft_limit_pct=0.0,
        )
        manager = TimeoutBudgetManager(
            layer_budgets={
                Layer.LAYER1_VALIDATION: LayerTimeoutBudget(
                    layer=Layer.LAYER1_VALIDATION, budget_ms=5.0
                ),
                Layer.LAYER2_DELIBERATION: budget,
                Layer.LAYER3_POLICY: LayerTimeoutBudget(layer=Layer.LAYER3_POLICY, budget_ms=10.0),
                Layer.LAYER4_AUDIT: LayerTimeoutBudget(
                    layer=Layer.LAYER4_AUDIT,
                    budget_ms=15.0,
                    strict_enforcement=False,
                ),
            }
        )

        async def noop():
            return "done"

        with caplog.at_level(logging.WARNING):
            await manager.execute_with_budget(Layer.LAYER2_DELIBERATION, noop)

        warning_messages = [r.message for r in caplog.records if "approaching" in r.message]
        assert warning_messages, "No soft-limit warning emitted"
        assert "layer2_deliberation" in warning_messages[0]


# ---------------------------------------------------------------------------
# execute_sync_with_budget - soft-limit warning path (lines 313-317)
# ---------------------------------------------------------------------------


class TestExecuteSyncWithBudgetSoftLimitWarning:
    """Sync operations that finish under the hard limit but past the soft limit
    should emit a warning rather than raise."""

    def _make_manager_soft_trigger(self, layer: Layer) -> TimeoutBudgetManager:
        """Return a manager where the given layer has a zero-pct soft limit."""
        budgets = {
            Layer.LAYER1_VALIDATION: LayerTimeoutBudget(
                layer=Layer.LAYER1_VALIDATION, budget_ms=5.0
            ),
            Layer.LAYER2_DELIBERATION: LayerTimeoutBudget(
                layer=Layer.LAYER2_DELIBERATION, budget_ms=20.0
            ),
            Layer.LAYER3_POLICY: LayerTimeoutBudget(layer=Layer.LAYER3_POLICY, budget_ms=10.0),
            Layer.LAYER4_AUDIT: LayerTimeoutBudget(
                layer=Layer.LAYER4_AUDIT,
                budget_ms=15.0,
                strict_enforcement=False,
            ),
        }
        budgets[layer] = LayerTimeoutBudget(
            layer=layer,
            budget_ms=5000.0,  # hard limit never hit
            soft_limit_pct=0.0,  # soft limit = 0% ⟹ any elapsed triggers
        )
        return TimeoutBudgetManager(layer_budgets=budgets)

    def test_soft_limit_warning_emitted(self, caplog):
        manager = self._make_manager_soft_trigger(Layer.LAYER1_VALIDATION)

        def fast_sync():
            return "result"

        with caplog.at_level(logging.WARNING):
            result = manager.execute_sync_with_budget(
                Layer.LAYER1_VALIDATION, fast_sync, operation_name="soft_sync_op"
            )

        assert result == "result"
        assert any("approaching" in r.message for r in caplog.records), (
            f"Expected soft-limit warning; got: {[r.message for r in caplog.records]}"
        )

    def test_soft_limit_warning_contains_layer_and_budget(self, caplog):
        manager = self._make_manager_soft_trigger(Layer.LAYER3_POLICY)

        def fast_sync():
            return 42

        with caplog.at_level(logging.WARNING):
            manager.execute_sync_with_budget(Layer.LAYER3_POLICY, fast_sync)

        warning_messages = [r.message for r in caplog.records if "approaching" in r.message]
        assert warning_messages, "No soft-limit warning emitted"
        assert "layer3_policy" in warning_messages[0]


# ---------------------------------------------------------------------------
# execute_sync_with_budget - LayerTimeoutError re-raise (line 321-322)
# ---------------------------------------------------------------------------


class TestExecuteSyncLayerTimeoutErrorReRaise:
    """When the inner operation raises LayerTimeoutError directly (not via
    strict_enforcement logic), the bare 'except LayerTimeoutError: raise'
    branch must propagate it unchanged."""

    def test_layer_timeout_error_is_reraised_unchanged(self):
        manager = TimeoutBudgetManager()

        original_error = LayerTimeoutError(
            layer_name="layer3_policy",
            budget_ms=10.0,
            elapsed_ms=12.0,
            operation="manual_raise",
        )

        def raises_layer_timeout():
            raise original_error

        with pytest.raises(LayerTimeoutError) as exc_info:
            manager.execute_sync_with_budget(Layer.LAYER3_POLICY, raises_layer_timeout)

        # Must be the exact same instance -- not wrapped or re-constructed
        assert exc_info.value is original_error

    def test_layer_timeout_error_identity_preserved(self):
        """Verify the re-raise preserves error attributes."""
        manager = TimeoutBudgetManager()

        err = LayerTimeoutError("layer4_audit", 15.0, 20.0, "audit_write")

        def inner():
            raise err

        with pytest.raises(LayerTimeoutError) as exc_info:
            manager.execute_sync_with_budget(Layer.LAYER4_AUDIT, inner)

        assert exc_info.value.layer_name == "layer4_audit"
        assert exc_info.value.budget_ms == 15.0
        assert exc_info.value.elapsed_ms == 20.0
        assert exc_info.value.operation == "audit_write"


# ---------------------------------------------------------------------------
# Additional edge-case completeness tests
# ---------------------------------------------------------------------------


class TestLayerTimeoutErrorWithoutOperation:
    """LayerTimeoutError message when operation is None."""

    def test_message_without_operation(self):
        error = LayerTimeoutError(
            layer_name="layer2_deliberation",
            budget_ms=20.0,
            elapsed_ms=25.0,
        )
        msg = str(error)
        assert "during" not in msg
        assert "layer2_deliberation" in msg

    def test_to_dict_operation_none(self):
        error = LayerTimeoutError("layer1_validation", 5.0, 6.0)
        data = error.to_dict()
        assert data["operation"] is None


class TestTimeoutBudgetManagerCustomLayerBudgets:
    """Manager initialized with custom layer_budgets skips __post_init__ default fill."""

    def test_custom_budgets_are_preserved(self):
        custom = {
            Layer.LAYER1_VALIDATION: LayerTimeoutBudget(
                layer=Layer.LAYER1_VALIDATION, budget_ms=999.0
            ),
            Layer.LAYER2_DELIBERATION: LayerTimeoutBudget(
                layer=Layer.LAYER2_DELIBERATION, budget_ms=888.0
            ),
            Layer.LAYER3_POLICY: LayerTimeoutBudget(layer=Layer.LAYER3_POLICY, budget_ms=777.0),
            Layer.LAYER4_AUDIT: LayerTimeoutBudget(
                layer=Layer.LAYER4_AUDIT, budget_ms=666.0, strict_enforcement=False
            ),
        }
        manager = TimeoutBudgetManager(layer_budgets=custom)
        assert manager.layer_budgets[Layer.LAYER1_VALIDATION].budget_ms == 999.0
        assert manager.layer_budgets[Layer.LAYER2_DELIBERATION].budget_ms == 888.0


class TestTotalRemainingMs:
    """total_remaining_ms clamps to zero when elapsed exceeds budget."""

    def test_clamps_to_zero_when_overrun(self):
        manager = TimeoutBudgetManager(total_budget_ms=10.0)
        manager._total_elapsed = 20.0  # pretend we overran
        assert manager.total_remaining_ms == 0.0

    def test_positive_when_within_budget(self):
        manager = TimeoutBudgetManager(total_budget_ms=50.0)
        manager._total_elapsed = 10.0
        assert manager.total_remaining_ms == 40.0


class TestBudgetReportWhileRunning:
    """get_budget_report includes live elapsed time while total is running."""

    def test_report_reflects_running_total(self):
        import time

        manager = TimeoutBudgetManager()
        manager.start_total()
        # tiny sleep to ensure non-zero elapsed
        time.sleep(0.001)
        report = manager.get_budget_report()
        # _total_start is set → total_elapsed_ms is computed live (line 194-195)
        assert report["total_elapsed_ms"] > 0.0
        manager.stop_total()


class TestExecuteWithBudgetNoOperationName:
    """execute_with_budget with no operation_name on timeout."""

    async def test_timeout_error_has_none_operation(self):
        manager = TimeoutBudgetManager()

        async def slow():
            await asyncio.sleep(1.0)

        with pytest.raises(LayerTimeoutError) as exc_info:
            await manager.execute_with_budget(Layer.LAYER1_VALIDATION, slow)

        assert exc_info.value.operation is None


class TestExecuteSyncNonStrictExceeded:
    """execute_sync_with_budget with non-strict enforcement does not raise on exceed."""

    def test_non_strict_layer_returns_result_even_when_exceeded(self):
        import time

        manager = TimeoutBudgetManager()
        # Layer 4 (audit) has strict_enforcement=False
        audit_budget = manager.layer_budgets[Layer.LAYER4_AUDIT]
        # Set budget to tiny value so even a no-sleep call exceeds it
        audit_budget.budget_ms = 0.0

        def slow_audit():
            time.sleep(0.005)
            return "audit_done"

        result = manager.execute_sync_with_budget(Layer.LAYER4_AUDIT, slow_audit)
        assert result == "audit_done"


class TestGetBudgetReportSoftLimitFlag:
    """Budget report correctly reflects is_soft_limit_exceeded."""

    def test_is_soft_limit_exceeded_true_in_report(self):
        manager = TimeoutBudgetManager()
        budget = manager.layer_budgets[Layer.LAYER1_VALIDATION]
        budget.elapsed_ms = budget.budget_ms * 0.9  # 90% → past 80% soft limit
        report = manager.get_budget_report()
        assert report["layers"]["layer1_validation"]["is_soft_limit_exceeded"] is True

    def test_is_soft_limit_exceeded_false_in_report(self):
        manager = TimeoutBudgetManager()
        budget = manager.layer_budgets[Layer.LAYER1_VALIDATION]
        budget.elapsed_ms = budget.budget_ms * 0.5  # 50% → under soft limit
        report = manager.get_budget_report()
        assert report["layers"]["layer1_validation"]["is_soft_limit_exceeded"] is False
