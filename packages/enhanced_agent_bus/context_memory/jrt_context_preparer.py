"""
ACGS-2 Context & Memory - JRT Context Preparer
Constitutional Hash: cdd01ef066bc6cf2

Implements Just-in-Time Retrieval (JRT) context preparation for optimal
LLM performance. Repeats critical sections for better recall and uses
smart windowing based on relevance.

Key Features:
- Critical section repetition (3x default) for better recall
- Smart context windowing based on relevance scores
- Priority-based context injection
- Constitutional context always present and prioritized
"""

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from packages.enhanced_agent_bus.bus_types import JSONDict
from src.core.shared.constants import CONSTITUTIONAL_HASH

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import (
    ContextChunk,
    ContextPriority,
    ContextType,
    ContextWindow,
    JRTConfig,
)

logger = get_logger(__name__)


class JRTRetrievalStrategy(str, Enum):  # noqa: UP042
    """Retrieval strategies for JRT context preparation."""

    RELEVANCE_FIRST = "relevance_first"  # Sort by relevance score
    RECENCY_FIRST = "recency_first"  # Sort by recency
    PRIORITY_FIRST = "priority_first"  # Sort by priority
    BALANCED = "balanced"  # Balance all factors
    CONSTITUTIONAL_WEIGHTED = "constitutional_weighted"  # Extra weight for constitutional


@dataclass
class CriticalSectionMarker:
    """Marks a critical section in the context.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    start_position: int
    end_position: int
    section_type: ContextType
    priority: ContextPriority
    repetition_count: int = 3
    content_hash: str = ""
    source_chunk_id: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = hashlib.sha256(
                f"{self.start_position}:{self.end_position}".encode()
            ).hexdigest()[:16]


@dataclass
class JRTPreparationResult:
    """Result of JRT context preparation.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    prepared_window: ContextWindow
    original_tokens: int
    prepared_tokens: int
    critical_sections: list[CriticalSectionMarker]
    repetitions_applied: int
    preparation_time_ms: float
    relevance_scores: dict[str, float] = field(default_factory=dict)
    constitutional_context_present: bool = True
    warnings: list[str] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


class JRTContextPreparer:
    """Prepares context using Just-in-Time Retrieval techniques.

    Optimizes context for LLM processing by:
    - Repeating critical sections for better recall
    - Smart windowing based on relevance
    - Priority-based ordering
    - Always including constitutional context

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        config: JRTConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.config = config or JRTConfig()
        self.constitutional_hash = constitutional_hash

        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {constitutional_hash}")

        # Constitutional context (always present)
        self._constitutional_context: list[ContextChunk] = []

        # Relevance scoring function (can be customized)
        self._relevance_scorer: Callable | None = None

        # Metrics
        self._metrics = {
            "preparations": 0,
            "total_repetitions": 0,
            "total_tokens_saved": 0,
            "average_relevance": 0.0,
        }

        logger.info(
            f"Initialized JRTContextPreparer (repetition_factor={self.config.repetition_factor})"
        )

    def set_constitutional_context(self, chunks: list[ContextChunk]) -> None:
        """Set the constitutional context that is always present.

        Args:
            chunks: List of constitutional context chunks
        """
        self._constitutional_context = [
            ContextChunk(
                content=c.content,
                context_type=ContextType.CONSTITUTIONAL,
                priority=ContextPriority.CRITICAL,
                token_count=c.token_count,
                relevance_score=1.0,
                is_critical=True,
                source_id=c.source_id,
                metadata={**c.metadata, "constitutional": True},
                constitutional_hash=self.constitutional_hash,
            )
            for c in chunks
        ]
        logger.info(f"Set {len(self._constitutional_context)} constitutional context chunks")

    def set_relevance_scorer(self, scorer: Callable[[str, str], float]) -> None:
        """Set custom relevance scoring function.

        Args:
            scorer: Function(query, content) -> float [0, 1]
        """
        self._relevance_scorer = scorer

    async def prepare_context(
        self,
        query: str,
        available_chunks: list[ContextChunk],
        strategy: JRTRetrievalStrategy = JRTRetrievalStrategy.CONSTITUTIONAL_WEIGHTED,
        max_tokens: int | None = None,
    ) -> JRTPreparationResult:
        """Prepare context for LLM processing using JRT techniques.

        Args:
            query: The query/task for context relevance scoring
            available_chunks: Pool of available context chunks
            strategy: Retrieval strategy to use
            max_tokens: Maximum tokens in prepared context

        Returns:
            JRTPreparationResult with prepared context window
        """
        start_time = time.perf_counter()
        max_tokens = max_tokens or self.config.context_window_size
        warnings = []

        # 1. Score relevance for each chunk
        scored_chunks = await self._score_chunks(query, available_chunks)

        # 2. Identify critical sections
        critical_sections = self._identify_critical_sections(scored_chunks)

        # 3. Filter by relevance threshold
        relevant_chunks = [
            (chunk, score)
            for chunk, score in scored_chunks
            if score >= self.config.relevance_threshold
        ]

        # 4. Apply retrieval strategy
        ordered_chunks = self._apply_strategy(relevant_chunks, strategy)

        # 5. Build context window with repetitions
        prepared_window = await self._build_window_with_repetitions(
            query=query,
            ordered_chunks=ordered_chunks,
            critical_sections=critical_sections,
            max_tokens=max_tokens,
        )

        # 6. Ensure constitutional context is present
        constitutional_present = self._ensure_constitutional_context(prepared_window)
        if not constitutional_present:
            warnings.append("Constitutional context could not be fully included")

        # Calculate stats
        original_tokens = sum(c.token_count for c in available_chunks)
        prepared_tokens = prepared_window.total_tokens
        repetitions = sum(
            s.repetition_count - 1 for s in critical_sections if s.repetition_count > 1
        )

        # Update metrics
        self._metrics["preparations"] += 1
        self._metrics["total_repetitions"] += repetitions
        self._metrics["total_tokens_saved"] += original_tokens - prepared_tokens

        preparation_time = (time.perf_counter() - start_time) * 1000

        return JRTPreparationResult(
            prepared_window=prepared_window,
            original_tokens=original_tokens,
            prepared_tokens=prepared_tokens,
            critical_sections=critical_sections,
            repetitions_applied=repetitions,
            preparation_time_ms=preparation_time,
            relevance_scores={chunk.chunk_id: score for chunk, score in scored_chunks},
            constitutional_context_present=constitutional_present,
            warnings=warnings,
            metadata={
                "strategy": strategy.value,
                "chunks_considered": len(available_chunks),
                "chunks_included": len(prepared_window.chunks),
            },
            constitutional_hash=self.constitutional_hash,
        )

    async def _score_chunks(
        self,
        query: str,
        chunks: list[ContextChunk],
    ) -> list[tuple[ContextChunk, float]]:
        """Score chunks for relevance to query."""
        scored = []

        for chunk in chunks:
            # Use custom scorer if available
            if self._relevance_scorer:
                base_score = self._relevance_scorer(query, chunk.content)
            else:
                base_score = self._default_relevance_score(query, chunk.content)

            # Apply constitutional priority boost
            if chunk.context_type == ContextType.CONSTITUTIONAL:
                base_score = min(1.0, base_score + self.config.constitutional_priority_boost)

            # Apply priority boost
            priority_boost = chunk.priority.value * 0.05
            final_score = min(1.0, base_score + priority_boost)

            # Store relevance score in chunk
            chunk.relevance_score = final_score
            scored.append((chunk, final_score))

        return scored

    def _default_relevance_score(self, query: str, content: str) -> float:
        """Default relevance scoring using simple term overlap."""
        query_terms = set(query.lower().split())
        content_terms = set(content.lower().split())

        if not query_terms:
            return 0.5

        overlap = len(query_terms & content_terms)
        return min(1.0, overlap / len(query_terms))

    def _identify_critical_sections(
        self,
        scored_chunks: list[tuple[ContextChunk, float]],
    ) -> list[CriticalSectionMarker]:
        """Identify critical sections for repetition."""
        critical = []
        position = 0

        # Sort by score for critical identification
        sorted_chunks = sorted(scored_chunks, key=lambda x: x[1], reverse=True)

        for chunk, score in sorted_chunks[: self.config.max_critical_sections]:
            # Mark as critical if high score or constitutional
            if score >= 0.8 or chunk.context_type == ContextType.CONSTITUTIONAL:
                marker = CriticalSectionMarker(
                    start_position=position,
                    end_position=position + chunk.token_count,
                    section_type=chunk.context_type,
                    priority=chunk.priority,
                    repetition_count=self.config.repetition_factor,
                    source_chunk_id=chunk.chunk_id,
                    constitutional_hash=self.constitutional_hash,
                )
                critical.append(marker)
                chunk.is_critical = True

            position += chunk.token_count

        return critical

    def _apply_strategy(
        self,
        chunks: list[tuple[ContextChunk, float]],
        strategy: JRTRetrievalStrategy,
    ) -> list[ContextChunk]:
        """Apply retrieval strategy to order chunks."""
        if strategy == JRTRetrievalStrategy.RELEVANCE_FIRST:
            sorted_items = sorted(chunks, key=lambda x: x[1], reverse=True)

        elif strategy == JRTRetrievalStrategy.RECENCY_FIRST:
            sorted_items = sorted(chunks, key=lambda x: x[0].created_at, reverse=True)

        elif strategy == JRTRetrievalStrategy.PRIORITY_FIRST:
            sorted_items = sorted(chunks, key=lambda x: x[0].priority.value, reverse=True)

        elif strategy == JRTRetrievalStrategy.CONSTITUTIONAL_WEIGHTED:

            def weighted_score(item: tuple[ContextChunk, float]) -> float:
                chunk, score = item
                boost = 0.5 if chunk.context_type == ContextType.CONSTITUTIONAL else 0
                return score + chunk.priority.value * 0.1 + boost

            sorted_items = sorted(chunks, key=weighted_score, reverse=True)

        else:  # BALANCED

            def balanced_score(item: tuple[ContextChunk, float]) -> float:
                chunk, score = item
                recency_score = 1.0  # Would calculate based on age
                return score * 0.4 + chunk.priority.value * 0.1 + recency_score * 0.5

            sorted_items = sorted(chunks, key=balanced_score, reverse=True)

        return [chunk for chunk, _ in sorted_items]

    async def _build_window_with_repetitions(
        self,
        query: str,
        ordered_chunks: list[ContextChunk],
        critical_sections: list[CriticalSectionMarker],
        max_tokens: int,
    ) -> ContextWindow:
        """Build context window with critical section repetitions."""
        window = ContextWindow(
            max_tokens=max_tokens,
            constitutional_hash=self.constitutional_hash,
        )

        # Track which chunks are critical
        critical_chunk_ids = {s.source_chunk_id for s in critical_sections}

        # Add constitutional context first (always)
        for chunk in self._constitutional_context:
            if not window.add_chunk(chunk):
                break

        # Add chunks with repetitions for critical ones
        added_ids: set[str] = set()

        for chunk in ordered_chunks:
            if chunk.chunk_id in added_ids:
                continue

            # Add original chunk
            if not window.add_chunk(chunk):
                break
            added_ids.add(chunk.chunk_id)

            # Add repetitions for critical chunks
            if chunk.chunk_id in critical_chunk_ids:
                for i in range(self.config.repetition_factor - 1):
                    repeated = ContextChunk(
                        content=chunk.content,
                        context_type=chunk.context_type,
                        priority=chunk.priority,
                        token_count=chunk.token_count,
                        relevance_score=chunk.relevance_score * 0.9,  # Slight decay
                        is_critical=True,
                        source_id=chunk.chunk_id,
                        metadata={
                            **chunk.metadata,
                            "repetition": i + 2,
                            "original_chunk_id": chunk.chunk_id,
                        },
                        constitutional_hash=self.constitutional_hash,
                    )
                    if not window.add_chunk(repeated):
                        break

        return window

    def _ensure_constitutional_context(self, window: ContextWindow) -> bool:
        """Ensure constitutional context is present in window."""
        # Check if constitutional context already present
        constitutional_chunks = window.get_by_type(ContextType.CONSTITUTIONAL)
        if constitutional_chunks:
            return True

        # Try to add constitutional context
        all_added = True
        for chunk in self._constitutional_context:
            if not window.add_chunk(chunk):
                all_added = False
                break

        return all_added

    def create_smart_window(
        self,
        chunks: list[ContextChunk],
        target_tokens: int,
    ) -> ContextWindow:
        """Create a smart context window with relevance-based selection.

        Args:
            chunks: Available chunks
            target_tokens: Target token count

        Returns:
            Optimized ContextWindow
        """
        window = ContextWindow(
            max_tokens=target_tokens,
            constitutional_hash=self.constitutional_hash,
        )

        # Sort by relevance and priority
        sorted_chunks = sorted(
            chunks,
            key=lambda c: (c.priority.value, c.relevance_score),
            reverse=True,
        )

        # Add until full
        for chunk in sorted_chunks:
            if not window.add_chunk(chunk):
                break

        return window

    def get_metrics(self) -> JSONDict:
        """Get JRT preparation metrics."""
        avg_relevance = 0.0
        if self._metrics["preparations"] > 0:
            avg_relevance = self._metrics["total_repetitions"] / self._metrics["preparations"]

        return {
            **self._metrics,
            "average_repetitions_per_prep": avg_relevance,
            "constitutional_context_chunks": len(self._constitutional_context),
            "constitutional_hash": self.constitutional_hash,
        }


__all__ = [
    "CONSTITUTIONAL_HASH",
    "CriticalSectionMarker",
    "JRTContextPreparer",
    "JRTPreparationResult",
    "JRTRetrievalStrategy",
]
