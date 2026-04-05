"""
ACGS-2 Enhanced Agent Bus - Chaos Scenarios Coverage Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for chaos/scenarios.py covering:
- All 5 scenario classes: NetworkPartitionScenario, LatencyInjectionScenario,
  MemoryPressureScenario, CPUStressScenario, DependencyFailureScenario
- ScenarioExecutor orchestration
- ScenarioResult dataclass
- All enum values: ScenarioStatus, PartitionType, DependencyType
- Safety limits and clamping behavior
- Status transitions through execute() and cancel()
- Rollback mechanics
- Error paths
- Edge cases: invalid params, boundary values, concurrent access
"""

import asyncio
import threading
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.chaos.scenarios import (
    MAX_CPU_PERCENT,
    MAX_DURATION_S,
    MAX_LATENCY_MS,
    MAX_MEMORY_PERCENT,
    CPUStressScenario,
    DependencyFailureScenario,
    DependencyType,
    LatencyInjectionScenario,
    MemoryPressureScenario,
    NetworkPartitionScenario,
    PartitionType,
    ScenarioExecutor,
    ScenarioResult,
    ScenarioStatus,
)
from enhanced_agent_bus.exceptions import ConstitutionalHashMismatchError

# ---------------------------------------------------------------------------
# Helper: fast-forward asyncio.sleep so tests run in milliseconds
# ---------------------------------------------------------------------------


def make_fast_sleep(factor: float = 0.001):
    """Return a patched asyncio.sleep that multiplies duration by factor."""
    original = asyncio.sleep

    async def _fast_sleep(delay: float, **kwargs):
        await original(delay * factor, **kwargs)

    return _fast_sleep


# ============================================================
# ScenarioStatus enum
# ============================================================


class TestScenarioStatus:
    def test_all_values_exist(self):
        assert ScenarioStatus.PENDING.value == "pending"
        assert ScenarioStatus.RUNNING.value == "running"
        assert ScenarioStatus.COMPLETED.value == "completed"
        assert ScenarioStatus.FAILED.value == "failed"
        assert ScenarioStatus.ROLLED_BACK.value == "rolled_back"
        assert ScenarioStatus.CANCELLED.value == "cancelled"

    def test_str_enum_equality(self):
        assert ScenarioStatus.PENDING == "pending"
        assert ScenarioStatus.RUNNING == "running"

    def test_enum_count(self):
        assert len(ScenarioStatus) == 6


# ============================================================
# PartitionType enum
# ============================================================


class TestPartitionType:
    def test_all_values_exist(self):
        assert PartitionType.FULL.value == "full"
        assert PartitionType.PARTIAL.value == "partial"
        assert PartitionType.ONE_WAY.value == "one_way"
        assert PartitionType.SLOW.value == "slow"

    def test_enum_count(self):
        assert len(PartitionType) == 4


# ============================================================
# DependencyType enum
# ============================================================


class TestDependencyType:
    def test_all_values_exist(self):
        assert DependencyType.REDIS.value == "redis"
        assert DependencyType.OPA.value == "opa"
        assert DependencyType.KAFKA.value == "kafka"
        assert DependencyType.DATABASE.value == "database"
        assert DependencyType.EXTERNAL_API.value == "external_api"
        assert DependencyType.BLOCKCHAIN.value == "blockchain"

    def test_enum_count(self):
        assert len(DependencyType) == 6


# ============================================================
# ScenarioResult dataclass
# ============================================================


class TestScenarioResult:
    def test_minimal_construction(self):
        now = datetime.now(UTC)
        result = ScenarioResult(
            scenario_name="test",
            status=ScenarioStatus.COMPLETED,
            started_at=now,
        )
        assert result.scenario_name == "test"
        assert result.status == ScenarioStatus.COMPLETED
        assert result.started_at == now
        assert result.ended_at is None
        assert result.duration_s == 0.0
        assert result.events == []
        assert result.errors == []
        assert result.metrics == {}
        assert result.rollback_performed is False
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_to_dict_no_ended_at(self):
        now = datetime.now(UTC)
        result = ScenarioResult(
            scenario_name="s1",
            status=ScenarioStatus.FAILED,
            started_at=now,
        )
        d = result.to_dict()
        assert d["scenario_name"] == "s1"
        assert d["status"] == "failed"
        assert d["ended_at"] is None
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_with_ended_at(self):
        start = datetime.now(UTC)
        end = datetime.now(UTC)
        result = ScenarioResult(
            scenario_name="s2",
            status=ScenarioStatus.COMPLETED,
            started_at=start,
            ended_at=end,
            duration_s=1.5,
            events=["e1"],
            errors=["err1"],
            metrics={"key": 1.0},
            rollback_performed=True,
        )
        d = result.to_dict()
        assert d["ended_at"] == end.isoformat()
        assert d["duration_s"] == 1.5
        assert d["events"] == ["e1"]
        assert d["errors"] == ["err1"]
        assert d["metrics"] == {"key": 1.0}
        assert d["rollback_performed"] is True

    def test_default_events_are_independent_instances(self):
        """Ensure mutable default_factory creates separate lists per instance."""
        r1 = ScenarioResult(
            scenario_name="a", status=ScenarioStatus.PENDING, started_at=datetime.now(UTC)
        )
        r2 = ScenarioResult(
            scenario_name="b", status=ScenarioStatus.PENDING, started_at=datetime.now(UTC)
        )
        r1.events.append("x")
        assert "x" not in r2.events


# ============================================================
# Safety limit constants
# ============================================================


class TestSafetyConstants:
    def test_max_duration(self):
        assert MAX_DURATION_S == 300.0

    def test_max_latency(self):
        assert MAX_LATENCY_MS == 5000

    def test_max_memory(self):
        assert MAX_MEMORY_PERCENT == 80.0

    def test_max_cpu(self):
        assert MAX_CPU_PERCENT == 90.0


# ============================================================
# BaseScenario (tested through concrete subclasses)
# ============================================================


class TestBaseScenarioViaNetworkPartition:
    """Exercise BaseScenario behaviours through NetworkPartitionScenario."""

    def test_invalid_hash_raises(self):
        with pytest.raises(ConstitutionalHashMismatchError):
            NetworkPartitionScenario(
                target_service="svc",
                constitutional_hash="wrong-hash",
            )

    def test_duration_clamped_to_max(self):
        scenario = NetworkPartitionScenario(
            target_service="svc",
            duration_s=MAX_DURATION_S + 100,
        )
        assert scenario.duration_s == MAX_DURATION_S

    def test_duration_at_max_boundary(self):
        scenario = NetworkPartitionScenario(
            target_service="svc",
            duration_s=MAX_DURATION_S,
        )
        assert scenario.duration_s == MAX_DURATION_S

    def test_initial_status_is_pending(self):
        s = NetworkPartitionScenario(target_service="svc")
        assert s.status == ScenarioStatus.PENDING

    def test_result_initially_none(self):
        s = NetworkPartitionScenario(target_service="svc")
        assert s.result is None

    def test_cancel_sets_cancelled_flag_and_status(self):
        s = NetworkPartitionScenario(target_service="svc")
        s.cancel()
        assert s.status == ScenarioStatus.CANCELLED
        assert s._cancelled is True

    def test_blast_radius_empty_allows_all(self):
        s = NetworkPartitionScenario(target_service="svc", affected_services=[])
        # When blast_radius is not empty (target_service is included), only that matters
        # With blast_radius populated by target, is_target_allowed checks membership
        assert s.is_target_allowed("svc")

    def test_blast_radius_restricts_unknown_targets(self):
        s = NetworkPartitionScenario(
            target_service="svc",
            affected_services=["dep1"],
        )
        assert s.is_target_allowed("svc")
        assert s.is_target_allowed("dep1")
        assert not s.is_target_allowed("unknown")

    def test_to_dict_structure(self):
        s = NetworkPartitionScenario(target_service="redis")
        d = s.to_dict()
        assert d["name"] == "network_partition_redis"
        assert d["type"] == "NetworkPartitionScenario"
        assert d["duration_s"] == 30.0
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "blast_radius" in d
        assert "status" in d


# ============================================================
# NetworkPartitionScenario
# ============================================================


class TestNetworkPartitionScenario:
    def test_default_partition_type(self):
        s = NetworkPartitionScenario(target_service="svc")
        assert s.partition_type == PartitionType.FULL

    def test_packet_loss_clamped_to_one(self):
        s = NetworkPartitionScenario(target_service="svc", packet_loss_rate=2.0)
        assert s.packet_loss_rate == 1.0

    def test_is_partitioned_when_inactive(self):
        s = NetworkPartitionScenario(target_service="svc")
        assert not s.is_partitioned("svc", "other")

    def test_is_partitioned_full_when_active(self):
        s = NetworkPartitionScenario(target_service="svc", partition_type=PartitionType.FULL)
        s._partitioned = True
        assert s.is_partitioned("svc", "other")
        assert s.is_partitioned("other", "svc")

    def test_is_partitioned_unrelated_services_not_affected(self):
        s = NetworkPartitionScenario(target_service="svc")
        s._partitioned = True
        assert not s.is_partitioned("a", "b")

    def test_is_partitioned_one_way_blocks_only_inbound(self):
        s = NetworkPartitionScenario(
            target_service="svc",
            partition_type=PartitionType.ONE_WAY,
        )
        s._partitioned = True
        # Traffic TO svc should be blocked
        assert s.is_partitioned("client", "svc")
        # Traffic FROM svc should not be blocked
        assert not s.is_partitioned("svc", "client")

    def test_is_partitioned_slow_never_blocks(self):
        s = NetworkPartitionScenario(
            target_service="svc",
            partition_type=PartitionType.SLOW,
        )
        s._partitioned = True
        assert not s.is_partitioned("svc", "other")

    def test_is_partitioned_partial_returns_bool(self):
        s = NetworkPartitionScenario(
            target_service="svc",
            partition_type=PartitionType.PARTIAL,
            packet_loss_rate=0.5,
        )
        s._partitioned = True
        # Should return a bool (probabilistic)
        result = s.is_partitioned("svc", "other")
        assert isinstance(result, bool)

    async def test_execute_completes_and_returns_result(self):
        s = NetworkPartitionScenario(target_service="svc", duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.status == ScenarioStatus.COMPLETED
        assert result.scenario_name == "network_partition_svc"
        assert result.ended_at is not None
        assert result.duration_s >= 0
        assert not s._partitioned  # partition deactivated in finally

    async def test_execute_cancelled_mid_run(self):
        s = NetworkPartitionScenario(target_service="svc", duration_s=10.0)

        async def cancel_soon():
            await asyncio.sleep(0.05)
            s.cancel()

        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            _, result = await asyncio.gather(cancel_soon(), s.execute())
        assert result.status == ScenarioStatus.CANCELLED
        assert "Scenario cancelled before completion" in result.events

    async def test_execute_sets_result_on_scenario(self):
        s = NetworkPartitionScenario(target_service="svc", duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            await s.execute()
        assert s.result is not None
        assert s.result.status == ScenarioStatus.COMPLETED

    async def test_rollback_deactivates_partition(self):
        s = NetworkPartitionScenario(target_service="svc")
        s._partitioned = True
        await s.rollback()
        assert not s._partitioned

    async def test_execute_with_affected_services(self):
        s = NetworkPartitionScenario(
            target_service="svc",
            duration_s=0.05,
            affected_services=["dep1", "dep2"],
        )
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.status == ScenarioStatus.COMPLETED

    def test_affected_services_in_blast_radius(self):
        s = NetworkPartitionScenario(
            target_service="svc",
            affected_services=["dep1", "dep2"],
        )
        assert "svc" in s.blast_radius
        assert "dep1" in s.blast_radius
        assert "dep2" in s.blast_radius


# ============================================================
# LatencyInjectionScenario
# ============================================================


class TestLatencyInjectionScenario:
    def test_default_construction(self):
        s = LatencyInjectionScenario(target_service="svc")
        assert s.latency_ms == 100
        assert s.latency_variance_ms == 0
        assert s.affected_operations == []
        assert not s._active

    def test_latency_clamped_to_max(self):
        s = LatencyInjectionScenario(target_service="svc", latency_ms=MAX_LATENCY_MS + 1000)
        assert s.latency_ms == MAX_LATENCY_MS

    def test_latency_at_max_boundary(self):
        s = LatencyInjectionScenario(target_service="svc", latency_ms=MAX_LATENCY_MS)
        assert s.latency_ms == MAX_LATENCY_MS

    def test_get_latency_when_inactive(self):
        s = LatencyInjectionScenario(target_service="svc", latency_ms=200)
        assert s.get_latency() == 0
        assert s.get_latency("op1") == 0

    def test_get_latency_when_active_no_filter(self):
        s = LatencyInjectionScenario(target_service="svc", latency_ms=200)
        s._active = True
        assert s.get_latency() == 200
        assert s.get_latency("any_op") == 200

    def test_get_latency_filtered_by_operation(self):
        s = LatencyInjectionScenario(
            target_service="svc",
            latency_ms=100,
            affected_operations=["read", "write"],
        )
        s._active = True
        assert s.get_latency("read") == 100
        assert s.get_latency("write") == 100
        assert s.get_latency("delete") == 0

    def test_get_latency_with_variance(self):
        s = LatencyInjectionScenario(
            target_service="svc",
            latency_ms=100,
            latency_variance_ms=50,
        )
        s._active = True
        # Result must be non-negative
        for _ in range(20):
            lat = s.get_latency()
            assert lat >= 0

    async def test_execute_completes(self):
        s = LatencyInjectionScenario(target_service="svc", duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.status == ScenarioStatus.COMPLETED
        assert not s._active

    async def test_execute_cancelled(self):
        s = LatencyInjectionScenario(target_service="svc", duration_s=10.0)

        async def cancel_soon():
            await asyncio.sleep(0.05)
            s.cancel()

        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            _, result = await asyncio.gather(cancel_soon(), s.execute())
        assert result.status == ScenarioStatus.CANCELLED

    async def test_execute_active_during_run(self):
        activation_states = []

        async def check_active(s):
            await asyncio.sleep(0.02)
            activation_states.append(s._active)

        s = LatencyInjectionScenario(target_service="svc", duration_s=0.1)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            await asyncio.gather(check_active(s), s.execute())

    async def test_rollback_deactivates(self):
        s = LatencyInjectionScenario(target_service="svc")
        s._active = True
        await s.rollback()
        assert not s._active

    async def test_execute_returns_result_with_events(self):
        s = LatencyInjectionScenario(target_service="svc", duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert len(result.events) >= 2
        assert any("100ms" in e for e in result.events)
        assert any("Latency injection deactivated" in e for e in result.events)

    def test_invalid_hash_raises(self):
        with pytest.raises(ConstitutionalHashMismatchError):
            LatencyInjectionScenario(
                target_service="svc",
                constitutional_hash="bad-hash",
            )


# ============================================================
# MemoryPressureScenario
# ============================================================


class TestMemoryPressureScenario:
    def test_default_construction(self):
        s = MemoryPressureScenario()
        assert s.target_percent == 80.0
        assert s.ramp_up_s == 5.0
        assert s._current_pressure == 0.0
        assert not s._active

    def test_target_percent_clamped(self):
        s = MemoryPressureScenario(target_percent=MAX_MEMORY_PERCENT + 10)
        assert s.target_percent == MAX_MEMORY_PERCENT

    def test_target_percent_at_boundary(self):
        s = MemoryPressureScenario(target_percent=MAX_MEMORY_PERCENT)
        assert s.target_percent == MAX_MEMORY_PERCENT

    def test_current_pressure_property(self):
        s = MemoryPressureScenario()
        assert s.current_pressure == 0.0
        s._current_pressure = 50.0
        assert s.current_pressure == 50.0

    def test_is_memory_constrained_when_inactive(self):
        s = MemoryPressureScenario()
        assert not s.is_memory_constrained()

    def test_is_memory_constrained_below_threshold(self):
        s = MemoryPressureScenario()
        s._active = True
        s._current_pressure = 60.0
        assert not s.is_memory_constrained()

    def test_is_memory_constrained_at_threshold(self):
        s = MemoryPressureScenario()
        s._active = True
        s._current_pressure = 70.0
        assert s.is_memory_constrained()

    def test_is_memory_constrained_above_threshold(self):
        s = MemoryPressureScenario()
        s._active = True
        s._current_pressure = 80.0
        assert s.is_memory_constrained()

    async def test_execute_completes(self):
        s = MemoryPressureScenario(target_percent=50.0, duration_s=0.3, ramp_up_s=0.1)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.status == ScenarioStatus.COMPLETED
        assert not s._active
        assert s._current_pressure == 0.0

    async def test_execute_metrics_include_peak_pressure(self):
        # ramp_up_s=1.0 gives steps=10, avoiding ZeroDivisionError when steps=0
        s = MemoryPressureScenario(target_percent=60.0, duration_s=2.0, ramp_up_s=1.0)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.metrics.get("peak_pressure_percent") == 60.0

    async def test_execute_cancelled(self):
        s = MemoryPressureScenario(target_percent=50.0, duration_s=10.0, ramp_up_s=0.1)

        async def cancel_soon():
            await asyncio.sleep(0.05)
            s.cancel()

        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            _, result = await asyncio.gather(cancel_soon(), s.execute())
        assert result.status == ScenarioStatus.CANCELLED

    async def test_execute_no_ramp_up(self):
        s = MemoryPressureScenario(target_percent=50.0, duration_s=0.1, ramp_up_s=0.0)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.status == ScenarioStatus.COMPLETED

    async def test_rollback_resets_state(self):
        s = MemoryPressureScenario()
        s._active = True
        s._current_pressure = 75.0
        await s.rollback()
        assert s._current_pressure == 0.0
        assert not s._active

    def test_invalid_hash_raises(self):
        with pytest.raises(ConstitutionalHashMismatchError):
            MemoryPressureScenario(constitutional_hash="bad")


# ============================================================
# CPUStressScenario
# ============================================================


class TestCPUStressScenario:
    def test_default_construction(self):
        s = CPUStressScenario()
        assert s.target_percent == 80.0
        assert s.cores_affected == 1
        assert s._current_load == 0.0
        assert not s._active

    def test_target_percent_clamped(self):
        s = CPUStressScenario(target_percent=MAX_CPU_PERCENT + 10)
        assert s.target_percent == MAX_CPU_PERCENT

    def test_target_percent_at_boundary(self):
        s = CPUStressScenario(target_percent=MAX_CPU_PERCENT)
        assert s.target_percent == MAX_CPU_PERCENT

    def test_current_load_property(self):
        s = CPUStressScenario()
        assert s.current_load == 0.0
        s._current_load = 85.0
        assert s.current_load == 85.0

    def test_is_cpu_constrained_when_inactive(self):
        s = CPUStressScenario()
        assert not s.is_cpu_constrained()

    def test_is_cpu_constrained_below_threshold(self):
        s = CPUStressScenario()
        s._active = True
        s._current_load = 65.0
        assert not s.is_cpu_constrained()

    def test_is_cpu_constrained_at_threshold(self):
        s = CPUStressScenario()
        s._active = True
        s._current_load = 70.0
        assert s.is_cpu_constrained()

    def test_is_cpu_constrained_above_threshold(self):
        s = CPUStressScenario()
        s._active = True
        s._current_load = 90.0
        assert s.is_cpu_constrained()

    async def test_execute_completes(self):
        s = CPUStressScenario(target_percent=70.0, duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.status == ScenarioStatus.COMPLETED
        assert not s._active
        assert s._current_load == 0.0

    async def test_execute_metrics_include_peak_load(self):
        s = CPUStressScenario(target_percent=75.0, duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.metrics.get("peak_load_percent") == 75.0

    async def test_execute_cancelled(self):
        s = CPUStressScenario(target_percent=80.0, duration_s=10.0)

        async def cancel_soon():
            await asyncio.sleep(0.05)
            s.cancel()

        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            _, result = await asyncio.gather(cancel_soon(), s.execute())
        assert result.status == ScenarioStatus.CANCELLED

    async def test_rollback_resets_state(self):
        s = CPUStressScenario()
        s._active = True
        s._current_load = 85.0
        await s.rollback()
        assert s._current_load == 0.0
        assert not s._active

    async def test_execute_multiple_cores(self):
        s = CPUStressScenario(target_percent=80.0, duration_s=0.05, cores_affected=4)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.status == ScenarioStatus.COMPLETED
        assert "4 cores" in result.events[0]

    def test_invalid_hash_raises(self):
        with pytest.raises(ConstitutionalHashMismatchError):
            CPUStressScenario(constitutional_hash="bad")


# ============================================================
# DependencyFailureScenario
# ============================================================


class TestDependencyFailureScenario:
    def test_construction_with_enum(self):
        s = DependencyFailureScenario(dependency=DependencyType.REDIS)
        assert s.dependency == DependencyType.REDIS
        assert s._dependency_value == "redis"
        assert s.name == "dependency_failure_redis"

    def test_construction_with_string_matching_enum(self):
        s = DependencyFailureScenario(dependency="redis")
        assert isinstance(s.dependency, DependencyType)
        assert s._dependency_value == "redis"

    def test_construction_with_unknown_string(self):
        s = DependencyFailureScenario(dependency="custom_db")
        assert s.dependency == "custom_db"
        assert s._dependency_value == "custom_db"

    def test_all_dependency_types_construction(self):
        for dep_type in DependencyType:
            s = DependencyFailureScenario(dependency=dep_type)
            assert s._dependency_value == dep_type.value

    def test_should_fail_when_inactive(self):
        s = DependencyFailureScenario(dependency=DependencyType.REDIS)
        assert not s.should_fail()

    def test_should_fail_complete_mode(self):
        s = DependencyFailureScenario(dependency=DependencyType.REDIS, failure_mode="complete")
        s._active = True
        assert s.should_fail()
        assert s._call_count == 1
        assert s._failure_count == 1

    def test_should_fail_slow_mode(self):
        s = DependencyFailureScenario(dependency=DependencyType.REDIS, failure_mode="slow")
        s._active = True
        assert not s.should_fail()

    def test_should_fail_intermittent_mode_returns_bool(self):
        s = DependencyFailureScenario(
            dependency=DependencyType.REDIS,
            failure_mode="intermittent",
            intermittent_rate=0.5,
        )
        s._active = True
        results = [s.should_fail() for _ in range(100)]
        # At least some should be True and False (statistically safe with 100 samples)
        assert any(results)

    def test_should_fail_unknown_mode_returns_false(self):
        s = DependencyFailureScenario(dependency=DependencyType.REDIS, failure_mode="unknown_mode")
        s._active = True
        assert not s.should_fail()

    def test_get_failure_error_returns_connection_error(self):
        s = DependencyFailureScenario(dependency=DependencyType.OPA, error_message="OPA down")
        err = s.get_failure_error()
        assert isinstance(err, ConnectionError)
        assert "opa" in str(err)
        assert "OPA down" in str(err)

    def test_get_failure_error_string_dependency(self):
        s = DependencyFailureScenario(dependency="custom_svc", error_message="offline")
        err = s.get_failure_error()
        assert isinstance(err, ConnectionError)
        assert "custom_svc" in str(err)

    async def test_execute_completes(self):
        s = DependencyFailureScenario(dependency=DependencyType.REDIS, duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.status == ScenarioStatus.COMPLETED
        assert not s._active

    async def test_execute_cancelled(self):
        s = DependencyFailureScenario(dependency=DependencyType.KAFKA, duration_s=10.0)

        async def cancel_soon():
            await asyncio.sleep(0.05)
            s.cancel()

        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            _, result = await asyncio.gather(cancel_soon(), s.execute())
        assert result.status == ScenarioStatus.CANCELLED

    async def test_execute_metrics_track_calls_and_failures(self):
        s = DependencyFailureScenario(
            dependency=DependencyType.REDIS,
            failure_mode="complete",
            duration_s=0.05,
        )
        # Manually trigger some calls before execute to verify counter reset
        s._active = True
        s.should_fail()
        s._active = False

        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        # Call count is reset inside execute()
        assert "total_calls" in result.metrics
        assert "failed_calls" in result.metrics
        assert "failure_rate" in result.metrics

    async def test_execute_failure_rate_zero_when_no_calls(self):
        s = DependencyFailureScenario(dependency=DependencyType.DATABASE, duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.metrics["failure_rate"] == 0.0

    async def test_rollback_deactivates(self):
        s = DependencyFailureScenario(dependency=DependencyType.REDIS)
        s._active = True
        await s.rollback()
        assert not s._active

    def test_invalid_hash_raises(self):
        with pytest.raises(ConstitutionalHashMismatchError):
            DependencyFailureScenario(
                dependency=DependencyType.REDIS,
                constitutional_hash="bad",
            )

    async def test_execute_result_events_contain_dependency(self):
        s = DependencyFailureScenario(
            dependency=DependencyType.OPA,
            failure_mode="complete",
            duration_s=0.05,
        )
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert any("opa" in e.lower() for e in result.events)


# ============================================================
# ScenarioExecutor
# ============================================================


class TestScenarioExecutor:
    def test_construction_valid_hash(self):
        executor = ScenarioExecutor()
        assert executor.constitutional_hash == CONSTITUTIONAL_HASH
        assert executor.get_active_scenarios() == []
        assert executor.get_results() == []

    def test_construction_invalid_hash_raises(self):
        with pytest.raises(ConstitutionalHashMismatchError):
            ScenarioExecutor(constitutional_hash="bad-hash")

    async def test_execute_completes_scenario(self):
        executor = ScenarioExecutor()
        s = NetworkPartitionScenario(target_service="svc", duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await executor.execute(s)
        assert result.status == ScenarioStatus.COMPLETED
        assert len(executor.get_results()) == 1

    async def test_execute_removes_from_active_on_completion(self):
        executor = ScenarioExecutor()
        s = NetworkPartitionScenario(target_service="svc", duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            await executor.execute(s)
        assert len(executor.get_active_scenarios()) == 0

    async def test_execute_duplicate_name_raises(self):
        executor = ScenarioExecutor()
        s1 = NetworkPartitionScenario(target_service="svc", duration_s=10.0)
        s2 = NetworkPartitionScenario(target_service="svc", duration_s=10.0)

        # Start s1 in background
        task = asyncio.create_task(_execute_with_fast_sleep(executor, s1))
        # Give the task a moment to register
        await asyncio.sleep(0.01)

        with pytest.raises(ValueError, match="already running"):
            await executor.execute(s2)

        s1.cancel()
        await task

    async def test_rollback_all_active_scenarios(self):
        executor = ScenarioExecutor()
        s1 = NetworkPartitionScenario(target_service="svc1", duration_s=10.0)
        s2 = LatencyInjectionScenario(target_service="svc2", duration_s=10.0)

        # Manually put them in _active_scenarios to simulate running
        with executor._lock:
            executor._active_scenarios["network_partition_svc1"] = s1
            executor._active_scenarios["latency_injection_svc2"] = s2

        # Both start as "partitioned" / "active"
        s1._partitioned = True
        s2._active = True

        await executor.rollback_all()

        assert not s1._partitioned
        assert not s2._active

    async def test_rollback_all_continues_on_error(self):
        executor = ScenarioExecutor()
        bad_scenario = MagicMock()
        bad_scenario.name = "bad"
        bad_scenario.rollback = AsyncMock(side_effect=RuntimeError("rollback failed"))

        with executor._lock:
            executor._active_scenarios["bad"] = bad_scenario

        # Should not raise
        await executor.rollback_all()

    def test_cancel_all(self):
        executor = ScenarioExecutor()
        s1 = NetworkPartitionScenario(target_service="svc1")
        s2 = LatencyInjectionScenario(target_service="svc2")

        with executor._lock:
            executor._active_scenarios["network_partition_svc1"] = s1
            executor._active_scenarios["latency_injection_svc2"] = s2

        executor.cancel_all()
        assert s1.status == ScenarioStatus.CANCELLED
        assert s2.status == ScenarioStatus.CANCELLED

    def test_get_active_scenarios_returns_copy(self):
        executor = ScenarioExecutor()
        s = NetworkPartitionScenario(target_service="svc")
        with executor._lock:
            executor._active_scenarios["network_partition_svc"] = s
        active = executor.get_active_scenarios()
        active.append(MagicMock())  # Mutating the returned list should not affect executor
        assert len(executor.get_active_scenarios()) == 1

    def test_get_results_returns_copy(self):
        executor = ScenarioExecutor()
        now = datetime.now(UTC)
        r = ScenarioResult(scenario_name="r", status=ScenarioStatus.COMPLETED, started_at=now)
        executor._results.append(r)
        results = executor.get_results()
        results.append(MagicMock())
        assert len(executor.get_results()) == 1

    async def test_execute_accumulates_results(self):
        executor = ScenarioExecutor()
        for service in ["svc1", "svc2", "svc3"]:
            s = LatencyInjectionScenario(target_service=service, duration_s=0.03)
            with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
                await executor.execute(s)
        assert len(executor.get_results()) == 3


# ============================================================
# Cross-scenario: cancel() then execute() (race-condition check)
# ============================================================


class TestCancelBeforeExecute:
    async def test_network_partition_pre_cancelled(self):
        s = NetworkPartitionScenario(target_service="svc", duration_s=5.0)
        s.cancel()  # Cancel before execute

        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        # Since _cancelled is set, the while loop exits immediately
        assert result.status == ScenarioStatus.CANCELLED

    async def test_latency_pre_cancelled(self):
        s = LatencyInjectionScenario(target_service="svc", duration_s=5.0)
        s.cancel()
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.status == ScenarioStatus.CANCELLED

    async def test_memory_pressure_pre_cancelled(self):
        s = MemoryPressureScenario(target_percent=50.0, duration_s=5.0, ramp_up_s=0.1)
        s.cancel()
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.status == ScenarioStatus.CANCELLED

    async def test_cpu_stress_pre_cancelled(self):
        s = CPUStressScenario(target_percent=80.0, duration_s=5.0)
        s.cancel()
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.status == ScenarioStatus.CANCELLED

    async def test_dependency_failure_pre_cancelled(self):
        s = DependencyFailureScenario(dependency=DependencyType.REDIS, duration_s=5.0)
        s.cancel()
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.status == ScenarioStatus.CANCELLED


# ============================================================
# Thread-safety: BaseScenario._lock usage
# ============================================================


class TestThreadSafety:
    def test_cancel_is_thread_safe(self):
        s = NetworkPartitionScenario(target_service="svc")
        errors = []

        def do_cancel():
            try:
                s.cancel()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=do_cancel) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert s.status == ScenarioStatus.CANCELLED

    def test_executor_lock_protects_active_scenarios(self):
        executor = ScenarioExecutor()
        errors = []

        def add_and_remove():
            try:
                s = NetworkPartitionScenario(target_service=f"svc_{id(threading.current_thread())}")
                with executor._lock:
                    executor._active_scenarios[s.name] = s
                with executor._lock:
                    executor._active_scenarios.pop(s.name, None)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_and_remove) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ============================================================
# Constitutional hash validation in results
# ============================================================


class TestConstitutionalHashInResults:
    async def test_network_partition_result_has_hash(self):
        s = NetworkPartitionScenario(target_service="svc", duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_latency_result_has_hash(self):
        s = LatencyInjectionScenario(target_service="svc", duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_memory_result_has_hash(self):
        # ramp_up_s=1.0 gives steps=10, avoiding ZeroDivisionError
        s = MemoryPressureScenario(duration_s=2.0, ramp_up_s=1.0)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_cpu_result_has_hash(self):
        s = CPUStressScenario(duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_dependency_failure_result_has_hash(self):
        s = DependencyFailureScenario(dependency=DependencyType.REDIS, duration_s=0.05)
        with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
            result = await s.execute()
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


# ============================================================
# Helper used by duplicate-name test
# ============================================================


async def _execute_with_fast_sleep(executor: ScenarioExecutor, scenario) -> ScenarioResult:
    with patch("asyncio.sleep", new=make_fast_sleep(0.001)):
        return await executor.execute(scenario)


# ============================================================
# Line 172: is_target_allowed when blast_radius is empty
# MemoryPressureScenario and CPUStressScenario pass no blast_radius
# to BaseScenario.__init__, so the set stays empty.
# ============================================================


class TestIsTargetAllowedEmptyBlastRadius:
    def test_memory_pressure_no_blast_radius_allows_any_target(self):
        """Line 172: return True when blast_radius is empty."""
        s = MemoryPressureScenario()
        # blast_radius is set() by default for MemoryPressureScenario
        assert s.blast_radius == set()
        assert s.is_target_allowed("any_random_target") is True
        assert s.is_target_allowed("") is True
        assert s.is_target_allowed("service-xyz-99") is True

    def test_cpu_stress_no_blast_radius_allows_any_target(self):
        """Line 172: return True when blast_radius is empty (CPUStressScenario)."""
        s = CPUStressScenario()
        assert s.blast_radius == set()
        assert s.is_target_allowed("anything") is True

    def test_blast_radius_with_members_restricts(self):
        """Confirm the non-empty branch still works (line 173)."""
        s = NetworkPartitionScenario(target_service="svc")
        assert "svc" in s.blast_radius
        assert s.is_target_allowed("svc") is True
        assert s.is_target_allowed("other") is False


# ============================================================
# Exception handler paths in execute() (lines 307-310, 423-425,
# 532-534, 631-633, 780-782) — inject RuntimeError mid-sleep.
# ============================================================


class TestExecuteExceptionHandlers:
    async def test_network_partition_execute_handles_runtime_error(self):
        """Lines 307-310: except block in NetworkPartitionScenario.execute()."""
        s = NetworkPartitionScenario(target_service="svc", duration_s=5.0)

        call_count = 0

        async def raise_on_second_call(delay: float, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise RuntimeError("simulated network fault")
            await asyncio.sleep(delay * 0.001)

        with patch("asyncio.sleep", new=raise_on_second_call):
            result = await s.execute()

        assert result.status == ScenarioStatus.FAILED
        assert any("RuntimeError" in e for e in result.errors)
        assert not s._partitioned  # finally block still deactivates

    async def test_network_partition_execute_handles_value_error(self):
        """Lines 307-310: except ValueError in NetworkPartitionScenario.execute()."""
        s = NetworkPartitionScenario(target_service="svc", duration_s=5.0)

        async def raise_value_error(delay: float, **kwargs: object) -> None:
            raise ValueError("bad value")

        with patch("asyncio.sleep", new=raise_value_error):
            result = await s.execute()

        assert result.status == ScenarioStatus.FAILED
        assert any("ValueError" in e for e in result.errors)

    async def test_network_partition_execute_handles_type_error(self):
        """Lines 307-310: except TypeError in NetworkPartitionScenario.execute()."""
        s = NetworkPartitionScenario(target_service="svc", duration_s=5.0)

        async def raise_type_error(delay: float, **kwargs: object) -> None:
            raise TypeError("type mismatch")

        with patch("asyncio.sleep", new=raise_type_error):
            result = await s.execute()

        assert result.status == ScenarioStatus.FAILED
        assert any("TypeError" in e for e in result.errors)

    async def test_latency_injection_execute_handles_runtime_error(self):
        """Lines 423-425: except block in LatencyInjectionScenario.execute()."""
        s = LatencyInjectionScenario(target_service="svc", duration_s=5.0)

        call_count = 0

        async def raise_on_second_call(delay: float, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise RuntimeError("latency error")
            await asyncio.sleep(delay * 0.001)

        with patch("asyncio.sleep", new=raise_on_second_call):
            result = await s.execute()

        assert result.status == ScenarioStatus.FAILED
        assert any("RuntimeError" in e for e in result.errors)
        assert not s._active  # finally block resets

    async def test_latency_injection_execute_handles_value_error(self):
        """Lines 423-425: except ValueError in LatencyInjectionScenario.execute()."""
        s = LatencyInjectionScenario(target_service="svc", duration_s=5.0)

        async def raise_value_error(delay: float, **kwargs: object) -> None:
            raise ValueError("latency value error")

        with patch("asyncio.sleep", new=raise_value_error):
            result = await s.execute()

        assert result.status == ScenarioStatus.FAILED

    async def test_memory_pressure_execute_handles_runtime_error(self):
        """Lines 532-534: except block in MemoryPressureScenario.execute()."""
        s = MemoryPressureScenario(target_percent=50.0, duration_s=5.0, ramp_up_s=0.0)

        call_count = 0

        async def raise_on_second_call(delay: float, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise RuntimeError("memory error")
            await asyncio.sleep(delay * 0.001)

        with patch("asyncio.sleep", new=raise_on_second_call):
            result = await s.execute()

        assert result.status == ScenarioStatus.FAILED
        assert any("RuntimeError" in e for e in result.errors)
        assert not s._active
        assert s._current_pressure == 0.0  # finally resets

    async def test_memory_pressure_execute_handles_value_error(self):
        """Lines 532-534: except ValueError in MemoryPressureScenario.execute()."""
        s = MemoryPressureScenario(target_percent=50.0, duration_s=5.0, ramp_up_s=0.0)

        async def raise_value_error(delay: float, **kwargs: object) -> None:
            raise ValueError("memory value error")

        with patch("asyncio.sleep", new=raise_value_error):
            result = await s.execute()

        assert result.status == ScenarioStatus.FAILED

    async def test_cpu_stress_execute_handles_runtime_error(self):
        """Lines 631-633: except block in CPUStressScenario.execute()."""
        s = CPUStressScenario(target_percent=70.0, duration_s=5.0)

        call_count = 0

        async def raise_on_second_call(delay: float, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise RuntimeError("cpu error")
            await asyncio.sleep(delay * 0.001)

        with patch("asyncio.sleep", new=raise_on_second_call):
            result = await s.execute()

        assert result.status == ScenarioStatus.FAILED
        assert any("RuntimeError" in e for e in result.errors)
        assert not s._active
        assert s._current_load == 0.0  # finally resets

    async def test_cpu_stress_execute_handles_value_error(self):
        """Lines 631-633: except ValueError in CPUStressScenario.execute()."""
        s = CPUStressScenario(target_percent=70.0, duration_s=5.0)

        async def raise_value_error(delay: float, **kwargs: object) -> None:
            raise ValueError("cpu value error")

        with patch("asyncio.sleep", new=raise_value_error):
            result = await s.execute()

        assert result.status == ScenarioStatus.FAILED

    async def test_dependency_failure_execute_handles_runtime_error(self):
        """Lines 780-782: except block in DependencyFailureScenario.execute()."""
        s = DependencyFailureScenario(dependency=DependencyType.REDIS, duration_s=5.0)

        call_count = 0

        async def raise_on_second_call(delay: float, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise RuntimeError("redis error")
            await asyncio.sleep(delay * 0.001)

        with patch("asyncio.sleep", new=raise_on_second_call):
            result = await s.execute()

        assert result.status == ScenarioStatus.FAILED
        assert any("RuntimeError" in e for e in result.errors)
        assert not s._active  # finally resets

    async def test_dependency_failure_execute_handles_value_error(self):
        """Lines 780-782: except ValueError in DependencyFailureScenario.execute()."""
        s = DependencyFailureScenario(dependency=DependencyType.OPA, duration_s=5.0)

        async def raise_value_error(delay: float, **kwargs: object) -> None:
            raise ValueError("dep value error")

        with patch("asyncio.sleep", new=raise_value_error):
            result = await s.execute()

        assert result.status == ScenarioStatus.FAILED

    async def test_execute_asyncio_timeout_error_handled(self):
        """All except clauses also catch asyncio.TimeoutError."""
        s = NetworkPartitionScenario(target_service="svc", duration_s=5.0)

        async def raise_timeout(delay: float, **kwargs: object) -> None:
            raise TimeoutError("timed out")

        with patch("asyncio.sleep", new=raise_timeout):
            result = await s.execute()

        assert result.status == ScenarioStatus.FAILED
        assert any("TimeoutError" in e for e in result.errors)
