"""
Tests for verification_layer/verification_pipeline.py

Covers:
- PipelineConfig, StageResult, PipelineResult dataclasses
- VerificationPipeline.verify() with various stage combinations
- fail_fast behaviour
- timeout and error handling
- _compute_overall_verification and _compute_confidence
- _generate_recommendations
- get_pipeline_stats and quick_verify
- create_verification_pipeline factory
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.verification_layer.verification_pipeline import (
    PipelineConfig,
    PipelineResult,
    PipelineStage,
    PipelineStatus,
    StageResult,
    VerificationPipeline,
    create_verification_pipeline,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_maci_result(is_compliant: bool = True, confidence: float = 0.9):
    """Build a mock MACIVerificationResult."""
    r = MagicMock()
    r.is_compliant = is_compliant
    r.confidence = confidence
    r.verification_id = "maci-001"
    r.violations = [] if is_compliant else [{"type": "role_violation"}]
    r.recommendations = [] if is_compliant else ["Fix role separation"]
    r.to_dict.return_value = {"is_compliant": is_compliant, "confidence": confidence}
    return r


def _make_policy_result(is_verified: bool = True, has_proof: bool = True):
    """Build a mock PolicyVerificationResult."""
    r = MagicMock()
    r.is_verified = is_verified
    r.verification_id = "policy-001"
    r.violations = [] if is_verified else [{"type": "policy_violation"}]
    r.recommendations = [] if is_verified else ["Review policy constraints"]
    r.status = MagicMock(value="satisfiable" if is_verified else "unsatisfiable")
    if has_proof:
        r.proof = MagicMock()
        r.proof.heuristic_score = 0.85
    else:
        r.proof = None
    r.to_dict.return_value = {"is_verified": is_verified}
    return r


def _make_transition(success: bool = True):
    """Build a mock ConstitutionalTransition."""
    t = MagicMock()
    proof = MagicMock()
    proof.to_dict.return_value = {"type": "proof"}
    t.proofs = [proof] if success else []
    t.to_dict.return_value = {"state": "completed" if success else "failed"}
    return t


def _make_saga(success: bool = True):
    """Build a mock SagaTransaction."""
    s = MagicMock()
    s.failure_reason = None if success else "step failed"
    s.to_dict.return_value = {"state": "completed" if success else "failed"}
    return s


def _build_pipeline(
    *,
    maci_compliant: bool = True,
    policy_verified: bool = True,
    saga_success: bool = True,
    transition_success: bool = True,
    config: PipelineConfig | None = None,
) -> VerificationPipeline:
    """Create a VerificationPipeline with fully-mocked sub-components."""
    cfg = config or PipelineConfig()

    maci_verifier = AsyncMock()
    maci_verifier.verify = AsyncMock(return_value=_make_maci_result(maci_compliant))

    z3_verifier = AsyncMock()
    z3_verifier.verify_policy = AsyncMock(return_value=_make_policy_result(policy_verified))

    saga_coordinator = MagicMock()
    saga = _make_saga(saga_success)
    saga_coordinator.create_saga.return_value = saga
    saga_coordinator.add_step = MagicMock()
    saga_coordinator.execute_saga = AsyncMock(return_value=saga_success)

    transition_manager = MagicMock()
    transition = _make_transition(transition_success)
    transition_manager.create_transition.return_value = transition
    transition_manager._validate_transition_sequence = AsyncMock(
        return_value=(transition_success, MagicMock())
    )
    transition_manager.transition_to = AsyncMock(return_value=(transition_success, MagicMock()))

    return VerificationPipeline(
        config=cfg,
        maci_verifier=maci_verifier,
        z3_verifier=z3_verifier,
        saga_coordinator=saga_coordinator,
        transition_manager=transition_manager,
    )


# ---------------------------------------------------------------------------
# Dataclass / enum tests
# ---------------------------------------------------------------------------


class TestPipelineEnumsAndDataclasses:
    def test_pipeline_stage_values(self):
        assert PipelineStage.INITIALIZATION.value == "initialization"
        assert PipelineStage.FINALIZATION.value == "finalization"

    def test_pipeline_status_values(self):
        assert PipelineStatus.PENDING.value == "pending"
        assert PipelineStatus.COMPENSATED.value == "compensated"

    def test_pipeline_config_defaults(self):
        cfg = PipelineConfig()
        assert cfg.enable_maci is True
        assert cfg.enable_policy_verification is True
        assert cfg.fail_fast is False
        assert cfg.require_all_stages is False

    def test_pipeline_config_to_dict(self):
        cfg = PipelineConfig(maci_timeout_ms=5000)
        d = cfg.to_dict()
        assert d["maci_timeout_ms"] == 5000
        assert "enable_maci" in d

    def test_stage_result_to_dict(self):
        sr = StageResult(
            stage=PipelineStage.MACI_VERIFICATION,
            success=True,
        )
        d = sr.to_dict()
        assert d["stage"] == "maci_verification"
        assert d["success"] is True

    def test_pipeline_result_to_dict_minimal(self):
        pr = PipelineResult()
        d = pr.to_dict()
        assert d["status"] == "pending"
        assert d["is_verified"] is False

    def test_pipeline_result_add_audit_entry(self):
        pr = PipelineResult()
        pr.add_audit_entry("init", "start", {"key": "value"})
        assert len(pr.audit_trail) == 1
        assert pr.audit_trail[0]["stage"] == "init"
        assert pr.audit_trail[0]["action"] == "start"


# ---------------------------------------------------------------------------
# VerificationPipeline.verify() tests
# ---------------------------------------------------------------------------


class TestVerifyHappyPath:
    @pytest.mark.asyncio
    async def test_all_stages_pass(self):
        pipeline = _build_pipeline()
        result = await pipeline.verify(
            action="approve_proposal",
            context={"proposal_id": "p-1"},
            policy_text="All proposals require approval",
            saga_steps=[{"name": "step1", "execute": AsyncMock(), "compensate": AsyncMock()}],
        )
        assert result.status == PipelineStatus.COMPLETED
        assert result.is_verified is True
        assert result.confidence > 0
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_maci_only(self):
        cfg = PipelineConfig(
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _build_pipeline(config=cfg)
        result = await pipeline.verify("action", {"key": "val"})
        assert result.status == PipelineStatus.COMPLETED
        assert result.is_verified is True

    @pytest.mark.asyncio
    async def test_no_stages_enabled(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _build_pipeline(config=cfg)
        result = await pipeline.verify("action", {})
        # No stage results -> is_verified depends on require_all_stages
        assert result.status == PipelineStatus.FAILED
        assert result.is_verified is False


class TestVerifyFailures:
    @pytest.mark.asyncio
    async def test_maci_failure_no_fail_fast(self):
        pipeline = _build_pipeline(maci_compliant=False)
        cfg = PipelineConfig(fail_fast=False, enable_saga=False)
        pipeline.config = cfg
        result = await pipeline.verify("action", {}, policy_text="some policy")
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_maci_failure_fail_fast(self):
        cfg = PipelineConfig(fail_fast=True, enable_saga=False, enable_state_transitions=False)
        pipeline = _build_pipeline(maci_compliant=False, config=cfg)
        result = await pipeline.verify("action", {})
        assert result.status == PipelineStatus.FAILED

    @pytest.mark.asyncio
    async def test_policy_failure_fail_fast(self):
        cfg = PipelineConfig(fail_fast=True, enable_saga=False, enable_state_transitions=False)
        pipeline = _build_pipeline(policy_verified=False, config=cfg)
        result = await pipeline.verify("action", {}, policy_text="bad policy")
        assert result.status == PipelineStatus.FAILED

    @pytest.mark.asyncio
    async def test_saga_failure_fail_fast(self):
        cfg = PipelineConfig(fail_fast=True, enable_state_transitions=False)
        pipeline = _build_pipeline(saga_success=False, config=cfg)
        steps = [{"name": "s1", "execute": AsyncMock()}]
        result = await pipeline.verify("action", {}, saga_steps=steps)
        assert result.status == PipelineStatus.COMPENSATED

    @pytest.mark.asyncio
    async def test_transition_failure_fail_fast(self):
        cfg = PipelineConfig(fail_fast=True, enable_saga=False)
        pipeline = _build_pipeline(transition_success=False, config=cfg)
        result = await pipeline.verify("action", {})
        assert result.status == PipelineStatus.FAILED


class TestVerifyErrorPaths:
    @pytest.mark.asyncio
    async def test_timeout_error_in_maci_stage(self):
        """TimeoutError inside a stage is caught by the stage handler, producing FAILED (not TIMEOUT)."""
        pipeline = _build_pipeline()
        pipeline.maci_verifier.verify = AsyncMock(side_effect=TimeoutError("timed out"))
        cfg = PipelineConfig(
            enable_saga=False, enable_state_transitions=False, enable_policy_verification=False
        )
        pipeline.config = cfg
        result = await pipeline.verify("action", {})
        # The MACI stage catches the TimeoutError internally; pipeline sees a failed stage
        assert result.status == PipelineStatus.FAILED
        assert any(sr.status == "timeout" for sr in result.stage_results)

    @pytest.mark.asyncio
    async def test_runtime_error_in_pipeline(self):
        pipeline = _build_pipeline()
        pipeline.maci_verifier.verify = AsyncMock(side_effect=RuntimeError("bad"))
        cfg = PipelineConfig(
            enable_saga=False, enable_state_transitions=False, enable_policy_verification=False
        )
        pipeline.config = cfg
        result = await pipeline.verify("action", {})
        assert result.status == PipelineStatus.FAILED
        assert len(result.violations) > 0


# ---------------------------------------------------------------------------
# Internal computation tests
# ---------------------------------------------------------------------------


class TestComputations:
    def test_compute_overall_require_all_stages_all_pass(self):
        pipeline = _build_pipeline()
        pipeline.config.require_all_stages = True
        pr = PipelineResult()
        pr.stage_results = [
            StageResult(stage=PipelineStage.MACI_VERIFICATION, success=True),
            StageResult(stage=PipelineStage.POLICY_VERIFICATION, success=True),
        ]
        assert pipeline._compute_overall_verification(pr) is True

    def test_compute_overall_require_all_stages_one_fails(self):
        pipeline = _build_pipeline()
        pipeline.config.require_all_stages = True
        pr = PipelineResult()
        pr.stage_results = [
            StageResult(stage=PipelineStage.MACI_VERIFICATION, success=True),
            StageResult(stage=PipelineStage.POLICY_VERIFICATION, success=False),
        ]
        assert pipeline._compute_overall_verification(pr) is False

    def test_compute_overall_require_all_stages_empty(self):
        pipeline = _build_pipeline()
        pipeline.config.require_all_stages = True
        pr = PipelineResult()
        assert pipeline._compute_overall_verification(pr) is False

    def test_compute_overall_any_stage_one_pass(self):
        pipeline = _build_pipeline()
        pipeline.config.require_all_stages = False
        pr = PipelineResult()
        pr.stage_results = [
            StageResult(stage=PipelineStage.MACI_VERIFICATION, success=False),
            StageResult(stage=PipelineStage.POLICY_VERIFICATION, success=True),
        ]
        assert pipeline._compute_overall_verification(pr) is True

    def test_compute_confidence_no_data(self):
        pipeline = _build_pipeline()
        pr = PipelineResult()
        assert pipeline._compute_confidence(pr) == 0.0

    def test_compute_confidence_with_maci(self):
        pipeline = _build_pipeline()
        pr = PipelineResult()
        pr.maci_result = _make_maci_result(confidence=0.8)
        pr.stage_results = [StageResult(stage=PipelineStage.MACI_VERIFICATION, success=True)]
        c = pipeline._compute_confidence(pr)
        assert c > 0

    def test_generate_recommendations_verified(self):
        pipeline = _build_pipeline()
        pr = PipelineResult(is_verified=True)
        recs = pipeline._generate_recommendations(pr)
        assert "Review and address" not in " ".join(recs)

    def test_generate_recommendations_failed_stage(self):
        pipeline = _build_pipeline()
        pr = PipelineResult(is_verified=False)
        pr.stage_results = [
            StageResult(stage=PipelineStage.MACI_VERIFICATION, success=False, status="timeout"),
        ]
        recs = pipeline._generate_recommendations(pr)
        assert any("maci_verification" in r for r in recs)
        assert any("timeout" in r for r in recs)


# ---------------------------------------------------------------------------
# quick_verify and stats
# ---------------------------------------------------------------------------


class TestQuickVerifyAndStats:
    @pytest.mark.asyncio
    async def test_quick_verify(self):
        pipeline = _build_pipeline()
        ok, conf, violations = await pipeline.quick_verify("action", {"x": 1})
        assert ok is True
        assert conf > 0
        assert violations == []

    def test_get_pipeline_stats_empty(self):
        pipeline = _build_pipeline()
        stats = pipeline.get_pipeline_stats()
        assert stats["total_executions"] == 0

    @pytest.mark.asyncio
    async def test_get_pipeline_stats_after_execution(self):
        pipeline = _build_pipeline()
        cfg = PipelineConfig(
            enable_saga=False, enable_state_transitions=False, enable_policy_verification=False
        )
        pipeline.config = cfg
        await pipeline.verify("action", {})
        stats = pipeline.get_pipeline_stats()
        assert stats["total_executions"] == 1
        assert "verification_rate" in stats

    def test_get_constitutional_hash(self):
        pipeline = _build_pipeline()
        h = pipeline.get_constitutional_hash()
        assert isinstance(h, str)


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


class TestFactory:
    def test_create_verification_pipeline_default(self):
        pipeline = create_verification_pipeline()
        assert isinstance(pipeline, VerificationPipeline)

    def test_create_verification_pipeline_custom_config(self):
        cfg = PipelineConfig(enable_maci=False)
        pipeline = create_verification_pipeline(config=cfg)
        assert pipeline.config.enable_maci is False
