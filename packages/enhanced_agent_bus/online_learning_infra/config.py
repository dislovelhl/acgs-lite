"""
Configuration for ACGS-2 Online Learning.

Constitutional Hash: 608508a9bd224290
"""

import os
from enum import Enum

# Model configuration from environment
RIVER_MODEL_TYPE = os.getenv("RIVER_MODEL_TYPE", "classifier")
RIVER_N_MODELS = int(os.getenv("RIVER_N_MODELS", "10"))
RIVER_SEED = int(os.getenv("RIVER_SEED", "42"))
MIN_SAMPLES_FOR_PREDICTION = int(os.getenv("MIN_SAMPLES_FOR_PREDICTION", "500"))
ENABLE_COLD_START_FALLBACK = os.getenv("ENABLE_COLD_START_FALLBACK", "true").lower() == "true"
USE_HASHING_TRICK = os.getenv("USE_HASHING_TRICK", "false").lower() == "true"

# Kafka configuration from environment
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPIC_FEEDBACK = os.getenv("KAFKA_TOPIC_FEEDBACK", "governance.feedback.v1")
KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "river-learner")
KAFKA_AUTO_OFFSET_RESET = os.getenv("KAFKA_AUTO_OFFSET_RESET", "earliest")
KAFKA_MAX_POLL_RECORDS = int(os.getenv("KAFKA_MAX_POLL_RECORDS", "100"))


class ModelType(str, Enum):
    """Type of River model to use."""

    CLASSIFIER = "classifier"
    REGRESSOR = "regressor"


class LearningStatus(str, Enum):
    """Status of the online learning system."""

    COLD_START = "cold_start"  # Insufficient samples for reliable predictions
    WARMING_UP = "warming_up"  # Learning but not yet reliable
    READY = "ready"  # Sufficient samples for predictions
    ERROR = "error"  # System in error state
