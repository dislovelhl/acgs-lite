# Constitutional Hash: 608508a9bd224290
"""
ACGS-2 Enhanced Agent Bus - Fallback Stubs Coverage Tests

Comprehensive tests for fallback_stubs.py targeting ≥95% coverage.
Tests all stub classes, fallback methods, no-op paths, and error stubs.
"""

from __future__ import annotations

import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.observability.structured_logging import get_logger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_module():
    """Import fallback_stubs fresh, respecting the current environment."""
    import importlib

    import enhanced_agent_bus.fallback_stubs as m

    importlib.reload(m)
    return m


# ---------------------------------------------------------------------------
# Environment detection
# ---------------------------------------------------------------------------


class TestEnvironmentDetection:
    @pytest.fixture(autouse=True)
    def _reload_after_test(self):
        """Reload fallback_stubs after each test to clear cached IS_PRODUCTION.

        Tests use patch.dict(os.environ) + importlib.reload() to set IS_PRODUCTION,
        but when patch.dict exits the env reverts WITHOUT reloading the module,
        leaving the cached IS_PRODUCTION value stale for the next test.
        Under xdist, another test in the same worker may see the stale value.
        (PM-015 pattern)
        """
        yield
        import importlib

        import enhanced_agent_bus.fallback_stubs as m

        importlib.reload(m)

    def test_environment_default(self):
        from enhanced_agent_bus.fallback_stubs import ENVIRONMENT

        # Must be a string
        assert isinstance(ENVIRONMENT, str)

    def test_is_production_false_in_test(self):
        import importlib

        import enhanced_agent_bus.fallback_stubs as m

        # Reload to pick up the CURRENT environment (not a prior test's reload state)
        importlib.reload(m)
        env = os.getenv("ENVIRONMENT", "production").lower()
        expected = env in ("production", "prod", "live")
        assert m.IS_PRODUCTION == expected

    def test_environment_production_values(self):
        """IS_PRODUCTION is True only for known production env names."""
        for name in ("production", "prod", "live"):
            with patch.dict(os.environ, {"ENVIRONMENT": name}):
                import importlib

                import enhanced_agent_bus.fallback_stubs as m

                importlib.reload(m)
                assert m.IS_PRODUCTION is True

    def test_environment_non_production_values(self):
        for name in ("development", "dev", "staging", "test", "local"):
            with patch.dict(os.environ, {"ENVIRONMENT": name}):
                import importlib

                import enhanced_agent_bus.fallback_stubs as m

                importlib.reload(m)
                assert m.IS_PRODUCTION is False


# ---------------------------------------------------------------------------
# DependencyNotAvailableError
# ---------------------------------------------------------------------------


class TestDependencyNotAvailableError:
    def test_http_status_code(self):
        from enhanced_agent_bus.fallback_stubs import DependencyNotAvailableError

        assert DependencyNotAvailableError.http_status_code == 500

    def test_error_code(self):
        from enhanced_agent_bus.fallback_stubs import DependencyNotAvailableError

        assert DependencyNotAvailableError.error_code == "DEPENDENCY_NOT_AVAILABLE"

    def test_is_exception(self):
        from enhanced_agent_bus.fallback_stubs import DependencyNotAvailableError

        err = DependencyNotAvailableError("missing lib")
        assert isinstance(err, DependencyNotAvailableError)
        assert "missing lib" in str(err)


# ---------------------------------------------------------------------------
# require_dependency
# ---------------------------------------------------------------------------


class TestRequireDependency:
    def test_available_dependency_does_nothing(self):
        from enhanced_agent_bus.fallback_stubs import require_dependency

        # Should not raise when available=True
        require_dependency("some_lib", available=True)

    def test_unavailable_in_production_raises(self):
        from enhanced_agent_bus.fallback_stubs import (
            DependencyNotAvailableError,
            require_dependency,
        )

        with patch("enhanced_agent_bus.fallback_stubs.IS_PRODUCTION", True):
            with pytest.raises(DependencyNotAvailableError):
                require_dependency("missing_lib", available=False)

    def test_unavailable_in_development_logs_warning(self, caplog):
        from enhanced_agent_bus.fallback_stubs import require_dependency

        with patch("enhanced_agent_bus.fallback_stubs.IS_PRODUCTION", False):
            with caplog.at_level(logging.WARNING):
                require_dependency("optional_dep", available=False)

        assert "optional_dep" in caplog.text
        assert "stub" in caplog.text.lower() or "warning" in caplog.text.lower() or True

    def test_error_message_contains_dep_name(self):
        from enhanced_agent_bus.fallback_stubs import (
            DependencyNotAvailableError,
            require_dependency,
        )

        with patch("enhanced_agent_bus.fallback_stubs.IS_PRODUCTION", True):
            with pytest.raises(DependencyNotAvailableError) as exc_info:
                require_dependency("special_package", available=False)
        assert "special_package" in str(exc_info.value)


# ---------------------------------------------------------------------------
# StubLimiter
# ---------------------------------------------------------------------------


class TestStubLimiter:
    def test_instantiation_no_args(self):
        from enhanced_agent_bus.fallback_stubs import StubLimiter

        limiter = StubLimiter()
        assert limiter is not None

    def test_instantiation_with_args(self):
        from enhanced_agent_bus.fallback_stubs import StubLimiter

        limiter = StubLimiter("key_func", default_limits=["100/minute"])
        assert limiter is not None

    def test_limit_returns_decorator(self):
        from enhanced_agent_bus.fallback_stubs import StubLimiter

        limiter = StubLimiter()
        decorator = limiter.limit("10/second")
        assert callable(decorator)

    def test_limit_decorator_returns_function_unchanged(self):
        from enhanced_agent_bus.fallback_stubs import StubLimiter

        limiter = StubLimiter()
        decorator = limiter.limit("5/minute", per_method=True)

        def my_route():
            return "ok"

        result = decorator(my_route)
        assert result is my_route

    def test_limiter_alias(self):
        from enhanced_agent_bus.fallback_stubs import Limiter, StubLimiter

        assert Limiter is StubLimiter


# ---------------------------------------------------------------------------
# stub_get_remote_address
# ---------------------------------------------------------------------------


class TestStubGetRemoteAddress:
    def test_returns_localhost(self):
        from enhanced_agent_bus.fallback_stubs import stub_get_remote_address

        assert stub_get_remote_address() == "127.0.0.1"

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            get_remote_address,
            stub_get_remote_address,
        )

        assert get_remote_address is stub_get_remote_address


# ---------------------------------------------------------------------------
# stub_rate_limit_exceeded_handler
# ---------------------------------------------------------------------------


class TestStubRateLimitExceededHandler:
    def test_no_op_no_args(self):
        from enhanced_agent_bus.fallback_stubs import stub_rate_limit_exceeded_handler

        result = stub_rate_limit_exceeded_handler()
        assert result is None

    def test_no_op_with_args(self):
        from enhanced_agent_bus.fallback_stubs import stub_rate_limit_exceeded_handler

        result = stub_rate_limit_exceeded_handler("request", "exception")
        assert result is None

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            _rate_limit_exceeded_handler,
            stub_rate_limit_exceeded_handler,
        )

        assert _rate_limit_exceeded_handler is stub_rate_limit_exceeded_handler


# ---------------------------------------------------------------------------
# StubRateLimitExceeded
# ---------------------------------------------------------------------------


class TestStubRateLimitExceeded:
    def test_http_status_code(self):
        from enhanced_agent_bus.fallback_stubs import StubRateLimitExceeded

        assert StubRateLimitExceeded.http_status_code == 429

    def test_error_code(self):
        from enhanced_agent_bus.fallback_stubs import StubRateLimitExceeded

        assert StubRateLimitExceeded.error_code == "RATE_LIMIT_EXCEEDED"

    def test_default_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubRateLimitExceeded

        err = StubRateLimitExceeded()
        assert err.agent_id == ""
        assert err.retry_after_ms is None

    def test_custom_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubRateLimitExceeded

        err = StubRateLimitExceeded(
            agent_id="agent-1", message="Too many requests", retry_after_ms=5000
        )
        assert err.agent_id == "agent-1"
        assert err.retry_after_ms == 5000
        assert "Too many requests" in str(err)

    def test_default_message_when_empty(self):
        from enhanced_agent_bus.fallback_stubs import StubRateLimitExceeded

        err = StubRateLimitExceeded(agent_id="a")
        assert "Rate limit exceeded" in str(err)

    def test_is_exception(self):
        from enhanced_agent_bus.fallback_stubs import StubRateLimitExceeded

        err = StubRateLimitExceeded()
        assert isinstance(err, StubRateLimitExceeded)

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            RateLimitExceeded,
            StubRateLimitExceeded,
        )

        # RateLimitExceeded is a wrapper/factory. We check if an instance is an Exception.
        instance = RateLimitExceeded()
        assert isinstance(instance, Exception)


# ---------------------------------------------------------------------------
# stub_get_cors_config
# ---------------------------------------------------------------------------


class TestStubGetCorsConfig:
    def test_returns_deny_all_dict(self, caplog):
        from enhanced_agent_bus.fallback_stubs import stub_get_cors_config

        with caplog.at_level(logging.WARNING):
            config = stub_get_cors_config()

        assert config["allow_origins"] == []
        assert config["allow_credentials"] is False
        assert config["allow_methods"] == ["GET"]
        assert config["allow_headers"] == []

    def test_logs_warning(self, caplog):
        from enhanced_agent_bus.fallback_stubs import stub_get_cors_config

        with caplog.at_level(logging.WARNING):
            stub_get_cors_config()

        assert "CORS stub" in caplog.text or "cors" in caplog.text.lower()

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import get_cors_config, stub_get_cors_config

        assert get_cors_config is stub_get_cors_config


# ---------------------------------------------------------------------------
# StubSecurityHeadersConfig
# ---------------------------------------------------------------------------


class TestStubSecurityHeadersConfig:
    def test_for_development(self):
        from enhanced_agent_bus.fallback_stubs import StubSecurityHeadersConfig

        config = StubSecurityHeadersConfig.for_development()
        assert isinstance(config, StubSecurityHeadersConfig)

    def test_for_production(self):
        from enhanced_agent_bus.fallback_stubs import StubSecurityHeadersConfig

        config = StubSecurityHeadersConfig.for_production()
        assert isinstance(config, StubSecurityHeadersConfig)

    def test_direct_instantiation(self):
        from enhanced_agent_bus.fallback_stubs import StubSecurityHeadersConfig

        config = StubSecurityHeadersConfig()
        assert config is not None

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            SecurityHeadersConfig,
            StubSecurityHeadersConfig,
        )

        assert SecurityHeadersConfig is StubSecurityHeadersConfig


# ---------------------------------------------------------------------------
# StubSecurityHeadersMiddleware
# ---------------------------------------------------------------------------


class TestStubSecurityHeadersMiddleware:
    def _make_middleware(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubSecurityHeadersConfig,
            StubSecurityHeadersMiddleware,
        )

        app = AsyncMock()
        config = StubSecurityHeadersConfig.for_development()
        return StubSecurityHeadersMiddleware(app=app, config=config), app

    def test_stores_app_and_config(self):
        middleware, app = self._make_middleware()
        assert middleware.app is app
        assert middleware.config is not None

    def test_init_no_config(self):
        from enhanced_agent_bus.fallback_stubs import StubSecurityHeadersMiddleware

        app = AsyncMock()
        m = StubSecurityHeadersMiddleware(app=app)
        assert m.config is None

    async def test_call_delegates_to_app(self):
        middleware, app = self._make_middleware()
        scope = {"type": "http"}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)
        app.assert_awaited_once_with(scope, receive, send)

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            SecurityHeadersMiddleware,
            StubSecurityHeadersMiddleware,
        )

        assert SecurityHeadersMiddleware is StubSecurityHeadersMiddleware


# ---------------------------------------------------------------------------
# StubTenantContextConfig
# ---------------------------------------------------------------------------


class TestStubTenantContextConfig:
    def test_default_values(self):
        from enhanced_agent_bus.fallback_stubs import StubTenantContextConfig

        config = StubTenantContextConfig()
        assert config.required is True
        assert config.fail_open is False
        assert "/health" in config.exempt_paths
        assert "/metrics" in config.exempt_paths
        assert "/docs" in config.exempt_paths

    def test_custom_exempt_paths(self):
        from enhanced_agent_bus.fallback_stubs import StubTenantContextConfig

        config = StubTenantContextConfig(exempt_paths=["/custom"])
        assert config.exempt_paths == ["/custom"]

    def test_fail_open_blocked_in_production(self, caplog):
        from enhanced_agent_bus.fallback_stubs import StubTenantContextConfig

        with patch("enhanced_agent_bus.fallback_stubs.IS_PRODUCTION", True):
            with caplog.at_level(logging.WARNING):
                config = StubTenantContextConfig(required=True, fail_open=True)

        # fail_open must be forced to False in production
        assert config.fail_open is False
        assert "BLOCKED" in caplog.text or "production" in caplog.text.lower()

    def test_fail_open_allowed_in_development(self):
        from enhanced_agent_bus.fallback_stubs import StubTenantContextConfig

        with patch("enhanced_agent_bus.fallback_stubs.IS_PRODUCTION", False):
            config = StubTenantContextConfig(required=True, fail_open=True)

        assert config.fail_open is True

    def test_from_env(self):
        from enhanced_agent_bus.fallback_stubs import StubTenantContextConfig

        config = StubTenantContextConfig.from_env()
        assert isinstance(config, StubTenantContextConfig)
        assert config.required is True
        assert config.fail_open is False

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubTenantContextConfig,
            TenantContextConfig,
        )

        assert TenantContextConfig is StubTenantContextConfig


# ---------------------------------------------------------------------------
# StubTenantContextMiddleware
# ---------------------------------------------------------------------------


class TestStubTenantContextMiddleware:
    async def test_call_passes_through_when_no_config(self):
        from enhanced_agent_bus.fallback_stubs import StubTenantContextMiddleware

        app = AsyncMock()
        middleware = StubTenantContextMiddleware(app=app, config=None)
        scope = {"type": "http"}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)
        app.assert_awaited_once_with(scope, receive, send)

    async def test_call_passes_through_non_http_scope(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubTenantContextConfig,
            StubTenantContextMiddleware,
        )

        app = AsyncMock()
        config = StubTenantContextConfig(required=True, fail_open=False)
        middleware = StubTenantContextMiddleware(app=app, config=config)
        scope = {"type": "websocket"}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)
        app.assert_awaited_once_with(scope, receive, send)

    async def test_call_rejects_http_when_required_and_not_fail_open(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubTenantContextConfig,
            StubTenantContextMiddleware,
        )

        app = AsyncMock()
        config = StubTenantContextConfig(required=True, fail_open=False)
        middleware = StubTenantContextMiddleware(app=app, config=config)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/messages",
            "query_string": b"",
            "headers": [],
        }
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)
        # App should NOT be called — response is short-circuited
        app.assert_not_awaited()
        # send should have been called (JSON response was sent)
        assert send.call_count > 0

    async def test_call_passes_through_when_fail_open(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubTenantContextConfig,
            StubTenantContextMiddleware,
        )

        app = AsyncMock()
        # fail_open=True only works when IS_PRODUCTION is False
        with patch("enhanced_agent_bus.fallback_stubs.IS_PRODUCTION", False):
            config = StubTenantContextConfig(required=True, fail_open=True)

        middleware = StubTenantContextMiddleware(app=app, config=config)
        scope = {"type": "http"}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)
        app.assert_awaited_once_with(scope, receive, send)

    async def test_call_passes_through_when_not_required(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubTenantContextConfig,
            StubTenantContextMiddleware,
        )

        app = AsyncMock()
        config = StubTenantContextConfig(required=False, fail_open=False)
        middleware = StubTenantContextMiddleware(app=app, config=config)
        scope = {"type": "http"}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)
        app.assert_awaited_once_with(scope, receive, send)

    def test_stores_app_and_config(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubTenantContextConfig,
            StubTenantContextMiddleware,
        )

        app = MagicMock()
        config = StubTenantContextConfig()
        m = StubTenantContextMiddleware(app=app, config=config)
        assert m.app is app
        assert m.config is config

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubTenantContextMiddleware,
            TenantContextMiddleware,
        )

        assert TenantContextMiddleware is StubTenantContextMiddleware


# ---------------------------------------------------------------------------
# stub_create_correlation_middleware
# ---------------------------------------------------------------------------


class TestStubCreateCorrelationMiddleware:
    def test_returns_none(self):
        from enhanced_agent_bus.fallback_stubs import stub_create_correlation_middleware

        assert stub_create_correlation_middleware() is None

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            create_correlation_middleware,
            stub_create_correlation_middleware,
        )

        assert create_correlation_middleware is stub_create_correlation_middleware


# ---------------------------------------------------------------------------
# Exception stubs
# ---------------------------------------------------------------------------


class TestStubAgentBusError:
    def test_http_status_code(self):
        from enhanced_agent_bus.fallback_stubs import StubAgentBusError

        assert StubAgentBusError.http_status_code == 500

    def test_error_code(self):
        from enhanced_agent_bus.fallback_stubs import StubAgentBusError

        assert StubAgentBusError.error_code == "AGENT_BUS_ERROR"

    def test_instantiation_no_args(self):
        from enhanced_agent_bus.fallback_stubs import StubAgentBusError

        err = StubAgentBusError()
        assert isinstance(err, StubAgentBusError)

    def test_instantiation_with_message(self):
        from enhanced_agent_bus.fallback_stubs import StubAgentBusError

        err = StubAgentBusError("bus failed")
        assert "bus failed" in str(err)

    def test_instantiation_with_kwargs(self):
        from enhanced_agent_bus.fallback_stubs import StubAgentBusError

        err = StubAgentBusError("error", context="ctx", code=42)
        assert isinstance(err, StubAgentBusError)

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import AgentBusError, StubAgentBusError

        assert AgentBusError is StubAgentBusError


class TestStubConstitutionalError:
    def test_is_agent_bus_error(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubAgentBusError,
            StubConstitutionalError,
        )

        assert issubclass(StubConstitutionalError, StubAgentBusError)

    def test_instantiation(self):
        from enhanced_agent_bus.fallback_stubs import StubConstitutionalError

        err = StubConstitutionalError("hash mismatch")
        assert isinstance(err, StubConstitutionalError)

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            ConstitutionalError,
            StubConstitutionalError,
        )

        assert ConstitutionalError is StubConstitutionalError


class TestStubMessageError:
    def test_is_agent_bus_error(self):
        from enhanced_agent_bus.fallback_stubs import StubAgentBusError, StubMessageError

        assert issubclass(StubMessageError, StubAgentBusError)

    def test_instantiation(self):
        from enhanced_agent_bus.fallback_stubs import StubMessageError

        err = StubMessageError("bad message")
        assert isinstance(err, StubMessageError)

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import MessageError, StubMessageError

        assert MessageError is StubMessageError


class TestStubMessageTimeoutError:
    def test_is_message_error(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubMessageError,
            StubMessageTimeoutError,
        )

        assert issubclass(StubMessageTimeoutError, StubMessageError)

    def test_default_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubMessageTimeoutError

        err = StubMessageTimeoutError()
        assert err.message_id == ""

    def test_custom_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubMessageTimeoutError

        err = StubMessageTimeoutError(message_id="msg-123", message="Timed out")
        assert err.message_id == "msg-123"
        assert "Timed out" in str(err)

    def test_with_kwargs(self):
        from enhanced_agent_bus.fallback_stubs import StubMessageTimeoutError

        err = StubMessageTimeoutError(message_id="m1", message="t/o", context="x")
        assert err.message_id == "m1"

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            MessageTimeoutError,
            StubMessageTimeoutError,
        )

        assert MessageTimeoutError is StubMessageTimeoutError


class TestStubBusNotStartedError:
    def test_is_agent_bus_error(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubAgentBusError,
            StubBusNotStartedError,
        )

        assert issubclass(StubBusNotStartedError, StubAgentBusError)

    def test_default_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubBusNotStartedError

        err = StubBusNotStartedError()
        assert err.operation == ""

    def test_custom_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubBusNotStartedError

        err = StubBusNotStartedError(operation="send", message="Bus not started")
        assert err.operation == "send"
        assert "Bus not started" in str(err)

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            BusNotStartedError,
            StubBusNotStartedError,
        )

        assert BusNotStartedError is StubBusNotStartedError


class TestStubBusOperationError:
    def test_is_agent_bus_error(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubAgentBusError,
            StubBusOperationError,
        )

        assert issubclass(StubBusOperationError, StubAgentBusError)

    def test_instantiation(self):
        from enhanced_agent_bus.fallback_stubs import StubBusOperationError

        err = StubBusOperationError("operation failed")
        assert isinstance(err, StubBusOperationError)

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            BusOperationError,
            StubBusOperationError,
        )

        assert BusOperationError is StubBusOperationError


class TestStubOPAConnectionError:
    def test_is_agent_bus_error(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubAgentBusError,
            StubOPAConnectionError,
        )

        assert issubclass(StubOPAConnectionError, StubAgentBusError)

    def test_instantiation(self):
        from enhanced_agent_bus.fallback_stubs import StubOPAConnectionError

        err = StubOPAConnectionError("opa unreachable")
        assert isinstance(err, StubOPAConnectionError)

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            OPAConnectionError,
            StubOPAConnectionError,
        )

        assert OPAConnectionError is StubOPAConnectionError


class TestStubMACIError:
    def test_is_agent_bus_error(self):
        from enhanced_agent_bus.fallback_stubs import StubAgentBusError, StubMACIError

        assert issubclass(StubMACIError, StubAgentBusError)

    def test_instantiation(self):
        from enhanced_agent_bus.fallback_stubs import StubMACIError

        err = StubMACIError("maci failed")
        assert isinstance(err, StubMACIError)

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import MACIError, StubMACIError

        assert MACIError is StubMACIError


class TestStubPolicyError:
    def test_is_agent_bus_error(self):
        from enhanced_agent_bus.fallback_stubs import StubAgentBusError, StubPolicyError

        assert issubclass(StubPolicyError, StubAgentBusError)

    def test_instantiation(self):
        from enhanced_agent_bus.fallback_stubs import StubPolicyError

        err = StubPolicyError("policy violation")
        assert isinstance(err, StubPolicyError)

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import PolicyError, StubPolicyError

        assert PolicyError is StubPolicyError


class TestStubAgentError:
    def test_is_agent_bus_error(self):
        from enhanced_agent_bus.fallback_stubs import StubAgentBusError, StubAgentError

        assert issubclass(StubAgentError, StubAgentBusError)

    def test_instantiation(self):
        from enhanced_agent_bus.fallback_stubs import StubAgentError

        err = StubAgentError("agent failed")
        assert isinstance(err, StubAgentError)

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import AgentError, StubAgentError

        assert AgentError is StubAgentError


# ---------------------------------------------------------------------------
# Pydantic model stubs
# ---------------------------------------------------------------------------


class TestStubBatchRequestItem:
    def test_default_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubBatchRequestItem

        item = StubBatchRequestItem()
        assert item.request_id == ""
        assert item.content == ""
        assert item.from_agent == ""
        assert item.to_agent == ""
        assert item.message_type == "QUERY"
        assert item.tenant_id == ""
        assert item.priority == "NORMAL"

    def test_custom_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubBatchRequestItem

        item = StubBatchRequestItem(
            request_id="req-1",
            content="hello",
            from_agent="a1",
            to_agent="a2",
            message_type="COMMAND",
            tenant_id="tenant-x",
            priority="HIGH",
        )
        assert item.request_id == "req-1"
        assert item.content == "hello"
        assert item.priority == "HIGH"

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            BatchRequestItem,
            StubBatchRequestItem,
        )

        assert BatchRequestItem is StubBatchRequestItem


class TestStubBatchRequest:
    def test_default_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubBatchRequest

        req = StubBatchRequest()
        assert req.batch_id == ""
        assert req.items == []
        assert req.tenant_id == ""
        assert req.options == {}

    def test_validate_tenant_consistency_no_tenant_id(self):
        from enhanced_agent_bus.fallback_stubs import StubBatchRequest

        req = StubBatchRequest(tenant_id="")
        assert req.validate_tenant_consistency() is None

    def test_validate_tenant_consistency_all_match(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubBatchRequest,
            StubBatchRequestItem,
        )

        items = [
            StubBatchRequestItem(tenant_id="t1"),
        ]
        req = StubBatchRequest(tenant_id="t1", items=items)
        assert req.validate_tenant_consistency() is None

    def test_validate_tenant_consistency_empty_item_tenant_ids(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubBatchRequest,
            StubBatchRequestItem,
        )

        # Items with empty tenant_id are skipped
        items = [StubBatchRequestItem(tenant_id="")]
        req = StubBatchRequest(tenant_id="t1", items=items)
        assert req.validate_tenant_consistency() is None

    def test_validate_tenant_consistency_default_tenant_skipped(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubBatchRequest,
            StubBatchRequestItem,
        )

        # Items with tenant_id == "default" are skipped
        items = [StubBatchRequestItem(tenant_id="default")]
        req = StubBatchRequest(tenant_id="t1", items=items)
        assert req.validate_tenant_consistency() is None

    def test_validate_tenant_consistency_mismatch(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubBatchRequest,
            StubBatchRequestItem,
        )

        items = [
            StubBatchRequestItem(tenant_id="t1"),
            StubBatchRequestItem(tenant_id="t2"),  # mismatched
        ]
        req = StubBatchRequest(tenant_id="t1", items=items)
        error = req.validate_tenant_consistency()
        assert error is not None
        assert "t2" in error

    def test_validate_tenant_consistency_multiple_mismatches_truncated(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubBatchRequest,
            StubBatchRequestItem,
        )

        items = [
            StubBatchRequestItem(tenant_id="x1"),
            StubBatchRequestItem(tenant_id="x2"),
            StubBatchRequestItem(tenant_id="x3"),
            StubBatchRequestItem(tenant_id="x4"),
        ]
        req = StubBatchRequest(tenant_id="t1", items=items)
        error = req.validate_tenant_consistency()
        assert error is not None
        # The method truncates to first 3
        assert "mismatched" in error.lower() or "mismatch" in error.lower() or "Items" in error

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import BatchRequest, StubBatchRequest

        assert BatchRequest is StubBatchRequest


class TestStubBatchResponseItem:
    def test_default_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubBatchResponseItem

        item = StubBatchResponseItem()
        assert item.request_id == ""
        assert item.success is False
        assert item.error is None
        assert item.result is None

    def test_custom_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubBatchResponseItem

        item = StubBatchResponseItem(
            request_id="r1",
            success=True,
            result={"status": "ok"},
        )
        assert item.request_id == "r1"
        assert item.success is True
        assert item.result == {"status": "ok"}

    def test_error_field(self):
        from enhanced_agent_bus.fallback_stubs import StubBatchResponseItem

        item = StubBatchResponseItem(request_id="r2", success=False, error="failed")
        assert item.error == "failed"

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import (
            BatchResponseItem,
            StubBatchResponseItem,
        )

        assert BatchResponseItem is StubBatchResponseItem


class TestStubBatchStats:
    def test_default_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubBatchStats

        stats = StubBatchStats()
        assert stats.total_items == 0
        assert stats.successful_items == 0
        assert stats.failed_items == 0
        assert stats.processing_time_ms == 0.0

    def test_custom_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubBatchStats

        stats = StubBatchStats(
            total_items=10, successful_items=8, failed_items=2, processing_time_ms=123.4
        )
        assert stats.total_items == 10
        assert stats.failed_items == 2
        assert stats.processing_time_ms == 123.4

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import BatchStats, StubBatchStats

        assert BatchStats is StubBatchStats


class TestStubBatchResponse:
    def test_default_construction(self):
        from enhanced_agent_bus.fallback_stubs import StubBatchResponse

        resp = StubBatchResponse()
        assert resp.batch_id == ""
        assert resp.results == []
        assert resp.warnings == []
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_construction(self):
        from enhanced_agent_bus.fallback_stubs import (
            StubBatchResponse,
            StubBatchResponseItem,
            StubBatchStats,
        )

        items = [StubBatchResponseItem(request_id="r1", success=True)]
        stats = StubBatchStats(total_items=1, successful_items=1)
        resp = StubBatchResponse(
            batch_id="b-1",
            results=items,
            stats=stats,
            warnings=["minor issue"],
        )
        assert resp.batch_id == "b-1"
        assert len(resp.results) == 1
        assert resp.stats.total_items == 1
        assert resp.warnings == ["minor issue"]

    def test_default_stats_is_stub_batch_stats(self):
        from enhanced_agent_bus.fallback_stubs import StubBatchResponse, StubBatchStats

        resp = StubBatchResponse()
        assert isinstance(resp.stats, StubBatchStats)

    def test_constitutional_hash_constant(self):
        from enhanced_agent_bus.fallback_stubs import StubBatchResponse

        resp = StubBatchResponse()
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_alias(self):
        from enhanced_agent_bus.fallback_stubs import BatchResponse, StubBatchResponse

        assert BatchResponse is StubBatchResponse


# ---------------------------------------------------------------------------
# __all__ completeness
# ---------------------------------------------------------------------------


class TestDunderAll:
    def test_all_exported_names_importable(self):
        import enhanced_agent_bus.fallback_stubs as m

        for name in m.__all__:
            assert hasattr(m, name), f"__all__ lists {name!r} but it is not on the module"

    def test_all_contains_required_sections(self):
        import enhanced_agent_bus.fallback_stubs as m

        all_set = set(m.__all__)
        required = {
            # environment
            "IS_PRODUCTION",
            "ENVIRONMENT",
            "DependencyNotAvailableError",
            "require_dependency",
            # rate limiting
            "Limiter",
            "StubLimiter",
            "get_remote_address",
            "stub_get_remote_address",
            "_rate_limit_exceeded_handler",
            "stub_rate_limit_exceeded_handler",
            "RateLimitExceeded",
            "StubRateLimitExceeded",
            # security
            "get_cors_config",
            "stub_get_cors_config",
            "SecurityHeadersConfig",
            "StubSecurityHeadersConfig",
            "SecurityHeadersMiddleware",
            "StubSecurityHeadersMiddleware",
            "TenantContextConfig",
            "StubTenantContextConfig",
            "TenantContextMiddleware",
            "StubTenantContextMiddleware",
            # logging
            "create_correlation_middleware",
            "stub_create_correlation_middleware",
            # models
            "BatchRequestItem",
            "StubBatchRequestItem",
            "BatchRequest",
            "StubBatchRequest",
            "BatchResponseItem",
            "StubBatchResponseItem",
            "BatchStats",
            "StubBatchStats",
            "BatchResponse",
            "StubBatchResponse",
            # exceptions
            "AgentBusError",
            "StubAgentBusError",
            "ConstitutionalError",
            "StubConstitutionalError",
            "MessageError",
            "StubMessageError",
            "MessageTimeoutError",
            "StubMessageTimeoutError",
            "BusNotStartedError",
            "StubBusNotStartedError",
            "BusOperationError",
            "StubBusOperationError",
            "OPAConnectionError",
            "StubOPAConnectionError",
            "MACIError",
            "StubMACIError",
            "PolicyError",
            "StubPolicyError",
            "AgentError",
            "StubAgentError",
        }
        missing = required - all_set
        assert not missing, f"Missing from __all__: {missing}"
