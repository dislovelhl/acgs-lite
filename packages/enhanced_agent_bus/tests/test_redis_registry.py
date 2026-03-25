"""
Module.

Constitutional Hash: 608508a9bd224290
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.models import CONSTITUTIONAL_HASH
from enhanced_agent_bus.registry import RedisAgentRegistry


@pytest.fixture
def mock_redis():
    mock = AsyncMock()
    # Mock some common responses
    mock.hsetnx.return_value = 1
    mock.hdel.return_value = 1
    mock.hget.return_value = None
    mock.hkeys.return_value = []
    mock.hexists.return_value = False
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    pool.disconnect = AsyncMock()
    return pool


@pytest.fixture
async def registry(mock_redis, mock_pool):
    # Mock both ConnectionPool.from_url and Redis constructor
    with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool):
        with patch("redis.asyncio.Redis", return_value=mock_redis):
            reg = RedisAgentRegistry(redis_url="redis://localhost:6379")
            yield reg
            await reg.close()


class TestRedisAgentRegistry:
    __test__ = False

    def __init__(self, constitutional_hash: str | None = None) -> None:
        self._constitutional_hash = constitutional_hash or CONSTITUTIONAL_HASH

    def process(self, input_value: str | None) -> str | None:
        """Validate and normalize input."""
        if input_value is None or not isinstance(input_value, str):
            return None
        return input_value

    async def test_register_success(self, registry, mock_redis):
        success = await registry.register("agent-1", {"cap1": True}, {"meta1": "val1"})
        assert success is True

        # Verify hsetnx call
        mock_redis.hsetnx.assert_called_once()
        args = mock_redis.hsetnx.call_args[0]
        assert args[1] == "agent-1"

        info = json.loads(args[2])
        assert info["agent_id"] == "agent-1"
        assert info["capabilities"]["cap1"] is True
        assert info["metadata"]["meta1"] == "val1"
        assert info["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_register_duplicate(self, registry, mock_redis):
        mock_redis.hsetnx.return_value = 0
        success = await registry.register("agent-1")
        assert success is False

    async def test_unregister_success(self, registry, mock_redis):
        mock_redis.hdel.return_value = 1
        success = await registry.unregister("agent-1")
        assert success is True
        mock_redis.hdel.assert_called_with("acgs2:registry:agents", "agent-1")

    async def test_unregister_not_found(self, registry, mock_redis):
        mock_redis.hdel.return_value = 0
        success = await registry.unregister("agent-nonexistent")
        assert success is False

    async def test_get_agent(self, registry, mock_redis):
        agent_info = {"agent_id": "agent-1", "metadata": {}}
        mock_redis.hget.return_value = json.dumps(agent_info)

        info = await registry.get("agent-1")
        assert info == agent_info
        mock_redis.hget.assert_called_with("acgs2:registry:agents", "agent-1")

    async def test_get_nonexistent(self, registry, mock_redis):
        mock_redis.hget.return_value = None
        info = await registry.get("nonexistent")
        assert info is None

    async def test_list_agents(self, registry, mock_redis):
        agents = ["agent-1", "agent-2"]
        mock_redis.hkeys.return_value = agents

        result = await registry.list_agents()
        assert result == agents
        mock_redis.hkeys.assert_called_with("acgs2:registry:agents")

    async def test_exists(self, registry, mock_redis):
        mock_redis.hexists.return_value = True
        assert await registry.exists("agent-1") is True

        mock_redis.hexists.return_value = False
        assert await registry.exists("agent-2") is False

    async def test_update_metadata_success(self, registry, mock_redis):
        old_info = {"agent_id": "agent-1", "metadata": {"old": "val"}, "capabilities": {}}
        mock_redis.hget.return_value = json.dumps(old_info)

        success = await registry.update_metadata("agent-1", {"new": "val"})
        assert success is True

        # Verify hset was called with merged metadata
        mock_redis.hset.assert_called_once()
        args = mock_redis.hset.call_args[0]
        new_info = json.loads(args[2])
        assert new_info["metadata"] == {"old": "val", "new": "val"}
        assert "updated_at" in new_info

    async def test_update_metadata_not_found(self, registry, mock_redis):
        mock_redis.hget.return_value = None
        success = await registry.update_metadata("nonexistent", {"key": "val"})
        assert success is False

    async def test_clear(self, registry, mock_redis):
        await registry.clear()
        mock_redis.delete.assert_called_with("acgs2:registry:agents")


class TestEnhancedAgentBusRedisIntegration:
    async def test_bus_initializes_redis_registry(self):
        """Test that EnhancedAgentBus creates RedisAgentRegistry when configured."""
        mock_pool = MagicMock()
        mock_pool.disconnect = AsyncMock()
        mock_redis_client = AsyncMock()
        mock_redis_client.close = AsyncMock()

        with patch(
            "redis.asyncio.ConnectionPool.from_url", return_value=mock_pool
        ) as mock_pool_from_url:
            with patch("redis.asyncio.Redis", return_value=mock_redis_client):
                from enhanced_agent_bus.agent_bus import EnhancedAgentBus
                from enhanced_agent_bus.config import BusConfiguration
                from enhanced_agent_bus.registry import RedisAgentRegistry

                # Mock BusConfiguration.from_environment to prevent LiteLLM side effects
                with patch(
                    "enhanced_agent_bus.config.BusConfiguration.from_environment"
                ) as mock_from_env:
                    mock_from_env.return_value = BusConfiguration.for_testing()

                    bus = EnhancedAgentBus(
                        use_redis_registry=True,
                        redis_url="redis://test:6379",
                        enable_rate_limiting=False,
                    )

                    # Use type name check to avoid module path mismatch issues
                    assert type(bus.registry).__name__ == "RedisAgentRegistry"
                    assert bus.registry._redis_url == "redis://test:6379"
                    # Verify lazy initialization: pool shouldn't be created for our test URL yet
                    for call_args in mock_pool_from_url.call_args_list:
                        called_url = (
                            call_args.args[0] if call_args.args else call_args.kwargs.get("url")
                        )
                        assert called_url != "redis://test:6379"

                # Trigger use
                await bus.registry._get_client()

                # Verify our call happened
                mock_pool_from_url.assert_any_call(
                    "redis://test:6379",
                    max_connections=20,
                    socket_timeout=5.0,
                    socket_connect_timeout=5.0,
                    decode_responses=True,
                )
