# pyright: reportAttributeAccessIssue=false
"""
ACGS-2 Batch Processing Metrics

Constitutional Hash: 608508a9bd224290

Prometheus/OpenTelemetry metrics for batch processing operations.
Tracks throughput, latency, success/failure rates, and resource usage.
"""

import time
from dataclasses import dataclass, field
from importlib import import_module

from .structured_logging import get_logger
from .telemetry import NoOpCounter, NoOpHistogram, NoOpMeter, get_meter

logger = get_logger(__name__)
BATCH_METRICS_INIT_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"


@dataclass
class BatchMetrics:
    """
    Metrics collector for batch processing operations.

    Provides counters, histograms, and gauges for monitoring batch
    validation performance and constitutional compliance.
    """

    service_name: str = "acgs2-batch-processor"
    _meter: object = field(default=None, repr=False)
    _initialized: bool = field(default=False, repr=False)

    # Counters
    _batch_requests_total: object = field(default=None, repr=False)
    _batch_items_total: object = field(default=None, repr=False)
    _batch_items_success: object = field(default=None, repr=False)
    _batch_items_failed: object = field(default=None, repr=False)
    _batch_cache_hits: object = field(default=None, repr=False)
    _batch_cache_misses: object = field(default=None, repr=False)
    _batch_errors_total: object = field(default=None, repr=False)
    _batch_retries_total: object = field(default=None, repr=False)
    _constitutional_validations: object = field(default=None, repr=False)
    _constitutional_violations: object = field(default=None, repr=False)

    # Histograms
    _batch_request_duration: object = field(default=None, repr=False)
    _batch_item_duration: object = field(default=None, repr=False)
    _batch_size_distribution: object = field(default=None, repr=False)

    def __post_init__(self):
        """Initialize metrics after dataclass creation."""
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize all metric instruments."""
        if self._initialized:
            return

        try:
            self._meter = get_meter(self.service_name)

            # Initialize counters
            self._batch_requests_total = self._meter.create_counter(
                name="batch_requests_total",
                description="Total number of batch validation requests",
                unit="1",
            )

            self._batch_items_total = self._meter.create_counter(
                name="batch_items_total",
                description="Total number of items processed in batches",
                unit="1",
            )

            self._batch_items_success = self._meter.create_counter(
                name="batch_items_success_total",
                description="Total number of successfully validated items",
                unit="1",
            )

            self._batch_items_failed = self._meter.create_counter(
                name="batch_items_failed_total",
                description="Total number of failed item validations",
                unit="1",
            )

            self._batch_cache_hits = self._meter.create_counter(
                name="batch_cache_hits_total",
                description="Total number of cache hits during batch processing",
                unit="1",
            )

            self._batch_cache_misses = self._meter.create_counter(
                name="batch_cache_misses_total",
                description="Total number of cache misses during batch processing",
                unit="1",
            )

            self._batch_errors_total = self._meter.create_counter(
                name="batch_errors_total",
                description="Total number of batch processing errors by type",
                unit="1",
            )

            self._batch_retries_total = self._meter.create_counter(
                name="batch_retries_total",
                description="Total number of retry attempts during batch processing",
                unit="1",
            )

            self._constitutional_validations = self._meter.create_counter(
                name="constitutional_validations_total",
                description="Total number of constitutional hash validations",
                unit="1",
            )

            self._constitutional_violations = self._meter.create_counter(
                name="constitutional_violations_total",
                description="Total number of constitutional hash violations detected",
                unit="1",
            )

            # Initialize histograms
            self._batch_request_duration = self._meter.create_histogram(
                name="batch_request_duration_seconds",
                description="Duration of batch validation requests",
                unit="s",
            )

            self._batch_item_duration = self._meter.create_histogram(
                name="batch_item_duration_seconds",
                description="Duration of individual item validations",
                unit="s",
            )

            self._batch_size_distribution = self._meter.create_histogram(
                name="batch_size_distribution",
                description="Distribution of batch sizes",
                unit="1",
            )

            self._initialized = True
            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Batch metrics initialized for {self.service_name}"
            )

        except BATCH_METRICS_INIT_ERRORS as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Failed to initialize batch metrics: {e}")
            self._use_noop_metrics()

    def _use_noop_metrics(self) -> None:
        """Fall back to no-op metrics if initialization fails."""
        try:
            telemetry_module = import_module("packages.enhanced_agent_bus.observability.telemetry")
            noop_meter = telemetry_module.NoOpMeter()
        except ImportError:
            noop_meter = NoOpMeter()
        self._batch_requests_total = noop_meter.create_counter("batch_requests_total")
        self._batch_items_total = noop_meter.create_counter("batch_items_total")
        self._batch_items_success = noop_meter.create_counter("batch_items_success_total")
        self._batch_items_failed = noop_meter.create_counter("batch_items_failed_total")
        self._batch_cache_hits = noop_meter.create_counter("batch_cache_hits_total")
        self._batch_cache_misses = noop_meter.create_counter("batch_cache_misses_total")
        self._batch_errors_total = noop_meter.create_counter("batch_errors_total")
        self._batch_retries_total = noop_meter.create_counter("batch_retries_total")
        self._constitutional_validations = noop_meter.create_counter(
            "constitutional_validations_total"
        )
        self._constitutional_violations = noop_meter.create_counter(
            "constitutional_violations_total"
        )
        self._batch_request_duration = noop_meter.create_histogram("batch_request_duration_seconds")
        self._batch_item_duration = noop_meter.create_histogram("batch_item_duration_seconds")
        self._batch_size_distribution = noop_meter.create_histogram("batch_size_distribution")
        self._initialized = True

    # ==========================================================================
    # Counter Methods
    # ==========================================================================

    def record_batch_request(
        self,
        tenant_id: str,
        batch_size: int,
        success: bool,
        duration_seconds: float,
        cache_hits: int = 0,
        cache_misses: int = 0,
    ) -> None:
        """
        Record a complete batch request with all metrics.

        Args:
            tenant_id: Tenant identifier
            batch_size: Number of items in the batch
            success: Whether the batch completed successfully
            duration_seconds: Total processing time
            cache_hits: Number of cache hits
            cache_misses: Number of cache misses
        """
        attributes = {
            "tenant_id": tenant_id,
            "success": str(success).lower(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        self._batch_requests_total.add(1, attributes)
        self._batch_size_distribution.record(batch_size, attributes)
        self._batch_request_duration.record(duration_seconds, attributes)

        if cache_hits > 0:
            self._batch_cache_hits.add(cache_hits, {"tenant_id": tenant_id})
        if cache_misses > 0:
            self._batch_cache_misses.add(cache_misses, {"tenant_id": tenant_id})

    def record_items_processed(
        self,
        tenant_id: str,
        total: int,
        successful: int,
        failed: int,
    ) -> None:
        """
        Record item-level processing statistics.

        Args:
            tenant_id: Tenant identifier
            total: Total items processed
            successful: Successfully validated items
            failed: Failed validations
        """
        base_attrs = {"tenant_id": tenant_id}

        self._batch_items_total.add(total, base_attrs)
        self._batch_items_success.add(successful, base_attrs)
        self._batch_items_failed.add(failed, base_attrs)

    def record_item_duration(
        self,
        tenant_id: str,
        duration_seconds: float,
        success: bool,
    ) -> None:
        """
        Record duration of a single item validation.

        Args:
            tenant_id: Tenant identifier
            duration_seconds: Processing time
            success: Whether validation succeeded
        """
        attributes = {
            "tenant_id": tenant_id,
            "success": str(success).lower(),
        }
        self._batch_item_duration.record(duration_seconds, attributes)

    def record_error(
        self,
        tenant_id: str,
        error_type: str,
        error_code: str | None = None,
    ) -> None:
        """
        Record a batch processing error.

        Args:
            tenant_id: Tenant identifier
            error_type: Type of error (e.g., "timeout", "validation", "processing")
            error_code: Specific error code if available
        """
        attributes = {
            "tenant_id": tenant_id,
            "error_type": error_type,
            "error_code": error_code or "unknown",
        }
        self._batch_errors_total.add(1, attributes)

    def record_retry(
        self,
        tenant_id: str,
        attempt: int,
        reason: str,
    ) -> None:
        """
        Record a retry attempt.

        Args:
            tenant_id: Tenant identifier
            attempt: Retry attempt number
            reason: Reason for retry
        """
        attributes = {
            "tenant_id": tenant_id,
            "attempt": str(attempt),
            "reason": reason,
        }
        self._batch_retries_total.add(1, attributes)

    def record_constitutional_validation(
        self,
        tenant_id: str,
        valid: bool,
        hash_used: str,
    ) -> None:
        """
        Record a constitutional hash validation.

        Args:
            tenant_id: Tenant identifier
            valid: Whether validation passed
            hash_used: Constitutional hash that was validated
        """
        attributes = {
            "tenant_id": tenant_id,
            "expected_hash": CONSTITUTIONAL_HASH,
        }
        self._constitutional_validations.add(1, attributes)

        if not valid:
            violation_attrs = {
                **attributes,
                "actual_hash": hash_used or "missing",
            }
            self._constitutional_violations.add(1, violation_attrs)

    def record_cache_stats(
        self,
        tenant_id: str,
        hits: int,
        misses: int,
    ) -> None:
        """
        Record cache statistics.

        Args:
            tenant_id: Tenant identifier
            hits: Number of cache hits
            misses: Number of cache misses
        """
        attrs = {"tenant_id": tenant_id}
        if hits > 0:
            self._batch_cache_hits.add(hits, attrs)
        if misses > 0:
            self._batch_cache_misses.add(misses, attrs)


# ==========================================================================
# Singleton Instance
# ==========================================================================

_batch_metrics: BatchMetrics | None = None


def get_batch_metrics() -> BatchMetrics:
    """
    Get the singleton BatchMetrics instance.

    Returns:
        BatchMetrics instance
    """
    global _batch_metrics
    if _batch_metrics is None:
        _batch_metrics = BatchMetrics()
    return _batch_metrics


def reset_batch_metrics() -> None:
    """Reset the batch metrics singleton (for testing)."""
    global _batch_metrics
    _batch_metrics = None


# ==========================================================================
# Context Manager for Timing
# ==========================================================================


class BatchRequestTimer:
    """
    Context manager for timing batch requests.

    Usage:
        with BatchRequestTimer(tenant_id="acme-corp", batch_size=100) as timer:
            # Process batch
            timer.record_items(successful=95, failed=5)
    """

    def __init__(
        self,
        tenant_id: str,
        batch_size: int,
        cache_enabled: bool = False,
    ):
        self.tenant_id = tenant_id
        self.batch_size = batch_size
        self.cache_enabled = cache_enabled
        self.start_time: float = 0
        self.successful: int = 0
        self.failed: int = 0
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.metrics = get_batch_metrics()

    def __enter__(self) -> "BatchRequestTimer":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration = time.perf_counter() - self.start_time
        success = exc_type is None

        self.metrics.record_batch_request(
            tenant_id=self.tenant_id,
            batch_size=self.batch_size,
            success=success,
            duration_seconds=duration,
            cache_hits=self.cache_hits,
            cache_misses=self.cache_misses,
        )

        self.metrics.record_items_processed(
            tenant_id=self.tenant_id,
            total=self.batch_size,
            successful=self.successful,
            failed=self.failed,
        )

        # Don't suppress exceptions (return None is equivalent to return False)

    def record_items(self, successful: int, failed: int) -> None:
        """Record item counts before context exits."""
        self.successful = successful
        self.failed = failed

    def record_cache(self, hits: int, misses: int) -> None:
        """Record cache statistics."""
        self.cache_hits = hits
        self.cache_misses = misses


class ItemTimer:
    """
    Context manager for timing individual item validations.

    Usage:
        with ItemTimer(tenant_id="acme-corp") as timer:
            # Validate item
            pass
        # Duration automatically recorded
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.start_time: float = 0
        self.success: bool = True
        self.metrics = get_batch_metrics()

    def __enter__(self) -> "ItemTimer":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration = time.perf_counter() - self.start_time
        self.success = exc_type is None

        self.metrics.record_item_duration(
            tenant_id=self.tenant_id,
            duration_seconds=duration,
            success=self.success,
        )

        # Don't suppress exceptions (return None is equivalent to return False)
