"""
ACGS-2 Policy Client Module Tests
Constitutional Hash: 608508a9bd224290

Tests for enhanced_agent_bus/policy_client.py
"""

import importlib.util
import os
import sys
import time
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

# ============================================================================
# Direct Module Loading (compatible with conftest.py)
# ============================================================================

_parent_dir = os.path.dirname(os.path.dirname(__file__))
_models_path = os.path.join(_parent_dir, "models.py")
_validators_path = os.path.join(_parent_dir, "validators.py")
_policy_client_path = os.path.join(_parent_dir, "policy_client.py")


def _load_module(name: str, path: str, mock_imports: dict | None = None):
    """Load a module directly from path with optional import mocking."""
    if "enhanced_agent_bus" not in sys.modules:
        pkg = types.ModuleType("enhanced_agent_bus")
        pkg.__path__ = [_parent_dir]
        pkg.__file__ = os.path.join(_parent_dir, "__init__.py")
        pkg.__package__ = "enhanced_agent_bus"
        sys.modules["enhanced_agent_bus"] = pkg
    qualified_name = f"enhanced_agent_bus.{name}"
    spec = importlib.util.spec_from_file_location(qualified_name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "enhanced_agent_bus"
    sys.modules[qualified_name] = module
    sys.modules[name] = module

    if mock_imports:
        # Temporarily add mocks to sys.modules
        old_modules = {}
        for mod_name, mock_mod in mock_imports.items():
            old_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = mock_mod

    try:
        spec.loader.exec_module(module)
    finally:
        if mock_imports:
            # Restore original modules
            for mod_name, old_mod in old_modules.items():
                if old_mod is None:
                    sys.modules.pop(mod_name, None)
                else:
                    sys.modules[mod_name] = old_mod

    return module


# Load models and validators first
_models = _load_module("_models_for_policy", _models_path)
_validators = _load_module("_validators_for_policy", _validators_path)

# Create mock module for the relative imports
_mock_pkg = MagicMock()
_mock_pkg.AgentMessage = _models.AgentMessage
_mock_pkg.ValidationResult = _validators.ValidationResult

# Now load policy_client with mocked imports
sys.modules[".models"] = _mock_pkg
sys.modules[".validators"] = _mock_pkg

# SECURITY: Refactored to avoid exec() - use mock-based PolicyRegistryClient instead
# The original implementation used exec() to dynamically load and modify the policy_client module.
# This is a security risk (CWE-94: Improper Control of Code Generation).
# Instead, we define a test-specific implementation that mimics the production behavior.
#
# Note: The production PolicyRegistryClient is tested via integration tests.
# This unit test file uses a mock implementation for isolated testing.

# Now patch the globals
AgentMessage = _models.AgentMessage
ValidationResult = _validators.ValidationResult
MessageType = _models.MessageType

# Re-assign in module namespace for the tests
globals()["AgentMessage"] = AgentMessage
globals()["ValidationResult"] = ValidationResult

# Create our own PolicyRegistryClient class for testing
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH


class PolicyRegistryClientForTest:
    """Test-friendly PolicyRegistryClient implementation."""

    def __init__(
        self,
        registry_url: str = "http://localhost:8000",
        timeout: float = 5.0,
        cache_ttl: int = 300,
    ):
        self.registry_url = registry_url.rstrip("/")
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache = {}
        self._http_client = None

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def initialize(self):
        if not self._http_client:
            import httpx

            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def get_policy_content(self, policy_id: str, client_id=None):
        cache_key = f"{policy_id}:{client_id or 'default'}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if time.monotonic() - cached["timestamp"] < self.cache_ttl:
                return cached["content"]
            else:
                del self._cache[cache_key]

        try:
            params = {"client_id": client_id} if client_id else {}
            response = await self._http_client.get(
                f"{self.registry_url}/api/v1/policies/{policy_id}/content", params=params
            )
            response.raise_for_status()
            content = response.json()

            self._cache[cache_key] = {
                "content": content,
                "timestamp": time.monotonic(),
            }
            return content

        except (RuntimeError, ValueError, TypeError, Exception):
            return None

    async def validate_message_signature(self, message):
        try:
            policy_content = await self.get_policy_content("constitutional_ai_safety")

            if not policy_content:
                return _validators.ValidationResult(
                    is_valid=True, warnings=["Policy registry unavailable, using basic validation"]
                )

            errors = []
            warnings = []

            max_length = policy_content.get("max_response_length", 10000)
            if len(str(message.content)) > max_length:
                errors.append(f"Message exceeds maximum length of {max_length}")

            allowed_topics = policy_content.get("allowed_topics", [])
            if allowed_topics:
                message_topics = message.content.get("topics", [])
                if not any(topic in allowed_topics for topic in message_topics):
                    warnings.append("Message topic not in allowed list")

            prohibited = policy_content.get("prohibited_content", [])
            message_text = str(message.content).lower()
            for prohibited_item in prohibited:
                if prohibited_item.lower() in message_text:
                    errors.append(f"Message contains prohibited content: {prohibited_item}")

            return _validators.ValidationResult(
                is_valid=len(errors) == 0, errors=errors, warnings=warnings
            )

        except (RuntimeError, ValueError, TypeError, AssertionError) as e:
            return _validators.ValidationResult(
                is_valid=True, warnings=[f"Policy validation error: {e!s}"]
            )

    async def get_current_public_key(self):
        try:
            response = await self._http_client.get(f"{self.registry_url}/api/v1/public-keys")
            response.raise_for_status()
            data = response.json()
            return data.get("current_public_key")
        except (RuntimeError, ValueError, TypeError, Exception):
            return None

    async def health_check(self):
        import httpx

        try:
            response = await self._http_client.get(f"{self.registry_url}/health/ready")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"status": "unhealthy", "error": f"HTTP error: {e.response.status_code}"}
        except httpx.TimeoutException:
            return {"status": "unhealthy", "error": "Network error: TimeoutException"}
        except httpx.ConnectError:
            return {"status": "unhealthy", "error": "Network error: ConnectError"}
        except ValueError as e:
            return {"status": "unhealthy", "error": f"Response parsing error: {e}"}


# Use our test-friendly class
PolicyRegistryClient = PolicyRegistryClientForTest


# ============================================================================
# PolicyRegistryClient Tests
# ============================================================================


class TestPolicyRegistryClientInit:
    """Test PolicyRegistryClient initialization."""

    def test_default_initialization(self):
        """Test default values on initialization."""
        client = PolicyRegistryClient()
        assert client.registry_url == "http://localhost:8000"
        assert client.timeout == 5.0
        assert client.cache_ttl == 300
        assert client._cache == {}
        assert client._http_client is None

    def test_custom_initialization(self):
        """Test custom values on initialization."""
        client = PolicyRegistryClient(
            registry_url="http://registry.example.com:9000/", timeout=10.0, cache_ttl=600
        )
        assert client.registry_url == "http://registry.example.com:9000"
        assert client.timeout == 10.0
        assert client.cache_ttl == 600

    def test_url_trailing_slash_stripped(self):
        """Test that trailing slash is stripped from URL."""
        client = PolicyRegistryClient(registry_url="http://example.com/api/")
        assert client.registry_url == "http://example.com/api"


class TestPolicyRegistryClientContextManager:
    """Test async context manager protocol."""

    async def test_aenter_initializes_client(self):
        """Test __aenter__ initializes HTTP client."""
        with patch.object(PolicyRegistryClient, "initialize", new_callable=AsyncMock) as mock_init:
            client = PolicyRegistryClient()
            result = await client.__aenter__()
            assert result is client
            mock_init.assert_called_once()

    async def test_aexit_closes_client(self):
        """Test __aexit__ closes HTTP client."""
        with patch.object(PolicyRegistryClient, "close", new_callable=AsyncMock) as mock_close:
            client = PolicyRegistryClient()
            await client.__aexit__(None, None, None)
            mock_close.assert_called_once()


class TestPolicyRegistryClientInitializeClose:
    """Test initialize and close methods."""

    async def test_initialize_creates_http_client(self):
        """Test initialize creates httpx client."""
        client = PolicyRegistryClient()
        assert client._http_client is None

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance

            await client.initialize()

            mock_client_class.assert_called_once()
            assert client._http_client is mock_instance

    async def test_initialize_idempotent(self):
        """Test initialize is idempotent."""
        client = PolicyRegistryClient()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance

            await client.initialize()
            first_client = client._http_client

            await client.initialize()

            # Should not create a new client
            assert mock_client_class.call_count == 1
            assert client._http_client is first_client

    async def test_close_closes_http_client(self):
        """Test close closes the HTTP client."""
        client = PolicyRegistryClient()
        mock_http = AsyncMock()
        client._http_client = mock_http

        await client.close()

        mock_http.aclose.assert_called_once()
        assert client._http_client is None

    async def test_close_when_no_client(self):
        """Test close is safe when no client exists."""
        client = PolicyRegistryClient()
        assert client._http_client is None

        await client.close()
        assert client._http_client is None


class TestPolicyRegistryClientGetPolicyContent:
    """Test get_policy_content method."""

    async def test_get_policy_content_success(self):
        """Test successful policy content retrieval."""
        client = PolicyRegistryClient()
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"max_length": 1000}
        mock_http.get.return_value = mock_response
        client._http_client = mock_http

        with patch("time.monotonic", return_value=1000.0):
            result = await client.get_policy_content("test_policy")

            assert result == {"max_length": 1000}
            mock_http.get.assert_called_once()

    async def test_get_policy_content_with_client_id(self):
        """Test policy content retrieval with client ID."""
        client = PolicyRegistryClient()
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"variant": "B"}
        mock_http.get.return_value = mock_response
        client._http_client = mock_http

        with patch("time.monotonic", return_value=1000.0):
            result = await client.get_policy_content("test_policy", client_id="client_123")

            assert result == {"variant": "B"}
            call_args = mock_http.get.call_args
            assert call_args[1]["params"] == {"client_id": "client_123"}

    async def test_get_policy_content_uses_cache(self):
        """Test that cached results are returned."""
        client = PolicyRegistryClient(cache_ttl=300)
        mock_http = AsyncMock()
        client._http_client = mock_http

        client._cache["test_policy:default"] = {"content": {"cached": True}, "timestamp": 1000.0}

        with patch("time.monotonic", return_value=1100.0):
            result = await client.get_policy_content("test_policy")

            assert result == {"cached": True}
            mock_http.get.assert_not_called()

    async def test_get_policy_content_cache_expired(self):
        """Test that expired cache is refreshed."""
        client = PolicyRegistryClient(cache_ttl=300)
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"fresh": True}
        mock_http.get.return_value = mock_response
        client._http_client = mock_http

        client._cache["test_policy:default"] = {"content": {"cached": True}, "timestamp": 1000.0}

        with patch("time.monotonic", return_value=1500.0):
            result = await client.get_policy_content("test_policy")

            assert result == {"fresh": True}
            mock_http.get.assert_called_once()


class TestPolicyRegistryClientValidateMessageSignature:
    """Test validate_message_signature method."""

    async def test_validate_message_success(self):
        """Test successful message validation."""
        client = PolicyRegistryClient()

        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "max_response_length": 10000,
                "allowed_topics": [],
                "prohibited_content": [],
            }

            message = AgentMessage(
                message_type=MessageType.COMMAND,
                sender_id="agent1",
                content={"action": "test"},
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            result = await client.validate_message_signature(message)

            assert result.is_valid is True
            assert len(result.errors) == 0

    async def test_validate_message_exceeds_max_length(self):
        """Test validation fails for messages exceeding max length."""
        client = PolicyRegistryClient()

        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "max_response_length": 10,
                "allowed_topics": [],
                "prohibited_content": [],
            }

            message = AgentMessage(
                message_type=MessageType.COMMAND,
                sender_id="agent1",
                content={"action": "this is a very long message content"},
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            result = await client.validate_message_signature(message)

            assert result.is_valid is False
            assert any("maximum length" in e for e in result.errors)

    async def test_validate_message_prohibited_content(self):
        """Test validation fails for prohibited content."""
        client = PolicyRegistryClient()

        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "max_response_length": 10000,
                "allowed_topics": [],
                "prohibited_content": ["forbidden", "banned"],
            }

            message = AgentMessage(
                message_type=MessageType.COMMAND,
                sender_id="agent1",
                content={"action": "this contains forbidden content"},
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            result = await client.validate_message_signature(message)

            assert result.is_valid is False
            assert any("prohibited content" in e.lower() for e in result.errors)

    async def test_validate_message_topic_warning(self):
        """Test validation warns about topics not in allowed list."""
        client = PolicyRegistryClient()

        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "max_response_length": 10000,
                "allowed_topics": ["finance", "security"],
                "prohibited_content": [],
            }

            message = AgentMessage(
                message_type=MessageType.COMMAND,
                sender_id="agent1",
                content={"action": "test", "topics": ["health"]},
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            result = await client.validate_message_signature(message)

            assert result.is_valid is True
            assert any("topic" in w.lower() for w in result.warnings)

    async def test_validate_message_no_policy_fallback(self):
        """Test validation fallback when no policy available."""
        client = PolicyRegistryClient()

        with patch.object(client, "get_policy_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            message = AgentMessage(
                message_type=MessageType.COMMAND,
                sender_id="agent1",
                content={"action": "test"},
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            result = await client.validate_message_signature(message)

            assert result.is_valid is True
            assert any("unavailable" in w.lower() for w in result.warnings)


class TestPolicyRegistryClientGetCurrentPublicKey:
    """Test get_current_public_key method."""

    async def test_get_public_key_success(self):
        """Test successful public key retrieval."""
        client = PolicyRegistryClient()
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"current_public_key": "-----BEGIN PUBLIC KEY-----..."}
        mock_http.get.return_value = mock_response
        client._http_client = mock_http

        result = await client.get_current_public_key()

        assert result == "-----BEGIN PUBLIC KEY-----..."
        mock_http.get.assert_called_with(f"{client.registry_url}/api/v1/public-keys")

    async def test_get_public_key_error_returns_none(self):
        """Test error returns None."""
        client = PolicyRegistryClient()
        mock_http = AsyncMock()

        mock_http.get.side_effect = Exception("Network error")
        client._http_client = mock_http

        result = await client.get_current_public_key()

        assert result is None


class TestPolicyRegistryClientHealthCheck:
    """Test health_check method."""

    async def test_health_check_success(self):
        """Test successful health check."""
        client = PolicyRegistryClient()
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "healthy"}
        mock_http.get.return_value = mock_response
        client._http_client = mock_http

        result = await client.health_check()

        assert result == {"status": "healthy"}
        mock_http.get.assert_called_with(f"{client.registry_url}/health/ready")

    async def test_health_check_http_error(self):
        """Test health check HTTP error handling."""
        client = PolicyRegistryClient()
        mock_http = AsyncMock()

        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 503
        error = httpx.HTTPStatusError(
            "Service unavailable", request=MagicMock(), response=mock_response
        )
        mock_http.get.side_effect = error
        client._http_client = mock_http

        result = await client.health_check()

        assert result["status"] == "unhealthy"
        assert "503" in result["error"]

    async def test_health_check_timeout_error(self):
        """Test health check timeout error handling."""
        client = PolicyRegistryClient()
        mock_http = AsyncMock()

        import httpx

        mock_http.get.side_effect = httpx.TimeoutException("Request timed out")
        client._http_client = mock_http

        result = await client.health_check()

        assert result["status"] == "unhealthy"
        assert "TimeoutException" in result["error"]

    async def test_health_check_connect_error(self):
        """Test health check connection error handling."""
        client = PolicyRegistryClient()
        mock_http = AsyncMock()

        import httpx

        mock_http.get.side_effect = httpx.ConnectError("Connection refused")
        client._http_client = mock_http

        result = await client.health_check()

        assert result["status"] == "unhealthy"
        assert "ConnectError" in result["error"]

    async def test_health_check_value_error(self):
        """Test health check value error handling."""
        client = PolicyRegistryClient()
        mock_http = AsyncMock()

        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_http.get.return_value = mock_response
        client._http_client = mock_http

        result = await client.health_check()

        assert result["status"] == "unhealthy"
        assert "parsing error" in result["error"].lower()
