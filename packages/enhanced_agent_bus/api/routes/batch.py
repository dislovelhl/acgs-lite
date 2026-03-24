"""
ACGS-2 Enhanced Agent Bus Batch Processing Routes
Constitutional Hash: cdd01ef066bc6cf2

This module provides batch processing endpoints for governance validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Request,
    status,
)
from src.core.shared.security.auth import UserClaims, get_current_user

from ...api_exceptions import correlation_id_var
from ...api_models import (
    ErrorResponse,
    ServiceUnavailableResponse,
    ValidationErrorResponse,
)
from ..dependencies import get_batch_processor
from ..middleware import logger
from ..rate_limiting import (
    RATE_LIMITING_AVAILABLE,
    RateLimitExceeded,
    check_batch_rate_limit,
    get_remote_address,
    validate_item_sizes,
)

router = APIRouter()

if TYPE_CHECKING:
    from enhanced_agent_bus.models import BatchRequest, BatchResponse

    from ...batch_processor import BatchMessageProcessor
else:
    try:
        from enhanced_agent_bus.models import BatchRequest, BatchResponse
    except ImportError:
        from ...fallback_stubs import BatchRequest, BatchResponse


def _rate_limit_http_exception(error: RateLimitExceeded) -> HTTPException:
    """Convert rate-limit exceptions to standardized HTTP 429 responses."""
    logger.warning("Rate limit exceeded: %s", error, exc_info=True)
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded. Please retry later.",
    )


def _resolve_client_id(request: Request) -> str:
    """Resolve client identifier for rate limiting."""
    if not RATE_LIMITING_AVAILABLE:
        return "default"
    return cast(str, get_remote_address(request))


async def _check_batch_rate_limit_or_raise(client_id: str, item_count: int) -> None:
    """Apply batch-aware rate limiting and map violations to HTTP 429."""
    try:
        await check_batch_rate_limit(client_id, item_count)
    except RateLimitExceeded as err:
        raise _rate_limit_http_exception(err) from err


def _validate_batch_request_safety(batch_request: BatchRequest, tenant_id: str) -> None:
    """Validate payload size and tenant consistency requirements."""
    if size_error := validate_item_sizes(batch_request):
        logger.warning("Batch size validation failed: %s", size_error)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Request payload too large",
        )

    # Validate tenant consistency — reject mismatches, then enforce authenticated tenant
    if batch_request.tenant_id and batch_request.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"tenant_id in body '{batch_request.tenant_id}' must match "
                f"X-Tenant-ID header '{tenant_id}'"
            ),
        )
    batch_request.tenant_id = tenant_id
    validate_fn = getattr(batch_request, "validate_tenant_consistency", None)
    if validate_fn and (tenant_error := validate_fn()):
        logger.error(
            f"Tenant consistency validation failed: {tenant_error}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request",
        )


@router.post(
    "/api/v1/batch/validate",
    responses={
        200: {
            "description": "Batch processed successfully (may include partial failures)",
        },
        400: {
            "model": ErrorResponse,
            "description": "Bad Request - Invalid batch format or constitutional hash mismatch",
        },
        413: {
            "model": ErrorResponse,
            "description": "Payload Too Large - Individual item exceeds size limit",
        },
        422: {
            "model": ValidationErrorResponse,
            "description": "Unprocessable Entity - Batch validation errors",
        },
        429: {
            "model": ErrorResponse,
            "description": "Too Many Requests - Rate limit exceeded",
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal Server Error - Batch processing failed",
        },
        503: {
            "model": ServiceUnavailableResponse,
            "description": "Service Unavailable - Batch processor not initialized",
        },
    },
    summary="Validate batch of governance requests",
    tags=["Batch Processing"],
)
async def batch_validate(
    request: Request,
    batch_request: BatchRequest = Body(...),
    user: UserClaims = Depends(get_current_user),
    processor: BatchMessageProcessor = Depends(get_batch_processor),
) -> BatchResponse:
    """
    Process a batch of governance validation requests.

    **High-Throughput Batch Processing** (Spec 006)

    Enables batch governance validation for processing multiple requests
    simultaneously, maintaining low latency while dramatically improving
    throughput for high-volume applications.

    **Performance Targets:**
    - P99 latency < 10ms for batch of 100 items
    - Throughput > 10,000 RPS in batch mode
    - Max batch size: 1000 items

    **Features:**
    - Parallel validation using asyncio.gather
    - Constitutional hash validation (cdd01ef066bc6cf2)
    - MACI role enforcement with separation of powers
    - Per-item error isolation for partial failure handling
    - Request deduplication within batch
    - Batch-size-aware rate limiting

    **Rate Limiting:**
    - Base limit: 100 tokens/minute per client
    - Cost per batch: batch_size / 10 tokens
    - Example: batch of 100 items consumes 10 tokens

    **Example Request:**
    ```json
    {
        "items": [
            {"content": {"action": "read", "resource": "policy"}, "priority": "high"},
            {"content": {"action": "write", "resource": "audit"}, "priority": "normal"}
        ],
        "constitutional_hash": CONSTITUTIONAL_HASH,  # pragma: allowlist secret
        "tenant_id": "tenant-001"
    }
    ```

    **Returns:**
    BatchResponse with individual validation results, statistics, and warnings.
    """
    tenant_id = user.tenant_id
    correlation_id = correlation_id_var.get()

    item_count = len(batch_request.items)
    await _check_batch_rate_limit_or_raise(_resolve_client_id(request), item_count)
    _validate_batch_request_safety(batch_request, tenant_id)

    logger.info(
        "Processing batch request",
        extra={
            "batch_id": batch_request.batch_id,
            "item_count": item_count,
            "tenant_id": batch_request.tenant_id,
            "correlation_id": correlation_id,
        },
    )
    try:
        response = cast(BatchResponse, await processor.process_batch(batch_request))
    except RateLimitExceeded as err:
        raise _rate_limit_http_exception(err) from err
    except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as err:
        logger.error(
            f"Batch processing failed: {err}",
            extra={
                "batch_id": getattr(batch_request, "batch_id", "unknown"),
                "correlation_id": correlation_id,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Batch processing failed. Check logs with correlation_id for details.",
        ) from err

    logger.info(
        "Batch processing complete",
        extra={
            "batch_id": batch_request.batch_id,
            "success_rate": response.success_rate,
            "p99_latency_ms": response.stats.p99_latency_ms if response.stats else None,
            "correlation_id": correlation_id,
        },
    )
    return response


__all__ = [
    "batch_validate",
    "router",
]
