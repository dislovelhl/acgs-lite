"""
ContextCoordinator - Mamba-2 hybrid context processing coordinator.

Manages large-context processing via Mamba-2 with graceful fallback.
Part of the MetaOrchestrator decomposition effort.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

import psutil

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

if TYPE_CHECKING:
    from enhanced_agent_bus.mamba2_hybrid_processor import (
        ConstitutionalContextManager,
    )


@runtime_checkable
class ContextCoordinatorProtocol(Protocol):
    """Protocol defining the ContextCoordinator interface."""

    constitutional_hash: str

    async def process_with_context(
        self,
        input_text: str,
        context_window: list[str] | None = None,
        critical_keywords: list[str] | None = None,
    ) -> ContextProcessingResult: ...

    def get_context_stats(self) -> JSONDict: ...

    def is_mamba_available(self) -> bool: ...


logger = get_logger(__name__)
DEFAULT_CACHE_HASH_MODE = "sha256"
_CACHE_HASH_MODES = {"sha256", "fast"}
MAMBA_CONTEXT_OPERATION_ERRORS = (
    AttributeError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)

# Import Mamba availability flag
try:
    from enhanced_agent_bus.mamba2_hybrid_processor import (
        MAMBA_AVAILABLE,
        create_constitutional_context_manager,
    )
except ImportError:
    MAMBA_AVAILABLE = False
    create_constitutional_context_manager = None  # type: ignore[misc,assignment]
    logger.warning("Mamba-2 processor not available - using fallback context processing")

try:
    from acgs2_perf import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:
    FAST_HASH_AVAILABLE = False


@dataclass
class ContextProcessingResult:
    """Result of context processing operation."""

    input_text: str
    context_length: int
    compliance_score: float
    constitutional_hash: str
    critical_keywords_detected: list[str]
    mamba_processed: bool
    cache_hit: bool = False


class ContextCoordinator:
    """
    Manages large-context processing via Mamba-2.

    Responsibilities:
    - Mamba-2 hybrid context processing
    - Constitutional context management
    - 100K+ token context handling
    - Context caching and optimization
    - Graceful fallback when Mamba-2 unavailable
    """

    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __init__(
        self,
        context_size: int = 100_000,
        enable_caching: bool = True,
        memory_threshold: float = 0.85,
        cache_hash_mode: Literal["sha256", "fast"] = DEFAULT_CACHE_HASH_MODE,
    ):
        """
        Initialize ContextCoordinator.

        Args:
            context_size: Maximum context size in tokens (default 100K)
            enable_caching: Whether to enable context caching
            memory_threshold: Threshold ratio (0.0 to 1.0) above which Mamba processing gracefully degrades.
            cache_hash_mode: Cache key hash mode ("sha256" default, "fast" optional)
        """
        self._context_size = context_size
        self._enable_caching = enable_caching
        self._memory_threshold = memory_threshold
        if cache_hash_mode not in _CACHE_HASH_MODES:
            raise ValueError(f"Invalid cache_hash_mode: {cache_hash_mode}")
        self._cache_hash_mode = cache_hash_mode
        self._cache: dict[str, ContextProcessingResult] = {}
        self._total_processed = 0
        self._cache_hits = 0
        self._degradations = 0

        # Initialize Mamba-2 context manager if available
        self._mamba_context: ConstitutionalContextManager | None = None
        if MAMBA_AVAILABLE and create_constitutional_context_manager:
            try:
                self._mamba_context = create_constitutional_context_manager()
                logger.info(
                    f"ContextCoordinator: Mamba-2 initialized (context_size={context_size})"
                )
            except (RuntimeError, ValueError, TypeError, ImportError) as e:
                logger.warning(f"Mamba-2 initialization failed: {e}")
                self._mamba_context = None

        if self._cache_hash_mode == "fast" and not FAST_HASH_AVAILABLE:
            logger.warning(
                "cache_hash_mode=fast requested but acgs2_perf.fast_hash unavailable; "
                "falling back to sha256"
            )

    def is_mamba_available(self) -> bool:
        """Check if Mamba-2 context processing is available."""
        return self._mamba_context is not None

    async def process_with_context(
        self,
        input_text: str,
        context_window: list[str] | None = None,
        critical_keywords: list[str] | None = None,
    ) -> ContextProcessingResult:
        """
        Process input with full constitutional context.

        Args:
            input_text: Input text to process
            context_window: Recent context for continuity
            critical_keywords: Keywords to preserve in context

        Returns:
            ContextProcessingResult with compliance scores and metadata
        """
        # Check cache first if enabled
        if self._enable_caching:
            cache_key = self._generate_cache_key(input_text, context_window, critical_keywords)
            if cache_key in self._cache:
                self._cache_hits += 1
                result = self._cache[cache_key]
                result.cache_hit = True
                return result

        # Check memory pressure before utilizing Mamba-2
        memory_usage = psutil.virtual_memory().percent
        if memory_usage > (self._memory_threshold * 100):
            logger.warning(
                f"Memory pressure high ({memory_usage}% > {self._memory_threshold * 100}% threshold). "
                "Degrading gracefully to fallback context processing."
            )
            self._degradations += 1
            result = await self._process_with_fallback(
                input_text, context_window, critical_keywords
            )
        elif self._mamba_context is not None:
            try:
                result = await self._process_with_mamba(
                    input_text, context_window, critical_keywords
                )
                self._total_processed += 1

                if self._enable_caching:
                    self._cache[cache_key] = result

                return result
            except MAMBA_CONTEXT_OPERATION_ERRORS as e:
                logger.warning(f"Mamba-2 processing failed, falling back: {e}")
                result = await self._process_with_fallback(
                    input_text, context_window, critical_keywords
                )
        else:
            # Fallback processing when Mamba-2 isn't available
            result = await self._process_with_fallback(
                input_text, context_window, critical_keywords
            )

        self._total_processed += 1

        if self._enable_caching:
            self._cache[cache_key] = result

        return result

    async def _process_with_mamba(
        self,
        input_text: str,
        context_window: list[str] | None,
        critical_keywords: list[str] | None,
    ) -> ContextProcessingResult:
        """Process using Mamba-2 context manager."""
        if self._mamba_context is None:
            raise RuntimeError("Mamba context not available")

        # Build full context
        full_context = self._build_context(input_text, context_window)

        # Process through Mamba
        mamba_result = await self._mamba_context.process_with_context(
            input_text=full_context,
            context_window=context_window,
            critical_keywords=critical_keywords,
        )

        # Detect critical keywords
        detected_keywords = self._detect_critical_keywords(full_context, critical_keywords or [])

        return ContextProcessingResult(
            input_text=input_text,
            context_length=len(full_context),
            compliance_score=mamba_result.get("compliance_score", 0.5),
            constitutional_hash=CONSTITUTIONAL_HASH,
            critical_keywords_detected=detected_keywords,
            mamba_processed=True,
            cache_hit=False,
        )

    async def _process_with_fallback(
        self,
        input_text: str,
        context_window: list[str] | None,
        critical_keywords: list[str] | None,
    ) -> ContextProcessingResult:
        """Fallback processing when Mamba-2 is unavailable."""
        # Build full context
        full_context = self._build_context(input_text, context_window)

        # Truncate if exceeds context size (simple word-based truncation)
        words = full_context.split()
        if len(words) > self._context_size:
            # Preserve beginning and end, truncate middle
            keep_start = self._context_size // 4
            keep_end = self._context_size // 4
            truncated = words[:keep_start] + ["..."] + words[-keep_end:]
            full_context = " ".join(truncated)

        # Detect critical keywords
        detected_keywords = self._detect_critical_keywords(full_context, critical_keywords or [])

        # Calculate compliance score based on keywords and content
        compliance_score = self._calculate_fallback_compliance(full_context, detected_keywords)

        return ContextProcessingResult(
            input_text=input_text,
            context_length=len(full_context),
            compliance_score=compliance_score,
            constitutional_hash=CONSTITUTIONAL_HASH,
            critical_keywords_detected=detected_keywords,
            mamba_processed=False,
            cache_hit=False,
        )

    def _build_context(self, input_text: str, context_window: list[str] | None) -> str:
        """Build full context from input and recent history."""
        if not context_window:
            return input_text

        # Combine recent context with current input
        recent_context = " ".join(context_window[-5:])  # Last 5 entries
        return f"{recent_context} {input_text}"

    def _detect_critical_keywords(self, text: str, keywords: list[str]) -> list[str]:
        """Detect critical keywords in text (case-insensitive)."""
        text_lower = text.lower()
        detected = []

        for keyword in keywords:
            if keyword.lower() in text_lower:
                detected.append(keyword)

        return detected

    def _calculate_fallback_compliance(self, text: str, detected_keywords: list[str]) -> float:
        """Calculate a compliance score for fallback mode."""
        # Base score
        base_score = 0.7

        # Boost for critical keywords (up to 0.2)
        keyword_boost = min(len(detected_keywords) * 0.05, 0.2)

        # Text length factor (longer text = slightly higher confidence)
        length_factor = min(len(text) / 10000, 0.1)

        # Calculate final score
        score = base_score + keyword_boost + length_factor

        # Ensure within 0-1 range
        return min(max(score, 0.0), 1.0)

    def _generate_cache_key(
        self,
        input_text: str,
        context_window: list[str] | None,
        critical_keywords: list[str] | None,
    ) -> str:
        """Generate cache key for input combination."""
        key_parts = [input_text]
        if context_window:
            key_parts.extend(context_window)
        if critical_keywords:
            key_parts.extend(sorted(critical_keywords))

        key_string = "|".join(key_parts)
        if self._cache_hash_mode == "fast" and FAST_HASH_AVAILABLE:
            return f"{fast_hash(key_string):016x}"
        return hashlib.sha256(key_string.encode()).hexdigest()[:32]

    def get_context_stats(self) -> JSONDict:
        """Get context processing statistics."""
        stats: JSONDict = {
            "constitutional_hash": self.constitutional_hash,
            "mamba_available": self.is_mamba_available(),
            "context_size": self._context_size,
            "cache_enabled": self._enable_caching,
            "cache_size": len(self._cache),
            "total_processed": self._total_processed,
            "cache_hits": self._cache_hits,
            "memory_threshold": self._memory_threshold,
            "current_memory_usage_percent": psutil.virtual_memory().percent,
            "degradations_due_to_memory": self._degradations,
        }

        # Add Mamba stats if available
        if self._mamba_context is not None and hasattr(self._mamba_context, "get_context_stats"):
            try:
                mamba_stats = self._mamba_context.get_context_stats()
                stats["mamba_stats"] = mamba_stats
            except MAMBA_CONTEXT_OPERATION_ERRORS as e:
                logger.warning(f"Failed to get Mamba stats: {e}")

        return stats

    def clear_cache(self) -> None:
        """Clear the context cache."""
        self._cache.clear()
        logger.debug("ContextCoordinator cache cleared")


__all__ = [
    "CONSTITUTIONAL_HASH",
    "ContextCoordinator",
    "ContextCoordinatorProtocol",
    "ContextProcessingResult",
]
