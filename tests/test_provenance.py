"""Tests for training-to-inference provenance records."""

from __future__ import annotations

import json

from acgs_lite.provenance import ProvenanceRecord


def test_from_env_returns_none_without_model_id(monkeypatch) -> None:
    monkeypatch.delenv("ACGS_MODEL_ID", raising=False)

    assert ProvenanceRecord.from_env() is None


def test_from_env_appends_inference_node(monkeypatch) -> None:
    monkeypatch.setenv("ACGS_MODEL_ID", "test-model")
    monkeypatch.setenv("ACGS_BASE_MODEL", "base-model")
    monkeypatch.setenv("ACGS_TRAINING_RUN_ID", "run-123")
    monkeypatch.setenv("ACGS_TRAINING_DATASET_HASH", "dataset-hash")
    monkeypatch.setenv("ACGS_FINETUNE_HASH", "finetune-hash")
    monkeypatch.setenv("ACGS_DEPLOYMENT_ID", "deployment-123")

    record = ProvenanceRecord.from_env()

    assert record is not None
    assert record.model_id == "test-model"
    assert record.nodes[-1].stage == "inference"
    assert record.nodes[-1].artifact_id == "test-model"


def test_to_dict_is_json_serializable(monkeypatch) -> None:
    monkeypatch.setenv("ACGS_MODEL_ID", "test-model")

    record = ProvenanceRecord.from_env()

    assert record is not None
    json.dumps(record.to_dict())
