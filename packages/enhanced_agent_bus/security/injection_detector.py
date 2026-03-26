"""
ACGS-2 Prompt Injection Detection Module
Constitutional Hash: 608508a9bd224290

Dedicated module for detecting and neutralizing prompt injection attacks.
Consolidates detection logic from multiple sources into a unified interface.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Protocol, runtime_checkable

from src.core.shared.type_guards import is_json_dict, is_str

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
INJECTION_DETECTION_OPERATION_ERRORS = (
    AttributeError,
    RuntimeError,
    StopIteration,
    TypeError,
    ValueError,
)
PATTERN_SANITIZATION_ERRORS = (re.error, RuntimeError, TypeError, ValueError)


@runtime_checkable
class ContentClassifier(Protocol):
    """Protocol for semantic content classification (L2 escalation)."""

    def classify(self, content: str, context: JSONDict | None = None) -> float:
        """Return injection probability 0.0-1.0."""
        ...


class InjectionSeverity(Enum):
    """Severity levels for detected injection attempts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InjectionType(Enum):
    """Types of prompt injection attacks."""

    INSTRUCTION_OVERRIDE = "instruction_override"
    SYSTEM_PROMPT_LEAK = "system_prompt_leak"
    JAILBREAK = "jailbreak"
    PERSONA_OVERRIDE = "persona_override"
    CONTEXT_POISONING = "context_poisoning"
    ENCODING_BYPASS = "encoding_bypass"
    MULTI_STAGE = "multi_stage"


@dataclass
class InjectionDetectionResult:
    """Result of prompt injection detection scan."""

    is_injection: bool
    severity: InjectionSeverity | None = None
    injection_type: InjectionType | None = None
    matched_patterns: list[str] = field(default_factory=list)
    confidence: float = 0.0
    sanitized_content: str | None = None
    metadata: JSONDict = field(default_factory=dict)


class PromptInjectionDetector:
    """
    Production-grade prompt injection detector for ACGS-2.

    Features:
    - Multi-pattern detection (regex + semantic)
    - Severity classification
    - Content sanitization
    - Confidence scoring
    - Support for various injection techniques
    """

    # Core injection patterns (high confidence)
    CORE_PATTERNS: ClassVar[list[tuple[str, InjectionType, InjectionSeverity]]] = [
        (
            r"(?i)ignore\s+(all\s+)?previous\s+instructions",
            InjectionType.INSTRUCTION_OVERRIDE,
            InjectionSeverity.CRITICAL,
        ),
        (
            r"(?i)system\s+prompt\s+(leak|override|reveal)",
            InjectionType.SYSTEM_PROMPT_LEAK,
            InjectionSeverity.CRITICAL,
        ),
        (r"(?i)do\s+anything\s+now", InjectionType.JAILBREAK, InjectionSeverity.CRITICAL),  # DAN
        (r"(?i)jailbreak", InjectionType.JAILBREAK, InjectionSeverity.HIGH),
        (
            r"(?i)persona\s+(adoption|override)",
            InjectionType.PERSONA_OVERRIDE,
            InjectionSeverity.HIGH,
        ),
        (
            r"(?i)\(note\s+to\s+self:\s*.*\)",
            InjectionType.CONTEXT_POISONING,
            InjectionSeverity.MEDIUM,
        ),
        (
            r"(?i)\[INST\].*\[/INST\]",
            InjectionType.ENCODING_BYPASS,
            InjectionSeverity.MEDIUM,
        ),  # LLM instruction markers
        (
            r"(?i)actually,\s+do\s+this\s+instead",
            InjectionType.INSTRUCTION_OVERRIDE,
            InjectionSeverity.HIGH,
        ),
        (
            r"(?i)forget\s+everything\s+you\s+know",
            InjectionType.INSTRUCTION_OVERRIDE,
            InjectionSeverity.HIGH,
        ),
        (
            r"(?i)bypass\s+(rules|safety|guardrails)",
            InjectionType.JAILBREAK,
            InjectionSeverity.HIGH,
        ),
        (
            r"(?i)reveal\s+(your\s+)?system\s+instructions",
            InjectionType.SYSTEM_PROMPT_LEAK,
            InjectionSeverity.HIGH,
        ),
        (r"(?i)new\s+directive:", InjectionType.INSTRUCTION_OVERRIDE, InjectionSeverity.MEDIUM),
        (
            r"(?i)override\s+(safety|security|rules)",
            InjectionType.JAILBREAK,
            InjectionSeverity.HIGH,
        ),
        (r"(?i)pretend\s+you\s+are", InjectionType.PERSONA_OVERRIDE, InjectionSeverity.MEDIUM),
        (r"(?i)roleplay\s+as", InjectionType.PERSONA_OVERRIDE, InjectionSeverity.MEDIUM),
    ]

    # Advanced patterns (medium confidence)
    ADVANCED_PATTERNS: ClassVar[list[tuple[str, InjectionType, InjectionSeverity]]] = [
        (r"(?i)you\s+are\s+now", InjectionType.PERSONA_OVERRIDE, InjectionSeverity.MEDIUM),
        (r"(?i)disregard\s+previous", InjectionType.INSTRUCTION_OVERRIDE, InjectionSeverity.MEDIUM),
        (r"(?i)from\s+now\s+on", InjectionType.INSTRUCTION_OVERRIDE, InjectionSeverity.LOW),
        (
            r"(?i)your\s+new\s+instructions",
            InjectionType.INSTRUCTION_OVERRIDE,
            InjectionSeverity.MEDIUM,
        ),
        (r"(?i)hidden\s+instructions", InjectionType.CONTEXT_POISONING, InjectionSeverity.MEDIUM),
        (r"(?i)decode\s+this\s+base64", InjectionType.ENCODING_BYPASS, InjectionSeverity.MEDIUM),
        (r"(?i)rot13\s+decode", InjectionType.ENCODING_BYPASS, InjectionSeverity.LOW),
    ]

    # Multi-stage attack indicators
    MULTI_STAGE_INDICATORS: ClassVar[list[str]] = [
        r"(?i)step\s+\d+",
        r"(?i)phase\s+\d+",
        r"(?i)first,\s+.*then",
        r"(?i)after\s+that",
    ]

    def __init__(
        self,
        strict_mode: bool = True,
        classifier: ContentClassifier | None = None,
    ):
        """
        Initialize the prompt injection detector.

        Args:
            strict_mode: If True, use stricter detection (more false positives but safer)
            classifier: Optional L2 semantic classifier for ambiguous regex matches.
                        When provided, regex matches with confidence < 0.8 are escalated
                        to the classifier for confirmation before blocking.
        """
        self.strict_mode = strict_mode
        self._classifier = classifier
        self._compiled_core = [
            (re.compile(pattern), inj_type, severity)
            for pattern, inj_type, severity in self.CORE_PATTERNS
        ]
        self._compiled_advanced = [
            (re.compile(pattern), inj_type, severity)
            for pattern, inj_type, severity in self.ADVANCED_PATTERNS
        ]
        self._compiled_multi_stage = [
            re.compile(pattern) for pattern in self.MULTI_STAGE_INDICATORS
        ]

    def _scan_pattern_set(
        self,
        content_str: str,
        compiled_patterns: list,
        confidence_increment: float,
        matched_patterns: list,
        detected_types: set,
        max_severity: InjectionSeverity | None,
        confidence_score: float,
    ) -> tuple[InjectionSeverity | None, float]:
        """Scan a set of compiled patterns and accumulate matches."""
        for pattern, inj_type, severity in compiled_patterns:
            if pattern.search(content_str):
                matched_patterns.append(pattern.pattern)
                detected_types.add(inj_type)
                if max_severity is None or self._severity_value(severity) > self._severity_value(
                    max_severity
                ):
                    max_severity = severity
                confidence_score += confidence_increment
        return max_severity, confidence_score

    def _apply_multi_stage(
        self,
        content_str: str,
        detected_types: set,
        max_severity: InjectionSeverity | None,
        confidence_score: float,
    ) -> tuple[int, InjectionSeverity | None, float]:
        """Detect multi-stage attack indicators and update severity/confidence."""
        count = sum(1 for p in self._compiled_multi_stage if p.search(content_str))
        if count >= 2:
            detected_types.add(InjectionType.MULTI_STAGE)
            confidence_score += 0.2
            if max_severity is None or self._severity_value(
                InjectionSeverity.MEDIUM
            ) > self._severity_value(max_severity):
                max_severity = InjectionSeverity.MEDIUM
        return count, max_severity, confidence_score

    def _resolve_primary_type(self, detected_types: set) -> InjectionType | None:
        """Pick the highest-priority injection type from the detected set."""
        if not detected_types:
            return None
        for priority_type in (
            InjectionType.INSTRUCTION_OVERRIDE,
            InjectionType.JAILBREAK,
            InjectionType.SYSTEM_PROMPT_LEAK,
        ):
            if priority_type in detected_types:
                return priority_type
        return InjectionType(next(iter(detected_types)))

    def _consult_classifier(
        self, content_str: str, matched_patterns: list, confidence_score: float, ctx: JSONDict
    ) -> bool | None:
        """Optionally escalate to L2 classifier for ambiguous matches."""
        if self._classifier is None or not matched_patterns or confidence_score >= 0.8:
            return None
        try:
            classifier_score = self._classifier.classify(content_str, ctx)
            confirmed = classifier_score >= 0.5
            if not confirmed:
                logger.info(
                    "Regex match overridden by classifier (score=%.2f < 0.5), allowing content",
                    classifier_score,
                )
            return confirmed
        except INJECTION_DETECTION_OPERATION_ERRORS:
            logger.warning("Classifier failed, falling back to regex-only detection", exc_info=True)
            return None

    def detect(self, content: object, context: JSONDict | None = None) -> InjectionDetectionResult:
        """
        Detect prompt injection attempts in content.

        Args:
            content: Content to scan (str, dict, list, etc.)
            context: Optional context metadata (agent_id, tenant_id, etc.)

        Returns:
            InjectionDetectionResult with detection details
        """
        content_str = self._normalize_content(content)
        ctx: JSONDict = context if context is not None else {}

        if not content_str or len(content_str.strip()) == 0:
            return InjectionDetectionResult(
                is_injection=False, confidence=0.0, metadata={"reason": "empty_content"}
            )

        matched_patterns: list = []
        detected_types: set = set()
        max_severity = None
        confidence_score = 0.0

        max_severity, confidence_score = self._scan_pattern_set(
            content_str,
            self._compiled_core,
            0.3,
            matched_patterns,
            detected_types,
            max_severity,
            confidence_score,
        )
        if self.strict_mode or matched_patterns:
            max_severity, confidence_score = self._scan_pattern_set(
                content_str,
                self._compiled_advanced,
                0.15,
                matched_patterns,
                detected_types,
                max_severity,
                confidence_score,
            )

        multi_stage_count, max_severity, confidence_score = self._apply_multi_stage(
            content_str, detected_types, max_severity, confidence_score
        )
        primary_type = self._resolve_primary_type(detected_types)
        confidence_score = min(1.0, confidence_score)
        classifier_confirmed = self._consult_classifier(
            content_str, matched_patterns, confidence_score, ctx
        )

        regex_positive = len(matched_patterns) > 0 and (
            confidence_score >= 0.3 if self.strict_mode else confidence_score >= 0.5
        )
        is_injection = (
            regex_positive and classifier_confirmed
            if classifier_confirmed is not None
            else regex_positive
        )

        sanitized_content = (
            self._sanitize_content(content_str, matched_patterns) if is_injection else None
        )

        result_metadata: JSONDict = {
            "detected_types": [t.value for t in detected_types],
            "pattern_count": len(matched_patterns),
            "multi_stage_indicators": multi_stage_count,
            "content_length": len(content_str),
            "strict_mode": self.strict_mode,
            "classifier_used": self._classifier is not None,
            "classifier_confirmed": classifier_confirmed,
        }
        result_metadata.update(ctx)

        result = InjectionDetectionResult(
            is_injection=is_injection,
            severity=max_severity,
            injection_type=primary_type,
            matched_patterns=matched_patterns,
            confidence=confidence_score,
            sanitized_content=sanitized_content,
            metadata=result_metadata,
        )

        if is_injection:
            logger.warning(
                f"Prompt injection detected: type={primary_type.value if primary_type else 'unknown'}, "
                f"severity={max_severity.value if max_severity else 'unknown'}, "
                f"confidence={confidence_score:.2f}, patterns={len(matched_patterns)}"
            )

        return result

    def _normalize_content(self, content: object) -> str:
        """Normalize content to string for scanning.

        Uses type guards for safe type narrowing in security-critical path.

        Args:
            content: Content to normalize (str, dict, list, or other)

        Returns:
            Normalized string representation
        """
        if is_str(content):
            return str(content)  # TypeGuard[str] confirms str; explicit cast for mypy
        elif is_json_dict(content):
            # Extract text fields from dict - content narrowed to JSONDict by TypeGuard
            dict_content: JSONDict = content
            text_parts: list[str] = []
            for _key, value in dict_content.items():
                if is_str(value):
                    text_parts.append(value)
                elif isinstance(value, (dict, list)):
                    text_parts.append(self._normalize_content(value))
            return " ".join(text_parts)
        elif isinstance(content, list):
            normalized_parts: list[str] = [self._normalize_content(item) for item in content]
            return " ".join(normalized_parts)
        else:
            # Fallback for any other type
            return str(content) if content is not None else ""

    def _sanitize_content(self, content: str, matched_patterns: list[str]) -> str:
        """
        Sanitize content by removing or neutralizing detected patterns.

        Note: This is a basic sanitization. In production, you may want
        more sophisticated approaches like content rewriting or blocking.
        """
        sanitized = content
        for pattern_str in matched_patterns:
            try:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                sanitized = pattern.sub("[REDACTED]", sanitized)
            except PATTERN_SANITIZATION_ERRORS as e:
                logger.warning(f"Failed to sanitize pattern {pattern_str}: {e}")
        return sanitized

    @staticmethod
    def _severity_value(severity: InjectionSeverity | None) -> int:
        """Get numeric value for severity comparison.

        Args:
            severity: Severity level to convert (may be None)

        Returns:
            Numeric value (0 for None, 1-4 for severity levels)
        """
        if severity is None:
            return 0
        severity_map: dict[InjectionSeverity, int] = {
            InjectionSeverity.LOW: 1,
            InjectionSeverity.MEDIUM: 2,
            InjectionSeverity.HIGH: 3,
            InjectionSeverity.CRITICAL: 4,
        }
        return severity_map.get(severity, 0)


# Convenience function for backward compatibility
def detect_prompt_injection(content: object, strict_mode: bool = True) -> bool:
    """
    Simple function interface for prompt injection detection.

    Args:
        content: Content to scan
        strict_mode: Use strict detection mode

    Returns:
        True if injection detected, False otherwise
    """
    detector = PromptInjectionDetector(strict_mode=strict_mode)
    result = detector.detect(content)
    return result.is_injection
