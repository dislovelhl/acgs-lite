"""Regression tests for create_governance_app api_key / X-API-Key auth."""

from __future__ import annotations

import logging

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from acgs_lite.server import create_governance_app


class TestApiKeyEnforcement:
    def test_no_key_allows_requests_but_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING, logger="acgs_lite.server")
        # Explicit require_auth=None restores v2.9.x fail-open behaviour.
        app = create_governance_app(require_auth=None)
        client = TestClient(app)
        # /health is always public
        assert client.get("/health").status_code == 200
        # /rules is also public when no key configured (back-compat)
        assert client.get("/rules").status_code == 200
        assert any("WITHOUT API-key authentication" in r.message for r in caplog.records)

    def test_key_required_returns_401_without_header(self) -> None:
        app = create_governance_app(api_key="top-secret")
        client = TestClient(app)
        resp = client.get("/rules")
        assert resp.status_code == 401

    def test_key_accepts_correct_header(self) -> None:
        app = create_governance_app(api_key="top-secret")
        client = TestClient(app)
        resp = client.get("/rules", headers={"X-API-Key": "top-secret"})
        assert resp.status_code == 200

    def test_wrong_key_returns_401(self) -> None:
        app = create_governance_app(api_key="top-secret")
        client = TestClient(app)
        resp = client.get("/rules", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_health_endpoint_never_requires_auth(self) -> None:
        app = create_governance_app(api_key="top-secret")
        client = TestClient(app)
        # Health stays public so load-balancer probes keep working.
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_mutation_endpoints_require_auth(self) -> None:
        app = create_governance_app(api_key="top-secret")
        client = TestClient(app)
        assert client.post("/validate", json={"action": "hi"}).status_code == 401
        assert client.post("/rules", json={"id": "r1"}).status_code == 401
        assert client.put("/rules/r1", json={}).status_code == 401
        assert client.delete("/rules/r1").status_code == 401

    def test_audit_endpoints_require_auth(self) -> None:
        app = create_governance_app(api_key="top-secret")
        client = TestClient(app)
        assert client.get("/audit/entries").status_code == 401
        assert client.get("/audit/chain").status_code == 401
        assert client.get("/audit/count").status_code == 401

    def test_require_auth_true_without_key_raises(self) -> None:
        with pytest.raises(ValueError, match="require_auth=True"):
            create_governance_app(require_auth=True)

    def test_default_fails_closed_without_key(self) -> None:
        # v2.10.0: require_auth defaults to True, so calling without a key raises.
        with pytest.raises(ValueError, match="require_auth=True"):
            create_governance_app()

    def test_env_var_is_used_when_param_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ACGS_API_KEY", "env-secret")
        app = create_governance_app()
        client = TestClient(app)
        assert client.get("/rules").status_code == 401
        assert client.get("/rules", headers={"X-API-Key": "env-secret"}).status_code == 200

    def test_require_auth_false_silences_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING, logger="acgs_lite.server")
        create_governance_app(require_auth=False)
        assert not any("WITHOUT API-key authentication" in r.message for r in caplog.records)
