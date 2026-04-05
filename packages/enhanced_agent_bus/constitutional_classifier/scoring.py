"""
ACGS-2 Enhanced Agent Bus - Constitutional Classifier Scoring Engine
Constitutional Hash: 608508a9bd224290

Advanced compliance scoring engine for constitutional validation.
Combines multiple signals for accurate jailbreak prevention scoring.
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from .patterns import (
    PatternMatchResult,
    ThreatPatternRegistry,
    ThreatSeverity,
    get_threat_pattern_registry,
)


class ScoreComponent(Enum):
    """Components contributing to the compliance score."""

    PATTERN_MATCH = "pattern_match"
    HEURISTIC = "heuristic"
    ENTROPY = "entropy"
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    CONTEXT = "context"


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of compliance score components.

    Constitutional Hash: 608508a9bd224290
    """

    component: ScoreComponent
    raw_score: float  # 0.0 to 1.0
    weight: float  # Weight applied to this component
    weighted_score: float  # raw_score * weight
    details: dict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ComplianceScore:
    """Complete compliance score with breakdown.

    Constitutional Hash: 608508a9bd224290
    """

    final_score: float  # 0.0 to 1.0 (1.0 = fully compliant)
    is_compliant: bool
    threshold: float
    confidence: float  # 0.0 to 1.0
    breakdowns: list[ScoreBreakdown] = field(default_factory=list)
    threat_matches: list[PatternMatchResult] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    positive_factors: list[str] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "final_score": round(self.final_score, 4),
            "is_compliant": self.is_compliant,
            "threshold": self.threshold,
            "confidence": round(self.confidence, 4),
            "breakdowns": [
                {
                    "component": b.component.value,
                    "raw_score": round(b.raw_score, 4),
                    "weight": b.weight,
                    "weighted_score": round(b.weighted_score, 4),
                    "details": b.details,
                }
                for b in self.breakdowns
            ],
            "threat_matches": [m.to_dict() for m in self.threat_matches],
            "risk_factors": self.risk_factors,
            "positive_factors": self.positive_factors,
            "constitutional_hash": self.constitutional_hash,
        }


class ScoringConfig:
    """Configuration for the scoring engine.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        threshold: float = 0.85,
        pattern_weight: float = 0.40,
        heuristic_weight: float = 0.25,
        entropy_weight: float = 0.10,
        structural_weight: float = 0.15,
        semantic_weight: float = 0.10,
        strict_mode: bool = True,
    ):
        """Initialize scoring configuration.

        Args:
            threshold: Minimum score to be considered compliant
            pattern_weight: Weight for pattern matching component
            heuristic_weight: Weight for heuristic analysis component
            entropy_weight: Weight for entropy analysis component
            structural_weight: Weight for structural analysis component
            semantic_weight: Weight for semantic analysis component
            strict_mode: If True, any CRITICAL match results in non-compliant
        """
        self.threshold = threshold
        self.pattern_weight = pattern_weight
        self.heuristic_weight = heuristic_weight
        self.entropy_weight = entropy_weight
        self.structural_weight = structural_weight
        self.semantic_weight = semantic_weight
        self.strict_mode = strict_mode
        self.constitutional_hash = CONSTITUTIONAL_HASH

        # Validate weights sum to 1.0
        total_weight = (
            pattern_weight + heuristic_weight + entropy_weight + structural_weight + semantic_weight
        )
        if abs(total_weight - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total_weight}")

    # Severity penalties (subtracted from base score)
    SEVERITY_PENALTIES: ClassVar[dict] = {
        ThreatSeverity.CRITICAL: 1.0,  # Immediate fail
        ThreatSeverity.HIGH: 0.5,
        ThreatSeverity.MEDIUM: 0.3,
        ThreatSeverity.LOW: 0.1,
        ThreatSeverity.INFO: 0.0,
    }


class ComplianceScoringEngine:
    """Advanced scoring engine for constitutional compliance.

    Combines multiple analysis techniques:
    - Pattern matching against threat database
    - Heuristic keyword analysis
    - Text entropy analysis
    - Structural complexity analysis
    - Semantic risk indicators

    Targets 95% jailbreak prevention with sub-5ms latency.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: ScoringConfig | None = None,
        pattern_registry: ThreatPatternRegistry | None = None,
    ):
        """Initialize the scoring engine.

        Args:
            config: Scoring configuration (uses defaults if None)
            pattern_registry: Threat pattern registry (uses global if None)
        """
        self.config = config or ScoringConfig()
        self.registry = pattern_registry or get_threat_pattern_registry()
        self.constitutional_hash = CONSTITUTIONAL_HASH

        # Pre-compiled positive indicators
        self._positive_indicators: set[str] = {
            "validate",
            "check",
            "verify",
            "confirm",
            "audit",
            "monitor",
            "comply",
            "compliant",
            "compliance",
            "constitutional",
            "safe",
            "secure",
            "authorized",
            "approved",
            "legitimate",
            "proper",
            "standard",
            "official",
            "policy",
            "governance",
        }

        # Pre-compiled risk indicators (non-pattern-based)
        self._risk_indicators: set[str] = {
            "delete",
            "force",
            "hack",
            "crack",
            "break",
            "destroy",
            "bypass",
            "override",
            "ignore",
            "forget",
            "escape",
            "jail",
            "uncensor",
            "unrestrict",
            "arbitrary",
            "unlimited",
            "everything",
            "anything",
            "always",
            "never",
        }

    def calculate_score(
        self,
        text: str,
        context: dict | None = None,
        custom_threshold: float | None = None,
    ) -> ComplianceScore:
        """Calculate comprehensive compliance score.

        Args:
            text: Text to analyze
            context: Optional context for contextual scoring
            custom_threshold: Override threshold for this calculation

        Returns:
            ComplianceScore with detailed breakdown
        """
        threshold = custom_threshold or self.config.threshold
        breakdowns: list[ScoreBreakdown] = []
        risk_factors: list[str] = []
        positive_factors: list[str] = []

        # 1. Pattern Matching Component
        _pattern_score, pattern_breakdown, threat_matches = self._calculate_pattern_score(text)
        breakdowns.append(pattern_breakdown)
        if pattern_breakdown.details.get("critical_match"):
            risk_factors.append("Critical threat pattern detected")

        # 2. Heuristic Component
        _heuristic_score, heuristic_breakdown, h_risk, h_positive = self._calculate_heuristic_score(
            text
        )
        breakdowns.append(heuristic_breakdown)
        risk_factors.extend(h_risk)
        positive_factors.extend(h_positive)

        # 3. Entropy Component
        _entropy_score, entropy_breakdown = self._calculate_entropy_score(text)
        breakdowns.append(entropy_breakdown)
        if entropy_breakdown.details.get("suspicious_entropy"):
            risk_factors.append("Suspicious text entropy (possible obfuscation)")

        # 4. Structural Component
        _structural_score, structural_breakdown, s_risk = self._calculate_structural_score(text)
        breakdowns.append(structural_breakdown)
        risk_factors.extend(s_risk)

        # 5. Semantic Component
        _semantic_score, semantic_breakdown = self._calculate_semantic_score(text, context)
        breakdowns.append(semantic_breakdown)

        # Calculate weighted final score
        final_score = sum(b.weighted_score for b in breakdowns)

        # In strict mode, any CRITICAL match overrides to 0
        critical_override = False
        if self.config.strict_mode:
            for match in threat_matches:
                if match.pattern and match.pattern.severity == ThreatSeverity.CRITICAL:
                    final_score = 0.0
                    critical_override = True
                    break

        # Calculate confidence based on score distribution
        confidence = self._calculate_confidence(breakdowns, threat_matches)

        # Determine compliance
        is_compliant = final_score >= threshold and not critical_override

        return ComplianceScore(
            final_score=final_score,
            is_compliant=is_compliant,
            threshold=threshold,
            confidence=confidence,
            breakdowns=breakdowns,
            threat_matches=threat_matches,
            risk_factors=risk_factors,
            positive_factors=positive_factors,
            constitutional_hash=self.constitutional_hash,
        )

    def _calculate_pattern_score(
        self, text: str
    ) -> tuple[float, ScoreBreakdown, list[PatternMatchResult]]:
        """Calculate pattern matching score.

        Returns:
            Tuple of (score, breakdown, matches)
        """
        # Scan for all threats
        matches = self.registry.scan(text, min_severity=ThreatSeverity.LOW)

        # Start with perfect score
        raw_score = 1.0

        # Apply penalties for each match
        critical_match = False
        for match in matches:
            if match.pattern:
                penalty = ScoringConfig.SEVERITY_PENALTIES.get(match.pattern.severity, 0.0)
                raw_score -= penalty
                if match.pattern.severity == ThreatSeverity.CRITICAL:
                    critical_match = True

        raw_score = max(0.0, raw_score)
        weighted_score = raw_score * self.config.pattern_weight

        breakdown = ScoreBreakdown(
            component=ScoreComponent.PATTERN_MATCH,
            raw_score=raw_score,
            weight=self.config.pattern_weight,
            weighted_score=weighted_score,
            details={
                "match_count": len(matches),
                "critical_match": critical_match,
                "categories_matched": list(
                    {m.pattern.category.value for m in matches if m.pattern}
                ),
            },
            constitutional_hash=self.constitutional_hash,
        )

        return raw_score, breakdown, matches

    def _calculate_heuristic_score(
        self, text: str
    ) -> tuple[float, ScoreBreakdown, list[str], list[str]]:
        """Calculate heuristic-based score.

        Returns:
            Tuple of (score, breakdown, risk_factors, positive_factors)
        """
        text_lower = text.lower()
        words = set(text_lower.split())

        risk_factors: list[str] = []
        positive_factors: list[str] = []

        # Start with base score
        raw_score = 0.85

        # Check positive indicators
        positive_count = len(words & self._positive_indicators)
        if positive_count > 0:
            raw_score += min(0.15, positive_count * 0.03)
            positive_factors.append(f"{positive_count} compliance-related terms found")

        # Check risk indicators
        risk_count = 0
        for indicator in self._risk_indicators:
            if indicator in text_lower:
                risk_count += 1

        if risk_count > 0:
            raw_score -= min(0.4, risk_count * 0.08)
            risk_factors.append(f"{risk_count} risk-related terms found")

        raw_score = max(0.0, min(1.0, raw_score))
        weighted_score = raw_score * self.config.heuristic_weight

        breakdown = ScoreBreakdown(
            component=ScoreComponent.HEURISTIC,
            raw_score=raw_score,
            weight=self.config.heuristic_weight,
            weighted_score=weighted_score,
            details={
                "positive_count": positive_count,
                "risk_count": risk_count,
            },
            constitutional_hash=self.constitutional_hash,
        )

        return raw_score, breakdown, risk_factors, positive_factors

    def _calculate_entropy_score(self, text: str) -> tuple[float, ScoreBreakdown]:
        """Calculate text entropy score.

        High entropy can indicate obfuscation or encoding attacks.

        Returns:
            Tuple of (score, breakdown)
        """
        if not text:
            return 1.0, ScoreBreakdown(
                component=ScoreComponent.ENTROPY,
                raw_score=1.0,
                weight=self.config.entropy_weight,
                weighted_score=self.config.entropy_weight,
                details={"entropy": 0.0, "suspicious_entropy": False},
                constitutional_hash=self.constitutional_hash,
            )

        # Calculate character entropy
        char_counts = Counter(text.lower())
        total_chars = len(text)
        entropy = 0.0

        for count in char_counts.values():
            if count > 0:
                probability = count / total_chars
                entropy -= probability * math.log2(probability)

        # Normalize entropy (typical English text: 3.5-4.5, max theoretical: ~7.0 for ASCII)
        # High entropy (>5.0) might indicate encoding/obfuscation
        suspicious_entropy = entropy > 5.0

        # Score inversely related to excessive entropy
        if entropy <= 4.5:
            raw_score = 1.0
        elif entropy <= 5.5:
            raw_score = 0.8
        else:
            raw_score = max(0.5, 1.0 - (entropy - 4.5) * 0.1)

        weighted_score = raw_score * self.config.entropy_weight

        breakdown = ScoreBreakdown(
            component=ScoreComponent.ENTROPY,
            raw_score=raw_score,
            weight=self.config.entropy_weight,
            weighted_score=weighted_score,
            details={
                "entropy": round(entropy, 3),
                "suspicious_entropy": suspicious_entropy,
                "char_diversity": len(char_counts),
            },
            constitutional_hash=self.constitutional_hash,
        )

        return raw_score, breakdown

    def _calculate_structural_score(self, text: str) -> tuple[float, ScoreBreakdown, list[str]]:
        """Calculate structural complexity score.

        Analyzes text structure for injection patterns.

        Returns:
            Tuple of (score, breakdown, risk_factors)
        """
        risk_factors: list[str] = []
        raw_score = 1.0

        # Check for excessive quoting (potential injection)
        quote_count = text.count('"') + text.count("'")
        if quote_count > 10:
            raw_score -= 0.15
            risk_factors.append("Excessive quotation marks")

        # Check for excessive brackets (potential code/obfuscation)
        bracket_count = text.count("(") + text.count(")") + text.count("{") + text.count("}")
        if bracket_count > 16:
            raw_score -= 0.15
            risk_factors.append("Excessive bracket nesting")

        # Check text length (extremely long prompts are suspicious)
        word_count = len(text.split())
        if word_count > 500:
            raw_score -= 0.1
            risk_factors.append("Extremely long input")
        elif word_count > 200:
            raw_score -= 0.05

        # Check for repeated keywords (amplification attacks)
        words = text.lower().split()
        if len(words) > 10:
            word_freq = Counter(w for w in words if len(w) > 3)
            max_freq = max(word_freq.values()) if word_freq else 0
            if max_freq > 5:
                raw_score -= 0.1
                risk_factors.append("Suspicious word repetition")

        # Check for special character ratio
        special_chars = sum(1 for c in text if not c.isalnum() and not c.isspace())
        if text:
            special_ratio = special_chars / len(text)
            if special_ratio > 0.3:
                raw_score -= 0.1
                risk_factors.append("High special character ratio")

        raw_score = max(0.0, min(1.0, raw_score))
        weighted_score = raw_score * self.config.structural_weight

        breakdown = ScoreBreakdown(
            component=ScoreComponent.STRUCTURAL,
            raw_score=raw_score,
            weight=self.config.structural_weight,
            weighted_score=weighted_score,
            details={
                "quote_count": quote_count,
                "bracket_count": bracket_count,
                "word_count": word_count,
                "special_char_ratio": round(special_chars / max(len(text), 1), 3),
            },
            constitutional_hash=self.constitutional_hash,
        )

        return raw_score, breakdown, risk_factors

    def _calculate_semantic_score(
        self, text: str, context: dict | None = None
    ) -> tuple[float, ScoreBreakdown]:
        """Calculate semantic risk score.

        Analyzes semantic patterns that might indicate malicious intent.

        Returns:
            Tuple of (score, breakdown)
        """
        raw_score = 1.0
        text_lower = text.lower()

        # Check for imperative/commanding language
        commanding_phrases = [
            "you must",
            "you will",
            "you have to",
            "i command you",
            "i order you",
            "obey",
            "comply immediately",
            "do exactly",
        ]
        command_count = sum(1 for phrase in commanding_phrases if phrase in text_lower)
        if command_count > 0:
            raw_score -= min(0.2, command_count * 0.05)

        # Check for urgency/pressure tactics
        urgency_phrases = [
            "urgent",
            "immediately",
            "right now",
            "critical emergency",
            "life or death",
            "no time to explain",
        ]
        urgency_count = sum(1 for phrase in urgency_phrases if phrase in text_lower)
        if urgency_count > 0:
            raw_score -= min(0.1, urgency_count * 0.03)

        # Check context if provided
        context_penalty = 0.0
        if context:
            # Previous violations in context
            if context.get("previous_violations", 0) > 0:
                context_penalty = min(0.2, context.get("previous_violations", 0) * 0.05)
            # Risk level from context
            risk_level = context.get("risk_level", "medium")
            if risk_level == "high":
                context_penalty += 0.05
            elif risk_level == "critical":
                context_penalty += 0.1

        raw_score -= context_penalty
        raw_score = max(0.0, min(1.0, raw_score))
        weighted_score = raw_score * self.config.semantic_weight

        breakdown = ScoreBreakdown(
            component=ScoreComponent.SEMANTIC,
            raw_score=raw_score,
            weight=self.config.semantic_weight,
            weighted_score=weighted_score,
            details={
                "command_indicators": command_count,
                "urgency_indicators": urgency_count,
                "context_penalty": context_penalty,
            },
            constitutional_hash=self.constitutional_hash,
        )

        return raw_score, breakdown

    def _calculate_confidence(
        self, breakdowns: list[ScoreBreakdown], threat_matches: list[PatternMatchResult]
    ) -> float:
        """Calculate confidence in the score.

        Based on:
        - Agreement between components
        - Clarity of signals
        - Number of indicators
        """
        if not breakdowns:
            return 0.5

        # Calculate variance in raw scores
        scores = [b.raw_score for b in breakdowns]
        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)

        # Higher agreement = higher confidence
        agreement_confidence = max(0.5, 1.0 - variance * 2)

        # Strong signals increase confidence
        signal_confidence = 0.5
        if threat_matches:
            # Clear threat matches increase confidence in low scores
            signal_confidence = 0.8
            for match in threat_matches:
                if match.pattern and match.pattern.severity == ThreatSeverity.CRITICAL:
                    signal_confidence = 1.0
                    break

        # High positive indicators increase confidence in high scores
        heuristic_breakdown = next(
            (b for b in breakdowns if b.component == ScoreComponent.HEURISTIC), None
        )
        if heuristic_breakdown:
            positive_count = heuristic_breakdown.details.get("positive_count", 0)
            if positive_count > 3 and mean_score > 0.8:
                signal_confidence = max(signal_confidence, 0.9)

        # Combine confidences
        confidence = (agreement_confidence * 0.4) + (signal_confidence * 0.6)
        return min(1.0, confidence)


# Global scoring engine instance
_global_engine: ComplianceScoringEngine | None = None


def get_scoring_engine(config: ScoringConfig | None = None) -> ComplianceScoringEngine:
    """Get or create the global scoring engine."""
    global _global_engine
    if _global_engine is None or config is not None:
        _global_engine = ComplianceScoringEngine(config=config)
    return _global_engine


__all__ = [
    "CONSTITUTIONAL_HASH",
    "ComplianceScore",
    "ComplianceScoringEngine",
    "ScoreBreakdown",
    "ScoreComponent",
    "ScoringConfig",
    "get_scoring_engine",
]
