"""
Agent Health Monitoring — Data Models and Enums.
Constitutional Hash: 608508a9bd224290

Defines all Pydantic v2 data contracts for the agent health sub-system:
- Enums: HealthState, AutonomyTier, HealingTrigger, HealingActionType, OverrideMode
- Models: AgentHealthRecord, HealingAction, HealingOverride, AgentHealthThresholds
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.types import AgentID

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class HealthState(StrEnum):
    """Current health state of an agent."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    QUARANTINED = "QUARANTINED"
    RESTARTING = "RESTARTING"


class AutonomyTier(StrEnum):
    """Autonomy tier governing which healing actions an agent may take autonomously."""

    ADVISORY = "ADVISORY"  # Tier 1 — lowest autonomy; quarantine + HITL request
    BOUNDED = "BOUNDED"  # Tier 2 — supervised; notify supervisor, await approval
    HUMAN_APPROVED = "HUMAN_APPROVED"  # Tier 3 — full autonomy; self-restart


class HealingTrigger(StrEnum):
    """What condition triggered a healing action."""

    FAILURE_LOOP = "FAILURE_LOOP"
    MEMORY_EXHAUSTION = "MEMORY_EXHAUSTION"
    MANUAL = "MANUAL"


class HealingActionType(StrEnum):
    """Type of healing action taken."""

    GRACEFUL_RESTART = "GRACEFUL_RESTART"
    QUARANTINE = "QUARANTINE"
    SUPERVISOR_NOTIFY = "SUPERVISOR_NOTIFY"
    HITL_REQUEST = "HITL_REQUEST"


class OverrideMode(StrEnum):
    """Mode for an operator-issued healing override."""

    SUPPRESS_HEALING = "SUPPRESS_HEALING"
    FORCE_RESTART = "FORCE_RESTART"
    FORCE_QUARANTINE = "FORCE_QUARANTINE"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AgentHealthRecord(BaseModel):
    """Current health snapshot for a single agent instance, stored as Redis hash.

    Constitutional Hash: 608508a9bd224290
    """

    model_config = {"frozen": False}

    agent_id: Annotated[AgentID, Field(min_length=1, max_length=255)]
    health_state: HealthState
    consecutive_failure_count: Annotated[int, Field(ge=0)]
    memory_usage_pct: Annotated[float, Field(ge=0.0, le=100.0)]
    last_error_type: Annotated[str | None, Field(default=None, max_length=128)]
    last_event_at: datetime
    autonomy_tier: AutonomyTier
    healing_override_id: str | None = None


class HealingAction(BaseModel):
    """A governance-approved action taken to restore agent health.

    Written to the governance audit log before execution.
    Constitutional Hash: 608508a9bd224290
    """

    model_config = {"frozen": True}

    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: AgentID
    trigger: HealingTrigger
    action_type: HealingActionType
    tier_determined_by: AutonomyTier
    initiated_at: datetime
    completed_at: datetime | None = None
    audit_event_id: str
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    @field_validator("constitutional_hash")
    @classmethod
    def _validate_hash(cls, v: str) -> str:
        if v != CONSTITUTIONAL_HASH:
            raise ValueError(f"constitutional_hash must equal '{CONSTITUTIONAL_HASH}', got '{v}'")
        return v


class HealingOverride(BaseModel):
    """Operator-issued instruction to suppress or force a healing action.

    Constitutional Hash: 608508a9bd224290
    """

    model_config = {"frozen": True}

    override_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: AgentID
    mode: OverrideMode
    reason: Annotated[str, Field(min_length=1, max_length=1000)]
    issued_by: str
    issued_at: datetime
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_expiry(self) -> HealingOverride:
        if self.expires_at is not None and self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be strictly after issued_at")
        return self


class AgentHealthThresholds(BaseModel):
    """Configurable thresholds controlling when healing actions trigger.

    Per-agent overrides fall back to global defaults when agent_id is None.
    Constitutional Hash: 608508a9bd224290
    """

    model_config = {"frozen": False}

    agent_id: AgentID | None = None
    failure_count_threshold: Annotated[int, Field(ge=1, default=5)]
    failure_window_seconds: Annotated[int, Field(ge=10, default=60)]
    memory_exhaustion_pct: Annotated[float, Field(ge=50.0, le=99.0, default=85.0)]
    memory_hysteresis_pct: Annotated[float, Field(ge=1.0, le=20.0, default=10.0)]
    drain_timeout_seconds: Annotated[int, Field(ge=5, default=30)]
    metric_emit_interval_seconds: Annotated[int, Field(ge=5, default=30)]


__all__ = [
    "CONSTITUTIONAL_HASH",
    "AgentHealthRecord",
    "AgentHealthThresholds",
    "AutonomyTier",
    "HealingAction",
    "HealingActionType",
    "HealingOverride",
    "HealingTrigger",
    "HealthState",
    "OverrideMode",
]
