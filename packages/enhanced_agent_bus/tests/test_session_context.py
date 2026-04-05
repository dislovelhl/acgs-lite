"""
ACGS-2 Enhanced Agent Bus - Session Context Tests
Constitutional Hash: 608508a9bd224290

Tests for SessionContext model and SessionContextStore.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Constitutional hash constant
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.models import RiskLevel, SessionGovernanceConfig

from ..session_context import SessionContext, SessionContextManager, SessionContextStore


@pytest.fixture
def sample_governance_config():
    """Create a sample governance configuration."""
    return SessionGovernanceConfig(
        session_id="test-session-123",
        tenant_id="tenant-123",
        user_id="user-456",
        risk_level=RiskLevel.HIGH,
        policy_overrides={"max_tokens": 1000, "temperature": 0.7},
    )


@pytest.fixture
def sample_session_context(sample_governance_config):
    """Create a sample session context."""
    return SessionContext(
        session_id="session-abc123",
        tenant_id="tenant-123",
        governance_config=sample_governance_config,
        metadata={"client_ip": "192.168.1.1", "user_agent": "test-client"},
    )


class TestSessionContext:
    """Tests for SessionContext model."""

    def test_session_context_creation(self, sample_governance_config):
        """Test creating a session context."""
        context = SessionContext(
            tenant_id="tenant-123",
            governance_config=sample_governance_config,
        )

        assert context.session_id is not None
        assert context.tenant_id == "tenant-123"
        # Compare key fields rather than full object to avoid Pydantic equality issues
        assert context.governance_config.tenant_id == sample_governance_config.tenant_id
        assert context.governance_config.user_id == sample_governance_config.user_id
        assert context.governance_config.risk_level == sample_governance_config.risk_level
        assert (
            context.governance_config.policy_overrides == sample_governance_config.policy_overrides
        )
        assert context.metadata == {}
        assert context.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(context.created_at, datetime)
        assert isinstance(context.updated_at, datetime)

    def test_session_context_with_custom_session_id(self, sample_governance_config):
        """Test creating session context with custom session ID."""
        custom_id = "custom-session-123"
        context = SessionContext(
            session_id=custom_id,
            tenant_id="tenant-123",
            governance_config=sample_governance_config,
        )

        assert context.session_id == custom_id

    def test_session_context_with_metadata(self, sample_governance_config):
        """Test session context with metadata."""
        metadata = {"key": "value", "number": 42}
        context = SessionContext(
            tenant_id="tenant-123",
            governance_config=sample_governance_config,
            metadata=metadata,
        )

        assert context.metadata == metadata

    def test_session_context_constitutional_hash_validation(self, sample_governance_config):
        """Test constitutional hash validation."""
        # Valid hash should work
        context = SessionContext(
            tenant_id="tenant-123",
            governance_config=sample_governance_config,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        assert context.constitutional_hash == CONSTITUTIONAL_HASH

        # Invalid hash should raise error
        with pytest.raises(ValueError, match="Constitutional hash mismatch"):
            SessionContext(
                tenant_id="tenant-123",
                governance_config=sample_governance_config,
                constitutional_hash="invalid-hash",
            )

    def test_session_context_to_dict(self, sample_session_context):
        """Test converting session context to dictionary."""
        data = sample_session_context.to_dict()

        assert data["session_id"] == sample_session_context.session_id
        assert "governance_config" in data
        assert data["metadata"] == sample_session_context.metadata
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "created_at" in data
        assert "updated_at" in data

    def test_session_context_from_dict(self, sample_session_context):
        """Test creating session context from dictionary."""
        data = sample_session_context.to_dict()
        restored = SessionContext.from_dict(data)

        assert restored.session_id == sample_session_context.session_id
        assert (
            restored.governance_config.tenant_id
            == sample_session_context.governance_config.tenant_id
        )
        assert (
            restored.governance_config.user_id == sample_session_context.governance_config.user_id
        )
        assert (
            restored.governance_config.risk_level
            == sample_session_context.governance_config.risk_level
        )
        assert restored.metadata == sample_session_context.metadata
        assert restored.constitutional_hash == CONSTITUTIONAL_HASH

    def test_session_context_roundtrip(self, sample_session_context):
        """Test round-trip serialization/deserialization."""
        data = sample_session_context.to_dict()
        json_str = json.dumps(data)
        restored_data = json.loads(json_str)
        restored = SessionContext.from_dict(restored_data)

        assert restored.session_id == sample_session_context.session_id
        assert restored.metadata == sample_session_context.metadata


class TestSessionContextStore:
    """Tests for SessionContextStore."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = AsyncMock()
        mock.ping = AsyncMock(return_value=True)
        mock.setex = AsyncMock(return_value=True)
        mock.set = AsyncMock(return_value=True)
        mock.get = AsyncMock(return_value=None)
        mock.delete = AsyncMock(return_value=1)
        mock.exists = AsyncMock(return_value=1)
        mock.expire = AsyncMock(return_value=1)
        mock.ttl = AsyncMock(return_value=3600)
        mock.close = AsyncMock()
        return mock

    @pytest.fixture
    def store(self):
        """Create a session context store."""
        return SessionContextStore(
            redis_url="redis://localhost:6379",
            key_prefix="test:session",
            default_ttl=3600,
        )

    async def test_store_initialization(self, store):
        """Test store initialization."""
        assert store.redis_url == "redis://localhost:6379"
        assert store.key_prefix == "test:session"
        assert store.default_ttl == 3600
        assert store.redis_client is None

    async def test_make_key(self, store):
        """Test Redis key generation with tenant isolation."""
        key = store._make_key("session-123", "tenant-123")
        assert key == "test:session:t:tenant-123:session-123"

    async def test_connect_success(self, store, mock_redis):
        """Test successful Redis connection."""
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            result = await store.connect()

            assert result is True
            assert store.redis_client is not None
            mock_redis.ping.assert_awaited_once()

    async def test_connect_failure(self, store):
        """Test failed Redis connection."""
        with patch("redis.asyncio.from_url", side_effect=ConnectionError("Connection failed")):
            result = await store.connect()

            assert result is False
            assert store.redis_client is None

    async def test_connect_redis_unavailable(self, store):
        """Test connection when Redis is not available."""
        with patch("enhanced_agent_bus.session_context.REDIS_AVAILABLE", False):
            result = await store.connect()

            assert result is False

    async def test_disconnect(self, store, mock_redis):
        """Test Redis disconnection."""
        store.redis_client = mock_redis
        await store.disconnect()

        mock_redis.close.assert_awaited_once()
        assert store.redis_client is None

    async def test_set_session_context(self, store, mock_redis, sample_session_context):
        """Test storing session context."""
        store.redis_client = mock_redis

        result = await store.set(sample_session_context, ttl=1800)

        assert result is True
        mock_redis.setex.assert_awaited_once()

        # Verify the key used - now includes tenant namespace
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "test:session:t:tenant-123:session-abc123"
        assert call_args[0][1] == 1800  # TTL

    async def test_set_session_context_default_ttl(self, store, mock_redis, sample_session_context):
        """Test storing session context with default TTL."""
        store.redis_client = mock_redis

        result = await store.set(sample_session_context)

        assert result is True
        mock_redis.setex.assert_awaited_once()

        # Verify default TTL is used
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 3600  # Default TTL

    async def test_set_session_context_no_ttl(self, store, mock_redis, sample_session_context):
        """Test storing session context without TTL."""
        store.redis_client = mock_redis

        result = await store.set(sample_session_context, ttl=0)

        assert result is True
        mock_redis.set.assert_awaited_once()

    async def test_set_without_connection(self, store, sample_session_context):
        """Test set operation without Redis connection."""
        result = await store.set(sample_session_context)
        assert result is False

    async def test_get_session_context(self, store, mock_redis, sample_session_context):
        """Test retrieving session context."""
        store.redis_client = mock_redis

        # Mock Redis to return serialized session context
        session_data = json.dumps(sample_session_context.to_dict())
        mock_redis.get = AsyncMock(return_value=session_data)

        result = await store.get("session-abc123", "tenant-123")

        assert result is not None
        assert result.session_id == sample_session_context.session_id
        assert result.governance_config.tenant_id == "tenant-123"
        mock_redis.get.assert_awaited_once_with("test:session:t:tenant-123:session-abc123")

    async def test_get_session_context_not_found(self, store, mock_redis):
        """Test retrieving non-existent session context."""
        store.redis_client = mock_redis
        mock_redis.get = AsyncMock(return_value=None)

        result = await store.get("non-existent", "tenant-123")

        assert result is None

    async def test_get_session_context_expired(self, store, mock_redis, sample_session_context):
        """Test retrieving expired session context."""
        store.redis_client = mock_redis

        # Set expiration in the past
        sample_session_context.expires_at = datetime.now(UTC) - timedelta(hours=1)
        session_data = json.dumps(sample_session_context.to_dict())
        mock_redis.get = AsyncMock(return_value=session_data)
        mock_redis.delete = AsyncMock(return_value=1)

        result = await store.get("session-abc123", "tenant-123")

        assert result is None
        mock_redis.delete.assert_awaited_once()

    async def test_get_without_connection(self, store):
        """Test get operation without Redis connection."""
        result = await store.get("session-123", "tenant-123")
        assert result is None

    async def test_delete_session_context(self, store, mock_redis):
        """Test deleting session context."""
        store.redis_client = mock_redis

        result = await store.delete("session-abc123", "tenant-123")

        assert result is True
        mock_redis.delete.assert_awaited_once_with("test:session:t:tenant-123:session-abc123")

    async def test_delete_without_connection(self, store):
        """Test delete operation without Redis connection."""
        result = await store.delete("session-123", "tenant-123")
        assert result is False

    async def test_exists_session_context(self, store, mock_redis):
        """Test checking session context existence."""
        store.redis_client = mock_redis
        mock_redis.exists = AsyncMock(return_value=1)

        result = await store.exists("session-abc123", "tenant-123")

        assert result is True
        mock_redis.exists.assert_awaited_once_with("test:session:t:tenant-123:session-abc123")

    async def test_exists_session_not_found(self, store, mock_redis):
        """Test checking non-existent session."""
        store.redis_client = mock_redis
        mock_redis.exists = AsyncMock(return_value=0)

        result = await store.exists("non-existent", "tenant-123")

        assert result is False

    async def test_exists_without_connection(self, store):
        """Test exists operation without Redis connection."""
        result = await store.exists("session-123", "tenant-123")
        assert result is False

    async def test_update_ttl(self, store, mock_redis):
        """Test updating session TTL."""
        store.redis_client = mock_redis
        mock_redis.expire = AsyncMock(return_value=1)

        result = await store.update_ttl("session-abc123", "tenant-123", 7200)

        assert result is True
        mock_redis.expire.assert_awaited_once_with("test:session:t:tenant-123:session-abc123", 7200)

    async def test_update_ttl_without_connection(self, store):
        """Test update TTL without Redis connection."""
        result = await store.update_ttl("session-123", "tenant-123", 3600)
        assert result is False

    async def test_get_ttl(self, store, mock_redis):
        """Test getting session TTL."""
        store.redis_client = mock_redis
        mock_redis.ttl = AsyncMock(return_value=1800)

        result = await store.get_ttl("session-abc123", "tenant-123")

        assert result == 1800
        mock_redis.ttl.assert_awaited_once_with("test:session:t:tenant-123:session-abc123")

    async def test_get_ttl_no_expiration(self, store, mock_redis):
        """Test getting TTL for session without expiration."""
        store.redis_client = mock_redis
        mock_redis.ttl = AsyncMock(return_value=-1)

        result = await store.get_ttl("session-abc123", "tenant-123")

        assert result is None

    async def test_get_ttl_not_found(self, store, mock_redis):
        """Test getting TTL for non-existent session."""
        store.redis_client = mock_redis
        mock_redis.ttl = AsyncMock(return_value=-2)

        result = await store.get_ttl("non-existent", "tenant-123")

        assert result is None

    async def test_get_ttl_without_connection(self, store):
        """Test get TTL without Redis connection."""
        result = await store.get_ttl("session-123", "tenant-123")
        assert result is None

    async def test_concurrent_operations(self, store, mock_redis, sample_session_context):
        """Test thread-safe concurrent operations."""
        store.redis_client = mock_redis

        # Simulate concurrent set operations
        async def set_operation():
            return await store.set(sample_session_context)

        results = await asyncio.gather(set_operation(), set_operation(), set_operation())

        assert all(results)
        assert mock_redis.setex.call_count == 3


@pytest.mark.integration
class TestSessionContextStoreIntegration:
    """Integration tests with real Redis (skipped if Redis unavailable)."""

    @pytest.fixture
    async def redis_store(self):
        """Create store and connect to real Redis."""
        store = SessionContextStore(
            redis_url="redis://localhost:6379",
            key_prefix="test:integration:session",
            default_ttl=60,
        )
        connected = await store.connect()
        if not connected:
            pytest.skip("Redis not available for integration tests")
        yield store
        await store.disconnect()

    async def test_full_lifecycle(self, redis_store, sample_session_context):
        """Test complete session lifecycle with real Redis."""
        tenant_id = sample_session_context.tenant_id

        # Set session
        result = await redis_store.set(sample_session_context, ttl=10)
        assert result is True

        # Check existence
        exists = await redis_store.exists(sample_session_context.session_id, tenant_id)
        assert exists is True

        # Get session
        retrieved = await redis_store.get(sample_session_context.session_id, tenant_id)
        assert retrieved is not None
        assert retrieved.session_id == sample_session_context.session_id

        # Update TTL
        updated = await redis_store.update_ttl(sample_session_context.session_id, tenant_id, 20)
        assert updated is True

        # Get TTL
        ttl = await redis_store.get_ttl(sample_session_context.session_id, tenant_id)
        assert ttl is not None
        assert ttl > 0

        # Delete session
        deleted = await redis_store.delete(sample_session_context.session_id, tenant_id)
        assert deleted is True

        # Verify deletion
        exists = await redis_store.exists(sample_session_context.session_id, tenant_id)
        assert exists is False


class TestSessionContextManager:
    """Tests for SessionContextManager."""

    @pytest.fixture
    def mock_store(self):
        """Create mock SessionContextStore."""
        store = MagicMock(spec=SessionContextStore)
        store.connect = AsyncMock(return_value=True)
        store.disconnect = AsyncMock()
        store.exists = AsyncMock(return_value=False)
        store.get = AsyncMock(return_value=None)
        store.set = AsyncMock(return_value=True)
        store.delete = AsyncMock(return_value=True)
        store.update_ttl = AsyncMock(return_value=True)
        return store

    @pytest.fixture
    def manager(self, mock_store):
        """Create SessionContextManager with mock store."""
        return SessionContextManager(
            store=mock_store, cache_size=10, cache_ttl=60, default_session_ttl=3600
        )

    def test_manager_initialization(self, manager):
        """Test manager initialization."""
        assert manager.cache_size == 10
        assert manager.cache_ttl == 60
        assert manager.default_session_ttl == 3600
        assert len(manager._cache) == 0
        metrics = manager.get_metrics()
        assert metrics["cache_hits"] == 0
        assert metrics["cache_misses"] == 0

    async def test_connect_disconnect(self, manager, mock_store):
        """Test connect and disconnect operations."""
        # Connect
        result = await manager.connect()
        assert result is True
        mock_store.connect.assert_called_once()

        # Disconnect
        await manager.disconnect()
        mock_store.disconnect.assert_called_once()

    async def test_create_session(self, manager, mock_store, sample_governance_config):
        """Test creating a new session."""
        session = await manager.create(
            governance_config=sample_governance_config,
            tenant_id="tenant-123",
            session_id="test-session-123",
            metadata={"test": "data"},
            ttl=1800,
        )

        assert session.session_id == "test-session-123"
        assert session.tenant_id == "tenant-123"
        # Compare key fields rather than full object to avoid Pydantic equality issues
        assert session.governance_config.tenant_id == sample_governance_config.tenant_id
        assert session.governance_config.user_id == sample_governance_config.user_id
        assert session.governance_config.risk_level == sample_governance_config.risk_level
        assert session.metadata == {"test": "data"}

        # Verify stored in Redis
        mock_store.set.assert_called_once()
        # Verify cached with tenant-namespaced key
        assert "tenant-123:test-session-123" in manager._cache
        # Verify metrics
        metrics = manager.get_metrics()
        assert metrics["creates"] == 1

    async def test_create_session_duplicate(self, manager, mock_store, sample_governance_config):
        """Test creating duplicate session raises error."""
        mock_store.exists = AsyncMock(return_value=True)

        with pytest.raises(ValueError, match="already exists"):
            await manager.create(
                governance_config=sample_governance_config,
                tenant_id="tenant-123",
                session_id="duplicate-session",
            )

    async def test_get_session_cache_hit(self, manager, mock_store, sample_session_context):
        """Test getting session from cache (cache hit)."""
        # Populate cache
        manager._update_cache(sample_session_context)

        # Get session with tenant_id
        result = await manager.get(
            sample_session_context.session_id, sample_session_context.tenant_id
        )

        assert result == sample_session_context
        # Should not call Redis
        mock_store.get.assert_not_called()
        # Verify metrics
        metrics = manager.get_metrics()
        assert metrics["cache_hits"] == 1
        assert metrics["cache_misses"] == 0

    async def test_get_session_cache_miss(self, manager, mock_store, sample_session_context):
        """Test getting session from Redis (cache miss)."""
        mock_store.get = AsyncMock(return_value=sample_session_context)

        # Get session (not in cache) with tenant_id
        result = await manager.get(
            sample_session_context.session_id, sample_session_context.tenant_id
        )

        assert result == sample_session_context
        # Should call Redis with session_id and tenant_id
        mock_store.get.assert_called_once_with(
            sample_session_context.session_id, sample_session_context.tenant_id
        )
        # Should now be in cache with tenant-namespaced key
        cache_key = f"{sample_session_context.tenant_id}:{sample_session_context.session_id}"
        assert cache_key in manager._cache
        # Verify metrics
        metrics = manager.get_metrics()
        assert metrics["cache_hits"] == 0
        assert metrics["cache_misses"] == 1

    async def test_update_session(self, manager, mock_store, sample_session_context):
        """Test updating session."""
        # Setup - session exists
        mock_store.get = AsyncMock(return_value=sample_session_context)

        # Update with new metadata
        new_governance_config = SessionGovernanceConfig(
            session_id=sample_session_context.session_id,
            tenant_id="new-tenant",
            user_id="new-user",
            risk_level=RiskLevel.LOW,
        )

        result = await manager.update(
            session_id=sample_session_context.session_id,
            tenant_id=sample_session_context.tenant_id,
            governance_config=new_governance_config,
            metadata={"updated": True},
            ttl=7200,
        )

        assert result is not None
        assert result.governance_config == new_governance_config
        assert result.metadata["updated"] is True
        # Verify metrics
        metrics = manager.get_metrics()
        assert metrics["updates"] == 1

    async def test_update_nonexistent_session(self, manager, mock_store):
        """Test updating non-existent session."""
        mock_store.get = AsyncMock(return_value=None)

        result = await manager.update(
            session_id="nonexistent",
            tenant_id="tenant-123",
            metadata={"test": "data"},
        )

        assert result is None

    async def test_delete_session(self, manager, mock_store, sample_session_context):
        """Test deleting session."""
        # Add to cache first
        manager._update_cache(sample_session_context)
        cache_key = f"{sample_session_context.tenant_id}:{sample_session_context.session_id}"
        assert cache_key in manager._cache

        # Delete with tenant_id
        result = await manager.delete(
            sample_session_context.session_id, sample_session_context.tenant_id
        )

        assert result is True
        mock_store.delete.assert_called_once_with(
            sample_session_context.session_id, sample_session_context.tenant_id
        )
        # Should be removed from cache
        assert cache_key not in manager._cache
        # Verify metrics
        metrics = manager.get_metrics()
        assert metrics["deletes"] == 1

    async def test_exists_in_cache(self, manager, sample_session_context):
        """Test exists check when session is in cache."""
        manager._update_cache(sample_session_context)

        result = await manager.exists(
            sample_session_context.session_id, sample_session_context.tenant_id
        )

        assert result is True

    async def test_exists_in_redis(self, manager, mock_store):
        """Test exists check when session is in Redis but not cache."""
        mock_store.exists = AsyncMock(return_value=True)

        result = await manager.exists("session-in-redis", "tenant-123")

        assert result is True
        mock_store.exists.assert_called_once_with("session-in-redis", "tenant-123")

    async def test_extend_ttl(self, manager, mock_store):
        """Test extending session TTL."""
        result = await manager.extend_ttl("session-123", "tenant-123", 7200)

        assert result is True
        mock_store.update_ttl.assert_called_once_with("session-123", "tenant-123", 7200)

    async def test_cache_lru_eviction(self, manager, sample_governance_config):
        """Test LRU cache eviction when cache is full."""
        # Create manager with small cache
        manager.cache_size = 3

        # Add 4 sessions (one more than capacity)
        sessions = []
        for i in range(4):
            session = SessionContext(
                session_id=f"session-{i}",
                tenant_id="tenant-123",
                governance_config=sample_governance_config,
            )
            sessions.append(session)
            manager._update_cache(session)

        # Cache should only have 3 sessions (oldest evicted)
        assert len(manager._cache) == 3
        # First session should be evicted (cache key is tenant_id:session_id)
        assert "tenant-123:session-0" not in manager._cache
        # Other sessions should be present
        assert "tenant-123:session-1" in manager._cache
        assert "tenant-123:session-2" in manager._cache
        assert "tenant-123:session-3" in manager._cache

    async def test_cache_ttl_expiration(self, manager, sample_session_context):
        """Test cache entry expiration based on TTL."""
        import time

        # Set very short cache TTL
        manager.cache_ttl = 0.1

        # Add to cache
        manager._update_cache(sample_session_context)

        # Cache key uses tenant_id:session_id format
        cache_key = f"{sample_session_context.tenant_id}:{sample_session_context.session_id}"

        # Immediately check - should be valid
        assert manager._is_cache_valid(cache_key)

        # Wait for TTL to expire
        await asyncio.sleep(0.15)

        # Should now be invalid
        assert not manager._is_cache_valid(cache_key)

    def test_get_metrics(self, manager):
        """Test getting metrics."""
        metrics = manager.get_metrics()

        assert "cache_hits" in metrics
        assert "cache_misses" in metrics
        assert "creates" in metrics
        assert "reads" in metrics
        assert "updates" in metrics
        assert "deletes" in metrics
        assert "errors" in metrics
        assert "cache_hit_rate" in metrics
        assert "cache_size" in metrics
        assert "cache_capacity" in metrics

        # Initially all zeros
        assert metrics["cache_hits"] == 0
        assert metrics["cache_hit_rate"] == 0.0

    def test_reset_metrics(self, manager):
        """Test resetting metrics."""
        # Set some metrics
        manager._metrics["cache_hits"] = 10
        manager._metrics["cache_misses"] = 5

        # Reset
        manager.reset_metrics()

        # Should be zero
        metrics = manager.get_metrics()
        assert metrics["cache_hits"] == 0
        assert metrics["cache_misses"] == 0

    async def test_clear_cache(self, manager, sample_session_context):
        """Test clearing cache."""
        # Add sessions to cache
        manager._update_cache(sample_session_context)
        assert len(manager._cache) > 0

        # Clear
        await manager.clear_cache()

        # Should be empty
        assert len(manager._cache) == 0
        assert len(manager._cache_timestamps) == 0

    async def test_concurrent_operations(self, manager, mock_store, sample_governance_config):
        """Test concurrent operations are thread-safe."""

        # Create multiple concurrent operations
        async def create_session(i):
            return await manager.create(
                governance_config=sample_governance_config,
                tenant_id="tenant-123",
                session_id=f"concurrent-{i}",
            )

        # Run concurrently
        results = await asyncio.gather(
            create_session(1),
            create_session(2),
            create_session(3),
        )

        # All should succeed
        assert len(results) == 3
        assert all(r.session_id.startswith("concurrent-") for r in results)

    async def test_cache_hit_rate_calculation(self, manager, sample_session_context):
        """Test cache hit rate calculation."""
        # Simulate cache hits and misses
        manager._update_cache(sample_session_context)

        # Cache hit
        await manager.get(sample_session_context.session_id, sample_session_context.tenant_id)

        # Cache miss
        mock_store = manager.store
        mock_store.get = AsyncMock(return_value=None)
        await manager.get("nonexistent", "tenant-123")

        # Check metrics
        metrics = manager.get_metrics()
        assert metrics["cache_hits"] == 1
        assert metrics["cache_misses"] == 1
        assert metrics["cache_hit_rate"] == 0.5  # 50%


@pytest.mark.integration
class TestSessionContextManagerIntegration:
    """Integration tests for SessionContextManager with real Redis."""

    @pytest.fixture
    async def redis_manager(self):
        """Create manager with real Redis."""
        manager = SessionContextManager(
            redis_url="redis://localhost:6379",
            cache_size=100,
            cache_ttl=300,
            default_session_ttl=3600,
        )
        connected = await manager.connect()
        if not connected:
            pytest.skip("Redis not available for integration tests")
        yield manager
        await manager.disconnect()

    async def test_full_crud_lifecycle(self, redis_manager, sample_governance_config):
        """Test complete CRUD lifecycle with real Redis."""
        tenant_id = "integration-tenant"

        # Create
        session = await redis_manager.create(
            governance_config=sample_governance_config,
            tenant_id=tenant_id,
            session_id="integration-test-session",
            metadata={"test": "integration"},
            ttl=60,
        )
        assert session.session_id == "integration-test-session"
        assert session.tenant_id == tenant_id

        # Read (should be from cache)
        retrieved = await redis_manager.get("integration-test-session", tenant_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

        # Update
        updated = await redis_manager.update(
            session_id="integration-test-session",
            tenant_id=tenant_id,
            metadata={"updated": True},
        )
        assert updated is not None
        assert updated.metadata["updated"] is True

        # Exists
        exists = await redis_manager.exists("integration-test-session", tenant_id)
        assert exists is True

        # Delete
        deleted = await redis_manager.delete("integration-test-session", tenant_id)
        assert deleted is True

        # Verify deletion
        exists = await redis_manager.exists("integration-test-session", tenant_id)
        assert exists is False

    async def test_cache_performance(self, redis_manager, sample_governance_config):
        """Test cache improves performance."""
        tenant_id = "cache-perf-tenant"

        # Ensure clean state from prior runs
        try:
            await redis_manager.delete("cache-perf-test", tenant_id)
        except Exception:
            pass

        # Create session
        session = await redis_manager.create(
            governance_config=sample_governance_config,
            tenant_id=tenant_id,
            session_id="cache-perf-test",
        )

        # Record baseline metrics after create (create populates cache)
        baseline = redis_manager.get_metrics()
        baseline_hits = baseline["cache_hits"]
        baseline_misses = baseline["cache_misses"]

        # Evict from local cache so first get is a true cache miss
        redis_manager._invalidate_cache("cache-perf-test", tenant_id)

        # First get - cache miss (from Redis)
        await redis_manager.get("cache-perf-test", tenant_id)

        # Second get - cache hit (from memory)
        await redis_manager.get("cache-perf-test", tenant_id)

        # Check that we got exactly 1 new hit and 1 new miss
        metrics = redis_manager.get_metrics()
        assert metrics["cache_hits"] - baseline_hits == 1
        assert metrics["cache_misses"] - baseline_misses == 1

        # Cleanup
        await redis_manager.delete("cache-perf-test", tenant_id)
