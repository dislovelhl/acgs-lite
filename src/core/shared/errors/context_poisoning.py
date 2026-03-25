"""
ACGS-2 Context Poisoning Error
Constitutional Hash: 608508a9bd224290

Custom exception for OWASP AA05 (Memory Poisoning) violations detected
by the ContextIntegrityGuard when agent-supplied context contains
injection patterns.
"""

from __future__ import annotations

from ..constants import CONSTITUTIONAL_HASH
from ..types import JSONDict
from .exceptions import ACGSBaseError


class ContextPoisoningError(ACGSBaseError):
    """Raised when agent-supplied context fails injection scanning.

    This exception indicates that content destined for working memory
    contains prompt injection patterns and must be rejected to prevent
    memory poisoning attacks (OWASP AA05).

    Attributes:
        source_id: Identifier of the agent or source that supplied the content.
        source_type: Category of the source (e.g., "agent", "workflow", "api").
        matched_patterns: List of injection patterns that were matched.
        severity: Severity level of the detected injection.
        confidence: Confidence score of the detection (0.0-1.0).
    """

    http_status_code: int = 403
    error_code: str = "CONTEXT_POISONING"

    def __init__(
        self,
        message: str,
        *,
        source_id: str = "",
        source_type: str = "",
        matched_patterns: list[str] | None = None,
        severity: str = "",
        confidence: float = 0.0,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        details: JSONDict | None = None,
    ) -> None:
        """Initialize ContextPoisoningError.

        Args:
            message: Human-readable description of the poisoning attempt.
            source_id: Identifier of the content source.
            source_type: Category of the source.
            matched_patterns: Injection patterns that triggered the rejection.
            severity: Severity level string (low/medium/high/critical).
            confidence: Detection confidence score.
            constitutional_hash: Constitutional hash for governance tracking.
            details: Additional structured error context.
        """
        self.source_id = source_id
        self.source_type = source_type
        self.matched_patterns = matched_patterns or []
        self.severity = severity
        self.confidence = confidence

        enriched_details: JSONDict = {
            "source_id": source_id,
            "source_type": source_type,
            "matched_patterns": self.matched_patterns,
            "severity": severity,
            "confidence": confidence,
            "owasp_category": "AA05",
        }
        if details:
            enriched_details.update(details)

        super().__init__(
            message,
            error_code=self.error_code,
            constitutional_hash=constitutional_hash,
            details=enriched_details,
        )
