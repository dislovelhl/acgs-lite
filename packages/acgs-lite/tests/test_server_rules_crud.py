"""Tests for rules CRUD endpoints in acgs-lite server."""

import pytest
from fastapi.testclient import TestClient

from acgs_lite.server import create_governance_app


@pytest.fixture
def client(tmp_path):
    app = create_governance_app(audit_db_path=tmp_path / "audit.db")
    return TestClient(app)


class TestListRules:
    def test_returns_default_rules(self, client):
        resp = client.get("/rules")
        assert resp.status_code == 200
        rules = resp.json()
        assert isinstance(rules, list)
        assert len(rules) > 0
        assert "id" in rules[0]
        assert "severity" in rules[0]

    def test_rule_has_expected_fields(self, client):
        resp = client.get("/rules")
        rule = resp.json()[0]
        for field in ["id", "text", "severity", "keywords", "category", "workflow_action", "enabled"]:
            assert field in rule


class TestGetRule:
    def test_get_existing_rule(self, client):
        rules = client.get("/rules").json()
        rule_id = rules[0]["id"]
        resp = client.get(f"/rules/{rule_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == rule_id

    def test_get_nonexistent_rule(self, client):
        resp = client.get("/rules/nonexistent-rule-id")
        assert resp.status_code == 404


class TestCreateRule:
    def test_create_valid_rule(self, client):
        payload = {
            "id": "test-new-rule",
            "text": "Block harmful content",
            "severity": "high",
            "keywords": ["harmful", "dangerous"],
            "category": "safety",
            "workflow_action": "block",
        }
        resp = client.post("/rules", json=payload)
        assert resp.status_code == 201
        assert resp.json()["id"] == "test-new-rule"

        # Verify it appears in the list
        rules = client.get("/rules").json()
        assert any(r["id"] == "test-new-rule" for r in rules)

    def test_create_duplicate_rule(self, client):
        rules = client.get("/rules").json()
        existing_id = rules[0]["id"]
        resp = client.post("/rules", json={"id": existing_id, "text": "dup"})
        assert resp.status_code == 409

    def test_create_rule_missing_id(self, client):
        resp = client.post("/rules", json={"text": "no id"})
        assert resp.status_code == 422

    def test_created_rule_is_enforceable(self, client):
        """After creating a rule, validation should enforce it."""
        client.post("/rules", json={
            "id": "test-enforce",
            "text": "Block test keyword",
            "severity": "critical",
            "keywords": ["blockedword"],
            "category": "safety",
            "workflow_action": "block",
        })
        result = client.post("/validate", json={
            "action": "do something with blockedword",
            "agent_id": "test",
        }).json()
        assert len(result["violations"]) > 0
        assert any(v["rule_id"] == "test-enforce" for v in result["violations"])


class TestUpdateRule:
    def test_update_existing_rule(self, client):
        rules = client.get("/rules").json()
        rule_id = rules[0]["id"]
        resp = client.put(f"/rules/{rule_id}", json={"text": "Updated text"})
        assert resp.status_code == 200
        assert resp.json()["text"] == "Updated text"

    def test_update_nonexistent_rule(self, client):
        resp = client.put("/rules/nonexistent", json={"text": "nope"})
        assert resp.status_code == 404

    def test_update_preserves_unchanged_fields(self, client):
        rules = client.get("/rules").json()
        original = rules[0]
        rule_id = original["id"]
        resp = client.put(f"/rules/{rule_id}", json={"text": "Changed"})
        updated = resp.json()
        assert updated["text"] == "Changed"
        assert updated["severity"] == original["severity"]
        assert updated["category"] == original["category"]


class TestDeleteRule:
    def test_delete_existing_rule(self, client):
        # Create then delete
        client.post("/rules", json={
            "id": "to-delete",
            "text": "Will be deleted",
            "severity": "low",
            "category": "test",
        })
        resp = client.delete("/rules/to-delete")
        assert resp.status_code == 204

        # Verify gone
        assert client.get("/rules/to-delete").status_code == 404

    def test_delete_nonexistent_rule(self, client):
        resp = client.delete("/rules/nonexistent")
        assert resp.status_code == 404
