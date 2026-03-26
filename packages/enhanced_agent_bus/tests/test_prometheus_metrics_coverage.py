# Constitutional Hash: 608508a9bd224290
"""
Additional coverage tests for prometheus_metrics.py — targeting ≥90% coverage.

Covers:
- _get_constitutional_validations_counter() second call (already-initialized path)
- ValueError re-raise when "Duplicated timeseries" NOT in message
- MetricsCollector.__post_init__ when PROMETHEUS_AVAILABLE=False
- MetricsCollector.__post_init__ exception handler (lines 250-251)
- get_metrics() return b"" when PROMETHEUS_AVAILABLE=False (line 389)
- create_metrics_endpoint() FastAPI path and ImportError path (lines 516-531)
"""

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to reach the module via importlib mode
# ---------------------------------------------------------------------------

_MODULE_PATH = "enhanced_agent_bus.observability.prometheus_metrics"


def _fresh_module():
    """Return a freshly-imported copy of the module under test."""
    mod_name = _MODULE_PATH
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


# ---------------------------------------------------------------------------
# Import the module once for the majority of tests
# ---------------------------------------------------------------------------

import enhanced_agent_bus.observability.prometheus_metrics as pm

# ---------------------------------------------------------------------------
# _get_constitutional_validations_counter — already-initialised path
# ---------------------------------------------------------------------------


class TestGetConstitutionalValidationsCounterCached:
    """Line 75->91: call the factory twice so the second call returns cache."""

    def test_second_call_returns_same_object(self):
        """Calling the getter twice returns identical object (cached path)."""
        # Ensure the module-level global was already set by import-time call.
        first = pm._get_constitutional_validations_counter()
        second = pm._get_constitutional_validations_counter()
        assert first is second

    def test_reset_then_call_returns_noop_when_prometheus_unavailable(self):
        """When PROMETHEUS_AVAILABLE=False the getter creates a NoOpCounter."""
        original = pm._acgs_constitutional_validations_total
        try:
            pm._acgs_constitutional_validations_total = None
            with patch.dict(
                pm._get_constitutional_validations_counter.__globals__,
                {"PROMETHEUS_AVAILABLE": False},
            ):
                result = pm._get_constitutional_validations_counter()
            # Should be a no-op counter
            assert hasattr(result, "inc")
            assert hasattr(result, "labels")
        finally:
            pm._acgs_constitutional_validations_total = original


# ---------------------------------------------------------------------------
# _get_constitutional_validations_counter — ValueError re-raise path (88-90)
# ---------------------------------------------------------------------------


class TestGetConstitutionalValidationsCounterValueErrorReRaise:
    """Lines 88-90: ValueError without 'Duplicated timeseries' must be re-raised."""

    def test_value_error_without_duplicated_timeseries_re_raised(self):
        """A ValueError whose message is NOT about duplicate timeseries is re-raised."""
        original = pm._acgs_constitutional_validations_total
        try:
            pm._acgs_constitutional_validations_total = None

            bad_counter = MagicMock(side_effect=ValueError("some other error"))

            with patch.dict(
                pm._get_constitutional_validations_counter.__globals__,
                {"PROMETHEUS_AVAILABLE": True, "Counter": bad_counter},
            ):
                with pytest.raises(ValueError, match="some other error"):
                    pm._get_constitutional_validations_counter()
        finally:
            pm._acgs_constitutional_validations_total = original

    def test_value_error_with_duplicated_timeseries_returns_noop(self):
        """A ValueError about 'Duplicated timeseries' yields a NoOpCounter."""
        original = pm._acgs_constitutional_validations_total
        try:
            pm._acgs_constitutional_validations_total = None

            dup_counter = MagicMock(side_effect=ValueError("Duplicated timeseries in registry"))

            with patch.dict(
                pm._get_constitutional_validations_counter.__globals__,
                {"PROMETHEUS_AVAILABLE": True, "Counter": dup_counter},
            ):
                result = pm._get_constitutional_validations_counter()

            assert hasattr(result, "inc")
        finally:
            pm._acgs_constitutional_validations_total = original


# ---------------------------------------------------------------------------
# MetricsCollector.__post_init__ when PROMETHEUS_AVAILABLE=False (240->exit)
# ---------------------------------------------------------------------------


class TestMetricsCollectorPostInitNoPrometheus:
    """Line 240->exit: __post_init__ skips info() call when prometheus unavailable."""

    def test_post_init_skipped_when_prometheus_unavailable(self):
        """MetricsCollector can be created when PROMETHEUS_AVAILABLE=False."""
        with patch.object(pm, "PROMETHEUS_AVAILABLE", False):
            collector = pm.MetricsCollector(service_name="test-no-prometheus")
        assert collector.service_name == "test-no-prometheus"
        # _initialized stays False because the branch was not entered
        assert collector._initialized is False


# ---------------------------------------------------------------------------
# MetricsCollector.__post_init__ exception handler (lines 250-251)
# ---------------------------------------------------------------------------


class TestMetricsCollectorPostInitException:
    """Lines 250-251: exception in acgs_system_info.info() is caught and logged."""

    def test_post_init_logs_warning_on_info_error(self, caplog):
        """When acgs_system_info.info() raises a covered error, a warning is logged."""
        broken_info = MagicMock()
        broken_info.info.side_effect = RuntimeError("registry error")

        with (
            patch.object(pm, "PROMETHEUS_AVAILABLE", True),
            patch.object(pm, "acgs_system_info", broken_info),
        ):
            import logging

            with caplog.at_level(logging.WARNING):
                collector = pm.MetricsCollector(service_name="test-exc")

        # _initialized was not set to True because the exception path was hit
        assert collector._initialized is False
        assert "Failed to set system info" in caplog.text

    def test_post_init_already_initialized_skips_info_call(self):
        """When _initialized=True __post_init__ does not call info() again."""
        info_mock = MagicMock()

        with (
            patch.object(pm, "PROMETHEUS_AVAILABLE", True),
            patch.object(pm, "acgs_system_info", info_mock),
        ):
            collector = pm.MetricsCollector(service_name="test", _initialized=True)

        info_mock.info.assert_not_called()


# ---------------------------------------------------------------------------
# get_metrics() return b"" path (line 389)
# ---------------------------------------------------------------------------


class TestGetMetricsNoPrometheus:
    """Line 389: get_metrics() returns b'' when PROMETHEUS_AVAILABLE=False."""

    def test_get_metrics_returns_empty_bytes_when_unavailable(self):
        with patch.object(pm, "PROMETHEUS_AVAILABLE", False):
            collector = pm.MetricsCollector()
            result = collector.get_metrics()
        assert result == b""

    def test_get_content_type_returns_plain_text_when_unavailable(self):
        """get_content_type() falls back to CONTENT_TYPE_LATEST when unavailable."""
        with (
            patch.object(pm, "PROMETHEUS_AVAILABLE", False),
            patch.object(pm, "CONTENT_TYPE_LATEST", "text/plain"),
        ):
            collector = pm.MetricsCollector()
            ct = collector.get_content_type()
        assert ct == "text/plain"


# ---------------------------------------------------------------------------
# create_metrics_endpoint() — FastAPI available path (lines 516-531)
# ---------------------------------------------------------------------------


class TestCreateMetricsEndpointFastAPI:
    """Lines 516-531: create_metrics_endpoint() with FastAPI installed."""

    def test_returns_router_when_fastapi_available(self):
        """When fastapi is importable, create_metrics_endpoint returns a router."""
        # Use real fastapi if available, otherwise mock it
        try:
            import fastapi

            router = pm.create_metrics_endpoint()
            assert router is not None
        except ImportError:
            pytest.skip("FastAPI not installed")

    async def test_router_metrics_route_callable(self):
        """The /metrics route should be callable asynchronously."""
        try:
            import fastapi

            router = pm.create_metrics_endpoint()
            assert router is not None
            # Find the /metrics route and call it
            for route in router.routes:
                if route.path == "/metrics":
                    result = await route.endpoint()
                    assert result is not None
                    break
        except ImportError:
            pytest.skip("FastAPI not installed")


# ---------------------------------------------------------------------------
# create_metrics_endpoint() — ImportError path (line 532-534)
# ---------------------------------------------------------------------------


class TestCreateMetricsEndpointImportError:
    """Lines 532-534: create_metrics_endpoint() returns None when FastAPI missing."""

    def test_returns_none_when_fastapi_missing(self, caplog):
        """When FastAPI import fails, function returns None and logs a warning."""
        import builtins
        import logging

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in ("fastapi", "fastapi.routing"):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=fake_import),
            caplog.at_level(logging.WARNING),
        ):
            result = pm.create_metrics_endpoint()

        assert result is None
        assert "FastAPI not available" in caplog.text


# ---------------------------------------------------------------------------
# Validation timer — additional coverage for context value propagation
# ---------------------------------------------------------------------------


class TestValidationTimerEdgeCases:
    """Extra coverage for validation_timer branches."""

    def test_validation_timer_with_custom_endpoint(self):
        """Timer records latency with a custom endpoint label."""
        collector = pm.MetricsCollector()
        with collector.validation_timer(endpoint="/api/v2/validate") as ctx:
            ctx["result"] = pm.ValidationResult.SUCCESS
        assert ctx["result"] == pm.ValidationResult.SUCCESS

    def test_validation_timer_catches_runtime_error(self):
        """RuntimeError inside the timer sets result to ERROR and re-raises."""
        collector = pm.MetricsCollector()
        with pytest.raises(RuntimeError):
            with collector.validation_timer() as ctx:
                raise RuntimeError("boom")
        assert ctx["result"] == pm.ValidationResult.ERROR

    def test_validation_timer_catches_os_error(self):
        """OSError inside the timer sets result to ERROR and re-raises."""
        collector = pm.MetricsCollector()
        with pytest.raises(OSError):
            with collector.validation_timer() as ctx:
                raise OSError("disk error")
        assert ctx["result"] == pm.ValidationResult.ERROR

    def test_validation_timer_catches_type_error(self):
        """TypeError inside the timer sets result to ERROR and re-raises."""
        collector = pm.MetricsCollector()
        with pytest.raises(TypeError):
            with collector.validation_timer() as ctx:
                raise TypeError("type error")
        assert ctx["result"] == pm.ValidationResult.ERROR


# ---------------------------------------------------------------------------
# record_validation — no-confidence path
# ---------------------------------------------------------------------------


class TestRecordValidationNoConfidence:
    """record_validation with confidence=None skips the confidence histogram."""

    def test_record_validation_without_confidence(self):
        """record_validation succeeds when confidence is None."""
        collector = pm.MetricsCollector()
        collector.record_validation(
            result=pm.ValidationResult.TIMEOUT,
            principle_category="rate_limit",
            agent_id="agent-timeout",
            latency_seconds=0.3,
            confidence=None,
        )


# ---------------------------------------------------------------------------
# get_metrics_collector singleton and reset
# ---------------------------------------------------------------------------


class TestGetMetricsCollectorSingleton:
    """Verify singleton semantics and reset."""

    def test_reset_allows_new_instance(self):
        """After reset, a new MetricsCollector is created on next call."""
        pm.reset_metrics_collector()
        c1 = pm.get_metrics_collector()
        pm.reset_metrics_collector()
        c2 = pm.get_metrics_collector()
        assert c1 is not c2

    def test_singleton_after_reset(self):
        """get_metrics_collector returns same object on repeated calls."""
        pm.reset_metrics_collector()
        c1 = pm.get_metrics_collector()
        c2 = pm.get_metrics_collector()
        assert c1 is c2
