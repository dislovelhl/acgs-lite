"""Tests for health readiness/liveness endpoints."""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.api.routes.health import router


def _build_app(agent_bus_ready: bool = True) -> FastAPI:
    app = FastAPI()
    if agent_bus_ready:
        app.state.agent_bus = object()
    app.include_router(router)
    return app


async def test_liveness_probe_exposes_constitutional_hash() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_build_app()),
        base_url="http://test",
    ) as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "alive"
    assert payload["constitutional_hash"] == CONSTITUTIONAL_HASH


async def test_readiness_probe_fails_on_constitutional_hash_mismatch(monkeypatch) -> None:
    monkeypatch.setenv("CONSTITUTIONAL_HASH", "deadbeefdeadbeef")
    async with AsyncClient(
        transport=ASGITransport(app=_build_app(agent_bus_ready=True)),
        base_url="http://test",
    ) as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["ready"] is False
    assert payload["checks"]["constitutional_hash_runtime"] == "down"


async def test_readiness_probe_fails_when_agent_bus_missing() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_build_app(agent_bus_ready=False)),
        base_url="http://test",
    ) as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["ready"] is False
    assert payload["checks"]["agent_bus"] == "down"


async def test_readiness_probe_fails_on_probe_header_mismatch() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_build_app(agent_bus_ready=True)),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/health/ready",
            headers={"X-Constitutional-Hash": "badbadbadbadbadb"},
        )
    assert response.status_code == 503
    payload = response.json()
    assert payload["ready"] is False
    assert payload["checks"]["constitutional_hash_probe_header"] == "down"
