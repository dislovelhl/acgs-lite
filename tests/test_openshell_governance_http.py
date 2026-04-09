"""HTTP integration tests for the stable OpenShell governance API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from acgs_lite.openshell import (
    GovernanceStateChecksumError,
    JsonFileGovernanceStateBackend,
    RedisGovernanceStateBackend,
    SQLiteGovernanceStateBackend,
    create_openshell_governance_app,
)


def _evaluate_payload() -> dict[str, object]:
    return {
        "action_type": "github.write",
        "operation": "write",
        "risk_level": "high",
        "actor": {
            "actor_id": "agent/openclaw-primary",
            "role": "proposer",
            "display_name": "OpenClaw Main Agent",
            "sandbox_id": "sandbox-demo",
        },
        "resource": {
            "uri": "github://repo/org/repo/issues",
            "kind": "github_repo",
            "tenant_id": "tenant-acme",
        },
        "context": {
            "request_id": "req_123",
            "session_id": "sess_456",
            "environment": "prod",
        },
        "requirements": {
            "requires_network": True,
            "requires_secret": True,
            "requires_human_approval": True,
            "requires_separate_executor": True,
            "mutates_state": True,
        },
        "payload": {
            "payload_hash": "sha256:abcd1234",
            "summary": "Create GitHub issue for production incident follow-up",
        },
    }


@pytest.mark.integration
class TestOpenShellGovernanceHttp:
    class _FakeRedisClient:
        def __init__(self) -> None:
            self._store: dict[str, str] = {}

        def get(self, key: str) -> str | None:
            return self._store.get(key)

        def set(self, key: str, value: str) -> None:
            self._store[key] = value

    def test_openapi_docs_expose_examples(self) -> None:
        with TestClient(create_openshell_governance_app()) as client:
            schema = client.get("/openapi.json")
            assert schema.status_code == 200
            examples = schema.json()["paths"]["/governance/evaluate-action"]["post"]["requestBody"][
                "content"
            ]["application/json"]["examples"]
            assert "high_risk_github_write" in examples

    def test_http_review_flow_survives_restart_with_persistent_state(
        self,
        tmp_path: Path,
    ) -> None:
        state_path = tmp_path / "openshell-state.json"

        with TestClient(create_openshell_governance_app(state_path=state_path)) as client:
            evaluate_response = client.post("/governance/evaluate-action", json=_evaluate_payload())
            assert evaluate_response.status_code == 200
            evaluated = evaluate_response.json()
            assert evaluated["decision"] == "escalate"

            submit_response = client.post(
                "/governance/submit-for-approval",
                json={
                    "decision_id": evaluated["decision_id"],
                    "submitted_by": {
                        "actor_id": "agent/openclaw-primary",
                        "role": "proposer",
                        "display_name": "OpenClaw Main Agent",
                    },
                    "note": "Submit for validator review",
                },
            )
            assert submit_response.status_code == 202
            assert submit_response.json()["decision"] == "escalate"

        assert state_path.exists()

        with TestClient(create_openshell_governance_app(state_path=state_path)) as client:
            review_response = client.post(
                "/governance/review-approval",
                json={
                    "decision_id": evaluated["decision_id"],
                    "reviewer": {
                        "actor_id": "human/alice",
                        "role": "validator",
                        "display_name": "Alice Validator",
                    },
                    "approve": True,
                    "note": "Approved after review",
                },
            )
            assert review_response.status_code == 200
            reviewed = review_response.json()
            assert reviewed["updated_decision"]["decision"] == "require_separate_executor"
            assert reviewed["updated_decision"]["required_role"] == "executor"

    def test_http_review_flow_survives_restart_with_sqlite_backend(
        self,
        tmp_path: Path,
    ) -> None:
        db_path = tmp_path / "openshell-state.db"
        backend = SQLiteGovernanceStateBackend(db_path)

        with TestClient(create_openshell_governance_app(state_backend=backend)) as client:
            evaluated = client.post("/governance/evaluate-action", json=_evaluate_payload()).json()
            client.post(
                "/governance/submit-for-approval",
                json={
                    "decision_id": evaluated["decision_id"],
                    "submitted_by": {
                        "actor_id": "agent/openclaw-primary",
                        "role": "proposer",
                    },
                },
            )

        with TestClient(
            create_openshell_governance_app(state_backend=SQLiteGovernanceStateBackend(db_path))
        ) as client:
            reviewed = client.post(
                "/governance/review-approval",
                json={
                    "decision_id": evaluated["decision_id"],
                    "reviewer": {
                        "actor_id": "human/alice",
                        "role": "validator",
                    },
                    "approve": True,
                },
            ).json()
            assert reviewed["updated_decision"]["decision"] == "require_separate_executor"

    def test_legacy_json_state_migrates_to_versioned_format(self, tmp_path: Path) -> None:
        state_path = tmp_path / "legacy-governance.json"
        legacy_payload = {
            "decisions": {
                "dec_legacy": {
                    "decision_id": "dec_legacy",
                    "decision": "escalate",
                    "action_allowed": False,
                    "is_final": False,
                    "compliance": {
                        "is_compliant": None,
                        "status": "unknown",
                        "reason_codes": ["APPROVAL_PENDING"],
                        "findings": ["Legacy pending approval state."],
                        "reasoning": "Legacy file format",
                        "latency_ms": 0.0,
                        "constitutional_hash": "608508a9bd224290",
                    },
                    "reason_codes": ["APPROVAL_PENDING"],
                    "rationale": "Legacy approval flow",
                    "required_role": "validator",
                    "required_approvals": 1,
                    "expires_at": None,
                    "policy_hash": None,
                    "constitutional_hash": "608508a9bd224290",
                }
            },
            "gates": {
                "dec_legacy": {
                    "action": "Legacy approval flow",
                    "required_approvals": 1,
                    "eligible_voters": None,
                    "deadline": "",
                    "state": "open",
                    "metadata": {
                        "submitted_by": "agent/openclaw-primary",
                        "submitted_role": "proposer",
                        "constitutional_hash": "608508a9bd224290",
                    },
                    "votes": [],
                }
            },
        }
        state_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

        with TestClient(
            create_openshell_governance_app(
                state_backend=JsonFileGovernanceStateBackend(state_path)
            )
        ) as client:
            reviewed = client.post(
                "/governance/review-approval",
                json={
                    "decision_id": "dec_legacy",
                    "reviewer": {
                        "actor_id": "human/alice",
                        "role": "validator",
                    },
                    "approve": True,
                },
            )
            assert reviewed.status_code == 200
            assert reviewed.json()["updated_decision"]["decision"] == "require_separate_executor"

        migrated = json.loads(state_path.read_text(encoding="utf-8"))
        assert migrated["format_version"] == 2
        assert "backend" in migrated

    def test_http_review_flow_survives_restart_with_redis_backend(self) -> None:
        redis_client = self._FakeRedisClient()

        with TestClient(
            create_openshell_governance_app(state_backend=RedisGovernanceStateBackend(redis_client))
        ) as client:
            evaluated = client.post("/governance/evaluate-action", json=_evaluate_payload()).json()
            client.post(
                "/governance/submit-for-approval",
                json={
                    "decision_id": evaluated["decision_id"],
                    "submitted_by": {
                        "actor_id": "agent/openclaw-primary",
                        "role": "proposer",
                    },
                },
            )

        with TestClient(
            create_openshell_governance_app(state_backend=RedisGovernanceStateBackend(redis_client))
        ) as client:
            reviewed = client.post(
                "/governance/review-approval",
                json={
                    "decision_id": evaluated["decision_id"],
                    "reviewer": {
                        "actor_id": "human/alice",
                        "role": "validator",
                    },
                    "approve": True,
                },
            ).json()
            assert reviewed["updated_decision"]["decision"] == "require_separate_executor"

    def test_corrupt_json_state_fails_fast_on_app_creation(self, tmp_path: Path) -> None:
        state_path = tmp_path / "corrupt-state.json"
        state_path.write_text(
            json.dumps(
                {
                    "format_version": 2,
                    "backend": "json-file",
                    "updated_at": "",
                    "decisions": {},
                    "gates": {},
                    "checksum": "tampered",
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(GovernanceStateChecksumError, match="checksum mismatch"):
            create_openshell_governance_app(
                state_backend=JsonFileGovernanceStateBackend(state_path)
            )

    def test_observability_hook_receives_load_and_migration_events(self, tmp_path: Path) -> None:
        events: list[tuple[str, dict[str, object]]] = []
        state_path = tmp_path / "legacy.json"
        state_path.write_text(json.dumps({"decisions": {}, "gates": {}}), encoding="utf-8")

        with TestClient(
            create_openshell_governance_app(
                state_backend=JsonFileGovernanceStateBackend(state_path),
                observability_hook=lambda event, **fields: events.append((event, fields)),
            )
        ):
            pass

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
