"""
Coverage tests for batch 20f:
- enhanced_agent_bus.llm_adapters.anthropic_adapter
- enhanced_agent_bus.governance.democratic_governance
- enhanced_agent_bus.adaptive_governance.amendment_recommender
- enhanced_agent_bus.saga_persistence.models

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── adaptive_governance.amendment_recommender ───────────────────────────
from enhanced_agent_bus.adaptive_governance.amendment_recommender import (
    AmendmentRecommendation,
    AmendmentRecommender,
    RecommendationPriority,
    RecommendationTrigger,
)

# ── governance.democratic_governance ────────────────────────────────────
from enhanced_agent_bus.governance.democratic_governance import (
    DemocraticConstitutionalGovernance,
    deliberate_on_proposal,
    get_ccai_governance,
)
from enhanced_agent_bus.governance.models import (
    OpinionCluster,
    Stakeholder,
    StakeholderGroup,
)

# ── llm_adapters.anthropic_adapter ──────────────────────────────────────
from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter
from enhanced_agent_bus.llm_adapters.base import (
    AdapterStatus,
    CostEstimate,
    HealthCheckResult,
    LLMMessage,
    LLMResponse,
    StreamingMode,
    TokenUsage,
)
from enhanced_agent_bus.llm_adapters.config import AnthropicAdapterConfig

# ── saga_persistence.models ─────────────────────────────────────────────
from enhanced_agent_bus.saga_persistence.models import (
    CompensationEntry,
    CompensationStrategy,
    PersistedSagaState,
    PersistedStepSnapshot,
    SagaCheckpoint,
    SagaState,
    StepState,
)

# =====================================================================
# Helpers
# =====================================================================


def _make_adapter(**overrides: Any) -> AnthropicAdapter:
    """Build an AnthropicAdapter with sensible test defaults."""
    defaults: dict[str, Any] = {
        "model": "claude-sonnet-4-6",
        "api_key": "test-key-123",
    }
    defaults.update(overrides)
    return AnthropicAdapter(**defaults)


def _user_msg(content: str = "hello") -> LLMMessage:
    return LLMMessage(role="user", content=content)


def _system_msg(content: str = "You are helpful.") -> LLMMessage:
    return LLMMessage(role="system", content=content)


def _mock_anthropic_response_dict() -> dict:
    return {
        "id": "msg_test123",
        "type": "message",
        "model": "claude-sonnet-4-6",
        "content": [{"type": "text", "text": "Hello back!"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def _make_stakeholder(
    group: StakeholderGroup = StakeholderGroup.TECHNICAL_EXPERTS,
    name: str | None = None,
) -> Stakeholder:
    return Stakeholder(
        stakeholder_id=str(uuid.uuid4()),
        name=name or f"test-{group.value}",
        group=group,
        expertise_areas=[group.value],
    )


# =====================================================================
# SAGA PERSISTENCE MODELS
# =====================================================================


class TestSagaState:
    def test_is_terminal_states(self):
        assert SagaState.COMPLETED.is_terminal() is True
        assert SagaState.COMPENSATED.is_terminal() is True
        assert SagaState.FAILED.is_terminal() is True
        assert SagaState.INITIALIZED.is_terminal() is False
        assert SagaState.RUNNING.is_terminal() is False
        assert SagaState.COMPENSATING.is_terminal() is False

    def test_allows_compensation(self):
        assert SagaState.RUNNING.allows_compensation() is True
        assert SagaState.COMPENSATING.allows_compensation() is True
        assert SagaState.COMPLETED.allows_compensation() is False
        assert SagaState.INITIALIZED.allows_compensation() is False
        assert SagaState.FAILED.allows_compensation() is False


class TestStepState:
    def test_is_terminal(self):
        assert StepState.COMPLETED.is_terminal() is True
        assert StepState.FAILED.is_terminal() is True
        assert StepState.COMPENSATED.is_terminal() is True
        assert StepState.SKIPPED.is_terminal() is True
        assert StepState.PENDING.is_terminal() is False
        assert StepState.RUNNING.is_terminal() is False

    def test_requires_compensation(self):
        assert StepState.COMPLETED.requires_compensation() is True
        assert StepState.FAILED.requires_compensation() is False
        assert StepState.PENDING.requires_compensation() is False


class TestCompensationEntry:
    def test_to_dict_without_executed_at(self):
        entry = CompensationEntry(step_id="s1", step_name="step1")
        d = entry.to_dict()
        assert d["step_id"] == "s1"
        assert d["step_name"] == "step1"
        assert d["executed"] is False
        assert d["executed_at"] is None

    def test_to_dict_with_executed_at(self):
        now = datetime.now(UTC)
        entry = CompensationEntry(
            step_id="s1",
            step_name="step1",
            executed=True,
            executed_at=now,
            duration_ms=42.5,
            result={"ok": True},
            error=None,
            retry_count=2,
            max_retries=5,
        )
        d = entry.to_dict()
        assert d["executed"] is True
        assert d["executed_at"] == now.isoformat()
        assert d["duration_ms"] == 42.5
        assert d["retry_count"] == 2

    def test_from_dict_full(self):
        now = datetime.now(UTC)
        data = {
            "compensation_id": "c-1",
            "step_id": "s1",
            "step_name": "step1",
            "executed": True,
            "executed_at": now.isoformat(),
            "duration_ms": 10.0,
            "result": "ok",
            "error": "err",
            "retry_count": 1,
            "max_retries": 3,
            "constitutional_hash": "test-hash",
        }
        entry = CompensationEntry.from_dict(data)
        assert entry.compensation_id == "c-1"
        assert entry.executed is True
        assert entry.error == "err"
        assert entry.constitutional_hash == "test-hash"

    def test_from_dict_minimal(self):
        entry = CompensationEntry.from_dict({})
        assert entry.step_id == ""
        assert entry.executed is False
        assert entry.executed_at is None


class TestPersistedStepSnapshot:
    def test_to_dict_roundtrip(self):
        now = datetime.now(UTC)
        comp = CompensationEntry(step_id="s1", step_name="step1")
        snap = PersistedStepSnapshot(
            step_id="snap-1",
            step_name="test-step",
            step_index=2,
            state=StepState.COMPLETED,
            input_data={"key": "val"},
            output_data={"result": 42},
            started_at=now,
            completed_at=now,
            duration_ms=100.0,
            dependencies=["dep-1"],
            compensation=comp,
            metadata={"m": 1},
        )
        d = snap.to_dict()
        assert d["step_id"] == "snap-1"
        assert d["state"] == "COMPLETED"
        assert d["compensation"] is not None
        assert d["dependencies"] == ["dep-1"]

        restored = PersistedStepSnapshot.from_dict(d)
        assert restored.step_id == "snap-1"
        assert restored.state == StepState.COMPLETED
        assert restored.compensation is not None

    def test_from_dict_minimal(self):
        snap = PersistedStepSnapshot.from_dict({})
        assert snap.state == StepState.PENDING
        assert snap.dependencies == []
        assert snap.compensation is None

    def test_from_dict_non_list_dependencies(self):
        snap = PersistedStepSnapshot.from_dict({"dependencies": "not-a-list"})
        assert snap.dependencies == []

    def test_from_dict_string_compensation(self):
        snap = PersistedStepSnapshot.from_dict({"compensation": "not-a-dict"})
        assert snap.compensation is None


class TestPersistedSagaState:
    def _make_saga(self, **kwargs: Any) -> PersistedSagaState:
        defaults = {
            "saga_id": "saga-1",
            "saga_name": "test-saga",
            "tenant_id": "t1",
            "state": SagaState.RUNNING,
        }
        defaults.update(kwargs)
        return PersistedSagaState(**defaults)

    def test_to_dict_and_from_dict_roundtrip(self):
        now = datetime.now(UTC)
        step = PersistedStepSnapshot(step_id="s1", state=StepState.COMPLETED)
        comp_log = CompensationEntry(step_id="s1", step_name="step1")
        saga = self._make_saga(
            steps=[step],
            compensation_log=[comp_log],
            started_at=now,
            completed_at=now,
            failed_at=now,
            compensated_at=now,
            failure_reason="test failure",
            compensation_strategy=CompensationStrategy.PARALLEL,
        )
        d = saga.to_dict()
        assert d["state"] == "RUNNING"
        assert d["compensation_strategy"] == "PARALLEL"
        assert len(d["steps"]) == 1

        restored = PersistedSagaState.from_dict(d)
        assert restored.saga_id == "saga-1"
        assert restored.state == SagaState.RUNNING
        assert len(restored.steps) == 1
        assert len(restored.compensation_log) == 1
        assert restored.failure_reason == "test failure"

    def test_from_dict_with_non_list_steps(self):
        saga = PersistedSagaState.from_dict({"steps": "bad", "compensation_log": "bad"})
        assert saga.steps == []
        assert saga.compensation_log == []

    def test_from_dict_with_non_dict_step_items(self):
        saga = PersistedSagaState.from_dict({"steps": ["not-a-dict", {"step_id": "s1"}]})
        assert len(saga.steps) == 1

    def test_properties(self):
        steps = [
            PersistedStepSnapshot(step_id="a", state=StepState.COMPLETED),
            PersistedStepSnapshot(step_id="b", state=StepState.PENDING),
            PersistedStepSnapshot(step_id="c", state=StepState.FAILED),
        ]
        saga = self._make_saga(steps=steps)
        assert len(saga.completed_steps) == 1
        assert len(saga.pending_steps) == 1
        assert len(saga.failed_steps) == 1

    def test_is_terminal(self):
        saga_running = self._make_saga(state=SagaState.RUNNING)
        assert saga_running.is_terminal is False
        saga_done = self._make_saga(state=SagaState.COMPLETED)
        assert saga_done.is_terminal is True

    def test_increment_version(self):
        saga = self._make_saga(version=3)
        new_saga = saga.increment_version()
        assert new_saga.version == 4
        assert new_saga.saga_id == saga.saga_id

    def test_to_redis_hash_and_from_redis_hash(self):
        now = datetime.now(UTC)
        step = PersistedStepSnapshot(step_id="s1", state=StepState.COMPLETED)
        comp = CompensationEntry(step_id="s1")
        saga = self._make_saga(
            steps=[step],
            compensation_log=[comp],
            started_at=now,
            completed_at=now,
            failed_at=now,
            compensated_at=now,
            failure_reason="oops",
            context={"ctx": 1},
            metadata={"md": 2},
        )
        redis_hash = saga.to_redis_hash()
        assert isinstance(redis_hash["steps"], str)
        assert isinstance(redis_hash["current_step_index"], str)

        restored = PersistedSagaState.from_redis_hash(redis_hash)
        assert restored.saga_id == "saga-1"
        assert restored.state == SagaState.RUNNING
        assert len(restored.steps) == 1
        assert restored.context == {"ctx": 1}
        assert restored.failure_reason == "oops"

    def test_from_redis_hash_empty_strings(self):
        data = {
            "saga_id": "s1",
            "saga_name": "",
            "tenant_id": "",
            "correlation_id": "c1",
            "state": "INITIALIZED",
            "compensation_strategy": "LIFO",
            "steps": "[]",
            "current_step_index": "0",
            "context": "{}",
            "metadata": "{}",
            "compensation_log": "[]",
            "created_at": datetime.now(UTC).isoformat(),
            "started_at": "",
            "completed_at": "",
            "failed_at": "",
            "compensated_at": "",
            "total_duration_ms": "0.0",
            "failure_reason": "",
            "timeout_ms": "300000",
            "version": "1",
            "constitutional_hash": "test",
        }
        saga = PersistedSagaState.from_redis_hash(data)
        assert saga.started_at is None
        assert saga.failure_reason is None


class TestSagaCheckpoint:
    def test_to_dict_and_from_dict(self):
        now = datetime.now(UTC)
        cp = SagaCheckpoint(
            checkpoint_id="cp-1",
            saga_id="s-1",
            checkpoint_name="before-irreversible",
            state_snapshot={"key": "val"},
            completed_step_ids=["s1", "s2"],
            pending_step_ids=["s3"],
            created_at=now,
            is_constitutional=True,
            metadata={"m": 1},
        )
        d = cp.to_dict()
        assert d["is_constitutional"] is True
        assert d["completed_step_ids"] == ["s1", "s2"]

        restored = SagaCheckpoint.from_dict(d)
        assert restored.checkpoint_id == "cp-1"
        assert restored.is_constitutional is True

    def test_from_dict_non_list_ids(self):
        cp = SagaCheckpoint.from_dict(
            {
                "completed_step_ids": "not-a-list",
                "pending_step_ids": 123,
            }
        )
        assert cp.completed_step_ids == []
        assert cp.pending_step_ids == []

    def test_from_dict_no_snapshot(self):
        cp = SagaCheckpoint.from_dict({})
        assert cp.state_snapshot == {}
        assert cp.metadata == {}


# =====================================================================
# AMENDMENT RECOMMENDER
# =====================================================================


class TestRecommendationEnums:
    def test_trigger_values(self):
        assert RecommendationTrigger.DTMC_RISK_THRESHOLD == "dtmc_risk_threshold"
        assert RecommendationTrigger.THRESHOLD_DRIFT == "threshold_drift"
        assert RecommendationTrigger.DEGRADATION_PATTERN == "degradation_pattern"
        assert RecommendationTrigger.FEEDBACK_SIGNAL == "feedback_signal"

    def test_priority_values(self):
        assert RecommendationPriority.CRITICAL == "critical"
        assert RecommendationPriority.HIGH == "high"
        assert RecommendationPriority.MEDIUM == "medium"
        assert RecommendationPriority.LOW == "low"


class TestAmendmentRecommendation:
    def test_defaults(self):
        rec = AmendmentRecommendation(
            recommendation_id="R1",
            trigger=RecommendationTrigger.DTMC_RISK_THRESHOLD,
            priority=RecommendationPriority.HIGH,
            target_area="governance.high_risk",
            proposed_changes={"action": "tighten"},
            justification="risk too high",
        )
        assert rec.risk_score == 0.0
        assert rec.cooldown_until is None
        assert isinstance(rec.created_at, datetime)
        assert rec.evidence == {}


class TestAmendmentRecommender:
    def test_below_threshold_returns_none(self):
        recommender = AmendmentRecommender(risk_threshold=0.8)
        result = recommender.evaluate_risk_signal(0.5, [0, 1])
        assert result is None

    def test_above_threshold_generates_recommendation(self):
        recommender = AmendmentRecommender(risk_threshold=0.8)
        result = recommender.evaluate_risk_signal(0.9, [3])
        assert result is not None
        assert result.trigger == RecommendationTrigger.DTMC_RISK_THRESHOLD
        assert result.priority == RecommendationPriority.HIGH
        assert result.target_area == "governance.high_risk"

    def test_critical_priority(self):
        recommender = AmendmentRecommender(risk_threshold=0.8)
        result = recommender.evaluate_risk_signal(0.96, [4])
        assert result is not None
        assert result.priority == RecommendationPriority.CRITICAL

    def test_medium_priority(self):
        recommender = AmendmentRecommender(risk_threshold=0.4)
        result = recommender.evaluate_risk_signal(0.6, [2])
        assert result is not None
        assert result.priority == RecommendationPriority.MEDIUM

    def test_low_priority(self):
        recommender = AmendmentRecommender(risk_threshold=0.1)
        result = recommender.evaluate_risk_signal(0.3, [0])
        assert result is not None
        assert result.priority == RecommendationPriority.LOW

    def test_context_target_area_override(self):
        recommender = AmendmentRecommender(risk_threshold=0.5)
        result = recommender.evaluate_risk_signal(0.9, [3], context={"target_area": "custom.area"})
        assert result is not None
        assert result.target_area == "custom.area"

    def test_empty_trajectory_prefix(self):
        recommender = AmendmentRecommender(risk_threshold=0.5)
        result = recommender.evaluate_risk_signal(0.9, [])
        assert result is not None
        assert result.target_area == "governance.general"

    def test_unknown_state_in_trajectory(self):
        recommender = AmendmentRecommender(risk_threshold=0.5)
        result = recommender.evaluate_risk_signal(0.9, [99])
        assert result is not None
        assert result.target_area == "governance.general"

    def test_cooldown_prevents_duplicate(self):
        recommender = AmendmentRecommender(risk_threshold=0.5, cooldown_minutes=60)
        r1 = recommender.evaluate_risk_signal(0.9, [3])
        assert r1 is not None
        r2 = recommender.evaluate_risk_signal(0.95, [3])
        assert r2 is None

    def test_max_pending_reached(self):
        recommender = AmendmentRecommender(
            risk_threshold=0.5, max_pending_recommendations=2, cooldown_minutes=0
        )
        # Exhaust cooldown by using different areas
        r1 = recommender.evaluate_risk_signal(0.9, [3], context={"target_area": "area.1"})
        r2 = recommender.evaluate_risk_signal(0.9, [4], context={"target_area": "area.2"})
        assert r1 is not None
        assert r2 is not None
        r3 = recommender.evaluate_risk_signal(0.9, [0], context={"target_area": "area.3"})
        assert r3 is None

    def test_get_pending(self):
        recommender = AmendmentRecommender(risk_threshold=0.5)
        recommender.evaluate_risk_signal(0.9, [3])
        pending = recommender.get_pending()
        assert len(pending) == 1

    def test_acknowledge(self):
        recommender = AmendmentRecommender(risk_threshold=0.5)
        rec = recommender.evaluate_risk_signal(0.9, [3])
        assert rec is not None
        ack = recommender.acknowledge(rec.recommendation_id)
        assert ack is not None
        assert ack.recommendation_id == rec.recommendation_id
        assert len(recommender.get_pending()) == 0
        assert len(recommender._history) == 1

    def test_acknowledge_unknown_id(self):
        recommender = AmendmentRecommender(risk_threshold=0.5)
        assert recommender.acknowledge("nonexistent") is None

    def test_dismiss(self):
        recommender = AmendmentRecommender(risk_threshold=0.5)
        rec = recommender.evaluate_risk_signal(0.9, [3])
        assert rec is not None
        dismissed = recommender.dismiss(rec.recommendation_id, reason="not needed")
        assert dismissed is True
        assert len(recommender.get_pending()) == 0
        assert len(recommender._history) == 1

    def test_dismiss_unknown_id(self):
        recommender = AmendmentRecommender(risk_threshold=0.5)
        assert recommender.dismiss("nonexistent") is False

    def test_evaluate_threshold_drift_below_minimum(self):
        recommender = AmendmentRecommender()
        result = recommender.evaluate_threshold_drift("metric1", 0.5, 0.45, 0.05)
        assert result is None

    def test_evaluate_threshold_drift_generates_recommendation(self):
        recommender = AmendmentRecommender()
        result = recommender.evaluate_threshold_drift("metric1", 0.7, 0.5, 0.2)
        assert result is not None
        assert result.trigger == RecommendationTrigger.THRESHOLD_DRIFT
        assert result.priority == RecommendationPriority.MEDIUM
        assert result.target_area == "thresholds.metric1"
        assert result.risk_score == 0.2

    def test_evaluate_threshold_drift_cooldown(self):
        recommender = AmendmentRecommender(cooldown_minutes=60)
        r1 = recommender.evaluate_threshold_drift("metric1", 0.7, 0.5, 0.2)
        assert r1 is not None
        r2 = recommender.evaluate_threshold_drift("metric1", 0.8, 0.5, 0.3)
        assert r2 is None

    def test_evaluate_threshold_drift_max_pending(self):
        recommender = AmendmentRecommender(max_pending_recommendations=1, cooldown_minutes=0)
        r1 = recommender.evaluate_threshold_drift("m1", 0.7, 0.5, 0.2)
        assert r1 is not None
        r2 = recommender.evaluate_threshold_drift("m2", 0.8, 0.4, 0.4)
        assert r2 is None

    def test_suggest_changes(self):
        recommender = AmendmentRecommender()
        changes = recommender._suggest_changes("governance.critical", 0.9, {})
        assert "governance.critical" in changes
        assert changes["governance.critical"]["requires_human_review"] is True
        assert changes["governance.critical"]["current_risk"] == 0.9

    def test_score_priority_boundary(self):
        recommender = AmendmentRecommender()
        assert recommender._score_priority(0.95) == RecommendationPriority.CRITICAL
        assert recommender._score_priority(0.94) == RecommendationPriority.HIGH
        assert recommender._score_priority(0.80) == RecommendationPriority.HIGH
        assert recommender._score_priority(0.79) == RecommendationPriority.MEDIUM
        assert recommender._score_priority(0.50) == RecommendationPriority.MEDIUM
        assert recommender._score_priority(0.49) == RecommendationPriority.LOW


# =====================================================================
# DEMOCRATIC GOVERNANCE
# =====================================================================


class TestDemocraticConstitutionalGovernance:
    def test_init(self):
        gov = DemocraticConstitutionalGovernance(consensus_threshold=0.7, min_participants=50)
        assert gov.consensus_threshold == 0.7
        assert gov.min_participants == 50
        # stability_layer may or may not be available depending on env
        assert gov.polis_engine is not None

    async def test_register_stakeholder(self):
        gov = DemocraticConstitutionalGovernance()
        s = await gov.register_stakeholder("Dr. Test", StakeholderGroup.TECHNICAL_EXPERTS, ["AI"])
        assert s.name == "Dr. Test"
        assert s.group == StakeholderGroup.TECHNICAL_EXPERTS
        assert s.stakeholder_id in gov.stakeholders

    async def test_propose_constitutional_change(self):
        gov = DemocraticConstitutionalGovernance()
        proposer = await gov.register_stakeholder(
            "Alice", StakeholderGroup.ETHICS_REVIEWERS, ["ethics"]
        )
        proposal = await gov.propose_constitutional_change(
            title="Test Proposal",
            description="A test change",
            proposed_changes={"transparency": True},
            proposer=proposer,
        )
        assert proposal.title == "Test Proposal"
        assert proposal.proposal_id in gov.proposals
        assert proposal.status == "proposed"

    async def test_run_deliberation(self):
        gov = DemocraticConstitutionalGovernance()
        stakeholders = []
        for group in [StakeholderGroup.TECHNICAL_EXPERTS, StakeholderGroup.ETHICS_REVIEWERS]:
            for i in range(5):
                s = await gov.register_stakeholder(f"{group.value}_{i}", group, [group.value])
                stakeholders.append(s)

        proposer = stakeholders[0]
        proposal = await gov.propose_constitutional_change(
            title="Test Deliberation",
            description="Testing full deliberation",
            proposed_changes={"rule": "new"},
            proposer=proposer,
        )
        result = await gov.run_deliberation(proposal, stakeholders, duration_hours=1)
        assert result.total_participants == len(stakeholders)
        assert result.statements_submitted > 0
        assert result.clusters_identified >= 0
        assert isinstance(result.consensus_reached, bool)

    def test_calculate_representative_metrics_empty(self):
        gov = DemocraticConstitutionalGovernance()
        metrics = gov._calculate_representative_metrics([])
        assert metrics["total_representatives"] == 0
        assert metrics["avg_centrality_across_all"] == 0.0

    def test_calculate_representative_metrics_with_clusters(self):
        gov = DemocraticConstitutionalGovernance()
        clusters = [
            OpinionCluster(
                cluster_id="c1",
                name="Group 1",
                description="test",
                representative_statements=[],
                member_stakeholders=[],
                consensus_score=0.8,
                polarization_level=0.1,
                size=5,
                metadata={
                    "representative_count": 3,
                    "avg_centrality_score": 0.7,
                    "min_centrality_score": 0.5,
                    "max_centrality_score": 0.9,
                    "centrality_scores": [0.5, 0.7, 0.9],
                    "diversity_filtering_enabled": True,
                    "diversity_threshold": 0.3,
                },
            ),
            OpinionCluster(
                cluster_id="c2",
                name="Group 2",
                description="test2",
                representative_statements=[],
                member_stakeholders=[],
                consensus_score=0.6,
                polarization_level=0.2,
                size=3,
                metadata={
                    "representative_count": 2,
                    "avg_centrality_score": 0.4,
                    "min_centrality_score": 0.3,
                    "max_centrality_score": 0.5,
                    "centrality_scores": [0.3, 0.5],
                },
            ),
        ]
        metrics = gov._calculate_representative_metrics(clusters)
        assert metrics["total_representatives"] == 5
        assert metrics["avg_representatives_per_cluster"] == 2.5
        assert metrics["avg_centrality_across_all"] > 0
        assert metrics["median_centrality_across_all"] > 0
        assert metrics["stdev_centrality_across_all"] > 0
        assert "excellent" in metrics["quality_distribution"]
        assert len(metrics["cluster_metrics"]) == 2

    def test_calculate_representative_metrics_single_score(self):
        gov = DemocraticConstitutionalGovernance()
        clusters = [
            OpinionCluster(
                cluster_id="c1",
                name="Solo",
                description="",
                representative_statements=[],
                member_stakeholders=[],
                consensus_score=0.9,
                polarization_level=0.0,
                size=1,
                metadata={
                    "representative_count": 1,
                    "centrality_scores": [0.85],
                },
            ),
        ]
        metrics = gov._calculate_representative_metrics(clusters)
        assert metrics["stdev_centrality_across_all"] == 0.0

    async def test_fast_govern_without_stakeholders(self):
        gov = DemocraticConstitutionalGovernance()
        result = await gov.fast_govern(
            decision={"description": "test decision"},
            time_budget_ms=100,
        )
        assert result["immediate_decision"]["approved"] is True
        assert result["deliberation_pending"] is False
        assert result["deliberation_task"] is None
        assert result["performance_optimized"] is True
        assert len(gov.fast_decisions) == 1

    async def test_fast_govern_with_few_stakeholders(self):
        gov = DemocraticConstitutionalGovernance()
        stakeholders = [_make_stakeholder(name=f"s{i}") for i in range(5)]
        result = await gov.fast_govern(
            decision={"description": "small group"},
            time_budget_ms=50,
            stakeholders=stakeholders,
        )
        assert result["deliberation_pending"] is False

    async def test_get_governance_status(self):
        gov = DemocraticConstitutionalGovernance()
        status = await gov.get_governance_status()
        assert status["framework"] == "CCAI Democratic Constitutional Governance"
        assert status["status"] == "operational"
        assert status["registered_stakeholders"] == 0
        assert "polis_deliberation" in status["capabilities"]

    async def test_generate_statement_for_each_group(self):
        gov = DemocraticConstitutionalGovernance()
        proposer = await gov.register_stakeholder("P", StakeholderGroup.TECHNICAL_EXPERTS, ["AI"])
        proposal = await gov.propose_constitutional_change(
            title="T",
            description="D",
            proposed_changes={},
            proposer=proposer,
        )
        for group in [
            StakeholderGroup.TECHNICAL_EXPERTS,
            StakeholderGroup.ETHICS_REVIEWERS,
            StakeholderGroup.END_USERS,
            StakeholderGroup.LEGAL_EXPERTS,
            StakeholderGroup.CIVIL_SOCIETY,
        ]:
            s = _make_stakeholder(group=group)
            stmt = await gov._generate_statement_for_stakeholder(proposal, s)
            assert isinstance(stmt, str)
            assert len(stmt) > 0

    async def test_apply_stability_constraint_no_mhc(self):
        gov = DemocraticConstitutionalGovernance()
        scores = [0.5, 0.6, 0.7]
        result = await gov._apply_stability_constraint(scores)
        assert result == scores

    async def test_apply_stability_constraint_empty(self):
        gov = DemocraticConstitutionalGovernance()
        result = await gov._apply_stability_constraint([])
        assert result == []

    def test_extract_consensus_metrics(self):
        gov = DemocraticConstitutionalGovernance()
        s1 = _make_stakeholder()
        gov.stakeholders[s1.stakeholder_id] = s1

        clusters = [
            OpinionCluster(
                cluster_id="c1",
                name="G1",
                description="",
                representative_statements=[],
                member_stakeholders=[s1.stakeholder_id],
                consensus_score=0.8,
                polarization_level=0.1,
                size=1,
                metadata={},
            ),
        ]
        cross_group = {"consensus_ratio": 0.75}
        ratio, trust = gov._extract_consensus_metrics(clusters, cross_group)
        assert ratio == 0.75
        assert len(trust) == 1
        assert trust[0] == s1.trust_score

    def test_extract_consensus_metrics_unknown_stakeholder(self):
        gov = DemocraticConstitutionalGovernance()
        clusters = [
            OpinionCluster(
                cluster_id="c1",
                name="G1",
                description="",
                representative_statements=[],
                member_stakeholders=["unknown-id"],
                consensus_score=0.8,
                polarization_level=0.1,
                size=1,
                metadata={},
            ),
        ]
        _, trust = gov._extract_consensus_metrics(clusters, {})
        assert trust == [0.5]


class TestGetCcaiGovernance:
    def test_returns_instance(self):
        gov = get_ccai_governance()
        assert isinstance(gov, DemocraticConstitutionalGovernance)


class TestDeliberateOnProposal:
    async def test_deliberate_on_proposal(self):
        result = await deliberate_on_proposal(
            title="Test",
            description="Test description",
            changes={"rule": "new"},
            stakeholder_groups=[
                StakeholderGroup.TECHNICAL_EXPERTS,
                StakeholderGroup.ETHICS_REVIEWERS,
            ],
            min_participants=10,
        )
        assert result.total_participants >= 10
        assert isinstance(result.consensus_reached, bool)


# =====================================================================
# ANTHROPIC ADAPTER
# =====================================================================


class TestAnthropicAdapterInit:
    def test_default_init(self):
        adapter = _make_adapter()
        assert adapter.model == "claude-sonnet-4-6"
        assert adapter.api_key == "test-key-123"

    def test_init_with_config(self):
        config = AnthropicAdapterConfig(
            model="claude-3-haiku-20240307",
            api_base="https://custom.api.com",
        )
        adapter = AnthropicAdapter(config=config, api_key="k")
        assert adapter.model == "claude-3-haiku-20240307"
        assert adapter.config.api_base == "https://custom.api.com"

    def test_init_no_model_defaults(self):
        adapter = AnthropicAdapter(api_key="test-key")
        assert adapter.model == "claude-sonnet-4-6"


class TestAnthropicAdapterMethods:
    def test_get_streaming_mode(self):
        adapter = _make_adapter()
        assert adapter.get_streaming_mode() == StreamingMode.SUPPORTED

    def test_get_provider_name(self):
        adapter = _make_adapter()
        assert adapter.get_provider_name() == "anthropic"

    def test_convert_tools_to_anthropic(self):
        adapter = _make_adapter()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather data",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {"type": "other", "data": "ignored"},
        ]
        result = adapter._convert_tools_to_anthropic(tools)
        assert len(result) == 1
        assert result[0]["name"] == "get_weather"
        assert result[0]["description"] == "Get weather data"
        assert result[0]["input_schema"] == {"type": "object", "properties": {}}

    def test_convert_tools_empty(self):
        adapter = _make_adapter()
        assert adapter._convert_tools_to_anthropic([]) == []

    def test_prepare_messages_with_system(self):
        adapter = _make_adapter()
        msgs = [_system_msg("Be helpful"), _user_msg("hi")]
        sys_prompt, conv_msgs = adapter._prepare_messages(msgs)
        assert sys_prompt == "Be helpful"
        assert len(conv_msgs) == 1

    def test_prepare_messages_no_system(self):
        adapter = _make_adapter()
        msgs = [_user_msg("hi")]
        sys_prompt, conv_msgs = adapter._prepare_messages(msgs)
        assert sys_prompt is None
        assert len(conv_msgs) == 1

    def test_prepare_messages_multiple_system(self):
        adapter = _make_adapter()
        msgs = [_system_msg("A"), _system_msg("B"), _user_msg("hi")]
        sys_prompt, _ = adapter._prepare_messages(msgs)
        assert sys_prompt == "A B"


class TestAnthropicAdapterEstimateCost:
    def test_known_model(self):
        adapter = _make_adapter(model="claude-sonnet-4-6")
        cost = adapter.estimate_cost(1000, 500)
        assert isinstance(cost, CostEstimate)
        assert cost.total_cost_usd > 0
        expected_prompt = (1000 / 1_000_000) * 3.00
        expected_completion = (500 / 1_000_000) * 15.00
        assert abs(cost.prompt_cost_usd - expected_prompt) < 1e-9
        assert abs(cost.completion_cost_usd - expected_completion) < 1e-9
        assert cost.currency == "USD"

    def test_unknown_model_falls_back(self):
        adapter = _make_adapter(model="claude-unknown-model")
        cost = adapter.estimate_cost(1000, 1000)
        assert cost.total_cost_usd > 0
        assert cost.pricing_model == "claude-unknown-model"

    def test_zero_tokens(self):
        adapter = _make_adapter()
        cost = adapter.estimate_cost(0, 0)
        assert cost.total_cost_usd == 0.0

    def test_opus_pricing(self):
        adapter = _make_adapter(model="claude-opus-4-6")
        cost = adapter.estimate_cost(1_000_000, 0)
        assert cost.prompt_cost_usd == 5.00


class TestAnthropicAdapterGetClient:
    def test_get_client_no_api_key_raises(self):
        adapter = _make_adapter(api_key=None)
        adapter.api_key = None
        with pytest.raises(ValueError, match="API key is required"):
            adapter._get_client()

    def test_get_async_client_no_api_key_raises(self):
        adapter = _make_adapter(api_key=None)
        adapter.api_key = None
        with pytest.raises(ValueError, match="API key is required"):
            adapter._get_async_client()

    @patch.dict("sys.modules", {"anthropic": None})
    def test_get_client_import_error(self):
        adapter = _make_adapter()
        adapter._client = None
        with pytest.raises(ImportError, match="anthropic package is required"):
            adapter._get_client()

    @patch.dict("sys.modules", {"anthropic": None})
    def test_get_async_client_import_error(self):
        adapter = _make_adapter()
        adapter._async_client = None
        with pytest.raises(ImportError, match="anthropic package is required"):
            adapter._get_async_client()

    def test_get_client_with_api_base_and_timeout(self):
        config = AnthropicAdapterConfig(
            model="claude-sonnet-4-6",
            api_base="https://custom.api.com",
            timeout_seconds=30,
        )
        adapter = AnthropicAdapter(config=config, api_key="test-key")
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            client = adapter._get_client()
            assert client is mock_client
            call_kwargs = mock_anthropic.Anthropic.call_args[1]
            assert call_kwargs["base_url"] == "https://custom.api.com"
            assert call_kwargs["timeout"] == 30

    def test_get_async_client_with_api_base_and_timeout(self):
        config = AnthropicAdapterConfig(
            model="claude-sonnet-4-6",
            api_base="https://custom.api.com",
            timeout_seconds=60,
        )
        adapter = AnthropicAdapter(config=config, api_key="test-key")
        mock_anthropic = MagicMock()
        mock_async_client = MagicMock()
        mock_anthropic.AsyncAnthropic.return_value = mock_async_client
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            client = adapter._get_async_client()
            assert client is mock_async_client
            call_kwargs = mock_anthropic.AsyncAnthropic.call_args[1]
            assert call_kwargs["base_url"] == "https://custom.api.com"
            assert call_kwargs["timeout"] == 60

    def test_get_client_caches(self):
        adapter = _make_adapter()
        sentinel = MagicMock()
        adapter._client = sentinel
        assert adapter._get_client() is sentinel

    def test_get_async_client_caches(self):
        adapter = _make_adapter()
        sentinel = MagicMock()
        adapter._async_client = sentinel
        assert adapter._get_async_client() is sentinel


class TestAnthropicAdapterComplete:
    def test_complete_sync(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = _mock_anthropic_response_dict()
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        adapter._client = mock_client

        msgs = [_user_msg("hello")]
        result = adapter.complete(msgs, temperature=0.5, max_tokens=100)
        assert isinstance(result, LLMResponse)
        assert result.metadata.latency_ms > 0

    def test_complete_sync_with_system_and_stop(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = _mock_anthropic_response_dict()
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        adapter._client = mock_client

        msgs = [_system_msg("Be concise"), _user_msg("hello")]
        result = adapter.complete(msgs, stop=["END"])
        assert isinstance(result, LLMResponse)
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["stop_sequences"] == ["END"]
        assert "system" in call_kwargs

    def test_complete_sync_default_max_tokens(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = _mock_anthropic_response_dict()
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        adapter._client = mock_client

        adapter.complete([_user_msg("hi")])
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] == 4096

    def test_complete_with_tools_and_top_k(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = _mock_anthropic_response_dict()
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        adapter._client = mock_client

        tools = [{"type": "function", "function": {"name": "f1", "parameters": {}}}]
        adapter.complete([_user_msg("hi")], tools=tools, top_k=40)
        call_kwargs = mock_client.messages.create.call_args[1]
        assert "tools" in call_kwargs
        assert call_kwargs["top_k"] == 40

    def test_complete_sync_error(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API error")
        adapter._client = mock_client

        with pytest.raises(RuntimeError, match="API error"):
            adapter.complete([_user_msg("hi")])


class TestAnthropicAdapterAcomplete:
    async def test_acomplete(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = _mock_anthropic_response_dict()
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        adapter._async_client = mock_client

        result = await adapter.acomplete([_user_msg("hello")], max_tokens=50)
        assert isinstance(result, LLMResponse)
        assert result.metadata.latency_ms >= 0

    async def test_acomplete_with_system_stop_tools_topk(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = _mock_anthropic_response_dict()
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        adapter._async_client = mock_client

        tools = [{"type": "function", "function": {"name": "f1", "parameters": {}}}]
        msgs = [_system_msg("sys"), _user_msg("hi")]
        result = await adapter.acomplete(msgs, stop=["X"], tools=tools, top_k=10)
        assert isinstance(result, LLMResponse)
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["stop_sequences"] == ["X"]
        assert "tools" in call_kwargs
        assert call_kwargs["top_k"] == 10
        assert "system" in call_kwargs

    async def test_acomplete_default_max_tokens(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = _mock_anthropic_response_dict()
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        adapter._async_client = mock_client

        await adapter.acomplete([_user_msg("hi")])
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] == 4096

    async def test_acomplete_error(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("async fail"))
        adapter._async_client = mock_client

        with pytest.raises(RuntimeError, match="async fail"):
            await adapter.acomplete([_user_msg("hi")])


class TestAnthropicAdapterStream:
    def test_stream_sync(self):
        adapter = _make_adapter()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_stream_ctx.text_stream = iter(["Hello", " world"])
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream_ctx
        adapter._client = mock_client

        chunks = list(adapter.stream([_user_msg("hi")]))
        assert chunks == ["Hello", " world"]

    def test_stream_with_all_options(self):
        adapter = _make_adapter()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_stream_ctx.text_stream = iter(["ok"])
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream_ctx
        adapter._client = mock_client

        tools = [{"type": "function", "function": {"name": "t1", "parameters": {}}}]
        msgs = [_system_msg("sys"), _user_msg("hi")]
        chunks = list(adapter.stream(msgs, stop=["END"], tools=tools, top_k=5))
        assert chunks == ["ok"]
        call_kwargs = mock_client.messages.stream.call_args[1]
        assert "system" in call_kwargs
        assert call_kwargs["stop_sequences"] == ["END"]
        assert "tools" in call_kwargs
        assert call_kwargs["top_k"] == 5

    def test_stream_error(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = RuntimeError("stream fail")
        adapter._client = mock_client

        with pytest.raises(RuntimeError, match="stream fail"):
            list(adapter.stream([_user_msg("hi")]))


class TestAnthropicAdapterAstream:
    async def test_astream(self):
        adapter = _make_adapter()

        class MockAsyncStream:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            @property
            def text_stream(self):
                return self._gen()

            async def _gen(self):
                for chunk in ["async", " chunk"]:
                    yield chunk

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = MockAsyncStream()
        adapter._async_client = mock_client

        chunks = []
        async for chunk in adapter.astream([_user_msg("hi")]):
            chunks.append(chunk)
        assert chunks == ["async", " chunk"]

    async def test_astream_with_all_options(self):
        adapter = _make_adapter()

        class MockAsyncStream:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            @property
            def text_stream(self):
                return self._gen()

            async def _gen(self):
                yield "ok"

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = MockAsyncStream()
        adapter._async_client = mock_client

        tools = [{"type": "function", "function": {"name": "t1", "parameters": {}}}]
        msgs = [_system_msg("sys"), _user_msg("hi")]
        chunks = []
        async for chunk in adapter.astream(msgs, stop=["S"], tools=tools, top_k=3):
            chunks.append(chunk)
        assert chunks == ["ok"]
        call_kwargs = mock_client.messages.stream.call_args[1]
        assert "system" in call_kwargs
        assert call_kwargs["stop_sequences"] == ["S"]

    async def test_astream_error(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = RuntimeError("astream fail")
        adapter._async_client = mock_client

        with pytest.raises(RuntimeError, match="astream fail"):
            async for _ in adapter.astream([_user_msg("hi")]):
                pass


class TestAnthropicAdapterCountTokens:
    def test_count_tokens_with_client_method(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.count_tokens.return_value = SimpleNamespace(input_tokens=42)
        adapter._client = mock_client

        msgs = [_user_msg("hello world")]
        count = adapter.count_tokens(msgs)
        assert count == 42

    def test_count_tokens_with_system_prompt(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.count_tokens.return_value = SimpleNamespace(input_tokens=50)
        adapter._client = mock_client

        msgs = [_system_msg("sys"), _user_msg("hi")]
        count = adapter.count_tokens(msgs)
        assert count == 50
        call_kwargs = mock_client.count_tokens.call_args[1]
        assert "system" in call_kwargs

    def test_count_tokens_fallback_no_method(self):
        adapter = _make_adapter()
        mock_client = MagicMock(spec=[])  # no count_tokens
        adapter._client = mock_client

        msgs = [_user_msg("hello world")]
        count = adapter.count_tokens(msgs)
        expected = (len("user") + len("hello world")) // 4
        assert count == expected

    def test_count_tokens_fallback_on_error(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.count_tokens.side_effect = RuntimeError("broken")
        adapter._client = mock_client

        msgs = [_user_msg("test"), _system_msg("sys")]
        count = adapter.count_tokens(msgs)
        total_chars = sum(len(m.role) + len(m.content) for m in msgs)
        assert count == total_chars // 4


class TestAnthropicAdapterHealthCheck:
    async def test_health_check_success(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=MagicMock())
        adapter._async_client = mock_client

        result = await adapter.health_check()
        assert isinstance(result, HealthCheckResult)
        assert result.status == AdapterStatus.HEALTHY
        assert "Anthropic API is accessible" in result.message
        assert result.details["provider"] == "anthropic"

    async def test_health_check_failure(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=ConnectionError("no connection"))
        adapter._async_client = mock_client

        result = await adapter.health_check()
        assert result.status == AdapterStatus.UNHEALTHY
        assert "no connection" in result.message
        assert "error" in result.details

    async def test_health_check_with_api_base(self):
        config = AnthropicAdapterConfig(
            model="claude-sonnet-4-6",
            api_base="https://my-proxy.com",
        )
        adapter = AnthropicAdapter(config=config, api_key="test-key")
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=MagicMock())
        adapter._async_client = mock_client

        result = await adapter.health_check()
        assert result.details["api_base"] == "https://my-proxy.com"

    async def test_health_check_without_api_base(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=MagicMock())
        adapter._async_client = mock_client

        result = await adapter.health_check()
        assert result.details["api_base"] == "https://api.anthropic.com"
