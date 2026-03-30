# ADR-0001: Governed Flywheel Integration Inside ACGS Runtime

## Status

Proposed

## Date

2026-03-30

## Context

We want to integrate a data-flywheel capability similar in intent to NVIDIA's Data Flywheel
blueprint: collect governed runtime traffic, assemble bounded datasets, evaluate candidate
improvements, and promote only validated changes.

This repository already contains several critical primitives that change the integration shape:

- `packages/enhanced_agent_bus/data_flywheel/config.py` already defines flywheel configuration
  models.
- `packages/enhanced_agent_bus/adaptive_governance/governance_engine.py` already integrates
  feedback and adaptive decisioning.
- `packages/enhanced_agent_bus/ab_testing.py` already provides champion/candidate routing.
- `packages/enhanced_agent_bus/feedback_handler/` already stores decision-linked feedback.
- `packages/enhanced_agent_bus/tests/test_message_processor_independent_validator_gate.py`
  documents the independent-validator invariant.
- `src/core/services/api_gateway/routes/evolution_control.py` expects a self-evolution control
  plane that is not checked in under `src/core/self_evolution/`.

The external NVIDIA/MLRun blueprint uses a separate MLOps topology. ACGS is different: governance,
role separation, policy validation, and approval chains are already first-class runtime concerns.
Any flywheel integration that bypasses those concerns would create a second, weaker control plane.

## Decision

Implement the flywheel as a bounded self-evolution subsystem inside the ACGS runtime.

The canonical execution model is:

1. Observe governed decision and feedback traffic through gateway and bus integrations.
2. Normalize it into tenant-local, constitutional-hash-bound workload datasets.
3. Generate bounded governance candidates first:
   - thresholds
   - routing policies
   - prompt and evaluator variants
   - context-selection strategies
4. Run offline replay before any live exposure.
5. Use existing A/B and canary primitives for shadow and low-percent routing.
6. Require independent validation and, for high-impact changes, HITL approval before promotion.
7. Persist immutable evidence bundles for every recommendation, promotion, rejection, and rollback.

## Decision Drivers

- Preserve constitutional governance and MACI separation of powers.
- Reuse existing platform primitives instead of duplicating orchestration stacks.
- Keep storage and run-state concerns aligned with existing `persistence/` and
  `saga_persistence/` boundaries.
- Keep tenant isolation and fail-closed behavior explicit.
- Deliver incremental value before introducing model fine-tuning complexity.

## Scope

### In scope

- Extending `packages/enhanced_agent_bus/data_flywheel/` from config-only to a full bounded
  subsystem.
- Creating the missing `src/core/self_evolution/` control-plane package.
- Admin APIs for run control, evidence access, promotion, and rollback.
- Offline replay, shadow evaluation, canary promotion, and evidence bundle generation.
- Frontend admin visibility for flywheel runs and candidate comparisons.

### Out of scope for the first implementation

- Production LoRA or full model fine-tuning.
- New MongoDB or Elasticsearch system-of-record dependencies.
- Automatic promotion based purely on offline score improvements.
- Cross-tenant dataset pooling.

## Consequences

### Positive

- The flywheel inherits ACGS governance invariants instead of bypassing them.
- Promotion and rollback can reuse existing A/B routing and deliberation infrastructure.
- Evidence generation becomes part of the same constitutional audit trail rather than a sidecar.
- The repo closes an existing control-plane gap by implementing `src/core/self_evolution/`.

### Negative

- The initial implementation is slower than dropping in a generic MLOps pipeline.
- More integration work is required in the bus, gateway, persistence, and frontend layers.
- Strong governance gates will limit how quickly candidates can be promoted.

### Risks

- Existing `data_flywheel/config.py` fields still assume Elastic/Mongo-oriented topology and will
  need migration or deprecation.
- The missing `src/core/self_evolution/` package is already referenced by the gateway, so partial
  implementation could leave the control plane inconsistent.
- If event normalization is sloppy, tenant or constitutional-hash leakage could contaminate
  evaluation datasets.

## Alternatives Considered

### 1. Copy the NVIDIA/MLRun topology directly

Rejected.

Reason:
- It would duplicate orchestration outside ACGS governance.
- It would add operational complexity before solving the internal control-plane gap.
- It would bias storage and run-state design toward external blueprint assumptions.

### 2. Build a separate flywheel microservice outside `enhanced_agent_bus`

Rejected.

Reason:
- It weakens the connection between live governance decisions and evaluation/promotion.
- It risks creating a second approval model that does not honor independent-validator rules.

### 3. Delay flywheel work until full model fine-tuning is available

Rejected.

Reason:
- The repo can deliver value now through threshold, prompt, routing, and evaluator optimization.
- Waiting for model training would block evidence-backed replay and canary infrastructure.

## Invariants

- Every flywheel record must carry `constitutional_hash`.
- Every workload grouping must remain tenant-local.
- Promotion must remain impossible without independent validation.
- High-impact promotions must require explicit human approval.
- Replay and export must fail closed on redaction or evidence-generation failure.

## Implementation Notes

- Extend the existing `packages/enhanced_agent_bus/data_flywheel/` namespace.
- Add `src/core/self_evolution/` as the canonical admin and operator control plane expected by the
  gateway.
- Store immutable flywheel metadata and evidence in `persistence/`.
- Store active run state and orchestration progress in `saga_persistence/`.
- Reuse `ab_testing.py` for shadow/canary routing instead of inventing a new promotion router.

## Concrete Storage Contract

### PostgreSQL tables

The first implementation will add flywheel-specific metadata tables under the existing workflow
repository layer, while keeping long-running orchestration state in the generic saga tables already
defined by `saga_persistence`.

#### New metadata tables

1. `flywheel_decision_events`
   - Purpose: normalized governed runtime records emitted by gateway and bus integrations
   - Primary key: `decision_id`
   - Required columns:
     - `decision_id UUID PRIMARY KEY`
     - `tenant_id VARCHAR(255) NOT NULL`
     - `workload_key VARCHAR(512) NOT NULL`
     - `constitutional_hash VARCHAR(64) NOT NULL`
     - `from_agent VARCHAR(255)`
     - `validated_by_agent VARCHAR(255)`
     - `decision_kind VARCHAR(100) NOT NULL`
     - `request_context JSONB NOT NULL DEFAULT '{}'::jsonb`
     - `decision_payload JSONB NOT NULL`
     - `latency_ms DOUBLE PRECISION`
     - `outcome VARCHAR(50) NOT NULL`
     - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - Required indexes:
     - `(tenant_id, workload_key, created_at DESC)`
     - `(tenant_id, constitutional_hash)`
     - `(tenant_id, validated_by_agent)`

2. `flywheel_dataset_snapshots`
   - Purpose: immutable replay/training snapshot metadata
   - Primary key: `snapshot_id`
   - Required columns:
     - `snapshot_id UUID PRIMARY KEY`
     - `tenant_id VARCHAR(255) NOT NULL`
     - `workload_key VARCHAR(512) NOT NULL`
     - `constitutional_hash VARCHAR(64) NOT NULL`
     - `record_count INTEGER NOT NULL`
     - `redaction_status VARCHAR(50) NOT NULL`
     - `time_window_start TIMESTAMPTZ NOT NULL`
     - `time_window_end TIMESTAMPTZ NOT NULL`
     - `artifact_manifest_uri TEXT NOT NULL`
     - `created_by VARCHAR(255)`
     - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - Required indexes:
     - `(tenant_id, workload_key, created_at DESC)`
     - `(tenant_id, redaction_status)`

3. `flywheel_candidates`
   - Purpose: candidate governance variants derived from replayable evidence
   - Primary key: `candidate_id`
   - Required columns:
     - `candidate_id UUID PRIMARY KEY`
     - `tenant_id VARCHAR(255) NOT NULL`
     - `workload_key VARCHAR(512) NOT NULL`
     - `constitutional_hash VARCHAR(64) NOT NULL`
     - `candidate_type VARCHAR(100) NOT NULL`
     - `parent_version VARCHAR(255)`
     - `candidate_spec JSONB NOT NULL`
     - `status VARCHAR(50) NOT NULL DEFAULT 'draft'`
     - `created_by VARCHAR(255)`
     - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - Required indexes:
     - `(tenant_id, workload_key, status)`
     - `(tenant_id, candidate_type)`

4. `flywheel_evaluation_runs`
   - Purpose: immutable summary of replay, shadow, and canary evaluations
   - Primary key: `run_id`
   - Required columns:
     - `run_id UUID PRIMARY KEY`
     - `tenant_id VARCHAR(255) NOT NULL`
     - `workload_key VARCHAR(512) NOT NULL`
     - `candidate_id UUID NOT NULL`
     - `constitutional_hash VARCHAR(64) NOT NULL`
     - `evaluation_mode VARCHAR(50) NOT NULL`
     - `status VARCHAR(50) NOT NULL`
     - `summary_metrics JSONB NOT NULL DEFAULT '{}'::jsonb`
     - `regression_report JSONB`
     - `started_at TIMESTAMPTZ`
     - `ended_at TIMESTAMPTZ`
     - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - Required indexes:
     - `(tenant_id, workload_key, created_at DESC)`
     - `(candidate_id, evaluation_mode)`

5. `flywheel_evidence_bundles`
   - Purpose: immutable approval and audit packages for recommendation, promotion, rejection, and rollback
   - Primary key: `evidence_id`
   - Required columns:
     - `evidence_id UUID PRIMARY KEY`
     - `tenant_id VARCHAR(255) NOT NULL`
     - `workload_key VARCHAR(512) NOT NULL`
     - `candidate_id UUID NOT NULL`
     - `constitutional_hash VARCHAR(64) NOT NULL`
     - `dataset_snapshot_id UUID NOT NULL`
     - `approval_state VARCHAR(50) NOT NULL`
     - `validator_records JSONB NOT NULL DEFAULT '[]'::jsonb`
     - `rollback_plan JSONB NOT NULL DEFAULT '{}'::jsonb`
     - `artifact_manifest_uri TEXT NOT NULL`
     - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - Required indexes:
     - `(tenant_id, workload_key, created_at DESC)`
     - `(candidate_id)`
     - `(tenant_id, approval_state)`

#### Long-running orchestration state

No new flywheel-specific saga tables are required in the first cut.

Use the existing saga tables:
- `saga_states`
- `saga_checkpoints`
- `saga_locks`

Constraint:
- Flywheel orchestrations must set `saga_name = 'flywheel_run'` and carry `tenant_id`,
  `constitutional_hash`, and `run_id` in saga metadata.

### Artifact-store contract

Use the existing S3-compatible configuration surface from
`src/core/shared/config/operations.py` (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`AWS_REGION`, `S3_ENDPOINT_URL`) instead of inventing a new storage config stack.

#### Required artifact classes

1. Dataset exports
2. Replay input manifests
3. Evaluation output summaries
4. Regression reports
5. Approval-chain exports
6. Rollback plans

#### URI shape

All flywheel artifacts must use a stable URI layout:

```text
s3://{bucket}/flywheel/{tenant_id}/{workload_key_hash}/{yyyy}/{mm}/{dd}/{artifact_kind}/{artifact_id}.{ext}
```

Where:
- `bucket` is deployment-configured
- `workload_key_hash` is a deterministic hash of the canonical workload key
- `artifact_kind` is one of:
  - `dataset`
  - `manifest`
  - `evaluation`
  - `regression`
  - `approval`
  - `rollback`

#### Artifact manifest schema

Every persisted artifact set must have a manifest JSON document containing:

- `artifact_id`
- `tenant_id`
- `workload_key`
- `constitutional_hash`
- `artifact_kind`
- `content_type`
- `byte_size`
- `sha256`
- `created_at`
- `created_by`
- `related_run_id`
- `related_candidate_id`
- `retention_class`
- `legal_hold`

#### Immutability rule

- Artifact payloads are write-once.
- Manifest metadata may only gain retention or legal-hold annotations after creation.
- A promoted or rejected evidence bundle must never point to mutable artifact contents.

## Approval and Follow-Up

If accepted, this ADR should be followed by:

1. A concrete package/file plan
2. A phased implementation backlog with acceptance criteria
3. Incremental implementation starting with observation and offline replay only
