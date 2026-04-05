"""Tests for mcp_integration.auth.token_refresh module.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import OAuth2Token, TokenStatus
from enhanced_agent_bus.mcp_integration.auth.token_refresh import (
    ManagedToken,
    RefreshConfig,
    RefreshResult,
    RefreshStatus,
    TokenRefresher,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token(
    access_token: str = "access-123",
    refresh_token: str | None = "refresh-456",
    expires_in: int | None = 3600,
    needs_refresh: bool = False,
) -> OAuth2Token:
    """Create a test OAuth2Token."""
    token = OAuth2Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )
    if needs_refresh:
        # Set expires_at to a time that needs refresh
        token.expires_at = datetime.now(UTC) + timedelta(seconds=60)
    return token


def _make_provider(new_token: OAuth2Token | None = None) -> AsyncMock:
    """Create a mock OAuth2Provider."""
    provider = AsyncMock()
    provider.refresh_token.return_value = new_token
    return provider


# ---------------------------------------------------------------------------
# RefreshConfig
# ---------------------------------------------------------------------------


class TestRefreshConfig:
    def test_defaults(self):
        config = RefreshConfig()
        assert config.refresh_threshold_seconds == 300
        assert config.check_interval_seconds == 60
        assert config.max_retries == 3
        assert config.max_concurrent_refreshes == 10


# ---------------------------------------------------------------------------
# RefreshResult
# ---------------------------------------------------------------------------


class TestRefreshResult:
    def test_to_dict(self):
        result = RefreshResult(
            token_id="t1",
            status=RefreshStatus.SUCCESS,
            retry_count=1,
            duration_ms=42.5,
        )
        d = result.to_dict()
        assert d["token_id"] == "t1"
        assert d["status"] == "success"
        assert d["retry_count"] == 1
        assert d["has_new_token"] is False
        assert "constitutional_hash" in d

    def test_to_dict_with_new_token(self):
        new_tok = _make_token("new-access")
        result = RefreshResult(
            token_id="t1",
            status=RefreshStatus.SUCCESS,
            new_token=new_tok,
        )
        assert result.to_dict()["has_new_token"] is True


# ---------------------------------------------------------------------------
# RefreshStatus enum
# ---------------------------------------------------------------------------


class TestRefreshStatus:
    def test_values(self):
        assert RefreshStatus.SUCCESS.value == "success"
        assert RefreshStatus.FAILED.value == "failed"
        assert RefreshStatus.NO_REFRESH_TOKEN.value == "no_refresh_token"


# ---------------------------------------------------------------------------
# TokenRefresher - registration
# ---------------------------------------------------------------------------


class TestTokenRefresherRegistration:
    @pytest.mark.asyncio
    async def test_register_token(self):
        refresher = TokenRefresher()
        token = _make_token()
        provider = _make_provider()
        await refresher.register_token("t1", token, provider)
        assert refresher.get_token("t1") is token
        assert refresher._stats["tokens_registered"] == 1

    @pytest.mark.asyncio
    async def test_unregister_token(self):
        refresher = TokenRefresher()
        token = _make_token()
        provider = _make_provider()
        await refresher.register_token("t1", token, provider)
        result = await refresher.unregister_token("t1")
        assert result is True
        assert refresher.get_token("t1") is None

    @pytest.mark.asyncio
    async def test_unregister_missing_token(self):
        refresher = TokenRefresher()
        result = await refresher.unregister_token("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_managed_token(self):
        refresher = TokenRefresher()
        token = _make_token()
        provider = _make_provider()
        await refresher.register_token("t1", token, provider, metadata={"env": "test"})
        managed = refresher.get_managed_token("t1")
        assert managed is not None
        assert managed.metadata == {"env": "test"}

    @pytest.mark.asyncio
    async def test_get_managed_token_missing(self):
        refresher = TokenRefresher()
        assert refresher.get_managed_token("missing") is None


# ---------------------------------------------------------------------------
# TokenRefresher - refresh
# ---------------------------------------------------------------------------


class TestTokenRefresherRefresh:
    @pytest.mark.asyncio
    async def test_refresh_unregistered_token(self):
        refresher = TokenRefresher()
        result = await refresher.refresh_token("nonexistent")
        assert result.status == RefreshStatus.FAILED
        assert "not registered" in result.error

    @pytest.mark.asyncio
    async def test_refresh_no_refresh_token(self):
        refresher = TokenRefresher()
        token = _make_token(refresh_token=None)
        provider = _make_provider()
        await refresher.register_token("t1", token, provider)
        result = await refresher.refresh_token("t1")
        assert result.status == RefreshStatus.NO_REFRESH_TOKEN

    @pytest.mark.asyncio
    async def test_refresh_not_needed(self):
        refresher = TokenRefresher()
        # Token expires far in the future
        token = _make_token(expires_in=7200)
        provider = _make_provider()
        await refresher.register_token("t1", token, provider)
        result = await refresher.refresh_token("t1")
        assert result.status == RefreshStatus.NOT_NEEDED

    @pytest.mark.asyncio
    async def test_force_refresh_success(self):
        refresher = TokenRefresher(RefreshConfig(max_retries=0))
        old_token = _make_token()
        new_token = _make_token("new-access")
        provider = _make_provider(new_token)
        await refresher.register_token("t1", old_token, provider)
        result = await refresher.refresh_token("t1", force=True)
        assert result.status == RefreshStatus.SUCCESS
        assert result.new_token is new_token
        assert refresher._stats["refreshes_successful"] == 1

    @pytest.mark.asyncio
    async def test_force_refresh_returns_none(self):
        refresher = TokenRefresher(RefreshConfig(max_retries=0))
        token = _make_token()
        provider = _make_provider(None)  # returns None
        await refresher.register_token("t1", token, provider)
        result = await refresher.refresh_token("t1", force=True)
        assert result.status == RefreshStatus.FAILED
        assert refresher._stats["refreshes_failed"] == 1

    @pytest.mark.asyncio
    async def test_refresh_with_retry_on_error(self):
        config = RefreshConfig(
            max_retries=1,
            initial_retry_delay_seconds=0.01,
            max_retry_delay_seconds=0.02,
        )
        refresher = TokenRefresher(config)
        token = _make_token(needs_refresh=True)
        provider = AsyncMock()
        new_token = _make_token("refreshed")
        provider.refresh_token.side_effect = [RuntimeError("fail"), new_token]
        await refresher.register_token("t1", token, provider)
        result = await refresher.refresh_token("t1", force=True)
        assert result.status == RefreshStatus.SUCCESS
        assert result.retry_count == 1

    @pytest.mark.asyncio
    async def test_refresh_all_retries_exhausted(self):
        config = RefreshConfig(
            max_retries=1,
            initial_retry_delay_seconds=0.01,
        )
        refresher = TokenRefresher(config)
        token = _make_token(needs_refresh=True)
        provider = AsyncMock()
        provider.refresh_token.side_effect = RuntimeError("always fails")
        on_error = AsyncMock()
        await refresher.register_token("t1", token, provider, on_error=on_error)
        result = await refresher.refresh_token("t1", force=True)
        assert result.status == RefreshStatus.FAILED
        on_error.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_refresh_callback(self):
        refresher = TokenRefresher(RefreshConfig(max_retries=0))
        old_token = _make_token()
        new_token = _make_token("new")
        provider = _make_provider(new_token)
        on_refresh = AsyncMock()
        await refresher.register_token("t1", old_token, provider, on_refresh=on_refresh)
        await refresher.refresh_token("t1", force=True)
        on_refresh.assert_awaited_once()


# ---------------------------------------------------------------------------
# TokenRefresher - list_tokens / get_stats
# ---------------------------------------------------------------------------


class TestTokenRefresherInfo:
    @pytest.mark.asyncio
    async def test_list_tokens(self):
        refresher = TokenRefresher()
        token = _make_token()
        provider = _make_provider()
        await refresher.register_token("t1", token, provider)
        tokens = refresher.list_tokens()
        assert len(tokens) == 1
        assert tokens[0]["token_id"] == "t1"
        assert "has_refresh_token" in tokens[0]

    def test_get_stats(self):
        refresher = TokenRefresher()
        stats = refresher.get_stats()
        assert stats["managed_tokens"] == 0
        assert stats["running"] is False
        assert "config" in stats
        assert "constitutional_hash" in stats


# ---------------------------------------------------------------------------
# TokenRefresher - refresh_all
# ---------------------------------------------------------------------------


class TestRefreshAll:
    @pytest.mark.asyncio
    async def test_refresh_all_force(self):
        refresher = TokenRefresher(RefreshConfig(max_retries=0))
        new_token = _make_token("new")
        for i in range(3):
            token = _make_token(f"old-{i}")
            provider = _make_provider(new_token)
            await refresher.register_token(f"t{i}", token, provider)
        results = await refresher.refresh_all(force=True)
        assert len(results) == 3
        assert all(r.status == RefreshStatus.SUCCESS for r in results)


# ---------------------------------------------------------------------------
# TokenRefresher - start / stop
# ---------------------------------------------------------------------------


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_creates_background_task(self):
        refresher = TokenRefresher()
        await refresher.start()
        assert refresher._running is True
        assert refresher._refresh_task is not None
        await refresher.stop()
        assert refresher._running is False
        assert refresher._refresh_task is None

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        refresher = TokenRefresher()
        await refresher.start()
        task1 = refresher._refresh_task
        await refresher.start()  # should be no-op
        assert refresher._refresh_task is task1
        await refresher.stop()

    @pytest.mark.asyncio
    async def test_start_disabled_background(self):
        config = RefreshConfig(background_refresh_enabled=False)
        refresher = TokenRefresher(config)
        await refresher.start()
        assert refresher._running is True
        assert refresher._refresh_task is None
        await refresher.stop()
