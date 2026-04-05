# Constitutional Hash: 608508a9bd224290
"""Comprehensive tests for session_context.py targeting >=98% coverage."""

from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.enums import RiskLevel
from enhanced_agent_bus.session_context import (
    _SESSION_CONTEXT_OPERATION_ERRORS,
    DUAL_READ_MIGRATION_ENABLED,
    SessionContext,
    SessionContextManager,
    SessionContextStore,
)
from enhanced_agent_bus.session_models import SessionGovernanceConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_governance_config(
    session_id: str = "sess-1", tenant_id: str = "t1"
) -> SessionGovernanceConfig:
    return SessionGovernanceConfig(session_id=session_id, tenant_id=tenant_id)


def _make_session_context(
    session_id: str = "sess-1",
    tenant_id: str = "t1",
    expires_at: datetime | None = None,
) -> SessionContext:
    gov = _make_governance_config(session_id=session_id, tenant_id=tenant_id)
    return SessionContext(
        session_id=session_id,
        tenant_id=tenant_id,
        governance_config=gov,
        expires_at=expires_at,
    )


def _make_mock_redis() -> AsyncMock:
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
    r.setex = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=1)
    r.exists = AsyncMock(return_value=1)
    r.expire = AsyncMock(return_value=1)
    r.ttl = AsyncMock(return_value=300)
    r.close = AsyncMock()
    return r


# ---------------------------------------------------------------------------
# _SESSION_CONTEXT_OPERATION_ERRORS
# ---------------------------------------------------------------------------


class TestSessionContextOperationErrors:
    def test_contains_expected_types(self) -> None:
        for exc_type in (
            RuntimeError,
            ValueError,
            TypeError,
            AttributeError,
            LookupError,
            OSError,
            TimeoutError,
            ConnectionError,
            json.JSONDecodeError,
        ):
            assert exc_type in _SESSION_CONTEXT_OPERATION_ERRORS


# ---------------------------------------------------------------------------
# DUAL_READ_MIGRATION_ENABLED
# ---------------------------------------------------------------------------


class TestDualReadMigrationEnabled:
    def test_is_bool(self) -> None:
        assert isinstance(DUAL_READ_MIGRATION_ENABLED, bool)

    def test_default_true(self) -> None:
        with patch.dict("os.environ", {"SESSION_DUAL_READ_MIGRATION": "true"}):
            import importlib

            import enhanced_agent_bus.session_context as sc_mod

            importlib.reload(sc_mod)
            assert sc_mod.DUAL_READ_MIGRATION_ENABLED is True

    def test_false_when_disabled(self) -> None:
        with patch.dict("os.environ", {"SESSION_DUAL_READ_MIGRATION": "false"}):
            import importlib

            import enhanced_agent_bus.session_context as sc_mod

            importlib.reload(sc_mod)
            assert sc_mod.DUAL_READ_MIGRATION_ENABLED is False

    def test_truthy_one(self) -> None:
        with patch.dict("os.environ", {"SESSION_DUAL_READ_MIGRATION": "1"}):
            import importlib

            import enhanced_agent_bus.session_context as sc_mod

            importlib.reload(sc_mod)
            assert sc_mod.DUAL_READ_MIGRATION_ENABLED is True

    def test_truthy_yes(self) -> None:
        with patch.dict("os.environ", {"SESSION_DUAL_READ_MIGRATION": "yes"}):
            import importlib

            import enhanced_agent_bus.session_context as sc_mod

            importlib.reload(sc_mod)
            assert sc_mod.DUAL_READ_MIGRATION_ENABLED is True


# ---------------------------------------------------------------------------
# SessionContext model
# ---------------------------------------------------------------------------


class TestSessionContext:
    def test_default_fields(self) -> None:
        ctx = _make_session_context()
        assert ctx.session_id == "sess-1"
        assert ctx.tenant_id == "t1"
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH
        assert ctx.metadata == {}
        assert ctx.expires_at is None

    def test_auto_generated_session_id(self) -> None:
        gov = _make_governance_config()
        ctx = SessionContext(tenant_id="t1", governance_config=gov)
        assert ctx.session_id  # non-empty UUID

    def test_constitutional_hash_mismatch_raises(self) -> None:
        gov = _make_governance_config()
        with pytest.raises(ValueError, match="Constitutional hash mismatch"):
            SessionContext(
                tenant_id="t1",
                governance_config=gov,
                constitutional_hash="deadbeefdeadbeef",
            )

    def test_to_dict_no_expires(self) -> None:
        ctx = _make_session_context()
        d = ctx.to_dict()
        assert d["session_id"] == "sess-1"
        assert d["tenant_id"] == "t1"
        assert d["expires_at"] is None
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert isinstance(d["governance_config"], dict)
        assert isinstance(d["created_at"], str)

    def test_to_dict_with_expires(self) -> None:
        exp = datetime.now(UTC) + timedelta(hours=1)
        ctx = _make_session_context(expires_at=exp)
        d = ctx.to_dict()
        assert d["expires_at"] == exp.isoformat()

    def test_from_dict_round_trip(self) -> None:
        ctx = _make_session_context()
        d = ctx.to_dict()
        ctx2 = SessionContext.from_dict(d)
        assert ctx2.session_id == ctx.session_id
        assert ctx2.tenant_id == ctx.tenant_id
        assert ctx2.constitutional_hash == CONSTITUTIONAL_HASH

    def test_from_dict_no_expires_at_key(self) -> None:
        ctx = _make_session_context()
        d = ctx.to_dict()
        d.pop("expires_at")
        ctx2 = SessionContext.from_dict(d)
        assert ctx2.expires_at is None

    def test_from_dict_with_expires_at(self) -> None:
        exp = datetime.now(UTC) + timedelta(hours=2)
        ctx = _make_session_context(expires_at=exp)
        d = ctx.to_dict()
        ctx2 = SessionContext.from_dict(d)
        assert ctx2.expires_at is not None

    def test_from_dict_missing_constitutional_hash_uses_default(self) -> None:
        ctx = _make_session_context()
        d = ctx.to_dict()
        del d["constitutional_hash"]
        ctx2 = SessionContext.from_dict(d)
        assert ctx2.constitutional_hash == CONSTITUTIONAL_HASH

    def test_metadata_custom(self) -> None:
        gov = _make_governance_config()
        ctx = SessionContext(
            session_id="s1",
            tenant_id="t1",
            governance_config=gov,
            metadata={"key": "value"},
        )
        assert ctx.metadata == {"key": "value"}


# ---------------------------------------------------------------------------
# SessionContextStore
# ---------------------------------------------------------------------------


class TestSessionContextStoreInit:
    def test_defaults(self) -> None:
        store = SessionContextStore()
        assert store.redis_url == "redis://localhost:6379"
        assert store.key_prefix == "acgs:session"
        assert store.default_ttl == 3600
        assert store.redis_client is None

    def test_custom_args(self) -> None:
        store = SessionContextStore(
            redis_url="redis://other:6380",
            key_prefix="custom",
            default_ttl=60,
        )
        assert store.redis_url == "redis://other:6380"
        assert store.key_prefix == "custom"
        assert store.default_ttl == 60

    def test_make_key(self) -> None:
        store = SessionContextStore()
        key = store._make_key("sid", "tid")
        assert key == "acgs:session:t:tid:sid"

    def test_make_legacy_key(self) -> None:
        store = SessionContextStore()
        key = store._make_legacy_key("sid")
        assert key == "acgs:session:sid"


class TestSessionContextStoreConnect:
    async def test_connect_success(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        with (
            patch("enhanced_agent_bus.session_context.aioredis") as mock_aioredis,
            patch("enhanced_agent_bus.session_context.REDIS_AVAILABLE", True),
        ):
            mock_aioredis.from_url.return_value = mock_redis
            result = await store.connect()
        assert result is True
        assert store.redis_client is mock_redis

    async def test_connect_redis_not_available(self) -> None:
        store = SessionContextStore()
        with patch("enhanced_agent_bus.session_context.REDIS_AVAILABLE", False):
            result = await store.connect()
        assert result is False
        assert store.redis_client is None

    async def test_connect_connection_error(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.ping.side_effect = ConnectionError("refused")
        with (
            patch("enhanced_agent_bus.session_context.aioredis") as mock_aioredis,
            patch("enhanced_agent_bus.session_context.REDIS_AVAILABLE", True),
        ):
            mock_aioredis.from_url.return_value = mock_redis
            result = await store.connect()
        assert result is False
        assert store.redis_client is None

    async def test_connect_os_error(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.ping.side_effect = OSError("io error")
        with (
            patch("enhanced_agent_bus.session_context.aioredis") as mock_aioredis,
            patch("enhanced_agent_bus.session_context.REDIS_AVAILABLE", True),
        ):
            mock_aioredis.from_url.return_value = mock_redis
            result = await store.connect()
        assert result is False

    async def test_connect_redis_error(self) -> None:
        import redis.exceptions

        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.ping.side_effect = redis.exceptions.RedisError("generic")
        with (
            patch("enhanced_agent_bus.session_context.aioredis") as mock_aioredis,
            patch("enhanced_agent_bus.session_context.REDIS_AVAILABLE", True),
        ):
            mock_aioredis.from_url.return_value = mock_redis
            result = await store.connect()
        assert result is False


class TestSessionContextStoreDisconnect:
    async def test_disconnect_with_client(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        store.redis_client = mock_redis
        await store.disconnect()
        mock_redis.close.assert_awaited_once()
        assert store.redis_client is None

    async def test_disconnect_without_client(self) -> None:
        store = SessionContextStore()
        await store.disconnect()  # Should not raise


class TestSessionContextStoreSet:
    async def test_set_with_ttl(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        store.redis_client = mock_redis
        ctx = _make_session_context()
        result = await store.set(ctx, ttl=60)
        assert result is True
        mock_redis.setex.assert_awaited_once()

    async def test_set_without_ttl_uses_default(self) -> None:
        store = SessionContextStore(default_ttl=120)
        mock_redis = _make_mock_redis()
        store.redis_client = mock_redis
        ctx = _make_session_context()
        result = await store.set(ctx, ttl=None)
        assert result is True
        mock_redis.setex.assert_awaited_once()

    async def test_set_ttl_zero_uses_plain_set(self) -> None:
        store = SessionContextStore(default_ttl=0)
        mock_redis = _make_mock_redis()
        store.redis_client = mock_redis
        ctx = _make_session_context()
        result = await store.set(ctx, ttl=0)
        assert result is True
        mock_redis.set.assert_awaited_once()
        mock_redis.setex.assert_not_awaited()

    async def test_set_no_redis_client(self) -> None:
        store = SessionContextStore()
        ctx = _make_session_context()
        result = await store.set(ctx)
        assert result is False

    async def test_set_connection_error(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.setex.side_effect = ConnectionError("err")
        store.redis_client = mock_redis
        ctx = _make_session_context()
        result = await store.set(ctx, ttl=30)
        assert result is False

    async def test_set_os_error(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.setex.side_effect = OSError("io")
        store.redis_client = mock_redis
        ctx = _make_session_context()
        result = await store.set(ctx, ttl=30)
        assert result is False

    async def test_set_type_error(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.setex.side_effect = TypeError("type err")
        store.redis_client = mock_redis
        ctx = _make_session_context()
        result = await store.set(ctx, ttl=30)
        assert result is False

    async def test_set_updates_expires_at_when_ttl_positive(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        store.redis_client = mock_redis
        ctx = _make_session_context()
        before = datetime.now(UTC)
        await store.set(ctx, ttl=3600)
        assert ctx.expires_at is not None
        assert ctx.expires_at > before


class TestSessionContextStoreGet:
    async def test_get_success(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        store.redis_client = mock_redis
        ctx = _make_session_context()
        mock_redis.get.return_value = json.dumps(ctx.to_dict())
        result = await store.get("sess-1", "t1")
        assert result is not None
        assert result.session_id == "sess-1"

    async def test_get_no_redis_client(self) -> None:
        store = SessionContextStore()
        result = await store.get("sess-1", "t1")
        assert result is None

    async def test_get_key_not_found_returns_none(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.get.return_value = None
        store.redis_client = mock_redis
        with patch("enhanced_agent_bus.session_context.DUAL_READ_MIGRATION_ENABLED", False):
            result = await store.get("unknown-session", "t1")
        assert result is None

    async def test_get_dual_read_migration_finds_legacy_key(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        store.redis_client = mock_redis
        ctx = _make_session_context()
        mock_redis.get.side_effect = [None, json.dumps(ctx.to_dict())]
        with patch("enhanced_agent_bus.session_context.DUAL_READ_MIGRATION_ENABLED", True):
            result = await store.get("sess-1", "t1")
        assert result is not None
        assert result.session_id == "sess-1"

    async def test_get_dual_read_both_miss(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.get.return_value = None
        store.redis_client = mock_redis
        with patch("enhanced_agent_bus.session_context.DUAL_READ_MIGRATION_ENABLED", True):
            result = await store.get("missing", "t1")
        assert result is None

    async def test_get_tenant_mismatch_returns_none(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        store.redis_client = mock_redis
        ctx = _make_session_context(tenant_id="t1")
        mock_redis.get.return_value = json.dumps(ctx.to_dict())
        result = await store.get("sess-1", "other")
        assert result is None

    async def test_get_expired_session_deletes_and_returns_none(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        store.redis_client = mock_redis
        exp = datetime.now(UTC) - timedelta(seconds=1)
        ctx = _make_session_context(expires_at=exp)
        mock_redis.get.return_value = json.dumps(ctx.to_dict())
        mock_redis.delete.return_value = 1
        result = await store.get("sess-1", "t1")
        assert result is None
        mock_redis.delete.assert_awaited_once()

    async def test_get_no_expires_at_returns_session(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        store.redis_client = mock_redis
        ctx = _make_session_context()
        mock_redis.get.return_value = json.dumps(ctx.to_dict())
        result = await store.get("sess-1", "t1")
        assert result is not None

    async def test_get_connection_error_returns_none(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.get.side_effect = ConnectionError("conn err")
        store.redis_client = mock_redis
        result = await store.get("sess-1", "t1")
        assert result is None

    async def test_get_json_decode_error_returns_none(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.get.return_value = "not valid json{"
        store.redis_client = mock_redis
        result = await store.get("sess-1", "t1")
        assert result is None

    async def test_get_value_error_returns_none(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.get.side_effect = ValueError("val err")
        store.redis_client = mock_redis
        result = await store.get("sess-1", "t1")
        assert result is None

    async def test_get_os_error_returns_none(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.get.side_effect = OSError("io")
        store.redis_client = mock_redis
        result = await store.get("sess-1", "t1")
        assert result is None


class TestSessionContextStoreDelete:
    async def test_delete_success(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.delete.return_value = 1
        store.redis_client = mock_redis
        result = await store.delete("sess-1", "t1")
        assert result is True

    async def test_delete_not_found(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.delete.return_value = 0
        store.redis_client = mock_redis
        result = await store.delete("missing", "t1")
        assert result is False

    async def test_delete_no_redis_client(self) -> None:
        store = SessionContextStore()
        result = await store.delete("sess-1", "t1")
        assert result is False

    async def test_delete_connection_error(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.delete.side_effect = ConnectionError("err")
        store.redis_client = mock_redis
        result = await store.delete("sess-1", "t1")
        assert result is False

    async def test_delete_os_error(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.delete.side_effect = OSError("io")
        store.redis_client = mock_redis
        result = await store.delete("sess-1", "t1")
        assert result is False


class TestSessionContextStoreExists:
    async def test_exists_true(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.exists.return_value = 1
        store.redis_client = mock_redis
        result = await store.exists("sess-1", "t1")
        assert result is True

    async def test_exists_false(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.exists.return_value = 0
        store.redis_client = mock_redis
        result = await store.exists("sess-1", "t1")
        assert result is False

    async def test_exists_no_redis_client(self) -> None:
        store = SessionContextStore()
        result = await store.exists("sess-1", "t1")
        assert result is False

    async def test_exists_connection_error(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.exists.side_effect = ConnectionError("err")
        store.redis_client = mock_redis
        result = await store.exists("sess-1", "t1")
        assert result is False

    async def test_exists_os_error(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.exists.side_effect = OSError("io")
        store.redis_client = mock_redis
        result = await store.exists("sess-1", "t1")
        assert result is False


class TestSessionContextStoreUpdateTtl:
    async def test_update_ttl_success(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.expire.return_value = 1
        store.redis_client = mock_redis
        result = await store.update_ttl("sess-1", "t1", 600)
        assert result is True

    async def test_update_ttl_key_not_found(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.expire.return_value = 0
        store.redis_client = mock_redis
        result = await store.update_ttl("missing", "t1", 600)
        assert result is False

    async def test_update_ttl_no_redis_client(self) -> None:
        store = SessionContextStore()
        result = await store.update_ttl("sess-1", "t1", 600)
        assert result is False

    async def test_update_ttl_connection_error(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.expire.side_effect = ConnectionError("err")
        store.redis_client = mock_redis
        result = await store.update_ttl("sess-1", "t1", 600)
        assert result is False

    async def test_update_ttl_os_error(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.expire.side_effect = OSError("io")
        store.redis_client = mock_redis
        result = await store.update_ttl("sess-1", "t1", 600)
        assert result is False

    async def test_update_ttl_logs_debug_on_success(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.expire.return_value = 1
        store.redis_client = mock_redis
        with patch("enhanced_agent_bus.session_context.logger") as mock_log:
            result = await store.update_ttl("sess-1", "t1", 600)
        assert result is True
        mock_log.debug.assert_called()


class TestSessionContextStoreGetTtl:
    async def test_get_ttl_success(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.ttl.return_value = 300
        store.redis_client = mock_redis
        result = await store.get_ttl("sess-1", "t1")
        assert result == 300

    async def test_get_ttl_no_ttl_returns_none(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.ttl.return_value = -1
        store.redis_client = mock_redis
        result = await store.get_ttl("sess-1", "t1")
        assert result is None

    async def test_get_ttl_key_not_exist_returns_none(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.ttl.return_value = -2
        store.redis_client = mock_redis
        result = await store.get_ttl("sess-1", "t1")
        assert result is None

    async def test_get_ttl_no_redis_client(self) -> None:
        store = SessionContextStore()
        result = await store.get_ttl("sess-1", "t1")
        assert result is None

    async def test_get_ttl_connection_error(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.ttl.side_effect = ConnectionError("err")
        store.redis_client = mock_redis
        result = await store.get_ttl("sess-1", "t1")
        assert result is None

    async def test_get_ttl_os_error(self) -> None:
        store = SessionContextStore()
        mock_redis = _make_mock_redis()
        mock_redis.ttl.side_effect = OSError("io")
        store.redis_client = mock_redis
        result = await store.get_ttl("sess-1", "t1")
        assert result is None


# ---------------------------------------------------------------------------
# SessionContextManager
# ---------------------------------------------------------------------------


class TestSessionContextManagerInit:
    def test_default_init(self) -> None:
        mgr = SessionContextManager()
        assert mgr.cache_size == 1000
        assert mgr.cache_ttl == 300
        assert mgr.default_session_ttl == 3600
        assert mgr.store is not None
        assert mgr.store.redis_url == "redis://localhost:6379"

    def test_custom_store(self) -> None:
        store = SessionContextStore(redis_url="redis://custom:6379")
        mgr = SessionContextManager(store=store)
        assert mgr.store is store

    def test_metrics_initialized(self) -> None:
        mgr = SessionContextManager()
        m = mgr._metrics
        for key in (
            "cache_hits",
            "cache_misses",
            "creates",
            "reads",
            "updates",
            "deletes",
            "errors",
        ):
            assert m[key] == 0

    def test_cache_initially_empty(self) -> None:
        mgr = SessionContextManager()
        assert len(mgr._cache) == 0


class TestSessionContextManagerConnect:
    async def test_connect_delegates_to_store(self) -> None:
        mgr = SessionContextManager()
        mgr.store.connect = AsyncMock(return_value=True)
        result = await mgr.connect()
        assert result is True
        mgr.store.connect.assert_awaited_once()

    async def test_disconnect_delegates_to_store(self) -> None:
        mgr = SessionContextManager()
        mgr.store.disconnect = AsyncMock()
        await mgr.disconnect()
        mgr.store.disconnect.assert_awaited_once()


class TestSessionContextManagerIsCacheValid:
    def test_not_in_cache_returns_false(self) -> None:
        mgr = SessionContextManager()
        assert mgr._is_cache_valid("not-there") is False

    def test_fresh_entry_returns_true(self) -> None:
        mgr = SessionContextManager(cache_ttl=300)
        ctx = _make_session_context()
        mgr._update_cache(ctx)
        cache_key = f"{ctx.tenant_id}:{ctx.session_id}"
        assert mgr._is_cache_valid(cache_key) is True

    def test_expired_entry_returns_false(self) -> None:
        mgr = SessionContextManager(cache_ttl=300)
        ctx = _make_session_context()
        mgr._update_cache(ctx)
        cache_key = f"{ctx.tenant_id}:{ctx.session_id}"
        # Set timestamp far in the past to simulate expiry
        mgr._cache_timestamps[cache_key] = time.monotonic() - 999
        assert mgr._is_cache_valid(cache_key) is False


class TestSessionContextManagerUpdateCache:
    def test_update_cache_adds_entry(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr._update_cache(ctx)
        assert len(mgr._cache) == 1

    def test_update_cache_lru_eviction(self) -> None:
        mgr = SessionContextManager(cache_size=2)
        ctx1 = _make_session_context(session_id="s1")
        ctx2 = _make_session_context(session_id="s2")
        ctx3 = _make_session_context(session_id="s3")
        mgr._update_cache(ctx1)
        mgr._update_cache(ctx2)
        mgr._update_cache(ctx3)
        assert len(mgr._cache) == 2
        assert "t1:s1" not in mgr._cache

    def test_update_cache_cleans_lock_on_eviction(self) -> None:
        mgr = SessionContextManager(cache_size=1)
        ctx1 = _make_session_context(session_id="s1")
        ctx2 = _make_session_context(session_id="s2")
        # Pre-create lock for s1
        _ = mgr._session_locks["t1:s1"]
        mgr._update_cache(ctx1)
        mgr._update_cache(ctx2)
        assert "t1:s1" not in mgr._session_locks

    def test_update_cache_moves_to_end(self) -> None:
        mgr = SessionContextManager(cache_size=10)
        ctx1 = _make_session_context(session_id="s1")
        ctx2 = _make_session_context(session_id="s2")
        mgr._update_cache(ctx1)
        mgr._update_cache(ctx2)
        mgr._update_cache(ctx1)
        keys = list(mgr._cache.keys())
        assert keys[-1] == "t1:s1"


class TestSessionContextManagerInvalidateCache:
    def test_invalidate_removes_entry(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr._update_cache(ctx)
        mgr._invalidate_cache("sess-1", "t1")
        assert "t1:sess-1" not in mgr._cache

    def test_invalidate_removes_timestamp(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr._update_cache(ctx)
        mgr._invalidate_cache("sess-1", "t1")
        assert "t1:sess-1" not in mgr._cache_timestamps

    def test_invalidate_removes_lock(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        _ = mgr._session_locks["t1:sess-1"]
        mgr._update_cache(ctx)
        mgr._invalidate_cache("sess-1", "t1")
        assert "t1:sess-1" not in mgr._session_locks

    def test_invalidate_missing_key_no_error(self) -> None:
        mgr = SessionContextManager()
        mgr._invalidate_cache("never-stored", "t1")  # Should not raise


class TestSessionContextManagerCreate:
    async def test_create_success(self) -> None:
        mgr = SessionContextManager()
        mgr.store.exists = AsyncMock(return_value=False)
        mgr.store.set = AsyncMock(return_value=True)
        gov = _make_governance_config()
        ctx = await mgr.create(gov, "t1")
        assert ctx.tenant_id == "t1"
        assert mgr._metrics["creates"] == 1

    async def test_create_with_explicit_session_id(self) -> None:
        mgr = SessionContextManager()
        mgr.store.exists = AsyncMock(return_value=False)
        mgr.store.set = AsyncMock(return_value=True)
        gov = _make_governance_config()
        ctx = await mgr.create(gov, "t1", session_id="explicit-id")
        assert ctx.session_id == "explicit-id"

    async def test_create_with_metadata(self) -> None:
        mgr = SessionContextManager()
        mgr.store.exists = AsyncMock(return_value=False)
        mgr.store.set = AsyncMock(return_value=True)
        gov = _make_governance_config()
        ctx = await mgr.create(gov, "t1", metadata={"key": "val"})
        assert ctx.metadata == {"key": "val"}

    async def test_create_with_explicit_ttl(self) -> None:
        mgr = SessionContextManager()
        mgr.store.exists = AsyncMock(return_value=False)
        mgr.store.set = AsyncMock(return_value=True)
        gov = _make_governance_config()
        ctx = await mgr.create(gov, "t1", ttl=7200)
        assert ctx is not None

    async def test_create_already_exists_raises(self) -> None:
        mgr = SessionContextManager()
        mgr.store.exists = AsyncMock(return_value=True)
        gov = _make_governance_config()
        with pytest.raises(ValueError, match="already exists"):
            await mgr.create(gov, "t1", session_id="dup-id")
        assert mgr._metrics["errors"] == 1

    async def test_create_store_set_fails_raises(self) -> None:
        mgr = SessionContextManager()
        mgr.store.exists = AsyncMock(return_value=False)
        mgr.store.set = AsyncMock(return_value=False)
        gov = _make_governance_config()
        with pytest.raises(RuntimeError, match="Failed to store session context"):
            await mgr.create(gov, "t1")
        assert mgr._metrics["errors"] == 1

    async def test_create_increments_errors_on_operation_errors(self) -> None:
        mgr = SessionContextManager()
        mgr.store.exists = AsyncMock(side_effect=ConnectionError("fail"))
        gov = _make_governance_config()
        with pytest.raises(ConnectionError):
            await mgr.create(gov, "t1")
        assert mgr._metrics["errors"] == 1


class TestSessionContextManagerGet:
    async def test_get_from_cache(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr._update_cache(ctx)
        result = await mgr.get("sess-1", "t1")
        assert result is not None
        assert result.session_id == "sess-1"
        assert mgr._metrics["cache_hits"] == 1

    async def test_get_cache_miss_fetches_from_store(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr.store.get = AsyncMock(return_value=ctx)
        result = await mgr.get("sess-1", "t1")
        assert result is not None
        assert mgr._metrics["cache_misses"] == 1

    async def test_get_not_found_returns_none(self) -> None:
        mgr = SessionContextManager()
        mgr.store.get = AsyncMock(return_value=None)
        result = await mgr.get("missing", "t1")
        assert result is None

    async def test_get_populates_cache_on_miss(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr.store.get = AsyncMock(return_value=ctx)
        await mgr.get("sess-1", "t1")
        assert "t1:sess-1" in mgr._cache

    async def test_get_internal_error_increments_errors(self) -> None:
        mgr = SessionContextManager()
        mgr.store.get = AsyncMock(side_effect=ConnectionError("fail"))
        result = await mgr.get("sess-1", "t1")
        assert result is None
        assert mgr._metrics["errors"] == 1


class TestSessionContextManagerUpdate:
    async def test_update_success_with_new_config(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr.store.get = AsyncMock(return_value=ctx)
        mgr.store.set = AsyncMock(return_value=True)
        new_gov = _make_governance_config()
        result = await mgr.update("sess-1", "t1", governance_config=new_gov)
        assert result is not None
        assert mgr._metrics["updates"] == 1

    async def test_update_with_metadata_merges(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        ctx.metadata = {"existing": "data"}
        mgr.store.get = AsyncMock(return_value=ctx)
        mgr.store.set = AsyncMock(return_value=True)
        result = await mgr.update("sess-1", "t1", metadata={"new": "field"})
        assert result is not None
        assert result.metadata.get("existing") == "data"
        assert result.metadata.get("new") == "field"

    async def test_update_no_metadata_arg_keeps_existing(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        ctx.metadata = {"keep": "this"}
        mgr.store.get = AsyncMock(return_value=ctx)
        mgr.store.set = AsyncMock(return_value=True)
        result = await mgr.update("sess-1", "t1")
        assert result is not None
        assert result.metadata == {"keep": "this"}

    async def test_update_not_found_returns_none(self) -> None:
        mgr = SessionContextManager()
        mgr.store.get = AsyncMock(return_value=None)
        result = await mgr.update("missing", "t1")
        assert result is None

    async def test_update_store_set_fails_returns_none(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr.store.get = AsyncMock(return_value=ctx)
        mgr.store.set = AsyncMock(return_value=False)
        result = await mgr.update("sess-1", "t1")
        assert result is None

    async def test_update_with_ttl(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr.store.get = AsyncMock(return_value=ctx)
        mgr.store.set = AsyncMock(return_value=True)
        result = await mgr.update("sess-1", "t1", ttl=7200)
        assert result is not None

    async def test_update_error_increments_metrics(self) -> None:
        mgr = SessionContextManager()
        mgr.store.get = AsyncMock(side_effect=ConnectionError("fail"))
        result = await mgr.update("sess-1", "t1")
        assert result is None
        assert mgr._metrics["errors"] == 1

    async def test_update_invalidates_and_refreshes_cache(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr._update_cache(ctx)
        mgr.store.get = AsyncMock(return_value=ctx)
        mgr.store.set = AsyncMock(return_value=True)
        await mgr.update("sess-1", "t1")
        assert "t1:sess-1" in mgr._cache


class TestSessionContextManagerDelete:
    async def test_delete_success(self) -> None:
        mgr = SessionContextManager()
        mgr.store.delete = AsyncMock(return_value=True)
        result = await mgr.delete("sess-1", "t1")
        assert result is True
        assert mgr._metrics["deletes"] == 1

    async def test_delete_not_found(self) -> None:
        mgr = SessionContextManager()
        mgr.store.delete = AsyncMock(return_value=False)
        result = await mgr.delete("missing", "t1")
        assert result is False

    async def test_delete_removes_from_cache(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr._update_cache(ctx)
        mgr.store.delete = AsyncMock(return_value=True)
        await mgr.delete("sess-1", "t1")
        assert "t1:sess-1" not in mgr._cache

    async def test_delete_error_increments_metrics(self) -> None:
        mgr = SessionContextManager()
        mgr.store.delete = AsyncMock(side_effect=ConnectionError("fail"))
        result = await mgr.delete("sess-1", "t1")
        assert result is False
        assert mgr._metrics["errors"] == 1


class TestSessionContextManagerExists:
    async def test_exists_from_cache(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr._update_cache(ctx)
        result = await mgr.exists("sess-1", "t1")
        assert result is True

    async def test_exists_from_store(self) -> None:
        mgr = SessionContextManager()
        mgr.store.exists = AsyncMock(return_value=True)
        result = await mgr.exists("sess-1", "t1")
        assert result is True
        mgr.store.exists.assert_awaited_once()

    async def test_exists_false_from_store(self) -> None:
        mgr = SessionContextManager()
        mgr.store.exists = AsyncMock(return_value=False)
        result = await mgr.exists("sess-1", "t1")
        assert result is False


class TestSessionContextManagerExtendTtl:
    async def test_extend_ttl_success(self) -> None:
        mgr = SessionContextManager()
        mgr.store.update_ttl = AsyncMock(return_value=True)
        result = await mgr.extend_ttl("sess-1", "t1", 1800)
        assert result is True

    async def test_extend_ttl_failure(self) -> None:
        mgr = SessionContextManager()
        mgr.store.update_ttl = AsyncMock(return_value=False)
        result = await mgr.extend_ttl("sess-1", "t1", 1800)
        assert result is False

    async def test_extend_ttl_logs_on_success(self) -> None:
        mgr = SessionContextManager()
        mgr.store.update_ttl = AsyncMock(return_value=True)
        with patch("enhanced_agent_bus.session_context.logger") as mock_log:
            await mgr.extend_ttl("sess-1", "t1", 1800)
        mock_log.info.assert_called()


class TestSessionContextManagerGetMetrics:
    def test_initial_metrics(self) -> None:
        mgr = SessionContextManager()
        m = mgr.get_metrics()
        assert m["cache_hit_rate"] == 0.0
        assert m["cache_size"] == 0
        assert m["cache_capacity"] == 1000

    def test_cache_hit_rate_calculation(self) -> None:
        mgr = SessionContextManager()
        mgr._metrics["cache_hits"] = 3
        mgr._metrics["cache_misses"] = 1
        m = mgr.get_metrics()
        assert m["cache_hit_rate"] == pytest.approx(0.75)

    def test_cache_size_reflects_current_cache(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr._update_cache(ctx)
        m = mgr.get_metrics()
        assert m["cache_size"] == 1


class TestSessionContextManagerResetMetrics:
    def test_reset_metrics(self) -> None:
        mgr = SessionContextManager()
        mgr._metrics["cache_hits"] = 99
        mgr._metrics["errors"] = 10
        mgr.reset_metrics()
        for v in mgr._metrics.values():
            assert v == 0

    def test_reset_logs(self) -> None:
        mgr = SessionContextManager()
        with patch("enhanced_agent_bus.session_context.logger") as mock_log:
            mgr.reset_metrics()
        mock_log.info.assert_called_with("Metrics reset")


class TestSessionContextManagerClearCache:
    async def test_clear_cache_empties_cache(self) -> None:
        mgr = SessionContextManager()
        ctx = _make_session_context()
        mgr._update_cache(ctx)
        assert len(mgr._cache) == 1
        await mgr.clear_cache()
        assert len(mgr._cache) == 0
        assert len(mgr._cache_timestamps) == 0

    async def test_clear_cache_logs(self) -> None:
        mgr = SessionContextManager()
        with patch("enhanced_agent_bus.session_context.logger") as mock_log:
            await mgr.clear_cache()
        mock_log.info.assert_called_with("Cache cleared")


# ---------------------------------------------------------------------------
# Integration-style: full lifecycle through manager with mocked store
# ---------------------------------------------------------------------------


class TestSessionContextManagerIntegration:
    async def test_create_get_update_delete_lifecycle(self) -> None:
        mgr = SessionContextManager()
        gov = _make_governance_config(session_id="life-sess", tenant_id="tenant-a")
        ctx_stub = SessionContext(
            session_id="life-sess",
            tenant_id="tenant-a",
            governance_config=gov,
        )

        mgr.store.exists = AsyncMock(return_value=False)
        mgr.store.set = AsyncMock(return_value=True)
        mgr.store.get = AsyncMock(return_value=ctx_stub)
        mgr.store.delete = AsyncMock(return_value=True)

        created = await mgr.create(gov, "tenant-a", session_id="life-sess")
        assert created.session_id == "life-sess"

        fetched = await mgr.get("life-sess", "tenant-a")
        assert fetched is not None

        updated = await mgr.update("life-sess", "tenant-a", metadata={"env": "prod"})
        assert updated is not None

        deleted = await mgr.delete("life-sess", "tenant-a")
        assert deleted is True

    async def test_concurrent_creates_same_session_raises(self) -> None:
        mgr = SessionContextManager()
        gov = _make_governance_config(session_id="dup", tenant_id="t1")

        call_count = 0

        async def exists_side_effect(sid: str, tid: str) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count > 1

        mgr.store.exists = AsyncMock(side_effect=exists_side_effect)
        mgr.store.set = AsyncMock(return_value=True)

        ctx1 = await mgr.create(gov, "t1", session_id="dup")
        assert ctx1.session_id == "dup"

        with pytest.raises(ValueError, match="already exists"):
            await mgr.create(gov, "t1", session_id="dup")

    async def test_cache_eviction_multiple_sessions(self) -> None:
        mgr = SessionContextManager(cache_size=3)

        mgr.store.exists = AsyncMock(return_value=False)
        mgr.store.set = AsyncMock(return_value=True)

        for i in range(4):
            gov = _make_governance_config(session_id=f"s{i}", tenant_id="t1")
            await mgr.create(gov, "t1", session_id=f"s{i}")

        assert len(mgr._cache) == 3
        assert "t1:s0" not in mgr._cache


# ---------------------------------------------------------------------------
# Module-level __all__ export
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exported(self) -> None:
        import enhanced_agent_bus.session_context as mod

        assert "SessionContext" in mod.__all__
        assert "SessionContextStore" in mod.__all__
        assert "SessionContextManager" in mod.__all__
