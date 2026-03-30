# Governed Flywheel Integration Design

> Date: 2026-03-30
> Constitutional Hash: `608508a9bd224290`
> Scope: `packages/enhanced_agent_bus/`, `src/core/services/api_gateway/`, `src/core/self_evolution/`, `packages/propriety-ai/`

## Intent

Integrate a bounded, governance-first data flywheel into ACGS by extending the existing
`enhanced_agent_bus.data_flywheel` namespace, reusing the current feedback, adaptive governance,
A/B routing, persistence, and deliberation primitives, and adding the missing self-evolution
control plane under `src/core/self_evolution/`.

This is not a direct transplant of the NVIDIA blueprint runtime. ACGS already contains the core
governance and promotion controls, so the flywheel should become a governed subsystem inside the
bus rather than a separate MLOps service that can mutate behavior outside constitutional review.

## Current Repo Signals

### Existing foundations

- `packages/enhanced_agent_bus/data_flywheel/config.py` already defines `FlywheelConfig`,
  experiment modes, evaluation config, candidate models, and constitutional-hash binding.
- `packages/enhanced_agent_bus/adaptive_governance/governance_engine.py` already integrates
  feedback loops and A/B testing.
- `packages/enhanced_agent_bus/ab_testing.py` already provides champion/candidate routing and
  promotion comparison primitives.
- `packages/enhanced_agent_bus/feedback_handler/` already provides decision-linked feedback event
  storage.
- `src/core/services/api_gateway/routes/feedback.py` already ingests public/operator feedback.
- `src/core/services/api_gateway/routes/evolution_control.py` already exposes operator pause,
  resume, and stop endpoints for self-evolution.
- `packages/enhanced_agent_bus/tests/test_message_processor_independent_validator_gate.py`
  confirms the independent-validator rule is already a platform invariant.

### Current gaps

- `src/core/self_evolution/` is referenced by the gateway but is not checked in.
- `packages/enhanced_agent_bus/data_flywheel/` is only a config stub today.
- There is no canonical flywheel dataset model, evaluator, evidence bundle, or promotion workflow.
- There is no admin UI for bounded experiment review.

## Design Principles

1. Governed by default: every experiment, evaluation, and promotion is bound to the
   constitutional hash and independent validation.
2. Tenant-safe by default: no dataset assembly, replay, or candidate evaluation may cross tenant
   boundaries.
3. Extend existing namespaces: use `data_flywheel/`, `deliberation_layer/`, `persistence/`, and
   `saga_persistence/` instead of adding a parallel subsystem.
4. Separate run state from evidence state: saga state belongs in `saga_persistence/`; durable
   evidence and experiment records belong in `persistence/`.
5. Start with governance candidates first: thresholds, routing, prompts, context policies, and
   rule variants before model fine-tuning.

## Package and File Plan

### 1. Extend `packages/enhanced_agent_bus/data_flywheel/`

| Path | Action | Responsibility |
| ---- | ------ | -------------- |
| `packages/enhanced_agent_bus/data_flywheel/__init__.py` | Modify | Re-export canonical flywheel services and models. |
| `packages/enhanced_agent_bus/data_flywheel/config.py` | Modify | Keep config models, deprecate direct Elastic/Mongo assumptions, add object-storage and replay settings. |
| `packages/enhanced_agent_bus/data_flywheel/models.py` | Create | Pydantic models for workload keys, decision events, datasets, candidates, evaluation runs, and evidence bundles. |
| `packages/enhanced_agent_bus/data_flywheel/workload_registry.py` | Create | Normalize `tenant_id` + service + route/tool + decision kind into stable `workload_key` values. |
| `packages/enhanced_agent_bus/data_flywheel/ingest.py` | Create | Convert gateway/bus events into canonical flywheel decision and feedback records. |
| `packages/enhanced_agent_bus/data_flywheel/redaction.py` | Create | PII stripping and export safety checks before replay/training. |
| `packages/enhanced_agent_bus/data_flywheel/dataset_builder.py` | Create | Build bounded tenant-local dataset snapshots from governed runtime records. |
| `packages/enhanced_agent_bus/data_flywheel/candidate_generator.py` | Create | Produce threshold, prompt, routing, evaluator, and policy candidates. |
| `packages/enhanced_agent_bus/data_flywheel/evaluator.py` | Create | Offline replay and shadow evaluation against held-out records. |
| `packages/enhanced_agent_bus/data_flywheel/promotion.py` | Create | Promotion readiness, rollback triggers, and canary gating. |
| `packages/enhanced_agent_bus/data_flywheel/artifacts.py` | Create | Persist evidence manifests and artifact pointers. |
| `packages/enhanced_agent_bus/data_flywheel/metrics.py` | Create | Flywheel-specific metrics: replay pass rate, regression counts, promotion blocks, rollback triggers. |
| `packages/enhanced_agent_bus/data_flywheel/tests/` | Create | Unit and integration tests for the namespace. |

### 2. Add self-evolution control plane under `src/core/self_evolution/`

| Path | Action | Responsibility |
| ---- | ------ | -------------- |
| `src/core/self_evolution/__init__.py` | Create | Package marker and exports. |
| `src/core/self_evolution/models.py` | Create | Shared control-plane and admin API schemas. |
| `src/core/self_evolution/api.py` | Create | Evidence routers expected by the gateway and admin endpoints for experiment records. |
| `src/core/self_evolution/evidence_store.py` | Create | Read-only evidence access and evidence bundle lookup. |
| `src/core/self_evolution/research/__init__.py` | Create | Research namespace marker. |
| `src/core/self_evolution/research/operator_control.py` | Create | Shared pause/resume/stop control plane consumed by the gateway lifespan and routes. |
| `src/core/self_evolution/services.py` | Create | Wiring helpers to instantiate flywheel orchestrators and evidence stores. |
| `src/core/self_evolution/tests/` | Create | API and control-plane tests. |

### 3. Extend `packages/enhanced_agent_bus/persistence/`

| Path | Action | Responsibility |
| ---- | ------ | -------------- |
| `packages/enhanced_agent_bus/persistence/models.py` | Modify | Add durable models for dataset snapshots, evaluation summaries, candidate artifacts, and evidence bundles. |
| `packages/enhanced_agent_bus/persistence/repository.py` | Modify | Abstract repository methods for flywheel metadata persistence. |
| `packages/enhanced_agent_bus/persistence/postgres_repository.py` | Modify | Postgres implementation for flywheel metadata and evidence records. |
| `packages/enhanced_agent_bus/persistence/replay.py` | Modify | Replay helpers for evaluation datasets and benchmark slices. |

### 4. Extend `packages/enhanced_agent_bus/saga_persistence/`

| Path | Action | Responsibility |
| ---- | ------ | -------------- |
| `packages/enhanced_agent_bus/saga_persistence/models.py` | Modify | Represent long-running flywheel runs, retries, pause states, and terminal outcomes. |
| `packages/enhanced_agent_bus/saga_persistence/repository.py` | Modify | Shared access pattern for experiment/run progress. |
| `packages/enhanced_agent_bus/saga_persistence/postgres/repository.py` | Modify | Durable long-run storage for flywheel workflows. |
| `packages/enhanced_agent_bus/saga_persistence/redis/repository.py` | Modify | Fast resumable control state for active runs. |

### 5. Extend governance and routing control surfaces

| Path | Action | Responsibility |
| ---- | ------ | -------------- |
| `packages/enhanced_agent_bus/adaptive_governance/governance_engine.py` | Modify | Feed governed decision outcomes into flywheel ingestion and shadow/candidate evaluation. |
| `packages/enhanced_agent_bus/ab_testing.py` | Modify | Support named flywheel candidates, evidence-linked promotions, and rollback metadata. |
| `packages/enhanced_agent_bus/deliberation_layer/hitl_manager.py` | Modify | Require explicit human approval for high-impact candidate promotions. |
| `packages/enhanced_agent_bus/deliberation_layer/multi_approver.py` | Modify | Multi-approver promotion chain for production candidates. |
| `packages/enhanced_agent_bus/message_processor.py` | Modify | Emit normalized decision telemetry and preserve independent-validator evidence on promoted changes. |

### 6. Extend gateway/admin APIs

| Path | Action | Responsibility |
| ---- | ------ | -------------- |
| `src/core/services/api_gateway/main.py` | Modify | Mount flywheel evidence and admin routes. |
| `src/core/services/api_gateway/lifespan.py` | Modify | Initialize flywheel control-plane components. |
| `src/core/services/api_gateway/routes/feedback.py` | Modify | Attach normalized workload metadata required for flywheel ingestion. |
| `src/core/services/api_gateway/routes/evolution_control.py` | Modify | Expand from generic operator control to run-aware flywheel controls. |
| `src/core/services/api_gateway/routes/flywheel_admin.py` | Create | Create/list runs, inspect candidates, promote, rollback, and view evidence bundles. |
| `src/core/services/api_gateway/routes/pipeline_metrics.py` | Modify | Replace demo-only metrics with flywheel-aware pipeline metrics over time. |

### 7. Add frontend admin surfaces in `packages/propriety-ai/`

| Path | Action | Responsibility |
| ---- | ------ | -------------- |
| `packages/propriety-ai/src/routes/admin/flywheel/+page.svelte` | Create | Runs overview and status dashboard. |
| `packages/propriety-ai/src/routes/admin/flywheel/[runId]/+page.svelte` | Create | Candidate comparisons, replay metrics, and evidence bundle links. |
| `packages/propriety-ai/src/lib/components/flywheel/RunTable.svelte` | Create | Run list with pause/resume/stop actions. |
| `packages/propriety-ai/src/lib/components/flywheel/CandidateComparison.svelte` | Create | Champion vs candidate metrics, constitutional diffs, and rollback state. |
| `packages/propriety-ai/src/lib/api/flywheel.ts` | Create | Typed client for admin flywheel routes. |
| `packages/propriety-ai/tests/flywheel/` | Create | UI tests for admin flows. |

## Canonical Runtime Flow

1. Gateway and bus emit governed `DecisionEvent` and `FeedbackEvent` records.
2. `data_flywheel.ingest` normalizes them into workload-scoped flywheel records.
3. `dataset_builder` assembles tenant-local snapshots after redaction and retention checks.
4. `candidate_generator` creates bounded governance candidates.
5. `evaluator` runs offline replay and, later, shadow evaluation.
6. `promotion` submits high-confidence candidates into a deliberation workflow.
7. `hitl_manager` and validator gates enforce proposer/validator/executor separation.
8. Approved candidates are canaried through `ab_testing.py`.
9. `artifacts.py` writes an immutable evidence bundle for every recommendation, promotion,
   rollback, or rejection.

## Canonical Data Models

### WorkloadKey

Stable grouping key for replay and candidate comparison:

```text
{tenant_id}/{service}/{route_or_tool}/{decision_kind}/{constitutional_hash}
```

### DecisionEvent

Required fields:

- `decision_id`
- `tenant_id`
- `workload_key`
- `constitutional_hash`
- `from_agent`
- `validated_by_agent`
- `request_context`
- `decision_payload`
- `latency_ms`
- `outcome`
- `created_at`

### FeedbackEvent

Required fields:

- `feedback_id`
- `decision_id`
- `tenant_id`
- `workload_key`
- `feedback_type`
- `outcome_status`
- `comment`
- `actual_impact`
- `created_at`

### EvaluationRun

Required fields:

- `run_id`
- `tenant_id`
- `workload_key`
- `candidate_id`
- `evaluation_mode` (`offline_replay`, `shadow`, `canary`)
- `status`
- `constitutional_hash`
- `started_at`
- `ended_at`
- `summary_metrics`

### EvidenceBundle

Required fields:

- `evidence_id`
- `candidate_id`
- `tenant_id`
- `workload_key`
- `constitutional_hash`
- `dataset_snapshot_id`
- `evaluation_run_ids`
- `validator_records`
- `approval_chain`
- `rollback_plan`
- `artifact_uris`

## Boundaries and Invariants

### `persistence/` vs `saga_persistence/`

- `persistence/` stores durable metadata and immutable evidence.
- `saga_persistence/` stores active run state, orchestration progress, retries, locks, and pause
  control.

Do not cross-import these packages directly. Keep orchestration code behind the repository/factory
surfaces already documented in their local `AGENTS.md` files.

### Promotion rules

- A proposer must not validate or promote its own candidate.
- A candidate cannot be promoted without constitutional-hash match.
- High-impact candidates require explicit HITL approval.
- Flywheel evaluation must fail closed if redaction, validation, or evidence generation fails.
- Cross-tenant replay and dataset joins are forbidden.

## Sequence of Implementation

### Phase A: Observation and evidence

- Implement canonical flywheel models and workload registry.
- Ingest decision and feedback telemetry into durable stores.
- Add admin read APIs and evidence bundle shells.

### Phase B: Offline replay

- Add dataset builder, redaction, and replay evaluator.
- Generate bounded governance candidates.
- Produce evidence-backed recommendations without live routing.

### Phase C: Shadow and canary

- Connect evaluator output to `ab_testing.py`.
- Add promotion workflow and rollback triggers.
- Expose run control and candidate comparison in the UI.

### Phase D: Advanced experimentation

- Add external trainer adapters for optional prompt/model tuning.
- Keep model-tuning paths off by default and behind stricter approval.

## Explicit Non-Goals For The First Cut

- No new MongoDB dependency as a system of record.
- No Elasticsearch requirement for flywheel storage.
- No automatic production promotion based only on offline scores.
- No model fine-tuning in the initial implementation slice.

## Validation Strategy

- Unit tests under `packages/enhanced_agent_bus/data_flywheel/tests/`
- Repository tests for new persistence and saga state models
- Gateway route tests for admin control and evidence access
- Shadow/canary behavior tests around `ab_testing.py`
- Deliberation tests proving proposer/validator separation for promotion workflows

