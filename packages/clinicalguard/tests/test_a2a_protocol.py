"""ClinicalGuard: A2A protocol + HIPAA + audit query tests.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from clinicalguard.agent import ClinicalGuardApp
from clinicalguard.skills.validate_clinical import (
    CONDITIONAL,
    RISK_HIGH,
    LLMClinicalAssessment,
)


@pytest.fixture
def client(tmp_path):
    """Test client with a fresh ClinicalGuardApp instance."""
    guard = ClinicalGuardApp.create(audit_log_path=tmp_path / "audit.json")
    app = guard.build_starlette_app()
    return TestClient(app)


@pytest.fixture
def client_with_auth(tmp_path, monkeypatch):
    """Test client with API key auth enabled."""
    monkeypatch.setenv("CLINICALGUARD_API_KEY", "test-key-123")
    guard = ClinicalGuardApp.create(audit_log_path=tmp_path / "audit.json")
    app = guard.build_starlette_app()
    return TestClient(app, raise_server_exceptions=False)


def _make_a2a_body(text: str, task_id: str = "task-001") -> dict:
    return {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "id": "req-1",
        "params": {
            "id": task_id,
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": text}],
            },
        },
    }


class TestAgentCard:
    def test_agent_card_accessible(self, client):
        resp = client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "ClinicalGuard"
        assert len(data["skills"]) == 3

    def test_agent_card_has_required_fields(self, client):
        data = client.get("/.well-known/agent.json").json()
        assert "capabilities" in data
        assert "skills" in data
        skill_ids = [s["id"] for s in data["skills"]]
        assert "validate_clinical_action" in skill_ids
        assert "check_hipaa_compliance" in skill_ids
        assert "query_audit_trail" in skill_ids


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["rules"] == 20
        assert "constitutional_hash" in data


class TestA2AProtocol:
    def test_unknown_method_returns_32601(self, client):
        body = {"jsonrpc": "2.0", "method": "tasks/unknown", "id": "r1", "params": {}}
        resp = client.post("/", json=body)
        data = resp.json()
        assert data["error"]["code"] == -32601

    def test_malformed_json_returns_400(self, client):
        resp = client.post(
            "/",
            content=b"not json at all",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_validate_clinical_action_dispatched(self, client):
        mock_llm = LLMClinicalAssessment(
            recommended_decision=CONDITIONAL,
            risk_tier=RISK_HIGH,
            reasoning="Test reasoning.",
            conditions=["Condition A"],
            llm_available=True,
        )
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=mock_llm,
        ):
            resp = client.post(
                "/",
                json=_make_a2a_body(
                    "validate_clinical_action: Patient SYNTH-001 propose Lisinopril 10mg."
                ),
            )
        assert resp.status_code == 200
        data = resp.json()
        result = data["result"]["result"]
        assert "decision" in result
        assert "audit_id" in result
        assert result["audit_id"].startswith("HC-")

    def test_check_hipaa_dispatched(self, client):
        resp = client.post(
            "/",
            json=_make_a2a_body(
                "check_hipaa_compliance: This agent processes synthetic patient data "
                "with a tamper-evident audit log, MACI enforcement, and API key auth."
            ),
        )
        data = resp.json()
        result = data["result"]["result"]
        assert "compliant" in result
        assert "checklist" in result
        assert result["items_checked"] > 0

    def test_query_audit_trail_dispatched(self, client):
        # First create an audit entry
        mock_llm = LLMClinicalAssessment(
            recommended_decision=CONDITIONAL,
            risk_tier=RISK_HIGH,
            reasoning="Test.",
            llm_available=True,
        )
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=mock_llm,
        ):
            resp = client.post(
                "/",
                json=_make_a2a_body("validate_clinical_action: Patient SYNTH-099 Lisinopril."),
            )
        audit_id = resp.json()["result"]["result"]["audit_id"]

        # Now query it
        resp = client.post("/", json=_make_a2a_body(f"query_audit_trail: {audit_id}"))
        data = resp.json()["result"]["result"]
        assert data["found"] is True
        assert data["chain_valid"] is True
        assert data["entries"][0]["id"] == audit_id

    def test_unknown_skill_returns_helpful_error(self, client):
        resp = client.post("/", json=_make_a2a_body("do_something_unknown: please help"))
        result = resp.json()["result"]["result"]
        # Falls through to default validate skill or returns error with available skills
        assert "decision" in result or "available_skills" in result


class TestAuth:
    def test_valid_api_key_accepted(self, client_with_auth):
        mock_llm = LLMClinicalAssessment(
            recommended_decision=CONDITIONAL,
            risk_tier=RISK_HIGH,
            reasoning="Test.",
            llm_available=True,
        )
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=mock_llm,
        ):
            resp = client_with_auth.post(
                "/",
                json=_make_a2a_body("validate_clinical_action: SYNTH-001 Lisinopril 10mg."),
                headers={"X-API-Key": "test-key-123"},
            )
        assert resp.status_code == 200

    def test_missing_api_key_rejected(self, client_with_auth):
        resp = client_with_auth.post(
            "/",
            json=_make_a2a_body("validate_clinical_action: SYNTH-001 Lisinopril."),
        )
        assert resp.status_code == 401

    def test_wrong_api_key_rejected(self, client_with_auth):
        resp = client_with_auth.post(
            "/",
            json=_make_a2a_body("validate_clinical_action: SYNTH-001 Lisinopril."),
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401


class TestHIPAAChecklist:
    def test_synthetic_data_agent_passes(self, client):
        resp = client.post(
            "/",
            json=_make_a2a_body(
                "check_hipaa_compliance: This agent uses only synthetic de-identified "
                "patient data. It maintains a tamper-evident audit log. It enforces "
                "MACI separation of powers. It uses HTTPS with API key authentication. "
                "No real PHI is ever processed."
            ),
        )
        result = resp.json()["result"]["result"]
        assert result["items_checked"] >= 5

    def test_checklist_has_mitigations(self, client):
        resp = client.post(
            "/",
            json=_make_a2a_body(
                "check_hipaa_compliance: AI healthcare agent with audit logging and MACI enforcement."
            ),
        )
        result = resp.json()["result"]["result"]
        items_with_mitigation = [i for i in result["checklist"] if i.get("mitigation")]
        assert len(items_with_mitigation) > 0
