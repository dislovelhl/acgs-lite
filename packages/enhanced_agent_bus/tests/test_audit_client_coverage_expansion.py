"""
ACGS-2 Enhanced Agent Bus - Audit Client Coverage Expansion Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests to expand audit_client.py coverage from 54% to 70%+.
Targets: batching, circuit breaker, health checks, global client functions.
"""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import httpx

from audit_client import (
    CONSTITUTIONAL_HASH,
    AuditBatchResult,
    AuditClient,
    AuditClientConfig,
    close_audit_client,
    get_audit_client,
    initialize_audit_client,
)
from enhanced_agent_bus._compat.types import JSONDict

# =============================================================================
# Test Data Classes
# =============================================================================


@dataclass
class MockValidationResult:
    """Mock validation result with to_dict method."""

    is_valid: bool
    message_id: str
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        return {
            "is_valid": self.is_valid,
            "message_id": self.message_id,
            "constitutional_hash": self.constitutional_hash,
        }


# =============================================================================
# AuditClientConfig Tests
# =============================================================================


class TestAuditClientConfig:
    """Tests for AuditClientConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = AuditClientConfig()
        assert config.service_url == "http://localhost:8001"
        assert config.timeout == 5.0
        assert config.enable_batching is True
        assert config.batch_size == 50
        assert config.batch_flush_interval_s == 5.0
        assert config.enable_circuit_breaker is True
        assert config.circuit_fail_max == 5
        assert config.circuit_reset_timeout == 30
        assert config.max_retries == 3
        assert config.retry_delay_s == 0.5
        assert config.queue_size == 1000

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = AuditClientConfig(
            service_url="http://audit:9000",
            timeout=10.0,
            enable_batching=False,
            batch_size=100,
            batch_flush_interval_s=10.0,
            enable_circuit_breaker=False,
            circuit_fail_max=10,
            circuit_reset_timeout=60,
            max_retries=5,
            retry_delay_s=1.0,
            queue_size=2000,
        )
        assert config.service_url == "http://audit:9000"
        assert config.timeout == 10.0
        assert config.enable_batching is False
        assert config.batch_size == 100
        assert config.enable_circuit_breaker is False

    def test_config_based_initialization(self) -> None:
        """Test AuditClient initialization with config object."""
        config = AuditClientConfig(
            service_url="http://custom:8080",
            timeout=15.0,
            enable_batching=False,
        )
        client = AuditClient(config=config)
        assert client.service_url == "http://custom:8080"
        assert client.config.timeout == 15.0
        assert client.config.enable_batching is False


# =============================================================================
# AuditBatchResult Tests
# =============================================================================


class TestAuditBatchResult:
    """Tests for AuditBatchResult dataclass."""

    def test_batch_result_creation(self) -> None:
        """Test creating an AuditBatchResult."""
        result = AuditBatchResult(
            batch_id="test-batch-123",
            entry_count=10,
            successful=8,
            failed=2,
            entry_hashes=["hash1", "hash2", "hash3"],
        )
        assert result.batch_id == "test-batch-123"
        assert result.entry_count == 10
        assert result.successful == 8
        assert result.failed == 2
        assert len(result.entry_hashes) == 3
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_batch_result_to_dict(self) -> None:
        """Test AuditBatchResult to_dict conversion."""
        result = AuditBatchResult(
            batch_id="batch-456",
            entry_count=5,
            successful=5,
            failed=0,
            entry_hashes=["h1", "h2", "h3", "h4", "h5"],
        )
        d = result.to_dict()
        assert d["batch_id"] == "batch-456"
        assert d["entry_count"] == 5
        assert d["successful"] == 5
        assert d["failed"] == 0
        assert d["entry_hashes"] == ["h1", "h2", "h3", "h4", "h5"]
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "timestamp" in d


# =============================================================================
# Start/Stop Lifecycle Tests
# =============================================================================


class TestAuditClientLifecycle:
    """Tests for AuditClient start/stop lifecycle."""

    async def test_start_creates_batch_worker(self) -> None:
        """Test that start() creates a batch worker when batching is enabled."""
        config = AuditClientConfig(enable_batching=True)
        client = AuditClient(config=config)

        await client.start()
        try:
            assert client._running is True
            assert client._batch_worker is not None
            assert not client._batch_worker.done()
        finally:
            await client.stop()

    async def test_start_no_worker_when_batching_disabled(self) -> None:
        """Test that start() doesn't create worker when batching is disabled."""
        config = AuditClientConfig(enable_batching=False)
        client = AuditClient(config=config)

        await client.start()
        try:
            assert client._running is True
            assert client._batch_worker is None
        finally:
            await client.stop()

    async def test_start_already_running(self) -> None:
        """Test that start() is idempotent when already running."""
        config = AuditClientConfig(enable_batching=True)
        client = AuditClient(config=config)

        await client.start()
        original_worker = client._batch_worker

        # Call start again - should be no-op
        await client.start()
        assert client._batch_worker is original_worker

        await client.stop()

    async def test_stop_flushes_pending_batch(self) -> None:
        """Test that stop() flushes any pending batch."""
        config = AuditClientConfig(enable_batching=True, batch_size=100)
        client = AuditClient(config=config)

        await client.start()

        # Add some items to batch directly
        async with client._batch_lock:
            client._batch.append({"test": "data"})

        # Create mock for HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hashes": ["hash1"]}

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            await client.stop()

            # Batch should be flushed
            assert len(client._batch) == 0

    async def test_stop_cancels_batch_worker(self) -> None:
        """Test that stop() cancels the batch worker."""
        config = AuditClientConfig(enable_batching=True)
        client = AuditClient(config=config)

        await client.start()
        worker = client._batch_worker

        await client.stop()

        assert client._running is False
        assert worker.done() or worker.cancelled()


# =============================================================================
# Batching Tests
# =============================================================================


class TestBatchingWorkflow:
    """Tests for batching workflow."""

    async def test_queue_for_batch(self) -> None:
        """Test queuing validation results for batch submission."""
        config = AuditClientConfig(enable_batching=True, batch_size=10)
        client = AuditClient(config=config)

        # Set running flag without starting background worker
        client._running = True

        result = MockValidationResult(True, "msg-1")

        with patch.object(client, "_submit_batch", new_callable=AsyncMock) as mock_submit:
            mock_submit.return_value = None

            audit_hash = await client.report_validation(result)
            assert audit_hash == "queued"
            assert len(client._batch) == 1

        client._running = False

    async def test_batch_auto_flush_when_full(self) -> None:
        """Test that batch is auto-flushed when reaching batch_size via _queue_for_batch."""
        config = AuditClientConfig(enable_batching=True, batch_size=3)
        client = AuditClient(config=config)

        # Don't start the background worker - test the mechanism directly
        client._running = True  # Set flag to enable batching path

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hashes": ["h1", "h2", "h3"]}

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            # Add 3 items to trigger auto-flush
            for i in range(3):
                result = MockValidationResult(True, f"msg-{i}")
                await client.report_validation(result)

            # Batch should have been flushed (size reached batch_size)
            assert len(client._batch) == 0
            mock_post.assert_called()

        client._running = False

    async def test_flush_empty_batch_returns_none(self) -> None:
        """Test that flushing an empty batch returns None."""
        config = AuditClientConfig(enable_batching=True)
        client = AuditClient(config=config)

        result = await client._flush_batch()
        assert result is None

    async def test_submit_batch_success(self) -> None:
        """Test successful batch submission."""
        config = AuditClientConfig(enable_batching=True)
        client = AuditClient(config=config)

        batch = [
            MockValidationResult(True, "msg-1"),
            MockValidationResult(True, "msg-2"),
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hashes": ["hash1", "hash2"]}

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await client._submit_batch(batch)

            assert result is not None
            assert result.entry_count == 2
            assert result.successful == 2
            assert result.failed == 0
            assert client._stats["batches_sent"] == 1
            assert client._stats["successful"] == 2

    async def test_submit_batch_empty_returns_none(self) -> None:
        """Test that submitting empty batch returns None."""
        client = AuditClient()
        result = await client._submit_batch([])
        assert result is None

    async def test_submit_batch_with_failures(self) -> None:
        """Test batch submission with partial failures."""
        client = AuditClient()

        batch = [
            MockValidationResult(True, "msg-1"),
            MockValidationResult(True, "msg-2"),
            MockValidationResult(True, "msg-3"),
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hashes": ["hash1"]}  # Only 1 success

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await client._submit_batch(batch)

            assert result.successful == 1
            assert result.failed == 2
            assert client._stats["failed"] == 2

    async def test_submit_batch_retry_on_network_error(self) -> None:
        """Test batch submission retries on network errors."""
        config = AuditClientConfig(max_retries=3, retry_delay_s=0.01)
        client = AuditClient(config=config)

        batch = [MockValidationResult(True, "msg-1")]

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.RequestError("Network error")

            result = await client._submit_batch(batch)

            assert result is None
            assert mock_post.call_count == 3  # max_retries
            assert client._stats["failed"] == 1

    async def test_submit_batch_non_200_response(self) -> None:
        """Test batch submission with non-200 response."""
        config = AuditClientConfig(max_retries=2, retry_delay_s=0.01)
        client = AuditClient(config=config)

        batch = [MockValidationResult(True, "msg-1")]

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await client._submit_batch(batch)

            assert result is None
            assert client._stats["failed"] == 1


# =============================================================================
# Circuit Breaker Tests
# =============================================================================


class TestCircuitBreakerIntegration:
    """Tests for circuit breaker integration."""

    async def test_submit_single_circuit_open_rejection(self) -> None:
        """Test that open circuit breaker rejects single submissions."""
        config = AuditClientConfig(enable_circuit_breaker=True)
        client = AuditClient(config=config)

        # Mock circuit breaker as open
        mock_cb = MagicMock()
        mock_cb.current_state = "open"
        client._circuit_breaker = mock_cb

        with patch("audit_client.CIRCUIT_BREAKER_AVAILABLE", True):
            result = await client._submit_single(MockValidationResult(True, "msg-1"))

            assert result is None
            assert client._stats["circuit_rejections"] == 1

    async def test_submit_batch_circuit_open_rejection(self) -> None:
        """Test that open circuit breaker rejects batch submissions."""
        config = AuditClientConfig(enable_circuit_breaker=True)
        client = AuditClient(config=config)

        # Mock circuit breaker as open
        mock_cb = MagicMock()
        mock_cb.current_state = "open"
        client._circuit_breaker = mock_cb

        batch = [
            MockValidationResult(True, "msg-1"),
            MockValidationResult(True, "msg-2"),
        ]

        with patch("audit_client.CIRCUIT_BREAKER_AVAILABLE", True):
            result = await client._submit_batch(batch)

            assert result is None
            assert client._stats["circuit_rejections"] == 2  # Counts each item

    async def test_circuit_breaker_exception_handling(self) -> None:
        """Test graceful handling of circuit breaker exceptions."""
        config = AuditClientConfig(enable_circuit_breaker=True)
        client = AuditClient(config=config)

        # Mock circuit breaker that raises exception
        mock_cb = MagicMock()
        type(mock_cb).current_state = PropertyMock(side_effect=RuntimeError("CB error"))
        client._circuit_breaker = mock_cb

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hash": "hash1"}

        with patch("audit_client.CIRCUIT_BREAKER_AVAILABLE", True):
            with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response

                # Should proceed despite circuit breaker error
                result = await client._submit_single(MockValidationResult(True, "msg-1"))
                assert result == "hash1"


# =============================================================================
# Health Check Tests
# =============================================================================


class TestHealthCheck:
    """Tests for health_check method."""

    async def test_health_check_healthy(self) -> None:
        """Test health check when service is healthy."""
        client = AuditClient()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(client.client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            health = await client.health_check()

            assert health["status"] == "healthy"
            assert health["latency_ms"] is not None
            assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_health_check_degraded(self) -> None:
        """Test health check when service returns non-200."""
        client = AuditClient()

        mock_response = MagicMock()
        mock_response.status_code = 503

        with patch.object(client.client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            health = await client.health_check()

            assert health["status"] == "degraded"
            assert health["latency_ms"] is not None

    async def test_health_check_unhealthy(self) -> None:
        """Test health check when service is unreachable."""
        client = AuditClient()

        with patch.object(client.client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.RequestError("Connection refused")

            health = await client.health_check()

            assert health["status"] == "unhealthy"
            assert health["error"] == "Connection refused"
            assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_health_check_with_circuit_state(self) -> None:
        """Test health check includes circuit breaker state."""
        config = AuditClientConfig(enable_circuit_breaker=True)
        client = AuditClient(config=config)

        # Mock circuit breaker
        mock_cb = MagicMock()
        mock_cb.current_state = "half_open"
        client._circuit_breaker = mock_cb

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("audit_client.CIRCUIT_BREAKER_AVAILABLE", True):
            with patch.object(client.client, "get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_response

                health = await client.health_check()

                assert health["circuit_state"] == "half_open"


# =============================================================================
# Recent Results Tests
# =============================================================================


class TestRecentResults:
    """Tests for get_recent_results method."""

    def test_get_recent_results_empty(self) -> None:
        """Test getting recent results when none exist."""
        client = AuditClient()
        results = client.get_recent_results()
        assert results == []

    def test_get_recent_results_with_data(self) -> None:
        """Test getting recent results with data."""
        client = AuditClient()

        # Add some results directly
        result1 = AuditBatchResult(
            batch_id="batch-1",
            entry_count=5,
            successful=5,
            failed=0,
            entry_hashes=["h1"],
        )
        result2 = AuditBatchResult(
            batch_id="batch-2",
            entry_count=3,
            successful=2,
            failed=1,
            entry_hashes=["h2"],
        )
        client._recent_results.append(result1)
        client._recent_results.append(result2)

        results = client.get_recent_results(n=10)
        assert len(results) == 2
        assert results[0]["batch_id"] == "batch-1"
        assert results[1]["batch_id"] == "batch-2"

    def test_get_recent_results_limited(self) -> None:
        """Test that get_recent_results respects the n limit."""
        client = AuditClient()

        for i in range(20):
            result = AuditBatchResult(
                batch_id=f"batch-{i}",
                entry_count=1,
                successful=1,
                failed=0,
                entry_hashes=[f"h{i}"],
            )
            client._recent_results.append(result)

        results = client.get_recent_results(n=5)
        assert len(results) == 5


# =============================================================================
# Global Client Functions Tests
# =============================================================================


class TestGlobalClientFunctions:
    """Tests for global client functions."""

    async def test_get_audit_client_creates_singleton(self) -> None:
        """Test that get_audit_client creates a singleton."""
        # Reset global client
        import audit_client

        audit_client._global_client = None

        client1 = get_audit_client()
        client2 = get_audit_client()

        assert client1 is client2

        # Cleanup
        await close_audit_client()

    async def test_get_audit_client_with_config(self) -> None:
        """Test get_audit_client with custom config."""
        import audit_client

        audit_client._global_client = None

        config = AuditClientConfig(service_url="http://test:8080")
        client = get_audit_client(config)

        assert client.service_url == "http://test:8080"

        await close_audit_client()

    async def test_initialize_audit_client(self) -> None:
        """Test initialize_audit_client starts the client."""
        import audit_client

        audit_client._global_client = None

        config = AuditClientConfig(enable_batching=True)
        client = await initialize_audit_client(config)

        assert client._running is True

        await close_audit_client()

    async def test_close_audit_client(self) -> None:
        """Test close_audit_client stops and clears the global client."""
        import audit_client

        audit_client._global_client = None

        config = AuditClientConfig(enable_batching=True)
        await initialize_audit_client(config)

        with patch.object(audit_client._global_client.client, "aclose", new_callable=AsyncMock):
            await close_audit_client()

        assert audit_client._global_client is None

    async def test_close_audit_client_when_none(self) -> None:
        """Test close_audit_client when no client exists."""
        import audit_client

        audit_client._global_client = None

        # Should not raise
        await close_audit_client()

        assert audit_client._global_client is None


# =============================================================================
# Retry Logic Tests
# =============================================================================


class TestRetryLogic:
    """Tests for retry logic in submissions."""

    async def test_submit_single_retry_on_request_error(self) -> None:
        """Test single submission retries on request errors."""
        config = AuditClientConfig(max_retries=3, retry_delay_s=0.01)
        client = AuditClient(config=config)

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.RequestError("Network error")

            result = await client._submit_single(MockValidationResult(True, "msg-1"))

            assert result is None
            assert mock_post.call_count == 3
            assert client._stats["failed"] == 1

    async def test_submit_single_success_after_retry(self) -> None:
        """Test single submission succeeds after initial failures."""
        config = AuditClientConfig(max_retries=3, retry_delay_s=0.01)
        client = AuditClient(config=config)

        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_success.json.return_value = {"entry_hash": "success_hash"}

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            # Fail twice, then succeed
            mock_post.side_effect = [
                httpx.RequestError("Error 1"),
                httpx.RequestError("Error 2"),
                mock_success,
            ]

            result = await client._submit_single(MockValidationResult(True, "msg-1"))

            assert result == "success_hash"
            assert mock_post.call_count == 3
            assert client._stats["successful"] == 1

    async def test_submit_single_non_200_response(self) -> None:
        """Test single submission handles non-200 response."""
        config = AuditClientConfig(max_retries=2, retry_delay_s=0.01)
        client = AuditClient(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await client._submit_single(MockValidationResult(True, "msg-1"))

            assert result is None
            # Should retry as it's not a permanent failure
            assert mock_post.call_count == 2
            assert client._stats["failed"] == 1


# =============================================================================
# Batch Flush Worker Tests
# =============================================================================


class TestBatchFlushWorker:
    """Tests for the background batch flush worker."""

    async def test_batch_flush_worker_exists_when_batching_enabled(self) -> None:
        """Test that batch flush worker is created when batching is enabled."""
        config = AuditClientConfig(
            enable_batching=True,
            batch_flush_interval_s=5.0,  # Long interval to avoid actual execution
            batch_size=100,
        )
        client = AuditClient(config=config)

        try:
            await client.start()
            # Worker should exist
            assert client._batch_worker is not None
            assert not client._batch_worker.done()
        finally:
            await client.stop()

    async def test_batch_flush_worker_stops_on_cancel(self) -> None:
        """Test that batch flush worker handles cancellation gracefully."""
        config = AuditClientConfig(
            enable_batching=True,
            batch_flush_interval_s=5.0,
        )
        client = AuditClient(config=config)

        await client.start()
        worker = client._batch_worker

        # Stop should cancel the worker
        await client.stop()

        assert not client._running
        # Worker should be done (cancelled)
        assert worker.done() or worker.cancelled()


# =============================================================================
# Stats Tracking Tests
# =============================================================================


class TestStatsTracking:
    """Tests for statistics tracking."""

    async def test_stats_track_submitted(self) -> None:
        """Test that stats track total submitted."""
        config = AuditClientConfig(enable_batching=False)
        client = AuditClient(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hash": "hash1"}

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await client.report_validation(MockValidationResult(True, "msg-1"))
            await client.report_validation(MockValidationResult(True, "msg-2"))

        assert client._stats["total_submitted"] == 2
        assert client._stats["successful"] == 2

    async def test_get_stats_returns_comprehensive_info(self) -> None:
        """Test that get_stats returns comprehensive information."""
        config = AuditClientConfig(enable_batching=True)
        client = AuditClient(config=config)

        await client.start()

        mock_response = MagicMock()
        mock_response.json.return_value = {"remote": "data"}

        with patch.object(client.client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            stats = await client.get_stats()

            assert "client_stats" in stats
            assert "remote_stats" in stats
            assert "queue_size" in stats
            assert "running" in stats
            assert "circuit_breaker_available" in stats
            assert "constitutional_hash" in stats
            assert stats["running"] is True

        await client.stop()


# =============================================================================
# Serialization Tests
# =============================================================================


class TestSerialization:
    """Tests for validation result serialization."""

    def test_serialize_with_to_dict(self) -> None:
        """Test serialization of object with to_dict method."""
        client = AuditClient()
        result = MockValidationResult(True, "msg-1")

        serialized = client._serialize_validation_result(result)

        assert serialized["is_valid"] is True
        assert serialized["message_id"] == "msg-1"

    def test_serialize_dataclass(self) -> None:
        """Test serialization of plain dataclass."""

        @dataclass
        class PlainResult:
            value: int
            name: str

        client = AuditClient()
        result = PlainResult(value=42, name="test")

        serialized = client._serialize_validation_result(result)

        assert serialized["value"] == 42
        assert serialized["name"] == "test"

    def test_serialize_dict(self) -> None:
        """Test serialization of raw dictionary."""
        client = AuditClient()
        result = {"key": "value", "count": 5}

        serialized = client._serialize_validation_result(result)

        assert serialized == result


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    async def test_report_with_batching_not_running(self) -> None:
        """Test reporting when batching enabled but not started."""
        config = AuditClientConfig(enable_batching=True)
        client = AuditClient(config=config)

        # Don't call start() - batching enabled but not running
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hash": "hash1"}

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            # Should fall back to immediate submission
            result = await client.report_validation(MockValidationResult(True, "msg-1"))
            assert result == "hash1"

    async def test_concurrent_batch_operations(self) -> None:
        """Test concurrent batch operations don't cause race conditions."""
        config = AuditClientConfig(enable_batching=True, batch_size=20)
        client = AuditClient(config=config)

        # Set running flag without starting background worker
        client._running = True

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"entry_hashes": ["h1", "h2", "h3", "h4", "h5"]}

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            # Submit 10 items concurrently (less than batch_size to avoid auto-flush)
            tasks = [
                client.report_validation(MockValidationResult(True, f"msg-{i}")) for i in range(10)
            ]
            results = await asyncio.gather(*tasks)

            # Should have queued all items
            assert all(r == "queued" for r in results)

        client._running = False

    async def test_stop_without_start(self) -> None:
        """Test stopping a client that was never started."""
        client = AuditClient()

        # Should not raise
        with patch.object(client.client, "aclose", new_callable=AsyncMock):
            await client.stop()

        assert client._running is False
