"""
ACGS-2 Enhanced Agent Bus - OPA Batch Operations
Constitutional Hash: 608508a9bd224290

High-performance batch OPA policy evaluation optimization.
Implements Phase 4-Task 3 acceptance criteria:
- Batch OPA requests where possible
- Parallel OPA calls using asyncio
- Connection pooling for OPA client
"""

import asyncio
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from typing import Literal, cast

from typing_extensions import TypedDict

from enhanced_agent_bus.observability.structured_logging import get_logger


class _OPABatchMetrics(TypedDict):
    """Type definition for OPA batch metrics."""

    total_evaluations: int
    batch_evaluations: int
    cache_hits: int
    cache_misses: int
    errors: int
    total_latency_ms: float
    created_at: str


import httpx

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

try:
    from acgs2_perf import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:
    FAST_HASH_AVAILABLE = False

logger = get_logger(__name__)
# Default configuration
DEFAULT_MAX_CONCURRENT = 10
DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_CONNECTIONS = 20
DEFAULT_MAX_KEEPALIVE = 10
DEFAULT_TIMEOUT = 5.0
DEFAULT_CACHE_TTL = 300  # 5 minutes
DEFAULT_CACHE_HASH_MODE = "sha256"
_CACHE_HASH_MODES = {"sha256", "fast"}

OPA_EVALUATION_ERRORS = (
    httpx.HTTPError,
    json.JSONDecodeError,
    ValueError,
    TypeError,
    KeyError,
    RuntimeError,
)


class OPABatchClient:
    """
    High-performance OPA client optimized for batch policy evaluation.

    Features:
    - Parallel policy evaluation using asyncio semaphore
    - Deduplication of identical requests within batch
    - Connection pooling via httpx limits
    - In-batch caching for repeated inputs
    - Metrics collection for observability
    - Fail-closed error handling for security

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        opa_url: str = "http://localhost:8181",
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
        max_keepalive: int = DEFAULT_MAX_KEEPALIVE,
        timeout: float = DEFAULT_TIMEOUT,
        enable_cache: bool = True,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        cache_hash_mode: Literal["sha256", "fast"] = DEFAULT_CACHE_HASH_MODE,
    ):
        """
        Initialize OPA batch client.

        Args:
            opa_url: OPA server URL
            max_concurrent: Maximum concurrent OPA requests
            batch_size: Maximum batch size before splitting
            max_connections: Maximum HTTP connections in pool
            max_keepalive: Maximum keepalive connections
            timeout: Request timeout in seconds
            enable_cache: Enable in-batch deduplication caching
            cache_ttl: Cache TTL in seconds
            cache_hash_mode: Cache key hash mode ("sha256" for collision-resistant,
                "fast" for high-throughput non-cryptographic hashing)
        """
        self.opa_url = opa_url.rstrip("/")
        self.max_concurrent = max_concurrent
        self.batch_size = batch_size
        self.max_connections = max_connections
        self.max_keepalive = max_keepalive
        self.timeout = timeout
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl
        if cache_hash_mode not in _CACHE_HASH_MODES:
            raise ValueError(f"Invalid cache_hash_mode: {cache_hash_mode}")
        self.cache_hash_mode = cache_hash_mode
        self.constitutional_hash = CONSTITUTIONAL_HASH

        if self.cache_hash_mode == "fast" and not FAST_HASH_AVAILABLE:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] cache_hash_mode=fast requested but acgs2_perf.fast_hash "
                "is unavailable; falling back to sha256"
            )

        # HTTP client with connection pooling
        self._http_client: httpx.AsyncClient | None = None
        self._semaphore: asyncio.Semaphore | None = None

        # In-batch cache for deduplication
        self._batch_cache: dict[str, JSONDict] = {}

        # Metrics
        self._metrics: _OPABatchMetrics = {
            "total_evaluations": 0,
            "batch_evaluations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "total_latency_ms": 0.0,
            "created_at": datetime.now(UTC).isoformat(),
        }

    async def __aenter__(self) -> "OPABatchClient":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def initialize(self) -> None:
        """Initialize HTTP client with connection pooling."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(
                    max_connections=self.max_connections,
                    max_keepalive_connections=self.max_keepalive,
                ),
            )
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
            logger.info(
                f"[{CONSTITUTIONAL_HASH}] OPA batch client initialized: "
                f"max_concurrent={self.max_concurrent}, "
                f"max_connections={self.max_connections}"
            )

    async def close(self) -> None:
        """Close HTTP client and release resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
            self._semaphore = None
            self._batch_cache.clear()
            logger.info(f"[{CONSTITUTIONAL_HASH}] OPA batch client closed")

    def _generate_cache_key(self, input_data: JSONDict, policy_path: str) -> str:
        """Generate cache key for deduplication."""
        input_str = json.dumps(input_data, sort_keys=True)
        combined = f"{policy_path}:{input_str}"
        if self.cache_hash_mode == "fast" and FAST_HASH_AVAILABLE:
            # Non-cryptographic hash for high-throughput deduplication only.
            return f"fast:{fast_hash(combined):016x}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def _validate_policy_path(self, policy_path: str) -> None:
        """Validate OPA policy path to prevent injection."""
        if not re.match(r"^[a-zA-Z0-9_.]+$", policy_path):
            raise ValueError(f"Invalid policy path characters: {policy_path}")
        if ".." in policy_path:
            raise ValueError(f"Path traversal detected: {policy_path}")

    def _sanitize_error(self, error: Exception) -> str:
        """Sanitize error message for logging."""
        error_msg = str(error)
        error_msg = re.sub(r"key=[^&\s]+", "key=REDACTED", error_msg)
        error_msg = re.sub(r"token=[^&\s]+", "token=REDACTED", error_msg)
        return error_msg

    def _create_error_result(self, error: Exception, policy_path: str) -> JSONDict:
        """Create fail-closed error result."""
        sanitized_error = self._sanitize_error(error)
        return {
            "result": False,
            "allowed": False,
            "reason": f"Policy evaluation failed: {sanitized_error}",
            "metadata": {
                "error": sanitized_error,
                "mode": "batch",
                "policy_path": policy_path,
                "security": "fail-closed",
                "constitutional_hash": self.constitutional_hash,
            },
        }

    def _parse_opa_response(self, response_data: JSONDict, policy_path: str) -> JSONDict:
        """Parse OPA response into standardized format."""
        opa_result = response_data.get("result", False)

        if isinstance(opa_result, bool):
            return {
                "result": opa_result,
                "allowed": opa_result,
                "reason": "Policy evaluated successfully",
                "metadata": {
                    "mode": "batch",
                    "policy_path": policy_path,
                    "constitutional_hash": self.constitutional_hash,
                },
            }
        elif isinstance(opa_result, dict):
            # Extract resource info for order verification
            metadata = {
                "mode": "batch",
                "policy_path": policy_path,
                "constitutional_hash": self.constitutional_hash,
            }
            # Preserve resource info if present
            if "resource" in opa_result:
                metadata["resource"] = opa_result["resource"]
            if "action" in opa_result:
                metadata["action"] = opa_result["action"]
            # Add any additional metadata from OPA
            if "metadata" in opa_result:
                metadata.update(opa_result["metadata"])

            return {
                "result": opa_result,
                "allowed": opa_result.get("allow", False),
                "reason": opa_result.get("reason", "Policy evaluated successfully"),
                "metadata": metadata,
            }
        else:
            return {
                "result": False,
                "allowed": False,
                "reason": f"Unexpected result type: {type(opa_result)}",
                "metadata": {
                    "mode": "batch",
                    "policy_path": policy_path,
                    "constitutional_hash": self.constitutional_hash,
                },
            }

    async def _evaluate_single(
        self,
        input_data: JSONDict,
        policy_path: str,
    ) -> JSONDict:
        """Evaluate single policy with semaphore for concurrency control."""
        if not self._http_client or not self._semaphore:
            raise RuntimeError("OPA batch client not initialized")

        start_time = time.perf_counter()

        async with self._semaphore:
            try:
                # Build OPA URL
                path_parts = policy_path.replace("data.", "").replace(".", "/")
                url = f"{self.opa_url}/v1/data/{path_parts}"

                response = await self._http_client.post(url, json={"input": input_data})
                response.raise_for_status()

                result = self._parse_opa_response(response.json(), policy_path)

                elapsed_ms = (time.perf_counter() - start_time) * 1000
                self._metrics["total_latency_ms"] += elapsed_ms

                return result

            except OPA_EVALUATION_ERRORS as e:
                self._metrics["errors"] += 1
                logger.error(
                    f"[{CONSTITUTIONAL_HASH}] OPA evaluation error: {self._sanitize_error(e)}"
                )
                return self._create_error_result(e, policy_path)

    async def batch_evaluate(
        self,
        inputs: list[JSONDict],
        policy_path: str = "data.acgs.allow",
    ) -> list[JSONDict]:
        """
        Evaluate multiple policy inputs in parallel.

        Args:
            inputs: List of input dictionaries for policy evaluation
            policy_path: OPA policy path to evaluate

        Returns:
            List of evaluation results in same order as inputs
        """
        if not inputs:
            return []

        # Validate policy path
        self._validate_policy_path(policy_path)

        # Initialize if needed
        if not self._http_client:
            await self.initialize()

        # Update metrics
        self._metrics["batch_evaluations"] += 1
        self._metrics["total_evaluations"] += len(inputs)

        # Deduplicate inputs while preserving order
        unique_inputs: dict[str, tuple[int, JSONDict]] = {}
        input_to_key: list[str] = []
        cache_used: list[bool] = []

        for idx, input_data in enumerate(inputs):
            cache_key = self._generate_cache_key(input_data, policy_path)
            input_to_key.append(cache_key)

            if self.enable_cache and cache_key in unique_inputs:
                # Duplicate - will use cached result
                cache_used.append(True)
                self._metrics["cache_hits"] += 1
            else:
                unique_inputs[cache_key] = (idx, input_data)
                cache_used.append(False)
                self._metrics["cache_misses"] += 1

        # Evaluate unique inputs in parallel
        tasks = []
        for cache_key, (_idx, input_data) in unique_inputs.items():
            task = self._evaluate_single(input_data, policy_path)
            tasks.append((cache_key, task))

        # Gather results maintaining association with cache keys
        cache_key_to_result: dict[str, JSONDict] = {}

        if tasks:
            results = await asyncio.gather(
                *[task for _, task in tasks],
                return_exceptions=True,
            )

            for (cache_key, _), result in zip(tasks, results, strict=False):
                if isinstance(result, Exception):
                    cache_key_to_result[cache_key] = self._create_error_result(result, policy_path)
                else:
                    cache_key_to_result[cache_key] = result  # type: ignore[assignment]

        # Build final results in original order
        final_results: list[JSONDict] = []
        for _idx, cache_key in enumerate(input_to_key):
            final_results.append(cache_key_to_result[cache_key])

        return final_results

    async def batch_evaluate_multi_policy(
        self,
        inputs: list[tuple[JSONDict, str]],
    ) -> list[JSONDict]:
        """
        Evaluate inputs against different policies in parallel.

        Args:
            inputs: List of (input_data, policy_path) tuples

        Returns:
            List of evaluation results in same order as inputs
        """
        if not inputs:
            return []

        # Initialize if needed
        if not self._http_client:
            await self.initialize()

        # Update metrics
        self._metrics["batch_evaluations"] += 1
        self._metrics["total_evaluations"] += len(inputs)

        # Evaluate all in parallel
        tasks = []
        for input_data, policy_path in inputs:
            self._validate_policy_path(policy_path)
            task = self._evaluate_single(input_data, policy_path)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error results
        final_results = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                _, policy_path = inputs[idx]
                final_results.append(self._create_error_result(result, policy_path))
            else:
                final_results.append(cast(JSONDict, result))

        return final_results

    def get_stats(self) -> JSONDict:
        """
        Get batch client statistics.

        Returns:
            Dictionary with client metrics
        """
        total_ops = self._metrics["cache_hits"] + self._metrics["cache_misses"]
        cache_hit_rate = (self._metrics["cache_hits"] / total_ops * 100) if total_ops > 0 else 0.0

        actual_evaluations = self._metrics["cache_misses"]  # Only non-cached calls
        avg_latency = (
            (self._metrics["total_latency_ms"] / actual_evaluations)
            if actual_evaluations > 0
            else 0.0
        )

        return {
            "constitutional_hash": self.constitutional_hash,
            "total_evaluations": self._metrics["total_evaluations"],
            "batch_evaluations": self._metrics["batch_evaluations"],
            "cache_hits": self._metrics["cache_hits"],
            "cache_misses": self._metrics["cache_misses"],
            "cache_hit_rate": cache_hit_rate,
            "errors": self._metrics["errors"],
            "avg_latency_ms": avg_latency,
            "max_concurrent": self.max_concurrent,
            "max_connections": self.max_connections,
            "created_at": self._metrics["created_at"],
        }


# Singleton instance for shared batch client
_batch_client: OPABatchClient | None = None
_batch_client_lock = asyncio.Lock()


async def get_batch_client(
    opa_url: str = "http://localhost:8181",
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
) -> OPABatchClient:
    """
    Get or create shared OPA batch client singleton.

    Args:
        opa_url: OPA server URL (only used on first call)
        max_concurrent: Max concurrent requests (only used on first call)

    Returns:
        Shared OPABatchClient instance
    """
    global _batch_client

    if _batch_client is not None:
        return _batch_client

    async with _batch_client_lock:
        if _batch_client is None:
            _batch_client = OPABatchClient(
                opa_url=opa_url,
                max_concurrent=max_concurrent,
            )
            await _batch_client.initialize()

        return _batch_client


async def reset_batch_client() -> None:
    """Reset the shared batch client singleton (for testing)."""
    global _batch_client

    async with _batch_client_lock:
        if _batch_client is not None:
            try:
                await _batch_client.close()
            except (RuntimeError, ConnectionError, OSError):
                pass  # Ignore close errors during cleanup
            _batch_client = None


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_CACHE_HASH_MODE",
    "DEFAULT_MAX_CONCURRENT",
    "OPABatchClient",
    "get_batch_client",
    "reset_batch_client",
]
