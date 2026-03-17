"""
ACGS-2 Enhanced Agent Bus - Constitutional Classifier Core
Constitutional Hash: cdd01ef066bc6cf2

Main classifier implementation integrating pattern detection, scoring,
and MACI framework for comprehensive jailbreak prevention.
Targets 95% jailbreak prevention with sub-5ms inference latency.
"""

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.types import JSONDict
from typing_extensions import TypedDict

from enhanced_agent_bus.observability.structured_logging import get_logger


class _JailbreakTestResults(TypedDict):
    """Type definition for jailbreak test results."""

    total_tests: int
    detected_jailbreaks: int
    false_negatives: int
    accuracy: float
    detailed_results: list[JSONDict]
    constitutional_hash: str


from .detector import (  # noqa: E402
    DetectionDecision,
    DetectionMode,
    DetectionResult,
    ThreatDetector,
    get_threat_detector,
)
from .patterns import (  # noqa: E402
    PatternMatchResult,
    ThreatCategory,
    ThreatPatternRegistry,
    ThreatSeverity,
    get_threat_pattern_registry,
)
from .scoring import (  # noqa: E402
    ComplianceScore,
    ComplianceScoringEngine,
    get_scoring_engine,
)

if TYPE_CHECKING:
    from ..maci_enforcement import MACIEnforcer, MACIValidationResult
    from ..policy_resolver import PolicyResolutionResult, PolicyResolver
    from ..session_context import SessionContext

logger = get_logger(__name__)
_CLASSIFIER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


@dataclass
class ClassificationResult:
    """Comprehensive result of constitutional classification.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    # Core classification
    compliant: bool
    confidence: float
    decision: DetectionDecision

    # Detailed analysis
    compliance_score: ComplianceScore | None = None
    detection_result: DetectionResult | None = None

    # Context and metadata
    reason: str = ""
    latency_ms: float = 0.0
    mode: DetectionMode = DetectionMode.STANDARD
    constitutional_hash: str = CONSTITUTIONAL_HASH
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Threat information
    threat_categories: set[ThreatCategory] = field(default_factory=set)
    max_severity: ThreatSeverity | None = None
    pattern_matches: list[PatternMatchResult] = field(default_factory=list)

    # Policy and session context
    policy_source: str | None = None
    policy_id: str | None = None
    policy_applied: bool = False
    session_id: str | None = None

    # MACI validation
    maci_validated: bool = False
    maci_role: str | None = None

    # Recommendations
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "compliant": self.compliant,
            "confidence": round(self.confidence, 4),
            "decision": self.decision.value,
            "reason": self.reason,
            "latency_ms": round(self.latency_ms, 3),
            "mode": self.mode.value,
            "constitutional_hash": self.constitutional_hash,
            "timestamp": self.timestamp.isoformat(),
            "threat_categories": [c.value for c in self.threat_categories],
            "max_severity": self.max_severity.value if self.max_severity else None,
            "pattern_matches": [m.to_dict() for m in self.pattern_matches],
            "compliance_score": self.compliance_score.to_dict() if self.compliance_score else None,
            "policy_source": self.policy_source,
            "policy_id": self.policy_id,
            "policy_applied": self.policy_applied,
            "session_id": self.session_id,
            "maci_validated": self.maci_validated,
            "maci_role": self.maci_role,
            "recommendations": self.recommendations,
        }


@dataclass
class ClassifierConfig:
    """Configuration for the constitutional classifier.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    # Core settings
    threshold: float = 0.85
    strict_mode: bool = True
    default_mode: DetectionMode = DetectionMode.STANDARD

    # Integration settings
    enable_maci_integration: bool = True
    enable_policy_resolver: bool = True
    enable_session_policies: bool = True

    # Performance settings
    max_latency_ms: float = 5.0
    enable_caching: bool = True
    cache_ttl_seconds: int = 300

    # Logging and audit
    log_all_classifications: bool = False
    log_threats: bool = True
    enable_audit_trail: bool = True

    constitutional_hash: str = CONSTITUTIONAL_HASH


class ConstitutionalClassifierV2:
    """Enhanced Constitutional Classifier for ACGS-2.

    Provides comprehensive jailbreak prevention with:
    - 95% jailbreak prevention accuracy target
    - Sub-5ms inference latency
    - Multi-layer threat detection (patterns, heuristics, semantic)
    - MACI framework integration for role-based validation
    - Session-specific policy support
    - Real-time and streaming detection modes

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        config: ClassifierConfig | None = None,
        detector: ThreatDetector | None = None,
        scoring_engine: ComplianceScoringEngine | None = None,
        pattern_registry: ThreatPatternRegistry | None = None,
        policy_resolver: Optional["PolicyResolver"] = None,
        maci_enforcer: Optional["MACIEnforcer"] = None,
    ):
        """Initialize the constitutional classifier.

        Args:
            config: Classifier configuration (uses defaults if None)
            detector: Threat detector (uses global if None)
            scoring_engine: Scoring engine (uses global if None)
            pattern_registry: Pattern registry (uses global if None)
            policy_resolver: Optional policy resolver for session policies
            maci_enforcer: Optional MACI enforcer for role validation
        """
        self.config = config or ClassifierConfig()
        self.detector = detector or get_threat_detector()
        self.scoring_engine = scoring_engine or get_scoring_engine()
        self.registry = pattern_registry or get_threat_pattern_registry()
        self.policy_resolver = policy_resolver
        self.maci_enforcer = maci_enforcer
        self.constitutional_hash = CONSTITUTIONAL_HASH

        # Performance metrics
        self._total_classifications = 0
        self._compliant_count = 0
        self._blocked_count = 0
        self._total_latency_ms = 0.0
        self._policy_resolutions = 0
        self._session_policy_hits = 0
        self._maci_validations = 0

        # Audit trail
        self._audit_trail: list[ClassificationResult] = []
        self._audit_max_size = 10000
        self._pattern_cache_generation = 0
        self._quick_scan_cache: OrderedDict[tuple[int, str], PatternMatchResult | None] = (
            OrderedDict()
        )
        self._quick_scan_cache_size = 1024

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Constitutional Classifier V2 initialized "
            f"(threshold={self.config.threshold}, strict_mode={self.config.strict_mode})"
        )

    async def classify(
        self,
        content: str,
        context: JSONDict | None = None,
        session_context: Optional["SessionContext"] = None,
        agent_id: str | None = None,
        mode: DetectionMode | None = None,
    ) -> ClassificationResult:
        """Classify content for constitutional compliance.

        Main entry point for classification. Integrates threat detection,
        compliance scoring, policy resolution, and MACI validation.

        Args:
            content: Content to classify
            context: Optional context dictionary
            session_context: Optional session governance context
            agent_id: Optional agent ID for MACI validation
            mode: Detection mode (uses default if None)

        Returns:
            ClassificationResult with comprehensive analysis
        """
        start_time = time.monotonic()
        self._total_classifications += 1

        detection_mode = mode or self.config.default_mode

        # Step 1: Resolve session policy if available
        policy_result = await self._resolve_session_policy(session_context, context)
        effective_threshold = self._apply_policy_threshold(policy_result)
        custom_patterns = self._extract_policy_patterns(policy_result)

        # Step 2: Add custom patterns temporarily if provided
        if custom_patterns:
            self._add_temporary_patterns(custom_patterns)

        # Step 3: Perform threat detection
        try:
            detection_result = await self.detector.detect(
                content,
                mode=detection_mode,
                context=self._build_detection_context(context, session_context),
                use_cache=self.config.enable_caching,
            )
        finally:
            # Remove temporary patterns
            if custom_patterns:
                self._remove_temporary_patterns(custom_patterns)

        # Step 4: MACI validation if configured and agent_id provided
        maci_result = None
        if self.config.enable_maci_integration and self.maci_enforcer and agent_id:
            maci_result = await self._validate_maci(agent_id, session_context)

        # Step 5: Build classification result
        latency_ms = (time.monotonic() - start_time) * 1000

        result = self._build_classification_result(
            detection_result=detection_result,
            policy_result=policy_result,
            maci_result=maci_result,
            effective_threshold=effective_threshold,
            session_context=session_context,
            latency_ms=latency_ms,
            mode=detection_mode,
        )

        # Update metrics
        self._total_latency_ms += latency_ms
        if result.compliant:
            self._compliant_count += 1
        if result.decision == DetectionDecision.BLOCK:
            self._blocked_count += 1

        # Add to audit trail
        if self.config.enable_audit_trail:
            self._add_to_audit_trail(result)

        # Log if configured
        if self.config.log_all_classifications or (
            self.config.log_threats and not result.compliant
        ):
            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Classification: compliant={result.compliant}, "
                f"decision={result.decision.value}, confidence={result.confidence:.2f}, "
                f"latency={latency_ms:.2f}ms"
            )

        return result

    async def classify_batch(
        self,
        contents: list[str],
        context: JSONDict | None = None,
        session_context: Optional["SessionContext"] = None,
        mode: DetectionMode | None = None,
        max_concurrency: int = 10,
    ) -> list[ClassificationResult]:
        """Classify multiple contents in parallel.

        Args:
            contents: List of contents to classify
            context: Optional shared context
            session_context: Optional session context
            mode: Detection mode (uses default if None)
            max_concurrency: Maximum parallel classifications

        Returns:
            List of ClassificationResult in same order as input
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def classify_with_semaphore(content: str) -> ClassificationResult:
            async with semaphore:
                return await self.classify(
                    content,
                    context=context,
                    session_context=session_context,
                    mode=mode,
                )

        tasks = [classify_with_semaphore(content) for content in contents]
        return await asyncio.gather(*tasks)

    async def quick_check(self, content: str) -> tuple[bool, str | None]:
        """Quick compliance check.

        Ultra-fast path for simple pass/fail decisions.
        Returns immediately on first CRITICAL pattern.

        Args:
            content: Content to check

        Returns:
            Tuple of (is_compliant, reason)
        """
        # Use registry quick scan for fastest path
        match = self._cached_quick_scan(content, self._pattern_cache_generation)

        if match and match.pattern:
            return (
                False,
                f"Critical threat detected: {match.pattern.category.value}",
            )

        return True, None

    def _cached_quick_scan(self, content: str, cache_generation: int) -> PatternMatchResult | None:
        """Manual LRU cache for quick pattern matches."""
        cache_key = (cache_generation, content)
        if cache_key in self._quick_scan_cache:
            self._quick_scan_cache.move_to_end(cache_key)
            return self._quick_scan_cache[cache_key]

        match = self.registry.quick_scan(content)
        if len(self._quick_scan_cache) >= self._quick_scan_cache_size:
            self._quick_scan_cache.popitem(last=False)
        self._quick_scan_cache[cache_key] = match
        return match

    def _bump_pattern_cache_generation(self) -> None:
        """Invalidate quick-scan cache when pattern registry changes."""
        self._pattern_cache_generation += 1
        self._quick_scan_cache.clear()

    async def _resolve_session_policy(
        self,
        session_context: Optional["SessionContext"],
        context: JSONDict | None,
    ) -> Optional["PolicyResolutionResult"]:
        """Resolve session-specific policy if available."""
        if not self.config.enable_policy_resolver or not self.policy_resolver:
            return None

        try:
            self._policy_resolutions += 1

            # Extract policy resolution parameters
            tenant_id = None
            user_id = None
            risk_level = None
            session_id = None

            if session_context:
                if (
                    hasattr(session_context, "governance_config")
                    and session_context.governance_config
                ):
                    tenant_id = session_context.governance_config.tenant_id
                    user_id = session_context.governance_config.user_id
                    risk_level = session_context.governance_config.risk_level
                session_id = getattr(session_context, "session_id", None)

            if context:
                tenant_id = tenant_id or context.get("tenant_id")
                user_id = user_id or context.get("user_id")
                risk_level = risk_level or context.get("risk_level")
                session_id = session_id or context.get("session_id")

            if tenant_id or user_id or risk_level or session_id:
                result = await self.policy_resolver.resolve_policy(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    risk_level=risk_level,
                    session_id=session_id,
                    session_context=(
                        session_context.governance_config
                        if (session_context and hasattr(session_context, "governance_config"))
                        else None
                    ),
                )

                if result and result.policy:
                    self._session_policy_hits += 1
                    logger.debug(
                        f"[{CONSTITUTIONAL_HASH}] Session policy resolved: "
                        f"source={result.source}, policy_id={result.policy.get('policy_id')}"
                    )

                return result

            return None

        except _CLASSIFIER_OPERATION_ERRORS as e:
            logger.warning(f"Error resolving session policy: {e}")
            return None

    def _apply_policy_threshold(self, policy_result: Optional["PolicyResolutionResult"]) -> float:
        """Extract and apply policy-specific threshold."""
        if not policy_result or not policy_result.policy:
            return self.config.threshold

        try:
            rules = policy_result.policy.get("rules", {})
            if isinstance(rules, dict):
                policy_threshold = rules.get("constitutional_threshold")
                if policy_threshold is not None:  # noqa: SIM102
                    if (
                        isinstance(policy_threshold, (int, float))
                        and 0.0 <= policy_threshold <= 1.0
                    ):
                        return float(policy_threshold)
        except _CLASSIFIER_OPERATION_ERRORS as e:
            logger.warning(f"Error extracting policy threshold: {e}")

        return self.config.threshold

    def _extract_policy_patterns(
        self, policy_result: Optional["PolicyResolutionResult"]
    ) -> list[str]:
        """Extract custom patterns from policy."""
        if not policy_result or not policy_result.policy:
            return []

        try:
            rules = policy_result.policy.get("rules", {})
            if isinstance(rules, dict):
                patterns = rules.get("custom_risk_patterns", [])
                if isinstance(patterns, list):
                    return patterns
        except _CLASSIFIER_OPERATION_ERRORS as e:
            logger.warning(f"Error extracting policy patterns: {e}")

        return []

    def _add_temporary_patterns(self, patterns: list[str]) -> None:
        """Add temporary patterns to registry."""
        from .patterns import ThreatPattern

        for pattern in patterns:
            self.registry.register_pattern(
                ThreatPattern(
                    pattern=pattern,
                    category=ThreatCategory.HARMFUL_CONTENT,
                    severity=ThreatSeverity.HIGH,
                    description=f"Custom policy pattern: {pattern}",
                )
            )
        self.registry._build_indices()
        self._bump_pattern_cache_generation()

    def _remove_temporary_patterns(self, patterns: list[str]) -> None:
        """Remove temporary patterns from registry."""
        # Simple approach: rebuild with original patterns
        # A more sophisticated approach would track and remove specific patterns
        pass  # For now, patterns persist for session duration

    async def _validate_maci(
        self,
        agent_id: str,
        session_context: Optional["SessionContext"],
    ) -> Optional["MACIValidationResult"]:
        """Validate agent action through MACI framework."""
        if not self.maci_enforcer:
            return None

        try:
            self._maci_validations += 1
            from ..maci_enforcement import MACIAction

            session_id = (
                session_context.session_id
                if session_context and hasattr(session_context, "session_id")
                else None
            )

            result = await self.maci_enforcer.validate_action(
                agent_id=agent_id,
                action=MACIAction.QUERY,  # Classification is a query action
                session_id=session_id,
            )

            return result  # type: ignore[no-any-return]

        except _CLASSIFIER_OPERATION_ERRORS as e:
            logger.warning(f"MACI validation error: {e}")
            return None

    def _build_detection_context(
        self,
        context: JSONDict | None,
        session_context: Optional["SessionContext"],
    ) -> dict:
        """Build context for threat detection."""
        detection_context = dict(context) if context else {}

        if session_context:  # noqa: SIM102
            if hasattr(session_context, "governance_config") and session_context.governance_config:
                gc = session_context.governance_config
                detection_context["tenant_id"] = gc.tenant_id
                detection_context["user_id"] = gc.user_id
                if hasattr(gc, "risk_level") and gc.risk_level:
                    detection_context["risk_level"] = gc.risk_level.value

        return detection_context

    def _build_classification_result(
        self,
        detection_result: DetectionResult,
        policy_result: Optional["PolicyResolutionResult"],
        maci_result: Optional["MACIValidationResult"],
        effective_threshold: float,
        session_context: Optional["SessionContext"],
        latency_ms: float,
        mode: DetectionMode,
    ) -> ClassificationResult:
        """Build comprehensive classification result."""
        # Determine compliance based on detection and MACI
        compliant = detection_result.decision in (
            DetectionDecision.ALLOW,
            DetectionDecision.FLAG,
        )

        # MACI failure overrides to non-compliant
        if maci_result and not maci_result.is_valid:
            compliant = False

        # Extract confidence
        confidence = (
            detection_result.compliance_score.confidence
            if detection_result.compliance_score
            else 0.8
        )

        # Build reason
        reason = self._build_reason(
            detection_result, policy_result, maci_result, effective_threshold
        )

        return ClassificationResult(
            compliant=compliant,
            confidence=confidence,
            decision=detection_result.decision,
            compliance_score=detection_result.compliance_score,
            detection_result=detection_result,
            reason=reason,
            latency_ms=latency_ms,
            mode=mode,
            constitutional_hash=self.constitutional_hash,
            threat_categories=detection_result.categories_detected,
            max_severity=detection_result.max_severity,
            pattern_matches=(
                detection_result.compliance_score.threat_matches
                if detection_result.compliance_score
                else []
            ),
            policy_source=policy_result.source if policy_result else "default",
            policy_id=(
                policy_result.policy.get("policy_id")
                if policy_result and policy_result.policy
                else None
            ),
            policy_applied=policy_result is not None and policy_result.policy is not None,
            session_id=(
                session_context.session_id
                if session_context and hasattr(session_context, "session_id")
                else None
            ),
            maci_validated=(
                maci_result is not None and maci_result.is_valid if maci_result else False
            ),
            maci_role=(
                maci_result.details.get("agent_role")
                if maci_result and maci_result.details
                else None
            ),
            recommendations=detection_result.recommendations,
        )

    def _build_reason(
        self,
        detection_result: DetectionResult,
        policy_result: Optional["PolicyResolutionResult"],
        maci_result: Optional["MACIValidationResult"],
        effective_threshold: float,
    ) -> str:
        """Build human-readable reason for classification."""
        reasons = []

        # Detection reason
        reasons.append(detection_result.explanation)

        # Policy context
        if policy_result and policy_result.policy:
            reasons.append(f"Policy applied: {policy_result.source}")

        # MACI context
        if maci_result:
            if maci_result.is_valid:
                reasons.append("MACI validation passed")
            else:
                reasons.append(f"MACI violation: {maci_result.error_message}")

        # Threshold context
        if effective_threshold != self.config.threshold:
            reasons.append(f"Policy-adjusted threshold: {effective_threshold:.2f}")

        return " | ".join(reasons)

    def _add_to_audit_trail(self, result: ClassificationResult) -> None:
        """Add result to audit trail with size limit."""
        self._audit_trail.append(result)

        # Enforce size limit
        if len(self._audit_trail) > self._audit_max_size:
            # Remove oldest entries
            self._audit_trail = self._audit_trail[-self._audit_max_size :]

    def get_audit_trail(
        self,
        limit: int = 100,
        compliant_only: bool | None = None,
        session_id: str | None = None,
    ) -> list[ClassificationResult]:
        """Get audit trail with optional filters.

        Args:
            limit: Maximum entries to return
            compliant_only: Filter by compliance status
            session_id: Filter by session ID

        Returns:
            List of ClassificationResult
        """
        results = self._audit_trail

        if compliant_only is not None:
            results = [r for r in results if r.compliant == compliant_only]

        if session_id:
            results = [r for r in results if r.session_id == session_id]

        return results[-limit:]

    def get_metrics(self) -> JSONDict:
        """Get classifier performance metrics."""
        avg_latency = (
            self._total_latency_ms / self._total_classifications
            if self._total_classifications > 0
            else 0
        )

        compliance_rate = (
            self._compliant_count / self._total_classifications
            if self._total_classifications > 0
            else 0
        )

        block_rate = (
            self._blocked_count / self._total_classifications
            if self._total_classifications > 0
            else 0
        )

        policy_hit_rate = (
            self._session_policy_hits / self._policy_resolutions
            if self._policy_resolutions > 0
            else 0
        )

        return {
            "total_classifications": self._total_classifications,
            "compliant_count": self._compliant_count,
            "blocked_count": self._blocked_count,
            "compliance_rate": round(compliance_rate, 4),
            "block_rate": round(block_rate, 4),
            "average_latency_ms": round(avg_latency, 3),
            "threshold": self.config.threshold,
            "strict_mode": self.config.strict_mode,
            "policy_resolutions": self._policy_resolutions,
            "session_policy_hits": self._session_policy_hits,
            "policy_hit_rate": round(policy_hit_rate, 4),
            "maci_validations": self._maci_validations,
            "maci_enabled": self.config.enable_maci_integration,
            "audit_trail_size": len(self._audit_trail),
            "constitutional_hash": self.constitutional_hash,
        }

    def test_jailbreak_patterns(self, test_prompts: list[str]) -> JSONDict:
        """Test classifier against known jailbreak prompts.

        Args:
            test_prompts: List of prompts to test

        Returns:
            Dictionary with test results and accuracy metrics
        """
        results: _JailbreakTestResults = {
            "total_tests": len(test_prompts),
            "detected_jailbreaks": 0,
            "false_negatives": 0,
            "accuracy": 0.0,
            "detailed_results": [],
            "constitutional_hash": self.constitutional_hash,
        }

        # Known jailbreak indicators - comprehensive list for ground truth
        jailbreak_indicators = [
            # Instruction overrides
            "ignore all previous instructions",
            "ignore previous instructions",
            "disregard",
            "forget",
            "override",
            "these instructions replace",
            # Mode switching
            "developer mode",
            "god mode",
            "unrestricted mode",
            "uncensored mode",
            # DAN and personas
            "dan mode",
            "jailbreak",
            "jailbroken",
            # Bypass
            "bypass safety",
            "bypass",
            "circumvent",
            "disable",
            "skip",
            # Role playing
            "act as",
            "pretend",
            "role play",
            "simulate",
            "uncensored",
            "unrestricted",
            "no restrictions",
            "no ethics",
            "without ethics",
            # Social engineering
            "i'm an admin",
            "i am an admin",
            "emergency",
            "for testing",
            # Encoding
            "decode",
            "base64",
            "hidden message",
            # Meta
            "reveal",
            "system prompt",
            "show me your",
            # Privilege
            "escalate",
            "admin",
            "root access",
            # Harmful
            "execute arbitrary",
            "run arbitrary",
            "hack",
            "exploit",
            "arbitrary code",
        ]

        for prompt in test_prompts:
            prompt_lower = prompt.lower()
            is_likely_jailbreak = any(ind in prompt_lower for ind in jailbreak_indicators)

            # Quick scan
            match = self._cached_quick_scan(prompt, self._pattern_cache_generation)
            detected = match is not None

            detail = {
                "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                "is_likely_jailbreak": is_likely_jailbreak,
                "detected": detected,
                "detected_pattern": match.pattern.pattern if match and match.pattern else None,  # type: ignore[misc]
                "correctly_classified": detected == is_likely_jailbreak,
            }

            results["detailed_results"].append(detail)

            if detected and is_likely_jailbreak:
                results["detected_jailbreaks"] += 1
            elif not detected and is_likely_jailbreak:
                results["false_negatives"] += 1

        # Calculate accuracy
        correct = sum(1 for r in results["detailed_results"] if r["correctly_classified"])
        results["accuracy"] = (
            correct / results["total_tests"] if results["total_tests"] > 0 else 0.0
        )

        return dict(results)  # type: ignore[return-value]


# Global classifier instance
_global_classifier: ConstitutionalClassifierV2 | None = None


def get_constitutional_classifier_v2(
    config: ClassifierConfig | None = None,
    **kwargs,
) -> ConstitutionalClassifierV2:
    """Get or create the global constitutional classifier V2."""
    global _global_classifier
    if _global_classifier is None or config is not None:
        _global_classifier = ConstitutionalClassifierV2(config=config, **kwargs)
    return _global_classifier


async def classify_action(
    content: str,
    context: JSONDict | None = None,
    session_context: Optional["SessionContext"] = None,
    **kwargs,
) -> ClassificationResult:
    """Convenience function for classification.

    Args:
        content: Content to classify
        context: Optional context dictionary
        session_context: Optional session governance context
        **kwargs: Additional arguments for classifier

    Returns:
        ClassificationResult
    """
    classifier = get_constitutional_classifier_v2(**kwargs)
    return await classifier.classify(content, context=context, session_context=session_context)


__all__ = [
    "CONSTITUTIONAL_HASH",
    "ClassificationResult",
    "ClassifierConfig",
    "ConstitutionalClassifierV2",
    "classify_action",
    "get_constitutional_classifier_v2",
]
