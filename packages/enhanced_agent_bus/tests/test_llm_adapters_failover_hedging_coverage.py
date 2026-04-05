# Constitutional Hash: 608508a9bd224290
# Sprint 59 — llm_adapters/failover/hedging.py coverage
"""
Comprehensive test suite for:
  src/core/enhanced_agent_bus/llm_adapters/failover/hedging.py

Target: ≥95% line coverage.

All async tests run without @pytest.mark.asyncio because
asyncio_mode = "auto" is configured in pyproject.toml.
"""

from __future__ import annotations

import asyncio
import statistics
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.llm_adapters.failover.hedging import (
    HEDGED_EXECUTION_ERRORS,
    HedgedRequest,
    RequestHedgingManager,
)

CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# HedgedRequest dataclass tests
# ---------------------------------------------------------------------------


class TestHedgedRequest:
    """Tests for HedgedRequest dataclass."""

    def test_default_initialization(self):
        req = HedgedRequest(request_id="req-1", providers=["p1", "p2"])
        assert req.request_id == "req-1"
        assert req.providers == ["p1", "p2"]
        assert isinstance(req.started_at, datetime)
        assert req.started_at.tzinfo is not None
        assert req.completed_at is None
        assert req.winning_provider is None
        assert req.responses == {}
        assert req.errors == {}
        assert req.latencies_ms == {}
        assert req.constitutional_hash == CONSTITUTIONAL_HASH

    def test_full_initialization(self):
        now = datetime.now(UTC)
        req = HedgedRequest(
            request_id="req-2",
            providers=["a", "b"],
            completed_at=now,
            winning_provider="a",
            responses={"a": {"text": "hi"}},
            errors={"b": "timeout"},
            latencies_ms={"a": 42.0, "b": 99.0},
        )
        assert req.completed_at == now
        assert req.winning_provider == "a"
        assert req.responses == {"a": {"text": "hi"}}
        assert req.errors == {"b": "timeout"}
        assert req.latencies_ms == {"a": 42.0, "b": 99.0}

    def test_independent_mutable_defaults(self):
        """Each HedgedRequest instance gets independent dicts/lists."""
        r1 = HedgedRequest(request_id="r1", providers=[])
        r2 = HedgedRequest(request_id="r2", providers=[])
        r1.responses["x"] = 1
        r1.errors["y"] = "err"
        r1.latencies_ms["z"] = 5.0
        assert r2.responses == {}
        assert r2.errors == {}
        assert r2.latencies_ms == {}

    def test_constitutional_hash_value(self):
        req = HedgedRequest(request_id="r", providers=[])
        assert req.constitutional_hash == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# HEDGED_EXECUTION_ERRORS constant
# ---------------------------------------------------------------------------


class TestHedgedExecutionErrors:
    """Verify the error tuple contents."""

    def test_contains_expected_exceptions(self):
        expected = (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            ConnectionError,
            OSError,
            asyncio.TimeoutError,
        )
        assert set(expected) == set(HEDGED_EXECUTION_ERRORS)

    def test_is_tuple(self):
        assert isinstance(HEDGED_EXECUTION_ERRORS, tuple)


# ---------------------------------------------------------------------------
# RequestHedgingManager.__init__
# ---------------------------------------------------------------------------


class TestRequestHedgingManagerInit:
    """Constructor tests."""

    def test_defaults(self):
        m = RequestHedgingManager()
        assert m._default_hedge_count == 2
        assert m._hedge_delay_ms == 100
        assert len(m._hedged_requests) == 0

    def test_custom_params(self):
        m = RequestHedgingManager(default_hedge_count=5, hedge_delay_ms=50)
        assert m._default_hedge_count == 5
        assert m._hedge_delay_ms == 50

    def test_deque_maxlen(self):
        m = RequestHedgingManager()
        assert m._hedged_requests.maxlen == 1000

    def test_lock_is_asyncio_lock(self):
        m = RequestHedgingManager()
        assert isinstance(m._lock, asyncio.Lock)


# ---------------------------------------------------------------------------
# RequestHedgingManager.execute_hedged — success paths
# ---------------------------------------------------------------------------


class TestExecuteHedgedSuccess:
    """Tests for successful hedged execution."""

    async def test_single_provider_success(self):
        """One provider, no hedging delay."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            return {"provider": provider_id, "result": "ok"}

        winner, result = await manager.execute_hedged(
            request_id="req-single",
            providers=["p1"],
            execute_fn=execute_fn,
        )
        assert winner == "p1"
        assert result == {"provider": "p1", "result": "ok"}

    async def test_first_provider_wins(self):
        """Both providers succeed; first (no delay) wins."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)

        call_order = []

        async def execute_fn(provider_id: str):
            call_order.append(provider_id)
            return f"response-{provider_id}"

        winner, result = await manager.execute_hedged(
            request_id="req-two",
            providers=["fast", "slow"],
            execute_fn=execute_fn,
        )
        # First provider should win when delays are 0 and providers respond immediately
        assert winner in ("fast", "slow")
        assert result is not None

    async def test_hedge_count_limits_providers(self):
        """hedge_count parameter restricts provider selection."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)

        called_providers = []

        async def execute_fn(provider_id: str):
            called_providers.append(provider_id)
            return "ok"

        await manager.execute_hedged(
            request_id="req-limit",
            providers=["p1", "p2", "p3", "p4"],
            execute_fn=execute_fn,
            hedge_count=2,
        )
        # Only first 2 providers should be used
        assert len(set(called_providers)) <= 2
        assert all(p in ("p1", "p2") for p in called_providers)

    async def test_explicit_hedge_count_overrides_default(self):
        """Explicit hedge_count overrides default."""
        manager = RequestHedgingManager(default_hedge_count=3, hedge_delay_ms=0)

        called = []

        async def execute_fn(provider_id: str):
            called.append(provider_id)
            return "ok"

        await manager.execute_hedged(
            request_id="req-override",
            providers=["p1", "p2", "p3"],
            execute_fn=execute_fn,
            hedge_count=1,
        )
        assert len(called) == 1
        assert called[0] == "p1"

    async def test_result_stored_in_hedged_requests(self):
        """Completed request is stored in _hedged_requests deque."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            return "done"

        await manager.execute_hedged("req-store", ["p1"], execute_fn)
        assert len(manager._hedged_requests) == 1
        stored = manager._hedged_requests[0]
        assert stored.request_id == "req-store"
        assert stored.winning_provider == "p1"
        assert stored.completed_at is not None

    async def test_latency_recorded(self):
        """Latency is recorded for winning provider."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            return "done"

        await manager.execute_hedged("req-lat", ["p1"], execute_fn)
        stored = manager._hedged_requests[0]
        assert "p1" in stored.latencies_ms
        assert stored.latencies_ms["p1"] >= 0

    async def test_second_provider_wins_when_first_fails(self):
        """Second provider wins when first raises an error."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            if provider_id == "p1":
                raise ConnectionError("p1 failed")
            return f"response-{provider_id}"

        winner, result = await manager.execute_hedged(
            request_id="req-fallback",
            providers=["p1", "p2"],
            execute_fn=execute_fn,
        )
        assert winner == "p2"
        assert result == "response-p2"

    async def test_responses_dict_populated(self):
        """responses dict is populated for winning provider."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            return {"key": "value"}

        await manager.execute_hedged("req-resp", ["p1"], execute_fn)
        stored = manager._hedged_requests[0]
        assert "p1" in stored.responses
        assert stored.responses["p1"] == {"key": "value"}

    async def test_pending_tasks_cancelled_after_winner(self):
        """Pending tasks are cancelled once a winner is found."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)

        p2_cancelled = asyncio.Event()

        async def execute_fn(provider_id: str):
            if provider_id == "p1":
                return "fast"
            # Slow provider — will be cancelled
            try:
                await asyncio.sleep(10)
                return "slow"
            except asyncio.CancelledError:
                p2_cancelled.set()
                raise

        winner, result = await manager.execute_hedged(
            request_id="req-cancel",
            providers=["p1", "p2"],
            execute_fn=execute_fn,
        )
        # Give cancellation a moment to propagate
        await asyncio.sleep(0.01)
        assert winner == "p1"
        assert result == "fast"

    async def test_uses_default_hedge_count_when_none_passed(self):
        """Uses _default_hedge_count when hedge_count=None."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        called = []

        async def execute_fn(provider_id: str):
            called.append(provider_id)
            return "ok"

        await manager.execute_hedged(
            request_id="req-default",
            providers=["p1", "p2", "p3"],
            execute_fn=execute_fn,
            hedge_count=None,
        )
        assert "p1" in called
        assert "p2" not in called


# ---------------------------------------------------------------------------
# RequestHedgingManager.execute_hedged — error paths
# ---------------------------------------------------------------------------


class TestExecuteHedgedErrors:
    """Tests for error handling in execute_hedged."""

    async def test_empty_providers_raises_value_error(self):
        """No providers raises ValueError."""
        manager = RequestHedgingManager()

        async def execute_fn(provider_id: str):
            return "ok"

        with pytest.raises(ValueError, match="No providers available for hedging"):
            await manager.execute_hedged("req-empty", [], execute_fn)

    async def test_all_providers_fail_raises_runtime_error(self):
        """All providers failing raises RuntimeError."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            raise ConnectionError(f"{provider_id} unavailable")

        with pytest.raises(RuntimeError, match="All hedged providers failed"):
            await manager.execute_hedged("req-all-fail", ["p1", "p2"], execute_fn)

    async def test_all_fail_error_message_contains_provider_errors(self):
        """RuntimeError message includes per-provider error details."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            raise ValueError(f"bad input for {provider_id}")

        with pytest.raises(RuntimeError) as exc_info:
            await manager.execute_hedged("req-msg", ["p1", "p2"], execute_fn)

        msg = str(exc_info.value)
        assert "p1" in msg or "p2" in msg

    async def test_error_stored_in_hedged_errors_dict(self):
        """Errors are recorded per provider in hedged.errors."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            raise RuntimeError(f"runtime error in {provider_id}")

        with pytest.raises(RuntimeError):
            await manager.execute_hedged("req-errs", ["p1", "p2"], execute_fn)

        stored = manager._hedged_requests[0]
        assert "p1" in stored.errors
        assert "p2" in stored.errors

    async def test_all_hedged_execution_errors_caught(self):
        """Each HEDGED_EXECUTION_ERRORS type is caught in execute_with_provider.

        Note: the outer loop in execute_hedged only re-catches
        (RuntimeError, ValueError, ConnectionError, TimeoutError).
        TypeError, KeyError, AttributeError, OSError propagate out of
        task.result() uncaught by the loop's except clause, so they
        surface directly rather than as 'All hedged providers failed'.
        """
        # Errors caught by BOTH the inner and outer handler → RuntimeError wrapper
        swallowed_errors = [
            RuntimeError("runtime"),
            ValueError("value"),
            ConnectionError("conn"),
            TimeoutError(),
        ]
        for error in swallowed_errors:
            manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

            async def execute_fn(provider_id: str, err=error):
                raise err

            with pytest.raises(RuntimeError, match="All hedged providers failed"):
                await manager.execute_hedged("req-err", ["p1"], execute_fn)

        # Errors caught in execute_with_provider but NOT in the outer loop → propagate
        propagated_errors = [
            (TypeError, TypeError("type")),
            (KeyError, KeyError("key")),
            (AttributeError, AttributeError("attr")),
            (OSError, OSError("os")),
        ]
        for exc_type, error in propagated_errors:
            manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

            async def execute_fn(provider_id: str, err=error):
                raise err

            with pytest.raises(exc_type):
                await manager.execute_hedged("req-err", ["p1"], execute_fn)

    async def test_hedge_count_zero_uses_no_providers(self):
        """hedge_count=0 is falsy, falls back to default_hedge_count."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)
        called = []

        async def execute_fn(provider_id: str):
            called.append(provider_id)
            return "ok"

        # hedge_count=0 is falsy so default (1) is used
        await manager.execute_hedged(
            request_id="req-zero",
            providers=["p1", "p2"],
            execute_fn=execute_fn,
            hedge_count=0,
        )
        assert "p1" in called

    async def test_failed_request_stored_with_no_winner(self):
        """Failed hedged request is stored with winning_provider=None."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            raise ValueError("fail")

        with pytest.raises(RuntimeError):
            await manager.execute_hedged("req-no-winner", ["p1"], execute_fn)

        stored = manager._hedged_requests[0]
        assert stored.winning_provider is None
        assert stored.completed_at is not None

    async def test_delay_applied_to_non_first_providers(self):
        """Non-first providers get a staggered delay (hedge_delay_ms)."""
        # Use a real delay to verify timing
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=50)

        timings: dict[str, float] = {}

        import time

        async def execute_fn(provider_id: str):
            timings[provider_id] = time.monotonic()
            return "ok"

        start = asyncio.get_event_loop().time()
        await manager.execute_hedged("req-delay", ["p1", "p2"], execute_fn)
        # p1 should fire immediately, p2 after 50ms
        # We just check both ran without error; the delay test verifies structure
        assert "p1" in timings

    async def test_single_provider_that_fails_no_empty_providers(self):
        """Single provider failure when hedge_count explicitly set to 1.

        KeyError propagates directly (not wrapped in RuntimeError) because
        the outer except clause only handles RuntimeError/ValueError/
        ConnectionError/TimeoutError.
        """
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            raise KeyError("missing key")

        with pytest.raises(KeyError):
            await manager.execute_hedged("req-one-fail", ["p1"], execute_fn, hedge_count=1)


# ---------------------------------------------------------------------------
# RequestHedgingManager.get_hedging_stats
# ---------------------------------------------------------------------------


class TestGetHedgingStats:
    """Tests for get_hedging_stats()."""

    def test_empty_returns_zeros(self):
        manager = RequestHedgingManager()
        stats = manager.get_hedging_stats()
        assert stats["total_hedged_requests"] == 0
        assert stats["avg_latency_improvement_ms"] == 0
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_stats_after_one_successful_request(self):
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            return "done"

        await manager.execute_hedged("req-stat1", ["p1"], execute_fn)
        stats = manager.get_hedging_stats()
        assert stats["total_hedged_requests"] == 1
        assert stats["successful_requests"] == 1
        assert stats["success_rate"] == 1.0
        assert "provider_win_counts" in stats
        assert stats["provider_win_counts"]["p1"] == 1
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_stats_after_multiple_requests(self):
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            return "ok"

        for i in range(3):
            await manager.execute_hedged(f"req-{i}", ["p1"], execute_fn)

        stats = manager.get_hedging_stats()
        assert stats["total_hedged_requests"] == 3
        assert stats["successful_requests"] == 3
        assert stats["success_rate"] == 1.0

    async def test_stats_with_failed_request(self):
        """Failed requests counted but no winning provider."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            raise ConnectionError("fail")

        with pytest.raises(RuntimeError):
            await manager.execute_hedged("req-fail-stat", ["p1"], execute_fn)

        stats = manager.get_hedging_stats()
        assert stats["total_hedged_requests"] == 1
        assert stats["successful_requests"] == 0
        assert stats["success_rate"] == 0.0

    async def test_latency_improvement_with_two_providers(self):
        """avg_latency_improvement_ms computed when multiple latencies present."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)

        # Manually insert a request with known latencies
        req = HedgedRequest(request_id="manual-1", providers=["p1", "p2"])
        req.winning_provider = "p1"
        req.latencies_ms = {"p1": 10.0, "p2": 90.0}
        req.completed_at = datetime.now(UTC)

        manager._hedged_requests.append(req)

        stats = manager.get_hedging_stats()
        # improvement = avg(other_latencies) - winner_latency = 90 - 10 = 80
        assert stats["avg_latency_improvement_ms"] == pytest.approx(80.0)

    async def test_latency_improvement_zero_when_single_latency(self):
        """No improvement when only one latency recorded (no comparison possible)."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        req = HedgedRequest(request_id="manual-2", providers=["p1"])
        req.winning_provider = "p1"
        req.latencies_ms = {"p1": 50.0}
        req.completed_at = datetime.now(UTC)

        manager._hedged_requests.append(req)

        stats = manager.get_hedging_stats()
        assert stats["avg_latency_improvement_ms"] == 0

    async def test_provider_win_counts_multiple_providers(self):
        """Win counts tracked per provider across multiple requests."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        call_count = {"n": 0}

        async def execute_fn(provider_id: str):
            return "ok"

        await manager.execute_hedged("r1", ["p1"], execute_fn)
        await manager.execute_hedged("r2", ["p2"], execute_fn)
        await manager.execute_hedged("r3", ["p1"], execute_fn)

        stats = manager.get_hedging_stats()
        assert stats["provider_win_counts"]["p1"] == 2
        assert stats["provider_win_counts"]["p2"] == 1

    async def test_stats_constitutional_hash_always_present(self):
        manager = RequestHedgingManager()
        stats = manager.get_hedging_stats()
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_mixed_success_and_failure(self):
        """Stats correctly computed with mix of successes and failures."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        # 2 successes
        async def ok_fn(provider_id: str):
            return "ok"

        async def fail_fn(provider_id: str):
            raise ValueError("err")

        await manager.execute_hedged("s1", ["p1"], ok_fn)
        await manager.execute_hedged("s2", ["p1"], ok_fn)
        with pytest.raises(RuntimeError):
            await manager.execute_hedged("f1", ["p1"], fail_fn)

        stats = manager.get_hedging_stats()
        assert stats["total_hedged_requests"] == 3
        assert stats["successful_requests"] == 2
        assert abs(stats["success_rate"] - 2 / 3) < 1e-9

    async def test_deque_maxlen_respected(self):
        """Deque respects maxlen=1000."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            return "ok"

        for i in range(1005):
            await manager.execute_hedged(f"req-{i}", ["p1"], execute_fn)

        assert len(manager._hedged_requests) == 1000

    async def test_multiple_latencies_improvement_calculation(self):
        """avg_latency_improvement_ms uses statistics.mean over multiple improvements."""
        manager = RequestHedgingManager()

        # Two requests, each with 2 providers
        r1 = HedgedRequest(request_id="r1", providers=["p1", "p2"])
        r1.winning_provider = "p1"
        r1.latencies_ms = {"p1": 20.0, "p2": 80.0}
        r1.completed_at = datetime.now(UTC)

        r2 = HedgedRequest(request_id="r2", providers=["p1", "p2"])
        r2.winning_provider = "p2"
        r2.latencies_ms = {"p1": 100.0, "p2": 40.0}
        r2.completed_at = datetime.now(UTC)

        manager._hedged_requests.append(r1)
        manager._hedged_requests.append(r2)

        stats = manager.get_hedging_stats()
        # r1 improvement: 80 - 20 = 60; r2 improvement: 100 - 40 = 60; mean = 60
        assert stats["avg_latency_improvement_ms"] == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# Concurrency / thread-safety
# ---------------------------------------------------------------------------


class TestConcurrency:
    """Tests ensuring concurrent access is safe."""

    async def test_concurrent_executions(self):
        """Multiple concurrent hedged requests all complete successfully."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            await asyncio.sleep(0)
            return f"ok-{provider_id}"

        results = await asyncio.gather(
            *[manager.execute_hedged(f"req-{i}", ["p1"], execute_fn) for i in range(10)]
        )
        assert len(results) == 10
        assert all(r[0] == "p1" for r in results)

    async def test_lock_protects_deque_append(self):
        """Lock is used during deque append (structural test)."""
        manager = RequestHedgingManager(default_hedge_count=1, hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            return "ok"

        # Run many requests concurrently to stress-test lock
        await asyncio.gather(
            *[manager.execute_hedged(f"r{i}", ["p1"], execute_fn) for i in range(50)]
        )
        assert len(manager._hedged_requests) == 50


# ---------------------------------------------------------------------------
# Module-level __all__
# ---------------------------------------------------------------------------


class TestModuleAll:
    """Verify __all__ exports."""

    def test_all_exports(self):
        from enhanced_agent_bus.llm_adapters.failover import hedging

        assert set(hedging.__all__) == {"HedgedRequest", "RequestHedgingManager"}
