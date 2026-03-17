import hashlib
import hmac
import json
import os
import sys
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ENABLE_RATE_LIMITING"] = "false"
os.environ["SAML_ENABLED"] = "false"

from src.core.services.api_gateway.main import app
from src.core.services.api_gateway.routes.admin_sso import get_current_admin
from src.core.services.api_gateway.workos_event_ingestion import reset_workos_ingestion_service
from src.core.shared.config import settings


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, base_url="https://testserver")


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> None:
    reset_workos_ingestion_service()
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    reset_workos_ingestion_service()


@pytest.fixture
def override_admin_dependency() -> None:
    def _override_admin():
        return {"id": "admin-test", "roles": ["admin"]}

    app.dependency_overrides[get_current_admin] = _override_admin


@pytest.fixture
def configure_workos(monkeypatch):
    def _configure(**overrides):
        defaults = {
            "workos_enabled": True,
            "workos_client_id": "client_test_123",
            "workos_api_key": SecretStr("sk_test_123"),
            "workos_webhook_secret": SecretStr("whsec_test_123"),  # pragma: allowlist secret
            "workos_portal_default_intent": "sso",
            "workos_api_base_url": "https://api.workos.com",
            "workos_webhook_dedupe_ttl_seconds": 86400,
            "workos_webhook_fail_closed": False,
        }
        defaults.update(overrides)
        for key, value in defaults.items():
            monkeypatch.setattr(settings.sso, key, value, raising=False)

    return _configure


def test_create_portal_link_success(
    client: TestClient,
    override_admin_dependency,
    configure_workos,
) -> None:
    configure_workos()

    with patch(
        "src.core.services.api_gateway.routes.admin_workos.generate_workos_admin_portal_link",
        new=AsyncMock(return_value="https://dashboard.workos.com/portal-link/abc123"),
    ) as mocked_generate:
        response = client.post(
            "/api/v1/admin/sso/workos/portal-links",
            json={
                "organization_id": "org_01ABCXYZ",
                "intent": "sso",
                "return_url": "https://acgs2.example.com/admin/sso",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["link"] == "https://dashboard.workos.com/portal-link/abc123"
    mocked_generate.assert_awaited_once()


def test_create_portal_link_requires_workos_enabled(
    client: TestClient,
    override_admin_dependency,
    configure_workos,
) -> None:
    configure_workos(workos_enabled=False)

    response = client.post(
        "/api/v1/admin/sso/workos/portal-links",
        json={
            "organization_id": "org_01ABCXYZ",
            "intent": "sso",
        },
    )

    assert response.status_code == 503
    assert "not enabled" in response.json()["detail"].lower()


def test_pull_workos_events_success(
    client: TestClient,
    override_admin_dependency,
    configure_workos,
) -> None:
    configure_workos()

    with patch(
        "src.core.services.api_gateway.routes.admin_workos.list_workos_events",
        new=AsyncMock(
            return_value={
                "data": [
                    {
                        "id": "event_123",
                        "event": "connection.activated",
                        "created_at": "2026-02-16T12:00:00.000Z",
                    }
                ],
                "list_metadata": {"after": "event_123"},
            }
        ),
    ) as mocked_list_events:
        response = client.get(
            "/api/v1/admin/sso/workos/events",
            params=[("event", "connection.activated")],
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["event"] == "connection.activated"
    assert data["list_metadata"]["after"] == "event_123"
    mocked_list_events.assert_awaited_once()


def _generate_workos_signature_header(payload: bytes, secret: str) -> str:
    timestamp_ms = int(time.time() * 1000)
    unhashed = f"{timestamp_ms}.{payload.decode('utf-8')}"
    digest = hmac.new(secret.encode("utf-8"), unhashed.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"t={timestamp_ms}, v1={digest}"


def test_workos_webhook_success(client: TestClient, configure_workos) -> None:
    webhook_secret = "whsec_test_123"  # pragma: allowlist secret
    configure_workos(workos_webhook_secret=SecretStr(webhook_secret))

    payload = json.dumps(
        {
            "id": "event_123",
            "event": "connection.activated",
            "created_at": "2026-02-17T00:00:00.000Z",
            "data": {"id": "conn_123"},
        }
    ).encode("utf-8")
    signature = _generate_workos_signature_header(payload, webhook_secret)

    response = client.post(
        "/api/v1/sso/workos/webhooks/events",
        content=payload,
        headers={"WorkOS-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["received"] is True
    assert data["event_id"] == "event_123"
    assert data["event_type"] == "connection.activated"
    assert data["duplicate"] is False
    assert data["forwarded"] is True
    assert data["audit_entry_hash"]


def test_workos_webhook_duplicate_event_is_idempotent(client: TestClient, configure_workos) -> None:
    webhook_secret = "whsec_test_123"  # pragma: allowlist secret
    configure_workos(workos_webhook_secret=SecretStr(webhook_secret))

    payload = json.dumps(
        {
            "id": "event_duplicate_123",
            "event": "connection.activated",
            "created_at": "2026-02-17T00:00:00.000Z",
            "data": {"id": "conn_123"},
        }
    ).encode("utf-8")

    first_signature = _generate_workos_signature_header(payload, webhook_secret)
    first_response = client.post(
        "/api/v1/sso/workos/webhooks/events",
        content=payload,
        headers={"WorkOS-Signature": first_signature, "Content-Type": "application/json"},
    )
    assert first_response.status_code == 200
    assert first_response.json()["duplicate"] is False

    second_signature = _generate_workos_signature_header(payload, webhook_secret)
    second_response = client.post(
        "/api/v1/sso/workos/webhooks/events",
        content=payload,
        headers={"WorkOS-Signature": second_signature, "Content-Type": "application/json"},
    )
    assert second_response.status_code == 200
    second_data = second_response.json()
    assert second_data["duplicate"] is True
    assert second_data["forwarded"] is False
    assert second_data["audit_entry_hash"] is None


def test_workos_webhook_fail_closed_returns_503(client: TestClient, configure_workos) -> None:
    webhook_secret = "whsec_test_123"  # pragma: allowlist secret
    configure_workos(
        workos_webhook_secret=SecretStr(webhook_secret),
        workos_webhook_fail_closed=True,
    )

    payload = json.dumps(
        {
            "id": "event_forwarding_fail_123",
            "event": "connection.activated",
            "created_at": "2026-02-17T00:00:00.000Z",
            "data": {"id": "conn_123"},
        }
    ).encode("utf-8")
    signature = _generate_workos_signature_header(payload, webhook_secret)

    with patch(
        "src.core.services.api_gateway.workos_event_ingestion.AuditClient.report_validation",
        new=AsyncMock(return_value=None),
    ):
        response = client.post(
            "/api/v1/sso/workos/webhooks/events",
            content=payload,
            headers={"WorkOS-Signature": signature, "Content-Type": "application/json"},
        )

    assert response.status_code == 503
    assert "failed to forward" in response.json()["detail"].lower()


def test_workos_webhook_rejects_invalid_signature(client: TestClient, configure_workos) -> None:
    configure_workos(workos_webhook_secret=SecretStr("whsec_test_123"))  # pragma: allowlist secret

    payload = json.dumps(
        {
            "id": "event_123",
            "event": "connection.activated",
            "created_at": "2026-02-17T00:00:00.000Z",
            "data": {"id": "conn_123"},
        }
    ).encode("utf-8")

    response = client.post(
        "/api/v1/sso/workos/webhooks/events",
        content=payload,
        headers={"WorkOS-Signature": "t=123, v1=bad-signature", "Content-Type": "application/json"},
    )

    assert response.status_code == 401
    assert "signature" in response.json()["detail"].lower()


def test_workos_webhook_requires_signature_header(client: TestClient, configure_workos) -> None:
    configure_workos()

    payload = json.dumps(
        {
            "id": "event_123",
            "event": "connection.activated",
            "created_at": "2026-02-17T00:00:00.000Z",
            "data": {"id": "conn_123"},
        }
    ).encode("utf-8")

    response = client.post(
        "/api/v1/sso/workos/webhooks/events",
        content=payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert "workos-signature" in response.json()["detail"].lower()
