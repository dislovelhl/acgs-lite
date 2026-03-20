"""Tests for acgs_lite.integrations.a2a coverage gaps."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from acgs_lite.constitution import Constitution
from acgs_lite.integrations.a2a import A2AGovernedClient, create_a2a_app


class TestA2AGovernedClient:
    def test_init(self) -> None:
        client = A2AGovernedClient("http://localhost:9000")
        assert client.agent_url == "http://localhost:9000"
        assert client.timeout == 30.0

    def test_init_strips_trailing_slash(self) -> None:
        client = A2AGovernedClient("http://localhost:9000/")
        assert client.agent_url == "http://localhost:9000"

    def test_init_custom_timeout(self) -> None:
        client = A2AGovernedClient("http://localhost:9000", timeout=10.0)
        assert client.timeout == 10.0


class TestCreateA2AApp:
    def test_creates_app(self) -> None:
        app = create_a2a_app()
        assert app is not None
        # Should have routes
        assert len(app.routes) >= 2

    def test_creates_app_with_constitution(self) -> None:
        c = Constitution.default()
        app = create_a2a_app(constitution=c)
        assert app is not None

    def test_agent_card_endpoint(self) -> None:
        from starlette.testclient import TestClient

        app = create_a2a_app()
        client = TestClient(app)
        resp = client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        card = resp.json()
        assert "name" in card
        assert "skills" in card
        assert len(card["skills"]) == 3

    def test_validate_action(self) -> None:
        from starlette.testclient import TestClient

        app = create_a2a_app()
        client = TestClient(app)
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "id": "test-1",
            "params": {
                "id": "task-1",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Validate: test action"}],
                },
            },
        }
        resp = client.post("/", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["jsonrpc"] == "2.0"
        assert "result" in data

    def test_audit_query(self) -> None:
        from starlette.testclient import TestClient

        app = create_a2a_app()
        client = TestClient(app)
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "id": "test-2",
            "params": {
                "id": "task-2",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Show me the audit trail"}],
                },
            },
        }
        resp = client.post("/", json=payload)
        assert resp.status_code == 200
        result = resp.json()["result"]["result"]
        assert "audit_log" in result
        assert "chain_valid" in result

    def test_status_query(self) -> None:
        from starlette.testclient import TestClient

        app = create_a2a_app()
        client = TestClient(app)
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "id": "test-3",
            "params": {
                "id": "task-3",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "What are the rules and status?"}],
                },
            },
        }
        resp = client.post("/", json=payload)
        assert resp.status_code == 200
        result = resp.json()["result"]["result"]
        assert "constitution_name" in result
        assert "rules_count" in result

    def test_unknown_method(self) -> None:
        from starlette.testclient import TestClient

        app = create_a2a_app()
        client = TestClient(app)
        payload = {
            "jsonrpc": "2.0",
            "method": "unknown/method",
            "id": "test-4",
            "params": {},
        }
        resp = client.post("/", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32601

    def test_empty_parts(self) -> None:
        from starlette.testclient import TestClient

        app = create_a2a_app()
        client = TestClient(app)
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "id": "test-5",
            "params": {
                "id": "task-5",
                "message": {"role": "user", "parts": []},
            },
        }
        resp = client.post("/", json=payload)
        assert resp.status_code == 200
