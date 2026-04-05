"""Tests for PQC-only mode enforcement middleware.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from src.core.services.api_gateway.middleware.pqc_only_mode import (
    _APPROVED_PQC_ALGORITHM_STRINGS,
    _REDIS_KEY,
    PQCOnlyModeMiddleware,
)


def _build_app_with_middleware(redis_client=None):
    """Build a minimal FastAPI app wrapped with PQCOnlyModeMiddleware."""
    from fastapi import FastAPI

    app = FastAPI()

    @app.post("/test")
    async def test_endpoint():
        return {"status": "ok"}

    @app.get("/no-body")
    async def no_body_endpoint():
        return {"status": "ok"}

    app.add_middleware(PQCOnlyModeMiddleware, redis_client=redis_client)
    return app


class TestPQCOnlyModeMiddleware:
    """Test suite for PQC-only mode enforcement."""

    # -- PQC mode inactive --------------------------------------------------

    def test_passes_through_when_mode_inactive(self):
        """Requests pass through when PQC_ONLY_MODE is false."""
        app = _build_app_with_middleware()
        with patch.dict(os.environ, {"PQC_ONLY_MODE": "false"}, clear=False):
            client = TestClient(app)
            resp = client.post(
                "/test",
                json={"algorithm": "Ed25519"},
                headers={"content-type": "application/json"},
            )
            assert resp.status_code == 200

    # -- PQC mode active, classical rejected --------------------------------

    def test_rejects_classical_algorithm(self):
        """Classical algorithms are rejected when PQC_ONLY_MODE is active."""
        app = _build_app_with_middleware()
        with patch.dict(os.environ, {"PQC_ONLY_MODE": "true"}, clear=False):
            client = TestClient(app)
            resp = client.post(
                "/test",
                json={"algorithm": "Ed25519"},
                headers={"content-type": "application/json"},
            )
            assert resp.status_code == 400
            body = resp.json()
            assert body["error"] == "CLASSICAL_ALGORITHM_REJECTED"
            assert body["algorithm"] == "Ed25519"

    def test_rejects_x25519(self):
        app = _build_app_with_middleware()
        with patch.dict(os.environ, {"PQC_ONLY_MODE": "true"}, clear=False):
            client = TestClient(app)
            resp = client.post(
                "/test",
                json={"algorithm": "X25519"},
                headers={"content-type": "application/json"},
            )
            assert resp.status_code == 400

    # -- PQC mode active, approved algorithms pass --------------------------

    @pytest.mark.parametrize("algo", sorted(_APPROVED_PQC_ALGORITHM_STRINGS))
    def test_approved_pqc_algorithm_passes(self, algo):
        app = _build_app_with_middleware()
        with patch.dict(os.environ, {"PQC_ONLY_MODE": "true"}, clear=False):
            client = TestClient(app)
            resp = client.post(
                "/test",
                json={"algorithm": algo},
                headers={"content-type": "application/json"},
            )
            assert resp.status_code == 200

    # -- Fast paths ---------------------------------------------------------

    def test_non_json_content_type_passes(self):
        """Non-JSON content types skip algorithm check entirely."""
        app = _build_app_with_middleware()
        with patch.dict(os.environ, {"PQC_ONLY_MODE": "true"}, clear=False):
            client = TestClient(app)
            resp = client.post(
                "/test",
                content=b"plain text",
                headers={"content-type": "text/plain"},
            )
            # FastAPI may return 422 for validation, but not 400 from middleware
            assert resp.status_code != 400

    def test_empty_body_passes(self):
        """Requests with no body skip algorithm check."""
        app = _build_app_with_middleware()
        with patch.dict(os.environ, {"PQC_ONLY_MODE": "true"}, clear=False):
            client = TestClient(app)
            resp = client.get("/no-body")
            assert resp.status_code == 200

    def test_no_algorithm_field_passes(self):
        """JSON body without 'algorithm' field passes through."""
        app = _build_app_with_middleware()
        with patch.dict(os.environ, {"PQC_ONLY_MODE": "true"}, clear=False):
            client = TestClient(app)
            resp = client.post(
                "/test",
                json={"data": "something"},
                headers={"content-type": "application/json"},
            )
            assert resp.status_code == 200

    def test_malformed_json_passes_through(self):
        """Malformed JSON passes through to let FastAPI handle it."""
        app = _build_app_with_middleware()
        with patch.dict(os.environ, {"PQC_ONLY_MODE": "true"}, clear=False):
            client = TestClient(app)
            resp = client.post(
                "/test",
                content=b"{not valid json",
                headers={"content-type": "application/json"},
            )
            # Should not be 400 from our middleware
            assert resp.status_code != 400 or "CLASSICAL_ALGORITHM_REJECTED" not in resp.text

    def test_json_array_body_passes_through(self):
        """JSON array body (not dict) passes through."""
        app = _build_app_with_middleware()
        with patch.dict(os.environ, {"PQC_ONLY_MODE": "true"}, clear=False):
            client = TestClient(app)
            resp = client.post(
                "/test",
                content=json.dumps([{"algorithm": "Ed25519"}]).encode(),
                headers={"content-type": "application/json"},
            )
            assert resp.status_code != 400 or "CLASSICAL_ALGORITHM_REJECTED" not in resp.text

    # -- Redis integration --------------------------------------------------

    @pytest.mark.asyncio
    async def test_redis_provides_mode_flag(self):
        """When Redis returns 'true', PQC mode is active."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="true")

        middleware = PQCOnlyModeMiddleware(MagicMock(), redis_client=mock_redis)
        result = await middleware._get_pqc_only_mode()
        assert result is True
        mock_redis.get.assert_called_once_with(_REDIS_KEY)

    @pytest.mark.asyncio
    async def test_redis_returns_false(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="false")

        middleware = PQCOnlyModeMiddleware(MagicMock(), redis_client=mock_redis)
        result = await middleware._get_pqc_only_mode()
        assert result is False

    @pytest.mark.asyncio
    async def test_redis_unavailable_falls_back_to_env(self):
        """When Redis raises, falls back to env var."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=ConnectionError("down"))

        middleware = PQCOnlyModeMiddleware(MagicMock(), redis_client=mock_redis)
        with patch.dict(os.environ, {"PQC_ONLY_MODE": "true"}, clear=False):
            result = await middleware._get_pqc_only_mode()
        assert result is True

    @pytest.mark.asyncio
    async def test_redis_returns_none_falls_back_to_env(self):
        """When Redis returns None (key not set), falls back to env."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        middleware = PQCOnlyModeMiddleware(MagicMock(), redis_client=mock_redis)
        with patch.dict(os.environ, {"PQC_ONLY_MODE": "false"}, clear=False):
            result = await middleware._get_pqc_only_mode()
        assert result is False

    @pytest.mark.asyncio
    async def test_ttl_cache_prevents_repeated_redis_calls(self):
        """Second call within TTL should use cached value."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="true")

        middleware = PQCOnlyModeMiddleware(MagicMock(), redis_client=mock_redis)
        await middleware._get_pqc_only_mode()
        await middleware._get_pqc_only_mode()
        # Only one Redis call due to TTL cache
        assert mock_redis.get.call_count == 1

    @pytest.mark.asyncio
    async def test_no_redis_client_uses_env_directly(self):
        """When no Redis client is provided, env var is used."""
        middleware = PQCOnlyModeMiddleware(MagicMock(), redis_client=None)
        with patch.dict(os.environ, {"PQC_ONLY_MODE": "true"}, clear=False):
            result = await middleware._get_pqc_only_mode()
        assert result is True
