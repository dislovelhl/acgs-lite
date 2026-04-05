"""
ACGS-2 Stats Endpoint
Constitutional Hash: 608508a9bd224290

GET /v1/stats — returns real aggregated validation statistics.
Requires API key authentication.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from ..api_key_auth import require_api_key
from ..rate_limiting import limiter
from ..runtime_guards import require_sandbox_endpoint
from ..validation_store import (
    RecentValidationRecord,
    ValidationStats,
    get_validation_store,
)

router = APIRouter(prefix="/v1", tags=["stats"])


class StatsResponse(BaseModel):
    """Aggregated validation statistics."""

    total_validations: int
    compliance_rate: float
    avg_latency_ms: float
    unique_agents: int
    constitutional_hash: str
    recent_validations: list[RecentValidationRecord]


@router.get("/stats", response_model=StatsResponse)
@limiter.limit("60/minute")
async def get_stats(
    request: Request,
    _api_key: str = Depends(require_api_key),
) -> StatsResponse:
    """Return sandbox-only validation statistics from the in-memory store."""
    require_sandbox_endpoint(
        "Public stats endpoint",
        "it reports non-authoritative in-memory validation history",
    )
    stats: ValidationStats = get_validation_store().get_stats()
    return StatsResponse(constitutional_hash=CONSTITUTIONAL_HASH, **stats)
