"""Tests for Telegram webhook governance integration."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from acgs_lite import Constitution, Rule, Severity
from acgs_lite.engine import GovernanceEngine
from acgs_lite.integrations.telegram_webhook import create_telegram_webhook_router
from acgs_lite.server import create_governance_app


def _make_engine() -> GovernanceEngine:
    constitution = Constitution.from_rules(
        [
            Rule(
                id="TG-001",
                text="Block restricted Telegram content",
                severity=Severity.HIGH,
                keywords=["forbidden"],
            )
        ]
    )
    return GovernanceEngine(constitution, strict=False, audit_mode="fast")


def _make_update(text: str) -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 99,
            "chat": {"id": 123456, "type": "private"},
            "text": text,
        },
    }


@pytest.mark.unit
def test_telegram_webhook_allows_safe_message() -> None:
    app = FastAPI()
    app.include_router(
        create_telegram_webhook_router(
            engine_getter=lambda: _make_engine(),
            webhook_path_secret="path-secret",
        )
    )
    client = TestClient(app)

    response = client.post("/telegram/webhook/path-secret", json=_make_update("hello there"))

    assert response.status_code == 200
    assert response.json() == {
        "method": "sendMessage",
        "chat_id": 123456,
        "text": "ACGS Agent: governance cleared your message. Send the next step when ready.",
    }


@pytest.mark.unit
def test_telegram_webhook_blocks_disallowed_message() -> None:
    app = FastAPI()
    app.include_router(
        create_telegram_webhook_router(
            engine_getter=lambda: _make_engine(),
            webhook_path_secret="path-secret",
        )
    )
    client = TestClient(app)

    response = client.post(
        "/telegram/webhook/path-secret",
        json=_make_update("this is forbidden content"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "method": "sendMessage",
        "chat_id": 123456,
        "text": "ACGS Agent: your message was blocked by constitutional governance and was not processed.",
    }


@pytest.mark.unit
def test_telegram_webhook_enforces_secret_token() -> None:
    app = FastAPI()
    app.include_router(
        create_telegram_webhook_router(
            engine_getter=lambda: _make_engine(),
            webhook_path_secret="path-secret",
            secret_token="expected-secret-token",
        )
    )
    client = TestClient(app)

    missing = client.post("/telegram/webhook/path-secret", json=_make_update("hello there"))
    wrong = client.post(
        "/telegram/webhook/path-secret",
        json=_make_update("hello there"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    correct = client.post(
        "/telegram/webhook/path-secret",
        json=_make_update("hello there"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "expected-secret-token"},
    )

    assert missing.status_code == 401
    assert missing.json() == {"detail": "Invalid Telegram secret token"}
    assert wrong.status_code == 401
    assert wrong.json() == {"detail": "Invalid Telegram secret token"}
    assert correct.status_code == 200


@pytest.mark.unit
def test_create_governance_app_mounts_telegram_router(tmp_path: Any) -> None:
    app = create_governance_app(
        audit_db_path=tmp_path / "audit.db",
        include_telegram=True,
        telegram_webhook_path_secret="mounted-secret",
        telegram_secret_token="mounted-header-token",
    )

    webhook_paths = {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/telegram/webhook/")
    }

    assert webhook_paths == {"/telegram/webhook/mounted-secret"}
