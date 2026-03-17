"""
Prometheus metric definitions for agent health monitoring.
Constitutional Hash: cdd01ef066bc6cf2

Module-level gauge/counter singletons are registered once at import time.
No side effects beyond registering with the default Prometheus registry.
"""

from __future__ import annotations

from packages.enhanced_agent_bus.agent_health.models import AgentHealthRecord
from prometheus_client import Counter, Gauge

# ---------------------------------------------------------------------------
# Metric singletons (defined at module import time)
# ---------------------------------------------------------------------------

# Current health state encoded as a gauge per agent/tier/state label-set.
# Use value=1 for the active state, 0 for inactive states.
HEALTH_STATE_GAUGE: Gauge = Gauge(
    "acgs_agent_health_state",
    "Current health state of the agent (1 = active for this label combination)",
    labelnames=["agent_id", "autonomy_tier", "health_state"],
)

# Number of consecutive failures observed by the failure-loop detector.
CONSECUTIVE_FAILURES_GAUGE: Gauge = Gauge(
    "acgs_agent_consecutive_failures",
    "Number of consecutive failures for the agent",
    labelnames=["agent_id", "autonomy_tier"],
)

# Memory utilisation as percentage of declared agent limit.
MEMORY_USAGE_GAUGE: Gauge = Gauge(
    "acgs_agent_memory_usage_pct",
    "Agent memory usage as a percentage of its declared memory limit",
    labelnames=["agent_id", "autonomy_tier"],
)

# Total healing actions initiated, partitioned by trigger and action type.
HEALING_ACTIONS_COUNTER: Counter = Counter(
    "acgs_agent_healing_actions_total",
    "Total number of healing actions initiated for the agent",
    labelnames=["agent_id", "autonomy_tier", "action_type", "trigger"],
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def emit_health_metrics(record: AgentHealthRecord) -> None:
    """Update all health gauges atomically from the given AgentHealthRecord.

    Sets the health-state gauge for the active state to 1 and all others to 0,
    then refreshes consecutive-failures and memory-usage gauges.

    Args:
        record: The current AgentHealthRecord for a single agent.
    """
    from packages.enhanced_agent_bus.agent_health.models import HealthState

    tier = record.autonomy_tier.value
    agent = record.agent_id

    # Set the active health-state label to 1; reset the rest to 0
    for state in HealthState:
        HEALTH_STATE_GAUGE.labels(
            agent_id=agent,
            autonomy_tier=tier,
            health_state=state.value,
        ).set(1 if state == record.health_state else 0)

    CONSECUTIVE_FAILURES_GAUGE.labels(
        agent_id=agent,
        autonomy_tier=tier,
    ).set(record.consecutive_failure_count)

    MEMORY_USAGE_GAUGE.labels(
        agent_id=agent,
        autonomy_tier=tier,
    ).set(record.memory_usage_pct)


__all__ = [
    "CONSECUTIVE_FAILURES_GAUGE",
    "HEALING_ACTIONS_COUNTER",
    "HEALTH_STATE_GAUGE",
    "MEMORY_USAGE_GAUGE",
    "emit_health_metrics",
]
