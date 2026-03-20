from __future__ import annotations

from fastapi import Body
from fastapi.testclient import TestClient

from src.core.shared.fastapi_base import create_acgs_app


def test_create_acgs_app_enforces_trusted_hosts() -> None:
    app = create_acgs_app(
        "test-service",
        environment="production",
        trusted_hosts=["api.example.com"],
    )

    client = TestClient(app, base_url="https://api.example.com")
    allowed_response = client.get("/health")

    blocked_client = TestClient(app, base_url="https://evil.example.com")
    blocked_response = blocked_client.get("/health")

    assert allowed_response.status_code == 200
    assert blocked_response.status_code == 400


def test_create_acgs_app_allows_testserver_in_test_environment() -> None:
    app = create_acgs_app(
        "test-service",
        environment="test",
        trusted_hosts=["localhost", "127.0.0.1"],
    )

    client = TestClient(app, base_url="https://testserver")
    response = client.get("/health")

    assert response.status_code == 200


def test_validation_errors_do_not_reflect_request_body() -> None:
    app = create_acgs_app(
        "test-service",
        environment="test",
        trusted_hosts=["localhost", "127.0.0.1"],
    )

    @app.post("/submit")
    async def submit(secret: str = Body(..., embed=True, min_length=8)) -> dict[str, bool]:
        return {"ok": bool(secret)}

    client = TestClient(app, base_url="https://testserver")
    response = client.post("/submit", json={"secret": "short"})

    assert response.status_code == 422
    payload = response.json()
    assert "detail" in payload
    assert "body" not in payload
