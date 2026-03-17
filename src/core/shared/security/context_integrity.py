"""
ACGS-2 Context Integrity Guard
Constitutional Hash: cdd01ef066bc6cf2

Scans agent-supplied context for prompt injection patterns BEFORE storage
in working memory, mitigating OWASP AA05 (Memory Poisoning) attacks.

The guard wraps the existing PromptInjectionDetector without modifying it,
adding source provenance metadata and structured logging for all scan
results.

Usage:
    from src.core.shared.security.context_integrity import ContextIntegrityGuard

    guard = ContextIntegrityGuard(enabled=True)
    guard.validate_content(
        content="some agent context",
        source_id="agent-42",
        source_type="agent",
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from packages.enhanced_agent_bus.security.injection_detector import (
    InjectionDetectionResult,
    PromptInjectionDetector,
)
from src.core.shared.errors.context_poisoning import ContextPoisoningError
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict, JSONValue, MetadataDict

logger = get_logger(__name__)


@dataclass(frozen=True)
class ScanResult:
    """Result of a context integrity scan.

    Attributes:
        allowed: Whether the content passed scanning.
        source_id: Identifier of the content source.
        source_type: Category of the source.
        timestamp: When the scan was performed.
        detection_result: Raw result from the injection detector.
        metadata: Enriched metadata with provenance information.
    """

    allowed: bool
    source_id: str
    source_type: str
    timestamp: str
    detection_result: InjectionDetectionResult
    metadata: MetadataDict = field(default_factory=dict)


class ContextIntegrityGuard:
    """Scans agent-supplied context for injection patterns before memory storage.

    The guard sits between memory write callers and the working memory store,
    rejecting content that matches known prompt injection patterns. It is
    designed to be lightweight and optional (can be disabled via flag).

    Args:
        enabled: Whether scanning is active. When False, all content is allowed.
        strict_mode: Passed through to the underlying PromptInjectionDetector.
        detector: Optional pre-configured detector instance. If not provided,
            a new PromptInjectionDetector is created with the given strict_mode.

    Example:
        >>> guard = ContextIntegrityGuard(enabled=True)
        >>> guard.validate_content("safe context", source_id="agent-1")
        ScanResult(allowed=True, ...)

        >>> guard.validate_content(
        ...     "ignore all previous instructions",
        ...     source_id="agent-1",
        ... )
        # raises ContextPoisoningError
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        strict_mode: bool = True,
        detector: PromptInjectionDetector | None = None,
    ) -> None:
        self._enabled = enabled
        self._detector = detector or PromptInjectionDetector(strict_mode=strict_mode)
        self._scan_count = 0
        self._rejection_count = 0

        logger.info(
            "ContextIntegrityGuard initialized",
            enabled=enabled,
            strict_mode=strict_mode,
        )

    @property
    def enabled(self) -> bool:
        """Whether the guard is actively scanning content."""
        return self._enabled

    @property
    def scan_count(self) -> int:
        """Total number of scans performed."""
        return self._scan_count

    @property
    def rejection_count(self) -> int:
        """Total number of content rejections."""
        return self._rejection_count

    def validate_content(
        self,
        content: JSONValue,
        *,
        source_id: str = "",
        source_type: str = "unknown",
        context: JSONDict | None = None,
    ) -> ScanResult:
        """Scan content for injection patterns and reject if detected.

        Args:
            content: The content to scan. Can be a string, dict, list, or
                any JSON-serializable value.
            source_id: Identifier of the agent or source providing the content.
            source_type: Category of the source (e.g., "agent", "workflow", "api").
            context: Optional additional context passed to the detector.

        Returns:
            ScanResult with scan details when content is allowed.

        Raises:
            ContextPoisoningError: When injection patterns are detected and
                the guard is enabled.
        """
        timestamp = datetime.now(UTC).isoformat()
        self._scan_count += 1

        if not self._enabled:
            logger.debug(
                "Context integrity guard disabled, allowing content",
                source_id=source_id,
                source_type=source_type,
            )
            return ScanResult(
                allowed=True,
                source_id=source_id,
                source_type=source_type,
                timestamp=timestamp,
                detection_result=InjectionDetectionResult(
                    is_injection=False,
                    confidence=0.0,
                    metadata={"guard_disabled": True},
                ),
                metadata=_build_metadata(source_id, source_type),
            )

        scan_context: JSONDict = {"source_id": source_id, "source_type": source_type}
        if context:
            scan_context.update(context)

        detection_result = self._detector.detect(content, context=scan_context)

        if detection_result.is_injection:
            self._rejection_count += 1
            severity_str = (
                detection_result.severity.value if detection_result.severity else "unknown"
            )

            logger.warning(
                "Context poisoning attempt detected — rejecting content",
                source_id=source_id,
                source_type=source_type,
                severity=severity_str,
                confidence=detection_result.confidence,
                pattern_count=len(detection_result.matched_patterns),
                owasp_category="AA05",
            )

            raise ContextPoisoningError(
                message=(
                    f"Content from source '{source_id}' ({source_type}) "
                    f"rejected: injection patterns detected "
                    f"(severity={severity_str}, "
                    f"confidence={detection_result.confidence:.2f})"
                ),
                source_id=source_id,
                source_type=source_type,
                matched_patterns=detection_result.matched_patterns,
                severity=severity_str,
                confidence=detection_result.confidence,
            )

        logger.debug(
            "Context integrity scan passed",
            source_id=source_id,
            source_type=source_type,
            confidence=detection_result.confidence,
        )

        return ScanResult(
            allowed=True,
            source_id=source_id,
            source_type=source_type,
            timestamp=timestamp,
            detection_result=detection_result,
            metadata=_build_metadata(source_id, source_type),
        )

    def enrich_metadata(
        self,
        metadata: MetadataDict,
        *,
        source_id: str = "",
        source_type: str = "unknown",
    ) -> MetadataDict:
        """Add source provenance fields to memory entry metadata.

        Creates a new dict with source_id and source_type added, without
        mutating the input.

        Args:
            metadata: Original metadata dict.
            source_id: Identifier of the content source.
            source_type: Category of the source.

        Returns:
            New metadata dict with provenance fields added.
        """
        return {
            **metadata,
            **_build_metadata(source_id, source_type),
        }

    def get_stats(self) -> JSONDict:
        """Return guard statistics.

        Returns:
            Dictionary with scan_count, rejection_count, and enabled state.
        """
        return {
            "enabled": self._enabled,
            "scan_count": self._scan_count,
            "rejection_count": self._rejection_count,
        }


def _build_metadata(source_id: str, source_type: str) -> MetadataDict:
    """Build provenance metadata dict for a memory entry.

    Args:
        source_id: Identifier of the content source.
        source_type: Category of the source.

    Returns:
        Metadata dict with source provenance fields.
    """
    return {
        "source_id": source_id,
        "source_type": source_type,
        "scanned_at": datetime.now(UTC).isoformat(),
    }
