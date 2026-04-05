# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/observability/batch_metrics.py.

Covers:
- BatchMetrics initialization (normal + error fallback to no-op)
- All counter/histogram recording methods
- Singleton get_batch_metrics / reset_batch_metrics
- BatchRequestTimer context manager (success, exception, cache stats)
- ItemTimer context manager (success, exception)
"""

from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_meter_with_distinct_instruments():
    """
    Return (meter, instrument_map) where instrument_map maps instrument name
    to its individual MagicMock.  The meter's create_counter/create_histogram
    use side_effect so each call returns a fresh mock keyed by the 'name' kwarg.
    """
    instrument_map: dict = {}
    meter = MagicMock()

    def _make_counter(**kwargs):
        name = kwargs.get("name", "_unknown")
        mock = MagicMock(name=f"counter:{name}")
        instrument_map[name] = mock
        return mock

    def _make_histogram(**kwargs):
        name = kwargs.get("name", "_unknown")
        mock = MagicMock(name=f"hist:{name}")
        instrument_map[name] = mock
        return mock

    meter.create_counter.side_effect = _make_counter
    meter.create_histogram.side_effect = _make_histogram
    return meter, instrument_map


def _make_bm_with_instruments():
    """Return (BatchMetrics instance, instrument_map)."""
    from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

    meter, inst = _make_meter_with_distinct_instruments()
    with patch(
        "enhanced_agent_bus.observability.batch_metrics.get_meter",
        return_value=meter,
    ):
        bm = BatchMetrics()
    return bm, inst


# ---------------------------------------------------------------------------
# BatchMetrics - normal initialisation
# ---------------------------------------------------------------------------


class TestBatchMetricsInit:
    def test_initializes_with_default_service_name(self):
        bm, _ = _make_bm_with_instruments()
        assert bm.service_name == "acgs2-batch-processor"
        assert bm._initialized is True

    def test_initializes_with_custom_service_name(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        meter, _ = _make_meter_with_distinct_instruments()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_meter",
            return_value=meter,
        ) as mock_get_meter:
            bm = BatchMetrics(service_name="custom-service")

        assert bm.service_name == "custom-service"
        mock_get_meter.assert_called_once_with("custom-service")

    def test_creates_all_counters_and_histograms(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        meter, _inst = _make_meter_with_distinct_instruments()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_meter",
            return_value=meter,
        ):
            BatchMetrics()

        counter_names = [c[1]["name"] for c in meter.create_counter.call_args_list]
        histogram_names = [c[1]["name"] for c in meter.create_histogram.call_args_list]

        assert "batch_requests_total" in counter_names
        assert "batch_items_total" in counter_names
        assert "batch_items_success_total" in counter_names
        assert "batch_items_failed_total" in counter_names
        assert "batch_cache_hits_total" in counter_names
        assert "batch_cache_misses_total" in counter_names
        assert "batch_errors_total" in counter_names
        assert "batch_retries_total" in counter_names
        assert "constitutional_validations_total" in counter_names
        assert "constitutional_violations_total" in counter_names

        assert "batch_request_duration_seconds" in histogram_names
        assert "batch_item_duration_seconds" in histogram_names
        assert "batch_size_distribution" in histogram_names

    def test_second_initialize_call_is_noop(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        meter, _ = _make_meter_with_distinct_instruments()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_meter",
            return_value=meter,
        ) as mock_get_meter:
            bm = BatchMetrics()
            call_count_after_first = mock_get_meter.call_count
            bm._initialize_metrics()  # second call -- should be skipped

        assert mock_get_meter.call_count == call_count_after_first


# ---------------------------------------------------------------------------
# BatchMetrics - error fallback to NoOp
# ---------------------------------------------------------------------------


class TestBatchMetricsNoOpFallback:
    def test_falls_back_to_noop_on_runtime_error(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics
        from enhanced_agent_bus.observability.telemetry import (
            NoOpCounter,
            NoOpHistogram,
        )

        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_meter",
            side_effect=RuntimeError("meter unavailable"),
        ):
            bm = BatchMetrics()

        assert bm._initialized is True
        assert isinstance(bm._batch_requests_total, NoOpCounter)
        assert isinstance(bm._batch_request_duration, NoOpHistogram)

    def test_falls_back_to_noop_on_value_error(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics
        from enhanced_agent_bus.observability.telemetry import NoOpCounter

        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_meter",
            side_effect=ValueError("bad value"),
        ):
            bm = BatchMetrics()

        assert isinstance(bm._batch_items_total, NoOpCounter)

    def test_falls_back_to_noop_on_type_error(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_meter",
            side_effect=TypeError("type mismatch"),
        ):
            bm = BatchMetrics()

        assert bm._initialized is True

    def test_falls_back_to_noop_on_key_error(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_meter",
            side_effect=KeyError("key"),
        ):
            bm = BatchMetrics()

        assert bm._initialized is True

    def test_falls_back_to_noop_on_attribute_error(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_meter",
            side_effect=AttributeError("attr"),
        ):
            bm = BatchMetrics()

        assert bm._initialized is True

    def test_noop_all_instruments_assigned(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics
        from enhanced_agent_bus.observability.telemetry import (
            NoOpCounter,
            NoOpHistogram,
        )

        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_meter",
            side_effect=RuntimeError("fail"),
        ):
            bm = BatchMetrics()

        noop_counters = [
            bm._batch_requests_total,
            bm._batch_items_total,
            bm._batch_items_success,
            bm._batch_items_failed,
            bm._batch_cache_hits,
            bm._batch_cache_misses,
            bm._batch_errors_total,
            bm._batch_retries_total,
            bm._constitutional_validations,
            bm._constitutional_violations,
        ]
        noop_histograms = [
            bm._batch_request_duration,
            bm._batch_item_duration,
            bm._batch_size_distribution,
        ]
        for c in noop_counters:
            assert isinstance(c, NoOpCounter)
        for h in noop_histograms:
            assert isinstance(h, NoOpHistogram)


# ---------------------------------------------------------------------------
# BatchMetrics - record_batch_request
# ---------------------------------------------------------------------------


class TestRecordBatchRequest:
    def test_records_batch_request_success(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_batch_request(tenant_id="t1", batch_size=10, success=True, duration_seconds=0.5)
        inst["batch_requests_total"].add.assert_called_once()
        inst["batch_size_distribution"].record.assert_called_once()
        inst["batch_request_duration_seconds"].record.assert_called_once()

    def test_records_cache_hits_when_nonzero(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_batch_request(
            tenant_id="t1",
            batch_size=5,
            success=True,
            duration_seconds=0.1,
            cache_hits=3,
            cache_misses=2,
        )
        inst["batch_cache_hits_total"].add.assert_called_once_with(3, {"tenant_id": "t1"})
        inst["batch_cache_misses_total"].add.assert_called_once_with(2, {"tenant_id": "t1"})

    def test_does_not_record_zero_cache_hits(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_batch_request(
            tenant_id="t1",
            batch_size=5,
            success=False,
            duration_seconds=0.2,
            cache_hits=0,
            cache_misses=0,
        )
        inst["batch_cache_hits_total"].add.assert_not_called()
        inst["batch_cache_misses_total"].add.assert_not_called()

    def test_attributes_contain_constitutional_hash(self):
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        bm, inst = _make_bm_with_instruments()
        bm.record_batch_request(tenant_id="acme", batch_size=1, success=True, duration_seconds=0.01)
        call_args = inst["batch_requests_total"].add.call_args
        attrs = call_args[0][1]
        assert attrs["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_success_false_encoded_as_string(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_batch_request(tenant_id="t1", batch_size=1, success=False, duration_seconds=0.1)
        call_args = inst["batch_requests_total"].add.call_args
        attrs = call_args[0][1]
        assert attrs["success"] == "false"

    def test_success_true_encoded_as_string(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_batch_request(tenant_id="t1", batch_size=1, success=True, duration_seconds=0.1)
        call_args = inst["batch_requests_total"].add.call_args
        attrs = call_args[0][1]
        assert attrs["success"] == "true"

    def test_only_cache_hits_nonzero(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_batch_request(
            tenant_id="t1",
            batch_size=5,
            success=True,
            duration_seconds=0.1,
            cache_hits=4,
            cache_misses=0,
        )
        inst["batch_cache_hits_total"].add.assert_called_once()
        inst["batch_cache_misses_total"].add.assert_not_called()

    def test_only_cache_misses_nonzero(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_batch_request(
            tenant_id="t1",
            batch_size=5,
            success=True,
            duration_seconds=0.1,
            cache_hits=0,
            cache_misses=3,
        )
        inst["batch_cache_hits_total"].add.assert_not_called()
        inst["batch_cache_misses_total"].add.assert_called_once()


# ---------------------------------------------------------------------------
# BatchMetrics - record_items_processed
# ---------------------------------------------------------------------------


class TestRecordItemsProcessed:
    def test_records_all_item_counts(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_items_processed(tenant_id="t2", total=20, successful=18, failed=2)

        inst["batch_items_total"].add.assert_called_once_with(20, {"tenant_id": "t2"})
        inst["batch_items_success_total"].add.assert_called_once_with(18, {"tenant_id": "t2"})
        inst["batch_items_failed_total"].add.assert_called_once_with(2, {"tenant_id": "t2"})

    def test_zero_items(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_items_processed(tenant_id="t2", total=0, successful=0, failed=0)
        inst["batch_items_total"].add.assert_called_once_with(0, {"tenant_id": "t2"})


# ---------------------------------------------------------------------------
# BatchMetrics - record_item_duration
# ---------------------------------------------------------------------------


class TestRecordItemDuration:
    def test_records_duration_success(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_item_duration(tenant_id="t3", duration_seconds=0.02, success=True)
        inst["batch_item_duration_seconds"].record.assert_called_once_with(
            0.02, {"tenant_id": "t3", "success": "true"}
        )

    def test_records_duration_failure(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_item_duration(tenant_id="t3", duration_seconds=0.5, success=False)
        inst["batch_item_duration_seconds"].record.assert_called_once_with(
            0.5, {"tenant_id": "t3", "success": "false"}
        )


# ---------------------------------------------------------------------------
# BatchMetrics - record_error
# ---------------------------------------------------------------------------


class TestRecordError:
    def test_records_error_with_code(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_error(tenant_id="t4", error_type="timeout", error_code="E001")
        inst["batch_errors_total"].add.assert_called_once_with(
            1, {"tenant_id": "t4", "error_type": "timeout", "error_code": "E001"}
        )

    def test_records_error_without_code_defaults_to_unknown(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_error(tenant_id="t4", error_type="validation")
        call_args = inst["batch_errors_total"].add.call_args
        attrs = call_args[0][1]
        assert attrs["error_code"] == "unknown"

    def test_records_error_with_explicit_none_code(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_error(tenant_id="t4", error_type="processing", error_code=None)
        call_args = inst["batch_errors_total"].add.call_args
        assert call_args[0][1]["error_code"] == "unknown"


# ---------------------------------------------------------------------------
# BatchMetrics - record_retry
# ---------------------------------------------------------------------------


class TestRecordRetry:
    def test_records_retry(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_retry(tenant_id="t5", attempt=2, reason="transient_error")
        inst["batch_retries_total"].add.assert_called_once_with(
            1, {"tenant_id": "t5", "attempt": "2", "reason": "transient_error"}
        )

    def test_attempt_converted_to_string(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_retry(tenant_id="t5", attempt=10, reason="rate_limit")
        attrs = inst["batch_retries_total"].add.call_args[0][1]
        assert attrs["attempt"] == "10"


# ---------------------------------------------------------------------------
# BatchMetrics - record_constitutional_validation
# ---------------------------------------------------------------------------


class TestRecordConstitutionalValidation:
    def test_valid_hash_increments_validations_only(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_constitutional_validation(
            tenant_id="t6",
            valid=True,
            hash_used=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
        )
        inst["constitutional_validations_total"].add.assert_called_once()
        inst["constitutional_violations_total"].add.assert_not_called()

    def test_invalid_hash_increments_both_counters(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_constitutional_validation(tenant_id="t6", valid=False, hash_used="deadbeef")
        inst["constitutional_validations_total"].add.assert_called_once()
        inst["constitutional_violations_total"].add.assert_called_once()
        violation_attrs = inst["constitutional_violations_total"].add.call_args[0][1]
        assert violation_attrs["actual_hash"] == "deadbeef"

    def test_none_hash_recorded_as_missing(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_constitutional_validation(tenant_id="t6", valid=False, hash_used=None)
        violation_attrs = inst["constitutional_violations_total"].add.call_args[0][1]
        assert violation_attrs["actual_hash"] == "missing"

    def test_validation_attrs_include_expected_hash(self):
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        bm, inst = _make_bm_with_instruments()
        bm.record_constitutional_validation(tenant_id="t6", valid=True, hash_used="x")
        attrs = inst["constitutional_validations_total"].add.call_args[0][1]
        assert attrs["expected_hash"] == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# BatchMetrics - record_cache_stats
# ---------------------------------------------------------------------------


class TestRecordCacheStats:
    def test_records_hits_and_misses(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_cache_stats(tenant_id="t7", hits=10, misses=5)
        inst["batch_cache_hits_total"].add.assert_called_once_with(10, {"tenant_id": "t7"})
        inst["batch_cache_misses_total"].add.assert_called_once_with(5, {"tenant_id": "t7"})

    def test_zero_hits_not_recorded(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_cache_stats(tenant_id="t7", hits=0, misses=3)
        inst["batch_cache_hits_total"].add.assert_not_called()
        inst["batch_cache_misses_total"].add.assert_called_once()

    def test_zero_misses_not_recorded(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_cache_stats(tenant_id="t7", hits=7, misses=0)
        inst["batch_cache_hits_total"].add.assert_called_once()
        inst["batch_cache_misses_total"].add.assert_not_called()

    def test_both_zero_nothing_recorded(self):
        bm, inst = _make_bm_with_instruments()
        bm.record_cache_stats(tenant_id="t7", hits=0, misses=0)
        inst["batch_cache_hits_total"].add.assert_not_called()
        inst["batch_cache_misses_total"].add.assert_not_called()


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_batch_metrics_returns_same_instance(self):
        from enhanced_agent_bus.observability.batch_metrics import (
            get_batch_metrics,
            reset_batch_metrics,
        )

        meter, _ = _make_meter_with_distinct_instruments()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_meter",
            return_value=meter,
        ):
            reset_batch_metrics()
            a = get_batch_metrics()
            b = get_batch_metrics()

        assert a is b

    def test_reset_batch_metrics_creates_new_instance(self):
        from enhanced_agent_bus.observability.batch_metrics import (
            get_batch_metrics,
            reset_batch_metrics,
        )

        meter1, _ = _make_meter_with_distinct_instruments()
        meter2, _ = _make_meter_with_distinct_instruments()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_meter",
        ) as mock_get_meter:
            mock_get_meter.side_effect = [meter1, meter2]
            reset_batch_metrics()
            a = get_batch_metrics()
            reset_batch_metrics()
            b = get_batch_metrics()

        assert a is not b

    def test_get_batch_metrics_creates_instance_on_first_call(self):
        from enhanced_agent_bus.observability import batch_metrics as bm_module

        meter, _ = _make_meter_with_distinct_instruments()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_meter",
            return_value=meter,
        ):
            bm_module.reset_batch_metrics()
            assert bm_module._batch_metrics is None
            instance = bm_module.get_batch_metrics()

        assert instance is not None


# ---------------------------------------------------------------------------
# BatchRequestTimer
# ---------------------------------------------------------------------------


class TestBatchRequestTimer:
    def _setup(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            timer = BatchRequestTimer(tenant_id="acme", batch_size=50)
        return timer, mock_metrics

    def test_enter_returns_self(self):
        timer, _ = self._setup()
        result = timer.__enter__()
        assert result is timer

    def test_enter_captures_start_time(self):
        timer, _ = self._setup()
        timer.__enter__()
        assert timer.start_time > 0

    def test_exit_success_records_batch_request(self):
        timer, mock_metrics = self._setup()
        timer.__enter__()
        timer.__exit__(None, None, None)

        mock_metrics.record_batch_request.assert_called_once()
        call_kwargs = mock_metrics.record_batch_request.call_args[1]
        assert call_kwargs["success"] is True
        assert call_kwargs["tenant_id"] == "acme"
        assert call_kwargs["batch_size"] == 50

    def test_exit_with_exception_marks_failure(self):
        timer, mock_metrics = self._setup()
        timer.__enter__()
        timer.__exit__(ValueError, ValueError("oops"), None)

        call_kwargs = mock_metrics.record_batch_request.call_args[1]
        assert call_kwargs["success"] is False

    def test_exit_records_items_processed(self):
        timer, mock_metrics = self._setup()
        timer.__enter__()
        timer.record_items(successful=45, failed=5)
        timer.__exit__(None, None, None)

        mock_metrics.record_items_processed.assert_called_once()
        call_kwargs = mock_metrics.record_items_processed.call_args[1]
        assert call_kwargs["successful"] == 45
        assert call_kwargs["failed"] == 5
        assert call_kwargs["total"] == 50

    def test_exit_does_not_suppress_exception(self):
        timer, _ = self._setup()
        timer.__enter__()
        result = timer.__exit__(RuntimeError, RuntimeError("boom"), None)
        assert result is None  # does not suppress

    def test_record_cache_updates_values(self):
        timer, mock_metrics = self._setup()
        timer.__enter__()
        timer.record_cache(hits=8, misses=2)
        timer.__exit__(None, None, None)

        call_kwargs = mock_metrics.record_batch_request.call_args[1]
        assert call_kwargs["cache_hits"] == 8
        assert call_kwargs["cache_misses"] == 2

    def test_default_cache_values_are_zero(self):
        timer, mock_metrics = self._setup()
        timer.__enter__()
        timer.__exit__(None, None, None)

        call_kwargs = mock_metrics.record_batch_request.call_args[1]
        assert call_kwargs["cache_hits"] == 0
        assert call_kwargs["cache_misses"] == 0

    def test_context_manager_full_flow(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with BatchRequestTimer(tenant_id="corp", batch_size=100) as t:
                t.record_items(successful=90, failed=10)
                t.record_cache(hits=50, misses=50)

        mock_metrics.record_batch_request.assert_called_once()
        mock_metrics.record_items_processed.assert_called_once()

    def test_context_manager_exception_propagates(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchRequestTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with pytest.raises(ValueError):
                with BatchRequestTimer(tenant_id="corp", batch_size=10):
                    raise ValueError("deliberate")

        # Even with exception, metrics should be recorded
        mock_metrics.record_batch_request.assert_called_once()
        recorded_success = mock_metrics.record_batch_request.call_args[1]["success"]
        assert recorded_success is False

    def test_duration_is_positive(self):
        timer, mock_metrics = self._setup()
        timer.__enter__()
        timer.__exit__(None, None, None)

        call_kwargs = mock_metrics.record_batch_request.call_args[1]
        assert call_kwargs["duration_seconds"] >= 0

    def test_record_items_default_values_are_zero(self):
        timer, mock_metrics = self._setup()
        timer.__enter__()
        timer.__exit__(None, None, None)

        call_kwargs = mock_metrics.record_items_processed.call_args[1]
        assert call_kwargs["successful"] == 0
        assert call_kwargs["failed"] == 0


# ---------------------------------------------------------------------------
# ItemTimer
# ---------------------------------------------------------------------------


class TestItemTimer:
    def _setup(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            timer = ItemTimer(tenant_id="corp")
        return timer, mock_metrics

    def test_enter_returns_self(self):
        timer, _ = self._setup()
        result = timer.__enter__()
        assert result is timer

    def test_enter_captures_start_time(self):
        timer, _ = self._setup()
        timer.__enter__()
        assert timer.start_time > 0

    def test_exit_success_records_duration(self):
        timer, mock_metrics = self._setup()
        timer.__enter__()
        timer.__exit__(None, None, None)

        mock_metrics.record_item_duration.assert_called_once()
        call_kwargs = mock_metrics.record_item_duration.call_args[1]
        assert call_kwargs["success"] is True
        assert call_kwargs["tenant_id"] == "corp"
        assert call_kwargs["duration_seconds"] >= 0

    def test_exit_with_exception_marks_failure(self):
        timer, mock_metrics = self._setup()
        timer.__enter__()
        timer.__exit__(ValueError, ValueError("fail"), None)

        call_kwargs = mock_metrics.record_item_duration.call_args[1]
        assert call_kwargs["success"] is False

    def test_exit_does_not_suppress_exception(self):
        timer, _ = self._setup()
        timer.__enter__()
        result = timer.__exit__(RuntimeError, RuntimeError("boom"), None)
        assert result is None

    def test_context_manager_success_flow(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with ItemTimer(tenant_id="tenant-x"):
                pass

        mock_metrics.record_item_duration.assert_called_once()
        assert mock_metrics.record_item_duration.call_args[1]["success"] is True

    def test_context_manager_exception_propagates(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            with pytest.raises(RuntimeError):
                with ItemTimer(tenant_id="tenant-y"):
                    raise RuntimeError("item failed")

        mock_metrics.record_item_duration.assert_called_once()
        assert mock_metrics.record_item_duration.call_args[1]["success"] is False

    def test_success_default_is_true(self):
        from enhanced_agent_bus.observability.batch_metrics import ItemTimer

        mock_metrics = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_batch_metrics",
            return_value=mock_metrics,
        ):
            t = ItemTimer(tenant_id="t")

        assert t.success is True


# ---------------------------------------------------------------------------
# NoOp path - smoke test all methods work without raising
# ---------------------------------------------------------------------------


class TestNoOpSmokeTest:
    """Verify all public methods work on no-op-backed BatchMetrics."""

    def _make_noop_bm(self):
        from enhanced_agent_bus.observability.batch_metrics import BatchMetrics

        with patch(
            "enhanced_agent_bus.observability.batch_metrics.get_meter",
            side_effect=RuntimeError("forced noop"),
        ):
            return BatchMetrics()

    def test_all_methods_smoke(self):
        bm = self._make_noop_bm()
        # Should not raise
        bm.record_batch_request(
            tenant_id="t",
            batch_size=5,
            success=True,
            duration_seconds=0.1,
            cache_hits=1,
            cache_misses=1,
        )
        bm.record_items_processed(tenant_id="t", total=5, successful=4, failed=1)
        bm.record_item_duration(tenant_id="t", duration_seconds=0.01, success=True)
        bm.record_error(tenant_id="t", error_type="timeout")
        bm.record_retry(tenant_id="t", attempt=1, reason="retry")
        bm.record_constitutional_validation(
            tenant_id="t",
            valid=True,
            hash_used=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
        )
        bm.record_constitutional_validation(tenant_id="t", valid=False, hash_used="bad")
        bm.record_cache_stats(tenant_id="t", hits=3, misses=2)
