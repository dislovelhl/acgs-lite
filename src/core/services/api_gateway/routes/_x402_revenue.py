"""
x402 Revenue Event Instrumentation

Constitutional Hash: cdd01ef066bc6cf2

Structured revenue tracking for x402 micropayment endpoints.  Emits events
to both structlog (for real-time observability) and an append-only JSONL file
(for offline analytics and auditability).

The ``/x402/revenue`` GET endpoint exposes aggregate revenue statistics and
is restricted to admin callers.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/x402", tags=["x402-revenue"])

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
X402_REVENUE_LOG: str = os.getenv("X402_REVENUE_LOG", "x402_revenue.jsonl")

# ---------------------------------------------------------------------------
# Async-safe JSONL writer lock
# ---------------------------------------------------------------------------
_write_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Revenue event data
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class RevenueEvent:
    """Immutable record of a single x402 payment interaction."""

    endpoint: str
    price_usd: str
    agent_id: str
    decision: str
    timestamp: str
    processing_ms: float
    network: str
    wallet_address: str
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class EndpointStats(BaseModel):
    revenue_usd: float = Field(description="Total revenue in USD for this endpoint")
    call_count: int = Field(description="Number of paid calls")
    avg_processing_ms: float = Field(description="Average processing time in ms")


class RevenueSummary(BaseModel):
    total_revenue_usd: float = Field(description="Aggregate revenue across all endpoints")
    total_calls: int = Field(description="Total paid calls across all endpoints")
    avg_processing_ms: float = Field(description="Global average processing time in ms")
    revenue_by_endpoint: dict[str, EndpointStats] = Field(
        default_factory=dict,
        description="Per-endpoint breakdown",
    )
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    generated_at: str = Field(default="")


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
async def emit_revenue_event(event: RevenueEvent) -> None:
    """Log a revenue event to structlog and append to the JSONL ledger.

    The JSONL write is guarded by an asyncio lock so that concurrent
    coroutines do not interleave partial lines.
    """
    record = asdict(event)

    logger.info(
        "x402_revenue_event",
        endpoint=event.endpoint,
        price_usd=event.price_usd,
        agent_id=event.agent_id,
        decision=event.decision,
        processing_ms=event.processing_ms,
        network=event.network,
    )

    line = json.dumps(record, separators=(",", ":")) + "\n"

    async with _write_lock:
        log_path = Path(X402_REVENUE_LOG)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            logger.error("x402_revenue_write_failed", path=str(log_path))


def _aggregate_events(events: list[dict[str, Any]]) -> RevenueSummary:
    """Pure function: aggregate a list of raw event dicts into a summary."""
    total_revenue = 0.0
    total_ms = 0.0
    total_calls = 0
    by_endpoint: dict[str, dict[str, Any]] = {}

    for evt in events:
        price = float(evt.get("price_usd", "0"))
        ms = float(evt.get("processing_ms", 0))
        ep = evt.get("endpoint", "unknown")

        total_revenue += price
        total_ms += ms
        total_calls += 1

        bucket = by_endpoint.setdefault(ep, {"revenue": 0.0, "count": 0, "ms_sum": 0.0})
        bucket["revenue"] += price
        bucket["count"] += 1
        bucket["ms_sum"] += ms

    endpoint_stats: dict[str, EndpointStats] = {}
    for ep, bucket in by_endpoint.items():
        endpoint_stats[ep] = EndpointStats(
            revenue_usd=round(bucket["revenue"], 6),
            call_count=bucket["count"],
            avg_processing_ms=round(bucket["ms_sum"] / bucket["count"], 2) if bucket["count"] else 0.0,
        )

    return RevenueSummary(
        total_revenue_usd=round(total_revenue, 6),
        total_calls=total_calls,
        avg_processing_ms=round(total_ms / total_calls, 2) if total_calls else 0.0,
        revenue_by_endpoint=endpoint_stats,
        constitutional_hash=CONSTITUTIONAL_HASH,
        generated_at=datetime.now(UTC).isoformat(),
    )


async def get_revenue_summary() -> RevenueSummary:
    """Read the JSONL ledger and return aggregated revenue statistics."""
    log_path = Path(X402_REVENUE_LOG)

    if not log_path.exists():
        return RevenueSummary(
            generated_at=datetime.now(UTC).isoformat(),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    events: list[dict[str, Any]] = []
    try:
        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    events.append(json.loads(stripped))
                except json.JSONDecodeError:
                    logger.warning("x402_revenue_corrupt_line", line=stripped[:120])
    except OSError as exc:
        logger.error("x402_revenue_read_failed", path=str(log_path))
        raise HTTPException(status_code=503, detail="Revenue log unavailable") from exc

    return _aggregate_events(events)


# ---------------------------------------------------------------------------
# Admin endpoint
# ---------------------------------------------------------------------------
@router.get(
    "/revenue",
    response_model=RevenueSummary,
    summary="Revenue summary for x402 paid endpoints",
    responses={
        403: {"description": "Admin access required"},
        503: {"description": "Revenue log unavailable"},
    },
)
async def revenue_summary_endpoint(request: Request) -> RevenueSummary:
    """Return aggregate revenue statistics.  Admin-only, free endpoint."""
    admin_key = os.getenv("X402_ADMIN_KEY", "")
    auth_header = request.headers.get("x-admin-key", "")

    if not admin_key:
        logger.warning("x402_revenue_admin_key_not_configured")
        raise HTTPException(status_code=403, detail="Admin access not configured")

    if auth_header != admin_key:
        raise HTTPException(status_code=403, detail="Invalid admin credentials")

    return await get_revenue_summary()
