"""Tests for chaos/experiments.py."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.chaos.experiments import (
    CONSTITUTIONAL_HASH,
    ChaosExperiment,
    ExperimentPhase,
    ExperimentResult,
    ExperimentStatus,
    chaos_experiment,
    get_experiment_registry,
    register_experiment,
    reset_experiment_registry,
)
from enhanced_agent_bus.chaos.scenarios import BaseScenario, ScenarioResult, ScenarioStatus
from enhanced_agent_bus.chaos.steady_state import SteadyStateValidator, ValidationResult
from enhanced_agent_bus.exceptions import ConstitutionalHashMismatchError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeScenario(BaseScenario):
    """Minimal concrete scenario for testing."""

    def __init__(self, name: str = "fake", duration_s: float = 0.1, **kwargs):
        super().__init__(name=name, duration_s=duration_s, **kwargs)

    async def execute(self) -> ScenarioResult:
        await asyncio.sleep(0.01)
        return ScenarioResult(
            scenario_name=self.name,
            status=ScenarioStatus.COMPLETED,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_s=self.duration_s,
        )

    async def rollback(self) -> None:
        pass


def _make_validator(name: str = "test_validator") -> SteadyStateValidator:
    return SteadyStateValidator(name=name, metrics={})


# ---------------------------------------------------------------------------
# ExperimentResult tests
# ---------------------------------------------------------------------------


class TestExperimentResult:
    def test_to_dict(self):
        now = datetime.now(UTC)
        r = ExperimentResult(
            experiment_name="test",
            hypothesis="things work",
            status=ExperimentStatus.PASSED,
            phase=ExperimentPhase.COMPLETED,
            started_at=now,
            ended_at=now,
            duration_s=1.5,
        )
        d = r.to_dict()
        assert d["experiment_name"] == "test"
        assert d["status"] == "passed"
        assert d["phase"] == "completed"
        assert d["duration_s"] == 1.5

    def test_defaults(self):
        r = ExperimentResult(
            experiment_name="x",
            hypothesis="h",
            status=ExperimentStatus.PENDING,
            phase=ExperimentPhase.INITIALIZED,
            started_at=datetime.now(UTC),
        )
        assert r.baseline_valid is True
        assert r.during_chaos_valid is True
        assert r.recovery_valid is True
        assert r.observations == []
        assert r.errors == []


# ---------------------------------------------------------------------------
# ChaosExperiment tests
# ---------------------------------------------------------------------------


class TestChaosExperiment:
    def test_init(self):
        scenario = FakeScenario()
        validator = _make_validator()
        exp = ChaosExperiment(
            name="test_exp",
            hypothesis="system is resilient",
            steady_state=validator,
            scenario=scenario,
        )
        assert exp.name == "test_exp"
        assert exp.phase == ExperimentPhase.INITIALIZED
        assert exp.status == ExperimentStatus.PENDING
        assert exp.result is None

    def test_init_bad_constitutional_hash(self):
        scenario = FakeScenario()
        validator = _make_validator()
        with pytest.raises(ConstitutionalHashMismatchError):
            ChaosExperiment(
                name="bad",
                hypothesis="h",
                steady_state=validator,
                scenario=scenario,
                constitutional_hash="wrong_hash",
            )

    def test_abort(self):
        scenario = FakeScenario()
        validator = _make_validator()
        exp = ChaosExperiment(
            name="abort_test",
            hypothesis="h",
            steady_state=validator,
            scenario=scenario,
        )
        exp.abort()
        assert exp.status == ExperimentStatus.ABORTED
        assert exp.phase == ExperimentPhase.ABORTED

    def test_to_dict(self):
        scenario = FakeScenario()
        validator = _make_validator()
        exp = ChaosExperiment(
            name="dict_test",
            hypothesis="h",
            steady_state=validator,
            scenario=scenario,
        )
        d = exp.to_dict()
        assert d["name"] == "dict_test"
        assert d["phase"] == "initialized"
        assert d["status"] == "pending"

    @pytest.mark.asyncio
    async def test_run_passes(self):
        scenario = FakeScenario(duration_s=0.05)
        validator = _make_validator()
        exp = ChaosExperiment(
            name="pass_test",
            hypothesis="h",
            steady_state=validator,
            scenario=scenario,
            baseline_check_duration_s=0.05,
            recovery_check_duration_s=0.05,
            validation_interval_s=0.05,
        )
        result = await exp.run()
        assert result.status == ExperimentStatus.PASSED
        assert result.phase == ExperimentPhase.COMPLETED
        assert result.duration_s > 0
        assert "PASSED" in result.observations[-1]

    @pytest.mark.asyncio
    async def test_run_with_violation(self):
        """Test that violations during chaos cause FAILED status."""
        scenario = FakeScenario(duration_s=0.05)
        validator = _make_validator()

        # Mock validate to return a violation during chaos
        call_count = 0

        async def mock_validate(consecutive_failures_allowed=2):
            nonlocal call_count
            call_count += 1
            if call_count > 2:  # After baseline
                return [
                    ValidationResult(
                        valid=False,
                        metric_name="latency",
                        expected_value="<= 5.0",
                        actual_value=10.0,
                    )
                ]
            return [
                ValidationResult(
                    valid=True,
                    metric_name="latency",
                    expected_value="<= 5.0",
                    actual_value=1.0,
                )
            ]

        validator.validate = mock_validate

        exp = ChaosExperiment(
            name="violation_test",
            hypothesis="h",
            steady_state=validator,
            scenario=scenario,
            baseline_check_duration_s=0.05,
            recovery_check_duration_s=0.05,
            validation_interval_s=0.05,
        )
        result = await exp.run()
        assert result.status == ExperimentStatus.FAILED

    @pytest.mark.asyncio
    async def test_run_error_handling(self):
        """Test that exceptions during run produce ERROR status."""
        scenario = FakeScenario(duration_s=0.05)
        validator = _make_validator()

        # Make baseline validation raise
        async def broken_validate(consecutive_failures_allowed=2):
            raise RuntimeError("validator exploded")

        validator.validate = broken_validate

        exp = ChaosExperiment(
            name="error_test",
            hypothesis="h",
            steady_state=validator,
            scenario=scenario,
            baseline_check_duration_s=0.05,
            recovery_check_duration_s=0.05,
        )
        result = await exp.run()
        assert result.status == ExperimentStatus.ERROR
        assert result.phase == ExperimentPhase.FAILED
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_run_abort_on_violation(self):
        """Test abort_on_violation during chaos."""
        scenario = FakeScenario(duration_s=0.2)
        validator = _make_validator()

        call_count = 0

        async def mock_validate(consecutive_failures_allowed=2):
            nonlocal call_count
            call_count += 1
            if call_count > 2:
                return [
                    ValidationResult(
                        valid=False,
                        metric_name="m",
                        expected_value="<= 1",
                        actual_value=99.0,
                    )
                ]
            return [
                ValidationResult(
                    valid=True, metric_name="m", expected_value="<= 1", actual_value=0.5
                )
            ]

        validator.validate = mock_validate

        exp = ChaosExperiment(
            name="abort_test",
            hypothesis="h",
            steady_state=validator,
            scenario=scenario,
            baseline_check_duration_s=0.05,
            recovery_check_duration_s=0.05,
            validation_interval_s=0.05,
            abort_on_violation=True,
        )
        result = await exp.run()
        assert result.status == ExperimentStatus.ABORTED

    @pytest.mark.asyncio
    async def test_get_result_after_run(self):
        scenario = FakeScenario(duration_s=0.05)
        validator = _make_validator()
        exp = ChaosExperiment(
            name="result_test",
            hypothesis="h",
            steady_state=validator,
            scenario=scenario,
            baseline_check_duration_s=0.05,
            recovery_check_duration_s=0.05,
        )
        assert exp.get_result() is None
        await exp.run()
        assert exp.get_result() is not None


# ---------------------------------------------------------------------------
# Experiment registry tests
# ---------------------------------------------------------------------------


class TestExperimentRegistry:
    def test_register_and_get(self):
        reset_experiment_registry()
        scenario = FakeScenario()
        validator = _make_validator()
        exp = ChaosExperiment(
            name="reg_test",
            hypothesis="h",
            steady_state=validator,
            scenario=scenario,
        )
        register_experiment(exp)
        registry = get_experiment_registry()
        assert "reg_test" in registry
        assert "reg_test" in registry

    def test_reset_registry(self):
        reset_experiment_registry()
        scenario = FakeScenario()
        validator = _make_validator()
        exp = ChaosExperiment(
            name="reset_test",
            hypothesis="h",
            steady_state=validator,
            scenario=scenario,
        )
        register_experiment(exp)
        reset_experiment_registry()
        assert len(get_experiment_registry()) == 0


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_experiment_phase_values(self):
        assert ExperimentPhase.INITIALIZED.value == "initialized"
        assert ExperimentPhase.COMPLETED.value == "completed"
        assert ExperimentPhase.ABORTED.value == "aborted"

    def test_experiment_status_values(self):
        assert ExperimentStatus.PENDING.value == "pending"
        assert ExperimentStatus.PASSED.value == "passed"
        assert ExperimentStatus.FAILED.value == "failed"
        assert ExperimentStatus.ERROR.value == "error"


# ---------------------------------------------------------------------------
# chaos_experiment decorator tests
# ---------------------------------------------------------------------------


class TestChaosExperimentDecorator:
    def test_sync_function_raises(self):
        scenario = FakeScenario()
        with pytest.raises(ValueError, match="async"):

            @chaos_experiment(
                hypothesis="h",
                scenario=scenario,
            )
            def sync_func():
                pass

    def test_decorator_wraps_async(self):
        scenario = FakeScenario(duration_s=0.05)

        @chaos_experiment(
            hypothesis="system handles it",
            scenario=scenario,
        )
        async def my_test():
            return "ok"

        assert my_test.__name__ == "my_test"
