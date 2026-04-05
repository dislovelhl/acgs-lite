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


class TestRollbackEngineError:
    def test_is_exception(self) -> None:
        err = RollbackEngineError("boom")
        assert isinstance(err, RollbackEngineError)

    def test_message(self) -> None:
        err = RollbackEngineError("bad rollback")
        assert "bad rollback" in str(err)

    def test_http_status_code(self) -> None:
        assert RollbackEngineError.http_status_code == 500

    def test_error_code(self) -> None:
        assert RollbackEngineError.error_code == "ROLLBACK_ENGINE_ERROR"

    def test_raise_and_catch(self) -> None:
        with pytest.raises(RollbackEngineError, match="oops"):
            raise RollbackEngineError("oops")


# ---------------------------------------------------------------------------
# RollbackReason
# ---------------------------------------------------------------------------


class TestRollbackReason:
    def test_automatic_degradation_value(self) -> None:
        assert RollbackReason.AUTOMATIC_DEGRADATION == "automatic_degradation"

    def test_manual_request_value(self) -> None:
        assert RollbackReason.MANUAL_REQUEST == "manual_request"

    def test_emergency_override_value(self) -> None:
        assert RollbackReason.EMERGENCY_OVERRIDE == "emergency_override"

    def test_is_str_subclass(self) -> None:
        assert isinstance(RollbackReason.MANUAL_REQUEST, str)


# ---------------------------------------------------------------------------
# RollbackTriggerConfig
# ---------------------------------------------------------------------------


class TestRollbackTriggerConfig:
    def test_defaults(self) -> None:
        cfg = RollbackTriggerConfig()
        assert cfg.enable_automatic_rollback is True
        assert cfg.require_hitl_approval_for_critical is True
        assert cfg.auto_approve_high_confidence is True
        assert len(cfg.monitoring_windows) == 2
        assert TimeWindow.ONE_HOUR in cfg.monitoring_windows
        assert TimeWindow.SIX_HOURS in cfg.monitoring_windows

    def test_custom_values(self) -> None:
        cfg = RollbackTriggerConfig(
            enable_automatic_rollback=False,
            monitoring_interval_seconds=60,
            monitoring_windows=[TimeWindow.TWELVE_HOURS],
            require_hitl_approval_for_critical=False,
            auto_approve_high_confidence=False,
            min_confidence_for_auto_rollback=0.95,
        )
        assert cfg.enable_automatic_rollback is False
        assert cfg.monitoring_interval_seconds == 60
        assert cfg.monitoring_windows == [TimeWindow.TWELVE_HOURS]
        assert cfg.require_hitl_approval_for_critical is False
        assert cfg.auto_approve_high_confidence is False
        assert cfg.min_confidence_for_auto_rollback == 0.95

    def test_monitoring_windows_default_is_copy(self) -> None:
        """Each instance gets its own list when None is passed."""
        cfg1 = RollbackTriggerConfig()
        cfg2 = RollbackTriggerConfig()
        assert cfg1.monitoring_windows is not cfg2.monitoring_windows


# ---------------------------------------------------------------------------
# RollbackSagaActivities - constructor / init / close
# ---------------------------------------------------------------------------
