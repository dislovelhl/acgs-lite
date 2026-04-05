"""
ACGS-2 OPA Adapter Coverage Expansion Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for OPAAdapter methods and module-level functions
targeting low-coverage areas: _get_http_client, _execute, _parse_opa_response,
_simulate_opa_response, _validate_response, _get_cache_key, _get_fallback_response,
close, and convenience functions.
"""

import asyncio
import hashlib
import json
import os

# Direct imports to ensure coverage tracking
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.json_utils import dumps as json_dumps

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

# Add parent to path for direct imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acl_adapters.base import AdapterResult
from acl_adapters.opa_adapter import (
    CONSTITUTIONAL_HASH,
    OPAAdapter,
    OPAAdapterConfig,
    OPARequest,
    OPAResponse,
    check_agent_permission,
    check_constitutional_compliance,
    evaluate_maci_role,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def opa_config():
    """Create OPA adapter configuration."""
    return OPAAdapterConfig(
        opa_url="http://localhost:8181",
        opa_bundle_path="/v1/data",
        fail_closed=True,
        default_policy_path="acgs2/constitutional",
        cache_enabled=True,
        cache_ttl_s=60,
        timeout_ms=1000,
        max_retries=2,
    )


@pytest.fixture
def opa_adapter(opa_config):
    """Create OPA adapter instance."""
    return OPAAdapter(name="test_opa", config=opa_config)


@pytest.fixture
def opa_request():
    """Create a sample OPA request."""
    return OPARequest(
        input={"action": "read", "resource": "test", "agent_id": "agent_001"},
        policy_path="acgs2/test/policy",
        explain=False,
        pretty=False,
        metrics=True,
        trace_id="test-trace-001",
    )


@pytest.fixture
def opa_request_with_options():
    """Create OPA request with all options enabled."""
    return OPARequest(
        input={"action": "write", "resource": "data"},
        policy_path="acgs2/test/policy",
        explain=True,
        pretty=True,
        metrics=True,
        trace_id="test-trace-002",
    )


# =============================================================================
# OPARequest Tests
# =============================================================================


class TestOPARequest:
    """Tests for OPARequest dataclass."""

    def test_request_with_trace_id(self):
        """Test OPARequest with explicit trace_id."""
        request = OPARequest(
            input={"action": "test"},
            trace_id="explicit-trace-id",
        )
        assert request.trace_id == "explicit-trace-id"
        assert request.input == {"action": "test"}
        assert request.policy_path is None
        assert request.explain is False
        assert request.pretty is False
        assert request.metrics is True

    def test_request_auto_generate_trace_id(self):
        """Test OPARequest generates trace_id when not provided."""
        request = OPARequest(input={"action": "test", "value": 123})

        # Should auto-generate trace_id in __post_init__
        assert request.trace_id is not None
        assert len(request.trace_id) == 16  # SHA256 hex digest truncated to 16

        # Verify deterministic generation
        expected = hashlib.sha256(
            json_dumps({"action": "test", "value": 123}, sort_keys=True).encode()
        ).hexdigest()[:16]
        assert request.trace_id == expected

    def test_request_with_all_options(self):
        """Test OPARequest with all options set."""
        request = OPARequest(
            input={"full": "test"},
            policy_path="custom/path",
            explain=True,
            pretty=True,
            metrics=False,
            trace_id="full-test-trace",
        )
        assert request.policy_path == "custom/path"
        assert request.explain is True
        assert request.pretty is True
        assert request.metrics is False


# =============================================================================
# OPAResponse Tests
# =============================================================================


class TestOPAResponse:
    """Tests for OPAResponse dataclass."""

    def test_response_minimal(self):
        """Test OPAResponse with minimal fields."""
        response = OPAResponse(allow=True)
        assert response.allow is True
        assert response.result is None
        assert response.decision_id is None
        assert response.constitutional_hash == CONSTITUTIONAL_HASH

    def test_response_full(self):
        """Test OPAResponse with all fields."""
        response = OPAResponse(
            allow=False,
            result={"reason": "denied"},
            decision_id="dec-001",
            explanation=["rule1 failed", "rule2 failed"],
            metrics={"eval_time_ns": 1000},
            trace_id="trace-001",
        )
        assert response.allow is False
        assert response.result == {"reason": "denied"}
        assert response.decision_id == "dec-001"
        assert response.explanation == ["rule1 failed", "rule2 failed"]
        assert response.metrics == {"eval_time_ns": 1000}
        assert response.trace_id == "trace-001"

    def test_response_to_dict(self):
        """Test OPAResponse.to_dict() method."""
        response = OPAResponse(
            allow=True,
            result={"allowed": True},
            decision_id="dec-123",
            explanation=["pass"],
            metrics={"time": 100},
            trace_id="trace-xyz",
        )

        result_dict = response.to_dict()

        assert result_dict["allow"] is True
        assert result_dict["result"] == {"allowed": True}
        assert result_dict["decision_id"] == "dec-123"
        assert result_dict["explanation"] == ["pass"]
        assert result_dict["metrics"] == {"time": 100}
        assert result_dict["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert result_dict["trace_id"] == "trace-xyz"


# =============================================================================
# OPAAdapterConfig Tests
# =============================================================================


class TestOPAAdapterConfig:
    """Tests for OPAAdapterConfig dataclass."""

    def test_default_config(self):
        """Test OPAAdapterConfig default values."""
        config = OPAAdapterConfig()

        assert config.opa_url == "http://localhost:8181"
        assert config.opa_bundle_path == "/v1/data"
        assert config.fail_closed is True
        assert config.default_policy_path == "acgs2/constitutional"
        assert config.cache_enabled is True
        assert config.cache_ttl_s == 60
        assert config.timeout_ms == 1000
        assert config.max_retries == 2
        assert config.circuit_failure_threshold == 3

    def test_custom_config(self):
        """Test OPAAdapterConfig with custom values."""
        config = OPAAdapterConfig(
            opa_url="http://custom:9191",
            fail_closed=False,
            cache_ttl_s=120,
            timeout_ms=5000,
        )

        assert config.opa_url == "http://custom:9191"
        assert config.fail_closed is False
        assert config.cache_ttl_s == 120
        assert config.timeout_ms == 5000


# =============================================================================
# OPAAdapter Tests
# =============================================================================


class TestOPAAdapterInit:
    """Tests for OPAAdapter initialization."""

    def test_init_default_config(self):
        """Test OPAAdapter with default configuration."""
        adapter = OPAAdapter()

        assert adapter.name == "opa"
        assert adapter.opa_config is not None
        assert adapter._http_client is not None

    def test_init_custom_config(self):
        """Test OPAAdapter with custom configuration."""
        config = OPAAdapterConfig(opa_url="http://custom:8181")
        adapter = OPAAdapter(name="custom_opa", config=config)

        assert adapter.name == "custom_opa"
        assert adapter.opa_config.opa_url == "http://custom:8181"

    def test_init_none_config_uses_default(self):
        """Test that None config creates default OPAAdapterConfig."""
        adapter = OPAAdapter(name="test", config=None)

        assert adapter.opa_config is not None
        assert adapter.opa_config.fail_closed is True


class TestOPAAdapterGetHttpClient:
    """Tests for OPAAdapter._get_http_client method."""

    async def test_get_http_client_creates_session(self, opa_adapter):
        """Test that _get_http_client creates internal HttpClient."""
        # Test the actual behavior
        client = await opa_adapter._get_http_client()
        assert client is not None

        # Either returns a session or None (if aiohttp not available)
        # This exercises the creation path

    async def test_get_http_client_returns_cached(self, opa_adapter):
        """Test that _get_http_client returns cached client."""
        mock_client = AsyncMock()
        opa_adapter._http_client = mock_client

        result = await opa_adapter._get_http_client()

        assert result is mock_client

    async def test_get_http_client_import_error(self, opa_adapter):
        """Test _get_http_client handles errors gracefully."""
        # Simulate HttpClient.start raising an error
        mock_client = AsyncMock()
        mock_client.start.side_effect = ImportError("Missing dependency")
        opa_adapter._http_client = mock_client

        with pytest.raises(ImportError):
            await opa_adapter._get_http_client()
            # Result may be None if aiohttp not available
            # This tests the ImportError handling path


class TestOPAAdapterSimulateResponse:
    """Tests for OPAAdapter._simulate_opa_response method."""

    def test_simulate_response_fail_closed(self, opa_adapter, opa_request):
        """Test _simulate_opa_response in fail-closed mode."""
        opa_adapter.opa_config.fail_closed = True

        response = opa_adapter._simulate_opa_response(opa_request)

        assert response.allow is False
        assert response.result == {"simulated": True, "reason": "opa_unavailable"}
        assert response.trace_id == opa_request.trace_id

    def test_simulate_response_fail_open(self, opa_adapter, opa_request):
        """Test _simulate_opa_response in fail-open mode."""
        opa_adapter.opa_config.fail_closed = False

        response = opa_adapter._simulate_opa_response(opa_request)

        assert response.allow is True
        assert response.result == {"simulated": True, "reason": "opa_unavailable_failopen"}
        assert response.trace_id == opa_request.trace_id


class TestOPAAdapterParseResponse:
    """Tests for OPAAdapter._parse_opa_response method."""

    def test_parse_response_bool_result(self, opa_adapter, opa_request):
        """Test parsing OPA response with boolean result."""
        data = {"result": True}

        response = opa_adapter._parse_opa_response(data, opa_request)

        assert response.allow is True
        assert response.trace_id == opa_request.trace_id
        assert response.decision_id is not None

    def test_parse_response_dict_with_allow(self, opa_adapter, opa_request):
        """Test parsing OPA response with dict containing 'allow' key."""
        data = {"result": {"allow": True, "reason": "permitted"}}

        response = opa_adapter._parse_opa_response(data, opa_request)

        assert response.allow is True
        assert response.result == {"allow": True, "reason": "permitted"}

    def test_parse_response_dict_with_allowed(self, opa_adapter, opa_request):
        """Test parsing OPA response with dict containing 'allowed' key."""
        data = {"result": {"allowed": False, "reason": "denied"}}

        response = opa_adapter._parse_opa_response(data, opa_request)

        assert response.allow is False

    def test_parse_response_with_explanation(self, opa_adapter, opa_request_with_options):
        """Test parsing OPA response with explanation."""
        data = {
            "result": True,
            "explanation": ["rule1 passed", "rule2 passed"],
        }

        response = opa_adapter._parse_opa_response(data, opa_request_with_options)

        assert response.explanation == ["rule1 passed", "rule2 passed"]

    def test_parse_response_with_metrics(self, opa_adapter, opa_request):
        """Test parsing OPA response with metrics."""
        data = {
            "result": True,
            "metrics": {"timer_eval_ns": 1000, "timer_server_handler_ns": 2000},
        }

        response = opa_adapter._parse_opa_response(data, opa_request)

        assert response.metrics == {"timer_eval_ns": 1000, "timer_server_handler_ns": 2000}

    def test_parse_response_empty_result(self, opa_adapter, opa_request):
        """Test parsing OPA response with empty result defaults to deny."""
        data = {}

        response = opa_adapter._parse_opa_response(data, opa_request)

        assert response.allow is False
        assert response.result == {}

    def test_parse_response_decision_id_generated(self, opa_adapter, opa_request):
        """Test that decision_id is generated correctly."""
        data = {"result": True}

        response = opa_adapter._parse_opa_response(data, opa_request)

        expected_decision = hashlib.sha256(f"{opa_request.trace_id}:True".encode()).hexdigest()[:16]
        assert response.decision_id == expected_decision


class TestOPAAdapterValidateResponse:
    """Tests for OPAAdapter._validate_response method."""

    def test_validate_response_valid_true(self, opa_adapter):
        """Test _validate_response with valid allow=True response."""
        response = OPAResponse(allow=True)

        assert opa_adapter._validate_response(response) is True

    def test_validate_response_valid_false(self, opa_adapter):
        """Test _validate_response with valid allow=False response."""
        response = OPAResponse(allow=False)

        assert opa_adapter._validate_response(response) is True

    def test_validate_response_invalid_type(self, opa_adapter):
        """Test _validate_response with non-boolean allow."""
        # Create response with invalid type (manually override)
        response = OPAResponse(allow=True)
        response.allow = "not_a_bool"  # type: ignore

        assert opa_adapter._validate_response(response) is False


class TestOPAAdapterGetCacheKey:
    """Tests for OPAAdapter._get_cache_key method."""

    def test_get_cache_key_basic(self, opa_adapter, opa_request):
        """Test _get_cache_key generates consistent key."""
        key1 = opa_adapter._get_cache_key(opa_request)
        key2 = opa_adapter._get_cache_key(opa_request)

        assert key1 == key2
        assert len(key1) == 64  # SHA256 hex digest

    def test_get_cache_key_different_inputs(self, opa_adapter):
        """Test _get_cache_key generates different keys for different inputs."""
        request1 = OPARequest(input={"action": "read"})
        request2 = OPARequest(input={"action": "write"})

        key1 = opa_adapter._get_cache_key(request1)
        key2 = opa_adapter._get_cache_key(request2)

        assert key1 != key2

    def test_get_cache_key_uses_policy_path(self, opa_adapter):
        """Test _get_cache_key includes policy path."""
        request1 = OPARequest(input={"action": "read"}, policy_path="path/a")
        request2 = OPARequest(input={"action": "read"}, policy_path="path/b")

        key1 = opa_adapter._get_cache_key(request1)
        key2 = opa_adapter._get_cache_key(request2)

        assert key1 != key2

    def test_get_cache_key_default_policy_path(self, opa_adapter):
        """Test _get_cache_key uses default policy path when not specified."""
        request = OPARequest(input={"action": "read"}, policy_path=None)

        key = opa_adapter._get_cache_key(request)

        # Should use default path from config
        expected_data = f"{opa_adapter.opa_config.default_policy_path}|{json_dumps(request.input, sort_keys=True)}"
        expected_key = hashlib.sha256(expected_data.encode()).hexdigest()
        assert key == expected_key


class TestOPAAdapterGetFallbackResponse:
    """Tests for OPAAdapter._get_fallback_response method."""

    def test_fallback_response_fail_closed(self, opa_adapter, opa_request):
        """Test _get_fallback_response in fail-closed mode."""
        opa_adapter.opa_config.fail_closed = True

        response = opa_adapter._get_fallback_response(opa_request)

        assert response is not None
        assert response.allow is False
        assert response.result == {"fallback": True, "reason": "circuit_open"}
        assert response.trace_id == opa_request.trace_id

    def test_fallback_response_fail_open(self, opa_adapter, opa_request):
        """Test _get_fallback_response in fail-open mode returns None."""
        opa_adapter.opa_config.fail_closed = False

        response = opa_adapter._get_fallback_response(opa_request)

        assert response is None


class TestOPAAdapterClose:
    """Tests for OPAAdapter.close method."""

    async def test_close_with_client(self, opa_adapter):
        """Test close() properly closes HTTP client."""
        mock_client = AsyncMock()
        opa_adapter._http_client = mock_client

        await opa_adapter.close()

        mock_client.close.assert_called_once()
        assert opa_adapter._http_client is None

    async def test_close_without_client(self, opa_adapter):
        """Test close() handles None client gracefully."""
        opa_adapter._http_client = None

        await opa_adapter.close()  # Should not raise

        assert opa_adapter._http_client is None


class TestOPAAdapterExecute:
    """Tests for OPAAdapter._execute method."""

    async def test_execute_without_http_client(self, opa_adapter, opa_request):
        """Test _execute falls back to simulated response when no HTTP client."""
        opa_adapter._http_client = None

        # Mock _get_http_client to return None (simulating no aiohttp)
        async def mock_get_client():
            return None

        opa_adapter._get_http_client = mock_get_client

        response = await opa_adapter._execute(opa_request)

        # Should use _simulate_opa_response
        assert response.result.get("simulated") is True

    async def test_execute_with_query_params(self, opa_adapter, opa_request_with_options):
        """Test _execute builds correct URL with query params."""
        # Mock client to capture the URL
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"result": True})

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.post = MagicMock(return_value=mock_context)

        opa_adapter._http_client = mock_client

        async def mock_get_client():
            return mock_client

        opa_adapter._get_http_client = mock_get_client

        await opa_adapter._execute(opa_request_with_options)

        # Check that URL contains query params
        call_args = mock_client.post.call_args
        url = call_args[0][0]
        assert "explain=full" in url
        assert "pretty=true" in url
        assert "metrics=true" in url

    async def test_execute_non_200_status_fail_closed(self, opa_adapter, opa_request):
        """Test _execute handles non-200 status in fail-closed mode."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def mock_get_client():
            return mock_client

        opa_adapter._get_http_client = mock_get_client
        opa_adapter.opa_config.fail_closed = True

        response = await opa_adapter._execute(opa_request)

        assert response.allow is False
        assert "error" in response.result
        assert "500" in response.result["error"]

    async def test_execute_timeout_fail_closed(self, opa_adapter, opa_request):
        """Test _execute handles timeout in fail-closed mode."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=TimeoutError())

        async def mock_get_client():
            return mock_client

        opa_adapter._get_http_client = mock_get_client
        opa_adapter.opa_config.fail_closed = True

        response = await opa_adapter._execute(opa_request)

        assert response.allow is False
        assert response.result == {"error": "timeout"}

    async def test_execute_exception_fail_closed(self, opa_adapter, opa_request):
        """Test _execute handles connection exception in fail-closed mode."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = ConnectionError("Connection refused")

        async def mock_get_client():
            return mock_client

        opa_adapter._get_http_client = mock_get_client
        opa_adapter.opa_config.fail_closed = True

        response = await opa_adapter._execute(opa_request)

        assert response.allow is False
        assert "Connection refused" in str(response.result["error"])


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestCheckConstitutionalCompliance:
    """Tests for check_constitutional_compliance function."""

    async def test_check_compliance_creates_adapter(self):
        """Test check_constitutional_compliance creates adapter when not provided."""
        with patch.object(OPAAdapter, "call", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = AdapterResult(
                success=True,
                data=OPAResponse(allow=True),
            )

            result = await check_constitutional_compliance(
                action="read",
                resource="test_resource",
            )

            mock_call.assert_called_once()
            # Verify request was created correctly
            request = mock_call.call_args[0][0]
            assert request.input["action"] == "read"
            assert request.input["resource"] == "test_resource"
            assert request.input["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_check_compliance_with_context(self):
        """Test check_constitutional_compliance with additional context."""
        with patch.object(OPAAdapter, "call", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = AdapterResult(
                success=True,
                data=OPAResponse(allow=True),
            )

            await check_constitutional_compliance(
                action="write",
                resource="sensitive_data",
                context={"user_role": "admin", "department": "security"},
            )

            request = mock_call.call_args[0][0]
            assert request.input["user_role"] == "admin"
            assert request.input["department"] == "security"

    async def test_check_compliance_with_provided_adapter(self):
        """Test check_constitutional_compliance with provided adapter."""
        mock_adapter = MagicMock(spec=OPAAdapter)
        mock_adapter.call = AsyncMock(
            return_value=AdapterResult(
                success=True,
                data=OPAResponse(allow=False),
            )
        )

        result = await check_constitutional_compliance(
            action="delete",
            resource="critical",
            adapter=mock_adapter,
        )

        mock_adapter.call.assert_called_once()
        assert result.success is True


class TestCheckAgentPermission:
    """Tests for check_agent_permission function."""

    async def test_check_permission_basic(self):
        """Test check_agent_permission basic functionality."""
        with patch.object(OPAAdapter, "call", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = AdapterResult(
                success=True,
                data=OPAResponse(allow=True),
            )

            result = await check_agent_permission(
                agent_id="agent_001",
                permission="execute_task",
            )

            request = mock_call.call_args[0][0]
            assert request.input["agent_id"] == "agent_001"
            assert request.input["permission"] == "execute_task"
            assert request.input["target"] is None
            assert request.policy_path == "acgs2/agent/permissions"

    async def test_check_permission_with_target(self):
        """Test check_agent_permission with target specified."""
        with patch.object(OPAAdapter, "call", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = AdapterResult(
                success=True,
                data=OPAResponse(allow=True),
            )

            await check_agent_permission(
                agent_id="agent_001",
                permission="send_message",
                target="agent_002",
            )

            request = mock_call.call_args[0][0]
            assert request.input["target"] == "agent_002"

    async def test_check_permission_with_adapter(self):
        """Test check_agent_permission with provided adapter."""
        mock_adapter = MagicMock(spec=OPAAdapter)
        mock_adapter.call = AsyncMock(
            return_value=AdapterResult(
                success=True,
                data=OPAResponse(allow=False),
            )
        )

        await check_agent_permission(
            agent_id="agent_003",
            permission="admin_access",
            adapter=mock_adapter,
        )

        mock_adapter.call.assert_called_once()


class TestEvaluateMaciRole:
    """Tests for evaluate_maci_role function."""

    async def test_evaluate_maci_role_basic(self):
        """Test evaluate_maci_role basic functionality."""
        with patch.object(OPAAdapter, "call", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = AdapterResult(
                success=True,
                data=OPAResponse(allow=True),
            )

            result = await evaluate_maci_role(
                agent_role="executive",
                action="propose",
            )

            request = mock_call.call_args[0][0]
            assert request.input["agent_role"] == "executive"
            assert request.input["action"] == "propose"
            assert request.input["target_role"] is None
            assert request.policy_path == "acgs2/maci/role_separation"
            assert request.explain is True  # Always explain role decisions

    async def test_evaluate_maci_role_with_target(self):
        """Test evaluate_maci_role with target role."""
        with patch.object(OPAAdapter, "call", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = AdapterResult(
                success=True,
                data=OPAResponse(allow=False),
            )

            await evaluate_maci_role(
                agent_role="legislative",
                action="validate",
                target_role="judicial",
            )

            request = mock_call.call_args[0][0]
            assert request.input["target_role"] == "judicial"

    async def test_evaluate_maci_role_with_adapter(self):
        """Test evaluate_maci_role with provided adapter."""
        mock_adapter = MagicMock(spec=OPAAdapter)
        mock_adapter.call = AsyncMock(
            return_value=AdapterResult(
                success=True,
                data=OPAResponse(allow=True),
            )
        )

        await evaluate_maci_role(
            agent_role="judicial",
            action="extract_rules",
            adapter=mock_adapter,
        )

        mock_adapter.call.assert_called_once()


# =============================================================================
# Integration Tests
# =============================================================================


class TestOPAAdapterIntegration:
    """Integration tests for OPAAdapter."""

    async def test_full_workflow_simulated(self, opa_adapter, opa_request):
        """Test full workflow with simulated OPA (no aiohttp)."""
        opa_adapter._http_client = None

        async def mock_get_client():
            return None

        opa_adapter._get_http_client = mock_get_client

        # Execute should use simulated response
        response = await opa_adapter._execute(opa_request)

        # Validate the response
        assert opa_adapter._validate_response(response) is True

        # Get cache key
        cache_key = opa_adapter._get_cache_key(opa_request)
        assert cache_key is not None

        # Close adapter
        await opa_adapter.close()

    async def test_fail_closed_security_model(self, opa_adapter, opa_request):
        """Test that fail-closed model denies on all failures."""
        opa_adapter.opa_config.fail_closed = True

        # Simulate response should deny
        sim_response = opa_adapter._simulate_opa_response(opa_request)
        assert sim_response.allow is False

        # Fallback response should deny
        fallback = opa_adapter._get_fallback_response(opa_request)
        assert fallback.allow is False

    async def test_fail_open_security_model(self, opa_adapter, opa_request):
        """Test fail-open model (not recommended for production)."""
        opa_adapter.opa_config.fail_closed = False

        # Simulate response should allow
        sim_response = opa_adapter._simulate_opa_response(opa_request)
        assert sim_response.allow is True

        # Fallback response should be None
        fallback = opa_adapter._get_fallback_response(opa_request)
        assert fallback is None


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestOPAAdapterEdgeCases:
    """Edge case tests for OPAAdapter."""

    def test_parse_response_nested_dict(self, opa_adapter, opa_request):
        """Test parsing deeply nested OPA response."""
        data = {"result": {"allow": True, "nested": {"deep": {"value": "test"}}}}

        response = opa_adapter._parse_opa_response(data, opa_request)
        assert response.allow is True

    def test_cache_key_with_complex_input(self, opa_adapter):
        """Test cache key generation with complex nested input."""
        request = OPARequest(
            input={
                "nested": {"a": 1, "b": [1, 2, 3]},
                "list": [{"x": 1}, {"y": 2}],
                "null": None,
            }
        )

        key = opa_adapter._get_cache_key(request)
        assert len(key) == 64

    def test_request_with_empty_input(self):
        """Test OPARequest with empty input dict."""
        request = OPARequest(input={})

        assert request.input == {}
        assert request.trace_id is not None

    def test_response_with_none_values(self, opa_adapter, opa_request):
        """Test parsing response with None values."""
        data = {
            "result": None,
            "explanation": None,
            "metrics": None,
        }

        response = opa_adapter._parse_opa_response(data, opa_request)
        assert response.allow is False  # None treated as False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
