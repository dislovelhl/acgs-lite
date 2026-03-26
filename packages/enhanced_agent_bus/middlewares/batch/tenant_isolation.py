"""
Batch Tenant Isolation Middleware for ACGS-2 Pipeline.

Ensures all batch items belong to same tenant.
Extracted from: batch_processor.py + models.py

Constitutional Hash: 608508a9bd224290
"""

import time
from typing import cast

from enhanced_agent_bus.validators import ValidationResult

from ...batch_models import BatchRequestItem
from ...pipeline.context import PipelineContext
from ...pipeline.middleware import BaseMiddleware, MiddlewareConfig
from .context import BatchPipelineContext
from .exceptions import BatchTenantIsolationException


class BatchTenantIsolationMiddleware(BaseMiddleware):
    """Ensures all batch items belong to same tenant.

    Enforces multi-tenant isolation at the batch level:
    - Validates all items share the same tenant_id
    - Supports tenant inheritance (default -> batch tenant)
    - Prevents cross-tenant data leakage
    - Validates against batch-level tenant_id if set

    Example:
        middleware = BatchTenantIsolationMiddleware()
        context = await middleware.process(batch_context)

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: MiddlewareConfig | None = None,
    ):
        """Initialize batch tenant isolation middleware.

        Args:
            config: Middleware configuration (timeout, fail_closed, etc.)
        """
        super().__init__(config)

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Process tenant isolation validation.

        Steps:
        1. Determine effective tenant ID
        2. Validate all items belong to same tenant
        3. Set tenant metadata on context

        Args:
            context: Batch pipeline context containing items

        Returns:
            Context with tenant validation results

        Raises:
            BatchTenantIsolationException: If validation fails and fail_closed is True
        """
        context = cast(BatchPipelineContext, context)
        start_time = time.perf_counter()

        # Skip if no items to validate
        if not context.batch_items:
            context = await self._call_next(context)
            return context

        # Validate tenant consistency
        is_valid, error_msg = self._validate_tenant_consistency(context.batch_items)

        if not is_valid:
            # Collect conflicting tenants for error details
            tenants = self._extract_tenants(context.batch_items)
            conflicting = list(set(t for t in tenants if t))

            if self.config.fail_closed:
                raise BatchTenantIsolationException(
                    message=error_msg,
                    tenant_id=context.batch_tenant_id,
                    conflicting_tenants=conflicting,
                )

            # Non-fail-closed: set early result and continue
            context.set_early_result(
                ValidationResult(
                    is_valid=False,
                    errors=[error_msg],
                    metadata={
                        "validation_stage": "tenant_isolation",
                        "conflicting_tenants": conflicting,
                    },
                )
            )
            context = await self._call_next(context)
            return context

        # Determine effective tenant ID
        effective_tenant = self._determine_effective_tenant(context.batch_items)
        if effective_tenant:
            context.batch_tenant_id = effective_tenant

        # Record metrics
        duration_ms = (time.perf_counter() - start_time) * 1000
        context.batch_latency_ms += duration_ms

        context = await self._call_next(context)
        return context

    def _validate_tenant_consistency(
        self,
        items: list[BatchRequestItem],
    ) -> tuple[bool, str]:
        """Validate all items belong to same tenant.

        Args:
            items: List of batch items to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not items:
            return True, ""

        # Get effective tenant for each item
        # Items with "default" or empty tenant inherit from first non-default
        non_default_tenants: list[str] = []

        for item in items:
            tenant = item.tenant_id or "default"
            if tenant != "default":
                non_default_tenants.append(tenant)

        # If no non-default tenants, all are "default" - valid
        if not non_default_tenants:
            return True, ""

        # Check all non-default tenants match
        first_tenant = non_default_tenants[0]
        for tenant in non_default_tenants[1:]:
            if tenant != first_tenant:
                return False, (
                    f"Cross-tenant batch detected: items have different tenants "
                    f"({first_tenant} vs {tenant})"
                )

        return True, ""

    def _extract_tenants(self, items: list[BatchRequestItem]) -> list[str]:
        """Extract all tenant IDs from items.

        Args:
            items: List of batch items

        Returns:
            List of tenant IDs
        """
        return [item.tenant_id or "default" for item in items]

    def _determine_effective_tenant(
        self,
        items: list[BatchRequestItem],
    ) -> str | None:
        """Determine the effective tenant ID for the batch.

        Uses the first non-default tenant, or "default" if all are default.

        Args:
            items: List of batch items

        Returns:
            Effective tenant ID or None if no items
        """
        if not items:
            return None

        for item in items:
            tenant = item.tenant_id or "default"
            if tenant != "default":
                return tenant

        return "default"

    def _normalize_tenant_id(self, tenant_id: str | None) -> str:
        """Normalize tenant ID to canonical form.

        Args:
            tenant_id: Raw tenant ID

        Returns:
            Normalized tenant ID (never None)
        """
        if not tenant_id:
            return "default"
        return tenant_id.strip().lower()
