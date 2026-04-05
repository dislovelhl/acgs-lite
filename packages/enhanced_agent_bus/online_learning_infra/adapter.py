"""
River-sklearn adapter for ACGS-2 Online Learning.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from enhanced_agent_bus.observability.structured_logging import get_logger

from .config import (
    MIN_SAMPLES_FOR_PREDICTION,
    RIVER_N_MODELS,
    RIVER_SEED,
    LearningStatus,
    ModelType,
)
from .models import LearningResult, LearningStats

if TYPE_CHECKING:
    import numpy.typing as npt

# Optional numpy support
try:
    import numpy as np_module

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np_module = None

# Optional River support
try:
    from river import forest as river_forest
    from river import metrics as river_metrics

    RIVER_AVAILABLE = True
except ImportError:
    RIVER_AVAILABLE = False
    river_forest = None
    river_metrics = None

logger = get_logger(__name__)
ONLINE_LEARNING_BATCH_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


class RiverSklearnAdapter:
    """
    Adapter to make River models compatible with sklearn API.
    """

    def __init__(
        self,
        river_model: object | None = None,
        model_type: ModelType = ModelType.CLASSIFIER,
        n_models: int = RIVER_N_MODELS,
        seed: int = RIVER_SEED,
        feature_names: list[str] | None = None,
        use_hashing_trick: bool = False,
        n_features: int = 4096,
    ):
        self._check_dependencies()

        self.model_type = model_type
        self.n_models = n_models
        self.seed = seed
        self.feature_names = feature_names or []
        self.use_hashing_trick = use_hashing_trick
        self.n_features = n_features

        if river_model is not None:
            self.model = river_model
        else:
            self.model = self._create_default_model()

        # Statistics tracking
        self._samples_learned = 0
        self._correct_predictions = 0
        self._total_predictions = 0
        self._last_update: datetime | None = None
        self._running_accuracy = river_metrics.Accuracy() if RIVER_AVAILABLE else None
        self._feature_stats: dict[str, dict[str, float]] = {}
        self._max_feature_stats = 1000

    def learn_one(self, x: dict[object, float] | list[float] | object, y: object) -> None:
        x_dict = self._to_dict(x) if not isinstance(x, dict) else x

        # Bounded feature stats to prevent memory leak
        if len(self._feature_stats) < self._max_feature_stats:
            for k, v in x_dict.items():
                k_str = str(k)
                if k_str not in self._feature_stats:
                    self._feature_stats[k_str] = {"min": v, "max": v, "sum": v, "count": 1}
                else:
                    s = self._feature_stats[k_str]
                    s["min"] = min(s["min"], v)
                    s["max"] = max(s["max"], v)
                    s["sum"] += v
                    s["count"] += 1

        if self.model_type == ModelType.CLASSIFIER and self._running_accuracy:
            y_pred = self.model.predict_one(x_dict)
            if y_pred is not None:
                self._running_accuracy.update(y, y_pred)
                if y_pred == y:
                    self._correct_predictions += 1

        self.model.learn_one(x_dict, y)
        self._samples_learned += 1
        self._last_update = datetime.now(UTC)

    def learn_batch(
        self,
        X: npt.NDArray[object] | list[list[float]],
        y: npt.NDArray[object] | list[object],
    ) -> LearningResult:
        try:
            samples_learned = 0
            for x_row, y_val in zip(X, y, strict=False):
                self.learn_one(x_row, y_val)
                samples_learned += 1

            return LearningResult(
                success=True,
                samples_learned=samples_learned,
                total_samples=self._samples_learned,
            )
        except ONLINE_LEARNING_BATCH_ERRORS as e:
            logger.error(f"Batch learning failed: {e}")
            return LearningResult(
                success=False,
                samples_learned=0,
                total_samples=self._samples_learned,
                error_message=str(e),
            )

    def _to_dict(self, x: object) -> dict[object, float]:
        if isinstance(x, dict):
            if not self.use_hashing_trick:
                return x

            # OPTIMIZATION: Implement Hashing Trick (Feature Hashing)
            # Map arbitrary feature names into a fixed-size numeric space
            # Prevents memory explosion when encountering thousands of unique keys
            hashed_x: dict[int, float] = {}
            for k, v in x.items():
                h = hash(str(k)) % self.n_features
                hashed_x[h] = hashed_x.get(h, 0.0) + float(v)
            return hashed_x

        if self.feature_names and len(self.feature_names) == len(x):
            if self.use_hashing_trick:
                hashed_x = {}
                for name, val in zip(self.feature_names, x, strict=True):
                    h = hash(name) % self.n_features
                    hashed_x[h] = hashed_x.get(h, 0.0) + float(val)
                return hashed_x
            return {name: float(val) for name, val in zip(self.feature_names, x, strict=True)}
        else:
            if self.use_hashing_trick:
                hashed_x = {}
                for i, val in enumerate(x):
                    h = i % self.n_features
                    hashed_x[h] = hashed_x.get(h, 0.0) + float(val)
                return hashed_x
            return {i: float(val) for i, val in enumerate(x)}  # type: ignore[return-value]

    def get_stats(self) -> LearningStats:
        if self._samples_learned < MIN_SAMPLES_FOR_PREDICTION // 2:
            status = LearningStatus.COLD_START
        elif self._samples_learned < MIN_SAMPLES_FOR_PREDICTION:
            status = LearningStatus.WARMING_UP
        else:
            status = LearningStatus.READY

        if self._running_accuracy and self.model_type == ModelType.CLASSIFIER:
            accuracy = self._running_accuracy.get()
        elif self._total_predictions > 0:
            accuracy = self._correct_predictions / self._total_predictions
        else:
            accuracy = 0.0

        return LearningStats(
            samples_learned=self._samples_learned,
            correct_predictions=self._correct_predictions,
            total_predictions=self._total_predictions,
            accuracy=accuracy,
            last_update=self._last_update,
            status=status,
            feature_names=self.feature_names.copy(),
        )

    @property
    def is_ready(self) -> bool:
        return bool(self._samples_learned >= MIN_SAMPLES_FOR_PREDICTION)

    @property
    def samples_learned(self) -> int:
        return self._samples_learned

    @property
    def accuracy(self) -> float:
        if self._running_accuracy and self.model_type == ModelType.CLASSIFIER:
            return float(self._running_accuracy.get())
        return 0.0

    def _check_dependencies(self) -> None:
        from enhanced_agent_bus import online_learning

        if not getattr(online_learning, "RIVER_AVAILABLE", RIVER_AVAILABLE):
            raise ImportError("River is required for online learning.")
        if not getattr(online_learning, "NUMPY_AVAILABLE", NUMPY_AVAILABLE):
            raise ImportError("NumPy is required for online learning.")

    def _create_default_model(self) -> object:
        if self.model_type == ModelType.CLASSIFIER:
            return river_forest.ARFClassifier(n_models=self.n_models, seed=self.seed)
        return river_forest.ARFRegressor(n_models=self.n_models, seed=self.seed)

    def predict_one(self, x: dict[object, float] | list[float] | object) -> object:
        x_dict = self._to_dict(x) if not isinstance(x, dict) else x
        res = self.model.predict_one(x_dict)
        self._total_predictions += 1
        return res

    def predict_proba_one(
        self, x: dict[object, float] | list[float] | object
    ) -> dict[object, float]:
        if self.model_type != ModelType.CLASSIFIER:
            raise ValueError("predict_proba_one is only available for classifiers")
        x_dict = self._to_dict(x) if not isinstance(x, dict) else x
        return self.model.predict_proba_one(x_dict)  # type: ignore[no-any-return]

    def predict(self, X: npt.NDArray[object] | list[list[float]]) -> list[object]:
        return [self.predict_one(x) for x in X]

    def predict_proba(
        self, X: npt.NDArray[object] | list[list[float]]
    ) -> list[dict[object, float]]:
        return [self.predict_proba_one(x) for x in X]

    def reset(self) -> None:
        self.model = self._create_default_model()
        self._samples_learned = 0
        self._correct_predictions = 0
        self._total_predictions = 0
        self._last_update = None
        self._running_accuracy = river_metrics.Accuracy() if RIVER_AVAILABLE else None
        logger.info("Online learning model reset")
