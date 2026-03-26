"""
Coverage tests for:
  1. enhanced_agent_bus/security_integration.py
  2. enhanced_agent_bus/data_flywheel/config.py
  3. enhanced_agent_bus/middlewares/batch/circuit_breaker.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Stub the drift_detector module so security_integration can import
# ---------------------------------------------------------------------------


class _DriftType(str, Enum):
    IMPACT = "impact"
    DECISION = "decision"
    CONSENSUS = "consensus"


@dataclass(frozen=True)
class _DriftAlert:
    drift_type: _DriftType = _DriftType.IMPACT
    severity: str = "medium"
    description: str = "test drift"
    agent_id: str = "agent-1"
    tenant_id: str = "default"


@dataclass
class _DriftDetectorConfig:
    impact_threshold: float = 0.8
    decision_threshold: float = 0.8
    consensus_threshold: float = 0.8
    window_size: int = 100


class _DriftDetector:
    def __init__(self, config: _DriftDetectorConfig | None = None):
        self._config = config or _DriftDetectorConfig()
        self._observations: list[dict] = []
        self._alerts: list[_DriftAlert] = []

    def record_observation(self, **kwargs: Any) -> None:
        self._observations.append(kwargs)

    def check_all(self, agent_id: str, tenant_id: str) -> list[_DriftAlert]:
        return list(self._alerts)

    def get_stats(self) -> dict:
        return {"observations": len(self._observations)}


# Create and inject the stub module — save originals so we can restore them
_orig_drift = sys.modules.get("enhanced_agent_bus.drift_detector")
_orig_payload = sys.modules.get("enhanced_agent_bus.payload_integrity")

_drift_mod = ModuleType("enhanced_agent_bus.drift_detector")
_drift_mod.DriftAlert = _DriftAlert  # type: ignore[attr-defined]
_drift_mod.DriftDetector = _DriftDetector  # type: ignore[attr-defined]
_drift_mod.DriftDetectorConfig = _DriftDetectorConfig  # type: ignore[attr-defined]
_drift_mod.DriftType = _DriftType  # type: ignore[attr-defined]
sys.modules["enhanced_agent_bus.drift_detector"] = _drift_mod

# Also stub payload_integrity so we can test it
_payload_mod = ModuleType("enhanced_agent_bus.payload_integrity")


def _verify_payload(payload: dict, hmac_value: str, *, key: bytes) -> bool:
    return hmac_value == "valid-hmac"


_payload_mod.verify_payload = _verify_payload  # type: ignore[attr-defined]
sys.modules["enhanced_agent_bus.payload_integrity"] = _payload_mod


@pytest.fixture(autouse=True, scope="session")
def _restore_stubbed_modules():
    """Restore real modules after all tests in this file finish."""
    yield
    # Restore payload_integrity to the real module (or remove stub)
    if _orig_payload is not None:
        sys.modules["enhanced_agent_bus.payload_integrity"] = _orig_payload
    else:
        sys.modules.pop("enhanced_agent_bus.payload_integrity", None)
    if _orig_drift is not None:
        sys.modules["enhanced_agent_bus.drift_detector"] = _orig_drift
    else:
        sys.modules.pop("enhanced_agent_bus.drift_detector", None)


# ---------------------------------------------------------------------------
# Now import the modules under test
# ---------------------------------------------------------------------------
from enhanced_agent_bus.batch_models import (
    BatchRequestItem,
    BatchResponse,
    BatchResponseItem,
)
from enhanced_agent_bus.circuit_breaker.batch import CircuitBreaker, CircuitBreakerConfig
from enhanced_agent_bus.circuit_breaker.enums import CircuitState
from enhanced_agent_bus.middlewares.batch.circuit_breaker import (
    BATCH_CIRCUIT_BREAKER_ERRORS,
    BatchCircuitBreakerMiddleware,
)
from enhanced_agent_bus.middlewares.batch.context import BatchPipelineContext
from enhanced_agent_bus.middlewares.batch.exceptions import BatchProcessingException
from enhanced_agent_bus.models import AgentMessage
from enhanced_agent_bus.pipeline.middleware import MiddlewareConfig
from enhanced_agent_bus.security_integration import (
    SecurityGate,
    SecurityGateResult,
    _constant_time_compare,
)

# Remove the payload_integrity stub from sys.modules immediately after import
# so subsequent test files can import the real module.
# security_integration already resolved its reference — the stub stays in its
# module-level namespace but won't block other importers.
sys.modules.pop("enhanced_agent_bus.payload_integrity", None)
# ---------------------------------------------------------------------------
# Import data_flywheel config (must handle CONSTITUTIONAL_HASH import)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.data_flywheel.config import (
    DEFAULT_FLYWHEEL_CONFIG,
    CandidateModel,
    DataSplitConfig,
    EvaluationConfig,
    ExperimentType,
    FlywheelConfig,
    FlywheelMode,
    ICLConfig,
    ModelSelectionStrategy,
    TrainingConfig,
)
from enhanced_agent_bus.validators import ValidationResult

# ============================================================================
# PART 1: security_integration.py tests
# ============================================================================


class TestConstantTimeCompare:
    """Tests for _constant_time_compare helper."""

    def test_identical_strings_return_true(self):
        assert _constant_time_compare("abc", "abc") is True

    def test_different_strings_return_false(self):
        assert _constant_time_compare("abc", "xyz") is False

    def test_different_lengths_return_false(self):
        assert _constant_time_compare("ab", "abc") is False

    def test_empty_strings_return_true(self):
        assert _constant_time_compare("", "") is True

    def test_single_char_mismatch(self):
        assert _constant_time_compare("a", "b") is False

    def test_single_char_match(self):
        assert _constant_time_compare("x", "x") is True


class TestSecurityGateResult:
    """Tests for SecurityGateResult dataclass."""

    def test_default_values(self):
        result = SecurityGateResult(passed=True)
        assert result.passed is True
        assert result.reason is None
        assert result.drift_alerts == ()
        assert result.payload_valid is True
        assert result.checksum_valid is True
        assert result.evaluated_at is not None

    def test_failed_result_with_reason(self):
        result = SecurityGateResult(passed=False, reason="drift detected")
        assert result.passed is False
        assert result.reason == "drift detected"

    def test_with_drift_alerts(self):
        alert = _DriftAlert(description="test alert")
        result = SecurityGateResult(passed=True, drift_alerts=(alert,))
        assert len(result.drift_alerts) == 1
        assert result.drift_alerts[0].description == "test alert"

    def test_frozen(self):
        result = SecurityGateResult(passed=True)
        with pytest.raises(AttributeError):
            result.passed = False  # type: ignore[misc]


class TestSecurityGate:
    """Tests for SecurityGate class."""

    def _make_msg(self, from_agent: str = "agent-1") -> AgentMessage:
        return AgentMessage(
            message_id="msg-1",
            from_agent=from_agent,
            content={"text": "hello"},
        )

    def test_init_defaults(self):
        gate = SecurityGate()
        assert gate._block_on_drift is False
        assert gate._payload_secret is None
        assert isinstance(gate._drift, _DriftDetector)

    def test_init_with_custom_drift_detector(self):
        detector = _DriftDetector()
        gate = SecurityGate(drift_detector=detector)
        assert gate._drift is detector

    def test_init_with_drift_config(self):
        cfg = _DriftDetectorConfig(impact_threshold=0.5)
        gate = SecurityGate(drift_config=cfg)
        assert gate._drift._config.impact_threshold == 0.5

    def test_register_and_deregister_checksum(self):
        gate = SecurityGate()
        gate.register_agent_checksum("agent-1", "sha256:abc")
        assert gate._agent_checksums["agent-1"] == "sha256:abc"

        gate.deregister_agent_checksum("agent-1")
        assert "agent-1" not in gate._agent_checksums

    def test_deregister_nonexistent_checksum_no_error(self):
        gate = SecurityGate()
        gate.deregister_agent_checksum("no-such-agent")  # should not raise

    def test_drift_detector_property(self):
        detector = _DriftDetector()
        gate = SecurityGate(drift_detector=detector)
        assert gate.drift_detector is detector

    def test_get_stats(self):
        gate = SecurityGate(payload_secret="secret123")
        gate.register_agent_checksum("a1", "chk1")
        gate.register_agent_checksum("a2", "chk2")
        stats = gate.get_stats()
        assert stats["registered_checksums"] == 2
        assert stats["block_on_drift"] is False
        assert stats["payload_integrity_enabled"] is True
        assert "drift_detector" in stats

    def test_get_stats_no_payload_secret(self):
        gate = SecurityGate()
        stats = gate.get_stats()
        assert stats["payload_integrity_enabled"] is False

    async def test_evaluate_pass_no_checks(self):
        gate = SecurityGate()
        msg = self._make_msg()
        result = await gate.evaluate(msg)
        assert result.passed is True
        assert result.drift_alerts == ()

    async def test_evaluate_records_observation(self):
        detector = _DriftDetector()
        gate = SecurityGate(drift_detector=detector)
        msg = self._make_msg()
        await gate.evaluate(msg, impact_score=0.7, decision="APPROVED", consensus_vote=0.9)
        assert len(detector._observations) == 1
        obs = detector._observations[0]
        assert obs["impact_score"] == 0.7
        assert obs["decision"] == "APPROVED"

    async def test_evaluate_skips_observation_when_no_impact(self):
        detector = _DriftDetector()
        gate = SecurityGate(drift_detector=detector)
        msg = self._make_msg()
        await gate.evaluate(msg)
        assert len(detector._observations) == 0

    async def test_evaluate_drift_alerts_no_block(self):
        detector = _DriftDetector()
        alert = _DriftAlert(description="high impact drift")
        detector._alerts = [alert]
        gate = SecurityGate(drift_detector=detector, block_on_drift=False)
        msg = self._make_msg()
        result = await gate.evaluate(msg)
        assert result.passed is True
        assert len(result.drift_alerts) == 1

    async def test_evaluate_drift_alerts_block(self):
        detector = _DriftDetector()
        alert = _DriftAlert(description="critical drift")
        detector._alerts = [alert]
        gate = SecurityGate(drift_detector=detector, block_on_drift=True)
        msg = self._make_msg()
        result = await gate.evaluate(msg)
        assert result.passed is False
        assert "critical drift" in result.reason
        assert len(result.drift_alerts) == 1

    async def test_evaluate_checksum_valid(self):
        gate = SecurityGate()
        gate.register_agent_checksum("agent-1", "sha256:abc")
        msg = self._make_msg()
        result = await gate.evaluate(msg, token_claims={"ach": "sha256:abc"})
        assert result.passed is True
        assert result.checksum_valid is True

    async def test_evaluate_checksum_mismatch(self):
        gate = SecurityGate()
        gate.register_agent_checksum("agent-1", "sha256:abc")
        msg = self._make_msg()
        result = await gate.evaluate(msg, token_claims={"ach": "sha256:wrong"})
        assert result.passed is False
        assert "ach mismatch" in result.reason
        assert result.checksum_valid is False

    async def test_evaluate_checksum_missing_from_token(self):
        gate = SecurityGate()
        gate.register_agent_checksum("agent-1", "sha256:abc")
        msg = self._make_msg()
        result = await gate.evaluate(msg, token_claims={"other": "val"})
        assert result.passed is True  # missing ach does not block, just sets flag
        assert result.checksum_valid is False

    async def test_evaluate_no_checksum_registered(self):
        gate = SecurityGate()
        msg = self._make_msg()
        result = await gate.evaluate(msg, token_claims={"ach": "anything"})
        assert result.passed is True
        assert result.checksum_valid is True

    async def test_evaluate_no_token_claims(self):
        gate = SecurityGate()
        gate.register_agent_checksum("agent-1", "sha256:abc")
        msg = self._make_msg()
        result = await gate.evaluate(msg, token_claims=None)
        assert result.passed is True

    async def test_evaluate_payload_integrity_valid(self):
        gate = SecurityGate(payload_secret="my-secret")
        msg = self._make_msg()
        msg.payload_hmac = "valid-hmac"  # type: ignore[attr-defined]
        with patch(
            "enhanced_agent_bus.payload_integrity.verify_payload",
            return_value=True,
            create=True,
        ):
            result = await gate.evaluate(msg)
        assert result.passed is True
        assert result.payload_valid is True

    async def test_evaluate_payload_integrity_invalid(self):
        gate = SecurityGate(payload_secret="my-secret")
        msg = self._make_msg()
        msg.payload_hmac = "bad-hmac"  # type: ignore[attr-defined]
        result = await gate.evaluate(msg)
        assert result.passed is False
        assert "HMAC mismatch" in result.reason
        assert result.payload_valid is False

    async def test_evaluate_payload_no_hmac_present(self):
        gate = SecurityGate(payload_secret="my-secret")
        msg = self._make_msg()
        # No payload_hmac attribute -> backward compat pass
        result = await gate.evaluate(msg)
        assert result.passed is True
        assert result.payload_valid is True

    async def test_evaluate_payload_no_secret_configured(self):
        gate = SecurityGate(payload_secret=None)
        msg = self._make_msg()
        result = await gate.evaluate(msg)
        assert result.passed is True

    async def test_check_payload_integrity_import_error(self):
        gate = SecurityGate(payload_secret="secret")
        msg = self._make_msg()
        msg.payload_hmac = "some-hmac"  # type: ignore[attr-defined]

        # Patch the local import to raise ImportError
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "enhanced_agent_bus.payload_integrity":
                raise ImportError("mocked")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            result = gate._check_payload_integrity(msg)
            assert result is True  # falls back to True on ImportError

    async def test_evaluate_drift_plus_checksum_fail(self):
        """Drift alerts logged but not blocking; checksum fail blocks."""
        detector = _DriftDetector()
        alert = _DriftAlert(description="minor drift")
        detector._alerts = [alert]
        gate = SecurityGate(drift_detector=detector, block_on_drift=False)
        gate.register_agent_checksum("agent-1", "sha256:expected")
        msg = self._make_msg()
        result = await gate.evaluate(msg, token_claims={"ach": "sha256:wrong"})
        assert result.passed is False
        assert len(result.drift_alerts) == 1

    async def test_evaluate_tenant_id_default(self):
        gate = SecurityGate()
        msg = self._make_msg()
        # AgentMessage may not have tenant_id -> getattr fallback
        result = await gate.evaluate(msg)
        assert result.passed is True


# ============================================================================
# PART 2: data_flywheel/config.py tests
# ============================================================================


class TestFlywheelMode:
    def test_all_modes(self):
        assert FlywheelMode.COLLECTION_ONLY == "collection_only"
        assert FlywheelMode.EVALUATION_ONLY == "evaluation_only"
        assert FlywheelMode.FULL == "full"
        assert FlywheelMode.DISABLED == "disabled"


class TestExperimentType:
    def test_all_types(self):
        assert ExperimentType.BASE == "base"
        assert ExperimentType.ICL == "icl"
        assert ExperimentType.FINE_TUNED == "fine_tuned"


class TestModelSelectionStrategy:
    def test_all_strategies(self):
        assert ModelSelectionStrategy.COST_OPTIMIZED == "cost_optimized"
        assert ModelSelectionStrategy.ACCURACY_OPTIMIZED == "accuracy_optimized"
        assert ModelSelectionStrategy.BALANCED == "balanced"
        assert ModelSelectionStrategy.CONSTITUTIONAL_STRICT == "constitutional_strict"


class TestDataSplitConfig:
    def test_defaults(self):
        cfg = DataSplitConfig()
        assert cfg.eval_size == 100
        assert cfg.val_ratio == 0.1
        assert cfg.min_total_records == 50
        assert cfg.random_seed == 42
        assert cfg.limit == 10000
        assert cfg.stratify_by_workload is True

    def test_custom_values(self):
        cfg = DataSplitConfig(eval_size=200, val_ratio=0.2, random_seed=None)
        assert cfg.eval_size == 200
        assert cfg.val_ratio == 0.2
        assert cfg.random_seed is None

    def test_validation_eval_size_min(self):
        with pytest.raises(ValidationError):
            DataSplitConfig(eval_size=5)  # ge=10

    def test_validation_val_ratio_max(self):
        with pytest.raises(ValidationError):
            DataSplitConfig(val_ratio=1.0)  # lt=1.0


class TestICLConfig:
    def test_defaults(self):
        cfg = ICLConfig()
        assert cfg.max_context_length == 8192
        assert cfg.reserved_tokens == 2048
        assert cfg.max_examples == 3
        assert cfg.min_examples == 1
        assert cfg.example_selection == "semantic_similarity"

    def test_boundary_values(self):
        cfg = ICLConfig(max_context_length=512, max_examples=10)
        assert cfg.max_context_length == 512
        assert cfg.max_examples == 10

    def test_validation_context_length_too_small(self):
        with pytest.raises(ValidationError):
            ICLConfig(max_context_length=100)


class TestTrainingConfig:
    def test_defaults(self):
        cfg = TrainingConfig()
        assert cfg.training_type == "sft"
        assert cfg.finetuning_type == "lora"
        assert cfg.epochs == 2
        assert cfg.batch_size == 16
        assert cfg.learning_rate == 0.0001
        assert cfg.lora_rank == 32
        assert cfg.lora_alpha == 64
        assert cfg.lora_dropout == 0.1

    def test_validation_learning_rate_zero(self):
        with pytest.raises(ValidationError):
            TrainingConfig(learning_rate=0.0)  # gt=0.0

    def test_custom(self):
        cfg = TrainingConfig(epochs=5, batch_size=32, lora_rank=64)
        assert cfg.epochs == 5
        assert cfg.batch_size == 32
        assert cfg.lora_rank == 64


class TestEvaluationConfig:
    def test_defaults(self):
        cfg = EvaluationConfig()
        assert cfg.use_llm_judge is True
        assert cfg.judge_model == "llama-3.1-70b-instruct"
        assert cfg.similarity_threshold == 0.7
        assert cfg.constitutional_compliance_weight == 0.3
        assert cfg.accuracy_weight == 0.5
        assert cfg.cost_weight == 0.2

    def test_custom(self):
        cfg = EvaluationConfig(use_llm_judge=False, similarity_threshold=0.9)
        assert cfg.use_llm_judge is False
        assert cfg.similarity_threshold == 0.9


class TestCandidateModel:
    def test_defaults(self):
        m = CandidateModel(model_name="test-model")
        assert m.model_name == "test-model"
        assert m.model_type == "llm"
        assert m.context_length == 8192
        assert m.gpu_requirements == 1
        assert m.enable_fine_tuning is False
        assert m.fine_tuning_target is None
        assert m.cost_per_1k_tokens == 0.0

    def test_full_config(self):
        m = CandidateModel(
            model_name="llama-3",
            enable_fine_tuning=True,
            fine_tuning_target="llama-3-ft",
            cost_per_1k_tokens=0.001,
            gpu_requirements=4,
        )
        assert m.enable_fine_tuning is True
        assert m.fine_tuning_target == "llama-3-ft"
        assert m.gpu_requirements == 4

    def test_gpu_validation(self):
        with pytest.raises(ValidationError):
            CandidateModel(model_name="x", gpu_requirements=10)  # le=8


class TestFlywheelConfig:
    def test_defaults(self):
        cfg = FlywheelConfig()
        assert cfg.mode == FlywheelMode.COLLECTION_ONLY
        assert cfg.require_constitutional_validation is True
        assert cfg.log_retention_days == 90
        assert cfg.max_logs_per_workload == 100000
        assert cfg.sample_rate == 1.0
        assert cfg.workload_classification_enabled is True
        assert len(cfg.supported_workload_types) == 5
        assert cfg.elasticsearch_url == "http://localhost:9200"
        assert cfg.redis_url == "redis://localhost:6379"
        assert cfg.mongodb_url is None
        assert cfg.require_human_approval is True

    def test_nested_configs(self):
        cfg = FlywheelConfig()
        assert isinstance(cfg.data_split, DataSplitConfig)
        assert isinstance(cfg.icl, ICLConfig)
        assert isinstance(cfg.training, TrainingConfig)
        assert isinstance(cfg.evaluation, EvaluationConfig)

    def test_validate_constitutional_hash_valid(self):
        cfg = FlywheelConfig()
        assert cfg.validate_constitutional_hash() is True

    def test_validate_constitutional_hash_invalid(self):
        cfg = FlywheelConfig()
        # Bypass pydantic to set wrong hash
        object.__setattr__(cfg, "constitutional_hash", "wrong-hash")
        assert cfg.validate_constitutional_hash() is False

    def test_validate_constitutional_hash_empty(self):
        cfg = FlywheelConfig()
        object.__setattr__(cfg, "constitutional_hash", "")
        assert cfg.validate_constitutional_hash() is False

    def test_custom_mode(self):
        cfg = FlywheelConfig(mode=FlywheelMode.FULL)
        assert cfg.mode == FlywheelMode.FULL

    def test_selection_strategy(self):
        cfg = FlywheelConfig(selection_strategy=ModelSelectionStrategy.COST_OPTIMIZED)
        assert cfg.selection_strategy == ModelSelectionStrategy.COST_OPTIMIZED

    def test_candidate_models(self):
        models = [CandidateModel(model_name="m1"), CandidateModel(model_name="m2")]
        cfg = FlywheelConfig(candidate_models=models)
        assert len(cfg.candidate_models) == 2

    def test_log_retention_validation(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(log_retention_days=0)  # ge=1

    def test_sample_rate_validation(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(sample_rate=1.5)  # le=1.0

    def test_from_attributes(self):
        cfg = FlywheelConfig()
        assert cfg.model_config.get("from_attributes") is True


class TestDefaultFlywheelConfig:
    def test_has_candidate_models(self):
        assert len(DEFAULT_FLYWHEEL_CONFIG.candidate_models) == 2

    def test_first_candidate(self):
        m = DEFAULT_FLYWHEEL_CONFIG.candidate_models[0]
        assert m.model_name == "meta/llama-3.2-1b-instruct"
        assert m.enable_fine_tuning is True
        assert m.cost_per_1k_tokens == 0.0001

    def test_second_candidate(self):
        m = DEFAULT_FLYWHEEL_CONFIG.candidate_models[1]
        assert m.model_name == "meta/llama-3.2-3b-instruct"
        assert m.cost_per_1k_tokens == 0.0003


# ============================================================================
# PART 3: middlewares/batch/circuit_breaker.py tests
# ============================================================================


def _make_batch_context(
    items: list[BatchRequestItem] | None = None,
    batch_response: BatchResponse | None = None,
) -> BatchPipelineContext:
    """Helper to create a BatchPipelineContext."""
    ctx = BatchPipelineContext()
    ctx.batch_items = items or [
        BatchRequestItem(request_id="req-1", content={"text": "hello"}),
        BatchRequestItem(request_id="req-2", content={"text": "world"}),
    ]
    if batch_response is not None:
        ctx.batch_response = batch_response
    return ctx


class TestBatchCircuitBreakerErrors:
    def test_error_tuple_contents(self):
        assert RuntimeError in BATCH_CIRCUIT_BREAKER_ERRORS
        assert ValueError in BATCH_CIRCUIT_BREAKER_ERRORS
        assert TypeError in BATCH_CIRCUIT_BREAKER_ERRORS
        assert KeyError in BATCH_CIRCUIT_BREAKER_ERRORS
        assert AttributeError in BATCH_CIRCUIT_BREAKER_ERRORS


class TestBatchCircuitBreakerMiddlewareInit:
    def test_default_init(self):
        mw = BatchCircuitBreakerMiddleware()
        assert mw._circuit_breaker is not None
        assert mw._fallback_response is None

    def test_custom_params(self):
        mw = BatchCircuitBreakerMiddleware(
            failure_threshold=0.3,
            cooldown_period=60.0,
            minimum_requests=5,
            success_threshold=0.7,
        )
        assert mw._circuit_breaker.config.failure_threshold == 0.3
        assert mw._circuit_breaker.config.cooldown_period == 60.0
        assert mw._circuit_breaker.config.minimum_requests == 5
        assert mw._circuit_breaker.config.success_threshold == 0.7

    def test_with_pre_configured_cb(self):
        cb_config = CircuitBreakerConfig(failure_threshold=0.1)
        cb = CircuitBreaker(cb_config)
        mw = BatchCircuitBreakerMiddleware(circuit_breaker=cb)
        assert mw._circuit_breaker is cb

    def test_with_middleware_config(self):
        cfg = MiddlewareConfig(fail_closed=False, timeout_ms=500)
        mw = BatchCircuitBreakerMiddleware(config=cfg)
        assert mw.config.fail_closed is False
        assert mw.config.timeout_ms == 500


class TestBatchCircuitBreakerMiddlewareProcess:
    """Tests for the process method and related helpers."""

    async def test_process_circuit_closed_success(self):
        """Circuit closed, next middleware succeeds."""
        mw = BatchCircuitBreakerMiddleware()
        ctx = _make_batch_context()

        # Create a successful response
        response = BatchResponse(
            batch_id="b1",
            success=True,
            items=[
                BatchResponseItem.create_success("req-1", True, 10.0),
                BatchResponseItem.create_success("req-2", True, 10.0),
            ],
        )

        async def fake_next(context):
            context.batch_response = response
            return context

        mw._call_next = fake_next  # type: ignore[assignment]

        result = await mw.process(ctx)
        assert result.metadata["circuit_state"] == "closed"
        assert result.metadata["circuit_success_count"] >= 0

    async def test_process_circuit_open_fail_closed(self):
        """Circuit open with fail_closed raises exception."""
        cb_config = CircuitBreakerConfig(failure_threshold=0.1, minimum_requests=1)
        cb = CircuitBreaker(cb_config)
        cb.state = CircuitState.OPEN
        cb.last_failure_time = time.time()  # recent failure

        cfg = MiddlewareConfig(fail_closed=True)
        mw = BatchCircuitBreakerMiddleware(config=cfg, circuit_breaker=cb)
        ctx = _make_batch_context()

        with pytest.raises(BatchProcessingException):
            await mw.process(ctx)

    async def test_process_circuit_open_fallback(self):
        """Circuit open with fail_closed=False returns fallback."""
        cb_config = CircuitBreakerConfig(failure_threshold=0.1, minimum_requests=1)
        cb = CircuitBreaker(cb_config)
        cb.state = CircuitState.OPEN
        cb.last_failure_time = time.time()  # recent failure

        cfg = MiddlewareConfig(fail_closed=False)
        mw = BatchCircuitBreakerMiddleware(config=cfg, circuit_breaker=cb)

        async def fake_next(context):
            return context

        mw._call_next = fake_next  # type: ignore[assignment]

        ctx = _make_batch_context()
        result = await mw.process(ctx)

        assert result.metadata["circuit_state"] == "OPEN"
        assert result.metadata["circuit_auto_reset_pending"] is True
        assert len(result.warnings) > 0
        assert result.batch_response is not None
        assert result.batch_response.success is False

    async def test_process_circuit_open_increments_rejections(self):
        """Circuit open increments rejection counter."""
        cb_config = CircuitBreakerConfig()
        cb = CircuitBreaker(cb_config)
        cb.state = CircuitState.OPEN
        cb.last_failure_time = time.time()

        cfg = MiddlewareConfig(fail_closed=False)
        mw = BatchCircuitBreakerMiddleware(config=cfg, circuit_breaker=cb)

        async def fake_next(context):
            return context

        mw._call_next = fake_next  # type: ignore[assignment]

        ctx = _make_batch_context()
        ctx.metadata["circuit_rejections"] = 2
        result = await mw.process(ctx)
        assert result.metadata["circuit_rejections"] == 3

    async def test_process_next_raises_error_fail_closed(self):
        """Next middleware raises; fail_closed re-raises."""
        mw = BatchCircuitBreakerMiddleware(
            config=MiddlewareConfig(fail_closed=True),
        )

        async def fail_next(context):
            raise RuntimeError("boom")

        mw._call_next = fail_next  # type: ignore[assignment]
        ctx = _make_batch_context()

        with pytest.raises(RuntimeError, match="boom"):
            await mw.process(ctx)

    async def test_process_next_raises_error_fail_open(self):
        """Next middleware raises; fail_closed=False sets early result."""
        mw = BatchCircuitBreakerMiddleware(
            config=MiddlewareConfig(fail_closed=False),
        )

        async def fail_next(context):
            raise ValueError("bad value")

        mw._call_next = fail_next  # type: ignore[assignment]
        ctx = _make_batch_context()
        result = await mw.process(ctx)

        assert result.early_result is not None
        assert result.early_result.is_valid is False
        assert "Circuit breaker recorded failure" in result.early_result.errors[0]

    async def test_process_latency_tracked(self):
        """batch_latency_ms is updated after processing."""
        mw = BatchCircuitBreakerMiddleware()

        async def fake_next(context):
            context.batch_response = BatchResponse(
                batch_id="b1",
                success=True,
                items=[BatchResponseItem.create_success("r1", True, 1.0)],
            )
            return context

        mw._call_next = fake_next  # type: ignore[assignment]
        ctx = _make_batch_context()
        result = await mw.process(ctx)
        assert result.batch_latency_ms > 0


class TestRecordResult:
    """Tests for _record_result."""

    async def test_no_response_records_failure(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        mw = BatchCircuitBreakerMiddleware(circuit_breaker=cb)
        ctx = _make_batch_context()
        ctx.batch_response = None

        await mw._record_result(ctx)
        assert cb.failure_count == 1

    async def test_empty_items_records_success(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        mw = BatchCircuitBreakerMiddleware(circuit_breaker=cb)
        ctx = _make_batch_context()
        ctx.batch_response = BatchResponse(batch_id="b1", success=True, items=[])

        await mw._record_result(ctx)
        assert cb.success_count == 1

    async def test_majority_success_records_success(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        mw = BatchCircuitBreakerMiddleware(circuit_breaker=cb)
        ctx = _make_batch_context()
        ctx.batch_response = BatchResponse(
            batch_id="b1",
            success=True,
            items=[
                BatchResponseItem.create_success("r1", True, 1.0),
                BatchResponseItem.create_success("r2", True, 1.0),
                BatchResponseItem.create_error("r3", "ERR", "failed"),
            ],
        )

        await mw._record_result(ctx)
        assert cb.success_count == 1
        assert cb.failure_count == 0

    async def test_majority_failure_records_failure(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        mw = BatchCircuitBreakerMiddleware(circuit_breaker=cb)
        ctx = _make_batch_context()
        ctx.batch_response = BatchResponse(
            batch_id="b1",
            success=False,
            items=[
                BatchResponseItem.create_success("r1", True, 1.0),
                BatchResponseItem.create_error("r2", "ERR", "fail"),
                BatchResponseItem.create_error("r3", "ERR", "fail"),
                BatchResponseItem.create_error("r4", "ERR", "fail"),
            ],
        )

        await mw._record_result(ctx)
        assert cb.failure_count == 1
        assert cb.success_count == 0

    async def test_exactly_half_records_success(self):
        """50% success rate should record as success (>= 0.5)."""
        cb = CircuitBreaker(CircuitBreakerConfig())
        mw = BatchCircuitBreakerMiddleware(circuit_breaker=cb)
        ctx = _make_batch_context()
        ctx.batch_response = BatchResponse(
            batch_id="b1",
            success=True,
            items=[
                BatchResponseItem.create_success("r1", True, 1.0),
                BatchResponseItem.create_error("r2", "ERR", "fail"),
            ],
        )

        await mw._record_result(ctx)
        assert cb.success_count == 1


class TestCreateFallbackResponse:
    def test_creates_error_items(self):
        mw = BatchCircuitBreakerMiddleware()
        items = [
            BatchRequestItem(request_id="req-1", content={"a": 1}),
            BatchRequestItem(request_id="req-2", content={"b": 2}),
        ]
        ctx = _make_batch_context(items=items)
        response = mw._create_fallback_response(ctx)
        assert response.success is False
        assert len(response.items) == 2
        assert response.items[0].error_code == "CIRCUIT_OPEN"
        assert response.items[1].error_code == "CIRCUIT_OPEN"
        assert "OPEN" in response.errors[0]

    def test_uses_batch_id_from_request(self):
        from enhanced_agent_bus.batch_models import BatchRequest

        mw = BatchCircuitBreakerMiddleware()
        ctx = _make_batch_context()
        ctx.batch_request = BatchRequest(
            batch_id="my-batch-123",
            items=[BatchRequestItem(content={"x": 1})],
        )
        response = mw._create_fallback_response(ctx)
        assert response.batch_id == "my-batch-123"

    def test_no_batch_request_uses_default_id(self):
        mw = BatchCircuitBreakerMiddleware()
        ctx = _make_batch_context()
        ctx.batch_request = None
        response = mw._create_fallback_response(ctx)
        assert response.batch_id == "circuit_open"


class TestGetCircuitState:
    def test_returns_state_string(self):
        mw = BatchCircuitBreakerMiddleware()
        assert mw.get_circuit_state() == "closed"

    def test_returns_open_state(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        cb.state = CircuitState.OPEN
        mw = BatchCircuitBreakerMiddleware(circuit_breaker=cb)
        assert mw.get_circuit_state() == "open"

    def test_returns_half_open_state(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        cb.state = CircuitState.HALF_OPEN
        mw = BatchCircuitBreakerMiddleware(circuit_breaker=cb)
        assert mw.get_circuit_state() == "half_open"


class TestGetMetrics:
    def test_returns_all_fields(self):
        mw = BatchCircuitBreakerMiddleware(
            failure_threshold=0.4,
            cooldown_period=20.0,
        )
        metrics = mw.get_metrics()
        assert metrics["state"] == "closed"
        assert metrics["failure_count"] == 0
        assert metrics["success_count"] == 0
        assert metrics["total_requests"] == 0
        assert metrics["failure_threshold"] == 0.4
        assert metrics["cooldown_period"] == 20.0


class TestManualReset:
    async def test_resets_all_counters(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        cb.state = CircuitState.OPEN
        cb.failure_count = 10
        cb.success_count = 5
        cb.total_requests = 15
        cb.half_open_success_count = 3

        mw = BatchCircuitBreakerMiddleware(circuit_breaker=cb)
        await mw.manual_reset()

        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0
        assert cb.total_requests == 0
        assert cb.half_open_success_count == 0
