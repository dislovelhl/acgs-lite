"""
Data Models for ACGS-2 Online Learning.

Constitutional Hash: 608508a9bd224290
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone

from .config import LearningStatus


@dataclass
class LearningStats:
    """Statistics for online learning progress."""

    samples_learned: int = 0
    correct_predictions: int = 0
    total_predictions: int = 0
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    model_type: str = ""
    last_update: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: LearningStatus = LearningStatus.COLD_START
    feature_names: list[str] = field(default_factory=list)
    metrics_history: list[dict[str, float]] = field(default_factory=list)
    feature_importance: dict[str, float] = field(default_factory=dict)

    @property
    def last_updated(self) -> datetime:
        return self.last_update

    @last_updated.setter
    def last_updated(self, value: datetime) -> None:
        self.last_update = value


@dataclass
class PredictionResult:
    """Result of an online prediction."""

    prediction: object
    confidence: float | None = None
    probabilities: dict[object, float] | None = None
    used_fallback: bool = False
    model_status: LearningStatus = LearningStatus.COLD_START
    latency_ms: float = 0.0


@dataclass
class LearningResult:
    """Result of a learning (update) operation."""

    success: bool
    samples_learned: int = 0
    total_samples: int = 0
    error_message: str | None = None
    stats: LearningStats | None = None


@dataclass
class PipelineStats:
    """Statistics for the online learning pipeline."""

    learning_stats: LearningStats = field(default_factory=LearningStats)
    total_predictions: int = 0
    online_predictions: int = 0
    fallback_predictions: int = 0
    fallback_rate: float = 0.0
    model_ready: bool = False
    has_fallback: bool = False
    preprocessing_enabled: bool = False
    total_learnings: int = 0
    successful_predictions: int = 0
    failed_predictions: int = 0
    avg_prediction_latency_ms: float = 0.0
    model_accuracy: float = 0.0
    samples_in_buffer: int = 0
    last_batch_time: datetime | None = None
    model_status: LearningStatus = LearningStatus.COLD_START

    @property
    def samples_learned(self) -> int:
        return self.learning_stats.samples_learned

    @property
    def accuracy(self) -> float:
        return self.learning_stats.accuracy

    @property
    def status(self) -> str:
        return self.learning_stats.status.value


@dataclass
class ConsumerStats:
    """Statistics for Kafka consumer."""

    messages_received: int = 0
    messages_processed: int = 0
    messages_failed: int = 0
    samples_learned: int = 0
    last_offset: int = -1
    last_message_at: datetime | None = None
    consumer_lag: int = 0
    status: str = "stopped"
    messages_consumed: int = 0
    batches_processed: int = 0
    lag: int = 0
    last_message_time: datetime | None = None
    consumer_status: str = "stopped"
