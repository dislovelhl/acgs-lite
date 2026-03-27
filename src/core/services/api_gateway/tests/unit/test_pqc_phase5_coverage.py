"""Tests for PQC Phase 5 admin API routes (pqc_phase5.py).

Constitutional Hash: 608508a9bd224290

Covers:
    - _opa_allow: allow, deny, HTTP error, exception
    - _get_redis: success, exception
    - activate_pqc_only_mode: happy path, quorum failure, OPA deny, Redis
      unavailable, already-active, Redis write error
    - get_pqc_only_mode_status: active with meta, inactive, Redis unavailable,
      Redis read error
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Stub the missing CouncilConsensusToken model before importing pqc_phase5
# ---------------------------------------------------------------------------


class _StubCouncilConsensusToken(BaseModel):
    """Minimal stand-in for the missing phase5.models module."""

    proposal_id: str = "proposal-001"
    signature_count: int = 5
    council_size: int = 7


_phase5_models_mod = types.ModuleType("src.core.tools.pqc_migration.phase5.models")
_phase5_models_mod.CouncilConsensusToken = _StubCouncilConsensusToken  # type: ignore[attr-defined]

# Build the full package chain so Python resolves the dotted import.
for _partial in (
    "src.core.tools",
    "src.core.tools.pqc_migration",
    "src.core.tools.pqc_migration.phase5",
    "src.core.tools.pqc_migration.phase5.models",
):
    sys.modules.setdefault(_partial, types.ModuleType(_partial))

sys.modules["src.core.tools.pqc_migration.phase5.models"] = _phase5_models_mod

# Now safe to import the module under test.
from src.core.services.api_gateway.routes.pqc_phase5 import (  # noqa: E402
    PQCOnlyModeStatusResponse,
    _get_redis,
    _opa_allow,
    pqc_phase5_router,
)
from src.core.shared.security.auth import UserClaims  # noqa: E402

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_ACTIVATE_URL = "/pqc-only-mode/activate"
_STATUS_URL = "/pqc-only-mode/status"


def _make_user(**overrides: object) -> UserClaims:
    """Build a minimal UserClaims with sensible defaults."""
    defaults: dict[str, object] = {
        "sub": "user-1",
        "tenant_id": "tenant-1",
        "roles": ["platform-operator", "admin"],
        "permissions": [],
        "exp": 9999999999,
        "iat": 1000000000,
    }
    defaults.update(overrides)
    return UserClaims(**defaults)  # type: ignore[arg-type]


def _build_app(
    *,
    user: UserClaims | None = None,
    redis_client: object | None = "sentinel",
    opa_allowed: bool = True,
):
    """Return a FastAPI test app with the pqc_phase5 router wired in.

    Overrides:
        require_role  -> returns a fixed UserClaims
        _get_redis    -> returns the supplied mock (or None)
        _opa_allow    -> returns a fixed bool
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    if user is None:
        user = _make_user()

    app = FastAPI()

    # Override the role-based auth dependency for both endpoints.
    async def _fake_role_dep() -> UserClaims:
        return user  # type: ignore[return-value]

    from src.core.shared.security.auth import require_role as real_require_role

    app.include_router(pqc_phase5_router)

    # Replace all Depends(require_role(...)) overrides.
    # The router stores the original dependency callable in endpoint.dependencies.
    # We override at the app level for the two known dependencies.
    for route in app.routes:
        deps = getattr(route, "dependant", None)
        if deps is None:
            continue
        for dep in getattr(deps, "dependencies", []):
            if dep.call is not None:
                app.dependency_overrides[dep.call] = _fake_role_dep

    # Override _get_redis at module level.
    mock_redis: AsyncMock | None = None
    if redis_client != "sentinel":
        mock_redis = redis_client  # type: ignore[assignment]

    async def _fake_get_redis():
        return mock_redis

    # Override _opa_allow at module level.
    async def _fake_opa_allow(user, proposal_id, consensus_token):
        return opa_allowed

    return app, TestClient(app), _fake_get_redis, _fake_opa_allow


def _valid_payload(**overrides: object) -> dict:
    """Return a valid activate request body."""
    base = {
        "operator_id": "op-1",
        "reason": "Transition to PQC-only enforcement",
        "consensus_token": {
            "proposal_id": "proposal-001",
            "signature_count": 5,
            "council_size": 7,
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Unit tests for _opa_allow
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOpaAllow:
    """Tests for the _opa_allow helper."""

    @pytest.mark.asyncio
    async def test_opa_allow_returns_true(self):
        """OPA returns 200 with result=True."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": True}

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            result = await _opa_allow(
                _make_user(),
                "proposal-001",
                _StubCouncilConsensusToken(),
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_opa_allow_returns_false_on_deny(self):
        """OPA returns 200 with result=False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": False}

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            result = await _opa_allow(
                _make_user(),
                "proposal-001",
                _StubCouncilConsensusToken(),
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_opa_allow_returns_false_on_non_200(self):
        """OPA returns non-200 — should deny (fail-closed)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            result = await _opa_allow(
                _make_user(),
                "proposal-001",
                _StubCouncilConsensusToken(),
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_opa_allow_returns_false_on_exception(self):
        """Network exception — should deny (fail-closed)."""
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(side_effect=ConnectionError("down"))
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            result = await _opa_allow(
                _make_user(),
                "proposal-001",
                _StubCouncilConsensusToken(),
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_opa_allow_missing_result_key(self):
        """OPA returns 200 but no 'result' key — should deny."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            result = await _opa_allow(
                _make_user(),
                "proposal-001",
                _StubCouncilConsensusToken(),
            )
        assert result is False


# ---------------------------------------------------------------------------
# Unit tests for _get_redis
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetRedis:
    """Tests for the _get_redis helper."""

    @pytest.mark.asyncio
    async def test_get_redis_returns_client(self):
        """Happy path: returns an aioredis client."""
        mock_client = MagicMock()
        with patch("redis.asyncio.from_url", return_value=mock_client):
            result = await _get_redis()
        assert result is mock_client

    @pytest.mark.asyncio
    async def test_get_redis_returns_none_on_exception(self):
        """Exception during from_url returns None (graceful degradation)."""
        with patch("redis.asyncio.from_url", side_effect=Exception("bad url")):
            result = await _get_redis()
        assert result is None


# ---------------------------------------------------------------------------
# Integration-style tests for POST /activate
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestActivatePqcOnlyMode:
    """Tests for the activate_pqc_only_mode endpoint."""

    def test_happy_path(self):
        """Successful activation: quorum OK, OPA allows, Redis writes succeed."""
        mock_rc = AsyncMock()
        mock_rc.get = AsyncMock(return_value=None)
        mock_rc.set = AsyncMock()
        mock_rc.hset = AsyncMock()
        mock_rc.__aenter__ = AsyncMock(return_value=mock_rc)
        mock_rc.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._get_redis",
                new=AsyncMock(return_value=mock_rc),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._opa_allow",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5.require_role",
                return_value=lambda: _make_user(),
            ),
        ):
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(pqc_phase5_router)
            # Override the dependency for require_role("platform-operator")
            for route in app.routes:
                dependant = getattr(route, "dependant", None)
                if dependant is None:
                    continue
                for dep in getattr(dependant, "dependencies", []):
                    if dep.call is not None:
                        app.dependency_overrides[dep.call] = lambda: _make_user()

            client = TestClient(app)
            resp = client.post(_ACTIVATE_URL, json=_valid_payload())

        assert resp.status_code == 200
        body = resp.json()
        assert body["pqc_only_mode"] is True
        assert body["activated_by"] == "op-1"
        assert body["activation_timestamp"] is not None
        assert body["audit_event_id"] is not None

    def test_quorum_failure(self):
        """Fewer signatures than the 2/3 quorum requirement -> 403."""
        payload = _valid_payload(
            consensus_token={
                "proposal_id": "p-1",
                "signature_count": 2,
                "council_size": 7,
            }
        )

        with (
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._opa_allow",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._get_redis",
                new=AsyncMock(return_value=MagicMock()),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5.require_role",
                return_value=lambda: _make_user(),
            ),
        ):
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(pqc_phase5_router)
            for route in app.routes:
                dependant = getattr(route, "dependant", None)
                if dependant is None:
                    continue
                for dep in getattr(dependant, "dependencies", []):
                    if dep.call is not None:
                        app.dependency_overrides[dep.call] = lambda: _make_user()

            client = TestClient(app)
            resp = client.post(_ACTIVATE_URL, json=payload)

        assert resp.status_code == 403
        assert "Insufficient council signatures" in resp.json()["detail"]

    def test_opa_deny(self):
        """OPA policy denies activation -> 403."""
        with (
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._opa_allow",
                new=AsyncMock(return_value=False),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._get_redis",
                new=AsyncMock(return_value=MagicMock()),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5.require_role",
                return_value=lambda: _make_user(),
            ),
        ):
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(pqc_phase5_router)
            for route in app.routes:
                dependant = getattr(route, "dependant", None)
                if dependant is None:
                    continue
                for dep in getattr(dependant, "dependencies", []):
                    if dep.call is not None:
                        app.dependency_overrides[dep.call] = lambda: _make_user()

            client = TestClient(app)
            resp = client.post(_ACTIVATE_URL, json=_valid_payload())

        assert resp.status_code == 403
        assert "OPA policy denied" in resp.json()["detail"]

    def test_redis_unavailable(self):
        """_get_redis returns None -> 503."""
        with (
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._opa_allow",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._get_redis",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5.require_role",
                return_value=lambda: _make_user(),
            ),
        ):
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(pqc_phase5_router)
            for route in app.routes:
                dependant = getattr(route, "dependant", None)
                if dependant is None:
                    continue
                for dep in getattr(dependant, "dependencies", []):
                    if dep.call is not None:
                        app.dependency_overrides[dep.call] = lambda: _make_user()

            client = TestClient(app)
            resp = client.post(_ACTIVATE_URL, json=_valid_payload())

        assert resp.status_code == 503
        assert "Redis unavailable" in resp.json()["detail"]

    def test_already_active(self):
        """PQC_ONLY_MODE already active in Redis -> 400."""
        mock_rc = AsyncMock()
        mock_rc.get = AsyncMock(return_value="true")
        mock_rc.__aenter__ = AsyncMock(return_value=mock_rc)
        mock_rc.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._opa_allow",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._get_redis",
                new=AsyncMock(return_value=mock_rc),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5.require_role",
                return_value=lambda: _make_user(),
            ),
        ):
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(pqc_phase5_router)
            for route in app.routes:
                dependant = getattr(route, "dependant", None)
                if dependant is None:
                    continue
                for dep in getattr(dependant, "dependencies", []):
                    if dep.call is not None:
                        app.dependency_overrides[dep.call] = lambda: _make_user()

            client = TestClient(app)
            resp = client.post(_ACTIVATE_URL, json=_valid_payload())

        assert resp.status_code == 400
        assert "already active" in resp.json()["detail"]

    def test_redis_write_error(self):
        """Redis set/hset raises during activation -> 500."""
        mock_rc = AsyncMock()
        mock_rc.get = AsyncMock(return_value=None)
        mock_rc.set = AsyncMock(side_effect=ConnectionError("write failed"))
        mock_rc.__aenter__ = AsyncMock(return_value=mock_rc)
        mock_rc.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._opa_allow",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._get_redis",
                new=AsyncMock(return_value=mock_rc),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5.require_role",
                return_value=lambda: _make_user(),
            ),
        ):
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(pqc_phase5_router)
            for route in app.routes:
                dependant = getattr(route, "dependant", None)
                if dependant is None:
                    continue
                for dep in getattr(dependant, "dependencies", []):
                    if dep.call is not None:
                        app.dependency_overrides[dep.call] = lambda: _make_user()

            client = TestClient(app)
            resp = client.post(_ACTIVATE_URL, json=_valid_payload())

        assert resp.status_code == 500
        assert "Failed to activate" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Integration-style tests for GET /status
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetPqcOnlyModeStatus:
    """Tests for the get_pqc_only_mode_status endpoint."""

    def test_active_with_meta(self):
        """PQC-only mode is active; Redis returns metadata."""
        mock_rc = AsyncMock()
        mock_rc.get = AsyncMock(return_value="true")
        mock_rc.hgetall = AsyncMock(
            return_value={
                "activation_timestamp": "2025-01-01T00:00:00+00:00",
                "activated_by": "op-1",
                "audit_event_id": "evt-123",
            }
        )
        mock_rc.__aenter__ = AsyncMock(return_value=mock_rc)
        mock_rc.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._get_redis",
                new=AsyncMock(return_value=mock_rc),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5.require_role",
                return_value=lambda: _make_user(),
            ),
        ):
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(pqc_phase5_router)
            for route in app.routes:
                dependant = getattr(route, "dependant", None)
                if dependant is None:
                    continue
                for dep in getattr(dependant, "dependencies", []):
                    if dep.call is not None:
                        app.dependency_overrides[dep.call] = lambda: _make_user()

            client = TestClient(app)
            resp = client.get(_STATUS_URL)

        assert resp.status_code == 200
        body = resp.json()
        assert body["pqc_only_mode"] is True
        assert body["activated_by"] == "op-1"
        assert body["activation_timestamp"] == "2025-01-01T00:00:00+00:00"
        assert body["audit_event_id"] == "evt-123"

    def test_inactive(self):
        """PQC-only mode is not active."""
        mock_rc = AsyncMock()
        mock_rc.get = AsyncMock(return_value="false")
        mock_rc.__aenter__ = AsyncMock(return_value=mock_rc)
        mock_rc.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._get_redis",
                new=AsyncMock(return_value=mock_rc),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5.require_role",
                return_value=lambda: _make_user(),
            ),
        ):
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(pqc_phase5_router)
            for route in app.routes:
                dependant = getattr(route, "dependant", None)
                if dependant is None:
                    continue
                for dep in getattr(dependant, "dependencies", []):
                    if dep.call is not None:
                        app.dependency_overrides[dep.call] = lambda: _make_user()

            client = TestClient(app)
            resp = client.get(_STATUS_URL)

        assert resp.status_code == 200
        body = resp.json()
        assert body["pqc_only_mode"] is False
        assert body["activated_by"] is None

    def test_redis_unavailable_degrades(self):
        """_get_redis returns None -> graceful degradation (200, inactive)."""
        with (
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._get_redis",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5.require_role",
                return_value=lambda: _make_user(),
            ),
        ):
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(pqc_phase5_router)
            for route in app.routes:
                dependant = getattr(route, "dependant", None)
                if dependant is None:
                    continue
                for dep in getattr(dependant, "dependencies", []):
                    if dep.call is not None:
                        app.dependency_overrides[dep.call] = lambda: _make_user()

            client = TestClient(app)
            resp = client.get(_STATUS_URL)

        assert resp.status_code == 200
        body = resp.json()
        assert body["pqc_only_mode"] is False

    def test_redis_read_error_degrades(self):
        """Redis raises during read -> graceful degradation (200, inactive)."""
        mock_rc = AsyncMock()
        mock_rc.get = AsyncMock(side_effect=ConnectionError("read fail"))
        mock_rc.__aenter__ = AsyncMock(return_value=mock_rc)
        mock_rc.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._get_redis",
                new=AsyncMock(return_value=mock_rc),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5.require_role",
                return_value=lambda: _make_user(),
            ),
        ):
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(pqc_phase5_router)
            for route in app.routes:
                dependant = getattr(route, "dependant", None)
                if dependant is None:
                    continue
                for dep in getattr(dependant, "dependencies", []):
                    if dep.call is not None:
                        app.dependency_overrides[dep.call] = lambda: _make_user()

            client = TestClient(app)
            resp = client.get(_STATUS_URL)

        assert resp.status_code == 200
        assert resp.json()["pqc_only_mode"] is False

    def test_active_no_meta(self):
        """PQC-only mode active but no metadata stored (edge case)."""
        mock_rc = AsyncMock()
        mock_rc.get = AsyncMock(return_value="true")
        mock_rc.hgetall = AsyncMock(return_value={})
        mock_rc.__aenter__ = AsyncMock(return_value=mock_rc)
        mock_rc.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._get_redis",
                new=AsyncMock(return_value=mock_rc),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5.require_role",
                return_value=lambda: _make_user(),
            ),
        ):
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(pqc_phase5_router)
            for route in app.routes:
                dependant = getattr(route, "dependant", None)
                if dependant is None:
                    continue
                for dep in getattr(dependant, "dependencies", []):
                    if dep.call is not None:
                        app.dependency_overrides[dep.call] = lambda: _make_user()

            client = TestClient(app)
            resp = client.get(_STATUS_URL)

        assert resp.status_code == 200
        body = resp.json()
        assert body["pqc_only_mode"] is True
        assert body["activated_by"] is None
        assert body["activation_timestamp"] is None

    def test_redis_returns_none_value(self):
        """Redis key not set (returns None) -> inactive."""
        mock_rc = AsyncMock()
        mock_rc.get = AsyncMock(return_value=None)
        mock_rc.__aenter__ = AsyncMock(return_value=mock_rc)
        mock_rc.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5._get_redis",
                new=AsyncMock(return_value=mock_rc),
            ),
            patch(
                "src.core.services.api_gateway.routes.pqc_phase5.require_role",
                return_value=lambda: _make_user(),
            ),
        ):
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(pqc_phase5_router)
            for route in app.routes:
                dependant = getattr(route, "dependant", None)
                if dependant is None:
                    continue
                for dep in getattr(dependant, "dependencies", []):
                    if dep.call is not None:
                        app.dependency_overrides[dep.call] = lambda: _make_user()

            client = TestClient(app)
            resp = client.get(_STATUS_URL)

        assert resp.status_code == 200
        assert resp.json()["pqc_only_mode"] is False


# ---------------------------------------------------------------------------
# Schema / model tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResponseModels:
    """Tests for Pydantic response model defaults and serialization."""

    def test_status_response_defaults(self):
        resp = PQCOnlyModeStatusResponse(pqc_only_mode=False)
        assert resp.activation_timestamp is None
        assert resp.activated_by is None
        assert resp.audit_event_id is None

    def test_status_response_with_all_fields(self):
        resp = PQCOnlyModeStatusResponse(
            pqc_only_mode=True,
            activation_timestamp="2025-01-01T00:00:00+00:00",
            activated_by="op-1",
            audit_event_id="evt-1",
        )
        assert resp.pqc_only_mode is True
        assert resp.activated_by == "op-1"
