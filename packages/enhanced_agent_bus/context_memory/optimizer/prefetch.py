"""
ACGS-2 Context Optimizer - Prefetch Manager
Constitutional Hash: cdd01ef066bc6cf2

Intelligent prefetching based on access patterns.
"""

import asyncio
import inspect
from collections.abc import Callable

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
PREFETCH_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)

from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict: type = JSONDict  # type: ignore[no-redef]


class PrefetchManager:
    """Intelligent prefetching based on access patterns.

    Predicts and pre-loads likely needed context based on
    historical access patterns.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        threshold: float = 0.7,
        max_entries: int = 100,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.threshold = threshold
        self.max_entries = max_entries
        self.constitutional_hash = constitutional_hash

        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {constitutional_hash}")

        # Access pattern tracking
        self._access_sequences: list[list[str]] = []
        self._current_sequence: list[str] = []

        # Prefetch cache
        self._prefetch_cache: JSONDict = {}

        # Co-occurrence matrix for prediction
        self._co_occurrence: dict[str, dict[str, int]] = {}

        # Metrics
        self._prefetch_hits = 0
        self._prefetch_misses = 0

    def record_access(self, key: str) -> None:
        """Record an access to update patterns.

        Args:
            key: Accessed key
        """
        # Update current sequence
        self._current_sequence.append(key)
        if len(self._current_sequence) > 10:
            self._current_sequence = self._current_sequence[-10:]

        # Update co-occurrence
        for prev_key in self._current_sequence[:-1]:
            if prev_key not in self._co_occurrence:
                self._co_occurrence[prev_key] = {}
            if key not in self._co_occurrence[prev_key]:
                self._co_occurrence[prev_key][key] = 0
            self._co_occurrence[prev_key][key] += 1

    def predict_next(self, current_key: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Predict next likely accessed keys.

        Args:
            current_key: Current key
            top_k: Number of predictions

        Returns:
            List of (key, probability) tuples
        """
        if current_key not in self._co_occurrence:
            return []

        # Get co-occurrence counts
        successors = self._co_occurrence[current_key]
        total = sum(successors.values())

        if total == 0:
            return []

        # Calculate probabilities
        predictions = [
            (key, count / total)
            for key, count in successors.items()
            if count / total >= self.threshold
        ]

        # Sort by probability
        predictions.sort(key=lambda x: x[1], reverse=True)
        return predictions[:top_k]

    async def prefetch(
        self,
        current_key: str,
        fetch_fn: Callable[[str], object],
    ) -> int:
        """Prefetch predicted next entries.

        Args:
            current_key: Current accessed key
            fetch_fn: Function to fetch values

        Returns:
            Number of entries prefetched
        """
        predictions = self.predict_next(current_key)
        prefetched = 0

        for key, _prob in predictions:
            if key not in self._prefetch_cache and len(self._prefetch_cache) < self.max_entries:
                try:
                    if inspect.iscoroutinefunction(fetch_fn):
                        value = await fetch_fn(key)
                    else:
                        value = fetch_fn(key)
                    self._prefetch_cache[key] = value
                    prefetched += 1
                except PREFETCH_OPERATION_ERRORS as e:
                    logger.debug("Prefetch failed for key %s: %s", key, e)

        return prefetched

    def get_prefetched(self, key: str) -> object | None:
        """Get prefetched value if available.

        Args:
            key: Key to look up

        Returns:
            Prefetched value or None
        """
        if key in self._prefetch_cache:
            self._prefetch_hits += 1
            return self._prefetch_cache.pop(key)  # type: ignore[no-any-return]
        self._prefetch_misses += 1
        return None

    def clear_session(self) -> None:
        """Clear session-specific data."""
        self._current_sequence.clear()
        self._access_sequences.append(self._current_sequence.copy())
        if len(self._access_sequences) > 100:
            self._access_sequences = self._access_sequences[-100:]

    def get_metrics(self) -> JSONDict:
        """Get prefetch metrics."""
        total = self._prefetch_hits + self._prefetch_misses
        hit_rate = self._prefetch_hits / max(1, total)
        return {
            "prefetch_hits": self._prefetch_hits,
            "prefetch_misses": self._prefetch_misses,
            "prefetch_hit_rate": hit_rate,
            "cache_size": len(self._prefetch_cache),
            "co_occurrence_keys": len(self._co_occurrence),
            "threshold": self.threshold,
            "constitutional_hash": self.constitutional_hash,
        }


__all__ = [
    "PrefetchManager",
]
