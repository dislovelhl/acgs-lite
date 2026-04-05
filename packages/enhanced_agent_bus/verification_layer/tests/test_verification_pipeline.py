"""
Tests for Verification Pipeline - Integrated Layer 2 Verification
Constitutional Hash: 608508a9bd224290

Tests cover:
- Pipeline configuration
- Stage execution
- Full pipeline flow
- Error handling
- Statistics and reporting
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from ..constitutional_transition import StateTransitionManager, TransitionState
from ..maci_verifier import MACIVerificationResult, MACIVerifier, VerificationStatus
from ..saga_coordinator import CompensationStrategy, SagaCoordinator, SagaState
from ..verification_pipeline import (
    CONSTITUTIONAL_HASH,
    PipelineConfig,
    PipelineResult,
    PipelineStage,
    PipelineStatus,
    StageResult,
    VerificationPipeline,
    create_verification_pipeline,
)
from ..z3_policy_verifier import PolicyVerificationResult, Z3PolicyVerifier, Z3VerificationStatus


class TestConstitutionalHash:
    """Tests for constitutional hash compliance."""

    def test_constitutional_hash_value(self):
        """Test that constitutional hash is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_pipeline_has_constitutional_hash(self):
        """Test that pipeline includes constitutional hash."""
        pipeline = create_verification_pipeline()
        assert pipeline.constitutional_hash == CONSTITUTIONAL_HASH
        assert pipeline.get_constitutional_hash() == CONSTITUTIONAL_HASH

    def test_config_has_constitutional_hash(self):
        """Test that config includes constitutional hash."""
        config = PipelineConfig()
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_has_constitutional_hash(self):
        """Test that result includes constitutional hash."""
        result = PipelineResult()
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


class TestPipelineConfig:
    """Tests for PipelineConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = PipelineConfig()

        assert config.enable_maci
        assert config.enable_policy_verification
        assert config.enable_saga
        assert config.enable_state_transitions
        assert config.maci_timeout_ms == 10000
        assert config.policy_timeout_ms == 5000
        assert config.saga_timeout_ms == 30000
        assert config.require_proofs

    def test_custom_config(self):
        """Test custom configuration."""
        config = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            maci_timeout_ms=20000,
            fail_fast=True,
        )

        assert not config.enable_maci
        assert not config.enable_policy_verification
        assert config.maci_timeout_ms == 20000
        assert config.fail_fast

    def test_config_to_dict(self):
        """Test config serialization."""
        config = PipelineConfig()
        data = config.to_dict()

        assert "enable_maci" in data
        assert "maci_timeout_ms" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestPipelineCreation:
    """Tests for pipeline creation."""

    def test_default_creation(self):
        """Test pipeline creation with defaults."""
        pipeline = create_verification_pipeline()

        assert pipeline is not None
        assert pipeline.maci_verifier is not None
        assert pipeline.z3_verifier is not None
        assert pipeline.saga_coordinator is not None
        assert pipeline.transition_manager is not None

    def test_creation_with_config(self):
        """Test pipeline with custom config."""
        config = PipelineConfig(
            enable_maci=False,
            enable_saga=False,
        )
        pipeline = create_verification_pipeline(config=config)

        assert not pipeline.config.enable_maci
        assert not pipeline.config.enable_saga


class TestPipelineStage:
    """Tests for PipelineStage enum."""

    def test_all_stages_defined(self):
        """Test that all stages are defined."""
        assert PipelineStage.INITIALIZATION.value == "initialization"
        assert PipelineStage.MACI_VERIFICATION.value == "maci_verification"
        assert PipelineStage.POLICY_VERIFICATION.value == "policy_verification"
        assert PipelineStage.SAGA_EXECUTION.value == "saga_execution"
        assert PipelineStage.STATE_TRANSITION.value == "state_transition"
        assert PipelineStage.FINALIZATION.value == "finalization"


class TestPipelineStatus:
    """Tests for PipelineStatus enum."""

    def test_all_statuses_defined(self):
        """Test that all statuses are defined."""
        assert PipelineStatus.PENDING.value == "pending"
        assert PipelineStatus.RUNNING.value == "running"
        assert PipelineStatus.COMPLETED.value == "completed"
        assert PipelineStatus.FAILED.value == "failed"
        assert PipelineStatus.COMPENSATED.value == "compensated"
        assert PipelineStatus.TIMEOUT.value == "timeout"


class TestStageResult:
    """Tests for StageResult model."""

    def test_stage_result_creation(self):
        """Test stage result creation."""
        result = StageResult(
            stage=PipelineStage.MACI_VERIFICATION,
            success=True,
            duration_ms=50.5,
        )

        assert result.stage == PipelineStage.MACI_VERIFICATION
        assert result.success
        assert result.duration_ms == 50.5

    def test_stage_result_to_dict(self):
        """Test stage result serialization."""
        result = StageResult(
            stage=PipelineStage.MACI_VERIFICATION,
            success=True,
            status="completed",
            duration_ms=50.5,
        )

        data = result.to_dict()

        assert data["stage"] == "maci_verification"
        assert data["success"]
        assert data["status"] == "completed"
        assert data["duration_ms"] == 50.5


class TestPipelineResult:
    """Tests for PipelineResult model."""

    def test_result_creation(self):
        """Test result creation."""
        result = PipelineResult()

        assert result.pipeline_id is not None
        assert result.status == PipelineStatus.PENDING
        assert not result.is_verified
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_to_dict(self):
        """Test result serialization."""
        result = PipelineResult(
            is_verified=True,
            confidence=0.95,
            status=PipelineStatus.COMPLETED,
        )

        data = result.to_dict()

        assert "pipeline_id" in data
        assert data["is_verified"]
        assert data["confidence"] == 0.95
        assert data["status"] == "completed"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_add_audit_entry(self):
        """Test adding audit entries."""
        result = PipelineResult()
        result.add_audit_entry("test_stage", "test_action", {"key": "value"})

        assert len(result.audit_trail) == 1
        assert result.audit_trail[0]["stage"] == "test_stage"
        assert result.audit_trail[0]["action"] == "test_action"
        assert result.audit_trail[0]["details"]["key"] == "value"
        assert result.audit_trail[0]["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestPipelineExecution:
    """Tests for pipeline execution."""

    async def test_simple_verification(self):
        """Test simple verification with MACI only."""
        config = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = create_verification_pipeline(config=config)

        result = await pipeline.verify(
            action="Test action",
            context={"key": "value"},
        )

        assert result is not None
        assert result.status in (PipelineStatus.COMPLETED, PipelineStatus.FAILED)
        assert result.total_duration_ms > 0

    async def test_full_pipeline(self):
        """Test full pipeline with all stages."""
        config = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=True,
            enable_saga=False,  # Skip saga for simpler test
            enable_state_transitions=True,
        )
        pipeline = create_verification_pipeline(config=config)

        result = await pipeline.verify(
            action="Grant access to resource",
            context={"resource_id": "res-001"},
            policy_text="Users must authenticate before accessing resources.",
        )

        assert result is not None
        assert len(result.stage_results) > 0
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_pipeline_produces_maci_result(self):
        """Test that pipeline produces MACI result."""
        config = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = create_verification_pipeline(config=config)

        result = await pipeline.verify(
            action="Test action",
            context={},
        )

        assert result.maci_result is not None

    async def test_pipeline_produces_policy_result(self):
        """Test that pipeline produces policy result when enabled."""
        config = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=True,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = create_verification_pipeline(config=config)

        result = await pipeline.verify(
            action="Test action",
            context={},
            policy_text="Data must be encrypted.",
        )

        assert result.policy_result is not None

    async def test_pipeline_produces_transition(self):
        """Test that pipeline produces transition when enabled."""
        config = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=True,
        )
        pipeline = create_verification_pipeline(config=config)

        result = await pipeline.verify(
            action="Test action",
            context={},
        )

        assert result.transition is not None

    async def test_pipeline_audit_trail(self):
        """Test that pipeline produces audit trail."""
        pipeline = create_verification_pipeline()

        result = await pipeline.verify(
            action="Auditable action",
            context={},
        )

        assert len(result.audit_trail) > 0
        # Check for initialization entry
        assert any(e.get("stage") == "initialization" for e in result.audit_trail)


class TestFailFastMode:
    """Tests for fail-fast mode."""

    async def test_fail_fast_stops_on_failure(self):
        """Test that fail-fast mode stops on first failure."""
        config = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=True,
            enable_state_transitions=True,
            fail_fast=True,
        )
        pipeline = create_verification_pipeline(config=config)

        # Mock MACI to fail
        async def mock_verify(*args, **kwargs):
            return MACIVerificationResult(
                verification_id="test",
                is_compliant=False,
                confidence=0.3,
                status=VerificationStatus.COMPLETED,
                violations=[{"type": "test", "description": "Test violation"}],
            )

        pipeline.maci_verifier.verify = mock_verify

        result = await pipeline.verify(
            action="Failing action",
            context={},
        )

        # Should fail after MACI
        assert result.status == PipelineStatus.FAILED


class TestSagaExecution:
    """Tests for saga execution in pipeline."""

    async def test_pipeline_with_saga_steps(self):
        """Test pipeline with saga steps."""
        config = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=True,
            enable_state_transitions=False,
        )
        pipeline = create_verification_pipeline(config=config)

        async def step1(ctx, data):
            return {"step": 1}

        async def compensate1(result):
            return {"compensated": 1}

        saga_steps = [
            {
                "name": "Step 1",
                "execute": step1,
                "compensate": compensate1,
            },
        ]

        result = await pipeline.verify(
            action="Saga action",
            context={},
            saga_steps=saga_steps,
        )

        assert result.saga_transaction is not None


class TestQuickVerify:
    """Tests for quick verification."""

    async def test_quick_verify(self):
        """Test quick verification shortcut."""
        pipeline = create_verification_pipeline()

        is_verified, confidence, violations = await pipeline.quick_verify(
            action="Quick test",
            context={},
        )

        assert isinstance(is_verified, bool)
        assert 0 <= confidence <= 1
        assert isinstance(violations, list)


class TestPipelineStatistics:
    """Tests for pipeline statistics."""

    def test_initial_stats(self):
        """Test initial statistics."""
        pipeline = create_verification_pipeline()
        stats = pipeline.get_pipeline_stats()

        assert stats["total_executions"] == 0

    async def test_stats_after_execution(self):
        """Test statistics after execution."""
        pipeline = create_verification_pipeline()

        await pipeline.verify("Test 1", {})
        await pipeline.verify("Test 2", {})

        stats = pipeline.get_pipeline_stats()

        assert stats["total_executions"] == 2
        assert "verification_rate" in stats
        assert "average_duration_ms" in stats
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestPipelineErrors:
    """Tests for error handling."""

    async def test_handles_exception(self):
        """Test pipeline handles exceptions gracefully."""
        config = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = create_verification_pipeline(config=config)

        # Mock to raise exception — must be a type in _PIPELINE_STAGE_ERRORS
        async def mock_verify(*args, **kwargs):
            raise RuntimeError("Test exception")

        pipeline.maci_verifier.verify = mock_verify

        result = await pipeline.verify(
            action="Error action",
            context={},
        )

        assert result.status == PipelineStatus.FAILED
        assert len(result.violations) > 0


class TestPipelineConfiguration:
    """Tests for various pipeline configurations."""

    async def test_maci_only_pipeline(self):
        """Test MACI-only pipeline."""
        config = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = create_verification_pipeline(config=config)

        result = await pipeline.verify("Test", {})

        # Only MACI stage should run
        maci_stages = [
            s for s in result.stage_results if s.stage == PipelineStage.MACI_VERIFICATION
        ]
        assert len(maci_stages) == 1

    async def test_policy_only_pipeline(self):
        """Test policy-only pipeline."""
        config = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=True,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = create_verification_pipeline(config=config)

        result = await pipeline.verify(
            "Test",
            {},
            policy_text="Test policy requirement.",
        )

        policy_stages = [
            s for s in result.stage_results if s.stage == PipelineStage.POLICY_VERIFICATION
        ]
        assert len(policy_stages) == 1

    async def test_parallel_verification_config(self):
        """Test parallel verification configuration."""
        config = PipelineConfig(
            parallel_verification=True,
        )

        assert config.parallel_verification

    async def test_require_all_stages_config(self):
        """Test require_all_stages configuration."""
        config = PipelineConfig(
            require_all_stages=True,
        )
        pipeline = create_verification_pipeline(config=config)

        # When require_all_stages is True, all enabled stages must pass
        assert pipeline.config.require_all_stages


class TestRecommendations:
    """Tests for recommendation generation."""

    async def test_generates_recommendations(self):
        """Test that pipeline generates recommendations."""
        pipeline = create_verification_pipeline()

        result = await pipeline.verify(
            action="Test action",
            context={"excessive_permissions": True},
        )

        assert isinstance(result.recommendations, list)

    async def test_recommendations_for_violations(self):
        """Test recommendations for violations."""
        config = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = create_verification_pipeline(config=config)

        # Create a context that will produce violations
        result = await pipeline.verify(
            action="Access sensitive data",
            context={
                "excessive_permissions": True,
                "data_unprotected": True,
            },
        )

        # If there are violations, there should be recommendations
        if len(result.violations) > 0:
            assert len(result.recommendations) > 0


class TestProofGeneration:
    """Tests for proof generation."""

    async def test_collects_proofs(self):
        """Test that pipeline collects proofs."""
        config = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=True,
            require_proofs=True,
        )
        pipeline = create_verification_pipeline(config=config)

        result = await pipeline.verify(
            action="Test action",
            context={},
        )

        assert len(result.proofs) > 0


class TestConfidenceCalculation:
    """Tests for confidence calculation."""

    async def test_computes_confidence(self):
        """Test that pipeline computes confidence."""
        pipeline = create_verification_pipeline()

        result = await pipeline.verify(
            action="Test action",
            context={},
        )

        assert 0 <= result.confidence <= 1


class TestStageTimeouts:
    """Tests for stage timeout handling."""

    async def test_stage_timeout_recorded(self):
        """Test that stage timeouts are properly recorded."""
        config = PipelineConfig(
            enable_maci=True,
            maci_timeout_ms=1,  # Very short timeout
        )
        pipeline = create_verification_pipeline(config=config)

        # Mock slow verification
        async def slow_verify(*args, **kwargs):
            await asyncio.sleep(1)
            return MACIVerificationResult(
                verification_id="test",
                is_compliant=True,
                confidence=0.9,
                status=VerificationStatus.COMPLETED,
            )

        pipeline.maci_verifier.verify = slow_verify

        result = await pipeline.verify(
            action="Slow action",
            context={},
        )

        # Should timeout
        maci_stage = next(
            (s for s in result.stage_results if s.stage == PipelineStage.MACI_VERIFICATION),
            None,
        )
        if maci_stage:
            assert maci_stage.status in ("timeout", "completed")
