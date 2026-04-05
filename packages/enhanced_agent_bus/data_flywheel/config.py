from __future__ import annotations

import sys
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

sys.modules.setdefault("enhanced_agent_bus.data_flywheel.config", sys.modules[__name__])


class FlywheelMode(str, Enum):
    COLLECTION_ONLY = "collection_only"
    EVALUATION_ONLY = "evaluation_only"
    FULL = "full"
    DISABLED = "disabled"


class ExperimentType(str, Enum):
    BASE = "base"
    ICL = "icl"
    FINE_TUNED = "fine_tuned"


class ModelSelectionStrategy(str, Enum):
    COST_OPTIMIZED = "cost_optimized"
    ACCURACY_OPTIMIZED = "accuracy_optimized"
    BALANCED = "balanced"
    CONSTITUTIONAL_STRICT = "constitutional_strict"


class DataSplitConfig(BaseModel):
    eval_size: int = Field(default=100, ge=10, le=10000)
    val_ratio: float = Field(default=0.1, ge=0.0, lt=1.0)
    min_total_records: int = Field(default=50, ge=10)
    random_seed: int | None = 42
    limit: int = Field(default=10000, ge=100)
    stratify_by_workload: bool = True


class ICLConfig(BaseModel):
    max_context_length: int = Field(default=8192, ge=512, le=128000)
    reserved_tokens: int = Field(default=2048, ge=256)
    max_examples: int = Field(default=3, ge=1, le=10)
    min_examples: int = Field(default=1, ge=0)
    example_selection: str = "semantic_similarity"


class TrainingConfig(BaseModel):
    training_type: str = "sft"
    finetuning_type: str = "lora"
    epochs: int = Field(default=2, ge=1, le=10)
    batch_size: int = Field(default=16, ge=1, le=128)
    learning_rate: float = Field(default=0.0001, gt=0.0, le=0.1)
    lora_rank: int = Field(default=32, ge=4, le=256)
    lora_alpha: int = Field(default=64, ge=8, le=512)
    lora_dropout: float = Field(default=0.1, ge=0.0, le=0.5)


class EvaluationConfig(BaseModel):
    use_llm_judge: bool = True
    judge_model: str = "llama-3.1-70b-instruct"
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    constitutional_compliance_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    accuracy_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    cost_weight: float = Field(default=0.2, ge=0.0, le=1.0)


class CandidateModel(BaseModel):
    model_name: str
    model_type: str = "llm"
    context_length: int = 8192
    gpu_requirements: int = Field(default=1, ge=1, le=8)
    enable_fine_tuning: bool = False
    fine_tuning_target: str | None = None
    cost_per_1k_tokens: float = Field(default=0.0, ge=0.0)


class FlywheelConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mode: FlywheelMode = FlywheelMode.COLLECTION_ONLY
    constitutional_hash: str = CONSTITUTIONAL_HASH
    require_constitutional_validation: bool = True
    log_retention_days: int = Field(default=90, ge=1, le=365)
    max_logs_per_workload: int = Field(default=100000, ge=1000)
    sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    workload_classification_enabled: bool = True
    supported_workload_types: list[str] = [
        "governance_request",
        "policy_evaluation",
        "constitutional_validation",
        "impact_scoring",
        "deliberation",
    ]
    data_split: DataSplitConfig = Field(default_factory=DataSplitConfig)
    icl: ICLConfig = Field(default_factory=ICLConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    selection_strategy: ModelSelectionStrategy = ModelSelectionStrategy.BALANCED
    candidate_models: list[CandidateModel] = Field(default_factory=list)
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index_prefix: str = "acgs2-flywheel"
    redis_url: str = "redis://localhost:6379"
    mongodb_url: str | None = None
    auto_experiment_threshold: int = Field(default=1000, ge=100)
    auto_experiment_interval_hours: int = Field(default=24, ge=1, le=168)
    require_human_approval: bool = True
    max_concurrent_experiments: int = Field(default=2, ge=1, le=10)
    experiment_timeout_hours: int = Field(default=6, ge=1, le=24)

    def validate_constitutional_hash(self) -> bool:
        return bool(self.constitutional_hash) and self.constitutional_hash == CONSTITUTIONAL_HASH


DEFAULT_FLYWHEEL_CONFIG = FlywheelConfig(
    candidate_models=[
        CandidateModel(
            model_name="meta/llama-3.2-1b-instruct",
            enable_fine_tuning=True,
            fine_tuning_target="meta/llama-3.2-1b-instruct-ft",
            context_length=8192,
            cost_per_1k_tokens=0.0001,
        ),
        CandidateModel(
            model_name="meta/llama-3.2-3b-instruct",
            enable_fine_tuning=True,
            fine_tuning_target="meta/llama-3.2-3b-instruct-ft",
            context_length=8192,
            cost_per_1k_tokens=0.0003,
        ),
    ]
)
