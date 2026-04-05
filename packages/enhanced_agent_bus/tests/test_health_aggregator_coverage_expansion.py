"""
ACGS-2 Enhanced Agent Bus - Health Aggregator Coverage Expansion Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests to expand health_aggregator.py coverage from 52.59% to 70%+.
"""

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

from health_aggregator import (
    CONSTITUTIONAL_HASH,
    HealthAggregator,
    HealthAggregatorConfig,
    HealthSnapshot,
    SystemHealthReport,
    SystemHealthStatus,
    get_health_aggregator,
    reset_health_aggregator,
)

# =============================================================================
# HealthSnapshot Tests
# =============================================================================


class TestHealthSnapshot:
    """Tests for HealthSnapshot dataclass."""

    def test_snapshot_creation(self) -> None:
        """Test creating a HealthSnapshot."""
        timestamp = datetime.now(UTC)
        snapshot = HealthSnapshot(
            timestamp=timestamp,
            status=SystemHealthStatus.HEALTHY,
            health_score=1.0,
            total_breakers=5,
            closed_breakers=5,
            half_open_breakers=0,
            open_breakers=0,
            circuit_states={"service_a": "closed", "service_b": "closed"},
        )
        assert snapshot.status == SystemHealthStatus.HEALTHY
        assert snapshot.health_score == 1.0
        assert snapshot.total_breakers == 5
        assert snapshot.constitutional_hash == CONSTITUTIONAL_HASH

    def test_snapshot_to_dict(self) -> None:
        """Test HealthSnapshot to_dict conversion."""
        timestamp = datetime.now(UTC)
        snapshot = HealthSnapshot(
            timestamp=timestamp,
            status=SystemHealthStatus.DEGRADED,
            health_score=0.6,
            total_breakers=4,
            closed_breakers=2,
            half_open_breakers=1,
            open_breakers=1,
            circuit_states={"svc1": "closed", "svc2": "open"},
        )
        d = snapshot.to_dict()
        assert d["status"] == "degraded"
        assert d["health_score"] == 0.6
        assert d["total_breakers"] == 4
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "timestamp" in d


# =============================================================================
# SystemHealthReport Tests
# =============================================================================


class TestSystemHealthReport:
    """Tests for SystemHealthReport dataclass."""

    def test_report_creation(self) -> None:
        """Test creating a SystemHealthReport."""
        timestamp = datetime.now(UTC)
        report = SystemHealthReport(
            status=SystemHealthStatus.CRITICAL,
            health_score=0.3,
            timestamp=timestamp,
            total_breakers=3,
            closed_breakers=1,
            half_open_breakers=0,
            open_breakers=2,
            circuit_details={"svc": {"state": "open", "fail_counter": 5}},
            degraded_services=[],
            critical_services=["svc"],
        )
        assert report.status == SystemHealthStatus.CRITICAL
        assert report.health_score == 0.3
        assert len(report.critical_services) == 1

    def test_report_to_dict(self) -> None:
        """Test SystemHealthReport to_dict conversion."""
        timestamp = datetime.now(UTC)
        report = SystemHealthReport(
            status=SystemHealthStatus.HEALTHY,
            health_score=0.95,
            timestamp=timestamp,
            total_breakers=2,
            closed_breakers=2,
            half_open_breakers=0,
            open_breakers=0,
            circuit_details={
                "audit": {"state": "closed", "fail_counter": 0},
                "policy": {"state": "closed", "fail_counter": 0},
            },
            degraded_services=[],
            critical_services=[],
        )
        d = report.to_dict()
        assert d["status"] == "healthy"
        assert d["health_score"] == 0.95
        assert d["total_breakers"] == 2
        assert d["degraded_services"] == []
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# HealthAggregatorConfig Tests
# =============================================================================


class TestHealthAggregatorConfig:
    """Tests for HealthAggregatorConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = HealthAggregatorConfig()
        assert config.enabled is True
        assert config.history_window_minutes == 5
        assert config.max_history_size == 300
        assert config.health_check_interval_seconds == 1.0
        assert config.degraded_threshold == 0.7
        assert config.critical_threshold == 0.5
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = HealthAggregatorConfig(
            enabled=False,
            history_window_minutes=10,
            max_history_size=600,
            health_check_interval_seconds=2.0,
            degraded_threshold=0.8,
            critical_threshold=0.6,
            constitutional_hash="custom_hash",
        )
        assert config.enabled is False
        assert config.history_window_minutes == 10
        assert config.max_history_size == 600
        assert config.health_check_interval_seconds == 2.0
        assert config.degraded_threshold == 0.8
        assert config.critical_threshold == 0.6
        assert config.constitutional_hash == "custom_hash"


# =============================================================================
# HealthAggregator Initialization Tests
# =============================================================================


class TestHealthAggregatorInitialization:
    """Tests for HealthAggregator initialization."""

    def test_default_initialization(self) -> None:
        """Test default initialization."""
        aggregator = HealthAggregator()
        assert aggregator.config is not None
        assert aggregator._running is False
        assert aggregator._snapshots_collected == 0
        assert aggregator._callbacks_fired == 0

    def test_with_custom_config(self) -> None:
        """Test initialization with custom config."""
        config = HealthAggregatorConfig(
            enabled=True,
            history_window_minutes=10,
        )
        aggregator = HealthAggregator(config=config)
        assert aggregator.config.history_window_minutes == 10


# =============================================================================
# Health Score Calculation Tests
# =============================================================================


class TestHealthScoreCalculation:
    """Tests for health score calculation."""

    def test_score_all_closed(self) -> None:
        """Test health score when all breakers are closed."""
        aggregator = HealthAggregator()
        score = aggregator._calculate_health_score(total=5, closed=5, half_open=0, open=0)
        assert score == 1.0

    def test_score_all_open(self) -> None:
        """Test health score when all breakers are open."""
        aggregator = HealthAggregator()
        score = aggregator._calculate_health_score(total=5, closed=0, half_open=0, open=5)
        assert score == 0.0

    def test_score_half_open_weight(self) -> None:
        """Test health score with half-open breakers (0.5 weight)."""
        aggregator = HealthAggregator()
        score = aggregator._calculate_health_score(total=4, closed=0, half_open=4, open=0)
        assert score == 0.5

    def test_score_mixed(self) -> None:
        """Test health score with mixed states."""
        aggregator = HealthAggregator()
        # 2 closed (2.0) + 1 half-open (0.5) + 1 open (0.0) = 2.5 / 4 = 0.625
        score = aggregator._calculate_health_score(total=4, closed=2, half_open=1, open=1)
        assert score == 0.625

    def test_score_no_breakers(self) -> None:
        """Test health score with no breakers (default healthy)."""
        aggregator = HealthAggregator()
        score = aggregator._calculate_health_score(total=0, closed=0, half_open=0, open=0)
        assert score == 1.0  # No breakers = healthy


# =============================================================================
# Health Status Determination Tests
# =============================================================================


class TestHealthStatusDetermination:
    """Tests for health status determination."""

    def test_status_healthy(self) -> None:
        """Test HEALTHY status determination."""
        config = HealthAggregatorConfig(
            degraded_threshold=0.7,
            critical_threshold=0.5,
        )
        aggregator = HealthAggregator(config=config)

        # 0.8 >= 0.7 = HEALTHY
        status = aggregator._determine_health_status(0.8)
        assert status == SystemHealthStatus.HEALTHY

        # Exactly at threshold
        status = aggregator._determine_health_status(0.7)
        assert status == SystemHealthStatus.HEALTHY

    def test_status_degraded(self) -> None:
        """Test DEGRADED status determination."""
        config = HealthAggregatorConfig(
            degraded_threshold=0.7,
            critical_threshold=0.5,
        )
        aggregator = HealthAggregator(config=config)

        # 0.6 < 0.7 and >= 0.5 = DEGRADED
        status = aggregator._determine_health_status(0.6)
        assert status == SystemHealthStatus.DEGRADED

        # Exactly at critical threshold
        status = aggregator._determine_health_status(0.5)
        assert status == SystemHealthStatus.DEGRADED

    def test_status_critical(self) -> None:
        """Test CRITICAL status determination."""
        config = HealthAggregatorConfig(
            degraded_threshold=0.7,
            critical_threshold=0.5,
        )
        aggregator = HealthAggregator(config=config)

        # 0.4 < 0.5 = CRITICAL
        status = aggregator._determine_health_status(0.4)
        assert status == SystemHealthStatus.CRITICAL

        # 0.0 = CRITICAL
        status = aggregator._determine_health_status(0.0)
        assert status == SystemHealthStatus.CRITICAL


# =============================================================================
# Circuit Breaker Registration Tests
# =============================================================================


class TestCircuitBreakerRegistration:
    """Tests for circuit breaker registration."""

    def test_register_circuit_breaker(self) -> None:
        """Test registering a circuit breaker."""
        aggregator = HealthAggregator()

        mock_breaker = MagicMock()
        mock_breaker.current_state = "closed"

        aggregator.register_circuit_breaker("test_breaker", mock_breaker)
        assert "test_breaker" in aggregator._custom_breakers

    def test_unregister_circuit_breaker(self) -> None:
        """Test unregistering a circuit breaker."""
        aggregator = HealthAggregator()

        mock_breaker = MagicMock()
        aggregator.register_circuit_breaker("test_breaker", mock_breaker)
        assert "test_breaker" in aggregator._custom_breakers

        aggregator.unregister_circuit_breaker("test_breaker")
        assert "test_breaker" not in aggregator._custom_breakers

    def test_unregister_nonexistent(self) -> None:
        """Test unregistering a non-existent breaker (no error)."""
        aggregator = HealthAggregator()
        # Should not raise
        aggregator.unregister_circuit_breaker("nonexistent")


# =============================================================================
# Health Change Callback Tests
# =============================================================================


class TestHealthChangeCallbacks:
    """Tests for health change callbacks."""

    def test_register_callback(self) -> None:
        """Test registering a health change callback."""
        aggregator = HealthAggregator()

        def my_callback(report):
            pass

        aggregator.on_health_change(my_callback)
        assert len(aggregator._health_change_callbacks) == 1

    def test_multiple_callbacks(self) -> None:
        """Test registering multiple callbacks."""
        aggregator = HealthAggregator()

        def cb1(report):
            pass

        def cb2(report):
            pass

        aggregator.on_health_change(cb1)
        aggregator.on_health_change(cb2)
        assert len(aggregator._health_change_callbacks) == 2

    async def test_invoke_sync_callback(self) -> None:
        """Test invoking a synchronous callback."""
        aggregator = HealthAggregator()
        callback_called = []

        def sync_callback(report):
            callback_called.append(report.status)

        report = SystemHealthReport(
            status=SystemHealthStatus.HEALTHY,
            health_score=1.0,
            timestamp=datetime.now(UTC),
            total_breakers=0,
            closed_breakers=0,
            half_open_breakers=0,
            open_breakers=0,
            circuit_details={},
        )

        await aggregator._invoke_callback(sync_callback, report)
        assert callback_called == [SystemHealthStatus.HEALTHY]

    async def test_invoke_async_callback(self) -> None:
        """Test invoking an async callback."""
        aggregator = HealthAggregator()
        callback_called = []

        async def async_callback(report):
            callback_called.append(report.status)

        report = SystemHealthReport(
            status=SystemHealthStatus.DEGRADED,
            health_score=0.6,
            timestamp=datetime.now(UTC),
            total_breakers=2,
            closed_breakers=1,
            half_open_breakers=1,
            open_breakers=0,
            circuit_details={},
        )

        await aggregator._invoke_callback(async_callback, report)
        assert callback_called == [SystemHealthStatus.DEGRADED]

    async def test_invoke_callback_handles_error(self) -> None:
        """Test that callback errors are caught and logged."""
        aggregator = HealthAggregator()

        def failing_callback(report):
            raise RuntimeError("Callback error")

        report = SystemHealthReport(
            status=SystemHealthStatus.HEALTHY,
            health_score=1.0,
            timestamp=datetime.now(UTC),
            total_breakers=0,
            closed_breakers=0,
            half_open_breakers=0,
            open_breakers=0,
            circuit_details={},
        )

        # Should not raise
        await aggregator._invoke_callback(failing_callback, report)


# =============================================================================
# Get System Health Tests (Without Circuit Breaker)
# =============================================================================


class TestGetSystemHealthWithoutCircuitBreaker:
    """Tests for get_system_health when circuit breaker not available."""

    def test_returns_unknown_status(self) -> None:
        """Test that UNKNOWN status is returned when CB not available."""
        with patch("health_aggregator.CIRCUIT_BREAKER_AVAILABLE", False):
            aggregator = HealthAggregator()
            report = aggregator.get_system_health()

            assert report.status == SystemHealthStatus.UNKNOWN
            assert report.health_score == 0.0
            assert report.total_breakers == 0
            assert report.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# Get Health History Tests
# =============================================================================


class TestGetHealthHistory:
    """Tests for get_health_history method."""

    def test_empty_history(self) -> None:
        """Test getting history when empty."""
        aggregator = HealthAggregator()
        history = aggregator.get_health_history()
        assert history == []

    def test_with_snapshots(self) -> None:
        """Test getting history with snapshots."""
        aggregator = HealthAggregator()

        # Add some snapshots directly
        for _i in range(5):
            snapshot = HealthSnapshot(
                timestamp=datetime.now(UTC),
                status=SystemHealthStatus.HEALTHY,
                health_score=1.0,
                total_breakers=1,
                closed_breakers=1,
                half_open_breakers=0,
                open_breakers=0,
                circuit_states={"test": "closed"},
            )
            aggregator._health_history.append(snapshot)

        history = aggregator.get_health_history()
        assert len(history) == 5

    def test_custom_window(self) -> None:
        """Test getting history with custom window."""
        aggregator = HealthAggregator()

        # Add a snapshot with current time
        snapshot = HealthSnapshot(
            timestamp=datetime.now(UTC),
            status=SystemHealthStatus.HEALTHY,
            health_score=1.0,
            total_breakers=1,
            closed_breakers=1,
            half_open_breakers=0,
            open_breakers=0,
            circuit_states={},
        )
        aggregator._health_history.append(snapshot)

        # With 1 minute window, recent snapshot should be included
        history = aggregator.get_health_history(window_minutes=1)
        assert len(history) == 1

    def test_default_window(self) -> None:
        """Test that default window uses configured value."""
        config = HealthAggregatorConfig(history_window_minutes=10)
        aggregator = HealthAggregator(config=config)

        snapshot = HealthSnapshot(
            timestamp=datetime.now(UTC),
            status=SystemHealthStatus.HEALTHY,
            health_score=1.0,
            total_breakers=0,
            closed_breakers=0,
            half_open_breakers=0,
            open_breakers=0,
            circuit_states={},
        )
        aggregator._health_history.append(snapshot)

        # Should use 10 minute window
        history = aggregator.get_health_history()
        assert len(history) == 1


# =============================================================================
# Get Metrics Tests
# =============================================================================


class TestGetMetrics:
    """Tests for get_metrics method."""

    def test_metrics_structure(self) -> None:
        """Test that metrics have expected structure."""
        aggregator = HealthAggregator()
        metrics = aggregator.get_metrics()

        assert "snapshots_collected" in metrics
        assert "callbacks_fired" in metrics
        assert "history_size" in metrics
        assert "running" in metrics
        assert "enabled" in metrics
        assert "current_status" in metrics
        assert "current_health_score" in metrics
        assert "constitutional_hash" in metrics

    def test_metrics_values(self) -> None:
        """Test initial metrics values."""
        aggregator = HealthAggregator()
        metrics = aggregator.get_metrics()

        assert metrics["snapshots_collected"] == 0
        assert metrics["callbacks_fired"] == 0
        assert metrics["history_size"] == 0
        assert metrics["running"] is False
        assert metrics["enabled"] is True
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Start/Stop Lifecycle Tests
# =============================================================================


class TestAggregatorLifecycle:
    """Tests for HealthAggregator start/stop lifecycle."""

    async def test_start_when_disabled(self) -> None:
        """Test that start does nothing when disabled."""
        config = HealthAggregatorConfig(enabled=False)
        aggregator = HealthAggregator(config=config)

        await aggregator.start()

        assert aggregator._running is False
        assert aggregator._health_check_task is None

    async def test_start_without_circuit_breaker(self) -> None:
        """Test start when circuit breaker not available."""
        with patch("health_aggregator.CIRCUIT_BREAKER_AVAILABLE", False):
            aggregator = HealthAggregator()
            await aggregator.start()

            assert aggregator._running is False

    async def test_start_already_running(self) -> None:
        """Test that start is idempotent when already running."""
        aggregator = HealthAggregator()
        aggregator._running = True
        original_task = aggregator._health_check_task

        await aggregator.start()

        # Should not change
        assert aggregator._health_check_task is original_task

    async def test_stop_without_task(self) -> None:
        """Test stop when no task is running."""
        aggregator = HealthAggregator()
        aggregator._running = True

        await aggregator.stop()

        assert aggregator._running is False


# =============================================================================
# Global Functions Tests
# =============================================================================


class TestGlobalFunctions:
    """Tests for global health aggregator functions."""

    def test_get_health_aggregator_creates_singleton(self) -> None:
        """Test that get_health_aggregator creates a singleton."""
        reset_health_aggregator()

        agg1 = get_health_aggregator()
        agg2 = get_health_aggregator()

        assert agg1 is agg2

        reset_health_aggregator()

    def test_get_health_aggregator_with_config(self) -> None:
        """Test get_health_aggregator with custom config."""
        reset_health_aggregator()

        config = HealthAggregatorConfig(history_window_minutes=20)
        agg = get_health_aggregator(config)

        assert agg.config.history_window_minutes == 20

        reset_health_aggregator()

    def test_reset_health_aggregator(self) -> None:
        """Test reset_health_aggregator clears singleton."""
        reset_health_aggregator()

        agg1 = get_health_aggregator()
        reset_health_aggregator()
        agg2 = get_health_aggregator()

        assert agg1 is not agg2

        reset_health_aggregator()


# =============================================================================
# SystemHealthStatus Enum Tests
# =============================================================================


class TestSystemHealthStatus:
    """Tests for SystemHealthStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert SystemHealthStatus.HEALTHY.value == "healthy"
        assert SystemHealthStatus.DEGRADED.value == "degraded"
        assert SystemHealthStatus.CRITICAL.value == "critical"
        assert SystemHealthStatus.UNKNOWN.value == "unknown"


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_max_history_size_respected(self) -> None:
        """Test that max_history_size is respected."""
        config = HealthAggregatorConfig(max_history_size=5)
        aggregator = HealthAggregator(config=config)

        # Add more than max size
        for _i in range(10):
            snapshot = HealthSnapshot(
                timestamp=datetime.now(UTC),
                status=SystemHealthStatus.HEALTHY,
                health_score=1.0,
                total_breakers=0,
                closed_breakers=0,
                half_open_breakers=0,
                open_breakers=0,
                circuit_states={},
            )
            aggregator._health_history.append(snapshot)

        # Should only keep last 5
        assert len(aggregator._health_history) == 5

    def test_custom_breaker_without_current_state(self) -> None:
        """Test handling custom breaker without current_state attribute."""
        aggregator = HealthAggregator()

        # Mock breaker without current_state
        mock_breaker = MagicMock(spec=[])  # No attributes
        aggregator.register_circuit_breaker("no_state_breaker", mock_breaker)

        # Should not crash when getting health
        with patch("health_aggregator.CIRCUIT_BREAKER_AVAILABLE", True):
            with patch.object(aggregator, "_registry", None):
                report = aggregator.get_system_health()
                # Breaker should not be included since it has no state
                assert "no_state_breaker" not in report.circuit_details

    def test_health_score_precision(self) -> None:
        """Test that health score is properly rounded."""
        timestamp = datetime.now(UTC)
        snapshot = HealthSnapshot(
            timestamp=timestamp,
            status=SystemHealthStatus.HEALTHY,
            health_score=0.6666666666,  # Repeating decimal
            total_breakers=3,
            closed_breakers=2,
            half_open_breakers=0,
            open_breakers=1,
            circuit_states={},
        )
        d = snapshot.to_dict()
        # Should be rounded to 3 decimal places
        assert d["health_score"] == 0.667
