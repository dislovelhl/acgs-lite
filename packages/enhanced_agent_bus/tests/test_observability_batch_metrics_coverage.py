# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/observability/batch_metrics.py

Targets ≥95% line coverage of batch_metrics.py (146 stmts).
"""

import time
from unittest.mock import MagicMock, call, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_mock_counter():
    """Return a mock that behaves like NoOpCounter / OTEL Counter."""
    c = MagicMock()
    c.add = MagicMock()
    return c


def _make_mock_histogram():
    """Return a mock that behaves like NoOpHistogram / OTEL Histogram."""
    h = MagicMock()
    h.record = MagicMock()
    return h


def _make_mock_meter():
    """Return a mock meter whose create_counter / create_histogram return traceable mocks."""
    meter = MagicMock()
    meter.create_counter.side_effect = lambda name, **kw: _make_mock_counter()
    meter.create_histogram.side_effect = lambda name, **kw: _make_mock_histogram()
    return meter


# ---------------------------------------------------------------------------
# Module-level import
# ---------------------------------------------------------------------------


class TestModuleImports:
    """Verify the module and its public API can be imported."""

    def test_import_batch_metrics_class(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        assert BatchMetrics is not None

    def test_import_batch_request_timer(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        assert BatchRequestTimer is not None

    def test_import_item_timer(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        assert ItemTimer is not None

    def test_import_get_batch_metrics(self):
        from enhanced_agent_bus.observability.batch_metrics import get_batch_metrics

        assert callable(get_batch_metrics)

    def test_import_reset_batch_metrics(self):
        from enhanced_agent_bus.observability.batch_metrics import reset_batch_metrics

        assert callable(reset_batch_metrics)

    def test_import_batch_metrics_init_errors(self):
        from enhanced_agent_bus.observability.batch_metrics import (
            BATCH_METRICS_INIT_ERRORS,
        )

        assert RuntimeError in BATCH_METRICS_INIT_ERRORS
        assert ValueError in BATCH_METRICS_INIT_ERRORS
        assert TypeError in BATCH_METRICS_INIT_ERRORS
        assert KeyError in BATCH_METRICS_INIT_ERRORS
        assert AttributeError in BATCH_METRICS_INIT_ERRORS


# ---------------------------------------------------------------------------
# BatchMetrics - initialisation path (happy path via NoOpMeter)
# ---------------------------------------------------------------------------


class TestBatchMetricsInit:
    """Test BatchMetrics initialisation and instrumentation creation."""

    def _make_instance(self):
        """Create a BatchMetrics instance with a mock meter injected via get_meter."""
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        mock_meter = _make_mock_meter()
        with patch.object(bm_module, "get_meter", return_value=mock_meter):
            instance = bm_module.BatchMetrics(service_name="test-svc")
        return instance, mock_meter

    def test_post_init_calls_initialize_metrics(self):
        """__post_init__ should call _initialize_metrics."""
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        mock_meter = _make_mock_meter()
        with patch.object(bm_module, "get_meter", return_value=mock_meter):
            instance = bm_module.BatchMetrics(service_name="svc-a")
        assert instance._initialized is True

    def test_initialized_flag_set_after_success(self):
        instance, _ = self._make_instance()
        assert instance._initialized is True

    def test_service_name_stored(self):
        instance, _ = self._make_instance()
        assert instance.service_name == "test-svc"

    def test_all_counters_created(self):
        _instance, mock_meter = self._make_instance()
        # create_counter is called with name= as a keyword argument
        counter_names = [
            c.kwargs.get("name", c.args[0] if c.args else None)
            for c in mock_meter.create_counter.call_args_list
        ]
        expected = [
            "batch_requests_total",
            "batch_items_total",
            "batch_items_success_total",
            "batch_items_failed_total",
            "batch_cache_hits_total",
            "batch_cache_misses_total",
            "batch_errors_total",
            "batch_retries_total",
            "constitutional_validations_total",
            "constitutional_violations_total",
        ]
        for name in expected:
            assert name in counter_names, f"Counter '{name}' not created"

    def test_all_histograms_created(self):
        _instance, mock_meter = self._make_instance()
        # create_histogram is called with name= as a keyword argument
        histogram_names = [
            c.kwargs.get("name", c.args[0] if c.args else None)
            for c in mock_meter.create_histogram.call_args_list
        ]
        expected = [
            "batch_request_duration_seconds",
            "batch_item_duration_seconds",
            "batch_size_distribution",
        ]
        for name in expected:
            assert name in histogram_names, f"Histogram '{name}' not created"

    def test_initialize_metrics_idempotent(self):
        """Calling _initialize_metrics again on already-initialized instance is a no-op."""
        instance, mock_meter = self._make_instance()
        call_count_before = mock_meter.create_counter.call_count
        instance._initialize_metrics()
        assert mock_meter.create_counter.call_count == call_count_before

    def test_default_service_name(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        mock_meter = _make_mock_meter()
        with patch.object(bm_module, "get_meter", return_value=mock_meter):
            instance = bm_module.BatchMetrics()
        assert instance.service_name == "acgs2-batch-processor"

    def test_meter_attribute_set(self):
        instance, mock_meter = self._make_instance()
        assert instance._meter is mock_meter


# ---------------------------------------------------------------------------
# BatchMetrics - fallback / noop path
# ---------------------------------------------------------------------------


class TestBatchMetricsNoopFallback:
    """Test that _use_noop_metrics is called when initialization fails."""

    def _make_failing_instance(self, exc_cls):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        def raise_exc(*args, **kwargs):
            raise exc_cls("boom")

        with patch.object(bm_module, "get_meter", side_effect=raise_exc):
            instance = bm_module.BatchMetrics(service_name="fail-svc")
        return instance

    def test_runtime_error_triggers_noop(self):
        instance = self._make_failing_instance(RuntimeError)
        assert instance._initialized is True
        assert instance._batch_requests_total is not None

    def test_value_error_triggers_noop(self):
        instance = self._make_failing_instance(ValueError)
        assert instance._initialized is True

    def test_type_error_triggers_noop(self):
        instance = self._make_failing_instance(TypeError)
        assert instance._initialized is True

    def test_key_error_triggers_noop(self):
        instance = self._make_failing_instance(KeyError)
        assert instance._initialized is True

    def test_attribute_error_triggers_noop(self):
        instance = self._make_failing_instance(AttributeError)
        assert instance._initialized is True

    def test_noop_metrics_all_set(self):
        instance = self._make_failing_instance(RuntimeError)
        # Verify all metric attributes are populated (not None)
        for attr in [
            "_batch_requests_total",
            "_batch_items_total",
            "_batch_items_success",
            "_batch_items_failed",
            "_batch_cache_hits",
            "_batch_cache_misses",
            "_batch_errors_total",
            "_batch_retries_total",
            "_constitutional_validations",
            "_constitutional_violations",
            "_batch_request_duration",
            "_batch_item_duration",
            "_batch_size_distribution",
        ]:
            assert getattr(instance, attr) is not None, f"{attr} is None after noop fallback"

    def test_use_noop_metrics_directly(self):
        """Call _use_noop_metrics() directly on an already-initialized instance."""
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        mock_meter = _make_mock_meter()
        with patch.object(bm_module, "get_meter", return_value=mock_meter):
            instance = bm_module.BatchMetrics()
        # Forcefully call noop again; should not raise
        instance._use_noop_metrics()
        assert instance._initialized is True


# ---------------------------------------------------------------------------
# BatchMetrics - record_batch_request
# ---------------------------------------------------------------------------


class TestRecordBatchRequest:
    """record_batch_request coverage."""

    def _instance(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        mock_meter = _make_mock_meter()
        with patch.object(bm_module, "get_meter", return_value=mock_meter):
            inst = bm_module.BatchMetrics()
        return inst

    def test_records_batch_request_counter(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_requests_total = counter
        inst.record_batch_request("t1", 10, True, 0.5)
        counter.add.assert_called_once()
        args, _ = counter.add.call_args
        assert args[0] == 1

    def test_records_batch_size_distribution(self):
        inst = self._instance()
        hist = _make_mock_histogram()
        inst._batch_size_distribution = hist
        inst.record_batch_request("t1", 42, True, 0.1)
        hist.record.assert_called()
        call_args = hist.record.call_args_list[0]
        assert call_args[0][0] == 42

    def test_records_request_duration(self):
        inst = self._instance()
        hist = _make_mock_histogram()
        inst._batch_request_duration = hist
        inst.record_batch_request("t1", 5, True, 1.23)
        hist.record.assert_called()
        call_args = hist.record.call_args_list[0]
        assert call_args[0][0] == pytest.approx(1.23)

    def test_cache_hits_recorded_when_positive(self):
        inst = self._instance()
        cache_hits = _make_mock_counter()
        inst._batch_cache_hits = cache_hits
        inst.record_batch_request("t1", 5, True, 0.1, cache_hits=3)
        cache_hits.add.assert_called_once()
        args, _ = cache_hits.add.call_args
        assert args[0] == 3

    def test_cache_hits_not_recorded_when_zero(self):
        inst = self._instance()
        cache_hits = _make_mock_counter()
        inst._batch_cache_hits = cache_hits
        inst.record_batch_request("t1", 5, True, 0.1, cache_hits=0)
        cache_hits.add.assert_not_called()

    def test_cache_misses_recorded_when_positive(self):
        inst = self._instance()
        cache_misses = _make_mock_counter()
        inst._batch_cache_misses = cache_misses
        inst.record_batch_request("t1", 5, True, 0.1, cache_misses=7)
        cache_misses.add.assert_called_once()
        args, _ = cache_misses.add.call_args
        assert args[0] == 7

    def test_cache_misses_not_recorded_when_zero(self):
        inst = self._instance()
        cache_misses = _make_mock_counter()
        inst._batch_cache_misses = cache_misses
        inst.record_batch_request("t1", 5, True, 0.1, cache_misses=0)
        cache_misses.add.assert_not_called()

    def test_success_false_in_attributes(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_requests_total = counter
        inst.record_batch_request("t1", 5, False, 0.1)
        _, _kwargs = counter.add.call_args
        attrs = counter.add.call_args[0][1]
        assert attrs["success"] == "false"

    def test_success_true_in_attributes(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_requests_total = counter
        inst.record_batch_request("t2", 5, True, 0.1)
        attrs = counter.add.call_args[0][1]
        assert attrs["success"] == "true"

    def test_tenant_id_in_attributes(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_requests_total = counter
        inst.record_batch_request("tenant-xyz", 5, True, 0.1)
        attrs = counter.add.call_args[0][1]
        assert attrs["tenant_id"] == "tenant-xyz"

    def test_constitutional_hash_in_attributes(self):
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_requests_total = counter
        inst.record_batch_request("t1", 5, True, 0.1)
        attrs = counter.add.call_args[0][1]
        assert attrs["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_both_cache_hits_and_misses(self):
        inst = self._instance()
        hits_counter = _make_mock_counter()
        misses_counter = _make_mock_counter()
        inst._batch_cache_hits = hits_counter
        inst._batch_cache_misses = misses_counter
        inst.record_batch_request("t1", 10, True, 0.5, cache_hits=4, cache_misses=6)
        hits_counter.add.assert_called_once()
        misses_counter.add.assert_called_once()


# ---------------------------------------------------------------------------
# BatchMetrics - record_items_processed
# ---------------------------------------------------------------------------


class TestRecordItemsProcessed:
    def _instance(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        mock_meter = _make_mock_meter()
        with patch.object(bm_module, "get_meter", return_value=mock_meter):
            return bm_module.BatchMetrics()

    def test_adds_total(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_items_total = counter
        inst.record_items_processed("t1", total=20, successful=18, failed=2)
        args, _ = counter.add.call_args
        assert args[0] == 20

    def test_adds_successful(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_items_success = counter
        inst.record_items_processed("t1", total=20, successful=18, failed=2)
        args, _ = counter.add.call_args
        assert args[0] == 18

    def test_adds_failed(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_items_failed = counter
        inst.record_items_processed("t1", total=20, successful=18, failed=2)
        args, _ = counter.add.call_args
        assert args[0] == 2

    def test_tenant_id_in_attrs(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_items_total = counter
        inst.record_items_processed("my-tenant", total=5, successful=5, failed=0)
        attrs = counter.add.call_args[0][1]
        assert attrs["tenant_id"] == "my-tenant"

    def test_zero_counts_still_calls_add(self):
        inst = self._instance()
        total_counter = _make_mock_counter()
        inst._batch_items_total = total_counter
        inst.record_items_processed("t1", total=0, successful=0, failed=0)
        total_counter.add.assert_called_once()


# ---------------------------------------------------------------------------
# BatchMetrics - record_item_duration
# ---------------------------------------------------------------------------


class TestRecordItemDuration:
    def _instance(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        mock_meter = _make_mock_meter()
        with patch.object(bm_module, "get_meter", return_value=mock_meter):
            return bm_module.BatchMetrics()

    def test_records_histogram(self):
        inst = self._instance()
        hist = _make_mock_histogram()
        inst._batch_item_duration = hist
        inst.record_item_duration("t1", 0.042, True)
        hist.record.assert_called_once()
        args, _ = hist.record.call_args
        assert args[0] == pytest.approx(0.042)

    def test_success_true_in_attrs(self):
        inst = self._instance()
        hist = _make_mock_histogram()
        inst._batch_item_duration = hist
        inst.record_item_duration("t1", 0.1, True)
        attrs = hist.record.call_args[0][1]
        assert attrs["success"] == "true"

    def test_success_false_in_attrs(self):
        inst = self._instance()
        hist = _make_mock_histogram()
        inst._batch_item_duration = hist
        inst.record_item_duration("t1", 0.1, False)
        attrs = hist.record.call_args[0][1]
        assert attrs["success"] == "false"

    def test_tenant_id_in_attrs(self):
        inst = self._instance()
        hist = _make_mock_histogram()
        inst._batch_item_duration = hist
        inst.record_item_duration("tenant-abc", 0.01, True)
        attrs = hist.record.call_args[0][1]
        assert attrs["tenant_id"] == "tenant-abc"


# ---------------------------------------------------------------------------
# BatchMetrics - record_error
# ---------------------------------------------------------------------------


class TestRecordError:
    def _instance(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        mock_meter = _make_mock_meter()
        with patch.object(bm_module, "get_meter", return_value=mock_meter):
            return bm_module.BatchMetrics()

    def test_adds_one_to_errors(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_errors_total = counter
        inst.record_error("t1", "timeout")
        args, _ = counter.add.call_args
        assert args[0] == 1

    def test_error_type_in_attrs(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_errors_total = counter
        inst.record_error("t1", "validation")
        attrs = counter.add.call_args[0][1]
        assert attrs["error_type"] == "validation"

    def test_error_code_set_when_provided(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_errors_total = counter
        inst.record_error("t1", "processing", error_code="E001")
        attrs = counter.add.call_args[0][1]
        assert attrs["error_code"] == "E001"

    def test_error_code_defaults_to_unknown(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_errors_total = counter
        inst.record_error("t1", "timeout")
        attrs = counter.add.call_args[0][1]
        assert attrs["error_code"] == "unknown"

    def test_error_code_none_becomes_unknown(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_errors_total = counter
        inst.record_error("t1", "timeout", error_code=None)
        attrs = counter.add.call_args[0][1]
        assert attrs["error_code"] == "unknown"

    def test_tenant_id_in_attrs(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_errors_total = counter
        inst.record_error("my-tenant", "timeout")
        attrs = counter.add.call_args[0][1]
        assert attrs["tenant_id"] == "my-tenant"


# ---------------------------------------------------------------------------
# BatchMetrics - record_retry
# ---------------------------------------------------------------------------


class TestRecordRetry:
    def _instance(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        mock_meter = _make_mock_meter()
        with patch.object(bm_module, "get_meter", return_value=mock_meter):
            return bm_module.BatchMetrics()

    def test_adds_one_to_retries(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_retries_total = counter
        inst.record_retry("t1", attempt=2, reason="timeout")
        args, _ = counter.add.call_args
        assert args[0] == 1

    def test_attempt_in_attrs(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_retries_total = counter
        inst.record_retry("t1", attempt=3, reason="backpressure")
        attrs = counter.add.call_args[0][1]
        assert attrs["attempt"] == "3"

    def test_reason_in_attrs(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_retries_total = counter
        inst.record_retry("t1", attempt=1, reason="network-error")
        attrs = counter.add.call_args[0][1]
        assert attrs["reason"] == "network-error"

    def test_tenant_id_in_attrs(self):
        inst = self._instance()
        counter = _make_mock_counter()
        inst._batch_retries_total = counter
        inst.record_retry("tenant-456", attempt=1, reason="ok")
        attrs = counter.add.call_args[0][1]
        assert attrs["tenant_id"] == "tenant-456"


# ---------------------------------------------------------------------------
# BatchMetrics - record_constitutional_validation
# ---------------------------------------------------------------------------


class TestRecordConstitutionalValidation:
    def _instance(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        mock_meter = _make_mock_meter()
        with patch.object(bm_module, "get_meter", return_value=mock_meter):
            return bm_module.BatchMetrics()

    def test_valid_true_increments_validations_only(self):
        inst = self._instance()
        val_counter = _make_mock_counter()
        viol_counter = _make_mock_counter()
        inst._constitutional_validations = val_counter
        inst._constitutional_violations = viol_counter
        inst.record_constitutional_validation("t1", valid=True, hash_used=CONSTITUTIONAL_HASH)
        val_counter.add.assert_called_once()
        viol_counter.add.assert_not_called()

    def test_valid_false_increments_both(self):
        inst = self._instance()
        val_counter = _make_mock_counter()
        viol_counter = _make_mock_counter()
        inst._constitutional_validations = val_counter
        inst._constitutional_violations = viol_counter
        inst.record_constitutional_validation("t1", valid=False, hash_used="wronghash")
        val_counter.add.assert_called_once()
        viol_counter.add.assert_called_once()

    def test_expected_hash_in_attributes(self):
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        inst = self._instance()
        val_counter = _make_mock_counter()
        inst._constitutional_validations = val_counter
        inst.record_constitutional_validation("t1", valid=True, hash_used=CONSTITUTIONAL_HASH)
        attrs = val_counter.add.call_args[0][1]
        assert attrs["expected_hash"] == CONSTITUTIONAL_HASH

    def test_violation_actual_hash_in_attrs(self):
        inst = self._instance()
        viol_counter = _make_mock_counter()
        inst._constitutional_violations = viol_counter
        inst.record_constitutional_validation("t1", valid=False, hash_used="badhash")
        attrs = viol_counter.add.call_args[0][1]
        assert attrs["actual_hash"] == "badhash"

    def test_violation_missing_hash_becomes_missing_string(self):
        inst = self._instance()
        viol_counter = _make_mock_counter()
        inst._constitutional_violations = viol_counter
        # hash_used is empty string which is falsy
        inst.record_constitutional_validation("t1", valid=False, hash_used="")
        attrs = viol_counter.add.call_args[0][1]
        assert attrs["actual_hash"] == "missing"

    def test_tenant_id_in_validation_attrs(self):
        inst = self._instance()
        val_counter = _make_mock_counter()
        inst._constitutional_validations = val_counter
        inst.record_constitutional_validation("tenant-q", valid=True, hash_used="h")
        attrs = val_counter.add.call_args[0][1]
        assert attrs["tenant_id"] == "tenant-q"


# ---------------------------------------------------------------------------
# BatchMetrics - record_cache_stats
# ---------------------------------------------------------------------------


class TestRecordCacheStats:
    def _instance(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        mock_meter = _make_mock_meter()
        with patch.object(bm_module, "get_meter", return_value=mock_meter):
            return bm_module.BatchMetrics()

    def test_hits_positive_recorded(self):
        inst = self._instance()
        hits_counter = _make_mock_counter()
        inst._batch_cache_hits = hits_counter
        inst.record_cache_stats("t1", hits=5, misses=0)
        hits_counter.add.assert_called_once()
        args, _ = hits_counter.add.call_args
        assert args[0] == 5

    def test_hits_zero_not_recorded(self):
        inst = self._instance()
        hits_counter = _make_mock_counter()
        inst._batch_cache_hits = hits_counter
        inst.record_cache_stats("t1", hits=0, misses=3)
        hits_counter.add.assert_not_called()

    def test_misses_positive_recorded(self):
        inst = self._instance()
        misses_counter = _make_mock_counter()
        inst._batch_cache_misses = misses_counter
        inst.record_cache_stats("t1", hits=0, misses=9)
        misses_counter.add.assert_called_once()
        args, _ = misses_counter.add.call_args
        assert args[0] == 9

    def test_misses_zero_not_recorded(self):
        inst = self._instance()
        misses_counter = _make_mock_counter()
        inst._batch_cache_misses = misses_counter
        inst.record_cache_stats("t1", hits=2, misses=0)
        misses_counter.add.assert_not_called()

    def test_both_zero_neither_recorded(self):
        inst = self._instance()
        hits = _make_mock_counter()
        misses = _make_mock_counter()
        inst._batch_cache_hits = hits
        inst._batch_cache_misses = misses
        inst.record_cache_stats("t1", hits=0, misses=0)
        hits.add.assert_not_called()
        misses.add.assert_not_called()

    def test_both_positive_both_recorded(self):
        inst = self._instance()
        hits = _make_mock_counter()
        misses = _make_mock_counter()
        inst._batch_cache_hits = hits
        inst._batch_cache_misses = misses
        inst.record_cache_stats("t1", hits=3, misses=7)
        hits.add.assert_called_once()
        misses.add.assert_called_once()

    def test_tenant_id_in_attrs(self):
        inst = self._instance()
        hits = _make_mock_counter()
        inst._batch_cache_hits = hits
        inst.record_cache_stats("tenant-z", hits=1, misses=0)
        attrs = hits.add.call_args[0][1]
        assert attrs["tenant_id"] == "tenant-z"


# ---------------------------------------------------------------------------
# Singleton: get_batch_metrics / reset_batch_metrics
# ---------------------------------------------------------------------------


class TestSingleton:
    def setup_method(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        bm_module.reset_batch_metrics()

    def teardown_method(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        bm_module.reset_batch_metrics()

    def test_get_batch_metrics_returns_instance(self):
        from enhanced_agent_bus.observability.batch_metrics import (
            BatchMetrics,
            get_batch_metrics,
        )

        inst = get_batch_metrics()
        assert isinstance(inst, BatchMetrics)

    def test_get_batch_metrics_singleton(self):
        from enhanced_agent_bus.observability.batch_metrics import get_batch_metrics

        a = get_batch_metrics()
        b = get_batch_metrics()
        assert a is b

    def test_reset_clears_singleton(self):
        from enhanced_agent_bus.observability.batch_metrics import (
            get_batch_metrics,
            reset_batch_metrics,
        )

        a = get_batch_metrics()
        reset_batch_metrics()
        b = get_batch_metrics()
        assert a is not b

    def test_reset_then_get_creates_new_instance(self):
        from enhanced_agent_bus.observability.batch_metrics import (
            BatchMetrics,
            get_batch_metrics,
            reset_batch_metrics,
        )

        reset_batch_metrics()
        inst = get_batch_metrics()
        assert isinstance(inst, BatchMetrics)

    def test_module_global_starts_none_after_reset(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        bm_module.reset_batch_metrics()
        assert bm_module._batch_metrics is None


# ---------------------------------------------------------------------------
# BatchRequestTimer - context manager
# ---------------------------------------------------------------------------


class TestBatchRequestTimer:
    def setup_method(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        bm_module.reset_batch_metrics()

    def teardown_method(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        bm_module.reset_batch_metrics()

    def _mock_metrics(self):
        """Return a mock BatchMetrics and patch get_batch_metrics."""
        mock_inst = MagicMock()
        return mock_inst

    def test_enter_returns_timer(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=MagicMock(),
        ):
            timer = BatchRequestTimer("t1", 50)
            result = timer.__enter__()
        assert result is timer

    def test_start_time_set_on_enter(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            timer = BatchRequestTimer("t1", 10)
            timer.__enter__()
            assert timer.start_time > 0

    def test_successful_exit_calls_record_batch_request(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with BatchRequestTimer("t1", 20) as timer:
                timer.record_items(successful=18, failed=2)

        mock_metrics.record_batch_request.assert_called_once()
        call_kwargs = mock_metrics.record_batch_request.call_args[1]
        assert call_kwargs["tenant_id"] == "t1"
        assert call_kwargs["batch_size"] == 20
        assert call_kwargs["success"] is True

    def test_failed_exit_success_false(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            try:
                with BatchRequestTimer("t1", 10) as _timer:
                    raise ValueError("test failure")
            except ValueError:
                pass

        call_kwargs = mock_metrics.record_batch_request.call_args[1]
        assert call_kwargs["success"] is False

    def test_exit_calls_record_items_processed(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with BatchRequestTimer("t1", 30) as timer:
                timer.record_items(successful=25, failed=5)

        mock_metrics.record_items_processed.assert_called_once()
        call_kwargs = mock_metrics.record_items_processed.call_args[1]
        assert call_kwargs["total"] == 30
        assert call_kwargs["successful"] == 25
        assert call_kwargs["failed"] == 5

    def test_cache_statistics_forwarded(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with BatchRequestTimer("t1", 10, cache_enabled=True) as timer:
                timer.record_cache(hits=6, misses=4)

        call_kwargs = mock_metrics.record_batch_request.call_args[1]
        assert call_kwargs["cache_hits"] == 6
        assert call_kwargs["cache_misses"] == 4

    def test_record_items_sets_attributes(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            timer = BatchRequestTimer("t1", 10)
            timer.record_items(successful=7, failed=3)
        assert timer.successful == 7
        assert timer.failed == 3

    def test_record_cache_sets_attributes(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            timer = BatchRequestTimer("t1", 10)
            timer.record_cache(hits=3, misses=2)
        assert timer.cache_hits == 3
        assert timer.cache_misses == 2

    def test_duration_positive(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with BatchRequestTimer("t1", 10):
                time.sleep(0.01)

        call_kwargs = mock_metrics.record_batch_request.call_args[1]
        assert call_kwargs["duration_seconds"] > 0

    def test_default_successful_failed_zero(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with BatchRequestTimer("t1", 5):
                pass  # no record_items call

        call_kwargs = mock_metrics.record_items_processed.call_args[1]
        assert call_kwargs["successful"] == 0
        assert call_kwargs["failed"] == 0

    def test_default_cache_hits_misses_zero(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with BatchRequestTimer("t1", 5):
                pass

        call_kwargs = mock_metrics.record_batch_request.call_args[1]
        assert call_kwargs["cache_hits"] == 0
        assert call_kwargs["cache_misses"] == 0

    def test_exception_not_suppressed(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with pytest.raises(RuntimeError, match="unexpected"):
                with BatchRequestTimer("t1", 5):
                    raise RuntimeError("unexpected")

    def test_cache_enabled_flag_stored(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            timer = BatchRequestTimer("t1", 10, cache_enabled=True)
        assert timer.cache_enabled is True

    def test_cache_enabled_default_false(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            timer = BatchRequestTimer("t1", 10)
        assert timer.cache_enabled is False


# ---------------------------------------------------------------------------
# ItemTimer - context manager
# ---------------------------------------------------------------------------


class TestItemTimer:
    def setup_method(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        bm_module.reset_batch_metrics()

    def teardown_method(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        bm_module.reset_batch_metrics()

    def test_enter_returns_self(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            timer = ItemTimer("t1")
            result = timer.__enter__()
        assert result is timer

    def test_start_time_set_on_enter(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            timer = ItemTimer("t1")
            timer.__enter__()
            assert timer.start_time > 0

    def test_successful_exit_calls_record_item_duration(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with ItemTimer("t1"):
                pass

        mock_metrics.record_item_duration.assert_called_once()
        call_kwargs = mock_metrics.record_item_duration.call_args[1]
        assert call_kwargs["tenant_id"] == "t1"
        assert call_kwargs["success"] is True

    def test_failed_exit_success_false(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            try:
                with ItemTimer("t1"):
                    raise KeyError("bad key")
            except KeyError:
                pass

        call_kwargs = mock_metrics.record_item_duration.call_args[1]
        assert call_kwargs["success"] is False

    def test_duration_recorded_positive(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with ItemTimer("t1"):
                time.sleep(0.005)

        call_kwargs = mock_metrics.record_item_duration.call_args[1]
        assert call_kwargs["duration_seconds"] > 0

    def test_exception_not_suppressed(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with pytest.raises(TypeError):
                with ItemTimer("t1"):
                    raise TypeError("type error")

    def test_tenant_id_stored(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            timer = ItemTimer("my-tenant")
        assert timer.tenant_id == "my-tenant"

    def test_success_default_true(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            timer = ItemTimer("t1")
        assert timer.success is True


# ---------------------------------------------------------------------------
# Integration: BatchMetrics with real NoOpMeter
# ---------------------------------------------------------------------------


class TestBatchMetricsIntegrationNoOp:
    """Exercise all public methods on a real BatchMetrics with NoOpMeter internals."""

    def setup_method(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        bm_module.reset_batch_metrics()

    def teardown_method(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        bm_module.reset_batch_metrics()

    def _instance(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        return BatchMetrics(service_name="integration-test")

    def test_record_batch_request_no_exception(self):
        inst = self._instance()
        inst.record_batch_request("t1", 100, True, 0.5)

    def test_record_batch_request_with_cache(self):
        inst = self._instance()
        inst.record_batch_request("t1", 50, False, 1.0, cache_hits=20, cache_misses=30)

    def test_record_items_processed_no_exception(self):
        inst = self._instance()
        inst.record_items_processed("t1", 10, 8, 2)

    def test_record_item_duration_no_exception(self):
        inst = self._instance()
        inst.record_item_duration("t1", 0.001, True)
        inst.record_item_duration("t1", 0.002, False)

    def test_record_error_no_exception(self):
        inst = self._instance()
        inst.record_error("t1", "timeout", "ETIMEOUT")
        inst.record_error("t1", "validation")

    def test_record_retry_no_exception(self):
        inst = self._instance()
        inst.record_retry("t1", 1, "timeout")
        inst.record_retry("t1", 2, "backpressure")

    def test_record_constitutional_validation_valid(self):
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        inst = self._instance()
        inst.record_constitutional_validation("t1", valid=True, hash_used=CONSTITUTIONAL_HASH)

    def test_record_constitutional_validation_invalid(self):
        inst = self._instance()
        inst.record_constitutional_validation("t1", valid=False, hash_used="wrong")

    def test_record_cache_stats_no_exception(self):
        inst = self._instance()
        inst.record_cache_stats("t1", hits=5, misses=3)
        inst.record_cache_stats("t1", hits=0, misses=0)

    def test_batch_request_timer_integration(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        with BatchRequestTimer("t1", 20) as timer:
            timer.record_items(successful=18, failed=2)
            timer.record_cache(hits=5, misses=15)

    def test_item_timer_integration(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        with ItemTimer("t1"):
            pass

    def test_item_timer_with_exception_integration(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        with pytest.raises(ValueError):
            with ItemTimer("t1"):
                raise ValueError("fail")

    def test_batch_timer_with_exception_integration(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        with pytest.raises(RuntimeError):
            with BatchRequestTimer("t1", 10):
                raise RuntimeError("fail")


# ---------------------------------------------------------------------------
# Edge cases and branch coverage
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def setup_method(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        bm_module.reset_batch_metrics()

    def teardown_method(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        bm_module.reset_batch_metrics()

    def test_record_batch_request_zero_duration(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        inst = BatchMetrics()
        inst.record_batch_request("t1", 1, True, 0.0)

    def test_record_batch_request_large_batch(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        inst = BatchMetrics()
        inst.record_batch_request("t1", 10000, True, 100.0)

    def test_record_items_all_zero(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        inst = BatchMetrics()
        inst.record_items_processed("t1", 0, 0, 0)

    def test_record_constitutional_validation_with_empty_hash(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        inst = BatchMetrics()
        # Valid=False with empty hash_used should produce "missing" in violation attrs
        inst.record_constitutional_validation("t1", valid=False, hash_used="")

    def test_multiple_errors_different_types(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        inst = BatchMetrics()
        for err_type in ["timeout", "validation", "processing", "network"]:
            inst.record_error("t1", err_type)

    def test_multiple_retries(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        inst = BatchMetrics()
        for attempt in range(1, 6):
            inst.record_retry("t1", attempt=attempt, reason="timeout")

    def test_batch_request_timer_with_cache_record(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        with BatchRequestTimer("t1", 100, cache_enabled=True) as timer:
            timer.record_cache(hits=50, misses=50)
            timer.record_items(successful=90, failed=10)

    def test_item_timer_many_items(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        for _ in range(5):
            with ItemTimer("t1"):
                pass

    def test_batch_metrics_repr(self):
        """Smoke test repr doesn't raise."""
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        inst = BatchMetrics(service_name="repr-test")
        s = repr(inst)
        assert "repr-test" in s

    def test_constitutional_hash_constant_in_attrs_matches_module(self):
        """The hash embedded in record_batch_request attrs must match CONSTITUTIONAL_HASH."""
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        mock_meter = _make_mock_meter()
        with patch.object(bm_module, "get_meter", return_value=mock_meter):
            inst = bm_module.BatchMetrics()

        counter = _make_mock_counter()
        inst._batch_requests_total = counter
        inst.record_batch_request("t", 1, True, 0.0)
        attrs = counter.add.call_args[0][1]
        assert attrs["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_noop_counter_add_is_callable(self):
        from enhanced_agent_bus.observability.telemetry import NoOpCounter

        c = NoOpCounter()
        c.add(1, {"k": "v"})  # should not raise

    def test_noop_histogram_record_is_callable(self):
        from enhanced_agent_bus.observability.telemetry import NoOpHistogram

        h = NoOpHistogram()
        h.record(0.5, {"k": "v"})  # should not raise

    def test_noop_meter_creates_counter(self):
        from enhanced_agent_bus.observability.telemetry import NoOpCounter, NoOpMeter

        m = NoOpMeter()
        c = m.create_counter("test")
        assert isinstance(c, NoOpCounter)

    def test_noop_meter_creates_histogram(self):
        from enhanced_agent_bus.observability.telemetry import NoOpHistogram, NoOpMeter

        m = NoOpMeter()
        h = m.create_histogram("test")
        assert isinstance(h, NoOpHistogram)
