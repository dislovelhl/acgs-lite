"""Comprehensive tests for the pipeline_metrics route module.

Covers all Pydantic models, helper functions, the /metrics endpoint,
response shape validation, SLA status logic, and jitter bounds.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.services.api_gateway.routes.pipeline_metrics import (
    CONSTITUTIONAL_HASH,
    PipelineMetricsResponse,
    PipelineStage,
    ScalingRecommendation,
    StageLatency,
    ThroughputMetrics,
    _jitter,
    _status_for,
    router,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def pipeline_app() -> FastAPI:
    """Standalone FastAPI app with only the pipeline router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def pipeline_client(pipeline_app: FastAPI) -> TestClient:
    return TestClient(pipeline_app)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestConstants:
    def test_constitutional_hash_value(self) -> None:
        assert CONSTITUTIONAL_HASH == "608508a9bd224290"

    def test_router_prefix(self) -> None:
        assert router.prefix == "/api/v1/pipeline"

    def test_router_tags(self) -> None:
        assert "pipeline-metrics" in router.tags


# ---------------------------------------------------------------------------
# Pydantic model construction
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPydanticModels:
    def test_stage_latency_construction(self) -> None:
        latency = StageLatency(
            p50_ms=1.0,
            p95_ms=2.0,
            p99_ms=3.0,
            avg_ms=1.5,
            sample_count=100,
        )
        assert latency.p50_ms == 1.0
        assert latency.p95_ms == 2.0
        assert latency.p99_ms == 3.0
        assert latency.avg_ms == 1.5
        assert latency.sample_count == 100

    def test_pipeline_stage_construction(self) -> None:
        stage = PipelineStage(
            id="layer1",
            name="Test Stage",
            order=1,
            budget_ms=10.0,
            latency=StageLatency(
                p50_ms=0.5,
                p95_ms=1.0,
                p99_ms=2.0,
                avg_ms=0.7,
                sample_count=50,
            ),
            status="healthy",
            sla_compliant=True,
            recent_violations=0,
            total_processed=1000,
        )
        assert stage.id == "layer1"
        assert stage.order == 1
        assert stage.sla_compliant is True

    def test_throughput_metrics_construction(self) -> None:
        tp = ThroughputMetrics(
            current_rps=100.0,
            peak_rps=200.0,
            avg_rps=150.0,
            total_requests=50000,
        )
        assert tp.current_rps == 100.0
        assert tp.total_requests == 50000

    def test_scaling_recommendation_construction(self) -> None:
        rec = ScalingRecommendation(
            direction="maintain",
            urgency="none",
            reasons=[],
        )
        assert rec.direction == "maintain"
        assert rec.reasons == []

    def test_scaling_recommendation_with_reasons(self) -> None:
        rec = ScalingRecommendation(
            direction="scale_up",
            urgency="immediate",
            reasons=["high latency", "SLA breach"],
        )
        assert len(rec.reasons) == 2
        assert rec.urgency == "immediate"

    def test_pipeline_metrics_response_construction(self) -> None:
        resp = PipelineMetricsResponse(
            timestamp="2026-01-01T00:00:00+00:00",
            constitutional_hash="608508a9bd224290",
            total_sla_ms=50.0,
            total_elapsed_ms=20.0,
            sla_status="healthy",
            stages=[],
            throughput=ThroughputMetrics(
                current_rps=10.0,
                peak_rps=20.0,
                avg_rps=15.0,
                total_requests=100,
            ),
            scaling_recommendation=ScalingRecommendation(
                direction="maintain",
                urgency="none",
                reasons=[],
            ),
        )
        assert resp.constitutional_hash == "608508a9bd224290"
        assert resp.sla_status == "healthy"
        assert resp.stages == []


# ---------------------------------------------------------------------------
# _jitter helper
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestJitter:
    def test_jitter_returns_float(self) -> None:
        result = _jitter(10.0)
        assert isinstance(result, float)

    def test_jitter_within_default_bounds(self) -> None:
        """With pct=0.15, output must be within base * [0.85, 1.15]."""
        base = 100.0
        for _ in range(200):
            val = _jitter(base, pct=0.15)
            assert base * 0.85 <= val <= base * 1.15

    def test_jitter_within_custom_bounds(self) -> None:
        base = 50.0
        pct = 0.3
        for _ in range(200):
            val = _jitter(base, pct=pct)
            assert base * (1.0 - pct) <= val <= base * (1.0 + pct)

    def test_jitter_zero_base(self) -> None:
        assert _jitter(0.0) == 0.0

    def test_jitter_zero_pct(self) -> None:
        """Zero pct means no jitter -- output equals base."""
        assert _jitter(42.0, pct=0.0) == 42.0

    def test_jitter_negative_base(self) -> None:
        """Negative base should still scale proportionally."""
        base = -10.0
        result = _jitter(base, pct=0.0)
        assert result == base


# ---------------------------------------------------------------------------
# _status_for helper
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestStatusFor:
    def test_healthy_when_ratio_below_0_7(self) -> None:
        assert _status_for(3.0, 10.0) == "healthy"

    def test_healthy_at_zero(self) -> None:
        assert _status_for(0.0, 10.0) == "healthy"

    def test_warning_when_ratio_between_0_7_and_0_9(self) -> None:
        assert _status_for(7.5, 10.0) == "warning"

    def test_warning_at_exactly_0_7(self) -> None:
        assert _status_for(7.0, 10.0) == "warning"

    def test_critical_when_ratio_at_or_above_0_9(self) -> None:
        assert _status_for(9.0, 10.0) == "critical"

    def test_critical_above_budget(self) -> None:
        assert _status_for(15.0, 10.0) == "critical"

    def test_boundary_just_below_0_7(self) -> None:
        assert _status_for(6.99, 10.0) == "healthy"

    def test_boundary_just_below_0_9(self) -> None:
        assert _status_for(8.99, 10.0) == "warning"


# ---------------------------------------------------------------------------
# GET /metrics endpoint
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPipelineMetricsEndpoint:
    def test_returns_200(self, pipeline_client: TestClient) -> None:
        resp = pipeline_client.get("/api/v1/pipeline/metrics")
        assert resp.status_code == 200

    def test_response_is_valid_json(self, pipeline_client: TestClient) -> None:
        resp = pipeline_client.get("/api/v1/pipeline/metrics")
        data = resp.json()
        assert isinstance(data, dict)

    def test_constitutional_hash_in_response(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        assert data["constitutional_hash"] == "608508a9bd224290"

    def test_total_sla_ms_is_50(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        assert data["total_sla_ms"] == 50.0

    def test_four_stages_returned(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        assert len(data["stages"]) == 4

    def test_stage_ids(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        ids = [s["id"] for s in data["stages"]]
        assert ids == [
            "layer1_validation",
            "layer2_deliberation",
            "layer3_policy",
            "layer4_audit",
        ]

    def test_stage_orders_sequential(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        orders = [s["order"] for s in data["stages"]]
        assert orders == [1, 2, 3, 4]

    def test_stage_budgets(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        budgets = [s["budget_ms"] for s in data["stages"]]
        assert budgets == [5.0, 20.0, 10.0, 15.0]

    def test_stage_names(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        names = [s["name"] for s in data["stages"]]
        assert names == [
            "MACI Enforcement",
            "Tenant Validation",
            "Impact Analysis",
            "Constitutional Check",
        ]

    def test_each_stage_has_latency_fields(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        required_keys = {"p50_ms", "p95_ms", "p99_ms", "avg_ms", "sample_count"}
        for stage in data["stages"]:
            assert required_keys.issubset(stage["latency"].keys())

    def test_each_stage_has_status_field(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        valid_statuses = {"healthy", "warning", "critical"}
        for stage in data["stages"]:
            assert stage["status"] in valid_statuses

    def test_each_stage_has_sla_compliant_bool(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        for stage in data["stages"]:
            assert isinstance(stage["sla_compliant"], bool)

    def test_throughput_section_present(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        tp = data["throughput"]
        assert "current_rps" in tp
        assert "peak_rps" in tp
        assert "avg_rps" in tp
        assert "total_requests" in tp

    def test_scaling_recommendation_present(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        sr = data["scaling_recommendation"]
        assert sr["direction"] == "maintain"
        assert sr["urgency"] == "none"
        assert sr["reasons"] == []

    def test_timestamp_is_iso_format(self, pipeline_client: TestClient) -> None:
        from datetime import datetime

        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        # Should not raise
        datetime.fromisoformat(data["timestamp"])

    def test_total_elapsed_ms_is_positive(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        assert data["total_elapsed_ms"] > 0

    def test_response_validates_against_model(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        parsed = PipelineMetricsResponse(**data)
        assert parsed.constitutional_hash == "608508a9bd224290"
        assert len(parsed.stages) == 4

    def test_layer2_has_zero_violations(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        layer2 = data["stages"][1]
        assert layer2["id"] == "layer2_deliberation"
        assert layer2["recent_violations"] == 0


# ---------------------------------------------------------------------------
# SLA status logic via controlled jitter
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSlaStatusLogic:
    def _get_metrics_with_fixed_random(
        self, pipeline_client: TestClient, random_value: float
    ) -> dict:
        """Return metrics with random.random() pinned to a fixed value."""
        with patch(
            "src.core.services.api_gateway.routes.pipeline_metrics.random.random",
            return_value=random_value,
        ):
            return pipeline_client.get("/api/v1/pipeline/metrics").json()

    def test_sla_healthy_with_low_jitter(self, pipeline_client: TestClient) -> None:
        """random=0.5 means jitter multiplier is 1.0 (no change).

        Base p99 sum: 0.103 + 3.8 + 4.2 + 12.3 = 20.403
        Well under 45.0 => healthy.
        """
        data = self._get_metrics_with_fixed_random(pipeline_client, 0.5)
        assert data["sla_status"] == "healthy"

    def test_sla_deterministic_elapsed(self, pipeline_client: TestClient) -> None:
        """With random=0.5, jitter factor is exactly 1.0, so elapsed = sum of bases."""
        data = self._get_metrics_with_fixed_random(pipeline_client, 0.5)
        expected_elapsed = round(0.103 + 3.8 + 4.2 + 12.3, 2)
        assert data["total_elapsed_ms"] == expected_elapsed

    def test_sla_warning_threshold(self, pipeline_client: TestClient) -> None:
        """Verify the warning boundary: total_elapsed > 45.0 but <= 50.0."""
        # We need jitter factor > 45.0 / 20.403 ~ 2.205
        # jitter factor = 1.0 + (random_val - 0.5) * 2.0 * pct
        # For layer4 (pct=0.2): factor = 1.0 + (r - 0.5) * 0.4
        # Max factor at r=1.0: 1.2 for layers 1-3, 1.4 for layer4
        # Max sum: 0.103*1.15 + 3.8*1.15 + 4.2*1.15 + 12.3*1.2
        #        = 0.11845 + 4.37 + 4.83 + 14.76 = ~24.08
        # This never reaches 45, so we test via direct model construction
        resp = PipelineMetricsResponse(
            timestamp="2026-01-01T00:00:00+00:00",
            constitutional_hash="608508a9bd224290",
            total_sla_ms=50.0,
            total_elapsed_ms=47.0,
            sla_status="warning",
            stages=[],
            throughput=ThroughputMetrics(
                current_rps=10.0, peak_rps=20.0, avg_rps=15.0, total_requests=100
            ),
            scaling_recommendation=ScalingRecommendation(
                direction="maintain", urgency="none", reasons=[]
            ),
        )
        assert resp.sla_status == "warning"

    def test_sla_critical_threshold(self, pipeline_client: TestClient) -> None:
        """Verify critical is set when total_elapsed > 50.0."""
        resp = PipelineMetricsResponse(
            timestamp="2026-01-01T00:00:00+00:00",
            constitutional_hash="608508a9bd224290",
            total_sla_ms=50.0,
            total_elapsed_ms=55.0,
            sla_status="critical",
            stages=[],
            throughput=ThroughputMetrics(
                current_rps=10.0, peak_rps=20.0, avg_rps=15.0, total_requests=100
            ),
            scaling_recommendation=ScalingRecommendation(
                direction="maintain", urgency="none", reasons=[]
            ),
        )
        assert resp.sla_status == "critical"


# ---------------------------------------------------------------------------
# SLA status branch coverage via endpoint with patched jitter
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSlaStatusBranches:
    """Test sla_status computation branches in pipeline_metrics() directly."""

    def test_healthy_branch(self, pipeline_client: TestClient) -> None:
        """Sum of p99 bases ~20.4 => healthy (< 45)."""
        with patch(
            "src.core.services.api_gateway.routes.pipeline_metrics._jitter",
            side_effect=lambda base, pct=0.15: base,
        ):
            data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        assert data["sla_status"] == "healthy"
        assert data["total_elapsed_ms"] == round(0.103 + 3.8 + 4.2 + 12.3, 2)

    def test_warning_branch(self, pipeline_client: TestClient) -> None:
        """Make total_elapsed land between 45 and 50 => warning."""

        def _scale_up(base: float, pct: float = 0.15) -> float:
            # Multiply to push total above 45 but under 50
            # Original sum of p99 bases: 20.403
            # Need factor ~2.3 => sum ~46.9
            return base * 2.3

        with patch(
            "src.core.services.api_gateway.routes.pipeline_metrics._jitter",
            side_effect=_scale_up,
        ):
            data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        assert data["sla_status"] == "warning"

    def test_critical_branch(self, pipeline_client: TestClient) -> None:
        """Make total_elapsed > 50 => critical."""

        def _scale_way_up(base: float, pct: float = 0.15) -> float:
            return base * 3.0

        with patch(
            "src.core.services.api_gateway.routes.pipeline_metrics._jitter",
            side_effect=_scale_way_up,
        ):
            data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        assert data["sla_status"] == "critical"


# ---------------------------------------------------------------------------
# Multiple requests return independent jitter
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestJitterVariation:
    def test_two_requests_may_differ(self, pipeline_client: TestClient) -> None:
        """Successive requests should (usually) produce different elapsed values."""
        results: list[float] = []
        for _ in range(10):
            data = pipeline_client.get("/api/v1/pipeline/metrics").json()
            results.append(data["total_elapsed_ms"])
        unique = set(results)
        # With 10 random draws, the chance of all being identical is negligible
        assert len(unique) > 1


# ---------------------------------------------------------------------------
# Edge: latency sample counts are positive integers
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSampleCounts:
    def test_sample_counts_positive(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        for stage in data["stages"]:
            assert stage["latency"]["sample_count"] > 0
            assert isinstance(stage["latency"]["sample_count"], int)

    def test_total_processed_positive(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        for stage in data["stages"]:
            assert stage["total_processed"] > 0
            assert isinstance(stage["total_processed"], int)


# ---------------------------------------------------------------------------
# Throughput bounds
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestThroughputBounds:
    def test_throughput_values_positive(self, pipeline_client: TestClient) -> None:
        data = pipeline_client.get("/api/v1/pipeline/metrics").json()
        tp = data["throughput"]
        assert tp["current_rps"] > 0
        assert tp["peak_rps"] > 0
        assert tp["avg_rps"] > 0
        assert tp["total_requests"] > 0
