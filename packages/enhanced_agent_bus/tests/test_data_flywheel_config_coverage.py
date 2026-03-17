# Constitutional Hash: cdd01ef066bc6cf2
"""
Comprehensive tests for src/core/enhanced_agent_bus/data_flywheel/config.py
Target: ≥95% line coverage (82 statements).
"""

import pytest
from packages.enhanced_agent_bus.data_flywheel.config import (
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
from pydantic import ValidationError
from src.core.shared.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# FlywheelMode enum
# ---------------------------------------------------------------------------


class TestFlywheelMode:
    def test_collection_only_value(self):
        assert FlywheelMode.COLLECTION_ONLY == "collection_only"

    def test_evaluation_only_value(self):
        assert FlywheelMode.EVALUATION_ONLY == "evaluation_only"

    def test_full_value(self):
        assert FlywheelMode.FULL == "full"

    def test_disabled_value(self):
        assert FlywheelMode.DISABLED == "disabled"

    def test_all_members_present(self):
        members = {m.value for m in FlywheelMode}
        assert members == {"collection_only", "evaluation_only", "full", "disabled"}

    def test_is_str_enum(self):
        assert isinstance(FlywheelMode.FULL, str)

    def test_equality_with_string(self):
        assert FlywheelMode.FULL == "full"

    def test_from_string(self):
        assert FlywheelMode("disabled") is FlywheelMode.DISABLED


# ---------------------------------------------------------------------------
# ExperimentType enum
# ---------------------------------------------------------------------------


class TestExperimentType:
    def test_base_value(self):
        assert ExperimentType.BASE == "base"

    def test_icl_value(self):
        assert ExperimentType.ICL == "icl"

    def test_fine_tuned_value(self):
        assert ExperimentType.FINE_TUNED == "fine_tuned"

    def test_all_members_present(self):
        members = {m.value for m in ExperimentType}
        assert members == {"base", "icl", "fine_tuned"}

    def test_is_str_enum(self):
        assert isinstance(ExperimentType.ICL, str)

    def test_from_string(self):
        assert ExperimentType("base") is ExperimentType.BASE


# ---------------------------------------------------------------------------
# ModelSelectionStrategy enum
# ---------------------------------------------------------------------------


class TestModelSelectionStrategy:
    def test_cost_optimized_value(self):
        assert ModelSelectionStrategy.COST_OPTIMIZED == "cost_optimized"

    def test_accuracy_optimized_value(self):
        assert ModelSelectionStrategy.ACCURACY_OPTIMIZED == "accuracy_optimized"

    def test_balanced_value(self):
        assert ModelSelectionStrategy.BALANCED == "balanced"

    def test_constitutional_strict_value(self):
        assert ModelSelectionStrategy.CONSTITUTIONAL_STRICT == "constitutional_strict"

    def test_all_members_present(self):
        members = {m.value for m in ModelSelectionStrategy}
        assert members == {
            "cost_optimized",
            "accuracy_optimized",
            "balanced",
            "constitutional_strict",
        }

    def test_is_str_enum(self):
        assert isinstance(ModelSelectionStrategy.BALANCED, str)


# ---------------------------------------------------------------------------
# DataSplitConfig
# ---------------------------------------------------------------------------


class TestDataSplitConfig:
    def test_defaults(self):
        cfg = DataSplitConfig()
        assert cfg.eval_size == 100
        assert cfg.val_ratio == pytest.approx(0.1)
        assert cfg.min_total_records == 50
        assert cfg.random_seed == 42
        assert cfg.limit == 10000
        assert cfg.stratify_by_workload is True

    def test_custom_values(self):
        cfg = DataSplitConfig(
            eval_size=500,
            val_ratio=0.2,
            min_total_records=100,
            random_seed=7,
            limit=5000,
            stratify_by_workload=False,
        )
        assert cfg.eval_size == 500
        assert cfg.val_ratio == pytest.approx(0.2)
        assert cfg.min_total_records == 100
        assert cfg.random_seed == 7
        assert cfg.limit == 5000
        assert cfg.stratify_by_workload is False

    def test_random_seed_none(self):
        cfg = DataSplitConfig(random_seed=None)
        assert cfg.random_seed is None

    def test_eval_size_minimum_boundary(self):
        cfg = DataSplitConfig(eval_size=10)
        assert cfg.eval_size == 10

    def test_eval_size_maximum_boundary(self):
        cfg = DataSplitConfig(eval_size=10000)
        assert cfg.eval_size == 10000

    def test_eval_size_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            DataSplitConfig(eval_size=9)

    def test_eval_size_above_maximum_raises(self):
        with pytest.raises(ValidationError):
            DataSplitConfig(eval_size=10001)

    def test_val_ratio_zero_boundary(self):
        cfg = DataSplitConfig(val_ratio=0.0)
        assert cfg.val_ratio == pytest.approx(0.0)

    def test_val_ratio_near_one_boundary(self):
        cfg = DataSplitConfig(val_ratio=0.99)
        assert cfg.val_ratio == pytest.approx(0.99)

    def test_val_ratio_one_raises(self):
        with pytest.raises(ValidationError):
            DataSplitConfig(val_ratio=1.0)

    def test_val_ratio_negative_raises(self):
        with pytest.raises(ValidationError):
            DataSplitConfig(val_ratio=-0.1)

    def test_min_total_records_minimum(self):
        cfg = DataSplitConfig(min_total_records=10)
        assert cfg.min_total_records == 10

    def test_min_total_records_below_min_raises(self):
        with pytest.raises(ValidationError):
            DataSplitConfig(min_total_records=9)

    def test_limit_minimum(self):
        cfg = DataSplitConfig(limit=100)
        assert cfg.limit == 100

    def test_limit_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            DataSplitConfig(limit=99)


# ---------------------------------------------------------------------------
# ICLConfig
# ---------------------------------------------------------------------------


class TestICLConfig:
    def test_defaults(self):
        cfg = ICLConfig()
        assert cfg.max_context_length == 8192
        assert cfg.reserved_tokens == 2048
        assert cfg.max_examples == 3
        assert cfg.min_examples == 1
        assert cfg.example_selection == "semantic_similarity"

    def test_custom_values(self):
        cfg = ICLConfig(
            max_context_length=4096,
            reserved_tokens=512,
            max_examples=5,
            min_examples=2,
            example_selection="uniform_distribution",
        )
        assert cfg.max_context_length == 4096
        assert cfg.reserved_tokens == 512
        assert cfg.max_examples == 5
        assert cfg.min_examples == 2
        assert cfg.example_selection == "uniform_distribution"

    def test_max_context_length_minimum(self):
        cfg = ICLConfig(max_context_length=512)
        assert cfg.max_context_length == 512

    def test_max_context_length_maximum(self):
        cfg = ICLConfig(max_context_length=128000)
        assert cfg.max_context_length == 128000

    def test_max_context_length_below_min_raises(self):
        with pytest.raises(ValidationError):
            ICLConfig(max_context_length=511)

    def test_max_context_length_above_max_raises(self):
        with pytest.raises(ValidationError):
            ICLConfig(max_context_length=128001)

    def test_reserved_tokens_minimum(self):
        cfg = ICLConfig(reserved_tokens=256)
        assert cfg.reserved_tokens == 256

    def test_reserved_tokens_below_min_raises(self):
        with pytest.raises(ValidationError):
            ICLConfig(reserved_tokens=255)

    def test_max_examples_minimum(self):
        cfg = ICLConfig(max_examples=1)
        assert cfg.max_examples == 1

    def test_max_examples_maximum(self):
        cfg = ICLConfig(max_examples=10)
        assert cfg.max_examples == 10

    def test_max_examples_below_min_raises(self):
        with pytest.raises(ValidationError):
            ICLConfig(max_examples=0)

    def test_max_examples_above_max_raises(self):
        with pytest.raises(ValidationError):
            ICLConfig(max_examples=11)

    def test_min_examples_zero_is_valid(self):
        cfg = ICLConfig(min_examples=0)
        assert cfg.min_examples == 0

    def test_min_examples_negative_raises(self):
        with pytest.raises(ValidationError):
            ICLConfig(min_examples=-1)


# ---------------------------------------------------------------------------
# TrainingConfig
# ---------------------------------------------------------------------------


class TestTrainingConfig:
    def test_defaults(self):
        cfg = TrainingConfig()
        assert cfg.training_type == "sft"
        assert cfg.finetuning_type == "lora"
        assert cfg.epochs == 2
        assert cfg.batch_size == 16
        assert cfg.learning_rate == pytest.approx(0.0001)
        assert cfg.lora_rank == 32
        assert cfg.lora_alpha == 64
        assert cfg.lora_dropout == pytest.approx(0.1)

    def test_custom_values(self):
        cfg = TrainingConfig(
            training_type="dpo",
            finetuning_type="full",
            epochs=5,
            batch_size=32,
            learning_rate=0.001,
            lora_rank=64,
            lora_alpha=128,
            lora_dropout=0.05,
        )
        assert cfg.training_type == "dpo"
        assert cfg.finetuning_type == "full"
        assert cfg.epochs == 5
        assert cfg.batch_size == 32
        assert cfg.learning_rate == pytest.approx(0.001)
        assert cfg.lora_rank == 64
        assert cfg.lora_alpha == 128
        assert cfg.lora_dropout == pytest.approx(0.05)

    def test_epochs_minimum(self):
        cfg = TrainingConfig(epochs=1)
        assert cfg.epochs == 1

    def test_epochs_maximum(self):
        cfg = TrainingConfig(epochs=10)
        assert cfg.epochs == 10

    def test_epochs_below_min_raises(self):
        with pytest.raises(ValidationError):
            TrainingConfig(epochs=0)

    def test_epochs_above_max_raises(self):
        with pytest.raises(ValidationError):
            TrainingConfig(epochs=11)

    def test_batch_size_minimum(self):
        cfg = TrainingConfig(batch_size=1)
        assert cfg.batch_size == 1

    def test_batch_size_maximum(self):
        cfg = TrainingConfig(batch_size=128)
        assert cfg.batch_size == 128

    def test_batch_size_below_min_raises(self):
        with pytest.raises(ValidationError):
            TrainingConfig(batch_size=0)

    def test_batch_size_above_max_raises(self):
        with pytest.raises(ValidationError):
            TrainingConfig(batch_size=129)

    def test_learning_rate_zero_raises(self):
        with pytest.raises(ValidationError):
            TrainingConfig(learning_rate=0.0)

    def test_learning_rate_maximum(self):
        cfg = TrainingConfig(learning_rate=0.1)
        assert cfg.learning_rate == pytest.approx(0.1)

    def test_learning_rate_above_max_raises(self):
        with pytest.raises(ValidationError):
            TrainingConfig(learning_rate=0.101)

    def test_lora_rank_minimum(self):
        cfg = TrainingConfig(lora_rank=4)
        assert cfg.lora_rank == 4

    def test_lora_rank_maximum(self):
        cfg = TrainingConfig(lora_rank=256)
        assert cfg.lora_rank == 256

    def test_lora_rank_below_min_raises(self):
        with pytest.raises(ValidationError):
            TrainingConfig(lora_rank=3)

    def test_lora_rank_above_max_raises(self):
        with pytest.raises(ValidationError):
            TrainingConfig(lora_rank=257)

    def test_lora_alpha_minimum(self):
        cfg = TrainingConfig(lora_alpha=8)
        assert cfg.lora_alpha == 8

    def test_lora_alpha_maximum(self):
        cfg = TrainingConfig(lora_alpha=512)
        assert cfg.lora_alpha == 512

    def test_lora_alpha_below_min_raises(self):
        with pytest.raises(ValidationError):
            TrainingConfig(lora_alpha=7)

    def test_lora_alpha_above_max_raises(self):
        with pytest.raises(ValidationError):
            TrainingConfig(lora_alpha=513)

    def test_lora_dropout_zero_boundary(self):
        cfg = TrainingConfig(lora_dropout=0.0)
        assert cfg.lora_dropout == pytest.approx(0.0)

    def test_lora_dropout_maximum(self):
        cfg = TrainingConfig(lora_dropout=0.5)
        assert cfg.lora_dropout == pytest.approx(0.5)

    def test_lora_dropout_above_max_raises(self):
        with pytest.raises(ValidationError):
            TrainingConfig(lora_dropout=0.51)

    def test_lora_dropout_negative_raises(self):
        with pytest.raises(ValidationError):
            TrainingConfig(lora_dropout=-0.01)


# ---------------------------------------------------------------------------
# EvaluationConfig
# ---------------------------------------------------------------------------


class TestEvaluationConfig:
    def test_defaults(self):
        cfg = EvaluationConfig()
        assert cfg.use_llm_judge is True
        assert cfg.judge_model == "llama-3.1-70b-instruct"
        assert cfg.similarity_threshold == pytest.approx(0.7)
        assert cfg.constitutional_compliance_weight == pytest.approx(0.3)
        assert cfg.accuracy_weight == pytest.approx(0.5)
        assert cfg.cost_weight == pytest.approx(0.2)

    def test_custom_values(self):
        cfg = EvaluationConfig(
            use_llm_judge=False,
            judge_model="gpt-4",
            similarity_threshold=0.9,
            constitutional_compliance_weight=0.4,
            accuracy_weight=0.4,
            cost_weight=0.2,
        )
        assert cfg.use_llm_judge is False
        assert cfg.judge_model == "gpt-4"
        assert cfg.similarity_threshold == pytest.approx(0.9)
        assert cfg.constitutional_compliance_weight == pytest.approx(0.4)
        assert cfg.accuracy_weight == pytest.approx(0.4)
        assert cfg.cost_weight == pytest.approx(0.2)

    def test_similarity_threshold_zero(self):
        cfg = EvaluationConfig(similarity_threshold=0.0)
        assert cfg.similarity_threshold == pytest.approx(0.0)

    def test_similarity_threshold_one(self):
        cfg = EvaluationConfig(similarity_threshold=1.0)
        assert cfg.similarity_threshold == pytest.approx(1.0)

    def test_similarity_threshold_negative_raises(self):
        with pytest.raises(ValidationError):
            EvaluationConfig(similarity_threshold=-0.01)

    def test_similarity_threshold_above_max_raises(self):
        with pytest.raises(ValidationError):
            EvaluationConfig(similarity_threshold=1.01)

    def test_constitutional_compliance_weight_zero(self):
        cfg = EvaluationConfig(constitutional_compliance_weight=0.0)
        assert cfg.constitutional_compliance_weight == pytest.approx(0.0)

    def test_constitutional_compliance_weight_one(self):
        cfg = EvaluationConfig(constitutional_compliance_weight=1.0)
        assert cfg.constitutional_compliance_weight == pytest.approx(1.0)

    def test_constitutional_compliance_weight_negative_raises(self):
        with pytest.raises(ValidationError):
            EvaluationConfig(constitutional_compliance_weight=-0.1)

    def test_accuracy_weight_boundaries(self):
        cfg = EvaluationConfig(accuracy_weight=0.0)
        assert cfg.accuracy_weight == pytest.approx(0.0)
        cfg2 = EvaluationConfig(accuracy_weight=1.0)
        assert cfg2.accuracy_weight == pytest.approx(1.0)

    def test_cost_weight_boundaries(self):
        cfg = EvaluationConfig(cost_weight=0.0)
        assert cfg.cost_weight == pytest.approx(0.0)
        cfg2 = EvaluationConfig(cost_weight=1.0)
        assert cfg2.cost_weight == pytest.approx(1.0)

    def test_cost_weight_negative_raises(self):
        with pytest.raises(ValidationError):
            EvaluationConfig(cost_weight=-0.01)


# ---------------------------------------------------------------------------
# CandidateModel
# ---------------------------------------------------------------------------


class TestCandidateModel:
    def test_required_model_name(self):
        with pytest.raises(ValidationError):
            CandidateModel()  # model_name is required

    def test_minimal_creation(self):
        m = CandidateModel(model_name="my-model")
        assert m.model_name == "my-model"
        assert m.model_type == "llm"
        assert m.context_length == 8192
        assert m.gpu_requirements == 1
        assert m.enable_fine_tuning is False
        assert m.fine_tuning_target is None
        assert m.cost_per_1k_tokens == pytest.approx(0.0)

    def test_full_creation(self):
        m = CandidateModel(
            model_name="org/model-7b",
            model_type="embedding",
            context_length=4096,
            gpu_requirements=2,
            enable_fine_tuning=True,
            fine_tuning_target="org/model-7b-ft",
            cost_per_1k_tokens=0.05,
        )
        assert m.model_name == "org/model-7b"
        assert m.model_type == "embedding"
        assert m.context_length == 4096
        assert m.gpu_requirements == 2
        assert m.enable_fine_tuning is True
        assert m.fine_tuning_target == "org/model-7b-ft"
        assert m.cost_per_1k_tokens == pytest.approx(0.05)

    def test_gpu_requirements_minimum(self):
        m = CandidateModel(model_name="m", gpu_requirements=1)
        assert m.gpu_requirements == 1

    def test_gpu_requirements_maximum(self):
        m = CandidateModel(model_name="m", gpu_requirements=8)
        assert m.gpu_requirements == 8

    def test_gpu_requirements_zero_raises(self):
        with pytest.raises(ValidationError):
            CandidateModel(model_name="m", gpu_requirements=0)

    def test_gpu_requirements_above_max_raises(self):
        with pytest.raises(ValidationError):
            CandidateModel(model_name="m", gpu_requirements=9)

    def test_cost_per_1k_tokens_zero(self):
        m = CandidateModel(model_name="m", cost_per_1k_tokens=0.0)
        assert m.cost_per_1k_tokens == pytest.approx(0.0)

    def test_cost_per_1k_tokens_negative_raises(self):
        with pytest.raises(ValidationError):
            CandidateModel(model_name="m", cost_per_1k_tokens=-0.01)

    def test_fine_tuning_target_explicit_none(self):
        m = CandidateModel(model_name="m", fine_tuning_target=None)
        assert m.fine_tuning_target is None

    def test_fine_tuning_target_set(self):
        m = CandidateModel(model_name="m", fine_tuning_target="target-model")
        assert m.fine_tuning_target == "target-model"


# ---------------------------------------------------------------------------
# FlywheelConfig — default construction
# ---------------------------------------------------------------------------


class TestFlywheelConfigDefaults:
    def test_mode_default(self):
        cfg = FlywheelConfig()
        assert cfg.mode == FlywheelMode.COLLECTION_ONLY

    def test_constitutional_hash_default(self):
        cfg = FlywheelConfig()
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_require_constitutional_validation_default(self):
        cfg = FlywheelConfig()
        assert cfg.require_constitutional_validation is True

    def test_log_retention_days_default(self):
        cfg = FlywheelConfig()
        assert cfg.log_retention_days == 90

    def test_max_logs_per_workload_default(self):
        cfg = FlywheelConfig()
        assert cfg.max_logs_per_workload == 100000

    def test_sample_rate_default(self):
        cfg = FlywheelConfig()
        assert cfg.sample_rate == pytest.approx(1.0)

    def test_workload_classification_enabled_default(self):
        cfg = FlywheelConfig()
        assert cfg.workload_classification_enabled is True

    def test_supported_workload_types_default(self):
        cfg = FlywheelConfig()
        expected = [
            "governance_request",
            "policy_evaluation",
            "constitutional_validation",
            "impact_scoring",
            "deliberation",
        ]
        assert cfg.supported_workload_types == expected

    def test_data_split_is_default_instance(self):
        cfg = FlywheelConfig()
        assert isinstance(cfg.data_split, DataSplitConfig)

    def test_icl_is_default_instance(self):
        cfg = FlywheelConfig()
        assert isinstance(cfg.icl, ICLConfig)

    def test_training_is_default_instance(self):
        cfg = FlywheelConfig()
        assert isinstance(cfg.training, TrainingConfig)

    def test_evaluation_is_default_instance(self):
        cfg = FlywheelConfig()
        assert isinstance(cfg.evaluation, EvaluationConfig)

    def test_selection_strategy_default(self):
        cfg = FlywheelConfig()
        assert cfg.selection_strategy == ModelSelectionStrategy.BALANCED

    def test_candidate_models_default_empty(self):
        cfg = FlywheelConfig()
        assert cfg.candidate_models == []

    def test_elasticsearch_url_default(self):
        cfg = FlywheelConfig()
        assert cfg.elasticsearch_url == "http://localhost:9200"

    def test_elasticsearch_index_prefix_default(self):
        cfg = FlywheelConfig()
        assert cfg.elasticsearch_index_prefix == "acgs2-flywheel"

    def test_redis_url_default(self):
        cfg = FlywheelConfig()
        assert cfg.redis_url == "redis://localhost:6379"

    def test_mongodb_url_default_none(self):
        cfg = FlywheelConfig()
        assert cfg.mongodb_url is None

    def test_auto_experiment_threshold_default(self):
        cfg = FlywheelConfig()
        assert cfg.auto_experiment_threshold == 1000

    def test_auto_experiment_interval_hours_default(self):
        cfg = FlywheelConfig()
        assert cfg.auto_experiment_interval_hours == 24

    def test_require_human_approval_default(self):
        cfg = FlywheelConfig()
        assert cfg.require_human_approval is True

    def test_max_concurrent_experiments_default(self):
        cfg = FlywheelConfig()
        assert cfg.max_concurrent_experiments == 2

    def test_experiment_timeout_hours_default(self):
        cfg = FlywheelConfig()
        assert cfg.experiment_timeout_hours == 6


# ---------------------------------------------------------------------------
# FlywheelConfig — custom construction & field validation
# ---------------------------------------------------------------------------


class TestFlywheelConfigCustom:
    def test_mode_full(self):
        cfg = FlywheelConfig(mode=FlywheelMode.FULL)
        assert cfg.mode == FlywheelMode.FULL

    def test_mode_disabled(self):
        cfg = FlywheelConfig(mode=FlywheelMode.DISABLED)
        assert cfg.mode == FlywheelMode.DISABLED

    def test_custom_constitutional_hash(self):
        cfg = FlywheelConfig(constitutional_hash="custom-hash-value")
        assert cfg.constitutional_hash == "custom-hash-value"

    def test_log_retention_days_minimum(self):
        cfg = FlywheelConfig(log_retention_days=1)
        assert cfg.log_retention_days == 1

    def test_log_retention_days_maximum(self):
        cfg = FlywheelConfig(log_retention_days=365)
        assert cfg.log_retention_days == 365

    def test_log_retention_days_below_min_raises(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(log_retention_days=0)

    def test_log_retention_days_above_max_raises(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(log_retention_days=366)

    def test_max_logs_per_workload_minimum(self):
        cfg = FlywheelConfig(max_logs_per_workload=1000)
        assert cfg.max_logs_per_workload == 1000

    def test_max_logs_per_workload_below_min_raises(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(max_logs_per_workload=999)

    def test_sample_rate_zero(self):
        cfg = FlywheelConfig(sample_rate=0.0)
        assert cfg.sample_rate == pytest.approx(0.0)

    def test_sample_rate_one(self):
        cfg = FlywheelConfig(sample_rate=1.0)
        assert cfg.sample_rate == pytest.approx(1.0)

    def test_sample_rate_above_max_raises(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(sample_rate=1.01)

    def test_sample_rate_negative_raises(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(sample_rate=-0.01)

    def test_custom_supported_workload_types(self):
        cfg = FlywheelConfig(supported_workload_types=["custom_type"])
        assert cfg.supported_workload_types == ["custom_type"]

    def test_auto_experiment_threshold_minimum(self):
        cfg = FlywheelConfig(auto_experiment_threshold=100)
        assert cfg.auto_experiment_threshold == 100

    def test_auto_experiment_threshold_below_min_raises(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(auto_experiment_threshold=99)

    def test_auto_experiment_interval_hours_minimum(self):
        cfg = FlywheelConfig(auto_experiment_interval_hours=1)
        assert cfg.auto_experiment_interval_hours == 1

    def test_auto_experiment_interval_hours_maximum(self):
        cfg = FlywheelConfig(auto_experiment_interval_hours=168)
        assert cfg.auto_experiment_interval_hours == 168

    def test_auto_experiment_interval_hours_below_min_raises(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(auto_experiment_interval_hours=0)

    def test_auto_experiment_interval_hours_above_max_raises(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(auto_experiment_interval_hours=169)

    def test_max_concurrent_experiments_minimum(self):
        cfg = FlywheelConfig(max_concurrent_experiments=1)
        assert cfg.max_concurrent_experiments == 1

    def test_max_concurrent_experiments_maximum(self):
        cfg = FlywheelConfig(max_concurrent_experiments=10)
        assert cfg.max_concurrent_experiments == 10

    def test_max_concurrent_experiments_below_min_raises(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(max_concurrent_experiments=0)

    def test_max_concurrent_experiments_above_max_raises(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(max_concurrent_experiments=11)

    def test_experiment_timeout_hours_minimum(self):
        cfg = FlywheelConfig(experiment_timeout_hours=1)
        assert cfg.experiment_timeout_hours == 1

    def test_experiment_timeout_hours_maximum(self):
        cfg = FlywheelConfig(experiment_timeout_hours=24)
        assert cfg.experiment_timeout_hours == 24

    def test_experiment_timeout_hours_below_min_raises(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(experiment_timeout_hours=0)

    def test_experiment_timeout_hours_above_max_raises(self):
        with pytest.raises(ValidationError):
            FlywheelConfig(experiment_timeout_hours=25)

    def test_mongodb_url_set(self):
        cfg = FlywheelConfig(mongodb_url="mongodb://localhost:27017")
        assert cfg.mongodb_url == "mongodb://localhost:27017"

    def test_candidate_models_with_entries(self):
        m = CandidateModel(model_name="test-model")
        cfg = FlywheelConfig(candidate_models=[m])
        assert len(cfg.candidate_models) == 1
        assert cfg.candidate_models[0].model_name == "test-model"

    def test_nested_data_split_custom(self):
        ds = DataSplitConfig(eval_size=200)
        cfg = FlywheelConfig(data_split=ds)
        assert cfg.data_split.eval_size == 200

    def test_nested_icl_custom(self):
        icl = ICLConfig(max_examples=5)
        cfg = FlywheelConfig(icl=icl)
        assert cfg.icl.max_examples == 5

    def test_nested_training_custom(self):
        tr = TrainingConfig(epochs=4)
        cfg = FlywheelConfig(training=tr)
        assert cfg.training.epochs == 4

    def test_nested_evaluation_custom(self):
        ev = EvaluationConfig(use_llm_judge=False)
        cfg = FlywheelConfig(evaluation=ev)
        assert cfg.evaluation.use_llm_judge is False

    def test_model_config_from_attributes(self):
        # Verify from_attributes=True in model_config
        assert FlywheelConfig.model_config.get("from_attributes") is True


# ---------------------------------------------------------------------------
# FlywheelConfig.validate_constitutional_hash()
# ---------------------------------------------------------------------------


class TestValidateConstitutionalHash:
    def test_returns_true_for_correct_hash(self):
        cfg = FlywheelConfig()
        assert cfg.validate_constitutional_hash() is True

    def test_returns_false_for_wrong_hash(self):
        cfg = FlywheelConfig(constitutional_hash="wrong-hash")
        assert cfg.validate_constitutional_hash() is False

    def test_returns_false_for_empty_hash(self):
        cfg = FlywheelConfig(constitutional_hash="")
        assert cfg.validate_constitutional_hash() is False

    def test_returns_true_when_explicitly_set_to_correct_hash(self):
        cfg = FlywheelConfig(constitutional_hash=CONSTITUTIONAL_HASH)
        assert cfg.validate_constitutional_hash() is True

    def test_returns_false_for_partial_match(self):
        # A partial/truncated hash must not match
        partial = CONSTITUTIONAL_HASH[:8]
        cfg = FlywheelConfig(constitutional_hash=partial)
        assert cfg.validate_constitutional_hash() is False


# ---------------------------------------------------------------------------
# DEFAULT_FLYWHEEL_CONFIG module-level instance
# ---------------------------------------------------------------------------


class TestDefaultFlywheelConfig:
    def test_is_flywheel_config_instance(self):
        assert isinstance(DEFAULT_FLYWHEEL_CONFIG, FlywheelConfig)

    def test_mode_is_collection_only(self):
        assert DEFAULT_FLYWHEEL_CONFIG.mode == FlywheelMode.COLLECTION_ONLY

    def test_has_two_candidate_models(self):
        assert len(DEFAULT_FLYWHEEL_CONFIG.candidate_models) == 2

    def test_first_candidate_model_name(self):
        assert (
            DEFAULT_FLYWHEEL_CONFIG.candidate_models[0].model_name == "meta/llama-3.2-1b-instruct"
        )

    def test_second_candidate_model_name(self):
        assert (
            DEFAULT_FLYWHEEL_CONFIG.candidate_models[1].model_name == "meta/llama-3.2-3b-instruct"
        )

    def test_first_candidate_fine_tuning_enabled(self):
        assert DEFAULT_FLYWHEEL_CONFIG.candidate_models[0].enable_fine_tuning is True

    def test_second_candidate_fine_tuning_enabled(self):
        assert DEFAULT_FLYWHEEL_CONFIG.candidate_models[1].enable_fine_tuning is True

    def test_first_candidate_context_length(self):
        assert DEFAULT_FLYWHEEL_CONFIG.candidate_models[0].context_length == 8192

    def test_second_candidate_context_length(self):
        assert DEFAULT_FLYWHEEL_CONFIG.candidate_models[1].context_length == 8192

    def test_first_candidate_cost(self):
        assert DEFAULT_FLYWHEEL_CONFIG.candidate_models[0].cost_per_1k_tokens == pytest.approx(
            0.0001
        )

    def test_second_candidate_cost(self):
        assert DEFAULT_FLYWHEEL_CONFIG.candidate_models[1].cost_per_1k_tokens == pytest.approx(
            0.0003
        )

    def test_constitutional_hash_valid(self):
        assert DEFAULT_FLYWHEEL_CONFIG.validate_constitutional_hash() is True

    def test_constitutional_hash_value(self):
        assert DEFAULT_FLYWHEEL_CONFIG.constitutional_hash == CONSTITUTIONAL_HASH

    def test_default_selection_strategy(self):
        assert DEFAULT_FLYWHEEL_CONFIG.selection_strategy == ModelSelectionStrategy.BALANCED

    def test_default_require_human_approval(self):
        assert DEFAULT_FLYWHEEL_CONFIG.require_human_approval is True
