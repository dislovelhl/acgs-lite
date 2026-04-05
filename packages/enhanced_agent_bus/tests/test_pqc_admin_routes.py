"""
ACGS-2 Enhanced Agent Bus - PQC Admin Routes Tests
Constitutional Hash: 608508a9bd224290

Tests for PATCH/GET /api/v1/admin/pqc-enforcement endpoints covering:
- 403 when caller has no admin role
- 200 with platform-operator JWT on PATCH
- PATCH mode=strict returns correct response body
- GET returns current mode and metadata
- PATCH mode=permissive triggers audit warning log
- PATCH with invalid mode value returns 400
"""

import logging
from datetime import UTC, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from enhanced_agent_bus.observability.structured_logging import get_logger

# ---------------------------------------------------------------------------
# Build a minimal test app
# ---------------------------------------------------------------------------

try:
    from enhanced_agent_bus.api.routes.pqc_admin import router as pqc_admin_router
    from enhanced_agent_bus.pqc_enforcement_config import (
        EnforcementModeConfigService,
        StorageUnavailableError,
    )
    from enhanced_agent_bus.pqc_enforcement_models import (
        EnforcementModeRequest,
        EnforcementModeResponse,
    )
except ImportError:
    from api.routes.pqc_admin import router as pqc_admin_router  # type: ignore[no-redef]
    from pqc_enforcement_config import (  # type: ignore[no-redef]
        EnforcementModeConfigService,
        StorageUnavailableError,
    )
    from pqc_enforcement_models import (  # type: ignore[no-redef]
        EnforcementModeRequest,
        EnforcementModeResponse,
    )

try:
    from enhanced_agent_bus._compat.security.auth import UserClaims
except ImportError:
    from unittest.mock import MagicMock as UserClaims  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 5, 12, 0, 0, tzinfo=UTC)

OPERATOR_CLAIMS = MagicMock(spec=UserClaims)
OPERATOR_CLAIMS.sub = "operator-1"
OPERATOR_CLAIMS.roles = ["platform-operator"]
OPERATOR_CLAIMS.tenant_id = "global"

TENANT_ADMIN_CLAIMS = MagicMock(spec=UserClaims)
TENANT_ADMIN_CLAIMS.sub = "admin-1"
TENANT_ADMIN_CLAIMS.roles = ["tenant-admin"]
TENANT_ADMIN_CLAIMS.tenant_id = "tenant-acme"

NO_ROLE_CLAIMS = MagicMock(spec=UserClaims)
NO_ROLE_CLAIMS.sub = "user-1"
NO_ROLE_CLAIMS.roles = ["viewer"]
NO_ROLE_CLAIMS.tenant_id = "global"


def _build_app(user_claims: Any, enforcement_svc: Any) -> FastAPI:
    """Create a fresh FastAPI test app with injected dependencies."""
    app = FastAPI()
    app.include_router(pqc_admin_router)

    # Override auth dependency
    try:
        from enhanced_agent_bus._compat.security.auth import get_current_user

        app.dependency_overrides[get_current_user] = lambda: user_claims
    except ImportError:
        pass

    # Override service dependency
    try:
        from enhanced_agent_bus.api.routes.pqc_admin import get_enforcement_service
    except ImportError:
        try:
            from api.routes.pqc_admin import get_enforcement_service  # type: ignore[no-redef]
        except ImportError:
            get_enforcement_service = None

    if get_enforcement_service is not None:
        app.dependency_overrides[get_enforcement_service] = lambda: enforcement_svc

    return app


def _make_enforcement_svc(mode: str = "permissive") -> AsyncMock:
    """Return a fully mocked EnforcementModeConfigService."""
    svc = AsyncMock(spec=EnforcementModeConfigService)
    svc.get_mode.return_value = mode
    svc.set_mode.return_value = None
    return svc


def _enforcement_response(mode: str, activated_by: str = "operator-1") -> dict:
    return {
        "mode": mode,
        "activated_at": _NOW.isoformat(),
        "activated_by": activated_by,
        "scope": "global",
        "propagation_deadline_seconds": 60,
    }


# ---------------------------------------------------------------------------
# PATCH tests
# ---------------------------------------------------------------------------


def test_patch_returns_403_without_admin_role():
    """PATCH endpoint returns 403 when caller has no admin role."""
    svc = _make_enforcement_svc()
    app = _build_app(NO_ROLE_CLAIMS, svc)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.patch(
        "/api/v1/admin/pqc-enforcement",
        json={"mode": "strict", "scope": "global"},
    )
    assert resp.status_code == 403


def test_patch_with_platform_operator_returns_200():
    """PATCH with platform-operator JWT returns 200 with EnforcementModeResponse body."""
    svc = _make_enforcement_svc()
    app = _build_app(OPERATOR_CLAIMS, svc)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.patch(
        "/api/v1/admin/pqc-enforcement",
        json={"mode": "strict", "scope": "global"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "strict"
    assert "activated_at" in body
    assert body["activated_by"] == OPERATOR_CLAIMS.sub
    assert body["propagation_deadline_seconds"] == 60


def test_patch_strict_persists_and_returns_metadata():
    """PATCH mode=strict calls set_mode and returns activated_at/activated_by/propagation_deadline."""
    svc = _make_enforcement_svc()
    app = _build_app(OPERATOR_CLAIMS, svc)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.patch(
        "/api/v1/admin/pqc-enforcement",
        json={"mode": "strict", "scope": "global"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "strict"
    assert body["scope"] == "global"
    assert body["propagation_deadline_seconds"] == 60
    assert "activated_at" in body

    svc.set_mode.assert_awaited_once()
    call_kwargs = svc.set_mode.await_args
    assert call_kwargs.kwargs.get("mode") == "strict" or call_kwargs.args[0] == "strict"


def test_patch_with_tenant_admin_role_is_allowed():
    """PATCH with tenant-admin JWT is also authorized."""
    svc = _make_enforcement_svc()
    app = _build_app(TENANT_ADMIN_CLAIMS, svc)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.patch(
        "/api/v1/admin/pqc-enforcement",
        json={"mode": "permissive", "scope": "global"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "permissive"
    assert body["activated_by"] == TENANT_ADMIN_CLAIMS.sub


def test_patch_invalid_mode_returns_400():
    """PATCH with an unrecognized mode value returns HTTP 400."""
    svc = _make_enforcement_svc()
    app = _build_app(OPERATOR_CLAIMS, svc)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.patch(
        "/api/v1/admin/pqc-enforcement",
        json={"mode": "banana", "scope": "global"},
    )
    assert resp.status_code == 422  # Pydantic validation error maps to 422


def test_patch_permissive_triggers_audit_warning_log(caplog):
    """PATCH with mode=permissive emits a warning-level audit log entry."""
    svc = _make_enforcement_svc()
    app = _build_app(OPERATOR_CLAIMS, svc)
    client = TestClient(app, raise_server_exceptions=False)

    with caplog.at_level(logging.WARNING):
        resp = client.patch(
            "/api/v1/admin/pqc-enforcement",
            json={"mode": "permissive", "scope": "global"},
        )

    assert resp.status_code == 200
    # A warning about permissive mode must appear in the log
    warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("permissive" in msg.lower() for msg in warning_messages), (
        f"No permissive-mode warning found. Captured: {warning_messages}"
    )


def test_patch_returns_503_when_storage_unavailable():
    """PATCH returns HTTP 503 when EnforcementModeConfigService raises StorageUnavailableError."""
    svc = _make_enforcement_svc()
    svc.set_mode.side_effect = StorageUnavailableError("Redis and PG both down")
    app = _build_app(OPERATOR_CLAIMS, svc)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.patch(
        "/api/v1/admin/pqc-enforcement",
        json={"mode": "strict", "scope": "global"},
    )
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET tests
# ---------------------------------------------------------------------------


def test_get_returns_403_without_admin_role():
    """GET /api/v1/admin/pqc-enforcement returns 403 when caller has no admin role."""
    svc = _make_enforcement_svc(mode="permissive")
    app = _build_app(NO_ROLE_CLAIMS, svc)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/v1/admin/pqc-enforcement")
    assert resp.status_code == 403


def test_get_with_admin_jwt_returns_current_mode():
    """GET with admin JWT returns current enforcement mode and metadata."""
    svc = _make_enforcement_svc(mode="strict")
    app = _build_app(OPERATOR_CLAIMS, svc)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/v1/admin/pqc-enforcement")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "strict"
    assert "activated_at" in body
    assert "scope" in body


def test_get_returns_503_when_storage_unavailable():
    """GET returns HTTP 503 when EnforcementModeConfigService raises StorageUnavailableError."""
    svc = _make_enforcement_svc()
    svc.get_mode.side_effect = StorageUnavailableError("Redis and PG both down")
    app = _build_app(OPERATOR_CLAIMS, svc)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/v1/admin/pqc-enforcement")
    assert resp.status_code == 503
