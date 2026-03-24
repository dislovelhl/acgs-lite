import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.services.api_gateway.routes import x402_governance, x402_marketplace


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(x402_governance.router)
    app.include_router(x402_marketplace.router)
    return TestClient(app)


def test_pricing_exposes_journey_groups(client: TestClient) -> None:
    response = client.get("/x402/pricing")

    assert response.status_code == 200
    payload = response.json()
    assert any(item["endpoint"] == "/x402/certify" for item in payload["endpoints"])

    journeys = {item["name"]: item for item in payload["journeys"]}
    assert "Safety Check" in journeys
    assert "Trust & Proof" in journeys
    assert journeys["Trust & Proof"]["steps"][0]["endpoint"] == "/x402/certify"


def test_verify_exposes_discovery_links(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATTESTATION_SECRET", "test-attestation-secret")

    canonical = json.dumps(
        {"compliant": True, "decision": "APPROVED"},
        sort_keys=True,
        separators=(",", ":"),
    )
    receipt_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    signature = hmac.new(
        b"test-attestation-secret",
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    response = client.get(
        "/x402/verify",
        params={
            "receipt_hash": receipt_hash,
            "signature": signature,
            "data": canonical,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["discovery"]["check"] == "/x402/check"
    assert payload["discovery"]["pricing"] == "/x402/pricing"


def test_validate_response_adds_disclaimer_and_related_endpoints(client: TestClient) -> None:
    response = client.post(
        "/x402/validate",
        json={"action": "deploy to staging", "agent_id": "agent-1", "context": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "Not legal advice" in payload["disclaimer"]
    assert any(item["endpoint"] == "/x402/certify" for item in payload["related_endpoints"])


def test_scan_response_uses_machine_readable_related_endpoints(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Severity:
        value = "low"

    class _Result:
        is_injection = False
        severity = _Severity()
        injection_type = None
        confidence = 0.02
        matched_patterns: tuple[str, ...] = ()
        sanitized_content = "safe prompt"

    class _Detector:
        def detect(self, content: str, context: dict[str, object] | None) -> _Result:
            return _Result()

    monkeypatch.setattr(x402_marketplace, "_get_injection_detector", lambda: _Detector())

    response = client.post("/x402/scan", json={"content": "safe prompt", "context": {}})

    assert response.status_code == 200
    payload = response.json()
    assert "upgrade" not in payload
    assert "Not legal advice" in payload["disclaimer"]
    assert payload["related_endpoints"][0]["endpoint"] == "/x402/validate"


def test_attestation_secret_validation_rejects_default_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("ATTESTATION_SECRET", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="ATTESTATION_SECRET"):
        x402_governance.ensure_attestation_secret_config()
