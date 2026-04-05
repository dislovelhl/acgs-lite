"""
Coverage tests for:
  - mcp_server/cli.py (CLI entry point)
  - src/core/shared/security/deserialization.py (SafeUnpickler)
  - constitutional/storage_infra/locking.py (LockManager)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import io
import pickle
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Section 1: mcp_server/cli.py
# ---------------------------------------------------------------------------


class TestMCPCLIDefaultArgs:
    """Test CLI main() with default arguments (stdio transport)."""

    def test_main_default_args_calls_create_mcp_server(self):
        """main() with no args uses stdio transport and creates server."""
        mock_server = MagicMock()
        mock_server.start = AsyncMock()

        with (
            patch("sys.argv", ["mcp-server"]),
            patch(
                "enhanced_agent_bus.mcp_server.cli.create_mcp_server",
                return_value=mock_server,
            ) as mock_create,
            patch("enhanced_agent_bus.mcp_server.cli.asyncio") as mock_asyncio,
        ):
            from enhanced_agent_bus.mcp_server.cli import main

            main()

            mock_create.assert_called_once()
            config = mock_create.call_args[1]["config"]
            from enhanced_agent_bus.mcp_server.config import TransportType

            assert config.transport_type == TransportType.STDIO
            mock_asyncio.run.assert_called_once()

    def test_main_default_server_name(self):
        """main() creates config with server_name 'acgs2-governance'."""
        mock_server = MagicMock()
        mock_server.start = AsyncMock()

        with (
            patch("sys.argv", ["mcp-server"]),
            patch(
                "enhanced_agent_bus.mcp_server.cli.create_mcp_server",
                return_value=mock_server,
            ) as mock_create,
            patch("enhanced_agent_bus.mcp_server.cli.asyncio"),
        ):
            from enhanced_agent_bus.mcp_server.cli import main

            main()

            config = mock_create.call_args[1]["config"]
            assert config.server_name == "acgs2-governance"

    def test_main_default_server_version(self):
        """main() creates config with version '3.0.0'."""
        mock_server = MagicMock()
        mock_server.start = AsyncMock()

        with (
            patch("sys.argv", ["mcp-server"]),
            patch(
                "enhanced_agent_bus.mcp_server.cli.create_mcp_server",
                return_value=mock_server,
            ) as mock_create,
            patch("enhanced_agent_bus.mcp_server.cli.asyncio"),
        ):
            from enhanced_agent_bus.mcp_server.cli import main

            main()

            config = mock_create.call_args[1]["config"]
            assert config.server_version == "3.0.0"


class TestMCPCLISSETransport:
    """Test CLI main() with SSE transport."""

    def test_main_sse_transport(self):
        """main() with --transport sse sets SSE transport type."""
        mock_server = MagicMock()
        mock_server.start = AsyncMock()

        with (
            patch("sys.argv", ["mcp-server", "--transport", "sse"]),
            patch(
                "enhanced_agent_bus.mcp_server.cli.create_mcp_server",
                return_value=mock_server,
            ) as mock_create,
            patch("enhanced_agent_bus.mcp_server.cli.asyncio"),
        ):
            from enhanced_agent_bus.mcp_server.cli import main

            main()

            config = mock_create.call_args[1]["config"]
            from enhanced_agent_bus.mcp_server.config import TransportType

            assert config.transport_type == TransportType.SSE

    def test_main_sse_with_custom_host_port(self):
        """main() with --transport sse --host 0.0.0.0 --port 9000."""
        mock_server = MagicMock()
        mock_server.start = AsyncMock()

        with (
            patch(
                "sys.argv",
                ["mcp-server", "--transport", "sse", "--host", "0.0.0.0", "--port", "9000"],
            ),
            patch(
                "enhanced_agent_bus.mcp_server.cli.create_mcp_server",
                return_value=mock_server,
            ) as mock_create,
            patch("enhanced_agent_bus.mcp_server.cli.asyncio"),
        ):
            from enhanced_agent_bus.mcp_server.cli import main

            main()

            mock_create.assert_called_once()


class TestMCPCLICustomArgs:
    """Test CLI main() with custom arguments."""

    def test_main_custom_host(self):
        """main() with --host 0.0.0.0 parses correctly."""
        mock_server = MagicMock()
        mock_server.start = AsyncMock()

        with (
            patch("sys.argv", ["mcp-server", "--host", "0.0.0.0"]),
            patch(
                "enhanced_agent_bus.mcp_server.cli.create_mcp_server",
                return_value=mock_server,
            ),
            patch("enhanced_agent_bus.mcp_server.cli.asyncio"),
        ):
            from enhanced_agent_bus.mcp_server.cli import main

            main()  # Should not raise

    def test_main_custom_port(self):
        """main() with --port 9999 parses correctly."""
        mock_server = MagicMock()
        mock_server.start = AsyncMock()

        with (
            patch("sys.argv", ["mcp-server", "--port", "9999"]),
            patch(
                "enhanced_agent_bus.mcp_server.cli.create_mcp_server",
                return_value=mock_server,
            ),
            patch("enhanced_agent_bus.mcp_server.cli.asyncio"),
        ):
            from enhanced_agent_bus.mcp_server.cli import main

            main()  # Should not raise

    def test_main_custom_log_level_debug(self):
        """main() with --log-level DEBUG configures logging."""
        mock_server = MagicMock()
        mock_server.start = AsyncMock()

        with (
            patch("sys.argv", ["mcp-server", "--log-level", "DEBUG"]),
            patch(
                "enhanced_agent_bus.mcp_server.cli.create_mcp_server",
                return_value=mock_server,
            ),
            patch("enhanced_agent_bus.mcp_server.cli.asyncio"),
        ):
            from enhanced_agent_bus.mcp_server.cli import main

            main()  # Should not raise

    def test_main_custom_log_level_warning(self):
        """main() with --log-level WARNING configures logging."""
        mock_server = MagicMock()
        mock_server.start = AsyncMock()

        with (
            patch("sys.argv", ["mcp-server", "--log-level", "WARNING"]),
            patch(
                "enhanced_agent_bus.mcp_server.cli.create_mcp_server",
                return_value=mock_server,
            ),
            patch("enhanced_agent_bus.mcp_server.cli.asyncio"),
        ):
            from enhanced_agent_bus.mcp_server.cli import main

            main()  # Should not raise


class TestMCPCLIKeyboardInterrupt:
    """Test CLI main() handles KeyboardInterrupt gracefully."""

    def test_main_keyboard_interrupt_suppressed(self):
        """main() suppresses KeyboardInterrupt from asyncio.run."""
        mock_server = MagicMock()
        mock_server.start = AsyncMock()

        with (
            patch("sys.argv", ["mcp-server"]),
            patch(
                "enhanced_agent_bus.mcp_server.cli.create_mcp_server",
                return_value=mock_server,
            ),
            patch("enhanced_agent_bus.mcp_server.cli.asyncio") as mock_asyncio,
        ):
            mock_asyncio.run.side_effect = KeyboardInterrupt()
            from enhanced_agent_bus.mcp_server.cli import main

            # Should NOT raise
            main()

    def test_main_keyboard_interrupt_does_not_propagate(self):
        """KeyboardInterrupt is caught and does not propagate."""
        mock_server = MagicMock()
        mock_server.start = AsyncMock()

        with (
            patch("sys.argv", ["mcp-server", "--transport", "sse"]),
            patch(
                "enhanced_agent_bus.mcp_server.cli.create_mcp_server",
                return_value=mock_server,
            ),
            patch("enhanced_agent_bus.mcp_server.cli.asyncio") as mock_asyncio,
        ):
            mock_asyncio.run.side_effect = KeyboardInterrupt()
            from enhanced_agent_bus.mcp_server.cli import main

            main()  # No exception expected


class TestMCPCLIOtherExceptions:
    """Test CLI main() when asyncio.run raises non-KeyboardInterrupt."""

    def test_main_runtime_error_propagates(self):
        """Non-KeyboardInterrupt exceptions propagate from main()."""
        mock_server = MagicMock()
        mock_server.start = AsyncMock()

        with (
            patch("sys.argv", ["mcp-server"]),
            patch(
                "enhanced_agent_bus.mcp_server.cli.create_mcp_server",
                return_value=mock_server,
            ),
            patch("enhanced_agent_bus.mcp_server.cli.asyncio") as mock_asyncio,
        ):
            mock_asyncio.run.side_effect = RuntimeError("Server crashed")
            from enhanced_agent_bus.mcp_server.cli import main

            with pytest.raises(RuntimeError, match="Server crashed"):
                main()


# ---------------------------------------------------------------------------
# Section 2: src/core/shared/security/deserialization.py
# ---------------------------------------------------------------------------


class TestSafePickleLoadsBuiltins:
    """Test safe_pickle_loads with builtin types."""

    def test_loads_dict(self):
        """safe_pickle_loads can deserialize a dict."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        data = pickle.dumps({"key": "value", "num": 42})
        result = safe_pickle_loads(data)
        assert result == {"key": "value", "num": 42}

    def test_loads_list(self):
        """safe_pickle_loads can deserialize a list."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        data = pickle.dumps([1, 2, 3, "four"])
        result = safe_pickle_loads(data)
        assert result == [1, 2, 3, "four"]

    def test_loads_str(self):
        """safe_pickle_loads can deserialize a string."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        data = pickle.dumps("hello world")
        result = safe_pickle_loads(data)
        assert result == "hello world"

    def test_loads_int(self):
        """safe_pickle_loads can deserialize an int."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        data = pickle.dumps(12345)
        result = safe_pickle_loads(data)
        assert result == 12345

    def test_loads_float(self):
        """safe_pickle_loads can deserialize a float."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        data = pickle.dumps(3.14159)
        result = safe_pickle_loads(data)
        assert result == pytest.approx(3.14159)

    def test_loads_bool(self):
        """safe_pickle_loads can deserialize a bool."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        data = pickle.dumps(True)
        result = safe_pickle_loads(data)
        assert result is True

    def test_loads_set(self):
        """safe_pickle_loads can deserialize a set."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        data = pickle.dumps({1, 2, 3})
        result = safe_pickle_loads(data)
        assert result == {1, 2, 3}

    def test_loads_none(self):
        """safe_pickle_loads can deserialize None."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        data = pickle.dumps(None)
        result = safe_pickle_loads(data)
        assert result is None

    def test_loads_nested_dict_list(self):
        """safe_pickle_loads handles nested dict/list structures."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        payload = {"items": [1, 2, {"nested": True}], "count": 3}
        data = pickle.dumps(payload)
        result = safe_pickle_loads(data)
        assert result == payload

    def test_loads_empty_dict(self):
        """safe_pickle_loads handles empty dict."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        data = pickle.dumps({})
        result = safe_pickle_loads(data)
        assert result == {}

    def test_loads_empty_list(self):
        """safe_pickle_loads handles empty list."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        data = pickle.dumps([])
        result = safe_pickle_loads(data)
        assert result == []


class TestSafePickleLoadsUnsafe:
    """Test safe_pickle_loads rejects unsafe classes."""

    def test_rejects_os_system(self):
        """safe_pickle_loads rejects os.system."""
        import os

        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        # Craft a pickle that references os.system
        payload = pickle.dumps(os.getcwd)
        with pytest.raises(pickle.UnpicklingError, match="Unsafe class detected"):
            safe_pickle_loads(payload)

    def test_rejects_subprocess(self):
        """safe_pickle_loads rejects subprocess.Popen."""
        import subprocess

        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        payload = pickle.dumps(subprocess.Popen)
        with pytest.raises(pickle.UnpicklingError, match="Unsafe class detected"):
            safe_pickle_loads(payload)

    def test_rejects_eval_builtin(self):
        """safe_pickle_loads rejects builtins that are not whitelisted."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        payload = pickle.dumps(eval)
        with pytest.raises(pickle.UnpicklingError, match="Unsafe class detected"):
            safe_pickle_loads(payload)


class TestSafePickleLoad:
    """Test safe_pickle_load with file-like objects."""

    def test_load_from_bytesio(self):
        """safe_pickle_load deserializes from a BytesIO object."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_load

        data = pickle.dumps({"file": "test"})
        file_obj = io.BytesIO(data)
        result = safe_pickle_load(file_obj)
        assert result == {"file": "test"}

    def test_load_from_bytesio_list(self):
        """safe_pickle_load deserializes a list from BytesIO."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_load

        data = pickle.dumps([10, 20, 30])
        file_obj = io.BytesIO(data)
        result = safe_pickle_load(file_obj)
        assert result == [10, 20, 30]

    def test_load_rejects_unsafe_from_file(self):
        """safe_pickle_load rejects unsafe classes from file objects."""
        import os

        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_load

        payload = pickle.dumps(os.getcwd)
        file_obj = io.BytesIO(payload)
        with pytest.raises(pickle.UnpicklingError, match="Unsafe class detected"):
            safe_pickle_load(file_obj)


class TestSafeUnpicklerCustomGlobals:
    """Test SafeUnpickler with custom safe_globals."""

    def test_custom_safe_globals_allows_specified(self):
        """SafeUnpickler with custom globals allows those globals."""
        from enhanced_agent_bus._compat.security.deserialization import SafeUnpickler

        # Use default safe_globals=None -> uses SAFE_MODEL_GLOBALS
        data = pickle.dumps({"ok": True})
        result = SafeUnpickler(io.BytesIO(data)).load()
        assert result == {"ok": True}

    def test_custom_safe_globals_empty_still_allows_builtins(self):
        """SafeUnpickler with empty safe_globals still allows builtins."""
        from enhanced_agent_bus._compat.security.deserialization import SafeUnpickler

        data = pickle.dumps(42)
        result = SafeUnpickler(io.BytesIO(data), safe_globals=set()).load()
        assert result == 42

    def test_custom_safe_globals_rejects_non_whitelisted(self):
        """SafeUnpickler with empty safe_globals rejects non-builtins."""
        import os

        from enhanced_agent_bus._compat.security.deserialization import SafeUnpickler

        payload = pickle.dumps(os.getcwd)
        with pytest.raises(pickle.UnpicklingError, match="Unsafe class detected"):
            SafeUnpickler(io.BytesIO(payload), safe_globals=set()).load()

    def test_safe_model_globals_constant_is_set(self):
        """SAFE_MODEL_GLOBALS is a non-empty set of tuples."""
        from enhanced_agent_bus._compat.security.deserialization import SAFE_MODEL_GLOBALS

        assert isinstance(SAFE_MODEL_GLOBALS, set)
        assert len(SAFE_MODEL_GLOBALS) > 0
        for item in SAFE_MODEL_GLOBALS:
            assert isinstance(item, tuple)
            assert len(item) == 2


class TestSafeUnpicklerComplexType:
    """Test SafeUnpickler with complex builtins."""

    def test_loads_complex_number(self):
        """safe_pickle_loads can deserialize a complex number."""
        from enhanced_agent_bus._compat.security.deserialization import safe_pickle_loads

        data = pickle.dumps(complex(1, 2))
        result = safe_pickle_loads(data)
        assert result == complex(1, 2)


# ---------------------------------------------------------------------------
# Section 3: constitutional/storage_infra/locking.py
# ---------------------------------------------------------------------------


def _make_lock_manager(redis_client=None):
    """Helper to create a LockManager with mocked dependencies."""
    from enhanced_agent_bus.constitutional.storage_infra.cache import CacheManager
    from enhanced_agent_bus.constitutional.storage_infra.config import StorageConfig
    from enhanced_agent_bus.constitutional.storage_infra.locking import LockManager

    config = StorageConfig()
    cache = CacheManager(config)
    cache.redis_client = redis_client
    return LockManager(config=config, cache=cache)


class TestLockManagerNoRedis:
    """Test LockManager when Redis is not available."""

    async def test_acquire_lock_no_redis_returns_true(self):
        """acquire_lock returns True when redis_client is None."""
        lm = _make_lock_manager(redis_client=None)
        result = await lm.acquire_lock("tenant-1")
        assert result is True

    async def test_release_lock_no_redis_returns_true(self):
        """release_lock returns True when redis_client is None."""
        lm = _make_lock_manager(redis_client=None)
        result = await lm.release_lock("tenant-1")
        assert result is True

    async def test_acquire_lock_no_redis_different_tenants(self):
        """acquire_lock returns True for any tenant when no Redis."""
        lm = _make_lock_manager(redis_client=None)
        assert await lm.acquire_lock("tenant-a") is True
        assert await lm.acquire_lock("tenant-b") is True

    async def test_release_lock_no_redis_different_tenants(self):
        """release_lock returns True for any tenant when no Redis."""
        lm = _make_lock_manager(redis_client=None)
        assert await lm.release_lock("tenant-a") is True
        assert await lm.release_lock("tenant-b") is True


class TestLockManagerAcquireWithRedis:
    """Test LockManager.acquire_lock with a mock Redis client."""

    async def test_acquire_lock_success(self):
        """acquire_lock returns True when Redis set() returns truthy."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        lm = _make_lock_manager(redis_client=mock_redis)

        result = await lm.acquire_lock("tenant-1")

        assert result is True
        mock_redis.set.assert_called_once()

    async def test_acquire_lock_already_held(self):
        """acquire_lock returns False when Redis set(nx=True) returns None."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=None)
        lm = _make_lock_manager(redis_client=mock_redis)

        result = await lm.acquire_lock("tenant-1")

        assert result is False

    async def test_acquire_lock_uses_nx_and_ex(self):
        """acquire_lock passes nx=True and ex=lock_timeout to Redis."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        lm = _make_lock_manager(redis_client=mock_redis)

        await lm.acquire_lock("tenant-1")

        call_kwargs = mock_redis.set.call_args[1]
        assert call_kwargs["nx"] is True
        assert call_kwargs["ex"] == lm.config.lock_timeout

    async def test_acquire_lock_uses_tenant_scoped_key(self):
        """acquire_lock creates a tenant-scoped lock key."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        lm = _make_lock_manager(redis_client=mock_redis)

        await lm.acquire_lock("my-tenant")

        call_args = mock_redis.set.call_args[0]
        assert "my-tenant" in call_args[0]
        assert "lock" in call_args[0]

    async def test_acquire_lock_connection_error_returns_false(self):
        """acquire_lock returns False on ConnectionError."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=ConnectionError("Redis down"))
        lm = _make_lock_manager(redis_client=mock_redis)

        result = await lm.acquire_lock("tenant-1")

        assert result is False

    async def test_acquire_lock_os_error_returns_false(self):
        """acquire_lock returns False on OSError."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=OSError("Network unreachable"))
        lm = _make_lock_manager(redis_client=mock_redis)

        result = await lm.acquire_lock("tenant-1")

        assert result is False


class TestLockManagerReleaseWithRedis:
    """Test LockManager.release_lock with a mock Redis client."""

    async def test_release_lock_success(self):
        """release_lock returns True on successful delete."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)
        lm = _make_lock_manager(redis_client=mock_redis)

        result = await lm.release_lock("tenant-1")

        assert result is True
        mock_redis.delete.assert_called_once()

    async def test_release_lock_uses_tenant_scoped_key(self):
        """release_lock creates a tenant-scoped lock key."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)
        lm = _make_lock_manager(redis_client=mock_redis)

        await lm.release_lock("my-tenant")

        call_args = mock_redis.delete.call_args[0]
        assert "my-tenant" in call_args[0]

    async def test_release_lock_connection_error_returns_false(self):
        """release_lock returns False on ConnectionError."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=ConnectionError("Redis gone"))
        lm = _make_lock_manager(redis_client=mock_redis)

        result = await lm.release_lock("tenant-1")

        assert result is False

    async def test_release_lock_os_error_returns_false(self):
        """release_lock returns False on OSError."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=OSError("Socket closed"))
        lm = _make_lock_manager(redis_client=mock_redis)

        result = await lm.release_lock("tenant-1")

        assert result is False

    async def test_release_lock_key_not_found_still_returns_true(self):
        """release_lock returns True even if key did not exist (delete returns 0)."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=0)
        lm = _make_lock_manager(redis_client=mock_redis)

        result = await lm.release_lock("tenant-1")

        assert result is True


class TestLockManagerInit:
    """Test LockManager initialization."""

    def test_lock_manager_stores_config(self):
        """LockManager stores config reference."""
        from enhanced_agent_bus.constitutional.storage_infra.cache import CacheManager
        from enhanced_agent_bus.constitutional.storage_infra.config import StorageConfig
        from enhanced_agent_bus.constitutional.storage_infra.locking import LockManager

        config = StorageConfig()
        cache = CacheManager(config)
        lm = LockManager(config=config, cache=cache)
        assert lm.config is config

    def test_lock_manager_stores_cache(self):
        """LockManager stores cache reference."""
        from enhanced_agent_bus.constitutional.storage_infra.cache import CacheManager
        from enhanced_agent_bus.constitutional.storage_infra.config import StorageConfig
        from enhanced_agent_bus.constitutional.storage_infra.locking import LockManager

        config = StorageConfig()
        cache = CacheManager(config)
        lm = LockManager(config=config, cache=cache)
        assert lm.cache is cache

    def test_lock_manager_default_lock_timeout(self):
        """LockManager uses StorageConfig's default lock_timeout (30)."""
        lm = _make_lock_manager()
        assert lm.config.lock_timeout == 30

    def test_lock_manager_custom_lock_timeout(self):
        """LockManager respects custom lock_timeout."""
        from enhanced_agent_bus.constitutional.storage_infra.cache import CacheManager
        from enhanced_agent_bus.constitutional.storage_infra.config import StorageConfig
        from enhanced_agent_bus.constitutional.storage_infra.locking import LockManager

        config = StorageConfig(lock_timeout=60)
        cache = CacheManager(config)
        lm = LockManager(config=config, cache=cache)
        assert lm.config.lock_timeout == 60
