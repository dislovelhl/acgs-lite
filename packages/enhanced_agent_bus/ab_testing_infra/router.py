from __future__ import annotations

import hashlib
import sys
import time
from datetime import UTC, datetime

from ..observability.structured_logging import get_logger
from .metrics import ABTestMetricsManager
from .model_manager import ABTestModelManager
from .models import (
    AB_TEST_CONFIDENCE_LEVEL,
    AB_TEST_MIN_IMPROVEMENT,
    AB_TEST_MIN_SAMPLES,
    AB_TEST_SPLIT,
    CANDIDATE_ALIAS,
    CHAMPION_ALIAS,
    MODEL_REGISTRY_NAME,
    CohortMetrics,
    CohortType,
    ComparisonResult,
    FeatureData,
    MetricsComparison,
    PredictionResult,
    PromotionResult,
    PromotionStatus,
    RoutingResult,
)

logger = get_logger(__name__)
_module = sys.modules.get(__name__)
if _module is not None:
    sys.modules.setdefault("enhanced_agent_bus.ab_testing_infra.router", _module)


class ABTestRouter:
    def __init__(
        self,
        split_ratio: float | None = None,
        candidate_split: float | None = None,
        min_samples: int = AB_TEST_MIN_SAMPLES,
        confidence_level: float = AB_TEST_CONFIDENCE_LEVEL,
        min_improvement: float = AB_TEST_MIN_IMPROVEMENT,
        champion_alias: str = CHAMPION_ALIAS,
        candidate_alias: str = CANDIDATE_ALIAS,
        model_registry_name: str = MODEL_REGISTRY_NAME,
    ) -> None:
        split = split_ratio if split_ratio is not None else candidate_split
        split = AB_TEST_SPLIT if split is None else split
        if not 0 <= split <= 1:
            raise ValueError("candidate_split must be between 0 and 1")
        self._candidate_split = split
        self.min_samples = min_samples
        self.confidence_level = confidence_level
        self.min_improvement = min_improvement
        self.champion_alias = champion_alias
        self.candidate_alias = candidate_alias
        self.ab_test_active = True
        self.model_manager = ABTestModelManager(
            champion_alias, candidate_alias, model_registry_name
        )
        self.metrics_manager = ABTestMetricsManager(split, min_samples, confidence_level)
        self._request_cohorts: dict[str, CohortType] = {}
        self._version_manager_mock = object()
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        if self.model_manager.is_ready():
            return
        if not self.model_manager.load_models():
            logger.warning("A/B test models not ready")

    @property
    def split_ratio(self) -> float:
        return self._candidate_split

    @split_ratio.setter
    def split_ratio(self, value: float) -> None:
        self._candidate_split = value
        self.metrics_manager.split_ratio = value

    @property
    def candidate_split(self) -> float:
        return self._candidate_split

    @candidate_split.setter
    def candidate_split(self, value: float) -> None:
        self.split_ratio = value

    @property
    def champion_model(self):
        return self.model_manager.champion_model

    @champion_model.setter
    def champion_model(self, value) -> None:
        self.model_manager.champion_model = value

    @property
    def candidate_model(self):
        return self.model_manager.candidate_model

    @candidate_model.setter
    def candidate_model(self, value) -> None:
        self.model_manager.candidate_model = value

    @property
    def champion_version(self):
        return self.model_manager.champion_version

    @champion_version.setter
    def champion_version(self, value) -> None:
        self.model_manager.champion_version = value

    @property
    def candidate_version(self):
        return self.model_manager.candidate_version

    @candidate_version.setter
    def candidate_version(self, value) -> None:
        self.model_manager.candidate_version = value

    @property
    def _champion_metrics(self) -> CohortMetrics:
        return self.metrics_manager.champion_metrics

    @_champion_metrics.setter
    def _champion_metrics(self, value: CohortMetrics) -> None:
        self.metrics_manager.champion_metrics = value

    @property
    def _candidate_metrics(self) -> CohortMetrics:
        return self.metrics_manager.candidate_metrics

    @_candidate_metrics.setter
    def _candidate_metrics(self, value: CohortMetrics) -> None:
        self.metrics_manager.candidate_metrics = value

    def set_champion_model(self, model, version=None) -> None:
        self.model_manager.set_champion_model(model, version)

    def set_candidate_model(self, model, version=None) -> None:
        self.model_manager.set_candidate_model(model, version)

    def set_ab_test_active(self, active: bool) -> None:
        self.ab_test_active = active

    def _compute_hash_value(self, request_id: str) -> float:
        expected_int = int(hashlib.sha256(request_id.encode()).hexdigest(), 16)
        return (expected_int % 10000) / 10000.0

    def route(self, request_id: str) -> RoutingResult:
        cohort = CohortType.CHAMPION
        if self.ab_test_active and self._compute_hash_value(request_id) < self.candidate_split:
            cohort = CohortType.CANDIDATE
        self._request_cohorts[request_id] = cohort
        version = (
            self.candidate_version if cohort == CohortType.CANDIDATE else self.champion_version
        )
        return RoutingResult(cohort=cohort, request_id=request_id, model_version=version)

    def predict(
        self, cohort_or_routing, features: FeatureData, request_id: str = ""
    ) -> PredictionResult:
        start = time.perf_counter()
        if isinstance(cohort_or_routing, RoutingResult):
            cohort = cohort_or_routing.cohort
            rid = request_id or cohort_or_routing.request_id
            version = cohort_or_routing.model_version
        else:
            cohort = cohort_or_routing
            rid = request_id or f"req-{datetime.now(UTC).timestamp()}"
            version = (
                self.candidate_version if cohort == CohortType.CANDIDATE else self.champion_version
            )
        model = self.candidate_model if cohort == CohortType.CANDIDATE else self.champion_model
        if model is None:
            latency_ms = (time.perf_counter() - start) * 1000
            return PredictionResult(
                None,
                cohort,
                rid,
                latency_ms,
                model_version=version,
                success=False,
                error="Model not loaded",
            )
        try:
            payload = [features] if not isinstance(features, dict) else features
            if hasattr(model, "predict"):
                raw = model.predict(payload)
                prediction = raw[0] if isinstance(raw, list) else raw
            else:
                prediction = model(payload)
            latency_ms = (time.perf_counter() - start) * 1000
            return PredictionResult(
                prediction, cohort, rid, latency_ms, model_version=version, success=True
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            return PredictionResult(
                None, cohort, rid, latency_ms, model_version=version, success=False, error=str(exc)
            )

    def route_and_predict(self, request_id: str, features: FeatureData) -> PredictionResult:
        return self.predict(self.route(request_id), features)

    def record_outcome(
        self, request_id: str, predicted, actual, latency_ms: float | None = 0.0
    ) -> bool:
        cohort = self._request_cohorts.get(request_id)
        if cohort is None:
            return False
        return self.metrics_manager.record_outcome(cohort, predicted, actual, latency_ms or 0.0)

    def get_champion_metrics(self) -> CohortMetrics:
        return self.metrics_manager.get_champion_metrics()

    def get_candidate_metrics(self) -> CohortMetrics:
        return self.metrics_manager.get_candidate_metrics()

    def get_metrics_summary(self) -> dict:
        summary = self.metrics_manager.get_metrics_summary(self.ab_test_active)
        summary.update(
            {
                "candidate_split": self.candidate_split,
                "champion_version": self.champion_version,
                "candidate_version": self.candidate_version,
                "champion_alias": self.champion_alias,
                "candidate_alias": self.candidate_alias,
                "has_champion_model": self.champion_model is not None,
                "has_candidate_model": self.candidate_model is not None,
            }
        )
        return summary

    def get_traffic_distribution(self, n_requests: int = 1000) -> dict:
        return self.metrics_manager.get_traffic_distribution(n_requests)

    def compare_metrics(self) -> MetricsComparison:
        return self.metrics_manager.compare_metrics()

    def promote_candidate(self, force: bool = False) -> PromotionResult:
        comparison = self.compare_metrics()
        if getattr(self, "_version_manager_mock", object()) is None:
            return PromotionResult(
                PromotionStatus.ERROR,
                False,
                error_message="Version manager unavailable",
                comparison=comparison,
            )
        if force and self.candidate_model is None:
            return PromotionResult(
                PromotionStatus.ERROR,
                False,
                error_message="Candidate model unavailable",
                comparison=comparison,
            )
        if not force and comparison.result == ComparisonResult.INSUFFICIENT_DATA:
            return PromotionResult(
                PromotionStatus.NOT_READY,
                False,
                error_message="Insufficient data",
                comparison=comparison,
            )
        if not force and not comparison.candidate_is_better:
            return PromotionResult(
                PromotionStatus.BLOCKED,
                False,
                error_message="Candidate is not better",
                comparison=comparison,
            )
        previous = self.champion_version
        self.champion_model = self.candidate_model
        self.champion_version = self.candidate_version
        self.candidate_model = None
        self.candidate_version = None
        self.metrics_manager.reset_metrics()
        return PromotionResult(
            PromotionStatus.PROMOTED,
            True,
            previous_champion_version=previous,
            new_champion_version=self.champion_version,
            promoted_at=datetime.now(UTC),
            comparison=comparison,
        )
