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


class TestRollbackAmendment:
    def _make_deps(self) -> tuple:
        storage = MagicMock()
        metrics_collector = MagicMock()
        degradation_detector = MagicMock()
        return storage, metrics_collector, degradation_detector

    async def test_raises_import_error_when_no_saga_context(self) -> None:
        storage, mc, dd = self._make_deps()
        with patch(
            "enhanced_agent_bus.constitutional.rollback_engine.SagaContext",
            None,
        ):
            with pytest.raises(ImportError, match="SagaContext not available"):
                await rollback_amendment(
                    current_version_id="v-123",
                    storage=storage,
                    metrics_collector=mc,
                    degradation_detector=dd,
                )

    async def test_successful_execution(self) -> None:
        storage, mc, dd = self._make_deps()

        # Mock saga result
        mock_result = MagicMock()

        # Build minimal saga classes
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
                self.execute = execute

        class MockSagaContext:
            def __init__(self, saga_id: str = "", **kwargs: Any):
                self.saga_id = saga_id

            def set_step_result(self, key: str, value: Any) -> None:
                pass

        class MockSaga:
            def __init__(self, saga_id: str):
                self.saga_id = saga_id
                self._steps: list = []

            def add_step(self, step: Any) -> None:
                self._steps.append(step)

            async def execute(self, context: Any) -> Any:
                return mock_result

        # We need the activities to have no-op initialize/close
        async def _noop_init(self: Any) -> None:
            pass

        async def _noop_close(self: Any) -> None:
            pass

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
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaContext",
                MockSagaContext,
            ),
            patch.object(RollbackSagaActivities, "initialize", new=_noop_init),
            patch.object(RollbackSagaActivities, "close", new=_noop_close),
        ):
            result = await rollback_amendment(
                current_version_id="version-abcdef12",
                storage=storage,
                metrics_collector=mc,
                degradation_detector=dd,
            )

        assert result is mock_result

    async def test_close_called_even_on_execute_failure(self) -> None:
        """Cleanup (close) must be called in the finally block even when execute raises."""
        storage, mc, dd = self._make_deps()

        close_called = []

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
                self.execute = execute

        class MockSagaContext:
            def __init__(self, saga_id: str = "", **kwargs: Any):
                self.saga_id = saga_id

            def set_step_result(self, key: str, value: Any) -> None:
                pass

        class MockSaga:
            def __init__(self, saga_id: str):
                self.saga_id = saga_id
                self._steps: list = []

            def add_step(self, step: Any) -> None:
                self._steps.append(step)

            async def execute(self, context: Any) -> Any:
                raise RuntimeError("saga failed")

        async def _noop_init(self: Any) -> None:
            pass

        async def _track_close(self: Any) -> None:
            close_called.append(True)

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
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaContext",
                MockSagaContext,
            ),
            patch.object(RollbackSagaActivities, "initialize", new=_noop_init),
            patch.object(RollbackSagaActivities, "close", new=_track_close),
        ):
            with pytest.raises(RuntimeError, match="saga failed"):
                await rollback_amendment(
                    current_version_id="version-abcdef12",
                    storage=storage,
                    metrics_collector=mc,
                    degradation_detector=dd,
                )

        assert close_called, "close() must be called in finally block"

    async def test_saga_with_no_steps_skips_initialize(self) -> None:
        """Branch: saga._steps is empty → initialize not called."""
        storage, mc, dd = self._make_deps()
        mock_result = MagicMock()

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
                self.execute = execute

        class MockSagaContext:
            def __init__(self, saga_id: str = "", **kwargs: Any):
                self.saga_id = saga_id

            def set_step_result(self, key: str, value: Any) -> None:
                pass

        class MockSagaNoSteps:
            """Saga that has _steps attribute but it's empty."""

            def __init__(self, saga_id: str):
                self.saga_id = saga_id
                self._steps: list = []  # Empty!

            def add_step(self, step: Any) -> None:
                # Don't actually add steps so _steps stays empty
                pass

            async def execute(self, context: Any) -> Any:
                return mock_result

        init_called = []

        async def tracking_init(self: Any) -> None:
            init_called.append(True)

        async def _noop_close(self: Any) -> None:
            pass

        with (
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.ConstitutionalSagaWorkflow",
                MockSagaNoSteps,
            ),
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaStep",
                MockSagaStep,
            ),
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaCompensation",
                MockSagaCompensation,
            ),
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaContext",
                MockSagaContext,
            ),
            patch.object(RollbackSagaActivities, "initialize", new=tracking_init),
            patch.object(RollbackSagaActivities, "close", new=_noop_close),
        ):
            await rollback_amendment(
                current_version_id="version-abcdef12",
                storage=storage,
                metrics_collector=mc,
                degradation_detector=dd,
            )

        # initialize should not have been called (no _steps)
        assert not init_called

    async def test_saga_step_execute_without_self_skips_initialize(self) -> None:
        """Branch: first_step.execute has no __self__ (plain function) → init skipped."""
        storage, mc, dd = self._make_deps()
        mock_result = MagicMock()

        class MockSagaCompensation:
            def __init__(self, **kwargs: Any):
                pass

        class MockSagaContext:
            def __init__(self, saga_id: str = "", **kwargs: Any):
                self.saga_id = saga_id

            def set_step_result(self, key: str, value: Any) -> None:
                pass

        # A step where execute is a plain async lambda (no __self__)
        async def _plain_execute(input: Any) -> Any:
            return {}

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
                # Deliberately use the plain function, not a bound method
                self.execute = _plain_execute

        class MockSaga:
            def __init__(self, saga_id: str):
                self.saga_id = saga_id
                self._steps: list = []

            def add_step(self, step: Any) -> None:
                self._steps.append(step)

            async def execute(self, context: Any) -> Any:
                return mock_result

        init_called = []

        async def tracking_init(self: Any) -> None:
            init_called.append(True)

        async def _noop_close(self: Any) -> None:
            pass

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
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaContext",
                MockSagaContext,
            ),
            patch.object(RollbackSagaActivities, "initialize", new=tracking_init),
            patch.object(RollbackSagaActivities, "close", new=_noop_close),
        ):
            await rollback_amendment(
                current_version_id="version-abcdef12",
                storage=storage,
                metrics_collector=mc,
                degradation_detector=dd,
            )

        # initialize should not have been called (execute has no __self__)
        assert not init_called

    async def test_saga_step_execute_non_activities_self_skips_initialize(self) -> None:
        """Branch: execute.__self__ is not a RollbackSagaActivities → init skipped."""
        storage, mc, dd = self._make_deps()
        mock_result = MagicMock()

        class MockSagaCompensation:
            def __init__(self, **kwargs: Any):
                pass

        class MockSagaContext:
            def __init__(self, saga_id: str = "", **kwargs: Any):
                self.saga_id = saga_id

            def set_step_result(self, key: str, value: Any) -> None:
                pass

        class SomeOtherClass:
            async def my_execute(self, input: Any) -> Any:
                return {}

        _other_instance = SomeOtherClass()

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
                # Bound method of a non-RollbackSagaActivities object
                self.execute = _other_instance.my_execute

        class MockSaga:
            def __init__(self, saga_id: str):
                self.saga_id = saga_id
                self._steps: list = []

            def add_step(self, step: Any) -> None:
                self._steps.append(step)

            async def execute(self, context: Any) -> Any:
                return mock_result

        init_called = []

        async def tracking_init(self: Any) -> None:
            init_called.append(True)

        async def _noop_close(self: Any) -> None:
            pass

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
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaContext",
                MockSagaContext,
            ),
            patch.object(RollbackSagaActivities, "initialize", new=tracking_init),
            patch.object(RollbackSagaActivities, "close", new=_noop_close),
        ):
            await rollback_amendment(
                current_version_id="version-abcdef12",
                storage=storage,
                metrics_collector=mc,
                degradation_detector=dd,
            )

        # initialize should not have been called
        assert not init_called

    async def test_passes_all_args_to_saga(self) -> None:
        storage, mc, dd = self._make_deps()

        created_activities: list[RollbackSagaActivities] = []
        mock_result = MagicMock()

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
                self.execute = execute

        class MockSagaContext:
            def __init__(self, saga_id: str = "", **kwargs: Any):
                self.saga_id = saga_id

            def set_step_result(self, key: str, value: Any) -> None:
                pass

        class MockSaga:
            def __init__(self, saga_id: str):
                self.saga_id = saga_id
                self._steps: list = []

            def add_step(self, step: Any) -> None:
                self._steps.append(step)

            async def execute(self, context: Any) -> Any:
                return mock_result

        original_init = RollbackSagaActivities.__init__

        def tracking_init(self: Any, *args: Any, **kwargs: Any) -> None:
            original_init(self, *args, **kwargs)
            created_activities.append(self)

        async def _noop(self: Any) -> None:
            pass

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
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaContext",
                MockSagaContext,
            ),
            patch.object(RollbackSagaActivities, "__init__", tracking_init),
            patch.object(RollbackSagaActivities, "initialize", new=_noop),
            patch.object(RollbackSagaActivities, "close", new=_noop),
        ):
            await rollback_amendment(
                current_version_id="version-abcdef12",
                storage=storage,
                metrics_collector=mc,
                degradation_detector=dd,
                opa_url="http://opa:8181",
                audit_service_url="http://audit:8001",
                redis_url="redis://myredis:6380",
                amendment_id="amend-999",
            )

        assert len(created_activities) == 1
        act = created_activities[0]
        assert act.opa_url == "http://opa:8181"
        assert act.audit_service_url == "http://audit:8001"
        assert act.redis_url == "redis://myredis:6380"


# ---------------------------------------------------------------------------
# Module-level __all__ and imports
# ---------------------------------------------------------------------------
