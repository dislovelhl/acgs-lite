from __future__ import annotations

import math

from .models import CohortMetrics, CohortType, ComparisonResult, MetricsComparison


class ABTestMetricsManager:
    def __init__(self, split_ratio: float, min_samples: int, confidence_level: float) -> None:
        self.split_ratio = split_ratio
        self.min_samples = min_samples
        self.confidence_level = confidence_level
        self.champion_metrics = CohortMetrics(cohort=CohortType.CHAMPION)
        self.candidate_metrics = CohortMetrics(cohort=CohortType.CANDIDATE)

    def record_outcome(self, cohort: CohortType, predicted, actual, latency_ms: float) -> bool:
        self.get_cohort_metrics(cohort).record_request(
            latency_ms, prediction=predicted, actual=actual
        )
        return True

    def get_champion_metrics(self) -> CohortMetrics:
        return self.champion_metrics

    def get_candidate_metrics(self) -> CohortMetrics:
        return self.candidate_metrics

    def get_cohort_metrics(self, cohort: CohortType) -> CohortMetrics:
        return self.candidate_metrics if cohort == CohortType.CANDIDATE else self.champion_metrics

    def _check_significance(self, p1: float, p2: float) -> bool:
        n1 = self.champion_metrics.request_count
        n2 = self.candidate_metrics.request_count
        if n1 < 30 or n2 < 30:
            return False
        if n1 == 0 or n2 == 0:
            return False
        p_combined = ((p1 * n1) + (p2 * n2)) / (n1 + n2)
        if p_combined in {0.0, 1.0}:
            return abs(p1 - p2) > 0.01
        se = math.sqrt(p_combined * (1 - p_combined) * ((1 / n1) + (1 / n2)))
        if se == 0:
            return abs(p1 - p2) > 0.01
        z_score = abs(p2 - p1) / se
        return z_score >= 1.96

    def compare_metrics(self) -> MetricsComparison:
        p1 = self.champion_metrics.accuracy if self.champion_metrics.request_count else 0.0
        p2 = self.candidate_metrics.accuracy if self.candidate_metrics.request_count else 0.0
        improvement = p2 - p1
        enough = (
            self.champion_metrics.request_count >= self.min_samples
            and self.candidate_metrics.request_count >= self.min_samples
        )
        is_significant = self._check_significance(p1, p2) if enough else False
        candidate_is_better = is_significant and improvement > 0.01
        if not enough:
            result = ComparisonResult.INSUFFICIENT_DATA
            recommendation = "Need more samples"
        elif candidate_is_better:
            result = ComparisonResult.CANDIDATE_BETTER
            recommendation = "Promote candidate"
        elif is_significant and improvement < -0.01:
            result = ComparisonResult.CHAMPION_BETTER
            recommendation = "Keep champion"
        else:
            result = ComparisonResult.NO_DIFFERENCE
            recommendation = "Keep champion"
        return MetricsComparison(
            result=result,
            champion_accuracy=p1,
            candidate_accuracy=p2,
            improvement=improvement,
            accuracy_delta=improvement,
            latency_delta_ms=self.candidate_metrics.avg_latency - self.champion_metrics.avg_latency,
            sample_size_champion=self.champion_metrics.request_count,
            sample_size_candidate=self.candidate_metrics.request_count,
            is_significant=is_significant,
            candidate_is_better=candidate_is_better,
            recommendation=recommendation,
        )

    def get_metrics_summary(self, ab_test_active: bool = True) -> dict:
        comparison = self.compare_metrics()
        return {
            "ab_test_active": ab_test_active,
            "champion": {
                "accuracy": self.champion_metrics.accuracy,
                "avg_latency": self.champion_metrics.avg_latency,
            },
            "candidate": {
                "accuracy": self.candidate_metrics.accuracy,
                "avg_latency": self.candidate_metrics.avg_latency,
            },
            "comparison": {
                "improvement": comparison.improvement,
                "is_significant": comparison.is_significant,
                "has_min_samples": comparison.result != ComparisonResult.INSUFFICIENT_DATA,
                "candidate_better": comparison.candidate_is_better,
                "candidate_split": self.split_ratio,
            },
            "traffic_distribution": self.get_traffic_distribution(),
        }

    def get_traffic_distribution(self, n_requests: int = 1000) -> dict:
        if n_requests <= 0:
            return {
                "n_requests": 0,
                "champion_count": 0,
                "candidate_count": 0,
                "actual_champion_split": 0.0,
                "actual_candidate_split": 0.0,
                "expected_candidate_split": self.split_ratio,
                "variance": self.split_ratio,
                "within_tolerance": False,
            }
        candidate_count = round(n_requests * self.split_ratio)
        champion_count = n_requests - candidate_count
        actual_candidate_split = candidate_count / n_requests
        actual_champion_split = champion_count / n_requests
        variance = abs(actual_candidate_split - self.split_ratio)
        return {
            "n_requests": n_requests,
            "champion_count": champion_count,
            "candidate_count": candidate_count,
            "actual_champion_split": actual_champion_split,
            "actual_candidate_split": actual_candidate_split,
            "expected_candidate_split": self.split_ratio,
            "variance": variance,
            "within_tolerance": variance <= 0.05,
        }

    def reset_metrics(self) -> None:
        self.champion_metrics = CohortMetrics(cohort=CohortType.CHAMPION)
        self.candidate_metrics = CohortMetrics(cohort=CohortType.CANDIDATE)
