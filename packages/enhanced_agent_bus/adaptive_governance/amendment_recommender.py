"""
ACGS-2 Amendment Recommender
Constitutional Hash: 608508a9bd224290

Bridges adaptive governance learning signals to constitutional amendment proposals.
Converts DTMC risk signals and threshold drift into structured amendment candidates
that flow through the standard proposal pipeline with full invariant checking.

Design principle: recommend only, never self-enact.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


class RecommendationTrigger(StrEnum):
    """What triggered the recommendation."""

    DTMC_RISK_THRESHOLD = "dtmc_risk_threshold"
    THRESHOLD_DRIFT = "threshold_drift"
    DEGRADATION_PATTERN = "degradation_pattern"
    FEEDBACK_SIGNAL = "feedback_signal"


class RecommendationPriority(StrEnum):
    """Priority level for an amendment recommendation."""

    CRITICAL = "critical"  # immediate attention (risk > 0.95)
    HIGH = "high"  # soon (risk > 0.8)
    MEDIUM = "medium"  # next review cycle
    LOW = "low"  # informational


class AmendmentRecommendation(BaseModel):
    """A recommendation for a constitutional amendment.

    This is NOT a proposal -- it is a suggestion that must go through
    the full proposal pipeline (with invariant checking, MACI separation,
    and human approval) before activation.
    """

    recommendation_id: str
    trigger: RecommendationTrigger
    priority: RecommendationPriority
    target_area: str
    proposed_changes: dict
    justification: str
    evidence: dict = Field(default_factory=dict)
    risk_score: float = 0.0
    cooldown_until: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Map DTMC states to governance areas
_STATE_AREA_MAP: dict[int, str] = {
    0: "governance.negligible",  # NEGLIGIBLE
    1: "governance.low_risk",  # LOW
    2: "governance.medium_risk",  # MEDIUM
    3: "governance.high_risk",  # HIGH -- threshold tuning
    4: "governance.critical",  # CRITICAL -- escalation rules
}


class AmendmentRecommender:
    """Converts governance learning signals into amendment recommendations.

    Key behaviors:
    - Generates recommendations from DTMC risk signals
    - Applies cooldown to prevent recommendation spam
    - Tracks recommendation history for learning
    - NEVER creates proposals directly -- only emits AmendmentRecommendation
    - Recommendations must be converted to ProposalRequest by an authorized actor
    """

    def __init__(
        self,
        risk_threshold: float = 0.8,
        cooldown_minutes: int = 60,
        max_pending_recommendations: int = 10,
    ) -> None:
        self.risk_threshold = risk_threshold
        self.cooldown_minutes = cooldown_minutes
        self.max_pending = max_pending_recommendations
        self._pending: list[AmendmentRecommendation] = []
        self._history: list[AmendmentRecommendation] = []
        self._cooldowns: dict[str, datetime] = {}

    def evaluate_risk_signal(
        self,
        risk_score: float,
        trajectory_prefix: list[int],
        context: dict | None = None,
    ) -> AmendmentRecommendation | None:
        """Evaluate a DTMC risk signal and optionally generate a recommendation.

        Returns None if:
        - Risk is below threshold
        - Target area is in cooldown
        - Max pending recommendations reached
        """
        if risk_score < self.risk_threshold:
            return None

        target_area = self._infer_target_area(trajectory_prefix, context or {})

        if self._is_in_cooldown(target_area):
            logger.debug("recommendation_in_cooldown", target_area=target_area)
            return None

        if len(self._pending) >= self.max_pending:
            logger.warning(
                "max_pending_recommendations_reached",
                count=len(self._pending),
            )
            return None

        priority = self._score_priority(risk_score)

        recommendation = AmendmentRecommendation(
            recommendation_id=(f"REC-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{target_area}"),
            trigger=RecommendationTrigger.DTMC_RISK_THRESHOLD,
            priority=priority,
            target_area=target_area,
            proposed_changes=self._suggest_changes(target_area, risk_score, context or {}),
            justification=(
                f"DTMC risk score {risk_score:.3f} exceeds threshold "
                f"{self.risk_threshold} for area '{target_area}'. "
                f"Trajectory prefix: {trajectory_prefix}"
            ),
            evidence={
                "risk_score": risk_score,
                "threshold": self.risk_threshold,
                "trajectory_prefix": trajectory_prefix,
                "context": context or {},
            },
            risk_score=risk_score,
        )

        self._pending.append(recommendation)
        self._set_cooldown(target_area)

        logger.info(
            "amendment_recommendation_generated",
            recommendation_id=recommendation.recommendation_id,
            priority=priority,
            risk_score=risk_score,
            target_area=target_area,
        )

        return recommendation

    def evaluate_threshold_drift(
        self,
        metric_name: str,
        current_value: float,
        baseline_value: float,
        drift_magnitude: float,
    ) -> AmendmentRecommendation | None:
        """Generate recommendation when adaptive thresholds drift significantly."""
        if abs(drift_magnitude) < 0.1:
            return None

        target_area = f"thresholds.{metric_name}"

        if self._is_in_cooldown(target_area):
            return None

        if len(self._pending) >= self.max_pending:
            return None

        recommendation = AmendmentRecommendation(
            recommendation_id=(
                f"REC-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-drift-{metric_name}"
            ),
            trigger=RecommendationTrigger.THRESHOLD_DRIFT,
            priority=RecommendationPriority.MEDIUM,
            target_area=target_area,
            proposed_changes={
                f"thresholds.{metric_name}": {
                    "from": baseline_value,
                    "to": current_value,
                    "drift": drift_magnitude,
                }
            },
            justification=(
                f"Adaptive threshold '{metric_name}' has drifted "
                f"{drift_magnitude:.1%} from baseline {baseline_value:.3f} "
                f"to {current_value:.3f}"
            ),
            evidence={
                "metric_name": metric_name,
                "baseline": baseline_value,
                "current": current_value,
                "drift": drift_magnitude,
            },
            risk_score=abs(drift_magnitude),
        )

        self._pending.append(recommendation)
        self._set_cooldown(target_area)
        return recommendation

    def get_pending(self) -> list[AmendmentRecommendation]:
        """Return all pending recommendations (not yet converted to proposals)."""
        return list(self._pending)

    def acknowledge(self, recommendation_id: str) -> AmendmentRecommendation | None:
        """Move a recommendation from pending to history (after proposal creation)."""
        for i, rec in enumerate(self._pending):
            if rec.recommendation_id == recommendation_id:
                acknowledged = self._pending.pop(i)
                self._history.append(acknowledged)
                logger.info(
                    "recommendation_acknowledged",
                    recommendation_id=recommendation_id,
                )
                return acknowledged
        return None

    def dismiss(self, recommendation_id: str, reason: str = "") -> bool:
        """Dismiss a recommendation without creating a proposal."""
        for i, rec in enumerate(self._pending):
            if rec.recommendation_id == recommendation_id:
                self._pending.pop(i)
                self._history.append(rec)
                logger.info(
                    "recommendation_dismissed",
                    recommendation_id=recommendation_id,
                    reason=reason,
                )
                return True
        return False

    def _is_in_cooldown(self, target_area: str) -> bool:
        """Check whether a target area is still in cooldown."""
        if target_area not in self._cooldowns:
            return False
        return datetime.now(UTC) < self._cooldowns[target_area]

    def _infer_target_area(self, trajectory_prefix: list[int], context: dict) -> str:
        """Infer which constitutional area needs attention from the trajectory."""
        # Override with context if available
        if "target_area" in context:
            return context["target_area"]

        if not trajectory_prefix:
            return "governance.general"

        last_state = trajectory_prefix[-1]
        return _STATE_AREA_MAP.get(last_state, "governance.general")

    def _score_priority(self, risk_score: float) -> RecommendationPriority:
        """Map a risk score to a recommendation priority."""
        if risk_score >= 0.95:
            return RecommendationPriority.CRITICAL
        if risk_score >= 0.8:
            return RecommendationPriority.HIGH
        if risk_score >= 0.5:
            return RecommendationPriority.MEDIUM
        return RecommendationPriority.LOW

    def _suggest_changes(self, target_area: str, risk_score: float, context: dict) -> dict:
        """Generate suggested changes based on risk signal."""
        return {
            target_area: {
                "action": "review_and_tighten",
                "current_risk": risk_score,
                "suggested_threshold_adjustment": min(risk_score + 0.05, 1.0),
                "requires_human_review": True,
            }
        }

    def _set_cooldown(self, target_area: str) -> None:
        """Set cooldown for a target area to prevent recommendation spam."""
        self._cooldowns[target_area] = datetime.now(UTC) + timedelta(minutes=self.cooldown_minutes)


__all__ = [
    "AmendmentRecommendation",
    "AmendmentRecommender",
    "RecommendationPriority",
    "RecommendationTrigger",
]
