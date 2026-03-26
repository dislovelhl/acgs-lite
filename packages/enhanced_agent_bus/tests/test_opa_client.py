"""
ACGS-2 Enhanced Agent Bus - OPA Client Tests
Constitutional Hash: 608508a9bd224290

Tests for OPA client integration.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]
RUN_EAB_OPA_CLIENT_TESTS = os.getenv("RUN_EAB_OPA_CLIENT_TESTS", "false").lower() == "true"
if not RUN_EAB_OPA_CLIENT_TESTS:
    pytestmark.append(
        pytest.mark.skip(
            reason=(
                "OPA client tests disabled by default in this runtime. "
                "Set RUN_EAB_OPA_CLIENT_TESTS=true to run."
            )
        )
    )

from enhanced_agent_bus.models import CONSTITUTIONAL_HASH

# Use package-relative imports to maintain class identity
from enhanced_agent_bus.opa_client import (
    OPAClient,
    close_opa_client,
    get_opa_client,
    initialize_opa_client,
)
from enhanced_agent_bus.validators import ValidationResult


class TestOPAClient:
    """Test suite for OPAClient."""

    @pytest.fixture
    async def opa_client(self):
        """Create OPA client for testing."""
        client = OPAClient(
            opa_url="http://localhost:8181",
            mode="fallback",  # Use fallback mode for testing
            enable_cache=True,
            timeout=5.0,
        )
        await client.initialize()
        yield client
        await client.close()

    @pytest.fixture
    async def http_opa_client(self):
        """Create HTTP mode OPA client with mocked HTTP."""
        client = OPAClient(
            opa_url="http://localhost:8181",
            mode="http",
            enable_cache=False,  # Disable cache for testing
            timeout=5.0,
        )
        await client.initialize()
        yield client
        await client.close()

    async def test_initialization(self, opa_client):
        """Test OPA client initialization."""
        assert opa_client is not None
        assert opa_client.mode == "fallback"
        assert opa_client.enable_cache is True

    async def test_context_manager(self):
        """Test OPA client as context manager."""
        async with OPAClient(mode="fallback") as client:
            assert client is not None
            assert client._http_client is not None

    async def test_evaluate_policy_fallback(self, opa_client):
        """Test policy evaluation in fallback mode.

        SECURITY: Fallback mode implements FAIL-CLOSED principle.
        When OPA is unavailable, requests are DENIED to prevent bypass.
        """
        input_data = {
            "agent_id": "test_agent",
            "action": "read",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        result = await opa_client.evaluate_policy(input_data, policy_path="data.acgs.allow")

        assert result is not None
        assert "result" in result
        assert "allowed" in result
        # FAIL-CLOSED: Denied when OPA unavailable
        assert result["allowed"] is False
        assert result["metadata"]["mode"] == "fallback"
        assert result["metadata"]["security"] == "fail-closed"

    async def test_evaluate_policy_invalid_hash(self, opa_client):
        """Test policy evaluation with invalid constitutional hash."""
        input_data = {
            "agent_id": "test_agent",
            "action": "read",
            "constitutional_hash": "invalid_hash",
        }

        result = await opa_client.evaluate_policy(input_data, policy_path="data.acgs.allow")

        assert result is not None
        assert result["allowed"] is False
        assert "Invalid constitutional hash" in result["reason"]

    async def test_validate_constitutional_valid(self, opa_client):
        """Test constitutional validation with valid message.

        SECURITY: Fallback mode implements FAIL-CLOSED principle.
        Even with valid constitutional hash, requests are DENIED when OPA unavailable.
        """
        message = {
            "message_id": "test_123",
            "from_agent": "agent_1",
            "to_agent": "agent_2",
            "content": {"action": "test"},
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        result = await opa_client.validate_constitutional(message)

        # Check type by name (handles module path differences in tests)
        assert type(result).__name__ == "ValidationResult"
        # FAIL-CLOSED: Invalid when OPA unavailable
        assert result.is_valid is False
        assert result.constitutional_hash == CONSTITUTIONAL_HASH
        assert len(result.errors) > 0
        assert (
            "fail-closed" in result.errors[0].lower() or "unavailable" in result.errors[0].lower()
        )

    async def test_validate_constitutional_invalid(self, opa_client):
        """Test constitutional validation with invalid hash."""
        message = {
            "message_id": "test_123",
            "from_agent": "agent_1",
            "to_agent": "agent_2",
            "content": {"action": "test"},
            "constitutional_hash": "invalid_hash",
        }

        result = await opa_client.validate_constitutional(message)

        # Check type by name (handles module path differences in tests)
        assert type(result).__name__ == "ValidationResult"
        assert result.is_valid is False
        assert len(result.errors) > 0

    async def test_check_agent_authorization(self, opa_client):
        """Test agent authorization check.

        SECURITY: Fallback mode implements FAIL-CLOSED principle.
        Authorization is DENIED when OPA is unavailable.
        """
        authorized = await opa_client.check_agent_authorization(
            agent_id="test_agent",
            action="read",
            resource="test_resource",
            context={"constitutional_hash": CONSTITUTIONAL_HASH},
        )

        # FAIL-CLOSED: Denied when OPA unavailable
        assert authorized is False

    async def test_check_agent_authorization_denied(self, opa_client):
        """Test agent authorization denial."""
        authorized = await opa_client.check_agent_authorization(
            agent_id="test_agent",
            action="read",
            resource="test_resource",
            context={"constitutional_hash": "invalid_hash"},
        )

        # Invalid hash should deny authorization
        assert authorized is False

    async def test_cache_functionality(self):
        """Test caching of policy results.

        SECURITY: Fallback mode implements FAIL-CLOSED principle.
        Both cached and non-cached results deny when OPA unavailable.
        """
        client = OPAClient(mode="fallback", enable_cache=True)
        await client.initialize()

        input_data = {"agent_id": "test_agent", "constitutional_hash": CONSTITUTIONAL_HASH}

        # First call - cache miss, FAIL-CLOSED
        result1 = await client.evaluate_policy(input_data, "data.acgs.allow")
        assert result1["allowed"] is False  # FAIL-CLOSED

        # Second call - should hit cache, still FAIL-CLOSED
        result2 = await client.evaluate_policy(input_data, "data.acgs.allow")
        assert result2["allowed"] is False  # FAIL-CLOSED
        assert result1 == result2

        await client.close()

    async def test_health_check(self, opa_client):
        """Test health check."""
        health = await opa_client.health_check()

        assert health is not None
        assert "status" in health
        assert "mode" in health
        assert health["mode"] == "fallback"

    async def test_get_stats(self, opa_client):
        """Test statistics retrieval."""
        stats = opa_client.get_stats()

        assert stats is not None
        assert "mode" in stats
        assert "cache_enabled" in stats
        assert stats["mode"] == "fallback"
        assert stats["cache_enabled"] is True

    async def test_http_mode_with_mock(self, http_opa_client):
        """Test HTTP mode with mocked responses."""
        # Mock the HTTP client - use MagicMock for response since .json() is sync
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"allow": True, "reason": "Policy allows action"}
        }
        mock_response.raise_for_status = MagicMock()

        http_opa_client._http_client.post = AsyncMock(return_value=mock_response)

        input_data = {"agent_id": "test_agent", "constitutional_hash": CONSTITUTIONAL_HASH}

        result = await http_opa_client.evaluate_policy(input_data, policy_path="data.acgs.allow")

        assert result["allowed"] is True
        assert result["metadata"]["mode"] == "http"

    async def test_load_policy(self, http_opa_client):
        """Test policy loading."""
        # Mock the HTTP client
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()

        http_opa_client._http_client.put = AsyncMock(return_value=mock_response)

        policy_content = """
        package acgs

        default allow = false

        allow {
            input.constitutional_hash == CONSTITUTIONAL_HASH
        }
        """

        success = await http_opa_client.load_policy("test_policy", policy_content)

        assert success is True

    async def test_global_client_singleton(self):
        """Test global client singleton pattern."""
        client1 = get_opa_client()
        client2 = get_opa_client()

        assert client1 is client2

        await close_opa_client()

    async def test_initialize_global_client(self):
        """Test global client initialization."""
        client = await initialize_opa_client(opa_url="http://localhost:8181", mode="fallback")

        assert client is not None
        assert client.mode == "fallback"

        await close_opa_client()

    async def test_error_handling_network_failure(self, http_opa_client):
        """Test error handling for network failures."""
        # Mock network failure
        http_opa_client._http_client.post = AsyncMock(
            side_effect=httpx.ConnectError("Network error")
        )

        input_data = {"agent_id": "test_agent", "constitutional_hash": CONSTITUTIONAL_HASH}

        result = await http_opa_client.evaluate_policy(input_data, policy_path="data.acgs.allow")

        # Should return error result
        assert result["allowed"] is False
        assert "error" in result["metadata"]

    async def test_cache_key_generation(self, opa_client):
        """Test cache key generation."""
        input_data1 = {"agent_id": "test", "action": "read"}
        input_data2 = {"action": "read", "agent_id": "test"}  # Same data, different order

        key1 = opa_client._generate_cache_key("data.acgs.allow", input_data1)
        key2 = opa_client._generate_cache_key("data.acgs.allow", input_data2)

        # Keys should be identical for same data regardless of order
        assert key1 == key2

        # Different data should produce different keys
        input_data3 = {"agent_id": "test", "action": "write"}
        key3 = opa_client._generate_cache_key("data.acgs.allow", input_data3)
        assert key1 != key3

    async def test_cache_expiration(self):
        """Test cache expiration."""
        client = OPAClient(mode="fallback", enable_cache=True, cache_ttl=1)
        await client.initialize()

        input_data = {"agent_id": "test_agent", "constitutional_hash": CONSTITUTIONAL_HASH}

        # First call
        result1 = await client.evaluate_policy(input_data, "data.acgs.allow")

        # Wait for cache to expire
        await asyncio.sleep(1.5)

        # Should re-evaluate (not from cache)
        result2 = await client.evaluate_policy(input_data, "data.acgs.allow")

        assert result1["allowed"] == result2["allowed"]

        await client.close()

    async def test_authorization_with_context(self, opa_client):
        """Test authorization with additional context.

        SECURITY: Fallback mode implements FAIL-CLOSED principle.
        Authorization is DENIED when OPA is unavailable, regardless of context.
        """
        context = {
            "user_role": "admin",
            "tenant_id": "tenant_123",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        authorized = await opa_client.check_agent_authorization(
            agent_id="admin_agent", action="write", resource="sensitive_resource", context=context
        )

        # FAIL-CLOSED: Denied when OPA unavailable
        assert authorized is False

    async def test_multiple_concurrent_evaluations(self, opa_client):
        """Test concurrent policy evaluations."""
        input_data = {"agent_id": "test_agent", "constitutional_hash": CONSTITUTIONAL_HASH}

        # Run multiple evaluations concurrently
        tasks = [opa_client.evaluate_policy(input_data, f"data.acgs.policy_{i}") for i in range(10)]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 10
        for result in results:
            assert "allowed" in result


class TestOPAClientEdgeCases:
    """Test edge cases and error conditions."""

    async def test_empty_input_data(self):
        """Test with empty input data."""
        async with OPAClient(mode="fallback") as client:
            result = await client.evaluate_policy({}, "data.acgs.allow")
            # Should handle gracefully
            assert result is not None

    async def test_invalid_policy_path(self):
        """Test with invalid policy path."""
        async with OPAClient(mode="fallback") as client:
            input_data = {"constitutional_hash": CONSTITUTIONAL_HASH}
            result = await client.evaluate_policy(input_data, "invalid..path")
            # Should still return a result
            assert result is not None

    async def test_large_input_data(self):
        """Test with large input data."""
        async with OPAClient(mode="fallback") as client:
            # Create large input
            large_input = {
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "data": ["item" + str(i) for i in range(1000)],
            }
            result = await client.evaluate_policy(large_input, "data.acgs.allow")
            assert result is not None

    async def test_special_characters_in_input(self):
        """Test with special characters in input."""
        async with OPAClient(mode="fallback") as client:
            input_data = {"agent_id": "agent<>\"'&123", "constitutional_hash": CONSTITUTIONAL_HASH}
            result = await client.evaluate_policy(input_data, "data.acgs.allow")
            assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
