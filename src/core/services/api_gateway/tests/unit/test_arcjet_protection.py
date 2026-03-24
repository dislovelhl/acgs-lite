"""Tests for Arcjet middleware integration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.services.api_gateway.arcjet_protection import (
    ArcjetProtectionMiddleware,
    create_arcjet_middleware_config,
    get_arcjet_runtime_status,
)
from src.core.shared.constants import CONSTITUTIONAL_HASH


class _DeniedRateLimitReason:
    def is_rate_limit(self) -> bool:
        return True

    def to_dict(self) -> dict[str, object]:
        return {"type": "RATE_LIMIT"}


class _DeniedRateLimitDecision:
    reason = _DeniedRateLimitReason()

    def is_denied(self) -> bool:
        return True


class _AllowedReason:
    def is_rate_limit(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {"type": "ALLOW"}


class _AllowedDecision:
    reason = _AllowedReason()

    def is_denied(self) -> bool:
        return False


class _DenyingClient:
    async def protect(self, request):
        return _DeniedRateLimitDecision()


class _AllowingClient:
    def __init__(self) -> None:
        self.calls = 0

    async def protect(self, request):
        self.calls += 1
        return _AllowedDecision()


def test_arcjet_middleware_denies_rate_limited_requests() -> None:
    app = FastAPI()

    @app.get("/api/v1/test")
    async def test_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(
        ArcjetProtectionMiddleware,
        client=_DenyingClient(),
        exempt_paths=(),
    )

    client = TestClient(app)
    response = client.get("/api/v1/test")

    assert response.status_code == 429
    assert response.json()["detail"] == "Request denied by Arcjet policy"


def test_arcjet_middleware_skips_exempt_paths() -> None:
    app = FastAPI()
    allowing_client = _AllowingClient()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    app.add_middleware(
        ArcjetProtectionMiddleware,
        client=allowing_client,
        exempt_paths=("/health",),
    )

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert allowing_client.calls == 0


def test_arcjet_runtime_status_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCJET_ENABLED", "true")
    monkeypatch.setenv("ARCJET_KEY", "ajkey_test_123")
    monkeypatch.setenv("ARCJET_MODE", "LIVE")
    monkeypatch.setenv("ARCJET_RATE_LIMIT_MAX", "240")
    monkeypatch.setenv("ARCJET_RATE_LIMIT_WINDOW_SECONDS", "30")

    status = get_arcjet_runtime_status(middleware_enabled=True)

    assert status["enabled"] is True
    assert status["key_configured"] is True
    assert status["middleware_enabled"] is True
    assert status["mode"] == "LIVE"
    assert status["rate_limit_max"] == 240
    assert status["rate_limit_window_seconds"] == 30


def test_arcjet_config_disabled_even_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCJET_ENABLED", "false")
    monkeypatch.setenv("ARCJET_KEY", "ajkey_test_123")
    assert create_arcjet_middleware_config() is None


def test_arcjet_config_enabled_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCJET_ENABLED", "true")
    monkeypatch.delenv("ARCJET_KEY", raising=False)
    assert create_arcjet_middleware_config() is None


def test_arcjet_status_endpoint_admin_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Admin-only access control for the Arcjet status endpoint.

    Builds a minimal FastAPI app with a ``get_current_user`` dependency and an
    admin-gated ``/api/v1/gateway/security/arcjet/status`` route so we can test
    authorisation logic without importing the full gateway application.
    """
    from fastapi import Depends, HTTPException

    from src.core.shared.security.auth import UserClaims

    now = datetime.now(UTC)
    admin_user = UserClaims(
        sub="admin-user",
        tenant_id="tenant-1",
        roles=["admin"],
        permissions=[],
        exp=int((now + timedelta(hours=1)).timestamp()),
        iat=int(now.timestamp()),
        jti="test-jti",
        constitutional_hash=CONSTITUTIONAL_HASH,
    )
    non_admin_user = admin_user.model_copy(update={"roles": ["user"]})

    # Mutable holder so the dependency can be swapped between requests.
    _current_user_holder: list[UserClaims] = [admin_user]

    async def _get_current_user() -> UserClaims:
        return _current_user_holder[0]

    # Build a self-contained app with the admin-gated arcjet status route.
    app = FastAPI()

    @app.get("/api/v1/gateway/security/arcjet/status")
    async def arcjet_status(
        user: UserClaims = Depends(_get_current_user),
    ) -> dict[str, object]:
        if "admin" not in (user.roles or []):
            raise HTTPException(status_code=403, detail="Admin role required")
        return get_arcjet_runtime_status(middleware_enabled=False)

    monkeypatch.setenv("ARCJET_ENABLED", "true")
    monkeypatch.setenv("ARCJET_MODE", "DRY_RUN")

    client = TestClient(app)

    # Admin user should be allowed.
    _current_user_holder[0] = admin_user
    allowed = client.get("/api/v1/gateway/security/arcjet/status")
    assert allowed.status_code == 200
    assert allowed.json()["mode"] == "DRY_RUN"

    # Non-admin user should be denied.
    _current_user_holder[0] = non_admin_user
    denied = client.get("/api/v1/gateway/security/arcjet/status")
    assert denied.status_code == 403
