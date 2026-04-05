"""
Online learning trainer/pipeline implementation for ACGS-2.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .adapter import RIVER_AVAILABLE, RiverSklearnAdapter
from .config import ENABLE_COLD_START_FALLBACK, RIVER_N_MODELS, RIVER_SEED, ModelType
from .evaluator import OnlineLearningEvaluator
from .models import LearningResult, PipelineStats, PredictionResult

if TYPE_CHECKING:
    pass

# Optional River support
try:
    from river import stats as river_stats
except ImportError:
    river_stats = None

# Optional numpy support
try:
    import numpy as np_module
except ImportError:
    np_module = None

logger = get_logger(__name__)
FALLBACK_PREDICTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)
ONLINE_LEARNING_FEEDBACK_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


class OnlineLearningPipeline:
    """
    Pipeline for online learning with preprocessing and cold start handling.
    (Acts as the primary Trainer orchestration layer)
    """

    def __init__(
        self,
        feature_names: list[str] | None = None,
        model_type: ModelType = ModelType.CLASSIFIER,
        n_models: int = RIVER_N_MODELS,
        seed: int = RIVER_SEED,
        enable_preprocessing: bool = True,
        enable_fallback: bool = ENABLE_COLD_START_FALLBACK,
    ):
        self._check_dependencies()

        self.feature_names = feature_names or []
        self.model_type = model_type
        self.enable_preprocessing = enable_preprocessing
        self.enable_fallback = enable_fallback

        self.adapter = RiverSklearnAdapter(
            model_type=model_type,
            n_models=n_models,
            seed=seed,
            feature_names=self.feature_names,
        )

        self._running_stats: JSONDict = {}
        if enable_preprocessing and RIVER_AVAILABLE:
            for name in self.feature_names:
                self._running_stats[name] = river_stats.Mean()

        self._fallback_model: object | None = None
        self._fallback_predictions = 0
        self._online_predictions = 0
        self.evaluator = OnlineLearningEvaluator()

    def _check_dependencies(self) -> None:
        if not RIVER_AVAILABLE:
            raise ImportError(
                "River is required for online learning. Install with: pip install river"
            )

    def set_fallback_model(self, model: object) -> None:
        self._fallback_model = model
        logger.info("Fallback sklearn model configured for cold start")

    def predict(
        self,
        x: dict[object, float] | list[float] | object,
    ) -> PredictionResult:
        stats = self.adapter.get_stats()
        use_fallback = (
            self.enable_fallback and not self.adapter.is_ready and self._fallback_model is not None
        )

        if use_fallback:
            try:
                x_array = self._to_array(x)
                prediction = self._fallback_model.predict([x_array])[0]

                probabilities = None
                confidence = None
                if hasattr(self._fallback_model, "predict_proba"):
                    proba = self._fallback_model.predict_proba([x_array])[0]
                    confidence = float(max(proba))
                    if hasattr(self._fallback_model, "classes_"):
                        proba_list = proba.tolist() if hasattr(proba, "tolist") else list(proba)
                        probabilities = dict(
                            zip(self._fallback_model.classes_, proba_list, strict=True)
                        )

                self._fallback_predictions += 1
                return PredictionResult(
                    prediction=prediction,
                    confidence=confidence,
                    probabilities=probabilities,
                    used_fallback=True,
                    model_status=stats.status,
                )
            except FALLBACK_PREDICTION_ERRORS as e:
                logger.warning(f"Fallback prediction failed: {e}, using online model")

        prediction = self.adapter.predict_one(x)
        probabilities = None
        confidence = None
        if self.model_type == ModelType.CLASSIFIER:
            proba_dict = self.adapter.predict_proba_one(x)
            if proba_dict:
                probabilities = proba_dict
                confidence = max(proba_dict.values()) if proba_dict else None

        self._online_predictions += 1
        return PredictionResult(
            prediction=prediction,
            confidence=confidence,
            probabilities=probabilities,
            used_fallback=False,
            model_status=stats.status,
        )

    def learn(
        self,
        x: dict[object, float] | list[float] | object,
        y: object,
    ) -> None:
        if self.enable_preprocessing and isinstance(x, dict):
            for name, value in x.items():
                if name in self._running_stats:
                    self._running_stats[name].update(value)

        self.adapter.learn_one(x, y)

    def learn_from_feedback(
        self,
        features: JSONDict | object,
        outcome: object = None,
        decision_id: str | None = None,
    ) -> LearningResult:
        if outcome is None and isinstance(features, dict) and "features" in features:
            actual_features = features.get("features", {})
            outcome = features.get("outcome") or features.get("actual_impact")
            decision_id = decision_id or features.get("decision_id")
        else:
            actual_features = features

        try:
            x_dict = {
                k: float(v) for k, v in actual_features.items() if isinstance(v, (int, float))
            }
            if outcome is None:
                raise ValueError("Outcome is required for learning")

            self.learn(x_dict, outcome)
            if decision_id:
                logger.info(f"Learned from decision {decision_id}")

            return LearningResult(
                success=True,
                samples_learned=1,
                total_samples=self.adapter.samples_learned,
            )
        except ONLINE_LEARNING_FEEDBACK_ERRORS as e:
            logger.error(f"Failed to learn from feedback: {e}")
            return LearningResult(
                success=False,
                samples_learned=0,
                total_samples=self.adapter.samples_learned,
                error_message=str(e),
            )

    def _to_array(self, x: object) -> object:
        if isinstance(x, dict):
            if self.feature_names:
                return np_module.array([x.get(name, 0.0) for name in self.feature_names])
            else:
                return np_module.array(list(x.values()))
        elif hasattr(x, "__array__"):
            return np_module.asarray(x)
        else:
            return np_module.array(x)

    def get_stats(self) -> PipelineStats:
        adapter_stats = self.adapter.get_stats()
        return self.evaluator.compute_pipeline_stats(
            adapter_stats=adapter_stats,
            online_predictions=self._online_predictions,
            fallback_predictions=self._fallback_predictions,
            has_fallback=self._fallback_model is not None,
            preprocessing_enabled=self.enable_preprocessing,
        )

    def reset(self) -> None:
        self.adapter.reset()
        self._fallback_predictions = 0
        self._online_predictions = 0

        if self.enable_preprocessing and RIVER_AVAILABLE:
            for name in self.feature_names:
                self._running_stats[name] = river_stats.Mean()

        logger.info("Online learning pipeline reset")
