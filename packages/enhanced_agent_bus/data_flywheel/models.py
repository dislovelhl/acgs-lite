"""Canonical models for ACGS flywheel records.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class EvaluationMode(StrEnum):
    OFFLINE_REPLAY = "offline_replay"
    SHADOW = "shadow"
    CANARY = "canary"


class WorkloadKey(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=255)
    service: str = Field(min_length=1, max_length=255)
    route_or_tool: str = Field(min_length=1, max_length=255)
    decision_kind: str = Field(min_length=1, max_length=255)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, min_length=1, max_length=64)

    @field_validator("tenant_id", "service", "route_or_tool", "decision_kind")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field must not be empty")
        return cleaned

    def as_key(self) -> str:
        return (
            f"{self.tenant_id}/{self.service}/{self.route_or_tool}/"
            f"{self.decision_kind}/{self.constitutional_hash}"
        )


class DecisionEvent(BaseModel):
    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = Field(min_length=1, max_length=255)
    workload_key: str = Field(min_length=1, max_length=512)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, min_length=1, max_length=64)
    from_agent: str = Field(default="", max_length=255)
    validated_by_agent: str | None = Field(default=None, max_length=255)
    decision_kind: str = Field(min_length=1, max_length=100)
    request_context: JSONDict = Field(default_factory=dict)
    decision_payload: JSONDict = Field(default_factory=dict)
    latency_ms: float | None = None
    outcome: str = Field(min_length=1, max_length=100)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FeedbackEvent(BaseModel):
    feedback_id: str = Field(default_factory=lambda: str(uuid4()))
    decision_id: str | None = Field(default=None, max_length=255)
    tenant_id: str = Field(min_length=1, max_length=255)
    workload_key: str = Field(min_length=1, max_length=512)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, min_length=1, max_length=64)
    feedback_type: str = Field(min_length=1, max_length=100)
    outcome_status: str = Field(min_length=1, max_length=100)
    comment: str | None = Field(default=None, max_length=5000)
    actual_impact: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: JSONDict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DatasetSnapshot(BaseModel):
    snapshot_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = Field(min_length=1, max_length=255)
    workload_key: str = Field(min_length=1, max_length=512)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, min_length=1, max_length=64)
    record_count: int = Field(ge=0)
    redaction_status: str = Field(min_length=1, max_length=64)
    artifact_manifest_uri: str = Field(min_length=1)
    window_started_at: datetime | None = None
    window_ended_at: datetime | None = None
    source_counts: JSONDict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CandidateArtifact(BaseModel):
    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = Field(min_length=1, max_length=255)
    workload_key: str = Field(min_length=1, max_length=512)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, min_length=1, max_length=64)
    candidate_type: str = Field(min_length=1, max_length=100)
    candidate_spec: JSONDict = Field(default_factory=dict)
    parent_version: str | None = Field(default=None, max_length=255)
    status: str = Field(default="draft", min_length=1, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvaluationRun(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = Field(min_length=1, max_length=255)
    workload_key: str = Field(min_length=1, max_length=512)
    candidate_id: str = Field(min_length=1, max_length=255)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, min_length=1, max_length=64)
    evaluation_mode: EvaluationMode
    status: str = Field(min_length=1, max_length=64)
    summary_metrics: JSONDict = Field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceBundle(BaseModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = Field(min_length=1, max_length=255)
    workload_key: str = Field(min_length=1, max_length=512)
    candidate_id: str = Field(min_length=1, max_length=255)
    dataset_snapshot_id: str = Field(min_length=1, max_length=255)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, min_length=1, max_length=64)
    approval_state: str = Field(min_length=1, max_length=64)
    validator_records: list[JSONDict] = Field(default_factory=list)
    rollback_plan: JSONDict = Field(default_factory=dict)
    artifact_manifest_uri: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "CandidateArtifact",
    "DatasetSnapshot",
    "DecisionEvent",
    "EvaluationMode",
    "EvaluationRun",
    "EvidenceBundle",
    "FeedbackEvent",
    "WorkloadKey",
]
