"""Processor-level session governance integration tests.

Detailed session-resolution behavior lives in ``test_session_coordinator.py``.
This file keeps only facade/config integration assertions for MessageProcessor.
"""

from __future__ import annotations

import pytest

from enhanced_agent_bus.config import BusConfiguration
from enhanced_agent_bus.message_processor import MessageProcessor


class TestSessionContextMetrics:
    def test_metrics_included_when_enabled(self) -> None:
        config = BusConfiguration.for_testing()
        config.enable_session_governance = True
        processor = MessageProcessor(config=config, isolated_mode=False, enable_maci=False)

        metrics = processor.get_metrics()

        assert "session_governance_enabled" in metrics
        assert metrics["session_governance_enabled"] is True
        assert "session_resolved_count" in metrics
        assert "session_not_found_count" in metrics
        assert "session_error_count" in metrics
        assert "session_resolution_rate" in metrics

    def test_metrics_when_disabled(self) -> None:
        config = BusConfiguration.for_testing()
        config.enable_session_governance = False
        processor = MessageProcessor(config=config, isolated_mode=False)

        metrics = processor.get_metrics()

        assert metrics["session_governance_enabled"] is False


class TestSessionContextDisabled:
    def test_session_governance_disabled_by_config(self) -> None:
        config = BusConfiguration.for_testing()
        config.enable_session_governance = False

        processor = MessageProcessor(config=config, isolated_mode=False)

        assert processor._enable_session_governance is False
        assert processor._session_context_manager is None

    def test_session_governance_disabled_in_isolated_mode(self) -> None:
        config = BusConfiguration.for_testing()
        config.enable_session_governance = True

        processor = MessageProcessor(config=config, isolated_mode=True)

        assert processor._enable_session_governance is False
        assert processor._session_context_manager is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
