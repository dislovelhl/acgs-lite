"""
agent_health sub-package for the Enhanced Agent Bus.

This package provides agent health monitoring, anomaly detection,
and autonomous healing capabilities. It tracks per-agent health
metrics, detects degradation, and initiates governed recovery actions
(restart, reroute, quarantine, HITL escalation) based on autonomy tier.

Public API exports:
  Models / Enums:
    AgentHealthRecord, HealingAction, HealingOverride, AgentHealthThresholds
    HealthState, AutonomyTier, HealingTrigger, HealingActionType, OverrideMode

  Store:
    AgentHealthStore

  Metrics:
    emit_health_metrics

  Actions:
    AgentBusGateway, GracefulRestarter

Constitutional Hash: 608508a9bd224290
"""

from enhanced_agent_bus.agent_health.actions import (
    AgentBusGateway,
    GracefulRestarter,
)
from enhanced_agent_bus.agent_health.metrics import emit_health_metrics
from enhanced_agent_bus.agent_health.models import (
    AgentHealthRecord,
    AgentHealthThresholds,
    AutonomyTier,
    HealingAction,
    HealingActionType,
    HealingOverride,
    HealingTrigger,
    HealthState,
    OverrideMode,
)
from enhanced_agent_bus.agent_health.monitor import AgentHealthMonitor
from enhanced_agent_bus.agent_health.store import AgentHealthStore

__all__ = [
    # Actions
    "AgentBusGateway",
    # Monitor
    "AgentHealthMonitor",
    # Models
    "AgentHealthRecord",
    # Store
    "AgentHealthStore",
    "AgentHealthThresholds",
    "AutonomyTier",
    "GracefulRestarter",
    "HealingAction",
    "HealingActionType",
    "HealingOverride",
    "HealingTrigger",
    # Enums
    "HealthState",
    "OverrideMode",
    # Metrics
    "emit_health_metrics",
]
