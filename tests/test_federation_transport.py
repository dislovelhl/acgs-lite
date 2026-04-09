"""Tests for federation HTTP transport endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from acgs_lite._meta import CONSTITUTIONAL_HASH
from acgs_lite.server import create_governance_app


def _valid_payload() -> dict[str, object]:
    return {
        "entry_id": "entry-1",
        "agent_id": "agent-1",
        "action": "share audit event",
        "valid": True,
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "timestamp": "2026-04-07T12:00:00+00:00",
    }


def test_audit_push_accepts_valid_body_when_federation_enabled(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ACGS_FEDERATION_ENABLED", "true")
    monkeypatch.delenv("ACGS_FEDERATION_TOKEN", raising=False)

    client = TestClient(create_governance_app())

    response = client.post("/v1/federation/audit/push", json=_valid_payload())

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}


def test_audit_push_rejects_wrong_constitutional_hash(monkeypatch) -> None:
    monkeypatch.setenv("ACGS_FEDERATION_ENABLED", "true")
    monkeypatch.delenv("ACGS_FEDERATION_TOKEN", raising=False)
    payload = _valid_payload()
    payload["constitutional_hash"] = "wrong-hash"

    client = TestClient(create_governance_app())
    response = client.post("/v1/federation/audit/push", json=payload)

    assert response.status_code == 422


def test_audit_push_rejects_wrong_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("ACGS_FEDERATION_ENABLED", "true")
    monkeypatch.setenv("ACGS_FEDERATION_TOKEN", "expected-token")

    client = TestClient(create_governance_app())
    response = client.post(
        "/v1/federation/audit/push",
        json=_valid_payload(),
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401


def test_router_not_mounted_when_federation_disabled(monkeypatch) -> None:
    monkeypatch.delenv("ACGS_FEDERATION_ENABLED", raising=False)
    monkeypatch.delenv("ACGS_FEDERATION_TOKEN", raising=False)

    client = TestClient(create_governance_app())
    response = client.post("/v1/federation/audit/push", json=_valid_payload())

    assert response.status_code == 404
