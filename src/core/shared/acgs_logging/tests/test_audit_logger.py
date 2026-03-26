"""
Tests for ACGS-2 Tenant-Scoped Audit Logger.

Covers: AuditEntry, AuditLogConfig, InMemoryAuditStore,
        TenantAuditLogger, RedisAuditStore (mocked), redaction,
        tenant isolation, query filtering, pagination, cleanup,
        factory functions, and error paths.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.shared.acgs_logging.audit_logger import (
    SENSITIVE_FIELDS,
    AuditAction,
    AuditEntry,
    AuditLogConfig,
    AuditLogStore,
    AuditQueryParams,
    AuditQueryResult,
    AuditSeverity,
    InMemoryAuditStore,
    RedisAuditStore,
    TenantAuditLogger,
    create_tenant_audit_logger,
    get_tenant_audit_logger,
)
from src.core.shared.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    tenant_id: str = "tenant-a",
    action: str = AuditAction.CREATE.value,
    severity: str = AuditSeverity.INFO.value,
    resource_type: str | None = "policy",
    resource_id: str | None = "pol-1",
    actor_id: str | None = "user-1",
    outcome: str = "success",
    timestamp: str | None = None,
) -> AuditEntry:
    return AuditEntry(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        timestamp=timestamp or datetime.now(UTC).isoformat(),
        action=action,
        severity=severity,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        outcome=outcome,
    )


def _disabled_config() -> AuditLogConfig:
    return AuditLogConfig(audit_enabled=False)


def _strict_config() -> AuditLogConfig:
    return AuditLogConfig(fail_open=False)


# ===========================================================================
# AuditEntry
# ===========================================================================


class TestAuditEntry:
    def test_to_dict_roundtrip(self):
        entry = _make_entry()
        d = entry.to_dict()
        assert d["tenant_id"] == "tenant-a"
        assert d["action"] == AuditAction.CREATE.value
        reconstructed = AuditEntry.from_dict(d)
        assert reconstructed.id == entry.id
        assert reconstructed.tenant_id == entry.tenant_id

    def test_from_dict_converts_enum_action(self):
        d = {
            "id": "abc",
            "tenant_id": "t",
            "timestamp": "2025-01-01T00:00:00",
            "action": AuditAction.DELETE,
            "severity": AuditSeverity.WARNING,
        }
        entry = AuditEntry.from_dict(d)
        assert entry.action == "delete"
        assert entry.severity == "warning"

    def test_default_constitutional_hash(self):
        entry = _make_entry()
        assert entry.constitutional_hash == CONSTITUTIONAL_HASH

    def test_default_values(self):
        entry = AuditEntry(id="x", tenant_id="t", timestamp="ts", action="create")
        assert entry.severity == AuditSeverity.INFO.value
        assert entry.actor_type == "user"
        assert entry.outcome == "success"
        assert entry.details == {}
        assert entry.error_message is None


# ===========================================================================
# AuditLogConfig
# ===========================================================================


class TestAuditLogConfig:
    def test_defaults(self):
        cfg = AuditLogConfig()
        assert cfg.use_redis is False
        assert cfg.retention_days == 90
        assert cfg.enable_redaction is True
        assert cfg.fail_open is True
        assert cfg.audit_enabled is True
        assert cfg.max_entries_per_tenant == 100000

    def test_from_env(self):
        env = {
            "REDIS_URL": "redis://custom:6380/1",
            "AUDIT_USE_REDIS": "true",
            "AUDIT_MAX_ENTRIES_PER_TENANT": "500",
            "AUDIT_RETENTION_DAYS": "30",
            "AUDIT_ENABLE_REDACTION": "false",
            "AUDIT_ENABLE_COMPRESSION": "true",
            "AUDIT_ENABLED": "false",
            "AUDIT_FAIL_OPEN": "false",
            "AUDIT_KEY_PREFIX": "custom:audit",
        }
        with patch.dict("os.environ", env, clear=False):
            cfg = AuditLogConfig.from_env()
        assert cfg.redis_url == "redis://custom:6380/1"
        assert cfg.use_redis is True
        assert cfg.max_entries_per_tenant == 500
        assert cfg.retention_days == 30
        assert cfg.enable_redaction is False
        assert cfg.enable_compression is True
        assert cfg.audit_enabled is False
        assert cfg.fail_open is False
        assert cfg.key_prefix == "custom:audit"

    def test_from_env_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            cfg = AuditLogConfig.from_env()
        assert cfg.use_redis is False
        assert cfg.audit_enabled is True


# ===========================================================================
# InMemoryAuditStore
# ===========================================================================


class TestInMemoryAuditStore:
    @pytest.fixture
    def store(self) -> InMemoryAuditStore:
        return InMemoryAuditStore(max_entries_per_tenant=5)

    @pytest.mark.asyncio
    async def test_store_and_count(self, store: InMemoryAuditStore):
        entry = _make_entry()
        assert await store.store(entry) is True
        assert await store.count("tenant-a") == 1

    @pytest.mark.asyncio
    async def test_count_missing_tenant(self, store: InMemoryAuditStore):
        assert await store.count("nonexistent") == 0

    @pytest.mark.asyncio
    async def test_max_entries_enforcement(self, store: InMemoryAuditStore):
        for i in range(8):
            await store.store(_make_entry(resource_id=f"r-{i}"))
        assert await store.count("tenant-a") == 5

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, store: InMemoryAuditStore):
        await store.store(_make_entry(tenant_id="t1"))
        await store.store(_make_entry(tenant_id="t2"))
        assert await store.count("t1") == 1
        assert await store.count("t2") == 1
        result = await store.query("t1", AuditQueryParams())
        assert all(e.tenant_id == "t1" for e in result.entries)

    @pytest.mark.asyncio
    async def test_query_filter_action(self, store: InMemoryAuditStore):
        await store.store(_make_entry(action=AuditAction.CREATE.value))
        await store.store(_make_entry(action=AuditAction.DELETE.value))
        result = await store.query("tenant-a", AuditQueryParams(action=AuditAction.DELETE))
        assert result.total_count == 1
        assert result.entries[0].action == "delete"

    @pytest.mark.asyncio
    async def test_query_filter_resource_type(self, store: InMemoryAuditStore):
        await store.store(_make_entry(resource_type="policy"))
        await store.store(_make_entry(resource_type="agent"))
        result = await store.query("tenant-a", AuditQueryParams(resource_type="agent"))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_filter_resource_id(self, store: InMemoryAuditStore):
        await store.store(_make_entry(resource_id="r1"))
        await store.store(_make_entry(resource_id="r2"))
        result = await store.query("tenant-a", AuditQueryParams(resource_id="r1"))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_filter_actor_id(self, store: InMemoryAuditStore):
        await store.store(_make_entry(actor_id="alice"))
        await store.store(_make_entry(actor_id="bob"))
        result = await store.query("tenant-a", AuditQueryParams(actor_id="bob"))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_filter_severity(self, store: InMemoryAuditStore):
        await store.store(_make_entry(severity=AuditSeverity.INFO.value))
        await store.store(_make_entry(severity=AuditSeverity.ERROR.value))
        result = await store.query("tenant-a", AuditQueryParams(severity=AuditSeverity.ERROR))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_filter_outcome(self, store: InMemoryAuditStore):
        await store.store(_make_entry(outcome="success"))
        await store.store(_make_entry(outcome="failure"))
        result = await store.query("tenant-a", AuditQueryParams(outcome="failure"))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_filter_time_range(self, store: InMemoryAuditStore):
        old_ts = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        new_ts = datetime.now(UTC).isoformat()
        await store.store(_make_entry(timestamp=old_ts))
        await store.store(_make_entry(timestamp=new_ts))

        cutoff = datetime.now(UTC) - timedelta(hours=1)
        result = await store.query("tenant-a", AuditQueryParams(start_time=cutoff))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_filter_end_time(self, store: InMemoryAuditStore):
        old_ts = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        new_ts = datetime.now(UTC).isoformat()
        await store.store(_make_entry(timestamp=old_ts))
        await store.store(_make_entry(timestamp=new_ts))

        cutoff = datetime.now(UTC) - timedelta(hours=1)
        result = await store.query("tenant-a", AuditQueryParams(end_time=cutoff))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_pagination(self, store: InMemoryAuditStore):
        for i in range(5):
            await store.store(_make_entry(resource_id=f"r-{i}"))
        result = await store.query("tenant-a", AuditQueryParams(limit=2, offset=0))
        assert len(result.entries) == 2
        assert result.total_count == 5
        assert result.has_more is True

        result2 = await store.query("tenant-a", AuditQueryParams(limit=2, offset=4))
        assert len(result2.entries) == 1
        assert result2.has_more is False

    @pytest.mark.asyncio
    async def test_query_sort_by_action(self, store: InMemoryAuditStore):
        await store.store(_make_entry(action="create"))
        await store.store(_make_entry(action="delete"))
        result = await store.query(
            "tenant-a",
            AuditQueryParams(order_by="action", order_desc=False),
        )
        assert result.entries[0].action == "create"
        assert result.entries[1].action == "delete"

    @pytest.mark.asyncio
    async def test_query_sort_by_severity(self, store: InMemoryAuditStore):
        await store.store(_make_entry(severity="error"))
        await store.store(_make_entry(severity="debug"))
        result = await store.query(
            "tenant-a",
            AuditQueryParams(order_by="severity", order_desc=False),
        )
        assert result.entries[0].severity == "debug"

    @pytest.mark.asyncio
    async def test_cleanup(self, store: InMemoryAuditStore):
        old_ts = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        new_ts = datetime.now(UTC).isoformat()
        await store.store(_make_entry(timestamp=old_ts))
        await store.store(_make_entry(timestamp=new_ts))

        cutoff = datetime.now(UTC) - timedelta(days=50)
        removed = await store.cleanup("tenant-a", cutoff)
        assert removed == 1
        assert await store.count("tenant-a") == 1

    @pytest.mark.asyncio
    async def test_cleanup_missing_tenant(self, store: InMemoryAuditStore):
        removed = await store.cleanup("nonexistent", datetime.now(UTC))
        assert removed == 0

    @pytest.mark.asyncio
    async def test_close_is_noop(self, store: InMemoryAuditStore):
        await store.close()  # should not raise

    def test_get_all_tenant_ids(self):
        store = InMemoryAuditStore()
        store._entries["t1"] = []
        store._entries["t2"] = []
        assert sorted(store.get_all_tenant_ids()) == ["t1", "t2"]


# ===========================================================================
# TenantAuditLogger
# ===========================================================================


class TestTenantAuditLogger:
    @pytest.fixture
    def logger_instance(self) -> TenantAuditLogger:
        cfg = AuditLogConfig(audit_enabled=True, fail_open=True, enable_redaction=True)
        return TenantAuditLogger(config=cfg)

    @pytest.mark.asyncio
    async def test_log_returns_entry_id(self, logger_instance: TenantAuditLogger):
        entry_id = await logger_instance.log(
            tenant_id="tenant-a",
            action=AuditAction.CREATE,
            resource_type="policy",
            resource_id="pol-1",
            actor_id="user-1",
        )
        assert entry_id is not None
        assert len(entry_id) > 0

    @pytest.mark.asyncio
    async def test_log_disabled_returns_none(self):
        lgr = TenantAuditLogger(config=_disabled_config())
        result = await lgr.log(tenant_id="t", action=AuditAction.CREATE)
        assert result is None

    @pytest.mark.asyncio
    async def test_log_with_all_fields(self, logger_instance: TenantAuditLogger):
        entry_id = await logger_instance.log(
            tenant_id="tenant-a",
            action=AuditAction.LOGIN,
            resource_type="session",
            resource_id="sess-1",
            actor_id="user-1",
            actor_type="service",
            client_ip="10.0.0.1",
            user_agent="TestAgent/1.0",
            request_id="req-abc",
            details={"method": "POST"},
            severity=AuditSeverity.WARNING,
            outcome="failure",
            error_message="Bad credentials",
        )
        assert entry_id is not None

        result = await logger_instance.query("tenant-a")
        assert result.total_count == 1
        e = result.entries[0]
        assert e.action == "login"
        assert e.client_ip == "10.0.0.1"
        assert e.user_agent == "TestAgent/1.0"
        assert e.outcome == "failure"
        assert e.error_message == "Bad credentials"

    @pytest.mark.asyncio
    async def test_log_redacts_sensitive_fields(self, logger_instance: TenantAuditLogger):
        entry_id = await logger_instance.log(
            tenant_id="tenant-a",
            action=AuditAction.UPDATE,
            details={
                "username": "alice",
                "password": "s3cret",
                "api_key": "sk-123",
                "nested": {"token": "tok-456", "safe": "ok"},
            },
        )
        assert entry_id is not None
        result = await logger_instance.query("tenant-a")
        details = result.entries[0].details
        assert details["username"] == "alice"
        assert details["password"] == "[REDACTED]"
        assert details["api_key"] == "[REDACTED]"
        assert details["nested"]["token"] == "[REDACTED]"
        assert details["nested"]["safe"] == "ok"

    @pytest.mark.asyncio
    async def test_redaction_disabled(self):
        cfg = AuditLogConfig(enable_redaction=False)
        lgr = TenantAuditLogger(config=cfg)
        await lgr.log(
            tenant_id="t1",
            action=AuditAction.CREATE,
            details={"password": "visible"},
        )
        result = await lgr.query("t1")
        assert result.entries[0].details["password"] == "visible"

    @pytest.mark.asyncio
    async def test_log_invalid_tenant_fail_open(self, logger_instance: TenantAuditLogger):
        result = await logger_instance.log(
            tenant_id="",
            action=AuditAction.CREATE,
        )
        assert result is None  # fail_open=True, returns None

    @pytest.mark.asyncio
    async def test_log_invalid_tenant_fail_closed(self):
        lgr = TenantAuditLogger(config=_strict_config())
        with pytest.raises(ValueError, match="Invalid tenant ID"):
            await lgr.log(tenant_id="", action=AuditAction.CREATE)

    @pytest.mark.asyncio
    async def test_log_store_failure_fail_open(self):
        mock_store = AsyncMock(spec=AuditLogStore)
        mock_store.store.return_value = False
        cfg = AuditLogConfig(fail_open=True)
        lgr = TenantAuditLogger(config=cfg, store=mock_store)
        result = await lgr.log(tenant_id="t1", action=AuditAction.CREATE)
        assert result is None

    @pytest.mark.asyncio
    async def test_log_store_failure_fail_closed(self):
        mock_store = AsyncMock(spec=AuditLogStore)
        mock_store.store.return_value = False
        cfg = AuditLogConfig(fail_open=False)
        lgr = TenantAuditLogger(config=cfg, store=mock_store)
        with pytest.raises(RuntimeError, match="Audit logging failed"):
            await lgr.log(tenant_id="t1", action=AuditAction.CREATE)

    @pytest.mark.asyncio
    async def test_log_store_exception_fail_open(self):
        mock_store = AsyncMock(spec=AuditLogStore)
        mock_store.store.side_effect = OSError("disk full")
        cfg = AuditLogConfig(fail_open=True)
        lgr = TenantAuditLogger(config=cfg, store=mock_store)
        result = await lgr.log(tenant_id="t1", action=AuditAction.CREATE)
        assert result is None

    @pytest.mark.asyncio
    async def test_log_store_exception_fail_closed(self):
        mock_store = AsyncMock(spec=AuditLogStore)
        mock_store.store.side_effect = OSError("disk full")
        cfg = AuditLogConfig(fail_open=False)
        lgr = TenantAuditLogger(config=cfg, store=mock_store)
        with pytest.raises(OSError):
            await lgr.log(tenant_id="t1", action=AuditAction.CREATE)

    @pytest.mark.asyncio
    async def test_query_returns_scoped_results(self):
        lgr = TenantAuditLogger()
        await lgr.log(tenant_id="t1", action=AuditAction.CREATE)
        await lgr.log(tenant_id="t2", action=AuditAction.DELETE)
        result = await lgr.query("t1")
        assert result.tenant_id == "t1"
        assert result.total_count == 1
        assert all(e.tenant_id == "t1" for e in result.entries)

    @pytest.mark.asyncio
    async def test_query_invalid_tenant(self):
        lgr = TenantAuditLogger()
        result = await lgr.query("")
        assert result.total_count == 0
        assert result.entries == []

    @pytest.mark.asyncio
    async def test_query_with_params(self):
        lgr = TenantAuditLogger()
        await lgr.log(tenant_id="t1", action=AuditAction.CREATE)
        await lgr.log(tenant_id="t1", action=AuditAction.DELETE)
        result = await lgr.query("t1", query=AuditQueryParams(action=AuditAction.DELETE))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_default_params(self):
        lgr = TenantAuditLogger()
        await lgr.log(tenant_id="t1", action=AuditAction.READ)
        result = await lgr.query("t1", query=None)
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_get_entry_found(self):
        lgr = TenantAuditLogger()
        entry_id = await lgr.log(tenant_id="t1", action=AuditAction.CREATE)
        entry = await lgr.get_entry("t1", entry_id)
        assert entry is not None
        assert entry.id == entry_id

    @pytest.mark.asyncio
    async def test_get_entry_not_found(self):
        lgr = TenantAuditLogger()
        await lgr.log(tenant_id="t1", action=AuditAction.CREATE)
        entry = await lgr.get_entry("t1", "nonexistent-id")
        assert entry is None

    @pytest.mark.asyncio
    async def test_get_entry_invalid_tenant(self):
        lgr = TenantAuditLogger()
        entry = await lgr.get_entry("", "some-id")
        assert entry is None

    @pytest.mark.asyncio
    async def test_count(self):
        lgr = TenantAuditLogger()
        await lgr.log(tenant_id="t1", action=AuditAction.CREATE)
        await lgr.log(tenant_id="t1", action=AuditAction.DELETE)
        assert await lgr.count("t1") == 2

    @pytest.mark.asyncio
    async def test_count_invalid_tenant(self):
        lgr = TenantAuditLogger()
        assert await lgr.count("") == 0

    @pytest.mark.asyncio
    async def test_cleanup_old_entries(self):
        lgr = TenantAuditLogger()
        old_ts = (datetime.now(UTC) - timedelta(days=200)).isoformat()
        store = lgr.get_store()
        assert isinstance(store, InMemoryAuditStore)
        await store.store(_make_entry(tenant_id="t1", timestamp=old_ts))
        await lgr.log(tenant_id="t1", action=AuditAction.CREATE)
        removed = await lgr.cleanup_old_entries("t1", retention_days=90)
        assert removed == 1
        assert await lgr.count("t1") == 1

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_default_retention(self):
        cfg = AuditLogConfig(retention_days=1)
        lgr = TenantAuditLogger(config=cfg)
        old_ts = (datetime.now(UTC) - timedelta(days=5)).isoformat()
        store = lgr.get_store()
        assert isinstance(store, InMemoryAuditStore)
        await store.store(_make_entry(tenant_id="t1", timestamp=old_ts))
        removed = await lgr.cleanup_old_entries("t1")
        assert removed == 1

    @pytest.mark.asyncio
    async def test_cleanup_invalid_tenant(self):
        lgr = TenantAuditLogger()
        assert await lgr.cleanup_old_entries("") == 0

    @pytest.mark.asyncio
    async def test_close(self):
        lgr = TenantAuditLogger()
        await lgr.close()  # should not raise

    def test_get_store(self):
        lgr = TenantAuditLogger()
        store = lgr.get_store()
        assert isinstance(store, InMemoryAuditStore)

    def test_custom_store_injection(self):
        mock_store = AsyncMock(spec=AuditLogStore)
        lgr = TenantAuditLogger(store=mock_store)
        assert lgr.get_store() is mock_store


# ===========================================================================
# TenantAuditLogger - Redis backend selection
# ===========================================================================


class TestLoggerBackendSelection:
    def test_uses_inmemory_by_default(self):
        lgr = TenantAuditLogger(config=AuditLogConfig(use_redis=False))
        assert isinstance(lgr.get_store(), InMemoryAuditStore)

    @patch("src.core.shared.acgs_logging.audit_logger.REDIS_AVAILABLE", True)
    def test_uses_redis_when_configured(self):
        cfg = AuditLogConfig(use_redis=True)
        lgr = TenantAuditLogger(config=cfg)
        assert isinstance(lgr.get_store(), RedisAuditStore)


# ===========================================================================
# RedisAuditStore (mocked Redis)
# ===========================================================================


class TestRedisAuditStore:
    @pytest.fixture
    def mock_redis(self):
        r = MagicMock()
        # Most methods need to be async
        r.close = AsyncMock()
        r.get = AsyncMock()
        r.zrange = AsyncMock()
        r.zrangebyscore = AsyncMock()
        r.zrevrangebyscore = AsyncMock()
        r.zcard = AsyncMock()
        # pipeline() is sync but its execute() is async
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[True, 1, 3])
        r.pipeline.return_value = pipe
        return r

    @pytest.fixture
    def store(self, mock_redis) -> RedisAuditStore:
        s = RedisAuditStore(
            redis_url="redis://localhost:6379/0",
            max_entries_per_tenant=100,
        )
        s._redis = mock_redis
        s._initialized = True
        return s

    def test_tenant_key_generation(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        assert s._tenant_key("t1") == "acgs2:audit:tenant:t1"
        assert s._tenant_key("t1", "index") == "acgs2:audit:tenant:t1:index"
        assert s._tenant_key("t1", "") == "acgs2:audit:tenant:t1"

    @pytest.mark.asyncio
    async def test_store_entry(self, store: RedisAuditStore, mock_redis):
        entry = _make_entry()
        result = await store.store(entry)
        assert result is True
        mock_redis.pipeline.assert_called()

    @pytest.mark.asyncio
    async def test_store_not_initialized(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        s._initialized = True
        s._redis = None
        result = await s.store(_make_entry())
        assert result is False

    @pytest.mark.asyncio
    async def test_store_exception_returns_false(self, store: RedisAuditStore, mock_redis):
        mock_redis.pipeline.side_effect = OSError("connection lost")
        result = await store.store(_make_entry())
        assert result is False

    @pytest.mark.asyncio
    async def test_store_triggers_trim(self, mock_redis):
        """When count > max, oldest entries should be trimmed."""
        s = RedisAuditStore(
            redis_url="redis://localhost",
            max_entries_per_tenant=2,
        )
        s._redis = mock_redis
        s._initialized = True

        pipe1 = MagicMock()
        pipe1.execute = AsyncMock(return_value=[True, 1, 5])
        pipe2 = MagicMock()
        pipe2.execute = AsyncMock(return_value=[True, True, True, True])

        mock_redis.pipeline.side_effect = [pipe1, pipe2]
        mock_redis.zrange = AsyncMock(return_value=["old-1", "old-2", "old-3"])

        entry = _make_entry()
        result = await s.store(entry)
        assert result is True
        mock_redis.zrange.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_not_initialized(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        s._initialized = True
        s._redis = None
        result = await s.query("t1", AuditQueryParams())
        assert result.total_count == 0
        assert result.entries == []

    @pytest.mark.asyncio
    async def test_query_with_time_range(self, store: RedisAuditStore, mock_redis):
        mock_redis.zrevrangebyscore = AsyncMock(return_value=[])
        params = AuditQueryParams(
            start_time=datetime.now(UTC) - timedelta(hours=1),
            end_time=datetime.now(UTC),
        )
        result = await store.query("t1", params)
        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_query_ascending_order(self, store: RedisAuditStore, mock_redis):
        mock_redis.zrangebyscore = AsyncMock(return_value=[])
        params = AuditQueryParams(order_desc=False)
        await store.query("t1", params)
        mock_redis.zrangebyscore.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_fetches_and_filters(self, store: RedisAuditStore, mock_redis):
        entry = _make_entry(tenant_id="t1", action="create")
        entry_json = json.dumps(entry.to_dict())
        mock_redis.zrevrangebyscore = AsyncMock(return_value=[entry.id])
        mock_redis.get = AsyncMock(return_value=entry_json)

        result = await store.query("t1", AuditQueryParams(action=AuditAction.CREATE))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_skips_invalid_entries(self, store: RedisAuditStore, mock_redis):
        mock_redis.zrevrangebyscore = AsyncMock(return_value=["id1", "id2"])
        mock_redis.get = AsyncMock(side_effect=["not-valid-json", None])
        result = await store.query("t1", AuditQueryParams())
        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_query_exception_returns_empty(self, store: RedisAuditStore, mock_redis):
        mock_redis.zrevrangebyscore = AsyncMock(side_effect=OSError("down"))
        result = await store.query("t1", AuditQueryParams())
        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_count(self, store: RedisAuditStore, mock_redis):
        mock_redis.zcard = AsyncMock(return_value=42)
        assert await store.count("t1") == 42

    @pytest.mark.asyncio
    async def test_count_not_initialized(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        s._initialized = True
        s._redis = None
        assert await s.count("t1") == 0

    @pytest.mark.asyncio
    async def test_count_exception(self, store: RedisAuditStore, mock_redis):
        mock_redis.zcard = AsyncMock(side_effect=OSError("timeout"))
        assert await store.count("t1") == 0

    @pytest.mark.asyncio
    async def test_cleanup(self, store: RedisAuditStore, mock_redis):
        mock_redis.zrangebyscore = AsyncMock(return_value=["old-1", "old-2"])
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[True, True, True])
        mock_redis.pipeline.return_value = pipe
        cutoff = datetime.now(UTC) - timedelta(days=30)
        removed = await store.cleanup("t1", cutoff)
        assert removed == 2

    @pytest.mark.asyncio
    async def test_cleanup_no_old_entries(self, store: RedisAuditStore, mock_redis):
        mock_redis.zrangebyscore = AsyncMock(return_value=[])
        cutoff = datetime.now(UTC)
        removed = await store.cleanup("t1", cutoff)
        assert removed == 0

    @pytest.mark.asyncio
    async def test_cleanup_not_initialized(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        s._initialized = True
        s._redis = None
        assert await s.cleanup("t1", datetime.now(UTC)) == 0

    @pytest.mark.asyncio
    async def test_cleanup_exception(self, store: RedisAuditStore, mock_redis):
        mock_redis.zrangebyscore = AsyncMock(side_effect=OSError("fail"))
        assert await store.cleanup("t1", datetime.now(UTC)) == 0

    @pytest.mark.asyncio
    async def test_close(self, store: RedisAuditStore, mock_redis):
        await store.close()
        mock_redis.close.assert_called_once()
        assert store._redis is None

    @pytest.mark.asyncio
    async def test_close_no_connection(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        s._redis = None
        await s.close()  # should not raise

    @pytest.mark.asyncio
    async def test_ensure_initialized_redis_unavailable(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        with patch("src.core.shared.acgs_logging.audit_logger.REDIS_AVAILABLE", False):
            result = await s._ensure_initialized()
        assert result is False
        assert s._initialized is True

    @pytest.mark.asyncio
    async def test_ensure_initialized_already_done(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        s._initialized = True
        s._redis = MagicMock()
        result = await s._ensure_initialized()
        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_initialized_connection_failure(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        with (
            patch("src.core.shared.acgs_logging.audit_logger.REDIS_AVAILABLE", True),
            patch("src.core.shared.acgs_logging.audit_logger.aioredis") as mock_aioredis,
        ):
            mock_aioredis.from_url = AsyncMock(side_effect=OSError("refused"))
            result = await s._ensure_initialized()
        assert result is False
        assert s._initialized is True

    @pytest.mark.asyncio
    async def test_ensure_initialized_success(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        fake_conn = AsyncMock()
        with (
            patch("src.core.shared.acgs_logging.audit_logger.REDIS_AVAILABLE", True),
            patch("src.core.shared.acgs_logging.audit_logger.aioredis") as mock_aioredis,
        ):
            mock_aioredis.from_url = AsyncMock(return_value=fake_conn)
            result = await s._ensure_initialized()
        assert result is True
        assert s._redis is fake_conn


# ===========================================================================
# Redaction helper
# ===========================================================================


class TestRedaction:
    def test_all_sensitive_fields_redacted(self):
        cfg = AuditLogConfig(enable_redaction=True)
        lgr = TenantAuditLogger(config=cfg)
        details = {f: f"value-{f}" for f in SENSITIVE_FIELDS}
        redacted = lgr._redact_sensitive(details)
        for f in SENSITIVE_FIELDS:
            assert redacted[f] == "[REDACTED]"

    def test_case_insensitive_matching(self):
        cfg = AuditLogConfig(enable_redaction=True)
        lgr = TenantAuditLogger(config=cfg)
        details = {"API_KEY": "secret", "Password": "hidden"}
        # Keys are lowercased for comparison; "api_key" matches "API_KEY".lower()
        redacted = lgr._redact_sensitive(details)
        assert redacted["API_KEY"] == "[REDACTED]"
        assert redacted["Password"] == "[REDACTED]"

    def test_nested_dict_redaction(self):
        cfg = AuditLogConfig(enable_redaction=True)
        lgr = TenantAuditLogger(config=cfg)
        details = {
            "config": {
                "token": "xyz",
                "name": "safe",
                "inner": {"secret": "deep"},
            }
        }
        redacted = lgr._redact_sensitive(details)
        assert redacted["config"]["token"] == "[REDACTED]"
        assert redacted["config"]["name"] == "safe"
        # Nested dicts within nested dicts
        assert redacted["config"]["inner"]["secret"] == "[REDACTED]"


# ===========================================================================
# Factory functions
# ===========================================================================


class TestFactoryFunctions:
    def test_create_tenant_audit_logger_default(self):
        lgr = create_tenant_audit_logger()
        assert isinstance(lgr, TenantAuditLogger)
        assert isinstance(lgr.get_store(), InMemoryAuditStore)

    def test_create_tenant_audit_logger_custom_config(self):
        cfg = AuditLogConfig(retention_days=7)
        lgr = create_tenant_audit_logger(config=cfg)
        assert lgr.config.retention_days == 7

    def test_create_tenant_audit_logger_custom_store(self):
        mock_store = AsyncMock(spec=AuditLogStore)
        lgr = create_tenant_audit_logger(store=mock_store)
        assert lgr.get_store() is mock_store

    def test_get_tenant_audit_logger_returns_singleton(self):
        get_tenant_audit_logger.cache_clear()
        lgr1 = get_tenant_audit_logger()
        lgr2 = get_tenant_audit_logger()
        assert lgr1 is lgr2
        get_tenant_audit_logger.cache_clear()


# ===========================================================================
# Enums
# ===========================================================================


class TestEnums:
    def test_audit_action_values(self):
        assert AuditAction.CREATE.value == "create"
        assert AuditAction.AUTH_FAILURE.value == "auth_failure"
        assert AuditAction.CUSTOM.value == "custom"

    def test_audit_severity_values(self):
        assert AuditSeverity.DEBUG.value == "debug"
        assert AuditSeverity.CRITICAL.value == "critical"


# ===========================================================================
# AuditQueryResult
# ===========================================================================


class TestAuditQueryResult:
    def test_defaults(self):
        r = AuditQueryResult(
            entries=[],
            total_count=0,
            tenant_id="t1",
            query_params=AuditQueryParams(),
        )
        assert r.has_more is False
        assert r.constitutional_hash == CONSTITUTIONAL_HASH

    def test_with_entries(self):
        entry = _make_entry()
        r = AuditQueryResult(
            entries=[entry],
            total_count=1,
            tenant_id="tenant-a",
            query_params=AuditQueryParams(),
            has_more=True,
        )
        assert r.has_more is True
        assert len(r.entries) == 1


# ===========================================================================
# Redis _apply_filters (separate from InMemory to cover the Redis path)
# ===========================================================================


class TestRedisApplyFilters:
    def test_filters_action(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        entries = [
            _make_entry(action="create"),
            _make_entry(action="delete"),
        ]
        result = s._apply_filters(entries, AuditQueryParams(action=AuditAction.DELETE))
        assert len(result) == 1
        assert result[0].action == "delete"

    def test_filters_resource_type(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        entries = [
            _make_entry(resource_type="policy"),
            _make_entry(resource_type="agent"),
        ]
        result = s._apply_filters(entries, AuditQueryParams(resource_type="agent"))
        assert len(result) == 1

    def test_filters_resource_id(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        entries = [_make_entry(resource_id="r1"), _make_entry(resource_id="r2")]
        result = s._apply_filters(entries, AuditQueryParams(resource_id="r1"))
        assert len(result) == 1

    def test_filters_actor_id(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        entries = [_make_entry(actor_id="a1"), _make_entry(actor_id="a2")]
        result = s._apply_filters(entries, AuditQueryParams(actor_id="a1"))
        assert len(result) == 1

    def test_filters_severity(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        entries = [
            _make_entry(severity="info"),
            _make_entry(severity="error"),
        ]
        result = s._apply_filters(entries, AuditQueryParams(severity=AuditSeverity.ERROR))
        assert len(result) == 1

    def test_filters_outcome(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        entries = [
            _make_entry(outcome="success"),
            _make_entry(outcome="failure"),
        ]
        result = s._apply_filters(entries, AuditQueryParams(outcome="failure"))
        assert len(result) == 1

    def test_no_filters(self):
        s = RedisAuditStore(redis_url="redis://localhost")
        entries = [_make_entry(), _make_entry()]
        result = s._apply_filters(entries, AuditQueryParams())
        assert len(result) == 2
