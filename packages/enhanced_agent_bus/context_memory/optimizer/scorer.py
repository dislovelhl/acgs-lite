"""
ACGS-2 Context Optimizer - Vectorized Scorer
Constitutional Hash: cdd01ef066bc6cf2

Vectorized relevance scoring using numpy for batch operations.
"""

import time

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict: type = JSONDict  # type: ignore[no-redef]

from enhanced_agent_bus.context_memory.models import ContextChunk, ContextType

from .models import ScoringResult

# Check for numpy availability for vectorized operations
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None  # type: ignore[assignment]


class VectorizedScorer:
    """Vectorized relevance scoring using numpy.

    Provides batch scoring with SIMD-friendly operations for
    improved performance on large context windows.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        batch_size: int = 256,
        constitutional_boost: float = 0.3,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.batch_size = batch_size
        self.constitutional_boost = constitutional_boost
        self.constitutional_hash = constitutional_hash

        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {constitutional_hash}")

        # Pre-computed term vectors for common queries
        self._term_cache: JSONDict = {}

        # Metrics
        self._total_scored = 0
        self._total_time_ms = 0.0

    def score_batch(
        self,
        query: str,
        chunks: list[ContextChunk],
        custom_weights: dict[str, float] | None = None,
    ) -> ScoringResult:
        """Score a batch of chunks against a query.

        Args:
            query: Search query
            chunks: List of chunks to score
            custom_weights: Optional custom scoring weights

        Returns:
            ScoringResult with relevance scores
        """
        start_time = time.perf_counter()
        constitutional_boosts = 0

        if not chunks:
            return ScoringResult(
                scores=[],
                scoring_time_ms=0.0,
                batch_size=0,
                vectorized=False,
                constitutional_boosts_applied=0,
                constitutional_hash=self.constitutional_hash,
            )

        # Use vectorized scoring if numpy available and batch large enough
        if NUMPY_AVAILABLE and len(chunks) >= 4:
            scores, constitutional_boosts = self._vectorized_score(query, chunks)
            vectorized = True
        else:
            scores, constitutional_boosts = self._sequential_score(query, chunks)
            vectorized = False

        # Apply custom weights if provided
        if custom_weights:
            scores = self._apply_weights(scores, chunks, custom_weights)

        scoring_time = (time.perf_counter() - start_time) * 1000
        self._total_scored += len(chunks)
        self._total_time_ms += scoring_time

        return ScoringResult(
            scores=scores,
            scoring_time_ms=scoring_time,
            batch_size=len(chunks),
            vectorized=vectorized,
            constitutional_boosts_applied=constitutional_boosts,
            metadata={
                "query_length": len(query),
                "avg_chunk_length": sum(c.token_count for c in chunks) / len(chunks),
            },
            constitutional_hash=self.constitutional_hash,
        )

    def _vectorized_score(
        self,
        query: str,
        chunks: list[ContextChunk],
    ) -> tuple[list[float], int]:
        """Vectorized scoring using numpy."""
        # Tokenize query
        query_terms = set(query.lower().split())
        if not query_terms:
            return [0.5] * len(chunks), 0

        # Build term presence matrix
        n_chunks = len(chunks)
        n_terms = len(query_terms)
        term_list = list(query_terms)

        # Create term presence matrix (chunks x terms)
        presence_matrix = np.zeros((n_chunks, n_terms), dtype=np.float32)

        for i, chunk in enumerate(chunks):
            chunk_terms = set(chunk.content.lower().split())
            for j, term in enumerate(term_list):
                if term in chunk_terms:
                    presence_matrix[i, j] = 1.0

        # Calculate overlap scores (normalized)
        overlap_counts = presence_matrix.sum(axis=1)
        base_scores = overlap_counts / n_terms

        # Apply priority boosts
        priority_boosts = np.array([c.priority.value * 0.05 for c in chunks], dtype=np.float32)
        scores = np.minimum(1.0, base_scores + priority_boosts)

        # Apply constitutional boosts
        constitutional_boosts = 0
        for i, chunk in enumerate(chunks):
            if chunk.context_type == ContextType.CONSTITUTIONAL:
                scores[i] = min(1.0, scores[i] + self.constitutional_boost)
                constitutional_boosts += 1

        return scores.tolist(), constitutional_boosts

    def _sequential_score(
        self,
        query: str,
        chunks: list[ContextChunk],
    ) -> tuple[list[float], int]:
        """Sequential scoring fallback."""
        query_terms = set(query.lower().split())
        if not query_terms:
            return [0.5] * len(chunks), 0

        scores = []
        constitutional_boosts = 0

        for chunk in chunks:
            chunk_terms = set(chunk.content.lower().split())
            overlap = len(query_terms & chunk_terms)
            base_score = overlap / len(query_terms)

            # Priority boost
            priority_boost = chunk.priority.value * 0.05
            score = min(1.0, base_score + priority_boost)

            # Constitutional boost
            if chunk.context_type == ContextType.CONSTITUTIONAL:
                score = min(1.0, score + self.constitutional_boost)
                constitutional_boosts += 1

            scores.append(score)

        return scores, constitutional_boosts

    def _apply_weights(
        self,
        scores: list[float],
        chunks: list[ContextChunk],
        weights: dict[str, float],
    ) -> list[float]:
        """Apply custom weights to scores."""
        weighted_scores = []
        for _idx, (score, chunk) in enumerate(zip(scores, chunks, strict=False)):
            # Apply type weight
            type_weight = weights.get(chunk.context_type.value, 1.0)
            # Apply priority weight
            priority_weight = weights.get(f"priority_{chunk.priority.value}", 1.0)

            weighted_score = score * type_weight * priority_weight
            weighted_scores.append(min(1.0, weighted_score))

        return weighted_scores

    def get_metrics(self) -> JSONDict:
        """Get scorer metrics."""
        avg_time = self._total_time_ms / max(1, self._total_scored)
        return {
            "total_scored": self._total_scored,
            "total_time_ms": self._total_time_ms,
            "average_time_per_chunk_ms": avg_time,
            "numpy_available": NUMPY_AVAILABLE,
            "constitutional_hash": self.constitutional_hash,
        }


__all__ = [
    "NUMPY_AVAILABLE",
    "VectorizedScorer",
]
