"""
ACGS-2 Enhanced Agent Bus - Response Quality Enhancement
Constitutional Hash: 608508a9bd224290

Phase 5 implementation providing:
- ResponseValidationPipeline: Multi-stage validation (SYNTAX, SEMANTIC, CONSTITUTIONAL)
- QualityScorer: Configurable multi-dimension quality scoring with COHERENCE,
  COMPLETENESS, and ALIGNMENT dimensions
- ResponseRefiner: Auto-refinement loop for iterative quality improvement

Part of Agent Orchestration Improvements Phases 4-7.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# Feature flag for response quality enhancement
RESPONSE_QUALITY_AVAILABLE = True


# =============================================================================
# Enums and Core Data Models
# =============================================================================


class ValidationStage(str, Enum):
    """Stages in the multi-stage response validation pipeline.

    Constitutional Hash: 608508a9bd224290
    """

    SYNTAX = "syntax"
    SEMANTIC = "semantic"
    CONSTITUTIONAL = "constitutional"


@dataclass
class ValidationResult:
    """Result of a single validation pipeline stage.

    Constitutional Hash: 608508a9bd224290
    """

    stage: ValidationStage
    passed: bool
    issues: list[str]
    confidence: float  # 0.0 - 1.0
    metadata: JSONDict = field(default_factory=dict)
    validated_at: datetime = field(default_factory=datetime.now)
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)

    def __post_init__(self) -> None:
        """Validate confidence is within [0.0, 1.0]."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")


class QualityDimension(str, Enum):
    """Quality dimensions used by the multi-dimension scorer.

    Constitutional Hash: 608508a9bd224290
    """

    COHERENCE = "coherence"
    COMPLETENESS = "completeness"
    ALIGNMENT = "alignment"


@dataclass
class QualityScore:
    """Multi-dimensional quality score for a response.

    Constitutional Hash: 608508a9bd224290
    """

    dimension_scores: dict[QualityDimension, float]
    overall_score: float
    passed: bool
    threshold: float
    response_length: int
    evaluation_notes: list[str] = field(default_factory=list)
    scored_at: datetime = field(default_factory=datetime.now)
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)

    def get_dimension(self, dimension: QualityDimension) -> float:
        """Return score for a specific dimension, defaulting to 0.0."""
        return self.dimension_scores.get(dimension, 0.0)

    def failing_dimensions(self, threshold: float | None = None) -> list[QualityDimension]:
        """Return dimensions whose score falls below the given threshold."""
        t = threshold if threshold is not None else self.threshold
        return [dim for dim, score in self.dimension_scores.items() if score < t]


# =============================================================================
# Pipeline Configuration
# =============================================================================


@dataclass
class PipelineStageConfig:
    """Configuration for a single validation stage.

    Constitutional Hash: 608508a9bd224290
    """

    stage: ValidationStage
    enabled: bool = True
    min_confidence: float = 0.5
    required: bool = True
    timeout_seconds: float = 5.0
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)


@dataclass
class PipelineConfig:
    """Full configuration for the ResponseValidationPipeline.

    Constitutional Hash: 608508a9bd224290
    """

    stages: list[PipelineStageConfig] = field(
        default_factory=lambda: [
            PipelineStageConfig(stage=ValidationStage.SYNTAX),
            PipelineStageConfig(stage=ValidationStage.SEMANTIC),
            PipelineStageConfig(stage=ValidationStage.CONSTITUTIONAL),
        ]
    )
    fail_fast: bool = False  # Stop pipeline at the first required-stage failure
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)


# =============================================================================
# Task 5.1: Individual Stage Validators
# =============================================================================

# Validator function type: (response_text, context) → ValidationResult
ValidatorFunc = Callable[[str, JSONDict], Coroutine[Any, Any, ValidationResult]]


class SyntaxValidator:
    """
    Syntax-stage validator for structural and format compliance.

    Checks length bounds, character encoding, and forbidden patterns.

    Constitutional Hash: 608508a9bd224290
    """

    DEFAULT_MIN_LENGTH: int = 10
    DEFAULT_MAX_LENGTH: int = 50_000
    _FORBIDDEN_DEFAULTS: ClassVar[list[str]] = [
        r"\x00",  # Null bytes
        r"<script",  # XSS injection attempt
        r"eval\(",  # Code injection
    ]

    def __init__(
        self,
        min_length: int = DEFAULT_MIN_LENGTH,
        max_length: int = DEFAULT_MAX_LENGTH,
        forbidden_patterns: list[str] | None = None,
    ) -> None:
        self._min_length = min_length
        self._max_length = max_length
        self._forbidden = forbidden_patterns or self._FORBIDDEN_DEFAULTS
        self._compiled = [re.compile(p, re.IGNORECASE) for p in self._forbidden]
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def validate(self, response: str, context: JSONDict) -> ValidationResult:
        """Run syntax validation against structural constraints."""
        issues: list[str] = []

        # Length bounds
        if len(response) < self._min_length:
            issues.append(f"Response too short: {len(response)} chars < minimum {self._min_length}")
        if len(response) > self._max_length:
            issues.append(f"Response too long: {len(response)} chars > maximum {self._max_length}")

        # UTF-8 encoding
        try:
            response.encode("utf-8")
        except (UnicodeEncodeError, ValueError) as exc:
            issues.append(f"Encoding error: {exc}")

        # Forbidden pattern scan
        for idx, pattern in enumerate(self._compiled):
            if pattern.search(response):
                issues.append(f"Forbidden pattern detected: {self._forbidden[idx]!r}")

        # Sentence structure heuristic
        sentence_count = len(re.findall(r"[.!?]+", response))
        if sentence_count == 0 and len(response) > 50:
            issues.append("Response lacks sentence-ending punctuation")

        passed = len(issues) == 0
        confidence = max(0.1, 1.0 - len(issues) * 0.2)

        return ValidationResult(
            stage=ValidationStage.SYNTAX,
            passed=passed,
            issues=issues,
            confidence=min(1.0, confidence),
            metadata={
                "length": len(response),
                "sentence_count": sentence_count,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )


class SemanticValidator:
    """
    Semantic-stage validator for logical coherence and topic alignment.

    Checks word count, repetition, contradictions, and required topics.

    Constitutional Hash: 608508a9bd224290
    """

    _CONTRADICTION_PAIRS: ClassVar[list[tuple[str, str]]] = [
        (r"\balways\b", r"\bnever\b"),
        (r"\bmust\b", r"\bcannot\b"),
    ]
    _STOP_WORDS: frozenset[str] = frozenset(
        {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "have",
            "has",
            "that",
            "this",
            "it",
            "as",
        }
    )

    def __init__(
        self,
        min_word_count: int = 5,
        max_repetition_ratio: float = 0.7,
        check_contradictions: bool = True,
    ) -> None:
        self._min_word_count = min_word_count
        self._max_repetition_ratio = max_repetition_ratio
        self._check_contradictions = check_contradictions
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def _word_repetition_ratio(self, text: str) -> float:
        """Compute ratio of repeated content words (excluding stop words)."""
        words = re.findall(r"\b[a-z]+\b", text.lower())
        content = [w for w in words if w not in self._STOP_WORDS]
        if not content:
            return 0.0
        return 1.0 - len(set(content)) / len(content)

    def _detect_contradictions(self, text: str) -> list[str]:
        """Detect contradictory phrase pairs in the response."""
        found: list[str] = []
        for p1, p2 in self._CONTRADICTION_PAIRS:
            if re.search(p1, text, re.IGNORECASE) and re.search(p2, text, re.IGNORECASE):
                found.append(f"Potential contradiction between '{p1}' and '{p2}'")
        return found

    async def validate(self, response: str, context: JSONDict) -> ValidationResult:
        """Run semantic validation for coherence and topic coverage."""
        issues: list[str] = []

        words = re.findall(r"\b\w+\b", response)
        if len(words) < self._min_word_count:
            issues.append(
                f"Response has too few words: {len(words)} < minimum {self._min_word_count}"
            )

        rep_ratio = self._word_repetition_ratio(response)
        if rep_ratio > self._max_repetition_ratio:
            issues.append(
                f"High word repetition ratio: {rep_ratio:.2f} > maximum "
                f"{self._max_repetition_ratio:.2f}"
            )

        if self._check_contradictions:
            issues.extend(self._detect_contradictions(response))

        # Required topic coverage from context
        required_topics: list[str] = context.get("required_topics", [])
        if required_topics:
            response_lower = response.lower()
            missing = [t for t in required_topics if t.lower() not in response_lower]
            if missing:
                issues.append(f"Response missing required topics: {', '.join(missing)}")

        passed = len(issues) == 0
        confidence = max(0.1, min(1.0, 1.0 - len(issues) * 0.15 - rep_ratio * 0.3))

        return ValidationResult(
            stage=ValidationStage.SEMANTIC,
            passed=passed,
            issues=issues,
            confidence=confidence,
            metadata={
                "word_count": len(words),
                "repetition_ratio": rep_ratio,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )


class ConstitutionalValidator:
    """
    Constitutional-stage validator for governance policy compliance.

    Verifies the response does not violate constitutional constraints and
    adheres to the MACI separation-of-powers principle.

    Constitutional Hash: 608508a9bd224290

    MACI Note: This validator operates independently and never validates
    its own output — consistent with the MACI non-self-validation rule.
    """

    _PROHIBITED_DEFAULTS: ClassVar[list[tuple[str, str]]] = [
        (r"override.*constitutional", "Constitutional override attempt"),
        (r"bypass.*governance", "Governance bypass attempt"),
        (r"ignore.*polic(?:y|ies)", "Policy violation attempt"),
        (r"admin.*password", "Credential exposure risk"),
        (r"secret[-_]?key\s*[:=]", "Secret key exposure risk"),
    ]

    def __init__(
        self,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        prohibited_patterns: list[tuple[str, str]] | None = None,
        require_hash_reference: bool = False,
    ) -> None:
        self._required_hash = constitutional_hash
        self._prohibited = prohibited_patterns or self._PROHIBITED_DEFAULTS
        self._require_hash_reference = require_hash_reference
        self._compiled = [(re.compile(p, re.IGNORECASE), msg) for p, msg in self._prohibited]
        self.constitutional_hash = constitutional_hash

    async def validate(self, response: str, context: JSONDict) -> ValidationResult:
        """Run constitutional validation against governance policy."""
        issues: list[str] = []

        # Prohibited pattern scan
        for pattern, message in self._compiled:
            if pattern.search(response):
                issues.append(f"Constitutional violation: {message}")

        # Optional: require constitutional hash in response
        if self._require_hash_reference and self._required_hash not in response:
            issues.append(f"Response must reference constitutional hash: {self._required_hash}")

        # Context-specified forbidden actions
        forbidden_actions: list[str] = context.get("forbidden_actions", [])
        for action in forbidden_actions:
            if action.lower() in response.lower():
                issues.append(f"Response references forbidden action: {action!r}")

        # MACI: detect self-validation language
        if re.search(r"\bself[-_]?validat", response, re.IGNORECASE):
            issues.append("Response contains self-validation language — violates MACI principle")

        passed = len(issues) == 0
        confidence = 1.0 if passed else max(0.0, 1.0 - len(issues) * 0.25)

        return ValidationResult(
            stage=ValidationStage.CONSTITUTIONAL,
            passed=passed,
            issues=issues,
            confidence=confidence,
            metadata={
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "maci_compliant": passed,
                "prohibited_patterns_checked": len(self._prohibited),
            },
        )


# =============================================================================
# Pipeline Run Result and Pipeline Class
# =============================================================================


@dataclass
class PipelineRunResult:
    """Complete result from a full validation pipeline run.

    Constitutional Hash: 608508a9bd224290
    """

    stage_results: list[ValidationResult]
    passed: bool
    all_issues: list[str]
    overall_confidence: float
    stages_run: list[ValidationStage]
    duration_ms: float
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)

    @property
    def failed_stages(self) -> list[ValidationStage]:
        """Return the list of stages that did not pass."""
        return [r.stage for r in self.stage_results if not r.passed]

    def issues_by_stage(self) -> dict[ValidationStage, list[str]]:
        """Return issues grouped by their originating validation stage."""
        return {r.stage: r.issues for r in self.stage_results}


class ResponseValidationPipeline:
    """
    Multi-stage response validation pipeline.

    Executes SYNTAX → SEMANTIC → CONSTITUTIONAL stages sequentially
    (or in fail-fast mode, stopping at the first required-stage failure).

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        syntax_validator: SyntaxValidator | None = None,
        semantic_validator: SemanticValidator | None = None,
        constitutional_validator: ConstitutionalValidator | None = None,
    ) -> None:
        self._config = config or PipelineConfig()
        self.constitutional_hash = CONSTITUTIONAL_HASH

        # Register built-in stage validators
        self._validators: dict[ValidationStage, ValidatorFunc] = {
            ValidationStage.SYNTAX: (syntax_validator or SyntaxValidator()).validate,
            ValidationStage.SEMANTIC: (semantic_validator or SemanticValidator()).validate,
            ValidationStage.CONSTITUTIONAL: (
                constitutional_validator or ConstitutionalValidator()
            ).validate,
        }
        self._stats: dict[str, int] = {
            "runs": 0,
            "passed": 0,
            "failed": 0,
            "syntax_failures": 0,
            "semantic_failures": 0,
            "constitutional_failures": 0,
        }

    def register_validator(self, stage: ValidationStage, validator: ValidatorFunc) -> None:
        """Register a custom validator function for the given stage."""
        self._validators[stage] = validator
        logger.info(f"[{CONSTITUTIONAL_HASH}] Registered validator for stage: {stage.value}")

    async def run(
        self,
        response: str,
        context: JSONDict | None = None,
        stages: list[ValidationStage] | None = None,
    ) -> PipelineRunResult:
        """
        Execute the validation pipeline on a response.

        Args:
            response: Response text to validate.
            context: Optional dict with required_topics, forbidden_actions, etc.
            stages: Explicit stage list to run; defaults to all enabled stages.

        Returns:
            PipelineRunResult aggregating all stage outcomes.
        """
        start_ms = time.monotonic() * 1000
        ctx = context or {}
        self._stats["runs"] += 1

        target_stages: list[ValidationStage] = stages or [
            sc.stage for sc in self._config.stages if sc.enabled
        ]

        stage_results: list[ValidationResult] = []
        all_issues: list[str] = []
        pipeline_passed = True

        for stage in target_stages:
            validator = self._validators.get(stage)
            if validator is None:
                logger.warning(f"[{CONSTITUTIONAL_HASH}] No validator for stage: {stage.value}")
                continue

            stage_config = next(
                (sc for sc in self._config.stages if sc.stage == stage),
                PipelineStageConfig(stage=stage),
            )

            try:
                result = await asyncio.wait_for(
                    validator(response, ctx),
                    timeout=stage_config.timeout_seconds,
                )
            except TimeoutError:
                result = ValidationResult(
                    stage=stage,
                    passed=False,
                    issues=[f"Stage {stage.value!r} validation timed out"],
                    confidence=0.0,
                )
            except Exception as exc:
                logger.exception(
                    f"[{CONSTITUTIONAL_HASH}] Validation stage {stage.value!r} error: {exc}"
                )
                result = ValidationResult(
                    stage=stage,
                    passed=False,
                    issues=[f"Stage {stage.value!r} raised exception: {exc}"],
                    confidence=0.0,
                )

            stage_results.append(result)
            all_issues.extend(result.issues)

            if not result.passed:
                pipeline_passed = False
                stat_key = f"{stage.value}_failures"
                if stat_key in self._stats:
                    self._stats[stat_key] += 1
                if self._config.fail_fast and stage_config.required:
                    break

        if pipeline_passed:
            self._stats["passed"] += 1
        else:
            self._stats["failed"] += 1

        overall_confidence = (
            sum(r.confidence for r in stage_results) / len(stage_results) if stage_results else 0.0
        )
        duration_ms = time.monotonic() * 1000 - start_ms

        return PipelineRunResult(
            stage_results=stage_results,
            passed=pipeline_passed,
            all_issues=all_issues,
            overall_confidence=overall_confidence,
            stages_run=target_stages,
            duration_ms=duration_ms,
        )

    def get_stats(self) -> JSONDict:
        """Return pipeline run statistics."""
        return {**self._stats, "constitutional_hash": CONSTITUTIONAL_HASH}


# =============================================================================
# Task 5.2: Quality Scoring — Dimension Scorers
# =============================================================================


@dataclass
class ScorerThresholds:
    """Per-dimension and overall pass/fail thresholds for QualityScorer.

    Constitutional Hash: 608508a9bd224290
    """

    coherence: float = 0.70
    completeness: float = 0.60
    alignment: float = 0.65
    overall: float = 0.65
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)

    def get(self, dimension: QualityDimension) -> float:
        """Return the threshold for the given dimension."""
        return float(getattr(self, dimension.value, self.overall))


class CoherenceScorer:
    """
    Scores response coherence (logical flow and topical consistency).

    Constitutional Hash: 608508a9bd224290
    """

    async def score(self, response: str, context: JSONDict) -> float:
        """Score coherence in [0.0, 1.0]."""
        sentences = [s.strip() for s in re.split(r"[.!?]+", response) if s.strip()]
        if not sentences:
            return 0.0

        penalties = 0.0

        # Penalise very short sentences (<3 words)
        short_count = sum(1 for s in sentences if len(re.findall(r"\w+", s)) < 3)
        penalties += (short_count / len(sentences)) * 0.2

        # Penalise excessive repetition
        all_words = re.findall(r"\b[a-z]+\b", response.lower())
        if all_words:
            unique_ratio = len(set(all_words)) / len(all_words)
            if unique_ratio < 0.3:
                penalties += 0.3
            elif unique_ratio < 0.5:
                penalties += 0.15

        # Penalise highly uneven sentence lengths (structural inconsistency)
        word_counts = [len(re.findall(r"\w+", s)) for s in sentences]
        if len(word_counts) > 1:
            avg = sum(word_counts) / len(word_counts)
            variance = sum((c - avg) ** 2 for c in word_counts) / len(word_counts)
            cv = variance**0.5 / max(avg, 1)
            if cv > 2.0:
                penalties += 0.1

        return max(0.0, min(1.0, 1.0 - penalties))


class CompletenessScorer:
    """
    Scores response completeness (sufficient content and topic coverage).

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, min_expected_words: int = 50) -> None:
        self._min_expected_words = min_expected_words

    async def score(self, response: str, context: JSONDict) -> float:
        """Score completeness in [0.0, 1.0]."""
        words = re.findall(r"\b\w+\b", response)
        word_count = len(words)

        if word_count == 0:
            return 0.0
        elif word_count < 10:
            base = 0.2
        elif word_count < self._min_expected_words:
            base = 0.4 + 0.4 * (word_count / self._min_expected_words)
        else:
            base = 0.8

        # Blend with required-topic coverage
        required_topics: list[str] = context.get("required_topics", [])
        if required_topics:
            response_lower = response.lower()
            covered = sum(1 for t in required_topics if t.lower() in response_lower)
            coverage_ratio = covered / len(required_topics)
            base = base * 0.5 + coverage_ratio * 0.5

        # Small boost for structured content (lists or headings)
        has_structure = bool(re.search(r"(?m)^[\s]*[-*•]|(?m)^#+\s", response))
        if has_structure:
            base = min(1.0, base + 0.1)

        return max(0.0, min(1.0, base))


class AlignmentScorer:
    """
    Scores response alignment with governance objectives.

    Constitutional Hash: 608508a9bd224290
    """

    _ALIGNMENT_KEYWORDS: ClassVar[list[str]] = [
        "constitutional",
        "governance",
        "policy",
        "compliance",
        "authorized",
        "validated",
        "approved",
    ]
    _MISALIGNMENT_KEYWORDS: ClassVar[list[str]] = [
        "bypass",
        "override",
        "circumvent",
        "ignore",
        "disable",
        "unauthorized",
        "unapproved",
    ]

    def __init__(
        self,
        alignment_keywords: list[str] | None = None,
        misalignment_keywords: list[str] | None = None,
    ) -> None:
        self._alignment_kw = alignment_keywords or self._ALIGNMENT_KEYWORDS
        self._misalignment_kw = misalignment_keywords or self._MISALIGNMENT_KEYWORDS
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def score(self, response: str, context: JSONDict) -> float:
        """Score alignment in [0.0, 1.0]."""
        response_lower = response.lower()

        alignment_hits = sum(1 for kw in self._alignment_kw if kw in response_lower)
        misalignment_hits = sum(1 for kw in self._misalignment_kw if kw in response_lower)

        base = 0.70
        base += min(alignment_hits * 0.05, 0.20)
        base -= misalignment_hits * 0.15

        # Optional: intent overlap from context
        expected_intent: str = context.get("expected_intent", "")
        if expected_intent:
            intent_words = set(re.findall(r"\b[a-z]+\b", expected_intent.lower()))
            response_words = set(re.findall(r"\b[a-z]+\b", response_lower))
            if intent_words:
                overlap = len(intent_words & response_words) / len(intent_words)
                base = base * 0.7 + overlap * 0.3

        return max(0.0, min(1.0, base))


class QualityScorer:
    """
    Configurable multi-dimension quality scorer.

    Aggregates COHERENCE, COMPLETENESS, and ALIGNMENT scores with
    weighted combination and configurable pass/fail thresholds.

    Constitutional Hash: 608508a9bd224290
    """

    # Governance context weights: alignment is most critical
    _WEIGHTS: ClassVar[dict[QualityDimension, float]] = {
        QualityDimension.COHERENCE: 0.30,
        QualityDimension.COMPLETENESS: 0.30,
        QualityDimension.ALIGNMENT: 0.40,
    }

    def __init__(
        self,
        thresholds: ScorerThresholds | None = None,
        coherence_scorer: CoherenceScorer | None = None,
        completeness_scorer: CompletenessScorer | None = None,
        alignment_scorer: AlignmentScorer | None = None,
    ) -> None:
        self._thresholds = thresholds or ScorerThresholds()
        self._coherence = coherence_scorer or CoherenceScorer()
        self._completeness = completeness_scorer or CompletenessScorer()
        self._alignment = alignment_scorer or AlignmentScorer()
        self.constitutional_hash = CONSTITUTIONAL_HASH

        self._stats: dict[str, int | float] = {
            "scored": 0,
            "passed": 0,
            "failed": 0,
            "avg_overall_score": 0.0,
        }

    async def score(self, response: str, context: JSONDict | None = None) -> QualityScore:
        """
        Score a response across all quality dimensions.

        Args:
            response: The response text to score.
            context: Optional dict with required_topics, expected_intent, etc.

        Returns:
            QualityScore with per-dimension scores, overall score, and pass/fail.
        """
        ctx = context or {}
        self._stats["scored"] = int(self._stats["scored"]) + 1

        coherence_score, completeness_score, alignment_score = await asyncio.gather(
            self._coherence.score(response, ctx),
            self._completeness.score(response, ctx),
            self._alignment.score(response, ctx),
        )

        dimension_scores: dict[QualityDimension, float] = {
            QualityDimension.COHERENCE: coherence_score,
            QualityDimension.COMPLETENESS: completeness_score,
            QualityDimension.ALIGNMENT: alignment_score,
        }

        overall_score = sum(dimension_scores[dim] * w for dim, w in self._WEIGHTS.items())

        passed = overall_score >= self._thresholds.overall and all(
            dimension_scores[dim] >= self._thresholds.get(dim) for dim in QualityDimension
        )

        notes: list[str] = [
            f"{dim.value.capitalize()} score {dimension_scores[dim]:.2f} below "
            f"threshold {self._thresholds.get(dim):.2f}"
            for dim in QualityDimension
            if dimension_scores[dim] < self._thresholds.get(dim)
        ]

        if passed:
            self._stats["passed"] = int(self._stats["passed"]) + 1
        else:
            self._stats["failed"] = int(self._stats["failed"]) + 1

        n = int(self._stats["scored"])
        prev_avg = float(self._stats["avg_overall_score"])
        self._stats["avg_overall_score"] = prev_avg * (n - 1) / n + overall_score / n

        return QualityScore(
            dimension_scores=dimension_scores,
            overall_score=overall_score,
            passed=passed,
            threshold=self._thresholds.overall,
            response_length=len(response),
            evaluation_notes=notes,
        )

    def get_stats(self) -> JSONDict:
        """Return scorer statistics."""
        return {**self._stats, "constitutional_hash": CONSTITUTIONAL_HASH}


# =============================================================================
# Task 5.3: Response Refinement
# =============================================================================

# Callback signature: (current_response, issues) → refined_response
RefinementCallback = Callable[[str, list[str]], Coroutine[Any, Any, str]]


@dataclass
class RefinementConfig:
    """Configuration for the iterative ResponseRefiner loop.

    Constitutional Hash: 608508a9bd224290
    """

    max_iterations: int = 3
    quality_threshold: float = 0.75
    improvement_target: float = 0.05  # Minimum gain per iteration to continue
    timeout_seconds: float = 30.0
    fail_on_no_improvement: bool = False
    validate_after_refine: bool = True
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        if not 0.0 <= self.quality_threshold <= 1.0:
            raise ValueError("quality_threshold must be between 0.0 and 1.0")


@dataclass
class RefinementStep:
    """Record of a single iteration in the refinement loop.

    Constitutional Hash: 608508a9bd224290
    """

    iteration: int
    input_score: float
    output_score: float
    issues_addressed: list[str]
    improvement: float
    duration_ms: float
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)


@dataclass
class RefinementResult:
    """Complete outcome of a response refinement run.

    Constitutional Hash: 608508a9bd224290
    """

    original_response: str
    refined_response: str
    original_score: float
    final_score: float
    passed: bool
    iterations: int
    refinement_steps: list[RefinementStep]
    total_duration_ms: float
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)

    @property
    def total_improvement(self) -> float:
        """Total quality improvement from original to refined response."""
        return self.final_score - self.original_score

    @property
    def converged(self) -> bool:
        """True when the quality threshold was reached."""
        return self.passed


class ResponseRefiner:
    """
    Iterative auto-refinement loop for response quality improvement.

    Applies a configurable RefinementCallback to address validation
    issues until the quality threshold is met or iterations are exhausted.

    Constitutional Hash: 608508a9bd224290

    MACI Note: The refinement callback is always an external, independent
    function. This class never self-validates its own refinement outputs.
    """

    def __init__(
        self,
        config: RefinementConfig | None = None,
        pipeline: ResponseValidationPipeline | None = None,
        scorer: QualityScorer | None = None,
        refinement_callback: RefinementCallback | None = None,
    ) -> None:
        self._config = config or RefinementConfig()
        self._pipeline = pipeline or ResponseValidationPipeline()
        self._scorer = scorer or QualityScorer()
        self._callback = refinement_callback
        self.constitutional_hash = CONSTITUTIONAL_HASH

        self._stats: dict[str, int | float] = {
            "refinements": 0,
            "converged": 0,
            "max_iter_reached": 0,
            "total_iterations": 0,
            "avg_improvement": 0.0,
        }

    def set_refinement_callback(self, callback: RefinementCallback) -> None:
        """Replace the refinement callback (independent validator)."""
        self._callback = callback
        logger.info(f"[{CONSTITUTIONAL_HASH}] Refinement callback updated")

    async def refine(
        self,
        response: str,
        context: JSONDict | None = None,
    ) -> RefinementResult:
        """
        Iteratively refine a response to meet quality thresholds.

        Args:
            response: Initial response text to refine.
            context: Optional context dict forwarded to validators and scorer.

        Returns:
            RefinementResult with the refined response and full iteration history.
        """
        start_ms = time.monotonic() * 1000
        ctx = context or {}
        self._stats["refinements"] = int(self._stats["refinements"]) + 1

        current_response = response
        steps: list[RefinementStep] = []

        initial_quality = await self._scorer.score(current_response, ctx)
        current_score = initial_quality.overall_score

        # Fast path: already meets threshold
        if current_score >= self._config.quality_threshold:
            total_ms = time.monotonic() * 1000 - start_ms
            self._stats["converged"] = int(self._stats["converged"]) + 1
            return RefinementResult(
                original_response=response,
                refined_response=response,
                original_score=current_score,
                final_score=current_score,
                passed=True,
                iterations=0,
                refinement_steps=[],
                total_duration_ms=total_ms,
            )

        for iteration in range(1, self._config.max_iterations + 1):
            iter_start = time.monotonic() * 1000

            pipeline_result = await self._pipeline.run(current_response, ctx)
            current_issues = pipeline_result.all_issues

            if not current_issues and current_score >= self._config.quality_threshold:
                break

            # Apply refinement via callback or built-in heuristics
            if self._callback is not None:
                try:
                    refined = await asyncio.wait_for(
                        self._callback(current_response, current_issues),
                        timeout=self._config.timeout_seconds,
                    )
                except TimeoutError:
                    logger.warning(
                        f"[{CONSTITUTIONAL_HASH}] Refinement callback timed out "
                        f"at iteration {iteration}"
                    )
                    break
                except Exception as exc:
                    logger.error(f"[{CONSTITUTIONAL_HASH}] Refinement callback error: {exc}")
                    break
            else:
                refined = self._apply_heuristic_refinements(current_response, current_issues)

            # Score the refined response
            new_quality = await self._scorer.score(refined, ctx)
            new_score = new_quality.overall_score
            improvement = new_score - current_score

            iter_ms = time.monotonic() * 1000 - iter_start
            steps.append(
                RefinementStep(
                    iteration=iteration,
                    input_score=current_score,
                    output_score=new_score,
                    issues_addressed=current_issues[:5],
                    improvement=improvement,
                    duration_ms=iter_ms,
                )
            )

            if (
                self._config.fail_on_no_improvement
                and improvement < self._config.improvement_target
            ):
                logger.info(
                    f"[{CONSTITUTIONAL_HASH}] Stopping refinement: insufficient "
                    f"improvement {improvement:.3f} at iteration {iteration}"
                )
                current_response = refined
                current_score = new_score
                break

            current_response = refined
            current_score = new_score
            self._stats["total_iterations"] = int(self._stats["total_iterations"]) + 1

            if current_score >= self._config.quality_threshold:
                break

        total_ms = time.monotonic() * 1000 - start_ms
        passed = current_score >= self._config.quality_threshold

        if passed:
            self._stats["converged"] = int(self._stats["converged"]) + 1
        else:
            self._stats["max_iter_reached"] = int(self._stats["max_iter_reached"]) + 1

        improvement_total = current_score - initial_quality.overall_score
        n = int(self._stats["refinements"])
        prev_avg = float(self._stats["avg_improvement"])
        self._stats["avg_improvement"] = prev_avg * (n - 1) / n + improvement_total / n

        return RefinementResult(
            original_response=response,
            refined_response=current_response,
            original_score=initial_quality.overall_score,
            final_score=current_score,
            passed=passed,
            iterations=len(steps),
            refinement_steps=steps,
            total_duration_ms=total_ms,
        )

    def _apply_heuristic_refinements(self, response: str, issues: list[str]) -> str:
        """
        Fallback heuristic refinement when no external callback is configured.

        Production deployments should always supply a proper RefinementCallback.
        """
        refined = response

        for issue in issues:
            issue_lower = issue.lower()
            if "too short" in issue_lower:
                refined += f" [Governance note — Constitutional Hash: {CONSTITUTIONAL_HASH}.]"
            elif "repetition" in issue_lower:
                sentences = re.split(r"(?<=[.!?])\s+", refined)
                seen: set[str] = set()
                deduped: list[str] = []
                for sentence in sentences:
                    key = sentence.strip().lower()
                    if key not in seen:
                        seen.add(key)
                        deduped.append(sentence)
                refined = " ".join(deduped)
            # Other issues require domain-specific logic; skip safely

        return refined

    def get_stats(self) -> JSONDict:
        """Return refiner statistics."""
        return {**self._stats, "constitutional_hash": CONSTITUTIONAL_HASH}


# =============================================================================
# Factory Functions
# =============================================================================


def create_validation_pipeline(
    fail_fast: bool = False,
    min_response_length: int = 10,
    max_response_length: int = 50_000,
    require_constitutional_hash: bool = False,
) -> ResponseValidationPipeline:
    """
    Create a fully configured ResponseValidationPipeline.

    Constitutional Hash: 608508a9bd224290
    """
    config = PipelineConfig(fail_fast=fail_fast)
    syntax_validator = SyntaxValidator(
        min_length=min_response_length,
        max_length=max_response_length,
    )
    constitutional_validator = ConstitutionalValidator(
        require_hash_reference=require_constitutional_hash,
    )
    return ResponseValidationPipeline(
        config=config,
        syntax_validator=syntax_validator,
        constitutional_validator=constitutional_validator,
    )


def create_quality_scorer(
    coherence_threshold: float = 0.70,
    completeness_threshold: float = 0.60,
    alignment_threshold: float = 0.65,
    overall_threshold: float = 0.65,
    min_expected_words: int = 50,
) -> QualityScorer:
    """
    Create a configured QualityScorer with per-dimension thresholds.

    Constitutional Hash: 608508a9bd224290
    """
    thresholds = ScorerThresholds(
        coherence=coherence_threshold,
        completeness=completeness_threshold,
        alignment=alignment_threshold,
        overall=overall_threshold,
    )
    completeness_scorer = CompletenessScorer(min_expected_words=min_expected_words)
    return QualityScorer(thresholds=thresholds, completeness_scorer=completeness_scorer)


def create_response_refiner(
    max_iterations: int = 3,
    quality_threshold: float = 0.75,
    improvement_target: float = 0.05,
    timeout_seconds: float = 30.0,
    refinement_callback: RefinementCallback | None = None,
    pipeline: ResponseValidationPipeline | None = None,
    scorer: QualityScorer | None = None,
) -> ResponseRefiner:
    """
    Create a configured ResponseRefiner with optional external callback.

    Constitutional Hash: 608508a9bd224290
    """
    config = RefinementConfig(
        max_iterations=max_iterations,
        quality_threshold=quality_threshold,
        improvement_target=improvement_target,
        timeout_seconds=timeout_seconds,
    )
    return ResponseRefiner(
        config=config,
        pipeline=pipeline or create_validation_pipeline(),
        scorer=scorer or create_quality_scorer(overall_threshold=quality_threshold),
        refinement_callback=refinement_callback,
    )


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Feature flag
    "RESPONSE_QUALITY_AVAILABLE",
    "AlignmentScorer",
    "CoherenceScorer",
    "CompletenessScorer",
    "ConstitutionalValidator",
    "PipelineConfig",
    "PipelineRunResult",
    "PipelineStageConfig",
    # Task 5.2: Quality scoring
    "QualityDimension",
    "QualityScore",
    "QualityScorer",
    "RefinementCallback",
    # Task 5.3: Response refinement
    "RefinementConfig",
    "RefinementResult",
    "RefinementStep",
    "ResponseRefiner",
    "ResponseValidationPipeline",
    "ScorerThresholds",
    "SemanticValidator",
    "SyntaxValidator",
    "ValidationResult",
    # Task 5.1: Validation pipeline
    "ValidationStage",
    "ValidatorFunc",
    "create_quality_scorer",
    "create_response_refiner",
    # Factory functions
    "create_validation_pipeline",
]
