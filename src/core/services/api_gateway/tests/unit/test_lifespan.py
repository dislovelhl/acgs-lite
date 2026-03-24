"""Tests for API Gateway lifespan management.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.shared.constants import CONSTITUTIONAL_HASH


def _patch_create_control_plane(lifespan_mod, mock_control):
    """Patch create_research_operator_control_plane as a regular (non-async) function.

    The original is async def but the lifespan code does NOT await the call,
    so we must replace it with a plain callable to avoid coroutine issues.
    """
    return patch.object(
        lifespan_mod,
        "create_research_operator_control_plane",
        lambda **kwargs: mock_control,
    )


def _mock_control_plane():
    mock = MagicMock()
    mock.aclose = AsyncMock()
    return mock


# ---------------------------------------------------------------------------
# _verify_constitutional_hash_at_startup
# ---------------------------------------------------------------------------


class TestVerifyConstitutionalHashAtStartup:
    """Test constitutional hash verification at startup (M-5 fix)."""

    def _call(self):
        from src.core.services.api_gateway.lifespan import (
            _verify_constitutional_hash_at_startup,
        )
        return _verify_constitutional_hash_at_startup()

    def test_production_no_env_hash_raises(self):
        import src.core.services.api_gateway.lifespan as mod

        with patch.object(mod, "_is_development_environment", return_value=False):
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
                with pytest.raises(RuntimeError, match="CONSTITUTIONAL_HASH must be set"):
                    self._call()

    def test_production_matching_hash_succeeds(self):
        import src.core.services.api_gateway.lifespan as mod

        with patch.object(mod, "_is_development_environment", return_value=False):
            env = {"CONSTITUTIONAL_HASH": CONSTITUTIONAL_HASH}
            with patch.dict(os.environ, env, clear=True):
                self._call()

    def test_production_mismatched_hash_raises(self):
        import src.core.services.api_gateway.lifespan as mod

        with patch.object(mod, "_is_development_environment", return_value=False):
            env = {"CONSTITUTIONAL_HASH": "wrong_hash_value"}
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(RuntimeError, match="Constitutional hash mismatch"):
                    self._call()

    def test_dev_no_env_hash_warns_but_continues(self):
        import src.core.services.api_gateway.lifespan as mod

        with patch.object(mod, "_is_development_environment", return_value=True):
            with patch.dict(os.environ, {}, clear=True):
                self._call()

    def test_dev_mismatched_hash_warns_but_continues(self):
        import src.core.services.api_gateway.lifespan as mod

        with patch.object(mod, "_is_development_environment", return_value=True):
            env = {"CONSTITUTIONAL_HASH": "wrong_hash_value"}
            with patch.dict(os.environ, env, clear=True):
                self._call()

    def test_test_environment_is_development_mode(self):
        import src.core.services.api_gateway.lifespan as mod

        with patch.object(mod, "_is_development_environment", return_value=True):
            with patch.dict(os.environ, {}, clear=True):
                self._call()

    def test_runtime_environment_prefers_environment_over_defaulted_settings_env(self, monkeypatch):
        import src.core.services.api_gateway.lifespan as mod

        monkeypatch.setattr(mod.settings, "env", "development")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")

        assert mod._runtime_environment() == "production"

    def test_environment_only_production_still_requires_constitutional_hash(self, monkeypatch):
        import src.core.services.api_gateway.lifespan as mod

        monkeypatch.setattr(mod.settings, "env", "development")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("CONSTITUTIONAL_HASH", raising=False)

        with pytest.raises(RuntimeError, match="CONSTITUTIONAL_HASH must be set"):
            self._call()


# ---------------------------------------------------------------------------
# lifespan context manager
# ---------------------------------------------------------------------------


class TestLifespan:
    @pytest.mark.asyncio
    async def test_lifespan_startup_initializes_hitl_client(self):
        """Lifespan should initialize HITL client on app state."""
        import src.core.services.api_gateway.lifespan as lifespan_mod

        env = {
            "ENVIRONMENT": "test",
            "HITL_URL": "http://hitl:8002",
            "SELF_EVOLUTION_OPERATOR_CONTROL_BACKEND": "memory",
        }
        mock_control = _mock_control_plane()

        with patch.dict(os.environ, env, clear=False), \
             patch.object(lifespan_mod, "_is_development_environment", return_value=True), \
             _patch_create_control_plane(lifespan_mod, mock_control), \
             patch.object(lifespan_mod, "close_proxy_client", new_callable=AsyncMock), \
             patch.object(lifespan_mod, "_close_feedback_redis", new_callable=AsyncMock):
            mock_app = MagicMock()
            mock_app.state = MagicMock()

            async with lifespan_mod.lifespan(mock_app):
                assert hasattr(mock_app.state, "hitl_client")

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_closes_clients(self):
        """Lifespan shutdown should close proxy and feedback Redis."""
        import src.core.services.api_gateway.lifespan as lifespan_mod

        env = {
            "ENVIRONMENT": "test",
            "SELF_EVOLUTION_OPERATOR_CONTROL_BACKEND": "memory",
        }
        mock_control = _mock_control_plane()
        mock_close_proxy = AsyncMock()
        mock_close_feedback = AsyncMock()

        with patch.dict(os.environ, env, clear=False), \
             patch.object(lifespan_mod, "_is_development_environment", return_value=True), \
             _patch_create_control_plane(lifespan_mod, mock_control), \
             patch.object(lifespan_mod, "close_proxy_client", mock_close_proxy), \
             patch.object(lifespan_mod, "_close_feedback_redis", mock_close_feedback):
            mock_app = MagicMock()
            mock_app.state = MagicMock()

            async with lifespan_mod.lifespan(mock_app):
                pass

            mock_close_proxy.assert_awaited_once()
            mock_close_feedback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_closes_operator_control_plane(self):
        """Lifespan shutdown should call aclose() on operator control plane."""
        import src.core.services.api_gateway.lifespan as lifespan_mod

        env = {
            "ENVIRONMENT": "test",
            "SELF_EVOLUTION_OPERATOR_CONTROL_BACKEND": "memory",
        }
        mock_control = _mock_control_plane()

        with patch.dict(os.environ, env, clear=False), \
             patch.object(lifespan_mod, "_is_development_environment", return_value=True), \
             _patch_create_control_plane(lifespan_mod, mock_control), \
             patch.object(lifespan_mod, "close_proxy_client", new_callable=AsyncMock), \
             patch.object(lifespan_mod, "_close_feedback_redis", new_callable=AsyncMock):
            mock_app = MagicMock()
            mock_app.state = MagicMock()

            async with lifespan_mod.lifespan(mock_app):
                pass

            mock_control.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_no_control_plane_skips_aclose(self):
        """When research_operator_control_plane is None, shutdown should not crash."""
        import src.core.services.api_gateway.lifespan as lifespan_mod

        env = {
            "ENVIRONMENT": "test",
            "SELF_EVOLUTION_OPERATOR_CONTROL_BACKEND": "memory",
        }

        with patch.dict(os.environ, env, clear=False), \
             patch.object(lifespan_mod, "_is_development_environment", return_value=True), \
             _patch_create_control_plane(lifespan_mod, None), \
             patch.object(lifespan_mod, "close_proxy_client", new_callable=AsyncMock), \
             patch.object(lifespan_mod, "_close_feedback_redis", new_callable=AsyncMock):
            mock_app = MagicMock()
            mock_app.state = MagicMock()

            async with lifespan_mod.lifespan(mock_app):
                # Ensure control plane is None on the state for shutdown path
                mock_app.state.research_operator_control_plane = None
