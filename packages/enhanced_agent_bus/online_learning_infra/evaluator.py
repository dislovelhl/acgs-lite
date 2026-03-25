"""
Online learning evaluator for ACGS-2.
Provides metrics and stats aggregation for the online learning pipeline.

Constitutional Hash: 608508a9bd224290
"""

from .config import LearningStatus
from .models import LearningStats, PipelineStats


class OnlineLearningEvaluator:
    """
    Evaluator for online learning metrics and system status.
    """

    @staticmethod
    def compute_pipeline_stats(
        adapter_stats: LearningStats,
        online_predictions: int,
        fallback_predictions: int,
        has_fallback: bool,
        preprocessing_enabled: bool,
    ) -> PipelineStats:
        """
        Compute comprehensive pipeline statistics.
        """
        total_predictions = fallback_predictions + online_predictions
        fallback_rate = fallback_predictions / total_predictions if total_predictions > 0 else 0.0

        return PipelineStats(
            learning_stats=adapter_stats,
            total_predictions=total_predictions,
            online_predictions=online_predictions,
            fallback_predictions=fallback_predictions,
            fallback_rate=fallback_rate,
            model_ready=adapter_stats.status == LearningStatus.READY,
            has_fallback=has_fallback,
            preprocessing_enabled=preprocessing_enabled,
        )

    @staticmethod
    def is_model_ready(samples_learned: int, min_samples: int) -> bool:
        """Check if the model has enough samples to be considered ready."""
        return samples_learned >= min_samples
