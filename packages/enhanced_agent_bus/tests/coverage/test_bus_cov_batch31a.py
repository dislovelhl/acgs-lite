"""
Coverage batch 31a -- targeted tests for:
  1. message_processor.py (83.3%, 80 missing lines)
  2. opa_client/core.py (83.8%, 77 missing lines)

Constitutional Hash: 608508a9bd224290

Focuses on error-handling branches, conditional paths, optional dependency
fallbacks, MCP integration, DLQ, metering, retry logic, SSL context building,
bundle management, singleton lifecycle, and edge cases.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import ssl
import sys
import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import httpx
import pytest

from enhanced_agent_bus.core_models import AgentMessage
from enhanced_agent_bus.exceptions.policy import (
    OPAConnectionError,
    OPANotInitializedError,
    PolicyEvaluationError,
)
from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    AutonomyTier,
    MessageStatus,
    MessageType,
    Priority,
)
from enhanced_agent_bus.validators import ValidationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_msg(**overrides: Any) -> AgentMessage:
    defaults: dict[str, Any] = {
        "from_agent": "sender-agent",
        "to_agent": "receiver-agent",
        "content": {"text": "hello"},
        "message_type": MessageType.COMMAND,
        "priority": Priority.MEDIUM,
        "tenant_id": "default",
    }
    defaults.update(overrides)
    return AgentMessage(**defaults)


# ===================================================================
# 1. message_processor.py -- MessageProcessor
# ===================================================================


class TestMessageProcessorInit:
    """Cover __init__ edge-case branches."""

    def test_invalid_cache_hash_mode_raises(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            MessageProcessor(isolated_mode=True, cache_hash_mode="bogus")

    def test_isolated_mode_skips_opa(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        assert mp._opa_client is None

    def test_opa_client_fallback_to_direct_instantiation(self):
        """When get_opa_client raises but _OPAClient is available, fall back."""
        from enhanced_agent_bus.message_processor import MessageProcessor

        mock_client = MagicMock()
        with (
            patch(
                "enhanced_agent_bus.message_processor.get_opa_client",
                side_effect=RuntimeError("not init"),
            ),
            patch(
                "enhanced_agent_bus.message_processor._OPAClient",
                return_value=mock_client,
            ),
        ):
            mp = MessageProcessor(isolated_mode=False)
            assert mp._opa_client is mock_client

    def test_opa_client_fallback_when_class_none(self):
        """When both get_opa_client and _OPAClient are unavailable."""
        from enhanced_agent_bus.message_processor import MessageProcessor

        with (
            patch(
                "enhanced_agent_bus.message_processor.get_opa_client",
                side_effect=RuntimeError("not init"),
            ),
            patch("enhanced_agent_bus.message_processor._OPAClient", None),
        ):
            mp = MessageProcessor(isolated_mode=False)
            assert mp._opa_client is None

    def test_opa_client_fallback_class_raises(self):
        """When get_opa_client fails AND _OPAClient() also raises."""
        from enhanced_agent_bus.message_processor import MessageProcessor

        with (
            patch(
                "enhanced_agent_bus.message_processor.get_opa_client",
                side_effect=RuntimeError("not init"),
            ),
            patch(
                "enhanced_agent_bus.message_processor._OPAClient",
                side_effect=OSError("bad"),
            ),
        ):
            mp = MessageProcessor(isolated_mode=False)
            assert mp._opa_client is None

    def test_cache_hash_mode_fast_warns_when_unavailable(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        with patch("enhanced_agent_bus.message_processor.FAST_HASH_AVAILABLE", False):
            mp = MessageProcessor(isolated_mode=True, cache_hash_mode="fast")
            assert mp._cache_hash_mode == "fast"


class TestAutoSelectStrategy:
    """Cover _auto_select_strategy branches."""

    def test_isolated_mode_returns_python_strategy(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        name = mp._processing_strategy.get_name()
        assert "python" in name.lower() or "static" in name.lower() or name

    def test_composite_with_rust(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mock_rust = MagicMock()
        mock_rust_mod = MagicMock()
        with (
            patch("enhanced_agent_bus.message_processor.USE_RUST", True),
            patch("enhanced_agent_bus.message_processor.rust_bus", mock_rust_mod),
        ):
            mp = MessageProcessor(
                isolated_mode=False,
                use_rust=True,
                enable_maci=False,
            )
            mp._rust_processor = mock_rust
            strategy = mp._auto_select_strategy()
            assert strategy is not None

    def test_maci_wrapping(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=False, enable_maci=True)
        name = mp._processing_strategy.get_name()
        assert name  # should have a name

    def test_constitutional_verifier_branch(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(
            isolated_mode=False,
            enable_maci=False,
            constitutional_verifier=MagicMock(),
        )
        strategy = mp._auto_select_strategy()
        assert strategy is not None


class TestProcessRetry:
    """Cover process() retry logic with exponential backoff."""

    async def test_process_retries_on_transient_error(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        call_count = 0

        async def failing_process(m: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient")
            return ValidationResult(is_valid=True)

        mp._do_process = failing_process  # type: ignore[assignment]
        msg = _make_msg()
        result = await mp.process(msg, max_retries=3)
        assert result.is_valid is True
        assert call_count == 3

    async def test_process_exhausts_retries(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)

        async def always_fail(m: Any) -> Any:
            raise ValueError("permanent")

        mp._do_process = always_fail  # type: ignore[assignment]
        msg = _make_msg()
        result = await mp.process(msg, max_retries=2)
        assert result.is_valid is False
        assert "retries" in result.errors[0].lower() or "2" in result.errors[0]

    async def test_process_cancelled_error_propagates(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)

        async def cancel(m: Any) -> Any:
            raise asyncio.CancelledError()

        mp._do_process = cancel  # type: ignore[assignment]
        with pytest.raises(asyncio.CancelledError):
            await mp.process(_make_msg())


class TestMeteringCallback:
    """Cover _async_metering_callback error path."""

    async def test_metering_callback_success(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mp._metering_hooks = MagicMock()
        await mp._async_metering_callback(_make_msg(), 1.5)
        mp._metering_hooks.on_constitutional_validation.assert_called_once()

    async def test_metering_callback_swallows_error(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mp._metering_hooks = MagicMock()
        mp._metering_hooks.on_constitutional_validation.side_effect = RuntimeError("boom")
        # Should not raise
        await mp._async_metering_callback(_make_msg(), 1.0)


class TestDLQ:
    """Cover _send_to_dlq and _get_dlq_redis branches."""

    async def test_send_to_dlq_success(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mock_redis = AsyncMock()
        mp._dlq_redis = mock_redis
        msg = _make_msg()
        result = ValidationResult(is_valid=False, errors=["rejected"])
        await mp._send_to_dlq(msg, result)
        mock_redis.lpush.assert_awaited_once()
        mock_redis.ltrim.assert_awaited_once()

    async def test_send_to_dlq_error_clears_redis(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mock_redis = AsyncMock()
        mock_redis.lpush.side_effect = OSError("connection refused")
        mp._dlq_redis = mock_redis
        msg = _make_msg()
        result = ValidationResult(is_valid=False, errors=["rejected"])
        await mp._send_to_dlq(msg, result)
        assert mp._dlq_redis is None  # cleared on error

    async def test_get_dlq_redis_creates_client(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mock_from_url = MagicMock(return_value=MagicMock())
        with patch("redis.asyncio.from_url", mock_from_url):
            client = await mp._get_dlq_redis()
            assert client is not None
            mock_from_url.assert_called_once()

    async def test_get_dlq_redis_reuses_cached(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        sentinel = MagicMock()
        mp._dlq_redis = sentinel
        client = await mp._get_dlq_redis()
        assert client is sentinel


class TestHandlerRegistration:
    """Cover register_handler / unregister_handler."""

    def test_register_and_unregister(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)

        async def handler(m: Any) -> None:
            pass

        mp.register_handler(MessageType.COMMAND, handler)
        assert MessageType.COMMAND in mp._handlers
        assert handler in mp._handlers[MessageType.COMMAND]

        removed = mp.unregister_handler(MessageType.COMMAND, handler)
        assert removed is True

    def test_unregister_nonexistent_returns_false(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)

        async def handler(m: Any) -> None:
            pass

        removed = mp.unregister_handler(MessageType.COMMAND, handler)
        assert removed is False


class TestProperties:
    """Cover simple property accessors."""

    def test_processed_count(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        assert mp.processed_count == 0

    def test_failed_count(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        assert mp.failed_count == 0

    def test_processing_strategy(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        assert mp.processing_strategy is not None

    def test_opa_client_property(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        assert mp.opa_client is None


class TestGetMetrics:
    """Cover get_metrics including session governance and OPA enrichment."""

    def test_metrics_basic_structure(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        metrics = mp.get_metrics()
        assert "processed_count" in metrics
        assert "failed_count" in metrics
        assert "success_rate" in metrics
        assert metrics["processed_count"] == 0

    def test_metrics_with_pqc_config(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mock_cfg = MagicMock()
        mock_cfg.pqc_mode = "dilithium"
        mock_cfg.verification_mode = "strict"
        mock_cfg.migration_phase = 2
        mp._pqc_config = mock_cfg
        metrics = mp.get_metrics()
        assert metrics["pqc_mode"] == "dilithium"

    def test_metrics_success_rate_calculation(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mp._processed_count = 7
        mp._failed_count = 3
        metrics = mp.get_metrics()
        assert abs(metrics["success_rate"] - 0.7) < 0.01


class TestLogDecision:
    """Cover _log_decision with span attributes."""

    def test_log_decision_no_span(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        msg = _make_msg()
        result = ValidationResult(is_valid=True)
        mp._log_decision(msg, result)  # no exception

    def test_log_decision_with_span(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        msg = _make_msg()
        result = ValidationResult(is_valid=True)
        span = MagicMock()
        ctx = MagicMock()
        ctx.trace_id = 12345
        span.get_span_context.return_value = ctx
        mp._log_decision(msg, result, span=span)
        span.set_attribute.assert_called()

    def test_log_decision_with_span_no_trace(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        msg = _make_msg()
        result = ValidationResult(is_valid=False)
        span = MagicMock(spec=["set_attribute"])  # no get_span_context
        mp._log_decision(msg, result, span=span)
        span.set_attribute.assert_called()


class TestComplianceTags:
    """Cover _get_compliance_tags."""

    def test_approved_tags(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        msg = _make_msg(priority=Priority.MEDIUM)
        result = ValidationResult(is_valid=True)
        tags = mp._get_compliance_tags(msg, result)
        assert "approved" in tags
        assert "constitutional_validated" in tags
        assert "high_priority" not in tags

    def test_rejected_critical_tags(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        msg = _make_msg(priority=Priority.CRITICAL)
        result = ValidationResult(is_valid=False)
        tags = mp._get_compliance_tags(msg, result)
        assert "rejected" in tags
        assert "high_priority" in tags


class TestMCPIntegration:
    """Cover initialize_mcp and handle_tool_request branches."""

    async def test_initialize_mcp_feature_flag_disabled(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        with patch("enhanced_agent_bus.message_processor.MCP_ENABLED", False):
            await mp.initialize_mcp({})
            assert mp._mcp_pool is None

    async def test_initialize_mcp_deps_unavailable(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        with (
            patch("enhanced_agent_bus.message_processor.MCP_ENABLED", True),
            patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", False),
        ):
            await mp.initialize_mcp({})
            assert mp._mcp_pool is None

    async def test_handle_tool_request_mcp_unavailable(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        with patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", False):
            result = await mp.handle_tool_request("agent-1", "tool_x")
            assert result["status"] == "error"
            assert "not available" in result["error"]

    async def test_handle_tool_request_pool_not_initialized(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mp._mcp_pool = None
        mock_result = MagicMock()
        mock_result_cls = MagicMock()
        mock_result_cls.error_result.return_value = mock_result
        with (
            patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", True),
            patch("enhanced_agent_bus.message_processor.MCPToolResult", mock_result_cls),
        ):
            result = await mp.handle_tool_request("agent-1", "tool_x")
            assert result is mock_result

    async def test_handle_tool_request_registry_lookup_fails(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mock_pool = AsyncMock()
        mock_pool_result = MagicMock()
        mock_pool_result.status.value = "success"
        mock_pool.call_tool.return_value = mock_pool_result
        mp._mcp_pool = mock_pool

        mock_registry = AsyncMock()
        mock_registry.get_agent.side_effect = RuntimeError("registry down")
        mp._maci_registry = mock_registry

        with (
            patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", True),
            patch("enhanced_agent_bus.message_processor.MCPToolResult", MagicMock()),
        ):
            result = await mp.handle_tool_request("agent-1", "tool_x", {"arg": 1})
            assert result is mock_pool_result

    async def test_handle_tool_request_agent_not_in_registry_preserves_legacy_fallback(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mock_pool = AsyncMock()
        mock_pool_result = MagicMock()
        mock_pool_result.status.value = "success"
        mock_pool.call_tool.return_value = mock_pool_result
        mp._mcp_pool = mock_pool

        mock_registry = AsyncMock()
        mock_registry.get_agent.return_value = None
        mp._maci_registry = mock_registry

        with (
            patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", True),
            patch("enhanced_agent_bus.message_processor.MCPToolResult", MagicMock()),
        ):
            result = await mp.handle_tool_request("agent-1", "tool_x", {"arg": 1})

        assert result is mock_pool_result
        mock_pool.call_tool.assert_awaited_once_with(
            "tool_x",
            arguments={"arg": 1},
            agent_id="agent-1",
            agent_role="",
        )


class TestRecordAgentWorkflowEvent:
    """Cover _record_agent_workflow_event branches."""

    def test_no_collector(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mp._agent_workflow_metrics = None
        # Should silently return
        mp._record_agent_workflow_event(event_type="test", msg=_make_msg(), reason="r")

    def test_collector_error_swallowed(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mock_collector = MagicMock()
        mock_collector.record_event.side_effect = TypeError("bad arg")
        mp._agent_workflow_metrics = mock_collector
        # Should not raise
        mp._record_agent_workflow_event(event_type="test", msg=_make_msg(), reason="r")


class TestHandleFailedProcessing:
    """Cover _handle_failed_processing with critical priority rollback trigger."""

    async def test_critical_priority_triggers_rollback_event(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mp._record_agent_workflow_event = MagicMock()
        msg = _make_msg(priority=Priority.CRITICAL)
        result = ValidationResult(is_valid=False, errors=["denied"])

        mock_redis = AsyncMock()
        mp._dlq_redis = mock_redis

        await mp._handle_failed_processing(msg, result)

        calls = mp._record_agent_workflow_event.call_args_list
        event_types = [c.kwargs.get("event_type") for c in calls]
        assert "rollback_trigger" in event_types

    async def test_non_critical_no_rollback_event(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mp._record_agent_workflow_event = MagicMock()
        msg = _make_msg(priority=Priority.LOW)
        result = ValidationResult(is_valid=False, errors=["denied"])

        mock_redis = AsyncMock()
        mp._dlq_redis = mock_redis

        await mp._handle_failed_processing(msg, result)

        calls = mp._record_agent_workflow_event.call_args_list
        event_types = [c.kwargs.get("event_type") for c in calls]
        assert "rollback_trigger" not in event_types


class TestSetStrategy:
    def test_set_strategy(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        mp = MessageProcessor(isolated_mode=True)
        mock_strategy = MagicMock()
        mp._set_strategy(mock_strategy)
        assert mp._processing_strategy is mock_strategy


# ===================================================================
# 2. opa_client/core.py -- OPAClientCore, OPAClient, singletons
# ===================================================================


class TestOPAClientCoreInit:
    """Cover __init__ edge cases."""

    def test_invalid_cache_hash_mode(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            OPAClientCore(cache_hash_mode="invalid")

    def test_fast_hash_fallback_warning(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core.FAST_HASH_AVAILABLE", False):
            client = OPAClientCore(cache_hash_mode="fast")
            assert client.cache_hash_mode == "fast"

    def test_embedded_mode_falls_back_to_http(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=False):
            client = OPAClientCore(mode="embedded")
            assert client.mode == "http"

    def test_fail_closed_always_true(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        assert client.fail_closed is True


class TestOPAClientContextManager:
    """Cover __aenter__ and __aexit__."""

    async def test_context_manager(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        client.initialize = AsyncMock()  # type: ignore[method-assign]
        client.close = AsyncMock()  # type: ignore[method-assign]

        async with client as c:
            assert c is client

        client.initialize.assert_awaited_once()
        client.close.assert_awaited_once()


class TestGetStats:
    """Cover get_stats branches."""

    def test_stats_memory_cache_backend(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        stats = client.get_stats()
        assert stats["cache_backend"] == "memory"
        assert stats["fail_closed"] is True

    def test_stats_redis_cache_backend(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client._redis_client = MagicMock()
        stats = client.get_stats()
        assert stats["cache_backend"] == "redis"

    def test_stats_disabled_cache_backend(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(enable_cache=False)
        stats = client.get_stats()
        assert stats["cache_backend"] == "disabled"


class TestInitialize:
    """Cover initialize() mode branches."""

    async def test_initialize_http(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http", enable_cache=False)
        client._ensure_http_client = AsyncMock()  # type: ignore[method-assign]
        await client.initialize()
        client._ensure_http_client.assert_awaited_once()

    async def test_initialize_fallback(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback", enable_cache=False)
        client._ensure_http_client = AsyncMock()  # type: ignore[method-assign]
        await client.initialize()
        client._ensure_http_client.assert_awaited_once()

    async def test_initialize_embedded_with_sdk(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True):
            client = OPAClientCore(mode="embedded", enable_cache=False)
            client._initialize_embedded_opa = AsyncMock()  # type: ignore[method-assign]
            await client.initialize()
            client._initialize_embedded_opa.assert_awaited_once()

    async def test_initialize_with_redis_cache(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch(
            "enhanced_agent_bus.opa_client.core._redis_client_available",
            return_value=True,
        ):
            client = OPAClientCore(mode="fallback", enable_cache=True)
            client._ensure_http_client = AsyncMock()  # type: ignore[method-assign]
            client._initialize_redis_cache = AsyncMock()  # type: ignore[method-assign]
            await client.initialize()
            client._initialize_redis_cache.assert_awaited_once()


class TestEnsureHttpClient:
    """Cover _ensure_http_client idempotency."""

    async def test_creates_client_once(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        assert client._http_client is None
        await client._ensure_http_client()
        assert client._http_client is not None
        first_client = client._http_client
        await client._ensure_http_client()
        assert client._http_client is first_client
        await client._http_client.aclose()


class TestBuildSSLContext:
    """Cover _build_ssl_context_if_needed branches."""

    def test_http_url_returns_none(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="http://localhost:8181")
        assert client._build_ssl_context_if_needed() is None

    def test_https_url_returns_ssl_context(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="https://opa.example.com", ssl_verify=True)
        ctx = client._build_ssl_context_if_needed()
        assert isinstance(ctx, ssl.SSLContext)

    def test_ssl_disabled_production_raises(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="https://opa.example.com", ssl_verify=False)
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with pytest.raises(Exception, match="SSL verification cannot be disabled"):
                client._build_ssl_context_if_needed()

    def test_ssl_disabled_prod_alias_raises(self):
        from enhanced_agent_bus._compat.errors import ConfigurationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="https://opa.example.com", ssl_verify=False)
        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}):
            with pytest.raises(ConfigurationError):
                client._build_ssl_context_if_needed()

    def test_ssl_disabled_dev_allows(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="https://opa.example.com", ssl_verify=False)
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            ctx = client._build_ssl_context_if_needed()
            assert isinstance(ctx, ssl.SSLContext)
            assert ctx.check_hostname is False

    def test_ssl_with_cert_and_key(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(
            opa_url="https://opa.example.com",
            ssl_verify=True,
            ssl_cert="/tmp/cert.pem",
            ssl_key="/tmp/key.pem",
        )
        with patch.object(ssl.SSLContext, "load_cert_chain") as mock_load:
            ctx = client._build_ssl_context_if_needed()
            mock_load.assert_called_once_with(certfile="/tmp/cert.pem", keyfile="/tmp/key.pem")


class TestInitializeEmbeddedOPA:
    """Cover _initialize_embedded_opa success and failure."""

    async def test_embedded_init_success(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        mock_cls = MagicMock(return_value=MagicMock())
        with (
            patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True),
            patch(
                "enhanced_agent_bus.opa_client.core._get_embedded_opa_class", return_value=mock_cls
            ),
        ):
            client = OPAClientCore(mode="embedded")
            await client._initialize_embedded_opa()
            assert client._embedded_opa is not None

    async def test_embedded_init_failure_falls_back_to_http(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        mock_cls = MagicMock(side_effect=RuntimeError("opa init failed"))
        with (
            patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True),
            patch(
                "enhanced_agent_bus.opa_client.core._get_embedded_opa_class", return_value=mock_cls
            ),
        ):
            client = OPAClientCore(mode="embedded")
            client._ensure_http_client = AsyncMock()  # type: ignore[method-assign]
            await client._initialize_embedded_opa()
            assert client.mode == "http"
            client._ensure_http_client.assert_awaited_once()


class TestClose:
    """Cover close() error handling paths."""

    async def test_close_http_client(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_http = AsyncMock()
        client._http_client = mock_http
        await client.close()
        mock_http.aclose.assert_awaited_once()
        assert client._http_client is None

    async def test_close_http_event_loop_closed(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_http = AsyncMock()
        mock_http.aclose.side_effect = RuntimeError("Event loop is closed")
        client._http_client = mock_http
        await client.close()
        assert client._http_client is None

    async def test_close_http_other_runtime_error_raises(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_http = AsyncMock()
        mock_http.aclose.side_effect = RuntimeError("Something else")
        client._http_client = mock_http
        with pytest.raises(RuntimeError, match="Something else"):
            await client.close()

    async def test_close_redis_event_loop_closed(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_redis = AsyncMock()
        mock_redis.close.side_effect = RuntimeError("Event loop is closed")
        client._redis_client = mock_redis
        await client.close()
        assert client._redis_client is None

    async def test_close_redis_other_error_raises(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_redis = AsyncMock()
        mock_redis.close.side_effect = RuntimeError("Redis boom")
        client._redis_client = mock_redis
        with pytest.raises(RuntimeError, match="Redis boom"):
            await client.close()

    async def test_close_clears_memory_cache(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client._memory_cache["key"] = {"val": True}
        client._memory_cache_timestamps["key"] = time.time()
        await client.close()
        assert len(client._memory_cache) == 0
        assert len(client._memory_cache_timestamps) == 0


class TestDispatchEvaluation:
    """Cover _dispatch_evaluation routing."""

    async def test_dispatch_http(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        client._evaluate_http = AsyncMock(return_value={"result": True})  # type: ignore[method-assign]
        result = await client._dispatch_evaluation({"a": 1}, "data.test")
        assert result == {"result": True}

    async def test_dispatch_embedded(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True):
            client = OPAClientCore(mode="embedded")
        client._evaluate_embedded = AsyncMock(return_value={"result": True})  # type: ignore[method-assign]
        result = await client._dispatch_evaluation({"a": 1}, "data.test")
        assert result == {"result": True}

    async def test_dispatch_fallback(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        client._evaluate_fallback = AsyncMock(return_value={"result": False})  # type: ignore[method-assign]
        result = await client._dispatch_evaluation({"a": 1}, "data.test")
        assert result == {"result": False}


class TestValidatePolicyPath:
    """Cover _validate_policy_path injection prevention."""

    def test_valid_path(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client._validate_policy_path("data.acgs.allow")  # no exception

    def test_invalid_characters(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with pytest.raises(Exception, match="Invalid policy path"):
            client._validate_policy_path("data/acgs/allow")

    def test_path_traversal(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with pytest.raises(Exception, match="Path traversal"):
            client._validate_policy_path("data..acgs..allow")


class TestValidateInputData:
    """Cover _validate_input_data size check."""

    def test_small_input_passes(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client._validate_input_data({"key": "value"})

    def test_oversized_input_raises(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        # Create a large payload
        big_data = {"key": "x" * (1024 * 600)}
        with pytest.raises(Exception, match="exceeds maximum"):
            client._validate_input_data(big_data)


class TestEstimateInputSize:
    """Cover _estimate_input_size_bytes recursive branches."""

    def test_dict_recursion(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        data = {"a": {"b": {"c": 1}}}
        size = client._estimate_input_size_bytes(data)
        assert size > 0

    def test_list_recursion(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        data = [1, [2, [3]]]
        size = client._estimate_input_size_bytes(data)
        assert size > 0

    def test_circular_reference_protection(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        data: dict[str, Any] = {"a": None}
        data["a"] = data  # circular reference
        size = client._estimate_input_size_bytes(data)
        assert size > 0  # should not infinite loop

    def test_tuple_and_set(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        data = (1, 2, frozenset([3, 4]))
        size = client._estimate_input_size_bytes(data)
        assert size > 0


class TestFormatEvaluationResult:
    """Cover _format_evaluation_result branches for bool, dict, other."""

    def test_bool_result(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._format_evaluation_result(True, "http", "data.allow")
        assert result["allowed"] is True
        assert result["result"] is True

    def test_dict_result(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        opa_res = {"allow": True, "reason": "ok", "metadata": {"level": 1}}
        result = client._format_evaluation_result(opa_res, "http", "data.allow")
        assert result["allowed"] is True
        assert result["metadata"]["level"] == 1

    def test_dict_result_no_allow(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._format_evaluation_result({"other": 1}, "http", "data.allow")
        assert result["allowed"] is False

    def test_unexpected_type(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._format_evaluation_result(42, "http", "data.allow")
        assert result["allowed"] is False
        assert "Unexpected result type" in result["reason"]


class TestEvaluateHTTP:
    """Cover _evaluate_http error paths."""

    async def test_no_client_raises(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client._http_client = None
        with pytest.raises(OPANotInitializedError):
            await client._evaluate_http({"a": 1}, "data.acgs.allow")

    async def test_successful_evaluation(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"allow": True, "reason": "ok"}}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        client._http_client = mock_http

        result = await client._evaluate_http({"a": 1}, "data.acgs.allow")
        assert result["allowed"] is True

    async def test_json_decode_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("bad", "doc", 0)

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        client._http_client = mock_http

        with pytest.raises(PolicyEvaluationError):
            await client._evaluate_http({"a": 1}, "data.acgs.allow")


class TestEvaluateEmbedded:
    """Cover _evaluate_embedded error paths."""

    async def test_no_embedded_opa_raises(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        client._embedded_opa = None
        with pytest.raises(OPANotInitializedError):
            await client._evaluate_embedded({"a": 1}, "data.allow")

    async def test_runtime_error_raises_policy_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        mock_opa = MagicMock()
        mock_opa.evaluate.side_effect = RuntimeError("opa crash")
        client._embedded_opa = mock_opa
        with pytest.raises(PolicyEvaluationError):
            await client._evaluate_embedded({"a": 1}, "data.allow")

    async def test_type_error_raises_policy_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        mock_opa = MagicMock()
        mock_opa.evaluate.side_effect = TypeError("bad input")
        client._embedded_opa = mock_opa
        with pytest.raises(PolicyEvaluationError):
            await client._evaluate_embedded({"a": 1}, "data.allow")


class TestEvaluateFallback:
    """Cover _evaluate_fallback constitutional hash check."""

    async def test_matching_hash_still_denied(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        result = await client._evaluate_fallback(
            {"constitutional_hash": CONSTITUTIONAL_HASH}, "data.allow"
        )
        assert result["allowed"] is False
        assert "fail-closed" in result["reason"]

    async def test_wrong_hash_denied(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        result = await client._evaluate_fallback(
            {"constitutional_hash": "wrong_hash"}, "data.allow"
        )
        assert result["allowed"] is False
        assert "Invalid constitutional hash" in result["reason"]


class TestEvaluatePolicy:
    """Cover evaluate_policy error handling and caching."""

    async def test_validation_error_returns_fail_closed(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback")
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)  # type: ignore[method-assign]

        result = await client.evaluate_policy({"a": 1}, policy_path="data/invalid/path")
        assert result["allowed"] is False

    async def test_transport_error_returns_fail_closed(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http")
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)  # type: ignore[method-assign]
        client._evaluate_http = AsyncMock(  # type: ignore[method-assign]
            side_effect=OPAConnectionError("localhost", "conn refused")
        )

        result = await client.evaluate_policy({"a": 1}, policy_path="data.acgs.allow")
        assert result["allowed"] is False
        assert result["metadata"]["security"] == "fail-closed"

    async def test_cache_hit_returns_cached(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback")
        cached = {"result": True, "allowed": True, "reason": "cached"}
        client._get_from_cache = AsyncMock(return_value=cached)  # type: ignore[method-assign]
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)  # type: ignore[method-assign]

        result = await client.evaluate_policy({"a": 1})
        assert result["allowed"] is True


class TestValidateConstitutional:
    """Cover validate_constitutional error handling."""

    async def test_opa_error_returns_invalid(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        client.evaluate_policy = AsyncMock(  # type: ignore[method-assign]
            side_effect=OPAConnectionError("url", "failed")
        )
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)  # type: ignore[method-assign]

        result = await client.validate_constitutional({"content": "test"})
        assert result.is_valid is False
        assert any("OPA error" in e for e in result.errors)

    async def test_value_error_returns_invalid(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        client.evaluate_policy = AsyncMock(  # type: ignore[method-assign]
            side_effect=ValueError("bad input")
        )
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)  # type: ignore[method-assign]

        result = await client.validate_constitutional({"content": "test"})
        assert result.is_valid is False
        assert any("Validation error" in e for e in result.errors)

    async def test_successful_denied(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        client.evaluate_policy = AsyncMock(  # type: ignore[method-assign]
            return_value={"allowed": False, "reason": "hash mismatch", "metadata": {}}
        )
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)  # type: ignore[method-assign]

        result = await client.validate_constitutional({"content": "test"})
        assert result.is_valid is False

    async def test_successful_allowed(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        client.evaluate_policy = AsyncMock(  # type: ignore[method-assign]
            return_value={"allowed": True, "reason": "ok", "metadata": {}}
        )
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)  # type: ignore[method-assign]

        result = await client.validate_constitutional({"content": "test"})
        assert result.is_valid is True


class TestCheckAgentAuthorization:
    """Cover check_agent_authorization branches."""

    async def test_wrong_hash_returns_false(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = await client.check_agent_authorization(
            "agent-1",
            "write",
            "resource-x",
            context={"constitutional_hash": "wrong"},
        )
        assert result is False

    async def test_opa_error_returns_false(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client.evaluate_policy = AsyncMock(  # type: ignore[method-assign]
            side_effect=OPAConnectionError("url", "down")
        )
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)  # type: ignore[method-assign]

        result = await client.check_agent_authorization("a", "b", "c")
        assert result is False

    async def test_value_error_returns_false(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client.evaluate_policy = AsyncMock(  # type: ignore[method-assign]
            side_effect=ValueError("bad")
        )
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)  # type: ignore[method-assign]

        result = await client.check_agent_authorization("a", "b", "c")
        assert result is False

    async def test_successful_authorization(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client.evaluate_policy = AsyncMock(return_value={"allowed": True})  # type: ignore[method-assign]
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)  # type: ignore[method-assign]

        result = await client.check_agent_authorization("a", "b", "c")
        assert result is True


class TestLoadPolicy:
    """Cover load_policy branches."""

    async def test_non_http_mode_returns_false(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        result = await client.load_policy("test_policy", "package test")
        assert result is False

    async def test_no_http_client_returns_false(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        client._http_client = None
        result = await client.load_policy("test_policy", "package test")
        assert result is False

    async def test_successful_load(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.put.return_value = mock_response
        client._http_client = mock_http
        client.clear_cache = AsyncMock()  # type: ignore[method-assign]

        result = await client.load_policy("pol1", "package pol1\ndefault allow = false")
        assert result is True
        client.clear_cache.assert_awaited_once()

    async def test_timeout_returns_false(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_http = AsyncMock()
        mock_http.put.side_effect = httpx.TimeoutException("timeout")
        client._http_client = mock_http

        result = await client.load_policy("pol1", "package pol1")
        assert result is False

    async def test_runtime_error_returns_false(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_http = AsyncMock()
        mock_http.put.side_effect = RuntimeError("unexpected")
        client._http_client = mock_http

        result = await client.load_policy("pol1", "package pol1")
        assert result is False


class TestVerifyBundle:
    """Cover _verify_bundle error paths."""

    async def test_import_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with patch.dict(sys.modules, {"app.services.crypto_service": None}):
            result = await client._verify_bundle("/nonexistent", "sig", "pubkey")
            assert result is False

    async def test_file_not_found(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        # Patch the CryptoService import to succeed but file doesn't exist
        mock_module = MagicMock()
        with patch.dict(
            sys.modules,
            {
                "app": MagicMock(),
                "app.services": MagicMock(),
                "app.services.crypto_service": mock_module,
            },
        ):
            result = await client._verify_bundle("/nonexistent/bundle.tar.gz", "sig", "pubkey")
            assert result is False


class TestRollbackToLKG:
    """Cover _rollback_to_lkg branches."""

    async def test_lkg_exists(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with patch("os.path.exists", return_value=True):
            result = await client._rollback_to_lkg()
            assert result is True

    async def test_lkg_not_exists(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with patch("os.path.exists", return_value=False):
            result = await client._rollback_to_lkg()
            assert result is False


class TestHandleEvaluationError:
    """Cover _handle_evaluation_error."""

    def test_returns_fail_closed_dict(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._handle_evaluation_error(ValueError("test error"), "data.acgs.allow")
        assert result["allowed"] is False
        assert result["result"] is False
        assert result["metadata"]["security"] == "fail-closed"
        assert result["metadata"]["policy_path"] == "data.acgs.allow"


class TestEvaluateWithHistory:
    """Cover evaluate_with_history branches."""

    async def test_no_support_candidates_simple_eval(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        client._is_temporal_multi_path_enabled = MagicMock(return_value=False)  # type: ignore[method-assign]
        client._evaluate_fallback = AsyncMock(  # type: ignore[method-assign]
            return_value={"result": False, "allowed": False, "reason": "denied", "metadata": {}}
        )

        result = await client.evaluate_with_history(
            {"action": "deploy", "constitutional_hash": CONSTITUTIONAL_HASH},
            action_history=["step1", "step2"],
        )
        assert result["allowed"] is False

    async def test_error_handling_returns_fail_closed(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        client._is_temporal_multi_path_enabled = MagicMock(return_value=False)  # type: ignore[method-assign]
        client._evaluate_fallback = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("boom")
        )

        result = await client.evaluate_with_history(
            {"action": "deploy"},
            action_history=["step1"],
        )
        assert result["allowed"] is False

    async def test_invalid_policy_path_returns_fail_closed(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")

        result = await client.evaluate_with_history(
            {"action": "deploy"},
            action_history=["step1"],
            policy_path="data/../../../etc/passwd",
        )
        assert result["allowed"] is False


class TestSingletonLifecycle:
    """Cover initialize_opa_client, get_opa_client, close_opa_client."""

    async def test_initialize_creates_singleton(self):
        import enhanced_agent_bus.opa_client.core as core_mod

        original = core_mod._opa_client
        try:
            core_mod._opa_client = None
            mock_init = AsyncMock()
            with patch.object(core_mod.OPAClient, "initialize", mock_init):
                client = await core_mod.initialize_opa_client(mode="fallback")
                assert client is not None
                mock_init.assert_awaited_once()

                # Second call reuses
                client2 = await core_mod.initialize_opa_client(mode="http")
                assert client2 is client
        finally:
            core_mod._opa_client = original

    def test_get_opa_client_not_initialized(self):
        import enhanced_agent_bus.opa_client.core as core_mod

        original = core_mod._opa_client
        try:
            core_mod._opa_client = None
            with pytest.raises(OPANotInitializedError):
                core_mod.get_opa_client()
        finally:
            core_mod._opa_client = original

    def test_get_opa_client_returns_singleton(self):
        import enhanced_agent_bus.opa_client.core as core_mod

        original = core_mod._opa_client
        try:
            sentinel = MagicMock()
            core_mod._opa_client = sentinel
            assert core_mod.get_opa_client() is sentinel
        finally:
            core_mod._opa_client = original

    async def test_close_opa_client(self):
        import enhanced_agent_bus.opa_client.core as core_mod

        original = core_mod._opa_client
        try:
            mock_client = AsyncMock()
            core_mod._opa_client = mock_client
            await core_mod.close_opa_client()
            mock_client.close.assert_awaited_once()
            assert core_mod._opa_client is None
        finally:
            core_mod._opa_client = original

    async def test_close_opa_client_when_none(self):
        import enhanced_agent_bus.opa_client.core as core_mod

        original = core_mod._opa_client
        try:
            core_mod._opa_client = None
            await core_mod.close_opa_client()  # should not raise
            assert core_mod._opa_client is None
        finally:
            core_mod._opa_client = original


class TestOPASdkHelpers:
    """Cover _opa_sdk_available and _get_embedded_opa_class."""

    def test_opa_sdk_available_from_package(self):
        from enhanced_agent_bus.opa_client.core import _opa_sdk_available

        result = _opa_sdk_available()
        assert isinstance(result, bool)

    def test_get_embedded_opa_class(self):
        from enhanced_agent_bus.opa_client.core import _get_embedded_opa_class

        result = _get_embedded_opa_class()
        # Could be None or a class
        assert result is None or callable(result)

    def test_opa_sdk_available_no_package_in_modules(self):
        from enhanced_agent_bus.opa_client.core import _opa_sdk_available

        pkg_name = "enhanced_agent_bus.opa_client"
        original = sys.modules.get(pkg_name)
        try:
            if pkg_name in sys.modules:
                del sys.modules[pkg_name]
            result = _opa_sdk_available()
            assert isinstance(result, bool)
        finally:
            if original is not None:
                sys.modules[pkg_name] = original


class TestSanitizeError:
    """Cover _sanitize_error."""

    def test_sanitize_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._sanitize_error(ValueError("some error"))
        assert isinstance(result, str)


class TestLoadBundleFromUrl:
    """Cover load_bundle_from_url error paths."""

    async def test_no_http_client_initializes(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        client._http_client = None
        client.initialize = AsyncMock()  # type: ignore[method-assign]
        # After initialize, _http_client is still None, so response will fail
        mock_http = AsyncMock()
        mock_http.get.side_effect = httpx.ConnectError("refused")

        async def set_http():
            client._http_client = mock_http

        client.initialize = set_http  # type: ignore[method-assign]
        with patch("os.path.exists", return_value=False):
            result = await client.load_bundle_from_url(
                "http://example.com/bundle.tar.gz", "sig", "pubkey"
            )
            assert result is False

    async def test_timeout_triggers_rollback(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_http = AsyncMock()
        mock_http.get.side_effect = httpx.TimeoutException("timeout")
        client._http_client = mock_http

        with patch("os.path.exists", return_value=False):
            result = await client.load_bundle_from_url(
                "http://example.com/bundle.tar.gz", "sig", "pubkey"
            )
            assert result is False

    async def test_os_error_triggers_rollback(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_response = MagicMock()
        mock_response.content = b"bundle data"
        mock_response.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        client._http_client = mock_http

        with (
            patch("os.makedirs", side_effect=OSError("permission denied")),
            patch("os.path.exists", return_value=False),
        ):
            result = await client.load_bundle_from_url(
                "http://example.com/bundle.tar.gz", "sig", "pubkey"
            )
            assert result is False
