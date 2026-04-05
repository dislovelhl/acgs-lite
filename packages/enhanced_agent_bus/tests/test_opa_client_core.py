"""
Tests for enhanced_agent_bus.opa_client.core

Covers OPAClientCore, OPAClient, and module-level singleton helpers.
Constitutional Hash: 608508a9bd224290
"""

import asyncio
import ssl
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from enhanced_agent_bus.models import CONSTITUTIONAL_HASH
from enhanced_agent_bus.opa_client.core import (
    OPAClient,
    OPAClientCore,
    _get_embedded_opa_class,
    _opa_sdk_available,
    close_opa_client,
    get_opa_client,
    initialize_opa_client,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Fresh OPAClient with caching disabled to simplify assertions."""
    return OPAClient(enable_cache=False)


@pytest.fixture
def http_client():
    """OPAClient pre-wired with a mock httpx client."""
    c = OPAClient(enable_cache=False)
    mock_http = MagicMock(spec=httpx.AsyncClient)
    c._http_client = mock_http
    return c


@pytest.fixture(autouse=True)
async def _reset_singleton():
    """Ensure the module singleton is cleared after each test."""
    yield
    await close_opa_client()


# ---------------------------------------------------------------------------
# __init__ validation
# ---------------------------------------------------------------------------


class TestOPAClientCoreInit:
    def test_defaults(self):
        c = OPAClientCore()
        assert c.opa_url == "http://localhost:8181"
        assert c.mode == "http"
        assert c.timeout == 5.0
        assert c.cache_ttl == 60
        assert c.enable_cache is True
        assert c.fail_closed is True
        assert c.ssl_verify is True
        assert c.optimize_level == 1

    def test_trailing_slash_stripped(self):
        c = OPAClientCore(opa_url="http://opa:8181/")
        assert c.opa_url == "http://opa:8181"

    def test_invalid_cache_hash_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            OPAClientCore(cache_hash_mode="bogus")

    def test_embedded_mode_falls_back_when_sdk_unavailable(self):
        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=False):
            c = OPAClientCore(mode="embedded")
            assert c.mode == "http"

    def test_embedded_mode_accepted_when_sdk_available(self):
        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True):
            c = OPAClientCore(mode="embedded")
            assert c.mode == "embedded"

    def test_custom_params(self):
        c = OPAClientCore(
            opa_url="http://custom:9999",
            mode="fallback",
            timeout=15.0,
            cache_ttl=300,
            enable_cache=False,
            ssl_verify=False,
            optimize_level=2,
        )
        assert c.opa_url == "http://custom:9999"
        assert c.mode == "fallback"
        assert c.timeout == 15.0
        assert c.cache_ttl == 300
        assert c.enable_cache is False
        assert c.ssl_verify is False
        assert c.optimize_level == 2


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    async def test_aenter_calls_initialize(self, client):
        with patch.object(client, "initialize", new_callable=AsyncMock) as mock:
            result = await client.__aenter__()
            mock.assert_awaited_once()
            assert result is client

    async def test_aexit_calls_close(self, client):
        with patch.object(client, "close", new_callable=AsyncMock) as mock:
            await client.__aexit__(None, None, None)
            mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    def test_memory_backend_default(self, client):
        client.enable_cache = True
        stats = client.get_stats()
        assert stats["cache_backend"] == "memory"
        assert stats["mode"] == "http"
        assert stats["fail_closed"] is True
        assert stats["cache_size"] == 0

    def test_redis_backend_when_redis_client_set(self, client):
        client.enable_cache = True
        client._redis_client = MagicMock()
        stats = client.get_stats()
        assert stats["cache_backend"] == "redis"

    def test_disabled_backend(self, client):
        client.enable_cache = False
        stats = client.get_stats()
        assert stats["cache_backend"] == "disabled"


# ---------------------------------------------------------------------------
# SSL context
# ---------------------------------------------------------------------------


class TestBuildSSLContext:
    def test_returns_none_for_http_url(self, client):
        client.opa_url = "http://localhost:8181"
        assert client._build_ssl_context_if_needed() is None

    def test_returns_ssl_context_for_https(self, client):
        client.opa_url = "https://opa.example.com"
        ctx = client._build_ssl_context_if_needed()
        assert isinstance(ctx, ssl.SSLContext)

    def test_raises_in_production_when_ssl_verify_false(self, client):
        client.opa_url = "https://opa.example.com"
        client.ssl_verify = False
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
            with pytest.raises(Exception, match="SSL verification cannot be disabled"):
                client._build_ssl_context_if_needed()

    def test_disables_verification_in_dev_when_ssl_verify_false(self, client):
        client.opa_url = "https://opa.example.com"
        client.ssl_verify = False
        with patch.dict("os.environ", {"ENVIRONMENT": "development"}):
            ctx = client._build_ssl_context_if_needed()
            assert ctx is not None
            assert ctx.check_hostname is False


# ---------------------------------------------------------------------------
# initialize / close
# ---------------------------------------------------------------------------


class TestInitializeClose:
    async def test_initialize_creates_http_client(self, client):
        await client.initialize()
        assert client._http_client is not None
        await client.close()

    async def test_initialize_idempotent(self, client):
        await client.initialize()
        first = client._http_client
        await client.initialize()
        assert client._http_client is first
        await client.close()

    async def test_close_clears_state(self, client):
        await client.initialize()
        client._memory_cache["k"] = {"v": 1}
        client._memory_cache_timestamps["k"] = 1.0
        client._embedded_executor = MagicMock()
        await client.close()
        assert client._http_client is None
        assert client._embedded_executor is None
        assert client._memory_cache == {}
        assert client._memory_cache_timestamps == {}

    async def test_close_handles_event_loop_closed_http(self, client):
        mock_http = AsyncMock()
        mock_http.aclose = AsyncMock(side_effect=RuntimeError("Event loop is closed"))
        client._http_client = mock_http
        await client.close()
        assert client._http_client is None

    async def test_close_reraises_other_runtime_errors_http(self, client):
        mock_http = AsyncMock()
        mock_http.aclose = AsyncMock(side_effect=RuntimeError("Something else"))
        client._http_client = mock_http
        with pytest.raises(RuntimeError, match="Something else"):
            await client.close()

    async def test_close_handles_event_loop_closed_redis(self, client):
        mock_redis = AsyncMock()
        mock_redis.close = AsyncMock(side_effect=RuntimeError("Event loop is closed"))
        client._redis_client = mock_redis
        await client.close()
        assert client._redis_client is None

    async def test_close_reraises_other_runtime_errors_redis(self, client):
        mock_redis = AsyncMock()
        mock_redis.close = AsyncMock(side_effect=RuntimeError("bad state"))
        client._redis_client = mock_redis
        with pytest.raises(RuntimeError, match="bad state"):
            await client.close()

    async def test_initialize_embedded_opa_success(self, client):
        fake_opa = MagicMock()
        with (
            patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True),
            patch(
                "enhanced_agent_bus.opa_client.core._get_embedded_opa_class",
                return_value=MagicMock(return_value=fake_opa),
            ),
        ):
            client.mode = "embedded"
            await client._initialize_embedded_opa()
            assert client._embedded_opa is fake_opa
            assert client._embedded_executor is not None

    async def test_initialize_embedded_opa_fallback_on_error(self, client):
        with patch(
            "enhanced_agent_bus.opa_client.core._get_embedded_opa_class",
            return_value=MagicMock(side_effect=RuntimeError("no wasm")),
        ):
            client.mode = "embedded"
            await client._initialize_embedded_opa()
            assert client.mode == "http"


# ---------------------------------------------------------------------------
# Policy path / input validation (VULN-009)
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_policy_path(self, client):
        client._validate_policy_path("data.acgs.allow")

    def test_policy_path_rejects_special_chars(self, client):
        with pytest.raises(Exception, match="Invalid policy path"):
            client._validate_policy_path("data.acgs; DROP TABLE")

    def test_policy_path_rejects_traversal(self, client):
        with pytest.raises(Exception, match="Path traversal"):
            client._validate_policy_path("data..acgs.allow")

    def test_policy_path_rejects_slashes(self, client):
        with pytest.raises(Exception, match="Invalid policy path"):
            client._validate_policy_path("data/acgs/allow")

    def test_validate_input_data_small(self, client):
        client._validate_input_data({"key": "value"})

    def test_validate_input_data_too_large(self, client):
        huge = {"key": "x" * (1024 * 600)}
        with pytest.raises(Exception, match="exceeds maximum"):
            client._validate_input_data(huge)

    def test_estimate_input_size_handles_nested(self, client):
        data = {"a": [1, 2, {"b": "c"}], "d": (4, 5)}
        size = client._estimate_input_size_bytes(data)
        assert size > 0

    def test_estimate_input_size_handles_circular_ref(self, client):
        a: dict = {}
        a["self"] = a
        size = client._estimate_input_size_bytes(a)
        assert size > 0


# ---------------------------------------------------------------------------
# _dispatch_evaluation
# ---------------------------------------------------------------------------


class TestDispatchEvaluation:
    async def test_dispatch_http(self, client):
        with patch.object(
            client, "_evaluate_http", new_callable=AsyncMock, return_value={"result": True}
        ) as mock:
            client.mode = "http"
            result = await client._dispatch_evaluation({"x": 1}, "data.test")
            mock.assert_awaited_once_with({"x": 1}, "data.test")
            assert result == {"result": True}

    async def test_dispatch_embedded(self, client):
        with patch.object(
            client, "_evaluate_embedded", new_callable=AsyncMock, return_value={"result": True}
        ) as mock:
            client.mode = "embedded"
            result = await client._dispatch_evaluation({"x": 1}, "data.test")
            mock.assert_awaited_once()

    async def test_dispatch_fallback(self, client):
        with patch.object(
            client, "_evaluate_fallback", new_callable=AsyncMock, return_value={"result": False}
        ) as mock:
            client.mode = "fallback"
            result = await client._dispatch_evaluation({"x": 1}, "data.test")
            mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# evaluate_policy
# ---------------------------------------------------------------------------


class TestEvaluatePolicy:
    async def test_happy_path(self, http_client):
        expected = {"result": True, "allowed": True, "reason": "ok", "metadata": {"mode": "http"}}
        with patch.object(
            http_client, "_dispatch_evaluation", new_callable=AsyncMock, return_value=expected
        ):
            result = await http_client.evaluate_policy({"user": "alice"}, "data.test.allow")
            assert result["allowed"] is True

    async def test_returns_cached(self, client):
        policy = "data.test.allow"
        inp = {"user": "alice"}
        cached = {"result": True, "allowed": True}
        with (
            patch.object(client, "_get_from_cache", new_callable=AsyncMock, return_value=cached),
            patch.object(client, "_generate_cache_key", return_value="k"),
        ):
            result = await client.evaluate_policy(inp, policy)
            assert result == cached

    def test_memory_cache_ttl_boundary_expires_exactly_at_threshold(self):
        client = OPAClient(enable_cache=True)
        cache_key = "opa:data.acgs.allow:test"
        client._memory_cache[cache_key] = {"allowed": True}
        client._memory_cache_timestamps[cache_key] = 100.0
        client.cache_ttl = 60

        with patch("enhanced_agent_bus.opa_client.cache.time.time", return_value=160.0):
            assert client._read_memory_cache(cache_key) is None

        assert cache_key not in client._memory_cache
        assert cache_key not in client._memory_cache_timestamps

    async def test_fallback_empty_input_fails_closed(self):
        client = OPAClient(mode="fallback", enable_cache=False)

        result = await client.evaluate_policy({})

        assert result["allowed"] is False
        assert "fail" in result["reason"].lower() or "hash" in result["reason"].lower()

    async def test_fail_closed_on_connection_error(self, http_client):
        http_client._http_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        result = await http_client.evaluate_policy({"user": "a"}, "data.test.allow")
        assert result["allowed"] is False
        assert result["metadata"]["security"] == "fail-closed"

    async def test_fail_closed_on_timeout(self, http_client):
        http_client._http_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        result = await http_client.evaluate_policy({"user": "a"}, "data.test.allow")
        assert result["allowed"] is False

    async def test_fail_closed_on_validation_error(self, client):
        result = await client.evaluate_policy({"user": "a"}, "data..bad.path")
        assert result["allowed"] is False

    async def test_delegates_to_multi_path_when_candidates_present(self, client):
        inp = {"user": "a", "support_set_candidates": [{"x": 1}]}
        with patch.object(
            client,
            "evaluate_policy_multi_path",
            new_callable=AsyncMock,
            return_value={"allowed": True},
        ) as mock:
            result = await client.evaluate_policy(inp, "data.test.allow")
            mock.assert_awaited_once()
            assert result["allowed"] is True


# ---------------------------------------------------------------------------
# _evaluate_http
# ---------------------------------------------------------------------------


class TestEvaluateHTTP:
    async def test_success_bool_result(self, http_client):
        resp = MagicMock()
        resp.json.return_value = {"result": True}
        resp.raise_for_status = MagicMock()
        http_client._http_client.post = AsyncMock(return_value=resp)

        result = await http_client._evaluate_http({"x": 1}, "data.acgs.allow")
        assert result["allowed"] is True
        assert result["metadata"]["mode"] == "http"

    async def test_success_dict_result(self, http_client):
        resp = MagicMock()
        resp.json.return_value = {"result": {"allow": True, "reason": "ok"}}
        resp.raise_for_status = MagicMock()
        http_client._http_client.post = AsyncMock(return_value=resp)

        result = await http_client._evaluate_http({"x": 1}, "data.acgs.allow")
        assert result["allowed"] is True

    async def test_not_initialized_raises(self, client):
        from enhanced_agent_bus.exceptions import OPANotInitializedError

        client._http_client = None
        with pytest.raises(OPANotInitializedError):
            await client._evaluate_http({}, "data.test")

    async def test_connect_error_raises_opa_connection(self, http_client):
        from enhanced_agent_bus.exceptions import OPAConnectionError

        http_client._http_client.post = AsyncMock(side_effect=httpx.ConnectError("fail"))
        with pytest.raises(OPAConnectionError):
            await http_client._evaluate_http({}, "data.test")

    async def test_timeout_raises_opa_connection(self, http_client):
        from enhanced_agent_bus.exceptions import OPAConnectionError

        http_client._http_client.post = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        with pytest.raises(OPAConnectionError):
            await http_client._evaluate_http({}, "data.test")

    async def test_status_error_raises_policy_evaluation(self, http_client):
        from enhanced_agent_bus.exceptions import PolicyEvaluationError

        request = httpx.Request("POST", "http://localhost")
        response = httpx.Response(500, request=request)
        http_client._http_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError("500", request=request, response=response)
        )
        with pytest.raises(PolicyEvaluationError):
            await http_client._evaluate_http({}, "data.test")

    async def test_json_decode_error_raises(self, http_client):
        import json as _json

        from enhanced_agent_bus.exceptions import PolicyEvaluationError

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = _json.JSONDecodeError("bad", "", 0)
        http_client._http_client.post = AsyncMock(return_value=resp)
        with pytest.raises(PolicyEvaluationError):
            await http_client._evaluate_http({}, "data.test")

    async def test_constructs_correct_url(self, http_client):
        resp = MagicMock()
        resp.json.return_value = {"result": True}
        resp.raise_for_status = MagicMock()
        http_client._http_client.post = AsyncMock(return_value=resp)

        await http_client._evaluate_http({}, "data.acgs.allow")
        call_args = http_client._http_client.post.call_args
        url = call_args[0][0]
        assert url == "http://localhost:8181/v1/data/acgs/allow"


# ---------------------------------------------------------------------------
# _evaluate_embedded
# ---------------------------------------------------------------------------


class TestEvaluateEmbedded:
    async def test_not_initialized_raises(self, client):
        from enhanced_agent_bus.exceptions import OPANotInitializedError

        client._embedded_opa = None
        with pytest.raises(OPANotInitializedError):
            await client._evaluate_embedded({}, "data.test")

    async def test_success(self, client):
        mock_opa = MagicMock()
        mock_opa.evaluate = MagicMock(return_value=True)
        client._embedded_opa = mock_opa

        result = await client._evaluate_embedded({"x": 1}, "data.test")
        assert result["allowed"] is True

    async def test_reuses_dedicated_executor_across_calls(self, client):
        mock_opa = MagicMock()
        mock_opa.evaluate = MagicMock(return_value=True)
        client._embedded_opa = mock_opa
        loop = MagicMock()
        loop.run_in_executor = AsyncMock(return_value=True)

        with patch(
            "enhanced_agent_bus.opa_client.core.asyncio.get_running_loop", return_value=loop
        ):
            with patch("enhanced_agent_bus.opa_client.core.ThreadPoolExecutor") as executor_cls:
                executor = MagicMock()
                executor_cls.return_value = executor

                await client._evaluate_embedded({"x": 1}, "data.test")
                await client._evaluate_embedded({"x": 2}, "data.test")

        executor_cls.assert_called_once_with(
            max_workers=1,
            thread_name_prefix="opa-embedded",
        )
        assert loop.run_in_executor.await_count == 2

    async def test_runtime_error_raises_policy_eval(self, client):
        from enhanced_agent_bus.exceptions import PolicyEvaluationError

        mock_opa = MagicMock()
        mock_opa.evaluate = MagicMock(side_effect=RuntimeError("boom"))
        client._embedded_opa = mock_opa

        with pytest.raises(PolicyEvaluationError):
            await client._evaluate_embedded({}, "data.test")

    async def test_type_error_raises_policy_eval(self, client):
        from enhanced_agent_bus.exceptions import PolicyEvaluationError

        mock_opa = MagicMock()
        mock_opa.evaluate = MagicMock(side_effect=TypeError("bad input"))
        client._embedded_opa = mock_opa

        with pytest.raises(PolicyEvaluationError):
            await client._evaluate_embedded({}, "data.test")


# ---------------------------------------------------------------------------
# _evaluate_fallback
# ---------------------------------------------------------------------------


class TestEvaluateFallback:
    async def test_always_denies_with_correct_hash(self, client):
        result = await client._evaluate_fallback(
            {"constitutional_hash": CONSTITUTIONAL_HASH}, "data.test"
        )
        assert result["allowed"] is False
        assert result["metadata"]["mode"] == "fallback"
        assert result["metadata"]["security"] == "fail-closed"

    async def test_wrong_constitutional_hash(self, client):
        result = await client._evaluate_fallback({"constitutional_hash": "wrong"}, "data.test")
        assert result["allowed"] is False
        assert "Invalid constitutional hash" in result["reason"]

    async def test_correct_hash_still_denies(self, client):
        result = await client._evaluate_fallback(
            {"constitutional_hash": CONSTITUTIONAL_HASH}, "data.test"
        )
        assert result["allowed"] is False


# ---------------------------------------------------------------------------
# _format_evaluation_result
# ---------------------------------------------------------------------------


class TestFormatEvaluationResult:
    def test_bool_true(self, client):
        r = client._format_evaluation_result(True, "http", "data.test")
        assert r["allowed"] is True
        assert r["result"] is True

    def test_bool_false(self, client):
        r = client._format_evaluation_result(False, "http", "data.test")
        assert r["allowed"] is False

    def test_dict_with_allow(self, client):
        r = client._format_evaluation_result(
            {"allow": True, "reason": "ok", "metadata": {"extra": 1}},
            "embedded",
            "data.test",
        )
        assert r["allowed"] is True
        assert r["metadata"]["extra"] == 1
        assert r["metadata"]["mode"] == "embedded"

    def test_dict_without_allow(self, client):
        r = client._format_evaluation_result({"foo": "bar"}, "http", "data.test")
        assert r["allowed"] is False

    def test_unexpected_type(self, client):
        r = client._format_evaluation_result(42, "http", "data.test")
        assert r["allowed"] is False
        assert "Unexpected result type" in r["reason"]


# ---------------------------------------------------------------------------
# _handle_evaluation_error / _sanitize_error
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_handle_evaluation_error_fail_closed(self, client):
        err = RuntimeError("connection lost")
        result = client._handle_evaluation_error(err, "data.test")
        assert result["allowed"] is False
        assert result["result"] is False
        assert result["metadata"]["security"] == "fail-closed"
        assert result["metadata"]["policy_path"] == "data.test"

    def test_sanitize_error_returns_string(self, client):
        s = client._sanitize_error(ValueError("bad"))
        assert isinstance(s, str)


# ---------------------------------------------------------------------------
# validate_constitutional
# ---------------------------------------------------------------------------


class TestValidateConstitutional:
    async def test_success(self, client):
        with patch.object(
            client,
            "evaluate_policy",
            new_callable=AsyncMock,
            return_value={"allowed": True, "reason": "ok", "metadata": {}},
        ):
            result = await client.validate_constitutional(
                {"constitutional_hash": CONSTITUTIONAL_HASH, "action": "test"}
            )
            assert result.is_valid is True

    async def test_denied(self, client):
        with patch.object(
            client,
            "evaluate_policy",
            new_callable=AsyncMock,
            return_value={"allowed": False, "reason": "policy denied", "metadata": {}},
        ):
            result = await client.validate_constitutional({"action": "test"})
            assert result.is_valid is False
            assert any("policy denied" in e for e in result.errors)

    async def test_opa_connection_error(self, client):
        from enhanced_agent_bus.exceptions import OPAConnectionError

        with patch.object(
            client,
            "evaluate_policy",
            new_callable=AsyncMock,
            side_effect=OPAConnectionError("localhost", "refused"),
        ):
            result = await client.validate_constitutional({"action": "test"})
            assert result.is_valid is False

    async def test_http_error(self, client):
        with patch.object(
            client,
            "evaluate_policy",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("fail"),
        ):
            result = await client.validate_constitutional({"action": "test"})
            assert result.is_valid is False

    async def test_validation_error(self, client):
        from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError

        with patch.object(
            client,
            "evaluate_policy",
            new_callable=AsyncMock,
            side_effect=ACGSValidationError("bad", field="x", constraint="y"),
        ):
            result = await client.validate_constitutional({"action": "test"})
            assert result.is_valid is False


# ---------------------------------------------------------------------------
# check_agent_authorization
# ---------------------------------------------------------------------------


class TestCheckAgentAuthorization:
    async def test_authorized(self, client):
        with patch.object(
            client,
            "evaluate_policy",
            new_callable=AsyncMock,
            return_value={"allowed": True},
        ):
            result = await client.check_agent_authorization("agent-1", "read", "resource-1")
            assert result is True

    async def test_denied(self, client):
        with patch.object(
            client,
            "evaluate_policy",
            new_callable=AsyncMock,
            return_value={"allowed": False},
        ):
            result = await client.check_agent_authorization("agent-1", "write", "resource-1")
            assert result is False

    async def test_wrong_hash_returns_false(self, client):
        result = await client.check_agent_authorization(
            "agent-1",
            "read",
            "resource-1",
            context={"constitutional_hash": "wrong_hash"},
        )
        assert result is False

    async def test_connection_error_returns_false(self, client):
        from enhanced_agent_bus.exceptions import OPAConnectionError

        with patch.object(
            client,
            "evaluate_policy",
            new_callable=AsyncMock,
            side_effect=OPAConnectionError("localhost", "refused"),
        ):
            result = await client.check_agent_authorization("a", "b", "c")
            assert result is False

    async def test_http_error_returns_false(self, client):
        with patch.object(
            client,
            "evaluate_policy",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("fail"),
        ):
            result = await client.check_agent_authorization("a", "b", "c")
            assert result is False

    async def test_value_error_returns_false(self, client):
        with patch.object(
            client,
            "evaluate_policy",
            new_callable=AsyncMock,
            side_effect=ValueError("bad"),
        ):
            result = await client.check_agent_authorization("a", "b", "c")
            assert result is False


# ---------------------------------------------------------------------------
# load_policy
# ---------------------------------------------------------------------------


class TestLoadPolicy:
    async def test_success(self, http_client):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        http_client._http_client.put = AsyncMock(return_value=resp)
        with patch.object(http_client, "clear_cache", new_callable=AsyncMock):
            result = await http_client.load_policy(
                "my_policy", "package my_policy\ndefault allow = false"
            )
            assert result is True

    async def test_not_http_mode(self, client):
        client.mode = "fallback"
        result = await client.load_policy("p", "content")
        assert result is False

    async def test_no_http_client(self, client):
        client._http_client = None
        result = await client.load_policy("p", "content")
        assert result is False

    async def test_connect_error(self, http_client):
        http_client._http_client.put = AsyncMock(side_effect=httpx.ConnectError("fail"))
        result = await http_client.load_policy("p", "content")
        assert result is False

    async def test_timeout_error(self, http_client):
        http_client._http_client.put = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        result = await http_client.load_policy("p", "content")
        assert result is False

    async def test_status_error(self, http_client):
        request = httpx.Request("PUT", "http://localhost")
        response = httpx.Response(500, request=request)
        http_client._http_client.put = AsyncMock(
            side_effect=httpx.HTTPStatusError("500", request=request, response=response)
        )
        result = await http_client.load_policy("p", "content")
        assert result is False

    async def test_runtime_error(self, http_client):
        http_client._http_client.put = AsyncMock(side_effect=RuntimeError("unexpected"))
        result = await http_client.load_policy("p", "content")
        assert result is False


# ---------------------------------------------------------------------------
# evaluate_with_history
# ---------------------------------------------------------------------------


class TestEvaluateWithHistory:
    async def test_basic_temporal_evaluation(self, client):
        with (
            patch.object(
                client,
                "_evaluate_http",
                new_callable=AsyncMock,
                return_value={
                    "result": True,
                    "allowed": True,
                    "reason": "ok",
                    "metadata": {"mode": "http"},
                },
            ),
            patch.object(
                client,
                "_is_temporal_multi_path_enabled",
                return_value=False,
            ),
        ):
            client._http_client = MagicMock()
            result = await client.evaluate_with_history(
                {"action": "test"}, ["step1", "step2"], "data.acgs.temporal.allow"
            )
            assert result["allowed"] is True

    async def test_fail_closed_on_error(self, client):
        with patch.object(
            client,
            "_evaluate_http",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("refused"),
        ):
            client._http_client = MagicMock()
            result = await client.evaluate_with_history(
                {"action": "test"}, ["step1"], "data.acgs.temporal.allow"
            )
            assert result["allowed"] is False

    async def test_invalid_policy_path_fail_closed(self, client):
        result = await client.evaluate_with_history({"action": "test"}, ["step1"], "data..bad")
        assert result["allowed"] is False


# ---------------------------------------------------------------------------
# _rollback_to_lkg
# ---------------------------------------------------------------------------


class TestRollbackToLKG:
    async def test_rollback_with_existing_lkg(self, client):
        with patch("os.path.exists", return_value=True):
            result = await client._rollback_to_lkg()
            assert result is True

    async def test_rollback_without_lkg(self, client):
        with patch("os.path.exists", return_value=False):
            result = await client._rollback_to_lkg()
            assert result is False


# ---------------------------------------------------------------------------
# load_bundle_from_url
# ---------------------------------------------------------------------------


class TestLoadBundleFromUrl:
    async def test_connection_error_triggers_rollback(self, http_client):
        http_client._http_client.get = AsyncMock(side_effect=httpx.ConnectError("fail"))
        with patch.object(
            http_client, "_rollback_to_lkg", new_callable=AsyncMock, return_value=False
        ) as mock_rollback:
            result = await http_client.load_bundle_from_url(
                "http://example.com/b.tar.gz", "sig", "key"
            )
            assert result is False
            mock_rollback.assert_awaited_once()

    async def test_timeout_triggers_rollback(self, http_client):
        http_client._http_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        with patch.object(
            http_client, "_rollback_to_lkg", new_callable=AsyncMock, return_value=False
        ):
            result = await http_client.load_bundle_from_url(
                "http://example.com/b.tar.gz", "sig", "key"
            )
            assert result is False


# ---------------------------------------------------------------------------
# _verify_bundle
# ---------------------------------------------------------------------------


class TestVerifyBundle:
    async def test_import_error_returns_false(self, client):
        with (
            patch("enhanced_agent_bus.opa_client.core.hashlib"),
            patch("builtins.open", side_effect=ImportError("no crypto")),
        ):
            result = await client._verify_bundle("/tmp/fake.tar.gz", "sig", "key")
            assert result is False

    async def test_file_not_found_returns_false(self, client):
        result = await client._verify_bundle("/nonexistent/bundle.tar.gz", "sig", "key")
        assert result is False


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------


class TestSingletonHelpers:
    async def test_initialize_creates_singleton(self):
        c = await initialize_opa_client(enable_cache=False)
        assert isinstance(c, OPAClient)
        await close_opa_client()

    async def test_initialize_idempotent(self):
        c1 = await initialize_opa_client(enable_cache=False)
        c2 = await initialize_opa_client(enable_cache=False)
        assert c1 is c2
        await close_opa_client()

    async def test_get_opa_client_raises_when_not_initialized(self):
        from enhanced_agent_bus.exceptions import OPANotInitializedError

        with pytest.raises(OPANotInitializedError):
            get_opa_client()

    async def test_get_opa_client_after_init(self):
        await initialize_opa_client(enable_cache=False)
        c = get_opa_client()
        assert isinstance(c, OPAClient)
        await close_opa_client()

    async def test_close_clears_singleton(self):
        await initialize_opa_client(enable_cache=False)
        await close_opa_client()
        from enhanced_agent_bus.exceptions import OPANotInitializedError

        with pytest.raises(OPANotInitializedError):
            get_opa_client()

    async def test_close_noop_when_not_initialized(self):
        await close_opa_client()


# ---------------------------------------------------------------------------
# _opa_sdk_available / _get_embedded_opa_class helpers
# ---------------------------------------------------------------------------


class TestSDKHelpers:
    def test_opa_sdk_available_returns_bool(self):
        result = _opa_sdk_available()
        assert isinstance(result, bool)

    def test_get_embedded_opa_class_returns_none_or_type(self):
        result = _get_embedded_opa_class()
        assert result is None or isinstance(result, type)


# ---------------------------------------------------------------------------
# OPAClient inherits correctly
# ---------------------------------------------------------------------------


class TestOPAClientComposition:
    def test_opa_client_is_core(self):
        c = OPAClient()
        assert isinstance(c, OPAClientCore)

    def test_opa_client_has_cache_methods(self):
        c = OPAClient()
        assert hasattr(c, "_generate_cache_key")
        assert hasattr(c, "_get_from_cache")
        assert hasattr(c, "_set_to_cache")
        assert hasattr(c, "clear_cache")

    def test_opa_client_has_health_methods(self):
        c = OPAClient()
        assert hasattr(c, "health_check")
        assert hasattr(c, "evaluate_policy_multi_path")
