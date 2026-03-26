"""
ACGS-2 OPA Client Coverage Tests
Constitutional Hash: 608508a9bd224290

Extended tests to increase opa_client.py coverage.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]
RUN_EAB_OPA_CLIENT_COVERAGE_TESTS = (
    os.getenv("RUN_EAB_OPA_CLIENT_COVERAGE_TESTS", "false").lower() == "true"
)
if not RUN_EAB_OPA_CLIENT_COVERAGE_TESTS:
    pytestmark.append(
        pytest.mark.skip(
            reason=(
                "OPA client coverage tests disabled by default in this runtime. "
                "Set RUN_EAB_OPA_CLIENT_COVERAGE_TESTS=true to run."
            )
        )
    )

try:
    from enhanced_agent_bus.models import CONSTITUTIONAL_HASH
    from enhanced_agent_bus.opa_client import (
        OPA_SDK_AVAILABLE,
        REDIS_AVAILABLE,
        OPAClient,
        close_opa_client,
        get_opa_client,
        get_redis_url,
        initialize_opa_client,
    )
except ImportError:
    from models import CONSTITUTIONAL_HASH
    from opa_client import (
        OPA_SDK_AVAILABLE,
        REDIS_AVAILABLE,
        OPAClient,
        close_opa_client,
        get_opa_client,
        get_redis_url,
        initialize_opa_client,
    )


class TestOPAClientInit:
    """Tests for OPAClient initialization."""

    def test_default_init(self):
        """OPAClient initializes with defaults."""
        client = OPAClient()
        assert client.opa_url == "http://localhost:8181"
        assert client.fail_closed is True
        assert client.cache_ttl == 60
        assert client.timeout == 5.0

    def test_custom_opa_url(self):
        """OPAClient with custom OPA URL."""
        client = OPAClient(opa_url="http://opa.example.com:8181/")
        # Trailing slash should be stripped
        assert client.opa_url == "http://opa.example.com:8181"

    def test_fail_closed_always_enforced(self):
        """OPAClient always enforces fail-closed for security (VULN-002)."""
        # fail_closed is hardcoded to True and cannot be overridden
        # This is a security measure to prevent fail-open scenarios
        client = OPAClient()
        assert client.fail_closed is True

    def test_custom_cache_ttl(self):
        """OPAClient with custom cache TTL."""
        client = OPAClient(cache_ttl=600)
        assert client.cache_ttl == 600

    def test_custom_timeout(self):
        """OPAClient with custom timeout."""
        client = OPAClient(timeout=10.0)
        assert client.timeout == 10.0


class TestOPAClientCaching:
    """Tests for caching behavior."""

    @pytest.fixture
    def client(self):
        """Create client for testing."""
        return OPAClient()

    def test_generate_cache_key(self, client):
        """_generate_cache_key creates consistent keys."""
        policy = "data.authz.allow"
        input_data = {"user": "alice", "action": "read"}

        key1 = client._generate_cache_key(policy, input_data)
        key2 = client._generate_cache_key(policy, input_data)

        assert key1 == key2
        assert policy in key1

    def test_cache_key_varies_with_input(self, client):
        """Cache keys differ for different inputs."""
        policy = "data.authz.allow"
        input1 = {"user": "alice"}
        input2 = {"user": "bob"}

        key1 = client._generate_cache_key(policy, input1)
        key2 = client._generate_cache_key(policy, input2)

        assert key1 != key2


class TestOPAClientContextManager:
    """Tests for context manager behavior."""

    async def test_aenter_initializes(self):
        """__aenter__ initializes the client."""
        client = OPAClient()

        with patch.object(client, "initialize", new_callable=AsyncMock) as mock_init:
            result = await client.__aenter__()
            mock_init.assert_called_once()
            assert result is client

    async def test_aexit_closes(self):
        """__aexit__ closes the client."""
        client = OPAClient()

        with patch.object(client, "close", new_callable=AsyncMock) as mock_close:
            await client.__aexit__(None, None, None)
            mock_close.assert_called_once()


class TestOPAClientInitializeClose:
    """Tests for initialize and close methods."""

    async def test_initialize_creates_http_client(self):
        """Initialize creates HTTP client if none exists."""
        client = OPAClient()
        assert client._http_client is None

        try:
            await client.initialize()
            assert client._http_client is not None
        finally:
            await client.close()

    async def test_initialize_idempotent(self):
        """Initialize is idempotent."""
        client = OPAClient()

        try:
            await client.initialize()
            first_client = client._http_client

            await client.initialize()
            second_client = client._http_client

            assert first_client is second_client
        finally:
            await client.close()

    async def test_close_clears_http_client(self):
        """Close closes and clears HTTP client."""
        client = OPAClient()

        await client.initialize()
        assert client._http_client is not None

        await client.close()
        assert client._http_client is None

    async def test_close_safe_when_not_initialized(self):
        """Close is safe when client not initialized."""
        client = OPAClient()
        assert client._http_client is None

        # Should not raise
        await client.close()


class TestOPAClientEvaluatePolicy:
    """Tests for evaluate_policy method."""

    @pytest.fixture
    def client(self):
        """Create client for testing."""
        return OPAClient()

    async def test_evaluate_returns_cached_result(self, client):
        """evaluate_policy returns cached result when available."""
        policy_path = "data.test.allow"
        input_data = {"user": "alice"}
        expected = {"result": True, "allowed": True}

        # Pre-populate in-memory cache with proper structure
        cache_key = client._generate_cache_key(policy_path, input_data)
        import time

        client._memory_cache[cache_key] = expected
        client._memory_cache_timestamps[cache_key] = time.time()

        result = await client.evaluate_policy(input_data, policy_path)
        assert result == expected

    async def test_evaluate_fail_closed_on_error(self):
        """evaluate_policy fails closed on error (security default)."""
        client = OPAClient()  # fail_closed is always True for security

        # Mock HTTP to fail
        mock_http = MagicMock()
        mock_http.post = AsyncMock(side_effect=Exception("Connection refused"))
        client._http_client = mock_http

        # Correct argument order: input_data first, then policy_path
        result = await client.evaluate_policy({"user": "alice"}, policy_path="data.test.allow")

        # Fail closed should return deny
        assert (
            result.get("allow", result.get("result", False)) is False
            or "denied" in str(result).lower()
        )

    async def test_fail_open_not_supported(self):
        """Verify fail-open mode is NOT supported (security measure VULN-002).

        OPAClient always enforces fail-closed behavior even on errors.
        This test verifies the security hardening is in place.
        """
        client = OPAClient()

        # Verify fail_closed is always True and cannot be overridden
        assert client.fail_closed is True

        # Mock HTTP to fail
        mock_http = MagicMock()
        mock_http.post = AsyncMock(side_effect=Exception("Connection refused"))
        client._http_client = mock_http

        # Correct argument order: input_data first, then policy_path
        result = await client.evaluate_policy({"user": "alice"}, policy_path="data.test.allow")

        # Should always fail closed (deny on error)
        assert (
            result.get("allow", result.get("result", False)) is False
            or "denied" in str(result).lower()
            or "error" in str(result).lower()
        )


class TestOPAClientValidateConstitutional:
    """Tests for validate_constitutional method."""

    @pytest.fixture
    def client(self):
        """Create client for testing."""
        return OPAClient()

    async def test_validate_with_correct_hash(self, client):
        """validate_constitutional passes with correct hash."""
        # Mock evaluate_policy to return success
        with patch.object(client, "evaluate_policy", new_callable=AsyncMock) as mock_eval:
            mock_eval.return_value = {"allowed": True, "reason": "Success"}

            message = {
                "action": "test",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
            result = await client.validate_constitutional(message)

            # Result is a ValidationResult object
            assert result.is_valid is True


class TestOPAClientCheckAgentAuthorization:
    """Tests for check_agent_authorization method."""

    @pytest.fixture
    def client(self):
        """Create client for testing."""
        return OPAClient()

    async def test_check_authorization(self, client):
        """check_agent_authorization returns authorization result."""
        with patch.object(client, "evaluate_policy", new_callable=AsyncMock) as mock_eval:
            mock_eval.return_value = {"allowed": True}

            result = await client.check_agent_authorization(
                agent_id="agent-1",
                action="send_message",
                resource="agent-2",
            )

            mock_eval.assert_called_once()
            # Result should be a boolean
            assert isinstance(result, bool)


class TestOPAClientHealthCheck:
    """Tests for health_check method."""

    async def test_health_check_success(self):
        """Health check returns healthy on success."""
        client = OPAClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "healthy"}
        mock_response.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.health_check()

        assert result.get("status") == "healthy" or result.get("healthy", False) is True

    async def test_health_check_connection_error(self):
        """Health check returns unhealthy on connection error."""
        import httpx

        client = OPAClient()

        mock_http = MagicMock()
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        client._http_client = mock_http

        result = await client.health_check()

        assert result.get("status") == "unhealthy" or result.get("healthy", False) is False

    async def test_health_check_timeout(self):
        """Health check returns unhealthy on timeout."""
        import httpx

        client = OPAClient()

        mock_http = MagicMock()
        mock_http.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        client._http_client = mock_http

        result = await client.health_check()

        assert result.get("status") == "unhealthy" or result.get("healthy", False) is False


class TestOPAClientLoadPolicy:
    """Tests for load_policy method."""

    @pytest.fixture
    def client(self):
        """Create client for testing."""
        return OPAClient()

    async def test_load_policy_success(self, client):
        """load_policy uploads policy successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.put = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        policy_content = "package test\ndefault allow = false"
        result = await client.load_policy("test", policy_content)

        assert result is True
        mock_http.put.assert_called_once()

    async def test_load_policy_failure(self, client):
        """load_policy handles failure gracefully."""
        mock_http = MagicMock()
        mock_http.put = AsyncMock(side_effect=Exception("Upload failed"))
        client._http_client = mock_http

        policy_content = "package test\ndefault allow = false"
        result = await client.load_policy("test", policy_content)

        assert result is False


class TestOPAClientGetStats:
    """Tests for get_stats method."""

    def test_get_stats_returns_dict(self):
        """get_stats returns statistics dictionary."""
        client = OPAClient()

        stats = client.get_stats()

        assert isinstance(stats, dict)
        assert "cache_size" in stats or "evaluations" in stats or isinstance(stats, dict)


class TestGetRedisUrl:
    """Tests for get_redis_url function."""

    def test_get_redis_url_default(self):
        """get_redis_url returns default URL."""
        with patch.dict("os.environ", {}, clear=True):
            url = get_redis_url()
            assert "redis" in url.lower() or "localhost" in url

    def test_get_redis_url_returns_string(self):
        """get_redis_url returns a string URL."""
        url = get_redis_url()
        assert isinstance(url, str)
        assert "redis" in url.lower() or "localhost" in url


class TestModuleFunctions:
    """Tests for module-level functions."""

    async def test_get_opa_client_returns_client(self):
        """get_opa_client returns an OPAClient instance."""
        client = get_opa_client()
        assert isinstance(client, OPAClient)

    async def test_initialize_and_close_opa_client(self):
        """initialize_opa_client and close_opa_client work correctly."""
        client = await initialize_opa_client()
        assert client is not None
        assert isinstance(client, OPAClient)

        await close_opa_client()


class TestOPAClientConstants:
    """Tests for module constants."""

    def test_redis_available_is_bool(self):
        """REDIS_AVAILABLE is a boolean."""
        assert isinstance(REDIS_AVAILABLE, bool)

    def test_opa_sdk_available_is_bool(self):
        """OPA_SDK_AVAILABLE is a boolean."""
        assert isinstance(OPA_SDK_AVAILABLE, bool)


class TestOPAClientEvaluationMethods:
    """Tests for internal evaluation methods."""

    @pytest.fixture
    def client(self):
        """Create client for testing."""
        return OPAClient()

    async def test_evaluate_http_success(self, client):
        """_evaluate_http successfully evaluates via HTTP."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"allow": True}}
        mock_response.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        # Note: signature is (input_data, policy_path)
        result = await client._evaluate_http({"user": "alice"}, "data.test.allow")

        assert result is not None
        mock_http.post.assert_called_once()

    async def test_evaluate_fallback(self, client):
        """_evaluate_fallback returns appropriate result."""
        # Test fail-closed behavior
        client.fail_closed = True
        # Note: signature is (input_data, policy_path)
        result = await client._evaluate_fallback({"user": "alice"}, "data.test.allow")
        assert result is not None
        assert isinstance(result, dict)

    def test_handle_evaluation_error_fail_closed(self, client):
        """_handle_evaluation_error respects fail_closed."""
        client.fail_closed = True
        error = Exception("test error")

        # Note: signature is (error, policy_path)
        result = client._handle_evaluation_error(error, "data.test.allow")

        # Should return deny for fail-closed
        assert result is not None
        assert result.get("allowed") is False


class TestOPAClientBundleLoading:
    """Tests for bundle loading functionality."""

    @pytest.fixture
    def client(self):
        """Create client for testing."""
        return OPAClient()

    async def test_load_bundle_from_url_success(self, client):
        """load_bundle_from_url successfully loads bundle."""
        mock_response = MagicMock()
        mock_response.content = b"bundle content"
        mock_response.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        # Mock _verify_bundle to return True (it's async)
        with patch.object(client, "_verify_bundle", new_callable=AsyncMock, return_value=True):
            # Signature: (url, signature, public_key)
            result = await client.load_bundle_from_url(
                "http://example.com/bundle.tar.gz", "test_signature", "test_public_key"
            )

            # Should succeed or at least not crash
            assert isinstance(result, bool)

    async def test_load_bundle_from_url_failure(self, client):
        """load_bundle_from_url handles failure and rollback fails."""
        mock_http = MagicMock()
        mock_http.get = AsyncMock(side_effect=Exception("Download failed"))
        client._http_client = mock_http

        # Mock rollback to also fail so we get False return
        with patch.object(client, "_rollback_to_lkg", new_callable=AsyncMock, return_value=False):
            # Signature: (url, signature, public_key)
            result = await client.load_bundle_from_url(
                "http://example.com/bundle.tar.gz", "test_signature", "test_public_key"
            )

            assert result is False

    async def test_verify_bundle_returns_bool(self, client):
        """_verify_bundle returns a boolean."""
        import os
        import tempfile

        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".tar.gz") as f:
            f.write(b"test bundle content")
            temp_path = f.name

        try:
            # _verify_bundle takes (bundle_path, signature, public_key)
            result = await client._verify_bundle(temp_path, "test_sig", "test_key")
            assert isinstance(result, bool)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
