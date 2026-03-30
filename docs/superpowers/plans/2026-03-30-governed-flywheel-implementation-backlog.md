# Governed Flywheel Implementation Backlog

> Date: 2026-03-30
> Constitutional Hash: `608508a9bd224290`
> Depends on: `docs/architecture/2026-03-30-governed-flywheel-integration-design.md`, `docs/adrs/0001-governed-flywheel-integration.md`

## Objective

Deliver a bounded, governance-first flywheel in phases, starting with observation and replay,
then moving to shadow and canary promotion once evidence and operator controls are in place.

## Phase 0: Foundation and control-plane closure

### FW-001: Establish canonical flywheel models

**Files**
- `packages/enhanced_agent_bus/data_flywheel/models.py`
- `packages/enhanced_agent_bus/data_flywheel/__init__.py`
- `packages/enhanced_agent_bus/tests/`

**Acceptance criteria**
- Defines `WorkloadKey`, `DecisionEvent`, `FeedbackEvent`, `DatasetSnapshot`,
  `EvaluationRun`, `CandidateArtifact`, and `EvidenceBundle`.
- All models require `constitutional_hash`.
- All persisted event models require `tenant_id`.
- Tests verify validation failures for missing tenant and constitutional hash fields.

### FW-002: Implement the missing self-evolution control plane

**Files**
- `src/core/self_evolution/__init__.py`
- `src/core/self_evolution/models.py`
- `src/core/self_evolution/research/operator_control.py`
- `src/core/self_evolution/tests/`

**Acceptance criteria**
- Gateway imports for operator control resolve without fallback stubs.
- Pause, resume, and stop state can be stored and retrieved via the control plane.
- Control snapshots include `paused`, `stop_requested`, `status`, `updated_by`, and `reason`.
- Tests cover unavailable backend, healthy backend, and state transitions.

### FW-003: Refactor flywheel config away from blueprint-specific assumptions

**Files**
- `packages/enhanced_agent_bus/data_flywheel/config.py`
- `packages/enhanced_agent_bus/tests/coverage/test_bus_cov_batch17b.py`

**Acceptance criteria**
- Config distinguishes required durable stores from optional external integrations.
- Elastic/Mongo fields are either marked optional or documented as adapter-specific.
- Config adds object-storage and replay options.
- Existing config coverage tests are updated and pass.

## Phase 1: Observation and evidence

### FW-004: Normalize workload identity and runtime ingestion

**Files**
- `packages/enhanced_agent_bus/data_flywheel/workload_registry.py`
- `packages/enhanced_agent_bus/data_flywheel/ingest.py`
- `src/core/services/api_gateway/routes/feedback.py`
- `packages/enhanced_agent_bus/message_processor.py`

**Acceptance criteria**
- Gateway and bus events can be normalized into a stable `workload_key`.
- `workload_key` includes tenant, route/tool, decision kind, and constitutional hash.
- Ingestion rejects records without tenant context or validator metadata for governed actions.
- Tests cover tenant isolation, malformed workload keys, and independent-validator metadata.

### FW-005: Add durable flywheel metadata persistence

**Files**
- `packages/enhanced_agent_bus/persistence/models.py`
- `packages/enhanced_agent_bus/persistence/repository.py`
- `packages/enhanced_agent_bus/persistence/postgres_repository.py`
- `packages/enhanced_agent_bus/tests/`

**Acceptance criteria**
- Dataset snapshots, evaluation summaries, candidate artifacts, and evidence bundles can be
  persisted and retrieved through repository abstractions.
- Repository tests do not bypass the persistence layer directly.
- Evidence bundles can be listed by tenant and workload.

### FW-006: Add flywheel run-state saga persistence

**Files**
- `packages/enhanced_agent_bus/saga_persistence/models.py`
- `packages/enhanced_agent_bus/saga_persistence/repository.py`
- `packages/enhanced_agent_bus/saga_persistence/postgres/repository.py`
- `packages/enhanced_agent_bus/saga_persistence/redis/repository.py`

**Acceptance criteria**
- Long-running flywheel runs can be created, paused, resumed, retried, and completed.
- Saga state stores orchestration progress separately from immutable evidence.
- Tests verify resume-after-interruption semantics.

### FW-007: Expose admin evidence APIs

**Files**
- `src/core/self_evolution/api.py`
- `src/core/self_evolution/evidence_store.py`
- `src/core/services/api_gateway/main.py`
- `src/core/services/api_gateway/tests/`

**Acceptance criteria**
- Admin routes can list evidence bundles and fetch individual evidence records.
- Access is restricted to authenticated admin users.
- Evidence payloads include dataset snapshot references, validator records, and rollback plans.
- Route tests verify authorization failures and successful retrieval.

## Phase 2: Offline replay and recommendation

### FW-008: Build bounded dataset snapshots

**Files**
- `packages/enhanced_agent_bus/data_flywheel/redaction.py`
- `packages/enhanced_agent_bus/data_flywheel/dataset_builder.py`
- `packages/enhanced_agent_bus/persistence/replay.py`

**Acceptance criteria**
- Dataset builder produces tenant-local snapshots grouped by `workload_key`.
- Redaction runs before export or replay.
- Snapshot metadata records record counts, time window, and redaction status.
- Tests verify that cross-tenant joins and unredacted export are rejected.

### FW-009: Generate bounded governance candidates

**Files**
- `packages/enhanced_agent_bus/data_flywheel/candidate_generator.py`
- `packages/enhanced_agent_bus/adaptive_governance/governance_engine.py`

**Acceptance criteria**
- Candidate generation supports thresholds, prompts, routing, evaluator weights, and context
  selection strategies.
- Candidate metadata records parent champion version and intended workload scope.
- Generation can be disabled per tenant or per workload.
- Tests verify deterministic candidate generation from a fixed replay slice.

### FW-010: Implement offline replay evaluator

**Files**
- `packages/enhanced_agent_bus/data_flywheel/evaluator.py`
- `packages/enhanced_agent_bus/data_flywheel/metrics.py`
- `packages/enhanced_agent_bus/tests/`

**Acceptance criteria**
- Evaluator can score candidates on compliance, latency, intervention rate, and regression count.
- Evaluations write `EvaluationRun` summaries and evidence artifacts.
- Failed redaction or validator checks abort the run with fail-closed status.
- Tests cover successful replay, blocked replay, and regression detection.

### FW-011: Surface recommendation-only admin routes

**Files**
- `src/core/services/api_gateway/routes/flywheel_admin.py`
- `src/core/services/api_gateway/main.py`
- `src/core/services/api_gateway/tests/`

**Acceptance criteria**
- Admins can create replay runs, list candidates, and inspect evaluation summaries.
- No production promotion action is enabled in this phase.
- API responses include run status, summary metrics, and evidence IDs.

## Phase 3: Deliberation, shadow, and canary

### FW-012: Add promotion workflow integration

**Files**
- `packages/enhanced_agent_bus/data_flywheel/promotion.py`
- `packages/enhanced_agent_bus/deliberation_layer/hitl_manager.py`
- `packages/enhanced_agent_bus/deliberation_layer/multi_approver.py`

**Acceptance criteria**
- Promotion requests require proposer, validator, and executor separation.
- High-impact candidates require explicit HITL approval.
- Promotion decisions write approval-chain evidence.
- Tests verify that self-validation blocks promotion.

### FW-013: Extend A/B routing for flywheel candidates

**Files**
- `packages/enhanced_agent_bus/ab_testing.py`
- `packages/enhanced_agent_bus/adaptive_governance/governance_engine.py`
- `packages/enhanced_agent_bus/tests/`

**Acceptance criteria**
- Candidate routing supports shadow-only and canary modes.
- Routing metadata links each served decision to the candidate and evidence bundle.
- Automatic rollback triggers on configured regression thresholds.
- Tests verify champion/candidate metrics accounting and rollback activation.

### FW-014: Add run-aware operator controls

**Files**
- `src/core/services/api_gateway/routes/evolution_control.py`
- `src/core/self_evolution/research/operator_control.py`
- `src/core/services/api_gateway/tests/`

**Acceptance criteria**
- Operators can pause, resume, and stop specific flywheel runs.
- Control actions are reflected in saga state and surfaced in API status.
- Pause respects safe boundaries and does not corrupt active run state.

## Phase 4: Frontend visibility and operator UX

### FW-015: Add flywheel admin dashboard

**Files**
- `packages/propriety-ai/src/routes/admin/flywheel/+page.svelte`
- `packages/propriety-ai/src/lib/api/flywheel.ts`
- `packages/propriety-ai/tests/flywheel/`

**Acceptance criteria**
- Admin UI lists runs, statuses, and recent evidence bundles.
- UI can trigger pause, resume, and stop actions for authorized users.
- UI displays replay metrics and candidate comparison summaries.

### FW-016: Add candidate comparison and evidence views

**Files**
- `packages/propriety-ai/src/routes/admin/flywheel/[runId]/+page.svelte`
- `packages/propriety-ai/src/lib/components/flywheel/CandidateComparison.svelte`
- `packages/propriety-ai/src/lib/components/flywheel/RunTable.svelte`

**Acceptance criteria**
- UI shows champion vs candidate comparisons with compliance and latency deltas.
- Evidence view includes validator identities, approval chain, and rollback plan.
- UI tests cover loading, error, and unauthorized states.

## Phase 5: Hardening and optional advanced experimentation

### FW-017: Add object-storage artifact manifests

**Files**
- `packages/enhanced_agent_bus/data_flywheel/artifacts.py`
- `packages/enhanced_agent_bus/persistence/models.py`

**Acceptance criteria**
- Evidence bundles reference object-storage URIs for datasets and evaluation artifacts.
- Artifact manifests are immutable once promoted or rejected.
- Tests verify manifest integrity and missing-artifact handling.

### FW-018: Add optional external trainer adapters behind strict gates

**Files**
- `packages/enhanced_agent_bus/data_flywheel/trainer_adapters.py`
- `packages/enhanced_agent_bus/data_flywheel/config.py`
- `packages/enhanced_agent_bus/tests/`

**Acceptance criteria**
- Trainer adapters are disabled by default.
- External training requires explicit config enablement and admin approval.
- Unredacted data cannot enter training adapters.
- No promotion path bypasses replay, validation, and evidence generation.

## Global Exit Criteria

- Observation path exists for governed decision and feedback traffic.
- Offline replay can generate evidence-backed candidate recommendations.
- Shadow and canary routing are controlled through existing governance primitives.
- Promotion and rollback are impossible without independent validation and constitutional-hash
  match.
- Admin users can inspect evidence bundles and control runs from both API and UI surfaces.

## Suggested Validation Commands

```bash
make test-bus
make test-gw
python -m pytest packages/enhanced_agent_bus/tests/ -m "not slow" --import-mode=importlib
python -m pytest src/core/services/api_gateway/tests/ --import-mode=importlib
```
