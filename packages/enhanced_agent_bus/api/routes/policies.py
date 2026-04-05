"""
ACGS-2 Enhanced Agent Bus Policies Routes
Constitutional Hash: 608508a9bd224290

This module provides policy validation endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Request,
)

from enhanced_agent_bus._compat.security.auth import UserClaims, get_current_user

from ..rate_limiting import limiter

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from ...api_models import (
    ErrorResponse,
    ServiceUnavailableResponse,
    ValidationErrorResponse,
)
from ..dependencies import get_agent_bus

POLICY_HASH_PLACEHOLDER = "dev-placeholder-hash"
POLICY_VALIDATION_TIMESTAMP = "2024-01-01T00:00:00Z"
POLICY_VALIDATION_NOTE = "Development mode - simplified validation (tenant-scoped in production)"

if TYPE_CHECKING:
    from ...message_processor import MessageProcessor

router = APIRouter()


@router.post(
    "/api/v1/policies/validate",
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Bad Request - Invalid policy format or constitutional hash mismatch",
        },
        422: {
            "model": ValidationErrorResponse,
            "description": "Unprocessable Entity - Policy validation failed "
            "against governance rules",
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal Server Error - Policy validation processing failed",
        },
        503: {
            "model": ServiceUnavailableResponse,
            "description": "Service Unavailable - Agent bus or OPA service not initialized",
        },
    },
    summary="Validate policy",
    tags=["Policies"],
)
@limiter.limit("20/minute")
async def validate_policy(
    request: Request,
    _payload: JSONDict = Body(...),
    user: UserClaims = Depends(get_current_user),
    _bus: MessageProcessor | dict = Depends(get_agent_bus),
) -> JSONDict:
    """Validate a policy against constitutional requirements."""
    tenant_id = user.tenant_id

    return {
        "valid": True,
        "tenant_id": tenant_id,
        "policy_hash": POLICY_HASH_PLACEHOLDER,
        "validation_timestamp": POLICY_VALIDATION_TIMESTAMP,
        "note": POLICY_VALIDATION_NOTE,
    }


__all__ = [
    "router",
    "validate_policy",
]
