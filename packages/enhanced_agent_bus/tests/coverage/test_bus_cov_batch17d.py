"""
Coverage tests for batch17d:
  1. mcp_integration/auth/mcp_auth_provider/provider.py
  2. mcp_integration/auth/mcp_auth_provider/token_ops.py
  3. api/routes/z3.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "packages/enhanced_agent_bus")


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_oauth2_token(
    access_token: str = "test-access-token",
    token_type: str = "Bearer",
    expires_in: int | None = 3600,
    refresh_token: str | None = None,
    expired: bool = False,
    needs_refresh: bool = False,
) -> Any:
    """Build a mock OAuth2Token."""
    from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import OAuth2Token

    tok = OAuth2Token(
        access_token=access_token,
        token_type=token_type,
        expires_in=expires_in,
        refresh_token=refresh_token,
    )
    if expired:
        tok.expires_at = datetime.now(UTC) - timedelta(hours=1)
    if needs_refresh:
        tok.expires_at = datetime.now(UTC) + timedelta(seconds=30)
    return tok


def _make_oidc_tokens(
    access_token: str = "oidc-access",
    refresh_token: str | None = "oidc-refresh",
) -> Any:
    from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import OAuth2Token
    from enhanced_agent_bus.mcp_integration.auth.oidc_provider import OIDCTokens

    oauth2_tok = OAuth2Token(
        access_token=access_token,
        expires_in=3600,
        refresh_token=refresh_token,
    )
    return OIDCTokens(oauth2_token=oauth2_tok)


# ============================================================================
# PROVIDER TESTS (provider.py)
# ============================================================================


class TestMCPAuthProviderInit:
    """Test MCPAuthProvider initialization."""

    def test_default_init(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        assert provider._oauth2_providers == {}
        assert provider._oidc_providers == {}
        assert provider._managed_tokens == {}
        assert provider._tool_providers == {}
        assert provider._stats["tokens_acquired"] == 0

    def test_init_with_config(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(enable_audit=False)
        provider = MCPAuthProvider(config=cfg)
        assert provider._audit_logger is None
        assert provider.config is cfg

    def test_init_with_audit_enabled(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(enable_audit=True)
        provider = MCPAuthProvider(config=cfg)
        assert provider._audit_logger is not None


class TestMCPAuthProviderInitialize:
    """Test MCPAuthProvider.initialize()."""

    async def test_initialize_no_providers(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(
            auto_refresh_enabled=False,
            enable_audit=False,
        )
        provider = MCPAuthProvider(config=cfg)
        provider._credential_manager = AsyncMock()
        provider._token_refresher = AsyncMock()
        provider._token_refresher.start = AsyncMock()
        provider._credential_manager.load_credentials = AsyncMock()

        await provider.initialize()
        provider._credential_manager.load_credentials.assert_awaited_once()

    async def test_initialize_with_auto_refresh(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(
            auto_refresh_enabled=True,
            enable_audit=False,
        )
        provider = MCPAuthProvider(config=cfg)
        provider._credential_manager = AsyncMock()
        provider._token_refresher = AsyncMock()

        await provider.initialize()
        provider._token_refresher.start.assert_awaited_once()

    async def test_initialize_with_audit(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(
            auto_refresh_enabled=False,
            enable_audit=True,
        )
        provider = MCPAuthProvider(config=cfg)
        provider._credential_manager = AsyncMock()
        provider._token_refresher = AsyncMock()
        provider._audit_logger = AsyncMock()

        await provider.initialize()
        provider._audit_logger.log_event.assert_awaited_once()


class TestMCPAuthProviderShutdown:
    """Test MCPAuthProvider.shutdown()."""

    async def test_shutdown_stops_refresher(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        provider._token_refresher = AsyncMock()
        provider._audit_logger = None

        await provider.shutdown()
        provider._token_refresher.stop.assert_awaited_once()

    async def test_shutdown_with_audit(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        provider._token_refresher = AsyncMock()
        provider._audit_logger = AsyncMock()

        await provider.shutdown()
        provider._audit_logger.log_event.assert_awaited_once()


class TestAddProvider:
    """Test MCPAuthProvider.add_provider()."""

    async def test_add_generic_oauth2_provider(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.enums import ProviderType
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import ProviderConfig
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        cfg = ProviderConfig(
            provider_type=ProviderType.GENERIC,
            name="test",
            token_endpoint="https://example.com/token",
            discovery_enabled=False,
        )
        result = await provider.add_provider("test", cfg)
        assert result is True
        assert "test" in provider._oauth2_providers

    async def test_add_oidc_provider_discovery_success(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.enums import ProviderType
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import ProviderConfig
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        cfg = ProviderConfig(
            provider_type=ProviderType.AZURE_AD,
            name="azure",
            tenant_id="test-tenant",
        )

        mock_metadata = MagicMock()
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oidc_provider.OIDCProvider.discover",
            new_callable=AsyncMock,
            return_value=mock_metadata,
        ):
            result = await provider.add_provider("azure", cfg)

        assert result is True
        assert "azure" in provider._oidc_providers
        assert provider._stats["discovery_calls"] == 1

    async def test_add_oidc_provider_discovery_none_falls_back(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.enums import ProviderType
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import ProviderConfig
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        cfg = ProviderConfig(
            provider_type=ProviderType.GOOGLE,
            name="google",
        )

        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oidc_provider.OIDCProvider.discover",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await provider.add_provider("google", cfg)

        assert result is True
        # Falls back to OAuth2
        assert "google" in provider._oauth2_providers

    async def test_add_oidc_provider_discovery_error(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.enums import ProviderType
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import ProviderConfig
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        cfg = ProviderConfig(
            provider_type=ProviderType.OKTA,
            name="okta",
            okta_domain="dev-123.okta.com",
        )

        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oidc_provider.OIDCProvider.discover",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network error"),
        ):
            result = await provider.add_provider("okta", cfg)

        assert result is False

    async def test_add_provider_with_discovery_enabled_and_issuer(self):
        """Provider with discovery_enabled=True and issuer_url should use OIDC path."""
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.enums import ProviderType
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import ProviderConfig
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        cfg = ProviderConfig(
            provider_type=ProviderType.CUSTOM,
            name="custom-oidc",
            issuer_url="https://custom.example.com",
            discovery_enabled=True,
        )

        mock_metadata = MagicMock()
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oidc_provider.OIDCProvider.discover",
            new_callable=AsyncMock,
            return_value=mock_metadata,
        ):
            result = await provider.add_provider("custom-oidc", cfg)

        assert result is True
        assert "custom-oidc" in provider._oidc_providers


class TestRemoveProvider:
    """Test MCPAuthProvider.remove_provider()."""

    async def test_remove_oauth2_provider(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        provider._oauth2_providers["test"] = MagicMock()
        provider._token_refresher = AsyncMock()

        result = await provider.remove_provider("test")
        assert result is True
        assert "test" not in provider._oauth2_providers

    async def test_remove_oidc_provider(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        provider._oidc_providers["test"] = MagicMock()
        provider._discovery_cache["test"] = MagicMock()
        provider._token_refresher = AsyncMock()

        result = await provider.remove_provider("test")
        assert result is True
        assert "test" not in provider._oidc_providers
        assert "test" not in provider._discovery_cache

    async def test_remove_nonexistent_provider(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        provider._token_refresher = AsyncMock()

        result = await provider.remove_provider("no-such")
        assert result is False

    async def test_remove_provider_revokes_tokens(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        provider._oauth2_providers["prov"] = MagicMock()
        provider._token_refresher = AsyncMock()

        managed_token = MagicMock()
        managed_token.provider_name = "prov"
        provider._managed_tokens["tok1"] = managed_token

        await provider.remove_provider("prov")
        assert "tok1" not in provider._managed_tokens
        provider._token_refresher.unregister_token.assert_awaited_with("tok1")


class TestDiscoverProvider:
    """Test MCPAuthProvider.discover_provider()."""

    async def test_discover_cached(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        mock_meta = MagicMock()
        mock_meta.discovered_at = datetime.now(UTC)
        provider._discovery_cache["cached"] = mock_meta

        result = await provider.discover_provider("https://example.com", name="cached")
        assert result is mock_meta

    async def test_discover_expired_cache(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        mock_meta = MagicMock()
        mock_meta.discovered_at = datetime.now(UTC) - timedelta(hours=2)
        provider._discovery_cache["old"] = mock_meta

        new_meta = MagicMock()
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oidc_provider.OIDCProvider.discover",
            new_callable=AsyncMock,
            return_value=new_meta,
        ):
            result = await provider.discover_provider("https://example.com", name="old")
        assert result is new_meta
        assert provider._discovery_cache["old"] is new_meta

    async def test_discover_force_refresh(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        mock_meta = MagicMock()
        mock_meta.discovered_at = datetime.now(UTC)
        provider._discovery_cache["cached"] = mock_meta

        new_meta = MagicMock()
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oidc_provider.OIDCProvider.discover",
            new_callable=AsyncMock,
            return_value=new_meta,
        ):
            result = await provider.discover_provider(
                "https://example.com", name="cached", force_refresh=True
            )
        assert result is new_meta

    async def test_discover_no_name_uses_hash(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        new_meta = MagicMock()
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oidc_provider.OIDCProvider.discover",
            new_callable=AsyncMock,
            return_value=new_meta,
        ):
            result = await provider.discover_provider("https://example.com")
        assert result is new_meta
        assert provider._stats["discovery_calls"] == 1

    async def test_discover_returns_none(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oidc_provider.OIDCProvider.discover",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await provider.discover_provider("https://example.com")
        assert result is None


class TestGenerateTokenId:
    """Test MCPAuthProvider._generate_token_id()."""

    def test_with_all_components(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        tid = provider._generate_token_id("prov", "tool", "tenant")
        assert tid == "prov:tool:tenant"

    def test_with_none_tool_and_tenant(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        tid = provider._generate_token_id("prov", None, None)
        assert tid == "prov:global:default"


class TestGetStats:
    """Test MCPAuthProvider.get_stats()."""

    def test_get_stats(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        provider._token_refresher = MagicMock()
        provider._token_refresher.get_stats.return_value = {"running": False}
        provider._credential_manager = MagicMock()
        provider._credential_manager.get_stats.return_value = {}

        stats = provider.get_stats()
        assert "tokens_acquired" in stats
        assert "oauth2_providers" in stats
        assert "oidc_providers" in stats
        assert "refresher_stats" in stats
        assert "constitutional_hash" in stats


class TestListManagedTokens:
    """Test MCPAuthProvider.list_managed_tokens()."""

    def test_empty(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        assert provider.list_managed_tokens() == []

    def test_with_tokens(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        mock_managed = MagicMock()
        mock_managed.update_state.return_value = None
        mock_managed.to_dict.return_value = {"token_id": "t1"}
        provider._managed_tokens["t1"] = mock_managed

        result = provider.list_managed_tokens()
        assert len(result) == 1
        assert result[0]["token_id"] == "t1"


class TestGetProviderInfo:
    """Test MCPAuthProvider.get_provider_info()."""

    def test_oidc_provider_with_metadata(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        mock_oidc = MagicMock()
        mock_meta = MagicMock()
        mock_meta.to_dict.return_value = {"issuer": "https://ex.com"}
        mock_oidc.get_metadata.return_value = mock_meta
        mock_oidc.get_stats.return_value = {}
        provider._oidc_providers["test"] = mock_oidc

        info = provider.get_provider_info("test")
        assert info is not None
        assert info["type"] == "oidc"
        assert info["discovered"] is True

    def test_oidc_provider_without_metadata(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        mock_oidc = MagicMock()
        mock_oidc.get_metadata.return_value = None
        mock_oidc.get_stats.return_value = {}
        provider._oidc_providers["test"] = mock_oidc

        info = provider.get_provider_info("test")
        assert info is not None
        assert info["discovered"] is False
        assert info["metadata"] is None

    def test_oauth2_provider(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        mock_oauth2 = MagicMock()
        mock_oauth2.get_stats.return_value = {"calls": 5}
        provider._oauth2_providers["test"] = mock_oauth2

        info = provider.get_provider_info("test")
        assert info is not None
        assert info["type"] == "oauth2"

    def test_nonexistent_provider(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        assert provider.get_provider_info("nope") is None


class TestGetHealth:
    """Test MCPAuthProvider.get_health()."""

    async def test_health_basic(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        provider._token_refresher = MagicMock()
        provider._token_refresher._running = False

        health = await provider.get_health()
        assert health["healthy"] is True
        assert health["total_providers"] == 0
        assert health["managed_tokens"] == 0

    async def test_health_with_providers_and_tokens(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.enums import TokenState
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        provider = MCPAuthProvider()
        provider._token_refresher = MagicMock()
        provider._token_refresher._running = True
        provider._oauth2_providers["o1"] = MagicMock()

        mock_oidc = MagicMock()
        mock_oidc.get_metadata.return_value = MagicMock()
        provider._oidc_providers["o2"] = mock_oidc

        # Add tokens in different states
        tok_valid = MagicMock()
        tok_valid.update_state.return_value = TokenState.VALID
        tok_expiring = MagicMock()
        tok_expiring.update_state.return_value = TokenState.EXPIRING_SOON
        tok_expired = MagicMock()
        tok_expired.update_state.return_value = TokenState.EXPIRED

        provider._managed_tokens = {
            "t1": tok_valid,
            "t2": tok_expiring,
            "t3": tok_expired,
        }

        health = await provider.get_health()
        assert health["total_providers"] == 2
        assert health["managed_tokens"] == 3
        assert health["expiring_tokens"] == 1
        assert health["expired_tokens"] == 1
        assert health["refresher_running"] is True


# ============================================================================
# TOKEN OPS TESTS (token_ops.py)
# ============================================================================


class TestAcquireToken:
    """Test TokenOperationsMixin.acquire_token()."""

    def _make_provider(self, **kwargs):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(
            enable_audit=False,
            auto_refresh_enabled=False,
            **kwargs,
        )
        prov = MCPAuthProvider(config=cfg)
        prov._token_refresher = AsyncMock()
        return prov

    async def test_no_provider_no_default(self):
        prov = self._make_provider()
        result = await prov.acquire_token()
        assert result.success is False
        assert "No provider" in result.error

    async def test_existing_valid_token_returned(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.enums import TokenState

        prov = self._make_provider(default_provider="dp")
        tok = _make_oauth2_token()
        managed = MagicMock()
        managed.state = TokenState.VALID
        managed.update_state.return_value = TokenState.VALID
        managed.token = tok
        managed.oidc_tokens = None
        prov._managed_tokens["dp:global:default"] = managed

        result = await prov.acquire_token()
        assert result.success is True
        assert result.token is tok

    async def test_acquire_from_oauth2_provider(self):
        prov = self._make_provider()
        tok = _make_oauth2_token()
        mock_oauth2 = AsyncMock()
        mock_oauth2.acquire_token = AsyncMock(return_value=tok)
        prov._oauth2_providers["myprov"] = mock_oauth2

        result = await prov.acquire_token(provider_name="myprov")
        assert result.success is True
        assert result.token is tok
        assert prov._stats["tokens_acquired"] == 1

    async def test_acquire_from_oauth2_with_refresh_token_registers(self):
        prov = self._make_provider()
        tok = _make_oauth2_token(refresh_token="rt")
        mock_oauth2 = AsyncMock()
        mock_oauth2.acquire_token = AsyncMock(return_value=tok)
        prov._oauth2_providers["myprov"] = mock_oauth2

        result = await prov.acquire_token(provider_name="myprov")
        assert result.success is True
        prov._token_refresher.register_token.assert_awaited_once()

    async def test_acquire_from_oauth2_error(self):
        prov = self._make_provider()
        mock_oauth2 = AsyncMock()
        mock_oauth2.acquire_token = AsyncMock(side_effect=ValueError("bad"))
        prov._oauth2_providers["myprov"] = mock_oauth2

        result = await prov.acquire_token(provider_name="myprov")
        assert result.success is False
        assert "bad" in result.error
        assert prov._stats["auth_failures"] == 1

    async def test_acquire_provider_not_found(self):
        prov = self._make_provider()
        result = await prov.acquire_token(provider_name="unknown")
        assert result.success is False
        assert "not found" in result.error

    async def test_acquire_with_audit_logger(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(
            enable_audit=True,
            auto_refresh_enabled=False,
        )
        prov = MCPAuthProvider(config=cfg)
        prov._token_refresher = AsyncMock()
        prov._audit_logger = AsyncMock()

        tok = _make_oauth2_token()
        mock_oauth2 = AsyncMock()
        mock_oauth2.acquire_token = AsyncMock(return_value=tok)
        prov._oauth2_providers["prov"] = mock_oauth2

        result = await prov.acquire_token(provider_name="prov")
        assert result.success is True
        prov._audit_logger.log_event.assert_awaited_once()


class TestDoAcquireTokenOIDC:
    """Test _do_acquire_token with OIDC providers."""

    async def test_oidc_acquire_success(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(enable_audit=False, auto_refresh_enabled=False)
        prov = MCPAuthProvider(config=cfg)
        prov._token_refresher = AsyncMock()

        oidc_tokens = _make_oidc_tokens()
        mock_oidc = AsyncMock()
        mock_oidc.acquire_tokens = AsyncMock(return_value=oidc_tokens)
        mock_oidc._oauth2_provider = MagicMock()
        prov._oidc_providers["oidc1"] = mock_oidc

        result = await prov.acquire_token(provider_name="oidc1")
        assert result.success is True
        assert result.oidc_tokens is oidc_tokens
        prov._token_refresher.register_token.assert_awaited_once()

    async def test_oidc_acquire_no_refresh_token(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(enable_audit=False, auto_refresh_enabled=False)
        prov = MCPAuthProvider(config=cfg)
        prov._token_refresher = AsyncMock()

        oidc_tokens = _make_oidc_tokens(refresh_token=None)
        mock_oidc = AsyncMock()
        mock_oidc.acquire_tokens = AsyncMock(return_value=oidc_tokens)
        mock_oidc._oauth2_provider = MagicMock()
        prov._oidc_providers["oidc1"] = mock_oidc

        result = await prov.acquire_token(provider_name="oidc1")
        assert result.success is True
        prov._token_refresher.register_token.assert_not_awaited()

    async def test_oidc_acquire_fails_falls_to_oauth2(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(enable_audit=False, auto_refresh_enabled=False)
        prov = MCPAuthProvider(config=cfg)
        prov._token_refresher = AsyncMock()

        mock_oidc = AsyncMock()
        mock_oidc.acquire_tokens = AsyncMock(side_effect=ValueError("oidc fail"))
        prov._oidc_providers["both"] = mock_oidc

        tok = _make_oauth2_token()
        mock_oauth2 = AsyncMock()
        mock_oauth2.acquire_token = AsyncMock(return_value=tok)
        prov._oauth2_providers["both"] = mock_oauth2

        result = await prov.acquire_token(provider_name="both")
        assert result.success is True
        assert result.token is tok

    async def test_oidc_returns_none(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(enable_audit=False, auto_refresh_enabled=False)
        prov = MCPAuthProvider(config=cfg)
        prov._token_refresher = AsyncMock()

        mock_oidc = AsyncMock()
        mock_oidc.acquire_tokens = AsyncMock(return_value=None)
        prov._oidc_providers["oidc1"] = mock_oidc

        # No OAuth2 fallback either
        result = await prov.acquire_token(provider_name="oidc1")
        assert result.success is False


class TestRefreshToken:
    """Test TokenOperationsMixin.refresh_token()."""

    async def test_refresh_success(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.enums import TokenState
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )
        from enhanced_agent_bus.mcp_integration.auth.token_refresh import (
            RefreshResult,
            RefreshStatus,
        )

        prov = MCPAuthProvider()
        new_tok = _make_oauth2_token(access_token="new-access")
        refresh_result = RefreshResult(
            token_id="t1",
            status=RefreshStatus.SUCCESS,
            new_token=new_tok,
        )
        prov._token_refresher = AsyncMock()
        prov._token_refresher.refresh_token = AsyncMock(return_value=refresh_result)

        managed = MagicMock()
        managed.refresh_count = 0
        prov._managed_tokens["t1"] = managed

        result = await prov.refresh_token("t1")
        assert result.status == RefreshStatus.SUCCESS
        assert prov._stats["tokens_refreshed"] == 1
        assert managed.token == new_tok

    async def test_refresh_failed(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )
        from enhanced_agent_bus.mcp_integration.auth.token_refresh import (
            RefreshResult,
            RefreshStatus,
        )

        prov = MCPAuthProvider()
        refresh_result = RefreshResult(
            token_id="t1",
            status=RefreshStatus.FAILED,
        )
        prov._token_refresher = AsyncMock()
        prov._token_refresher.refresh_token = AsyncMock(return_value=refresh_result)

        result = await prov.refresh_token("t1")
        assert result.status == RefreshStatus.FAILED
        assert prov._stats["tokens_refreshed"] == 0


class TestRevokeToken:
    """Test TokenOperationsMixin.revoke_token()."""

    async def test_revoke_existing_token(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        prov = MCPAuthProvider()
        prov._token_refresher = AsyncMock()
        prov._audit_logger = None

        tok = _make_oauth2_token()
        managed = MagicMock()
        managed.provider_name = "prov1"
        managed.token = tok
        managed.tool_name = "tool1"
        managed.tenant_id = None
        prov._managed_tokens["t1"] = managed

        mock_oauth2 = AsyncMock()
        prov._oauth2_providers["prov1"] = mock_oauth2

        result = await prov.revoke_token("t1")
        assert result is True
        assert prov._stats["tokens_revoked"] == 1
        mock_oauth2.revoke_token.assert_awaited_once()
        prov._token_refresher.unregister_token.assert_awaited_with("t1")

    async def test_revoke_nonexistent_token(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        prov = MCPAuthProvider()
        result = await prov.revoke_token("no-such")
        assert result is False

    async def test_revoke_with_audit(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        prov = MCPAuthProvider()
        prov._token_refresher = AsyncMock()
        prov._audit_logger = AsyncMock()

        tok = _make_oauth2_token()
        managed = MagicMock()
        managed.provider_name = "prov1"
        managed.token = tok
        managed.tool_name = "t"
        managed.tenant_id = None
        prov._managed_tokens["t1"] = managed
        prov._oauth2_providers["prov1"] = AsyncMock()

        await prov.revoke_token("t1")
        prov._audit_logger.log_event.assert_awaited_once()


class TestGetTokenForTool:
    """Test TokenOperationsMixin.get_token_for_tool()."""

    async def test_no_provider_mapping(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(default_provider=None, enable_audit=False)
        prov = MCPAuthProvider(config=cfg)
        result = await prov.get_token_for_tool("unknown-tool")
        assert result is None

    async def test_existing_valid_token(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.enums import TokenState
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(default_provider="dp", enable_audit=False)
        prov = MCPAuthProvider(config=cfg)

        tok = _make_oauth2_token()
        managed = MagicMock()
        managed.state = TokenState.VALID
        managed.update_state.return_value = TokenState.VALID
        managed.token = tok
        prov._managed_tokens["dp:mytool:default"] = managed

        result = await prov.get_token_for_tool("mytool")
        assert result is tok

    async def test_expiring_token_still_returned(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.enums import TokenState
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(default_provider="dp", enable_audit=False)
        prov = MCPAuthProvider(config=cfg)

        tok = _make_oauth2_token()
        managed = MagicMock()
        managed.state = TokenState.EXPIRING_SOON
        managed.update_state.return_value = TokenState.EXPIRING_SOON
        managed.token = tok
        prov._managed_tokens["dp:mytool:default"] = managed

        result = await prov.get_token_for_tool("mytool")
        assert result is tok

    async def test_acquire_new_token_on_expired(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.enums import TokenState
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(default_provider="dp", enable_audit=False)
        prov = MCPAuthProvider(config=cfg)
        prov._token_refresher = AsyncMock()

        tok = _make_oauth2_token()
        managed = MagicMock()
        managed.state = TokenState.EXPIRED
        managed.update_state.return_value = TokenState.EXPIRED
        managed.token = tok
        prov._managed_tokens["dp:mytool:default"] = managed

        new_tok = _make_oauth2_token(access_token="new")
        mock_oauth2 = AsyncMock()
        mock_oauth2.acquire_token = AsyncMock(return_value=new_tok)
        prov._oauth2_providers["dp"] = mock_oauth2

        result = await prov.get_token_for_tool("mytool")
        assert result is new_tok

    async def test_tool_with_configured_provider(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(enable_audit=False)
        prov = MCPAuthProvider(config=cfg)
        prov._token_refresher = AsyncMock()

        prov.configure_tool_provider("special-tool", "special-prov")
        assert prov._tool_providers["special-tool"] == "special-prov"

        tok = _make_oauth2_token()
        mock_oauth2 = AsyncMock()
        mock_oauth2.acquire_token = AsyncMock(return_value=tok)
        prov._oauth2_providers["special-prov"] = mock_oauth2

        result = await prov.get_token_for_tool("special-tool")
        assert result is tok


class TestInjectAuthHeaders:
    """Test TokenOperationsMixin.inject_auth_headers()."""

    async def test_inject_with_valid_token(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.enums import TokenState
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(default_provider="dp", enable_audit=False)
        prov = MCPAuthProvider(config=cfg)

        tok = _make_oauth2_token(access_token="secret")
        managed = MagicMock()
        managed.state = TokenState.VALID
        managed.update_state.return_value = TokenState.VALID
        managed.token = tok
        prov._managed_tokens["dp:tool1:default"] = managed

        headers: dict[str, str] = {"Accept": "application/json"}
        result = await prov.inject_auth_headers("tool1", headers)
        assert "Authorization" in result
        assert result["Authorization"] == "Bearer secret"

    async def test_inject_no_token_available(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
            MCPAuthProviderConfig,
        )
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        cfg = MCPAuthProviderConfig(default_provider=None, enable_audit=False)
        prov = MCPAuthProvider(config=cfg)

        headers: dict[str, str] = {"Accept": "application/json"}
        result = await prov.inject_auth_headers("tool1", headers)
        assert "Authorization" not in result


class TestTokenCallbacks:
    """Test _on_token_refresh and _on_refresh_error callbacks."""

    async def test_on_token_refresh_no_audit(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        prov = MCPAuthProvider()
        prov._audit_logger = None
        old_tok = _make_oauth2_token()
        new_tok = _make_oauth2_token(access_token="new")
        # Should not raise
        await prov._on_token_refresh(old_tok, new_tok)

    async def test_on_token_refresh_with_audit(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        prov = MCPAuthProvider()
        prov._audit_logger = AsyncMock()
        old_tok = _make_oauth2_token()
        new_tok = _make_oauth2_token(access_token="new")
        await prov._on_token_refresh(old_tok, new_tok)
        prov._audit_logger.log_event.assert_awaited_once()

    async def test_on_refresh_error_increments_count(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        prov = MCPAuthProvider()
        prov._audit_logger = None
        managed = MagicMock()
        managed.error_count = 0
        prov._managed_tokens["t1"] = managed

        await prov._on_refresh_error("t1", RuntimeError("err"))
        assert managed.error_count == 1

    async def test_on_refresh_error_with_audit(self):
        from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.provider import (
            MCPAuthProvider,
        )

        prov = MCPAuthProvider()
        prov._audit_logger = AsyncMock()
        await prov._on_refresh_error("t1", RuntimeError("err"))
        prov._audit_logger.log_event.assert_awaited_once()


# ============================================================================
# Z3 ROUTE TESTS (api/routes/z3.py)
# ============================================================================


class TestNormalizeSolverResult:
    """Test _normalize_solver_result."""

    def test_sat(self):
        from enhanced_agent_bus.api.routes.z3 import _normalize_solver_result

        assert _normalize_solver_result("sat") == "sat"
        assert _normalize_solver_result("valid") == "sat"
        assert _normalize_solver_result("SAT") == "sat"
        assert _normalize_solver_result(" Valid ") == "sat"

    def test_unsat(self):
        from enhanced_agent_bus.api.routes.z3 import _normalize_solver_result

        assert _normalize_solver_result("unsat") == "unsat"
        assert _normalize_solver_result("invalid") == "unsat"
        assert _normalize_solver_result("UNSAT") == "unsat"

    def test_unknown(self):
        from enhanced_agent_bus.api.routes.z3 import _normalize_solver_result

        assert _normalize_solver_result("timeout") == "unknown"
        assert _normalize_solver_result("error") == "unknown"
        assert _normalize_solver_result("") == "unknown"


class TestResetState:
    """Test _reset_state."""

    def test_reset_clears_all(self):
        from enhanced_agent_bus.api.routes.z3 import (
            _METRICS,
            _RECENT_RESULTS,
            _reset_state,
        )

        _METRICS["total_verifications"] = 10
        _RECENT_RESULTS.append({"test": True})
        _reset_state()

        assert _METRICS["total_verifications"] == 0
        assert len(_RECENT_RESULTS) == 0
        assert _METRICS["verification_times_ms"] == []
        assert _METRICS["policy_type_counts"] == {}


class TestComputedMetrics:
    """Test _computed_metrics."""

    def test_empty_metrics(self):
        from enhanced_agent_bus.api.routes.z3 import _computed_metrics, _reset_state

        _reset_state()
        m = _computed_metrics()
        assert m["average_verification_time_ms"] == 0.0
        assert m["cache_hit_rate"] == 0.0
        assert "verification_times_ms" not in m
        # All policy types present
        for pt in (
            "access_control",
            "resource_constraint",
            "temporal_governance",
            "constitutional",
            "general",
        ):
            assert pt in m["policy_type_counts"]

    def test_with_data(self):
        from enhanced_agent_bus.api.routes.z3 import _METRICS, _computed_metrics, _reset_state

        _reset_state()
        _METRICS["verification_times_ms"] = [10.0, 20.0, 30.0]
        _METRICS["cache_hits"] = 7
        _METRICS["cache_misses"] = 3

        m = _computed_metrics()
        assert m["average_verification_time_ms"] == 20.0
        assert m["cache_hit_rate"] == 0.7


class TestRecordResult:
    """Test _record_result."""

    def test_record_success(self):
        from enhanced_agent_bus.api.routes.z3 import (
            _METRICS,
            _RECENT_RESULTS,
            _record_result,
            _reset_state,
        )

        _reset_state()
        _record_result({"id": "p1"}, "general", is_success=True, elapsed_ms=5.0)

        assert _METRICS["total_verifications"] == 1
        assert _METRICS["successful_verifications"] == 1
        assert _METRICS["failed_verifications"] == 0
        assert len(_RECENT_RESULTS) == 1
        assert _METRICS["policy_type_counts"]["general"]["success"] == 1

    def test_record_failure(self):
        from enhanced_agent_bus.api.routes.z3 import _METRICS, _record_result, _reset_state

        _reset_state()
        _record_result({"id": "p1"}, "constitutional", is_success=False, elapsed_ms=10.0)

        assert _METRICS["failed_verifications"] == 1
        assert _METRICS["policy_type_counts"]["constitutional"]["failed"] == 1

    def test_record_trims_times_list(self):
        from enhanced_agent_bus.api.routes.z3 import _METRICS, _record_result, _reset_state

        _reset_state()
        _METRICS["verification_times_ms"] = list(range(1001))
        _record_result({"id": "p1"}, "general", is_success=True, elapsed_ms=99.0)
        assert len(_METRICS["verification_times_ms"]) == 1000

    def test_record_new_policy_type(self):
        from enhanced_agent_bus.api.routes.z3 import _METRICS, _record_result, _reset_state

        _reset_state()
        _record_result({"id": "p1"}, "custom_type", is_success=True, elapsed_ms=1.0)
        assert "custom_type" in _METRICS["policy_type_counts"]
        assert _METRICS["policy_type_counts"]["custom_type"]["total"] == 1


class TestGetVerifier:
    """Test _get_verifier."""

    def test_get_verifier_returns_cached(self):
        from enhanced_agent_bus.api.routes import z3 as z3_mod

        original = z3_mod._VERIFIER
        try:
            sentinel = object()
            z3_mod._VERIFIER = sentinel
            assert z3_mod._get_verifier() is sentinel
        finally:
            z3_mod._VERIFIER = original

    def test_get_verifier_import_fails(self):
        from enhanced_agent_bus.api.routes import z3 as z3_mod

        original = z3_mod._VERIFIER
        try:
            z3_mod._VERIFIER = None
            # The import will fail since z3 verifier is not available
            result = z3_mod._get_verifier()
            # Should return None when import fails
            assert result is None
        finally:
            z3_mod._VERIFIER = original


class TestVerifyApiKey:
    """Test _verify_api_key."""

    async def test_missing_key_raises_401(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.z3 import _verify_api_key

        with pytest.raises(HTTPException) as exc_info:
            await _verify_api_key(None)
        assert exc_info.value.status_code == 401
        assert "Missing" in exc_info.value.detail

    async def test_invalid_key_raises_401(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.z3 import _verify_api_key

        with patch("enhanced_agent_bus.api.routes.z3._load_auth_module") as mock_load:
            mock_mod = MagicMock()
            mock_mod._is_known_api_key.return_value = False
            mock_load.return_value = mock_mod

            with pytest.raises(HTTPException) as exc_info:
                await _verify_api_key("bad-key")
            assert exc_info.value.status_code == 401
            assert "Invalid" in exc_info.value.detail

    async def test_valid_key_returns_key(self):
        from enhanced_agent_bus.api.routes.z3 import _verify_api_key

        with patch("enhanced_agent_bus.api.routes.z3._load_auth_module") as mock_load:
            mock_mod = MagicMock()
            mock_mod._is_known_api_key.return_value = True
            mock_load.return_value = mock_mod

            result = await _verify_api_key("good-key")
            assert result == "good-key"


class TestLoadAuthModule:
    """Test _load_auth_module."""

    def test_load_caches_module(self):
        from enhanced_agent_bus.api.routes import z3 as z3_mod

        original = z3_mod._auth_module
        try:
            z3_mod._auth_module = None
            with patch("importlib.util.spec_from_file_location") as mock_spec:
                mock_loader = MagicMock()
                mock_spec_obj = MagicMock()
                mock_spec_obj.loader = mock_loader
                mock_spec.return_value = mock_spec_obj

                with patch("importlib.util.module_from_spec") as mock_from_spec:
                    mock_mod = MagicMock()
                    mock_from_spec.return_value = mock_mod

                    result = z3_mod._load_auth_module()
                    assert result is mock_mod

                    # Second call uses cache
                    result2 = z3_mod._load_auth_module()
                    assert result2 is mock_mod
                    assert mock_spec.call_count == 1
        finally:
            z3_mod._auth_module = original


class TestPolicyVerifyRequest:
    """Test PolicyVerifyRequest model."""

    def test_valid_request(self):
        from enhanced_agent_bus.api.routes.z3 import PolicyVerifyRequest

        req = PolicyVerifyRequest(policy_id="p1")
        assert req.policy_id == "p1"
        assert req.policy_type == "general"
        assert req.description == ""
        assert req.rules == []

    def test_request_with_all_fields(self):
        from enhanced_agent_bus.api.routes.z3 import PolicyVerifyRequest

        req = PolicyVerifyRequest(
            policy_id="p2",
            policy_type="constitutional",
            description="test desc",
            rules=["rule1", "rule2"],
        )
        assert req.policy_type == "constitutional"
        assert len(req.rules) == 2

    def test_empty_policy_id_rejected(self):
        from pydantic import ValidationError

        from enhanced_agent_bus.api.routes.z3 import PolicyVerifyRequest

        with pytest.raises(ValidationError):
            PolicyVerifyRequest(policy_id="")


class TestZ3Endpoints:
    """Test Z3 API endpoints using httpx."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        from enhanced_agent_bus.api.routes.z3 import _reset_state

        _reset_state()
        yield
        _reset_state()

    def _make_app(self):
        from fastapi import FastAPI

        from enhanced_agent_bus.api.routes.z3 import router

        app = FastAPI()
        app.include_router(router)
        return app

    async def test_get_metrics(self):
        import httpx

        app = self._make_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/z3/metrics")

        assert resp.status_code == 200
        data = resp.json()
        assert "constitutional_hash" in data
        assert "metrics" in data
        assert "recent_verifications" in data
        assert data["metrics"]["total_verifications"] == 0

    async def test_verify_no_api_key(self):
        import httpx

        app = self._make_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/v1/z3/verify",
                json={"policy_id": "p1"},
            )
        assert resp.status_code == 401

    async def test_verify_synthetic(self):
        """When Z3 is not installed, endpoint returns synthetic result."""
        import httpx

        from enhanced_agent_bus.api.routes.z3 import _verify_api_key

        app = self._make_app()

        async def _override_key():
            return "test-key"

        app.dependency_overrides[_verify_api_key] = _override_key

        try:
            with patch(
                "enhanced_agent_bus.api.routes.z3._get_verifier",
                return_value=None,
            ):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    resp = await client.post(
                        "/api/v1/z3/verify",
                        json={"policy_id": "test-policy", "policy_type": "general"},
                        headers={"X-API-Key": "test-key"},
                    )

            assert resp.status_code == 200
            data = resp.json()
            assert data["is_satisfiable"] is True
            assert data["solver_result"] == "sat"
            assert data["policy_id"] == "test-policy"
        finally:
            app.dependency_overrides.clear()

    async def test_verify_with_verifier_success(self):
        """When Z3 verifier is available, use it."""
        import importlib

        import httpx

        from enhanced_agent_bus.api.routes.z3 import _verify_api_key

        app = self._make_app()

        async def _override_key():
            return "test-key"

        app.dependency_overrides[_verify_api_key] = _override_key

        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.to_dict.return_value = {
            "policy_id": "p1",
            "is_satisfiable": True,
            "is_valid": True,
            "solver_result": "sat",
        }

        mock_verifier = AsyncMock()
        mock_verifier.verify_policy = AsyncMock(return_value=mock_result)

        mock_models = MagicMock()
        mock_models.PolicyType.GENERAL = "GENERAL"
        mock_models.PolicyType.ACCESS_CONTROL = "ACCESS_CONTROL"
        mock_models.PolicyType.RESOURCE_CONSTRAINT = "RESOURCE_CONSTRAINT"
        mock_models.PolicyType.TEMPORAL_GOVERNANCE = "TEMPORAL_GOVERNANCE"
        mock_models.PolicyType.CONSTITUTIONAL = "CONSTITUTIONAL"

        try:
            with (
                patch(
                    "enhanced_agent_bus.api.routes.z3._get_verifier",
                    return_value=mock_verifier,
                ),
                patch.object(
                    importlib,
                    "import_module",
                    return_value=mock_models,
                ),
            ):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    resp = await client.post(
                        "/api/v1/z3/verify",
                        json={"policy_id": "p1"},
                        headers={"X-API-Key": "test-key"},
                    )

            assert resp.status_code == 200
            data = resp.json()
            assert data["solver_result"] == "sat"
        finally:
            app.dependency_overrides.clear()

    async def test_verify_with_verifier_exception(self):
        """When verifier raises, endpoint returns 500."""
        import importlib

        import httpx

        from enhanced_agent_bus.api.routes.z3 import _verify_api_key

        app = self._make_app()

        async def _override_key():
            return "test-key"

        app.dependency_overrides[_verify_api_key] = _override_key

        mock_verifier = MagicMock()

        try:
            with (
                patch(
                    "enhanced_agent_bus.api.routes.z3._get_verifier",
                    return_value=mock_verifier,
                ),
                patch.object(
                    importlib,
                    "import_module",
                    side_effect=RuntimeError("Z3 crash"),
                ),
            ):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    resp = await client.post(
                        "/api/v1/z3/verify",
                        json={"policy_id": "p1"},
                        headers={"X-API-Key": "test-key"},
                    )

            assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()

    async def test_metrics_with_recent_results(self):
        """Metrics endpoint includes recent verification results."""
        import httpx

        from enhanced_agent_bus.api.routes.z3 import _record_result

        app = self._make_app()

        _record_result({"id": "r1"}, "general", True, 5.0)
        _record_result({"id": "r2"}, "constitutional", False, 10.0)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/z3/metrics")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["recent_verifications"]) == 2
        assert data["metrics"]["total_verifications"] == 2
