"""
Online learning registry for ACGS-2.
Handles lifecycle and singleton management with persistence hooks.

Constitutional Hash: cdd01ef066bc6cf2
"""

from enhanced_agent_bus.observability.structured_logging import get_logger

from .adapter import RiverSklearnAdapter
from .config import RIVER_N_MODELS, ModelType
from .consumer import FeedbackKafkaConsumer
from .models import ConsumerStats
from .trainer import OnlineLearningPipeline

logger = get_logger(__name__)
# Global instances (Internal)
_online_learning_adapter: RiverSklearnAdapter | None = None
_online_learning_pipeline: OnlineLearningPipeline | None = None
_feedback_kafka_consumer: FeedbackKafkaConsumer | None = None


def get_online_learning_adapter(
    model_type: ModelType = ModelType.CLASSIFIER,
    n_models: int = RIVER_N_MODELS,
    feature_names: list[str] | None = None,
    force_new: bool = False,
) -> RiverSklearnAdapter:
    """Get the global online learning adapter instance."""
    global _online_learning_adapter

    if _online_learning_adapter is None or force_new:
        _load_registry_state("adapter")
        _online_learning_adapter = RiverSklearnAdapter(
            model_type=model_type,
            n_models=n_models,
            feature_names=feature_names,
        )

    return _online_learning_adapter


def get_online_learning_pipeline(
    feature_names: list[str] | None = None,
    model_type: ModelType = ModelType.CLASSIFIER,
    force_new: bool = False,
) -> OnlineLearningPipeline:
    """Get the global online learning pipeline instance."""
    global _online_learning_pipeline

    if _online_learning_pipeline is None or force_new:
        _load_registry_state("pipeline")
        _online_learning_pipeline = OnlineLearningPipeline(
            feature_names=feature_names,
            model_type=model_type,
        )

    return _online_learning_pipeline


async def get_feedback_kafka_consumer(
    pipeline: OnlineLearningPipeline | None = None,
) -> FeedbackKafkaConsumer:
    """Get or create the global FeedbackKafkaConsumer instance."""
    global _feedback_kafka_consumer

    if _feedback_kafka_consumer is None:
        _feedback_kafka_consumer = FeedbackKafkaConsumer(pipeline=pipeline)

    return _feedback_kafka_consumer


async def start_feedback_consumer(
    pipeline: OnlineLearningPipeline | None = None,
) -> bool:
    """Start the global feedback Kafka consumer."""
    consumer = await get_feedback_kafka_consumer(pipeline)
    return await consumer.start()


async def stop_feedback_consumer() -> None:
    """Stop the global feedback Kafka consumer."""
    global _feedback_kafka_consumer

    if _feedback_kafka_consumer is not None:
        await _feedback_kafka_consumer.stop()
        _save_registry_state("consumer")
        _feedback_kafka_consumer = None


def get_consumer_stats() -> ConsumerStats | None:
    """Get statistics from the global feedback consumer."""
    if _feedback_kafka_consumer is not None:
        return _feedback_kafka_consumer.get_stats()
    return None


def _load_registry_state(component: str) -> None:
    """Hook for future persistence/versioning (In-memory only for now)."""
    # Placeholder for loading state from Redis or disk
    pass


def _save_registry_state(component: str) -> None:
    """Hook for future persistence/versioning (In-memory only for now)."""
    # Placeholder for saving state to Redis or disk
    pass
