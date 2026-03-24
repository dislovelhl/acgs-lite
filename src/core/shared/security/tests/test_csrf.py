from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from src.core.shared.security.csrf import CSRFConfig, CSRFMiddleware


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-session-secret",  # pragma: allowlist secret
        session_cookie="acgs2_session",
        https_only=True,
    )
    app.add_middleware(
        CSRFMiddleware,
        config=CSRFConfig(
            secret="test-csrf-secret",  # pragma: allowlist secret
            session_cookie_name="acgs2_session",
            exempt_paths=("/webhooks",),
        ),
    )

    @app.get("/login")
    async def login(request: Request) -> JSONResponse:
        request.session["user"] = {"id": "user-1", "roles": ["admin"]}
        return JSONResponse({"ok": True})

    @app.post("/protected")
    async def protected() -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.post("/webhooks/events")
    async def webhook() -> JSONResponse:
        return JSONResponse({"ok": True})

    return app


def test_safe_request_sets_csrf_cookie() -> None:
    client = TestClient(_make_app(), base_url="https://testserver")

    response = client.get("/login")

    assert response.status_code == 200
    assert "acgs2_session" in client.cookies
    assert "csrf_token" in client.cookies


def test_session_post_requires_csrf_header() -> None:
    client = TestClient(_make_app(), base_url="https://testserver")
    client.get("/login")

    response = client.post("/protected")

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF token missing"


def test_session_post_accepts_matching_csrf_header() -> None:
    client = TestClient(_make_app(), base_url="https://testserver")
    client.get("/login")

    response = client.post(
        "/protected",
        headers={"X-CSRF-Token": client.cookies["csrf_token"]},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_stateless_post_skips_csrf_enforcement() -> None:
    client = TestClient(_make_app(), base_url="https://testserver")

    response = client.post("/protected")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_exempt_path_skips_csrf_enforcement() -> None:
    client = TestClient(_make_app(), base_url="https://testserver")
    client.get("/login")

    response = client.post("/webhooks/events")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_csrf_secret_required_when_only_environment_is_production(monkeypatch) -> None:
    from src.core.shared.security import csrf

    monkeypatch.setattr(csrf.settings, "env", "development")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("CSRF_SECRET", raising=False)

    with pytest.raises(OSError, match="CSRF_SECRET environment variable is required"):
        CSRFConfig().get_secret()
