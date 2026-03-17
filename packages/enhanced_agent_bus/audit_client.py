"""
Audit Client - Communicates with the decentralized Audit Service
Constitutional Hash: cdd01ef066bc6cf2

Enhanced with:
- Circuit breaker integration for fault tolerance
- Batched submission for efficiency
- Fire-and-forget async pattern
- Health monitoring
"""

import asyncio
import json
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC

import httpx
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import pybreaker
    from src.core.shared.circuit_breaker import CircuitBreakerConfig, get_circuit_breaker

    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False
    pybreaker = None

logger = get_logger(__name__)
CIRCUIT_BREAKER_CHECK_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
)


@dataclass
class AuditClientConfig:
    """Configuration for AuditClient."""

    service_url: str = "http://localhost:8001"
    timeout: float = 5.0

    # Batching settings
    enable_batching: bool = True
    batch_size: int = 50
    batch_flush_interval_s: float = 5.0

    # Circuit breaker settings
    enable_circuit_breaker: bool = True
    circuit_fail_max: int = 5
    circuit_reset_timeout: int = 30

    # Retry settings
    max_retries: int = 3
    retry_delay_s: float = 0.5

    # Queue settings
    queue_size: int = 1000


@dataclass
class AuditBatchResult:
    """Result of batch audit submission."""

    batch_id: str
    entry_count: int
    successful: int
    failed: int
    entry_hashes: list[str]
    timestamp: float = field(default_factory=time.time)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        return {
            "batch_id": self.batch_id,
            "entry_count": self.entry_count,
            "successful": self.successful,
            "failed": self.failed,
            "entry_hashes": self.entry_hashes,
            "timestamp": self.timestamp,
            "constitutional_hash": self.constitutional_hash,
        }


class AuditClient:
    """
    Asynchronous client for reporting validation results to the Audit Service.
    Designed to be used within the EnhancedAgentBus.

    Enhanced features:
    - Circuit breaker for fault tolerance
    - Batch submission for efficiency
    - Fire-and-forget pattern for minimal latency
    - Health monitoring and statistics
    """

    def __init__(
        self,
        service_url: str = "http://localhost:8001",
        config: AuditClientConfig | None = None,
    ):
        # Support both old API (service_url only) and new config-based API
        if config:
            self.config = config
        else:
            self.config = AuditClientConfig(service_url=service_url)

        self.service_url = self.config.service_url
        self.client = httpx.AsyncClient(
            timeout=self.config.timeout,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )

        # Circuit breaker
        self._circuit_breaker = None
        if CIRCUIT_BREAKER_AVAILABLE and self.config.enable_circuit_breaker:
            cb_config = CircuitBreakerConfig(
                fail_max=self.config.circuit_fail_max,
                reset_timeout=self.config.circuit_reset_timeout,
            )
            self._circuit_breaker = get_circuit_breaker("audit_service", cb_config)

        # Batching
        self._batch: list[object] = []
        self._batch_lock = asyncio.Lock()
        self._batch_worker: asyncio.Task | None = None
        self._running = False

        # Statistics
        self._stats = {
            "total_submitted": 0,
            "successful": 0,
            "failed": 0,
            "batches_sent": 0,
            "circuit_rejections": 0,
        }

        # Recent results for monitoring
        self._recent_results: deque = deque(maxlen=100)

    async def start(self) -> None:
        """Start the background batch worker."""
        if self._running:
            return

        self._running = True
        if self.config.enable_batching:
            self._batch_worker = asyncio.create_task(self._batch_flush_worker())
            logger.info(f"[{CONSTITUTIONAL_HASH}] AuditClient batch worker started")

    async def stop(self) -> None:
        """Stop the client and flush pending batches."""
        self._running = False

        # Flush any remaining batch
        if self._batch:
            await self._flush_batch()

        if self._batch_worker:
            self._batch_worker.cancel()
            try:  # noqa: SIM105
                await self._batch_worker
            except asyncio.CancelledError:
                pass

        logger.info(f"[{CONSTITUTIONAL_HASH}] AuditClient stopped")

    async def report_validation(self, validation_result: object) -> str | None:
        """
        Reports a single validation result to the audit ledger.
        Returns the entry hash if successful.

        If batching is enabled, the result is queued for batch submission.
        If batching is disabled, submits immediately.

        Note: This is designed to be fire-and-forget or async monitored.
        """
        self._stats["total_submitted"] += 1

        if self.config.enable_batching and self._running:
            return await self._queue_for_batch(validation_result)
        else:
            return await self._submit_single(validation_result)

    async def record(self, message_id: str, workflow_result: object) -> str:
        """
        Record a workflow result to the audit trail.

        This is a convenience method for recording deliberation workflow results.
        It wraps report_validation with the expected interface.

        Args:
            message_id: ID of the message being audited
            workflow_result: Workflow result data to record

        Returns:
            Audit hash/ID for the recorded entry
        """
        import hashlib
        import json
        from datetime import datetime

        # Build audit record
        audit_record = {
            "message_id": message_id,
            "workflow_result": workflow_result,
            "timestamp": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        # Generate audit hash
        audit_hash = hashlib.sha256(
            json.dumps(audit_record, default=str, sort_keys=True).encode()
        ).hexdigest()[:16]

        # Submit to audit ledger
        await self.report_validation(audit_record)

        return audit_hash

    async def _queue_for_batch(self, validation_result: object) -> str | None:
        """Queue a validation result for batch submission."""
        batch_to_send = None

        async with self._batch_lock:
            self._batch.append(validation_result)

            # If batch is full, prepare to flush (outside lock to avoid deadlock)
            if len(self._batch) >= self.config.batch_size:
                batch_to_send = self._batch.copy()
                self._batch.clear()

        # Submit outside lock to avoid deadlock with _flush_batch
        if batch_to_send:
            await self._submit_batch(batch_to_send)

        return "queued"

    async def _flush_batch(self) -> AuditBatchResult | None:
        """Flush the current batch to the audit service."""
        async with self._batch_lock:
            if not self._batch:
                return None

            batch_to_send = self._batch.copy()
            self._batch.clear()

        return await self._submit_batch(batch_to_send)

    async def _batch_flush_worker(self) -> None:
        """Background worker that periodically flushes batches."""
        while self._running:
            try:
                await asyncio.sleep(self.config.batch_flush_interval_s)
                if self._batch:
                    await self._flush_batch()
            except asyncio.CancelledError:
                break
            except (httpx.RequestError, RuntimeError, ValueError, TypeError, OSError) as e:
                logger.error(f"[{CONSTITUTIONAL_HASH}] Batch flush worker error: {e}")

    async def _submit_single(self, validation_result: object) -> str | None:
        """Submit a single validation result immediately."""
        # Check circuit breaker
        if self._circuit_breaker and CIRCUIT_BREAKER_AVAILABLE:
            try:
                current_state = getattr(self._circuit_breaker, "current_state", None)
                if current_state == "open":
                    self._stats["circuit_rejections"] += 1
                    logger.debug(f"[{CONSTITUTIONAL_HASH}] Circuit breaker open, rejecting audit")
                    return None
            except CIRCUIT_BREAKER_CHECK_ERRORS as e:
                logger.debug(f"[{CONSTITUTIONAL_HASH}] Circuit breaker state check failed: {e}")

        try:
            data = self._serialize_validation_result(validation_result)

            for attempt in range(self.config.max_retries):
                try:
                    response = await self.client.post(f"{self.service_url}/record", json=data)
                    if response.status_code == 200:
                        audit_hash = response.json().get("entry_hash")
                        self._stats["successful"] += 1
                        logger.info(f"Audit record successful: {audit_hash}")
                        return audit_hash  # type: ignore[no-any-return]
                    else:
                        logger.error(
                            f"Audit Service returned error {response.status_code}: {response.text}"
                        )
                except httpx.RequestError as e:
                    logger.warning(
                        f"[{CONSTITUTIONAL_HASH}] Audit request failed (attempt {attempt + 1}): {e}"
                    )
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay_s * (attempt + 1))

            self._stats["failed"] += 1
            return None

        except (httpx.RequestError, RuntimeError, ValueError, TypeError, OSError) as e:
            logger.error(f"Failed to report validation to audit service: {e}")
            self._stats["failed"] += 1
            return None

    async def _submit_batch(self, batch: list[object]) -> AuditBatchResult | None:
        """Submit a batch of validation results."""
        if not batch:
            return None

        # Check circuit breaker
        if self._circuit_breaker and CIRCUIT_BREAKER_AVAILABLE:
            try:
                if hasattr(self._circuit_breaker, "current_state"):  # noqa: SIM102
                    if self._circuit_breaker.current_state == "open":
                        self._stats["circuit_rejections"] += len(batch)
                        logger.warning(
                            f"[{CONSTITUTIONAL_HASH}] Circuit open, rejecting batch of {len(batch)}"
                        )
                        return None
            except AttributeError as e:
                logger.debug(f"[{CONSTITUTIONAL_HASH}] Circuit breaker state check failed: {e}")

        batch_data = [self._serialize_validation_result(vr) for vr in batch]
        batch_id = f"batch_{int(time.time() * 1000)}"

        for attempt in range(self.config.max_retries):
            try:
                response = await self.client.post(
                    f"{self.service_url}/record/batch",
                    json={
                        "batch_id": batch_id,
                        "entries": batch_data,
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                )

                if response.status_code == 200:
                    result_data = response.json()
                    entry_hashes = result_data.get("entry_hashes", [])

                    result = AuditBatchResult(
                        batch_id=batch_id,
                        entry_count=len(batch),
                        successful=len(entry_hashes),
                        failed=len(batch) - len(entry_hashes),
                        entry_hashes=entry_hashes,
                    )

                    self._stats["batches_sent"] += 1
                    self._stats["successful"] += result.successful
                    self._stats["failed"] += result.failed
                    self._recent_results.append(result)

                    logger.info(
                        f"[{CONSTITUTIONAL_HASH}] Batch {batch_id} submitted: "
                        f"{result.successful}/{result.entry_count} successful"
                    )
                    return result

                else:
                    logger.error(
                        f"Batch submission failed: {response.status_code} - {response.text}"
                    )

            except httpx.RequestError as e:
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] Batch request failed (attempt {attempt + 1}): {e}"
                )
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay_s * (attempt + 1))

        # All retries failed
        self._stats["failed"] += len(batch)
        return None

    def _serialize_validation_result(self, validation_result: object) -> JSONDict:
        """Serialize a validation result to a dictionary."""
        if hasattr(validation_result, "to_dict"):
            return validation_result.to_dict()

        from dataclasses import is_dataclass

        if is_dataclass(validation_result) and not isinstance(validation_result, type):
            return asdict(validation_result)  # type: ignore[arg-type]

        return validation_result

    async def get_stats(self) -> JSONDict:
        """Fetch statistics from the Audit Service."""
        try:
            response = await self.client.get(f"{self.service_url}/stats")
            remote_stats = response.json()
        except (
            httpx.RequestError,
            RuntimeError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ) as e:
            logger.error(f"Failed to fetch audit stats: {e}")
            remote_stats = {}

        return {
            "client_stats": self._stats,
            "remote_stats": remote_stats,
            "queue_size": len(self._batch),
            "running": self._running,
            "circuit_breaker_available": CIRCUIT_BREAKER_AVAILABLE,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    async def health_check(self) -> JSONDict:
        """Check health of the audit service."""
        health: JSONDict = {
            "status": "unknown",
            "latency_ms": None,
            "circuit_state": None,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        # Check circuit breaker state
        if self._circuit_breaker and CIRCUIT_BREAKER_AVAILABLE:
            try:
                if hasattr(self._circuit_breaker, "current_state"):
                    health["circuit_state"] = self._circuit_breaker.current_state
            except AttributeError as e:
                logger.debug(f"[{CONSTITUTIONAL_HASH}] Circuit state check failed: {e}")

        # Ping the service
        start = time.perf_counter()
        try:
            response = await self.client.get(f"{self.service_url}/health")
            health["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)

            if response.status_code == 200:
                health["status"] = "healthy"
            else:
                health["status"] = "degraded"

        except httpx.RequestError as e:
            health["status"] = "unhealthy"
            health["error"] = str(e)

        return health

    def get_recent_results(self, n: int = 10) -> list[JSONDict]:
        """Get recent batch results for monitoring."""
        results = list(self._recent_results)[-n:]
        return [r.to_dict() for r in results]

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.stop()
        await self.client.aclose()


# Convenience function for fire-and-forget auditing
_global_client: AuditClient | None = None


def get_audit_client(config: AuditClientConfig | None = None) -> AuditClient:
    """Get or create the global audit client."""
    global _global_client
    if _global_client is None:
        _global_client = AuditClient(config=config)
    return _global_client


async def initialize_audit_client(
    config: AuditClientConfig | None = None,
) -> AuditClient:
    """Initialize and start the global audit client."""
    client = get_audit_client(config)
    await client.start()
    return client


async def close_audit_client() -> None:
    """Close the global audit client."""
    global _global_client
    if _global_client:
        await _global_client.close()
        _global_client = None
