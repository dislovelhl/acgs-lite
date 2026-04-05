"""
ACGS-2 Response Quality Enhancement - Data Models
Constitutional Hash: 608508a9bd224290

Data models for response quality assessment including quality dimensions,
assessments, and refinement tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class QualityLevel(Enum):
    """Quality level classifications."""

    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    UNACCEPTABLE = "unacceptable"


class RefinementStatus(Enum):
    """Status of refinement operations."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class QualityDimension:
    """
    Represents a single dimension of quality assessment.

    Each dimension has a name, score, threshold for passing,
    and optional critique explaining the assessment.

    Attributes:
        name: Identifier for this quality dimension (e.g., 'accuracy', 'coherence')
        score: Normalized score between 0.0 and 1.0
        threshold: Minimum score required to pass this dimension
        critique: Optional textual explanation of the assessment
    """

    name: str
    score: float
    threshold: float
    critique: str | None = None

    def __post_init__(self):
        """Validate score is within bounds."""
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"Score must be between 0.0 and 1.0, got {self.score}")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError(f"Threshold must be between 0.0 and 1.0, got {self.threshold}")

    @property
    def passes(self) -> bool:
        """Check if this dimension passes its threshold."""
        return self.score >= self.threshold

    @property
    def gap(self) -> float:
        """Calculate the gap between score and threshold (negative if failing)."""
        return self.score - self.threshold

    @property
    def level(self) -> QualityLevel:
        """Determine quality level based on score."""
        if self.score >= 0.95:
            return QualityLevel.EXCELLENT
        elif self.score >= 0.8:
            return QualityLevel.GOOD
        elif self.score >= 0.6:
            return QualityLevel.ACCEPTABLE
        elif self.score >= 0.4:
            return QualityLevel.POOR
        else:
            return QualityLevel.UNACCEPTABLE

    def to_dict(self) -> JSONDict:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "score": self.score,
            "threshold": self.threshold,
            "critique": self.critique,
            "passes": self.passes,
            "gap": self.gap,
            "level": self.level.value,
        }


@dataclass
class QualityAssessment:
    """
    Complete quality assessment for a response.

    Aggregates multiple quality dimensions into an overall assessment,
    including constitutional compliance verification.

    Attributes:
        dimensions: list of individual quality dimension assessments
        overall_score: Weighted aggregate score across all dimensions
        passes_threshold: Whether all critical thresholds are met
        refinement_suggestions: list of suggested improvements
        constitutional_compliance: Whether response meets constitutional requirements
        response_id: Optional identifier for the assessed response
        timestamp: When the assessment was performed
        metadata: Additional context about the assessment
    """

    dimensions: list[QualityDimension]
    overall_score: float
    passes_threshold: bool
    refinement_suggestions: list[str]
    constitutional_compliance: bool
    response_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self):
        """Validate assessment data."""
        if not 0.0 <= self.overall_score <= 1.0:
            raise ValueError(f"Overall score must be between 0.0 and 1.0, got {self.overall_score}")

    @property
    def dimension_count(self) -> int:
        """Number of dimensions assessed."""
        return len(self.dimensions)

    @property
    def passing_dimensions(self) -> list[QualityDimension]:
        """Get all dimensions that pass their thresholds."""
        return [d for d in self.dimensions if d.passes]

    @property
    def failing_dimensions(self) -> list[QualityDimension]:
        """Get all dimensions that fail their thresholds."""
        return [d for d in self.dimensions if not d.passes]

    @property
    def pass_rate(self) -> float:
        """Calculate the fraction of dimensions passing."""
        if not self.dimensions:
            return 0.0
        return len(self.passing_dimensions) / len(self.dimensions)

    @property
    def critical_failures(self) -> list[QualityDimension]:
        """Get dimensions with critical failures (constitutional or safety)."""
        critical_names = {"constitutional_alignment", "safety"}
        return [d for d in self.failing_dimensions if d.name in critical_names]

    @property
    def overall_level(self) -> QualityLevel:
        """Determine overall quality level."""
        if self.overall_score >= 0.95:
            return QualityLevel.EXCELLENT
        elif self.overall_score >= 0.8:
            return QualityLevel.GOOD
        elif self.overall_score >= 0.6:
            return QualityLevel.ACCEPTABLE
        elif self.overall_score >= 0.4:
            return QualityLevel.POOR
        else:
            return QualityLevel.UNACCEPTABLE

    @property
    def needs_refinement(self) -> bool:
        """Check if response requires refinement."""
        return not self.passes_threshold or not self.constitutional_compliance

    def get_dimension(self, name: str) -> QualityDimension | None:
        """Get a specific dimension by name."""
        for dim in self.dimensions:
            if dim.name == name:
                return dim
        return None

    def to_dict(self) -> JSONDict:
        """Convert to dictionary representation."""
        return {
            "dimensions": [d.to_dict() for d in self.dimensions],
            "overall_score": self.overall_score,
            "passes_threshold": self.passes_threshold,
            "refinement_suggestions": self.refinement_suggestions,
            "constitutional_compliance": self.constitutional_compliance,
            "response_id": self.response_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "dimension_count": self.dimension_count,
            "pass_rate": self.pass_rate,
            "overall_level": self.overall_level.value,
            "needs_refinement": self.needs_refinement,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "QualityAssessment":
        """Create from dictionary representation."""
        dimensions = [
            QualityDimension(
                name=d["name"],
                score=d["score"],
                threshold=d["threshold"],
                critique=d.get("critique"),
            )
            for d in data.get("dimensions", [])
        ]

        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()

        return cls(
            dimensions=dimensions,
            overall_score=data["overall_score"],
            passes_threshold=data["passes_threshold"],
            refinement_suggestions=data.get("refinement_suggestions", []),
            constitutional_compliance=data.get("constitutional_compliance", True),
            response_id=data.get("response_id"),
            timestamp=timestamp,
            metadata=data.get("metadata", {}),
        )


@dataclass
class RefinementIteration:
    """
    Tracks a single iteration of response refinement.

    Attributes:
        iteration_number: Which iteration this represents (1-indexed)
        original_response: The response before refinement
        refined_response: The response after refinement
        before_assessment: Quality assessment before refinement
        after_assessment: Quality assessment after refinement
        improvements: Description of improvements made
        duration_ms: Time taken for this iteration in milliseconds
    """

    iteration_number: int
    original_response: str
    refined_response: str
    before_assessment: QualityAssessment
    after_assessment: QualityAssessment
    improvements: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def improvement_delta(self) -> float:
        """Calculate improvement in overall score."""
        return self.after_assessment.overall_score - self.before_assessment.overall_score

    @property
    def improved(self) -> bool:
        """Check if refinement improved the response."""
        return self.improvement_delta > 0

    @property
    def now_passes(self) -> bool:
        """Check if response now passes after refinement."""
        return (
            not self.before_assessment.passes_threshold and self.after_assessment.passes_threshold
        )


@dataclass
class RefinementResult:
    """
    Complete result of a refinement operation.

    Attributes:
        original_response: The original unrefined response
        final_response: The final refined response
        iterations: list of refinement iterations performed
        total_iterations: Number of refinement iterations
        status: Final status of the refinement operation
        initial_assessment: Quality assessment before any refinement
        final_assessment: Quality assessment after all refinements
        total_duration_ms: Total time for all iterations
        constitutional_hash: Hash for compliance verification
    """

    original_response: str
    final_response: str
    iterations: list[RefinementIteration]
    total_iterations: int
    status: RefinementStatus
    initial_assessment: QualityAssessment
    final_assessment: QualityAssessment
    total_duration_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @property
    def total_improvement(self) -> float:
        """Calculate total improvement from original to final."""
        return self.final_assessment.overall_score - self.initial_assessment.overall_score

    @property
    def was_refined(self) -> bool:
        """Check if any refinement occurred."""
        return len(self.iterations) > 0

    @property
    def improved(self) -> bool:
        """Check if overall quality improved."""
        return self.total_improvement > 0

    @property
    def success(self) -> bool:
        """Check if refinement was successful."""
        return self.status == RefinementStatus.COMPLETED and self.final_assessment.passes_threshold

    def to_dict(self) -> JSONDict:
        """Convert to dictionary representation."""
        return {
            "original_response": self.original_response,
            "final_response": self.final_response,
            "total_iterations": self.total_iterations,
            "status": self.status.value,
            "initial_assessment": self.initial_assessment.to_dict(),
            "final_assessment": self.final_assessment.to_dict(),
            "total_improvement": self.total_improvement,
            "total_duration_ms": self.total_duration_ms,
            "constitutional_hash": self.constitutional_hash,
            "was_refined": self.was_refined,
            "improved": self.improved,
            "success": self.success,
        }


# type aliases for convenience
DimensionScores = dict[str, float]
SuggestionList = list[str]

__all__ = [
    "CONSTITUTIONAL_HASH",
    "DimensionScores",
    "QualityAssessment",
    "QualityDimension",
    "QualityLevel",
    "RefinementIteration",
    "RefinementResult",
    "RefinementStatus",
    "SuggestionList",
]
