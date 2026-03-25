"""
ACGS-2 Online Learning Module (Facade)
Constitutional Hash: 608508a9bd224290

Incremental learning using River with sklearn compatibility.
Delegates to specialized modules in .online_learning_infra.
"""

from enhanced_agent_bus.online_learning_infra.adapter import (
    RIVER_AVAILABLE,
    RiverSklearnAdapter,
)
from enhanced_agent_bus.online_learning_infra.config import (
    ENABLE_COLD_START_FALLBACK,
    KAFKA_AUTO_OFFSET_RESET,
    KAFKA_BOOTSTRAP,
    KAFKA_CONSUMER_GROUP,
    KAFKA_MAX_POLL_RECORDS,
    KAFKA_TOPIC_FEEDBACK,
    MIN_SAMPLES_FOR_PREDICTION,
    RIVER_MODEL_TYPE,
    RIVER_N_MODELS,
    RIVER_SEED,
    LearningStatus,
    ModelType,
)
from enhanced_agent_bus.online_learning_infra.consumer import FeedbackKafkaConsumer
from enhanced_agent_bus.online_learning_infra.evaluator import OnlineLearningEvaluator
from enhanced_agent_bus.online_learning_infra.models import (
    ConsumerStats,
    LearningResult,
    LearningStats,
    PipelineStats,
    PredictionResult,
)
from enhanced_agent_bus.online_learning_infra.registry import (
    get_consumer_stats,
    get_feedback_kafka_consumer,
    get_online_learning_adapter,
    get_online_learning_pipeline,
    start_feedback_consumer,
    stop_feedback_consumer,
)
from enhanced_agent_bus.online_learning_infra.trainer import OnlineLearningPipeline

# Optional availability flags (backward compatibility)
NUMPY_AVAILABLE = True
KAFKA_AVAILABLE = True


# Helper for direct feedback learning (delegates to singleton pipeline)
def learn_from_feedback_event(
    features: dict, outcome: float | None = None, decision_id: str | None = None
) -> LearningResult:
    """Convenience function to learn from a feedback event using the global pipeline."""
    pipeline = get_online_learning_pipeline()
    return pipeline.learn_from_feedback(features, outcome, decision_id)


__all__ = [
    "ENABLE_COLD_START_FALLBACK",
    "KAFKA_AUTO_OFFSET_RESET",
    "KAFKA_AVAILABLE",
    "KAFKA_BOOTSTRAP",
    "KAFKA_CONSUMER_GROUP",
    "KAFKA_MAX_POLL_RECORDS",
    "KAFKA_TOPIC_FEEDBACK",
    "MIN_SAMPLES_FOR_PREDICTION",
    "NUMPY_AVAILABLE",
    "RIVER_AVAILABLE",
    "RIVER_MODEL_TYPE",
    "RIVER_N_MODELS",
    "RIVER_SEED",
    "ConsumerStats",
    "FeedbackKafkaConsumer",
    "LearningResult",
    "LearningStats",
    "LearningStatus",
    "ModelType",
    "OnlineLearningEvaluator",
    "OnlineLearningPipeline",
    "PipelineStats",
    "PredictionResult",
    "RiverSklearnAdapter",
    "get_consumer_stats",
    "get_feedback_kafka_consumer",
    "get_online_learning_adapter",
    "get_online_learning_pipeline",
    "learn_from_feedback_event",
    "start_feedback_consumer",
    "stop_feedback_consumer",
]
