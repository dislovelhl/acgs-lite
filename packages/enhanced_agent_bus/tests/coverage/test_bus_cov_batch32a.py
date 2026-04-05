"""
Coverage tests for opa_client/core.py and message_processor.py — Batch 32a
Constitutional Hash: 608508a9bd224290

Targets remaining uncovered lines in:
- enhanced_agent_bus.opa_client.core (OPAClientCore, OPAClient, singleton helpers)
- enhanced_agent_bus.message_processor (MessageProcessor edge cases)
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import sys
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from enhanced_agent_bus._compat.errors import ConfigurationError
from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError
from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    AgentMessage,
    AutonomyTier,
    MessageStatus,
    MessageType,
    Priority,
    get_enum_value,
)
from enhanced_agent_bus.validators import ValidationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_msg(**overrides: Any) -> AgentMessage:
    """Create a minimal AgentMessage with defaults."""
    defaults: dict[str, Any] = {
        "from_agent": "agent-a",
        "to_agent": "agent-b",
        "message_type": MessageType.QUERY,
        "priority": Priority.NORMAL,
        "content": {"text": "hello"},
    }
    defaults.update(overrides)
    return AgentMessage(**defaults)


# ===========================================================================
# OPA CLIENT CORE TESTS
# ===========================================================================


class TestOPAClientCoreInit:
    """Tests for OPAClientCore.__init__ edge cases."""

    def test_invalid_cache_hash_mode_raises(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            OPAClientCore(cache_hash_mode="invalid_mode")

    def test_default_init_sets_fail_closed(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        assert client.fail_closed is True

    def test_trailing_slash_stripped_from_url(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="http://localhost:8181///")
        assert not client.opa_url.endswith("/")

    def test_embedded_mode_falls_back_to_http_when_sdk_unavailable(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=False):
            client = OPAClientCore(mode="embedded")
            assert client.mode == "http"

    def test_embedded_mode_kept_when_sdk_available(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True):
            client = OPAClientCore(mode="embedded")
            assert client.mode == "embedded"

    def test_fast_hash_warning_when_unavailable(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core.FAST_HASH_AVAILABLE", False):
            # Should not raise, just warn
            client = OPAClientCore(cache_hash_mode="fast")
            assert client.cache_hash_mode == "fast"

    def test_redis_url_from_param(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(redis_url="redis://custom:6379/5")
        assert client.redis_url == "redis://custom:6379/5"

    def test_memory_cache_maxsize_default(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        assert client._memory_cache_maxsize == 10000


class TestOPAClientCoreContextManager:
    """Tests for async context manager protocol."""

    async def test_aenter_calls_initialize(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        client.initialize = AsyncMock()
        result = await client.__aenter__()
        client.initialize.assert_awaited_once()
        assert result is client

    async def test_aexit_calls_close(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        client.close = AsyncMock()
        await client.__aexit__(None, None, None)
        client.close.assert_awaited_once()


class TestGetStats:
    """Tests for OPAClientCore.get_stats."""

    def test_stats_with_cache_disabled(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(enable_cache=False)
        stats = client.get_stats()
        assert stats["cache_backend"] == "disabled"
        assert stats["fail_closed"] is True

    def test_stats_with_redis_cache(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(enable_cache=True)
        client._redis_client = MagicMock()
        stats = client.get_stats()
        assert stats["cache_backend"] == "redis"

    def test_stats_with_memory_cache(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(enable_cache=True)
        stats = client.get_stats()
        assert stats["cache_backend"] == "memory"

    def test_stats_multipath_fields(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client._multipath_evaluation_count = 5
        client._multipath_last_path_count = 3
        stats = client.get_stats()
        assert stats["multipath_evaluation_count"] == 5
        assert stats["multipath_last_path_count"] == 3


class TestInitialize:
    """Tests for OPAClientCore.initialize."""

    async def test_initialize_http_mode(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http", enable_cache=False)
        await client.initialize()
        assert client._http_client is not None
        await client.close()

    async def test_initialize_fallback_mode(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback", enable_cache=False)
        await client.initialize()
        assert client._http_client is not None
        await client.close()

    async def test_initialize_embedded_mode(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        mock_opa = MagicMock()
        with (
            patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True),
            patch(
                "enhanced_agent_bus.opa_client.core._get_embedded_opa_class",
                return_value=mock_opa,
            ),
        ):
            client = OPAClientCore(mode="embedded", enable_cache=False)
            await client.initialize()
            assert client._embedded_opa is not None
            await client.close()

    async def test_initialize_embedded_fallback_on_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        def raise_runtime():
            raise RuntimeError("OPA init failed")

        with (
            patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True),
            patch(
                "enhanced_agent_bus.opa_client.core._get_embedded_opa_class",
                return_value=raise_runtime,
            ),
        ):
            client = OPAClientCore(mode="embedded", enable_cache=False)
            await client.initialize()
            assert client.mode == "http"
            await client.close()


class TestSSLContext:
    """Tests for _build_ssl_context_if_needed."""

    def test_no_ssl_for_http(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="http://localhost:8181")
        result = client._build_ssl_context_if_needed()
        assert result is None

    def test_ssl_context_for_https(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="https://opa.example.com:8181")
        result = client._build_ssl_context_if_needed()
        assert isinstance(result, ssl.SSLContext)

    def test_ssl_disabled_in_production_raises(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="https://opa.example.com", ssl_verify=False)
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with pytest.raises(Exception, match="SSL verification cannot be disabled"):
                client._build_ssl_context_if_needed()

    def test_ssl_disabled_in_prod_variant(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="https://opa.example.com", ssl_verify=False)
        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}):
            with pytest.raises(ConfigurationError):
                client._build_ssl_context_if_needed()

    def test_ssl_disabled_in_live_raises(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="https://opa.example.com", ssl_verify=False)
        with patch.dict(os.environ, {"ENVIRONMENT": "live"}):
            with pytest.raises(ConfigurationError):
                client._build_ssl_context_if_needed()

    def test_ssl_disabled_in_dev_warns_but_succeeds(self):
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
            ssl_cert="/tmp/cert.pem",
            ssl_key="/tmp/key.pem",
        )
        with patch.object(ssl.SSLContext, "load_cert_chain") as mock_load:
            ctx = client._build_ssl_context_if_needed()
            mock_load.assert_called_once_with(certfile="/tmp/cert.pem", keyfile="/tmp/key.pem")


class TestClose:
    """Tests for OPAClientCore.close."""

    async def test_close_http_client(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http", enable_cache=False)
        await client.initialize()
        assert client._http_client is not None
        await client.close()
        assert client._http_client is None

    async def test_close_event_loop_closed_http(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_http = AsyncMock()
        mock_http.aclose.side_effect = RuntimeError("Event loop is closed")
        client._http_client = mock_http
        await client.close()
        assert client._http_client is None

    async def test_close_event_loop_closed_redis(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_redis = AsyncMock()
        mock_redis.close.side_effect = RuntimeError("Event loop is closed")
        client._redis_client = mock_redis
        await client.close()
        assert client._redis_client is None

    async def test_close_runtime_error_not_event_loop_reraises(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_http = AsyncMock()
        mock_http.aclose.side_effect = RuntimeError("Something else")
        client._http_client = mock_http
        with pytest.raises(RuntimeError, match="Something else"):
            await client.close()

    async def test_close_redis_runtime_error_reraises(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_redis = AsyncMock()
        mock_redis.close.side_effect = RuntimeError("Not event loop")
        client._redis_client = mock_redis
        with pytest.raises(RuntimeError, match="Not event loop"):
            await client.close()

    async def test_close_clears_embedded_and_caches(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client._embedded_opa = MagicMock()
        client._memory_cache = {"key": "val"}
        client._memory_cache_timestamps = {"key": 1.0}
        await client.close()
        assert client._embedded_opa is None
        assert len(client._memory_cache) == 0
        assert len(client._memory_cache_timestamps) == 0


class TestValidatePolicyPath:
    """Tests for _validate_policy_path."""

    def test_valid_policy_path(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        # Should not raise
        client._validate_policy_path("data.acgs.allow")

    def test_invalid_chars_in_path(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with pytest.raises(Exception, match="Invalid policy path"):
            client._validate_policy_path("data/acgs/../allow")

    def test_path_traversal_detected(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with pytest.raises(Exception, match="Path traversal"):
            client._validate_policy_path("data..acgs..allow")

    def test_special_chars_rejected(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with pytest.raises(ACGSValidationError):
            client._validate_policy_path("data.acgs; DROP TABLE")


class TestValidateInputData:
    """Tests for _validate_input_data."""

    def test_small_input_passes(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client._validate_input_data({"key": "value"})

    def test_oversized_input_raises(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        # Create input larger than 512KB
        large_input = {"data": "x" * (1024 * 600)}
        with pytest.raises(Exception, match="exceeds maximum"):
            client._validate_input_data(large_input)


class TestEstimateInputSize:
    """Tests for _estimate_input_size_bytes edge cases."""

    def test_circular_reference_handled(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        d: dict[str, Any] = {"a": 1}
        d["self"] = d  # circular reference
        # Should not infinite loop
        size = client._estimate_input_size_bytes(d)
        assert size > 0

    def test_nested_list_sized(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        data = {"list": [1, 2, [3, 4, {"nested": True}]]}
        size = client._estimate_input_size_bytes(data)
        assert size > 0

    def test_tuple_and_set_sized(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        data = {"t": (1, 2, 3), "s": frozenset([4, 5])}
        size = client._estimate_input_size_bytes(data)
        assert size > 0

    def test_empty_dict(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        size = client._estimate_input_size_bytes({})
        assert size > 0

    def test_string_value(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        size = client._estimate_input_size_bytes("hello world")
        assert size > 0


class TestSanitizeError:
    """Tests for _sanitize_error."""

    def test_sanitize_basic_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._sanitize_error(ValueError("test error"))
        assert isinstance(result, str)

    def test_sanitize_error_with_url(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._sanitize_error(RuntimeError("Failed at http://secret:password@host/path"))
        assert isinstance(result, str)


class TestHandleEvaluationError:
    """Tests for _handle_evaluation_error."""

    def test_returns_fail_closed_result(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._handle_evaluation_error(ValueError("bad input"), "data.acgs.allow")
        assert result["result"] is False
        assert result["allowed"] is False
        assert result["metadata"]["security"] == "fail-closed"
        assert result["metadata"]["policy_path"] == "data.acgs.allow"


class TestFormatEvaluationResult:
    """Tests for _format_evaluation_result."""

    def test_bool_true_result(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._format_evaluation_result(True, "http", "data.acgs.allow")
        assert result["allowed"] is True
        assert result["result"] is True

    def test_bool_false_result(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._format_evaluation_result(False, "http", "data.acgs.allow")
        assert result["allowed"] is False

    def test_dict_result_with_allow(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        opa_result = {"allow": True, "reason": "Policy passed", "metadata": {"tier": "1"}}
        result = client._format_evaluation_result(opa_result, "http", "data.acgs.allow")
        assert result["allowed"] is True
        assert result["metadata"]["tier"] == "1"

    def test_dict_result_without_allow(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        opa_result = {"some_key": "val"}
        result = client._format_evaluation_result(opa_result, "http", "data.test")
        assert result["allowed"] is False
        assert result["reason"] == "Success"

    def test_unexpected_type_result(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._format_evaluation_result(42, "http", "data.test")
        assert result["allowed"] is False
        assert "Unexpected result type" in result["reason"]

    def test_list_type_result(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._format_evaluation_result([1, 2, 3], "embedded", "data.test")
        assert result["allowed"] is False

    def test_none_type_result(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._format_evaluation_result(None, "fallback", "data.test")
        assert result["allowed"] is False


class TestDispatchEvaluation:
    """Tests for _dispatch_evaluation routing."""

    async def test_dispatch_http(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        client._evaluate_http = AsyncMock(return_value={"result": True})
        result = await client._dispatch_evaluation({"input": 1}, "data.test")
        client._evaluate_http.assert_awaited_once()

    async def test_dispatch_embedded(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True):
            client = OPAClientCore(mode="embedded")
        client._evaluate_embedded = AsyncMock(return_value={"result": True})
        result = await client._dispatch_evaluation({"input": 1}, "data.test")
        client._evaluate_embedded.assert_awaited_once()

    async def test_dispatch_fallback(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        client._evaluate_fallback = AsyncMock(return_value={"result": False})
        result = await client._dispatch_evaluation({"input": 1}, "data.test")
        client._evaluate_fallback.assert_awaited_once()


class TestEvaluateHTTP:
    """Tests for _evaluate_http."""

    async def test_not_initialized_raises(self):
        from enhanced_agent_bus.exceptions import OPANotInitializedError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        client._http_client = None
        with pytest.raises(OPANotInitializedError):
            await client._evaluate_http({}, "data.acgs.allow")

    async def test_json_decode_error(self):
        from enhanced_agent_bus.exceptions import PolicyEvaluationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("bad", "", 0)

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        client._http_client = mock_http

        with pytest.raises(PolicyEvaluationError, match="Invalid OPA response"):
            await client._evaluate_http({"test": 1}, "data.acgs.allow")

    async def test_successful_http_eval(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"result": True}

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        client._http_client = mock_http

        result = await client._evaluate_http({"test": 1}, "data.acgs.allow")
        assert result["allowed"] is True

    async def test_connect_error_raises_opa_connection_error(self):
        from httpx import ConnectError as HTTPConnectError

        from enhanced_agent_bus.exceptions import OPAConnectionError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_http = AsyncMock()
        mock_http.post.side_effect = HTTPConnectError("Connection refused")
        client._http_client = mock_http

        with pytest.raises(OPAConnectionError):
            await client._evaluate_http({}, "data.acgs.allow")

    async def test_timeout_error_raises_opa_connection_error(self):
        from httpx import ConnectTimeout as HTTPConnectTimeout

        from enhanced_agent_bus.exceptions import OPAConnectionError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_http = AsyncMock()
        mock_http.post.side_effect = HTTPConnectTimeout("Timed out")
        client._http_client = mock_http

        with pytest.raises(OPAConnectionError):
            await client._evaluate_http({}, "data.acgs.allow")

    async def test_generic_timeout_raises_opa_connection_error(self):
        from httpx import TimeoutException as HTTPTimeoutException

        from enhanced_agent_bus.exceptions import OPAConnectionError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_http = AsyncMock()
        mock_http.post.side_effect = HTTPTimeoutException("timeout")
        client._http_client = mock_http

        with pytest.raises(OPAConnectionError):
            await client._evaluate_http({}, "data.acgs.allow")

    async def test_http_status_error_raises_policy_eval_error(self):
        import httpx
        from httpx import HTTPStatusError

        from enhanced_agent_bus.exceptions import PolicyEvaluationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_http = AsyncMock()
        mock_request = httpx.Request("POST", "http://localhost:8181/v1/data/test")
        mock_resp = httpx.Response(500, request=mock_request)
        mock_http.post.side_effect = HTTPStatusError(
            "Server Error", request=mock_request, response=mock_resp
        )
        client._http_client = mock_http

        with pytest.raises(PolicyEvaluationError):
            await client._evaluate_http({}, "data.acgs.allow")


class TestEvaluateEmbedded:
    """Tests for _evaluate_embedded."""

    async def test_not_initialized_raises(self):
        from enhanced_agent_bus.exceptions import OPANotInitializedError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True):
            client = OPAClientCore(mode="embedded")
        client._embedded_opa = None
        with pytest.raises(OPANotInitializedError):
            await client._evaluate_embedded({}, "data.test")

    async def test_runtime_error_raises_policy_eval_error(self):
        from enhanced_agent_bus.exceptions import PolicyEvaluationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True):
            client = OPAClientCore(mode="embedded")
        mock_opa = MagicMock()
        mock_opa.evaluate.side_effect = RuntimeError("OPA crashed")
        client._embedded_opa = mock_opa

        with pytest.raises(PolicyEvaluationError):
            await client._evaluate_embedded({}, "data.test")

    async def test_type_error_raises_policy_eval_error(self):
        from enhanced_agent_bus.exceptions import PolicyEvaluationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True):
            client = OPAClientCore(mode="embedded")
        mock_opa = MagicMock()
        mock_opa.evaluate.side_effect = TypeError("bad type")
        client._embedded_opa = mock_opa

        with pytest.raises(PolicyEvaluationError):
            await client._evaluate_embedded({}, "data.test")

    async def test_successful_embedded_eval(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True):
            client = OPAClientCore(mode="embedded")
        mock_opa = MagicMock()
        mock_opa.evaluate.return_value = True
        client._embedded_opa = mock_opa

        result = await client._evaluate_embedded({"data": 1}, "data.test")
        assert result["allowed"] is True


class TestEvaluateFallback:
    """Tests for _evaluate_fallback."""

    async def test_invalid_hash_denied(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        result = await client._evaluate_fallback(
            {"constitutional_hash": "wrong_hash"}, "data.acgs.allow"
        )
        assert result["allowed"] is False
        assert "Invalid constitutional hash" in result["reason"]

    async def test_correct_hash_still_denied_fail_closed(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        result = await client._evaluate_fallback(
            {"constitutional_hash": CONSTITUTIONAL_HASH}, "data.acgs.allow"
        )
        assert result["allowed"] is False
        assert "fail-closed" in result["reason"]

    async def test_empty_hash_denied(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        result = await client._evaluate_fallback({}, "data.acgs.allow")
        assert result["allowed"] is False


class TestEvaluatePolicy:
    """Tests for evaluate_policy main method."""

    async def test_cached_result_returned(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        cached = {"result": True, "allowed": True, "reason": "cached"}
        client._generate_cache_key = MagicMock(return_value="test_key")
        client._get_from_cache = AsyncMock(return_value=cached)

        result = await client.evaluate_policy({"test": 1})
        assert result["reason"] == "cached"

    async def test_validation_error_handled(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        client._generate_cache_key = MagicMock(return_value="key")
        client._get_from_cache = AsyncMock(return_value=None)
        client._validate_policy_path = MagicMock(side_effect=ValueError("bad path"))

        result = await client.evaluate_policy({"test": 1}, "bad;path")
        assert result["allowed"] is False

    async def test_connection_error_handled(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http", enable_cache=False)
        client._generate_cache_key = MagicMock(return_value="key")
        client._get_from_cache = AsyncMock(return_value=None)
        client._dispatch_evaluation = AsyncMock(side_effect=OSError("Network unreachable"))

        result = await client.evaluate_policy({"test": 1})
        assert result["allowed"] is False
        assert result["metadata"]["security"] == "fail-closed"

    async def test_runtime_error_handled(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http", enable_cache=False)
        client._generate_cache_key = MagicMock(return_value="key")
        client._get_from_cache = AsyncMock(return_value=None)
        client._dispatch_evaluation = AsyncMock(side_effect=RuntimeError("unexpected"))

        result = await client.evaluate_policy({"test": 1})
        assert result["allowed"] is False

    async def test_type_error_handled(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http", enable_cache=False)
        client._generate_cache_key = MagicMock(return_value="key")
        client._get_from_cache = AsyncMock(return_value=None)
        client._dispatch_evaluation = AsyncMock(side_effect=TypeError("bad type"))

        result = await client.evaluate_policy({"test": 1})
        assert result["allowed"] is False

    async def test_attribute_error_handled(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http", enable_cache=False)
        client._generate_cache_key = MagicMock(return_value="key")
        client._get_from_cache = AsyncMock(return_value=None)
        client._dispatch_evaluation = AsyncMock(side_effect=AttributeError("missing attr"))

        result = await client.evaluate_policy({"test": 1})
        assert result["allowed"] is False

    async def test_key_error_handled(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http", enable_cache=False)
        client._generate_cache_key = MagicMock(return_value="key")
        client._get_from_cache = AsyncMock(return_value=None)
        client._dispatch_evaluation = AsyncMock(side_effect=KeyError("missing key"))

        result = await client.evaluate_policy({"test": 1})
        assert result["allowed"] is False

    async def test_successful_eval_caches_result(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        client._generate_cache_key = MagicMock(return_value="key")
        client._get_from_cache = AsyncMock(return_value=None)
        client._set_to_cache = AsyncMock()
        expected = {"result": False, "allowed": False, "reason": "fail-closed", "metadata": {}}
        client._dispatch_evaluation = AsyncMock(return_value=expected)

        result = await client.evaluate_policy({"constitutional_hash": CONSTITUTIONAL_HASH})
        client._set_to_cache.assert_awaited_once()


class TestEvaluateWithHistory:
    """Tests for evaluate_with_history."""

    async def test_basic_history_evaluation(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        result = await client.evaluate_with_history(
            {"constitutional_hash": CONSTITUTIONAL_HASH, "action": "test"},
            action_history=["step1", "step2"],
        )
        assert result["allowed"] is False

    async def test_history_with_error_returns_fail_closed(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http", enable_cache=False)
        client._evaluate_http = AsyncMock(side_effect=RuntimeError("fail"))

        result = await client.evaluate_with_history(
            {"action": "test"},
            action_history=["step1"],
        )
        assert result["allowed"] is False

    async def test_history_validation_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        result = await client.evaluate_with_history(
            {"action": "test"},
            action_history=["step1"],
            policy_path="data..bad..path",  # triggers path traversal
        )
        assert result["allowed"] is False


class TestValidateConstitutional:
    """Tests for validate_constitutional."""

    async def test_valid_constitutional_message(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        client.evaluate_policy = AsyncMock(
            return_value={"allowed": True, "reason": "OK", "metadata": {}}
        )
        result = await client.validate_constitutional(
            {"constitutional_hash": CONSTITUTIONAL_HASH, "content": "test"}
        )
        assert isinstance(result, ValidationResult)

    async def test_invalid_constitutional_message(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        client.evaluate_policy = AsyncMock(
            return_value={
                "allowed": False,
                "reason": "Hash mismatch",
                "metadata": {},
            }
        )
        result = await client.validate_constitutional({"content": "bad"})
        assert result.is_valid is False

    async def test_constitutional_opa_error(self):
        from enhanced_agent_bus.exceptions import OPAConnectionError
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        client.evaluate_policy = AsyncMock(side_effect=OPAConnectionError("localhost", "refused"))
        result = await client.validate_constitutional({"content": "test"})
        assert result.is_valid is False

    async def test_constitutional_http_error(self):
        from httpx import ConnectError as HTTPConnectError

        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        client.evaluate_policy = AsyncMock(side_effect=HTTPConnectError("connection refused"))
        result = await client.validate_constitutional({"content": "test"})
        assert result.is_valid is False

    async def test_constitutional_value_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        client.evaluate_policy = AsyncMock(side_effect=ValueError("bad input"))
        result = await client.validate_constitutional({"content": "test"})
        assert result.is_valid is False


class TestCheckAgentAuthorization:
    """Tests for check_agent_authorization."""

    async def test_authorization_with_valid_hash(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        client.evaluate_policy = AsyncMock(
            return_value={"allowed": True, "reason": "OK", "metadata": {}}
        )
        result = await client.check_agent_authorization(
            "agent-1",
            "read",
            "resource-1",
            context={"constitutional_hash": CONSTITUTIONAL_HASH},
        )
        assert result is True

    async def test_authorization_with_wrong_hash(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        result = await client.check_agent_authorization(
            "agent-1",
            "read",
            "resource-1",
            context={"constitutional_hash": "wrong_hash"},
        )
        assert result is False

    async def test_authorization_with_no_context(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        client.evaluate_policy = AsyncMock(
            return_value={"allowed": False, "reason": "denied", "metadata": {}}
        )
        result = await client.check_agent_authorization("agent-1", "write", "res-1")
        assert result is False

    async def test_authorization_opa_error_returns_false(self):
        from enhanced_agent_bus.exceptions import OPAConnectionError
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        client.evaluate_policy = AsyncMock(side_effect=OPAConnectionError("localhost", "refused"))
        result = await client.check_agent_authorization("agent-1", "read", "res-1")
        assert result is False

    async def test_authorization_value_error_returns_false(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        client.evaluate_policy = AsyncMock(side_effect=ValueError("bad"))
        result = await client.check_agent_authorization("agent-1", "read", "res-1")
        assert result is False

    async def test_authorization_http_error_returns_false(self):
        from httpx import ConnectError as HTTPConnectError

        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="fallback", enable_cache=False)
        client.evaluate_policy = AsyncMock(side_effect=HTTPConnectError("connection refused"))
        result = await client.check_agent_authorization("agent-1", "read", "res-1")
        assert result is False


class TestLoadPolicy:
    """Tests for load_policy."""

    async def test_load_policy_not_http_mode(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback")
        result = await client.load_policy("test-policy", "package test")
        assert result is False

    async def test_load_policy_no_client(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        client._http_client = None
        result = await client.load_policy("test-policy", "package test")
        assert result is False

    async def test_load_policy_success(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.put.return_value = mock_response
        client._http_client = mock_http
        client.clear_cache = AsyncMock()

        result = await client.load_policy("test-policy", "package test\nallow = true")
        assert result is True
        client.clear_cache.assert_awaited_once()

    async def test_load_policy_connect_error(self):
        from httpx import ConnectError as HTTPConnectError

        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_http = AsyncMock()
        mock_http.put.side_effect = HTTPConnectError("refused")
        client._http_client = mock_http

        result = await client.load_policy("test-policy", "package test")
        assert result is False

    async def test_load_policy_timeout_error(self):
        from httpx import TimeoutException as HTTPTimeoutException

        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_http = AsyncMock()
        mock_http.put.side_effect = HTTPTimeoutException("timeout")
        client._http_client = mock_http

        result = await client.load_policy("test-policy", "package test")
        assert result is False

    async def test_load_policy_http_status_error(self):
        import httpx
        from httpx import HTTPStatusError

        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_http = AsyncMock()
        req = httpx.Request("PUT", "http://localhost:8181/v1/policies/test")
        resp = httpx.Response(400, request=req)
        mock_http.put.side_effect = HTTPStatusError("Bad Request", request=req, response=resp)
        client._http_client = mock_http

        result = await client.load_policy("test-policy", "bad rego")
        assert result is False

    async def test_load_policy_runtime_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_http = AsyncMock()
        mock_http.put.side_effect = RuntimeError("unexpected")
        client._http_client = mock_http

        result = await client.load_policy("test-policy", "package test")
        assert result is False

    async def test_load_policy_connect_timeout(self):
        from httpx import ConnectTimeout as HTTPConnectTimeout

        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        mock_http = AsyncMock()
        mock_http.put.side_effect = HTTPConnectTimeout("connect timeout")
        client._http_client = mock_http

        result = await client.load_policy("test-policy", "package test")
        assert result is False


class TestVerifyBundle:
    """Tests for _verify_bundle."""

    async def test_import_error_returns_false(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with patch.dict(sys.modules, {"app.services.crypto_service": None}):
            result = await client._verify_bundle("/nonexistent/bundle.tar.gz", "sig", "key")
        assert result is False

    async def test_file_not_found_returns_false(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = await client._verify_bundle("/nonexistent/path.tar.gz", "sig", "key")
        assert result is False


class TestRollbackToLKG:
    """Tests for _rollback_to_lkg."""

    async def test_rollback_with_lkg_file(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with patch("os.path.exists", return_value=True):
            result = await client._rollback_to_lkg()
            assert result is True

    async def test_rollback_without_lkg_file(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with patch("os.path.exists", return_value=False):
            result = await client._rollback_to_lkg()
            assert result is False


class TestSingletonLifecycle:
    """Tests for module-level singleton helpers."""

    async def test_initialize_creates_singleton(self):
        import enhanced_agent_bus.opa_client.core as core_mod

        original = core_mod._opa_client
        try:
            core_mod._opa_client = None
            client = await core_mod.initialize_opa_client(mode="fallback", enable_cache=False)
            assert client is not None
            assert core_mod._opa_client is client

            # Second call returns same instance
            client2 = await core_mod.initialize_opa_client()
            assert client2 is client
        finally:
            if core_mod._opa_client is not None:
                await core_mod._opa_client.close()
            core_mod._opa_client = original

    async def test_get_opa_client_raises_when_not_initialized(self):
        import enhanced_agent_bus.opa_client.core as core_mod
        from enhanced_agent_bus.exceptions import OPANotInitializedError

        original = core_mod._opa_client
        try:
            core_mod._opa_client = None
            with pytest.raises(OPANotInitializedError):
                core_mod.get_opa_client()
        finally:
            core_mod._opa_client = original

    async def test_close_opa_client(self):
        import enhanced_agent_bus.opa_client.core as core_mod

        original = core_mod._opa_client
        try:
            core_mod._opa_client = None
            client = await core_mod.initialize_opa_client(mode="fallback", enable_cache=False)
            await core_mod.close_opa_client()
            assert core_mod._opa_client is None
        finally:
            core_mod._opa_client = original

    async def test_close_opa_client_when_none(self):
        import enhanced_agent_bus.opa_client.core as core_mod

        original = core_mod._opa_client
        try:
            core_mod._opa_client = None
            await core_mod.close_opa_client()  # Should not raise
            assert core_mod._opa_client is None
        finally:
            core_mod._opa_client = original


class TestOpaSDKHelpers:
    """Tests for _opa_sdk_available and _get_embedded_opa_class."""

    def test_opa_sdk_available_from_package(self):
        from enhanced_agent_bus.opa_client.core import _opa_sdk_available

        result = _opa_sdk_available()
        assert isinstance(result, bool)

    def test_get_embedded_opa_class(self):
        from enhanced_agent_bus.opa_client.core import _get_embedded_opa_class

        result = _get_embedded_opa_class()
        # Could be None or a class
        assert result is None or callable(result)

    def test_opa_sdk_available_fallback_when_no_package(self):
        from enhanced_agent_bus.opa_client import core as core_mod

        pkg_name = core_mod.__name__.rsplit(".", 1)[0]
        saved = sys.modules.get(pkg_name)
        try:
            sys.modules[pkg_name] = None  # type: ignore[assignment]
            result = core_mod._opa_sdk_available()
            assert isinstance(result, bool)
        finally:
            if saved is not None:
                sys.modules[pkg_name] = saved
            elif pkg_name in sys.modules:
                del sys.modules[pkg_name]


# ===========================================================================
# MESSAGE PROCESSOR TESTS
# ===========================================================================


class TestMessageProcessorInit:
    """Tests for MessageProcessor.__init__ edge cases."""

    def test_isolated_mode_disables_features(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc._isolated_mode is True
        assert proc._opa_client is None

    def test_invalid_cache_hash_mode_raises(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            MessageProcessor(isolated_mode=True, cache_hash_mode="bogus")

    def test_non_string_cache_hash_mode_raises(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            MessageProcessor(isolated_mode=True, cache_hash_mode=123)


class TestMessageProcessorProcess:
    """Tests for MessageProcessor.process retry logic."""

    async def test_process_retries_on_transient_error(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        call_count = 0

        async def flaky_process(m):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient")
            return ValidationResult(is_valid=True)

        proc._do_process = flaky_process
        msg = _make_msg()
        result = await proc.process(msg, max_retries=3)
        assert result.is_valid is True
        assert call_count == 3

    async def test_process_exhausts_retries(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)

        async def always_fail(m):
            raise ValueError("permanent error")

        proc._do_process = always_fail
        msg = _make_msg()
        result = await proc.process(msg, max_retries=2)
        assert result.is_valid is False
        assert "2 retries" in result.errors[0]

    async def test_process_cancelled_error_propagates(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)

        async def cancel(m):
            raise asyncio.CancelledError()

        proc._do_process = cancel
        msg = _make_msg()
        with pytest.raises(asyncio.CancelledError):
            await proc.process(msg, max_retries=3)


class TestMessageProcessorProperties:
    """Tests for MessageProcessor properties."""

    def test_processed_count(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc.processed_count == 0
        proc._processed_count = 5
        assert proc.processed_count == 5

    def test_failed_count(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc.failed_count == 0
        proc._failed_count = 3
        assert proc.failed_count == 3

    def test_processing_strategy(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc.processing_strategy is not None

    def test_opa_client_property(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc.opa_client is None


class TestRegisterHandler:
    """Tests for handler registration/unregistration."""

    def test_register_handler(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)

        async def handler(msg):
            return msg

        proc.register_handler(MessageType.QUERY, handler)
        assert MessageType.QUERY in proc._handlers
        assert handler in proc._handlers[MessageType.QUERY]

    def test_register_multiple_handlers(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)

        async def handler1(msg):
            return msg

        async def handler2(msg):
            return msg

        proc.register_handler(MessageType.QUERY, handler1)
        proc.register_handler(MessageType.QUERY, handler2)
        assert len(proc._handlers[MessageType.QUERY]) == 2

    def test_unregister_handler(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)

        async def handler(msg):
            return msg

        proc.register_handler(MessageType.QUERY, handler)
        result = proc.unregister_handler(MessageType.QUERY, handler)
        assert result is True
        assert len(proc._handlers[MessageType.QUERY]) == 0

    def test_unregister_nonexistent_handler(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)

        async def handler(msg):
            return msg

        result = proc.unregister_handler(MessageType.QUERY, handler)
        assert result is False


class TestGetMetrics:
    """Tests for get_metrics."""

    def test_metrics_basic(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        metrics = proc.get_metrics()
        assert "processed_count" in metrics
        assert "failed_count" in metrics
        assert "success_rate" in metrics
        assert metrics["success_rate"] == 0.0

    def test_metrics_with_counts(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        proc._processed_count = 8
        proc._failed_count = 2
        metrics = proc.get_metrics()
        assert metrics["success_rate"] == 0.8


class TestLogDecision:
    """Tests for _log_decision."""

    def test_log_decision_no_span(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        msg = _make_msg()
        result = ValidationResult(is_valid=True)
        # Should not raise
        proc._log_decision(msg, result)

    def test_log_decision_with_span(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        msg = _make_msg()
        result = ValidationResult(is_valid=True)
        span = MagicMock()
        span.get_span_context.return_value = MagicMock(trace_id=12345)
        proc._log_decision(msg, result, span=span)
        span.set_attribute.assert_called()

    def test_log_decision_with_span_no_trace_id(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        msg = _make_msg()
        result = ValidationResult(is_valid=False)
        span = MagicMock()
        span_ctx = MagicMock(spec=[])  # no trace_id attribute
        span.get_span_context.return_value = span_ctx
        proc._log_decision(msg, result, span=span)


class TestGetComplianceTags:
    """Tests for _get_compliance_tags."""

    def test_approved_tags(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        msg = _make_msg()
        result = ValidationResult(is_valid=True)
        tags = proc._get_compliance_tags(msg, result)
        assert "constitutional_validated" in tags
        assert "approved" in tags

    def test_rejected_tags(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        msg = _make_msg()
        result = ValidationResult(is_valid=False)
        tags = proc._get_compliance_tags(msg, result)
        assert "rejected" in tags

    def test_critical_priority_tag(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        msg = _make_msg(priority=Priority.CRITICAL)
        result = ValidationResult(is_valid=True)
        tags = proc._get_compliance_tags(msg, result)
        assert "high_priority" in tags


class TestRecordAgentWorkflowEvent:
    """Tests for _record_agent_workflow_event."""

    def test_no_collector_noop(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        proc._agent_workflow_metrics = None
        msg = _make_msg()
        # Should not raise
        proc._record_agent_workflow_event(event_type="test", msg=msg, reason="test")

    def test_collector_error_swallowed(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        mock_collector = MagicMock()
        mock_collector.record_event.side_effect = RuntimeError("boom")
        proc._agent_workflow_metrics = mock_collector
        msg = _make_msg()
        # Should not raise
        proc._record_agent_workflow_event(event_type="test", msg=msg, reason="test")


class TestIndependentValidatorGate:
    """Tests for _enforce_independent_validator_gate."""

    def test_disabled_returns_none(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True, require_independent_validator=False)
        msg = _make_msg()
        assert proc._enforce_independent_validator_gate(msg) is None

    def test_low_impact_non_governance_returns_none(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True, require_independent_validator=True)
        msg = _make_msg(message_type=MessageType.QUERY, impact_score=0.1)
        assert proc._enforce_independent_validator_gate(msg) is None

    def test_high_impact_missing_validator_rejected(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
            independent_validator_threshold=0.5,
        )
        msg = _make_msg(impact_score=0.9, metadata={})
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert result.is_valid is False
        assert "independent_validator_missing" in result.metadata.get("rejection_reason", "")

    def test_self_validation_rejected(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
            independent_validator_threshold=0.5,
        )
        msg = _make_msg(
            impact_score=0.9,
            metadata={"validated_by_agent": "agent-a"},
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert "self_validation" in result.metadata.get("rejection_reason", "")

    def test_invalid_validation_stage_rejected(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
            independent_validator_threshold=0.5,
        )
        msg = _make_msg(
            impact_score=0.9,
            metadata={
                "validated_by_agent": "validator-1",
                "validation_stage": "proposer",
            },
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert "invalid_stage" in result.metadata.get("rejection_reason", "")

    def test_valid_independent_validator_passes(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
            independent_validator_threshold=0.5,
        )
        msg = _make_msg(
            impact_score=0.9,
            metadata={
                "validated_by_agent": "validator-1",
                "validation_stage": "independent",
            },
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is None

    def test_governance_request_requires_validator(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
        )
        msg = _make_msg(
            message_type=MessageType.GOVERNANCE_REQUEST,
            impact_score=0.1,
            metadata={},
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None

    def test_none_impact_score_treated_as_zero(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
            independent_validator_threshold=0.5,
        )
        msg = _make_msg(impact_score=None)
        # Low impact, non-governance type => should pass
        assert proc._enforce_independent_validator_gate(msg) is None


class TestAsyncMeteringCallback:
    """Tests for _async_metering_callback."""

    async def test_metering_callback_success(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        mock_hooks = MagicMock()
        proc._metering_hooks = mock_hooks
        msg = _make_msg()
        await proc._async_metering_callback(msg, 5.0)
        mock_hooks.on_constitutional_validation.assert_called_once()

    async def test_metering_callback_error_swallowed(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        mock_hooks = MagicMock()
        mock_hooks.on_constitutional_validation.side_effect = TypeError("bad")
        proc._metering_hooks = mock_hooks
        msg = _make_msg()
        # Should not raise
        await proc._async_metering_callback(msg, 5.0)


class TestSendToDLQ:
    """Tests for _send_to_dlq."""

    async def test_dlq_import_error_handled(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)

        async def fail_redis():
            raise ImportError("no redis")

        proc._get_dlq_redis = fail_redis
        msg = _make_msg()
        result = ValidationResult(is_valid=False, errors=["test failure"])
        # Should not raise
        await proc._send_to_dlq(msg, result)

    async def test_dlq_connection_error_handled(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        mock_client = AsyncMock()
        mock_client.lpush.side_effect = OSError("connection refused")
        proc._get_dlq_redis = AsyncMock(return_value=mock_client)
        msg = _make_msg()
        result = ValidationResult(is_valid=False, errors=["test"])
        await proc._send_to_dlq(msg, result)
        assert proc._dlq_redis is None


class TestSetStrategy:
    """Tests for _set_strategy."""

    def test_set_strategy(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        mock_strategy = MagicMock()
        proc._set_strategy(mock_strategy)
        assert proc._processing_strategy is mock_strategy


class TestHandleToolRequest:
    """Tests for handle_tool_request MCP integration."""

    async def test_mcp_unavailable(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        with patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", False):
            result = await proc.handle_tool_request("agent-1", "tool-1")
        assert result["status"] == "error"

    async def test_pool_not_initialized(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        proc._mcp_pool = None
        with patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", True):
            mock_tool_result = MagicMock()
            mock_tool_result.error_result.return_value = {"status": "error"}
            with patch("enhanced_agent_bus.message_processor.MCPToolResult", mock_tool_result):
                result = await proc.handle_tool_request("agent-1", "tool-1")
                assert result["status"] == "error"


class TestInitializeMCP:
    """Tests for initialize_mcp."""

    async def test_mcp_disabled_feature_flag(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        with patch("enhanced_agent_bus.message_processor.MCP_ENABLED", False):
            await proc.initialize_mcp({})
            assert proc._mcp_pool is None

    async def test_mcp_dependencies_unavailable(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        with (
            patch("enhanced_agent_bus.message_processor.MCP_ENABLED", True),
            patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", False),
        ):
            await proc.initialize_mcp({})
            assert proc._mcp_pool is None

    async def test_mcp_invalid_config_type(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        # Use a real class as MCPConfig so isinstance() works
        mock_mcp_config_cls = type("MCPConfig", (), {})
        with (
            patch("enhanced_agent_bus.message_processor.MCP_ENABLED", True),
            patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.message_processor.MCPConfig",
                mock_mcp_config_cls,
            ),
        ):
            # Pass an integer - not dict or MCPConfig
            await proc.initialize_mcp(12345)
            assert proc._mcp_pool is None
