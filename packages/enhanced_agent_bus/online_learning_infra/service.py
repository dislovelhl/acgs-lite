"""
Online learning service shim for ACGS-2.
Re-exports implementation from .registry for backward compatibility.

Constitutional Hash: 608508a9bd224290
"""

from .registry import (
    get_consumer_stats,
    get_feedback_kafka_consumer,
    get_online_learning_adapter,
    get_online_learning_pipeline,
    start_feedback_consumer,
    stop_feedback_consumer,
)

__all__ = [
    "get_consumer_stats",
    "get_feedback_kafka_consumer",
    "get_online_learning_adapter",
    "get_online_learning_pipeline",
    "start_feedback_consumer",
    "stop_feedback_consumer",
]
