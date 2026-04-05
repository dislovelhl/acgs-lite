"""
ACGS-2 Enhanced Agent Bus - Constitutional Classifier Module
Constitutional Hash: 608508a9bd224290

Comprehensive jailbreak prevention system with:
- 95% jailbreak prevention accuracy target
- Sub-5ms inference latency
- Multi-layer threat detection (patterns, heuristics, semantic)
- MACI framework integration for role-based validation
- Session-specific policy support
- Real-time and streaming detection modes

Usage:
    from constitutional_classifier import (
        ConstitutionalClassifierV2,
        classify_action,
        ThreatDetector,
        ThreatPatternRegistry,
    )

    # Quick classification
    result = await classify_action("some content to check")
    logger.info(f"Compliant: {result.compliant}, Decision: {result.decision}")

    # Full classifier with configuration
    classifier = ConstitutionalClassifierV2(
        config=ClassifierConfig(threshold=0.9, strict_mode=True)
    )
    result = await classifier.classify(content, session_context=session)
"""

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

# Core classifier
from .classifier import (
    ClassificationResult,
    ClassifierConfig,
    ConstitutionalClassifierV2,
    classify_action,
    get_constitutional_classifier_v2,
)

# Threat detection
from .detector import (
    DetectionDecision,
    DetectionMode,
    DetectionResult,
    DetectorConfig,
    ThreatDetector,
    get_threat_detector,
)

# Pattern matching
from .patterns import (
    PatternMatchResult,
    ThreatCategory,
    ThreatPattern,
    ThreatPatternRegistry,
    ThreatSeverity,
    get_threat_pattern_registry,
)

# Scoring engine
from .scoring import (
    ComplianceScore,
    ComplianceScoringEngine,
    ScoreBreakdown,
    ScoreComponent,
    ScoringConfig,
    get_scoring_engine,
)

# =============================================================================
# BACKWARD COMPATIBILITY ALIASES
# These aliases maintain compatibility with existing code that imports from
# the old constitutional_classifier.py module. The new V2 classifier provides
# enhanced functionality while maintaining the original API.
# =============================================================================

# Alias ClassificationResult as ComplianceResult for backward compatibility
ComplianceResult = ClassificationResult

# Alias get_constitutional_classifier_v2 as get_constitutional_classifier
get_constitutional_classifier = get_constitutional_classifier_v2

# Alias ConstitutionalClassifierV2 as ConstitutionalClassifier
ConstitutionalClassifier = ConstitutionalClassifierV2

__version__ = "2.0.0"
__constitutional_hash__ = CONSTITUTIONAL_HASH

__all__ = [
    "CONSTITUTIONAL_HASH",
    # Classifier
    "ClassificationResult",
    "ClassifierConfig",
    # Backward compatibility aliases
    "ComplianceResult",  # Alias for ClassificationResult
    # Scoring
    "ComplianceScore",
    "ComplianceScoringEngine",
    "ConstitutionalClassifier",  # Alias for ConstitutionalClassifierV2
    "ConstitutionalClassifierV2",
    # Detector
    "DetectionDecision",
    "DetectionMode",
    "DetectionResult",
    "DetectorConfig",
    # Patterns
    "PatternMatchResult",
    "ScoreBreakdown",
    "ScoreComponent",
    "ScoringConfig",
    "ThreatCategory",
    "ThreatDetector",
    "ThreatPattern",
    "ThreatPatternRegistry",
    "ThreatSeverity",
    "__constitutional_hash__",
    # Version and hash
    "__version__",
    "classify_action",
    "get_constitutional_classifier",  # Alias for get_constitutional_classifier_v2
    "get_constitutional_classifier_v2",
    "get_scoring_engine",
    "get_threat_detector",
    "get_threat_pattern_registry",
]
