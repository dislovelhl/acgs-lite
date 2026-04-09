"""Training-to-inference provenance chain helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class ProvenanceNode:
    """Single immutable link in a model provenance chain."""

    stage: str
    artifact_id: str
    artifact_hash: str
    timestamp: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, str]:
        return {
            "stage": self.stage,
            "artifact_id": self.artifact_id,
            "artifact_hash": self.artifact_hash,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class ProvenanceRecord:
    """Traceability chain from base model through inference."""

    model_id: str
    base_model: str
    nodes: list[ProvenanceNode]
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "base_model": self.base_model,
            "nodes": [node.to_dict() for node in self.nodes],
            "created_at": self.created_at,
        }

    @classmethod
    def from_env(cls) -> ProvenanceRecord | None:
        model_id = os.getenv("ACGS_MODEL_ID", "").strip()
        if not model_id:
            return None

        base_model = os.getenv("ACGS_BASE_MODEL", "").strip()
        training_run_id = os.getenv("ACGS_TRAINING_RUN_ID", "").strip()
        training_dataset_hash = os.getenv("ACGS_TRAINING_DATASET_HASH", "").strip()
        finetune_hash = os.getenv("ACGS_FINETUNE_HASH", "").strip()
        deployment_id = os.getenv("ACGS_DEPLOYMENT_ID", "").strip()

        nodes: list[ProvenanceNode] = []
        if base_model:
            nodes.append(
                ProvenanceNode(
                    stage="base_model",
                    artifact_id=base_model,
                    artifact_hash="",
                )
            )
        if training_run_id or training_dataset_hash:
            nodes.append(
                ProvenanceNode(
                    stage="training",
                    artifact_id=training_run_id or model_id,
                    artifact_hash=training_dataset_hash,
                )
            )
        if finetune_hash:
            nodes.append(
                ProvenanceNode(
                    stage="finetune",
                    artifact_id=model_id,
                    artifact_hash=finetune_hash,
                )
            )
        if deployment_id:
            nodes.append(
                ProvenanceNode(
                    stage="deployment",
                    artifact_id=deployment_id,
                    artifact_hash=finetune_hash,
                )
            )
        nodes.append(
            ProvenanceNode(
                stage="inference",
                artifact_id=model_id,
                artifact_hash=finetune_hash or training_dataset_hash,
            )
        )
        return cls(model_id=model_id, base_model=base_model, nodes=nodes)
