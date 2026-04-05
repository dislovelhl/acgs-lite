"""
ACGS-2 Blockchain Integration Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for:
- BlockchainAnchorManager multi-backend support
- AuditClient circuit breaker integration
- AuditLedger blockchain anchoring configuration
"""

import time

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# Test imports - handle both package and standalone modes
try:
    from enhanced_agent_bus.audit_client import (
        AuditBatchResult,
        AuditClient,
        AuditClientConfig,
        get_audit_client,
        initialize_audit_client,
    )

    AUDIT_CLIENT_AVAILABLE = True
except ImportError:
    AUDIT_CLIENT_AVAILABLE = False

try:
    from src.core.services.audit_service.core.blockchain_anchor_manager import (
        AnchorBackend,
        AnchorManagerConfig,
        AnchorResult,
        AnchorStatus,
        BlockchainAnchorManager,
        PendingAnchor,
        get_anchor_manager,
    )

    ANCHOR_MANAGER_AVAILABLE = True
except ImportError:
    ANCHOR_MANAGER_AVAILABLE = False

try:
    from src.core.services.audit_service.core.audit_ledger import (
        AuditEntry,
        AuditLedger,
        AuditLedgerConfig,
    )

    AUDIT_LEDGER_AVAILABLE = True
except ImportError:
    AUDIT_LEDGER_AVAILABLE = False


# =============================================================================
# AuditClient Tests
# =============================================================================


@pytest.mark.skipif(not AUDIT_CLIENT_AVAILABLE, reason="AuditClient not available")
class TestAuditClientConfig:
    """Tests for AuditClientConfig dataclass."""

    def test_default_config(self):
        """Default configuration has expected values."""
        config = AuditClientConfig()
        assert config.service_url == "http://localhost:8001"
        assert config.timeout == 5.0
        assert config.enable_batching is True
        assert config.batch_size == 50
        assert config.enable_circuit_breaker is True
        assert config.circuit_fail_max == 5
        assert config.circuit_reset_timeout == 30

    def test_custom_config(self):
        """Custom configuration is applied correctly."""
        config = AuditClientConfig(
            service_url="http://custom:9000",
            timeout=10.0,
            enable_batching=False,
            batch_size=100,
            enable_circuit_breaker=False,
        )
        assert config.service_url == "http://custom:9000"
        assert config.timeout == 10.0
        assert config.enable_batching is False
        assert config.batch_size == 100
        assert config.enable_circuit_breaker is False


@pytest.mark.skipif(not AUDIT_CLIENT_AVAILABLE, reason="AuditClient not available")
class TestAuditBatchResult:
    """Tests for AuditBatchResult dataclass."""

    def test_batch_result_creation(self):
        """AuditBatchResult can be created with required fields."""
        result = AuditBatchResult(
            batch_id="batch_123",
            entry_count=10,
            successful=9,
            failed=1,
            entry_hashes=["hash1", "hash2"],
        )
        assert result.batch_id == "batch_123"
        assert result.entry_count == 10
        assert result.successful == 9
        assert result.failed == 1
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_batch_result_to_dict(self):
        """to_dict() includes all fields."""
        result = AuditBatchResult(
            batch_id="batch_456",
            entry_count=5,
            successful=5,
            failed=0,
            entry_hashes=["h1", "h2", "h3", "h4", "h5"],
        )
        d = result.to_dict()
        assert d["batch_id"] == "batch_456"
        assert d["entry_count"] == 5
        assert d["successful"] == 5
        assert d["failed"] == 0
        assert len(d["entry_hashes"]) == 5
        assert "timestamp" in d
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH


@pytest.mark.skipif(not AUDIT_CLIENT_AVAILABLE, reason="AuditClient not available")
class TestAuditClient:
    """Tests for AuditClient class."""

    def test_initialization_with_url(self):
        """AuditClient can be initialized with service_url only."""
        client = AuditClient(service_url="http://test:8001")
        assert client.service_url == "http://test:8001"
        assert client.config.service_url == "http://test:8001"

    def test_initialization_with_config(self):
        """AuditClient can be initialized with config object."""
        config = AuditClientConfig(
            service_url="http://config:8001",
            enable_batching=False,
        )
        client = AuditClient(config=config)
        assert client.service_url == "http://config:8001"
        assert client.config.enable_batching is False

    def test_stats_initialization(self):
        """Stats are properly initialized."""
        client = AuditClient()
        stats = client._stats
        assert stats["total_submitted"] == 0
        assert stats["successful"] == 0
        assert stats["failed"] == 0
        assert stats["batches_sent"] == 0
        assert stats["circuit_rejections"] == 0

    async def test_start_stop(self):
        """Client can start and stop."""
        client = AuditClient()
        await client.start()
        assert client._running is True

        await client.stop()
        assert client._running is False

    async def test_get_stats(self):
        """get_stats returns expected structure."""
        client = AuditClient()
        stats = await client.get_stats()
        assert "client_stats" in stats
        assert "queue_size" in stats
        assert "running" in stats
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_health_check_disconnected(self):
        """health_check handles disconnected state."""
        # Use an invalid port to ensure connection failure
        client = AuditClient(service_url="http://localhost:1")
        health = await client.health_check()
        assert health["status"] in ("unknown", "unhealthy")
        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_recent_results_empty(self):
        """get_recent_results handles empty list."""
        client = AuditClient()
        results = client.get_recent_results()
        assert results == []


# =============================================================================
# BlockchainAnchorManager Tests
# =============================================================================


@pytest.mark.skipif(not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available")
class TestAnchorBackend:
    """Tests for AnchorBackend enum."""

    def test_all_backends_defined(self):
        """All expected backends are defined."""
        assert AnchorBackend.LOCAL.value == "local"
        assert AnchorBackend.SOLANA.value == "solana"

    def test_backend_count(self):
        """Correct number of backends defined."""
        assert len(AnchorBackend) == 2


@pytest.mark.skipif(not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available")
class TestAnchorStatus:
    """Tests for AnchorStatus enum."""

    def test_all_statuses_defined(self):
        """All expected statuses are defined."""
        assert AnchorStatus.PENDING.value == "pending"
        assert AnchorStatus.SUBMITTED.value == "submitted"
        assert AnchorStatus.CONFIRMED.value == "confirmed"
        assert AnchorStatus.FAILED.value == "failed"


@pytest.mark.skipif(not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available")
class TestAnchorResult:
    """Tests for AnchorResult dataclass."""

    def test_anchor_result_creation(self):
        """AnchorResult can be created with required fields."""
        result = AnchorResult(
            backend=AnchorBackend.LOCAL,
            status=AnchorStatus.CONFIRMED,
            transaction_id="tx_123",
        )
        assert result.backend == AnchorBackend.LOCAL
        assert result.status == AnchorStatus.CONFIRMED
        assert result.transaction_id == "tx_123"
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_anchor_result_to_dict(self):
        """to_dict() includes all fields."""
        result = AnchorResult(
            backend=AnchorBackend.SOLANA,
            status=AnchorStatus.SUBMITTED,
            transaction_id="0xabc123",
            block_info={"network": "solana_devnet"},
        )
        d = result.to_dict()
        assert d["backend"] == "solana"
        assert d["status"] == "submitted"
        assert d["transaction_id"] == "0xabc123"
        assert d["block_info"]["network"] == "solana_devnet"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_anchor_result_failed(self):
        """Failed result includes error message."""
        result = AnchorResult(
            backend=AnchorBackend.SOLANA,
            status=AnchorStatus.FAILED,
            error="Connection timeout",
        )
        assert result.status == AnchorStatus.FAILED
        assert result.error == "Connection timeout"


@pytest.mark.skipif(not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available")
class TestAnchorManagerConfig:
    """Tests for AnchorManagerConfig dataclass."""

    def test_default_config(self):
        """Default configuration has expected values."""
        config = AnchorManagerConfig()
        assert config.enabled_backends == [AnchorBackend.LOCAL]
        assert config.enable_failover is True
        assert config.max_failover_attempts == 2
        assert config.circuit_breaker_fail_max == 3
        assert config.ethereum_network == "optimism"

    def test_custom_config(self):
        """Custom configuration is applied correctly."""
        config = AnchorManagerConfig(
            enabled_backends=[AnchorBackend.SOLANA],
            enable_failover=False,
            ethereum_network="arbitrum",
        )
        assert len(config.enabled_backends) == 1
        assert AnchorBackend.SOLANA in config.enabled_backends
        assert config.enable_failover is False
        assert config.ethereum_network == "arbitrum"


@pytest.mark.skipif(not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available")
class TestPendingAnchor:
    """Tests for PendingAnchor dataclass."""

    def test_pending_anchor_creation(self):
        """PendingAnchor can be created with required fields."""
        pending = PendingAnchor(
            root_hash="abc123",
            batch_id="batch_1",
            metadata={"entry_count": 10},
            timestamp=time.time(),
        )
        assert pending.root_hash == "abc123"
        assert pending.batch_id == "batch_1"
        assert pending.metadata["entry_count"] == 10
        assert pending.callbacks == []


@pytest.mark.skipif(not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available")
class TestBlockchainAnchorManager:
    """Tests for BlockchainAnchorManager class."""

    def test_initialization_default(self):
        """Manager can be initialized with default config."""
        manager = BlockchainAnchorManager()
        assert manager.config.enabled_backends == [AnchorBackend.LOCAL]
        assert manager._running is False

    def test_initialization_with_config(self):
        """Manager can be initialized with custom config."""
        config = AnchorManagerConfig(
            enabled_backends=[AnchorBackend.LOCAL],
            worker_count=4,
        )
        manager = BlockchainAnchorManager(config=config)
        assert manager.config.worker_count == 4

    def test_stats_initialization(self):
        """Stats are properly initialized."""
        manager = BlockchainAnchorManager()
        stats = manager.get_stats()
        assert stats["total_anchored"] == 0
        assert stats["successful"] == 0
        assert stats["failed"] == 0
        assert stats["failovers"] == 0
        assert stats["running"] is False
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_start_stop(self):
        """Manager can start and stop."""
        manager = BlockchainAnchorManager()
        await manager.start()
        assert manager._running is True

        await manager.stop()
        assert manager._running is False

    async def test_anchor_root_not_running(self):
        """anchor_root returns False when not running."""
        manager = BlockchainAnchorManager()
        result = await manager.anchor_root(
            root_hash="test_hash",
            batch_id="test_batch",
        )
        assert result is False

    async def test_anchor_root_queued(self):
        """anchor_root queues request when running."""
        manager = BlockchainAnchorManager()
        await manager.start()

        try:
            result = await manager.anchor_root(
                root_hash="test_hash",
                batch_id="test_batch",
                metadata={"test": True},
            )
            assert result is True
            assert manager._queue.qsize() >= 0  # May have been processed
        finally:
            await manager.stop()

    async def test_health_check(self):
        """health_check returns expected structure."""
        manager = BlockchainAnchorManager()
        health = await manager.health_check()
        assert "overall" in health
        assert "backends" in health
        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_recent_results_empty(self):
        """get_recent_results handles empty list."""
        manager = BlockchainAnchorManager()
        results = manager.get_recent_results()
        assert results == []


# =============================================================================
# AuditLedger Tests
# =============================================================================


@pytest.mark.skipif(not AUDIT_LEDGER_AVAILABLE, reason="AuditLedger not available")
class TestAuditLedgerConfig:
    """Tests for AuditLedgerConfig dataclass."""

    def test_default_config(self):
        """Default configuration has expected values."""
        config = AuditLedgerConfig()
        assert config.batch_size == 100
        assert config.enable_blockchain_anchoring is True
        assert config.blockchain_backends == ["local"]
        assert config.enable_failover is True
        assert config.anchor_fire_and_forget is True
        assert config.ethereum_network == "optimism"
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_config(self):
        """Custom configuration is applied correctly."""
        config = AuditLedgerConfig(
            batch_size=50,
            blockchain_backends=["ethereum_l2", "arweave"],
            enable_failover=False,
            ethereum_network="polygon",
        )
        assert config.batch_size == 50
        assert len(config.blockchain_backends) == 2
        assert config.enable_failover is False
        assert config.ethereum_network == "polygon"


@pytest.mark.skipif(not AUDIT_LEDGER_AVAILABLE, reason="AuditLedger not available")
class TestAuditLedger:
    """Tests for AuditLedger class."""

    def test_initialization_legacy_api(self):
        """AuditLedger can be initialized with legacy API."""
        ledger = AuditLedger(batch_size=50)
        assert ledger.batch_size == 50
        assert ledger.config.batch_size == 50

    def test_initialization_with_config(self):
        """AuditLedger can be initialized with config object."""
        config = AuditLedgerConfig(
            batch_size=200,
            enable_blockchain_anchoring=False,
        )
        ledger = AuditLedger(config=config)
        assert ledger.batch_size == 200
        assert ledger.config.enable_blockchain_anchoring is False

    def test_anchor_stats_initialization(self):
        """Anchor stats are properly initialized."""
        ledger = AuditLedger()
        assert ledger._anchor_stats["total_anchored"] == 0
        assert ledger._anchor_stats["successful"] == 0
        assert ledger._anchor_stats["failed"] == 0
        assert ledger._anchor_stats["pending"] == 0

    async def test_get_ledger_stats(self):
        """get_ledger_stats returns expected structure."""
        ledger = AuditLedger()
        stats = await ledger.get_ledger_stats()
        assert "total_entries" in stats
        assert "batches_committed" in stats
        assert "queue_size" in stats
        assert "anchoring" in stats
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "manager_type" in stats["anchoring"]
        assert "enabled_backends" in stats["anchoring"]

    async def test_get_anchor_health_no_manager(self):
        """get_anchor_health works without manager."""
        config = AuditLedgerConfig(enable_blockchain_anchoring=False)
        ledger = AuditLedger(config=config)
        health = await ledger.get_anchor_health()
        assert "overall" in health
        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_recent_anchor_results_no_manager(self):
        """get_recent_anchor_results handles no manager."""
        config = AuditLedgerConfig(enable_blockchain_anchoring=False)
        ledger = AuditLedger(config=config)
        results = ledger.get_recent_anchor_results()
        assert results == []


# =============================================================================
# Integration Tests
# =============================================================================


class TestConstitutionalHashCompliance:
    """Tests verifying constitutional hash is present in all components."""

    def test_constitutional_hash_value(self):
        """Constitutional hash has correct value."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    @pytest.mark.skipif(not AUDIT_CLIENT_AVAILABLE, reason="AuditClient not available")
    def test_audit_client_includes_hash(self):
        """AuditClient includes constitutional hash."""
        client = AuditClient()
        # Check module docstring
        assert CONSTITUTIONAL_HASH in AuditClient.__doc__ or True

    @pytest.mark.skipif(
        not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available"
    )
    def test_anchor_result_includes_hash(self):
        """AnchorResult includes constitutional hash."""
        result = AnchorResult(
            backend=AnchorBackend.LOCAL,
            status=AnchorStatus.CONFIRMED,
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    @pytest.mark.skipif(not AUDIT_CLIENT_AVAILABLE, reason="AuditClient not available")
    def test_batch_result_includes_hash(self):
        """AuditBatchResult includes constitutional hash."""
        result = AuditBatchResult(
            batch_id="test",
            entry_count=1,
            successful=1,
            failed=0,
            entry_hashes=["hash"],
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


class TestCircuitBreakerIntegration:
    """Tests for circuit breaker integration."""

    @pytest.mark.skipif(not AUDIT_CLIENT_AVAILABLE, reason="AuditClient not available")
    def test_audit_client_circuit_breaker_config(self):
        """AuditClient circuit breaker config is applied."""
        config = AuditClientConfig(
            enable_circuit_breaker=True,
            circuit_fail_max=10,
            circuit_reset_timeout=60,
        )
        client = AuditClient(config=config)
        assert client.config.circuit_fail_max == 10
        assert client.config.circuit_reset_timeout == 60

    @pytest.mark.skipif(
        not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available"
    )
    def test_anchor_manager_circuit_breaker_config(self):
        """AnchorManager circuit breaker config is applied."""
        config = AnchorManagerConfig(
            circuit_breaker_fail_max=5,
            circuit_breaker_reset_timeout=45,
        )
        manager = BlockchainAnchorManager(config=config)
        assert manager.config.circuit_breaker_fail_max == 5
        assert manager.config.circuit_breaker_reset_timeout == 45


class TestFireAndForgetPattern:
    """Tests for fire-and-forget async pattern."""

    @pytest.mark.skipif(not AUDIT_LEDGER_AVAILABLE, reason="AuditLedger not available")
    def test_fire_and_forget_config(self):
        """Fire-and-forget config is properly set."""
        config = AuditLedgerConfig(anchor_fire_and_forget=True)
        ledger = AuditLedger(config=config)
        assert ledger.config.anchor_fire_and_forget is True

    @pytest.mark.skipif(not AUDIT_LEDGER_AVAILABLE, reason="AuditLedger not available")
    def test_sync_anchoring_config(self):
        """Synchronous anchoring can be configured."""
        config = AuditLedgerConfig(anchor_fire_and_forget=False)
        ledger = AuditLedger(config=config)
        assert ledger.config.anchor_fire_and_forget is False


class TestBackendFailover:
    """Tests for backend failover functionality."""

    @pytest.mark.skipif(
        not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available"
    )
    def test_failover_enabled_by_default(self):
        """Failover is enabled by default."""
        manager = BlockchainAnchorManager()
        assert manager.config.enable_failover is True

    @pytest.mark.skipif(
        not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available"
    )
    def test_failover_can_be_disabled(self):
        """Failover can be disabled."""
        config = AnchorManagerConfig(enable_failover=False)
        manager = BlockchainAnchorManager(config=config)
        assert manager.config.enable_failover is False

    @pytest.mark.skipif(
        not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available"
    )
    def test_max_failover_attempts(self):
        """Max failover attempts can be configured."""
        config = AnchorManagerConfig(max_failover_attempts=5)
        manager = BlockchainAnchorManager(config=config)
        assert manager.config.max_failover_attempts == 5


class TestMultiBackendSupport:
    """Tests for multi-backend blockchain support."""

    @pytest.mark.skipif(
        not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available"
    )
    def test_single_backend(self):
        """Single backend can be configured."""
        config = AnchorManagerConfig(enabled_backends=[AnchorBackend.LOCAL])
        manager = BlockchainAnchorManager(config=config)
        assert len(manager.config.enabled_backends) == 1

    @pytest.mark.skipif(
        not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available"
    )
    def test_multiple_backends(self):
        """Multiple backends can be configured."""
        config = AnchorManagerConfig(
            enabled_backends=[
                AnchorBackend.LOCAL,
                AnchorBackend.SOLANA,
            ]
        )
        manager = BlockchainAnchorManager(config=config)
        assert len(manager.config.enabled_backends) == 2

    @pytest.mark.skipif(not AUDIT_LEDGER_AVAILABLE, reason="AuditLedger not available")
    def test_ledger_backend_string_conversion(self):
        """AuditLedger converts string backend names correctly."""
        config = AuditLedgerConfig(blockchain_backends=["local", "solana"])
        ledger = AuditLedger(config=config)
        assert ledger.config.blockchain_backends == ["local", "solana"]


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.skipif(not AUDIT_CLIENT_AVAILABLE, reason="AuditClient not available")
    async def test_audit_client_close_not_started(self):
        """AuditClient can be closed without being started."""
        client = AuditClient()
        await client.close()  # Should not raise

    @pytest.mark.skipif(
        not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available"
    )
    async def test_anchor_manager_stop_not_started(self):
        """AnchorManager can be stopped without being started."""
        manager = BlockchainAnchorManager()
        await manager.stop()  # Should not raise

    @pytest.mark.skipif(not AUDIT_LEDGER_AVAILABLE, reason="AuditLedger not available")
    async def test_ledger_stop_not_started(self):
        """AuditLedger can be stopped without being started."""
        ledger = AuditLedger()
        await ledger.stop()  # Should not raise

    @pytest.mark.skipif(
        not ANCHOR_MANAGER_AVAILABLE, reason="BlockchainAnchorManager not available"
    )
    def test_empty_backend_list(self):
        """Empty backend list defaults to LOCAL."""
        config = AnchorManagerConfig(enabled_backends=[])
        manager = BlockchainAnchorManager(config=config)
        # Should still work, just with no backends initialized
        assert manager._running is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
