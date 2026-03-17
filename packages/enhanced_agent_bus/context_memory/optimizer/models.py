"""
ACGS-2 Context Optimizer - Models
Constitutional Hash: cdd01ef066bc6cf2

Data models for context optimization results and cache entries.
"""

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Optional

from src.core.shared.constants import CONSTITUTIONAL_HASH

try:
    from src.core.shared.types import JSONDict, JSONList
except ImportError:
    JSONDict: type = JSONDict  # type: ignore[no-redef]
    JSONList: type = JSONList  # type: ignore[no-redef]


@dataclass
class BatchProcessingResult:
    """Result of batch processing operation.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    chunks_processed: int
    successful_chunks: int
    failed_chunks: int
    processing_time_ms: float
    parallel_factor: int
    outputs: JSONList = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    constitutional_validated: bool = True
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ScoringResult:
    """Result of vectorized scoring operation.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    scores: list[float]
    scoring_time_ms: float
    batch_size: int
    vectorized: bool
    constitutional_boosts_applied: int
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class StreamingResult:
    """Result of streaming processing.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    output_embeddings: object
    chunks_streamed: int
    overlap_tokens: int
    total_tokens: int
    processing_time_ms: float
    memory_peak_mb: float
    constitutional_validated: bool = True
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class AdaptiveCacheEntry:
    """Cache entry with adaptive TTL.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    key: str
    value: object
    created_at: datetime
    base_ttl_seconds: int
    access_count: int = 0
    last_accessed: datetime | None = None
    is_constitutional: bool = False
    access_pattern: list[float] = field(default_factory=list)
    predicted_next_access: float | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def get_adaptive_ttl(self, multiplier: float = 1.5) -> int:
        """Calculate adaptive TTL based on access patterns."""
        if self.access_count == 0:
            return self.base_ttl_seconds

        # Boost TTL for frequently accessed items
        boost = min(10.0, 1.0 + (self.access_count * 0.1))

        # Extra boost for constitutional content
        if self.is_constitutional:
            boost *= 2.0

        return int(self.base_ttl_seconds * boost * multiplier)

    def record_access(self) -> None:
        """Record an access and update pattern."""
        now = time.perf_counter()
        self.access_count += 1
        self.last_accessed = datetime.now(UTC)

        # Track access pattern for prediction
        self.access_pattern.append(now)
        if len(self.access_pattern) > 100:
            self.access_pattern = self.access_pattern[-100:]

        # Predict next access (simple moving average of intervals)
        if len(self.access_pattern) >= 2:
            intervals = [
                self.access_pattern[i] - self.access_pattern[i - 1]
                for i in range(1, len(self.access_pattern))
            ]
            avg_interval = sum(intervals) / len(intervals)
            self.predicted_next_access = now + avg_interval

    def is_expired(self, current_time: datetime) -> bool:
        """Check if entry has expired with adaptive TTL."""
        ttl = self.get_adaptive_ttl()
        expiry = self.created_at + timedelta(seconds=ttl)
        return current_time > expiry


__all__ = [
    "CONSTITUTIONAL_HASH",
    "AdaptiveCacheEntry",
    "BatchProcessingResult",
    "JSONDict",
    "ScoringResult",
    "StreamingResult",
]
