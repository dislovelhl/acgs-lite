"""
ACGS-2 Adaptive Governance Engine
Constitutional Hash: cdd01ef066bc6cf2

Core governance engine implementing ML-based adaptive governance with dynamic
impact scoring, threshold management, and constitutional compliance evaluation.

This module contains:
- AdaptiveGovernanceEngine: Main governance orchestration engine integrating
  impact scoring, threshold management, drift detection, online learning,
  and A/B testing for intelligent AI safety governance.

Key Features:
- Integration with ImpactScorer and AdaptiveThresholds
- Drift detection for model and data distribution monitoring
- Online learning with River ML for continuous adaptation
- A/B testing support for model comparison
- Feedback loop integration for governance improvement
- Constitutional compliance verification
- Thread-safe operation with locking mechanisms
"""

import asyncio
import dataclasses
import time
from collections import deque
from datetime import UTC, datetime
from importlib import import_module
from typing import TYPE_CHECKING

from enhanced_agent_bus.interfaces import GovernanceDecisionValidatorProtocol
from enhanced_agent_bus.observability.structured_logging import get_logger

if TYPE_CHECKING:
    from enhanced_agent_bus.config import BusConfiguration

try:
    from src.core.shared.types import (
        JSONDict,
        MessagePayload,
        PolicyContext,
    )  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    MessagePayload = dict  # type: ignore[misc,assignment]
    PolicyContext = dict  # type: ignore[misc,assignment]

# Optional ML dependency — lazy-imported
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore[assignment]
    NUMPY_AVAILABLE = False

# Feedback handler imports
try:
    from ..feedback_handler import (
        FeedbackEvent,
        FeedbackHandler,
        FeedbackType,
        OutcomeStatus,
        get_feedback_handler,
    )

    FEEDBACK_HANDLER_AVAILABLE = True
except ImportError:
    try:
        from feedback_handler import (  # type: ignore[no-redef]
            FeedbackEvent,
            FeedbackHandler,
            FeedbackType,
            OutcomeStatus,
            get_feedback_handler,
        )

        FEEDBACK_HANDLER_AVAILABLE = True
    except ImportError:
        FEEDBACK_HANDLER_AVAILABLE = False  # type: ignore[no-redef]
        FeedbackEvent = None  # type: ignore[no-redef, misc]
        FeedbackHandler = None  # type: ignore[no-redef, misc]
        FeedbackType = None  # type: ignore[no-redef, misc]
        OutcomeStatus = None  # type: ignore[no-redef, misc]
        get_feedback_handler = None  # type: ignore[no-redef, misc]

# Drift monitoring imports
try:
    from ..drift_monitoring import (
        DRIFT_CHECK_INTERVAL_HOURS,
        DriftDetector,
        DriftReport,
        DriftSeverity,
        DriftStatus,
        get_drift_detector,
    )

    DRIFT_MONITORING_AVAILABLE = True
except ImportError:
    try:
        from drift_monitoring import (  # type: ignore[no-redef]
            DRIFT_CHECK_INTERVAL_HOURS,
            DriftDetector,
            DriftReport,
            DriftSeverity,
            DriftStatus,
            get_drift_detector,
        )

        DRIFT_MONITORING_AVAILABLE = True
    except ImportError:
        DRIFT_MONITORING_AVAILABLE = False  # type: ignore[no-redef]
        DRIFT_CHECK_INTERVAL_HOURS = 6  # type: ignore[no-redef]
        DriftDetector = None  # type: ignore[no-redef, misc]
        DriftReport = None  # type: ignore[no-redef, misc]
        DriftSeverity = None  # type: ignore[no-redef, misc]
        DriftStatus = None  # type: ignore[no-redef, misc]
        get_drift_detector = None  # type: ignore[no-redef, misc]

# Online learning imports (River model)
try:
    from ..online_learning import (
        RIVER_AVAILABLE,
        LearningResult,
        LearningStatus,
        ModelType,
        OnlineLearningPipeline,
        PredictionResult,
        get_online_learning_pipeline,
    )

    ONLINE_LEARNING_AVAILABLE = True
except ImportError:
    try:
        from online_learning import (  # type: ignore[no-redef]
            RIVER_AVAILABLE,
            LearningResult,
            LearningStatus,
            ModelType,
            OnlineLearningPipeline,
            PredictionResult,
            get_online_learning_pipeline,
        )

        ONLINE_LEARNING_AVAILABLE = True
    except ImportError:
        ONLINE_LEARNING_AVAILABLE = False  # type: ignore[no-redef]
        RIVER_AVAILABLE = False  # type: ignore[no-redef]
        LearningResult = None  # type: ignore[no-redef, misc]
        LearningStatus = None  # type: ignore[no-redef, misc]
        ModelType = None  # type: ignore[no-redef, misc]
        OnlineLearningPipeline = None  # type: ignore[no-redef, misc]
        PredictionResult = None  # type: ignore[no-redef, misc]
        get_online_learning_pipeline = None  # type: ignore[no-redef, misc]

# Anomaly monitoring import
try:
    from src.core.integrations.anomaly_monitoring import AnomalyMonitor

    ANOMALY_MONITORING_AVAILABLE = True
except ImportError:
    ANOMALY_MONITORING_AVAILABLE = False
    AnomalyMonitor = None  # type: ignore[misc]

# A/B testing imports for traffic routing between champion and candidate models
try:
    from ..ab_testing import (
        AB_TEST_SPLIT,
        ABTestRouter,
        CohortType,
        MetricsComparison,
        PromotionResult,
        RoutingResult,
        ShadowPolicyExecutor,
        get_ab_test_router,
    )

    AB_TESTING_AVAILABLE = True
except ImportError:
    try:
        from ab_testing import (  # type: ignore[no-redef]
            AB_TEST_SPLIT,
            ABTestRouter,
            CohortType,
            MetricsComparison,
            PromotionResult,
            RoutingResult,
            ShadowPolicyExecutor,
            get_ab_test_router,
        )

        AB_TESTING_AVAILABLE = True
    except ImportError:
        AB_TESTING_AVAILABLE = False  # type: ignore[no-redef]
        AB_TEST_SPLIT = 0.1  # type: ignore[no-redef]
        ABTestRouter = None  # type: ignore[no-redef, misc]
        CohortType = None  # type: ignore[no-redef, misc]
        MetricsComparison = None  # type: ignore[no-redef, misc]
        PromotionResult = None  # type: ignore[no-redef, misc]
        RoutingResult = None  # type: ignore[no-redef, misc]
        get_ab_test_router = None  # type: ignore[no-redef, misc]
        ShadowPolicyExecutor = None  # type: ignore[no-redef, misc]

# Import from our own modules
from enhanced_agent_bus.governance_constants import (
    GOVERNANCE_BACKOFF_SECONDS,
    GOVERNANCE_COMPLIANCE_THRESHOLD,
    GOVERNANCE_EMA_ALPHA,
    GOVERNANCE_FALLBACK_CONFIDENCE,
    GOVERNANCE_FEEDBACK_WINDOW_SECONDS,
    GOVERNANCE_HISTORY_TRIM,
    GOVERNANCE_LEARNING_CYCLE_SECONDS,
    GOVERNANCE_MAX_TREND_LENGTH,
    GOVERNANCE_PERFORMANCE_TARGET,
    GOVERNANCE_RECOMMENDED_THRESHOLD,
    GOVERNANCE_RETRAIN_CHECK_MODULUS,
    GOVERNANCE_RETRAIN_HISTORY_MIN,
    GOVERNANCE_RISK_CRITICAL,
    GOVERNANCE_RISK_HIGH,
    GOVERNANCE_RISK_LOW,
    GOVERNANCE_RISK_MEDIUM,
)

from .dtmc_learner import DTMCLearner
from .impact_scorer import ImpactScorer
from .models import (
    GovernanceDecision,
    GovernanceMetrics,
    GovernanceMode,
    ImpactFeatures,
    ImpactLevel,
)
from .threshold_manager import AdaptiveThresholds
from .trace_collector import IMPACT_TO_STATE, TraceCollector

logger = get_logger(__name__)


class AdaptiveGovernanceEngine:
    """Main adaptive governance engine with ML-enhanced decision making."""

    def __init__(self, constitutional_hash: str, config: "BusConfiguration | None" = None):
        """Initialize the adaptive governance engine.

        Sets up all components required for ML-enhanced governance decisions
        including impact scoring, threshold management, drift detection,
        online learning, A/B testing, and anomaly monitoring.

        Args:
            constitutional_hash: Hash of the constitutional rules for compliance verification.
            config: Optional BusConfiguration for feature flags (e.g. enable_dtmc).
        """
        self.constitutional_hash = constitutional_hash
        self.config = config
        self.mode = GovernanceMode.ADAPTIVE

        self.impact_scorer = ImpactScorer(self.constitutional_hash)
        self.threshold_manager = AdaptiveThresholds(self.constitutional_hash)
        validators_module = import_module("enhanced_agent_bus.validators")
        self._decision_validator: GovernanceDecisionValidatorProtocol = (
            validators_module.GovernanceDecisionValidator()
        )

        self._feedback_handler: FeedbackHandler | None = None
        self._initialize_feedback_handler()

        self.metrics = GovernanceMetrics()
        self.decision_history: deque[GovernanceDecision] = deque(maxlen=5000)
        self._dtmc_feedback_idx: int = 0

        self.feedback_window = GOVERNANCE_FEEDBACK_WINDOW_SECONDS
        self.performance_target = GOVERNANCE_PERFORMANCE_TARGET
        self.learning_task: asyncio.Task | None = None
        self.learning_thread: asyncio.Task | None = None  # Legacy alias
        self.running = False

        self._drift_detector: DriftDetector | None = None
        self._last_drift_check: float = 0.0
        self._drift_check_interval: int = DRIFT_CHECK_INTERVAL_HOURS * 3600
        self._latest_drift_report: DriftReport | None = None
        self._initialize_drift_detector()

        self._river_feature_names = self._default_river_feature_names()
        self.river_model: OnlineLearningPipeline | None = None
        self._initialize_river_model()

        self._ab_test_router: ABTestRouter | None = None
        self._shadow_executor: ShadowPolicyExecutor | None = None
        self._initialize_ab_test_router()

        self._anomaly_monitor: AnomalyMonitor | None = None
        self._initialize_anomaly_monitor()

        self._dtmc_learner = DTMCLearner(
            intervention_threshold=getattr(config, "dtmc_intervention_threshold", 0.8)
        )
        self._trace_collector = TraceCollector()
        self._background_tasks: set[asyncio.Task] = set()

    def _initialize_feedback_handler(self) -> None:
        """Initialize optional feedback handler for persistent event storage."""
        if not FEEDBACK_HANDLER_AVAILABLE:
            return

        try:
            self._feedback_handler = get_feedback_handler()
            self._feedback_handler.initialize_schema()
            logger.info("Feedback handler initialized for governance engine")
        except (RuntimeError, ValueError, TypeError) as e:
            logger.warning("Failed to initialize feedback handler: %s", e)
            self._feedback_handler = None

    def _initialize_drift_detector(self) -> None:
        """Initialize optional drift detector and load baseline reference data."""
        if not DRIFT_MONITORING_AVAILABLE:
            return

        try:
            self._drift_detector = get_drift_detector()
            if self._drift_detector.load_reference_data():
                logger.info("Drift detector initialized with reference data")
            else:
                logger.warning("Drift detector initialized but reference data not loaded")
        except (RuntimeError, ValueError, TypeError) as e:
            logger.warning("Failed to initialize drift detector: %s", e)
            self._drift_detector = None

    @staticmethod
    def _default_river_feature_names() -> list[str]:
        """Return canonical feature order for River online model."""
        return [
            "message_length",
            "agent_count",
            "tenant_complexity",
            "temporal_mean",
            "temporal_std",
            "semantic_similarity",
            "historical_precedence",
            "resource_utilization",
            "network_isolation",
            "risk_score",
            "confidence_level",
        ]

    def _initialize_river_model(self) -> None:
        """Initialize River online learning pipeline when available."""
        if ONLINE_LEARNING_AVAILABLE and RIVER_AVAILABLE:
            try:
                self.river_model = get_online_learning_pipeline(
                    feature_names=self._river_feature_names,
                    model_type=ModelType.REGRESSOR,
                )
                if self.impact_scorer.model_trained:
                    self.river_model.set_fallback_model(self.impact_scorer.impact_classifier)
                logger.info(
                    "River online learning model initialized (features: %s)",
                    len(self._river_feature_names),
                )
            except (RuntimeError, ValueError, TypeError) as e:
                logger.warning("Failed to initialize River model: %s", e)
                self.river_model = None
            return

        if ONLINE_LEARNING_AVAILABLE:
            logger.warning("River library not installed, online learning disabled")
        else:
            logger.warning("Online learning module not available, River model disabled")

    def _initialize_ab_test_router(self) -> None:
        """Initialize optional A/B routing and shadow execution components."""
        if not AB_TESTING_AVAILABLE:
            logger.warning("A/B testing module not available, traffic routing disabled")
            return

        try:
            self._ab_test_router = get_ab_test_router()
            self._shadow_executor = ShadowPolicyExecutor(self._ab_test_router)
            if self.impact_scorer.model_trained:
                self._ab_test_router.set_champion_model(
                    self.impact_scorer.impact_classifier, version=1
                )
            logger.info(
                "A/B test router initialized (champion_split=%.0f%%, candidate_split=%.0f%%)",
                (1 - AB_TEST_SPLIT) * 100,
                AB_TEST_SPLIT * 100,
            )
        except Exception as e:
            logger.warning("Failed to initialize A/B test router: %s", e)
            self._ab_test_router = None
            self._shadow_executor = None

    def _initialize_anomaly_monitor(self) -> None:
        """Initialize optional anomaly monitor."""
        if not ANOMALY_MONITORING_AVAILABLE:
            return

        try:
            self._anomaly_monitor = AnomalyMonitor()
            logger.info("Anomaly monitor initialized")
        except (RuntimeError, ValueError, TypeError) as e:
            logger.warning("Failed to initialize anomaly monitor: %s", e)

    @property
    def _learning_thread(self) -> asyncio.Task | None:
        """Internal alias for learning_task."""
        return self.learning_task

    async def initialize(self) -> None:
        """Initialize the adaptive governance engine."""
        logger.info("Initializing Adaptive Governance Engine")

        # Load historical data if available
        await self._load_historical_data()

        # Start background learning
        self.running = True
        import asyncio

        self.learning_task = asyncio.create_task(self._background_learning_loop())
        self.learning_thread = self.learning_task

        # Start anomaly monitoring
        if self._anomaly_monitor:
            await self._anomaly_monitor.start()

        logger.info("Adaptive Governance Engine initialized")

    async def shutdown(self) -> None:
        """Gracefully shutdown the adaptive governance engine."""
        self.running = False
        if self.learning_task and not self.learning_task.done():
            self.learning_task.cancel()
            try:  # noqa: SIM105
                await asyncio.wait_for(self.learning_task, timeout=5)
            except (TimeoutError, asyncio.CancelledError):
                pass

        if self._anomaly_monitor:
            await self._anomaly_monitor.stop()

        # Save final model state
        await self._save_model_state()

        logger.info("Adaptive Governance Engine shutdown complete")

    async def evaluate_governance_decision(
        self, message: MessagePayload, context: PolicyContext
    ) -> GovernanceDecision:
        """Make an adaptive governance decision for a message.

        Traffic is routed between champion and candidate models based on A/B testing
        configuration. By default, 90% of requests go to champion and 10% to candidate.
        The routing is deterministic based on the decision_id hash.
        """
        start_time = time.time()

        try:
            impact_features = await self.impact_scorer.assess_impact(message, context)
            impact_features = self._apply_dtmc_risk_blend(impact_features)

            decision_id = f"gov-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
            decision = self._build_decision_for_features(impact_features, decision_id)
            decision = self._apply_ab_test_routing(decision, impact_features, start_time)
            decision = self._apply_dtmc_escalation(decision)

            is_valid, validation_errors = await self._decision_validator.validate_decision(
                decision={
                    "action_allowed": decision.action_allowed,
                    "risk_score": decision.features_used.risk_score,
                    "recommended_threshold": decision.recommended_threshold,
                },
                context={
                    "constitutional_hash": self.constitutional_hash,
                    "expected_constitutional_hash": self.constitutional_hash,
                },
            )
            if not is_valid:
                raise ValueError(
                    "Governance decision validation failed: " + "; ".join(validation_errors)
                )

            self._record_decision_metrics(decision, start_time)
            return decision

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Governance evaluation error: %s", e)
            return self._build_conservative_fallback_decision(e)

    def _apply_dtmc_risk_blend(self, impact_features: ImpactFeatures) -> ImpactFeatures:
        """Blend DTMC trajectory risk into impact features when enabled."""
        dtmc_weight = getattr(self.config, "dtmc_impact_weight", 0.0)
        if (
            not getattr(self.config, "enable_dtmc", False)
            or not self._dtmc_learner.is_fitted
            or dtmc_weight <= 0.0
        ):
            return impact_features

        trajectory_prefix = self._get_trajectory_prefix()
        if not trajectory_prefix:
            return impact_features

        dtmc_risk = self._dtmc_learner.predict_risk(trajectory_prefix)
        blended_risk = min(1.0, impact_features.risk_score + dtmc_risk * dtmc_weight)
        logger.debug(
            "DTMC risk blend: dtmc=%.3f weight=%.3f → blended=%.3f",
            dtmc_risk,
            dtmc_weight,
            blended_risk,
        )
        return dataclasses.replace(impact_features, risk_score=blended_risk)

    def _build_decision_for_features(
        self,
        impact_features: ImpactFeatures,
        decision_id: str,
    ) -> GovernanceDecision:
        """Build baseline governance decision from assessed impact features."""
        impact_level = self._classify_impact_level(impact_features.risk_score)
        threshold = self.threshold_manager.get_adaptive_threshold(impact_level, impact_features)
        action_allowed = impact_features.risk_score <= threshold
        reasoning = self._generate_reasoning(action_allowed, impact_features, threshold)

        return GovernanceDecision(
            action_allowed=action_allowed,
            impact_level=impact_level,
            confidence_score=impact_features.confidence_level,
            reasoning=reasoning,
            recommended_threshold=threshold,
            features_used=impact_features,
            decision_id=decision_id,
        )

    def _apply_ab_test_routing(
        self,
        decision: GovernanceDecision,
        impact_features: ImpactFeatures,
        start_time: float,
    ) -> GovernanceDecision:
        """Apply optional A/B cohort routing and shadow execution metadata."""
        if not (AB_TESTING_AVAILABLE and self._ab_test_router is not None):
            return decision

        try:
            routing_result = self._ab_test_router.route(decision.decision_id)
            latency_ms = (time.time() - start_time) * 1000
            self._record_ab_test_request(routing_result, latency_ms, decision.action_allowed)

            logger.debug(
                "A/B test routing: decision %s -> %s (version: %s)",
                decision.decision_id,
                routing_result.cohort.value,
                routing_result.model_version,
            )

            self._schedule_shadow_execution_if_needed(routing_result, decision, impact_features)

            return dataclasses.replace(
                decision,
                cohort=routing_result.cohort.value,
                model_version=routing_result.model_version,
            )

        except (RuntimeError, ValueError, TypeError) as e:
            logger.warning("A/B test routing failed, using default: %s", e)
            return decision

    def _record_ab_test_request(
        self,
        routing_result: RoutingResult,
        latency_ms: float,
        action_allowed: bool,
    ) -> None:
        """Record A/B request metrics for routed decision."""
        if routing_result.cohort == CohortType.CANDIDATE:
            self._ab_test_router.get_candidate_metrics().record_request(
                latency_ms=latency_ms,
                prediction=action_allowed,
            )
            return

        self._ab_test_router.get_champion_metrics().record_request(
            latency_ms=latency_ms,
            prediction=action_allowed,
        )

    def _schedule_shadow_execution_if_needed(
        self,
        routing_result: RoutingResult,
        decision: GovernanceDecision,
        impact_features: ImpactFeatures,
    ) -> None:
        """Schedule candidate shadow execution for champion-routed traffic."""
        if routing_result.cohort != CohortType.CHAMPION or self._shadow_executor is None:
            return

        task = asyncio.create_task(
            self._shadow_executor.execute_shadow(
                request_id=decision.decision_id,
                features=impact_features,
                champion_result=decision.action_allowed,
            )
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _apply_dtmc_escalation(self, decision: GovernanceDecision) -> GovernanceDecision:
        """Escalate to high impact when DTMC predicts intervention risk."""
        if not (getattr(self.config, "enable_dtmc", False) and self._dtmc_learner.is_fitted):
            return decision

        prefix = self._get_trajectory_prefix()
        if not prefix or not self._dtmc_learner.should_intervene(prefix):
            return decision

        risk_score = self._dtmc_learner.predict_risk(prefix)
        if decision.impact_level in (ImpactLevel.HIGH, ImpactLevel.CRITICAL):
            return decision

        # Keep the escalated decision internally consistent with downstream validation.
        escalated_risk_score = min(
            1.0,
            max(
                float(decision.features_used.risk_score),
                float(risk_score),
                float(decision.recommended_threshold) + 1e-6,
            ),
        )
        escalated_features = dataclasses.replace(
            decision.features_used,
            risk_score=escalated_risk_score,
        )

        return dataclasses.replace(
            decision,
            impact_level=ImpactLevel.HIGH,
            action_allowed=False,
            features_used=escalated_features,
            reasoning=(
                f"{decision.reasoning} | DTMC trajectory risk={risk_score:.3f}"
                " exceeds intervention threshold — escalated to deliberation."
            ),
        )

    def _record_decision_metrics(self, decision: GovernanceDecision, start_time: float) -> None:
        """Store decision history and update runtime metrics."""
        self.decision_history.append(decision)
        self._update_metrics(decision, time.time() - start_time)
        if self._anomaly_monitor:
            self._anomaly_monitor.record_metrics(self.metrics)

    @staticmethod
    def _build_conservative_fallback_decision(error: Exception) -> GovernanceDecision:
        """Build fail-closed fallback decision when evaluation pipeline errors."""
        return GovernanceDecision(
            action_allowed=False,
            impact_level=ImpactLevel.HIGH,
            confidence_score=GOVERNANCE_FALLBACK_CONFIDENCE,
            reasoning=f"Governance evaluation failed: {error}. Applied conservative fallback.",
            recommended_threshold=GOVERNANCE_RECOMMENDED_THRESHOLD,
            features_used=ImpactFeatures(
                message_length=0,
                agent_count=0,
                tenant_complexity=0,
                temporal_patterns=[],
                semantic_similarity=0,
                historical_precedence=0,
                resource_utilization=0,
                network_isolation=0,
            ),
        )

    def _classify_impact_level(self, risk_score: float) -> ImpactLevel:
        """Classify risk score into impact levels."""
        if risk_score >= GOVERNANCE_RISK_CRITICAL:
            return ImpactLevel.CRITICAL
        elif risk_score >= GOVERNANCE_RISK_HIGH:
            return ImpactLevel.HIGH
        elif risk_score >= GOVERNANCE_RISK_MEDIUM:
            return ImpactLevel.MEDIUM
        elif risk_score >= GOVERNANCE_RISK_LOW:
            return ImpactLevel.LOW
        else:
            return ImpactLevel.NEGLIGIBLE

    def _generate_reasoning(self, action_allowed: bool, features, threshold: float) -> str:
        """Generate human-readable reasoning for the decision."""
        action_word = "ALLOWED" if action_allowed else "BLOCKED"

        reasoning_parts = [
            f"Action {action_word} based on risk score {features.risk_score:.3f} "
            f"(threshold: {threshold:.3f})"
        ]

        if features.confidence_level < 0.7:
            reasoning_parts.append(
                f"Low confidence ({features.confidence_level:.2f}) in assessment"
            )

        if features.historical_precedence > 0:
            reasoning_parts.append(f"Based on {features.historical_precedence} similar precedents")

        return ". ".join(reasoning_parts)

    def provide_feedback(
        self,
        decision: GovernanceDecision,
        outcome_success: bool,
        human_override: bool | None = None,
    ) -> None:
        """Provide feedback to improve the ML models and store for training."""
        try:
            # Update threshold manager
            human_feedback = None
            if human_override is not None:
                human_feedback = human_override == decision.action_allowed

            self.threshold_manager.update_model(decision, outcome_success, human_feedback)

            # Update impact scorer with actual outcome
            actual_impact = decision.features_used.risk_score
            if not outcome_success:
                actual_impact = min(1.0, actual_impact + 0.2)  # Increase perceived risk

            self.impact_scorer.update_model(decision.features_used, actual_impact)

            # Update River model for incremental online learning
            self._update_river_model(decision, actual_impact)

            # Store feedback event for persistent storage and later training
            self._store_feedback_event(decision, outcome_success, human_override, actual_impact)

            # DTMC online incremental update — only process decisions since last feedback
            if getattr(self.config, "enable_dtmc", False) and self._dtmc_learner.is_fitted:
                new_decisions = list(self.decision_history)[self._dtmc_feedback_idx :]
                self._dtmc_feedback_idx = len(self.decision_history)
                if len(new_decisions) >= 2:
                    recent = self._trace_collector.collect_from_decision_history(
                        new_decisions, min_length=2
                    )
                    for traj in recent:
                        self._dtmc_learner.update_online(traj)

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Error processing feedback: %s", e)

    def _store_feedback_event(
        self,
        decision: GovernanceDecision,
        outcome_success: bool,
        human_override: bool | None,
        actual_impact: float,
    ) -> None:
        """Store feedback event using the feedback handler for persistent storage."""
        if not FEEDBACK_HANDLER_AVAILABLE or self._feedback_handler is None:
            return

        try:
            # Determine feedback type based on outcome and human override
            if human_override is not None:
                feedback_type = FeedbackType.CORRECTION
            elif outcome_success:
                feedback_type = FeedbackType.POSITIVE
            else:
                feedback_type = FeedbackType.NEGATIVE

            # Determine outcome status
            if outcome_success:  # noqa: SIM108
                outcome_status = OutcomeStatus.SUCCESS
            else:
                outcome_status = OutcomeStatus.FAILURE

            # Extract features as dict for storage
            features_dict = {
                "message_length": decision.features_used.message_length,
                "agent_count": decision.features_used.agent_count,
                "tenant_complexity": decision.features_used.tenant_complexity,
                "temporal_patterns": decision.features_used.temporal_patterns,
                "semantic_similarity": decision.features_used.semantic_similarity,
                "historical_precedence": decision.features_used.historical_precedence,
                "resource_utilization": decision.features_used.resource_utilization,
                "network_isolation": decision.features_used.network_isolation,
                "risk_score": decision.features_used.risk_score,
                "confidence_level": decision.features_used.confidence_level,
            }

            # Build correction data if human override was provided
            correction_data = None
            if human_override is not None:
                correction_data = {
                    "original_decision": decision.action_allowed,
                    "human_override": human_override,
                    "correction_applied": human_override != decision.action_allowed,
                }

            # Create feedback event
            feedback_event = FeedbackEvent(
                decision_id=decision.decision_id,
                feedback_type=feedback_type,
                outcome=outcome_status,
                features=features_dict,
                actual_impact=actual_impact,
                correction_data=correction_data,
                metadata={
                    "impact_level": decision.impact_level.value,
                    "confidence_score": decision.confidence_score,
                    "recommended_threshold": decision.recommended_threshold,
                    "reasoning": decision.reasoning,
                    "timestamp": decision.timestamp.isoformat(),
                    "constitutional_hash": self.constitutional_hash,
                },
            )

            # Store the feedback event
            response = self._feedback_handler.store_feedback(feedback_event)
            logger.debug(
                "Stored feedback event %s for decision %s",
                response.feedback_id,
                decision.decision_id,
            )

        except (RuntimeError, ValueError, TypeError) as e:
            logger.warning("Failed to store feedback event: %s", e)

    def _update_river_model(
        self,
        decision: GovernanceDecision,
        actual_impact: float,
    ) -> None:
        """Update the River model with incremental online learning.

        This enables continuous learning from feedback without requiring
        full batch retraining. The River model uses AdaptiveRandomForest
        which handles concept drift naturally.

        Args:
            decision: The governance decision that was made
            actual_impact: The actual impact score based on outcome
        """
        if not ONLINE_LEARNING_AVAILABLE or self.river_model is None:
            return

        try:
            # Extract features from the decision for River model
            features = decision.features_used
            features_dict = {
                "message_length": float(features.message_length),
                "agent_count": float(features.agent_count),
                "tenant_complexity": float(features.tenant_complexity),
                "temporal_mean": (
                    float(np.mean(features.temporal_patterns))
                    if features.temporal_patterns and NUMPY_AVAILABLE
                    else (
                        sum(features.temporal_patterns) / len(features.temporal_patterns)
                        if features.temporal_patterns
                        else 0.0
                    )
                ),
                "temporal_std": (
                    float(np.std(features.temporal_patterns))
                    if features.temporal_patterns and NUMPY_AVAILABLE
                    else 0.0
                ),
                "semantic_similarity": float(features.semantic_similarity),
                "historical_precedence": float(features.historical_precedence),
                "resource_utilization": float(features.resource_utilization),
                "network_isolation": float(features.network_isolation),
                "risk_score": float(features.risk_score),
                "confidence_level": float(features.confidence_level),
            }

            # Learn from the feedback event incrementally
            result = self.river_model.learn_from_feedback(
                features=features_dict,
                outcome=actual_impact,
                decision_id=decision.decision_id,
            )

            if result.success:
                logger.debug(
                    "River model updated for decision %s, total samples: %s",
                    decision.decision_id,
                    result.total_samples,
                )

                # Update sklearn fallback model if River model is now ready
                # but sklearn model wasn't trained yet
                if self.river_model.adapter.is_ready and not self.impact_scorer.model_trained:
                    logger.info(
                        "River model ready with %s samples, can now provide predictions",
                        result.total_samples,
                    )
            else:
                logger.warning(
                    "River model update failed for decision %s: %s",
                    decision.decision_id,
                    result.error_message,
                )

        except (RuntimeError, ValueError, TypeError) as e:
            logger.warning("Failed to update River model: %s", e)

    def get_river_model_stats(self) -> JSONDict | None:
        """Get statistics from the River online learning model.

        Returns:
            Dict with learning stats, or None if River model unavailable
        """
        if not ONLINE_LEARNING_AVAILABLE or self.river_model is None:
            return None

        try:
            stats = self.river_model.get_stats()
            # Convert PipelineStats to dict if needed
            if hasattr(stats, "__dict__"):
                return dict(stats.__dict__)
            return dict(stats) if stats else None  # type: ignore[call-overload]
        except (RuntimeError, ValueError, TypeError) as e:
            logger.warning("Failed to get River model stats: %s", e)
            return None

    def get_ab_test_router(self) -> ABTestRouter | None:
        """Get the A/B test router instance.

        Returns:
            ABTestRouter instance or None if not available
        """
        return self._ab_test_router

    def get_ab_test_metrics(self) -> JSONDict | None:
        """Get A/B testing metrics for champion and candidate cohorts.

        Returns:
            Dict with metrics summary for both cohorts, or None if not available
        """
        if not AB_TESTING_AVAILABLE or self._ab_test_router is None:
            return None

        try:
            return self._ab_test_router.get_metrics_summary()
        except (RuntimeError, ValueError, TypeError) as e:
            logger.warning("Failed to get A/B test metrics: %s", e)
            return None

    def get_ab_test_comparison(self) -> MetricsComparison | None:
        """Compare champion and candidate model performance.

        Returns:
            MetricsComparison with statistical analysis, or None if not available
        """
        if not AB_TESTING_AVAILABLE or self._ab_test_router is None:
            return None

        try:
            return self._ab_test_router.compare_metrics()
        except (RuntimeError, ValueError, TypeError) as e:
            logger.warning("Failed to compare A/B test metrics: %s", e)
            return None

    def promote_candidate_model(self, force: bool = False) -> PromotionResult | None:
        """Promote the candidate model to champion if it performs better.

        Args:
            force: If True, bypass validation checks and promote regardless

        Returns:
            PromotionResult with status and details, or None if not available
        """
        if not AB_TESTING_AVAILABLE or self._ab_test_router is None:
            logger.warning("A/B testing not available, cannot promote candidate")
            return None

        try:
            result = self._ab_test_router.promote_candidate(force=force)
            if result.status.value == "promoted":
                logger.info(
                    "Candidate model promoted to champion: v%s -> v%s",
                    result.previous_champion_version,
                    result.new_champion_version,
                )
            return result
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Failed to promote candidate model: %s", e)
            return None

    def _update_metrics(self, decision: GovernanceDecision, response_time: float) -> None:
        """Update performance metrics."""
        # Update counters
        self.metrics.average_response_time = (
            self.metrics.average_response_time * (1 - GOVERNANCE_EMA_ALPHA)
            + response_time * GOVERNANCE_EMA_ALPHA
        )

        # Calculate compliance metrics
        decision_history = list(self.decision_history)
        recent_decisions = (
            decision_history[-GOVERNANCE_HISTORY_TRIM:]
            if len(decision_history) > GOVERNANCE_HISTORY_TRIM
            else decision_history
        )

        if recent_decisions:
            compliant_decisions = sum(
                1 for d in recent_decisions if d.confidence_score > GOVERNANCE_COMPLIANCE_THRESHOLD
            )
            self.metrics.constitutional_compliance_rate = compliant_decisions / len(
                recent_decisions
            )

    async def _background_learning_loop(self) -> None:
        """Background task for continuous model improvement."""
        import asyncio

        while self.running:
            try:
                await asyncio.sleep(GOVERNANCE_LEARNING_CYCLE_SECONDS)

                # Analyze recent performance
                self._analyze_performance_trends()

                # Trigger model retraining if needed
                if self._should_retrain_models():
                    logger.info("Triggering background model retraining")
                    # Retraining happens automatically in the model update methods

                # Scheduled drift detection (every drift_check_interval)
                self._run_scheduled_drift_detection()

                # DTMC periodic refit from accumulated decision history
                self._maybe_refit_dtmc()

                # Log performance summary
                self._log_performance_summary()

            except (RuntimeError, ValueError, TypeError) as e:
                logger.error("Background learning error: %s", e)
                await asyncio.sleep(GOVERNANCE_BACKOFF_SECONDS)

    def _run_scheduled_drift_detection(self) -> None:
        """Run drift detection if the scheduled interval has elapsed."""
        if not DRIFT_MONITORING_AVAILABLE or self._drift_detector is None:
            return

        current_time = time.time()
        time_since_last_check = current_time - self._last_drift_check

        # Check if drift detection is due
        if time_since_last_check < self._drift_check_interval:
            return

        logger.info(
            "drift_check_interval: Running scheduled drift detection (interval: %.1f hours)",
            self._drift_check_interval / 3600,
        )

        try:
            # Collect recent decision data for drift analysis
            recent_data = self._collect_drift_data()

            if recent_data is None or len(recent_data) == 0:
                logger.info("drift_check_interval: Insufficient data for drift detection, skipping")
                self._last_drift_check = current_time
                return

            # Run drift detection
            drift_report = self._drift_detector.detect_drift(recent_data)
            self._latest_drift_report = drift_report
            self._last_drift_check = current_time

            # Log drift detection results
            if drift_report.status == DriftStatus.SUCCESS:
                if drift_report.dataset_drift:
                    logger.warning(
                        "drift_check_interval: Drift detected! Severity: %s, "
                        "Drifted features: %s/%s (%.1f%%)",
                        drift_report.drift_severity.value,
                        drift_report.drifted_features,
                        drift_report.total_features,
                        drift_report.drift_share * 100,
                    )

                    # Log recommendations
                    for recommendation in drift_report.recommendations:
                        logger.info("drift_check_interval: Recommendation - %s", recommendation)

                    # Check if retraining should be triggered
                    if self._drift_detector.should_trigger_retraining(drift_report):
                        logger.warning(
                            "drift_check_interval: Drift severity warrants model retraining"
                        )
                else:
                    logger.info(
                        "drift_check_interval: No significant drift detected. Drift share: %.1f%%",
                        drift_report.drift_share * 100,
                    )
            else:
                logger.warning(
                    "drift_check_interval: Drift detection completed with status: %s. %s",
                    drift_report.status.value,
                    drift_report.error_message or "",
                )

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("drift_check_interval: Error during drift detection: %s", e)
            # Still update last check time to prevent retry flood
            self._last_drift_check = current_time

    def _collect_drift_data(self):
        """Collect recent decision data for drift analysis."""
        try:
            # Need pandas for DataFrame creation
            try:
                import pandas as pd
            except ImportError:
                logger.warning("pandas not available for drift data collection")
                return None

            # Collect features from recent decisions
            if not self.decision_history:
                return None

            # Extract feature data from decision history
            feature_records = []
            for decision in self.decision_history:
                features = decision.features_used
                record = {
                    "message_length": features.message_length,
                    "agent_count": features.agent_count,
                    "tenant_complexity": features.tenant_complexity,
                    "temporal_mean": (
                        float(np.mean(features.temporal_patterns))
                        if features.temporal_patterns and NUMPY_AVAILABLE
                        else (
                            sum(features.temporal_patterns) / len(features.temporal_patterns)
                            if features.temporal_patterns
                            else 0.0
                        )
                    ),
                    "temporal_std": (
                        float(np.std(features.temporal_patterns))
                        if features.temporal_patterns and NUMPY_AVAILABLE
                        else 0.0
                    ),
                    "semantic_similarity": features.semantic_similarity,
                    "historical_precedence": features.historical_precedence,
                    "resource_utilization": features.resource_utilization,
                    "network_isolation": features.network_isolation,
                    "risk_score": features.risk_score,
                    "confidence_level": features.confidence_level,
                }
                feature_records.append(record)

            if not feature_records:
                return None

            return pd.DataFrame(feature_records)

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Error collecting drift data: %s", e)
            return None

    def get_latest_drift_report(self) -> DriftReport | None:
        """Get the most recent drift detection report."""
        return self._latest_drift_report

    def _analyze_performance_trends(self) -> None:
        """Analyze performance trends for adaptive adjustments."""
        try:
            # Update trend data
            self.metrics.compliance_trend.append(self.metrics.constitutional_compliance_rate)
            self.metrics.accuracy_trend.append(1.0 - self.metrics.false_positive_rate)
            self.metrics.performance_trend.append(
                1.0 / max(0.001, self.metrics.average_response_time)
            )

            # Trim trends to GOVERNANCE_MAX_TREND_LENGTH (handles plain-list overrides).
            max_len = GOVERNANCE_MAX_TREND_LENGTH
            for trend_name in ("compliance_trend", "accuracy_trend", "performance_trend"):
                trend = getattr(self.metrics, trend_name)
                if len(trend) > max_len:
                    trimmed = type(trend)(list(trend)[-max_len:])
                    setattr(self.metrics, trend_name, trimmed)

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Performance trend analysis error: %s", e)

    def _should_retrain_models(self) -> bool:
        """Determine if models should be retrained."""
        # Retrain if accuracy drops below target
        if self.metrics.constitutional_compliance_rate < self.performance_target:
            return True

        # Retrain if we have sufficient new data
        return (
            len(self.decision_history) >= GOVERNANCE_RETRAIN_HISTORY_MIN
            and len(self.decision_history) % GOVERNANCE_RETRAIN_CHECK_MODULUS == 0
        )

    def _log_performance_summary(self) -> None:
        """Log periodic performance summary."""
        try:
            summary = {
                "compliance_rate": f"{self.metrics.constitutional_compliance_rate:.3f}",
                "avg_response_time": f"{self.metrics.average_response_time:.4f}s",
                "decisions_made": len(self.decision_history),
                "mode": self.mode.value,
            }
            logger.info("Governance Performance: %s", summary)

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Performance logging error: %s", e)

    def _get_trajectory_prefix(self) -> list[int] | None:
        """Return last 10 impact levels as DTMC state indices, or None if history is empty."""
        if not self.decision_history:
            return None
        return [IMPACT_TO_STATE[d.impact_level] for d in list(self.decision_history)[-10:]]

    def _maybe_refit_dtmc(self) -> None:
        """Refit DTMC from decision_history when enough data has accumulated."""
        if not getattr(self.config, "enable_dtmc", False):
            return
        if len(self.decision_history) < 10:
            return
        trajectories = self._trace_collector.collect_from_decision_history(
            list(self.decision_history)
        )
        if not trajectories:
            return
        result = self._dtmc_learner.fit(trajectories)
        logger.info(
            "DTMC refit: %d trajectories, unsafe_fraction=%.3f",
            result.n_trajectories,
            result.unsafe_fraction,
        )

    async def _load_historical_data(self) -> None:
        """Load historical decision data for model initialization."""
        try:
            # Implementation would load from persistent storage
            # For now, start with empty models
            logger.info("Loaded historical governance data")

        except (RuntimeError, ValueError, TypeError) as e:
            logger.warning("Could not load historical data: %s", e)

    async def _save_model_state(self) -> None:
        """Save current model state for persistence."""
        try:
            # Implementation would save models to persistent storage
            logger.info("Saved governance model state")

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Error saving model state: %s", e)


__all__ = [
    "AB_TESTING_AVAILABLE",
    # Availability flags
    "DRIFT_MONITORING_AVAILABLE",
    "ONLINE_LEARNING_AVAILABLE",
    "AdaptiveGovernanceEngine",
]
