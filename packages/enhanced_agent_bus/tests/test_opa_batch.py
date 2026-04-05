"""
ACGS-2 Enhanced Agent Bus - OPA Batch Operations Tests
Constitutional Hash: 608508a9bd224290

TDD tests for batch OPA policy evaluation optimization.
Tests Phase 4-Task 3 acceptance criteria:
- Batch OPA requests where possible
- Parallel OPA calls
- Connection pooling for OPA client
"""

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

# Import centralized constitutional hash
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH


@pytest.fixture(autouse=True)
def _reset_opa_batch_singleton():
    """Reset OPA batch client singleton and module-level globals before AND after each test.

    The _batch_client singleton in opa_batch.py is shared globally. Without
    teardown, a test that calls get_batch_client() or initialize() leaves the
    singleton populated, polluting subsequent test files in the same xdist worker.
    (PM-012 pattern)

    Setup-phase reset also needed: if a *prior* test file in the same xdist
    worker corrupts the module-level Lock before this file's tests start,
    the teardown-only approach is insufficient (PM-015 pattern).
    """
    import sys

    import enhanced_agent_bus.opa_batch as mod

    # --- Setup: reset before test ---
    mod._batch_client = None
    mod._batch_client_lock = asyncio.Lock()
    alias = sys.modules.get("enhanced_agent_bus.opa_batch")
    if alias is not None and alias is not mod:
        alias._batch_client = None
        alias._batch_client_lock = asyncio.Lock()

    yield

    # --- Teardown: reset after test ---
    mod._batch_client = None
    mod._batch_client_lock = asyncio.Lock()
    alias = sys.modules.get("enhanced_agent_bus.opa_batch")
    if alias is not None and alias is not mod:
        alias._batch_client = None
        alias._batch_client_lock = asyncio.Lock()


class TestOPABatchClientConfig:
    """Test OPA batch client configuration."""

    async def test_batch_client_has_constitutional_hash(self):
        """Test batch client tracks constitutional hash for compliance."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        client = OPABatchClient(opa_url="http://localhost:8181")
        assert client.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_batch_client_configurable_concurrency(self):
        """Test batch client concurrency limit is configurable."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        client = OPABatchClient(
            opa_url="http://localhost:8181",
            max_concurrent=20,
        )
        assert client.max_concurrent == 20

    async def test_batch_client_default_concurrency(self):
        """Test batch client has reasonable default concurrency."""
        from enhanced_agent_bus.opa_batch import DEFAULT_MAX_CONCURRENT, OPABatchClient

        client = OPABatchClient(opa_url="http://localhost:8181")
        assert client.max_concurrent == DEFAULT_MAX_CONCURRENT
        assert DEFAULT_MAX_CONCURRENT >= 5
        assert DEFAULT_MAX_CONCURRENT <= 50

    async def test_batch_client_configurable_batch_size(self):
        """Test batch client batch size is configurable."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        client = OPABatchClient(
            opa_url="http://localhost:8181",
            batch_size=50,
        )
        assert client.batch_size == 50

    async def test_batch_client_default_cache_hash_mode(self):
        """Test batch client defaults to SHA-256 cache keys."""
        from enhanced_agent_bus.opa_batch import DEFAULT_CACHE_HASH_MODE, OPABatchClient

        client = OPABatchClient(opa_url="http://localhost:8181")
        assert client.cache_hash_mode == DEFAULT_CACHE_HASH_MODE
        assert DEFAULT_CACHE_HASH_MODE == "sha256"

    async def test_batch_client_rejects_invalid_cache_hash_mode(self):
        """Test invalid cache hash mode is rejected."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            OPABatchClient(opa_url="http://localhost:8181", cache_hash_mode="unknown")  # type: ignore[arg-type]

    async def test_generate_cache_key_fast_mode_uses_kernel(self, monkeypatch):
        """Test fast mode uses Rust fast_hash when available."""
        import importlib
        import sys

        import enhanced_agent_bus.opa_batch as opa_batch_module

        called = {"value": False}

        def _fake_fast_hash(value: str) -> int:
            called["value"] = True
            return 0x1234

        # Simulate acgs2_perf being importable and having fast_hash
        mock_acgs2_perf = MagicMock(fast_hash=_fake_fast_hash)
        monkeypatch.setitem(sys.modules, "acgs2_perf", mock_acgs2_perf)

        # Ensure the module knows fast_hash is available
        monkeypatch.setattr(opa_batch_module, "FAST_HASH_AVAILABLE", True)

        # Reload the module to pick up the changes to sys.modules
        importlib.reload(opa_batch_module)

        # Now instantiate OPABatchClient after the module has been reloaded
        client = opa_batch_module.OPABatchClient(
            opa_url="http://localhost:8181", cache_hash_mode="fast"
        )
        key = client._generate_cache_key({"a": 1}, "data.acgs.allow")
        assert called["value"] is True
        assert key == "fast:0000000000001234"

    async def test_generate_cache_key_fast_mode_falls_back_to_sha256(self, monkeypatch):
        """Test fast mode falls back to SHA-256 when Rust kernel is unavailable."""
        import enhanced_agent_bus.opa_batch as opa_batch_module
        from enhanced_agent_bus.opa_batch import OPABatchClient

        monkeypatch.setattr(opa_batch_module, "FAST_HASH_AVAILABLE", False)
        client = OPABatchClient(opa_url="http://localhost:8181", cache_hash_mode="fast")
        key = client._generate_cache_key({"a": 1}, "data.acgs.allow")

        expected = hashlib.sha256(b'data.acgs.allow:{"a": 1}').hexdigest()
        assert key == expected


class TestOPABatchEvaluation:
    """Test OPA batch policy evaluation."""

    async def test_batch_evaluate_single_policy(self):
        """Test batch evaluate with single input."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": True}
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(opa_url="http://localhost:8181")
            await client.initialize()

            inputs = [{"action": "read", "resource": "policy"}]
            results = await client.batch_evaluate(inputs, "data.acgs.allow")

            assert len(results) == 1
            assert results[0]["allowed"] is True

            await client.close()

    async def test_batch_evaluate_multiple_inputs(self):
        """Test batch evaluate with multiple inputs."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": True}
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(opa_url="http://localhost:8181")
            await client.initialize()

            inputs = [
                {"action": "read", "resource": "policy_1"},
                {"action": "write", "resource": "policy_2"},
                {"action": "delete", "resource": "policy_3"},
            ]
            results = await client.batch_evaluate(inputs, "data.acgs.allow")

            assert len(results) == 3
            # Each input should have been evaluated
            assert mock_client.post.call_count == 3

            await client.close()

    async def test_batch_evaluate_empty_input(self):
        """Test batch evaluate with empty input list."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        client = OPABatchClient(opa_url="http://localhost:8181")
        results = await client.batch_evaluate([], "data.acgs.allow")

        assert results == []

    async def test_batch_evaluate_preserves_order(self):
        """Test batch evaluate preserves input order in results."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()

            # Create different responses for different inputs
            call_count = 0

            async def mock_post(url, **kwargs):
                nonlocal call_count
                call_count += 1
                response = MagicMock()
                response.status_code = 200
                # Use input index to create unique results
                input_data = kwargs.get("json", {}).get("input", {})
                resource = input_data.get("resource", "unknown")
                response.json.return_value = {"result": {"allow": True, "resource": resource}}
                response.raise_for_status = MagicMock()
                return response

            mock_client.post = mock_post
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(opa_url="http://localhost:8181")
            await client.initialize()

            inputs = [
                {"resource": "first"},
                {"resource": "second"},
                {"resource": "third"},
            ]
            results = await client.batch_evaluate(inputs, "data.acgs.allow")

            assert len(results) == 3
            # Results should be in same order as inputs
            assert results[0]["metadata"]["resource"] == "first"
            assert results[1]["metadata"]["resource"] == "second"
            assert results[2]["metadata"]["resource"] == "third"

            await client.close()


class TestOPABatchParallelExecution:
    """Test OPA batch parallel execution."""

    async def test_batch_uses_parallel_execution(self):
        """Test batch evaluate uses parallel execution."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            execution_times = []

            async def mock_post(url, **kwargs):
                start = asyncio.get_running_loop().time()
                await asyncio.sleep(0.01)  # Simulate network delay
                end = asyncio.get_running_loop().time()
                execution_times.append((start, end))

                response = MagicMock()
                response.status_code = 200
                response.json.return_value = {"result": True}
                response.raise_for_status = MagicMock()
                return response

            mock_client.post = mock_post
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(
                opa_url="http://localhost:8181",
                max_concurrent=10,
            )
            await client.initialize()

            # Create 5 inputs
            inputs = [{"action": f"action_{i}"} for i in range(5)]

            start_time = asyncio.get_running_loop().time()
            results = await client.batch_evaluate(inputs, "data.acgs.allow")
            total_time = asyncio.get_running_loop().time() - start_time

            assert len(results) == 5
            # If sequential, it would take at least 0.05s (5 * 0.01s)
            # Parallel should be much faster (around 0.01s + overhead)
            # Allow some margin for test environment variability
            assert total_time < 0.04  # Should be faster than sequential

            await client.close()

    async def test_batch_respects_concurrency_limit(self):
        """Test batch evaluate respects concurrency limit."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            concurrent_count = 0
            max_concurrent_observed = 0
            lock = asyncio.Lock()

            async def mock_post(url, **kwargs):
                nonlocal concurrent_count, max_concurrent_observed
                async with lock:
                    concurrent_count += 1
                    max_concurrent_observed = max(max_concurrent_observed, concurrent_count)

                await asyncio.sleep(0.01)  # Simulate work

                async with lock:
                    concurrent_count -= 1

                response = MagicMock()
                response.status_code = 200
                response.json.return_value = {"result": True}
                response.raise_for_status = MagicMock()
                return response

            mock_client.post = mock_post
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(
                opa_url="http://localhost:8181",
                max_concurrent=3,  # Limit to 3 concurrent
            )
            await client.initialize()

            # Create 10 inputs to test concurrency limiting
            inputs = [{"action": f"action_{i}"} for i in range(10)]
            results = await client.batch_evaluate(inputs, "data.acgs.allow")

            assert len(results) == 10
            # Should never exceed concurrency limit
            assert max_concurrent_observed <= 3

            await client.close()


class TestOPABatchCaching:
    """Test OPA batch caching integration."""

    async def test_batch_uses_cache_for_duplicates(self):
        """Test batch evaluate uses cache for duplicate inputs."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            call_count = 0

            async def mock_post(url, **kwargs):
                nonlocal call_count
                call_count += 1
                response = MagicMock()
                response.status_code = 200
                response.json.return_value = {"result": True}
                response.raise_for_status = MagicMock()
                return response

            mock_client.post = mock_post
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(
                opa_url="http://localhost:8181",
                enable_cache=True,
            )
            await client.initialize()

            # Create inputs with duplicates
            inputs = [
                {"action": "read"},  # unique
                {"action": "read"},  # duplicate
                {"action": "write"},  # unique
                {"action": "read"},  # duplicate
            ]
            results = await client.batch_evaluate(inputs, "data.acgs.allow")

            assert len(results) == 4
            # Should only make 2 OPA calls (for unique inputs)
            assert call_count == 2

            await client.close()

    async def test_batch_cache_returns_correct_results_for_duplicates(self):
        """Test batch cache returns correct results for duplicate inputs."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()

            async def mock_post(url, **kwargs):
                input_data = kwargs.get("json", {}).get("input", {})
                action = input_data.get("action", "unknown")
                response = MagicMock()
                response.status_code = 200
                # Return True for "read", False for "write"
                response.json.return_value = {
                    "result": {"allow": action == "read", "action": action}
                }
                response.raise_for_status = MagicMock()
                return response

            mock_client.post = mock_post
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(
                opa_url="http://localhost:8181",
                enable_cache=True,
            )
            await client.initialize()

            inputs = [
                {"action": "read"},
                {"action": "write"},
                {"action": "read"},  # Should get cached "read" result
            ]
            results = await client.batch_evaluate(inputs, "data.acgs.allow")

            assert results[0]["allowed"] is True  # read
            assert results[1]["allowed"] is False  # write
            assert results[2]["allowed"] is True  # read (cached)

            await client.close()


class TestOPABatchErrorHandling:
    """Test OPA batch error handling."""

    async def test_batch_handles_partial_failures(self):
        """Test batch evaluate handles partial failures gracefully."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            call_count = 0

            async def mock_post(url, **kwargs):
                nonlocal call_count
                call_count += 1
                input_data = kwargs.get("json", {}).get("input", {})

                # Fail on the second request
                if input_data.get("action") == "fail":
                    raise Exception("Simulated OPA failure")

                response = MagicMock()
                response.status_code = 200
                response.json.return_value = {"result": True}
                response.raise_for_status = MagicMock()
                return response

            mock_client.post = mock_post
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(opa_url="http://localhost:8181")
            await client.initialize()

            inputs = [
                {"action": "success_1"},
                {"action": "fail"},
                {"action": "success_2"},
            ]
            results = await client.batch_evaluate(inputs, "data.acgs.allow")

            assert len(results) == 3
            # Successful results
            assert results[0]["allowed"] is True
            assert results[2]["allowed"] is True
            # Failed result should be fail-closed
            assert results[1]["allowed"] is False
            assert "error" in results[1]["metadata"]

            await client.close()

    async def test_batch_fail_closed_on_error(self):
        """Test batch evaluate uses fail-closed on errors."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()

            async def mock_post(url, **kwargs):
                raise Exception("OPA unavailable")

            mock_client.post = mock_post
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(opa_url="http://localhost:8181")
            await client.initialize()

            inputs = [{"action": "read"}]
            results = await client.batch_evaluate(inputs, "data.acgs.allow")

            assert len(results) == 1
            # Fail-closed: error results in denial
            assert results[0]["allowed"] is False
            assert "security" in results[0]["metadata"]
            assert results[0]["metadata"]["security"] == "fail-closed"

            await client.close()


class TestOPABatchMetrics:
    """Test OPA batch metrics collection."""

    async def test_batch_tracks_metrics(self):
        """Test batch client tracks evaluation metrics."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": True}
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(opa_url="http://localhost:8181")
            await client.initialize()

            inputs = [{"action": f"action_{i}"} for i in range(5)]
            await client.batch_evaluate(inputs, "data.acgs.allow")

            stats = client.get_stats()
            assert "total_evaluations" in stats
            assert "batch_evaluations" in stats
            assert stats["total_evaluations"] == 5
            assert stats["batch_evaluations"] == 1

            await client.close()

    async def test_batch_tracks_cache_hits(self):
        """Test batch client tracks cache hit rate."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": True}
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(
                opa_url="http://localhost:8181",
                enable_cache=True,
            )
            await client.initialize()

            # First batch with duplicates
            inputs = [
                {"action": "read"},
                {"action": "read"},  # duplicate
                {"action": "write"},
            ]
            await client.batch_evaluate(inputs, "data.acgs.allow")

            stats = client.get_stats()
            assert "cache_hits" in stats
            assert stats["cache_hits"] == 1  # One duplicate hit

            await client.close()

    async def test_batch_tracks_latency(self):
        """Test batch client tracks average latency."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()

            async def mock_post(url, **kwargs):
                await asyncio.sleep(0.01)  # 10ms delay
                response = MagicMock()
                response.status_code = 200
                response.json.return_value = {"result": True}
                response.raise_for_status = MagicMock()
                return response

            mock_client.post = mock_post
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(opa_url="http://localhost:8181")
            await client.initialize()

            inputs = [{"action": "read"}]
            await client.batch_evaluate(inputs, "data.acgs.allow")

            stats = client.get_stats()
            assert "avg_latency_ms" in stats
            assert stats["avg_latency_ms"] >= 10  # At least 10ms

            await client.close()


class TestOPABatchConnectionPooling:
    """Test OPA batch connection pooling."""

    async def test_batch_reuses_connections(self):
        """Test batch client reuses HTTP connections."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": True}
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(opa_url="http://localhost:8181")
            await client.initialize()

            # Multiple batch evaluations
            for _ in range(3):
                inputs = [{"action": "read"}]
                await client.batch_evaluate(inputs, "data.acgs.allow")

            # Client should only be created once
            mock_client_cls.assert_called_once()

            await client.close()

    async def test_batch_configures_connection_pool(self):
        """Test batch client configures connection pool limits."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(
                opa_url="http://localhost:8181",
                max_connections=30,
                max_keepalive=15,
            )
            await client.initialize()

            # Verify connection pool was configured
            call_kwargs = mock_client_cls.call_args[1]
            limits = call_kwargs.get("limits")
            assert limits is not None
            assert limits.max_connections == 30
            assert limits.max_keepalive_connections == 15

            await client.close()


class TestOPABatchIntegration:
    """Test OPA batch integration with existing OPA client."""

    async def test_batch_client_compatible_with_opa_client(self):
        """Test batch client produces compatible results with OPAClient."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "result": {"allow": True, "reason": "Policy allows action"}
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            client = OPABatchClient(opa_url="http://localhost:8181")
            await client.initialize()

            inputs = [{"action": "read", "resource": "policy"}]
            results = await client.batch_evaluate(inputs, "data.acgs.allow")

            result = results[0]
            # Result format should match OPAClient.evaluate_policy format
            assert "result" in result
            assert "allowed" in result
            assert "reason" in result
            assert "metadata" in result
            assert result["allowed"] is True
            assert "mode" in result["metadata"]

            await client.close()

    async def test_batch_client_context_manager(self):
        """Test batch client works as async context manager."""
        from enhanced_agent_bus.opa_batch import OPABatchClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": True}
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            async with OPABatchClient(opa_url="http://localhost:8181") as client:
                inputs = [{"action": "read"}]
                results = await client.batch_evaluate(inputs, "data.acgs.allow")
                assert len(results) == 1

            # Verify close was called
            mock_client.aclose.assert_called_once()
