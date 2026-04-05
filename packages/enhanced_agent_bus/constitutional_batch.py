"""
ACGS-2 Enhanced Agent Bus - Parallel Constitutional Validation
Constitutional Hash: 608508a9bd224290

High-performance parallel constitutional hash validation for batch operations.
Implements Phase 4-Task 4 acceptance criteria:
- Parallel hash validation
- Vectorized operations where possible
- Sub-millisecond validation per item
"""

import asyncio
import hmac
import time
from datetime import UTC, datetime
from typing import cast

from typing_extensions import TypedDict

from enhanced_agent_bus.observability.structured_logging import get_logger


class _ConstitutionalBatchMetrics(TypedDict):
    """Type definition for constitutional batch metrics."""

    total_validations: int
    valid_count: int
    invalid_count: int
    total_latency_ms: float
    batch_count: int
    created_at: str


try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

logger = get_logger(__name__)
# Default configuration
DEFAULT_MAX_PARALLEL = 100
DEFAULT_CHUNK_SIZE = 500
CONSTITUTIONAL_BATCH_VALIDATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


class ConstitutionalBatchValidator:
    """
    High-performance parallel constitutional hash validator for batch operations.

    Features:
    - Parallel validation using asyncio semaphore
    - Constant-time hash comparison for security
    - Sub-millisecond per-item validation
    - Metrics collection for observability
    - Fail-closed error handling

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        max_parallel: int = DEFAULT_MAX_PARALLEL,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ):
        """
        Initialize constitutional batch validator.

        Args:
            max_parallel: Maximum concurrent validations
            chunk_size: Items per processing chunk
        """
        self.max_parallel = max_parallel
        self.chunk_size = chunk_size
        self.constitutional_hash = CONSTITUTIONAL_HASH

        # Semaphore for concurrency control
        self._semaphore: asyncio.Semaphore | None = None

        # Metrics
        self._metrics: _ConstitutionalBatchMetrics = {
            "total_validations": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "total_latency_ms": 0.0,
            "batch_count": 0,
            "created_at": datetime.now(UTC).isoformat(),
        }

    async def __aenter__(self) -> "ConstitutionalBatchValidator":
        """Async context manager entry."""
        self._initialize_semaphore()
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Async context manager exit."""
        pass

    def _initialize_semaphore(self) -> None:
        """Initialize semaphore for concurrency control."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_parallel)

    def _constant_time_compare(self, a: str, b: str) -> bool:
        """
        Perform constant-time string comparison to prevent timing attacks.

        Uses hmac.compare_digest for cryptographic security.

        Args:
            a: First string
            b: Second string

        Returns:
            True if strings are equal
        """
        return hmac.compare_digest(a.encode(), b.encode())

    def _validate_hash(self, item_hash: str | None) -> bool:
        """
        Validate constitutional hash using constant-time comparison.

        Args:
            item_hash: Hash to validate

        Returns:
            True if hash matches constitutional hash
        """
        if item_hash is None:
            return False

        return self._constant_time_compare(item_hash, self.constitutional_hash)

    async def _validate_single(self, item: object, index: int) -> JSONDict:
        """
        Validate a single item's constitutional hash.

        Args:
            item: Item to validate
            index: Original index for order preservation

        Returns:
            Validation result dictionary
        """
        start_time = time.perf_counter()

        try:
            # Handle malformed items
            if item is None or not isinstance(item, dict):
                return {
                    "is_valid": False,
                    "index": index,
                    "error": "Invalid item format",
                    "constitutional_hash": self.constitutional_hash,
                }

            # Extract hash from item
            item_hash = item.get("constitutional_hash")

            # Validate hash
            is_valid = self._validate_hash(item_hash)

            result = {
                "is_valid": is_valid,
                "index": index,
                "constitutional_hash": self.constitutional_hash,
            }

            if not is_valid:
                result["error"] = "Constitutional hash validation failed"

            return result

        except CONSTITUTIONAL_BATCH_VALIDATION_ERRORS as e:
            # Fail closed on any error
            return {
                "is_valid": False,
                "index": index,
                "error": str(e),
                "constitutional_hash": self.constitutional_hash,
            }
        finally:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._metrics["total_latency_ms"] += elapsed_ms

    async def _validate_with_semaphore(self, item: object, index: int) -> JSONDict:
        """
        Validate with semaphore for concurrency control.

        Args:
            item: Item to validate
            index: Original index

        Returns:
            Validation result
        """
        if self._semaphore is None:
            self._initialize_semaphore()

        async with self._semaphore:
            return await self._validate_single(item, index)

    async def validate_batch(self, items: list[object]) -> list[JSONDict]:
        """
        Validate multiple items in parallel.

        Args:
            items: List of items to validate

        Returns:
            List of validation results in same order as inputs
        """
        if not items:
            return []

        # Initialize semaphore if needed
        self._initialize_semaphore()

        # Update metrics
        self._metrics["batch_count"] += 1
        self._metrics["total_validations"] += len(items)

        # Create validation tasks with index tracking
        tasks = [self._validate_with_semaphore(item, idx) for idx, item in enumerate(items)]

        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and handle exceptions
        final_results: list[JSONDict] = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                # Fail closed on exception
                final_results.append(
                    {
                        "is_valid": False,
                        "index": idx,
                        "error": str(result),
                        "constitutional_hash": self.constitutional_hash,
                    }
                )
                self._metrics["invalid_count"] += 1
            else:
                result_dict = cast(JSONDict, result)
                final_results.append(result_dict)
                if result_dict.get("is_valid", False):
                    self._metrics["valid_count"] += 1
                else:
                    self._metrics["invalid_count"] += 1

        # Sort by original index to maintain order
        final_results.sort(key=lambda x: x.get("index", 0))

        return final_results

    async def validate_batch_chunked(self, items: list[object]) -> list[JSONDict]:
        """
        Validate large batch in chunks for memory efficiency.

        Args:
            items: List of items to validate

        Returns:
            List of validation results in same order as inputs
        """
        if not items:
            return []

        if len(items) <= self.chunk_size:
            return await self.validate_batch(items)

        # Process in chunks
        all_results: list[JSONDict] = []
        for chunk_start in range(0, len(items), self.chunk_size):
            chunk_end = min(chunk_start + self.chunk_size, len(items))
            chunk = items[chunk_start:chunk_end]

            # Validate chunk with offset indices
            tasks = [
                self._validate_with_semaphore(item, chunk_start + idx)
                for idx, item in enumerate(chunk)
            ]

            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

            for idx, result in enumerate(chunk_results):
                actual_index = chunk_start + idx
                if isinstance(result, Exception):
                    all_results.append(
                        {
                            "is_valid": False,
                            "index": actual_index,
                            "error": str(result),
                            "constitutional_hash": self.constitutional_hash,
                        }
                    )
                    self._metrics["invalid_count"] += 1
                else:
                    result_dict = cast(JSONDict, result)
                    all_results.append(result_dict)
                    if result_dict.get("is_valid", False):
                        self._metrics["valid_count"] += 1
                    else:
                        self._metrics["invalid_count"] += 1

        # Update batch metrics
        self._metrics["batch_count"] += 1
        self._metrics["total_validations"] += len(items)

        # Sort by original index
        all_results.sort(key=lambda x: x.get("index", 0))

        return all_results

    def get_stats(self) -> JSONDict:
        """
        Get validation statistics.

        Returns:
            Dictionary with validator metrics
        """
        total = self._metrics["total_validations"]
        valid_rate = (self._metrics["valid_count"] / total * 100) if total > 0 else 0.0
        avg_latency = (self._metrics["total_latency_ms"] / total) if total > 0 else 0.0

        return {
            "constitutional_hash": self.constitutional_hash,
            "total_validations": self._metrics["total_validations"],
            "valid_count": self._metrics["valid_count"],
            "invalid_count": self._metrics["invalid_count"],
            "valid_rate": valid_rate,
            "batch_count": self._metrics["batch_count"],
            "avg_latency_ms": avg_latency,
            "max_parallel": self.max_parallel,
            "chunk_size": self.chunk_size,
            "created_at": self._metrics["created_at"],
        }


# Singleton instance for shared validator
_batch_validator: ConstitutionalBatchValidator | None = None
_batch_validator_lock = asyncio.Lock()


async def get_batch_validator(
    max_parallel: int = DEFAULT_MAX_PARALLEL,
) -> ConstitutionalBatchValidator:
    """
    Get or create shared constitutional batch validator singleton.

    Args:
        max_parallel: Max concurrent validations (only used on first call)

    Returns:
        Shared ConstitutionalBatchValidator instance
    """
    global _batch_validator

    if _batch_validator is not None:
        return _batch_validator

    async with _batch_validator_lock:
        if _batch_validator is None:
            _batch_validator = ConstitutionalBatchValidator(
                max_parallel=max_parallel,
            )

        return _batch_validator


async def reset_batch_validator() -> None:
    """Reset the shared validator singleton (for testing)."""
    global _batch_validator

    async with _batch_validator_lock:
        _batch_validator = None


__all__ = [
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_MAX_PARALLEL",
    "ConstitutionalBatchValidator",
    "get_batch_validator",
    "reset_batch_validator",
]
