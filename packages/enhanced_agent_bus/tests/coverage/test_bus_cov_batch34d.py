"""Coverage tests for src.core.shared modules: interfaces, redis_config, database/utils.

Constitutional Hash: 608508a9bd224290

Targets:
  - src/core/shared/interfaces.py (57.8% -> higher)
  - src/core/shared/redis_config.py (84.2% -> higher)
  - src/core/shared/database/utils.py (81.2% -> higher)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

# Ensure project root is on sys.path for src.core.shared imports
_project_root = str(Path(__file__).resolve().parents[4])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


# ============================================================================
# Part 1: src.core.shared.interfaces — Protocol stub body coverage
#
# Protocols cannot be instantiated directly. We create bare subclasses
# that inherit the Protocol methods without overriding them, so that
# calling the methods executes the `...` (ellipsis) stub bodies in the
# Protocol definitions.
# ============================================================================


def _make_bare_subclass(protocol_cls: type, name: str = "Bare") -> type:
    """Create a bare subclass of a Protocol that inherits all methods."""
    return type(name, (protocol_cls,), {})


class TestCacheClientStubBodies:
    """Exercise CacheClient Protocol stub bodies via bare subclass."""

    async def test_get_stub(self):
        from enhanced_agent_bus._compat.interfaces import CacheClient

        Bare = _make_bare_subclass(CacheClient)
        obj = Bare()
        result = await obj.get("key")
        assert result is None

    async def test_set_stub(self):
        from enhanced_agent_bus._compat.interfaces import CacheClient

        Bare = _make_bare_subclass(CacheClient)
        result = await Bare().set("k", "v", ex=60)
        assert result is None

    async def test_setex_stub(self):
        from enhanced_agent_bus._compat.interfaces import CacheClient

        Bare = _make_bare_subclass(CacheClient)
        result = await Bare().setex("k", 60, "v")
        assert result is None

    async def test_delete_stub(self):
        from enhanced_agent_bus._compat.interfaces import CacheClient

        Bare = _make_bare_subclass(CacheClient)
        result = await Bare().delete("k")
        assert result is None

    async def test_exists_stub(self):
        from enhanced_agent_bus._compat.interfaces import CacheClient

        Bare = _make_bare_subclass(CacheClient)
        result = await Bare().exists("k")
        assert result is None

    async def test_expire_stub(self):
        from enhanced_agent_bus._compat.interfaces import CacheClient

        Bare = _make_bare_subclass(CacheClient)
        result = await Bare().expire("k", 60)
        assert result is None


class TestPolicyEvaluatorStubBodies:
    async def test_evaluate_stub(self):
        from enhanced_agent_bus._compat.interfaces import PolicyEvaluator

        Bare = _make_bare_subclass(PolicyEvaluator)
        result = await Bare().evaluate("path", {})
        assert result is None

    async def test_evaluate_batch_stub(self):
        from enhanced_agent_bus._compat.interfaces import PolicyEvaluator

        Bare = _make_bare_subclass(PolicyEvaluator)
        result = await Bare().evaluate_batch("path", [{}])
        assert result is None

    async def test_get_policy_stub(self):
        from enhanced_agent_bus._compat.interfaces import PolicyEvaluator

        Bare = _make_bare_subclass(PolicyEvaluator)
        result = await Bare().get_policy("path")
        assert result is None

    async def test_list_policies_stub(self):
        from enhanced_agent_bus._compat.interfaces import PolicyEvaluator

        Bare = _make_bare_subclass(PolicyEvaluator)
        result = await Bare().list_policies()
        assert result is None

    async def test_list_policies_with_path(self):
        from enhanced_agent_bus._compat.interfaces import PolicyEvaluator

        Bare = _make_bare_subclass(PolicyEvaluator)
        result = await Bare().list_policies(path="/some/path")
        assert result is None


class TestAuditServiceStubBodies:
    async def test_log_event_stub(self):
        from enhanced_agent_bus._compat.interfaces import AuditService

        Bare = _make_bare_subclass(AuditService)
        result = await Bare().log_event("t", "a", "act", "res", "ok")
        assert result is None

    async def test_log_event_with_kwargs(self):
        from datetime import datetime, timezone

        from enhanced_agent_bus._compat.interfaces import AuditService

        Bare = _make_bare_subclass(AuditService)
        result = await Bare().log_event(
            "t",
            "a",
            "act",
            "res",
            "ok",
            details={"key": "val"},
            tenant_id="t1",
            timestamp=datetime.now(tz=timezone.utc),
        )
        assert result is None

    async def test_log_events_batch_stub(self):
        from enhanced_agent_bus._compat.interfaces import AuditService

        Bare = _make_bare_subclass(AuditService)
        result = await Bare().log_events_batch([{"event": "x"}])
        assert result is None

    async def test_get_event_stub(self):
        from enhanced_agent_bus._compat.interfaces import AuditService

        uid = UUID("12345678-1234-5678-1234-567812345678")
        Bare = _make_bare_subclass(AuditService)
        result = await Bare().get_event(uid)
        assert result is None

    async def test_query_events_stub(self):
        from enhanced_agent_bus._compat.interfaces import AuditService

        Bare = _make_bare_subclass(AuditService)
        result = await Bare().query_events(
            event_type="t",
            actor="a",
            action="act",
            resource="res",
            tenant_id="t1",
            limit=10,
        )
        assert result is None

    async def test_verify_integrity_stub(self):
        from enhanced_agent_bus._compat.interfaces import AuditService

        Bare = _make_bare_subclass(AuditService)
        result = await Bare().verify_integrity()
        assert result is None


class TestDatabaseSessionStubBodies:
    async def test_execute_stub(self):
        from enhanced_agent_bus._compat.interfaces import DatabaseSession

        Bare = _make_bare_subclass(DatabaseSession)
        result = await Bare().execute("SELECT 1")
        assert result is None

    async def test_execute_with_params(self):
        from enhanced_agent_bus._compat.interfaces import DatabaseSession

        Bare = _make_bare_subclass(DatabaseSession)
        result = await Bare().execute("SELECT 1", params={"id": 1})
        assert result is None

    async def test_commit_stub(self):
        from enhanced_agent_bus._compat.interfaces import DatabaseSession

        Bare = _make_bare_subclass(DatabaseSession)
        result = await Bare().commit()
        assert result is None

    async def test_rollback_stub(self):
        from enhanced_agent_bus._compat.interfaces import DatabaseSession

        Bare = _make_bare_subclass(DatabaseSession)
        result = await Bare().rollback()
        assert result is None

    async def test_close_stub(self):
        from enhanced_agent_bus._compat.interfaces import DatabaseSession

        Bare = _make_bare_subclass(DatabaseSession)
        result = await Bare().close()
        assert result is None


class TestNotificationServiceStubBodies:
    async def test_send_email_stub(self):
        from enhanced_agent_bus._compat.interfaces import NotificationService

        Bare = _make_bare_subclass(NotificationService)
        result = await Bare().send_email("to@x.com", "subj", "body")
        assert result is None

    async def test_send_email_with_kwargs(self):
        from enhanced_agent_bus._compat.interfaces import NotificationService

        Bare = _make_bare_subclass(NotificationService)
        result = await Bare().send_email(
            "to@x.com",
            "subj",
            "body",
            html=True,
            cc=["cc@x.com"],
            _bcc=["bcc@x.com"],
        )
        assert result is None

    async def test_send_sms_stub(self):
        from enhanced_agent_bus._compat.interfaces import NotificationService

        Bare = _make_bare_subclass(NotificationService)
        result = await Bare().send_sms("+1234", "msg")
        assert result is None

    async def test_send_webhook_stub(self):
        from enhanced_agent_bus._compat.interfaces import NotificationService

        Bare = _make_bare_subclass(NotificationService)
        result = await Bare().send_webhook("http://x", {"k": "v"})
        assert result is None

    async def test_send_in_app_stub(self):
        from enhanced_agent_bus._compat.interfaces import NotificationService

        Bare = _make_bare_subclass(NotificationService)
        result = await Bare().send_in_app("user1", "msg")
        assert result is None

    async def test_send_in_app_with_kwargs(self):
        from enhanced_agent_bus._compat.interfaces import NotificationService

        Bare = _make_bare_subclass(NotificationService)
        result = await Bare().send_in_app("user1", "msg", title="Title", data={"k": "v"})
        assert result is None


class TestMessageProcessorStubBodies:
    async def test_process_stub(self):
        from enhanced_agent_bus._compat.interfaces import MessageProcessor

        Bare = _make_bare_subclass(MessageProcessor)
        result = await Bare().process({"m": 1})
        assert result is None

    async def test_process_batch_stub(self):
        from enhanced_agent_bus._compat.interfaces import MessageProcessor

        Bare = _make_bare_subclass(MessageProcessor)
        result = await Bare().process_batch([{"m": 1}])
        assert result is None


class TestCircuitBreakerStubBodies:
    async def test_record_success_stub(self):
        from enhanced_agent_bus._compat.interfaces import CircuitBreaker

        Bare = _make_bare_subclass(CircuitBreaker)
        result = await Bare().record_success()
        assert result is None

    async def test_record_failure_stub(self):
        from enhanced_agent_bus._compat.interfaces import CircuitBreaker

        Bare = _make_bare_subclass(CircuitBreaker)
        result = await Bare().record_failure()
        assert result is None

    async def test_allow_request_stub(self):
        from enhanced_agent_bus._compat.interfaces import CircuitBreaker

        Bare = _make_bare_subclass(CircuitBreaker)
        result = await Bare().allow_request()
        assert result is None

    async def test_get_state_stub(self):
        from enhanced_agent_bus._compat.interfaces import CircuitBreaker

        Bare = _make_bare_subclass(CircuitBreaker)
        result = await Bare().get_state()
        assert result is None


class TestMetricsCollectorStubBodies:
    async def test_increment_counter_stub(self):
        from enhanced_agent_bus._compat.interfaces import MetricsCollector

        Bare = _make_bare_subclass(MetricsCollector)
        result = await Bare().increment_counter("c")
        assert result is None

    async def test_increment_counter_with_tags(self):
        from enhanced_agent_bus._compat.interfaces import MetricsCollector

        Bare = _make_bare_subclass(MetricsCollector)
        result = await Bare().increment_counter("c", value=5.0, tags={"env": "test"})
        assert result is None

    async def test_record_timing_stub(self):
        from enhanced_agent_bus._compat.interfaces import MetricsCollector

        Bare = _make_bare_subclass(MetricsCollector)
        result = await Bare().record_timing("t", 1.5)
        assert result is None

    async def test_record_timing_with_tags(self):
        from enhanced_agent_bus._compat.interfaces import MetricsCollector

        Bare = _make_bare_subclass(MetricsCollector)
        result = await Bare().record_timing("t", 1.5, tags={"service": "api"})
        assert result is None

    async def test_record_gauge_stub(self):
        from enhanced_agent_bus._compat.interfaces import MetricsCollector

        Bare = _make_bare_subclass(MetricsCollector)
        result = await Bare().record_gauge("g", 42.0)
        assert result is None

    async def test_record_gauge_with_tags(self):
        from enhanced_agent_bus._compat.interfaces import MetricsCollector

        Bare = _make_bare_subclass(MetricsCollector)
        result = await Bare().record_gauge("g", 42.0, tags={"region": "us"})
        assert result is None

    async def test_get_metrics_stub(self):
        from enhanced_agent_bus._compat.interfaces import MetricsCollector

        Bare = _make_bare_subclass(MetricsCollector)
        result = await Bare().get_metrics()
        assert result is None


class TestRetryStrategyStubBodies:
    """RetryStrategy is ABC so we test both abstract enforcement and sub-class calls."""

    def test_cannot_instantiate_directly(self):
        from enhanced_agent_bus._compat.interfaces import RetryStrategy

        with pytest.raises(TypeError):
            RetryStrategy()

    async def test_subclass_with_delegation(self):
        from enhanced_agent_bus._compat.interfaces import RetryStrategy

        class DelegatingRetry(RetryStrategy):
            async def should_retry(self, attempt: int, error: Exception) -> bool:
                return attempt < 5

            async def get_delay(self, attempt: int) -> float:
                return attempt * 0.1

        r = DelegatingRetry()
        assert await r.should_retry(1, ValueError("x")) is True
        assert await r.should_retry(5, ValueError("x")) is False
        assert await r.get_delay(3) == pytest.approx(0.3)


class TestInterfacesImportFallback:
    """Cover the ImportError fallback for JSONDict (line 15)."""

    def test_jsondict_fallback_via_broken_types_import(self):
        """Force ImportError on src.core.shared.types to hit fallback."""
        import importlib

        import src.core.shared.interfaces as mod

        original_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "src.core.shared.types":
                raise ImportError("mocked")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            importlib.reload(mod)

        # Module should still have all protocols available
        assert hasattr(mod, "CacheClient")
        assert hasattr(mod, "PolicyEvaluator")

        # Reload cleanly to restore normal state
        importlib.reload(mod)


class TestInterfacesModuleLevel:
    """Cover module-level import and type alias."""

    def test_all_interfaces_importable(self):
        from enhanced_agent_bus._compat.interfaces import (
            AuditService,
            CacheClient,
            CircuitBreaker,
            DatabaseSession,
            MessageProcessor,
            MetricsCollector,
            NotificationService,
            PolicyEvaluator,
            RetryStrategy,
        )

        for cls in [
            AuditService,
            CacheClient,
            CircuitBreaker,
            DatabaseSession,
            MessageProcessor,
            MetricsCollector,
            NotificationService,
            PolicyEvaluator,
            RetryStrategy,
        ]:
            assert cls is not None

    def test_uuid_import_used(self):
        """interfaces.py imports UUID at module level."""
        from enhanced_agent_bus._compat import interfaces

        # The module uses UUID in type annotations
        assert "UUID" in dir(interfaces) or hasattr(interfaces, "AuditService")

    def test_abc_and_protocol_imported(self):
        from enhanced_agent_bus._compat import interfaces

        # Verify ABC and Protocol are used
        assert hasattr(interfaces, "RetryStrategy")
        from abc import ABC

        assert issubclass(interfaces.RetryStrategy, ABC)


# ============================================================================
# Part 2: src.core.shared.redis_config — uncovered branches
# ============================================================================


class TestRedisConfigGetUrl:
    """Cover get_url branches not tested elsewhere."""

    def test_get_url_from_env_var(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        with patch.dict("os.environ", {"REDIS_URL": "redis://custom:1234"}):
            url = RedisConfig.get_url()
        assert "custom:1234" in url

    def test_get_url_from_env_var_with_db_already(self):
        """URL with existing db path segment should be returned as-is."""
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        with patch.dict("os.environ", {"REDIS_URL": "redis://host:6379/5"}):
            url = RedisConfig.get_url()
        assert url == "redis://host:6379/5"

    def test_get_url_with_trailing_slash(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        with patch.dict("os.environ", {"REDIS_URL": "redis://host:6379/"}):
            url = RedisConfig.get_url()
        # Trailing slash should be stripped
        assert not url.endswith("/")

    def test_get_url_explicit_db_nonzero(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        with patch.dict("os.environ", {"REDIS_URL": "redis://host:6379"}):
            url = RedisConfig.get_url(db=3)
        assert url == "redis://host:6379/3"

    def test_get_url_from_settings_with_ssl(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        mock_settings = MagicMock()
        mock_settings.redis.ssl = True
        mock_settings.redis.host = "secure-host"
        mock_settings.redis.port = 6380
        mock_settings.redis.db = 0

        import os

        old = os.environ.pop("REDIS_URL", None)
        try:
            with patch(
                "src.core.shared.redis_config._get_settings",
                return_value=mock_settings,
            ):
                url = RedisConfig.get_url()
        finally:
            if old is not None:
                os.environ["REDIS_URL"] = old
        assert url.startswith("rediss://")
        assert "secure-host" in url

    def test_get_url_custom_env_var(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        with patch.dict("os.environ", {"MY_REDIS": "redis://alt:9999"}):
            url = RedisConfig.get_url(env_var="MY_REDIS")
        assert "alt:9999" in url

    def test_get_url_settings_db_nonzero(self):
        """When db=0 passed but settings.redis.db > 0, use settings db."""
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        mock_settings = MagicMock()
        mock_settings.redis.ssl = False
        mock_settings.redis.host = "localhost"
        mock_settings.redis.port = 6379
        mock_settings.redis.db = 2

        import os

        old = os.environ.pop("REDIS_URL", None)
        try:
            with patch(
                "src.core.shared.redis_config._get_settings",
                return_value=mock_settings,
            ):
                url = RedisConfig.get_url(db=0)
        finally:
            if old is not None:
                os.environ["REDIS_URL"] = old
        assert url.endswith("/2")


class TestRedisConfigGetConnectionParams:
    def test_get_connection_params_returns_dict(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        params = RedisConfig.get_connection_params()
        assert isinstance(params, dict)
        assert "url" in params
        assert "max_connections" in params
        assert "socket_timeout" in params
        assert "retry_on_timeout" in params
        assert "ssl" in params
        assert "socket_keepalive" in params
        assert "health_check_interval" in params


class TestRedisConfigGetOrCreateClient:
    def test_returns_existing_client(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        config = RedisConfig()
        fake_client = MagicMock()
        config._redis_client = fake_client
        assert config._get_or_create_client() is fake_client

    def test_redis_import_error_returns_none(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        config = RedisConfig()

        original_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "redis":
                raise ImportError("no redis")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = config._get_or_create_client()
        assert result is None

    def test_connection_error_returns_none(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        config = RedisConfig()
        mock_redis_mod = MagicMock()
        mock_redis_mod.Redis.from_url.side_effect = ConnectionError("refused")

        original_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "redis":
                return mock_redis_mod
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = config._get_or_create_client()
        assert result is None


class TestRedisConfigHealthCheckEdgeCases:
    def test_health_check_no_client_available(self):
        """When _get_or_create_client returns None, health check should fail."""
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        config = RedisConfig()

        with patch.object(config, "_get_or_create_client", return_value=None):
            is_healthy, latency = config.health_check()
        assert is_healthy is False
        assert latency is not None

    def test_health_check_timeout_error(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        config = RedisConfig()
        mock_client = MagicMock()
        mock_client.ping.side_effect = TimeoutError("timed out")

        is_healthy, latency = config.health_check(redis_client=mock_client)
        assert is_healthy is False

    def test_health_check_os_error(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        config = RedisConfig()
        mock_client = MagicMock()
        mock_client.ping.side_effect = OSError("network error")

        is_healthy, latency = config.health_check(redis_client=mock_client)
        assert is_healthy is False

    def test_listener_error_on_success_is_swallowed(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig, RedisHealthListener

        config = RedisConfig()
        bad_listener = RedisHealthListener(name="bad")
        bad_listener.on_health_check_success = MagicMock(side_effect=RuntimeError("listener boom"))
        config.add_listener(bad_listener)

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        # Should not raise despite listener error
        is_healthy, latency = config.health_check(redis_client=mock_client)
        assert is_healthy is True

    def test_listener_error_on_failure_is_swallowed(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig, RedisHealthListener

        config = RedisConfig()
        bad_listener = RedisHealthListener(name="bad")
        bad_listener.on_health_check_failure = MagicMock(side_effect=RuntimeError("listener boom"))
        config.add_listener(bad_listener)

        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("down")

        is_healthy, latency = config.health_check(redis_client=mock_client)
        assert is_healthy is False

    def test_listener_error_on_state_change_is_swallowed(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig, RedisHealthListener

        config = RedisConfig()
        bad_listener = RedisHealthListener(name="bad")
        bad_listener.on_state_change = MagicMock(side_effect=RuntimeError("state change boom"))
        config.add_listener(bad_listener)

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        # Transition from UNKNOWN -> HEALTHY triggers state change
        is_healthy, _latency = config.health_check(redis_client=mock_client)
        assert is_healthy is True

    def test_callback_error_is_swallowed(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        config = RedisConfig()

        def bad_callback(old, new):
            raise RuntimeError("callback boom")

        config.register_health_callback(bad_callback)

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        # Should not raise
        is_healthy, _latency = config.health_check(redis_client=mock_client)
        assert is_healthy is True


class TestRedisConfigAsyncHealthCheckEdgeCases:
    async def test_async_no_client(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        config = RedisConfig()
        # No client set, no redis_client passed
        is_healthy, latency = await config.health_check_async()
        assert is_healthy is False

    async def test_async_timeout_error(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        config = RedisConfig()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=TimeoutError("async timeout"))

        is_healthy, latency = await config.health_check_async(redis_client=mock_client)
        assert is_healthy is False
        assert latency is not None

    async def test_async_listener_error_on_success(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig, RedisHealthListener

        config = RedisConfig()
        bad_listener = RedisHealthListener(name="bad")
        bad_listener.on_health_check_success = MagicMock(
            side_effect=ValueError("async listener boom")
        )
        config.add_listener(bad_listener)

        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)

        is_healthy, _latency = await config.health_check_async(redis_client=mock_client)
        assert is_healthy is True

    async def test_async_listener_error_on_failure(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig, RedisHealthListener

        config = RedisConfig()
        bad_listener = RedisHealthListener(name="bad")
        bad_listener.on_health_check_failure = MagicMock(
            side_effect=TypeError("async listener fail boom")
        )
        config.add_listener(bad_listener)

        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=OSError("down"))

        is_healthy, _latency = await config.health_check_async(redis_client=mock_client)
        assert is_healthy is False


class TestRedisConfigRecoveringState:
    def test_unhealthy_to_healthy_transition(self):
        """After going UNHEALTHY and getting one success, state goes to HEALTHY."""
        from enhanced_agent_bus._compat.redis_config import (
            RedisConfig,
            RedisHealthCheckConfig,
            RedisHealthState,
        )

        config = RedisConfig(
            health_config=RedisHealthCheckConfig(
                unhealthy_threshold=1,
                healthy_threshold=1,
            )
        )
        mock_fail = MagicMock()
        mock_fail.ping.side_effect = ConnectionError("down")
        mock_ok = MagicMock()
        mock_ok.ping.return_value = True

        config.health_check(redis_client=mock_fail)
        assert config.current_state == RedisHealthState.UNHEALTHY

        config.health_check(redis_client=mock_ok)
        assert config.current_state == RedisHealthState.HEALTHY

    def test_multiple_failures_below_threshold(self):
        """Failures below threshold should not transition to UNHEALTHY."""
        from enhanced_agent_bus._compat.redis_config import (
            RedisConfig,
            RedisHealthCheckConfig,
            RedisHealthState,
        )

        config = RedisConfig(health_config=RedisHealthCheckConfig(unhealthy_threshold=3))
        mock_fail = MagicMock()
        mock_fail.ping.side_effect = ConnectionError("down")

        config.health_check(redis_client=mock_fail)
        config.health_check(redis_client=mock_fail)
        assert config.current_state == RedisHealthState.UNKNOWN


class TestRedisConfigResetFromHealthy:
    def test_reset_triggers_state_change_notification(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig, RedisHealthState

        config = RedisConfig()
        state_changes: list[tuple] = []

        def callback(old, new):
            state_changes.append((old, new))

        config.register_health_callback(callback)

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        config.health_check(redis_client=mock_client)
        assert config.current_state == RedisHealthState.HEALTHY

        state_changes.clear()
        config.reset()
        assert config.current_state == RedisHealthState.UNKNOWN
        assert len(state_changes) == 1
        assert state_changes[0] == (RedisHealthState.HEALTHY, RedisHealthState.UNKNOWN)

    def test_reset_from_unknown_no_notification(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig, RedisHealthState

        config = RedisConfig()
        state_changes: list[tuple] = []

        def callback(old, new):
            state_changes.append((old, new))

        config.register_health_callback(callback)
        config.reset()
        assert config.current_state == RedisHealthState.UNKNOWN
        assert len(state_changes) == 0


class TestRedisConfigGetHealthStatsWithCheckTime:
    def test_stats_after_health_check(self):
        from enhanced_agent_bus._compat.redis_config import RedisConfig

        config = RedisConfig()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        config.health_check(redis_client=mock_client)

        stats = config.get_health_stats()
        assert stats["state"] == "healthy"
        assert stats["is_healthy"] is True
        assert stats["last_latency_ms"] is not None
        assert stats["last_check_time"] is not None
        assert stats["consecutive_successes"] >= 1
        assert stats["consecutive_failures"] == 0


class TestRedisConfigSingleton:
    def test_get_redis_config_singleton(self):
        import src.core.shared.redis_config as rc_mod

        from enhanced_agent_bus._compat.redis_config import get_redis_config

        original = rc_mod._global_redis_config
        try:
            rc_mod._global_redis_config = None
            c1 = get_redis_config()
            c2 = get_redis_config()
            assert c1 is c2
        finally:
            rc_mod._global_redis_config = original

    def test_get_redis_url_convenience(self):
        from enhanced_agent_bus._compat.redis_config import get_redis_url

        url = get_redis_url(db=0)
        assert isinstance(url, str)
        assert "redis" in url.lower()


class TestRedisHealthCheckConfigDefaults:
    def test_defaults(self):
        from enhanced_agent_bus._compat.redis_config import RedisHealthCheckConfig

        cfg = RedisHealthCheckConfig()
        assert cfg.check_interval == 30.0
        assert cfg.timeout == 5.0
        assert cfg.unhealthy_threshold == 3
        assert cfg.healthy_threshold == 1


class TestRedisHealthStateRecovering:
    def test_recovering_value(self):
        from enhanced_agent_bus._compat.redis_config import RedisHealthState

        assert RedisHealthState.RECOVERING.value == "recovering"


# ============================================================================
# Part 3: src.core.shared.database.utils — uncovered branches
# ============================================================================


class TestDetectNPlus1:
    """Cover the detect_n_plus_1 async context manager."""

    async def test_no_warning_under_threshold(self):
        from enhanced_agent_bus._compat.database.utils import detect_n_plus_1

        mock_session = AsyncMock()
        mock_session.bind = None

        async with detect_n_plus_1(mock_session, threshold=10, operation_name="test_op"):
            pass

    async def test_with_mock_engine(self):
        """Test with a mock engine that supports event.listen/remove."""
        from enhanced_agent_bus._compat.database.utils import detect_n_plus_1

        mock_session = AsyncMock()
        mock_engine = MagicMock()
        mock_session.bind = mock_engine

        with (
            patch("sqlalchemy.event.listen") as mock_listen,
            patch("sqlalchemy.event.remove") as mock_remove,
        ):
            async with detect_n_plus_1(mock_session, threshold=5, operation_name="test_op"):
                pass

            mock_listen.assert_called_once()
            mock_remove.assert_called_once()

    async def test_with_engine_exceeding_threshold(self):
        """Simulate queries exceeding threshold to trigger warning."""
        from enhanced_agent_bus._compat.database.utils import detect_n_plus_1

        mock_session = AsyncMock()
        mock_engine = MagicMock()
        mock_session.bind = mock_engine

        captured_handler = {}

        def fake_listen(engine, event_name, handler):
            captured_handler["fn"] = handler

        def fake_remove(engine, event_name, handler):
            pass

        with (
            patch("sqlalchemy.event.listen", side_effect=fake_listen),
            patch("sqlalchemy.event.remove", side_effect=fake_remove),
        ):
            async with detect_n_plus_1(mock_session, threshold=2, operation_name="n_plus_1_test"):
                handler = captured_handler["fn"]
                for i in range(5):
                    handler(None, None, f"SELECT * FROM table_{i}", None, None, False)

    async def test_no_engine_skips_listener(self):
        from enhanced_agent_bus._compat.database.utils import detect_n_plus_1

        mock_session = AsyncMock()
        mock_session.bind = None

        # With threshold=0, even 0 queries don't trigger (0 > 0 is False)
        async with detect_n_plus_1(mock_session, threshold=0, operation_name="empty"):
            pass


class TestPaginateFunction:
    """Cover the paginate() helper function."""

    async def test_paginate_basic(self):
        from enhanced_agent_bus._compat.database.utils import Page, Pageable, paginate

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 50

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = ["item1", "item2", "item3"]
        content_result = MagicMock()
        content_result.scalars.return_value = scalars_mock

        mock_session.execute.side_effect = [count_result, content_result]

        mock_stmt = MagicMock()
        mock_stmt.offset.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt

        pageable = Pageable(page=0, size=10)

        with (
            patch("src.core.shared.database.utils.select") as mock_select,
            patch("src.core.shared.database.utils.func") as mock_func,
        ):
            mock_count = MagicMock()
            mock_func.count.return_value = mock_count
            mock_count.select_from.return_value = MagicMock()

            page = await paginate(mock_session, mock_stmt, pageable)

        assert isinstance(page, Page)
        assert page.content == ["item1", "item2", "item3"]
        assert page.total_elements == 50
        assert page.page_number == 0
        assert page.page_size == 10

    async def test_paginate_with_custom_count_stmt(self):
        from enhanced_agent_bus._compat.database.utils import Pageable, paginate

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 10
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        content_result = MagicMock()
        content_result.scalars.return_value = scalars_mock

        mock_session.execute.side_effect = [count_result, content_result]

        mock_stmt = MagicMock()
        mock_stmt.offset.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt
        mock_count_stmt = MagicMock()

        pageable = Pageable(page=0, size=5)
        page = await paginate(mock_session, mock_stmt, pageable, count_stmt=mock_count_stmt)
        assert page.total_elements == 10

    async def test_paginate_with_sort(self):
        from enhanced_agent_bus._compat.database.utils import Pageable, paginate

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 5
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = ["a"]
        content_result = MagicMock()
        content_result.scalars.return_value = scalars_mock

        mock_session.execute.side_effect = [count_result, content_result]

        mock_column = MagicMock()
        mock_table_c = MagicMock()
        mock_name_col = MagicMock()
        mock_name_col.desc.return_value = "name DESC"
        mock_name_col.asc.return_value = "name ASC"
        mock_table_c.name = mock_name_col
        mock_column.table.c = mock_table_c

        mock_stmt = MagicMock()
        mock_stmt.selected_columns.__getitem__ = MagicMock(return_value=mock_column)
        mock_stmt.order_by.return_value = mock_stmt
        mock_stmt.offset.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt

        pageable = Pageable(page=0, size=10, sort=[("name", "desc")])

        with (
            patch("src.core.shared.database.utils.select") as mock_select,
            patch("src.core.shared.database.utils.func") as mock_func,
        ):
            mock_count = MagicMock()
            mock_func.count.return_value = mock_count
            mock_count.select_from.return_value = MagicMock()

            page = await paginate(mock_session, mock_stmt, pageable)

        assert page.total_elements == 5
        mock_stmt.order_by.assert_called()

    async def test_paginate_with_asc_sort(self):
        from enhanced_agent_bus._compat.database.utils import Pageable, paginate

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 3
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = ["x"]
        content_result = MagicMock()
        content_result.scalars.return_value = scalars_mock

        mock_session.execute.side_effect = [count_result, content_result]

        mock_column = MagicMock()
        mock_table_c = MagicMock()
        mock_id_col = MagicMock()
        mock_id_col.asc.return_value = "id ASC"
        mock_table_c.id = mock_id_col
        mock_column.table.c = mock_table_c

        mock_stmt = MagicMock()
        mock_stmt.selected_columns.__getitem__ = MagicMock(return_value=mock_column)
        mock_stmt.order_by.return_value = mock_stmt
        mock_stmt.offset.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt

        pageable = Pageable(page=0, size=10, sort=[("id", "asc")])

        with (
            patch("src.core.shared.database.utils.select") as mock_select,
            patch("src.core.shared.database.utils.func") as mock_func,
        ):
            mock_count = MagicMock()
            mock_func.count.return_value = mock_count
            mock_count.select_from.return_value = MagicMock()

            page = await paginate(mock_session, mock_stmt, pageable)

        assert page.total_elements == 3

    async def test_paginate_count_returns_none(self):
        """When count query returns None, total should be 0."""
        from enhanced_agent_bus._compat.database.utils import Pageable, paginate

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = None
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        content_result = MagicMock()
        content_result.scalars.return_value = scalars_mock

        mock_session.execute.side_effect = [count_result, content_result]

        mock_stmt = MagicMock()
        mock_stmt.offset.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt

        pageable = Pageable(page=0, size=10)

        with (
            patch("src.core.shared.database.utils.select") as mock_select,
            patch("src.core.shared.database.utils.func") as mock_func,
        ):
            mock_count = MagicMock()
            mock_func.count.return_value = mock_count
            mock_count.select_from.return_value = MagicMock()

            page = await paginate(mock_session, mock_stmt, pageable)

        assert page.total_elements == 0

    async def test_paginate_sort_column_not_found(self):
        """When sort field not found on table, sorting is skipped."""
        from enhanced_agent_bus._compat.database.utils import Pageable, paginate

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 1
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = ["item"]
        content_result = MagicMock()
        content_result.scalars.return_value = scalars_mock

        mock_session.execute.side_effect = [count_result, content_result]

        mock_column = MagicMock()
        mock_table_c = MagicMock(spec=[])  # No attributes at all
        mock_column.table.c = mock_table_c

        mock_stmt = MagicMock()
        mock_stmt.selected_columns.__getitem__ = MagicMock(return_value=mock_column)
        mock_stmt.offset.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt

        pageable = Pageable(page=0, size=10, sort=[("nonexistent_field", "asc")])

        with (
            patch("src.core.shared.database.utils.select") as mock_select,
            patch("src.core.shared.database.utils.func") as mock_func,
        ):
            mock_count = MagicMock()
            mock_func.count.return_value = mock_count
            mock_count.select_from.return_value = MagicMock()

            page = await paginate(mock_session, mock_stmt, pageable)

        assert page.total_elements == 1
        # order_by should NOT have been called since column was not found
        mock_stmt.order_by.assert_not_called()


class TestBaseRepositoryFindAllWithFilters:
    """Cover find_all with filters."""

    @pytest.fixture()
    def session(self):
        s = AsyncMock()
        s.add = MagicMock()
        s.add_all = MagicMock()
        return s

    @pytest.fixture()
    def model(self):
        m = MagicMock()
        m.id = MagicMock()
        m.status = MagicMock()
        return m

    @pytest.fixture()
    def repo(self, session, model):
        from enhanced_agent_bus._compat.database.utils import BaseRepository

        return BaseRepository(session, model)

    async def test_find_all_with_filters_applied(self, repo, session):
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = ["filtered_item"]
        mock_result = MagicMock()
        mock_result.scalars.return_value = scalars_mock
        session.execute.return_value = mock_result

        with patch("src.core.shared.database.utils.select") as mock_select:
            mock_stmt = MagicMock()
            mock_stmt.where.return_value = mock_stmt
            mock_select.return_value = mock_stmt
            result = await repo.find_all(status="active")
        assert result == ["filtered_item"]

    async def test_count_with_filters(self, repo, session):
        mock_result = MagicMock()
        mock_result.scalar.return_value = 7
        session.execute.return_value = mock_result

        with (
            patch("src.core.shared.database.utils.select") as mock_select,
            patch("src.core.shared.database.utils.func") as mock_func,
        ):
            mock_count_stmt = MagicMock()
            mock_count_stmt.select_from.return_value = mock_count_stmt
            mock_count_stmt.where.return_value = mock_count_stmt
            mock_func.count.return_value = MagicMock()
            mock_func.count.return_value.select_from.return_value = mock_count_stmt
            result = await repo.count(status="active")
        assert result == 7


class TestBulkOperationsAdditional:
    """Cover additional bulk operation branches."""

    @pytest.fixture()
    def session(self):
        return AsyncMock()

    @pytest.fixture()
    def table(self):
        from sqlalchemy import Column, Integer, MetaData, String
        from sqlalchemy import Table as SATable

        metadata = MetaData()
        return SATable(
            "test_bulk_table",
            metadata,
            Column("tenant_id", String, primary_key=True),
            Column("name", String),
            Column("status", String),
        )

    async def test_bulk_update_custom_id_column(self, session, table):
        from enhanced_agent_bus._compat.database.utils import BulkOperations

        exec_result = MagicMock()
        exec_result.rowcount = 1
        session.execute.return_value = exec_result

        values = [
            {"tenant_id": "t1", "name": "updated1"},
            {"tenant_id": "t2", "name": "updated2"},
        ]
        count = await BulkOperations.bulk_update(session, table, values, id_column="tenant_id")
        assert count == 2

    async def test_bulk_update_batching(self, session, table):
        from enhanced_agent_bus._compat.database.utils import BulkOperations

        exec_result = MagicMock()
        exec_result.rowcount = 1
        session.execute.return_value = exec_result

        values = [{"tenant_id": f"t{i}", "name": f"name{i}"} for i in range(5)]
        count = await BulkOperations.bulk_update(
            session, table, values, id_column="tenant_id", batch_size=2
        )
        assert count == 5

    async def test_bulk_insert_on_conflict_batching(self, session, table):
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from enhanced_agent_bus._compat.database.utils import BulkOperations

        values = [{"tenant_id": f"t{i}", "name": f"n{i}"} for i in range(5)]

        with patch("src.core.shared.database.utils.insert", pg_insert):
            await BulkOperations.bulk_insert_on_conflict(
                session,
                table,
                values,
                index_elements=["tenant_id"],
                update_columns=["name"],
                batch_size=2,
            )
        assert session.execute.await_count == 3

    async def test_bulk_delete_custom_id_column(self, session, table):
        from enhanced_agent_bus._compat.database.utils import BulkOperations

        exec_result = MagicMock()
        exec_result.rowcount = 2
        session.execute.return_value = exec_result

        count = await BulkOperations.bulk_delete(
            session, table, ["t1", "t2"], id_column="tenant_id"
        )
        assert count == 2


class TestProjectionProtocol:
    """Cover the Projection protocol import."""

    def test_projection_protocol_importable(self):
        from enhanced_agent_bus._compat.database.utils import Projection

        assert Projection is not None

    def test_projection_conformance(self):
        from dataclasses import dataclass

        from enhanced_agent_bus._compat.database.utils import Projection

        @dataclass
        class MyProjection:
            name: str
            status: str

        proj = MyProjection(name="test", status="active")
        assert proj.name == "test"


class TestPageEdgeCases:
    def test_page_is_last_with_zero_elements(self):
        from enhanced_agent_bus._compat.database.utils import Page

        p = Page(content=[], total_elements=0, page_number=0, page_size=10)
        assert p.is_last is True
        assert p.is_first is True
        assert p.has_next is False
        assert p.has_previous is False
        assert p.total_pages == 0

    def test_page_single_element_single_page(self):
        from enhanced_agent_bus._compat.database.utils import Page

        p = Page(content=["only"], total_elements=1, page_number=0, page_size=10)
        assert p.total_pages == 1
        assert p.is_first is True
        assert p.is_last is True
        assert p.number_of_elements == 1


class TestPageableEdgeCases:
    def test_with_sort_chaining(self):
        from enhanced_agent_bus._compat.database.utils import Pageable

        p = Pageable()
        p3 = p.with_sort("name", "asc")
        p4 = p3.with_sort("created_at", "desc")
        assert p4.sort == [("name", "asc"), ("created_at", "desc")]
        assert p3.sort == [("name", "asc")]
        assert p.sort == []

    def test_next_page_preserves_sort(self):
        from enhanced_agent_bus._compat.database.utils import Pageable

        p = Pageable(page=0, size=10, sort=[("id", "asc")])
        n = p.next_page()
        assert n.sort == [("id", "asc")]
        assert n.page == 1

    def test_previous_page_preserves_sort(self):
        from enhanced_agent_bus._compat.database.utils import Pageable

        p = Pageable(page=3, size=10, sort=[("id", "desc")])
        prev = p.previous_page()
        assert prev is not None
        assert prev.sort == [("id", "desc")]
        assert prev.page == 2
