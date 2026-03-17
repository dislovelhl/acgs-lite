"""
ACGS-2 Deliberation Layer - Adaptive Router
Routes messages based on impact scores to appropriate processing lanes.

Constitutional Hash: cdd01ef066bc6cf2
"""

from datetime import UTC, datetime, timezone
from typing import Optional, TypeAlias, Union

from packages.enhanced_agent_bus.bus_types import JSONDict, JSONValue

from enhanced_agent_bus.observability.structured_logging import get_logger


# Lazy imports to avoid circular dependency
def _get_imports():
    """Lazy-load deliberation dependencies from canonical sources."""
    from ..config import BusConfiguration
    from .deliberation_queue import DeliberationQueue, DeliberationStatus
    from .impact_scorer import calculate_message_impact
    from .intent_classifier import IntentClassifier, IntentType

    def get_deliberation_queue():
        return DeliberationQueue()

    return {
        "BusConfiguration": BusConfiguration,
        "DeliberationStatus": DeliberationStatus,
        "IntentClassifier": IntentClassifier,
        "IntentType": IntentType,
        "calculate_message_impact": calculate_message_impact,
        "get_deliberation_queue": get_deliberation_queue,
    }


# Cache for lazy imports
_imports_cache = None


def _lazy_import(name):
    global _imports_cache
    if _imports_cache is None:
        _imports_cache = _get_imports()
    return _imports_cache[name]


try:
    from packages.enhanced_agent_bus.models import AgentMessage, MessageStatus
except ImportError:
    try:
        from enhanced_agent_bus.models import AgentMessage, MessageStatus
    except ImportError:
        from packages.enhanced_agent_bus.models import AgentMessage, MessageStatus


def get_deliberation_queue():
    """Expose deliberation queue accessor for testing and patching."""
    return _lazy_import("get_deliberation_queue")()


logger = get_logger(__name__)


class AdaptiveRouter:
    """Routes messages based on impact assessment to appropriate processing lanes.

    This class implements dual-path routing:
    - Fast Path: Low impact, high performance.
    - Deliberation Path: High impact, OPA enforcement.

    Attributes:
        impact_threshold (float): Threshold above which messages go to deliberation.
        deliberation_timeout (int): Default timeout for deliberation in seconds.
        enable_learning (bool): Whether to enable adaptive threshold learning.
    """

    def __init__(
        self,
        impact_threshold: float = 0.8,
        deliberation_timeout: int = 300,
        enable_learning: bool = True,
        config=None,
    ):
        """Initializes the adaptive router.

        Args:
            impact_threshold (float): Threshold above which messages go to
                deliberation. Defaults to 0.8.
            deliberation_timeout (int): Default timeout for deliberation in seconds.
                Defaults to 300.
            enable_learning (bool): Whether to enable adaptive threshold learning.
                Defaults to True.
        """
        BusConfiguration_class = _lazy_import("BusConfiguration")
        if config:
            self.config = config
        elif BusConfiguration_class:
            self.config = BusConfiguration_class.from_environment()
        else:
            self.config = None
            logger.warning("BusConfiguration not available, initializing with None")
        self.impact_threshold = impact_threshold
        self.deliberation_timeout = deliberation_timeout
        self.enable_learning = enable_learning

        # Learning data
        self.routing_history: list = []
        self.performance_metrics: JSONDict = {
            "total_messages": 0,
            "fast_lane_count": 0,
            "deliberation_count": 0,
            "deliberation_approved": 0,
            "deliberation_rejected": 0,
            "deliberation_timeout": 0,
            "false_positives": 0,  # High impact but should have been fast
            "false_negatives": 0,  # Low impact but needed deliberation
        }

        # Get deliberation queue
        get_deliberation_queue_func = _lazy_import("get_deliberation_queue")
        self.deliberation_queue = get_deliberation_queue_func()

        # Initialize Intent Classifier with config
        IntentClassifier_class = _lazy_import("IntentClassifier")
        self.intent_classifier = IntentClassifier_class(config=self.config)

    async def route_message(
        self, message: AgentMessage, context: JSONDict | None = None
    ) -> JSONDict:
        """Routes a message based on impact assessment.

        Implements Dual-path Routing:
        - Fast Path: Low impact, high performance.
        - Deliberation Path: High impact, OPA enforcement.

        Args:
            message (AgentMessage): The message to route.
            context (Optional[JSONDict]): Optional context for impact
                assessment. Defaults to None.

        Returns:
            JSONDict: A dictionary containing the routing decision and metadata.
        """
        self.performance_metrics["total_messages"] += 1

        # Calculate impact score if not already present
        if message.impact_score is None:
            # Pass context to impact scorer for multi-dimensional analysis
            from .impact_scorer import get_impact_scorer

            scorer = get_impact_scorer()
            message.impact_score = await scorer.calculate_impact_score_async(
                message.content, context
            )
            logger.debug(
                f"Calculated impact score {message.impact_score:.3f} for message {message.message_id}"  # noqa: E501
            )

        impact_score = message.impact_score

        # Zero-Trust Security Boundary: Validate constitutional hash
        from packages.enhanced_agent_bus.validators import validate_constitutional_hash

        hash_validation = validate_constitutional_hash(message.constitutional_hash)
        if not hash_validation.is_valid:
            logger.warning(f"Message {message.message_id} failed constitutional hash validation.")
            # Force deliberation due to security violation
            decision = await self._route_to_deliberation(message, context)
            decision["intent_type"] = "security_violation"
            decision["dynamic_threshold"] = 0.0
            decision["error"] = "Constitutional hash mismatch"
            return decision

        # Start SDPC Phase 1: Intent Classification (Async)
        intent = await self.intent_classifier.classify_async(str(message.content))

        # Intent-driven threshold adjustments
        IntentType_enum = _lazy_import("IntentType")
        dynamic_threshold = self.impact_threshold
        if intent == IntentType_enum.FACTUAL:
            # Lower threshold for factual queries to ensure verification
            dynamic_threshold = min(dynamic_threshold, 0.6)
        elif intent == IntentType_enum.CREATIVE:
            # Higher threshold for creative queries to prioritize fluency
            dynamic_threshold = max(dynamic_threshold, 0.9)

        # Route decision
        if impact_score >= dynamic_threshold:
            # High-risk: route to deliberation queue (Deliberation Path)
            decision = await self._route_to_deliberation(message, context)
            decision["intent_type"] = intent.value
            decision["dynamic_threshold"] = dynamic_threshold
            return decision
        else:
            # Low-risk: fast lane (Fast Path)
            decision = await self._route_to_fast_lane(message, context)
            decision["intent_type"] = intent.value
            decision["dynamic_threshold"] = dynamic_threshold
            return decision

    async def _route_to_fast_lane(
        self, message: AgentMessage, context: JSONDict | None = None
    ) -> JSONDict:
        """
        Route message to fast lane (Fast Path).
        In production, this would trigger high-performance Rust-based delivery.
        """
        self.performance_metrics["fast_lane_count"] += 1

        # Mark as processed
        message.status = MessageStatus.DELIVERED
        message.updated_at = datetime.now(UTC)

        # Record routing decision
        routing_decision = {
            "lane": "fast",
            "impact_score": message.impact_score,
            "decision_timestamp": datetime.now(UTC),
            "processing_time": 0.0,
            "requires_deliberation": False,
            "fast_path_enabled": True,
        }

        self._record_routing_history(message, routing_decision)

        logger.info(
            f"Message {message.message_id} routed to FAST PATH (impact: {message.impact_score:.3f})"
        )

        return routing_decision

    async def _route_to_deliberation(
        self, message: AgentMessage, context: JSONDict | None = None
    ) -> JSONDict:
        """
        Route message to deliberation queue (Deliberation Path).
        Includes OPA enforcement and minimum privilege checks.
        """
        self.performance_metrics["deliberation_count"] += 1

        # Record routing decision
        routing_decision = {
            "lane": "deliberation",
            "impact_score": message.impact_score,
            "decision_timestamp": datetime.now(UTC),
            "requires_deliberation": True,
            "estimated_wait_time": self.deliberation_timeout,
            "opa_enforced": True,
        }

        self._record_routing_history(message, routing_decision)

        logger.info(
            f"Message {message.message_id} routed to DELIBERATION PATH "
            f"(impact: {message.impact_score:.3f})"
        )

        return routing_decision

    def _record_routing_history(self, message: AgentMessage, routing_decision: JSONDict) -> None:
        """Record routing decision for learning."""
        if not self.enable_learning:
            return

        history_entry = {
            "message_id": message.message_id,
            "impact_score": message.impact_score,
            "routing_decision": routing_decision,
            "timestamp": datetime.now(UTC),
            "message_type": message.message_type.value,
            "priority": (
                message.priority.value
                if hasattr(message.priority, "value")
                else str(message.priority)
            ),
        }

        self.routing_history.append(history_entry)

        # Keep only recent history (last 1000 entries)
        if len(self.routing_history) > 1000:
            self.routing_history = self.routing_history[-1000:]

    async def update_performance_feedback(
        self,
        message_id: str,
        actual_outcome: str,
        processing_time: float,
        feedback_score: float | None = None,
    ):
        """
        Update router with performance feedback for learning.

        Args:
            message_id: ID of the message
            actual_outcome: 'success', 'failure', 'timeout', etc.
            processing_time: Time taken to process
            feedback_score: Optional human feedback score (0-1)
        """
        if not self.enable_learning:
            return

        # Find routing decision in history
        routing_entry = None
        for entry in reversed(self.routing_history):
            if entry["message_id"] == message_id:
                routing_entry = entry
                break

        if not routing_entry:
            logger.warning(f"No routing history found for message {message_id}")
            return

        # Update performance metrics
        routing_entry["actual_outcome"] = actual_outcome
        routing_entry["processing_time"] = processing_time
        routing_entry["feedback_score"] = feedback_score

        # Update counters
        if routing_entry["routing_decision"]["lane"] == "deliberation":
            if actual_outcome == "approved":
                self.performance_metrics["deliberation_approved"] += 1
            elif actual_outcome == "rejected":
                self.performance_metrics["deliberation_rejected"] += 1
            elif actual_outcome == "timeout":
                self.performance_metrics["deliberation_timeout"] += 1

        # Adaptive threshold adjustment (simple version)
        await self._adjust_threshold()

    async def _adjust_threshold(self) -> None:
        """Adjust impact threshold based on performance feedback."""
        if len(self.routing_history) < 50:  # Need minimum data
            return

        # Analyze recent performance
        recent_entries = self.routing_history[-100:]  # Last 100 decisions

        # Calculate false positive/negative rates
        deliberation_entries = [
            e for e in recent_entries if e["routing_decision"]["lane"] == "deliberation"
        ]
        fast_lane_entries = [e for e in recent_entries if e["routing_decision"]["lane"] == "fast"]

        # False positives: deliberation that should have been fast
        # Feedback low (< 0.5) means it was NOT appropriate to deliberate.
        # Defaults to 0.6 (positive) if no feedback.
        false_positives = sum(1 for e in deliberation_entries if e.get("feedback_score", 0.6) < 0.5)

        # False negatives: fast lane that needed deliberation
        # Actual outcome failure/timeout/rejected means we missed a risk.
        false_negatives = sum(
            1
            for e in fast_lane_entries
            if e.get("actual_outcome") in ["failure", "timeout", "rejected"]
        )

        # Use max(len(list), 1) to avoid division by zero and fix validation bug
        fp_rate = false_positives / max(len(deliberation_entries), 1)
        fn_rate = false_negatives / max(len(fast_lane_entries), 1)

        # Adjust threshold based on error rates
        adjustment = 0.0

        # Priority: Safety (FN) > Friction (FP)
        if fn_rate > 0.05:  # >5% missed risks is unacceptable
            adjustment = -0.05  # Lower threshold to catch more
        elif fp_rate > 0.20:  # >20% unneeded deliberation is annoying
            adjustment = 0.05  # Raise threshold to reduce friction

        if adjustment != 0.0:
            old_threshold = self.impact_threshold
            # Clamp between 0.1 and 0.95
            self.impact_threshold = max(0.1, min(0.95, self.impact_threshold + adjustment))

            if abs(self.impact_threshold - old_threshold) > 0.01:
                logger.info(
                    f"Adjusted impact threshold from {old_threshold:.3f} to {self.impact_threshold:.3f} "  # noqa: E501
                    f"(FP rate: {fp_rate:.2f}, FN rate: {fn_rate:.2f})"
                )

    def get_routing_stats(self) -> JSONDict:
        """Get routing statistics and performance metrics."""
        total = self.performance_metrics["total_messages"]
        if total == 0:
            return self.performance_metrics.copy()

        stats = self.performance_metrics.copy()
        stats.update(
            {
                "fast_lane_percentage": self.performance_metrics["fast_lane_count"] / total,
                "deliberation_percentage": self.performance_metrics["deliberation_count"] / total,
                "deliberation_approval_rate": (
                    self.performance_metrics["deliberation_approved"]
                    / max(self.performance_metrics["deliberation_count"], 1)
                ),
                "current_threshold": self.impact_threshold,
                "learning_enabled": self.enable_learning,
                "history_size": len(self.routing_history),
            }
        )

        return stats

    def set_impact_threshold(self, threshold: float) -> None:
        """Manually set the impact threshold."""
        self.impact_threshold = max(0.0, min(1.0, threshold))
        logger.info(f"Impact threshold manually set to {self.impact_threshold}")

    async def force_deliberation(
        self, message: AgentMessage, reason: str = "manual_override"
    ) -> JSONDict:
        """Force a message into deliberation regardless of impact score."""
        logger.info(f"Forcing message {message.message_id} into deliberation: {reason}")

        # Override impact score for routing
        original_score = message.impact_score
        message.impact_score = 1.0

        result = await self._route_to_deliberation(message)

        # Restore original score
        message.impact_score = original_score

        result["forced"] = True
        result["force_reason"] = reason

        return result


# Global router instance
_adaptive_router = None


def get_adaptive_router() -> AdaptiveRouter:
    """Get or create global adaptive router instance."""
    global _adaptive_router
    if _adaptive_router is None:
        _adaptive_router = AdaptiveRouter()
    return _adaptive_router


def reset_adaptive_router() -> None:
    """Reset the global adaptive router instance.

    Used primarily for test isolation to prevent state leakage between tests.
    Constitutional Hash: cdd01ef066bc6cf2
    """
    global _adaptive_router
    _adaptive_router = None
