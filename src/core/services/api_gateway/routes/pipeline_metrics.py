"""Pipeline metrics endpoint for governance visualization.

Returns per-layer latency, throughput, and SLA status matching
the 4-layer timeout budget architecture.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import random
import time
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline-metrics"])

_START_TIME = time.monotonic()
CONSTITUTIONAL_HASH = "cdd01ef066bc6cf2"


class StageLatency(BaseModel):
    p50_ms: float
    p95_ms: float
    p99_ms: float
    avg_ms: float
    sample_count: int


class PipelineStage(BaseModel):
    id: str
    name: str
    order: int
    budget_ms: float
    latency: StageLatency
    status: str  # healthy, warning, critical
    sla_compliant: bool
    recent_violations: int
    total_processed: int


class ThroughputMetrics(BaseModel):
    current_rps: float
    peak_rps: float
    avg_rps: float
    total_requests: int


class ScalingRecommendation(BaseModel):
    direction: str  # scale_up, scale_down, maintain
    urgency: str  # immediate, soon, none
    reasons: list[str]


class PipelineMetricsResponse(BaseModel):
    timestamp: str
    constitutional_hash: str
    total_sla_ms: float
    total_elapsed_ms: float
    sla_status: str
    stages: list[PipelineStage]
    throughput: ThroughputMetrics
    scaling_recommendation: ScalingRecommendation


def _jitter(base: float, pct: float = 0.15) -> float:
    return base * (1.0 + (random.random() - 0.5) * 2.0 * pct)  # noqa: S311


def _status_for(p99: float, budget: float) -> str:
    ratio = p99 / budget
    if ratio < 0.7:
        return "healthy"
    if ratio < 0.9:
        return "warning"
    return "critical"


@router.get("/metrics", response_model=PipelineMetricsResponse)
async def pipeline_metrics() -> PipelineMetricsResponse:
    """Aggregated pipeline metrics for all 4 governance layers.

    In production, this reads from the TimeoutBudgetManager and
    EnhancedAgentBusCapacityMetrics collectors. For now, returns
    realistic demo data with jitter.
    """
    now = datetime.now(UTC).isoformat()
    uptime = time.monotonic() - _START_TIME

    # Layer metrics with realistic jitter
    layer1_p99 = _jitter(0.103)
    layer2_p99 = _jitter(3.8)
    layer3_p99 = _jitter(4.2)
    layer4_p99 = _jitter(12.3, 0.2)

    total_elapsed = layer1_p99 + layer2_p99 + layer3_p99 + layer4_p99

    stages = [
        PipelineStage(
            id="layer1_validation",
            name="MACI Enforcement",
            order=1,
            budget_ms=5.0,
            latency=StageLatency(
                p50_ms=_jitter(0.08),
                p95_ms=_jitter(0.09),
                p99_ms=layer1_p99,
                avg_ms=_jitter(0.085),
                sample_count=int(_jitter(15423, 0.05)),
            ),
            status=_status_for(layer1_p99, 5.0),
            sla_compliant=layer1_p99 <= 5.0,
            recent_violations=int(_jitter(37, 0.3)),
            total_processed=int(_jitter(15423, 0.05)),
        ),
        PipelineStage(
            id="layer2_deliberation",
            name="Tenant Validation",
            order=2,
            budget_ms=20.0,
            latency=StageLatency(
                p50_ms=_jitter(1.2),
                p95_ms=_jitter(2.1),
                p99_ms=layer2_p99,
                avg_ms=_jitter(1.5),
                sample_count=int(_jitter(15386, 0.05)),
            ),
            status=_status_for(layer2_p99, 20.0),
            sla_compliant=layer2_p99 <= 20.0,
            recent_violations=0,
            total_processed=int(_jitter(15386, 0.05)),
        ),
        PipelineStage(
            id="layer3_policy",
            name="Impact Analysis",
            order=3,
            budget_ms=10.0,
            latency=StageLatency(
                p50_ms=_jitter(0.5),
                p95_ms=_jitter(1.8),
                p99_ms=layer3_p99,
                avg_ms=_jitter(0.9),
                sample_count=int(_jitter(15380, 0.05)),
            ),
            status=_status_for(layer3_p99, 10.0),
            sla_compliant=layer3_p99 <= 10.0,
            recent_violations=int(_jitter(6, 0.4)),
            total_processed=int(_jitter(15380, 0.05)),
        ),
        PipelineStage(
            id="layer4_audit",
            name="Constitutional Check",
            order=4,
            budget_ms=15.0,
            latency=StageLatency(
                p50_ms=_jitter(3.1),
                p95_ms=_jitter(8.5),
                p99_ms=layer4_p99,
                avg_ms=_jitter(4.2),
                sample_count=int(_jitter(15371, 0.05)),
            ),
            status=_status_for(layer4_p99, 15.0),
            sla_compliant=layer4_p99 <= 15.0,
            recent_violations=int(_jitter(9, 0.3)),
            total_processed=int(_jitter(15371, 0.05)),
        ),
    ]

    sla_status = "healthy"
    if total_elapsed > 45.0:
        sla_status = "warning"
    if total_elapsed > 50.0:
        sla_status = "critical"

    return PipelineMetricsResponse(
        timestamp=now,
        constitutional_hash=CONSTITUTIONAL_HASH,
        total_sla_ms=50.0,
        total_elapsed_ms=round(total_elapsed, 2),
        sla_status=sla_status,
        stages=stages,
        throughput=ThroughputMetrics(
            current_rps=round(_jitter(5066, 0.1), 1),
            peak_rps=round(_jitter(7200, 0.05), 1),
            avg_rps=round(_jitter(4800, 0.08), 1),
            total_requests=int(_jitter(61560 + uptime * 10, 0.05)),
        ),
        scaling_recommendation=ScalingRecommendation(
            direction="maintain",
            urgency="none",
            reasons=[],
        ),
    )
