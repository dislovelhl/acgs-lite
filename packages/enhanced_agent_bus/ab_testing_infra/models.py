from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..ab_testing import (
    AB_TEST_CONFIDENCE_LEVEL,
    AB_TEST_MIN_IMPROVEMENT,
    AB_TEST_MIN_SAMPLES,
    AB_TEST_SPLIT,
    CANDIDATE_ALIAS,
    CHAMPION_ALIAS,
    MODEL_REGISTRY_NAME,
    CohortType,
    ComparisonResult,
    PromotionStatus,
)

FeatureData = list[float] | tuple[float, ...] | dict[str, float]


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
    errors: int = 0

    @property
    def avg_latency(self) -> float:
        return 0.0 if self.request_count == 0 else self.total_latency_ms / self.request_count

    def record_request(
        self,
        latency_ms: float,
        prediction: Any | None = None,
        actual: Any | None = None,
        is_error: bool = False,
    ) -> None:
        self.request_count += 1
        self.total_latency_ms += latency_ms
        self.min_latency_ms = min(self.min_latency_ms, latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        if is_error:
            self.errors += 1
        else:
            self.total_predictions += 1
            if prediction == actual:
                self.correct_predictions += 1
            self.accuracy = (
                self.correct_predictions / self.total_predictions
                if self.total_predictions > 0
                else 0.0
            )


@dataclass
class RoutingResult:
    cohort: CohortType
    request_id: str
    model_version: Any | None = None
    routed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PredictionResult:
    prediction: Any | None
    cohort: CohortType
    request_id: str
    latency_ms: float
    model_version: Any | None = None
    success: bool = True
    error: str | None = None


@dataclass
class MetricsComparison:
    result: ComparisonResult
    champion_accuracy: float
    candidate_accuracy: float
    improvement: float
    accuracy_delta: float
    latency_delta_ms: float
    sample_size_champion: int
    sample_size_candidate: int
    is_significant: bool
    candidate_is_better: bool
    recommendation: str


@dataclass
class PromotionResult:
    status: PromotionStatus
    success: bool
    previous_champion_version: Any | None = None
    new_champion_version: Any | None = None
    promoted_at: datetime | None = None
    error_message: str | None = None
    comparison: MetricsComparison | None = None
