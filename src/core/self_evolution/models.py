"""Shared models for bounded self-evolution control surfaces.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from enhanced_agent_bus.data_flywheel.models import EvidenceBundle


class ResearchRuntimeState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOP_REQUESTED = "stop_requested"


class ResearchOperatorControlSnapshot(BaseModel):
    """Serialized snapshot of the self-evolution operator control plane."""

    paused: bool = False
    stop_requested: bool = False
    status: str = "running"
    updated_by: str | None = None
    reason: str | None = None
    mode: str = "running"
    requested_by: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    runtime_instance_id: str | None = None
    runtime_state: str | None = None
    runtime_last_run_id: str | None = None
    runtime_generation_index: int | None = None
    runtime_pid: int | None = None
    runtime_online: bool = False


class BoundedExperimentEvidenceRecord(BaseModel):
    """Immutable evidence record for a bounded self-evolution experiment."""

    evidence_id: UUID = Field(default_factory=uuid4)
    experiment_id: UUID
    hypothesis_id: UUID
    cycle_id: UUID
    proposal_id: UUID
    metric_name: str = Field(min_length=1, max_length=255)
    baseline: float
    observed: float
    delta_percent: float
    kept: bool
    reason: str = Field(min_length=1, max_length=2000)
    lower_is_better: bool = True
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BoundedExperimentEvidenceListResponse(BaseModel):
    total: int
    records: list[BoundedExperimentEvidenceRecord]


class FlywheelEvidenceBundleListResponse(BaseModel):
    total: int
    records: list[EvidenceBundle]


__all__ = [
    "BoundedExperimentEvidenceListResponse",
    "BoundedExperimentEvidenceRecord",
    "FlywheelEvidenceBundleListResponse",
    "ResearchOperatorControlSnapshot",
    "ResearchRuntimeState",
]
