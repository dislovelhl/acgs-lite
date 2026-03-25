"""
Comprehensive tests for audit_logger, cache/warming, and cache/manager modules.

Targets:
    - src/core/shared/acgs_logging/audit_logger.py
    - src/core/shared/cache/warming.py
    - src/core/shared/cache/manager.py
"""

import asyncio
import json
import threading
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# ---------------------------------------------------------------------------
# audit_logger imports
# ---------------------------------------------------------------------------
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
)

# ---------------------------------------------------------------------------
# cache/manager imports
# ---------------------------------------------------------------------------
from src.core.shared.cache.manager import TieredCacheManager
from src.core.shared.cache.models import (
    AccessRecord,
    CacheTier,
    TieredCacheConfig,
    TieredCacheStats,
)

# ---------------------------------------------------------------------------
# cache/warming imports
# ---------------------------------------------------------------------------
from src.core.shared.cache.warming import (
    CacheWarmer,
    RateLimiter,
    WarmingConfig,
    WarmingProgress,
    WarmingResult,
    WarmingStatus,
    get_cache_warmer,
    reset_cache_warmer,
)

# ===================================================================
# AUDIT LOGGER TESTS
# ===================================================================


class TestAuditAction:
    """Test AuditAction enum values."""

    def test_crud_actions_exist(self):
        assert AuditAction.CREATE == "create"
        assert AuditAction.READ == "read"
        assert AuditAction.UPDATE == "update"
        assert AuditAction.DELETE == "delete"
        assert AuditAction.LIST == "list"

    def test_auth_actions_exist(self):
        assert AuditAction.LOGIN == "login"
        assert AuditAction.LOGOUT == "logout"
        assert AuditAction.AUTH_FAILURE == "auth_failure"
        assert AuditAction.ACCESS_DENIED == "access_denied"

    def test_policy_actions_exist(self):
        assert AuditAction.POLICY_EVALUATE == "policy_evaluate"
        assert AuditAction.POLICY_APPROVE == "policy_approve"
        assert AuditAction.POLICY_REJECT == "policy_reject"

    def test_tenant_actions_exist(self):
        assert AuditAction.TENANT_CREATE == "tenant_create"
        assert AuditAction.TENANT_UPDATE == "tenant_update"
        assert AuditAction.TENANT_DELETE == "tenant_delete"

    def test_custom_action(self):
        assert AuditAction.CUSTOM == "custom"


class TestAuditSeverity:
    """Test AuditSeverity enum values."""

    def test_all_severity_levels(self):
        assert AuditSeverity.DEBUG == "debug"
        assert AuditSeverity.INFO == "info"
        assert AuditSeverity.WARNING == "warning"
        assert AuditSeverity.ERROR == "error"
        assert AuditSeverity.CRITICAL == "critical"


class TestAuditEntry:
    """Test AuditEntry dataclass."""

    def _make_entry(self, **kwargs):
        defaults = {
            "id": "entry-1",
            "tenant_id": "tenant-a",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "action": "create",
        }
        defaults.update(kwargs)
        return AuditEntry(**defaults)

    def test_to_dict(self):
        entry = self._make_entry()
        d = entry.to_dict()
        assert d["id"] == "entry-1"
        assert d["tenant_id"] == "tenant-a"
        assert d["action"] == "create"
        assert d["severity"] == "info"
        assert d["outcome"] == "success"

    def test_from_dict_basic(self):
        data = {
            "id": "e-2",
            "tenant_id": "t-b",
            "timestamp": "2025-06-01T00:00:00",
            "action": "read",
        }
        entry = AuditEntry.from_dict(data)
        assert entry.id == "e-2"
        assert entry.action == "read"

    def test_from_dict_with_enum_action(self):
        data = {
            "id": "e-3",
            "tenant_id": "t-c",
            "timestamp": "2025-06-01T00:00:00",
            "action": AuditAction.UPDATE,
        }
        entry = AuditEntry.from_dict(data)
        assert entry.action == "update"

    def test_from_dict_with_enum_severity(self):
        data = {
            "id": "e-4",
            "tenant_id": "t-d",
            "timestamp": "2025-06-01T00:00:00",
            "action": "create",
            "severity": AuditSeverity.ERROR,
        }
        entry = AuditEntry.from_dict(data)
        assert entry.severity == "error"

    def test_default_values(self):
        entry = self._make_entry()
        assert entry.severity == "info"
        assert entry.actor_type == "user"
        assert entry.outcome == "success"
        assert entry.details == {}
        assert entry.resource_type is None
        assert entry.resource_id is None
        assert entry.actor_id is None
        assert entry.client_ip is None
        assert entry.user_agent is None
        assert entry.request_id is None
        assert entry.error_message is None


class TestAuditQueryParams:
    """Test AuditQueryParams defaults."""

    def test_defaults(self):
        p = AuditQueryParams()
        assert p.action is None
        assert p.limit == 100
        assert p.offset == 0
        assert p.order_by == "timestamp"
        assert p.order_desc is True

    def test_custom_params(self):
        p = AuditQueryParams(
            action=AuditAction.CREATE,
            severity=AuditSeverity.WARNING,
            limit=10,
            offset=5,
            order_desc=False,
        )
        assert p.action == AuditAction.CREATE
        assert p.severity == AuditSeverity.WARNING
        assert p.limit == 10


class TestAuditQueryResult:
    """Test AuditQueryResult dataclass."""

    def test_basic_result(self):
        r = AuditQueryResult(
            entries=[],
            total_count=0,
            tenant_id="t-1",
            query_params=AuditQueryParams(),
        )
        assert r.total_count == 0
        assert r.has_more is False


class TestAuditLogConfig:
    """Test AuditLogConfig."""

    def test_defaults(self):
        c = AuditLogConfig()
        assert c.use_redis is False
        assert c.max_entries_per_tenant == 100000
        assert c.retention_days == 90
        assert c.enable_redaction is True
        assert c.audit_enabled is True
        assert c.fail_open is True

    def test_from_env_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            c = AuditLogConfig.from_env()
            assert c.redis_url == "redis://localhost:6379/0"
            assert c.use_redis is False
            assert c.audit_enabled is True

    def test_from_env_custom(self):
        env = {
            "REDIS_URL": "redis://custom:1234/1",
            "AUDIT_USE_REDIS": "true",
            "AUDIT_MAX_ENTRIES_PER_TENANT": "500",
            "AUDIT_RETENTION_DAYS": "30",
            "AUDIT_ENABLE_REDACTION": "false",
            "AUDIT_ENABLE_COMPRESSION": "true",
            "AUDIT_ENABLED": "false",
            "AUDIT_FAIL_OPEN": "false",
            "AUDIT_KEY_PREFIX": "custom:audit",
        }
        with patch.dict("os.environ", env, clear=True):
            c = AuditLogConfig.from_env()
            assert c.redis_url == "redis://custom:1234/1"
            assert c.use_redis is True
            assert c.max_entries_per_tenant == 500
            assert c.retention_days == 30
            assert c.enable_redaction is False
            assert c.enable_compression is True
            assert c.audit_enabled is False
            assert c.fail_open is False
            assert c.key_prefix == "custom:audit"


class TestInMemoryAuditStore:
    """Test InMemoryAuditStore."""

    def _make_entry(self, tenant_id="t-1", action="create", **kwargs):
        defaults = {
            "id": kwargs.pop("id", "e-1"),
            "tenant_id": tenant_id,
            "timestamp": kwargs.pop("timestamp", datetime.now(UTC).isoformat()),
            "action": action,
        }
        defaults.update(kwargs)
        return AuditEntry(**defaults)

    @pytest.mark.asyncio
    async def test_store_and_count(self):
        store = InMemoryAuditStore()
        entry = self._make_entry()
        result = await store.store(entry)
        assert result is True
        assert await store.count("t-1") == 1

    @pytest.mark.asyncio
    async def test_store_creates_tenant_bucket(self):
        store = InMemoryAuditStore()
        entry = self._make_entry(tenant_id="new-tenant")
        await store.store(entry)
        assert "new-tenant" in store.get_all_tenant_ids()

    @pytest.mark.asyncio
    async def test_max_entries_enforced(self):
        store = InMemoryAuditStore(max_entries_per_tenant=3)
        for i in range(5):
            entry = self._make_entry(id=f"e-{i}")
            await store.store(entry)
        assert await store.count("t-1") == 3

    @pytest.mark.asyncio
    async def test_query_empty_tenant(self):
        store = InMemoryAuditStore()
        result = await store.query("nonexistent", AuditQueryParams())
        assert result.total_count == 0
        assert result.entries == []

    @pytest.mark.asyncio
    async def test_query_with_action_filter(self):
        store = InMemoryAuditStore()
        await store.store(self._make_entry(id="e-1", action="create"))
        await store.store(self._make_entry(id="e-2", action="read"))
        result = await store.query("t-1", AuditQueryParams(action=AuditAction.CREATE))
        assert result.total_count == 1
        assert result.entries[0].action == "create"

    @pytest.mark.asyncio
    async def test_query_with_resource_type_filter(self):
        store = InMemoryAuditStore()
        await store.store(self._make_entry(id="e-1", resource_type="policy"))
        await store.store(self._make_entry(id="e-2", resource_type="user"))
        result = await store.query("t-1", AuditQueryParams(resource_type="policy"))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_with_resource_id_filter(self):
        store = InMemoryAuditStore()
        await store.store(self._make_entry(id="e-1", resource_id="r-1"))
        await store.store(self._make_entry(id="e-2", resource_id="r-2"))
        result = await store.query("t-1", AuditQueryParams(resource_id="r-1"))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_with_actor_id_filter(self):
        store = InMemoryAuditStore()
        await store.store(self._make_entry(id="e-1", actor_id="a-1"))
        await store.store(self._make_entry(id="e-2", actor_id="a-2"))
        result = await store.query("t-1", AuditQueryParams(actor_id="a-1"))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_with_severity_filter(self):
        store = InMemoryAuditStore()
        await store.store(self._make_entry(id="e-1", severity="error"))
        await store.store(self._make_entry(id="e-2", severity="info"))
        result = await store.query("t-1", AuditQueryParams(severity=AuditSeverity.ERROR))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_with_outcome_filter(self):
        store = InMemoryAuditStore()
        await store.store(self._make_entry(id="e-1", outcome="success"))
        await store.store(self._make_entry(id="e-2", outcome="failure"))
        result = await store.query("t-1", AuditQueryParams(outcome="failure"))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_with_time_range(self):
        store = InMemoryAuditStore()
        t1 = datetime(2025, 1, 1, tzinfo=UTC)
        t2 = datetime(2025, 6, 1, tzinfo=UTC)
        t3 = datetime(2025, 12, 1, tzinfo=UTC)
        await store.store(self._make_entry(id="e-1", timestamp=t1.isoformat()))
        await store.store(self._make_entry(id="e-2", timestamp=t2.isoformat()))
        await store.store(self._make_entry(id="e-3", timestamp=t3.isoformat()))

        params = AuditQueryParams(
            start_time=datetime(2025, 3, 1, tzinfo=UTC),
            end_time=datetime(2025, 9, 1, tzinfo=UTC),
        )
        result = await store.query("t-1", params)
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_sorting_by_action(self):
        store = InMemoryAuditStore()
        await store.store(self._make_entry(id="e-1", action="create"))
        await store.store(self._make_entry(id="e-2", action="delete"))
        params = AuditQueryParams(order_by="action", order_desc=False)
        result = await store.query("t-1", params)
        assert result.entries[0].action == "create"

    @pytest.mark.asyncio
    async def test_query_sorting_by_severity(self):
        store = InMemoryAuditStore()
        await store.store(self._make_entry(id="e-1", severity="error"))
        await store.store(self._make_entry(id="e-2", severity="debug"))
        params = AuditQueryParams(order_by="severity", order_desc=False)
        result = await store.query("t-1", params)
        assert result.entries[0].severity == "debug"

    @pytest.mark.asyncio
    async def test_query_pagination(self):
        store = InMemoryAuditStore()
        for i in range(5):
            await store.store(self._make_entry(id=f"e-{i}"))
        params = AuditQueryParams(limit=2, offset=0)
        result = await store.query("t-1", params)
        assert len(result.entries) == 2
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_query_pagination_no_more(self):
        store = InMemoryAuditStore()
        for i in range(3):
            await store.store(self._make_entry(id=f"e-{i}"))
        params = AuditQueryParams(limit=5, offset=0)
        result = await store.query("t-1", params)
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_cleanup(self):
        store = InMemoryAuditStore()
        old_ts = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        new_ts = datetime.now(UTC).isoformat()
        await store.store(self._make_entry(id="old", timestamp=old_ts))
        await store.store(self._make_entry(id="new", timestamp=new_ts))

        cutoff = datetime.now(UTC) - timedelta(days=50)
        removed = await store.cleanup("t-1", cutoff)
        assert removed == 1
        assert await store.count("t-1") == 1

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent_tenant(self):
        store = InMemoryAuditStore()
        removed = await store.cleanup("no-such-tenant", datetime.now(UTC))
        assert removed == 0

    @pytest.mark.asyncio
    async def test_count_nonexistent_tenant(self):
        store = InMemoryAuditStore()
        assert await store.count("no-such") == 0

    @pytest.mark.asyncio
    async def test_close_noop(self):
        store = InMemoryAuditStore()
        await store.close()  # Should not raise

    def test_get_all_tenant_ids(self):
        store = InMemoryAuditStore()
        assert store.get_all_tenant_ids() == []


class TestRedisAuditStore:
    """Test RedisAuditStore with mocked Redis."""

    def _make_entry(self, **kwargs):
        defaults = {
            "id": "e-1",
            "tenant_id": "t-1",
            "timestamp": datetime.now(UTC).isoformat(),
            "action": "create",
        }
        defaults.update(kwargs)
        return AuditEntry(**defaults)

    def _make_store(self):
        return RedisAuditStore(
            redis_url="redis://localhost:6379/0",
            key_prefix="test:audit",
            max_entries_per_tenant=100,
        )

    @pytest.mark.asyncio
    async def test_tenant_key_generation(self):
        store = self._make_store()
        assert store._tenant_key("t-1") == "test:audit:tenant:t-1"
        assert store._tenant_key("t-1", "entries") == "test:audit:tenant:t-1:entries"

    @pytest.mark.asyncio
    async def test_ensure_initialized_no_redis(self):
        store = self._make_store()
        with patch("src.core.shared.acgs_logging.audit_logger.REDIS_AVAILABLE", False):
            store._initialized = False
            result = await store._ensure_initialized()
            assert result is False

    @pytest.mark.asyncio
    async def test_ensure_initialized_already_initialized(self):
        store = self._make_store()
        store._initialized = True
        store._redis = MagicMock()
        result = await store._ensure_initialized()
        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_initialized_already_initialized_no_redis(self):
        store = self._make_store()
        store._initialized = True
        store._redis = None
        result = await store._ensure_initialized()
        assert result is False

    @pytest.mark.asyncio
    async def test_store_when_not_initialized(self):
        store = self._make_store()
        store._initialized = True
        store._redis = None
        entry = self._make_entry()
        result = await store.store(entry)
        assert result is False

    @pytest.mark.asyncio
    async def test_store_success(self):
        store = self._make_store()
        store._initialized = True

        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[True, True, 5])
        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        store._redis = mock_redis

        entry = self._make_entry()
        result = await store.store(entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_store_triggers_trim(self):
        store = RedisAuditStore(
            redis_url="redis://localhost:6379/0",
            key_prefix="test:audit",
            max_entries_per_tenant=5,
        )
        store._initialized = True

        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[True, True, 10])  # count > max
        mock_pipe2 = MagicMock()
        mock_pipe2.execute = AsyncMock(return_value=[True, True])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(side_effect=[mock_pipe, mock_pipe2])
        mock_redis.zrange = AsyncMock(return_value=["old-1", "old-2"])
        store._redis = mock_redis

        entry = self._make_entry()
        result = await store.store(entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_store_error_handling(self):
        store = self._make_store()
        store._initialized = True
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=OSError("Connection refused"))
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        store._redis = mock_redis

        entry = self._make_entry()
        result = await store.store(entry)
        assert result is False

    @pytest.mark.asyncio
    async def test_query_not_initialized(self):
        store = self._make_store()
        store._initialized = True
        store._redis = None
        result = await store.query("t-1", AuditQueryParams())
        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_query_success(self):
        store = self._make_store()
        store._initialized = True

        entry = self._make_entry()
        entry_json = json.dumps(entry.to_dict())

        mock_redis = MagicMock()
        mock_redis.zrevrangebyscore = AsyncMock(return_value=["e-1"])
        mock_redis.get = AsyncMock(return_value=entry_json)
        store._redis = mock_redis

        result = await store.query("t-1", AuditQueryParams())
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_with_time_range(self):
        store = self._make_store()
        store._initialized = True

        entry = self._make_entry()
        entry_json = json.dumps(entry.to_dict())

        mock_redis = MagicMock()
        mock_redis.zrangebyscore = AsyncMock(return_value=["e-1"])
        mock_redis.get = AsyncMock(return_value=entry_json)
        store._redis = mock_redis

        params = AuditQueryParams(
            start_time=datetime(2025, 1, 1, tzinfo=UTC),
            end_time=datetime(2025, 12, 31, tzinfo=UTC),
            order_desc=False,
        )
        result = await store.query("t-1", params)
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_entry_parse_failure(self):
        store = self._make_store()
        store._initialized = True

        mock_redis = MagicMock()
        mock_redis.zrevrangebyscore = AsyncMock(return_value=["e-1"])
        mock_redis.get = AsyncMock(return_value="not-valid-json{{{")
        store._redis = mock_redis

        result = await store.query("t-1", AuditQueryParams())
        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_query_entry_returns_none(self):
        store = self._make_store()
        store._initialized = True

        mock_redis = MagicMock()
        mock_redis.zrevrangebyscore = AsyncMock(return_value=["e-1"])
        mock_redis.get = AsyncMock(return_value=None)
        store._redis = mock_redis

        result = await store.query("t-1", AuditQueryParams())
        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_query_error_handling(self):
        store = self._make_store()
        store._initialized = True
        mock_redis = MagicMock()
        mock_redis.zrevrangebyscore = AsyncMock(side_effect=OSError("fail"))
        store._redis = mock_redis

        result = await store.query("t-1", AuditQueryParams())
        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_query_with_filters(self):
        store = self._make_store()
        store._initialized = True

        e1 = self._make_entry(id="e-1", action="create")
        e2 = self._make_entry(id="e-2", action="delete")
        entries_json = {
            "e-1": json.dumps(e1.to_dict()),
            "e-2": json.dumps(e2.to_dict()),
        }

        mock_redis = MagicMock()
        mock_redis.zrevrangebyscore = AsyncMock(return_value=["e-1", "e-2"])
        mock_redis.get = AsyncMock(side_effect=lambda k: entries_json.get(k.split(":")[-1]))
        store._redis = mock_redis

        result = await store.query("t-1", AuditQueryParams(action=AuditAction.CREATE))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_count_not_initialized(self):
        store = self._make_store()
        store._initialized = True
        store._redis = None
        assert await store.count("t-1") == 0

    @pytest.mark.asyncio
    async def test_count_success(self):
        store = self._make_store()
        store._initialized = True
        mock_redis = MagicMock()
        mock_redis.zcard = AsyncMock(return_value=42)
        store._redis = mock_redis
        assert await store.count("t-1") == 42

    @pytest.mark.asyncio
    async def test_count_error(self):
        store = self._make_store()
        store._initialized = True
        mock_redis = MagicMock()
        mock_redis.zcard = AsyncMock(side_effect=OSError("fail"))
        store._redis = mock_redis
        assert await store.count("t-1") == 0

    @pytest.mark.asyncio
    async def test_cleanup_not_initialized(self):
        store = self._make_store()
        store._initialized = True
        store._redis = None
        assert await store.cleanup("t-1", datetime.now(UTC)) == 0

    @pytest.mark.asyncio
    async def test_cleanup_no_old_entries(self):
        store = self._make_store()
        store._initialized = True
        mock_redis = MagicMock()
        mock_redis.zrangebyscore = AsyncMock(return_value=[])
        store._redis = mock_redis
        assert await store.cleanup("t-1", datetime.now(UTC)) == 0

    @pytest.mark.asyncio
    async def test_cleanup_success(self):
        store = self._make_store()
        store._initialized = True
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[True, True])
        mock_redis = MagicMock()
        mock_redis.zrangebyscore = AsyncMock(return_value=["old-1", "old-2"])
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        store._redis = mock_redis

        removed = await store.cleanup("t-1", datetime.now(UTC))
        assert removed == 2

    @pytest.mark.asyncio
    async def test_cleanup_error(self):
        store = self._make_store()
        store._initialized = True
        mock_redis = MagicMock()
        mock_redis.zrangebyscore = AsyncMock(side_effect=OSError("fail"))
        store._redis = mock_redis
        assert await store.cleanup("t-1", datetime.now(UTC)) == 0

    @pytest.mark.asyncio
    async def test_close_with_redis(self):
        store = self._make_store()
        mock_redis = MagicMock()
        mock_redis.close = AsyncMock()
        store._redis = mock_redis
        await store.close()
        assert store._redis is None
        mock_redis.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_without_redis(self):
        store = self._make_store()
        store._redis = None
        await store.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_apply_filters_with_resource_type(self):
        store = self._make_store()
        e1 = self._make_entry(resource_type="policy")
        e2 = self._make_entry(resource_type="user")
        result = store._apply_filters([e1, e2], AuditQueryParams(resource_type="policy"))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_apply_filters_with_resource_id(self):
        store = self._make_store()
        e1 = self._make_entry(resource_id="r-1")
        e2 = self._make_entry(resource_id="r-2")
        result = store._apply_filters([e1, e2], AuditQueryParams(resource_id="r-1"))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_apply_filters_with_actor_id(self):
        store = self._make_store()
        e1 = self._make_entry(actor_id="a-1")
        e2 = self._make_entry(actor_id="a-2")
        result = store._apply_filters([e1, e2], AuditQueryParams(actor_id="a-1"))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_apply_filters_with_severity(self):
        store = self._make_store()
        e1 = self._make_entry(severity="error")
        e2 = self._make_entry(severity="info")
        result = store._apply_filters([e1, e2], AuditQueryParams(severity=AuditSeverity.ERROR))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_apply_filters_with_outcome(self):
        store = self._make_store()
        e1 = self._make_entry(outcome="success")
        e2 = self._make_entry(outcome="failure")
        result = store._apply_filters([e1, e2], AuditQueryParams(outcome="failure"))
        assert len(result) == 1


class TestTenantAuditLogger:
    """Test TenantAuditLogger."""

    def _make_logger(self, **config_kwargs):
        config = AuditLogConfig(**config_kwargs)
        return TenantAuditLogger(config=config)

    @pytest.mark.asyncio
    async def test_log_basic(self):
        logger = self._make_logger()
        entry_id = await logger.log(
            tenant_id="t-1",
            action=AuditAction.CREATE,
            resource_type="policy",
            resource_id="p-1",
            actor_id="u-1",
        )
        assert entry_id is not None

    @pytest.mark.asyncio
    async def test_log_disabled(self):
        logger = self._make_logger(audit_enabled=False)
        entry_id = await logger.log(tenant_id="t-1", action=AuditAction.CREATE)
        assert entry_id is None

    @pytest.mark.asyncio
    async def test_log_with_all_fields(self):
        logger = self._make_logger()
        entry_id = await logger.log(
            tenant_id="t-1",
            action=AuditAction.LOGIN,
            resource_type="session",
            resource_id="s-1",
            actor_id="u-1",
            actor_type="service",
            client_ip="192.168.1.1",
            user_agent="test-agent/1.0",
            request_id="req-123",
            details={"key": "value"},
            severity=AuditSeverity.WARNING,
            outcome="failure",
            error_message="Auth failed",
        )
        assert entry_id is not None

    @pytest.mark.asyncio
    async def test_log_redacts_sensitive_fields(self):
        logger = self._make_logger(enable_redaction=True)
        entry_id = await logger.log(
            tenant_id="t-1",
            action=AuditAction.CREATE,
            details={"password": "secret123", "username": "admin"},
        )
        assert entry_id is not None
        store = logger.get_store()
        result = await store.query("t-1", AuditQueryParams())
        entry = result.entries[0]
        assert entry.details["password"] == "[REDACTED]"
        assert entry.details["username"] == "admin"

    @pytest.mark.asyncio
    async def test_log_redacts_nested_sensitive_fields(self):
        logger = self._make_logger(enable_redaction=True)
        # "credentials" contains "credential" so the whole key is redacted
        await logger.log(
            tenant_id="t-1",
            action=AuditAction.CREATE,
            details={"credentials": {"api_key": "abc", "name": "test"}},
        )
        store = logger.get_store()
        result = await store.query("t-1", AuditQueryParams())
        entry = result.entries[0]
        # "credentials" matches sensitive "credential" substring, so whole value redacted
        assert entry.details["credentials"] == "[REDACTED]"

    @pytest.mark.asyncio
    async def test_log_redacts_nested_dict_non_sensitive_key(self):
        logger = self._make_logger(enable_redaction=True)
        # "config" does not match sensitive fields, so nested dict is recursed
        await logger.log(
            tenant_id="t-1",
            action=AuditAction.CREATE,
            details={"config": {"api_key": "abc", "name": "test"}},
        )
        store = logger.get_store()
        result = await store.query("t-1", AuditQueryParams())
        entry = result.entries[0]
        assert entry.details["config"]["api_key"] == "[REDACTED]"
        assert entry.details["config"]["name"] == "test"

    @pytest.mark.asyncio
    async def test_log_no_redaction_when_disabled(self):
        logger = self._make_logger(enable_redaction=False)
        await logger.log(
            tenant_id="t-1",
            action=AuditAction.CREATE,
            details={"password": "secret123"},
        )
        store = logger.get_store()
        result = await store.query("t-1", AuditQueryParams())
        assert result.entries[0].details["password"] == "secret123"

    @pytest.mark.asyncio
    async def test_log_invalid_tenant_id_fail_open(self):
        logger = self._make_logger(fail_open=True)
        entry_id = await logger.log(
            tenant_id="",
            action=AuditAction.CREATE,
        )
        assert entry_id is None

    @pytest.mark.asyncio
    async def test_log_invalid_tenant_id_fail_closed(self):
        logger = self._make_logger(fail_open=False)
        with pytest.raises(ValueError):
            await logger.log(
                tenant_id="",
                action=AuditAction.CREATE,
            )

    @pytest.mark.asyncio
    async def test_log_store_failure_fail_open(self):
        mock_store = MagicMock(spec=AuditLogStore)
        mock_store.store = AsyncMock(return_value=False)
        config = AuditLogConfig(fail_open=True)
        logger = TenantAuditLogger(config=config, store=mock_store)
        entry_id = await logger.log(tenant_id="t-1", action=AuditAction.CREATE)
        assert entry_id is None

    @pytest.mark.asyncio
    async def test_log_store_failure_fail_closed(self):
        mock_store = MagicMock(spec=AuditLogStore)
        mock_store.store = AsyncMock(return_value=False)
        config = AuditLogConfig(fail_open=False)
        logger = TenantAuditLogger(config=config, store=mock_store)
        with pytest.raises(RuntimeError):
            await logger.log(tenant_id="t-1", action=AuditAction.CREATE)

    @pytest.mark.asyncio
    async def test_log_runtime_error_fail_open(self):
        mock_store = MagicMock(spec=AuditLogStore)
        mock_store.store = AsyncMock(side_effect=RuntimeError("boom"))
        config = AuditLogConfig(fail_open=True)
        logger = TenantAuditLogger(config=config, store=mock_store)
        entry_id = await logger.log(tenant_id="t-1", action=AuditAction.CREATE)
        assert entry_id is None

    @pytest.mark.asyncio
    async def test_log_runtime_error_fail_closed(self):
        mock_store = MagicMock(spec=AuditLogStore)
        mock_store.store = AsyncMock(side_effect=RuntimeError("boom"))
        config = AuditLogConfig(fail_open=False)
        logger = TenantAuditLogger(config=config, store=mock_store)
        with pytest.raises(RuntimeError):
            await logger.log(tenant_id="t-1", action=AuditAction.CREATE)

    @pytest.mark.asyncio
    async def test_query_basic(self):
        logger = self._make_logger()
        await logger.log(tenant_id="t-1", action=AuditAction.CREATE)
        result = await logger.query("t-1")
        assert result.total_count == 1
        assert result.tenant_id == "t-1"

    @pytest.mark.asyncio
    async def test_query_with_params(self):
        logger = self._make_logger()
        await logger.log(tenant_id="t-1", action=AuditAction.CREATE)
        await logger.log(tenant_id="t-1", action=AuditAction.DELETE)
        result = await logger.query("t-1", AuditQueryParams(action=AuditAction.CREATE))
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_query_invalid_tenant(self):
        logger = self._make_logger()
        result = await logger.query("")
        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_query_tenant_isolation(self):
        logger = self._make_logger()
        await logger.log(tenant_id="t-1", action=AuditAction.CREATE)
        await logger.log(tenant_id="t-2", action=AuditAction.CREATE)
        result = await logger.query("t-1")
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_get_entry_found(self):
        logger = self._make_logger()
        entry_id = await logger.log(tenant_id="t-1", action=AuditAction.CREATE)
        entry = await logger.get_entry("t-1", entry_id)
        assert entry is not None
        assert entry.id == entry_id

    @pytest.mark.asyncio
    async def test_get_entry_not_found(self):
        logger = self._make_logger()
        await logger.log(tenant_id="t-1", action=AuditAction.CREATE)
        entry = await logger.get_entry("t-1", "nonexistent-id")
        assert entry is None

    @pytest.mark.asyncio
    async def test_get_entry_invalid_tenant(self):
        logger = self._make_logger()
        entry = await logger.get_entry("", "some-id")
        assert entry is None

    @pytest.mark.asyncio
    async def test_count(self):
        logger = self._make_logger()
        await logger.log(tenant_id="t-1", action=AuditAction.CREATE)
        await logger.log(tenant_id="t-1", action=AuditAction.READ)
        count = await logger.count("t-1")
        assert count == 2

    @pytest.mark.asyncio
    async def test_count_invalid_tenant(self):
        logger = self._make_logger()
        count = await logger.count("")
        assert count == 0

    @pytest.mark.asyncio
    async def test_cleanup_old_entries(self):
        logger = self._make_logger()
        # Store an old entry directly
        store = logger.get_store()
        old_ts = (datetime.now(UTC) - timedelta(days=200)).isoformat()
        old_entry = AuditEntry(
            id="old-1",
            tenant_id="t-1",
            timestamp=old_ts,
            action="create",
        )
        await store.store(old_entry)
        await logger.log(tenant_id="t-1", action=AuditAction.CREATE)

        removed = await logger.cleanup_old_entries("t-1", retention_days=90)
        assert removed == 1

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_invalid_tenant(self):
        logger = self._make_logger()
        removed = await logger.cleanup_old_entries("")
        assert removed == 0

    @pytest.mark.asyncio
    async def test_cleanup_with_custom_retention(self):
        logger = self._make_logger()
        store = logger.get_store()
        old_ts = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        old_entry = AuditEntry(
            id="old-1", tenant_id="t-1", timestamp=old_ts, action="create"
        )
        await store.store(old_entry)

        removed = await logger.cleanup_old_entries("t-1", retention_days=5)
        assert removed == 1

    @pytest.mark.asyncio
    async def test_close(self):
        logger = self._make_logger()
        await logger.close()  # Should not raise

    def test_get_store(self):
        logger = self._make_logger()
        store = logger.get_store()
        assert isinstance(store, InMemoryAuditStore)

    def test_init_with_custom_store(self):
        mock_store = MagicMock(spec=AuditLogStore)
        logger = TenantAuditLogger(store=mock_store)
        assert logger.get_store() is mock_store

    def test_create_tenant_audit_logger_factory(self):
        logger = create_tenant_audit_logger()
        assert isinstance(logger, TenantAuditLogger)

    def test_create_tenant_audit_logger_with_config(self):
        config = AuditLogConfig(retention_days=30)
        logger = create_tenant_audit_logger(config=config)
        assert logger.config.retention_days == 30


class TestSensitiveFields:
    """Test SENSITIVE_FIELDS constant."""

    def test_contains_expected_fields(self):
        expected = {"password", "secret", "token", "api_key", "apikey",
                    "access_token", "refresh_token", "private_key",
                    "credential", "auth"}
        assert SENSITIVE_FIELDS == expected

    def test_is_frozen(self):
        assert isinstance(SENSITIVE_FIELDS, frozenset)


# ===================================================================
# CACHE WARMING TESTS
# ===================================================================


class TestWarmingStatus:
    """Test WarmingStatus enum."""

    def test_all_statuses(self):
        assert WarmingStatus.IDLE.value == "idle"
        assert WarmingStatus.WARMING.value == "warming"
        assert WarmingStatus.COMPLETED.value == "completed"
        assert WarmingStatus.FAILED.value == "failed"
        assert WarmingStatus.CANCELLED.value == "cancelled"


class TestWarmingConfig:
    """Test WarmingConfig defaults."""

    def test_defaults(self):
        c = WarmingConfig()
        assert c.rate_limit == 100
        assert c.batch_size == 10
        assert c.l1_count == 10
        assert c.l2_count == 100
        assert c.key_timeout == 1.0
        assert c.total_timeout == 300.0
        assert c.max_retries == 3
        assert c.priority_keys == []


class TestWarmingResult:
    """Test WarmingResult dataclass."""

    def test_success_property(self):
        r = WarmingResult(status=WarmingStatus.COMPLETED)
        assert r.success is True

    def test_not_success(self):
        r = WarmingResult(status=WarmingStatus.FAILED)
        assert r.success is False

    def test_success_rate(self):
        r = WarmingResult(status=WarmingStatus.COMPLETED, keys_warmed=8, keys_failed=2)
        assert r.success_rate == 0.8

    def test_success_rate_zero_total(self):
        r = WarmingResult(status=WarmingStatus.COMPLETED)
        assert r.success_rate == 0.0


class TestWarmingProgress:
    """Test WarmingProgress dataclass."""

    def test_percent_complete(self):
        p = WarmingProgress(total_keys=100, processed_keys=50)
        assert p.percent_complete == 50.0

    def test_percent_complete_zero_total(self):
        p = WarmingProgress(total_keys=0, processed_keys=0)
        assert p.percent_complete == 0.0


class TestRateLimiter:
    """Test RateLimiter."""

    def test_init_defaults(self):
        rl = RateLimiter(tokens_per_second=10.0)
        assert rl.tokens_per_second == 10.0
        assert rl.max_tokens == 10

    def test_init_custom_max(self):
        rl = RateLimiter(tokens_per_second=10.0, max_tokens=20)
        assert rl.max_tokens == 20

    def test_acquire_with_tokens_available(self):
        rl = RateLimiter(tokens_per_second=100.0, max_tokens=100)
        wait = rl.acquire(1)
        assert wait == 0.0

    def test_acquire_returns_wait_time(self):
        rl = RateLimiter(tokens_per_second=10.0, max_tokens=1)
        rl.acquire(1)  # Consume the 1 token
        wait = rl.acquire(1)
        assert wait > 0.0

    @pytest.mark.asyncio
    async def test_acquire_async_with_tokens(self):
        rl = RateLimiter(tokens_per_second=100.0, max_tokens=100)
        await rl.acquire_async(1)  # Should not block

    @pytest.mark.asyncio
    async def test_acquire_async_needs_wait(self):
        rl = RateLimiter(tokens_per_second=1000.0, max_tokens=1)
        await rl.acquire_async(1)  # Consume
        await rl.acquire_async(1)  # Should wait briefly then consume

    def test_refill(self):
        rl = RateLimiter(tokens_per_second=1000.0, max_tokens=10)
        rl.tokens = 0.0
        rl.last_update = time.monotonic() - 0.01  # 10ms ago
        rl._refill()
        assert rl.tokens > 0.0

    def test_refill_capped_at_max(self):
        rl = RateLimiter(tokens_per_second=1000.0, max_tokens=10)
        rl.tokens = 9.0
        rl.last_update = time.monotonic() - 1.0  # 1 second ago
        rl._refill()
        assert rl.tokens == 10.0


class TestCacheWarmer:
    """Test CacheWarmer."""

    def test_init_defaults(self):
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer()
            assert warmer.config.rate_limit == 100
            assert warmer.status == WarmingStatus.IDLE
            assert warmer.is_warming is False

    def test_init_custom_rate_limit(self):
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(rate_limit=50)
            assert warmer.config.rate_limit == 50

    def test_progress_property(self):
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer()
            p = warmer.progress
            assert isinstance(p, WarmingProgress)

    def test_cancel(self):
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer()
            warmer.cancel()
            assert warmer._cancel_event.is_set()

    def test_on_progress_callback(self):
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer()
            cb = MagicMock()
            warmer.on_progress(cb)
            assert cb in warmer._progress_callbacks

    def test_remove_progress_callback(self):
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer()
            cb = MagicMock()
            warmer.on_progress(cb)
            assert warmer.remove_progress_callback(cb) is True
            assert warmer.remove_progress_callback(cb) is False

    def test_get_stats(self):
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer()
            stats = warmer.get_stats()
            assert "status" in stats
            assert "config" in stats
            assert "progress" in stats
            assert stats["status"] == "idle"

    def test_repr(self):
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer()
            r = repr(warmer)
            assert "CacheWarmer" in r
            assert "rate_limit=100" in r

    @pytest.mark.asyncio
    async def test_warm_cache_no_keys(self):
        mock_cm = MagicMock()
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm)

        with patch.object(warmer, "_get_keys_to_warm", new_callable=AsyncMock, return_value=[]):
            result = await warmer.warm_cache()
            assert result.status == WarmingStatus.COMPLETED
            assert result.keys_warmed == 0

    @pytest.mark.asyncio
    async def test_warm_cache_already_warming(self):
        mock_cm = MagicMock()
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm)
        warmer._status = WarmingStatus.WARMING
        # Need to initialize the async lock
        warmer._lock_async = asyncio.Lock()

        result = await warmer.warm_cache()
        assert result.status == WarmingStatus.FAILED
        assert "already in progress" in result.error_message

    @pytest.mark.asyncio
    async def test_warm_cache_with_source_keys(self):
        mock_cm = MagicMock()
        mock_cm.set = AsyncMock()
        mock_cm.get = MagicMock(return_value="value")

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm, rate_limit=10000)

        mock_tier_module = MagicMock()
        mock_tier_module.CacheTier = CacheTier
        with patch.dict("sys.modules", {"src.core.shared.tiered_cache": mock_tier_module}):
            with patch.object(warmer, "_load_key_value",
                              new_callable=AsyncMock, return_value="test-val"):
                result = await warmer.warm_cache(source_keys=["key1", "key2"])
                assert result.status == WarmingStatus.COMPLETED
                assert result.keys_warmed == 2

    @pytest.mark.asyncio
    async def test_warm_cache_with_key_loader(self):
        mock_cm = MagicMock()
        mock_cm.set = AsyncMock()

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm, rate_limit=10000)

        def my_loader(key):
            return f"value-{key}"

        mock_tier_module = MagicMock()
        mock_tier_module.CacheTier = CacheTier
        with patch.dict("sys.modules", {"src.core.shared.tiered_cache": mock_tier_module}):
            with patch.object(warmer, "_load_key_value",
                              new_callable=AsyncMock, return_value="loaded-val"):
                result = await warmer.warm_cache(source_keys=["k1"], key_loader=my_loader)
                assert result.keys_warmed == 1

    @pytest.mark.asyncio
    async def test_warm_cache_exception_handling(self):
        mock_cm = MagicMock()
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm)

        with patch.object(warmer, "_get_keys_to_warm",
                          new_callable=AsyncMock,
                          side_effect=Exception("unexpected")):
            result = await warmer.warm_cache()
            assert result.status == WarmingStatus.FAILED
            assert "unexpected" in result.error_message

    @pytest.mark.asyncio
    async def test_warm_cache_cancelled(self):
        mock_cm = MagicMock()
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm)

        async def mock_get_keys(source_keys=None):
            raise asyncio.CancelledError()

        with patch.object(warmer, "_get_keys_to_warm", side_effect=mock_get_keys):
            result = await warmer.warm_cache()
            assert result.status == WarmingStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_get_keys_to_warm_with_source_keys(self):
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer()
        keys = await warmer._get_keys_to_warm(source_keys=["a", "b", "c"])
        assert keys == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_get_keys_to_warm_with_source_keys_truncated(self):
        config = WarmingConfig(l2_count=2)
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(config=config)
        keys = await warmer._get_keys_to_warm(source_keys=["a", "b", "c"])
        assert len(keys) == 2

    @pytest.mark.asyncio
    async def test_get_keys_to_warm_with_priority_keys(self):
        config = WarmingConfig(priority_keys=["priority-1", "priority-2"])
        mock_cm = MagicMock(spec=[])  # no _l3_cache attr
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(config=config, cache_manager=mock_cm)
        keys = await warmer._get_keys_to_warm()
        assert "priority-1" in keys
        assert "priority-2" in keys

    @pytest.mark.asyncio
    async def test_get_keys_to_warm_deduplication(self):
        config = WarmingConfig(priority_keys=["a", "a", "b"])
        mock_cm = MagicMock(spec=[])
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(config=config, cache_manager=mock_cm)
        keys = await warmer._get_keys_to_warm()
        assert keys == ["a", "b"]

    @pytest.mark.asyncio
    async def test_get_keys_to_warm_from_l3(self):
        mock_cm = MagicMock()
        mock_cm._l3_cache = {"k1": {}, "k2": {}}
        mock_cm._l3_lock = threading.Lock()
        # No _access_records
        del mock_cm._access_records

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm)
        keys = await warmer._get_keys_to_warm()
        assert "k1" in keys
        assert "k2" in keys

    @pytest.mark.asyncio
    async def test_get_keys_to_warm_from_l3_with_access_records(self):
        mock_cm = MagicMock()
        mock_cm._l3_cache = {"k1": {}, "k2": {}}
        mock_cm._l3_lock = threading.Lock()
        mock_cm._access_lock = threading.Lock()
        rec1 = MagicMock()
        rec1.accesses_per_minute = 5
        rec2 = MagicMock()
        rec2.accesses_per_minute = 10
        mock_cm._access_records = {"k1": rec1, "k2": rec2}

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm)
        keys = await warmer._get_keys_to_warm()
        assert keys[0] == "k2"  # Higher access count first

    @pytest.mark.asyncio
    async def test_get_keys_to_warm_l3_exception(self):
        mock_cm = MagicMock()
        mock_cm._l3_cache = property(lambda s: (_ for _ in ()).throw(RuntimeError("fail")))
        type(mock_cm)._l3_cache = PropertyMock(side_effect=RuntimeError("fail"))

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm)
        keys = await warmer._get_keys_to_warm()
        assert keys == []

    @pytest.mark.asyncio
    async def test_load_key_value_with_custom_loader(self):
        mock_cm = MagicMock()
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm)

        def loader(key):
            return f"val-{key}"

        value = await warmer._load_key_value("k1", mock_cm, loader)
        assert value == "val-k1"

    @pytest.mark.asyncio
    async def test_load_key_value_with_async_loader(self):
        mock_cm = MagicMock()
        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm)

        async def async_loader(key):
            return f"async-val-{key}"

        value = await warmer._load_key_value("k1", mock_cm, async_loader)
        assert value == "async-val-k1"

    @pytest.mark.asyncio
    async def test_load_key_value_from_l3(self):
        mock_cm = MagicMock()
        mock_cm._l3_cache = {"k1": {"data": "l3-value"}}
        mock_cm._l3_lock = threading.Lock()

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm)

        value = await warmer._load_key_value("k1", mock_cm, None)
        assert value == "l3-value"

    @pytest.mark.asyncio
    async def test_load_key_value_from_cache_manager_get(self):
        mock_cm = MagicMock(spec=[])  # no _l3_cache
        mock_cm.get = MagicMock(return_value="cm-value")

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm)

        # Need to add get attr
        mock_cm_with_get = MagicMock()
        del mock_cm_with_get._l3_cache
        mock_cm_with_get.get = MagicMock(return_value="cm-value")

        value = await warmer._load_key_value("k1", mock_cm_with_get, None)
        assert value == "cm-value"

    @pytest.mark.asyncio
    async def test_load_key_value_returns_none(self):
        mock_cm = MagicMock()
        del mock_cm._l3_cache
        mock_cm.get = MagicMock(return_value=None)

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(cache_manager=mock_cm)

        value = await warmer._load_key_value("missing", mock_cm, None)
        assert value is None

    @pytest.mark.asyncio
    async def test_load_key_value_timeout_retries(self):
        mock_cm = MagicMock()
        config = WarmingConfig(max_retries=2, retry_delay=0.01)

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(config=config, cache_manager=mock_cm)

        call_count = 0

        def failing_loader(key):
            nonlocal call_count
            call_count += 1
            raise TimeoutError("timeout")

        value = await warmer._load_key_value("k1", mock_cm, failing_loader)
        assert value is None
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_load_key_value_runtime_error_retries(self):
        mock_cm = MagicMock()
        config = WarmingConfig(max_retries=2, retry_delay=0.01)

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(config=config, cache_manager=mock_cm)

        def failing_loader(key):
            raise RuntimeError("fail")

        value = await warmer._load_key_value("k1", mock_cm, failing_loader)
        assert value is None

    @pytest.mark.asyncio
    async def test_warm_in_batches_with_cancellation(self):
        mock_cm = MagicMock()
        mock_cm.set = AsyncMock()
        config = WarmingConfig(batch_size=2, rate_limit=10000)

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(config=config, cache_manager=mock_cm)
        warmer._cancel_event.set()

        mock_tier_module = MagicMock()
        mock_tier_module.CacheTier = CacheTier
        with patch.dict("sys.modules", {"src.core.shared.tiered_cache": mock_tier_module}):
            result = await warmer._warm_in_batches(
                ["k1", "k2"], mock_cm, None, time.monotonic()
            )
        assert result.status == WarmingStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_warm_in_batches_timeout(self):
        mock_cm = MagicMock()
        mock_cm.set = AsyncMock()
        config = WarmingConfig(batch_size=2, total_timeout=0.0, rate_limit=10000)

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(config=config, cache_manager=mock_cm)

        mock_tier_module = MagicMock()
        mock_tier_module.CacheTier = CacheTier
        with patch.dict("sys.modules", {"src.core.shared.tiered_cache": mock_tier_module}):
            result = await warmer._warm_in_batches(
                ["k1", "k2"], mock_cm, None, time.monotonic() - 1.0
            )
        assert result.details.get("timeout") is True

    @pytest.mark.asyncio
    async def test_warm_in_batches_progress_callback(self):
        mock_cm = MagicMock()
        mock_cm.set = AsyncMock()
        config = WarmingConfig(batch_size=2, rate_limit=10000)

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(config=config, cache_manager=mock_cm)

        cb = MagicMock()
        warmer.on_progress(cb)

        mock_tier_module = MagicMock()
        mock_tier_module.CacheTier = CacheTier
        with patch.dict("sys.modules", {"src.core.shared.tiered_cache": mock_tier_module}):
            with patch.object(warmer, "_load_key_value", new_callable=AsyncMock, return_value="val"):
                await warmer._warm_in_batches(
                    ["k1", "k2"], mock_cm, None, time.monotonic()
                )
        assert cb.called

    @pytest.mark.asyncio
    async def test_warm_in_batches_progress_callback_error(self):
        mock_cm = MagicMock()
        mock_cm.set = AsyncMock()
        config = WarmingConfig(batch_size=2, rate_limit=10000)

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(config=config, cache_manager=mock_cm)

        bad_cb = MagicMock(side_effect=Exception("callback fail"))
        warmer.on_progress(bad_cb)

        mock_tier_module = MagicMock()
        mock_tier_module.CacheTier = CacheTier
        with patch.dict("sys.modules", {"src.core.shared.tiered_cache": mock_tier_module}):
            with patch.object(warmer, "_load_key_value", new_callable=AsyncMock, return_value="val"):
                result = await warmer._warm_in_batches(
                    ["k1"], mock_cm, None, time.monotonic()
                )
        assert result.keys_warmed == 1  # Should continue despite callback error

    @pytest.mark.asyncio
    async def test_warm_in_batches_key_load_failure(self):
        mock_cm = MagicMock()
        mock_cm.set = AsyncMock()
        config = WarmingConfig(batch_size=2, rate_limit=10000)

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(config=config, cache_manager=mock_cm)

        mock_tier_module = MagicMock()
        mock_tier_module.CacheTier = CacheTier
        with patch.dict("sys.modules", {"src.core.shared.tiered_cache": mock_tier_module}):
            with patch.object(warmer, "_load_key_value", new_callable=AsyncMock, return_value=None):
                result = await warmer._warm_in_batches(
                    ["k1"], mock_cm, None, time.monotonic()
                )
        assert result.keys_failed == 1

    @pytest.mark.asyncio
    async def test_warm_in_batches_set_exception(self):
        mock_cm = MagicMock()
        mock_cm.set = AsyncMock(side_effect=RuntimeError("set fail"))
        config = WarmingConfig(batch_size=2, rate_limit=10000)

        with patch("src.core.shared.cache.warming.get_logger"):
            warmer = CacheWarmer(config=config, cache_manager=mock_cm)

        mock_tier_module = MagicMock()
        mock_tier_module.CacheTier = CacheTier
        with patch.dict("sys.modules", {"src.core.shared.tiered_cache": mock_tier_module}):
            with patch.object(warmer, "_load_key_value", new_callable=AsyncMock, return_value="val"):
                result = await warmer._warm_in_batches(
                    ["k1"], mock_cm, None, time.monotonic()
                )
        assert result.keys_failed == 1


class TestCacheWarmerSingleton:
    """Test singleton get_cache_warmer / reset_cache_warmer."""

    def setup_method(self):
        reset_cache_warmer()

    def teardown_method(self):
        reset_cache_warmer()

    def test_get_cache_warmer_creates_singleton(self):
        warmer1 = get_cache_warmer()
        warmer2 = get_cache_warmer()
        assert warmer1 is warmer2

    def test_reset_cache_warmer(self):
        warmer1 = get_cache_warmer()
        reset_cache_warmer()
        warmer2 = get_cache_warmer()
        assert warmer1 is not warmer2

    def test_reset_cache_warmer_when_none(self):
        reset_cache_warmer()  # Should not raise


# ===================================================================
# CACHE MANAGER TESTS
# ===================================================================


class TestTieredCacheManager:
    """Test TieredCacheManager."""

    def _make_manager(self, **kwargs):
        defaults = {"l3_enabled": True, "serialize": True}
        defaults.update(kwargs)
        config = TieredCacheConfig(**defaults)
        mgr = TieredCacheManager(config=config, name="test")
        return mgr

    def test_init(self):
        mgr = self._make_manager()
        assert mgr.name == "test"
        assert mgr._l2_degraded is False

    def test_init_l1_ttl_adjusted(self):
        """L1 TTL should be adjusted to not exceed L2 TTL."""
        mgr = self._make_manager(l1_ttl=7200, l2_ttl=3600)
        assert mgr.config.l1_ttl == 3600

    def test_get_from_l1_miss(self):
        mgr = self._make_manager()
        result = mgr.get("nonexistent")
        assert result is None

    def test_get_set_l3(self):
        mgr = self._make_manager()
        mgr._set_in_l3("k1", json.dumps("hello"))
        value = mgr._get_from_l3("k1")
        assert value is not None

    def test_get_from_l3_disabled(self):
        mgr = self._make_manager(l3_enabled=False)
        mgr._set_in_l3("k1", "val")  # should be noop
        assert mgr._get_from_l3("k1") is None

    def test_get_from_l3_expired(self):
        mgr = self._make_manager(l3_ttl=0)
        with mgr._l3_lock:
            mgr._l3_cache["k1"] = {"data": "old", "timestamp": 0}
        result = mgr._get_from_l3("k1")
        assert result is None

    def test_set_in_l1(self):
        mgr = self._make_manager()
        mgr._set_in_l1("k1", "val1")
        result = mgr._get_from_l1("k1")
        assert result is not None

    def test_serialize_deserialize(self):
        mgr = self._make_manager(serialize=True)
        serialized = mgr._serialize({"key": "value"})
        assert isinstance(serialized, str)
        deserialized = mgr._deserialize(serialized)
        assert deserialized == {"key": "value"}

    def test_serialize_already_string(self):
        mgr = self._make_manager(serialize=True)
        assert mgr._serialize("hello") == "hello"

    def test_serialize_disabled(self):
        mgr = self._make_manager(serialize=False)
        val = {"key": "value"}
        assert mgr._serialize(val) is val

    def test_deserialize_disabled(self):
        mgr = self._make_manager(serialize=False)
        val = "hello"
        assert mgr._deserialize(val) == val

    def test_deserialize_invalid_json(self):
        mgr = self._make_manager(serialize=True)
        assert mgr._deserialize("not-json{") == "not-json{"

    def test_serialize_unserializable(self):
        mgr = self._make_manager(serialize=True)
        val = object()
        assert mgr._serialize(val) is val

    def test_get_stats(self):
        mgr = self._make_manager()
        stats = mgr.get_stats()
        assert stats["name"] == "test"
        assert "tiers" in stats
        assert "aggregate" in stats
        assert "l1" in stats["tiers"]
        assert "l2" in stats["tiers"]
        assert "l3" in stats["tiers"]

    def test_record_access_creates_record(self):
        mgr = self._make_manager()
        mgr._record_access("k1")
        assert "k1" in mgr._access_records

    def test_update_tier(self):
        mgr = self._make_manager()
        mgr._update_tier("k1", CacheTier.L1)
        assert mgr._access_records["k1"].current_tier == CacheTier.L1

    def test_update_tier_existing(self):
        mgr = self._make_manager()
        mgr._record_access("k1")
        mgr._update_tier("k1", CacheTier.L2)
        assert mgr._access_records["k1"].current_tier == CacheTier.L2

    def test_should_promote_to_l1_no_record(self):
        mgr = self._make_manager()
        assert mgr._should_promote_to_l1("nonexistent") is False

    def test_cleanup_old_records(self):
        mgr = self._make_manager()
        mgr._record_access("k1")
        # Force old timestamp
        mgr._access_records["k1"].last_access = time.time() - 7200
        with mgr._l3_lock:
            mgr._l3_cache["old_key"] = {"data": "x", "timestamp": time.time() - 7200}
        mgr._cleanup_old_records()
        assert "k1" not in mgr._access_records
        assert "old_key" not in mgr._l3_cache

    @pytest.mark.asyncio
    async def test_initialize_l2_no_aioredis(self):
        mgr = self._make_manager()
        with patch("src.core.shared.cache.manager.aioredis", None):
            result = await mgr._initialize_l2()
            assert result is False

    @pytest.mark.asyncio
    async def test_initialize_l2_connection_error(self):
        mgr = self._make_manager()
        mock_aioredis = MagicMock()
        mock_client = MagicMock()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("fail"))
        mock_aioredis.from_url = MagicMock(return_value=mock_client)

        with patch("src.core.shared.cache.manager.aioredis", mock_aioredis):
            result = await mgr._initialize_l2()
            assert result is False

    @pytest.mark.asyncio
    async def test_initialize_l2_success(self):
        mgr = self._make_manager()
        mock_aioredis = MagicMock()
        mock_client = MagicMock()
        mock_client.ping = AsyncMock()
        mock_aioredis.from_url = MagicMock(return_value=mock_client)

        with patch("src.core.shared.cache.manager.aioredis", mock_aioredis):
            result = await mgr._initialize_l2()
            assert result is True

    @pytest.mark.asyncio
    async def test_initialize_sets_degraded(self):
        mgr = self._make_manager()
        with patch.object(mgr, "_initialize_l2", new_callable=AsyncMock, return_value=False):
            result = await mgr.initialize()
            assert result is False
            assert mgr._l2_degraded is True

    @pytest.mark.asyncio
    async def test_initialize_success(self):
        mgr = self._make_manager()
        with patch.object(mgr, "_initialize_l2", new_callable=AsyncMock, return_value=True):
            result = await mgr.initialize()
            assert result is True
            assert mgr._l2_degraded is False

    @pytest.mark.asyncio
    async def test_close_with_client(self):
        mgr = self._make_manager()
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        mgr._l2_client = mock_client
        await mgr.close()
        assert mgr._l2_client is None

    @pytest.mark.asyncio
    async def test_close_without_client(self):
        mgr = self._make_manager()
        mgr._l2_client = None
        await mgr.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_with_error(self):
        mgr = self._make_manager()
        mock_client = MagicMock()
        mock_client.close = AsyncMock(side_effect=ConnectionError("fail"))
        mgr._l2_client = mock_client
        await mgr.close()  # Should suppress
        assert mgr._l2_client is None

    def test_on_redis_health_change_unhealthy(self):
        mgr = self._make_manager()
        from src.core.shared.redis_config import RedisHealthState
        mgr._on_redis_health_change(RedisHealthState.HEALTHY, RedisHealthState.UNHEALTHY)
        assert mgr._l2_degraded is True

    def test_on_redis_health_change_healthy(self):
        mgr = self._make_manager()
        from src.core.shared.redis_config import RedisHealthState
        mgr._l2_degraded = True
        mgr._on_redis_health_change(RedisHealthState.UNHEALTHY, RedisHealthState.HEALTHY)
        assert mgr._l2_degraded is False

    def test_handle_l2_failure(self):
        mgr = self._make_manager()
        mgr._handle_l2_failure()
        assert mgr._l2_degraded is True
        assert mgr._stats.redis_failures == 1

    def test_get_synchronous_l1_hit(self):
        mgr = self._make_manager()
        mgr._set_in_l1("k1", json.dumps("v1"))
        result = mgr.get("k1")
        assert result is not None

    def test_get_synchronous_l3_hit(self):
        mgr = self._make_manager()
        mgr._set_in_l3("k1", json.dumps("v1"))
        result = mgr.get("k1")
        assert result is not None

    def test_get_synchronous_miss(self):
        mgr = self._make_manager()
        result = mgr.get("missing", default="fallback")
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_get_async_l1_hit(self):
        mgr = self._make_manager()
        mgr._set_in_l1("k1", json.dumps("v1"))
        result = await mgr.get_async("k1")
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_async_l2_hit(self):
        mgr = self._make_manager()
        mock_client = MagicMock()
        mock_client.get = AsyncMock(
            return_value=json.dumps({"data": "v2", "timestamp": time.time()})
        )
        mgr._l2_client = mock_client
        mgr._l2_degraded = False
        result = await mgr.get_async("k2")
        assert result == "v2"

    @pytest.mark.asyncio
    async def test_get_async_l2_miss(self):
        mgr = self._make_manager()
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=None)
        mgr._l2_client = mock_client
        mgr._l2_degraded = False
        result = await mgr.get_async("k2", default="def")
        # Falls through to L3 then returns default
        assert result == "def"

    @pytest.mark.asyncio
    async def test_get_async_l2_degraded(self):
        mgr = self._make_manager()
        mgr._l2_client = MagicMock()
        mgr._l2_degraded = True
        mgr._last_l2_failure = time.time()  # Recent failure
        result = await mgr.get_async("k2", default="def")
        assert result == "def"

    @pytest.mark.asyncio
    async def test_get_async_l2_recovery_attempt(self):
        mgr = self._make_manager()
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=None)
        mgr._l2_client = mock_client
        mgr._l2_degraded = True
        mgr._last_l2_failure = time.time() - 60  # Old failure, should try recovery

        with patch.object(mgr, "_initialize_l2", new_callable=AsyncMock, return_value=False):
            result = await mgr.get_async("k2", default="def")
            assert result == "def"

    @pytest.mark.asyncio
    async def test_get_async_l2_error(self):
        mgr = self._make_manager()
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("fail"))
        mgr._l2_client = mock_client
        mgr._l2_degraded = False
        await mgr.get_async("k2", default="def")
        assert mgr._l2_degraded is True

    @pytest.mark.asyncio
    async def test_get_from_l2_no_client(self):
        mgr = self._make_manager()
        mgr._l2_client = None
        result = await mgr._get_from_l2("k1")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_default_tier(self):
        mgr = self._make_manager()
        mgr._l2_client = None
        mgr._l2_degraded = True
        await mgr.set("k1", "v1")
        # Falls back to L3
        assert "k1" in mgr._l3_cache

    @pytest.mark.asyncio
    async def test_set_l1_tier(self):
        mgr = self._make_manager()
        await mgr.set("k1", "v1", tier=CacheTier.L1)
        assert mgr._get_from_l1("k1") is not None

    @pytest.mark.asyncio
    async def test_set_l2_tier(self):
        mgr = self._make_manager()
        mock_client = MagicMock()
        mock_client.setex = AsyncMock()
        mgr._l2_client = mock_client
        mgr._l2_degraded = False
        await mgr.set("k1", "v1", tier=CacheTier.L2)
        mock_client.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_l3_tier(self):
        mgr = self._make_manager()
        await mgr.set("k1", "v1", tier=CacheTier.L3)
        assert "k1" in mgr._l3_cache

    @pytest.mark.asyncio
    async def test_set_l2_with_fallback_to_l3(self):
        mgr = self._make_manager()
        mock_client = MagicMock()
        mock_client.setex = AsyncMock(side_effect=ConnectionError("fail"))
        mgr._l2_client = mock_client
        mgr._l2_degraded = False
        await mgr.set("k1", "v1", tier=CacheTier.L2)
        # Should fall back to L3
        assert "k1" in mgr._l3_cache

    @pytest.mark.asyncio
    async def test_set_default_promotes_to_l1(self):
        mgr = self._make_manager(promotion_threshold=1)
        mock_client = MagicMock()
        mock_client.setex = AsyncMock()
        mgr._l2_client = mock_client
        mgr._l2_degraded = False

        # Create high-frequency access record
        mgr._record_access("k1")
        for _ in range(20):
            mgr._record_access("k1")

        await mgr.set("k1", "v1")
        # Should be promoted to L1
        assert mgr._get_from_l1("k1") is not None

    @pytest.mark.asyncio
    async def test_delete_from_all_tiers(self):
        mgr = self._make_manager()
        mgr._set_in_l1("k1", "v1")
        mgr._set_in_l3("k1", "v1")
        result = await mgr.delete("k1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        mgr = self._make_manager()
        result = await mgr.delete("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_from_l2(self):
        mgr = self._make_manager()
        mock_client = MagicMock()
        mock_client.delete = AsyncMock(return_value=1)
        mgr._l2_client = mock_client
        mgr._l2_degraded = False
        result = await mgr.delete("k1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_l2_error(self):
        mgr = self._make_manager()
        mock_client = MagicMock()
        mock_client.delete = AsyncMock(side_effect=ConnectionError("fail"))
        mgr._l2_client = mock_client
        mgr._l2_degraded = False
        mgr._set_in_l1("k1", "v1")
        result = await mgr.delete("k1")
        assert result is True
        assert mgr._l2_degraded is True

    @pytest.mark.asyncio
    async def test_exists_l1(self):
        mgr = self._make_manager()
        mgr._set_in_l1("k1", "v1")
        assert await mgr.exists("k1") is True

    @pytest.mark.asyncio
    async def test_exists_l2(self):
        mgr = self._make_manager()
        mock_client = MagicMock()
        mock_client.exists = AsyncMock(return_value=True)
        mgr._l2_client = mock_client
        mgr._l2_degraded = False
        assert await mgr.exists("k1") is True

    @pytest.mark.asyncio
    async def test_exists_l3(self):
        mgr = self._make_manager()
        with mgr._l3_lock:
            mgr._l3_cache["k1"] = {"data": "v1", "timestamp": time.time()}
        assert await mgr.exists("k1") is True

    @pytest.mark.asyncio
    async def test_exists_l3_expired(self):
        mgr = self._make_manager()
        with mgr._l3_lock:
            mgr._l3_cache["k1"] = {"data": "v1", "timestamp": 0}
        assert await mgr.exists("k1") is False

    @pytest.mark.asyncio
    async def test_exists_not_found(self):
        mgr = self._make_manager()
        assert await mgr.exists("missing") is False

    @pytest.mark.asyncio
    async def test_exists_l2_error(self):
        mgr = self._make_manager()
        mock_client = MagicMock()
        mock_client.exists = AsyncMock(side_effect=ConnectionError("fail"))
        mgr._l2_client = mock_client
        mgr._l2_degraded = False
        # Should not raise, just degrade
        assert await mgr.exists("k1") is False
        assert mgr._l2_degraded is True

    def test_check_and_promote(self):
        mgr = self._make_manager(promotion_threshold=1)
        # Create access record with high frequency
        mgr._record_access("k1")
        for _ in range(20):
            mgr._record_access("k1")
        mgr._access_records["k1"].current_tier = CacheTier.L3

        mgr._check_and_promote("k1", "val")
        assert mgr._access_records["k1"].current_tier == CacheTier.L1
        assert mgr._stats.promotions >= 1

    def test_check_and_promote_no_record(self):
        mgr = self._make_manager()
        mgr._check_and_promote("nonexistent", "val")  # Should not raise

    def test_check_and_promote_already_l1(self):
        mgr = self._make_manager(promotion_threshold=1)
        mgr._record_access("k1")
        for _ in range(20):
            mgr._record_access("k1")
        mgr._access_records["k1"].current_tier = CacheTier.L1
        initial_promotions = mgr._stats.promotions

        mgr._check_and_promote("k1", "val")
        assert mgr._stats.promotions == initial_promotions  # No new promotion

    def test_check_and_promote_tier_only(self):
        mgr = self._make_manager(promotion_threshold=1)
        mgr._record_access("k1")
        for _ in range(20):
            mgr._record_access("k1")
        mgr._access_records["k1"].current_tier = CacheTier.L3

        mgr._check_and_promote_tier_only("k1")
        assert mgr._access_records["k1"].current_tier == CacheTier.L1

    def test_check_and_promote_tier_only_no_record(self):
        mgr = self._make_manager()
        mgr._check_and_promote_tier_only("nonexistent")  # Should not raise

    def test_set_in_l3_disabled(self):
        mgr = self._make_manager(l3_enabled=False)
        mgr._set_in_l3("k1", "v1")
        assert "k1" not in mgr._l3_cache


class TestTieredCacheStats:
    """Test TieredCacheStats properties."""

    def test_total_hits(self):
        s = TieredCacheStats(l1_hits=10, l2_hits=5, l3_hits=2)
        assert s.total_hits == 17

    def test_total_misses(self):
        s = TieredCacheStats(l1_misses=3, l2_misses=2, l3_misses=1)
        assert s.total_misses == 6

    def test_hit_ratio(self):
        s = TieredCacheStats(l1_hits=8, l1_misses=2)
        assert s.hit_ratio == 0.8

    def test_hit_ratio_zero(self):
        s = TieredCacheStats()
        assert s.hit_ratio == 0.0

    def test_l1_hit_ratio(self):
        s = TieredCacheStats(l1_hits=9, l1_misses=1)
        assert s.l1_hit_ratio == 0.9

    def test_l1_hit_ratio_zero(self):
        s = TieredCacheStats()
        assert s.l1_hit_ratio == 0.0


class TestAccessRecord:
    """Test AccessRecord."""

    def test_record_access(self):
        rec = AccessRecord(key="k1")
        rec.record_access()
        assert len(rec.access_times) >= 1

    def test_accesses_per_minute(self):
        rec = AccessRecord(key="k1")
        for _ in range(5):
            rec.record_access()
        assert rec.accesses_per_minute == 5

    def test_hours_since_access(self):
        rec = AccessRecord(key="k1")
        rec.last_access = time.time() - 3600  # 1 hour ago
        assert abs(rec.hours_since_access - 1.0) < 0.1

    def test_old_accesses_pruned(self):
        rec = AccessRecord(key="k1")
        rec.access_times = [time.time() - 120, time.time() - 90]  # Old
        rec.record_access()  # Should prune old ones
        assert len(rec.access_times) == 1
