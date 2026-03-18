from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass
from threading import Lock

from src.core.shared.types import JSONDict

sys.modules.setdefault("src.core.shared.agent_workflow_metrics", sys.modules[__name__])

_VALID_EVENT_TYPES: frozenset[str] = frozenset(
    {"intervention", "gate_failure", "rollback_trigger", "autonomous_action"}
)


@dataclass(slots=True)
class WorkflowTenantCounters:
    interventions_total: int = 0
    gate_failures_total: int = 0
    rollback_triggers_total: int = 0
    autonomous_actions_total: int = 0

    def apply(self, event_type: str) -> None:
        if event_type == "intervention":
            self.interventions_total += 1
        elif event_type == "gate_failure":
            self.gate_failures_total += 1
        elif event_type == "rollback_trigger":
            self.rollback_triggers_total += 1
        elif event_type == "autonomous_action":
            self.autonomous_actions_total += 1

    def to_snapshot(self) -> JSONDict:
        denominator = self.interventions_total + self.autonomous_actions_total
        intervention_rate = self.interventions_total / denominator if denominator else 0.0
        return {
            "interventions_total": self.interventions_total,
            "gate_failures_total": self.gate_failures_total,
            "rollback_triggers_total": self.rollback_triggers_total,
            "autonomous_actions_total": self.autonomous_actions_total,
            "intervention_rate": intervention_rate,
        }


class AgentWorkflowMetricsCollector:
    def __init__(self) -> None:
        self._lock = Lock()
        self._tenant_counters: defaultdict[str, WorkflowTenantCounters] = defaultdict(
            WorkflowTenantCounters
        )

    def record_event(
        self,
        *,
        event_type: str,
        tenant_id: str = "default",
        source: str = "unknown",
        reason: str = "unknown",
    ) -> None:
        del source, reason
        if event_type not in _VALID_EVENT_TYPES:
            raise ValueError(f"Unsupported workflow event type: {event_type}")

        tenant_key = tenant_id or "default"
        with self._lock:
            self._tenant_counters[tenant_key].apply(event_type)

    def snapshot(self, tenant_id: str | None = None) -> JSONDict:
        with self._lock:
            if tenant_id is not None:
                return dict(self._tenant_counters[tenant_id or "default"].to_snapshot())

            total = WorkflowTenantCounters()
            for counters in self._tenant_counters.values():
                total.interventions_total += counters.interventions_total
                total.gate_failures_total += counters.gate_failures_total
                total.rollback_triggers_total += counters.rollback_triggers_total
                total.autonomous_actions_total += counters.autonomous_actions_total
            return dict(total.to_snapshot())

    def reset(self) -> None:
        with self._lock:
            self._tenant_counters.clear()


_COLLECTOR: AgentWorkflowMetricsCollector | None = None


def get_agent_workflow_metrics_collector() -> AgentWorkflowMetricsCollector:
    global _COLLECTOR
    if _COLLECTOR is None:
        _COLLECTOR = AgentWorkflowMetricsCollector()
    return _COLLECTOR


def reset_agent_workflow_metrics_collector() -> AgentWorkflowMetricsCollector:
    global _COLLECTOR
    _COLLECTOR = AgentWorkflowMetricsCollector()
    return _COLLECTOR


__all__ = [
    "AgentWorkflowMetricsCollector",
    "WorkflowTenantCounters",
    "get_agent_workflow_metrics_collector",
    "reset_agent_workflow_metrics_collector",
]
