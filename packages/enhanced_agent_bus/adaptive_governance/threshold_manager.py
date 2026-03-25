"""
ACGS-2 Adaptive Threshold Manager
Constitutional Hash: 608508a9bd224290

Implements adaptive threshold management with ML-based dynamic adjustment
for governance decision boundaries.

This module contains:
- AdaptiveThresholds: Self-evolving threshold manager using RandomForestRegressor
  for dynamic threshold adjustment based on feedback and performance metrics.

Key Features:
- ML-based threshold prediction using scikit-learn RandomForest
- MLflow integration for model versioning and tracking
- Adaptive learning from governance feedback
- Feature extraction from governance metrics and impact data
"""

from __future__ import annotations

import os
import sys
import time
from collections import deque
from datetime import UTC, datetime

import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.preprocessing import StandardScaler

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

# MLflow imports for model versioning
try:
    import mlflow

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    mlflow = None

# Import data models from local package
from .models import GovernanceDecision, ImpactFeatures, ImpactLevel

logger = get_logger(__name__)
MAX_TRAINING_SAMPLES = 5_000

_ADAPTIVE_THRESHOLD_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class AdaptiveThresholds:
    """ML-based dynamic threshold adjustment system."""

    # MLflow configuration
    MLFLOW_EXPERIMENT_NAME = "governance_thresholds"
    MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")

    def __init__(self, constitutional_hash: str):
        self.constitutional_hash = constitutional_hash
        self.base_thresholds = {
            ImpactLevel.NEGLIGIBLE: 0.1,
            ImpactLevel.LOW: 0.3,
            ImpactLevel.MEDIUM: 0.6,
            ImpactLevel.HIGH: 0.8,
            ImpactLevel.CRITICAL: 0.95,
        }

        # ML Models
        self.threshold_model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        self.anomaly_detector = IsolationForest(contamination=0.1, random_state=42)

        # Training data
        self.training_data: deque[JSONDict] = deque(maxlen=MAX_TRAINING_SAMPLES)
        self.feature_scaler = StandardScaler()

        # Adaptive parameters
        self.learning_rate = 0.1
        self.confidence_threshold = 0.8
        self.retraining_interval = 3600  # 1 hour

        self.last_retraining = time.time()
        self.model_trained = False

        # MLflow tracking
        self._mlflow_initialized = False
        self._mlflow_experiment_id: str | None = None
        self.model_version: int | None = None
        self._initialize_mlflow()

    def _initialize_mlflow(self) -> None:
        """Initialize MLflow tracking for training runs."""
        if not MLFLOW_AVAILABLE:
            logger.warning("MLflow not available. Training runs will not be tracked.")
            return

        # Check if we are running in tests
        if "pytest" in sys.modules:
            self._mlflow_initialized = False
            return

        try:
            mlflow.set_tracking_uri(self.MLFLOW_TRACKING_URI)

            # Create or get experiment
            experiment = mlflow.get_experiment_by_name(self.MLFLOW_EXPERIMENT_NAME)
            if experiment is None:
                self._mlflow_experiment_id = mlflow.create_experiment(
                    self.MLFLOW_EXPERIMENT_NAME,
                    tags={
                        "constitutional_hash": self.constitutional_hash,
                        "model_type": "adaptive_thresholds",
                    },
                )
            else:
                self._mlflow_experiment_id = experiment.experiment_id

            self._mlflow_initialized = True
            logger.info(
                f"MLflow initialized for experiment '{self.MLFLOW_EXPERIMENT_NAME}' "
                f"(id: {self._mlflow_experiment_id})"
            )

        except _ADAPTIVE_THRESHOLD_ERRORS as e:
            logger.warning(f"Failed to initialize MLflow tracking: {e}")
            self._mlflow_initialized = False
        except Exception as e:
            logger.warning(f"Failed to initialize MLflow tracking: {e}")
            self._mlflow_initialized = False

    def get_adaptive_threshold(self, impact_level: ImpactLevel, features: ImpactFeatures) -> float:
        """Get ML-adjusted threshold for given impact level and features."""
        if not self.model_trained:
            return self.base_thresholds[impact_level]

        try:
            # Prepare features for prediction
            feature_vector = self._extract_feature_vector(features)

            # Get ML prediction
            predicted_adjustment = self.threshold_model.predict([feature_vector])[0]

            # Apply confidence-based adjustment
            base_threshold = self.base_thresholds[impact_level]
            confidence_factor = min(features.confidence_level, 1.0)

            # Adaptive threshold with bounds checking
            adaptive_threshold = base_threshold + (predicted_adjustment * confidence_factor)
            adaptive_threshold = max(0.0, min(1.0, adaptive_threshold))

            logger.debug(
                f"Adaptive threshold for {impact_level.value}: "
                f"{base_threshold:.3f} -> {adaptive_threshold:.3f}"
            )

            return adaptive_threshold  # type: ignore[no-any-return]

        except _ADAPTIVE_THRESHOLD_ERRORS as e:
            logger.warning(f"Error in adaptive threshold calculation: {e}")
            return self.base_thresholds[impact_level]

    def update_model(
        self,
        decision: GovernanceDecision,
        outcome_success: bool,
        human_feedback: bool | None = None,
    ) -> None:
        """Update ML model with new decision outcomes."""
        try:
            feature_vector = self._extract_feature_vector(decision.features_used)

            # Calculate target adjustment based on outcomes
            base_threshold = self.base_thresholds[decision.impact_level]
            actual_threshold = decision.recommended_threshold

            # Learning signal based on success and human feedback
            if outcome_success and human_feedback is not False:
                # Positive reinforcement
                target_adjustment = actual_threshold - base_threshold
            elif not outcome_success or human_feedback is False:
                # Negative reinforcement - adjust towards safer thresholds
                target_adjustment = (base_threshold - actual_threshold) * 0.5
            else:
                # Neutral - small adjustment towards recommended
                target_adjustment = (actual_threshold - base_threshold) * 0.1

            # Store training sample
            training_sample = {
                "features": feature_vector,
                "target": target_adjustment,
                "timestamp": time.time(),
                "impact_level": decision.impact_level.value,
                "confidence": decision.confidence_score,
                "outcome_success": outcome_success,
                "human_feedback": human_feedback,
            }

            self.training_data.append(training_sample)

            # Periodic retraining
            if time.time() - self.last_retraining > self.retraining_interval:
                self._retrain_model()

        except _ADAPTIVE_THRESHOLD_ERRORS as e:
            logger.error(f"Error updating adaptive model: {e}")

    def _retrain_model(self) -> None:
        """Retrain the ML model with accumulated data and log to MLflow."""
        try:
            if len(self.training_data) < 100:  # Minimum samples for training
                return

            # Prepare training data
            recent_data = [
                d for d in self.training_data if time.time() - d["timestamp"] < 86400
            ]  # Last 24 hours

            if len(recent_data) < 50:
                return

            X = np.array([d["features"] for d in recent_data])
            y = np.array([d["target"] for d in recent_data])

            # Scale features
            X_scaled = self.feature_scaler.fit_transform(X)

            # Log training run to MLflow
            if self._mlflow_initialized and MLFLOW_AVAILABLE:
                self._log_training_run_to_mlflow(X_scaled, y, recent_data)
            else:
                # Train without MLflow logging
                self.threshold_model.fit(X_scaled, y)
                self.anomaly_detector.fit(X_scaled)

            self.model_trained = True
            self.last_retraining = time.time()

            logger.info(f"Retrained adaptive governance model with {len(recent_data)} samples")

        except _ADAPTIVE_THRESHOLD_ERRORS as e:
            logger.error(f"Error retraining adaptive model: {e}")

    def _log_training_run_to_mlflow(
        self, X_scaled: np.ndarray, y: np.ndarray, recent_data: list[JSONDict]
    ) -> None:
        """Log training run with metrics and model to MLflow."""
        try:
            run_name = f"threshold_retrain_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"

            with mlflow.start_run(
                experiment_id=self._mlflow_experiment_id,
                run_name=run_name,
            ) as run:
                # Log training parameters
                mlflow.log_params(
                    {
                        "n_estimators": self.threshold_model.n_estimators,
                        "random_state": self.threshold_model.random_state,
                        "n_jobs": self.threshold_model.n_jobs,
                        "learning_rate": self.learning_rate,
                        "confidence_threshold": self.confidence_threshold,
                        "retraining_interval": self.retraining_interval,
                        "constitutional_hash": self.constitutional_hash,
                    }
                )

                # Train model
                self.threshold_model.fit(X_scaled, y)

                # Update anomaly detector
                self.anomaly_detector.fit(X_scaled)

                # Calculate training metrics
                y_pred = self.threshold_model.predict(X_scaled)
                mse = float(np.mean((y - y_pred) ** 2))
                mae = float(np.mean(np.abs(y - y_pred)))
                r2_score = float(1 - (np.sum((y - y_pred) ** 2) / np.sum((y - np.mean(y)) ** 2)))

                # Calculate data distribution metrics
                positive_feedback = sum(1 for d in recent_data if d.get("outcome_success", False))
                human_feedback_count = sum(
                    1 for d in recent_data if d.get("human_feedback") is not None
                )

                # Log metrics
                mlflow.log_metrics(
                    {
                        "n_samples": len(recent_data),
                        "n_features": X_scaled.shape[1],
                        "mean_squared_error": mse,
                        "mean_absolute_error": mae,
                        "r2_score": r2_score,
                        "target_mean": float(np.mean(y)),
                        "target_std": float(np.std(y)),
                        "positive_feedback_rate": positive_feedback / len(recent_data),
                        "human_feedback_rate": human_feedback_count / len(recent_data),
                    }
                )

                # Log feature importance
                if hasattr(self.threshold_model, "feature_importances_"):
                    feature_names = [
                        "message_length",
                        "agent_count",
                        "tenant_complexity",
                        "temporal_mean",
                        "temporal_std",
                        "semantic_similarity",
                        "historical_precedence",
                        "resource_utilization",
                        "network_isolation",
                        "risk_score",
                        "confidence_level",
                    ]
                    for idx, importance in enumerate(self.threshold_model.feature_importances_):
                        feature_name = (
                            feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
                        )
                        mlflow.log_metric(f"importance_{feature_name}", float(importance))

                # Log the trained model
                mlflow.sklearn.log_model(
                    self.threshold_model,
                    artifact_path="threshold_model",
                    registered_model_name=None,  # Don't auto-register; use ml_versioning for that
                )

                # Log anomaly detector as artifact
                mlflow.sklearn.log_model(
                    self.anomaly_detector,
                    artifact_path="anomaly_detector",
                )

                # Store run info
                self.model_version = run.info.run_id

                logger.info(
                    f"MLflow run logged: {run.info.run_id} "
                    f"(MSE: {mse:.4f}, R2: {r2_score:.4f}, samples: {len(recent_data)})"
                )

        except _ADAPTIVE_THRESHOLD_ERRORS as e:
            logger.warning(f"Failed to log training run to MLflow: {e}")
            # Fallback to training without MLflow logging
            self.threshold_model.fit(X_scaled, y)
            self.anomaly_detector.fit(X_scaled)

        except Exception as e:
            logger.warning(f"Failed to log training run to MLflow: {e}")
            # Fallback to training without MLflow logging
            self.threshold_model.fit(X_scaled, y)
            self.anomaly_detector.fit(X_scaled)

    def _extract_feature_vector(self, features: ImpactFeatures) -> list[float]:
        """Extract numerical feature vector for ML prediction."""
        return [
            features.message_length,
            features.agent_count,
            features.tenant_complexity,
            float(np.mean(features.temporal_patterns)) if features.temporal_patterns else 0.0,
            float(np.std(features.temporal_patterns)) if features.temporal_patterns else 0.0,
            features.semantic_similarity,
            features.historical_precedence,
            features.resource_utilization,
            features.network_isolation,
            features.risk_score,
            features.confidence_level,
        ]


__all__ = ["AdaptiveThresholds"]
