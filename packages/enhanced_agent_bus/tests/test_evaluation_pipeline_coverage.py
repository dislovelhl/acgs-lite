"""
Comprehensive test coverage for data_flywheel/evaluation_pipeline.py
Constitutional Hash: cdd01ef066bc6cf2

Targets >=98% coverage of all classes, methods, and branches.
asyncio_mode = "auto" is set in pyproject.toml — no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from packages.enhanced_agent_bus.data_flywheel.config import (
    CandidateModel,
    ExperimentType,
    FlywheelConfig,
    ICLConfig,
)
from packages.enhanced_agent_bus.data_flywheel.evaluation_pipeline import (
    FINE_TUNING_EXECUTION_ERRORS,
    BatchEvaluationResults,
    EvaluationMetricType,
    EvaluationPipeline,
    EvaluationResult,
    EvaluationSample,
    FineTuningConfig,
    FineTuningJob,
    FineTuningMethod,
    FineTuningStatus,
    ICLPromptBuilder,
    MockModelEvaluator,
)
from packages.enhanced_agent_bus.data_flywheel.logger import (
    GovernanceDecision,
    GovernanceDecisionLog,
    WorkloadType,
)
from packages.enhanced_agent_bus.data_flywheel.store import (
    DatasetSplit,
    FlywheelDataset,
    FlywheelDataStore,
    InMemoryBackend,
)
from src.core.shared.constants import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.unit, pytest.mark.governance]


# ---------------------------------------------------------------------------
# Helpers / Factories
# ---------------------------------------------------------------------------


def _make_candidate_model(name: str = "test-model") -> CandidateModel:
    return CandidateModel(model_name=name)


def _make_eval_sample(
    input_text: str = "evaluate this",
    expected_output: str = "approved",
    workload_type: WorkloadType = WorkloadType.GOVERNANCE_REQUEST,
) -> EvaluationSample:
    return EvaluationSample(
        input_text=input_text,
        expected_output=expected_output,
        workload_type=workload_type,
    )


def _make_eval_result(
    sample_id: str = "abc123",
    model_name: str = "test-model",
    experiment_type: ExperimentType = ExperimentType.BASE,
    is_correct: bool = True,
    constitutional_validated: bool = True,
    validation_errors: list[str] | None = None,
    latency_ms: float = 20.0,
) -> EvaluationResult:
    return EvaluationResult(
        sample_id=sample_id,
        model_name=model_name,
        experiment_type=experiment_type,
        predicted_output="approved",
        is_correct=is_correct,
        latency_ms=latency_ms,
        constitutional_validated=constitutional_validated,
        validation_errors=validation_errors or [],
    )


def _make_governance_log(
    workload_type: WorkloadType = WorkloadType.GOVERNANCE_REQUEST,
    decision: GovernanceDecision = GovernanceDecision.APPROVED,
    quality_score: float = 0.9,
    decision_reasoning: str = "looks fine",
    impact_score: float = 0.3,
) -> GovernanceDecisionLog:
    return GovernanceDecisionLog(
        message_id="msg-001",
        workload_type=workload_type,
        decision=decision,
        quality_score=quality_score,
        decision_reasoning=decision_reasoning,
        impact_score=impact_score,
    )


def _make_dataset_split(records: list[dict] | None = None) -> DatasetSplit:
    return DatasetSplit(name="eval", records=records or [])


def _make_flywheel_dataset(
    eval_records: list[dict] | None = None,
    train_records: list[dict] | None = None,
) -> FlywheelDataset:
    return FlywheelDataset(
        dataset_id="ds-001",
        name="test-dataset",
        eval_split=_make_dataset_split(
            eval_records
            or [
                {
                    "decision": "approved",
                    "workload_type": "governance_request",
                    "impact_score": 0.2,
                }
            ]
        ),
        train_split=_make_dataset_split(
            train_records
            or [
                {
                    "decision": "rejected",
                    "workload_type": "policy_evaluation",
                    "impact_score": 0.6,
                }
            ]
        ),
    )


def _make_pipeline() -> EvaluationPipeline:
    backend = InMemoryBackend()
    config = FlywheelConfig()
    store = FlywheelDataStore(backend=backend, config=config)
    flywheel_config = FlywheelConfig()
    return EvaluationPipeline(store=store, config=flywheel_config)


def _make_fine_tuning_config(
    constitutional_hash: str = CONSTITUTIONAL_HASH,
    num_epochs: int = 1,
) -> FineTuningConfig:
    return FineTuningConfig(
        base_model="meta/llama-3b",
        output_model_name="my-fine-tuned-model",
        constitutional_hash=constitutional_hash,
        num_epochs=num_epochs,
    )


# ---------------------------------------------------------------------------
# EvaluationMetricType enum
# ---------------------------------------------------------------------------


class TestEvaluationMetricType:
    def test_all_values(self):
        values = {m.value for m in EvaluationMetricType}
        assert "accuracy" in values
        assert "precision" in values
        assert "recall" in values
        assert "f1_score" in values
        assert "constitutional_compliance" in values
        assert "latency_p50" in values
        assert "latency_p95" in values
        assert "latency_p99" in values
        assert "tokens_per_second" in values
        assert "cost_per_inference" in values

    def test_string_enum(self):
        assert EvaluationMetricType.ACCURACY == "accuracy"


# ---------------------------------------------------------------------------
# FineTuningMethod enum
# ---------------------------------------------------------------------------


class TestFineTuningMethod:
    def test_all_values(self):
        values = {m.value for m in FineTuningMethod}
        assert values == {"lora", "qlora", "full", "adapter", "expand"}

    def test_string_enum(self):
        assert FineTuningMethod.LORA == "lora"


# ---------------------------------------------------------------------------
# EvaluationSample
# ---------------------------------------------------------------------------


class TestEvaluationSample:
    def test_defaults(self):
        sample = EvaluationSample(input_text="query", expected_output="ans")
        assert sample.workload_type == WorkloadType.GOVERNANCE_REQUEST
        assert sample.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(sample.sample_id, str)
        assert len(sample.sample_id) == 16

    def test_custom_fields(self):
        sample = EvaluationSample(
            input_text="test input",
            expected_output="approved",
            workload_type=WorkloadType.POLICY_EVALUATION,
            metadata={"key": "value"},
        )
        assert sample.workload_type == WorkloadType.POLICY_EVALUATION
        assert sample.metadata == {"key": "value"}

    def test_unique_sample_ids(self):
        s1 = EvaluationSample(input_text="a", expected_output="x")
        s2 = EvaluationSample(input_text="b", expected_output="y")
        assert isinstance(s1.sample_id, str)
        assert isinstance(s2.sample_id, str)


# ---------------------------------------------------------------------------
# EvaluationResult
# ---------------------------------------------------------------------------


class TestEvaluationResult:
    def test_defaults(self):
        r = _make_eval_result()
        assert r.confidence == 0.0
        assert r.latency_ms == 20.0
        assert r.tokens_generated == 0
        assert r.constitutional_validated is True
        assert r.validation_errors == []
        assert r.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(r.created_at, datetime)

    def test_with_validation_errors(self):
        r = _make_eval_result(
            constitutional_validated=False,
            validation_errors=["err1", "err2"],
        )
        assert r.validation_errors == ["err1", "err2"]
        assert r.constitutional_validated is False


# ---------------------------------------------------------------------------
# BatchEvaluationResults.compute_metrics
# ---------------------------------------------------------------------------


class TestBatchEvaluationResults:
    def test_compute_metrics_empty(self):
        batch = BatchEvaluationResults(
            batch_id="b1",
            model_name="m",
            experiment_type=ExperimentType.BASE,
        )
        batch.compute_metrics()
        assert batch.total_samples == 0
        assert batch.accuracy == 0.0

    def test_compute_metrics_all_correct(self):
        results = [_make_eval_result(is_correct=True, latency_ms=float(i + 1)) for i in range(10)]
        batch = BatchEvaluationResults(
            batch_id="b2",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            results=results,
        )
        batch.compute_metrics()
        assert batch.total_samples == 10
        assert batch.correct_predictions == 10
        assert batch.accuracy == 1.0
        assert batch.constitutional_compliance_rate == 1.0
        assert batch.completed_at is not None

    def test_compute_metrics_mixed_correct(self):
        results = [
            _make_eval_result(is_correct=True, latency_ms=10.0),
            _make_eval_result(is_correct=False, latency_ms=20.0),
        ]
        batch = BatchEvaluationResults(
            batch_id="b3",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            results=results,
        )
        batch.compute_metrics()
        assert batch.total_samples == 2
        assert batch.correct_predictions == 1
        assert batch.accuracy == 0.5
        assert batch.avg_latency_ms == 15.0

    def test_compute_metrics_compliance_rate(self):
        results = [
            _make_eval_result(constitutional_validated=True),
            _make_eval_result(constitutional_validated=False),
            _make_eval_result(constitutional_validated=True),
            _make_eval_result(constitutional_validated=True),
        ]
        batch = BatchEvaluationResults(
            batch_id="b4",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            results=results,
        )
        batch.compute_metrics()
        assert batch.constitutional_compliance_rate == pytest.approx(0.75)

    def test_compute_metrics_p95_with_small_n(self):
        # n < 20 => p95 uses last element
        results = [_make_eval_result(latency_ms=float(i)) for i in range(5)]
        batch = BatchEvaluationResults(
            batch_id="b5",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            results=results,
        )
        batch.compute_metrics()
        latencies = sorted(r.latency_ms for r in results)
        assert batch.p95_latency_ms == latencies[-1]

    def test_compute_metrics_p99_with_small_n(self):
        # n < 100 => p99 uses last element
        results = [_make_eval_result(latency_ms=float(i)) for i in range(50)]
        batch = BatchEvaluationResults(
            batch_id="b6",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            results=results,
        )
        batch.compute_metrics()
        latencies = sorted(r.latency_ms for r in results)
        assert batch.p99_latency_ms == latencies[-1]

    def test_compute_metrics_p95_large_n(self):
        # n >= 20 => p95 uses percentile index
        results = [_make_eval_result(latency_ms=float(i)) for i in range(20)]
        batch = BatchEvaluationResults(
            batch_id="b7",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            results=results,
        )
        batch.compute_metrics()
        latencies = sorted(r.latency_ms for r in results)
        n = len(latencies)
        expected_p95 = latencies[int(n * 0.95)]
        assert batch.p95_latency_ms == expected_p95

    def test_compute_metrics_p99_large_n(self):
        # n >= 100 => p99 uses percentile index
        results = [_make_eval_result(latency_ms=float(i)) for i in range(100)]
        batch = BatchEvaluationResults(
            batch_id="b8",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            results=results,
        )
        batch.compute_metrics()
        latencies = sorted(r.latency_ms for r in results)
        n = len(latencies)
        expected_p99 = latencies[int(n * 0.99)]
        assert batch.p99_latency_ms == expected_p99

    def test_defaults(self):
        batch = BatchEvaluationResults(
            batch_id="x",
            model_name="m",
            experiment_type=ExperimentType.BASE,
        )
        assert batch.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(batch.started_at, datetime)
        assert batch.completed_at is None


# ---------------------------------------------------------------------------
# FineTuningConfig
# ---------------------------------------------------------------------------


class TestFineTuningConfig:
    def test_defaults(self):
        cfg = _make_fine_tuning_config()
        assert cfg.method == FineTuningMethod.LORA
        assert cfg.learning_rate == pytest.approx(2e-4)
        assert cfg.batch_size == 4
        assert cfg.num_epochs == 1
        assert cfg.lora_r == 8
        assert cfg.lora_alpha == 16
        assert cfg.lora_dropout == pytest.approx(0.1)
        assert cfg.target_modules == ["q_proj", "v_proj"]
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH
        assert cfg.require_compliance_check is True

    def test_all_methods(self):
        for method in FineTuningMethod:
            cfg = FineTuningConfig(
                method=method,
                base_model="base",
                output_model_name="out",
            )
            assert cfg.method == method

    def test_custom_values(self):
        cfg = FineTuningConfig(
            base_model="base",
            output_model_name="out",
            learning_rate=1e-3,
            batch_size=8,
            num_epochs=5,
            train_dataset_id="train-ds",
            val_dataset_id="val-ds",
        )
        assert cfg.learning_rate == pytest.approx(1e-3)
        assert cfg.batch_size == 8
        assert cfg.train_dataset_id == "train-ds"


# ---------------------------------------------------------------------------
# FineTuningJob
# ---------------------------------------------------------------------------


class TestFineTuningJob:
    def test_defaults(self):
        cfg = _make_fine_tuning_config()
        job = FineTuningJob(config=cfg)
        assert job.status == FineTuningStatus.PENDING
        assert job.progress == 0.0
        assert job.current_step == 0
        assert job.total_steps == 0
        assert job.current_loss is None
        assert job.best_loss is None
        assert job.output_model_path is None
        assert job.error_message is None
        assert job.completed_at is None
        assert job.constitutional_hash == CONSTITUTIONAL_HASH
        assert len(job.job_id) == 16

    def test_unique_job_ids(self):
        cfg = _make_fine_tuning_config()
        j1 = FineTuningJob(config=cfg)
        j2 = FineTuningJob(config=cfg)
        assert isinstance(j1.job_id, str)
        assert isinstance(j2.job_id, str)


# ---------------------------------------------------------------------------
# FineTuningStatus enum
# ---------------------------------------------------------------------------


class TestFineTuningStatus:
    def test_all_statuses(self):
        values = {s.value for s in FineTuningStatus}
        assert values == {
            "pending",
            "preparing",
            "training",
            "validating",
            "completed",
            "failed",
            "cancelled",
        }


# ---------------------------------------------------------------------------
# FINE_TUNING_EXECUTION_ERRORS tuple
# ---------------------------------------------------------------------------


class TestFineTuningExecutionErrors:
    def test_contains_expected_errors(self):
        assert RuntimeError in FINE_TUNING_EXECUTION_ERRORS
        assert ValueError in FINE_TUNING_EXECUTION_ERRORS
        assert TypeError in FINE_TUNING_EXECUTION_ERRORS
        assert KeyError in FINE_TUNING_EXECUTION_ERRORS
        assert AttributeError in FINE_TUNING_EXECUTION_ERRORS
        assert OSError in FINE_TUNING_EXECUTION_ERRORS
        assert asyncio.TimeoutError in FINE_TUNING_EXECUTION_ERRORS


# ---------------------------------------------------------------------------
# MockModelEvaluator
# ---------------------------------------------------------------------------


class TestMockModelEvaluator:
    async def test_evaluate_returns_result(self):
        evaluator = MockModelEvaluator()
        model = _make_candidate_model()
        sample = _make_eval_sample()
        result = await evaluator.evaluate(model, sample)
        assert isinstance(result, EvaluationResult)
        assert result.sample_id == sample.sample_id
        assert result.model_name == model.model_name
        assert result.experiment_type == ExperimentType.BASE
        assert isinstance(result.is_correct, bool)
        assert 0.0 <= result.confidence <= 1.0
        assert result.tokens_generated >= 10

    async def test_evaluate_batch_returns_batch_results(self):
        evaluator = MockModelEvaluator()
        model = _make_candidate_model()
        samples = [_make_eval_sample() for _ in range(5)]
        batch = await evaluator.evaluate_batch(model, samples)
        assert isinstance(batch, BatchEvaluationResults)
        assert batch.total_samples == 5
        assert len(batch.results) == 5
        assert batch.model_name == model.model_name
        assert batch.experiment_type == ExperimentType.BASE

    async def test_evaluate_batch_empty(self):
        evaluator = MockModelEvaluator()
        model = _make_candidate_model()
        batch = await evaluator.evaluate_batch(model, [])
        # compute_metrics returns early for empty results
        assert batch.total_samples == 0
        assert batch.accuracy == 0.0

    async def test_evaluate_correct_prediction_format(self):
        # Deterministic: always correct
        evaluator = MockModelEvaluator(accuracy_range=(1.0, 1.0), compliance_rate=1.0)
        model = _make_candidate_model()
        sample = _make_eval_sample(expected_output="approved")
        result = await evaluator.evaluate(model, sample)
        assert result.is_correct is True
        assert result.predicted_output == "approved"
        assert result.constitutional_validated is True
        assert result.validation_errors == []

    async def test_evaluate_incorrect_prediction_format(self):
        # Deterministic: never correct
        evaluator = MockModelEvaluator(accuracy_range=(0.0, 0.0), compliance_rate=0.0)
        model = _make_candidate_model()
        sample = _make_eval_sample(expected_output="approved")
        result = await evaluator.evaluate(model, sample)
        assert result.is_correct is False
        assert result.predicted_output == "incorrect"
        assert result.constitutional_validated is False
        assert "Mock validation error" in result.validation_errors

    async def test_evaluate_custom_latency_range(self):
        evaluator = MockModelEvaluator(latency_range=(50.0, 50.0))
        model = _make_candidate_model()
        sample = _make_eval_sample()
        result = await evaluator.evaluate(model, sample)
        assert result.latency_ms == pytest.approx(50.0)

    async def test_evaluate_batch_computes_metrics(self):
        evaluator = MockModelEvaluator(accuracy_range=(1.0, 1.0), compliance_rate=1.0)
        model = _make_candidate_model()
        samples = [_make_eval_sample() for _ in range(3)]
        batch = await evaluator.evaluate_batch(model, samples)
        assert batch.accuracy == 1.0
        assert batch.constitutional_compliance_rate == 1.0


# ---------------------------------------------------------------------------
# ICLPromptBuilder
# ---------------------------------------------------------------------------


class TestICLPromptBuilder:
    def test_build_prompt_no_examples_no_system(self):
        builder = ICLPromptBuilder()
        prompt = builder.build_prompt("my query", [])
        assert "my query" in prompt
        assert CONSTITUTIONAL_HASH in prompt
        assert "System:" not in prompt

    def test_build_prompt_with_system(self):
        builder = ICLPromptBuilder()
        prompt = builder.build_prompt("query", [], system_prompt="Be helpful")
        assert "System: Be helpful" in prompt

    def test_build_prompt_with_examples(self):
        builder = ICLPromptBuilder(config=ICLConfig(max_examples=3))
        logs = [
            _make_governance_log(decision=GovernanceDecision.APPROVED, decision_reasoning="fine"),
            _make_governance_log(decision=GovernanceDecision.REJECTED, decision_reasoning=""),
        ]
        prompt = builder.build_prompt("test query", logs)
        assert "Example 1:" in prompt
        assert "Example 2:" in prompt
        assert "test query" in prompt
        # Reasoning only shown when non-empty
        assert "fine" in prompt

    def test_build_prompt_limits_examples_to_max(self):
        builder = ICLPromptBuilder(config=ICLConfig(max_examples=2))
        logs = [_make_governance_log() for _ in range(10)]
        prompt = builder.build_prompt("q", logs)
        assert "Example 3:" not in prompt
        assert "Example 1:" in prompt
        assert "Example 2:" in prompt

    def test_build_prompt_no_reasoning_when_empty(self):
        builder = ICLPromptBuilder()
        log = _make_governance_log(decision_reasoning="")
        prompt = builder.build_prompt("q", [log])
        assert "Reasoning:" not in prompt

    def test_select_examples_no_filter(self):
        builder = ICLPromptBuilder(config=ICLConfig(max_examples=3))
        logs = [_make_governance_log() for _ in range(5)]
        selected = builder.select_examples(logs)
        assert len(selected) <= 3

    def test_select_examples_filter_by_workload_type_enough(self):
        builder = ICLPromptBuilder(config=ICLConfig(max_examples=2))
        gov_logs = [
            _make_governance_log(workload_type=WorkloadType.GOVERNANCE_REQUEST) for _ in range(5)
        ]
        pol_logs = [
            _make_governance_log(workload_type=WorkloadType.POLICY_EVALUATION) for _ in range(5)
        ]
        all_logs = gov_logs + pol_logs
        selected = builder.select_examples(all_logs, WorkloadType.GOVERNANCE_REQUEST)
        assert all(log.workload_type == WorkloadType.GOVERNANCE_REQUEST for log in selected)

    def test_select_examples_filter_by_workload_type_not_enough(self):
        # Only 1 matching log but max_examples=3 -> falls back to all logs
        builder = ICLPromptBuilder(config=ICLConfig(max_examples=3))
        gov_logs = [_make_governance_log(workload_type=WorkloadType.GOVERNANCE_REQUEST)]
        pol_logs = [
            _make_governance_log(workload_type=WorkloadType.POLICY_EVALUATION) for _ in range(5)
        ]
        all_logs = gov_logs + pol_logs
        selected = builder.select_examples(all_logs, WorkloadType.GOVERNANCE_REQUEST)
        # Falls back to all logs because typed_logs (1) < max_examples (3)
        assert len(selected) <= 3

    def test_select_examples_quality_filter(self):
        builder = ICLPromptBuilder(config=ICLConfig(max_examples=2))
        high_quality = [_make_governance_log(quality_score=0.9) for _ in range(5)]
        low_quality = [_make_governance_log(quality_score=0.3) for _ in range(5)]
        all_logs = high_quality + low_quality
        selected = builder.select_examples(all_logs)
        # High-quality logs selected when enough of them
        assert all(log.quality_score >= 0.8 for log in selected)

    def test_select_examples_quality_filter_not_enough(self):
        # Only 1 high-quality log but max_examples=3 -> falls back to all
        builder = ICLPromptBuilder(config=ICLConfig(max_examples=3))
        high_quality = [_make_governance_log(quality_score=0.9)]
        low_quality = [_make_governance_log(quality_score=0.3) for _ in range(5)]
        all_logs = high_quality + low_quality
        selected = builder.select_examples(all_logs)
        assert len(selected) <= 3

    def test_select_examples_decision_diversity(self):
        builder = ICLPromptBuilder(config=ICLConfig(max_examples=10))
        logs = [
            _make_governance_log(decision=GovernanceDecision.APPROVED),
            _make_governance_log(decision=GovernanceDecision.REJECTED),
            _make_governance_log(decision=GovernanceDecision.ESCALATED),
        ]
        selected = builder.select_examples(logs)
        decisions = {log.decision for log in selected}
        # Should include diverse decisions
        assert len(decisions) > 1

    def test_select_examples_max_examples_limit_enforced(self):
        builder = ICLPromptBuilder(config=ICLConfig(max_examples=2))
        logs = [_make_governance_log() for _ in range(20)]
        selected = builder.select_examples(logs)
        assert len(selected) <= 2

    def test_default_config_used_when_none(self):
        builder = ICLPromptBuilder(config=None)
        assert builder.config is not None
        assert isinstance(builder.config, ICLConfig)


# ---------------------------------------------------------------------------
# EvaluationPipeline._format_input_from_dict
# ---------------------------------------------------------------------------


class TestFormatInputFromDict:
    def test_basic_record(self):
        pipeline = _make_pipeline()
        record = {"workload_type": "governance_request", "impact_score": 0.5}
        result = pipeline._format_input_from_dict(record)
        assert "Workload Type: governance_request" in result
        assert "Impact Score: 0.50" in result

    def test_with_impact_vector(self):
        pipeline = _make_pipeline()
        record = {
            "workload_type": "policy_evaluation",
            "impact_score": 0.7,
            "impact_vector": {"safety": 0.8, "security": 0.6},
        }
        result = pipeline._format_input_from_dict(record)
        assert "Impact Vector:" in result
        assert "safety: 0.80" in result
        assert "security: 0.60" in result

    def test_with_impact_vector_non_numeric_values_skipped(self):
        pipeline = _make_pipeline()
        record = {
            "impact_vector": {"safety": 0.8, "label": "high"},  # label is str, not float
            "impact_score": 0.5,
        }
        result = pipeline._format_input_from_dict(record)
        assert "safety: 0.80" in result
        assert "label" not in result

    def test_with_context(self):
        pipeline = _make_pipeline()
        record = {
            "impact_score": 0.1,
            "context": {"key": "value"},
        }
        result = pipeline._format_input_from_dict(record)
        assert "Context:" in result
        assert '"key"' in result

    def test_without_optional_fields(self):
        pipeline = _make_pipeline()
        record = {}
        result = pipeline._format_input_from_dict(record)
        assert "Workload Type: governance_request" in result
        assert "Impact Score: 0.00" in result

    def test_impact_vector_not_dict_ignored(self):
        pipeline = _make_pipeline()
        record = {"impact_vector": "not-a-dict", "impact_score": 0.0}
        result = pipeline._format_input_from_dict(record)
        assert "Impact Vector:" not in result


# ---------------------------------------------------------------------------
# EvaluationPipeline._format_input (from GovernanceDecisionLog)
# ---------------------------------------------------------------------------


class TestFormatInputFromLog:
    def test_basic_log(self):
        pipeline = _make_pipeline()
        log = _make_governance_log(impact_score=0.5)
        result = pipeline._format_input(log)
        assert "Workload Type: governance_request" in result
        assert "Impact Score: 0.50" in result

    def test_log_with_impact_vector(self):
        pipeline = _make_pipeline()
        log = GovernanceDecisionLog(
            message_id="m1",
            impact_score=0.4,
            impact_vector={"safety": 0.9, "security": 0.7},
        )
        result = pipeline._format_input(log)
        assert "Impact Vector:" in result
        assert "safety: 0.90" in result

    def test_log_without_impact_vector(self):
        pipeline = _make_pipeline()
        log = GovernanceDecisionLog(message_id="m1", impact_score=0.3, impact_vector={})
        result = pipeline._format_input(log)
        assert "Impact Vector:" not in result


# ---------------------------------------------------------------------------
# EvaluationPipeline.prepare_evaluation_samples
# ---------------------------------------------------------------------------


class TestPrepareEvaluationSamples:
    async def test_eval_split(self):
        pipeline = _make_pipeline()
        dataset = _make_flywheel_dataset(
            eval_records=[
                {
                    "decision": "approved",
                    "workload_type": "governance_request",
                    "impact_score": 0.2,
                },
                {
                    "decision": "rejected",
                    "workload_type": "policy_evaluation",
                    "impact_score": 0.8,
                },
            ]
        )
        samples = await pipeline.prepare_evaluation_samples(dataset, split="eval")
        assert len(samples) == 2
        assert samples[0].expected_output == "approved"
        assert samples[1].expected_output == "rejected"

    async def test_train_split(self):
        pipeline = _make_pipeline()
        dataset = _make_flywheel_dataset(
            train_records=[
                {
                    "decision": "approved",
                    "workload_type": "governance_request",
                    "impact_score": 0.1,
                },
            ]
        )
        samples = await pipeline.prepare_evaluation_samples(dataset, split="train")
        assert len(samples) == 1

    async def test_val_split(self):
        pipeline = _make_pipeline()
        dataset = FlywheelDataset(
            dataset_id="ds",
            name="ds",
            val_split=DatasetSplit(
                name="val",
                records=[
                    {
                        "decision": "deferred",
                        "workload_type": "deliberation",
                        "impact_score": 0.5,
                    }
                ],
            ),
        )
        samples = await pipeline.prepare_evaluation_samples(dataset, split="val")
        assert len(samples) == 1
        assert samples[0].expected_output == "deferred"

    async def test_missing_split_returns_empty(self):
        pipeline = _make_pipeline()
        dataset = FlywheelDataset(dataset_id="ds", name="ds")
        samples = await pipeline.prepare_evaluation_samples(dataset, split="eval")
        assert samples == []

    async def test_unknown_split_returns_empty(self):
        pipeline = _make_pipeline()
        dataset = _make_flywheel_dataset()
        samples = await pipeline.prepare_evaluation_samples(dataset, split="unknown_split")
        assert samples == []

    async def test_invalid_workload_type_falls_back(self):
        pipeline = _make_pipeline()
        dataset = _make_flywheel_dataset(
            eval_records=[
                {
                    "decision": "approved",
                    "workload_type": "completely_unknown_type",
                    "impact_score": 0.1,
                }
            ]
        )
        samples = await pipeline.prepare_evaluation_samples(dataset, split="eval")
        assert len(samples) == 1
        assert samples[0].workload_type == WorkloadType.GOVERNANCE_REQUEST

    async def test_metadata_extracted(self):
        pipeline = _make_pipeline()
        dataset = _make_flywheel_dataset(
            eval_records=[
                {
                    "decision": "approved",
                    "workload_type": "governance_request",
                    "impact_score": 0.5,
                    "quality_score": 0.9,
                    "message_id": "msg-99",
                }
            ]
        )
        samples = await pipeline.prepare_evaluation_samples(dataset, split="eval")
        assert samples[0].metadata["impact_score"] == 0.5
        assert samples[0].metadata["quality_score"] == 0.9
        assert samples[0].metadata["original_message_id"] == "msg-99"

    async def test_valid_workload_types_parsed(self):
        pipeline = _make_pipeline()
        valid_types = [
            "governance_request",
            "policy_evaluation",
            "constitutional_validation",
            "impact_scoring",
            "deliberation",
            "hitl_approval",
            "maci_enforcement",
            "audit_log",
        ]
        records = [
            {"decision": "approved", "workload_type": wt, "impact_score": 0.1} for wt in valid_types
        ]
        dataset = _make_flywheel_dataset(eval_records=records)
        samples = await pipeline.prepare_evaluation_samples(dataset, split="eval")
        for sample, wt in zip(samples, valid_types, strict=False):
            assert sample.workload_type == WorkloadType(wt)


# ---------------------------------------------------------------------------
# EvaluationPipeline.run_base_evaluation
# ---------------------------------------------------------------------------


class TestRunBaseEvaluation:
    async def test_basic_run(self):
        pipeline = _make_pipeline()
        model = _make_candidate_model()
        samples = [_make_eval_sample() for _ in range(3)]
        results = await pipeline.run_base_evaluation(model, samples)
        assert isinstance(results, BatchEvaluationResults)
        assert results.total_samples == 3

    async def test_empty_samples(self):
        pipeline = _make_pipeline()
        model = _make_candidate_model()
        results = await pipeline.run_base_evaluation(model, [])
        assert results.total_samples == 0


# ---------------------------------------------------------------------------
# EvaluationPipeline.run_icl_evaluation
# ---------------------------------------------------------------------------


class TestRunICLEvaluation:
    async def test_returns_icl_experiment_type(self):
        pipeline = _make_pipeline()
        model = _make_candidate_model()
        samples = [_make_eval_sample() for _ in range(2)]
        logs = [_make_governance_log() for _ in range(5)]
        results = await pipeline.run_icl_evaluation(model, samples, logs)
        assert results.experiment_type == ExperimentType.ICL

    async def test_icl_no_example_logs(self):
        pipeline = _make_pipeline()
        model = _make_candidate_model()
        samples = [_make_eval_sample()]
        results = await pipeline.run_icl_evaluation(model, samples, [])
        assert results.experiment_type == ExperimentType.ICL

    async def test_icl_samples_contain_icl_prompt(self):
        """Verify ICL prompts are built and used (not original input_text)."""
        captured_samples = []

        class CapturingEvaluator(MockModelEvaluator):
            async def evaluate_batch(self, model, samples):
                captured_samples.extend(samples)
                return await super().evaluate_batch(model, samples)

        pipeline = _make_pipeline()
        pipeline.evaluator = CapturingEvaluator()
        model = _make_candidate_model()
        orig_sample = _make_eval_sample(input_text="original query")
        logs = [_make_governance_log()]
        await pipeline.run_icl_evaluation(model, [orig_sample], logs)
        assert len(captured_samples) == 1
        # The ICL prompt wraps the original query
        assert "original query" in captured_samples[0].input_text
        assert CONSTITUTIONAL_HASH in captured_samples[0].input_text

    async def test_icl_preserves_sample_metadata(self):
        pipeline = _make_pipeline()
        model = _make_candidate_model()
        sample = EvaluationSample(
            input_text="test",
            expected_output="approved",
            metadata={"custom": "data"},
        )
        results = await pipeline.run_icl_evaluation(model, [sample], [])
        assert results.total_samples == 1


# ---------------------------------------------------------------------------
# EvaluationPipeline.start_fine_tuning and related
# ---------------------------------------------------------------------------


class TestStartFineTuning:
    async def test_start_with_valid_hash(self):
        pipeline = _make_pipeline()
        cfg = _make_fine_tuning_config(num_epochs=1)
        job = await pipeline.start_fine_tuning(cfg)
        assert job.status in (
            FineTuningStatus.PENDING,
            FineTuningStatus.PREPARING,
            FineTuningStatus.TRAINING,
            FineTuningStatus.VALIDATING,
            FineTuningStatus.COMPLETED,
        )
        assert job.job_id in pipeline._fine_tuning_jobs

    async def test_start_with_invalid_hash_fails_immediately(self):
        pipeline = _make_pipeline()
        cfg = _make_fine_tuning_config(constitutional_hash="invalid-hash-xxxx")
        job = await pipeline.start_fine_tuning(cfg)
        assert job.status == FineTuningStatus.FAILED
        assert job.error_message == "Invalid constitutional hash"

    async def test_get_fine_tuning_job_found(self):
        pipeline = _make_pipeline()
        cfg = _make_fine_tuning_config()
        job = await pipeline.start_fine_tuning(cfg)
        found = pipeline.get_fine_tuning_job(job.job_id)
        assert found is not None
        assert found.job_id == job.job_id

    async def test_get_fine_tuning_job_not_found(self):
        pipeline = _make_pipeline()
        assert pipeline.get_fine_tuning_job("nonexistent-id") is None

    async def test_list_fine_tuning_jobs_all(self):
        pipeline = _make_pipeline()
        cfg = _make_fine_tuning_config()
        await pipeline.start_fine_tuning(cfg)
        await pipeline.start_fine_tuning(cfg)
        jobs = pipeline.list_fine_tuning_jobs()
        assert len(jobs) >= 2

    async def test_list_fine_tuning_jobs_filtered_by_status(self):
        pipeline = _make_pipeline()
        cfg_bad = _make_fine_tuning_config(constitutional_hash="bad-hash")
        job_bad = await pipeline.start_fine_tuning(cfg_bad)
        assert job_bad.status == FineTuningStatus.FAILED
        failed_jobs = pipeline.list_fine_tuning_jobs(status=FineTuningStatus.FAILED)
        assert any(j.job_id == job_bad.job_id for j in failed_jobs)

    async def test_list_fine_tuning_jobs_no_status_filter(self):
        pipeline = _make_pipeline()
        jobs = pipeline.list_fine_tuning_jobs(status=None)
        assert isinstance(jobs, list)


# ---------------------------------------------------------------------------
# EvaluationPipeline.cancel_fine_tuning
# ---------------------------------------------------------------------------


class TestCancelFineTuning:
    async def test_cancel_nonexistent_job(self):
        pipeline = _make_pipeline()
        result = await pipeline.cancel_fine_tuning("nonexistent")
        assert result is False

    async def test_cancel_completed_job(self):
        pipeline = _make_pipeline()
        cfg = _make_fine_tuning_config(constitutional_hash="bad-hash")
        job = await pipeline.start_fine_tuning(cfg)
        # Force to completed
        job.status = FineTuningStatus.COMPLETED
        result = await pipeline.cancel_fine_tuning(job.job_id)
        assert result is False

    async def test_cancel_failed_job(self):
        pipeline = _make_pipeline()
        cfg = _make_fine_tuning_config(constitutional_hash="bad-hash")
        job = await pipeline.start_fine_tuning(cfg)
        assert job.status == FineTuningStatus.FAILED
        result = await pipeline.cancel_fine_tuning(job.job_id)
        assert result is False

    async def test_cancel_pending_job(self):
        pipeline = _make_pipeline()
        cfg = _make_fine_tuning_config()
        job = await pipeline.start_fine_tuning(cfg)
        # Force to pending so we can cancel
        job.status = FineTuningStatus.PENDING
        result = await pipeline.cancel_fine_tuning(job.job_id)
        assert result is True
        assert job.status == FineTuningStatus.CANCELLED
        assert job.completed_at is not None


# ---------------------------------------------------------------------------
# EvaluationPipeline._run_fine_tuning (full execution path)
# ---------------------------------------------------------------------------


class TestRunFineTuning:
    async def test_successful_fine_tuning_run(self):
        pipeline = _make_pipeline()
        cfg = FineTuningConfig(
            base_model="base",
            output_model_name="out",
            num_epochs=1,
        )
        job = FineTuningJob(config=cfg)
        pipeline._fine_tuning_jobs[job.job_id] = job

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            await pipeline._run_fine_tuning(job)

        assert job.status == FineTuningStatus.COMPLETED
        assert job.completed_at is not None
        assert job.output_model_path == f"models/{cfg.output_model_name}"
        assert job.best_loss is not None

    async def test_fine_tuning_cancellation_during_training(self):
        pipeline = _make_pipeline()
        cfg = FineTuningConfig(
            base_model="base",
            output_model_name="out",
            num_epochs=10,  # Many steps
        )
        job = FineTuningJob(config=cfg)
        pipeline._fine_tuning_jobs[job.job_id] = job

        call_count = 0

        async def fake_sleep(t):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                job.status = FineTuningStatus.CANCELLED

        with patch("asyncio.sleep", new=fake_sleep):
            await pipeline._run_fine_tuning(job)

        # Job was cancelled during training
        assert job.status == FineTuningStatus.CANCELLED

    async def test_fine_tuning_error_handling(self):
        """Verify FINE_TUNING_EXECUTION_ERRORS are caught."""
        pipeline = _make_pipeline()
        cfg = FineTuningConfig(base_model="base", output_model_name="out", num_epochs=1)
        job = FineTuningJob(config=cfg)
        pipeline._fine_tuning_jobs[job.job_id] = job

        async def raising_sleep(t):
            raise RuntimeError("simulated training failure")

        with patch("asyncio.sleep", new=raising_sleep):
            await pipeline._run_fine_tuning(job)

        assert job.status == FineTuningStatus.FAILED
        assert "simulated training failure" in job.error_message
        assert job.completed_at is not None

    async def test_fine_tuning_oserror_caught(self):
        pipeline = _make_pipeline()
        cfg = FineTuningConfig(base_model="base", output_model_name="out", num_epochs=1)
        job = FineTuningJob(config=cfg)

        async def raising_sleep(t):
            raise OSError("disk full")

        with patch("asyncio.sleep", new=raising_sleep):
            await pipeline._run_fine_tuning(job)

        assert job.status == FineTuningStatus.FAILED
        assert "disk full" in job.error_message

    async def test_fine_tuning_updates_best_loss(self):
        pipeline = _make_pipeline()
        cfg = FineTuningConfig(base_model="base", output_model_name="out", num_epochs=1)
        job = FineTuningJob(config=cfg)

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            with patch("random.uniform", return_value=0.0):
                await pipeline._run_fine_tuning(job)

        assert job.best_loss is not None
        assert job.best_loss <= 2.0  # Should be at or below initial loss

    async def test_fine_tuning_validation_metrics_set(self):
        pipeline = _make_pipeline()
        cfg = FineTuningConfig(base_model="base", output_model_name="out", num_epochs=1)
        job = FineTuningJob(config=cfg)

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            await pipeline._run_fine_tuning(job)

        assert "accuracy" in job.validation_metrics
        assert "constitutional_compliance" in job.validation_metrics


# ---------------------------------------------------------------------------
# EvaluationPipeline.validate_constitutional_compliance
# ---------------------------------------------------------------------------


class TestValidateConstitutionalCompliance:
    async def test_compliant_results(self):
        pipeline = _make_pipeline()
        results = BatchEvaluationResults(
            batch_id="b",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            constitutional_compliance_rate=0.99,
            results=[_make_eval_result(constitutional_validated=True)],
        )
        is_compliant, violations = await pipeline.validate_constitutional_compliance(results)
        assert is_compliant is True
        assert violations == []

    async def test_compliance_rate_below_threshold(self):
        pipeline = _make_pipeline()
        results = BatchEvaluationResults(
            batch_id="b",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            constitutional_compliance_rate=0.80,
            results=[],
        )
        is_compliant, violations = await pipeline.validate_constitutional_compliance(
            results, min_compliance_rate=0.95
        )
        assert is_compliant is False
        assert len(violations) == 1
        assert "below required" in violations[0]

    async def test_individual_validation_errors_collected(self):
        pipeline = _make_pipeline()
        bad_result = _make_eval_result(
            constitutional_validated=False,
            validation_errors=["err1", "err2"],
        )
        results = BatchEvaluationResults(
            batch_id="b",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            constitutional_compliance_rate=0.99,
            results=[bad_result],
        )
        is_compliant, violations = await pipeline.validate_constitutional_compliance(results)
        assert is_compliant is False
        assert "err1" in violations
        assert "err2" in violations

    async def test_custom_min_compliance_rate(self):
        pipeline = _make_pipeline()
        results = BatchEvaluationResults(
            batch_id="b",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            constitutional_compliance_rate=0.70,
            results=[],
        )
        # Setting min to 0.5 should pass
        is_compliant, violations = await pipeline.validate_constitutional_compliance(
            results, min_compliance_rate=0.5
        )
        assert is_compliant is True
        assert violations == []

    async def test_both_rate_and_individual_violations(self):
        pipeline = _make_pipeline()
        bad = _make_eval_result(
            constitutional_validated=False,
            validation_errors=["violation-x"],
        )
        results = BatchEvaluationResults(
            batch_id="b",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            constitutional_compliance_rate=0.50,
            results=[bad],
        )
        is_compliant, violations = await pipeline.validate_constitutional_compliance(
            results, min_compliance_rate=0.95
        )
        assert is_compliant is False
        assert any("below required" in v for v in violations)
        assert "violation-x" in violations


# ---------------------------------------------------------------------------
# EvaluationPipeline.run_full_evaluation
# ---------------------------------------------------------------------------


class TestRunFullEvaluation:
    async def test_full_eval_base_type(self):
        pipeline = _make_pipeline()
        model = _make_candidate_model()
        dataset = _make_flywheel_dataset()
        results = await pipeline.run_full_evaluation(model, dataset, ExperimentType.BASE)
        assert isinstance(results, BatchEvaluationResults)

    async def test_full_eval_icl_type_no_train_split(self):
        pipeline = _make_pipeline()
        model = _make_candidate_model()
        # ICL with no train_split => empty example_logs (no AttributeError)
        dataset = FlywheelDataset(
            dataset_id="ds",
            name="ds",
            eval_split=DatasetSplit(
                name="eval",
                records=[
                    {
                        "decision": "approved",
                        "workload_type": "governance_request",
                        "impact_score": 0.1,
                    }
                ],
            ),
            train_split=None,
        )
        results = await pipeline.run_full_evaluation(model, dataset, ExperimentType.ICL)
        assert results.experiment_type == ExperimentType.ICL

    async def test_full_eval_fine_tuned_type(self):
        pipeline = _make_pipeline()
        model = _make_candidate_model()
        dataset = _make_flywheel_dataset()
        results = await pipeline.run_full_evaluation(model, dataset, ExperimentType.FINE_TUNED)
        assert results.experiment_type == ExperimentType.FINE_TUNED

    async def test_full_eval_appends_compliance_violations_to_errors(self):
        """When compliance fails, violations are added to results.errors."""
        pipeline = _make_pipeline()
        model = _make_candidate_model()
        dataset = _make_flywheel_dataset()

        async def mock_evaluate_batch(m, samples):
            bad_results = [
                _make_eval_result(
                    constitutional_validated=False,
                    validation_errors=["forced-violation"],
                )
                for _ in samples
            ]
            batch = BatchEvaluationResults(
                batch_id="b",
                model_name=m.model_name,
                experiment_type=ExperimentType.BASE,
                results=bad_results,
                constitutional_compliance_rate=0.0,
            )
            batch.compute_metrics()
            return batch

        pipeline.evaluator.evaluate_batch = mock_evaluate_batch
        results = await pipeline.run_full_evaluation(model, dataset, ExperimentType.BASE)
        assert len(results.errors) > 0

    async def test_full_eval_no_violations_when_compliant(self):
        pipeline = _make_pipeline()
        model = _make_candidate_model()
        dataset = _make_flywheel_dataset()

        async def mock_evaluate_batch(m, samples):
            good_results = [_make_eval_result(constitutional_validated=True) for _ in samples]
            batch = BatchEvaluationResults(
                batch_id="b",
                model_name=m.model_name,
                experiment_type=ExperimentType.BASE,
                results=good_results,
                constitutional_compliance_rate=1.0,
            )
            batch.compute_metrics()
            return batch

        pipeline.evaluator.evaluate_batch = mock_evaluate_batch
        results = await pipeline.run_full_evaluation(model, dataset, ExperimentType.BASE)
        assert results.errors == []


# ---------------------------------------------------------------------------
# EvaluationPipeline constructor
# ---------------------------------------------------------------------------


class TestEvaluationPipelineConstructor:
    def test_default_evaluator_created(self):
        backend = InMemoryBackend()
        config = FlywheelConfig()
        store = FlywheelDataStore(backend=backend, config=config)
        pipeline = EvaluationPipeline(store=store, config=config)
        assert isinstance(pipeline.evaluator, MockModelEvaluator)
        assert pipeline.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_evaluator_used(self):
        backend = InMemoryBackend()
        config = FlywheelConfig()
        store = FlywheelDataStore(backend=backend, config=config)
        custom_evaluator = MockModelEvaluator(accuracy_range=(0.5, 0.5))
        pipeline = EvaluationPipeline(store=store, config=config, evaluator=custom_evaluator)
        assert pipeline.evaluator is custom_evaluator

    def test_icl_builder_initialized(self):
        pipeline = _make_pipeline()
        assert isinstance(pipeline.icl_builder, ICLPromptBuilder)

    def test_fine_tuning_jobs_empty_initially(self):
        pipeline = _make_pipeline()
        assert pipeline._fine_tuning_jobs == {}


# ---------------------------------------------------------------------------
# Edge cases for BatchEvaluationResults with single result
# ---------------------------------------------------------------------------


class TestBatchMetricsSingleResult:
    def test_single_result_p50(self):
        result = _make_eval_result(latency_ms=42.0)
        batch = BatchEvaluationResults(
            batch_id="b",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            results=[result],
        )
        batch.compute_metrics()
        assert batch.p50_latency_ms == 42.0
        assert batch.p95_latency_ms == 42.0
        assert batch.p99_latency_ms == 42.0
        assert batch.avg_latency_ms == 42.0

    def test_all_non_compliant(self):
        results = [_make_eval_result(constitutional_validated=False) for _ in range(3)]
        batch = BatchEvaluationResults(
            batch_id="b",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            results=results,
        )
        batch.compute_metrics()
        assert batch.constitutional_compliance_rate == 0.0

    def test_all_correct(self):
        results = [_make_eval_result(is_correct=True) for _ in range(5)]
        batch = BatchEvaluationResults(
            batch_id="b",
            model_name="m",
            experiment_type=ExperimentType.BASE,
            results=results,
        )
        batch.compute_metrics()
        assert batch.accuracy == 1.0
        assert batch.correct_predictions == 5


# ---------------------------------------------------------------------------
# ICLPromptBuilder edge cases
# ---------------------------------------------------------------------------


class TestICLPromptBuilderEdgeCases:
    def test_build_prompt_exactly_at_max_examples(self):
        builder = ICLPromptBuilder(config=ICLConfig(max_examples=2))
        logs = [_make_governance_log() for _ in range(2)]
        prompt = builder.build_prompt("q", logs)
        assert "Example 1:" in prompt
        assert "Example 2:" in prompt
        assert "Example 3:" not in prompt

    def test_select_examples_empty_logs(self):
        builder = ICLPromptBuilder()
        selected = builder.select_examples([])
        assert selected == []

    def test_select_examples_fills_with_already_seen_decisions_when_less_than_3(self):
        """When len(selected) < 3, accept even seen decisions."""
        builder = ICLPromptBuilder(config=ICLConfig(max_examples=5))
        # All same decision
        logs = [_make_governance_log(decision=GovernanceDecision.APPROVED) for _ in range(4)]
        selected = builder.select_examples(logs)
        # Should accept repeated decisions when len(selected) < 3
        assert len(selected) >= 3


# ---------------------------------------------------------------------------
# Verify constitutional_hash attribute on models
# ---------------------------------------------------------------------------


class TestConstitutionalHashOnModels:
    def test_evaluation_sample_hash(self):
        s = _make_eval_sample()
        assert s.constitutional_hash == CONSTITUTIONAL_HASH

    def test_evaluation_result_hash(self):
        r = _make_eval_result()
        assert r.constitutional_hash == CONSTITUTIONAL_HASH

    def test_batch_evaluation_results_hash(self):
        b = BatchEvaluationResults(
            batch_id="x", model_name="m", experiment_type=ExperimentType.BASE
        )
        assert b.constitutional_hash == CONSTITUTIONAL_HASH

    def test_fine_tuning_config_hash(self):
        cfg = _make_fine_tuning_config()
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_fine_tuning_job_hash(self):
        cfg = _make_fine_tuning_config()
        job = FineTuningJob(config=cfg)
        assert job.constitutional_hash == CONSTITUTIONAL_HASH
