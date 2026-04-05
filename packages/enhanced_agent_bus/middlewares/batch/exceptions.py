"""
Exceptions for Batch Processing Middleware.

Constitutional Hash: 608508a9bd224290
"""

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from ...pipeline.exceptions import PipelineException


class BatchMiddlewareException(PipelineException):
    """Base exception for batch middleware errors."""

    def __init__(
        self,
        message: str,
        middleware: str | None = None,
        retryable: bool = False,
        details: JSONDict | None = None,
    ):
        super().__init__(
            message=message,
            middleware=middleware or "BatchMiddleware",
            retryable=retryable,
            details=details or {},
        )


class BatchValidationException(BatchMiddlewareException):
    """Exception raised when batch validation fails."""

    def __init__(
        self,
        message: str,
        validation_errors: list[str] | None = None,
        details: JSONDict | None = None,
    ):
        super().__init__(
            message=message,
            middleware="BatchValidationMiddleware",
            retryable=False,
            details={
                "validation_errors": validation_errors or [],
                **(details or {}),
            },
        )
        self.validation_errors = validation_errors or []


class BatchTenantIsolationException(BatchMiddlewareException):
    """Exception raised when tenant isolation is violated."""

    def __init__(
        self,
        message: str,
        tenant_id: str | None = None,
        conflicting_tenants: list[str] | None = None,
        details: JSONDict | None = None,
    ):
        super().__init__(
            message=message,
            middleware="BatchTenantIsolationMiddleware",
            retryable=False,
            details={
                "tenant_id": tenant_id,
                "conflicting_tenants": conflicting_tenants or [],
                **(details or {}),
            },
        )
        self.tenant_id = tenant_id
        self.conflicting_tenants = conflicting_tenants or []


class BatchDeduplicationException(BatchMiddlewareException):
    """Exception raised when deduplication processing fails."""

    def __init__(
        self,
        message: str,
        cache_size: int | None = None,
        details: JSONDict | None = None,
    ):
        super().__init__(
            message=message,
            middleware="BatchDeduplicationMiddleware",
            retryable=True,
            details={
                "cache_size": cache_size,
                **(details or {}),
            },
        )
        self.cache_size = cache_size


class BatchGovernanceException(BatchMiddlewareException):
    """Exception raised when batch governance validation fails."""

    def __init__(
        self,
        message: str,
        maci_violation: str | None = None,
        impact_score: float | None = None,
        details: JSONDict | None = None,
    ):
        super().__init__(
            message=message,
            middleware="BatchGovernanceMiddleware",
            retryable=False,
            details={
                "maci_violation": maci_violation,
                "impact_score": impact_score,
                **(details or {}),
            },
        )
        self.maci_violation = maci_violation
        self.impact_score = impact_score


class BatchConcurrencyException(BatchMiddlewareException):
    """Exception raised when concurrency control fails."""

    def __init__(
        self,
        message: str,
        max_concurrency: int | None = None,
        current_count: int | None = None,
        details: JSONDict | None = None,
    ):
        super().__init__(
            message=message,
            middleware="BatchConcurrencyMiddleware",
            retryable=True,
            details={
                "max_concurrency": max_concurrency,
                "current_count": current_count,
                **(details or {}),
            },
        )
        self.max_concurrency = max_concurrency
        self.current_count = current_count


class BatchProcessingException(BatchMiddlewareException):
    """Exception raised when batch item processing fails."""

    def __init__(
        self,
        message: str,
        item_id: str | None = None,
        error_code: str | None = None,
        details: JSONDict | None = None,
    ):
        super().__init__(
            message=message,
            middleware="BatchProcessingMiddleware",
            retryable=True,
            details={
                "item_id": item_id,
                "error_code": error_code,
                **(details or {}),
            },
        )
        self.item_id = item_id
        self.error_code = error_code


class BatchAutoTuneException(BatchMiddlewareException):
    """Exception raised when auto-tuning fails."""

    def __init__(
        self,
        message: str,
        target_p99_ms: float | None = None,
        current_p99_ms: float | None = None,
        details: JSONDict | None = None,
    ):
        super().__init__(
            message=message,
            middleware="BatchAutoTuneMiddleware",
            retryable=False,
            details={
                "target_p99_ms": target_p99_ms,
                "current_p99_ms": current_p99_ms,
                **(details or {}),
            },
        )
        self.target_p99_ms = target_p99_ms
        self.current_p99_ms = current_p99_ms


class BatchMetricsException(BatchMiddlewareException):
    """Exception raised when metrics recording fails."""

    def __init__(
        self,
        message: str,
        metric_name: str | None = None,
        details: JSONDict | None = None,
    ):
        super().__init__(
            message=message,
            middleware="BatchMetricsMiddleware",
            retryable=False,
            details={
                "metric_name": metric_name,
                **(details or {}),
            },
        )
        self.metric_name = metric_name
