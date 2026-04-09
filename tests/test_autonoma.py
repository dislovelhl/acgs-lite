"""Integration tests for the Autonoma Environment Factory endpoint."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from acgs_lite.autonoma import (
    _SCENARIO_CACHE,
    _active_runs,
    _fingerprint,
    _parse_scenarios,
    create_autonoma_router,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIGNING_SECRET = "test-signing-secret-for-hmac-verification"
JWT_SECRET = "test-jwt-secret-for-refs-signing-0123456789"
SCENARIOS_PATH = Path(__file__).resolve().parents[3] / "autonoma" / "scenarios.md"


@pytest.fixture(autouse=True)
def _clean_caches() -> Any:
    """Clear module-level caches between tests."""
    _SCENARIO_CACHE.clear()
    _active_runs.clear()
    yield
    _SCENARIO_CACHE.clear()
    _active_runs.clear()


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure required environment variables for every test."""
    monkeypatch.setenv("AUTONOMA_SIGNING_SECRET", SIGNING_SECRET)
    monkeypatch.setenv("AUTONOMA_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("AUTONOMA_ENV_FACTORY_ENABLED", "true")


@pytest.fixture()
def client() -> TestClient:
    """Create a lightweight TestClient with only the Autonoma router."""
    app = FastAPI()
    app.include_router(create_autonoma_router(scenarios_path=SCENARIOS_PATH))
    return TestClient(app)


def _sign_body(body: str | bytes) -> str:
    """Compute HMAC-SHA256 signature for a request body."""
    if isinstance(body, str):
        body = body.encode()
    return hmac.new(SIGNING_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _post(client: TestClient, payload: dict[str, Any]) -> Any:
    """POST to the Autonoma endpoint with proper HMAC signature."""
    body = json.dumps(payload)
    sig = _sign_body(body)
    return client.post(
        "/api/autonoma",
        content=body,
        headers={
            "Content-Type": "application/json",
            "x-signature": sig,
        },
    )


# ---------------------------------------------------------------------------
# Scenario parsing tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScenarioParsing:
    def test_parse_scenarios_returns_three_scenarios(self) -> None:
        scenarios = _parse_scenarios(SCENARIOS_PATH)
        assert len(scenarios) == 3
        names = {s["name"] for s in scenarios}
        assert names == {"standard", "empty", "large"}

    def test_fingerprint_is_deterministic(self) -> None:
        scenarios = _parse_scenarios(SCENARIOS_PATH)
        standard = next(s for s in scenarios if s["name"] == "standard")
        fp1 = _fingerprint(standard)
        fp2 = _fingerprint(standard)
        assert fp1 == fp2
        assert len(fp1) == 16
        assert all(c in "0123456789abcdef" for c in fp1)

    def test_fingerprint_differs_across_scenarios(self) -> None:
        scenarios = _parse_scenarios(SCENARIOS_PATH)
        fingerprints = {_fingerprint(s) for s in scenarios}
        assert len(fingerprints) == 3


# ---------------------------------------------------------------------------
# Environment gating tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEnvironmentGating:
    def test_returns_404_when_disabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
        client: TestClient,
    ) -> None:
        monkeypatch.setenv("AUTONOMA_ENV_FACTORY_ENABLED", "false")
        resp = _post(client, {"action": "discover"})
        assert resp.status_code == 404

    def test_returns_404_when_unset(
        self,
        monkeypatch: pytest.MonkeyPatch,
        client: TestClient,
    ) -> None:
        monkeypatch.delenv("AUTONOMA_ENV_FACTORY_ENABLED", raising=False)
        resp = _post(client, {"action": "discover"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# HMAC verification tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHMACVerification:
    def test_missing_signature_returns_401(self, client: TestClient) -> None:
        resp = client.post(
            "/api/autonoma",
            content=json.dumps({"action": "discover"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    def test_wrong_signature_returns_401(self, client: TestClient) -> None:
        body = json.dumps({"action": "discover"})
        resp = client.post(
            "/api/autonoma",
            content=body,
            headers={
                "Content-Type": "application/json",
                "x-signature": "deadbeefdeadbeefdeadbeefdeadbeef",
            },
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Discover action tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDiscoverAction:
    def test_discover_returns_three_environments(self, client: TestClient) -> None:
        resp = _post(client, {"action": "discover"})
        assert resp.status_code == 200
        data = resp.json()
        assert "environments" in data
        assert len(data["environments"]) == 3

    def test_discover_environment_fields(self, client: TestClient) -> None:
        resp = _post(client, {"action": "discover"})
        data = resp.json()
        for env in data["environments"]:
            assert "name" in env
            assert "description" in env
            assert "fingerprint" in env
            assert len(env["fingerprint"]) == 16

    def test_discover_contains_standard_empty_large(self, client: TestClient) -> None:
        resp = _post(client, {"action": "discover"})
        names = {env["name"] for env in resp.json()["environments"]}
        assert names == {"standard", "empty", "large"}

    def test_discover_fingerprints_are_consistent(self, client: TestClient) -> None:
        resp1 = _post(client, {"action": "discover"})
        # Clear cache to force re-parse
        _SCENARIO_CACHE.clear()
        resp2 = _post(client, {"action": "discover"})
        fps1 = {e["name"]: e["fingerprint"] for e in resp1.json()["environments"]}
        fps2 = {e["name"]: e["fingerprint"] for e in resp2.json()["environments"]}
        assert fps1 == fps2


# ---------------------------------------------------------------------------
# Up action tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUpAction:
    def test_up_standard_returns_refs(self, client: TestClient) -> None:
        resp = _post(
            client,
            {
                "action": "up",
                "environment": "standard",
                "testRunId": "run-001",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "refs" in data
        assert "refsToken" in data
        assert "auth" in data
        assert data["refs"]["testRunId"] == "run-001"

    def test_up_standard_refs_contain_expected_ids(self, client: TestClient) -> None:
        resp = _post(
            client,
            {
                "action": "up",
                "environment": "standard",
                "testRunId": "run-002",
            },
        )
        refs = resp.json()["refs"]
        assert "SAFE-001" in refs["rule_ids"]
        assert "PRIV-001" in refs["rule_ids"]
        assert len(refs["rule_ids"]) == 10
        assert len(refs["audit_ids"]) == 8
        assert len(refs["user_ids"]) == 5
        assert len(refs["framework_ids"]) == 9

    def test_up_empty_returns_empty_refs(self, client: TestClient) -> None:
        resp = _post(
            client,
            {
                "action": "up",
                "environment": "empty",
                "testRunId": "run-003",
            },
        )
        refs = resp.json()["refs"]
        assert refs["rule_ids"] == []
        assert refs["audit_ids"] == []

    def test_up_large_returns_large_refs(self, client: TestClient) -> None:
        resp = _post(
            client,
            {
                "action": "up",
                "environment": "large",
                "testRunId": "run-004",
            },
        )
        refs = resp.json()["refs"]
        assert len(refs["rule_ids"]) == 120
        assert len(refs["audit_ids"]) == 1000

    def test_up_unknown_environment_returns_400(self, client: TestClient) -> None:
        resp = _post(
            client,
            {
                "action": "up",
                "environment": "nonexistent",
                "testRunId": "run-005",
            },
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == "UNKNOWN_ENVIRONMENT"

    def test_up_returns_valid_jwt_refs_token(self, client: TestClient) -> None:
        resp = _post(
            client,
            {
                "action": "up",
                "environment": "standard",
                "testRunId": "run-006",
            },
        )
        data = resp.json()
        decoded = jwt.decode(data["refsToken"], JWT_SECRET, algorithms=["HS256"])
        assert decoded["refs"] == data["refs"]

    def test_up_auth_contains_headers(self, client: TestClient) -> None:
        resp = _post(
            client,
            {
                "action": "up",
                "environment": "standard",
                "testRunId": "run-007",
            },
        )
        auth = resp.json()["auth"]
        assert "headers" in auth
        assert auth["headers"]["X-Test-Run-Id"] == "run-007"

    def test_up_returns_expiry(self, client: TestClient) -> None:
        resp = _post(
            client,
            {
                "action": "up",
                "environment": "standard",
                "testRunId": "run-008",
            },
        )
        assert resp.json()["expiresInSeconds"] == 7200


# ---------------------------------------------------------------------------
# Down action tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDownAction:
    def test_down_succeeds_with_valid_token(self, client: TestClient) -> None:
        # First create
        up_resp = _post(
            client,
            {
                "action": "up",
                "environment": "standard",
                "testRunId": "run-down-001",
            },
        )
        up_data = up_resp.json()

        # Then tear down
        down_resp = _post(
            client,
            {
                "action": "down",
                "testRunId": "run-down-001",
                "refs": up_data["refs"],
                "refsToken": up_data["refsToken"],
            },
        )
        assert down_resp.status_code == 200
        assert down_resp.json() == {"ok": True}

    def test_down_rejects_tampered_refs(self, client: TestClient) -> None:
        up_resp = _post(
            client,
            {
                "action": "up",
                "environment": "standard",
                "testRunId": "run-down-002",
            },
        )
        up_data = up_resp.json()

        # Tamper with refs
        tampered_refs = {**up_data["refs"], "rule_ids": ["FAKE-001"]}
        down_resp = _post(
            client,
            {
                "action": "down",
                "testRunId": "run-down-002",
                "refs": tampered_refs,
                "refsToken": up_data["refsToken"],
            },
        )
        assert down_resp.status_code == 403

    def test_down_rejects_invalid_jwt(self, client: TestClient) -> None:
        up_resp = _post(
            client,
            {
                "action": "up",
                "environment": "standard",
                "testRunId": "run-down-003",
            },
        )
        up_data = up_resp.json()

        # Use a wrong JWT
        bad_token = jwt.encode(
            {"refs": {"bad": True}},
            "wrong-secret-that-is-intentionally-long-enough-0123456789",
            algorithm="HS256",
        )
        down_resp = _post(
            client,
            {
                "action": "down",
                "testRunId": "run-down-003",
                "refs": up_data["refs"],
                "refsToken": bad_token,
            },
        )
        assert down_resp.status_code == 403

    def test_down_rejects_missing_refs(self, client: TestClient) -> None:
        """down with missing refs should return 400."""
        up_resp = _post(
            client,
            {
                "action": "up",
                "environment": "standard",
                "testRunId": "run-no-refs",
            },
        )
        up_data = up_resp.json()
        down_resp = _post(
            client,
            {
                "action": "down",
                "testRunId": "run-no-refs",
                "refsToken": up_data["refsToken"],
            },
        )
        assert down_resp.status_code == 400

    def test_down_rejects_mismatched_test_run_id(self, client: TestClient) -> None:
        """Sending a valid token with wrong testRunId must be rejected."""
        up_resp = _post(
            client,
            {
                "action": "up",
                "environment": "standard",
                "testRunId": "run-match-A",
            },
        )
        up_data = up_resp.json()

        # Use valid refs/token from run-match-A but claim testRunId is different
        down_resp = _post(
            client,
            {
                "action": "down",
                "testRunId": "run-match-B",
                "refs": up_data["refs"],
                "refsToken": up_data["refsToken"],
            },
        )
        assert down_resp.status_code == 403


# ---------------------------------------------------------------------------
# Unknown action test
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUnknownAction:
    def test_unknown_action_returns_400(self, client: TestClient) -> None:
        resp = _post(client, {"action": "reset"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == "UNKNOWN_ACTION"


# ---------------------------------------------------------------------------
# Full lifecycle test
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFullLifecycle:
    def test_discover_up_down_lifecycle(self, client: TestClient) -> None:
        """Exercise the complete discover -> up -> down flow."""
        # Step 1: discover
        discover_resp = _post(client, {"action": "discover"})
        assert discover_resp.status_code == 200
        envs = discover_resp.json()["environments"]
        scenario_name = envs[0]["name"]

        # Step 2: up
        up_resp = _post(
            client,
            {
                "action": "up",
                "environment": scenario_name,
                "testRunId": "lifecycle-001",
            },
        )
        assert up_resp.status_code == 200
        up_data = up_resp.json()
        assert up_data["refs"]["testRunId"] == "lifecycle-001"

        # Step 3: down
        down_resp = _post(
            client,
            {
                "action": "down",
                "testRunId": "lifecycle-001",
                "refs": up_data["refs"],
                "refsToken": up_data["refsToken"],
            },
        )
        assert down_resp.status_code == 200
        assert down_resp.json() == {"ok": True}

    def test_parallel_test_runs_isolated(self, client: TestClient) -> None:
        """Two concurrent test runs produce independent refs."""
        up1 = _post(
            client,
            {
                "action": "up",
                "environment": "standard",
                "testRunId": "parallel-001",
            },
        )
        up2 = _post(
            client,
            {
                "action": "up",
                "environment": "standard",
                "testRunId": "parallel-002",
            },
        )
        assert up1.status_code == 200
        assert up2.status_code == 200

        refs1 = up1.json()["refs"]
        refs2 = up2.json()["refs"]
        assert refs1["testRunId"] != refs2["testRunId"]

        # Tear down both independently
        down1 = _post(
            client,
            {
                "action": "down",
                "testRunId": "parallel-001",
                "refs": refs1,
                "refsToken": up1.json()["refsToken"],
            },
        )
        down2 = _post(
            client,
            {
                "action": "down",
                "testRunId": "parallel-002",
                "refs": refs2,
                "refsToken": up2.json()["refsToken"],
            },
        )
        assert down1.status_code == 200
        assert down2.status_code == 200
