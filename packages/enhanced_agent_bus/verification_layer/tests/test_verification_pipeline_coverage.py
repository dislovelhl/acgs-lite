"""
Comprehensive coverage tests for VerificationPipeline.
Constitutional Hash: 608508a9bd224290

Covers:
- PipelineStage enum completeness
- PipelineStatus enum completeness
- PipelineConfig defaults and customisation
- StageResult dataclass
- PipelineResult dataclass (incl. proof_chain, audit_trail, to_dict)
- VerificationPipeline.__init__ (default and injected components)
- verify(): all 4 stages enabled happy path
- verify(): selective stages (each in isolation)
- verify(): fail_fast stops pipeline early
- verify(): MACI blocked scenario
- verify(): Z3 constraint violation
- verify(): Saga compensation triggered
- verify(): State transition rejected
- verify(): stage RuntimeError handled gracefully
- verify(): pipeline-level ValueError handled gracefully
- verify(): asyncio.TimeoutError handled at pipeline level
- verify(): stage-level asyncio.TimeoutError for every stage
- verify(): no stages enabled → empty stage_results
- verify(): require_all_stages=True with one failure
- verify(): require_all_stages=True all pass
- get_pipeline_stats(): empty, single, multi-execution
- quick_verify(): delegates to maci_verifier
- create_verification_pipeline() factory
- _compute_confidence() edge cases
- Concurrent verification requests
- Audit trail entries for each stage
"""

import asyncio
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from ..maci_verifier import MACIVerificationResult, VerificationStatus
from ..saga_coordinator import CompensationStrategy, SagaState
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
from ..z3_policy_verifier import (
    PolicyVerificationResult,
    VerificationProof,
    Z3VerificationStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _maci_result(compliant: bool = True, confidence: float = 0.9) -> MACIVerificationResult:
    return MACIVerificationResult(
        verification_id="mock-maci-id",
        is_compliant=compliant,
        confidence=confidence,
        status=VerificationStatus.COMPLETED,
        violations=[] if compliant else [{"type": "test_violation", "description": "blocked"}],
        recommendations=[] if compliant else ["Fix the violation"],
    )


def _policy_result(
    verified: bool = True,
    with_proof: bool = True,
    heuristic_score: float | None = 0.85,
) -> PolicyVerificationResult:
    proof = None
    if with_proof:
        proof = VerificationProof(
            verification_id="mock-z3-id",
            is_verified=verified,
            status=Z3VerificationStatus.SATISFIABLE
            if verified
            else Z3VerificationStatus.UNSATISFIABLE,
            heuristic_score=heuristic_score,
        )
    return PolicyVerificationResult(
        verification_id="mock-z3-id",
        is_verified=verified,
        status=Z3VerificationStatus.SATISFIABLE if verified else Z3VerificationStatus.UNSATISFIABLE,
        proof=proof,
        violations=[] if verified else [{"type": "constraint_violation", "description": "fails"}],
        recommendations=[] if verified else ["Fix constraint"],
    )


def _make_pipeline(
    maci_result: MACIVerificationResult | None = None,
    policy_result: PolicyVerificationResult | None = None,
    saga_success: bool = True,
    transition_success: bool = True,
    config: PipelineConfig | None = None,
) -> VerificationPipeline:
    """Build a pipeline with fully mocked sub-verifiers."""
    if maci_result is None:
        maci_result = _maci_result()
    if policy_result is None:
        policy_result = _policy_result()

    mock_maci = AsyncMock()
    mock_maci.verify = AsyncMock(return_value=maci_result)

    mock_z3 = AsyncMock()
    mock_z3.verify_policy = AsyncMock(return_value=policy_result)

    # Saga mock
    mock_saga_transaction = MagicMock()
    mock_saga_transaction.to_dict.return_value = {"saga_id": "mock-saga", "state": "completed"}
    mock_saga_transaction.failure_reason = None
    mock_saga_coordinator = MagicMock()
    mock_saga_coordinator.create_saga.return_value = mock_saga_transaction
    mock_saga_coordinator.add_step = MagicMock()
    mock_saga_coordinator.execute_saga = AsyncMock(return_value=saga_success)

    # Transition mock
    mock_proof = MagicMock()
    mock_proof.to_dict.return_value = {"proof_type": "mock"}
    mock_transition = MagicMock()
    mock_transition.proofs = [mock_proof]
    mock_transition.to_dict.return_value = {"transition_id": "mock-transition"}
    mock_transition_manager = MagicMock()
    mock_transition_manager.create_transition.return_value = mock_transition
    mock_transition_manager._validate_transition_sequence = AsyncMock(
        return_value=(transition_success, mock_proof)
    )
    mock_transition_manager.transition_to = AsyncMock(return_value=(transition_success, mock_proof))

    return VerificationPipeline(
        config=config or PipelineConfig(),
        maci_verifier=mock_maci,
        z3_verifier=mock_z3,
        saga_coordinator=mock_saga_coordinator,
        transition_manager=mock_transition_manager,
    )


# ---------------------------------------------------------------------------
# PipelineStage enum
# ---------------------------------------------------------------------------


class TestPipelineStageEnum:
    def test_all_stage_values(self):
        assert PipelineStage.INITIALIZATION.value == "initialization"
        assert PipelineStage.MACI_VERIFICATION.value == "maci_verification"
        assert PipelineStage.POLICY_VERIFICATION.value == "policy_verification"
        assert PipelineStage.SAGA_EXECUTION.value == "saga_execution"
        assert PipelineStage.STATE_TRANSITION.value == "state_transition"
        assert PipelineStage.FINALIZATION.value == "finalization"

    def test_stage_count(self):
        assert len(PipelineStage) == 6

    def test_stages_are_unique(self):
        values = [s.value for s in PipelineStage]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# PipelineStatus enum
# ---------------------------------------------------------------------------


class TestPipelineStatusEnum:
    def test_all_status_values(self):
        assert PipelineStatus.PENDING.value == "pending"
        assert PipelineStatus.RUNNING.value == "running"
        assert PipelineStatus.COMPLETED.value == "completed"
        assert PipelineStatus.FAILED.value == "failed"
        assert PipelineStatus.COMPENSATED.value == "compensated"
        assert PipelineStatus.TIMEOUT.value == "timeout"

    def test_status_count(self):
        assert len(PipelineStatus) == 6


# ---------------------------------------------------------------------------
# PipelineConfig
# ---------------------------------------------------------------------------


class TestPipelineConfigExtended:
    def test_default_values(self):
        c = PipelineConfig()
        assert c.enable_maci is True
        assert c.enable_policy_verification is True
        assert c.enable_saga is True
        assert c.enable_state_transitions is True
        assert c.maci_timeout_ms == 10000
        assert c.policy_timeout_ms == 5000
        assert c.saga_timeout_ms == 30000
        assert c.transition_timeout_ms == 5000
        assert c.require_all_stages is False
        assert c.fail_fast is False
        assert c.parallel_verification is False
        assert c.compensation_strategy == CompensationStrategy.LIFO
        assert c.require_proofs is True
        assert c.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(c.metadata, dict)

    def test_custom_timeouts(self):
        c = PipelineConfig(maci_timeout_ms=1000, policy_timeout_ms=2000, saga_timeout_ms=5000)
        assert c.maci_timeout_ms == 1000
        assert c.policy_timeout_ms == 2000
        assert c.saga_timeout_ms == 5000

    def test_to_dict_all_keys(self):
        c = PipelineConfig()
        d = c.to_dict()
        expected_keys = {
            "enable_maci",
            "enable_policy_verification",
            "enable_saga",
            "enable_state_transitions",
            "maci_timeout_ms",
            "policy_timeout_ms",
            "saga_timeout_ms",
            "transition_timeout_ms",
            "require_all_stages",
            "fail_fast",
            "parallel_verification",
            "compensation_strategy",
            "require_proofs",
            "metadata",
            "constitutional_hash",
        }
        assert expected_keys.issubset(set(d.keys()))

    def test_to_dict_compensation_strategy_serialised(self):
        c = PipelineConfig(compensation_strategy=CompensationStrategy.PARALLEL)
        d = c.to_dict()
        assert d["compensation_strategy"] == "parallel"

    def test_require_all_stages_flag(self):
        c = PipelineConfig(require_all_stages=True)
        assert c.require_all_stages is True

    def test_fail_fast_flag(self):
        c = PipelineConfig(fail_fast=True)
        assert c.fail_fast is True

    def test_parallel_verification_flag(self):
        c = PipelineConfig(parallel_verification=True)
        assert c.parallel_verification is True


# ---------------------------------------------------------------------------
# StageResult
# ---------------------------------------------------------------------------


class TestStageResultExtended:
    def test_defaults(self):
        sr = StageResult(stage=PipelineStage.SAGA_EXECUTION, success=True)
        assert sr.status == "completed"
        assert sr.result_data is None
        assert sr.error is None
        assert sr.duration_ms == 0.0
        assert sr.proofs == []
        assert sr.metadata == {}
        assert isinstance(sr.timestamp, datetime)

    def test_to_dict_complete(self):
        sr = StageResult(
            stage=PipelineStage.POLICY_VERIFICATION,
            success=False,
            status="error",
            error="boom",
            duration_ms=12.5,
            proofs=[{"p": 1}],
            metadata={"m": "v"},
        )
        d = sr.to_dict()
        assert d["stage"] == "policy_verification"
        assert d["success"] is False
        assert d["status"] == "error"
        assert d["error"] == "boom"
        assert d["duration_ms"] == 12.5
        assert d["proofs"] == [{"p": 1}]
        assert d["metadata"] == {"m": "v"}
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# PipelineResult
# ---------------------------------------------------------------------------


class TestPipelineResultExtended:
    def test_defaults(self):
        r = PipelineResult()
        assert r.status == PipelineStatus.PENDING
        assert r.is_verified is False
        assert r.confidence == 0.0
        assert r.stage_results == []
        assert r.violations == []
        assert r.warnings == []
        assert r.recommendations == []
        assert r.total_duration_ms == 0.0
        assert r.proofs == []
        assert r.audit_trail == []
        assert r.maci_result is None
        assert r.policy_result is None
        assert r.saga_transaction is None
        assert r.transition is None
        assert r.completed_at is None
        assert r.constitutional_hash == CONSTITUTIONAL_HASH

    def test_pipeline_id_is_unique(self):
        ids = {PipelineResult().pipeline_id for _ in range(10)}
        assert len(ids) == 10

    def test_add_multiple_audit_entries(self):
        r = PipelineResult()
        r.add_audit_entry("stage_a", "action_1", {"k": "v1"})
        r.add_audit_entry("stage_b", "action_2", {"k": "v2"})
        assert len(r.audit_trail) == 2
        assert r.audit_trail[1]["stage"] == "stage_b"

    def test_audit_entry_has_constitutional_hash(self):
        r = PipelineResult()
        r.add_audit_entry("s", "a", {})
        assert r.audit_trail[0]["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_audit_entry_has_timestamp(self):
        r = PipelineResult()
        r.add_audit_entry("s", "a", {})
        ts_str = r.audit_trail[0]["timestamp"]
        # Should be parseable ISO datetime
        datetime.fromisoformat(ts_str)

    def test_to_dict_with_nested_models(self):
        r = PipelineResult(
            status=PipelineStatus.COMPLETED,
            is_verified=True,
            confidence=0.9,
        )
        r.stage_results.append(StageResult(stage=PipelineStage.MACI_VERIFICATION, success=True))
        d = r.to_dict()
        assert d["status"] == "completed"
        assert d["is_verified"] is True
        assert len(d["stage_results"]) == 1

    def test_to_dict_completed_at_present(self):
        r = PipelineResult()
        r.completed_at = datetime.now(UTC)
        d = r.to_dict()
        assert d["completed_at"] is not None

    def test_to_dict_completed_at_none(self):
        r = PipelineResult()
        d = r.to_dict()
        assert d["completed_at"] is None


# ---------------------------------------------------------------------------
# VerificationPipeline init
# ---------------------------------------------------------------------------


class TestVerificationPipelineInit:
    def test_default_init_creates_components(self):
        pipeline = VerificationPipeline()
        assert pipeline.maci_verifier is not None
        assert pipeline.z3_verifier is not None
        assert pipeline.saga_coordinator is not None
        assert pipeline.transition_manager is not None
        assert pipeline.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_config_stored(self):
        cfg = PipelineConfig(enable_maci=False, fail_fast=True)
        pipeline = VerificationPipeline(config=cfg)
        assert pipeline.config.enable_maci is False
        assert pipeline.config.fail_fast is True

    def test_injected_verifiers_used(self):
        mock_maci = MagicMock()
        pipeline = VerificationPipeline(maci_verifier=mock_maci)
        assert pipeline.maci_verifier is mock_maci

    def test_execution_history_starts_empty(self):
        pipeline = VerificationPipeline()
        assert pipeline._execution_history == []


# ---------------------------------------------------------------------------
# create_verification_pipeline factory
# ---------------------------------------------------------------------------


class TestCreateVerificationPipelineFactory:
    def test_factory_returns_pipeline(self):
        p = create_verification_pipeline()
        assert isinstance(p, VerificationPipeline)

    def test_factory_with_config(self):
        cfg = PipelineConfig(enable_maci=False)
        p = create_verification_pipeline(config=cfg)
        assert p.config.enable_maci is False

    def test_factory_without_config(self):
        p = create_verification_pipeline()
        assert p.config.enable_maci is True  # default


# ---------------------------------------------------------------------------
# verify() - happy path with all 4 stages
# ---------------------------------------------------------------------------


class TestVerifyHappyPath:
    async def test_all_stages_enabled_happy_path(self):
        pipeline = _make_pipeline()
        cfg = PipelineConfig(enable_saga=True, enable_state_transitions=True)
        pipeline.config = cfg

        saga_steps = [{"name": "s1", "execute": AsyncMock(return_value={})}]
        result = await pipeline.verify(
            action="test-action",
            context={"key": "val"},
            policy_text="Users must authenticate.",
            saga_steps=saga_steps,
        )
        assert result.status == PipelineStatus.COMPLETED
        assert result.is_verified is True
        assert result.total_duration_ms >= 0
        assert result.completed_at is not None

    async def test_result_has_pipeline_id(self):
        pipeline = _make_pipeline()
        result = await pipeline.verify("action", {"k": "v"})
        assert result.pipeline_id is not None
        assert len(result.pipeline_id) > 0

    async def test_result_confidence_in_range(self):
        pipeline = _make_pipeline()
        result = await pipeline.verify("action", {})
        assert 0.0 <= result.confidence <= 1.0

    async def test_maci_result_populated(self):
        pipeline = _make_pipeline()
        result = await pipeline.verify("action", {})
        assert result.maci_result is not None
        assert result.maci_result.is_compliant is True

    async def test_policy_result_populated_when_policy_text_given(self):
        cfg = PipelineConfig(enable_maci=False, enable_saga=False, enable_state_transitions=False)
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("action", {}, policy_text="must encrypt data")
        assert result.policy_result is not None

    async def test_saga_transaction_populated(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        saga_steps = [{"name": "s", "execute": AsyncMock(return_value={})}]
        result = await pipeline.verify("action", {}, saga_steps=saga_steps)
        assert result.saga_transaction is not None

    async def test_transition_populated(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=False,
        )
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("action", {})
        assert result.transition is not None


# ---------------------------------------------------------------------------
# verify() - selective stages
# ---------------------------------------------------------------------------


class TestVerifySelectiveStages:
    async def test_only_maci_stage_runs(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("a", {})
        stages = [s.stage for s in result.stage_results]
        assert PipelineStage.MACI_VERIFICATION in stages
        assert PipelineStage.POLICY_VERIFICATION not in stages
        assert PipelineStage.SAGA_EXECUTION not in stages
        assert PipelineStage.STATE_TRANSITION not in stages

    async def test_only_policy_stage_runs(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=True,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("a", {}, policy_text="must do X")
        stages = [s.stage for s in result.stage_results]
        assert PipelineStage.POLICY_VERIFICATION in stages
        assert PipelineStage.MACI_VERIFICATION not in stages

    async def test_only_saga_stage_runs(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=True,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        saga_steps = [{"name": "s", "execute": AsyncMock(return_value={})}]
        result = await pipeline.verify("a", {}, saga_steps=saga_steps)
        stages = [s.stage for s in result.stage_results]
        assert PipelineStage.SAGA_EXECUTION in stages
        assert PipelineStage.MACI_VERIFICATION not in stages

    async def test_only_transition_stage_runs(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=True,
        )
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("a", {})
        stages = [s.stage for s in result.stage_results]
        assert PipelineStage.STATE_TRANSITION in stages
        assert PipelineStage.MACI_VERIFICATION not in stages

    async def test_no_stages_enabled(self):
        """When all stages are disabled the result has zero stage_results."""
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("a", {})
        assert result.stage_results == []

    async def test_policy_stage_skipped_when_no_policy_text(self):
        """Policy stage needs policy_text to execute."""
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=True,  # enabled but no policy_text provided
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("a", {})  # no policy_text kwarg
        stages = [s.stage for s in result.stage_results]
        assert PipelineStage.POLICY_VERIFICATION not in stages

    async def test_saga_stage_skipped_when_no_steps(self):
        """Saga stage needs saga_steps to execute."""
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=True,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("a", {})  # no saga_steps
        stages = [s.stage for s in result.stage_results]
        assert PipelineStage.SAGA_EXECUTION not in stages


# ---------------------------------------------------------------------------
# verify() - MACI blocked scenario
# ---------------------------------------------------------------------------


class TestVerifyMACIBlocked:
    async def test_maci_non_compliant_adds_violations(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(maci_result=_maci_result(compliant=False), config=cfg)
        result = await pipeline.verify("blocked-action", {})
        assert len(result.violations) > 0

    async def test_maci_non_compliant_with_fail_fast(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=True,
            fail_fast=True,
        )
        pipeline = _make_pipeline(maci_result=_maci_result(compliant=False), config=cfg)
        result = await pipeline.verify("blocked", {}, policy_text="must X")
        assert result.status == PipelineStatus.FAILED

    async def test_maci_non_compliant_includes_recommendations(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(maci_result=_maci_result(compliant=False), config=cfg)
        result = await pipeline.verify("action", {})
        assert isinstance(result.recommendations, list)


# ---------------------------------------------------------------------------
# verify() - Z3 constraint violation
# ---------------------------------------------------------------------------


class TestVerifyZ3Violation:
    async def test_z3_unverified_adds_violations(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=True,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(policy_result=_policy_result(verified=False), config=cfg)
        result = await pipeline.verify("action", {}, policy_text="constraint-fails")
        assert len(result.violations) > 0

    async def test_z3_policy_stage_marked_failed(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=True,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(policy_result=_policy_result(verified=False), config=cfg)
        result = await pipeline.verify("action", {}, policy_text="fails")
        policy_stage = next(
            (s for s in result.stage_results if s.stage == PipelineStage.POLICY_VERIFICATION),
            None,
        )
        assert policy_stage is not None
        assert policy_stage.success is False

    async def test_z3_no_proof_object(self):
        """PolicyVerificationResult without a proof still works."""
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=True,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(
            policy_result=_policy_result(verified=True, with_proof=False),
            config=cfg,
        )
        result = await pipeline.verify("action", {}, policy_text="no proof")
        # Stage should still succeed
        policy_stage = next(
            (s for s in result.stage_results if s.stage == PipelineStage.POLICY_VERIFICATION),
            None,
        )
        assert policy_stage is not None
        assert policy_stage.success is True

    async def test_z3_proof_without_heuristic_score(self):
        """Confidence path: proof present, is_verified=True, no heuristic_score."""
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=True,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(
            policy_result=_policy_result(verified=True, with_proof=True, heuristic_score=None),
            config=cfg,
        )
        result = await pipeline.verify("action", {}, policy_text="data must be encrypted")
        assert result.confidence >= 0.0

    async def test_z3_proof_not_verified_without_heuristic(self):
        """Confidence path: proof present, is_verified=False, no heuristic_score."""
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=True,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(
            policy_result=_policy_result(verified=False, with_proof=True, heuristic_score=None),
            config=cfg,
        )
        result = await pipeline.verify("action", {}, policy_text="fails")
        assert result.confidence >= 0.0


# ---------------------------------------------------------------------------
# verify() - Saga compensation triggered
# ---------------------------------------------------------------------------


class TestVerifySagaCompensation:
    async def test_saga_failure_sets_compensated_status(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=True,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(saga_success=False, config=cfg)
        pipeline.saga_coordinator.execute_saga = AsyncMock(return_value=False)
        # Also set failure_reason
        pipeline.saga_coordinator.create_saga.return_value.failure_reason = "step failed"
        pipeline.saga_coordinator.create_saga.return_value.to_dict.return_value = {
            "state": "compensated"
        }
        saga_steps = [{"name": "s", "execute": AsyncMock(return_value={})}]
        result = await pipeline.verify("action", {}, saga_steps=saga_steps)
        assert len(result.violations) > 0

    async def test_saga_stage_result_compensated_status(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=True,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(saga_success=False, config=cfg)
        pipeline.saga_coordinator.execute_saga = AsyncMock(return_value=False)
        pipeline.saga_coordinator.create_saga.return_value.failure_reason = None
        pipeline.saga_coordinator.create_saga.return_value.to_dict.return_value = {}
        saga_steps = [{"name": "s", "execute": AsyncMock(return_value={})}]
        result = await pipeline.verify("action", {}, saga_steps=saga_steps)
        saga_stage = next(
            (s for s in result.stage_results if s.stage == PipelineStage.SAGA_EXECUTION),
            None,
        )
        assert saga_stage is not None
        assert saga_stage.status == "compensated"

    async def test_saga_fail_fast_stops_pipeline(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=True,
            enable_state_transitions=True,
            fail_fast=True,
        )
        pipeline = _make_pipeline(saga_success=False, config=cfg)
        pipeline.saga_coordinator.execute_saga = AsyncMock(return_value=False)
        pipeline.saga_coordinator.create_saga.return_value.failure_reason = None
        pipeline.saga_coordinator.create_saga.return_value.to_dict.return_value = {}
        saga_steps = [{"name": "s", "execute": AsyncMock(return_value={})}]
        result = await pipeline.verify("action", {}, saga_steps=saga_steps)
        assert result.status == PipelineStatus.COMPENSATED
        # State transition should NOT have run
        stages = [s.stage for s in result.stage_results]
        assert PipelineStage.STATE_TRANSITION not in stages


# ---------------------------------------------------------------------------
# verify() - State transition rejected
# ---------------------------------------------------------------------------


class TestVerifyTransitionRejected:
    async def test_transition_failure_marks_stage_failed(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=True,
        )
        pipeline = _make_pipeline(transition_success=False, config=cfg)
        result = await pipeline.verify("action", {})
        transition_stage = next(
            (s for s in result.stage_results if s.stage == PipelineStage.STATE_TRANSITION),
            None,
        )
        assert transition_stage is not None
        assert transition_stage.success is False
        assert transition_stage.status == "failed"


# ---------------------------------------------------------------------------
# verify() - require_all_stages
# ---------------------------------------------------------------------------


class TestVerifyRequireAllStages:
    async def test_require_all_stages_passes_when_all_succeed(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
            require_all_stages=True,
        )
        pipeline = _make_pipeline(maci_result=_maci_result(compliant=True), config=cfg)
        result = await pipeline.verify("action", {})
        assert result.is_verified is True

    async def test_require_all_stages_fails_when_one_fails(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
            require_all_stages=True,
        )
        pipeline = _make_pipeline(maci_result=_maci_result(compliant=False), config=cfg)
        result = await pipeline.verify("action", {})
        assert result.is_verified is False

    async def test_require_all_stages_false_passes_with_one_success(self):
        """Default: any stage passing is enough."""
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
            require_all_stages=False,
        )
        pipeline = _make_pipeline(maci_result=_maci_result(compliant=True), config=cfg)
        result = await pipeline.verify("action", {})
        assert result.is_verified is True


# ---------------------------------------------------------------------------
# verify() - error handling
# ---------------------------------------------------------------------------


class TestVerifyErrorHandling:
    async def test_maci_stage_runtime_error_sets_failed(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        pipeline.maci_verifier.verify = AsyncMock(side_effect=RuntimeError("maci crash"))
        result = await pipeline.verify("action", {})
        # The stage-level error handler should catch it
        maci_stage = next(
            (s for s in result.stage_results if s.stage == PipelineStage.MACI_VERIFICATION),
            None,
        )
        assert maci_stage is not None
        assert maci_stage.success is False
        assert maci_stage.status == "error"

    async def test_policy_stage_runtime_error(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=True,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        pipeline.z3_verifier.verify_policy = AsyncMock(side_effect=ValueError("z3 crash"))
        result = await pipeline.verify("action", {}, policy_text="something")
        policy_stage = next(
            (s for s in result.stage_results if s.stage == PipelineStage.POLICY_VERIFICATION),
            None,
        )
        assert policy_stage is not None
        assert policy_stage.success is False
        assert policy_stage.status == "error"

    async def test_saga_stage_runtime_error(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=True,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        pipeline.saga_coordinator.execute_saga = AsyncMock(side_effect=RuntimeError("saga crash"))
        pipeline.saga_coordinator.create_saga.return_value.to_dict.return_value = {}
        saga_steps = [{"name": "s", "execute": AsyncMock(return_value={})}]
        result = await pipeline.verify("action", {}, saga_steps=saga_steps)
        saga_stage = next(
            (s for s in result.stage_results if s.stage == PipelineStage.SAGA_EXECUTION),
            None,
        )
        assert saga_stage is not None
        assert saga_stage.success is False
        assert saga_stage.status == "error"

    async def test_transition_stage_runtime_error(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=True,
        )
        pipeline = _make_pipeline(config=cfg)
        pipeline.transition_manager.create_transition.side_effect = RuntimeError("transition crash")
        result = await pipeline.verify("action", {})
        transition_stage = next(
            (s for s in result.stage_results if s.stage == PipelineStage.STATE_TRANSITION),
            None,
        )
        assert transition_stage is not None
        assert transition_stage.success is False
        assert transition_stage.status == "error"

    async def test_pipeline_level_value_error_sets_failed(self):
        """A ValueError raised outside stage handlers is caught by the pipeline."""
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)

        # Patch _execute_maci_stage to raise ValueError
        original_maci = pipeline._execute_maci_stage

        async def raise_value_error(*args, **kwargs):
            raise ValueError("pipeline-level error")

        pipeline._execute_maci_stage = raise_value_error
        result = await pipeline.verify("action", {})
        assert result.status == PipelineStatus.FAILED
        assert any(v["type"] == "pipeline_error" for v in result.violations)

    async def test_pipeline_level_timeout_sets_timeout_status(self):
        """asyncio.TimeoutError at pipeline level sets TIMEOUT status."""
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)

        async def raise_timeout(*args, **kwargs):
            raise TimeoutError

        pipeline._execute_maci_stage = raise_timeout
        result = await pipeline.verify("action", {})
        assert result.status == PipelineStatus.TIMEOUT
        assert any(v["type"] == "pipeline_timeout" for v in result.violations)


# ---------------------------------------------------------------------------
# verify() - stage-level timeouts
# ---------------------------------------------------------------------------


class TestVerifyStageLevelTimeouts:
    async def test_maci_stage_timeout(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
            maci_timeout_ms=1,
        )
        pipeline = _make_pipeline(config=cfg)

        async def slow_maci(*args, **kwargs):
            await asyncio.sleep(5)
            return _maci_result()

        pipeline.maci_verifier.verify = slow_maci
        result = await pipeline.verify("action", {})
        maci_stage = next(
            (s for s in result.stage_results if s.stage == PipelineStage.MACI_VERIFICATION),
            None,
        )
        assert maci_stage is not None
        assert maci_stage.status == "timeout"

    async def test_policy_stage_timeout(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=True,
            enable_saga=False,
            enable_state_transitions=False,
            policy_timeout_ms=1,
        )
        pipeline = _make_pipeline(config=cfg)

        async def slow_policy(*args, **kwargs):
            await asyncio.sleep(5)
            return _policy_result()

        pipeline.z3_verifier.verify_policy = slow_policy
        result = await pipeline.verify("action", {}, policy_text="slow policy")
        policy_stage = next(
            (s for s in result.stage_results if s.stage == PipelineStage.POLICY_VERIFICATION),
            None,
        )
        assert policy_stage is not None
        assert policy_stage.status == "timeout"

    async def test_saga_stage_timeout(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=True,
            enable_state_transitions=False,
            saga_timeout_ms=1,
        )
        pipeline = _make_pipeline(config=cfg)

        async def slow_saga(*args, **kwargs):
            await asyncio.sleep(5)
            return True

        pipeline.saga_coordinator.execute_saga = slow_saga
        pipeline.saga_coordinator.create_saga.return_value.to_dict.return_value = {}
        saga_steps = [{"name": "s", "execute": AsyncMock(return_value={})}]
        result = await pipeline.verify("action", {}, saga_steps=saga_steps)
        saga_stage = next(
            (s for s in result.stage_results if s.stage == PipelineStage.SAGA_EXECUTION),
            None,
        )
        assert saga_stage is not None
        assert saga_stage.status == "timeout"


# ---------------------------------------------------------------------------
# get_pipeline_stats()
# ---------------------------------------------------------------------------


class TestGetPipelineStats:
    def test_empty_stats(self):
        pipeline = _make_pipeline()
        stats = pipeline.get_pipeline_stats()
        assert stats == {"total_executions": 0}

    async def test_single_execution_stats(self):
        pipeline = _make_pipeline()
        await pipeline.verify("a", {})
        stats = pipeline.get_pipeline_stats()
        assert stats["total_executions"] == 1
        assert "verified_count" in stats
        assert "verification_rate" in stats
        assert "average_duration_ms" in stats
        assert "average_confidence" in stats
        assert "constitutional_hash" in stats
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_multiple_executions_stats(self):
        pipeline = _make_pipeline()
        await pipeline.verify("a", {})
        await pipeline.verify("b", {})
        await pipeline.verify("c", {})
        stats = pipeline.get_pipeline_stats()
        assert stats["total_executions"] == 3
        assert "status_distribution" in stats
        assert isinstance(stats["status_distribution"], dict)

    async def test_verification_rate_calculation(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(maci_result=_maci_result(compliant=True), config=cfg)
        await pipeline.verify("a", {})
        await pipeline.verify("b", {})
        stats = pipeline.get_pipeline_stats()
        assert 0.0 <= stats["verification_rate"] <= 1.0


# ---------------------------------------------------------------------------
# quick_verify()
# ---------------------------------------------------------------------------


class TestQuickVerifyExtended:
    async def test_quick_verify_returns_tuple(self):
        pipeline = _make_pipeline()
        is_verified, confidence, violations = await pipeline.quick_verify("action", {})
        assert isinstance(is_verified, bool)
        assert isinstance(confidence, float)
        assert isinstance(violations, list)

    async def test_quick_verify_delegates_to_maci(self):
        pipeline = _make_pipeline(maci_result=_maci_result(compliant=True, confidence=0.95))
        is_verified, confidence, _violations = await pipeline.quick_verify("action", {})
        assert is_verified is True
        assert confidence == 0.95

    async def test_quick_verify_non_compliant(self):
        pipeline = _make_pipeline(maci_result=_maci_result(compliant=False, confidence=0.2))
        is_verified, _confidence, violations = await pipeline.quick_verify("bad-action", {})
        assert is_verified is False
        assert len(violations) > 0


# ---------------------------------------------------------------------------
# get_constitutional_hash()
# ---------------------------------------------------------------------------


class TestGetConstitutionalHash:
    def test_returns_correct_hash(self):
        pipeline = _make_pipeline()
        assert pipeline.get_constitutional_hash() == CONSTITUTIONAL_HASH

    def test_hash_matches_module_constant(self):
        pipeline = _make_pipeline()
        assert pipeline.get_constitutional_hash() == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


class TestAuditTrail:
    async def test_audit_trail_contains_initialization(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("action", {"ctx_key": "val"})
        init_entries = [e for e in result.audit_trail if e["stage"] == "initialization"]
        assert len(init_entries) >= 1

    async def test_audit_trail_contains_finalization(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("action", {})
        final_entries = [e for e in result.audit_trail if e["stage"] == "finalization"]
        assert len(final_entries) >= 1

    async def test_audit_trail_maci_entries(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("action", {})
        maci_entries = [e for e in result.audit_trail if e["stage"] == "maci_verification"]
        assert len(maci_entries) >= 2  # start + complete

    async def test_audit_trail_policy_entries(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=True,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("action", {}, policy_text="must auth")
        policy_entries = [e for e in result.audit_trail if e["stage"] == "policy_verification"]
        assert len(policy_entries) >= 2  # start + complete

    async def test_audit_trail_saga_entries(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=True,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        saga_steps = [{"name": "s", "execute": AsyncMock(return_value={})}]
        result = await pipeline.verify("action", {}, saga_steps=saga_steps)
        saga_entries = [e for e in result.audit_trail if e["stage"] == "saga_execution"]
        assert len(saga_entries) >= 2  # start + complete

    async def test_audit_trail_transition_entries(self):
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=True,
        )
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("action", {})
        transition_entries = [e for e in result.audit_trail if e["stage"] == "state_transition"]
        assert len(transition_entries) >= 2  # start + complete

    async def test_audit_trail_all_entries_have_hash(self):
        pipeline = _make_pipeline()
        result = await pipeline.verify("action", {})
        for entry in result.audit_trail:
            assert entry["constitutional_hash"] == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# Concurrent verification requests
# ---------------------------------------------------------------------------


class TestConcurrentVerification:
    async def test_concurrent_verifications_produce_distinct_results(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)

        results = await asyncio.gather(
            pipeline.verify("action-1", {"idx": 1}),
            pipeline.verify("action-2", {"idx": 2}),
            pipeline.verify("action-3", {"idx": 3}),
        )
        pipeline_ids = [r.pipeline_id for r in results]
        assert len(pipeline_ids) == len(set(pipeline_ids))

    async def test_concurrent_verifications_all_complete(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)

        results = await asyncio.gather(
            pipeline.verify("a", {}),
            pipeline.verify("b", {}),
            pipeline.verify("c", {}),
            pipeline.verify("d", {}),
            pipeline.verify("e", {}),
        )
        for r in results:
            assert r.completed_at is not None
            assert r.total_duration_ms >= 0


# ---------------------------------------------------------------------------
# Recommendations generation
# ---------------------------------------------------------------------------


class TestRecommendationsGeneration:
    async def test_recommendations_for_timeout_stage(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
            maci_timeout_ms=1,
        )
        pipeline = _make_pipeline(config=cfg)

        async def slow_maci(*args, **kwargs):
            await asyncio.sleep(5)
            return _maci_result()

        pipeline.maci_verifier.verify = slow_maci
        result = await pipeline.verify("action", {})
        # Timeout stage recommendation should be present
        assert any("timeout" in r.lower() for r in result.recommendations)

    async def test_recommendations_not_verified(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(maci_result=_maci_result(compliant=False), config=cfg)
        result = await pipeline.verify("action", {})
        assert any("violations" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# _compute_confidence edge cases
# ---------------------------------------------------------------------------


class TestComputeConfidenceEdgeCases:
    async def test_confidence_no_results(self):
        """No stages run → confidence 0.0."""
        cfg = PipelineConfig(
            enable_maci=False,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(config=cfg)
        result = await pipeline.verify("action", {})
        assert result.confidence == 0.0

    async def test_confidence_with_maci_only(self):
        cfg = PipelineConfig(
            enable_maci=True,
            enable_policy_verification=False,
            enable_saga=False,
            enable_state_transitions=False,
        )
        pipeline = _make_pipeline(
            maci_result=_maci_result(compliant=True, confidence=0.75), config=cfg
        )
        result = await pipeline.verify("action", {})
        assert result.confidence > 0.0
