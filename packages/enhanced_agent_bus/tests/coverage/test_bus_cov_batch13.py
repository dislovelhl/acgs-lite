"""Coverage batch 13 — governance_engine, tensorrt_optimizer,
pqc_validators, message_processor.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. governance_engine — 147 missing lines, 72.1% covered
# ---------------------------------------------------------------------------


class TestAdaptiveGovernanceEngineInit:
    def test_creates_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        assert engine.constitutional_hash == "608508a9bd224290"
        assert engine.running is False

    def test_creates_engine_with_config(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration.from_environment()
        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290", config=config)
        assert engine.config is config


class TestClassifyImpactLevel:
    def test_critical(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        assert engine._classify_impact_level(0.95) == ImpactLevel.CRITICAL

    def test_high(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        assert engine._classify_impact_level(0.75) == ImpactLevel.HIGH

    def test_medium(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        assert engine._classify_impact_level(0.45) == ImpactLevel.MEDIUM

    def test_low(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        assert engine._classify_impact_level(0.25) == ImpactLevel.LOW

    def test_negligible(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        assert engine._classify_impact_level(0.05) == ImpactLevel.NEGLIGIBLE


class TestGenerateReasoning:
    def test_allowed_reasoning(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        features = ImpactFeatures(
            message_length=100,
            agent_count=2,
            tenant_complexity=1,
            temporal_patterns=[],
            semantic_similarity=0.5,
            historical_precedence=3,
            resource_utilization=0.3,
            network_isolation=0.8,
            risk_score=0.2,
            confidence_level=0.9,
        )
        reasoning = engine._generate_reasoning(True, features, 0.5)
        assert "ALLOWED" in reasoning
        assert "precedents" in reasoning.lower()

    def test_blocked_low_confidence(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        features = ImpactFeatures(
            message_length=100,
            agent_count=2,
            tenant_complexity=1,
            temporal_patterns=[],
            semantic_similarity=0.5,
            historical_precedence=0,
            resource_utilization=0.3,
            network_isolation=0.8,
            risk_score=0.8,
            confidence_level=0.3,
        )
        reasoning = engine._generate_reasoning(False, features, 0.5)
        assert "BLOCKED" in reasoning
        assert "confidence" in reasoning.lower()


class TestBuildConservativeFallback:
    def test_fallback_decision(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        decision = AdaptiveGovernanceEngine._build_conservative_fallback_decision(
            RuntimeError("test error")
        )
        assert decision.action_allowed is False
        assert "test error" in decision.reasoning


class TestGovernanceEngineInitSubsystems:
    def test_initialize_feedback_handler_not_available(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE",
            False,
        ):
            engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
            assert engine._feedback_handler is None

    def test_initialize_drift_detector_not_available(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
            False,
        ):
            engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
            assert engine._drift_detector is None

    def test_default_river_feature_names(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        names = AdaptiveGovernanceEngine._default_river_feature_names()
        assert "message_length" in names
        assert "risk_score" in names
        assert len(names) == 11


class TestGovernanceEngineShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_no_task(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        engine.running = True
        await engine.shutdown()
        assert engine.running is False

    @pytest.mark.asyncio
    async def test_shutdown_with_task(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        engine.running = True

        async def dummy():
            await asyncio.sleep(100)

        engine.learning_task = asyncio.create_task(dummy())
        await engine.shutdown()
        assert engine.running is False
        assert engine.learning_task.cancelled() or engine.learning_task.done()


class TestGovernanceEngineProvideFeedback:
    def _make_decision(self, risk_score=0.3, confidence=0.8, allowed=True, level_name="LOW"):
        from enhanced_agent_bus.adaptive_governance.models import (
            GovernanceDecision,
            ImpactFeatures,
            ImpactLevel,
        )

        features = ImpactFeatures(
            message_length=100,
            agent_count=2,
            tenant_complexity=1,
            temporal_patterns=[1.0, 2.0],
            semantic_similarity=0.5,
            historical_precedence=1,
            resource_utilization=0.3,
            network_isolation=0.8,
            risk_score=risk_score,
            confidence_level=confidence,
        )
        return GovernanceDecision(
            action_allowed=allowed,
            impact_level=ImpactLevel[level_name],
            confidence_score=confidence,
            reasoning="test",
            recommended_threshold=0.5,
            features_used=features,
        )

    def test_provide_feedback_basic(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        decision = self._make_decision()
        engine.provide_feedback(decision, outcome_success=True)

    def test_provide_feedback_with_human_override(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        decision = self._make_decision()
        engine.provide_feedback(decision, outcome_success=False, human_override=False)

    def test_provide_feedback_unsuccessful(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        decision = self._make_decision(risk_score=0.9, allowed=False, level_name="HIGH")
        engine.provide_feedback(decision, outcome_success=False)


class TestGovernanceEngineDTMC:
    def test_apply_dtmc_risk_blend_disabled(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        features = ImpactFeatures(
            message_length=100,
            agent_count=2,
            tenant_complexity=1,
            temporal_patterns=[],
            semantic_similarity=0.5,
            historical_precedence=1,
            resource_utilization=0.3,
            network_isolation=0.8,
            risk_score=0.3,
            confidence_level=0.8,
        )
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 0.3

    def test_apply_dtmc_escalation_disabled(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        from enhanced_agent_bus.adaptive_governance.models import (
            GovernanceDecision,
            ImpactFeatures,
            ImpactLevel,
        )

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        features = ImpactFeatures(
            message_length=100,
            agent_count=2,
            tenant_complexity=1,
            temporal_patterns=[],
            semantic_similarity=0.5,
            historical_precedence=1,
            resource_utilization=0.3,
            network_isolation=0.8,
            risk_score=0.3,
            confidence_level=0.8,
        )
        decision = GovernanceDecision(
            action_allowed=True,
            impact_level=ImpactLevel.LOW,
            confidence_score=0.8,
            reasoning="test",
            recommended_threshold=0.5,
            features_used=features,
        )
        result = engine._apply_dtmc_escalation(decision)
        assert result.impact_level == ImpactLevel.LOW

    def test_learning_thread_alias(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        assert engine._learning_thread is None


class TestGovernanceEngineABTest:
    def test_apply_ab_test_routing_no_router(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        from enhanced_agent_bus.adaptive_governance.models import (
            GovernanceDecision,
            ImpactFeatures,
            ImpactLevel,
        )

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        features = ImpactFeatures(
            message_length=100,
            agent_count=2,
            tenant_complexity=1,
            temporal_patterns=[],
            semantic_similarity=0.5,
            historical_precedence=1,
            resource_utilization=0.3,
            network_isolation=0.8,
            risk_score=0.3,
            confidence_level=0.8,
        )
        decision = GovernanceDecision(
            action_allowed=True,
            impact_level=ImpactLevel.LOW,
            confidence_score=0.8,
            reasoning="test",
            recommended_threshold=0.5,
            features_used=features,
        )
        result = engine._apply_ab_test_routing(decision, features, time.time())
        assert result is decision


class TestGovernanceEngineBuildDecision:
    def test_build_decision_for_features(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        features = ImpactFeatures(
            message_length=100,
            agent_count=2,
            tenant_complexity=1,
            temporal_patterns=[],
            semantic_similarity=0.5,
            historical_precedence=1,
            resource_utilization=0.3,
            network_isolation=0.8,
            risk_score=0.2,
            confidence_level=0.9,
        )
        decision = engine._build_decision_for_features(features, "test-id-1")
        assert decision.decision_id == "test-id-1"
        assert decision.features_used is features


class TestGovernanceEngineInitialize:
    @pytest.mark.asyncio
    async def test_initialize_and_shutdown(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        engine = AdaptiveGovernanceEngine(constitutional_hash="608508a9bd224290")
        await engine.initialize()
        assert engine.running is True
        assert engine.learning_task is not None
        await engine.shutdown()
        assert engine.running is False


# ---------------------------------------------------------------------------
# 2. tensorrt_optimizer — 141 missing lines, 58.5% covered
# ---------------------------------------------------------------------------


class TestTensorRTOptimizerInit:
    def test_basic_init(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        opt = TensorRTOptimizer(
            model_name="test-model",
            max_seq_length=64,
            use_fp16=False,
            cache_dir=tmp_path,
        )
        assert opt.model_name == "test-model"
        assert opt.max_seq_length == 64
        assert opt.use_fp16 is False
        assert opt.model_id == "test_model"

    def test_default_cache_dir(self):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        opt = TensorRTOptimizer()
        assert opt.cache_dir.exists()

    def test_status_property(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        status = opt.status
        assert "model_name" in status
        assert "max_seq_length" in status
        assert "use_fp16" in status
        assert "active_backend" in status


class TestTensorRTOptimizerExport:
    def test_export_onnx_existing_path(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.onnx_path.write_bytes(b"fake onnx")
        result = opt.export_onnx(force=False)
        assert result == opt.onnx_path
        assert opt._optimization_status["onnx_exported"] is True

    def test_export_onnx_no_torch(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TORCH_AVAILABLE", False
        ):
            opt = TensorRTOptimizer(cache_dir=tmp_path)
            with pytest.raises(RuntimeError, match="PyTorch required"):
                opt.export_onnx(force=True)


class TestTensorRTOptimizerConvert:
    def test_convert_no_tensorrt(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE", False
        ):
            opt = TensorRTOptimizer(cache_dir=tmp_path)
            result = opt.convert_to_tensorrt()
            assert result is None

    def test_convert_existing_path(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.trt_path.write_bytes(b"fake trt")
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE", True
        ):
            result = opt.convert_to_tensorrt(force=False)
            assert result == opt.trt_path


class TestTensorRTOptimizerLoadEngines:
    def test_load_tensorrt_no_trt(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE", False
        ):
            opt = TensorRTOptimizer(cache_dir=tmp_path)
            assert opt.load_tensorrt_engine() is False

    def test_load_tensorrt_no_file(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE", True
        ):
            opt = TensorRTOptimizer(cache_dir=tmp_path)
            assert opt.load_tensorrt_engine() is False

    def test_load_onnx_runtime_no_onnx(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.ONNX_AVAILABLE", False
        ):
            opt = TensorRTOptimizer(cache_dir=tmp_path)
            assert opt.load_onnx_runtime() is False

    def test_load_onnx_runtime_no_file(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        with patch("enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.ONNX_AVAILABLE", True):
            opt = TensorRTOptimizer(cache_dir=tmp_path)
            assert opt.load_onnx_runtime() is False

    def test_validate_engine_no_file(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.validate_engine(tmp_path / "nonexistent.trt") is False

    def test_validate_engine_no_trt(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        engine_path = tmp_path / "test.trt"
        engine_path.write_bytes(b"x" * 2_000_000)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE", False
        ):
            opt = TensorRTOptimizer(cache_dir=tmp_path)
            assert opt.validate_engine(engine_path) is False

    def test_validate_engine_too_small(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        engine_path = tmp_path / "test.trt"
        engine_path.write_bytes(b"small")
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE", True
        ):
            opt = TensorRTOptimizer(cache_dir=tmp_path)
            assert opt.validate_engine(engine_path) is False


class TestTensorRTOptimizerInference:
    def test_infer_no_numpy(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.NUMPY_AVAILABLE", False
        ):
            opt = TensorRTOptimizer(cache_dir=tmp_path)
            with pytest.raises(ImportError, match="numpy"):
                opt.infer("test")

    def test_infer_batch_no_numpy(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.NUMPY_AVAILABLE", False
        ):
            opt = TensorRTOptimizer(cache_dir=tmp_path)
            with pytest.raises(ImportError, match="numpy"):
                opt.infer_batch(["test"])

    def test_fallback_embeddings_no_numpy(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.NUMPY_AVAILABLE", False
        ):
            opt = TensorRTOptimizer(cache_dir=tmp_path)
            with pytest.raises(ImportError, match="numpy"):
                opt._generate_fallback_embeddings(1)

    def test_fallback_embeddings_with_numpy(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        result = opt._generate_fallback_embeddings(2)
        assert result.shape == (2, 768)

    def test_infer_tensorrt_raises(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(NotImplementedError):
            opt._infer_tensorrt({})

    def test_infer_onnx_no_session(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import TensorRTOptimizer

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(RuntimeError, match="ONNX session not loaded"):
            opt._infer_onnx({})


class TestTensorRTModuleFunctions:
    def test_get_optimization_status(self):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            get_optimization_status,
        )

        status = get_optimization_status()
        assert "model_name" in status
        assert "active_backend" in status

    def test_optimize_distilbert_no_torch(self):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import optimize_distilbert

        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TORCH_AVAILABLE", False
        ):
            result = optimize_distilbert()
            assert "onnx_error" in result or "steps_completed" in result

    def test_optimize_distilbert_with_existing_onnx(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
            optimize_distilbert,
        )

        with patch.object(TensorRTOptimizer, "DEFAULT_MODEL_DIR", tmp_path):
            model_id = "distilbert_base_uncased"
            onnx_path = tmp_path / f"{model_id}.onnx"
            onnx_path.write_bytes(b"fake onnx")
            result = optimize_distilbert()
            assert "steps_completed" in result


# ---------------------------------------------------------------------------
# 3. pqc_validators — 122 missing lines, 55.6% covered
# ---------------------------------------------------------------------------


class TestPqcValidatorsHelper:
    def test_process_valid_string(self):
        from enhanced_agent_bus.pqc_validators import PqcValidators

        v = PqcValidators()
        assert v.process("test") == "test"

    def test_process_none(self):
        from enhanced_agent_bus.pqc_validators import PqcValidators

        v = PqcValidators()
        assert v.process(None) is None

    def test_process_non_string(self):
        from enhanced_agent_bus.pqc_validators import PqcValidators

        v = PqcValidators()
        assert v.process(123) is None  # type: ignore[arg-type]


class TestExtractMessageContent:
    def test_extract_content(self):
        from enhanced_agent_bus.pqc_validators import _extract_message_content

        data = {"field1": "value1", "field2": 42, "signature": "should-be-excluded"}
        content = _extract_message_content(data)
        assert isinstance(content, bytes)
        assert b"signature" not in content
        assert b"field1" in content


class TestIsSelfValidation:
    def test_same_agent_and_author(self):
        from enhanced_agent_bus.pqc_validators import _is_self_validation

        assert _is_self_validation("agent-1", "output-1", {"output_author": "agent-1"}) is True

    def test_different_agent_and_author(self):
        from enhanced_agent_bus.pqc_validators import _is_self_validation

        assert _is_self_validation("agent-1", "output-1", {"output_author": "agent-2"}) is False

    def test_agent_id_in_target(self):
        from enhanced_agent_bus.pqc_validators import _is_self_validation

        assert _is_self_validation("agent-1", "output-from-agent-1-abc", {}) is True

    def test_no_self_validation(self):
        from enhanced_agent_bus.pqc_validators import _is_self_validation

        assert _is_self_validation("agent-1", "output-xyz", {}) is False


class TestCheckEnforcementForCreate:
    @pytest.mark.asyncio
    async def test_migration_context_skips(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        await check_enforcement_for_create(
            key_type=None,
            key_algorithm=None,
            enforcement_config=config,
            migration_context=True,
        )
        config.get_mode.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_strict_mode_skips(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="permissive")
        await check_enforcement_for_create(
            key_type=None,
            key_algorithm=None,
            enforcement_config=config,
        )

    @pytest.mark.asyncio
    async def test_strict_no_key_raises(self):
        from src.core.shared.security.pqc import PQCKeyRequiredError

        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        with pytest.raises(PQCKeyRequiredError):
            await check_enforcement_for_create(
                key_type=None,
                key_algorithm=None,
                enforcement_config=config,
            )

    @pytest.mark.asyncio
    async def test_strict_classical_key_raises(self):
        from src.core.shared.security.pqc import ClassicalKeyRejectedError

        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        with pytest.raises(ClassicalKeyRejectedError):
            await check_enforcement_for_create(
                key_type="classical",
                key_algorithm="ed25519",
                enforcement_config=config,
            )

    @pytest.mark.asyncio
    async def test_strict_pqc_valid_algorithm(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        await check_enforcement_for_create(
            key_type="pqc",
            key_algorithm="ML-DSA-65",
            enforcement_config=config,
        )

    @pytest.mark.asyncio
    async def test_strict_pqc_invalid_algorithm_raises(self):
        from src.core.shared.security.pqc import UnsupportedPQCAlgorithmError

        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        with pytest.raises(UnsupportedPQCAlgorithmError):
            await check_enforcement_for_create(
                key_type="pqc",
                key_algorithm="INVALID-ALG",
                enforcement_config=config,
            )


class TestCheckEnforcementForUpdate:
    @pytest.mark.asyncio
    async def test_migration_context_skips(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_update

        config = AsyncMock()
        await check_enforcement_for_update(
            existing_key_type="classical",
            enforcement_config=config,
            migration_context=True,
        )
        config.get_mode.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_strict_mode_skips(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_update

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="permissive")
        await check_enforcement_for_update(
            existing_key_type="classical",
            enforcement_config=config,
        )

    @pytest.mark.asyncio
    async def test_strict_classical_raises(self):
        from src.core.shared.security.pqc import MigrationRequiredError

        from enhanced_agent_bus.pqc_validators import check_enforcement_for_update

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        with pytest.raises(MigrationRequiredError):
            await check_enforcement_for_update(
                existing_key_type="classical",
                enforcement_config=config,
            )

    @pytest.mark.asyncio
    async def test_strict_pqc_key_passes(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_update

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        await check_enforcement_for_update(
            existing_key_type="pqc",
            enforcement_config=config,
        )


class TestGetModeSafe:
    @pytest.mark.asyncio
    async def test_get_mode_safe_error_returns_strict(self):
        from enhanced_agent_bus.pqc_validators import _get_mode_safe

        config = AsyncMock()
        config.get_mode = AsyncMock(side_effect=RuntimeError("fail"))
        result = await _get_mode_safe(config)
        assert result == "strict"


class TestValidateConstitutionalHashPqc:
    @pytest.mark.asyncio
    async def test_missing_hash(self):
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        result = await validate_constitutional_hash_pqc(data={})
        assert result.valid is False
        assert any("Missing" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_mismatched_hash(self):
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        result = await validate_constitutional_hash_pqc(
            data={"constitutional_hash": "wrong_hash_value"}
        )
        assert result.valid is False
        assert any("mismatch" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_valid_hash_no_signature(self):
        from enhanced_agent_bus.pqc_validators import (
            CONSTITUTIONAL_HASH,
            validate_constitutional_hash_pqc,
        )

        result = await validate_constitutional_hash_pqc(
            data={"constitutional_hash": CONSTITUTIONAL_HASH},
            expected_hash=CONSTITUTIONAL_HASH,
        )
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_valid_hash_non_dict_signature(self):
        """When signature is truthy but not a dict, we get empty dict for signature_data."""
        from enhanced_agent_bus.pqc_validators import (
            CONSTITUTIONAL_HASH,
            validate_constitutional_hash_pqc,
        )

        result = await validate_constitutional_hash_pqc(
            data={
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "signature": "string-sig",
            },
            expected_hash=CONSTITUTIONAL_HASH,
            pqc_config=None,
        )
        assert result.valid is True


class TestValidateMaciRecordPqc:
    @pytest.mark.asyncio
    async def test_missing_required_fields(self):
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        result = await validate_maci_record_pqc(record={})
        assert result.valid is False
        assert any("Missing required MACI field" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_valid_record_no_pqc(self):
        from enhanced_agent_bus.pqc_validators import (
            CONSTITUTIONAL_HASH,
            validate_maci_record_pqc,
        )

        result = await validate_maci_record_pqc(
            record={
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2024-01-01T00:00:00Z",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_self_validation_detected(self):
        from enhanced_agent_bus.pqc_validators import (
            CONSTITUTIONAL_HASH,
            validate_maci_record_pqc,
        )

        result = await validate_maci_record_pqc(
            record={
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2024-01-01T00:00:00Z",
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "target_output_id": "output-123",
                "output_author": "agent-1",
            },
        )
        assert result.valid is False
        assert any("Self-validation" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_hash_mismatch(self):
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        result = await validate_maci_record_pqc(
            record={
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2024-01-01T00:00:00Z",
                "constitutional_hash": "wrong_hash",
            },
        )
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_valid_record_with_pqc_config_disabled(self):
        from enhanced_agent_bus.pqc_validators import (
            CONSTITUTIONAL_HASH,
            PQCConfig,
            validate_maci_record_pqc,
        )

        config = PQCConfig(pqc_enabled=False)
        result = await validate_maci_record_pqc(
            record={
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2024-01-01T00:00:00Z",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
            pqc_config=config,
        )
        assert result.valid is True
        assert result.pqc_metadata is not None
        assert result.pqc_metadata.pqc_enabled is False

    @pytest.mark.asyncio
    async def test_missing_single_field(self):
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        result = await validate_maci_record_pqc(
            record={
                "agent_id": "agent-1",
                "action": "validate",
                # missing timestamp
            },
        )
        assert result.valid is False
        assert any("timestamp" in e for e in result.errors)


# ---------------------------------------------------------------------------
# 4. message_processor — 121 missing lines, 74.7% covered
# ---------------------------------------------------------------------------


class TestMessageProcessorInit:
    def test_isolated_mode(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc._isolated_mode is True
        assert proc._opa_client is None

    def test_invalid_cache_hash_mode(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            MessageProcessor(isolated_mode=True, cache_hash_mode="invalid")


class TestMessageProcessorAutoSelectStrategy:
    def test_isolated_returns_python(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        strategy = proc._auto_select_strategy()
        assert strategy is not None


class TestMessageProcessorRequiresIndependentValidation:
    def test_high_impact_requires(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
            independent_validator_threshold=0.5,
        )
        msg = AgentMessage(
            content="test",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.QUERY,
            priority=Priority.MEDIUM,
        )
        msg.impact_score = 0.9
        assert proc._requires_independent_validation(msg) is True

    def test_constitutional_type_requires(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
        )
        msg = AgentMessage(
            content="test",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.CONSTITUTIONAL_VALIDATION,
            priority=Priority.MEDIUM,
        )
        assert proc._requires_independent_validation(msg) is True

    def test_low_impact_not_required(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
            independent_validator_threshold=0.8,
        )
        msg = AgentMessage(
            content="test",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.QUERY,
            priority=Priority.LOW,
        )
        msg.impact_score = 0.1
        assert proc._requires_independent_validation(msg) is False

    def test_none_impact_score(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
            independent_validator_threshold=0.8,
        )
        msg = AgentMessage(
            content="test",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.QUERY,
            priority=Priority.LOW,
        )
        msg.impact_score = None
        assert proc._requires_independent_validation(msg) is False


class TestEnforceIndependentValidatorGate:
    def test_gate_disabled(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True, require_independent_validator=False)
        msg = AgentMessage(
            content="test",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.QUERY,
            priority=Priority.MEDIUM,
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is None

    def test_gate_missing_validator(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
            independent_validator_threshold=0.0,
        )
        msg = AgentMessage(
            content="test",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.GOVERNANCE_REQUEST,
            priority=Priority.HIGH,
            metadata={},
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert result.is_valid is False

    def test_gate_self_validation_rejected(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
            independent_validator_threshold=0.0,
        )
        msg = AgentMessage(
            content="test",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.GOVERNANCE_REQUEST,
            priority=Priority.HIGH,
            metadata={"validated_by_agent": "agent-1"},
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert result.is_valid is False
        assert "must not be the originating agent" in result.errors[0]

    def test_gate_invalid_stage(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
            independent_validator_threshold=0.0,
        )
        msg = AgentMessage(
            content="test",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.GOVERNANCE_REQUEST,
            priority=Priority.HIGH,
            metadata={"validated_by_agent": "agent-2", "validation_stage": "wrong_stage"},
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert result.is_valid is False

    def test_gate_valid_validator(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(
            isolated_mode=True,
            require_independent_validator=True,
            independent_validator_threshold=0.0,
        )
        msg = AgentMessage(
            content="test",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.GOVERNANCE_REQUEST,
            priority=Priority.HIGH,
            metadata={"validated_by_agent": "agent-2", "validation_stage": "independent"},
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is None


class TestMessageProcessorProcess:
    @pytest.mark.asyncio
    async def test_process_basic(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            content="Hello world test message for processing.",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.QUERY,
            priority=Priority.MEDIUM,
        )
        result = await proc.process(msg, max_retries=1)
        assert hasattr(result, "is_valid")

    @pytest.mark.asyncio
    async def test_process_retries_on_failure(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            content="test",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.QUERY,
            priority=Priority.MEDIUM,
        )
        call_count = 0

        async def failing_process(m):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("transient error")

        proc._do_process = failing_process
        result = await proc.process(msg, max_retries=2)
        assert result.is_valid is False
        assert call_count == 2
        assert "retries" in result.errors[0].lower()


class TestMessageProcessorRecordWorkflowEvent:
    def test_no_collector(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        proc._agent_workflow_metrics = None
        msg = AgentMessage(
            content="test",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.QUERY,
            priority=Priority.MEDIUM,
        )
        proc._record_agent_workflow_event(event_type="test", msg=msg, reason="testing")

    def test_collector_error(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        mock_collector = MagicMock()
        mock_collector.record_event.side_effect = RuntimeError("fail")
        proc._agent_workflow_metrics = mock_collector
        msg = AgentMessage(
            content="test",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.QUERY,
            priority=Priority.MEDIUM,
        )
        proc._record_agent_workflow_event(event_type="test", msg=msg, reason="testing")


class TestMessageProcessorMemoryProfiling:
    def test_setup_memory_profiling_context(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            content="test",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.QUERY,
            priority=Priority.MEDIUM,
        )
        ctx = proc._setup_memory_profiling_context(msg)
        assert ctx is not None


class TestMessageProcessorComputeCacheKey:
    def test_compute_cache_key(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        msg = AgentMessage(
            content="test content",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.QUERY,
            priority=Priority.MEDIUM,
        )
        key = proc._compute_cache_key(msg)
        assert isinstance(key, str)
        assert len(key) > 0

    def test_cache_keys_differ_for_different_content(self):
        from enhanced_agent_bus.message_processor import MessageProcessor
        from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

        proc = MessageProcessor(isolated_mode=True)
        msg1 = AgentMessage(
            content="content A",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.QUERY,
            priority=Priority.MEDIUM,
        )
        msg2 = AgentMessage(
            content="content B",
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.QUERY,
            priority=Priority.MEDIUM,
        )
        key1 = proc._compute_cache_key(msg1)
        key2 = proc._compute_cache_key(msg2)
        assert key1 != key2
