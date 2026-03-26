# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for online_learning_infra/models.py.

Targets ≥95% line coverage of all dataclass models and their
properties/setters defined in that module.
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from enhanced_agent_bus.online_learning_infra.config import LearningStatus
from enhanced_agent_bus.online_learning_infra.models import (
    ConsumerStats,
    LearningResult,
    LearningStats,
    PipelineStats,
    PredictionResult,
)

# ---------------------------------------------------------------------------
# LearningStats
# ---------------------------------------------------------------------------


class TestLearningStatsDefaults:
    """Verify all default field values."""

    def test_samples_learned_default(self):
        s = LearningStats()
        assert s.samples_learned == 0

    def test_correct_predictions_default(self):
        s = LearningStats()
        assert s.correct_predictions == 0

    def test_total_predictions_default(self):
        s = LearningStats()
        assert s.total_predictions == 0

    def test_accuracy_default(self):
        s = LearningStats()
        assert s.accuracy == 0.0

    def test_precision_default(self):
        s = LearningStats()
        assert s.precision == 0.0

    def test_recall_default(self):
        s = LearningStats()
        assert s.recall == 0.0

    def test_f1_score_default(self):
        s = LearningStats()
        assert s.f1_score == 0.0

    def test_model_type_default(self):
        s = LearningStats()
        assert s.model_type == ""

    def test_last_update_is_datetime(self):
        before = datetime.now(UTC)
        s = LearningStats()
        after = datetime.now(UTC)
        assert before <= s.last_update <= after

    def test_status_default(self):
        s = LearningStats()
        assert s.status == LearningStatus.COLD_START

    def test_feature_names_default_is_empty_list(self):
        s = LearningStats()
        assert s.feature_names == []

    def test_metrics_history_default_is_empty_list(self):
        s = LearningStats()
        assert s.metrics_history == []

    def test_feature_importance_default_is_empty_dict(self):
        s = LearningStats()
        assert s.feature_importance == {}

    def test_feature_names_are_independent(self):
        """Each instance should have its own list."""
        s1 = LearningStats()
        s2 = LearningStats()
        s1.feature_names.append("x")
        assert s2.feature_names == []

    def test_metrics_history_are_independent(self):
        s1 = LearningStats()
        s2 = LearningStats()
        s1.metrics_history.append({"acc": 0.9})
        assert s2.metrics_history == []

    def test_feature_importance_are_independent(self):
        s1 = LearningStats()
        s2 = LearningStats()
        s1.feature_importance["feat"] = 0.5
        assert s2.feature_importance == {}


class TestLearningStatsCustomValues:
    """Verify custom initialisation values."""

    def test_samples_learned_custom(self):
        s = LearningStats(samples_learned=100)
        assert s.samples_learned == 100

    def test_accuracy_custom(self):
        s = LearningStats(accuracy=0.95)
        assert s.accuracy == 0.95

    def test_status_ready(self):
        s = LearningStats(status=LearningStatus.READY)
        assert s.status == LearningStatus.READY

    def test_status_warming_up(self):
        s = LearningStats(status=LearningStatus.WARMING_UP)
        assert s.status == LearningStatus.WARMING_UP

    def test_status_error(self):
        s = LearningStats(status=LearningStatus.ERROR)
        assert s.status == LearningStatus.ERROR

    def test_feature_names_custom(self):
        s = LearningStats(feature_names=["a", "b", "c"])
        assert s.feature_names == ["a", "b", "c"]

    def test_metrics_history_custom(self):
        hist = [{"accuracy": 0.8}, {"accuracy": 0.9}]
        s = LearningStats(metrics_history=hist)
        assert s.metrics_history == hist

    def test_feature_importance_custom(self):
        fi = {"feature_a": 0.7, "feature_b": 0.3}
        s = LearningStats(feature_importance=fi)
        assert s.feature_importance == fi

    def test_model_type_custom(self):
        s = LearningStats(model_type="classifier")
        assert s.model_type == "classifier"

    def test_all_metric_fields(self):
        s = LearningStats(
            samples_learned=200,
            correct_predictions=180,
            total_predictions=200,
            accuracy=0.9,
            precision=0.88,
            recall=0.92,
            f1_score=0.90,
        )
        assert s.correct_predictions == 180
        assert s.total_predictions == 200
        assert s.precision == 0.88
        assert s.recall == 0.92
        assert s.f1_score == 0.90


class TestLearningStatsLastUpdatedProperty:
    """Property and setter for last_updated."""

    def test_last_updated_getter_equals_last_update(self):
        s = LearningStats()
        assert s.last_updated is s.last_update

    def test_last_updated_setter_updates_last_update(self):
        s = LearningStats()
        new_dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        s.last_updated = new_dt
        assert s.last_update == new_dt

    def test_last_updated_setter_value_visible_via_getter(self):
        s = LearningStats()
        new_dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        s.last_updated = new_dt
        assert s.last_updated == new_dt

    def test_last_updated_setter_does_not_affect_other_fields(self):
        s = LearningStats(samples_learned=42)
        s.last_updated = datetime.now(UTC)
        assert s.samples_learned == 42

    def test_last_update_direct_mutation(self):
        s = LearningStats()
        new_dt = datetime(2024, 1, 1, tzinfo=UTC)
        s.last_update = new_dt
        assert s.last_updated == new_dt


# ---------------------------------------------------------------------------
# PredictionResult
# ---------------------------------------------------------------------------


class TestPredictionResultDefaults:
    """Default field values for PredictionResult."""

    def test_prediction_required(self):
        pr = PredictionResult(prediction=1)
        assert pr.prediction == 1

    def test_confidence_default_none(self):
        pr = PredictionResult(prediction="label")
        assert pr.confidence is None

    def test_probabilities_default_none(self):
        pr = PredictionResult(prediction=True)
        assert pr.probabilities is None

    def test_used_fallback_default_false(self):
        pr = PredictionResult(prediction=0)
        assert pr.used_fallback is False

    def test_model_status_default_cold_start(self):
        pr = PredictionResult(prediction=0)
        assert pr.model_status == LearningStatus.COLD_START

    def test_latency_ms_default_zero(self):
        pr = PredictionResult(prediction=0)
        assert pr.latency_ms == 0.0


class TestPredictionResultCustomValues:
    """Custom field values for PredictionResult."""

    def test_prediction_string(self):
        pr = PredictionResult(prediction="class_A")
        assert pr.prediction == "class_A"

    def test_prediction_float(self):
        pr = PredictionResult(prediction=3.14)
        assert pr.prediction == pytest.approx(3.14)

    def test_prediction_none(self):
        pr = PredictionResult(prediction=None)
        assert pr.prediction is None

    def test_confidence_set(self):
        pr = PredictionResult(prediction=1, confidence=0.87)
        assert pr.confidence == pytest.approx(0.87)

    def test_probabilities_set(self):
        probs = {0: 0.3, 1: 0.7}
        pr = PredictionResult(prediction=1, probabilities=probs)
        assert pr.probabilities == probs

    def test_used_fallback_true(self):
        pr = PredictionResult(prediction=0, used_fallback=True)
        assert pr.used_fallback is True

    def test_model_status_ready(self):
        pr = PredictionResult(prediction=1, model_status=LearningStatus.READY)
        assert pr.model_status == LearningStatus.READY

    def test_model_status_warming_up(self):
        pr = PredictionResult(prediction=1, model_status=LearningStatus.WARMING_UP)
        assert pr.model_status == LearningStatus.WARMING_UP

    def test_model_status_error(self):
        pr = PredictionResult(prediction=0, model_status=LearningStatus.ERROR)
        assert pr.model_status == LearningStatus.ERROR

    def test_latency_ms_set(self):
        pr = PredictionResult(prediction=1, latency_ms=2.5)
        assert pr.latency_ms == pytest.approx(2.5)

    def test_all_fields_together(self):
        probs = {"yes": 0.9, "no": 0.1}
        pr = PredictionResult(
            prediction="yes",
            confidence=0.9,
            probabilities=probs,
            used_fallback=False,
            model_status=LearningStatus.READY,
            latency_ms=1.23,
        )
        assert pr.prediction == "yes"
        assert pr.confidence == pytest.approx(0.9)
        assert pr.probabilities == probs
        assert pr.used_fallback is False
        assert pr.model_status == LearningStatus.READY
        assert pr.latency_ms == pytest.approx(1.23)


# ---------------------------------------------------------------------------
# LearningResult
# ---------------------------------------------------------------------------


class TestLearningResultDefaults:
    """Default field values for LearningResult."""

    def test_success_true(self):
        lr = LearningResult(success=True)
        assert lr.success is True

    def test_success_false(self):
        lr = LearningResult(success=False)
        assert lr.success is False

    def test_samples_learned_default_zero(self):
        lr = LearningResult(success=True)
        assert lr.samples_learned == 0

    def test_total_samples_default_zero(self):
        lr = LearningResult(success=True)
        assert lr.total_samples == 0

    def test_error_message_default_none(self):
        lr = LearningResult(success=True)
        assert lr.error_message is None

    def test_stats_default_none(self):
        lr = LearningResult(success=True)
        assert lr.stats is None


class TestLearningResultCustomValues:
    """Custom field values for LearningResult."""

    def test_samples_learned_custom(self):
        lr = LearningResult(success=True, samples_learned=50)
        assert lr.samples_learned == 50

    def test_total_samples_custom(self):
        lr = LearningResult(success=True, total_samples=100)
        assert lr.total_samples == 100

    def test_error_message_on_failure(self):
        lr = LearningResult(success=False, error_message="Model not initialised")
        assert lr.error_message == "Model not initialised"

    def test_stats_attached(self):
        stats = LearningStats(samples_learned=10)
        lr = LearningResult(success=True, stats=stats)
        assert lr.stats is stats
        assert lr.stats.samples_learned == 10

    def test_all_fields_success(self):
        stats = LearningStats(accuracy=0.99)
        lr = LearningResult(
            success=True,
            samples_learned=200,
            total_samples=205,
            error_message=None,
            stats=stats,
        )
        assert lr.success is True
        assert lr.samples_learned == 200
        assert lr.total_samples == 205
        assert lr.error_message is None
        assert lr.stats.accuracy == pytest.approx(0.99)

    def test_all_fields_failure(self):
        lr = LearningResult(
            success=False,
            samples_learned=0,
            total_samples=10,
            error_message="connection refused",
            stats=None,
        )
        assert lr.success is False
        assert lr.samples_learned == 0
        assert lr.total_samples == 10
        assert lr.error_message == "connection refused"
        assert lr.stats is None


# ---------------------------------------------------------------------------
# PipelineStats
# ---------------------------------------------------------------------------


class TestPipelineStatsDefaults:
    """Default field values for PipelineStats."""

    def test_learning_stats_is_instance(self):
        ps = PipelineStats()
        assert isinstance(ps.learning_stats, LearningStats)

    def test_learning_stats_are_independent(self):
        ps1 = PipelineStats()
        ps2 = PipelineStats()
        ps1.learning_stats.samples_learned = 99
        assert ps2.learning_stats.samples_learned == 0

    def test_total_predictions_default(self):
        ps = PipelineStats()
        assert ps.total_predictions == 0

    def test_online_predictions_default(self):
        ps = PipelineStats()
        assert ps.online_predictions == 0

    def test_fallback_predictions_default(self):
        ps = PipelineStats()
        assert ps.fallback_predictions == 0

    def test_fallback_rate_default(self):
        ps = PipelineStats()
        assert ps.fallback_rate == 0.0

    def test_model_ready_default_false(self):
        ps = PipelineStats()
        assert ps.model_ready is False

    def test_has_fallback_default_false(self):
        ps = PipelineStats()
        assert ps.has_fallback is False

    def test_preprocessing_enabled_default_false(self):
        ps = PipelineStats()
        assert ps.preprocessing_enabled is False

    def test_total_learnings_default(self):
        ps = PipelineStats()
        assert ps.total_learnings == 0

    def test_successful_predictions_default(self):
        ps = PipelineStats()
        assert ps.successful_predictions == 0

    def test_failed_predictions_default(self):
        ps = PipelineStats()
        assert ps.failed_predictions == 0

    def test_avg_prediction_latency_ms_default(self):
        ps = PipelineStats()
        assert ps.avg_prediction_latency_ms == 0.0

    def test_model_accuracy_default(self):
        ps = PipelineStats()
        assert ps.model_accuracy == 0.0

    def test_samples_in_buffer_default(self):
        ps = PipelineStats()
        assert ps.samples_in_buffer == 0

    def test_last_batch_time_default_none(self):
        ps = PipelineStats()
        assert ps.last_batch_time is None

    def test_model_status_default_cold_start(self):
        ps = PipelineStats()
        assert ps.model_status == LearningStatus.COLD_START


class TestPipelineStatsCustomValues:
    """Custom field values for PipelineStats."""

    def test_total_predictions_custom(self):
        ps = PipelineStats(total_predictions=500)
        assert ps.total_predictions == 500

    def test_model_ready_true(self):
        ps = PipelineStats(model_ready=True)
        assert ps.model_ready is True

    def test_has_fallback_true(self):
        ps = PipelineStats(has_fallback=True)
        assert ps.has_fallback is True

    def test_preprocessing_enabled_true(self):
        ps = PipelineStats(preprocessing_enabled=True)
        assert ps.preprocessing_enabled is True

    def test_last_batch_time_set(self):
        now = datetime.now(UTC)
        ps = PipelineStats(last_batch_time=now)
        assert ps.last_batch_time == now

    def test_model_status_ready(self):
        ps = PipelineStats(model_status=LearningStatus.READY)
        assert ps.model_status == LearningStatus.READY

    def test_avg_prediction_latency(self):
        ps = PipelineStats(avg_prediction_latency_ms=3.7)
        assert ps.avg_prediction_latency_ms == pytest.approx(3.7)

    def test_model_accuracy_custom(self):
        ps = PipelineStats(model_accuracy=0.87)
        assert ps.model_accuracy == pytest.approx(0.87)


class TestPipelineStatsProperties:
    """Tests for computed properties on PipelineStats."""

    def test_samples_learned_delegates_to_learning_stats(self):
        ls = LearningStats(samples_learned=123)
        ps = PipelineStats(learning_stats=ls)
        assert ps.samples_learned == 123

    def test_samples_learned_zero_by_default(self):
        ps = PipelineStats()
        assert ps.samples_learned == 0

    def test_accuracy_delegates_to_learning_stats(self):
        ls = LearningStats(accuracy=0.75)
        ps = PipelineStats(learning_stats=ls)
        assert ps.accuracy == pytest.approx(0.75)

    def test_accuracy_zero_by_default(self):
        ps = PipelineStats()
        assert ps.accuracy == 0.0

    def test_status_returns_string_value(self):
        ls = LearningStats(status=LearningStatus.READY)
        ps = PipelineStats(learning_stats=ls)
        assert ps.status == "ready"

    def test_status_cold_start_string(self):
        ps = PipelineStats()
        assert ps.status == "cold_start"

    def test_status_warming_up_string(self):
        ls = LearningStats(status=LearningStatus.WARMING_UP)
        ps = PipelineStats(learning_stats=ls)
        assert ps.status == "warming_up"

    def test_status_error_string(self):
        ls = LearningStats(status=LearningStatus.ERROR)
        ps = PipelineStats(learning_stats=ls)
        assert ps.status == "error"

    def test_samples_learned_updated_after_mutation(self):
        ps = PipelineStats()
        ps.learning_stats.samples_learned = 77
        assert ps.samples_learned == 77

    def test_accuracy_updated_after_mutation(self):
        ps = PipelineStats()
        ps.learning_stats.accuracy = 0.92
        assert ps.accuracy == pytest.approx(0.92)

    def test_status_updated_after_mutation(self):
        ps = PipelineStats()
        ps.learning_stats.status = LearningStatus.READY
        assert ps.status == "ready"


# ---------------------------------------------------------------------------
# ConsumerStats
# ---------------------------------------------------------------------------


class TestConsumerStatsDefaults:
    """Default field values for ConsumerStats."""

    def test_messages_received_default(self):
        cs = ConsumerStats()
        assert cs.messages_received == 0

    def test_messages_processed_default(self):
        cs = ConsumerStats()
        assert cs.messages_processed == 0

    def test_messages_failed_default(self):
        cs = ConsumerStats()
        assert cs.messages_failed == 0

    def test_samples_learned_default(self):
        cs = ConsumerStats()
        assert cs.samples_learned == 0

    def test_last_offset_default(self):
        cs = ConsumerStats()
        assert cs.last_offset == -1

    def test_last_message_at_default_none(self):
        cs = ConsumerStats()
        assert cs.last_message_at is None

    def test_consumer_lag_default(self):
        cs = ConsumerStats()
        assert cs.consumer_lag == 0

    def test_status_default(self):
        cs = ConsumerStats()
        assert cs.status == "stopped"

    def test_messages_consumed_default(self):
        cs = ConsumerStats()
        assert cs.messages_consumed == 0

    def test_batches_processed_default(self):
        cs = ConsumerStats()
        assert cs.batches_processed == 0

    def test_lag_default(self):
        cs = ConsumerStats()
        assert cs.lag == 0

    def test_last_message_time_default_none(self):
        cs = ConsumerStats()
        assert cs.last_message_time is None

    def test_consumer_status_default(self):
        cs = ConsumerStats()
        assert cs.consumer_status == "stopped"


class TestConsumerStatsCustomValues:
    """Custom field values for ConsumerStats."""

    def test_messages_received_custom(self):
        cs = ConsumerStats(messages_received=100)
        assert cs.messages_received == 100

    def test_messages_processed_custom(self):
        cs = ConsumerStats(messages_processed=90)
        assert cs.messages_processed == 90

    def test_messages_failed_custom(self):
        cs = ConsumerStats(messages_failed=10)
        assert cs.messages_failed == 10

    def test_samples_learned_custom(self):
        cs = ConsumerStats(samples_learned=75)
        assert cs.samples_learned == 75

    def test_last_offset_custom(self):
        cs = ConsumerStats(last_offset=42)
        assert cs.last_offset == 42

    def test_last_message_at_set(self):
        now = datetime.now(UTC)
        cs = ConsumerStats(last_message_at=now)
        assert cs.last_message_at == now

    def test_consumer_lag_custom(self):
        cs = ConsumerStats(consumer_lag=5)
        assert cs.consumer_lag == 5

    def test_status_running(self):
        cs = ConsumerStats(status="running")
        assert cs.status == "running"

    def test_messages_consumed_custom(self):
        cs = ConsumerStats(messages_consumed=200)
        assert cs.messages_consumed == 200

    def test_batches_processed_custom(self):
        cs = ConsumerStats(batches_processed=3)
        assert cs.batches_processed == 3

    def test_lag_custom(self):
        cs = ConsumerStats(lag=15)
        assert cs.lag == 15

    def test_last_message_time_set(self):
        now = datetime.now(UTC)
        cs = ConsumerStats(last_message_time=now)
        assert cs.last_message_time == now

    def test_consumer_status_custom(self):
        cs = ConsumerStats(consumer_status="running")
        assert cs.consumer_status == "running"

    def test_all_fields_together(self):
        now = datetime.now(UTC)
        cs = ConsumerStats(
            messages_received=1000,
            messages_processed=980,
            messages_failed=20,
            samples_learned=500,
            last_offset=999,
            last_message_at=now,
            consumer_lag=3,
            status="running",
            messages_consumed=980,
            batches_processed=10,
            lag=3,
            last_message_time=now,
            consumer_status="running",
        )
        assert cs.messages_received == 1000
        assert cs.messages_processed == 980
        assert cs.messages_failed == 20
        assert cs.samples_learned == 500
        assert cs.last_offset == 999
        assert cs.last_message_at == now
        assert cs.consumer_lag == 3
        assert cs.status == "running"
        assert cs.messages_consumed == 980
        assert cs.batches_processed == 10
        assert cs.lag == 3
        assert cs.last_message_time == now
        assert cs.consumer_status == "running"


# ---------------------------------------------------------------------------
# Cross-model integration sanity checks
# ---------------------------------------------------------------------------


class TestModelInteractions:
    """Ensure models integrate correctly with each other."""

    def test_learning_result_wraps_learning_stats(self):
        stats = LearningStats(
            samples_learned=50,
            accuracy=0.85,
            status=LearningStatus.WARMING_UP,
        )
        lr = LearningResult(success=True, samples_learned=50, stats=stats)
        assert lr.stats.status == LearningStatus.WARMING_UP
        assert lr.stats.accuracy == pytest.approx(0.85)

    def test_pipeline_stats_wraps_learning_stats(self):
        ls = LearningStats(samples_learned=300, accuracy=0.95, status=LearningStatus.READY)
        ps = PipelineStats(learning_stats=ls, model_ready=True)
        assert ps.samples_learned == 300
        assert ps.accuracy == pytest.approx(0.95)
        assert ps.status == "ready"

    def test_prediction_result_confidence_zero(self):
        pr = PredictionResult(prediction=0, confidence=0.0)
        assert pr.confidence == 0.0

    def test_prediction_result_probabilities_empty_dict(self):
        pr = PredictionResult(prediction=0, probabilities={})
        assert pr.probabilities == {}

    def test_learning_stats_last_updated_round_trip(self):
        ts = datetime(2025, 3, 10, 8, 30, 0, tzinfo=UTC)
        s = LearningStats()
        s.last_updated = ts
        assert s.last_updated == ts
        assert s.last_update == ts
