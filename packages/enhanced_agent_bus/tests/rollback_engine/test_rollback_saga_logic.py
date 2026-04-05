from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.constitutional.amendment_model import (
    AmendmentProposal,
    AmendmentStatus,
)
from enhanced_agent_bus.constitutional.degradation_detector import (
    DegradationReport,
    DegradationSeverity,
    MetricDegradationAnalysis,
    SignificanceLevel,
    TimeWindow,
)
from enhanced_agent_bus.constitutional.rollback_engine import (
    RollbackEngineError,
    RollbackReason,
    RollbackSagaActivities,
    RollbackTriggerConfig,
    create_rollback_saga,
    rollback_amendment,
)

from .conftest import _make_activities, _make_degradation_report, _make_saga_input


class TestCreateRollbackSaga:
    def _make_base_deps(self) -> tuple:
        storage = MagicMock()
        metrics_collector = MagicMock()
        degradation_detector = MagicMock()
        return storage, metrics_collector, degradation_detector

    def test_raises_import_error_when_no_saga_workflow(self) -> None:
        storage, metrics_collector, degradation_detector = self._make_base_deps()
        with patch(
            "enhanced_agent_bus.constitutional.rollback_engine.ConstitutionalSagaWorkflow",
            None,
        ):
            with pytest.raises(ImportError, match="ConstitutionalSagaWorkflow not available"):
                create_rollback_saga(
                    current_version_id="version-123456789",
                    storage=storage,
                    metrics_collector=metrics_collector,
                    degradation_detector=degradation_detector,
                )

    def test_returns_saga_workflow_with_steps(self) -> None:
        storage, metrics_collector, degradation_detector = self._make_base_deps()

        # Build minimal saga classes
        class MockSagaCompensation:
            def __init__(self, name, description, execute):
                self.name = name
                self.description = description
                self.execute = execute

        class MockSagaStep:
            def __init__(
                self,
                name,
                description,
                execute,
                compensation,
                timeout_seconds=30,
                is_optional=False,
            ):
                self.name = name
                self.description = description
                self.execute = execute
                self.compensation = compensation
                self.timeout_seconds = timeout_seconds
                self.is_optional = is_optional

        class MockSaga:
            def __init__(self, saga_id: str):
                self.saga_id = saga_id
                self._steps: list = []

            def add_step(self, step: Any) -> None:
                self._steps.append(step)

        with (
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.ConstitutionalSagaWorkflow",
                MockSaga,
            ),
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaStep",
                MockSagaStep,
            ),
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaCompensation",
                MockSagaCompensation,
            ),
        ):
            saga = create_rollback_saga(
                current_version_id="version-abcdef12",
                storage=storage,
                metrics_collector=metrics_collector,
                degradation_detector=degradation_detector,
            )

        assert isinstance(saga, MockSaga)
        assert len(saga._steps) == 7
        step_names = [s.name for s in saga._steps]
        assert "detect_degradation" in step_names
        assert "prepare_rollback" in step_names
        assert "notify_hitl" in step_names
        assert "update_opa_to_previous" in step_names
        assert "restore_previous_version" in step_names
        assert "invalidate_cache" in step_names
        assert "audit_rollback" in step_names

    def test_saga_id_contains_version_prefix(self) -> None:
        storage, metrics_collector, degradation_detector = self._make_base_deps()

        class MockSagaCompensation:
            def __init__(self, **kwargs: Any):
                pass

        class MockSagaStep:
            def __init__(self, **kwargs: Any):
                pass

        class MockSaga:
            def __init__(self, saga_id: str):
                self.saga_id = saga_id
                self._steps: list = []

            def add_step(self, step: Any) -> None:
                self._steps.append(step)

        with (
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.ConstitutionalSagaWorkflow",
                MockSaga,
            ),
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaStep",
                MockSagaStep,
            ),
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaCompensation",
                MockSagaCompensation,
            ),
        ):
            saga = create_rollback_saga(
                current_version_id="version-abcdef12",
                storage=storage,
                metrics_collector=metrics_collector,
                degradation_detector=degradation_detector,
            )

        assert saga.saga_id.startswith("rollback-version-")

    def test_optional_steps_marked_correctly(self) -> None:
        storage, metrics_collector, degradation_detector = self._make_base_deps()

        class MockSagaCompensation:
            def __init__(self, **kwargs: Any):
                pass

        class MockSagaStep:
            def __init__(
                self,
                name: str = "",
                description: str = "",
                execute: Any = None,
                compensation: Any = None,
                timeout_seconds: int = 30,
                is_optional: bool = False,
            ):
                self.name = name
                self.is_optional = is_optional

        class MockSaga:
            def __init__(self, saga_id: str):
                self.saga_id = saga_id
                self._steps: list = []

            def add_step(self, step: Any) -> None:
                self._steps.append(step)

        with (
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.ConstitutionalSagaWorkflow",
                MockSaga,
            ),
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaStep",
                MockSagaStep,
            ),
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaCompensation",
                MockSagaCompensation,
            ),
        ):
            saga = create_rollback_saga(
                current_version_id="version-abcdef12",
                storage=storage,
                metrics_collector=metrics_collector,
                degradation_detector=degradation_detector,
            )

        optional_steps = {s.name for s in saga._steps if s.is_optional}
        assert "notify_hitl" in optional_steps
        assert "update_opa_to_previous" in optional_steps
        assert "audit_rollback" in optional_steps

        required_steps = {s.name for s in saga._steps if not s.is_optional}
        assert "detect_degradation" in required_steps
        assert "prepare_rollback" in required_steps
        assert "restore_previous_version" in required_steps
        assert "invalidate_cache" in required_steps


# ---------------------------------------------------------------------------
# rollback_amendment - convenience function
# ---------------------------------------------------------------------------
