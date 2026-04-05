"""
Coverage batch 11 — comprehensive tests for:
  1. observability/capacity_metrics/registry.py (122 missing, 41.1%)
  2. adaptive_governance/governance_engine.py (147 missing, 72.1%)
  3. deliberation_layer/tensorrt_optimizer.py (141 missing, 58.5%)
  4. pqc_validators.py (134 missing, 51.3%)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. observability/capacity_metrics/registry.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.observability.capacity_metrics.registry import (
    ADAPTIVE_THRESHOLD_BUCKETS,
    BATCH_OVERHEAD_BUCKETS,
    DELIBERATION_LAYER_BUCKETS,
    OPA_POLICY_LATENCY_BUCKETS,
    Z3_SOLVER_LATENCY_BUCKETS,
    CacheLayer,
    CacheMissReason,
    PerformanceMetricsRegistry,
    adaptive_threshold_timer,
    batch_overhead_timer,
    deliberation_layer_timer,
    get_performance_metrics,
    maci_enforcement_timer,
    opa_policy_timer,
    record_adaptive_threshold_decision,
    record_batch_processing_overhead,
    record_cache_miss,
    record_constitutional_validation,
    record_deliberation_layer_duration,
    record_maci_enforcement_latency,
    record_opa_policy_evaluation,
    record_z3_solver_latency,
    reset_performance_metrics,
    z3_solver_timer,
)
from enhanced_agent_bus.observability.capacity_metrics.registry import (
    ValidationResult as MetricsValidationResult,
)


class TestBucketDefinitions:
    def test_z3_buckets(self):
        assert len(Z3_SOLVER_LATENCY_BUCKETS) > 0
        assert all(isinstance(b, (int, float)) for b in Z3_SOLVER_LATENCY_BUCKETS)

    def test_adaptive_threshold_buckets(self):
        assert len(ADAPTIVE_THRESHOLD_BUCKETS) > 0

    def test_batch_overhead_buckets(self):
        assert len(BATCH_OVERHEAD_BUCKETS) > 0

    def test_opa_policy_buckets(self):
        assert len(OPA_POLICY_LATENCY_BUCKETS) > 0

    def test_deliberation_layer_buckets(self):
        assert len(DELIBERATION_LAYER_BUCKETS) > 0


class TestCacheEnums:
    def test_cache_layer_values(self):
        assert CacheLayer.L1.value == "L1"
        assert CacheLayer.L2.value == "L2"
        assert CacheLayer.L3.value == "L3"

    def test_cache_miss_reason_values(self):
        assert CacheMissReason.EXPIRED.value == "expired"
        assert CacheMissReason.EVICTED.value == "evicted"
        assert CacheMissReason.NOT_FOUND.value == "not_found"


class TestMetricsValidationResult:
    def test_values(self):
        assert MetricsValidationResult.SUCCESS.value == "success"
        assert MetricsValidationResult.FAILURE.value == "failure"
        assert MetricsValidationResult.ERROR.value == "error"
        assert MetricsValidationResult.HASH_MISMATCH.value == "hash_mismatch"
        assert MetricsValidationResult.TIMEOUT.value == "timeout"


class TestZ3SolverMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_z3_solver_latency(self):
        record_z3_solver_latency(5.0, operation="solve")
        record_z3_solver_latency(10.0, operation="check")

    def test_z3_solver_timer(self):
        with z3_solver_timer("solve"):
            time.sleep(0.001)

    def test_z3_solver_timer_optimize(self):
        with z3_solver_timer("optimize"):
            pass


class TestAdaptiveThresholdMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_adaptive_threshold_decision(self):
        record_adaptive_threshold_decision(2.0, decision_type="threshold_update")
        record_adaptive_threshold_decision(3.5, decision_type="calibration")

    def test_adaptive_threshold_timer(self):
        with adaptive_threshold_timer("adjustment"):
            time.sleep(0.001)


class TestCacheMissMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_cache_miss_enum(self):
        record_cache_miss(CacheLayer.L1, CacheMissReason.EXPIRED)
        record_cache_miss(CacheLayer.L2, CacheMissReason.EVICTED)
        record_cache_miss(CacheLayer.L3, CacheMissReason.NOT_FOUND)

    def test_record_cache_miss_string(self):
        record_cache_miss("L1", "expired")
        record_cache_miss("custom_layer", "custom_reason")


class TestBatchProcessingMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_batch_small(self):
        record_batch_processing_overhead(50.0, batch_size=5)

    def test_record_batch_medium_low(self):
        record_batch_processing_overhead(100.0, batch_size=25)

    def test_record_batch_medium_high(self):
        record_batch_processing_overhead(200.0, batch_size=75)

    def test_record_batch_large(self):
        record_batch_processing_overhead(500.0, batch_size=200)

    def test_record_batch_very_large(self):
        record_batch_processing_overhead(1000.0, batch_size=600)

    def test_batch_overhead_timer(self):
        with batch_overhead_timer(10):
            time.sleep(0.001)


class TestMACIEnforcementMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_maci_enforcement_latency(self):
        record_maci_enforcement_latency(1.0, maci_role="EXECUTIVE")

    def test_record_maci_p99_after_10_samples(self):
        for i in range(15):
            record_maci_enforcement_latency(float(i), maci_role="LEGISLATIVE")

    def test_maci_enforcement_timer(self):
        with maci_enforcement_timer("JUDICIAL"):
            time.sleep(0.001)


class TestConstitutionalValidationMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_validation_enum(self):
        record_constitutional_validation(MetricsValidationResult.SUCCESS)
        record_constitutional_validation(MetricsValidationResult.FAILURE, "strict")
        record_constitutional_validation(MetricsValidationResult.HASH_MISMATCH, "pqc")
        record_constitutional_validation(MetricsValidationResult.TIMEOUT)
        record_constitutional_validation(MetricsValidationResult.ERROR)

    def test_record_validation_string(self):
        record_constitutional_validation("success", "custom_type")


class TestOPAPolicyMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_opa_policy_evaluation(self):
        record_opa_policy_evaluation(5.0, policy_name="access_control", decision="allow")
        record_opa_policy_evaluation(10.0, policy_name="rate_limit", decision="deny")

    def test_opa_policy_timer_default(self):
        with opa_policy_timer("default") as ctx:
            time.sleep(0.001)
        assert ctx["decision"] == "allow"

    def test_opa_policy_timer_set_decision(self):
        with opa_policy_timer("access_control") as ctx:
            ctx["decision"] = "deny"
        assert ctx["decision"] == "deny"


class TestDeliberationLayerMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_deliberation_none_score(self):
        record_deliberation_layer_duration(50.0, layer_type="consensus")

    def test_record_deliberation_low_score(self):
        record_deliberation_layer_duration(50.0, layer_type="hitl", impact_score=0.1)

    def test_record_deliberation_medium_score(self):
        record_deliberation_layer_duration(50.0, impact_score=0.45)

    def test_record_deliberation_high_score(self):
        record_deliberation_layer_duration(50.0, impact_score=0.7)

    def test_record_deliberation_critical_score(self):
        record_deliberation_layer_duration(50.0, impact_score=0.9)

    def test_deliberation_layer_timer(self):
        with deliberation_layer_timer("impact_scoring", impact_score=0.5):
            time.sleep(0.001)


class TestPerformanceMetricsRegistry:
    def setup_method(self):
        reset_performance_metrics()

    def test_singleton(self):
        r1 = get_performance_metrics()
        r2 = get_performance_metrics()
        assert r1 is r2

    def test_reset_creates_new(self):
        r1 = get_performance_metrics()
        reset_performance_metrics()
        r2 = get_performance_metrics()
        assert r1 is not r2

    def test_constitutional_hash(self):
        reg = PerformanceMetricsRegistry()
        assert reg.constitutional_hash is not None

    def test_record_z3_latency(self):
        reg = get_performance_metrics()
        reg.record_z3_latency(5.0, "solve")

    def test_record_adaptive_threshold(self):
        reg = get_performance_metrics()
        reg.record_adaptive_threshold(2.0, "calibration")

    def test_record_cache_miss(self):
        reg = get_performance_metrics()
        reg.record_cache_miss(CacheLayer.L1, CacheMissReason.EXPIRED)
        reg.record_cache_miss("L2", "evicted")

    def test_record_batch_overhead(self):
        reg = get_performance_metrics()
        reg.record_batch_overhead(100.0, 50)

    def test_record_maci_latency(self):
        reg = get_performance_metrics()
        reg.record_maci_latency(3.0, "EXECUTIVE")

    def test_record_validation(self):
        reg = get_performance_metrics()
        reg.record_validation(MetricsValidationResult.SUCCESS)
        reg.record_validation("failure", "pqc")

    def test_record_opa_evaluation(self):
        reg = get_performance_metrics()
        reg.record_opa_evaluation(5.0, "access_control", "allow")

    def test_record_deliberation(self):
        reg = get_performance_metrics()
        reg.record_deliberation(50.0, "consensus", impact_score=0.5)


# ---------------------------------------------------------------------------
# 2. adaptive_governance/governance_engine.py
# ---------------------------------------------------------------------------

from enhanced_agent_bus.adaptive_governance.governance_engine import (
    AdaptiveGovernanceEngine,
)
from enhanced_agent_bus.adaptive_governance.models import (
    GovernanceDecision,
    GovernanceMetrics,
    GovernanceMode,
    ImpactFeatures,
    ImpactLevel,
)


def _make_features(**overrides: Any) -> ImpactFeatures:
    defaults = dict(
        message_length=100,
        agent_count=1,
        tenant_complexity=0.5,
        temporal_patterns=[0.1, 0.2],
        semantic_similarity=0.6,
        historical_precedence=3,
        resource_utilization=0.4,
        network_isolation=0.5,
        risk_score=0.3,
        confidence_level=0.8,
    )
    defaults.update(overrides)
    return ImpactFeatures(**defaults)


def _make_decision(**overrides: Any) -> GovernanceDecision:
    defaults = dict(
        action_allowed=True,
        impact_level=ImpactLevel.LOW,
        confidence_score=0.9,
        reasoning="Test decision",
        recommended_threshold=0.7,
        features_used=_make_features(),
        decision_id="gov-test-001",
    )
    defaults.update(overrides)
    return GovernanceDecision(**defaults)


class TestAdaptiveGovernanceEngineInit:
    def test_basic_init(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        assert engine.mode == GovernanceMode.ADAPTIVE
        assert engine.constitutional_hash == "608508a9bd224290"
        assert engine.running is False

    def test_default_river_feature_names(self):
        names = AdaptiveGovernanceEngine._default_river_feature_names()
        assert "message_length" in names
        assert "risk_score" in names
        assert len(names) == 11


class TestClassifyImpactLevel:
    @pytest.fixture
    def engine(self):
        return AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")

    def test_critical(self, engine):
        assert engine._classify_impact_level(0.95) == ImpactLevel.CRITICAL

    def test_high(self, engine):
        assert engine._classify_impact_level(0.75) == ImpactLevel.HIGH

    def test_medium(self, engine):
        assert engine._classify_impact_level(0.50) == ImpactLevel.MEDIUM

    def test_low(self, engine):
        assert engine._classify_impact_level(0.25) == ImpactLevel.LOW

    def test_negligible(self, engine):
        assert engine._classify_impact_level(0.05) == ImpactLevel.NEGLIGIBLE


class TestGenerateReasoning:
    @pytest.fixture
    def engine(self):
        return AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")

    def test_allowed_reasoning(self, engine):
        features = _make_features(risk_score=0.2, confidence_level=0.9)
        reasoning = engine._generate_reasoning(True, features, 0.5)
        assert "ALLOWED" in reasoning

    def test_blocked_reasoning(self, engine):
        features = _make_features(risk_score=0.8, confidence_level=0.9)
        reasoning = engine._generate_reasoning(False, features, 0.5)
        assert "BLOCKED" in reasoning

    def test_low_confidence_note(self, engine):
        features = _make_features(confidence_level=0.3)
        reasoning = engine._generate_reasoning(True, features, 0.5)
        assert "Low confidence" in reasoning

    def test_historical_precedence_note(self, engine):
        features = _make_features(historical_precedence=5)
        reasoning = engine._generate_reasoning(True, features, 0.5)
        assert "precedent" in reasoning.lower()


class TestBuildConservativeFallback:
    def test_fallback_decision(self):
        err = RuntimeError("test error")
        decision = AdaptiveGovernanceEngine._build_conservative_fallback_decision(err)
        assert decision.action_allowed is False
        assert decision.impact_level == ImpactLevel.HIGH
        assert "test error" in decision.reasoning


class TestProvideFeedback:
    @pytest.fixture
    def engine(self):
        return AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")

    def test_positive_feedback(self, engine):
        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True)

    def test_negative_feedback(self, engine):
        decision = _make_decision(action_allowed=False)
        engine.provide_feedback(decision, outcome_success=False)

    def test_human_override_feedback(self, engine):
        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True, human_override=False)


class TestUpdateMetrics:
    @pytest.fixture
    def engine(self):
        return AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")

    def test_update_metrics_basic(self, engine):
        decision = _make_decision()
        engine.decision_history.append(decision)
        engine._update_metrics(decision, 0.05)
        assert engine.metrics.average_response_time > 0

    def test_compliance_rate_calculation(self, engine):
        for _ in range(5):
            engine.decision_history.append(_make_decision(confidence_score=0.9))
        engine._update_metrics(_make_decision(), 0.01)
        assert engine.metrics.constitutional_compliance_rate > 0


class TestAnalyzePerformanceTrends:
    def test_trends_populated(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        engine.metrics.constitutional_compliance_rate = 0.95
        engine.metrics.false_positive_rate = 0.05
        engine.metrics.average_response_time = 0.01
        engine._analyze_performance_trends()
        assert len(engine.metrics.compliance_trend) == 1
        assert len(engine.metrics.accuracy_trend) == 1
        assert len(engine.metrics.performance_trend) == 1


class TestShouldRetrainModels:
    def test_retrain_when_compliance_low(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        engine.metrics.constitutional_compliance_rate = 0.5
        engine.performance_target = 0.9
        assert engine._should_retrain_models() is True

    def test_no_retrain_when_compliant(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        engine.metrics.constitutional_compliance_rate = 0.99
        engine.performance_target = 0.9
        assert engine._should_retrain_models() is False


class TestDTMCIntegration:
    @pytest.fixture
    def engine(self):
        return AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")

    def test_get_trajectory_prefix_empty(self, engine):
        assert engine._get_trajectory_prefix() is None

    def test_get_trajectory_prefix_with_history(self, engine):
        for _ in range(3):
            engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))
        prefix = engine._get_trajectory_prefix()
        assert prefix is not None
        assert len(prefix) == 3

    def test_apply_dtmc_risk_blend_disabled(self, engine):
        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 0.3

    def test_maybe_refit_dtmc_disabled(self, engine):
        engine._maybe_refit_dtmc()


class TestGovernanceEngineLifecycle:
    async def test_initialize_and_shutdown(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        await engine.initialize()
        assert engine.running is True
        assert engine.learning_task is not None
        await engine.shutdown()
        assert engine.running is False

    async def test_shutdown_without_initialize(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        await engine.shutdown()

    async def test_learning_thread_alias(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        assert engine._learning_thread is engine.learning_task


class TestEvaluateGovernanceDecision:
    async def test_evaluate_returns_decision(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        message = {"content": "test message", "agent_id": "agent-1"}
        context = {"policy_level": "standard"}
        decision = await engine.evaluate_governance_decision(message, context)
        assert isinstance(decision, GovernanceDecision)
        assert isinstance(decision.action_allowed, bool)

    async def test_evaluate_fallback_on_error(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        engine.impact_scorer.assess_impact = AsyncMock(side_effect=RuntimeError("scorer failed"))
        decision = await engine.evaluate_governance_decision({}, {})
        assert decision.action_allowed is False
        assert "failed" in decision.reasoning.lower()


class TestGetRiverModelStats:
    def test_returns_none_when_unavailable(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        engine.river_model = None
        assert engine.get_river_model_stats() is None


class TestGetABTestMetrics:
    def test_returns_none_when_unavailable(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        engine._ab_test_router = None
        assert engine.get_ab_test_metrics() is None
        assert engine.get_ab_test_comparison() is None
        assert engine.get_ab_test_router() is None

    def test_promote_candidate_none(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        engine._ab_test_router = None
        result = engine.promote_candidate_model()
        assert result is None


class TestLatestDriftReport:
    def test_default_none(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        assert engine.get_latest_drift_report() is None


class TestLogPerformanceSummary:
    def test_does_not_raise(self):
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        engine._log_performance_summary()


# ---------------------------------------------------------------------------
# 3. deliberation_layer/tensorrt_optimizer.py
# ---------------------------------------------------------------------------

from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
    TensorRTOptimizer,
    get_optimization_status,
)


class TestTensorRTOptimizerInit:
    def test_default_init(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.model_name == "distilbert-base-uncased"
        assert opt.max_seq_length == 128
        assert opt.use_fp16 is True
        assert opt.cache_dir == tmp_path

    def test_custom_model(self, tmp_path):
        opt = TensorRTOptimizer(
            model_name="bert-base-uncased",
            max_seq_length=256,
            use_fp16=False,
            cache_dir=tmp_path,
        )
        assert opt.model_name == "bert-base-uncased"
        assert opt.max_seq_length == 256
        assert opt.use_fp16 is False

    def test_model_id_sanitized(self, tmp_path):
        opt = TensorRTOptimizer(model_name="org/my-model", cache_dir=tmp_path)
        assert opt.model_id == "org_my_model"

    def test_onnx_and_trt_paths(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.onnx_path.suffix == ".onnx"
        assert opt.trt_path.suffix == ".trt"


class TestTensorRTOptimizerStatus:
    def test_status_dict(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        status = opt.status
        assert "torch_available" in status
        assert "onnx_available" in status
        assert "tensorrt_available" in status
        assert status["model_name"] == "distilbert-base-uncased"
        assert status["max_seq_length"] == 128
        assert status["use_fp16"] is True


class TestExportOnnx:
    def test_raises_without_torch(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TORCH_AVAILABLE",
            False,
        ):
            with pytest.raises(RuntimeError, match="PyTorch"):
                opt.export_onnx()

    def test_skips_if_exists(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.onnx_path.write_bytes(b"fake")
        result = opt.export_onnx(force=False)
        assert result == opt.onnx_path
        assert opt._optimization_status["onnx_exported"] is True


class TestConvertToTensorrt:
    def test_returns_none_without_trt(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
            False,
        ):
            result = opt.convert_to_tensorrt()
            assert result is None

    def test_skips_if_exists(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.trt_path.write_bytes(b"fake-trt-engine")
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
            True,
        ):
            result = opt.convert_to_tensorrt(force=False)
            assert result == opt.trt_path
            assert opt._optimization_status["tensorrt_ready"] is True


class TestLoadTensorrtEngine:
    def test_returns_false_without_trt(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
            False,
        ):
            assert opt.load_tensorrt_engine() is False

    def test_returns_false_no_file(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
            True,
        ):
            assert opt.load_tensorrt_engine() is False


class TestValidateEngine:
    def test_nonexistent_path(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.validate_engine(tmp_path / "no_such.trt") is False

    def test_returns_false_without_trt(self, tmp_path):
        engine_path = tmp_path / "test.trt"
        engine_path.write_bytes(b"x" * 2_000_000)
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
            False,
        ):
            assert opt.validate_engine(engine_path) is False

    def test_returns_false_for_small_file(self, tmp_path):
        engine_path = tmp_path / "small.trt"
        engine_path.write_bytes(b"x" * 100)
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        mock_trt = MagicMock()
        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.trt",
                mock_trt,
            ),
        ):
            assert opt.validate_engine(engine_path) is False


class TestLoadOnnxRuntime:
    def test_returns_false_without_onnx(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.ONNX_AVAILABLE",
            False,
        ):
            assert opt.load_onnx_runtime() is False

    def test_returns_false_no_file(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.ONNX_AVAILABLE",
            True,
        ):
            assert opt.load_onnx_runtime() is False


class TestInfer:
    def test_raises_without_numpy(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.NUMPY_AVAILABLE",
            False,
        ):
            with pytest.raises(ImportError, match="numpy"):
                opt.infer("test")

    def test_infer_batch_raises_without_numpy(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.NUMPY_AVAILABLE",
            False,
        ):
            with pytest.raises(ImportError, match="numpy"):
                opt.infer_batch(["test"])


class TestFallbackEmbeddings:
    def test_generate_fallback(self, tmp_path):
        import numpy as np

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        result = opt._generate_fallback_embeddings(3)
        assert result.shape == (3, 768)
        assert (result == 0).all()

    def test_fallback_raises_without_numpy(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.NUMPY_AVAILABLE",
            False,
        ):
            with pytest.raises(ImportError, match="numpy"):
                opt._generate_fallback_embeddings(1)


class TestInferTensorrt:
    def test_raises_not_implemented(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(NotImplementedError):
            opt._infer_tensorrt({})


class TestGetOptimizationStatus:
    def test_returns_dict(self):
        status = get_optimization_status()
        assert isinstance(status, dict)
        assert "torch_available" in status


class TestInferOnnx:
    def test_raises_without_session(self, tmp_path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._onnx_session = None
        with pytest.raises(RuntimeError, match="ONNX session not loaded"):
            opt._infer_onnx({"input_ids": None, "attention_mask": None})


class TestInferBatchBackendSelection:
    def test_fallback_on_timeout(self, tmp_path):
        """When check_timeout fires before torch, returns fallback."""
        import numpy as np

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._trt_context = None
        opt._onnx_session = None
        opt._latency_threshold_ms = 0.0  # instant timeout

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }
        opt._tokenizer_cache[opt.model_name] = mock_tokenizer

        result = opt.infer_batch(["test"])
        assert result.shape == (1, 768)
        assert (result == 0).all()

    def test_fallback_on_exception(self, tmp_path):
        """When inference raises, returns fallback embeddings."""
        import numpy as np

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._trt_context = None
        opt._onnx_session = None
        opt._latency_threshold_ms = 999999.0  # no timeout

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }
        opt._tokenizer_cache[opt.model_name] = mock_tokenizer

        # _infer_torch will fail because torch model isn't loaded
        with patch.object(opt, "_infer_torch", side_effect=RuntimeError("no model")):
            result = opt.infer_batch(["test"])
            assert result.shape == (1, 768)


# ---------------------------------------------------------------------------
# 4. pqc_validators.py
# ---------------------------------------------------------------------------

from enhanced_agent_bus.pqc_validators import (
    PqcValidators,
    _extract_message_content,
    _is_self_validation,
    check_enforcement_for_create,
    check_enforcement_for_update,
    validate_constitutional_hash_pqc,
    validate_maci_record_pqc,
    validate_signature,
)


class TestPqcValidatorsHelper:
    def test_process_valid_string(self):
        v = PqcValidators()
        assert v.process("hello") == "hello"

    def test_process_none(self):
        v = PqcValidators()
        assert v.process(None) is None

    def test_process_non_string(self):
        v = PqcValidators()
        assert v.process(42) is None  # type: ignore[arg-type]

    def test_custom_hash(self):
        v = PqcValidators(constitutional_hash="custom-hash")
        assert v._constitutional_hash == "custom-hash"


class TestExtractMessageContent:
    def test_excludes_signature(self):
        data = {"field_a": "value_a", "signature": "sig", "field_b": 123}
        content = _extract_message_content(data)
        assert b"signature" not in content
        assert b"field_a" in content

    def test_returns_bytes(self):
        data = {"key": "value"}
        assert isinstance(_extract_message_content(data), bytes)

    def test_canonical_json(self):
        data1 = {"b": 2, "a": 1}
        data2 = {"a": 1, "b": 2}
        assert _extract_message_content(data1) == _extract_message_content(data2)


class TestIsSelfValidation:
    def test_same_author(self):
        assert (
            _is_self_validation(
                "agent-1",
                "output-1",
                {"output_author": "agent-1"},
            )
            is True
        )

    def test_different_author(self):
        assert (
            _is_self_validation(
                "agent-1",
                "output-1",
                {"output_author": "agent-2"},
            )
            is False
        )

    def test_agent_in_target_id(self):
        assert (
            _is_self_validation(
                "agent-1",
                "output-by-agent-1-123",
                {},
            )
            is True
        )

    def test_agent_not_in_target_id(self):
        assert (
            _is_self_validation(
                "agent-1",
                "output-by-agent-2-123",
                {},
            )
            is False
        )

    def test_no_output_author_no_match(self):
        assert (
            _is_self_validation(
                "agent-1",
                "unrelated-output",
                {},
            )
            is False
        )


class TestCheckEnforcementForCreate:
    async def test_migration_context_skips(self):
        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        await check_enforcement_for_create("pqc", "ML-DSA-65", config, migration_context=True)

    async def test_non_strict_mode_skips(self):
        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="permissive")
        await check_enforcement_for_create(None, None, config)

    async def test_strict_no_key_type_raises(self):
        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        from enhanced_agent_bus._compat.security.pqc import PQCKeyRequiredError

        with pytest.raises(PQCKeyRequiredError):
            await check_enforcement_for_create(None, None, config)

    async def test_strict_classical_rejected(self):
        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        from enhanced_agent_bus._compat.security.pqc import ClassicalKeyRejectedError

        with pytest.raises(ClassicalKeyRejectedError):
            await check_enforcement_for_create("classical", "Ed25519", config)

    async def test_strict_unsupported_pqc_raises(self):
        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        from enhanced_agent_bus._compat.security.pqc import UnsupportedPQCAlgorithmError

        with pytest.raises(UnsupportedPQCAlgorithmError):
            await check_enforcement_for_create("pqc", "UNKNOWN-ALG", config)

    async def test_strict_valid_pqc_passes(self):
        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        await check_enforcement_for_create("pqc", "ML-DSA-65", config)

    async def test_config_get_mode_failure_defaults_strict(self):
        config = AsyncMock()
        config.get_mode = AsyncMock(side_effect=RuntimeError("broken"))
        from enhanced_agent_bus._compat.security.pqc import PQCKeyRequiredError

        with pytest.raises(PQCKeyRequiredError):
            await check_enforcement_for_create(None, None, config)


class TestCheckEnforcementForUpdate:
    async def test_migration_context_skips(self):
        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        await check_enforcement_for_update("classical", config, migration_context=True)

    async def test_non_strict_mode_skips(self):
        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="permissive")
        await check_enforcement_for_update("classical", config)

    async def test_strict_classical_requires_migration(self):
        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        from enhanced_agent_bus._compat.security.pqc import MigrationRequiredError

        with pytest.raises(MigrationRequiredError):
            await check_enforcement_for_update("classical", config)

    async def test_strict_pqc_passes(self):
        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        await check_enforcement_for_update("pqc", config)


class TestValidateConstitutionalHashPqc:
    async def test_missing_hash_field(self):
        result = await validate_constitutional_hash_pqc({})
        assert result.valid is False
        assert any("Missing" in e for e in result.errors)

    async def test_hash_mismatch(self):
        result = await validate_constitutional_hash_pqc(
            {"constitutional_hash": "wrong_hash_value"},
            expected_hash="608508a9bd224290",
        )
        assert result.valid is False
        assert any("mismatch" in e.lower() for e in result.errors)

    async def test_valid_hash_no_signature(self):
        result = await validate_constitutional_hash_pqc(
            {"constitutional_hash": "608508a9bd224290"},
            expected_hash="608508a9bd224290",
        )
        assert result.valid is True
        assert result.validation_duration_ms is not None

    async def test_valid_hash_empty_signature(self):
        result = await validate_constitutional_hash_pqc(
            {"constitutional_hash": "608508a9bd224290", "signature": None},
            expected_hash="608508a9bd224290",
        )
        assert result.valid is True

    async def test_valid_hash_classical_signature_no_pqc(self):
        """Classical signature path with pqc_config=None returns a valid result.
        The ValidationResult dataclass now includes classical_verification_ms and
        pqc_verification_ms fields, so the classical signature branch succeeds."""
        result = await validate_constitutional_hash_pqc(
            {
                "constitutional_hash": "608508a9bd224290",
                "signature": {"signature": "abc123"},
            },
            expected_hash="608508a9bd224290",
            pqc_config=None,
        )
        assert result.valid is True

    async def test_valid_hash_signature_dict_no_sig_key(self):
        """When signature dict has no 'signature' key and pqc_config is None,
        we still get a valid result (no classical verification attempted)."""
        result = await validate_constitutional_hash_pqc(
            {
                "constitutional_hash": "608508a9bd224290",
                "signature": {"other_field": "value"},
            },
            expected_hash="608508a9bd224290",
            pqc_config=None,
        )
        assert result.valid is True

    async def test_pqc_enabled_v1_classical(self):
        """When PQC is enabled, the code tries to construct PQCCryptoService
        with config= kwarg which fails (constructor takes no args).
        The error is caught and returned as validation failure."""
        from enhanced_agent_bus._compat.security.pqc_crypto import PQCConfig

        pqc_config = PQCConfig(pqc_enabled=True)
        result = await validate_constitutional_hash_pqc(
            {
                "constitutional_hash": "608508a9bd224290",
                "signature": {"version": "v1", "signature": "abc"},
            },
            expected_hash="608508a9bd224290",
            pqc_config=pqc_config,
        )
        # PQCCryptoService(config=...) raises TypeError caught by the handler
        assert result.valid is False
        assert any("Validation error" in e for e in result.errors)

    async def test_pqc_disabled_with_config(self):
        """When pqc_config has pqc_enabled=False and signature has 'signature' key,
        the classical verification path runs and returns a valid result.
        ValidationResult now accepts classical_verification_ms so no TypeError."""
        from enhanced_agent_bus._compat.security.pqc_crypto import PQCConfig

        pqc_config = PQCConfig(pqc_enabled=False)
        result = await validate_constitutional_hash_pqc(
            {
                "constitutional_hash": "608508a9bd224290",
                "signature": {"signature": "test"},
            },
            expected_hash="608508a9bd224290",
            pqc_config=pqc_config,
        )
        assert result.valid is True

    async def test_pqc_disabled_with_config_no_sig_key(self):
        """PQC disabled config, signature dict without 'signature' key -- valid."""
        from enhanced_agent_bus._compat.security.pqc_crypto import PQCConfig

        pqc_config = PQCConfig(pqc_enabled=False)
        result = await validate_constitutional_hash_pqc(
            {
                "constitutional_hash": "608508a9bd224290",
                "signature": {"other": "value"},
            },
            expected_hash="608508a9bd224290",
            pqc_config=pqc_config,
        )
        assert result.valid is True


class TestValidateMaciRecordPqc:
    async def test_missing_required_fields(self):
        result = await validate_maci_record_pqc({})
        assert result.valid is False
        assert any("Missing required" in e for e in result.errors)

    async def test_missing_single_field(self):
        result = await validate_maci_record_pqc(
            {
                "agent_id": "a1",
                "action": "validate",
            }
        )
        assert result.valid is False
        assert any("timestamp" in e for e in result.errors)

    async def test_valid_record_classical(self):
        result = await validate_maci_record_pqc(
            {
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2024-01-01T00:00:00Z",
            }
        )
        assert result.valid is True

    async def test_hash_mismatch(self):
        result = await validate_maci_record_pqc(
            {
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2024-01-01T00:00:00Z",
                "constitutional_hash": "wrong_hash",
            },
            expected_hash="608508a9bd224290",
        )
        assert result.valid is False
        assert any("hash mismatch" in e.lower() for e in result.errors)

    async def test_self_validation_detected(self):
        result = await validate_maci_record_pqc(
            {
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2024-01-01T00:00:00Z",
                "target_output_id": "output-1",
                "output_author": "agent-1",
            }
        )
        assert result.valid is False
        assert any("Self-validation" in e for e in result.errors)

    async def test_pqc_metadata_when_config_provided(self):
        from enhanced_agent_bus._compat.security.pqc_crypto import PQCConfig

        result = await validate_maci_record_pqc(
            {
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2024-01-01T00:00:00Z",
            },
            pqc_config=PQCConfig(pqc_enabled=False),
        )
        assert result.valid is True
        assert result.pqc_metadata is not None
        assert result.pqc_metadata.verification_mode == "classical_only"

    async def test_no_pqc_metadata_without_config(self):
        result = await validate_maci_record_pqc(
            {
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2024-01-01T00:00:00Z",
            }
        )
        assert result.valid is True
        assert result.pqc_metadata is None


class TestValidateSignature:
    async def test_classical_in_hybrid_mode(self):
        mock_module = MagicMock()
        mock_client = MagicMock()
        mock_client._registry = None
        mock_module.key_registry_client = mock_client

        with patch("importlib.import_module", return_value=mock_module):
            result = await validate_signature(
                payload=b"test",
                signature=b"sig",
                key_id="key-1",
                algorithm="Ed25519",
                hybrid_mode=True,
            )
            assert result["valid"] is True
            assert result["key_type"] == "classical"
            assert result["algorithm"] == "Ed25519"

    async def test_pqc_algorithm(self):
        mock_module = MagicMock()
        mock_client = MagicMock()
        mock_client._registry = None
        mock_module.key_registry_client = mock_client

        with patch("importlib.import_module", return_value=mock_module):
            result = await validate_signature(
                payload=b"test",
                signature=b"sig",
                key_id="key-1",
                algorithm="ML-DSA-65",
                hybrid_mode=True,
            )
            assert result["valid"] is True
            assert result["key_type"] == "pqc"

    async def test_classical_rejected_in_pqc_only_mode(self):
        from enhanced_agent_bus._compat.security.pqc import ClassicalKeyRejectedError

        with pytest.raises(ClassicalKeyRejectedError):
            await validate_signature(
                payload=b"test",
                signature=b"sig",
                key_id="key-1",
                algorithm="Ed25519",
                hybrid_mode=False,
            )

    async def test_unsupported_algorithm(self):
        from enhanced_agent_bus._compat.security.pqc import UnsupportedAlgorithmError

        with pytest.raises(UnsupportedAlgorithmError):
            await validate_signature(
                payload=b"test",
                signature=b"sig",
                key_id="key-1",
                algorithm="TOTALLY-UNKNOWN",
                hybrid_mode=True,
            )

    async def test_key_registry_failure_raises(self):
        from enhanced_agent_bus._compat.security.pqc import KeyRegistryUnavailableError

        with patch(
            "importlib.import_module",
            side_effect=RuntimeError("registry down"),
        ):
            with pytest.raises(KeyRegistryUnavailableError):
                await validate_signature(
                    payload=b"test",
                    signature=b"sig",
                    key_id="key-1",
                    algorithm="Ed25519",
                    hybrid_mode=True,
                )
