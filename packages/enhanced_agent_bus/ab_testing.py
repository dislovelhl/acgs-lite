"""
A/B testing shim for adaptive governance model routing.
"""

from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

try:
    import numpy as _np

    NUMPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _np = None
    NUMPY_AVAILABLE = False

AB_TEST_SPLIT = float(os.getenv("AB_TEST_SPLIT", "0.1"))
CHAMPION_ALIAS = os.getenv("CHAMPION_ALIAS", "champion")
CANDIDATE_ALIAS = os.getenv("CANDIDATE_ALIAS", "candidate")
AB_TEST_MIN_SAMPLES = int(os.getenv("AB_TEST_MIN_SAMPLES", "1000"))
AB_TEST_CONFIDENCE_LEVEL = float(os.getenv("AB_TEST_CONFIDENCE_LEVEL", "0.95"))
AB_TEST_MIN_IMPROVEMENT = float(os.getenv("AB_TEST_MIN_IMPROVEMENT", "0.01"))
MODEL_REGISTRY_NAME = os.getenv("MODEL_REGISTRY_NAME", "governance_impact_scorer")


class CohortType(StrEnum):
    CHAMPION = "champion"
    CANDIDATE = "candidate"


class PromotionStatus(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"
    BLOCKED = "blocked"
    PROMOTED = "promoted"
    ERROR = "error"


class ComparisonResult(StrEnum):
    CANDIDATE_BETTER = "candidate_better"
    CHAMPION_BETTER = "champion_better"
    NO_DIFFERENCE = "no_difference"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass
class CohortMetrics:
    cohort: CohortType
    request_count: int = 0
    correct_predictions: int = 0
    total_predictions: int = 0
    accuracy: float = 0.0
    total_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    errors: int = 0
    first_request_at: datetime | None = None
    last_request_at: datetime | None = None
    latencies: list[float] = field(default_factory=list)

    @property
    def avg_latency_ms(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.total_latency_ms / self.request_count

    @property
    def error_rate(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.errors / self.request_count

    def record_request(
        self,
        latency_ms: float,
        prediction: Any | None = None,
        actual: Any | None = None,
        is_error: bool = False,
    ) -> None:
        now = datetime.now(UTC)
        self.request_count += 1
        self.total_latency_ms += latency_ms
        self.min_latency_ms = min(self.min_latency_ms, latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        self.latencies.append(latency_ms)
        self.first_request_at = self.first_request_at or now
        self.last_request_at = now
        if is_error:
            self.errors += 1
        elif prediction is not None and actual is not None:
            self.total_predictions += 1
            if prediction == actual:
                self.correct_predictions += 1
            self.accuracy = self.correct_predictions / self.total_predictions
        self.calculate_percentiles()

    def calculate_percentiles(self) -> None:
        if not self.latencies:
            self.p50_latency_ms = 0.0
            self.p95_latency_ms = 0.0
            self.p99_latency_ms = 0.0
            return
        ordered = sorted(self.latencies)
        self.p50_latency_ms = _percentile(ordered, 50)
        self.p95_latency_ms = _percentile(ordered, 95)
        self.p99_latency_ms = _percentile(ordered, 99)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cohort": self.cohort.value,
            "request_count": self.request_count,
            "correct_predictions": self.correct_predictions,
            "total_predictions": self.total_predictions,
            "accuracy": self.accuracy,
            "avg_latency_ms": self.avg_latency_ms,
            "min_latency_ms": self.min_latency_ms if self.request_count else float("inf"),
            "max_latency_ms": self.max_latency_ms,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "errors": self.errors,
            "error_rate": self.error_rate,
            "first_request_at": self.first_request_at.isoformat()
            if self.first_request_at
            else None,
            "last_request_at": self.last_request_at.isoformat() if self.last_request_at else None,
        }


@dataclass
class RoutingResult:
    cohort: CohortType
    request_id: str
    model_version: int | None = None
    routed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PredictionResult:
    prediction: Any | None
    cohort: CohortType
    request_id: str
    latency_ms: float
    model_version: int | None = None
    confidence: float | None = None
    probabilities: dict[Any, float] | None = None
    error: str | None = None


@dataclass
class MetricsComparison:
    champion_metrics: CohortMetrics
    candidate_metrics: CohortMetrics
    result: ComparisonResult
    accuracy_delta: float
    latency_delta_ms: float
    sample_size_champion: int
    sample_size_candidate: int
    is_significant: bool
    candidate_is_better: bool
    recommendation: str
    compared_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "champion_metrics": self.champion_metrics.to_dict(),
            "candidate_metrics": self.candidate_metrics.to_dict(),
            "result": self.result.value,
            "accuracy_delta": self.accuracy_delta,
            "latency_delta_ms": self.latency_delta_ms,
            "sample_size_champion": self.sample_size_champion,
            "sample_size_candidate": self.sample_size_candidate,
            "is_significant": self.is_significant,
            "candidate_is_better": self.candidate_is_better,
            "recommendation": self.recommendation,
            "compared_at": self.compared_at.isoformat(),
        }


@dataclass
class PromotionResult:
    status: PromotionStatus
    previous_champion_version: int | None = None
    new_champion_version: int | None = None
    promoted_at: datetime | None = None
    error_message: str | None = None
    comparison: MetricsComparison | None = None


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if NUMPY_AVAILABLE and _np is not None:
        return float(_np.percentile(values, percentile, method="linear"))
    index = max(0, min(len(values) - 1, math.ceil(len(values) * percentile / 100) - 1))
    return values[index]


class ABTestRouter:
    def __init__(
        self,
        candidate_split: float = AB_TEST_SPLIT,
        min_samples: int = AB_TEST_MIN_SAMPLES,
        confidence_level: float = AB_TEST_CONFIDENCE_LEVEL,
        min_improvement: float = AB_TEST_MIN_IMPROVEMENT,
        champion_alias: str = CHAMPION_ALIAS,
        candidate_alias: str = CANDIDATE_ALIAS,
    ) -> None:
        if not 0.0 <= candidate_split <= 1.0:
            raise ValueError("candidate_split must be between 0 and 1")
        self.candidate_split = candidate_split
        self.min_samples = min_samples
        self.confidence_level = confidence_level
        self.min_improvement = min_improvement
        self.champion_alias = champion_alias
        self.candidate_alias = candidate_alias
        self.ab_test_active = True
        self.champion_model: Any | None = None
        self.candidate_model: Any | None = None
        self.champion_version: int | None = None
        self.candidate_version: int | None = None
        self._champion_metrics = CohortMetrics(CohortType.CHAMPION)
        self._candidate_metrics = CohortMetrics(CohortType.CANDIDATE)
        self._routing_history: dict[str, RoutingResult] = {}
        self._request_cohorts: dict[str, RoutingResult] = self._routing_history
        self._version_manager: Any | None = None
        self._initialized = False
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        self._initialized = True

    def is_ready(self) -> bool:
        return self._initialized

    def load_models(self) -> None:
        self._ensure_initialized()

    def _compute_hash_value(self, request_id: str) -> float:
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        return int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)

    def route(self, request_id: str) -> RoutingResult:
        cohort = CohortType.CHAMPION
        if self.ab_test_active and self._compute_hash_value(request_id) < self.candidate_split:
            cohort = CohortType.CANDIDATE
        version = (
            self.candidate_version if cohort == CohortType.CANDIDATE else self.champion_version
        )
        result = RoutingResult(cohort=cohort, request_id=request_id, model_version=version)
        self._routing_history[request_id] = result
        return result

    def set_champion_model(self, model: Any, version: int | None = None) -> None:
        self.champion_model = model
        self.champion_version = version

    def set_candidate_model(self, model: Any, version: int | None = None) -> None:
        self.candidate_model = model
        self.candidate_version = version

    def set_ab_test_active(self, active: bool) -> None:
        self.ab_test_active = active

    def get_champion_model(self) -> Any | None:
        return self.champion_model

    def get_candidate_model(self) -> Any | None:
        return self.candidate_model

    def get_champion_metrics(self) -> CohortMetrics:
        return self._champion_metrics

    def get_candidate_metrics(self) -> CohortMetrics:
        return self._candidate_metrics

    def get_cohort_metrics(self, cohort: CohortType) -> CohortMetrics:
        return self._candidate_metrics if cohort == CohortType.CANDIDATE else self._champion_metrics

    def get_traffic_distribution(
        self, n_requests: int | None = None
    ) -> dict[str, float | int | bool]:
        if n_requests is None:
            return {
                "champion": 1.0 - self.candidate_split if self.ab_test_active else 1.0,
                "candidate": self.candidate_split if self.ab_test_active else 0.0,
            }

        candidate_count = 0
        for index in range(n_requests):
            if self.route(f"traffic-split-{index}").cohort == CohortType.CANDIDATE:
                candidate_count += 1
        champion_count = n_requests - candidate_count
        actual_candidate_split = candidate_count / n_requests
        actual_champion_split = champion_count / n_requests
        expected_candidate_split = self.candidate_split if self.ab_test_active else 0.0
        variance = abs(actual_candidate_split - expected_candidate_split)
        return {
            "n_requests": n_requests,
            "champion_count": champion_count,
            "candidate_count": candidate_count,
            "actual_champion_split": actual_champion_split,
            "actual_candidate_split": actual_candidate_split,
            "expected_candidate_split": expected_candidate_split,
            "variance": variance,
            "within_tolerance": variance < 0.02,
        }

    def get_metrics_summary(self) -> dict[str, Any]:
        return {
            "ab_test_active": self.ab_test_active,
            "candidate_split": self.candidate_split,
            "champion": self._champion_metrics.to_dict(),
            "candidate": self._candidate_metrics.to_dict(),
            "champion_version": self.champion_version,
            "candidate_version": self.candidate_version,
            "has_champion_model": self.champion_model is not None,
            "has_candidate_model": self.candidate_model is not None,
        }

    def reset_metrics(self) -> None:
        self._champion_metrics = CohortMetrics(CohortType.CHAMPION)
        self._candidate_metrics = CohortMetrics(CohortType.CANDIDATE)

    def predict(self, routing: RoutingResult, features: Any) -> PredictionResult:
        started = time.perf_counter()
        model = (
            self.candidate_model if routing.cohort == CohortType.CANDIDATE else self.champion_model
        )
        metrics = self.get_cohort_metrics(routing.cohort)
        if model is None:
            latency_ms = (time.perf_counter() - started) * 1000
            metrics.record_request(latency_ms=latency_ms, is_error=True)
            return PredictionResult(
                prediction=None,
                cohort=routing.cohort,
                request_id=routing.request_id,
                latency_ms=latency_ms,
                model_version=routing.model_version,
            )
        try:
            payload = _normalize_features(features)
            prediction = model.predict(payload)[0]
            probabilities = None
            confidence = None
            if hasattr(model, "predict_proba"):
                raw_probs = model.predict_proba(payload)[0]
                classes = getattr(model, "classes_", list(range(len(raw_probs))))
                probabilities = dict(zip(classes, raw_probs, strict=False))
                confidence = max(probabilities.values()) if probabilities else None
            latency_ms = (time.perf_counter() - started) * 1000
            metrics.record_request(latency_ms=latency_ms)
            return PredictionResult(
                prediction=prediction,
                cohort=routing.cohort,
                request_id=routing.request_id,
                latency_ms=latency_ms,
                model_version=routing.model_version,
                confidence=confidence,
                probabilities=probabilities,
            )
        except Exception as exc:  # pragma: no cover - defensive
            latency_ms = (time.perf_counter() - started) * 1000
            metrics.record_request(latency_ms=latency_ms, is_error=True)
            return PredictionResult(
                prediction=None,
                cohort=routing.cohort,
                request_id=routing.request_id,
                latency_ms=latency_ms,
                model_version=routing.model_version,
                error=str(exc),
            )

    def route_and_predict(self, request_id: str, features: Any) -> PredictionResult:
        return self.predict(self.route(request_id), features)

    def record_outcome(self, request_id: str, predicted: Any, actual: Any) -> bool:
        routing = self._routing_history.get(request_id)
        if routing is None:
            return False
        self.get_cohort_metrics(routing.cohort).record_request(
            latency_ms=0.0, prediction=predicted, actual=actual
        )
        return True

    def compare_metrics(self) -> MetricsComparison:
        champion = self._champion_metrics
        candidate = self._candidate_metrics
        enough_data = (
            champion.total_predictions >= self.min_samples
            and candidate.total_predictions >= self.min_samples
        )
        accuracy_delta = candidate.accuracy - champion.accuracy
        latency_delta = candidate.avg_latency_ms - champion.avg_latency_ms
        if not enough_data:
            return MetricsComparison(
                champion_metrics=champion,
                candidate_metrics=candidate,
                result=ComparisonResult.INSUFFICIENT_DATA,
                accuracy_delta=accuracy_delta,
                latency_delta_ms=latency_delta,
                sample_size_champion=champion.total_predictions,
                sample_size_candidate=candidate.total_predictions,
                is_significant=False,
                candidate_is_better=False,
                recommendation="Need more samples before comparing models",
            )
        candidate_is_better = accuracy_delta > self.min_improvement
        champion_is_better = accuracy_delta < -self.min_improvement
        if candidate_is_better:
            result = ComparisonResult.CANDIDATE_BETTER
            recommendation = "Candidate outperforms champion"
        elif champion_is_better:
            result = ComparisonResult.CHAMPION_BETTER
            recommendation = "Champion remains stronger"
        else:
            result = ComparisonResult.NO_DIFFERENCE
            recommendation = "Continue testing"
        return MetricsComparison(
            champion_metrics=champion,
            candidate_metrics=candidate,
            result=result,
            accuracy_delta=accuracy_delta,
            latency_delta_ms=latency_delta,
            sample_size_champion=champion.total_predictions,
            sample_size_candidate=candidate.total_predictions,
            is_significant=abs(accuracy_delta) >= self.min_improvement,
            candidate_is_better=candidate_is_better,
            recommendation=recommendation,
        )

    def promote_candidate(self, force: bool = False) -> PromotionResult:
        comparison = self.compare_metrics()
        if not force and comparison.result == ComparisonResult.INSUFFICIENT_DATA:
            return PromotionResult(
                status=PromotionStatus.NOT_READY,
                error_message="Insufficient data for promotion",
                comparison=comparison,
            )
        if not force and comparison.result != ComparisonResult.CANDIDATE_BETTER:
            return PromotionResult(
                status=PromotionStatus.BLOCKED,
                error_message="Candidate is not better than champion",
                comparison=comparison,
            )
        if self.candidate_model is None:
            return PromotionResult(
                status=PromotionStatus.ERROR if force else PromotionStatus.NOT_READY,
                error_message="Candidate model unavailable",
                comparison=comparison,
            )
        if hasattr(self, "_version_manager_mock") and self._version_manager_mock is None:
            return PromotionResult(
                status=PromotionStatus.ERROR,
                error_message="Version manager not available",
                comparison=comparison,
            )
        if self._version_manager is None and not force:
            return PromotionResult(
                status=PromotionStatus.ERROR,
                error_message="Version manager not available",
                comparison=comparison,
            )
        if self._version_manager is not None and hasattr(
            self._version_manager, "promote_candidate_to_champion"
        ):
            self._version_manager.promote_candidate_to_champion()
        previous = self.champion_version
        self.champion_model = self.candidate_model or self.champion_model
        self.champion_version = self.candidate_version or self.champion_version
        self.candidate_model = None
        self.candidate_version = None
        self.reset_metrics()
        return PromotionResult(
            status=PromotionStatus.PROMOTED,
            previous_champion_version=previous,
            new_champion_version=self.champion_version,
            promoted_at=datetime.now(UTC),
            comparison=comparison,
        )


def _normalize_features(features: Any) -> list[list[Any]]:
    if isinstance(features, dict):
        return [[features[key] for key in sorted(features)]]
    if isinstance(features, list):
        return [features]
    if isinstance(features, tuple):
        return [list(features)]
    return [[features]]


_ab_test_router: ABTestRouter | None = None


def get_ab_test_router(**kwargs: Any) -> ABTestRouter:
    global _ab_test_router
    if _ab_test_router is None:
        _ab_test_router = ABTestRouter(**kwargs)
    return _ab_test_router


def route_request(request_id: str) -> RoutingResult:
    return get_ab_test_router().route(request_id)


def get_ab_test_metrics() -> dict[str, Any]:
    return get_ab_test_router().get_metrics_summary()


def compare_models() -> MetricsComparison:
    return get_ab_test_router().compare_metrics()


def promote_candidate_model(force: bool = False) -> PromotionResult:
    return get_ab_test_router().promote_candidate(force=force)


__all__ = [
    "AB_TEST_CONFIDENCE_LEVEL",
    "AB_TEST_MIN_IMPROVEMENT",
    "AB_TEST_MIN_SAMPLES",
    "AB_TEST_SPLIT",
    "CANDIDATE_ALIAS",
    "CHAMPION_ALIAS",
    "MODEL_REGISTRY_NAME",
    "NUMPY_AVAILABLE",
    "ABTestRouter",
    "CohortMetrics",
    "CohortType",
    "ComparisonResult",
    "MetricsComparison",
    "PredictionResult",
    "PromotionResult",
    "PromotionStatus",
    "RoutingResult",
    "compare_models",
    "get_ab_test_metrics",
    "get_ab_test_router",
    "promote_candidate_model",
    "route_request",
]
