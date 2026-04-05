"""
Integration tests for GET/POST/DELETE /api/v1/agents/{agent_id}/health* endpoints.
Constitutional Hash: 608508a9bd224290

Tests are TDD RED-first — all tests fail before api/routes/agent_health.py exists.

Uses FastAPI TestClient with mock AgentHealthStore injected via dependency override.
Auth (require_operator_role) is also overridden per test scenario.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.agent_health.models import (
    AgentHealthRecord,
    AgentHealthThresholds,
    AutonomyTier,
    HealingOverride,
    HealingTrigger,
    HealthState,
    OverrideMode,
)
from enhanced_agent_bus.agent_health.store import AgentHealthStore

CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_record(
    agent_id: str = "agent-001",
    health_state: HealthState = HealthState.HEALTHY,
    **kwargs,
) -> AgentHealthRecord:
    return AgentHealthRecord(
        agent_id=agent_id,
        health_state=health_state,
        consecutive_failure_count=kwargs.get("consecutive_failure_count", 0),
        memory_usage_pct=kwargs.get("memory_usage_pct", 42.5),
        last_error_type=kwargs.get("last_error_type", None),
        last_event_at=kwargs.get("last_event_at", datetime.now(UTC)),
        autonomy_tier=kwargs.get("autonomy_tier", AutonomyTier.ADVISORY),
        healing_override_id=kwargs.get("healing_override_id", None),
    )


def _make_override(agent_id: str = "agent-001") -> HealingOverride:
    now = datetime.now(UTC)
    return HealingOverride(
        agent_id=agent_id,
        mode=OverrideMode.SUPPRESS_HEALING,
        reason="Test override reason",
        issued_by="operator@example.com",
        issued_at=now,
        expires_at=now + timedelta(hours=2),
    )


def _build_authed_client(mock_store: AgentHealthStore) -> TestClient:
    """Client with valid operator auth and injected store."""
    from enhanced_agent_bus.api.routes.agent_health import (
        get_agent_health_store,
        require_operator_role,
        router,
    )

    app = FastAPI()
    app.include_router(router)

    async def _mock_store_dep() -> AgentHealthStore:
        return mock_store

    async def _mock_operator() -> str:
        return "test-operator"

    app.dependency_overrides[get_agent_health_store] = _mock_store_dep
    app.dependency_overrides[require_operator_role] = _mock_operator
    return TestClient(app, raise_server_exceptions=False)


def _build_unauthenticated_client(mock_store: AgentHealthStore) -> TestClient:
    """Client that raises 401 (no auth token)."""
    from enhanced_agent_bus.api.routes.agent_health import (
        get_agent_health_store,
        require_operator_role,
        router,
    )

    app = FastAPI()
    app.include_router(router)

    async def _mock_store_dep() -> AgentHealthStore:
        return mock_store

    async def _mock_unauthenticated() -> str:
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_agent_health_store] = _mock_store_dep
    app.dependency_overrides[require_operator_role] = _mock_unauthenticated
    return TestClient(app, raise_server_exceptions=False)


def _build_forbidden_client(mock_store: AgentHealthStore) -> TestClient:
    """Client that raises 403 (authenticated but missing operator role)."""
    from enhanced_agent_bus.api.routes.agent_health import (
        get_agent_health_store,
        require_operator_role,
        router,
    )

    app = FastAPI()
    app.include_router(router)

    async def _mock_store_dep() -> AgentHealthStore:
        return mock_store

    async def _mock_forbidden() -> str:
        raise HTTPException(status_code=403, detail="Insufficient role")

    app.dependency_overrides[get_agent_health_store] = _mock_store_dep
    app.dependency_overrides[require_operator_role] = _mock_forbidden
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 200 — happy path
# ---------------------------------------------------------------------------


def test_get_health_returns_200_with_all_required_fields() -> None:
    record = _make_record(
        agent_id="agent-001",
        health_state=HealthState.HEALTHY,
        consecutive_failure_count=0,
        memory_usage_pct=55.3,
        last_error_type=None,
        autonomy_tier=AutonomyTier.ADVISORY,
    )
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_health_record.return_value = record
    mock_store.get_override.return_value = None

    client = _build_authed_client(mock_store)
    response = client.get("/api/v1/agents/agent-001/health")

    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == "agent-001"
    assert body["health_state"] == "HEALTHY"
    assert body["consecutive_failure_count"] == 0
    assert body["memory_usage_pct"] == pytest.approx(55.3)
    assert body["last_error_type"] is None
    assert "last_event_at" in body
    assert body["autonomy_tier"] == "ADVISORY"
    assert body["healing_override"] is None
    assert body["constitutional_hash"] == CONSTITUTIONAL_HASH


def test_get_health_returns_200_for_quarantined_state() -> None:
    record = _make_record(
        agent_id="agent-q",
        health_state=HealthState.QUARANTINED,
        consecutive_failure_count=7,
        memory_usage_pct=91.0,
        last_error_type="RuntimeError",
        autonomy_tier=AutonomyTier.BOUNDED,
    )
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_health_record.return_value = record
    mock_store.get_override.return_value = None

    client = _build_authed_client(mock_store)
    response = client.get("/api/v1/agents/agent-q/health")

    assert response.status_code == 200
    body = response.json()
    assert body["health_state"] == "QUARANTINED"
    assert body["consecutive_failure_count"] == 7
    assert body["last_error_type"] == "RuntimeError"
    assert body["autonomy_tier"] == "BOUNDED"
    assert body["constitutional_hash"] == CONSTITUTIONAL_HASH


def test_get_health_returns_200_for_restarting_state() -> None:
    record = _make_record(
        agent_id="agent-r",
        health_state=HealthState.RESTARTING,
        autonomy_tier=AutonomyTier.HUMAN_APPROVED,
    )
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_health_record.return_value = record
    mock_store.get_override.return_value = None

    client = _build_authed_client(mock_store)
    response = client.get("/api/v1/agents/agent-r/health")

    assert response.status_code == 200
    body = response.json()
    assert body["health_state"] == "RESTARTING"
    assert body["autonomy_tier"] == "HUMAN_APPROVED"
    assert body["constitutional_hash"] == CONSTITUTIONAL_HASH


def test_get_health_includes_healing_override_when_active() -> None:
    record = _make_record(
        agent_id="agent-001",
        healing_override_id="override-abc",
    )
    override = _make_override(agent_id="agent-001")
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_health_record.return_value = record
    mock_store.get_override.return_value = override

    client = _build_authed_client(mock_store)
    response = client.get("/api/v1/agents/agent-001/health")

    assert response.status_code == 200
    body = response.json()
    ho = body["healing_override"]
    assert ho is not None
    assert ho["override_id"] == override.override_id
    assert ho["mode"] == "SUPPRESS_HEALING"
    assert ho["issued_by"] == "operator@example.com"
    assert "issued_at" in ho
    assert "expires_at" in ho
    assert body["constitutional_hash"] == CONSTITUTIONAL_HASH


def test_get_health_constitutional_hash_present_in_every_response() -> None:
    """constitutional_hash field must equal 608508a9bd224290 in every 200 response."""
    for state in (HealthState.HEALTHY, HealthState.QUARANTINED, HealthState.RESTARTING):
        record = _make_record(health_state=state)
        mock_store = AsyncMock(spec=AgentHealthStore)
        mock_store.get_health_record.return_value = record
        mock_store.get_override.return_value = None

        client = _build_authed_client(mock_store)
        response = client.get("/api/v1/agents/agent-001/health")

        assert response.status_code == 200
        assert response.json()["constitutional_hash"] == CONSTITUTIONAL_HASH, (
            f"constitutional_hash missing or wrong for state={state}"
        )


# ---------------------------------------------------------------------------
# 404 — unknown agent (FR-007)
# ---------------------------------------------------------------------------


def test_get_health_returns_404_for_unknown_agent_id() -> None:
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_health_record.return_value = None

    client = _build_authed_client(mock_store)
    response = client.get("/api/v1/agents/nonexistent-agent-xyz/health")

    assert response.status_code == 404
    detail = response.json().get("detail", "")
    # Error message must reference the agent or say "not found"
    assert "nonexistent-agent-xyz" in detail.lower() or "not found" in detail.lower()


# ---------------------------------------------------------------------------
# 401 / 403 — auth (NFR-003)
# ---------------------------------------------------------------------------


def test_get_health_returns_401_when_jwt_token_missing() -> None:
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_health_record.return_value = _make_record()

    client = _build_unauthenticated_client(mock_store)
    response = client.get("/api/v1/agents/agent-001/health")

    assert response.status_code == 401


def test_get_health_returns_403_when_user_lacks_operator_role() -> None:
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_health_record.return_value = _make_record()

    client = _build_forbidden_client(mock_store)
    response = client.get("/api/v1/agents/agent-001/health")

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Override endpoint helpers
# ---------------------------------------------------------------------------


def _make_mock_audit_client() -> AsyncMock:
    """Return a mock audit log client that returns a chain-hash-bearing event."""
    mock = AsyncMock()
    event = MagicMock()
    event.chain_hash = "fake-chain-hash-001"
    mock.log.return_value = event
    return mock


def _build_authed_client_with_audit(
    mock_store: AgentHealthStore,
    mock_audit_client: AsyncMock | None = None,
) -> TestClient:
    """Client with valid operator auth, injected store, and injected audit log client."""
    from enhanced_agent_bus.api.routes.agent_health import (
        get_agent_health_store,
        get_audit_log_client,
        require_operator_role,
        router,
    )

    app = FastAPI()
    app.include_router(router)

    async def _mock_store_dep() -> AgentHealthStore:
        return mock_store

    _audit = mock_audit_client or _make_mock_audit_client()

    async def _mock_audit_dep():
        return _audit

    async def _mock_operator() -> str:
        return "test-operator"

    app.dependency_overrides[get_agent_health_store] = _mock_store_dep
    app.dependency_overrides[get_audit_log_client] = _mock_audit_dep
    app.dependency_overrides[require_operator_role] = _mock_operator
    return TestClient(app, raise_server_exceptions=False)


def _build_unauthenticated_client_with_audit(mock_store: AgentHealthStore) -> TestClient:
    """Client that raises 401 (no auth token), with audit dep overridden."""
    from enhanced_agent_bus.api.routes.agent_health import (
        get_agent_health_store,
        get_audit_log_client,
        require_operator_role,
        router,
    )

    app = FastAPI()
    app.include_router(router)

    async def _mock_store_dep() -> AgentHealthStore:
        return mock_store

    async def _mock_audit_dep():
        return _make_mock_audit_client()

    async def _mock_unauthenticated() -> str:
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_agent_health_store] = _mock_store_dep
    app.dependency_overrides[get_audit_log_client] = _mock_audit_dep
    app.dependency_overrides[require_operator_role] = _mock_unauthenticated
    return TestClient(app, raise_server_exceptions=False)


def _build_forbidden_client_with_audit(mock_store: AgentHealthStore) -> TestClient:
    """Client that raises 403 (insufficient role), with audit dep overridden."""
    from enhanced_agent_bus.api.routes.agent_health import (
        get_agent_health_store,
        get_audit_log_client,
        require_operator_role,
        router,
    )

    app = FastAPI()
    app.include_router(router)

    async def _mock_store_dep() -> AgentHealthStore:
        return mock_store

    async def _mock_audit_dep():
        return _make_mock_audit_client()

    async def _mock_forbidden() -> str:
        raise HTTPException(status_code=403, detail="Insufficient role")

    app.dependency_overrides[get_agent_health_store] = _mock_store_dep
    app.dependency_overrides[get_audit_log_client] = _mock_audit_dep
    app.dependency_overrides[require_operator_role] = _mock_forbidden
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# POST /api/v1/agents/{agent_id}/health/override — happy path (US-008)
# ---------------------------------------------------------------------------


def test_post_override_returns_201_with_all_required_fields() -> None:
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_override.return_value = None
    mock_store.set_override.return_value = None

    mock_audit = _make_mock_audit_client()
    client = _build_authed_client_with_audit(mock_store, mock_audit)

    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=2)
    response = client.post(
        "/api/v1/agents/agent-001/health/override",
        json={
            "mode": "SUPPRESS_HEALING",
            "reason": "Maintenance window",
            "expires_at": expires_at.isoformat(),
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert "override_id" in body
    assert body["agent_id"] == "agent-001"
    assert body["mode"] == "SUPPRESS_HEALING"
    assert body["issued_by"] == "test-operator"
    assert "issued_at" in body
    assert "expires_at" in body
    assert "audit_event_id" in body


def test_post_override_returns_201_without_expires_at() -> None:
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_override.return_value = None
    mock_store.set_override.return_value = None

    client = _build_authed_client_with_audit(mock_store)
    response = client.post(
        "/api/v1/agents/agent-001/health/override",
        json={"mode": "FORCE_RESTART", "reason": "Manual restart required"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "FORCE_RESTART"
    assert body["expires_at"] is None


# ---------------------------------------------------------------------------
# POST — 400 validation errors
# ---------------------------------------------------------------------------


def test_post_override_returns_400_for_invalid_mode() -> None:
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_override.return_value = None

    client = _build_authed_client_with_audit(mock_store)
    response = client.post(
        "/api/v1/agents/agent-001/health/override",
        json={"mode": "INVALID_MODE", "reason": "test"},
    )

    assert response.status_code == 400


def test_post_override_returns_400_for_reason_too_long() -> None:
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_override.return_value = None

    client = _build_authed_client_with_audit(mock_store)
    response = client.post(
        "/api/v1/agents/agent-001/health/override",
        json={"mode": "SUPPRESS_HEALING", "reason": "x" * 1001},
    )

    assert response.status_code == 400


def test_post_override_returns_400_for_expires_at_in_past() -> None:
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_override.return_value = None

    client = _build_authed_client_with_audit(mock_store)
    past_time = datetime.now(UTC) - timedelta(hours=1)
    response = client.post(
        "/api/v1/agents/agent-001/health/override",
        json={
            "mode": "SUPPRESS_HEALING",
            "reason": "test",
            "expires_at": past_time.isoformat(),
        },
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# POST — 409 conflict
# ---------------------------------------------------------------------------


def test_post_override_returns_409_when_active_override_exists() -> None:
    existing = _make_override(agent_id="agent-001")
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_override.return_value = existing

    client = _build_authed_client_with_audit(mock_store)
    response = client.post(
        "/api/v1/agents/agent-001/health/override",
        json={"mode": "SUPPRESS_HEALING", "reason": "Another maintenance"},
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# POST — 401 / 403 auth
# ---------------------------------------------------------------------------


def test_post_override_returns_401_when_unauthenticated() -> None:
    mock_store = AsyncMock(spec=AgentHealthStore)

    client = _build_unauthenticated_client_with_audit(mock_store)
    response = client.post(
        "/api/v1/agents/agent-001/health/override",
        json={"mode": "SUPPRESS_HEALING", "reason": "test"},
    )

    assert response.status_code == 401


def test_post_override_returns_403_when_role_insufficient() -> None:
    mock_store = AsyncMock(spec=AgentHealthStore)

    client = _build_forbidden_client_with_audit(mock_store)
    response = client.post(
        "/api/v1/agents/agent-001/health/override",
        json={"mode": "SUPPRESS_HEALING", "reason": "test"},
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST — audit log ordering (FR-009)
# ---------------------------------------------------------------------------


def test_post_override_writes_audit_log_before_storing() -> None:
    """FR-009: audit log entry must be written BEFORE the override is stored."""
    call_order: list[str] = []

    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_override.return_value = None

    async def _track_store(*args, **kwargs) -> None:
        call_order.append("store")

    mock_store.set_override.side_effect = _track_store

    mock_audit = _make_mock_audit_client()

    async def _track_audit(*args, **kwargs) -> MagicMock:
        call_order.append("audit")
        event = MagicMock()
        event.chain_hash = "fake-hash"
        return event

    mock_audit.log.side_effect = _track_audit

    client = _build_authed_client_with_audit(mock_store, mock_audit)
    response = client.post(
        "/api/v1/agents/agent-001/health/override",
        json={"mode": "SUPPRESS_HEALING", "reason": "Maintenance window"},
    )

    assert response.status_code == 201
    assert call_order[0] == "audit", "Audit log must be written BEFORE storing override"
    assert "store" in call_order


# ---------------------------------------------------------------------------
# DELETE /api/v1/agents/{agent_id}/health/override (US-008)
# ---------------------------------------------------------------------------


def test_delete_override_returns_204_and_removes_override() -> None:
    existing = _make_override(agent_id="agent-001")
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_override.return_value = existing
    mock_store.delete_override.return_value = True

    client = _build_authed_client_with_audit(mock_store)
    response = client.delete("/api/v1/agents/agent-001/health/override")

    assert response.status_code == 204
    mock_store.delete_override.assert_called_once_with("agent-001")


def test_delete_override_returns_404_when_no_active_override() -> None:
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_override.return_value = None

    client = _build_authed_client_with_audit(mock_store)
    response = client.delete("/api/v1/agents/agent-001/health/override")

    assert response.status_code == 404


def test_delete_override_returns_401_when_unauthenticated() -> None:
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_override.return_value = _make_override()

    client = _build_unauthenticated_client_with_audit(mock_store)
    response = client.delete("/api/v1/agents/agent-001/health/override")

    assert response.status_code == 401


def test_delete_override_returns_403_when_role_insufficient() -> None:
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_override.return_value = _make_override()

    client = _build_forbidden_client_with_audit(mock_store)
    response = client.delete("/api/v1/agents/agent-001/health/override")

    assert response.status_code == 403


def test_delete_override_writes_audit_log() -> None:
    """FR-009: audit log entry must be written when an override is removed."""
    existing = _make_override(agent_id="agent-001")
    mock_store = AsyncMock(spec=AgentHealthStore)
    mock_store.get_override.return_value = existing
    mock_store.delete_override.return_value = True

    mock_audit = _make_mock_audit_client()
    client = _build_authed_client_with_audit(mock_store, mock_audit)
    response = client.delete("/api/v1/agents/agent-001/health/override")

    assert response.status_code == 204
    mock_audit.log.assert_called_once()


# ---------------------------------------------------------------------------
# SC-005: SUPPRESS_HEALING override blocks HealingEngine action
# ---------------------------------------------------------------------------


async def test_sc005_suppress_healing_override_produces_no_healing_action() -> None:
    """SC-005: when a SUPPRESS_HEALING override is active, HealingEngine returns None."""
    from enhanced_agent_bus.agent_health.healing_engine import HealingEngine

    store = AsyncMock()
    store.get_override.return_value = _make_override(agent_id="agent-sc005")
    store.save_healing_action = AsyncMock(return_value=None)

    audit_client = _make_mock_audit_client()

    engine = HealingEngine(
        store=store,
        audit_log_client=audit_client,
        restarter=AsyncMock(),
        quarantine_manager=AsyncMock(),
        hitl_requestor=AsyncMock(),
        supervisor_notifier=AsyncMock(),
        thresholds=AgentHealthThresholds(),
    )

    record = _make_record(
        agent_id="agent-sc005",
        health_state=HealthState.DEGRADED,
        consecutive_failure_count=5,
        autonomy_tier=AutonomyTier.ADVISORY,
    )

    result = await engine.handle(
        agent_id="agent-sc005",
        trigger=HealingTrigger.FAILURE_LOOP,
        record=record,
    )

    assert result is None, "SUPPRESS_HEALING override must prevent any HealingAction"
