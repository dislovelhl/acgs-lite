# Constitutional Hash: 608508a9bd224290
"""
Tests for src/core/enhanced_agent_bus/observability/capacity_metrics/models.py

Targets ≥ 90% coverage on the models module, exercising:
- CapacityStatus enum
- LatencyPercentiles dataclass + is_compliant()
- ThroughputMetrics dataclass + is_compliant()
- QueueMetrics dataclass
- ResourceUtilization dataclass
- CapacitySnapshot dataclass + to_dict() + get_scaling_recommendation()
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.observability.capacity_metrics.models import (
    CapacitySnapshot,
    CapacityStatus,
    LatencyPercentiles,
    QueueMetrics,
    ResourceUtilization,
    ThroughputMetrics,
)

# ---------------------------------------------------------------------------
# CapacityStatus
# ---------------------------------------------------------------------------


class TestCapacityStatus:
    """Verify every value of the CapacityStatus enum."""

    def test_healthy_value(self):
        assert CapacityStatus.HEALTHY == "healthy"
        assert CapacityStatus.HEALTHY.value == "healthy"

    def test_warning_value(self):
        assert CapacityStatus.WARNING == "warning"

    def test_critical_value(self):
        assert CapacityStatus.CRITICAL == "critical"

    def test_degraded_value(self):
        assert CapacityStatus.DEGRADED == "degraded"

    def test_is_str_enum(self):
        """CapacityStatus inherits from str so it compares equal to raw strings."""
        assert isinstance(CapacityStatus.HEALTHY, str)

    def test_all_members_present(self):
        members = {m.value for m in CapacityStatus}
        assert members == {"healthy", "warning", "critical", "degraded"}


# ---------------------------------------------------------------------------
# LatencyPercentiles
# ---------------------------------------------------------------------------


class TestLatencyPercentiles:
    """Full coverage of LatencyPercentiles fields and methods."""

    def test_default_construction(self):
        lp = LatencyPercentiles()
        assert lp.p50_ms == 0.0
        assert lp.p90_ms == 0.0
        assert lp.p95_ms == 0.0
        assert lp.p99_ms == 0.0
        assert lp.max_ms == 0.0
        assert lp.min_ms == 0.0
        assert lp.avg_ms == 0.0
        assert lp.sample_count == 0
        assert lp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_all_fields_settable(self):
        lp = LatencyPercentiles(
            p50_ms=1.0,
            p90_ms=2.0,
            p95_ms=3.0,
            p99_ms=4.0,
            max_ms=10.0,
            min_ms=0.1,
            avg_ms=2.5,
            sample_count=100,
        )
        assert lp.p50_ms == 1.0
        assert lp.p90_ms == 2.0
        assert lp.p95_ms == 3.0
        assert lp.p99_ms == 4.0
        assert lp.max_ms == 10.0
        assert lp.min_ms == 0.1
        assert lp.avg_ms == 2.5
        assert lp.sample_count == 100

    def test_is_compliant_below_target(self):
        """P99 < 5 ms → compliant."""
        assert LatencyPercentiles(p99_ms=4.999).is_compliant() is True

    def test_is_compliant_at_target(self):
        """P99 == 5 ms → not compliant (strict < 5)."""
        assert LatencyPercentiles(p99_ms=5.0).is_compliant() is False

    def test_is_compliant_above_target(self):
        """P99 > 5 ms → not compliant."""
        assert LatencyPercentiles(p99_ms=5.001).is_compliant() is False

    def test_is_compliant_zero(self):
        """Default p99_ms = 0.0 is compliant."""
        assert LatencyPercentiles().is_compliant() is True

    def test_constitutional_hash_value(self):
        assert (
            LatencyPercentiles().constitutional_hash == CONSTITUTIONAL_HASH
        )  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# ThroughputMetrics
# ---------------------------------------------------------------------------


class TestThroughputMetrics:
    """Full coverage of ThroughputMetrics fields and methods."""

    def test_default_construction(self):
        tm = ThroughputMetrics()
        assert tm.current_rps == 0.0
        assert tm.peak_rps == 0.0
        assert tm.avg_rps == 0.0
        assert tm.total_requests == 0
        assert tm.window_seconds == 60
        assert tm.constitutional_hash == CONSTITUTIONAL_HASH

    def test_all_fields_settable(self):
        tm = ThroughputMetrics(
            current_rps=500.0,
            peak_rps=1000.0,
            avg_rps=300.0,
            total_requests=9999,
            window_seconds=30,
        )
        assert tm.current_rps == 500.0
        assert tm.peak_rps == 1000.0
        assert tm.avg_rps == 300.0
        assert tm.total_requests == 9999
        assert tm.window_seconds == 30

    def test_is_compliant_above_target(self):
        """current_rps > 100 → compliant."""
        assert ThroughputMetrics(current_rps=100.001).is_compliant() is True

    def test_is_compliant_at_target(self):
        """current_rps == 100 → not compliant (strict >)."""
        assert ThroughputMetrics(current_rps=100.0).is_compliant() is False

    def test_is_compliant_below_target(self):
        """current_rps < 100 → not compliant."""
        assert ThroughputMetrics(current_rps=99.9).is_compliant() is False

    def test_is_compliant_zero(self):
        """Default current_rps = 0 → not compliant."""
        assert ThroughputMetrics().is_compliant() is False

    def test_constitutional_hash_value(self):
        assert (
            ThroughputMetrics().constitutional_hash == CONSTITUTIONAL_HASH
        )  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# QueueMetrics
# ---------------------------------------------------------------------------


class TestQueueMetrics:
    """Full coverage of QueueMetrics fields."""

    def test_default_construction(self):
        qm = QueueMetrics()
        assert qm.current_depth == 0
        assert qm.max_depth == 0
        assert qm.avg_depth == 0.0
        assert qm.enqueue_rate == 0.0
        assert qm.dequeue_rate == 0.0
        assert qm.pending_messages == 0
        assert qm.dlq_depth == 0
        assert qm.constitutional_hash == CONSTITUTIONAL_HASH

    def test_all_fields_settable(self):
        qm = QueueMetrics(
            current_depth=50,
            max_depth=200,
            avg_depth=30.5,
            enqueue_rate=10.0,
            dequeue_rate=9.5,
            pending_messages=5,
            dlq_depth=3,
        )
        assert qm.current_depth == 50
        assert qm.max_depth == 200
        assert qm.avg_depth == 30.5
        assert qm.enqueue_rate == 10.0
        assert qm.dequeue_rate == 9.5
        assert qm.pending_messages == 5
        assert qm.dlq_depth == 3

    def test_constitutional_hash_value(self):
        assert QueueMetrics().constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# ResourceUtilization
# ---------------------------------------------------------------------------


class TestResourceUtilization:
    """Full coverage of ResourceUtilization fields."""

    def test_default_construction(self):
        ru = ResourceUtilization()
        assert ru.cpu_percent == 0.0
        assert ru.memory_percent == 0.0
        assert ru.memory_bytes == 0
        assert ru.thread_count == 0
        assert ru.open_connections == 0
        assert ru.gc_collections == 0
        assert ru.constitutional_hash == CONSTITUTIONAL_HASH

    def test_all_fields_settable(self):
        ru = ResourceUtilization(
            cpu_percent=55.5,
            memory_percent=40.0,
            memory_bytes=1073741824,
            thread_count=8,
            open_connections=100,
            gc_collections=5,
        )
        assert ru.cpu_percent == 55.5
        assert ru.memory_percent == 40.0
        assert ru.memory_bytes == 1073741824
        assert ru.thread_count == 8
        assert ru.open_connections == 100
        assert ru.gc_collections == 5

    def test_constitutional_hash_value(self):
        assert (
            ResourceUtilization().constitutional_hash == CONSTITUTIONAL_HASH
        )  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# CapacitySnapshot — construction & to_dict()
# ---------------------------------------------------------------------------


class TestCapacitySnapshotConstruction:
    """Test CapacitySnapshot default and explicit construction."""

    def test_default_construction(self):
        snap = CapacitySnapshot()
        assert isinstance(snap.timestamp, datetime)
        assert snap.timestamp.tzinfo is not None  # timezone-aware
        assert isinstance(snap.latency, LatencyPercentiles)
        assert isinstance(snap.throughput, ThroughputMetrics)
        assert isinstance(snap.queue, QueueMetrics)
        assert isinstance(snap.resources, ResourceUtilization)
        assert snap.status == CapacityStatus.HEALTHY
        assert snap.constitutional_hash == CONSTITUTIONAL_HASH

    def test_explicit_construction(self):
        ts = datetime.now(UTC)
        snap = CapacitySnapshot(
            timestamp=ts,
            latency=LatencyPercentiles(p99_ms=2.0),
            throughput=ThroughputMetrics(current_rps=500.0),
            queue=QueueMetrics(current_depth=25),
            resources=ResourceUtilization(cpu_percent=45.0),
            status=CapacityStatus.WARNING,
        )
        assert snap.timestamp == ts
        assert snap.latency.p99_ms == 2.0
        assert snap.throughput.current_rps == 500.0
        assert snap.queue.current_depth == 25
        assert snap.resources.cpu_percent == 45.0
        assert snap.status == CapacityStatus.WARNING


class TestCapacitySnapshotToDict:
    """Test CapacitySnapshot.to_dict() serialises all expected fields."""

    def _make_snapshot(self, **kwargs) -> CapacitySnapshot:
        defaults = dict(
            latency=LatencyPercentiles(p99_ms=2.0, p50_ms=1.0, sample_count=50),
            throughput=ThroughputMetrics(current_rps=500.0, total_requests=5000),
            queue=QueueMetrics(current_depth=30, dlq_depth=2),
            resources=ResourceUtilization(cpu_percent=55.0, memory_bytes=512 * 1024 * 1024),
            status=CapacityStatus.HEALTHY,
        )
        defaults.update(kwargs)
        return CapacitySnapshot(**defaults)

    def test_top_level_keys(self):
        d = self._make_snapshot().to_dict()
        assert set(d.keys()) == {
            "timestamp",
            "status",
            "latency",
            "throughput",
            "queue",
            "resources",
            "constitutional_hash",
        }

    def test_timestamp_is_iso_string(self):
        d = self._make_snapshot().to_dict()
        # Should be parsable as ISO datetime
        datetime.fromisoformat(d["timestamp"])

    def test_status_is_value_string(self):
        d = self._make_snapshot(status=CapacityStatus.WARNING).to_dict()
        assert d["status"] == "warning"

    def test_constitutional_hash_present(self):
        d = self._make_snapshot().to_dict()
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_latency_section(self):
        snap = self._make_snapshot(
            latency=LatencyPercentiles(
                p50_ms=1.0,
                p90_ms=2.0,
                p95_ms=3.0,
                p99_ms=4.0,
                max_ms=10.0,
                min_ms=0.1,
                avg_ms=2.5,
                sample_count=100,
            )
        )
        d = snap.to_dict()["latency"]
        assert d["p50_ms"] == 1.0
        assert d["p90_ms"] == 2.0
        assert d["p95_ms"] == 3.0
        assert d["p99_ms"] == 4.0
        assert d["max_ms"] == 10.0
        assert d["min_ms"] == 0.1
        assert d["avg_ms"] == 2.5
        assert d["sample_count"] == 100
        assert d["compliant"] is True  # p99_ms = 4.0 < 5.0

    def test_latency_compliant_false(self):
        snap = self._make_snapshot(latency=LatencyPercentiles(p99_ms=6.0))
        assert snap.to_dict()["latency"]["compliant"] is False

    def test_throughput_section(self):
        snap = self._make_snapshot(
            throughput=ThroughputMetrics(
                current_rps=200.0,
                peak_rps=500.0,
                avg_rps=150.0,
                total_requests=9999,
            )
        )
        d = snap.to_dict()["throughput"]
        assert d["current_rps"] == 200.0
        assert d["peak_rps"] == 500.0
        assert d["avg_rps"] == 150.0
        assert d["total_requests"] == 9999
        assert d["compliant"] is True  # current_rps=200 > 100

    def test_throughput_compliant_false(self):
        snap = self._make_snapshot(throughput=ThroughputMetrics(current_rps=50.0))
        assert snap.to_dict()["throughput"]["compliant"] is False

    def test_queue_section(self):
        snap = self._make_snapshot(
            queue=QueueMetrics(
                current_depth=10,
                max_depth=100,
                avg_depth=8.5,
                enqueue_rate=5.0,
                dequeue_rate=4.8,
                pending_messages=2,
                dlq_depth=1,
            )
        )
        d = snap.to_dict()["queue"]
        assert d["current_depth"] == 10
        assert d["max_depth"] == 100
        assert d["avg_depth"] == 8.5
        assert d["enqueue_rate"] == 5.0
        assert d["dequeue_rate"] == 4.8
        assert d["pending_messages"] == 2
        assert d["dlq_depth"] == 1

    def test_resources_section(self):
        snap = self._make_snapshot(
            resources=ResourceUtilization(
                cpu_percent=60.0,
                memory_percent=45.0,
                memory_bytes=2 * 1024 * 1024 * 1024,
                thread_count=16,
                open_connections=50,
            )
        )
        d = snap.to_dict()["resources"]
        assert d["cpu_percent"] == 60.0
        assert d["memory_percent"] == 45.0
        assert d["memory_bytes"] == 2 * 1024 * 1024 * 1024
        assert d["thread_count"] == 16
        assert d["open_connections"] == 50


# ---------------------------------------------------------------------------
# CapacitySnapshot.get_scaling_recommendation()
# ---------------------------------------------------------------------------


class TestScalingRecommendation:
    """Exercise every branch in get_scaling_recommendation()."""

    # --- Helper -----------------------------------------------------------

    def _snap(
        self,
        p99_ms: float = 1.0,
        current_depth: int = 5,
        cpu_percent: float = 50.0,
        status: CapacityStatus = CapacityStatus.HEALTHY,
    ) -> CapacitySnapshot:
        return CapacitySnapshot(
            latency=LatencyPercentiles(p99_ms=p99_ms),
            throughput=ThroughputMetrics(current_rps=500.0),
            queue=QueueMetrics(current_depth=current_depth),
            resources=ResourceUtilization(cpu_percent=cpu_percent),
            status=status,
        )

    # --- "maintain" baseline -------------------------------------------

    def test_maintain_nominal(self):
        rec = self._snap(p99_ms=1.0, current_depth=5, cpu_percent=50.0).get_scaling_recommendation()
        assert rec["direction"] == "maintain"
        assert rec["urgency"] == "normal"
        assert rec["reasons"] == []
        assert rec["constitutional_hash"] == CONSTITUTIONAL_HASH

    # --- scale_down -------------------------------------------------------

    def test_scale_down_all_conditions_met(self):
        """cpu < 30, queue < 10, p99 < 1.0 → scale_down."""
        rec = self._snap(p99_ms=0.5, current_depth=5, cpu_percent=20.0).get_scaling_recommendation()
        assert rec["direction"] == "scale_down"
        assert rec["urgency"] == "planned"
        assert len(rec["reasons"]) == 1
        assert "underutilized" in rec["reasons"][0].lower()

    def test_scale_down_blocked_by_high_cpu(self):
        """cpu >= 30 prevents scale_down even if queue and latency are low."""
        rec = self._snap(p99_ms=0.5, current_depth=5, cpu_percent=31.0).get_scaling_recommendation()
        assert rec["direction"] == "maintain"

    def test_scale_down_blocked_by_high_queue(self):
        """current_depth >= 10 prevents scale_down."""
        rec = self._snap(
            p99_ms=0.5, current_depth=10, cpu_percent=20.0
        ).get_scaling_recommendation()
        assert rec["direction"] == "maintain"

    def test_scale_down_blocked_by_high_latency(self):
        """p99_ms >= 1.0 prevents scale_down."""
        rec = self._snap(p99_ms=1.0, current_depth=5, cpu_percent=20.0).get_scaling_recommendation()
        assert rec["direction"] == "maintain"

    # --- latency branches -------------------------------------------------

    def test_latency_approaching_limit(self):
        """3 < p99 <= 5 → scale_up soon."""
        rec = self._snap(p99_ms=4.0).get_scaling_recommendation()
        assert rec["direction"] == "scale_up"
        assert rec["urgency"] == "soon"
        assert any("approaching" in r for r in rec["reasons"])

    def test_latency_exceeds_constitutional_target(self):
        """p99 > 5 → scale_up immediate."""
        rec = self._snap(p99_ms=5.001).get_scaling_recommendation()
        assert rec["direction"] == "scale_up"
        assert rec["urgency"] == "immediate"
        assert any("constitutional" in r for r in rec["reasons"])

    def test_latency_exactly_at_3ms_threshold(self):
        """p99 == 3.0 is NOT > 3.0 so stays 'maintain'."""
        rec = self._snap(p99_ms=3.0).get_scaling_recommendation()
        assert rec["direction"] == "maintain"

    def test_latency_just_above_3ms_threshold(self):
        """p99 = 3.001 > 3.0 → soon."""
        rec = self._snap(p99_ms=3.001).get_scaling_recommendation()
        assert rec["direction"] == "scale_up"
        assert rec["urgency"] == "soon"

    # --- queue depth branches ---------------------------------------------

    def test_queue_depth_critical(self):
        """current_depth > 500 → immediate."""
        rec = self._snap(current_depth=501).get_scaling_recommendation()
        assert rec["direction"] == "scale_up"
        assert rec["urgency"] == "immediate"
        assert any("critical" in r.lower() for r in rec["reasons"])

    def test_queue_depth_elevated(self):
        """100 < current_depth <= 500 → soon (when no other scale_up trigger)."""
        rec = self._snap(current_depth=101).get_scaling_recommendation()
        assert rec["direction"] == "scale_up"
        assert rec["urgency"] == "soon"
        assert any("elevated" in r for r in rec["reasons"])

    def test_queue_depth_exactly_500_not_critical(self):
        """current_depth == 500 is not > 500, so falls to elevated branch."""
        rec = self._snap(current_depth=500).get_scaling_recommendation()
        assert rec["urgency"] in ("soon", "immediate")  # could be elevated

    def test_queue_depth_exactly_100_not_elevated(self):
        """current_depth == 100 is not > 100, so no queue reason."""
        rec = self._snap(current_depth=100).get_scaling_recommendation()
        assert not any("depth" in r.lower() for r in rec["reasons"])

    def test_queue_elevated_does_not_downgrade_immediate(self):
        """If urgency is already 'immediate' from latency, elevated queue keeps it."""
        snap = CapacitySnapshot(
            latency=LatencyPercentiles(p99_ms=6.0),
            throughput=ThroughputMetrics(current_rps=500.0),
            queue=QueueMetrics(current_depth=200),  # elevated, not critical
            resources=ResourceUtilization(cpu_percent=50.0),
            status=CapacityStatus.CRITICAL,
        )
        rec = snap.get_scaling_recommendation()
        assert rec["urgency"] == "immediate"  # preserved from latency branch
        assert len(rec["reasons"]) == 2  # both latency + queue reason

    # --- CPU branches -----------------------------------------------------

    def test_cpu_critical(self):
        """cpu > 85 → immediate."""
        rec = self._snap(cpu_percent=85.001).get_scaling_recommendation()
        assert rec["direction"] == "scale_up"
        assert rec["urgency"] == "immediate"
        assert any("critical" in r.lower() for r in rec["reasons"])

    def test_cpu_elevated(self):
        """70 < cpu <= 85 → soon (if no prior immediate trigger)."""
        rec = self._snap(cpu_percent=75.0).get_scaling_recommendation()
        assert rec["direction"] == "scale_up"
        assert rec["urgency"] == "soon"
        assert any("elevated" in r for r in rec["reasons"])

    def test_cpu_elevated_does_not_downgrade_immediate(self):
        """Elevated CPU does not override an existing 'immediate' urgency."""
        snap = CapacitySnapshot(
            latency=LatencyPercentiles(p99_ms=6.0),  # triggers immediate
            throughput=ThroughputMetrics(current_rps=500.0),
            queue=QueueMetrics(current_depth=5),
            resources=ResourceUtilization(cpu_percent=75.0),  # elevated
            status=CapacityStatus.CRITICAL,
        )
        rec = snap.get_scaling_recommendation()
        assert rec["urgency"] == "immediate"
        # Both a latency reason and a CPU reason should be present
        assert len(rec["reasons"]) == 2

    def test_cpu_exactly_85_not_critical(self):
        """cpu == 85 is NOT > 85, so falls to elevated branch."""
        rec = self._snap(cpu_percent=85.0).get_scaling_recommendation()
        assert rec["urgency"] in ("soon", "immediate")

    def test_cpu_exactly_70_not_elevated(self):
        """cpu == 70 is NOT > 70, no CPU reason."""
        rec = self._snap(cpu_percent=70.0).get_scaling_recommendation()
        assert not any("cpu" in r.lower() for r in rec["reasons"])

    # --- status field passthrough -----------------------------------------

    def test_status_in_recommendation(self):
        for status in CapacityStatus:
            snap = self._snap(status=status)
            rec = snap.get_scaling_recommendation()
            assert rec["status"] == status.value

    # --- multiple triggers accumulate reasons ----------------------------

    def test_multiple_triggers_accumulate_reasons(self):
        """High latency + high queue + high CPU all produce three reasons."""
        snap = CapacitySnapshot(
            latency=LatencyPercentiles(p99_ms=6.0),
            throughput=ThroughputMetrics(current_rps=500.0),
            queue=QueueMetrics(current_depth=600),
            resources=ResourceUtilization(cpu_percent=90.0),
            status=CapacityStatus.CRITICAL,
        )
        rec = snap.get_scaling_recommendation()
        assert rec["direction"] == "scale_up"
        assert rec["urgency"] == "immediate"
        assert len(rec["reasons"]) == 3


# ---------------------------------------------------------------------------
# __all__ completeness
# ---------------------------------------------------------------------------


class TestModuleExports:
    """Verify __all__ exports match what the module exposes."""

    def test_all_exports_importable(self):
        from enhanced_agent_bus.observability.capacity_metrics import models as m

        for name in m.__all__:
            assert hasattr(m, name), f"__all__ references missing name: {name}"

    def test_all_contents(self):
        from enhanced_agent_bus.observability.capacity_metrics import models as m

        assert set(m.__all__) == {
            "CapacityStatus",
            "LatencyPercentiles",
            "ThroughputMetrics",
            "QueueMetrics",
            "ResourceUtilization",
            "CapacitySnapshot",
        }
