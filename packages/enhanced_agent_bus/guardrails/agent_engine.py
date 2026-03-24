"""
Agent Engine Guardrail Component.

Layer 2 of OWASP guardrails: core governance layer with constitutional
validation and ML-based impact scoring.

Constitutional Hash: cdd01ef066bc6cf2
"""

import time
from dataclasses import dataclass

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .base import GuardrailComponent, GuardrailInput
from .enums import GuardrailLayer, SafetyAction, ViolationSeverity
from .models import GuardrailResult, Violation

logger = get_logger(__name__)
# Import impact scoring service for governance-aware impact calculation
try:
    from ..impact_scorer_infra import (
        ImpactScoringConfig,
        ImpactScoringService,
        configure_impact_scorer,
        get_impact_scorer_service,
        reset_impact_scorer,
    )

    IMPACT_SCORING_AVAILABLE = True
except ImportError:
    IMPACT_SCORING_AVAILABLE = False
    ImpactScoringConfig = None  # type: ignore[misc, assignment]
    ImpactScoringService = None  # type: ignore[misc, assignment]
    configure_impact_scorer = None  # type: ignore[misc, assignment]
    get_impact_scorer_service = None  # type: ignore[misc, assignment]
    reset_impact_scorer = None  # type: ignore[misc, assignment]


@dataclass
class AgentEngineConfig:
    """Configuration for agent engine."""

    enabled: bool = True
    constitutional_validation: bool = True
    impact_scoring: bool = True
    deliberation_required_threshold: float = 0.8
    timeout_ms: int = 5000

    # MiniCPM-enhanced scoring options
    enable_minicpm: bool = False
    minicpm_model_name: str = "MiniCPM4-0.5B"
    prefer_minicpm_semantic: bool = True


class AgentEngine(GuardrailComponent):
    """Agent Engine: Layer 2 of OWASP guardrails.

    Core governance layer with constitutional validation and impact scoring.
    Supports MiniCPM-enhanced 7-dimensional governance scoring when enabled.
    """

    def __init__(self, config: AgentEngineConfig | None = None):
        self.config = config or AgentEngineConfig()
        self._impact_scorer = None

        # Initialize impact scoring service if available and enabled
        if self.config.impact_scoring and IMPACT_SCORING_AVAILABLE:
            try:
                if self.config.enable_minicpm:
                    configure_impact_scorer(
                        enable_minicpm=True,
                        minicpm_model_name=self.config.minicpm_model_name,
                        minicpm_fallback_to_keywords=True,
                        prefer_minicpm_semantic=self.config.prefer_minicpm_semantic,
                    )
                self._impact_scorer = get_impact_scorer_service()
                logger.info(
                    f"Impact scoring initialized (MiniCPM: {self._impact_scorer.minicpm_available})"
                )
            except (ImportError, RuntimeError, ValueError, TypeError) as e:
                logger.warning(f"Failed to initialize impact scorer: {e}")

    def get_layer(self) -> GuardrailLayer:
        return GuardrailLayer.AGENT_ENGINE

    async def process(self, data: GuardrailInput, context: JSONDict) -> GuardrailResult:
        """Process through agent engine with constitutional validation."""
        start_time = time.monotonic()
        violations = []
        trace_id = context.get("trace_id", "")

        try:
            # Constitutional validation
            if self.config.constitutional_validation:
                constitutional_result = await self._validate_constitutional(data, context)
                if not constitutional_result["compliant"]:
                    violations.append(
                        Violation(
                            layer=self.get_layer(),
                            violation_type="constitutional_violation",
                            severity=ViolationSeverity.HIGH,
                            message="Request violates constitutional principles",
                            details=constitutional_result,
                            trace_id=trace_id,
                        )
                    )

            # Impact scoring
            if self.config.impact_scoring:
                impact_score = await self._calculate_impact_score(data, context)
                if impact_score > self.config.deliberation_required_threshold:
                    violations.append(
                        Violation(
                            layer=self.get_layer(),
                            violation_type="high_impact",
                            severity=ViolationSeverity.MEDIUM,
                            message=f"High impact action requires deliberation (score: {impact_score})",
                            details={"impact_score": impact_score},
                            trace_id=trace_id,
                        )
                    )

            # Determine action
            if violations:
                action = SafetyAction.ESCALATE
                allowed = False
            else:
                action = SafetyAction.ALLOW
                allowed = True

        except (TimeoutError, RuntimeError, ValueError, TypeError) as e:
            logger.error(f"Agent engine error: {e}")
            violations.append(
                Violation(
                    layer=self.get_layer(),
                    violation_type="processing_error",
                    severity=ViolationSeverity.HIGH,
                    message=f"Agent engine processing failed: {e!s}",
                    trace_id=trace_id,
                )
            )
            action = SafetyAction.BLOCK
            allowed = False

        processing_time = (time.monotonic() - start_time) * 1000

        return GuardrailResult(
            action=action,
            allowed=allowed,
            violations=violations,
            processing_time_ms=processing_time,
            trace_id=trace_id,
        )

    async def _validate_constitutional(self, data: GuardrailInput, context: JSONDict) -> JSONDict:
        """Validate against constitutional principles."""
        # This would integrate with the constitutional validation system
        # For now, return a mock result
        return {
            "compliant": True,
            "confidence": 0.95,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    async def _calculate_impact_score(self, data: GuardrailInput, context: JSONDict) -> float:
        """
        Calculate impact score for the action using ML-based scoring.

        Uses the ImpactScoringService which supports:
        - Basic semantic (keyword-based) scoring
        - MiniCPM-enhanced 7-dimensional governance scoring (when enabled)
        - Statistical pattern analysis

        Args:
            data: The input data to score.
            context: Additional context for scoring.

        Returns:
            Impact score between 0.0 and 1.0.
        """
        if self._impact_scorer is None:
            # Fallback to basic keyword-based scoring
            return self._keyword_based_impact_score(data)

        try:
            # Build context for the scoring service
            scoring_context = {
                "content": str(data) if data else "",
                **context,
            }

            # Get comprehensive impact score
            result = self._impact_scorer.get_impact_score(scoring_context)
            return result.aggregate_score

        except (RuntimeError, ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Impact scoring failed, using fallback: {e}")
            return self._keyword_based_impact_score(data)

    def _keyword_based_impact_score(self, data: GuardrailInput) -> float:
        """Fallback keyword-based impact scoring."""
        if not data:
            return 0.1

        text = str(data).lower()
        high_impact_keywords = [
            "critical",
            "security",
            "emergency",
            "danger",
            "breach",
            "vulnerability",
            "exploit",
            "unauthorized",
            "suspicious",
            "transaction",
            "transfer",
            "payment",
            "violation",
            "compliance",
            "audit",
            "governance",
            "attack",
            "threat",
        ]

        if any(kw in text for kw in high_impact_keywords):
            return 0.85

        return 0.3
