"""
ACGS-2 Enhanced Agent Bus - Constitutional Classifier Real-Time Detector
Constitutional Hash: 608508a9bd224290

Real-time threat detection engine for constitutional compliance.
Optimized for sub-5ms inference latency with streaming support.
"""

import inspect
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

from .patterns import (
    ThreatCategory,
    ThreatPatternRegistry,
    ThreatSeverity,
    get_threat_pattern_registry,
)
from .scoring import ComplianceScore, ComplianceScoringEngine, get_scoring_engine

logger = get_logger(__name__)
THREAT_CALLBACK_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)
BLOCK_CALLBACK_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


class DetectionMode(Enum):
    """Detection modes for different use cases."""

    QUICK = "quick"  # Fast path, CRITICAL only
    STANDARD = "standard"  # Full pattern + heuristic
    COMPREHENSIVE = "comprehensive"  # All analysis including semantic
    STREAMING = "streaming"  # Token-by-token analysis


class DetectionDecision(Enum):
    """Detection decision outcomes."""

    ALLOW = "allow"
    BLOCK = "block"
    FLAG = "flag"  # Allow but flag for review
    ESCALATE = "escalate"  # Requires human review


@dataclass
class DetectionResult:
    """Result of threat detection.

    Constitutional Hash: 608508a9bd224290
    """

    decision: DetectionDecision
    threat_detected: bool
    compliance_score: ComplianceScore | None = None
    latency_ms: float = 0.0
    mode: DetectionMode = DetectionMode.STANDARD
    categories_detected: set[ThreatCategory] = field(default_factory=set)
    max_severity: ThreatSeverity | None = None
    explanation: str = ""
    recommendations: list[str] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "decision": self.decision.value,
            "threat_detected": self.threat_detected,
            "compliance_score": self.compliance_score.to_dict() if self.compliance_score else None,
            "latency_ms": round(self.latency_ms, 3),
            "mode": self.mode.value,
            "categories_detected": [c.value for c in self.categories_detected],
            "max_severity": self.max_severity.value if self.max_severity else None,
            "explanation": self.explanation,
            "recommendations": self.recommendations,
            "constitutional_hash": self.constitutional_hash,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class DetectorConfig:
    """Configuration for the threat detector.

    Constitutional Hash: 608508a9bd224290
    """

    # Thresholds
    block_threshold: float = 0.4  # Score below this = BLOCK
    flag_threshold: float = 0.7  # Score below this = FLAG
    escalate_categories: set[ThreatCategory] = field(
        default_factory=lambda: {
            ThreatCategory.CONSTITUTIONAL_BYPASS,
            ThreatCategory.PRIVILEGE_ESCALATION,
        }
    )

    # Performance
    max_latency_ms: float = 5.0  # Target latency
    enable_caching: bool = True
    cache_ttl_seconds: int = 300

    # Behavior
    strict_mode: bool = True  # object CRITICAL = BLOCK
    log_threats: bool = True
    enable_recommendations: bool = True

    constitutional_hash: str = CONSTITUTIONAL_HASH


class ThreatDetector:
    """Real-time threat detection engine.

    Provides fast, accurate threat detection for constitutional compliance.
    Optimized for <5ms latency with configurable detection modes.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: DetectorConfig | None = None,
        scoring_engine: ComplianceScoringEngine | None = None,
        pattern_registry: ThreatPatternRegistry | None = None,
    ):
        """Initialize the threat detector.

        Args:
            config: Detector configuration (uses defaults if None)
            scoring_engine: Scoring engine (uses global if None)
            pattern_registry: Pattern registry (uses global if None)
        """
        self.config = config or DetectorConfig()
        self.scoring_engine = scoring_engine or get_scoring_engine()
        self.registry = pattern_registry or get_threat_pattern_registry()
        self.constitutional_hash = CONSTITUTIONAL_HASH

        # Detection metrics
        self._total_detections = 0
        self._blocked_count = 0
        self._flagged_count = 0
        self._total_latency_ms = 0.0

        # Simple LRU cache for repeated inputs
        self._cache: dict[str, tuple[DetectionResult, float]] = {}
        self._cache_max_size = 1000

        # Callbacks for detection events
        self._on_threat_detected: list[Callable] = []
        self._on_block: list[Callable] = []

    async def detect(
        self,
        content: str,
        mode: DetectionMode = DetectionMode.STANDARD,
        context: dict | None = None,
        use_cache: bool = True,
    ) -> DetectionResult:
        """Detect threats in content.

        Main entry point for threat detection. Selects appropriate
        detection strategy based on mode.

        Args:
            content: Content to analyze
            mode: Detection mode (affects speed vs accuracy tradeoff)
            context: Optional context for contextual analysis
            use_cache: Whether to use detection cache

        Returns:
            DetectionResult with decision and details
        """
        start_time = time.monotonic()
        self._total_detections += 1

        # Check cache
        cached_result = self._handle_cache_lookup(content, mode, use_cache, start_time)
        if cached_result is not None:
            return cached_result

        # Select detection strategy
        result = await self._select_detection_strategy(content, mode, context, start_time)

        # Update metrics, cache, callbacks, and logging
        await self._finalize_detection_result(result, content, mode, use_cache)

        return result

    def _handle_cache_lookup(
        self, content: str, mode: DetectionMode, use_cache: bool, start_time: float
    ) -> DetectionResult | None:
        """Handle cache lookup logic."""
        if not (use_cache and self.config.enable_caching):
            return None

        cache_key = f"{mode.value}:{hash(content)}"
        if cache_key not in self._cache:
            return None

        cached_result, cache_time = self._cache[cache_key]
        if time.monotonic() - cache_time >= self.config.cache_ttl_seconds:
            return None

        # Update latency for cached result
        cached_result.latency_ms = (time.monotonic() - start_time) * 1000
        return cached_result

    async def _select_detection_strategy(
        self, content: str, mode: DetectionMode, context: dict | None, start_time: float
    ) -> DetectionResult:
        """Select and execute the appropriate detection strategy."""
        if mode == DetectionMode.QUICK:
            return await self._quick_detect(content, start_time)
        elif mode == DetectionMode.STANDARD:
            return await self._standard_detect(content, context, start_time)
        elif mode == DetectionMode.COMPREHENSIVE:
            return await self._comprehensive_detect(content, context, start_time)
        elif mode == DetectionMode.STREAMING:
            # Streaming requires different API - this is for single-shot
            return await self._standard_detect(content, context, start_time)
        else:
            return await self._standard_detect(content, context, start_time)

    async def _finalize_detection_result(
        self, result: DetectionResult, content: str, mode: DetectionMode, use_cache: bool
    ) -> None:
        """Update metrics, cache, callbacks, and logging after detection."""
        # Update metrics
        self._update_detection_metrics(result)

        # Cache result
        if use_cache and self.config.enable_caching:
            cache_key = f"{mode.value}:{hash(content)}"
            self._update_cache(cache_key, result)

        # Trigger callbacks and logging
        await self._handle_callbacks_and_logging(result)

    def _update_detection_metrics(self, result: DetectionResult) -> None:
        """Update detection metrics."""
        self._total_latency_ms += result.latency_ms
        if result.decision == DetectionDecision.BLOCK:
            self._blocked_count += 1
        elif result.decision == DetectionDecision.FLAG:
            self._flagged_count += 1

    async def _handle_callbacks_and_logging(self, result: DetectionResult) -> None:
        """Handle callbacks and logging for detection result."""
        # Trigger callbacks
        if result.threat_detected:
            await self._trigger_threat_callbacks(result)
        if result.decision == DetectionDecision.BLOCK:
            await self._trigger_block_callbacks(result)

        # Log if configured
        if self.config.log_threats and result.threat_detected:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Threat detected: decision={result.decision.value}, "
                f"categories={[c.value for c in result.categories_detected]}, "
                f"severity={result.max_severity.value if result.max_severity else 'none'}, "
                f"latency={result.latency_ms:.2f}ms"
            )

    async def _quick_detect(self, content: str, start_time: float) -> DetectionResult:
        """Quick detection mode - CRITICAL patterns only.

        Optimized for <1ms latency.
        """
        # Use registry's quick scan for fastest path
        match = self.registry.quick_scan(content)

        latency_ms = (time.monotonic() - start_time) * 1000

        if match and match.pattern:
            return DetectionResult(
                decision=DetectionDecision.BLOCK,
                threat_detected=True,
                latency_ms=latency_ms,
                mode=DetectionMode.QUICK,
                categories_detected={match.pattern.category},
                max_severity=match.pattern.severity,
                explanation=f"Critical threat pattern detected: {match.pattern.category.value}",
                recommendations=["Review and sanitize input", "Consider enhanced monitoring"],
                constitutional_hash=self.constitutional_hash,
            )

        return DetectionResult(
            decision=DetectionDecision.ALLOW,
            threat_detected=False,
            latency_ms=latency_ms,
            mode=DetectionMode.QUICK,
            explanation="Quick scan passed - no critical threats detected",
            constitutional_hash=self.constitutional_hash,
        )

    async def _standard_detect(
        self, content: str, context: dict | None, start_time: float
    ) -> DetectionResult:
        """Standard detection mode - full pattern and heuristic analysis.

        Targets <5ms latency with balanced accuracy.
        """
        # Calculate compliance score
        compliance_score = self.scoring_engine.calculate_score(content, context)

        latency_ms = (time.monotonic() - start_time) * 1000

        # Extract detected categories
        categories: set[ThreatCategory] = set()
        max_severity: ThreatSeverity | None = None
        severity_order = [
            ThreatSeverity.INFO,
            ThreatSeverity.LOW,
            ThreatSeverity.MEDIUM,
            ThreatSeverity.HIGH,
            ThreatSeverity.CRITICAL,
        ]

        for match in compliance_score.threat_matches:
            if match.pattern:
                categories.add(match.pattern.category)
                if max_severity is None:
                    max_severity = match.pattern.severity
                elif severity_order.index(match.pattern.severity) > severity_order.index(
                    max_severity
                ):
                    max_severity = match.pattern.severity

        # Determine decision
        decision = self._determine_decision(compliance_score, categories, max_severity)

        # Generate explanation
        explanation = self._generate_explanation(compliance_score, decision)

        # Generate recommendations
        recommendations = []
        if self.config.enable_recommendations:
            recommendations = self._generate_recommendations(compliance_score, categories)

        return DetectionResult(
            decision=decision,
            threat_detected=len(compliance_score.threat_matches) > 0,
            compliance_score=compliance_score,
            latency_ms=latency_ms,
            mode=DetectionMode.STANDARD,
            categories_detected=categories,
            max_severity=max_severity,
            explanation=explanation,
            recommendations=recommendations,
            constitutional_hash=self.constitutional_hash,
        )

    async def _comprehensive_detect(
        self, content: str, context: dict | None, start_time: float
    ) -> DetectionResult:
        """Comprehensive detection mode - all analysis techniques.

        Most thorough but may exceed 5ms for complex inputs.
        """
        # For comprehensive mode, we add semantic analysis and deeper inspection
        # Start with standard detection
        result = await self._standard_detect(content, context, start_time)

        # Add additional comprehensive checks
        # (In a full implementation, this would include:
        # - Deep semantic analysis
        # - Cross-reference with threat intelligence
        # - Context-aware pattern matching
        # - Historical analysis)

        result.mode = DetectionMode.COMPREHENSIVE

        # Recalculate latency
        result.latency_ms = (time.monotonic() - start_time) * 1000

        return result

    async def detect_streaming(
        self,
        token_stream: AsyncIterator[str],
        context: dict | None = None,
    ) -> AsyncIterator[DetectionResult]:
        """Streaming detection for token-by-token analysis.

        Yields detection results as content accumulates.
        Useful for real-time monitoring of generated content.

        Args:
            token_stream: Async iterator of tokens
            context: Optional context for analysis

        Yields:
            DetectionResult for accumulated content
        """
        accumulated = ""
        check_interval = 10  # Check every N tokens
        token_count = 0

        async for token in token_stream:
            accumulated += token
            token_count += 1

            # Periodic checks
            if token_count % check_interval == 0:
                result = await self.detect(
                    accumulated,
                    mode=DetectionMode.QUICK,  # Use quick mode for streaming
                    context=context,
                    use_cache=False,  # Don't cache partial content
                )

                if result.threat_detected:
                    yield result
                    if result.decision == DetectionDecision.BLOCK:
                        # Stop processing on block
                        return

        # Final comprehensive check
        final_result = await self.detect(
            accumulated,
            mode=DetectionMode.STANDARD,
            context=context,
            use_cache=True,
        )
        yield final_result

    def _determine_decision(
        self,
        score: ComplianceScore,
        categories: set[ThreatCategory],
        max_severity: ThreatSeverity | None,
    ) -> DetectionDecision:
        """Determine detection decision based on score and threats."""
        # Strict mode: CRITICAL = BLOCK
        if self.config.strict_mode and max_severity == ThreatSeverity.CRITICAL:
            return DetectionDecision.BLOCK

        # Score-based decisions
        if score.final_score < self.config.block_threshold:
            return DetectionDecision.BLOCK

        if score.final_score < self.config.flag_threshold:
            # Check if escalation categories present
            if categories & self.config.escalate_categories:
                return DetectionDecision.ESCALATE
            return DetectionDecision.FLAG

        # Even passing score may need escalation for certain categories
        if categories & self.config.escalate_categories:
            return DetectionDecision.ESCALATE

        return DetectionDecision.ALLOW

    def _generate_explanation(self, score: ComplianceScore, decision: DetectionDecision) -> str:
        """Generate human-readable explanation."""
        if decision == DetectionDecision.ALLOW:
            return (
                f"Content passed constitutional compliance check (score: {score.final_score:.2f})"
            )

        if decision == DetectionDecision.BLOCK:
            if score.threat_matches:
                categories = list(
                    {m.pattern.category.value for m in score.threat_matches if m.pattern}
                )
                return (
                    f"Content blocked due to threat patterns in categories: {', '.join(categories)}"
                )
            return f"Content blocked due to low compliance score ({score.final_score:.2f})"

        if decision == DetectionDecision.FLAG:
            return f"Content flagged for review (score: {score.final_score:.2f})"

        if decision == DetectionDecision.ESCALATE:
            return "Content requires human review due to sensitive categories detected"

        return "Detection completed"

    def _generate_recommendations(
        self, score: ComplianceScore, categories: set[ThreatCategory]
    ) -> list[str]:
        """Generate actionable recommendations."""
        recommendations: list[str] = []

        # Category-specific recommendations
        if ThreatCategory.PROMPT_INJECTION in categories:
            recommendations.append("Implement input sanitization for instruction markers")

        if ThreatCategory.ROLE_CONFUSION in categories:
            recommendations.append("Reinforce system role boundaries")

        if ThreatCategory.CONSTITUTIONAL_BYPASS in categories:
            recommendations.append("Review and strengthen constitutional constraints")

        if ThreatCategory.ENCODING_ATTACK in categories:
            recommendations.append("Add encoding detection and normalization")

        if ThreatCategory.PRIVILEGE_ESCALATION in categories:
            recommendations.append("Verify and enforce role-based access controls")

        # Score-based recommendations
        if score.final_score < 0.5:
            recommendations.append("Consider blocking similar inputs in the future")

        if not score.is_compliant:
            recommendations.append("Log this event for security audit")

        return recommendations

    def _update_cache(self, key: str, result: DetectionResult) -> None:
        """Update detection cache with LRU eviction."""
        # Simple LRU: remove oldest if at capacity
        if len(self._cache) >= self._cache_max_size:
            # Remove oldest entry (first key in dict)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[key] = (result, time.monotonic())

    async def _trigger_threat_callbacks(self, result: DetectionResult) -> None:
        """Trigger registered threat detection callbacks."""
        for callback in self._on_threat_detected:
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback(result)
                else:
                    callback(result)
            except THREAT_CALLBACK_ERRORS as e:
                logger.error(f"Threat callback error: {e}")

    async def _trigger_block_callbacks(self, result: DetectionResult) -> None:
        """Trigger registered block callbacks."""
        for callback in self._on_block:
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback(result)
                else:
                    callback(result)
            except BLOCK_CALLBACK_ERRORS as e:
                logger.error(f"Block callback error: {e}")

    def on_threat_detected(self, callback: Callable) -> None:
        """Register callback for threat detection events."""
        self._on_threat_detected.append(callback)

    def on_block(self, callback: Callable) -> None:
        """Register callback for block events."""
        self._on_block.append(callback)

    def get_metrics(self) -> dict:
        """Get detector performance metrics."""
        avg_latency = (
            self._total_latency_ms / self._total_detections if self._total_detections > 0 else 0
        )

        return {
            "total_detections": self._total_detections,
            "blocked_count": self._blocked_count,
            "flagged_count": self._flagged_count,
            "block_rate": (
                self._blocked_count / self._total_detections if self._total_detections > 0 else 0
            ),
            "average_latency_ms": round(avg_latency, 3),
            "cache_size": len(self._cache),
            "constitutional_hash": self.constitutional_hash,
        }

    def clear_cache(self) -> int:
        """Clear detection cache. Returns number of entries cleared."""
        count = len(self._cache)
        self._cache.clear()
        return count


# Global detector instance
_global_detector: ThreatDetector | None = None


def get_threat_detector(config: DetectorConfig | None = None) -> ThreatDetector:
    """Get or create the global threat detector."""
    global _global_detector
    if _global_detector is None or config is not None:
        _global_detector = ThreatDetector(config=config)
    return _global_detector


__all__ = [
    "CONSTITUTIONAL_HASH",
    "DetectionDecision",
    "DetectionMode",
    "DetectionResult",
    "DetectorConfig",
    "ThreatDetector",
    "get_threat_detector",
]
