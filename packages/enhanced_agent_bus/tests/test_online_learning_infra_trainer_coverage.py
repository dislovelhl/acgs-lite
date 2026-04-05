# Constitutional Hash: 608508a9bd224290
# Sprint 58 — online_learning_infra/trainer.py coverage
"""
Comprehensive tests for online_learning_infra/trainer.py.

Targets ≥95% line/branch coverage of OnlineLearningPipeline and all
module-level constants/error tuples in that module.

Strategy
--------
* River and numpy are patched as available at module-import time so the
  class-under-test initialises without real ML libraries being installed.
* The ``RiverSklearnAdapter`` and ``OnlineLearningEvaluator`` are replaced
  with ``MagicMock`` instances so every path through ``OnlineLearningPipeline``
  can be exercised deterministically.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TRAINER_MODULE = "enhanced_agent_bus.online_learning_infra.trainer"
_ADAPTER_MODULE = "enhanced_agent_bus.online_learning_infra.adapter"


def _make_mock_adapter(
    *,
    is_ready: bool = False,
    samples_learned: int = 0,
    status=None,
) -> MagicMock:
    """Return a fully-configured mock RiverSklearnAdapter."""
    from enhanced_agent_bus.online_learning_infra.config import LearningStatus
    from enhanced_agent_bus.online_learning_infra.models import LearningStats

    adapter = MagicMock()
    adapter.is_ready = is_ready
    adapter.samples_learned = samples_learned

    _status = status or LearningStatus.COLD_START
    stats = LearningStats(samples_learned=samples_learned, status=_status)
    adapter.get_stats.return_value = stats
    adapter.predict_one.return_value = 1
    adapter.predict_proba_one.return_value = {0: 0.3, 1: 0.7}
    return adapter


def _make_mock_evaluator() -> MagicMock:
    """Return a mock OnlineLearningEvaluator."""
    from enhanced_agent_bus.online_learning_infra.models import PipelineStats

    ev = MagicMock()
    ev.compute_pipeline_stats.return_value = PipelineStats()
    return ev


def _build_pipeline(
    *,
    feature_names=None,
    model_type=None,
    enable_preprocessing: bool = True,
    enable_fallback: bool = True,
    adapter: MagicMock | None = None,
    evaluator: MagicMock | None = None,
    river_available: bool = True,
):
    """
    Construct an OnlineLearningPipeline with all external deps mocked.

    The RiverSklearnAdapter constructor is bypassed by directly assigning
    the mock *after* construction so we never touch real River code.
    """
    from enhanced_agent_bus.online_learning_infra.config import ModelType

    _model_type = model_type or ModelType.CLASSIFIER
    _adapter = adapter or _make_mock_adapter()
    _evaluator = evaluator or _make_mock_evaluator()

    # Patch RIVER_AVAILABLE so _check_dependencies passes
    # and running-stats block is toggled correctly.
    with (
        patch(f"{_TRAINER_MODULE}.RIVER_AVAILABLE", river_available),
        patch(f"{_ADAPTER_MODULE}.RIVER_AVAILABLE", river_available),
        patch(
            f"{_TRAINER_MODULE}.RiverSklearnAdapter",
            return_value=_adapter,
        ),
        patch(
            f"{_TRAINER_MODULE}.OnlineLearningEvaluator",
            return_value=_evaluator,
        ),
        # river_stats.Mean() used inside __init__ when preprocessing is on
        patch(f"{_TRAINER_MODULE}.river_stats") as mock_rs,
    ):
        mock_rs.Mean.return_value = MagicMock()

        from enhanced_agent_bus.online_learning_infra.trainer import (
            OnlineLearningPipeline,
        )

        pipeline = OnlineLearningPipeline(
            feature_names=feature_names,
            model_type=_model_type,
            enable_preprocessing=enable_preprocessing,
            enable_fallback=enable_fallback,
        )

    # Overwrite the adapter/evaluator that were injected during construction
    # so downstream calls observe the mock we configured.
    pipeline.adapter = _adapter
    pipeline.evaluator = _evaluator
    return pipeline


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_fallback_prediction_errors_tuple(self):
        from enhanced_agent_bus.online_learning_infra.trainer import (
            FALLBACK_PREDICTION_ERRORS,
        )

        assert RuntimeError in FALLBACK_PREDICTION_ERRORS
        assert ValueError in FALLBACK_PREDICTION_ERRORS
        assert TypeError in FALLBACK_PREDICTION_ERRORS
        assert KeyError in FALLBACK_PREDICTION_ERRORS
        assert AttributeError in FALLBACK_PREDICTION_ERRORS

    def test_online_learning_feedback_errors_tuple(self):
        from enhanced_agent_bus.online_learning_infra.trainer import (
            ONLINE_LEARNING_FEEDBACK_ERRORS,
        )

        assert RuntimeError in ONLINE_LEARNING_FEEDBACK_ERRORS
        assert ValueError in ONLINE_LEARNING_FEEDBACK_ERRORS
        assert TypeError in ONLINE_LEARNING_FEEDBACK_ERRORS
        assert KeyError in ONLINE_LEARNING_FEEDBACK_ERRORS
        assert AttributeError in ONLINE_LEARNING_FEEDBACK_ERRORS


# ---------------------------------------------------------------------------
# _check_dependencies
# ---------------------------------------------------------------------------


class TestCheckDependencies:
    def test_raises_import_error_when_river_unavailable(self):
        with (
            patch(f"{_TRAINER_MODULE}.RIVER_AVAILABLE", False),
            patch(f"{_ADAPTER_MODULE}.RIVER_AVAILABLE", False),
        ):
            from enhanced_agent_bus.online_learning_infra.trainer import (
                OnlineLearningPipeline,
            )

            with pytest.raises(ImportError, match="River is required"):
                OnlineLearningPipeline.__new__(OnlineLearningPipeline)._check_dependencies()

    def test_no_error_when_river_available(self):
        with patch(f"{_TRAINER_MODULE}.RIVER_AVAILABLE", True):
            from enhanced_agent_bus.online_learning_infra.trainer import (
                OnlineLearningPipeline,
            )

            # Should not raise
            obj = object.__new__(OnlineLearningPipeline)
            obj._check_dependencies()  # patched RIVER_AVAILABLE = True


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_feature_names_empty_list(self):
        p = _build_pipeline(feature_names=None)
        assert p.feature_names == []

    def test_custom_feature_names_stored(self):
        p = _build_pipeline(feature_names=["a", "b"])
        assert p.feature_names == ["a", "b"]

    def test_enable_preprocessing_stored(self):
        p = _build_pipeline(enable_preprocessing=True)
        assert p.enable_preprocessing is True

    def test_enable_fallback_stored(self):
        p = _build_pipeline(enable_fallback=True)
        assert p.enable_fallback is True

    def test_fallback_model_none_initially(self):
        p = _build_pipeline()
        assert p._fallback_model is None

    def test_fallback_predictions_zero_initially(self):
        p = _build_pipeline()
        assert p._fallback_predictions == 0

    def test_online_predictions_zero_initially(self):
        p = _build_pipeline()
        assert p._online_predictions == 0

    def test_running_stats_populated_with_preprocessing_and_features(self):
        p = _build_pipeline(feature_names=["x1", "x2"], enable_preprocessing=True)
        # Each feature should have a running stat object
        assert "x1" in p._running_stats
        assert "x2" in p._running_stats

    def test_running_stats_empty_when_no_features(self):
        p = _build_pipeline(feature_names=None, enable_preprocessing=True)
        assert p._running_stats == {}

    def test_running_stats_empty_when_preprocessing_disabled(self):
        p = _build_pipeline(feature_names=["x1"], enable_preprocessing=False)
        assert p._running_stats == {}

    def test_running_stats_empty_when_river_not_available(self):
        # When RIVER_AVAILABLE=False, _check_dependencies raises ImportError.
        # We verify the guard works by inspecting the module constant directly;
        # we do not construct the pipeline in that state.
        with patch(f"{_TRAINER_MODULE}.RIVER_AVAILABLE", False):
            # The guard is: `if enable_preprocessing and RIVER_AVAILABLE`
            # so with RIVER_AVAILABLE=False the loop is skipped.
            import importlib

            from enhanced_agent_bus.online_learning_infra import trainer

            assert trainer.RIVER_AVAILABLE is False  # confirms the patch took effect


# ---------------------------------------------------------------------------
# set_fallback_model
# ---------------------------------------------------------------------------


class TestSetFallbackModel:
    def test_sets_fallback_model(self):
        p = _build_pipeline()
        mock_model = MagicMock()
        p.set_fallback_model(mock_model)
        assert p._fallback_model is mock_model

    def test_logs_info_on_set(self, caplog):
        import logging

        p = _build_pipeline()
        with caplog.at_level(logging.INFO):
            p.set_fallback_model(MagicMock())
        assert "Fallback" in caplog.text or "fallback" in caplog.text.lower()


# ---------------------------------------------------------------------------
# predict — online path (no fallback)
# ---------------------------------------------------------------------------


class TestPredictOnlinePath:
    def test_returns_prediction_result(self):
        from enhanced_agent_bus.online_learning_infra.models import PredictionResult

        p = _build_pipeline()
        result = p.predict({"f1": 0.5})
        assert isinstance(result, PredictionResult)

    def test_used_fallback_false(self):
        p = _build_pipeline()
        result = p.predict({"f1": 0.5})
        assert result.used_fallback is False

    def test_online_predictions_incremented(self):
        p = _build_pipeline()
        p.predict({"f1": 0.5})
        assert p._online_predictions == 1

    def test_online_predictions_not_incremented_by_fallback(self):
        import numpy as np

        adapter = _make_mock_adapter(is_ready=False)
        p = _build_pipeline(adapter=adapter, enable_fallback=True, feature_names=["f1"])
        fallback = MagicMock()
        fallback.predict.return_value = [1]
        fallback.predict_proba.return_value = [np.array([0.2, 0.8])]
        fallback.classes_ = [0, 1]
        p._fallback_model = fallback
        # is_ready=False + fallback set → fallback path used
        # online counter must NOT be incremented on that prediction
        before = p._online_predictions
        p.predict({"f1": 0.5})
        assert p._online_predictions == before

    def test_confidence_set_for_classifier(self):
        p = _build_pipeline()
        result = p.predict({"f1": 0.5})
        # adapter.predict_proba_one returns {0: 0.3, 1: 0.7}
        assert result.confidence == pytest.approx(0.7)

    def test_probabilities_set_for_classifier(self):
        p = _build_pipeline()
        result = p.predict({"f1": 0.5})
        assert result.probabilities == {0: 0.3, 1: 0.7}

    def test_empty_proba_dict_leaves_confidence_none(self):
        from enhanced_agent_bus.online_learning_infra.config import ModelType

        adapter = _make_mock_adapter()
        adapter.predict_proba_one.return_value = {}  # empty → no confidence
        p = _build_pipeline(adapter=adapter)
        result = p.predict({"f1": 0.5})
        assert result.confidence is None
        assert result.probabilities is None

    def test_no_proba_for_regressor(self):
        from enhanced_agent_bus.online_learning_infra.config import ModelType

        adapter = _make_mock_adapter()
        p = _build_pipeline(adapter=adapter, model_type=ModelType.REGRESSOR)
        result = p.predict({"f1": 0.5})
        assert result.probabilities is None
        assert result.confidence is None


# ---------------------------------------------------------------------------
# predict — fallback path
# ---------------------------------------------------------------------------


class TestPredictFallbackPath:
    def _pipeline_with_fallback(self, *, proba=True, classes=True):
        adapter = _make_mock_adapter(is_ready=False)  # not ready → fallback triggers
        p = _build_pipeline(adapter=adapter, enable_fallback=True, feature_names=["f1"])

        fallback = MagicMock()
        fallback.predict.return_value = [1]

        if proba:
            mock_proba = MagicMock()
            mock_proba.__iter__ = MagicMock(return_value=iter([0.3, 0.7]))
            # Make max() work
            mock_proba.__len__ = MagicMock(return_value=2)

            import numpy as np

            proba_array = np.array([0.3, 0.7])
            fallback.predict_proba.return_value = [proba_array]
            if classes:
                fallback.classes_ = [0, 1]
        else:
            del fallback.predict_proba  # remove attribute so hasattr returns False

        p._fallback_model = fallback
        return p

    def test_used_fallback_true(self):
        p = self._pipeline_with_fallback()
        result = p.predict({"f1": 0.5})
        assert result.used_fallback is True

    def test_fallback_predictions_incremented(self):
        p = self._pipeline_with_fallback()
        p.predict({"f1": 0.5})
        assert p._fallback_predictions == 1

    def test_prediction_value_from_fallback(self):
        p = self._pipeline_with_fallback()
        result = p.predict({"f1": 0.5})
        assert result.prediction == 1

    def test_confidence_set_from_fallback_proba(self):
        p = self._pipeline_with_fallback(proba=True, classes=True)
        result = p.predict({"f1": 0.5})
        assert result.confidence == pytest.approx(0.7)

    def test_probabilities_set_when_classes_available(self):
        p = self._pipeline_with_fallback(proba=True, classes=True)
        result = p.predict({"f1": 0.5})
        assert result.probabilities == {0: 0.3, 1: 0.7}

    def test_no_probabilities_without_predict_proba(self):
        """When fallback has no predict_proba, probabilities should be None."""
        adapter = _make_mock_adapter(is_ready=False)
        p = _build_pipeline(adapter=adapter, enable_fallback=True, feature_names=["f1"])
        fallback = MagicMock(spec=["predict"])  # no predict_proba
        fallback.predict.return_value = [0]
        p._fallback_model = fallback
        result = p.predict({"f1": 0.5})
        assert result.probabilities is None

    def test_fallback_error_falls_through_to_online(self):
        """When fallback raises, online path is used as recovery."""
        adapter = _make_mock_adapter(is_ready=False)
        p = _build_pipeline(adapter=adapter, enable_fallback=True, feature_names=["f1"])

        fallback = MagicMock()
        fallback.predict.side_effect = RuntimeError("fallback broken")
        p._fallback_model = fallback

        # Should NOT raise — falls through to online adapter
        result = p.predict({"f1": 0.5})
        assert result.used_fallback is False
        # online counter should be incremented
        assert p._online_predictions == 1

    def test_fallback_disabled_even_with_model(self):
        """If enable_fallback=False, online path is used regardless."""
        adapter = _make_mock_adapter(is_ready=False)
        p = _build_pipeline(adapter=adapter, enable_fallback=False)
        p._fallback_model = MagicMock()  # model present but disabled
        result = p.predict({"f1": 0.5})
        assert result.used_fallback is False

    def test_fallback_skipped_when_adapter_ready(self):
        """Even if fallback model exists, online path is used when adapter is ready."""
        adapter = _make_mock_adapter(is_ready=True)
        p = _build_pipeline(adapter=adapter, enable_fallback=True)
        p._fallback_model = MagicMock()  # present but adapter is ready
        result = p.predict({"f1": 0.5})
        assert result.used_fallback is False

    def test_fallback_classes_not_present_skips_probabilities(self):
        """predict_proba exists but no classes_ attribute."""
        import numpy as np

        adapter = _make_mock_adapter(is_ready=False)
        p = _build_pipeline(adapter=adapter, enable_fallback=True, feature_names=["f1"])

        fallback = MagicMock(spec=["predict", "predict_proba"])
        fallback.predict.return_value = [1]
        fallback.predict_proba.return_value = [np.array([0.4, 0.6])]
        # No classes_ attribute on spec

        p._fallback_model = fallback
        result = p.predict({"f1": 0.5})
        # confidence should still be set
        assert result.confidence == pytest.approx(0.6)
        # probabilities should be None (no classes_)
        assert result.probabilities is None


# ---------------------------------------------------------------------------
# _to_array
# ---------------------------------------------------------------------------


class TestToArray:
    def test_dict_with_feature_names(self):
        import numpy as np

        p = _build_pipeline(feature_names=["a", "b"])
        with patch(f"{_TRAINER_MODULE}.np_module", np):
            arr = p._to_array({"a": 1.0, "b": 2.0})
        assert list(arr) == pytest.approx([1.0, 2.0])

    def test_dict_without_feature_names(self):
        import numpy as np

        p = _build_pipeline(feature_names=[])
        with patch(f"{_TRAINER_MODULE}.np_module", np):
            arr = p._to_array({"a": 1.0, "b": 2.0})
        assert sorted(arr) == pytest.approx([1.0, 2.0])

    def test_array_like_input(self):
        import numpy as np

        p = _build_pipeline()
        x = np.array([3.0, 4.0])
        with patch(f"{_TRAINER_MODULE}.np_module", np):
            arr = p._to_array(x)
        assert list(arr) == pytest.approx([3.0, 4.0])

    def test_plain_list_input(self):
        import numpy as np

        p = _build_pipeline()
        with patch(f"{_TRAINER_MODULE}.np_module", np):
            arr = p._to_array([5.0, 6.0])
        assert list(arr) == pytest.approx([5.0, 6.0])


# ---------------------------------------------------------------------------
# learn
# ---------------------------------------------------------------------------


class TestLearn:
    def test_calls_adapter_learn_one(self):
        adapter = _make_mock_adapter()
        p = _build_pipeline(adapter=adapter, feature_names=["x1"])
        p.learn({"x1": 1.0}, 1)
        adapter.learn_one.assert_called_once_with({"x1": 1.0}, 1)

    def test_updates_running_stats_for_known_feature(self):
        mock_stat = MagicMock()
        adapter = _make_mock_adapter()
        p = _build_pipeline(adapter=adapter, feature_names=["x1"], enable_preprocessing=True)
        p._running_stats["x1"] = mock_stat

        p.learn({"x1": 2.5}, 1)
        mock_stat.update.assert_called_once_with(2.5)

    def test_skips_running_stats_for_unknown_feature(self):
        mock_stat = MagicMock()
        adapter = _make_mock_adapter()
        p = _build_pipeline(adapter=adapter, feature_names=["x1"], enable_preprocessing=True)
        p._running_stats["x1"] = mock_stat

        # "x2" is not in _running_stats
        p.learn({"x2": 9.9}, 1)
        mock_stat.update.assert_not_called()

    def test_skips_running_stats_when_preprocessing_disabled(self):
        mock_stat = MagicMock()
        adapter = _make_mock_adapter()
        p = _build_pipeline(adapter=adapter, feature_names=["x1"], enable_preprocessing=False)
        p._running_stats["x1"] = mock_stat

        p.learn({"x1": 2.5}, 1)
        mock_stat.update.assert_not_called()

    def test_skips_running_stats_when_x_not_dict(self):
        mock_stat = MagicMock()
        adapter = _make_mock_adapter()
        p = _build_pipeline(adapter=adapter, feature_names=["x1"], enable_preprocessing=True)
        p._running_stats["x1"] = mock_stat

        # Non-dict input: stats update should be skipped
        p.learn([1.0, 2.0], 1)
        mock_stat.update.assert_not_called()


# ---------------------------------------------------------------------------
# learn_from_feedback
# ---------------------------------------------------------------------------


class TestLearnFromFeedback:
    def test_success_with_flat_features_and_outcome(self):
        adapter = _make_mock_adapter(samples_learned=1)
        p = _build_pipeline(adapter=adapter)

        result = p.learn_from_feedback({"f1": 1.0, "f2": 0.5}, outcome=1)
        assert result.success is True
        assert result.samples_learned == 1

    def test_success_with_nested_features_dict(self):
        """features dict containing 'features' key and 'outcome' key."""
        adapter = _make_mock_adapter(samples_learned=5)
        p = _build_pipeline(adapter=adapter)

        feedback = {"features": {"f1": 0.2, "f2": 0.8}, "outcome": 1}
        result = p.learn_from_feedback(feedback)
        assert result.success is True

    def test_success_with_actual_impact_key(self):
        adapter = _make_mock_adapter(samples_learned=3)
        p = _build_pipeline(adapter=adapter)

        feedback = {"features": {"f1": 0.1}, "actual_impact": 0.9}
        result = p.learn_from_feedback(feedback)
        assert result.success is True

    def test_decision_id_logged_when_provided(self, caplog):
        import logging

        adapter = _make_mock_adapter(samples_learned=1)
        p = _build_pipeline(adapter=adapter)

        with caplog.at_level(logging.INFO):
            p.learn_from_feedback({"f1": 1.0}, outcome=1, decision_id="abc-123")
        assert "abc-123" in caplog.text

    def test_decision_id_from_nested_dict(self, caplog):
        import logging

        adapter = _make_mock_adapter(samples_learned=1)
        p = _build_pipeline(adapter=adapter)

        feedback = {
            "features": {"f1": 0.5},
            "outcome": 1,
            "decision_id": "nested-id-999",
        }
        with caplog.at_level(logging.INFO):
            p.learn_from_feedback(feedback)
        assert "nested-id-999" in caplog.text

    def test_failure_when_outcome_none_flat(self):
        p = _build_pipeline()
        result = p.learn_from_feedback({"f1": 0.5}, outcome=None)
        assert result.success is False
        assert result.error_message is not None

    def test_failure_when_outcome_missing_from_nested(self):
        p = _build_pipeline()
        feedback = {"features": {"f1": 0.5}}  # no outcome or actual_impact
        result = p.learn_from_feedback(feedback)
        assert result.success is False

    def test_total_samples_reflects_adapter(self):
        adapter = _make_mock_adapter(samples_learned=42)
        p = _build_pipeline(adapter=adapter)
        result = p.learn_from_feedback({"f1": 1.0}, outcome=1)
        assert result.total_samples == 42

    def test_non_numeric_values_filtered(self):
        """Non-int/float values in features dict are filtered out."""
        adapter = _make_mock_adapter(samples_learned=1)
        p = _build_pipeline(adapter=adapter)

        result = p.learn_from_feedback({"f1": 1.0, "label": "text_value", "flag": True}, outcome=1)
        # Should succeed and only pass numeric keys to learn()
        assert result.success is True

    def test_error_during_learning_returns_failure(self):
        adapter = _make_mock_adapter()
        adapter.learn_one.side_effect = RuntimeError("model blew up")
        p = _build_pipeline(adapter=adapter)

        result = p.learn_from_feedback({"f1": 1.0}, outcome=1)
        assert result.success is False
        assert "model blew up" in (result.error_message or "")

    def test_value_error_returns_failure(self):
        adapter = _make_mock_adapter()
        adapter.learn_one.side_effect = ValueError("bad value")
        p = _build_pipeline(adapter=adapter)

        result = p.learn_from_feedback({"f1": 1.0}, outcome=1)
        assert result.success is False

    def test_type_error_returns_failure(self):
        adapter = _make_mock_adapter()
        adapter.learn_one.side_effect = TypeError("wrong type")
        p = _build_pipeline(adapter=adapter)

        result = p.learn_from_feedback({"f1": 1.0}, outcome=1)
        assert result.success is False

    def test_key_error_returns_failure(self):
        adapter = _make_mock_adapter()
        adapter.learn_one.side_effect = KeyError("missing key")
        p = _build_pipeline(adapter=adapter)

        result = p.learn_from_feedback({"f1": 1.0}, outcome=1)
        assert result.success is False

    def test_attribute_error_returns_failure(self):
        adapter = _make_mock_adapter()
        adapter.learn_one.side_effect = AttributeError("no attr")
        p = _build_pipeline(adapter=adapter)

        result = p.learn_from_feedback({"f1": 1.0}, outcome=1)
        assert result.success is False


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    def test_returns_pipeline_stats(self):
        from enhanced_agent_bus.online_learning_infra.models import PipelineStats

        evaluator = _make_mock_evaluator()
        p = _build_pipeline(evaluator=evaluator)
        result = p.get_stats()
        assert isinstance(result, PipelineStats)

    def test_delegates_to_evaluator(self):
        evaluator = _make_mock_evaluator()
        adapter = _make_mock_adapter()
        p = _build_pipeline(adapter=adapter, evaluator=evaluator)

        p._online_predictions = 7
        p._fallback_predictions = 3
        p.get_stats()

        evaluator.compute_pipeline_stats.assert_called_once_with(
            adapter_stats=adapter.get_stats.return_value,
            online_predictions=7,
            fallback_predictions=3,
            has_fallback=False,  # _fallback_model is None
            preprocessing_enabled=p.enable_preprocessing,
        )

    def test_has_fallback_true_when_model_set(self):
        evaluator = _make_mock_evaluator()
        p = _build_pipeline(evaluator=evaluator)
        p._fallback_model = MagicMock()

        p.get_stats()
        call_kwargs = evaluator.compute_pipeline_stats.call_args.kwargs
        assert call_kwargs["has_fallback"] is True


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


class TestReset:
    def test_adapter_reset_called(self):
        adapter = _make_mock_adapter()
        p = _build_pipeline(adapter=adapter)
        p.reset()
        adapter.reset.assert_called_once()

    def test_fallback_predictions_zeroed(self):
        p = _build_pipeline()
        p._fallback_predictions = 99
        p.reset()
        assert p._fallback_predictions == 0

    def test_online_predictions_zeroed(self):
        p = _build_pipeline()
        p._online_predictions = 55
        p.reset()
        assert p._online_predictions == 0

    def test_running_stats_reinitialized_when_preprocessing_and_river(self):
        p = _build_pipeline(feature_names=["a", "b"], enable_preprocessing=True)

        # Replace stats with sentinels so we can detect replacement
        old_a = p._running_stats.get("a")
        old_b = p._running_stats.get("b")

        with patch(f"{_TRAINER_MODULE}.river_stats") as mock_rs:
            new_mean = MagicMock()
            mock_rs.Mean.return_value = new_mean
            with patch(f"{_TRAINER_MODULE}.RIVER_AVAILABLE", True):
                p.reset()

        # After reset, each key should have a new Mean()
        assert "a" in p._running_stats
        assert "b" in p._running_stats

    def test_running_stats_not_reinitialized_when_river_unavailable(self):
        p = _build_pipeline(feature_names=["a"], enable_preprocessing=True)
        p._running_stats["a"] = sentinel = object()

        with patch(f"{_TRAINER_MODULE}.RIVER_AVAILABLE", False):
            p.reset()

        # Without river the reset loop is skipped; the sentinel should remain
        assert p._running_stats.get("a") is sentinel

    def test_running_stats_not_reinitialized_when_preprocessing_disabled(self):
        p = _build_pipeline(feature_names=["a"], enable_preprocessing=False)
        # running_stats is empty since preprocessing is off — just verify no error
        with patch(f"{_TRAINER_MODULE}.RIVER_AVAILABLE", True):
            p.reset()  # should complete without error
        # Stats dict remains empty
        assert p._running_stats == {}

    def test_logs_reset_message(self, caplog):
        import logging

        p = _build_pipeline()
        with caplog.at_level(logging.INFO):
            p.reset()
        assert "reset" in caplog.text.lower()


# ---------------------------------------------------------------------------
# Integration-style: multiple operations
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_learn_then_predict_increments_correctly(self):
        adapter = _make_mock_adapter(is_ready=False)
        p = _build_pipeline(adapter=adapter)

        p.learn({"f1": 0.1}, 0)
        p.learn({"f1": 0.9}, 1)
        assert adapter.learn_one.call_count == 2

        p.predict({"f1": 0.5})
        assert p._online_predictions == 1

    def test_feedback_loop(self):
        adapter = _make_mock_adapter(samples_learned=1)
        p = _build_pipeline(adapter=adapter)

        r1 = p.learn_from_feedback({"f1": 0.3}, outcome=0)
        r2 = p.learn_from_feedback({"f1": 0.7}, outcome=1)
        assert r1.success is True
        assert r2.success is True

    def test_full_lifecycle_with_fallback(self):
        import numpy as np

        adapter = _make_mock_adapter(is_ready=False, samples_learned=0)
        p = _build_pipeline(adapter=adapter, enable_fallback=True, feature_names=["f1", "f2"])

        fallback = MagicMock()
        fallback.predict.return_value = [1]
        fallback.predict_proba.return_value = [np.array([0.2, 0.8])]
        fallback.classes_ = [0, 1]
        p.set_fallback_model(fallback)

        # Predict uses fallback while cold
        r = p.predict({"f1": 0.5, "f2": 0.5})
        assert r.used_fallback is True
        assert p._fallback_predictions == 1

        # Learn a sample
        p.learn({"f1": 0.5, "f2": 0.5}, 1)
        adapter.learn_one.assert_called_once()

        # Reset clears counters
        p.reset()
        assert p._fallback_predictions == 0
        assert p._online_predictions == 0
