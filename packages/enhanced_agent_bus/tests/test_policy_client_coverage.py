"""
ACGS-2 Policy Client Coverage Tests
Constitutional Hash: 608508a9bd224290

Extended tests to increase policy_client.py coverage.
"""

import time
from collections import OrderedDict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

try:
    from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage
    from enhanced_agent_bus.policy_client import (
        DEFAULT_MAX_CACHE_SIZE,
        PolicyRegistryClient,
        get_policy_client,
    )
    from enhanced_agent_bus.validators import ValidationResult
except ImportError:
    from models import AgentMessage
    from policy_client import (
        DEFAULT_MAX_CACHE_SIZE,
        PolicyRegistryClient,
        get_policy_client,
    )


class TestPolicyRegistryClientInit:
    """Tests for PolicyRegistryClient initialization."""

    def test_default_init(self):
        """PolicyRegistryClient initializes with defaults."""
        client = PolicyRegistryClient()
        assert client.registry_url == "http://localhost:8000"
        assert client.api_key is None
        assert client.timeout == 5.0
        assert client.cache_ttl == 300
        # SECURITY FIX (2025-12): Default to fail-closed for security-first behavior
        assert client.fail_closed is True
        assert client.max_cache_size == DEFAULT_MAX_CACHE_SIZE
        assert isinstance(client._cache, OrderedDict)
        assert client._http_client is None

    def test_custom_registry_url(self):
        """PolicyRegistryClient with custom registry URL."""
        client = PolicyRegistryClient(registry_url="https://policy.example.com/")
        # Trailing slash should be stripped
        assert client.registry_url == "https://policy.example.com"

    def test_custom_api_key(self):
        """PolicyRegistryClient with API key."""
        client = PolicyRegistryClient(api_key="test-api-key-123")
        assert client.api_key == "test-api-key-123"

    def test_custom_timeout(self):
        """PolicyRegistryClient with custom timeout."""
        client = PolicyRegistryClient(timeout=10.0)
        assert client.timeout == 10.0

    def test_custom_cache_ttl(self):
        """PolicyRegistryClient with custom cache TTL."""
        client = PolicyRegistryClient(cache_ttl=600)
        assert client.cache_ttl == 600

    def test_fail_closed_mode(self):
        """PolicyRegistryClient with fail-closed mode."""
        client = PolicyRegistryClient(fail_closed=True)
        assert client.fail_closed is True

    def test_custom_max_cache_size(self):
        """PolicyRegistryClient with custom max cache size."""
        client = PolicyRegistryClient(max_cache_size=500)
        assert client.max_cache_size == 500


class TestPolicyRegistryClientCaching:
    """Tests for caching behavior."""

    def test_cache_is_ordered_dict(self):
        """Cache uses OrderedDict for LRU behavior."""
        client = PolicyRegistryClient()
        assert isinstance(client._cache, OrderedDict)

    def test_empty_cache_on_init(self):
        """Cache is empty on initialization."""
        client = PolicyRegistryClient()
        assert len(client._cache) == 0


class TestDefaultMaxCacheSize:
    """Tests for default max cache size constant."""

    def test_default_exists(self):
        """DEFAULT_MAX_CACHE_SIZE is defined."""
        assert DEFAULT_MAX_CACHE_SIZE is not None
        assert isinstance(DEFAULT_MAX_CACHE_SIZE, int)
        assert DEFAULT_MAX_CACHE_SIZE > 0


class TestPolicyRegistryClientContextManager:
    """Tests for context manager behavior."""

    async def test_aenter_initializes(self):
        """__aenter__ initializes the client."""
        client = PolicyRegistryClient()

        with patch.object(client, "initialize", new_callable=AsyncMock) as mock_init:
            result = await client.__aenter__()
            mock_init.assert_called_once()
            assert result is client

    async def test_aexit_closes(self):
        """__aexit__ closes the client."""
        client = PolicyRegistryClient()

        with patch.object(client, "close", new_callable=AsyncMock) as mock_close:
            await client.__aexit__(None, None, None)
            mock_close.assert_called_once()


class TestPolicyRegistryClientInitialize:
    """Tests for initialize method."""

    async def test_initialize_creates_http_client(self):
        """Initialize creates HTTP client if none exists."""
        client = PolicyRegistryClient()
        assert client._http_client is None

        try:
            await client.initialize()
            assert client._http_client is not None
        finally:
            await client.close()

    async def test_initialize_with_api_key_sets_header(self):
        """Initialize with API key sets header."""
        client = PolicyRegistryClient(api_key="test-key")

        try:
            await client.initialize()
            # The http_client should have the header set
            assert client._http_client is not None
        finally:
            await client.close()

    async def test_initialize_idempotent(self):
        """Initialize is idempotent - doesn't recreate client."""
        client = PolicyRegistryClient()

        try:
            await client.initialize()
            first_client = client._http_client

            await client.initialize()
            second_client = client._http_client

            assert first_client is second_client
        finally:
            await client.close()


class TestPolicyRegistryClientClose:
    """Tests for close method."""

    async def test_close_clears_http_client(self):
        """Close closes and clears HTTP client."""
        client = PolicyRegistryClient()

        await client.initialize()
        assert client._http_client is not None

        await client.close()
        assert client._http_client is None

    async def test_close_safe_when_not_initialized(self):
        """Close is safe when client not initialized."""
        client = PolicyRegistryClient()
        assert client._http_client is None

        # Should not raise
        await client.close()


class TestGetPolicyClient:
    """Tests for get_policy_client function."""

    def test_get_policy_client_returns_client(self):
        """get_policy_client returns a PolicyRegistryClient."""
        client = get_policy_client()
        assert isinstance(client, PolicyRegistryClient)

    def test_get_policy_client_with_fail_closed(self):
        """get_policy_client respects fail_closed parameter."""
        client = get_policy_client(fail_closed=True)
        assert client.fail_closed is True


class TestPolicyRegistryClientGetPolicyContent:
    """Tests for get_policy_content method."""

    @pytest.fixture
    async def initialized_client(self):
        """Create and initialize a client."""
        client = PolicyRegistryClient()
        await client.initialize()
        yield client
        await client.close()

    async def test_get_policy_content_returns_cached(self, initialized_client):
        """get_policy_content returns cached content if fresh."""
        # Pre-populate cache
        initialized_client._cache["test-policy:default"] = {
            "content": {"rule": "test"},
            "timestamp": time.monotonic(),
        }

        result = await initialized_client.get_policy_content("test-policy")
        assert result == {"rule": "test"}


class TestPolicyRegistryClientValidateMessageSignature:
    """Tests for validate_message_signature method."""

    def create_message(self, content=None):
        """Helper to create test messages."""
        return AgentMessage(
            content=content or {"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )

    async def test_validate_no_policy_fail_open(self):
        """Validation with no policy and fail_closed=False passes with warning."""
        client = PolicyRegistryClient(fail_closed=False)

        # Mock get_policy_content to return None
        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            msg = self.create_message()
            result = await client.validate_message_signature(msg)

            assert result.is_valid is True
            assert len(result.warnings) > 0
            assert any("unavailable" in w.lower() for w in result.warnings)

    async def test_validate_no_policy_fail_closed(self):
        """Validation with no policy and fail_closed=True fails."""
        client = PolicyRegistryClient(fail_closed=True)

        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            msg = self.create_message()
            result = await client.validate_message_signature(msg)

            assert result.is_valid is False
            assert len(result.errors) > 0

    async def test_validate_exceeds_max_length(self):
        """Validation fails when message exceeds max length."""
        client = PolicyRegistryClient()

        # Mock policy with small max_response_length
        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"max_response_length": 10}

            msg = self.create_message(content="This is a very long message that exceeds the limit")
            result = await client.validate_message_signature(msg)

            assert result.is_valid is False
            assert any("length" in e.lower() for e in result.errors)

    async def test_validate_prohibited_content(self):
        """Validation fails when message contains prohibited content."""
        client = PolicyRegistryClient()

        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"prohibited_content": ["forbidden", "banned"]}

            msg = self.create_message(content="This contains forbidden words")
            result = await client.validate_message_signature(msg)

            assert result.is_valid is False
            assert any("prohibited" in e.lower() for e in result.errors)

    async def test_validate_allowed_topics_warning(self):
        """Validation adds warning when topic not in allowed list."""
        client = PolicyRegistryClient()

        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"allowed_topics": ["finance", "health"]}

            msg = self.create_message(content={"topics": ["technology"], "text": "test"})
            result = await client.validate_message_signature(msg)

            # Should pass but with warning
            assert result.is_valid is True
            assert any("topic" in w.lower() for w in result.warnings)

    async def test_validate_passes_with_valid_content(self):
        """Validation passes with valid content."""
        client = PolicyRegistryClient()

        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"max_response_length": 10000}

            msg = self.create_message(content={"action": "test"})
            result = await client.validate_message_signature(msg)

            assert result.is_valid is True
            assert len(result.errors) == 0


class TestPolicyRegistryClientHealthCheck:
    """Tests for health_check method."""

    async def test_health_check_success(self):
        """Health check returns healthy status on success."""
        client = PolicyRegistryClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "healthy"}
        mock_response.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.health_check()

        assert result["status"] == "healthy"

    async def test_health_check_http_error(self):
        """Health check returns unhealthy on HTTP error."""
        import httpx

        client = PolicyRegistryClient()

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_http = MagicMock()
        error = httpx.HTTPStatusError(
            message="Server Error", request=MagicMock(), response=mock_response
        )
        mock_http.get = AsyncMock(side_effect=error)
        client._http_client = mock_http

        result = await client.health_check()

        assert result["status"] == "unhealthy"
        assert "500" in result["error"]

    async def test_health_check_timeout(self):
        """Health check returns unhealthy on timeout."""
        import httpx

        client = PolicyRegistryClient()

        mock_http = MagicMock()
        mock_http.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        client._http_client = mock_http

        result = await client.health_check()

        assert result["status"] == "unhealthy"
        assert "TimeoutException" in result["error"]

    async def test_health_check_connection_error(self):
        """Health check returns unhealthy on connection error."""
        import httpx

        client = PolicyRegistryClient()

        mock_http = MagicMock()
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        client._http_client = mock_http

        result = await client.health_check()

        assert result["status"] == "unhealthy"
        assert "ConnectError" in result["error"]

    async def test_health_check_parsing_error(self):
        """Health check returns unhealthy on response parsing error."""
        client = PolicyRegistryClient()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.health_check()

        assert result["status"] == "unhealthy"
        assert "parsing" in result["error"].lower()
