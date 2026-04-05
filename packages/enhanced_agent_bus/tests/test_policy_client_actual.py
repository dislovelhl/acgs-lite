"""
ACGS-2 Enhanced Agent Bus - Actual Policy Client Tests
Constitutional Hash: 608508a9bd224290

Tests that exercise the actual policy_client.py module.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

# Add parent directory to path for local imports
_parent_dir = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, _parent_dir)

# Import models directly first
from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

# Now load policy_client with mocked relative imports
_policy_client_path = os.path.join(_parent_dir, "policy_client.py")


# Create a mock settings object
class MockSecretStr:
    """Mock Pydantic SecretStr."""

    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


class MockSecuritySettings:
    """Mock security settings."""

    rate_limit_requests = 100
    rate_limit_window = 60
    api_key_internal = MockSecretStr("test-internal-api-key")


class MockServicesSettings:
    """Mock services settings."""

    policy_registry_url = "http://localhost:8003"


class MockSettings:
    """Mock settings for testing."""

    POLICY_REGISTRY_URL = "http://localhost:8003"
    POLICY_REGISTRY_API_KEY = "test-api-key"
    POLICY_CACHE_TTL = 300
    security = MockSecuritySettings()
    services = MockServicesSettings()


_mock_settings = MockSettings()

# SECURITY FIX: Replace exec() with safer importlib-based module loading
# This eliminates the security risk (CWE-94: Improper Control of Code Generation)
# while maintaining the same testing functionality

# Temporarily inject mock settings into sys.modules to intercept the import
original_settings = sys.modules.get("shared.config")
mock_config_module = type(sys)("shared.config")
mock_config_module.settings = _mock_settings
sys.modules["shared.config"] = mock_config_module

# Also handle the fallback import path
sys.modules["...shared.config"] = mock_config_module

try:
    # Use importlib to safely load the module
    import importlib.util

    spec = importlib.util.spec_from_file_location("policy_client", _policy_client_path)
    _policy_module = importlib.util.module_from_spec(spec)

    # Pre-populate the module's namespace with our mocks
    _policy_module.settings = _mock_settings

    # Execute the module using the proper importlib mechanism
    spec.loader.exec_module(_policy_module)

    # Extract classes/functions from the loaded module
    PolicyRegistryClient = _policy_module.PolicyRegistryClient
    get_policy_client = _policy_module.get_policy_client
    initialize_policy_client = _policy_module.initialize_policy_client
    close_policy_client = _policy_module.close_policy_client

finally:
    # Always restore original modules
    if original_settings is not None:
        sys.modules["shared.config"] = original_settings
    else:
        sys.modules.pop("shared.config", None)
    sys.modules.pop("...shared.config", None)


# ============================================================================
# PolicyRegistryClient Tests
# ============================================================================


class TestPolicyRegistryClientActual:
    """Test actual PolicyRegistryClient class."""

    def test_init_defaults(self):
        """Test default initialization."""
        client = PolicyRegistryClient()
        assert client.registry_url == "http://localhost:8000"
        assert client.timeout == 5.0
        assert client.cache_ttl == 300
        # SECURITY FIX (2025-12): Default to fail-closed for security-first behavior
        assert client.fail_closed is True
        assert client._cache == {}
        assert client._http_client is None

    def test_init_custom(self):
        """Test custom initialization."""
        client = PolicyRegistryClient(
            registry_url="http://custom:9000/",
            timeout=10.0,
            cache_ttl=600,
            fail_closed=True,
        )
        assert client.registry_url == "http://custom:9000"
        assert client.timeout == 10.0
        assert client.cache_ttl == 600
        assert client.fail_closed is True

    def test_url_strips_trailing_slash(self):
        """Test URL trailing slash is stripped."""
        client = PolicyRegistryClient(registry_url="http://test.com/api/")
        assert not client.registry_url.endswith("/")

    async def test_aenter_initializes(self):
        """Test context manager calls initialize."""
        client = PolicyRegistryClient()
        with patch.object(client, "initialize", new_callable=AsyncMock) as mock_init:
            with patch.object(client, "close", new_callable=AsyncMock):
                result = await client.__aenter__()
                mock_init.assert_called_once()
                assert result is client

    async def test_aexit_closes(self):
        """Test context manager calls close."""
        client = PolicyRegistryClient()
        with patch.object(client, "close", new_callable=AsyncMock) as mock_close:
            await client.__aexit__(None, None, None)
            mock_close.assert_called_once()

    async def test_initialize_creates_client(self):
        """Test initialize creates HTTP client."""
        client = PolicyRegistryClient()
        await client.initialize()
        assert client._http_client is not None
        await client.close()

    async def test_initialize_idempotent(self):
        """Test multiple initializes keep same client."""
        client = PolicyRegistryClient()
        await client.initialize()
        first = client._http_client
        await client.initialize()
        assert client._http_client is first
        await client.close()

    async def test_close_clears_client(self):
        """Test close clears HTTP client."""
        client = PolicyRegistryClient()
        await client.initialize()
        assert client._http_client is not None
        await client.close()
        assert client._http_client is None

    async def test_close_safe_when_none(self):
        """Test close is safe when no client."""
        client = PolicyRegistryClient()
        await client.close()  # Should not raise
        assert client._http_client is None


class TestGetPolicyContentActual:
    """Test get_policy_content with mocked HTTP."""

    @pytest.fixture
    def client(self):
        """Create client with mocked HTTP."""
        client = PolicyRegistryClient()
        client._http_client = AsyncMock()
        return client

    async def test_success(self, client):
        """Test successful policy fetch."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"rule": "value"}
        mock_resp.raise_for_status = MagicMock()
        client._http_client.get = AsyncMock(return_value=mock_resp)

        result = await client.get_policy_content("test_policy")
        assert result == {"rule": "value"}

    async def test_with_client_id(self, client):
        """Test fetch with client_id parameter."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"variant": "B"}
        mock_resp.raise_for_status = MagicMock()
        client._http_client.get = AsyncMock(return_value=mock_resp)

        result = await client.get_policy_content("policy", client_id="abc123")
        assert result == {"variant": "B"}
        call_args = client._http_client.get.call_args
        assert call_args[1]["params"] == {"client_id": "abc123"}

    async def test_404_returns_none(self, client):
        """Test 404 returns None."""
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        error = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_resp)
        client._http_client.get = AsyncMock(side_effect=error)

        result = await client.get_policy_content("missing")
        assert result is None

    async def test_timeout_raises(self, client):
        """Test timeout exception is raised."""
        import httpx

        client._http_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        with pytest.raises(httpx.TimeoutException):
            await client.get_policy_content("policy")

    async def test_connect_error_raises(self, client):
        """Test connection error is raised."""
        import httpx

        client._http_client.get = AsyncMock(side_effect=httpx.ConnectError("Failed"))

        with pytest.raises(httpx.ConnectError):
            await client.get_policy_content("policy")


class TestValidateMessageActual:
    """Test validate_message_signature with actual module."""

    @pytest.fixture
    def client(self):
        """Create client."""
        return PolicyRegistryClient()

    @pytest.fixture
    def message(self):
        """Create test message."""
        return AgentMessage(
            message_type=MessageType.TASK_REQUEST,
            content={"action": "test", "topics": ["general"]},
            from_agent="sender",
            to_agent="receiver",
            priority=Priority.NORMAL,
        )

    async def test_no_policy_fails_closed_by_default(self, client, message):
        """Test no policy fails closed by default (SECURITY FIX 2025-12).

        When policy registry is unavailable or policy not found, validation
        must fail (fail-closed) to prevent bypass attacks.
        """
        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            result = await client.validate_message_signature(message)
            # SECURITY: Default fail-closed behavior - policy unavailable = DENY
            assert result.is_valid is False
            assert any(
                "unavailable" in e.lower() or "not found" in e.lower() for e in result.errors
            )

    async def test_no_policy_with_fail_open_returns_warning(self, message):
        """Test no policy with explicit fail_closed=False returns warning."""
        # Explicit fail-open for legacy/testing scenarios only
        fail_open_client = PolicyRegistryClient(fail_closed=False)
        await fail_open_client.initialize()
        try:
            with patch.object(
                fail_open_client, "get_policy_content", new_callable=AsyncMock
            ) as mock_get:
                mock_get.return_value = None
                result = await fail_open_client.validate_message_signature(message)
                assert result.is_valid is True
                assert any("unavailable" in w.lower() for w in result.warnings)
        finally:
            await fail_open_client.close()

    async def test_valid_content_passes(self, client, message):
        """Test valid content passes."""
        policy = {
            "max_response_length": 10000,
            "allowed_topics": ["general"],
            "prohibited_content": [],
        }
        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = policy
            result = await client.validate_message_signature(message)
            assert result.is_valid is True

    async def test_exceeds_length_fails(self, client):
        """Test message exceeding max length fails."""
        message = AgentMessage(
            message_type=MessageType.TASK_REQUEST,
            content={"data": "x" * 500},
            from_agent="sender",
            to_agent="receiver",
        )
        policy = {"max_response_length": 100, "prohibited_content": []}
        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = policy
            result = await client.validate_message_signature(message)
            assert result.is_valid is False
            assert any("exceeds" in e.lower() or "maximum" in e.lower() for e in result.errors)

    async def test_prohibited_content_fails(self, client):
        """Test prohibited content fails."""
        message = AgentMessage(
            message_type=MessageType.TASK_REQUEST,
            content={"text": "contains FORBIDDEN word"},
            from_agent="sender",
            to_agent="receiver",
        )
        policy = {"max_response_length": 10000, "prohibited_content": ["forbidden"]}
        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = policy
            result = await client.validate_message_signature(message)
            assert result.is_valid is False
            assert any("prohibited" in e.lower() for e in result.errors)

    async def test_topic_warning(self, client):
        """Test topic not in allowed list warns."""
        message = AgentMessage(
            message_type=MessageType.TASK_REQUEST,
            content={"text": "test", "topics": ["unknown"]},
            from_agent="sender",
            to_agent="receiver",
        )
        policy = {
            "max_response_length": 10000,
            "allowed_topics": ["finance", "tech"],
            "prohibited_content": [],
        }
        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = policy
            result = await client.validate_message_signature(message)
            assert result.is_valid is True
            assert any("topic" in w.lower() for w in result.warnings)

    async def test_network_error_fails_closed_by_default(self, client, message):
        """Test network error fails closed by default (SECURITY FIX 2025-12).

        Network errors during validation must result in DENY to prevent
        bypass attacks when policy registry is unreachable.
        """
        import httpx

        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Timeout")
            result = await client.validate_message_signature(message)
            # SECURITY: Default fail-closed behavior - network error = DENY
            assert result.is_valid is False
            assert any("network" in e.lower() for e in result.errors)

    async def test_network_error_with_fail_open_returns_warning(self, message):
        """Test network error with explicit fail_closed=False returns warning."""
        import httpx

        fail_open_client = PolicyRegistryClient(fail_closed=False)
        await fail_open_client.initialize()
        try:
            with patch.object(
                fail_open_client, "get_policy_content", new_callable=AsyncMock
            ) as mock_get:
                mock_get.side_effect = httpx.TimeoutException("Timeout")
                result = await fail_open_client.validate_message_signature(message)
                assert result.is_valid is True
                assert any("network" in w.lower() for w in result.warnings)
        finally:
            await fail_open_client.close()


class TestHealthCheckActual:
    """Test health_check with actual module."""

    @pytest.fixture
    def client(self):
        """Create client with mocked HTTP."""
        client = PolicyRegistryClient()
        client._http_client = AsyncMock()
        return client

    async def test_healthy(self, client):
        """Test healthy response."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "healthy"}
        mock_resp.raise_for_status = MagicMock()
        client._http_client.get = AsyncMock(return_value=mock_resp)

        result = await client.health_check()
        assert result == {"status": "healthy"}

    async def test_http_error(self, client):
        """Test HTTP error returns unhealthy."""
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 503
        error = httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_resp)
        client._http_client.get = AsyncMock(side_effect=error)

        result = await client.health_check()
        assert result["status"] == "unhealthy"

    async def test_timeout(self, client):
        """Test timeout returns unhealthy."""
        import httpx

        client._http_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        result = await client.health_check()
        assert result["status"] == "unhealthy"

    async def test_connect_error(self, client):
        """Test connection error returns unhealthy."""
        import httpx

        client._http_client.get = AsyncMock(side_effect=httpx.ConnectError("Failed"))

        result = await client.health_check()
        assert result["status"] == "unhealthy"


class TestGetPublicKeyActual:
    """Test get_current_public_key with actual module."""

    @pytest.fixture
    def client(self):
        """Create client with mocked HTTP."""
        client = PolicyRegistryClient()
        client._http_client = AsyncMock()
        return client

    async def test_success(self, client):
        """Test successful key fetch."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"current_public_key": "key123"}
        mock_resp.raise_for_status = MagicMock()
        client._http_client.get = AsyncMock(return_value=mock_resp)

        result = await client.get_current_public_key()
        assert result == "key123"

    async def test_error_returns_none(self, client):
        """Test error returns None."""
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        error = httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_resp)
        client._http_client.get = AsyncMock(side_effect=error)

        result = await client.get_current_public_key()
        assert result is None


# ============================================================================
# Global Function Tests
# ============================================================================


class TestGlobalFunctionsActual:
    """Test global policy client functions."""

    def test_get_policy_client_creates_singleton(self):
        """Test get_policy_client returns singleton."""
        _policy_module._policy_client = None

        client1 = get_policy_client()
        client2 = get_policy_client()
        assert client1 is client2

        _policy_module._policy_client = None

    async def test_initialize_policy_client(self):
        """Test initialize_policy_client creates and initializes."""
        _policy_module._policy_client = None

        await initialize_policy_client("http://test:8000")

        assert _policy_module._policy_client is not None
        assert _policy_module._policy_client.registry_url == "http://test:8000"

        await close_policy_client()

    async def test_close_policy_client(self):
        """Test close_policy_client clears global."""
        await initialize_policy_client()

        await close_policy_client()

        assert _policy_module._policy_client is None

    async def test_close_when_none(self):
        """Test close safe when no client."""
        _policy_module._policy_client = None
        await close_policy_client()  # Should not raise
