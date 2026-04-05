"""
Batch Validation Middleware for ACGS-2 Pipeline.

Validates BatchRequest structure and item schema.
Extracted from: batch_processor.py + batch_processor_infra/orchestrator.py

Constitutional Hash: 608508a9bd224290
"""

import time
from typing import cast

from enhanced_agent_bus.validators import ValidationResult

from ...batch_models import BatchRequest, BatchRequestItem
from ...pipeline.context import PipelineContext
from ...pipeline.middleware import BaseMiddleware, MiddlewareConfig
from .context import BatchPipelineContext
from .exceptions import BatchValidationException


class BatchValidationMiddleware(BaseMiddleware):
    """Validates BatchRequest structure and item schema.

    Performs comprehensive validation of batch requests:
    - Batch size limits (min/max)
    - Item count validation
    - Required field presence
    - Schema compliance
    - Constitutional hash validation (per-item)

    Example:
        middleware = BatchValidationMiddleware(
            config=MiddlewareConfig(timeout_ms=500),
            max_batch_size=1000,
            min_batch_size=1,
        )
        context = await middleware.process(batch_context)

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: MiddlewareConfig | None = None,
        max_batch_size: int = 1000,
        min_batch_size: int = 1,
    ):
        """Initialize batch validation middleware.

        Args:
            config: Middleware configuration (timeout, fail_closed, etc.)
            max_batch_size: Maximum allowed items in a batch (default: 1000)
            min_batch_size: Minimum required items in a batch (default: 1)
        """
        super().__init__(config)
        self._max_batch_size = max_batch_size
        self._min_batch_size = min_batch_size

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Process batch validation.

        Steps:
        1. Validate batch request exists
        2. Validate batch structure (size limits)
        3. Validate each item's schema
        4. Set validation flags on context

        Args:
            context: Batch pipeline context containing the request

        Returns:
            Context with validation results

        Raises:
            BatchValidationException: If validation fails and fail_closed is True
        """
        context = cast(BatchPipelineContext, context)
        start_time = time.perf_counter()

        # Check batch request exists
        if context.batch_request is None:
            error_msg = "Batch request is required but not provided"
            if self.config.fail_closed:
                raise BatchValidationException(
                    message=error_msg,
                    validation_errors=[error_msg],
                )
            context.set_early_result(
                ValidationResult(
                    is_valid=False,
                    errors=[error_msg],
                    metadata={"validation_stage": "batch_structure"},
                )
            )
            return await self._call_next(context)

        # Validate batch structure
        batch_errors = self._validate_batch_request(context.batch_request)
        if batch_errors:
            if self.config.fail_closed:
                raise BatchValidationException(
                    message=f"Batch validation failed: {'; '.join(batch_errors)}",
                    validation_errors=batch_errors,
                )
            context.set_early_result(
                ValidationResult(
                    is_valid=False,
                    errors=batch_errors,
                    metadata={"validation_stage": "batch_structure"},
                )
            )
            return await self._call_next(context)

        # Validate each item
        context.batch_items = []
        all_item_errors: list[str] = []
        for idx, item in enumerate(context.batch_request.items):
            item_errors = self._validate_batch_item(item)
            if item_errors:
                all_item_errors.extend([f"Item[{idx}]: {e}" for e in item_errors])
            else:
                context.batch_items.append(item)

        if all_item_errors:
            if self.config.fail_closed:
                raise BatchValidationException(
                    message="Batch item validation failed",
                    validation_errors=all_item_errors,
                    details={"failed_items": len(all_item_errors)},
                )
            context.set_early_result(
                ValidationResult(
                    is_valid=False,
                    errors=all_item_errors,
                    metadata={"validation_stage": "batch_items"},
                )
            )
            return await self._call_next(context)

        # Set batch metadata
        context.batch_size = len(context.batch_items)
        context.batch_tenant_id = context.batch_request.tenant_id
        context.fail_fast = context.batch_request.fail_fast
        context.deduplicate = context.batch_request.deduplicate

        # Record metrics
        duration_ms = (time.perf_counter() - start_time) * 1000
        context.batch_latency_ms += duration_ms

        return await self._call_next(context)

    def _validate_batch_request(self, request: BatchRequest) -> list[str]:
        """Validate batch request structure.

        Args:
            request: The batch request to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors: list[str] = []

        # Check items exist
        if not request.items:
            errors.append("Batch request must contain at least one item")
            return errors

        # Check batch size limits
        item_count = len(request.items)
        if item_count < self._min_batch_size:
            errors.append(f"Batch size {item_count} below minimum {self._min_batch_size}")
        if item_count > self._max_batch_size:
            errors.append(f"Batch size {item_count} exceeds maximum {self._max_batch_size}")

        # Validate constitutional hash if present
        if request.constitutional_hash:
            from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

            if request.constitutional_hash != CONSTITUTIONAL_HASH:
                errors.append(f"Invalid constitutional hash: {request.constitutional_hash}")

        return errors

    def _validate_batch_item(self, item: BatchRequestItem) -> list[str]:
        """Validate a single batch item.

        Args:
            item: The batch request item to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors: list[str] = []

        # Check required fields
        self._validate_required_fields(item, errors)

        # Validate optional field formats
        self._validate_priority_field(item, errors)
        self._validate_tenant_id_field(item, errors)
        self._validate_agent_fields(item, errors)

        # Validate constitutional compliance
        self._validate_constitutional_hash_field(item, errors)

        return errors

    def _validate_required_fields(self, item: BatchRequestItem, errors: list[str]) -> None:
        """Validate required fields are present and correctly typed."""
        if not item.request_id:
            errors.append("request_id is required")

        if not item.content:
            errors.append("content is required")
        elif not isinstance(item.content, dict):
            errors.append("content must be a dictionary")

    def _validate_priority_field(self, item: BatchRequestItem, errors: list[str]) -> None:
        """Validate priority field range and type."""
        if item.priority is not None:
            if not isinstance(item.priority, int) or item.priority < 0 or item.priority > 3:
                errors.append(f"priority must be 0-3, got {item.priority}")

    def _validate_tenant_id_field(self, item: BatchRequestItem, errors: list[str]) -> None:
        """Validate tenant_id field format and length."""
        if item.tenant_id:
            if not isinstance(item.tenant_id, str):
                errors.append("tenant_id must be a string")
            elif len(item.tenant_id) > 128:
                errors.append("tenant_id exceeds 128 characters")

    def _validate_agent_fields(self, item: BatchRequestItem, errors: list[str]) -> None:
        """Validate agent-related fields."""
        # Validate from_agent if present
        if item.from_agent and not isinstance(item.from_agent, str):
            errors.append("from_agent must be a string")

        # Validate message_type if present
        if item.message_type and not isinstance(item.message_type, str):
            errors.append("message_type must be a string")

    def _validate_constitutional_hash_field(
        self, item: BatchRequestItem, errors: list[str]
    ) -> None:
        """Validate per-item constitutional hash compliance."""
        if item.constitutional_hash:
            from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

            if item.constitutional_hash != CONSTITUTIONAL_HASH:
                errors.append(f"Invalid item constitutional hash: {item.constitutional_hash}")
