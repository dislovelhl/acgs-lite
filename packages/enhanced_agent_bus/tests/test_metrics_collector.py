"""
Tests for GovernanceMetricsCollector and related models.
Constitutional Hash: 608508a9bd224290
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.constitutional.metrics_collector import (
    GovernanceMetricsCollector,
    GovernanceMetricsSnapshot,
    MetricsComparison,
)

# ---------------------------------------------------------------------------
# GovernanceMetricsSnapshot tests
# ---------------------------------------------------------------------------


class TestGovernanceMetricsSnapshot:
    """Tests for the GovernanceMetricsSnapshot model."""

    def test_default_snapshot(self):
        snap = GovernanceMetricsSnapshot()
        assert snap.violations_rate == 0.0
        assert snap.governance_latency_p99 == 0.0
        assert snap.deliberation_success_rate == 0.0
        assert snap.maci_violations_count == 0
        assert snap.total_requests == 0
        assert snap.error_rate == 0.0
        assert snap.window_duration_seconds == 60

    def test_meets_targets_perfect(self):
        snap = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=4.0,
            deliberation_success_rate=0.96,
            maci_violations_count=0,
        )
        assert snap.meets_targets is True

    def test_meets_targets_fails_violations(self):
        snap = GovernanceMetricsSnapshot(
            violations_rate=0.01,
            governance_latency_p99=4.0,
            deliberation_success_rate=0.96,
            maci_violations_count=0,
        )
        assert snap.meets_targets is False

    def test_meets_targets_fails_latency(self):
        snap = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=6.0,
            deliberation_success_rate=0.96,
            maci_violations_count=0,
        )
        assert snap.meets_targets is False

    def test_meets_targets_fails_deliberation(self):
        snap = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=4.0,
            deliberation_success_rate=0.90,
            maci_violations_count=0,
        )
        assert snap.meets_targets is False

    def test_meets_targets_fails_maci(self):
        snap = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=4.0,
            deliberation_success_rate=0.96,
            maci_violations_count=1,
        )
        assert snap.meets_targets is False

    def test_health_score_perfect(self):
        snap = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=0.0,
            deliberation_success_rate=1.0,
            maci_violations_count=0,
            error_rate=0.0,
        )
        assert snap.health_score == 1.0

    def test_health_score_with_violations(self):
        snap = GovernanceMetricsSnapshot(violations_rate=1.0)
        assert snap.health_score < 1.0
        # violations_penalty = min(0.3, 1.0 * 0.3) = 0.3
        assert snap.health_score <= 0.7

    def test_health_score_with_high_latency(self):
        snap = GovernanceMetricsSnapshot(governance_latency_p99=55.0)
        assert snap.health_score < 1.0

    def test_health_score_with_low_deliberation(self):
        snap = GovernanceMetricsSnapshot(deliberation_success_rate=0.5)
        assert snap.health_score < 1.0

    def test_health_score_with_maci_violations(self):
        snap = GovernanceMetricsSnapshot(maci_violations_count=10)
        assert snap.health_score < 1.0

    def test_health_score_with_errors(self):
        snap = GovernanceMetricsSnapshot(error_rate=1.0)
        assert snap.health_score < 1.0

    def test_health_score_minimum_zero(self):
        snap = GovernanceMetricsSnapshot(
            violations_rate=1.0,
            governance_latency_p99=100.0,
            deliberation_success_rate=0.0,
            maci_violations_count=100,
            error_rate=1.0,
        )
        assert snap.health_score >= 0.0

    def test_constitutional_version_pattern(self):
        snap = GovernanceMetricsSnapshot(constitutional_version="1.2.3")
        assert snap.constitutional_version == "1.2.3"


# ---------------------------------------------------------------------------
# MetricsComparison tests
# ---------------------------------------------------------------------------


class TestMetricsComparison:
    """Tests for MetricsComparison model."""

    def test_no_degradation(self):
        baseline = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=2.0,
            deliberation_success_rate=0.98,
            maci_violations_count=0,
            error_rate=0.0,
        )
        current = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=2.0,
            deliberation_success_rate=0.98,
            maci_violations_count=0,
            error_rate=0.0,
        )
        comp = MetricsComparison(baseline=baseline, current=current)
        assert comp.has_degradation is False
        assert len(comp.degradation_reasons) == 0

    def test_violations_degradation(self):
        baseline = GovernanceMetricsSnapshot(violations_rate=0.0)
        current = GovernanceMetricsSnapshot(violations_rate=0.05)
        comp = MetricsComparison(baseline=baseline, current=current)
        assert comp.has_degradation is True
        assert comp.violations_rate_delta == pytest.approx(0.05)
        assert any("violations" in r.lower() for r in comp.degradation_reasons)

    def test_latency_degradation(self):
        baseline = GovernanceMetricsSnapshot(governance_latency_p99=2.0)
        current = GovernanceMetricsSnapshot(governance_latency_p99=5.0)
        comp = MetricsComparison(baseline=baseline, current=current)
        assert comp.has_degradation is True
        assert comp.latency_p99_delta == pytest.approx(3.0)

    def test_deliberation_degradation(self):
        baseline = GovernanceMetricsSnapshot(deliberation_success_rate=0.98)
        current = GovernanceMetricsSnapshot(deliberation_success_rate=0.80)
        comp = MetricsComparison(baseline=baseline, current=current)
        assert comp.has_degradation is True
        assert comp.deliberation_success_rate_delta == pytest.approx(-0.18)

    def test_maci_violations_degradation(self):
        baseline = GovernanceMetricsSnapshot(maci_violations_count=0)
        current = GovernanceMetricsSnapshot(maci_violations_count=5)
        comp = MetricsComparison(baseline=baseline, current=current)
        assert comp.has_degradation is True
        assert comp.maci_violations_delta == 5

    def test_error_rate_degradation(self):
        baseline = GovernanceMetricsSnapshot(error_rate=0.01)
        current = GovernanceMetricsSnapshot(error_rate=0.10)
        comp = MetricsComparison(baseline=baseline, current=current)
        assert comp.has_degradation is True
        assert comp.error_rate_delta == pytest.approx(0.09)

    def test_health_score_degradation(self):
        baseline = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=1.0,
            deliberation_success_rate=0.99,
            maci_violations_count=0,
            error_rate=0.0,
        )
        current = GovernanceMetricsSnapshot(
            violations_rate=0.5,
            governance_latency_p99=50.0,
            deliberation_success_rate=0.5,
            maci_violations_count=10,
            error_rate=0.5,
        )
        comp = MetricsComparison(baseline=baseline, current=current)
        assert comp.has_degradation is True
        assert comp.health_score_delta < 0


# ---------------------------------------------------------------------------
# GovernanceMetricsCollector tests
# ---------------------------------------------------------------------------


class TestGovernanceMetricsCollector:
    """Tests for GovernanceMetricsCollector service."""

    def test_init_defaults(self):
        collector = GovernanceMetricsCollector()
        assert collector.snapshot_retention_hours == 168
        assert collector.measurement_window_seconds == 60
        assert collector.redis_client is None

    def test_init_custom(self):
        collector = GovernanceMetricsCollector(
            redis_url="redis://custom:6379",
            snapshot_retention_hours=48,
            measurement_window_seconds=120,
        )
        assert collector.redis_url == "redis://custom:6379"
        assert collector.snapshot_retention_hours == 48
        assert collector.measurement_window_seconds == 120

    @pytest.mark.asyncio
    async def test_collect_snapshot_no_redis(self):
        collector = GovernanceMetricsCollector()
        collector.redis_client = None
        snap = await collector.collect_snapshot()
        assert isinstance(snap, GovernanceMetricsSnapshot)
        assert snap.total_requests == 0

    @pytest.mark.asyncio
    async def test_collect_snapshot_no_redis_with_version(self):
        collector = GovernanceMetricsCollector()
        collector.redis_client = None
        snap = await collector.collect_snapshot(constitutional_version="1.0.0")
        assert snap.constitutional_version == "1.0.0"

    @pytest.mark.asyncio
    async def test_record_governance_decision_no_redis(self):
        collector = GovernanceMetricsCollector()
        collector.redis_client = None
        # Should not raise
        await collector.record_governance_decision(latency_ms=1.0, approved=True)

    @pytest.mark.asyncio
    async def test_record_maci_violation_no_redis(self):
        collector = GovernanceMetricsCollector()
        collector.redis_client = None
        await collector.record_maci_violation(agent_id="agent-1", action="approve", role="judicial")

    @pytest.mark.asyncio
    async def test_record_deliberation_outcome_no_redis(self):
        collector = GovernanceMetricsCollector()
        collector.redis_client = None
        await collector.record_deliberation_outcome(success=True)

    @pytest.mark.asyncio
    async def test_get_baseline_snapshot_no_redis(self):
        collector = GovernanceMetricsCollector()
        collector.redis_client = None
        result = await collector.get_baseline_snapshot("1.0.0")
        assert result is None

    @pytest.mark.asyncio
    async def test_store_baseline_snapshot_no_redis(self):
        collector = GovernanceMetricsCollector()
        collector.redis_client = None
        snap = GovernanceMetricsSnapshot()
        # Should not raise
        await collector.store_baseline_snapshot(snap, "1.0.0")

    @pytest.mark.asyncio
    async def test_disconnect_no_client(self):
        collector = GovernanceMetricsCollector()
        collector.redis_client = None
        await collector.disconnect()  # Should not raise

    @pytest.mark.asyncio
    async def test_disconnect_with_client(self):
        collector = GovernanceMetricsCollector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client
        await collector.disconnect()
        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_error_handled(self):
        collector = GovernanceMetricsCollector()
        mock_client = AsyncMock()
        mock_client.close.side_effect = RuntimeError("close failed")
        collector.redis_client = mock_client
        await collector.disconnect()  # Should not raise

    def test_compute_percentiles_empty(self):
        collector = GovernanceMetricsCollector()
        p50, p95, p99 = collector._compute_percentiles([])
        assert p50 == 0.0
        assert p95 == 0.0
        assert p99 == 0.0

    def test_compute_percentiles_single_value(self):
        collector = GovernanceMetricsCollector()
        p50, p95, p99 = collector._compute_percentiles([5.0])
        assert p50 == 5.0
        assert p95 == 5.0
        assert p99 == 5.0

    def test_compute_percentiles_multiple(self):
        collector = GovernanceMetricsCollector()
        values = list(range(1, 101))  # 1 to 100
        p50, p95, p99 = collector._compute_percentiles(values)
        # floor index: int(100 * 0.50) = 50, values[50] = 51
        assert p50 == 51
        assert p95 == 96
        assert p99 == 100

    @pytest.mark.asyncio
    async def test_compare_snapshots_both_provided(self):
        collector = GovernanceMetricsCollector()
        baseline = GovernanceMetricsSnapshot(violations_rate=0.0)
        current = GovernanceMetricsSnapshot(violations_rate=0.05)
        comp = await collector.compare_snapshots(baseline, current)
        assert isinstance(comp, MetricsComparison)
        assert comp.violations_rate_delta == pytest.approx(0.05)

    @pytest.mark.asyncio
    async def test_compare_snapshots_collects_current(self):
        collector = GovernanceMetricsCollector()
        collector.redis_client = None
        baseline = GovernanceMetricsSnapshot(violations_rate=0.0, constitutional_version="1.0.0")
        comp = await collector.compare_snapshots(baseline)
        assert isinstance(comp, MetricsComparison)

    @pytest.mark.asyncio
    async def test_record_governance_decision_with_redis(self):
        collector = GovernanceMetricsCollector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client

        await collector.record_governance_decision(
            latency_ms=2.5, approved=True, escalated=True, constitutional_violation=True
        )

        mock_client.zadd.assert_awaited()
        mock_client.hincrby.assert_awaited()

    @pytest.mark.asyncio
    async def test_record_governance_decision_denied(self):
        collector = GovernanceMetricsCollector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client

        await collector.record_governance_decision(latency_ms=1.0, approved=False)
        # Should increment denied counter
        calls = mock_client.hincrby.call_args_list
        keys = [c[0][1] for c in calls]
        assert "denied" in keys

    @pytest.mark.asyncio
    async def test_record_governance_decision_redis_error(self):
        collector = GovernanceMetricsCollector()
        mock_client = AsyncMock()
        mock_client.zadd.side_effect = RuntimeError("redis error")
        collector.redis_client = mock_client
        # Should not raise
        await collector.record_governance_decision(latency_ms=1.0, approved=True)

    @pytest.mark.asyncio
    async def test_record_maci_violation_with_redis(self):
        collector = GovernanceMetricsCollector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client

        await collector.record_maci_violation(agent_id="agent-1", action="approve", role="judicial")
        mock_client.zadd.assert_awaited()

    @pytest.mark.asyncio
    async def test_record_deliberation_outcome_with_redis(self):
        collector = GovernanceMetricsCollector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client

        await collector.record_deliberation_outcome(success=True)
        mock_client.hincrby.assert_awaited()

    @pytest.mark.asyncio
    async def test_record_deliberation_outcome_failed(self):
        collector = GovernanceMetricsCollector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client

        await collector.record_deliberation_outcome(success=False)
        calls = mock_client.hincrby.call_args_list
        keys = [c[0][1] for c in calls]
        assert "failed" in keys

    @pytest.mark.asyncio
    async def test_get_baseline_snapshot_found(self):
        collector = GovernanceMetricsCollector()
        mock_client = AsyncMock()
        snap = GovernanceMetricsSnapshot(constitutional_version="1.0.0")
        mock_client.get.return_value = snap.model_dump_json()
        collector.redis_client = mock_client

        result = await collector.get_baseline_snapshot("1.0.0")
        assert result is not None
        assert result.constitutional_version == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_baseline_snapshot_not_found(self):
        collector = GovernanceMetricsCollector()
        mock_client = AsyncMock()
        mock_client.get.return_value = None
        collector.redis_client = mock_client

        result = await collector.get_baseline_snapshot("1.0.0")
        assert result is None

    @pytest.mark.asyncio
    async def test_store_baseline_snapshot_with_redis(self):
        collector = GovernanceMetricsCollector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client

        snap = GovernanceMetricsSnapshot(constitutional_version="1.0.0")
        await collector.store_baseline_snapshot(snap, "1.0.0")
        mock_client.set.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("enhanced_agent_bus.constitutional.metrics_collector.REDIS_AVAILABLE", False)
    async def test_connect_no_redis_available(self):
        collector = GovernanceMetricsCollector()
        await collector.connect()
        assert collector.redis_client is None

    @pytest.mark.asyncio
    async def test_collect_snapshot_redis_error(self):
        collector = GovernanceMetricsCollector()
        mock_client = AsyncMock()
        mock_client.zrangebyscore.side_effect = RuntimeError("redis down")
        collector.redis_client = mock_client

        snap = await collector.collect_snapshot()
        # Should return empty snapshot on error
        assert isinstance(snap, GovernanceMetricsSnapshot)
        assert snap.total_requests == 0
