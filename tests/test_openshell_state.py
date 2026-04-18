"""Tests for OpenShell governance state backends and migrations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from acgs_lite.constitution.quorum import QuorumManager
from acgs_lite.openshell_state import (
    GovernanceStateChecksumError,
    InMemoryGovernanceStateBackend,
    JsonFileGovernanceStateBackend,
    PersistentGovernanceState,
    RedisGovernanceStateBackend,
    compute_state_checksum,
    migrate_state,
    verify_state_checksum,
    with_checksum,
)


class _FakeRedisClient:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        self._store[key] = value


class _DecisionModel(BaseModel):
    decision: str


@pytest.mark.unit
class TestOpenShellState:
    def test_migrate_legacy_state_adds_version_and_checksum(self) -> None:
        migrated = migrate_state({"decisions": {}, "gates": {}})
        assert migrated["format_version"] == 2
        assert isinstance(migrated["checksum"], str)
        verify_state_checksum(migrated)

    def test_checksum_detects_tampering(self) -> None:
        payload = with_checksum(
            {
                "format_version": 2,
                "backend": "memory",
                "updated_at": "",
                "decisions": {},
                "gates": {},
            }
        )
        payload["decisions"] = {"dec_1": {"decision": "allow"}}
        with pytest.raises(GovernanceStateChecksumError, match="checksum mismatch"):
            verify_state_checksum(payload)

    def test_json_backend_load_rejects_corrupt_payload(self, tmp_path: Path) -> None:
        path = tmp_path / "corrupt.json"
        payload = with_checksum(
            {
                "format_version": 2,
                "backend": "json-file",
                "updated_at": "",
                "decisions": {},
                "gates": {},
            }
        )
        payload["checksum"] = "bad"
        path.write_text(json.dumps(payload), encoding="utf-8")
        backend = JsonFileGovernanceStateBackend(path)
        with pytest.raises(GovernanceStateChecksumError, match="checksum mismatch"):
            migrate_state(backend.load_state())

    def test_redis_backend_load_rejects_corrupt_payload(self) -> None:
        client = _FakeRedisClient()
        payload = with_checksum(
            {
                "format_version": 2,
                "backend": "redis",
                "updated_at": "",
                "decisions": {},
                "gates": {},
            }
        )
        payload["checksum"] = compute_state_checksum({"unexpected": "shape"})
        client.set("openshell_governance", json.dumps(payload))
        backend = RedisGovernanceStateBackend(client)
        with pytest.raises(GovernanceStateChecksumError, match="checksum mismatch"):
            migrate_state(backend.load_state())

    def test_persistent_state_emits_migration_and_loaded_events(self, tmp_path: Path) -> None:
        events: list[tuple[str, dict[str, object]]] = []
        state_path = tmp_path / "legacy.json"
        state_path.write_text(json.dumps({"decisions": {}, "gates": {}}), encoding="utf-8")

        PersistentGovernanceState(
            JsonFileGovernanceStateBackend(state_path),
            observability_hook=lambda event, **fields: events.append((event, fields)),
        )

        assert (
            "loaded",
            {"backend_type": "JsonFileGovernanceStateBackend", "format_version": 2},
        ) in events
        assert (
            "migrated",
            {
                "backend_type": "JsonFileGovernanceStateBackend",
                "from_version": 1,
                "to_version": 2,
            },
        ) in events

    def test_persistent_state_emits_checksum_failure_event(self, tmp_path: Path) -> None:
        events: list[tuple[str, dict[str, object]]] = []
        state_path = tmp_path / "corrupt.json"
        payload = with_checksum(
            {
                "format_version": 2,
                "backend": "json-file",
                "updated_at": "",
                "decisions": {},
                "gates": {},
            }
        )
        payload["checksum"] = "tampered"
        state_path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(GovernanceStateChecksumError, match="checksum mismatch"):
            PersistentGovernanceState(
                JsonFileGovernanceStateBackend(state_path),
                observability_hook=lambda event, **fields: events.append((event, fields)),
            )

        assert len(events) == 1
        event, fields = events[0]
        assert event == "checksum_failure"
        assert fields["backend_type"] == "JsonFileGovernanceStateBackend"
        assert "checksum mismatch" in str(fields["error"])

    def test_persistent_state_emits_saved_event(self) -> None:
        events: list[tuple[str, dict[str, object]]] = []
        store = PersistentGovernanceState(
            InMemoryGovernanceStateBackend(),
            observability_hook=lambda event, **fields: events.append((event, fields)),
        )

        quorum = QuorumManager()
        store.save(
            decision_store={"dec_1": _DecisionModel(decision="allow")},
            quorum=quorum,
        )

        assert (
            "saved",
            {
                "backend_type": "InMemoryGovernanceStateBackend",
                "format_version": 2,
                "decision_count": 1,
                "gate_count": 0,
            },
        ) in events
