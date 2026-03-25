from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from fastapi import Body, Depends, FastAPI, Header, Request, Response
from fastapi.responses import ORJSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route


class CompatRequestItem(BaseModel):
    content: dict[str, str]


class CompatRequest(BaseModel):
    items: list[CompatRequestItem]
    tenant_id: str = ""


class CompatStats(BaseModel):
    total_items: int


class CompatResponse(BaseModel):
    success: bool
    tenant_id: str
    stats: CompatStats


def test_starlette_testclient_handles_basic_get() -> None:
    async def homepage(_request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    client = TestClient(Starlette(routes=[Route("/", homepage)]))
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_fastapi_testclient_persists_cookies_between_requests() -> None:
    app = FastAPI()

    @app.get("/login")
    async def login(response: Response) -> dict[str, bool]:
        response.set_cookie("session_id", "abc123", secure=True)
        return {"ok": True}

    @app.get("/me")
    async def me(request: Request) -> dict[str, str | None]:
        return {"session_id": request.cookies.get("session_id")}

    client = TestClient(app, base_url="https://testserver")
    client.get("/login")
    response = client.get("/me")

    assert client.cookies["session_id"] == "abc123"
    assert response.json() == {"session_id": "abc123"}


@pytest.mark.asyncio
async def test_sync_testclient_remains_usable_inside_async_tests() -> None:
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"pong": True}

    client = TestClient(app)
    response = client.get("/ping")

    assert response.status_code == 200
    assert response.json() == {"pong": True}


def test_testclient_context_manager_runs_lifespan_hooks() -> None:
    state: dict[str, bool] = {"started": False, "stopped": False}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.started = True
        state["started"] = True
        yield
        app.state.stopped = True
        state["stopped"] = True

    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert client.app.state.started is True

    assert state == {"started": True, "stopped": True}


def test_fastapi_testclient_handles_post_with_body_and_typed_response() -> None:
    app = FastAPI(default_response_class=ORJSONResponse)

    def get_tenant_id(x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID")) -> str:
        return x_tenant_id or "default-tenant"

    @app.post("/batch")
    async def batch(
        request: Request,
        payload: CompatRequest = Body(...),
        tenant_id: str = Depends(get_tenant_id),
    ) -> CompatResponse:
        del request
        return CompatResponse(
            success=True,
            tenant_id=payload.tenant_id or tenant_id,
            stats=CompatStats(total_items=len(payload.items)),
        )

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/batch",
        headers={"X-Tenant-ID": "tenant-from-header"},
        json={"items": [{"content": {"key": "value"}}]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "tenant_id": "tenant-from-header",
        "stats": {"total_items": 1},
    }
