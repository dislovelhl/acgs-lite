"""Shim for src.core.shared.agent_workflow_metrics."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.agent_workflow_metrics import *  # noqa: F403
except ImportError:

    class AgentWorkflowMetrics:
        """No-op agent workflow metrics collector."""

        def __init__(self, **kwargs: Any) -> None:
            pass

        def record_step(self, step_name: str, duration_ms: float = 0.0, **kwargs: Any) -> None:
            pass

        def record_decision(self, decision_type: str, outcome: str = "", **kwargs: Any) -> None:
            pass

        def record_error(self, error_type: str, **kwargs: Any) -> None:
            pass

        def get_summary(self) -> dict[str, Any]:
            return {}

    def get_workflow_metrics(**kwargs: Any) -> AgentWorkflowMetrics:
        return AgentWorkflowMetrics(**kwargs)
