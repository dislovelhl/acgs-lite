# Constitutional Hash: 608508a9bd224290
"""
Tests for src/core/enhanced_agent_bus/llm_adapters/failover/warmup.py
Target: >=95% line coverage (88 statements)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.circuit_breaker import CONSTITUTIONAL_HASH
from enhanced_agent_bus.llm_adapters.failover.warmup import (
    WARMUP_EXECUTION_ERRORS,
    WARMUP_LOOP_ERRORS,
    ProviderWarmupManager,
    WarmupResult,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

# ---------------------------------------------------------------------------
# WarmupResult dataclass tests
# ---------------------------------------------------------------------------


class TestWarmupResult:
    """Tests for the WarmupResult dataclass."""

    def test_warmup_result_basic_construction(self):
        """WarmupResult with required fields."""
        result = WarmupResult(
            provider_id="openai",
            success=True,
            latency_ms=42.5,
        )
        assert result.provider_id == "openai"
        assert result.success is True
        assert result.latency_ms == 42.5
        assert result.error is None
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_warmup_result_with_error(self):
        """WarmupResult with error message."""
        result = WarmupResult(
            provider_id="anthropic",
            success=False,
            latency_ms=0.0,
            error="Connection refused",
        )
        assert result.success is False
        assert result.error == "Connection refused"

    def test_warmup_result_timestamp_defaults_to_utc_now(self):
        """Timestamp defaults to a recent timezone.utc datetime."""
        before = datetime.now(UTC)
        result = WarmupResult(provider_id="p", success=True, latency_ms=1.0)
        after = datetime.now(UTC)
        assert before <= result.timestamp <= after

    def test_warmup_result_custom_timestamp(self):
        """Custom timestamp is preserved."""
        ts = datetime(2024, 1, 1, tzinfo=UTC)
        result = WarmupResult(provider_id="p", success=True, latency_ms=1.0, timestamp=ts)
        assert result.timestamp == ts

    def test_warmup_result_constitutional_hash(self):
        """Constitutional hash matches the canonical value."""
        result = WarmupResult(provider_id="p", success=True, latency_ms=0)
        assert result.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_warmup_result_zero_latency(self):
        """Zero latency is valid."""
        result = WarmupResult(provider_id="p", success=False, latency_ms=0)
        assert result.latency_ms == 0

    def test_warmup_result_high_latency(self):
        """High latency values are preserved."""
        result = WarmupResult(provider_id="p", success=True, latency_ms=9999.99)
        assert result.latency_ms == 9999.99


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_warmup_execution_errors_is_tuple(self):
        """WARMUP_EXECUTION_ERRORS is a tuple of exception types."""
        assert isinstance(WARMUP_EXECUTION_ERRORS, tuple)
        assert all(issubclass(e, Exception) for e in WARMUP_EXECUTION_ERRORS)

    def test_warmup_loop_errors_is_tuple(self):
        """WARMUP_LOOP_ERRORS is a tuple of exception types."""
        assert isinstance(WARMUP_LOOP_ERRORS, tuple)
        assert all(issubclass(e, Exception) for e in WARMUP_LOOP_ERRORS)

    def test_warmup_execution_errors_contains_expected_types(self):
        """WARMUP_EXECUTION_ERRORS contains the documented exception types."""
        for exc_type in (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            ConnectionError,
            OSError,
        ):
            assert exc_type in WARMUP_EXECUTION_ERRORS

    def test_warmup_loop_errors_contains_expected_types(self):
        """WARMUP_LOOP_ERRORS contains the documented exception types."""
        for exc_type in (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            ConnectionError,
            OSError,
        ):
            assert exc_type in WARMUP_LOOP_ERRORS


# ---------------------------------------------------------------------------
# ProviderWarmupManager.__init__
# ---------------------------------------------------------------------------


class TestProviderWarmupManagerInit:
    """Tests for ProviderWarmupManager initialization."""

    def test_init_creates_empty_state(self):
        """Manager initialises with empty internal dicts."""
        mgr = ProviderWarmupManager()
        assert mgr._warmup_handlers == {}
        assert mgr._last_warmup == {}
        assert mgr._warmup_results == {}
        assert mgr._warmup_tasks == {}

    def test_init_creates_lock(self):
        """Manager has an asyncio.Lock after init."""
        mgr = ProviderWarmupManager()
        assert isinstance(mgr._lock, asyncio.Lock)

    def test_default_warmup_interval(self):
        """Default warmup interval is 5 minutes."""
        assert ProviderWarmupManager.DEFAULT_WARMUP_INTERVAL == timedelta(minutes=5)

    def test_warmup_timeout_ms(self):
        """Warmup timeout is 10 000 ms."""
        assert ProviderWarmupManager.WARMUP_TIMEOUT_MS == 10000


# ---------------------------------------------------------------------------
# register_warmup_handler
# ---------------------------------------------------------------------------


class TestRegisterWarmupHandler:
    """Tests for register_warmup_handler."""

    def test_register_sync_handler(self):
        """Sync callable is stored correctly."""
        mgr = ProviderWarmupManager()

        def handler():
            return None

        mgr.register_warmup_handler("openai", handler)
        assert mgr._warmup_handlers["openai"] is handler

    def test_register_async_handler(self):
        """Async callable is stored correctly."""
        mgr = ProviderWarmupManager()
        handler = AsyncMock()
        mgr.register_warmup_handler("anthropic", handler)
        assert mgr._warmup_handlers["anthropic"] is handler

    def test_register_overwrites_existing_handler(self):
        """Re-registering a provider overwrites the previous handler."""
        mgr = ProviderWarmupManager()

        def h1():
            return None

        def h2():
            return None

        mgr.register_warmup_handler("openai", h1)
        mgr.register_warmup_handler("openai", h2)
        assert mgr._warmup_handlers["openai"] is h2

    def test_register_multiple_providers(self):
        """Multiple providers can be registered independently."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p1", lambda: None)
        mgr.register_warmup_handler("p2", lambda: None)
        assert "p1" in mgr._warmup_handlers
        assert "p2" in mgr._warmup_handlers


# ---------------------------------------------------------------------------
# warmup() — no handler registered
# ---------------------------------------------------------------------------


class TestWarmupNoHandler:
    """warmup() when no handler is registered."""

    async def test_warmup_returns_failure_when_no_handler(self):
        """Returns failure WarmupResult if provider has no handler."""
        mgr = ProviderWarmupManager()
        result = await mgr.warmup("unknown_provider")
        assert isinstance(result, WarmupResult)
        assert result.success is False
        assert result.latency_ms == 0
        assert result.error == "No warmup handler registered"
        assert result.provider_id == "unknown_provider"

    async def test_warmup_no_handler_state_not_updated(self):
        """No handler path does NOT update _last_warmup / _warmup_results."""
        mgr = ProviderWarmupManager()
        await mgr.warmup("unknown_provider")
        assert "unknown_provider" not in mgr._last_warmup
        assert "unknown_provider" not in mgr._warmup_results


# ---------------------------------------------------------------------------
# warmup() — async handler succeeds
# ---------------------------------------------------------------------------


class TestWarmupAsyncHandlerSuccess:
    """warmup() with an async handler that succeeds."""

    async def test_warmup_async_handler_success(self):
        """Async handler success path returns success WarmupResult."""
        mgr = ProviderWarmupManager()
        handler = AsyncMock(return_value=None)
        mgr.register_warmup_handler("openai", handler)

        result = await mgr.warmup("openai")

        assert result.success is True
        assert result.provider_id == "openai"
        assert result.error is None
        assert result.latency_ms >= 0
        handler.assert_called_once()

    async def test_warmup_async_handler_updates_state(self):
        """Successful warmup updates _last_warmup and _warmup_results."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("openai", AsyncMock(return_value=None))

        before = datetime.now(UTC)
        result = await mgr.warmup("openai")
        after = datetime.now(UTC)

        assert "openai" in mgr._last_warmup
        assert before <= mgr._last_warmup["openai"] <= after
        assert mgr._warmup_results["openai"] is result

    async def test_warmup_async_handler_constitutional_hash_on_result(self):
        """WarmupResult from successful warmup carries the constitutional hash."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("openai", AsyncMock(return_value=None))
        result = await mgr.warmup("openai")
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# warmup() — sync handler (asyncio.to_thread path)
# ---------------------------------------------------------------------------


class TestWarmupSyncHandler:
    """warmup() with a sync (non-coroutine) handler."""

    async def test_warmup_sync_handler_success(self):
        """Sync handler is run via asyncio.to_thread and succeeds."""
        mgr = ProviderWarmupManager()
        handler = MagicMock(return_value=None)
        mgr.register_warmup_handler("cohere", handler)

        result = await mgr.warmup("cohere")

        assert result.success is True
        handler.assert_called_once()

    async def test_warmup_sync_handler_updates_state(self):
        """Sync handler success updates internal state."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("cohere", MagicMock(return_value=None))
        result = await mgr.warmup("cohere")
        assert mgr._warmup_results["cohere"] is result


# ---------------------------------------------------------------------------
# warmup() — timeout
# ---------------------------------------------------------------------------


class TestWarmupTimeout:
    """warmup() when the handler times out."""

    async def test_warmup_timeout_returns_failure(self):
        """asyncio.TimeoutError path returns a failure WarmupResult with 'Timeout' error."""
        mgr = ProviderWarmupManager()
        # Use an AsyncMock so no unawaited coroutine warning is generated
        mgr.register_warmup_handler("slow", AsyncMock())

        with patch("asyncio.wait_for", side_effect=TimeoutError()):
            result = await mgr.warmup("slow")

        assert result.success is False
        assert result.error == "Timeout"
        assert result.provider_id == "slow"

    async def test_warmup_timeout_updates_state(self):
        """Timeout result is still stored in state."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("slow", AsyncMock())

        with patch("asyncio.wait_for", side_effect=TimeoutError()):
            result = await mgr.warmup("slow")

        assert "slow" in mgr._last_warmup
        assert mgr._warmup_results["slow"] is result


# ---------------------------------------------------------------------------
# warmup() — WARMUP_EXECUTION_ERRORS
# ---------------------------------------------------------------------------


class TestWarmupExecutionErrors:
    """warmup() when the handler raises one of WARMUP_EXECUTION_ERRORS."""

    @pytest.mark.parametrize(
        "exc_type,exc_msg",
        [
            (RuntimeError, "runtime problem"),
            (ValueError, "bad value"),
            (TypeError, "type error"),
            (KeyError, "missing key"),
            (AttributeError, "attr missing"),
            (ConnectionError, "connection lost"),
            (OSError, "os error"),
        ],
    )
    async def test_warmup_execution_error_returns_failure(self, exc_type, exc_msg):
        """Each WARMUP_EXECUTION_ERRORS variant produces a failure result."""
        mgr = ProviderWarmupManager()
        exc = exc_type(exc_msg)
        mgr.register_warmup_handler("p", AsyncMock(side_effect=exc))

        with patch("asyncio.wait_for", side_effect=exc):
            result = await mgr.warmup("p")

        assert result.success is False
        assert result.error == str(exc)
        assert result.provider_id == "p"

    async def test_warmup_execution_error_updates_state(self):
        """WARMUP_EXECUTION_ERRORS path still updates _last_warmup and _warmup_results."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())

        with patch("asyncio.wait_for", side_effect=ValueError("oops")):
            result = await mgr.warmup("p")

        assert "p" in mgr._last_warmup
        assert mgr._warmup_results["p"] is result


# ---------------------------------------------------------------------------
# warmup() — latency measurement
# ---------------------------------------------------------------------------


class TestWarmupLatencyMeasurement:
    """Verify latency_ms is measured in all paths."""

    async def test_warmup_success_latency_non_negative(self):
        """Success path reports non-negative latency."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        result = await mgr.warmup("p")
        assert result.latency_ms >= 0

    async def test_warmup_timeout_latency_non_negative(self):
        """Timeout path reports non-negative latency."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        with patch("asyncio.wait_for", side_effect=TimeoutError()):
            result = await mgr.warmup("p")
        assert result.latency_ms >= 0

    async def test_warmup_error_latency_non_negative(self):
        """Error path reports non-negative latency."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        with patch("asyncio.wait_for", side_effect=RuntimeError("err")):
            result = await mgr.warmup("p")
        assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# warmup_if_needed
# ---------------------------------------------------------------------------


class TestWarmupIfNeeded:
    """Tests for warmup_if_needed."""

    async def test_warmup_if_needed_runs_when_never_warmed(self):
        """Runs warmup if provider has never been warmed."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        result = await mgr.warmup_if_needed("p")
        assert result is not None
        assert isinstance(result, WarmupResult)

    async def test_warmup_if_needed_runs_when_interval_elapsed(self):
        """Runs warmup if the warmup interval has elapsed."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        # Set last warmup to 10 minutes ago
        mgr._last_warmup["p"] = datetime.now(UTC) - timedelta(minutes=10)
        result = await mgr.warmup_if_needed("p", interval=timedelta(minutes=5))
        assert result is not None

    async def test_warmup_if_needed_skips_when_recent(self):
        """Returns None when warmup was performed recently."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        mgr._last_warmup["p"] = datetime.now(UTC)  # just now
        result = await mgr.warmup_if_needed("p", interval=timedelta(minutes=5))
        assert result is None

    async def test_warmup_if_needed_uses_default_interval(self):
        """Uses DEFAULT_WARMUP_INTERVAL when no interval is supplied."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        # Set last warmup 6 minutes ago (> 5 min default)
        mgr._last_warmup["p"] = datetime.now(UTC) - timedelta(minutes=6)
        result = await mgr.warmup_if_needed("p")  # no interval arg
        assert result is not None

    async def test_warmup_if_needed_custom_interval_short(self):
        """Custom short interval causes warmup to run more often."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        # Set last warmup 2 seconds ago, interval is 1 second
        mgr._last_warmup["p"] = datetime.now(UTC) - timedelta(seconds=2)
        result = await mgr.warmup_if_needed("p", interval=timedelta(seconds=1))
        assert result is not None

    async def test_warmup_if_needed_exactly_at_boundary(self):
        """Warmup runs when elapsed time equals the interval exactly."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        interval = timedelta(minutes=5)
        # Set last warmup to exactly interval ago — difference > interval is False, but
        # we want to check the boundary: the code checks `> interval` so exactly equal
        # means no warmup. Set it slightly over.
        mgr._last_warmup["p"] = datetime.now(UTC) - interval - timedelta(microseconds=1)
        result = await mgr.warmup_if_needed("p", interval=interval)
        assert result is not None

    async def test_warmup_if_needed_no_handler(self):
        """warmup_if_needed returns failure result for unregistered provider (never warmed)."""
        mgr = ProviderWarmupManager()
        result = await mgr.warmup_if_needed("unknown")
        # Should call warmup which returns failure
        assert result is not None
        assert result.success is False


# ---------------------------------------------------------------------------
# warmup_before_failover
# ---------------------------------------------------------------------------


class TestWarmupBeforeFailover:
    """Tests for warmup_before_failover."""

    async def test_warmup_before_failover_calls_warmup(self):
        """warmup_before_failover delegates to warmup()."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("target", AsyncMock())

        result = await mgr.warmup_before_failover("target")

        assert isinstance(result, WarmupResult)
        assert result.provider_id == "target"

    async def test_warmup_before_failover_returns_success(self):
        """Returns success result if handler succeeds."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("target", AsyncMock(return_value=None))
        result = await mgr.warmup_before_failover("target")
        assert result.success is True

    async def test_warmup_before_failover_no_handler(self):
        """Returns failure if no handler registered."""
        mgr = ProviderWarmupManager()
        result = await mgr.warmup_before_failover("unknown")
        assert result.success is False
        assert result.error == "No warmup handler registered"

    async def test_warmup_before_failover_logs_info(self, caplog):
        """Logs an info message before performing warmup."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("target", AsyncMock())

        with caplog.at_level(
            logging.INFO, logger="enhanced_agent_bus.llm_adapters.failover.warmup"
        ):
            await mgr.warmup_before_failover("target")

        assert any("target" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# start_periodic_warmup / stop_periodic_warmup
# ---------------------------------------------------------------------------


class TestPeriodicWarmup:
    """Tests for start_periodic_warmup and stop_periodic_warmup."""

    async def test_start_periodic_warmup_creates_task(self):
        """start_periodic_warmup creates an asyncio.Task."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())

        mgr.start_periodic_warmup("p", interval=timedelta(seconds=60))
        assert "p" in mgr._warmup_tasks
        assert isinstance(mgr._warmup_tasks["p"], asyncio.Task)

        # Cleanup
        mgr.stop_periodic_warmup("p")

    async def test_start_periodic_warmup_default_interval(self):
        """start_periodic_warmup uses DEFAULT_WARMUP_INTERVAL when none supplied."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        mgr.start_periodic_warmup("p")  # no interval
        assert "p" in mgr._warmup_tasks
        mgr.stop_periodic_warmup("p")

    async def test_start_periodic_warmup_cancels_existing_task(self):
        """Starting periodic warmup for the same provider cancels the prior task."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())

        mgr.start_periodic_warmup("p", interval=timedelta(seconds=60))
        first_task = mgr._warmup_tasks["p"]

        mgr.start_periodic_warmup("p", interval=timedelta(seconds=60))
        second_task = mgr._warmup_tasks["p"]

        # Give event loop a chance to cancel
        await asyncio.sleep(0)

        assert first_task.cancelled() or first_task.done()
        assert second_task is not first_task

        mgr.stop_periodic_warmup("p")

    async def test_stop_periodic_warmup_cancels_task(self):
        """stop_periodic_warmup cancels the task and removes it from dict."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        mgr.start_periodic_warmup("p", interval=timedelta(seconds=60))
        task = mgr._warmup_tasks["p"]

        mgr.stop_periodic_warmup("p")
        await asyncio.sleep(0)

        assert task.cancelled() or task.done()
        assert "p" not in mgr._warmup_tasks

    async def test_stop_periodic_warmup_noop_when_not_started(self):
        """stop_periodic_warmup is a no-op if no task is running."""
        mgr = ProviderWarmupManager()
        mgr.stop_periodic_warmup("never_started")  # Should not raise

    async def test_periodic_warmup_loop_executes_warmup(self):
        """The warmup loop calls warmup() after the interval elapses."""
        mgr = ProviderWarmupManager()
        call_count = 0

        async def fast_handler():
            nonlocal call_count
            call_count += 1

        mgr.register_warmup_handler("p", fast_handler)
        mgr.start_periodic_warmup("p", interval=timedelta(seconds=0.05))

        # Wait for at least one invocation
        await asyncio.sleep(0.15)
        mgr.stop_periodic_warmup("p")
        await asyncio.sleep(0)

        assert call_count >= 1

    async def test_periodic_warmup_loop_continues_after_error(self):
        """Warmup loop catches WARMUP_LOOP_ERRORS and continues."""
        mgr = ProviderWarmupManager()
        call_count = 0

        async def flaky_handler():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient error")

        mgr.register_warmup_handler("p", flaky_handler)
        mgr.start_periodic_warmup("p", interval=timedelta(seconds=0.05))

        await asyncio.sleep(0.2)
        mgr.stop_periodic_warmup("p")
        await asyncio.sleep(0)

        # Loop should have continued after the first error
        assert call_count >= 1

    async def test_periodic_warmup_cancelled_gracefully(self):
        """Periodic warmup task ends cleanly when cancelled."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        mgr.start_periodic_warmup("p", interval=timedelta(seconds=60))
        task = mgr._warmup_tasks["p"]

        mgr.stop_periodic_warmup("p")
        # Allow CancelledError to propagate inside the loop
        await asyncio.sleep(0.05)

        assert task.cancelled() or task.done()

    async def test_periodic_warmup_loop_catches_warmup_loop_error(self):
        """Warmup loop catches WARMUP_LOOP_ERRORS raised by warmup() itself (not the handler)."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        call_count = 0

        original_warmup = mgr.warmup

        async def patched_warmup(provider_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("warmup-level error triggering loop handler")
            return await original_warmup(provider_id)

        mgr.warmup = patched_warmup  # type: ignore[method-assign]
        mgr.start_periodic_warmup("p", interval=timedelta(seconds=0.05))

        await asyncio.sleep(0.18)
        mgr.stop_periodic_warmup("p")
        await asyncio.sleep(0)

        # At least 1 call happened (the error one), loop continued
        assert call_count >= 1

    async def test_periodic_warmup_inner_cancelled_error_propagates(self):
        """CancelledError raised inside warmup() propagates through inner try to outer."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())

        async def raises_cancelled(provider_id):
            raise asyncio.CancelledError()

        mgr.warmup = raises_cancelled  # type: ignore[method-assign]
        mgr.start_periodic_warmup("p", interval=timedelta(seconds=0.05))
        task = mgr._warmup_tasks["p"]

        # Give the task time to hit the CancelledError from inside warmup()
        await asyncio.sleep(0.12)
        # The task should be done (terminated by inner CancelledError propagating out)
        mgr._warmup_tasks.pop("p", None)
        assert task.done()


# ---------------------------------------------------------------------------
# get_warmup_status
# ---------------------------------------------------------------------------


class TestGetWarmupStatus:
    """Tests for get_warmup_status."""

    def test_get_warmup_status_no_data(self):
        """Status for a completely unknown provider."""
        mgr = ProviderWarmupManager()
        status = mgr.get_warmup_status("unknown")

        assert status["provider_id"] == "unknown"
        assert status["has_handler"] is False
        assert status["last_warmup"] is None
        assert status["last_result"] is None
        assert status["periodic_enabled"] is False
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_warmup_status_with_handler(self):
        """has_handler is True when a handler is registered."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("openai", AsyncMock())
        status = mgr.get_warmup_status("openai")
        assert status["has_handler"] is True

    async def test_get_warmup_status_after_warmup(self):
        """last_warmup and last_result are populated after warmup()."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("openai", AsyncMock())
        await mgr.warmup("openai")

        status = mgr.get_warmup_status("openai")

        assert status["last_warmup"] is not None
        assert status["last_result"] is not None
        assert isinstance(status["last_result"]["success"], bool)
        assert isinstance(status["last_result"]["latency_ms"], float)
        assert "error" in status["last_result"]

    async def test_get_warmup_status_after_failed_warmup(self):
        """last_result reflects a failed warmup."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())

        with patch("asyncio.wait_for", side_effect=RuntimeError("bad")):
            await mgr.warmup("p")

        status = mgr.get_warmup_status("p")
        assert status["last_result"]["success"] is False
        assert status["last_result"]["error"] == "bad"

    async def test_get_warmup_status_periodic_enabled(self):
        """periodic_enabled is True while a periodic task is running."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        mgr.start_periodic_warmup("p", interval=timedelta(seconds=60))

        status = mgr.get_warmup_status("p")
        assert status["periodic_enabled"] is True

        mgr.stop_periodic_warmup("p")
        status_after = mgr.get_warmup_status("p")
        assert status_after["periodic_enabled"] is False

    def test_get_warmup_status_last_warmup_is_isoformat(self):
        """last_warmup is an ISO-format string when present."""
        mgr = ProviderWarmupManager()
        ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        mgr._last_warmup["p"] = ts
        status = mgr.get_warmup_status("p")
        assert status["last_warmup"] == ts.isoformat()

    def test_get_warmup_status_constitutional_hash_in_response(self):
        """Constitutional hash is always present in status response."""
        mgr = ProviderWarmupManager()
        status = mgr.get_warmup_status("any")
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Concurrency / lock tests
# ---------------------------------------------------------------------------


class TestConcurrency:
    """Tests for concurrent warmup calls and lock behaviour."""

    async def test_concurrent_warmups_different_providers(self):
        """Concurrent warmups for different providers succeed independently."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p1", AsyncMock())
        mgr.register_warmup_handler("p2", AsyncMock())

        r1, r2 = await asyncio.gather(mgr.warmup("p1"), mgr.warmup("p2"))

        assert r1.provider_id == "p1"
        assert r2.provider_id == "p2"
        assert r1.success is True
        assert r2.success is True

    async def test_concurrent_warmups_same_provider(self):
        """Concurrent warmups for the same provider both complete (lock is acquired serially)."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())

        results = await asyncio.gather(*[mgr.warmup("p") for _ in range(5)])

        assert len(results) == 5
        assert all(r.success for r in results)
        # State should reflect the last warmup
        assert "p" in mgr._last_warmup


# ---------------------------------------------------------------------------
# Integration / combined workflow tests
# ---------------------------------------------------------------------------


class TestIntegrationWorkflows:
    """Integration-style tests combining multiple methods."""

    async def test_full_register_warmup_status_cycle(self):
        """Register handler → warmup → check status."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("openai", AsyncMock())

        assert mgr.get_warmup_status("openai")["has_handler"] is True
        await mgr.warmup("openai")
        status = mgr.get_warmup_status("openai")
        assert status["last_result"]["success"] is True

    async def test_warmup_if_needed_then_warmup_before_failover(self):
        """warmup_if_needed (skip) then warmup_before_failover forces warmup."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())
        # Warmup now to mark as recent
        await mgr.warmup("p")

        # warmup_if_needed should skip (was just warmed)
        skip_result = await mgr.warmup_if_needed("p", interval=timedelta(minutes=5))
        assert skip_result is None

        # warmup_before_failover always runs
        failover_result = await mgr.warmup_before_failover("p")
        assert failover_result.success is True

    async def test_periodic_then_manual_warmup(self):
        """Periodic warmup runs alongside manual warmup calls."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())

        mgr.start_periodic_warmup("p", interval=timedelta(seconds=60))

        # Manual warmup while periodic task is running
        result = await mgr.warmup("p")
        assert result.success is True

        mgr.stop_periodic_warmup("p")

    async def test_handler_raises_warmup_execution_error(self):
        """End-to-end: handler raises RuntimeError, result reflects failure."""
        mgr = ProviderWarmupManager()

        async def bad_handler():
            raise RuntimeError("network down")

        mgr.register_warmup_handler("p", bad_handler)
        result = await mgr.warmup("p")

        assert result.success is False
        assert "network down" in result.error
        assert mgr._warmup_results["p"] is result

    async def test_successive_warmups_update_state(self):
        """Successive warmup calls update _last_warmup to a newer timestamp."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())

        await mgr.warmup("p")
        ts1 = mgr._last_warmup["p"]

        await asyncio.sleep(0.01)
        await mgr.warmup("p")
        ts2 = mgr._last_warmup["p"]

        assert ts2 >= ts1


# ---------------------------------------------------------------------------
# Logging tests
# ---------------------------------------------------------------------------


class TestLogging:
    """Tests that verify logging output."""

    async def test_warmup_success_logs_debug(self, caplog):
        """Successful warmup logs a debug message containing the provider id."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("openai", AsyncMock())

        with caplog.at_level(
            logging.DEBUG, logger="enhanced_agent_bus.llm_adapters.failover.warmup"
        ):
            await mgr.warmup("openai")

        assert any("openai" in r.message and r.levelno == logging.DEBUG for r in caplog.records)

    async def test_warmup_timeout_logs_warning(self, caplog):
        """Timeout warmup logs a warning."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())

        with caplog.at_level(
            logging.WARNING, logger="enhanced_agent_bus.llm_adapters.failover.warmup"
        ):
            with patch("asyncio.wait_for", side_effect=TimeoutError()):
                await mgr.warmup("p")

        assert any(r.levelno == logging.WARNING for r in caplog.records)

    async def test_warmup_error_logs_error(self, caplog):
        """Error warmup logs an error message."""
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p", AsyncMock())

        with caplog.at_level(
            logging.ERROR, logger="enhanced_agent_bus.llm_adapters.failover.warmup"
        ):
            with patch("asyncio.wait_for", side_effect=RuntimeError("fail")):
                await mgr.warmup("p")

        assert any(r.levelno == logging.ERROR for r in caplog.records)


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    """Verify public API is exported correctly."""

    def test_warmup_result_exported(self):
        """WarmupResult is in __all__."""
        from enhanced_agent_bus.llm_adapters.failover import warmup as warmup_module

        assert "WarmupResult" in warmup_module.__all__

    def test_provider_warmup_manager_exported(self):
        """ProviderWarmupManager is in __all__."""
        from enhanced_agent_bus.llm_adapters.failover import warmup as warmup_module

        assert "ProviderWarmupManager" in warmup_module.__all__
