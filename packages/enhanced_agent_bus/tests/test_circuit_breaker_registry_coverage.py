# Constitutional Hash: 608508a9bd224290
"""
Tests for src/core/enhanced_agent_bus/circuit_breaker/registry.py

Targets ≥ 90% coverage of the registry module, covering:
- ServiceCircuitBreakerRegistry singleton lifecycle
- get_or_create (new and cached paths, double-checked locking)
- get (present and absent)
- get_all_states
- reset (found / not-found)
- reset_all
- initialize_default_circuits (first call and idempotency)
- get_health_summary (all status branches)
- Module-level helpers: get_circuit_breaker_registry,
  reset_circuit_breaker_registry, get_service_circuit_breaker
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.circuit_breaker.config import (
    SERVICE_CIRCUIT_CONFIGS,
    ServiceCircuitConfig,
)
from enhanced_agent_bus.circuit_breaker.enums import (
    CircuitState,
    FallbackStrategy,
    ServiceSeverity,
)
from enhanced_agent_bus.circuit_breaker.registry import (
    ServiceCircuitBreakerRegistry,
    get_circuit_breaker_registry,
    get_service_circuit_breaker,
    reset_circuit_breaker_registry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_registry() -> ServiceCircuitBreakerRegistry:
    """Return a brand-new registry instance (wiping singleton state)."""
    reset_circuit_breaker_registry()
    return get_circuit_breaker_registry()


def _make_config(
    name: str = "svc_a",
    threshold: int = 3,
    severity: ServiceSeverity = ServiceSeverity.MEDIUM,
    fallback: FallbackStrategy = FallbackStrategy.FAIL_CLOSED,
) -> ServiceCircuitConfig:
    return ServiceCircuitConfig(
        name=name,
        failure_threshold=threshold,
        timeout_seconds=10.0,
        half_open_requests=2,
        fallback_strategy=fallback,
        severity=severity,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_registry():
    """Reset the singleton before and after every test."""
    reset_circuit_breaker_registry()
    yield
    reset_circuit_breaker_registry()


# ---------------------------------------------------------------------------
# Singleton behaviour
# ---------------------------------------------------------------------------


class TestSingletonBehaviour:
    def test_same_instance_returned_twice(self):
        r1 = get_circuit_breaker_registry()
        r2 = get_circuit_breaker_registry()
        assert r1 is r2

    def test_reset_produces_fresh_instance(self):
        r1 = get_circuit_breaker_registry()
        reset_circuit_breaker_registry()
        r2 = get_circuit_breaker_registry()
        assert r1 is not r2

    def test_new_returns_same_instance(self):
        r1 = ServiceCircuitBreakerRegistry()
        r2 = ServiceCircuitBreakerRegistry()
        assert r1 is r2

    def test_initialized_flag_starts_false(self):
        reg = _fresh_registry()
        assert reg._initialized is False

    def test_circuits_dict_starts_empty(self):
        reg = _fresh_registry()
        assert reg._circuits == {}


# ---------------------------------------------------------------------------
# get_or_create
# ---------------------------------------------------------------------------


class TestGetOrCreate:
    async def test_creates_new_circuit_breaker(self):
        reg = _fresh_registry()
        cb = await reg.get_or_create("new_svc")
        assert cb is not None
        assert cb.config.name == "new_svc"

    async def test_returns_existing_circuit_breaker(self):
        reg = _fresh_registry()
        cb1 = await reg.get_or_create("svc_x")
        cb2 = await reg.get_or_create("svc_x")
        assert cb1 is cb2

    async def test_uses_provided_config(self):
        reg = _fresh_registry()
        cfg = _make_config("custom_svc", threshold=7)
        cb = await reg.get_or_create("custom_svc", config=cfg)
        assert cb.config.failure_threshold == 7

    async def test_uses_default_config_when_none_provided(self):
        reg = _fresh_registry()
        # "policy_registry" is in SERVICE_CIRCUIT_CONFIGS
        cb = await reg.get_or_create("policy_registry")
        assert cb.config.name == "policy_registry"

    async def test_concurrent_creates_only_one_instance(self):
        reg = _fresh_registry()

        async def create():
            return await reg.get_or_create("concurrent_svc")

        results = await asyncio.gather(*[create() for _ in range(10)])
        assert all(r is results[0] for r in results)
        assert len(reg._circuits) == 1

    async def test_double_check_inside_lock_returns_existing(self):
        """Cover the branch where a second waiter finds the entry already created."""
        reg = _fresh_registry()
        cfg = _make_config("race_svc")

        # Pre-populate the dict so the inner check (line 52) sees it already there.
        # We simulate this by inserting before acquire via a patched lock.
        original_lock = reg._lock

        cb_pre = None

        class _PeekLock:
            """Async context manager that inserts the entry before yielding."""

            async def __aenter__(self):
                # Simulate another coroutine having created the entry while we waited
                from enhanced_agent_bus.circuit_breaker.breaker import (
                    ServiceCircuitBreaker,
                )
                from enhanced_agent_bus.circuit_breaker.config import (
                    get_service_config,
                )

                nonlocal cb_pre
                config = get_service_config("race_svc")
                cb_pre = ServiceCircuitBreaker(config)
                reg._circuits["race_svc"] = cb_pre
                return self

            async def __aexit__(self, *_):
                pass

        reg._lock = _PeekLock()
        try:
            # At this point "race_svc" is NOT in _circuits yet (first check passes)
            # but _PeekLock inserts it before the inner check executes.
            result = await reg.get_or_create("race_svc", config=cfg)
        finally:
            reg._lock = original_lock

        # Should have returned the pre-inserted instance, not a new one
        assert result is cb_pre


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


class TestGet:
    async def test_get_returns_none_for_unknown_service(self):
        reg = _fresh_registry()
        assert reg.get("nonexistent") is None

    async def test_get_returns_cb_for_known_service(self):
        reg = _fresh_registry()
        cb_created = await reg.get_or_create("known_svc")
        cb_fetched = reg.get("known_svc")
        assert cb_fetched is cb_created


# ---------------------------------------------------------------------------
# get_all_states
# ---------------------------------------------------------------------------


class TestGetAllStates:
    async def test_empty_registry_returns_empty_dict(self):
        reg = _fresh_registry()
        assert reg.get_all_states() == {}

    async def test_returns_status_for_each_circuit(self):
        reg = _fresh_registry()
        await reg.get_or_create("svc_1")
        await reg.get_or_create("svc_2")
        states = reg.get_all_states()
        assert set(states.keys()) == {"svc_1", "svc_2"}
        for status in states.values():
            assert "state" in status
            assert "constitutional_hash" in status


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


class TestReset:
    async def test_reset_returns_false_for_unknown_service(self):
        reg = _fresh_registry()
        result = await reg.reset("ghost_svc")
        assert result is False

    async def test_reset_returns_true_for_known_service(self):
        reg = _fresh_registry()
        await reg.get_or_create("svc_a")
        result = await reg.reset("svc_a")
        assert result is True

    async def test_reset_calls_circuit_reset(self):
        reg = _fresh_registry()
        cb = await reg.get_or_create("svc_b")
        # Drive it OPEN
        for _ in range(cb.config.failure_threshold):
            await cb.record_failure(error_type="E")
        assert cb.state == CircuitState.OPEN

        await reg.reset("svc_b")
        assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# reset_all
# ---------------------------------------------------------------------------


class TestResetAll:
    async def test_reset_all_resets_every_circuit(self):
        reg = _fresh_registry()
        # Use policy_registry (threshold=3) — known static config
        cb_a = await reg.get_or_create("policy_registry")
        for _ in range(3):
            await cb_a.record_failure(error_type="E")
        assert cb_a.state == CircuitState.OPEN

        cb_b = await reg.get_or_create("svc_z")
        for _ in range(cb_b.config.failure_threshold):
            await cb_b.record_failure(error_type="E")
        assert cb_b.state == CircuitState.OPEN

        await reg.reset_all()
        assert cb_a.state == CircuitState.CLOSED
        assert cb_b.state == CircuitState.CLOSED

    async def test_reset_all_on_empty_registry(self):
        reg = _fresh_registry()
        # Should not raise
        await reg.reset_all()


# ---------------------------------------------------------------------------
# initialize_default_circuits
# ---------------------------------------------------------------------------


class TestInitializeDefaultCircuits:
    async def test_creates_all_configured_services(self):
        reg = _fresh_registry()
        await reg.initialize_default_circuits()
        for name in SERVICE_CIRCUIT_CONFIGS:
            assert reg.get(name) is not None

    async def test_sets_initialized_flag(self):
        reg = _fresh_registry()
        await reg.initialize_default_circuits()
        assert reg._initialized is True

    async def test_idempotent_second_call(self):
        reg = _fresh_registry()
        await reg.initialize_default_circuits()
        count_after_first = len(reg._circuits)

        # Second call must be a no-op
        await reg.initialize_default_circuits()
        assert len(reg._circuits) == count_after_first


# ---------------------------------------------------------------------------
# get_health_summary — all status branches
# ---------------------------------------------------------------------------


class TestGetHealthSummary:
    async def test_empty_registry_returns_healthy(self):
        reg = _fresh_registry()
        summary = reg.get_health_summary()
        assert summary["status"] == "healthy"
        assert summary["health_score"] == 1.0
        assert summary["total_circuits"] == 0
        assert summary["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_all_closed_is_healthy(self):
        reg = _fresh_registry()
        await reg.get_or_create("svc_1")
        await reg.get_or_create("svc_2")
        summary = reg.get_health_summary()
        assert summary["status"] == "healthy"
        assert summary["health_score"] == 1.0
        assert summary["closed"] == 2
        assert summary["open"] == 0
        assert summary["half_open"] == 0

    async def test_critical_open_returns_critical_status(self):
        reg = _fresh_registry()
        cfg = _make_config("crit_svc", threshold=2, severity=ServiceSeverity.CRITICAL)
        cb = await reg.get_or_create("crit_svc", config=cfg)
        for _ in range(2):
            await cb.record_failure(error_type="E")
        assert cb.state == CircuitState.OPEN

        summary = reg.get_health_summary()
        assert summary["status"] == "critical"
        assert "crit_svc" in summary["critical_services_open"]

    async def test_non_critical_open_may_be_degraded(self):
        reg = _fresh_registry()
        # Two closed, two open (non-critical) → score = 2/4 = 0.5 → "degraded"
        await reg.get_or_create("c1")
        await reg.get_or_create("c2")
        cfg3 = _make_config("o1", threshold=1, severity=ServiceSeverity.MEDIUM)
        cfg4 = _make_config("o2", threshold=1, severity=ServiceSeverity.MEDIUM)
        cb3 = await reg.get_or_create("o1", config=cfg3)
        cb4 = await reg.get_or_create("o2", config=cfg4)
        await cb3.record_failure(error_type="E")
        await cb4.record_failure(error_type="E")
        assert cb3.state == CircuitState.OPEN
        assert cb4.state == CircuitState.OPEN

        summary = reg.get_health_summary()
        assert summary["status"] in ("degraded", "critical")
        assert summary["open"] == 2

    async def test_score_below_0_5_gives_critical_status_no_critical_services(self):
        reg = _fresh_registry()
        # One closed, three open (non-critical) → score = 1/4 = 0.25 → "critical"
        await reg.get_or_create("c1")
        for i in range(3):
            cfg = _make_config(f"o{i}", threshold=1, severity=ServiceSeverity.LOW)
            cb = await reg.get_or_create(f"o{i}", config=cfg)
            await cb.record_failure(error_type="E")

        summary = reg.get_health_summary()
        assert summary["status"] == "critical"
        assert summary["critical_services_open"] == []

    async def test_half_open_counted_as_half_point(self):
        reg = _fresh_registry()
        # One closed, one half-open → score = (1 + 0.5) / 2 = 0.75 → "healthy"
        await reg.get_or_create("closed_svc")
        cfg = _make_config("ho_svc", threshold=1)
        cfg.timeout_seconds = 0.01
        cb = await reg.get_or_create("ho_svc", config=cfg)
        await cb.record_failure(error_type="E")
        import asyncio as _asyncio

        await _asyncio.sleep(0.05)
        await cb.can_execute()  # triggers OPEN→HALF_OPEN transition
        assert cb.state == CircuitState.HALF_OPEN

        summary = reg.get_health_summary()
        assert summary["half_open"] == 1
        assert summary["health_score"] == round((1 + 0.5) / 2, 3)

    async def test_summary_contains_timestamp(self):
        reg = _fresh_registry()
        summary = reg.get_health_summary()
        assert "timestamp" in summary
        assert isinstance(summary["timestamp"], str)

    async def test_health_score_at_exactly_0_7_is_healthy(self):
        reg = _fresh_registry()
        # 7 closed + 3 open (non-critical) → score = 7/10 = 0.7 → "healthy"
        for i in range(7):
            await reg.get_or_create(f"closed_{i}")
        for i in range(3):
            cfg = _make_config(f"open_{i}", threshold=1, severity=ServiceSeverity.LOW)
            cb = await reg.get_or_create(f"open_{i}", config=cfg)
            await cb.record_failure(error_type="E")

        summary = reg.get_health_summary()
        assert summary["health_score"] == round(7 / 10, 3)
        assert summary["status"] == "healthy"


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestModuleLevelHelpers:
    def test_get_circuit_breaker_registry_returns_instance(self):
        reg = get_circuit_breaker_registry()
        assert isinstance(reg, ServiceCircuitBreakerRegistry)

    def test_get_circuit_breaker_registry_caches_instance(self):
        r1 = get_circuit_breaker_registry()
        r2 = get_circuit_breaker_registry()
        assert r1 is r2

    def test_reset_clears_global_registry(self):
        r1 = get_circuit_breaker_registry()
        reset_circuit_breaker_registry()
        r2 = get_circuit_breaker_registry()
        assert r1 is not r2

    async def test_get_service_circuit_breaker_creates_cb(self):
        cb = await get_service_circuit_breaker("helper_test_svc")
        assert cb is not None
        assert cb.config.name == "helper_test_svc"

    async def test_get_service_circuit_breaker_with_explicit_config(self):
        cfg = _make_config("explicit_svc", threshold=99)
        cb = await get_service_circuit_breaker("explicit_svc", config=cfg)
        assert cb.config.failure_threshold == 99

    async def test_get_service_circuit_breaker_returns_same_instance(self):
        cb1 = await get_service_circuit_breaker("idempotent_svc")
        cb2 = await get_service_circuit_breaker("idempotent_svc")
        assert cb1 is cb2
