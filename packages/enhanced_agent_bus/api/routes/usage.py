"""
ACGS-2 Usage Endpoint
Constitutional Hash: 608508a9bd224290

GET /v1/usage — returns remaining quota for the authenticated developer.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..api_key_auth import require_api_key
from ..rate_limiting import limiter
from ..runtime_guards import require_sandbox_endpoint
from .signup import get_account

router = APIRouter(prefix="/v1", tags=["usage"])
DEFAULT_MONTHLY_LIMIT = 1000
UNLIMITED_LIMIT = -1
EXTERNAL_PLAN = "external"


class UsageResponse(BaseModel):
    """Usage statistics for the authenticated developer."""

    used: int
    limit: int
    remaining: int
    plan: str
    resets_at: str


def _next_reset_time() -> datetime:
    """Get the first day of next month in timezone.utc."""
    now = datetime.now(tz=UTC)
    if now.month == 12:
        return datetime(now.year + 1, 1, 1, tzinfo=UTC)
    return datetime(now.year, now.month + 1, 1, tzinfo=UTC)


def _resolve_usage_quota(api_key: str) -> tuple[int, int, str]:
    """Resolve usage counters for API key."""
    account = get_account(api_key)
    if not account:
        return 0, UNLIMITED_LIMIT, EXTERNAL_PLAN

    return (
        account.get("used_this_month", 0),
        account.get("monthly_limit", DEFAULT_MONTHLY_LIMIT),
        account.get("plan", EXTERNAL_PLAN),
    )


@router.get("/usage", response_model=UsageResponse)
@limiter.limit("60/minute")
async def get_usage(
    request: Request,
    api_key: str = Depends(require_api_key),
) -> UsageResponse:
    """Return sandbox-only usage stats backed by the in-memory signup store."""
    require_sandbox_endpoint(
        "Public usage endpoint",
        "it derives quotas from the sandbox in-memory signup account store",
    )
    used, limit, plan = _resolve_usage_quota(api_key)
    resets_at = _next_reset_time()
    remaining = max(0, limit - used) if limit > 0 else UNLIMITED_LIMIT

    return UsageResponse(
        used=used,
        limit=limit,
        remaining=remaining,
        plan=plan,
        resets_at=resets_at.isoformat(),
    )
