"""
ACGS-2 Enhanced Agent Bus - Batch Models
Constitutional Hash: cdd01ef066bc6cf2

Batch processing models for governance validation.
Split from models.py for improved maintainability.
"""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

# Import constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .enums import BatchItemStatus

# Type alias


class BatchRequestItem(BaseModel):
    """Single request item in a batch validation request.

    Represents one governance validation request within a batch.
    Each item has its own request ID for tracking and can be
    independently validated and reported.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this request within the batch",
    )
    content: JSONDict = Field(..., description="Message content to validate (payload)")
    from_agent: str = Field(default="", description="Source agent identifier")
    to_agent: str = Field(default="", description="Target agent identifier (optional)")
    message_type: str = Field(
        default="governance_request", description="Type of message being validated"
    )
    tenant_id: str = Field(default="default", description="Tenant identifier for isolation")
    priority: int = Field(
        default=1, ge=0, le=3, description="Priority level (0=LOW, 1=MEDIUM, 2=HIGH, 3=CRITICAL)"
    )
    metadata: JSONDict = Field(
        default_factory=dict, description="Optional metadata for this request"
    )
    constitutional_hash: str = Field(
        default="", description="Constitutional hash for per-item governance validation"
    )

    model_config = {"from_attributes": True}


class BatchRequest(BaseModel):
    """Batch governance validation request.

    Accepts multiple validation requests to be processed in parallel,
    maintaining constitutional compliance and tenant isolation.

    Maximum batch size: 1000 items
    Constitutional Hash: cdd01ef066bc6cf2
    """

    batch_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this batch",
    )
    items: list[BatchRequestItem] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of validation requests (1-1000 items)",
    )

    @property
    def item_count(self) -> int:
        """Get number of items in batch."""
        return len(self.items)

    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH,
        description="Constitutional hash for compliance verification",
    )
    tenant_id: str = Field(
        default="default", description="Tenant identifier (will be validated against items)"
    )
    options: JSONDict = Field(
        default_factory=dict,
        description="Batch processing options (e.g., fail_fast, max_concurrency)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the batch request was created",
    )

    model_config = {"from_attributes": True, "populate_by_name": True, "extra": "allow"}

    @property
    def timeout_ms(self) -> int:
        """Get batch timeout in milliseconds."""
        return int(self.model_extra.get("timeout_ms") or self.options.get("timeout_ms", 30000))  # type: ignore[arg-type]

    @property
    def fail_fast(self) -> bool:
        """Get fail_fast option."""
        return bool(self.model_extra.get("fail_fast") or self.options.get("fail_fast", False))

    @property
    def deduplicate(self) -> bool:
        """Get deduplicate option."""
        # Check model_extra first, then options, then default True
        val = self.model_extra.get("deduplicate")
        if val is not None:
            return bool(val)
        return bool(self.options.get("deduplicate", True))

    @field_validator("constitutional_hash")
    @classmethod
    def validate_hash(cls, v: str) -> str:
        """Validate constitutional hash.

        Tests expect ValueError for invalid hashes on initialization.
        """
        if v and v != CONSTITUTIONAL_HASH:
            # Check for specific 'invalid-hash' from TestBatchRequest
            # or any mismatch from TestBatchMessageProcessor.
            # We raise ValueError to satisfy TestBatchRequest.
            raise ValueError("Invalid constitutional hash")
        return v

    def validate_constitutional_hash(self) -> bool:
        """Validate that constitutional hash matches expected value."""
        return bool(self.constitutional_hash == CONSTITUTIONAL_HASH)

    def validate_tenant_consistency(self) -> bool:
        """Validate that all items belong to the same tenant (if batch tenant_id is set).

        Items with tenant_id="default" or empty are considered to inherit the batch tenant.
        """
        if not self.tenant_id:
            return True
        return all(
            item.tenant_id == self.tenant_id
            or not item.tenant_id
            or item.tenant_id == "default"  # "default" inherits batch tenant
            for item in self.items
        )


class BatchResponseItem(BaseModel):
    """Response for a single item in a batch validation.

    Contains the validation result and any errors for an individual
    request within a batch.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    request_id: str = Field(..., description="Original request ID from BatchRequestItem")
    status: str = Field(..., description="Processing status (success, failed, skipped)")
    valid: bool = Field(default=False, description="Whether validation passed")
    validation_result: JSONDict | None = Field(
        default=None, description="Detailed validation result if successful"
    )
    error_code: str | None = Field(default=None, description="Error code if validation failed")
    error_message: str | None = Field(
        default=None, description="Human-readable error message if validation failed"
    )
    error_details: JSONDict | None = Field(
        default=None, description="Additional error details for debugging"
    )
    processing_time_ms: float | None = Field(
        default=None, description="Time taken to process this item in milliseconds"
    )
    impact_score: float | None = Field(
        default=None, description="Impact score if computed (0.0-1.0)"
    )
    constitutional_validated: bool = Field(
        default=False, description="Whether constitutional validation passed"
    )

    @property
    def success(self) -> bool:
        """Check if item processing was successful."""
        return bool(self.status == BatchItemStatus.SUCCESS.value)

    @property
    def constitutional_compliant(self) -> bool:
        """Alias for constitutional_validated for test compatibility."""
        return self.constitutional_validated

    @classmethod
    def create_success(
        cls,
        request_id: str,
        valid: bool,
        processing_time_ms: float,
        details: JSONDict | None = None,
    ) -> "BatchResponseItem":
        """Factory method for successful response item."""
        return cls(
            request_id=request_id,
            status=BatchItemStatus.SUCCESS.value,
            valid=valid,
            validation_result=details,
            processing_time_ms=processing_time_ms,
            constitutional_validated=True,
        )

    @classmethod
    def create_error(
        cls,
        request_id: str,
        error_code: str,
        error_message: str,
        processing_time_ms: float = 0.0,
    ) -> "BatchResponseItem":
        """Factory method for error response item."""
        return cls(
            request_id=request_id,
            status=BatchItemStatus.FAILED.value,
            valid=False,
            error_code=error_code,
            error_message=error_message,
            processing_time_ms=processing_time_ms,
            constitutional_validated=False,
        )

    model_config = {"from_attributes": True}


class BatchResponseStats(BaseModel):
    """Statistics for batch processing results.

    Provides summary metrics for the entire batch operation.
    """

    total_items: int = Field(..., description="Total number of items in batch")
    successful_items: int = Field(default=0, description="Number of successful validations")
    failed_items: int = Field(default=0, description="Number of failed validations")
    skipped: int = Field(default=0, description="Number of skipped items")
    valid_items: int = Field(default=0, description="Alias for successful_items")
    invalid_items: int = Field(default=0, description="Alias for failed_items")
    processing_time_ms: float = Field(
        default=0.0, description="Total batch processing time in milliseconds"
    )
    average_item_time_ms: float | None = Field(
        default=None, description="Average processing time per item"
    )
    p50_latency_ms: float | None = Field(
        default=None, description="P50 (median) latency for item processing"
    )
    p95_latency_ms: float | None = Field(
        default=None, description="P95 latency for item processing"
    )
    p99_latency_ms: float | None = Field(
        default=None, description="P99 latency for item processing"
    )
    deduplicated_count: int = Field(default=0, description="Number of items deduplicated")

    @model_validator(mode="before")
    @classmethod
    def sync_stats_fields(cls, data: object) -> object:
        """Synchronize various success/failure count field names."""
        if isinstance(data, dict):
            # Sync success counts
            s = data.get("successful_items")
            if s is None:
                s = data.get("successful")
            if s is None:
                s = data.get("valid_items")
            if s is not None:
                data["successful_items"] = s
                data["valid_items"] = s
                # Also set the internal 'successful' for properties if needed
                data["successful"] = s

            # Sync failure counts
            f = data.get("failed_items")
            if f is None:
                f = data.get("failed")
            if f is None:
                f = data.get("invalid_items")
            if f is not None:
                data["failed_items"] = f
                data["invalid_items"] = f
                data["failed"] = f
        return data

    @property
    def successful(self) -> int:
        """Alias for successful_items for internal logic."""
        return self.successful_items

    @property
    def failed(self) -> int:
        """Alias for failed_items for internal logic."""
        return self.failed_items

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_items == 0:
            return 0.0
        return (self.successful_items / self.total_items) * 100.0

    @property
    def validation_rate(self) -> float:
        """Calculate validation rate as percentage."""
        if self.total_items == 0:
            return 0.0
        return (self.valid_items / self.total_items) * 100.0

    model_config = {"from_attributes": True, "populate_by_name": True}


class BatchResponse(BaseModel):
    """Batch governance validation response.

    Returns validation results for all items in a batch, with detailed
    error reporting and performance metrics. Supports partial failures
    where some items succeed and others fail.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    batch_id: str = Field(..., description="Batch ID from original request")
    success: bool = Field(default=True, description="Overall batch success status")
    error_code: str | None = Field(default=None, description="Batch-level error code")
    items: list[BatchResponseItem] = Field(
        default_factory=list, description="Validation results for each request item"
    )
    stats: BatchResponseStats = Field(
        default_factory=lambda: BatchResponseStats(total_items=0),
        description="Batch processing statistics",
    )
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH,
        description="Constitutional hash for compliance verification",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Batch-level errors (e.g., invalid batch size, tenant mismatch)",
    )
    warnings: list[str] = Field(default_factory=list, description="Batch-level warnings")
    completed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When batch processing completed",
    )

    @property
    def error(self) -> str | None:
        """Backward-compatible single error accessor."""
        return self.errors[0] if self.errors else None

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_counts(cls, data: object) -> object:
        """Handle legacy flat count fields for backward compatibility with tests."""
        if isinstance(data, dict):
            # Map legacy counts to stats if provided flat
            item_count = data.get("item_count")
            success_count = data.get("success_count")
            failure_count = data.get("failure_count")
            skipped_count = data.get("skipped_count")

            if item_count is not None and "stats" not in data:
                data["stats"] = {
                    "total_items": item_count,
                    "successful": success_count or 0,
                    "failed": failure_count or 0,
                    "skipped": skipped_count or 0,
                }
        return data

    model_config = {"from_attributes": True, "extra": "allow", "populate_by_name": True}

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.stats.total_items == 0:
            return 0.0
        return (self.stats.successful / self.stats.total_items) * 100.0

    @property
    def item_count(self) -> int:
        """Get number of items in batch."""
        return self.stats.total_items

    @property
    def has_failures(self) -> bool:
        """Check if batch had any failed items."""
        return self.stats.failed_items > 0

    @property
    def all_valid(self) -> bool:
        """Check if all items were valid."""
        return self.stats.successful_items == self.stats.total_items and self.stats.total_items > 0

    @classmethod
    def create_batch_error(
        cls,
        batch_id: str,
        error_code: str,
        error_message: str,
        item_count: int = 0,
    ) -> "BatchResponse":
        """Factory method for batch-level error response."""
        return cls(
            batch_id=batch_id,
            success=False,
            error_code=error_code,
            items=[],
            stats=BatchResponseStats(
                total_items=item_count,
                failed_items=item_count,
            ),
            errors=[f"{error_code}: {error_message}"],
        )

    @property
    def is_partial_success(self) -> bool:
        """Check if batch had partial success (some items succeeded, some failed)."""
        return self.stats.successful > 0 and self.stats.failed > 0

    @property
    def is_complete_success(self) -> bool:
        """Check if all items succeeded."""
        return self.stats.successful == self.stats.total_items and self.stats.failed == 0

    @property
    def is_complete_failure(self) -> bool:
        """Check if all items failed."""
        return self.stats.failed == self.stats.total_items and self.stats.successful == 0


__all__ = [
    "BatchRequest",
    "BatchRequestItem",
    "BatchResponse",
    "BatchResponseItem",
    "BatchResponseStats",
]
