# Governed Flywheel GitHub Issue Board

> Date: 2026-03-30
> Constitutional Hash: `608508a9bd224290`
> Source docs: `docs/architecture/2026-03-30-governed-flywheel-integration-design.md`, `docs/adrs/0001-governed-flywheel-integration.md`, `docs/superpowers/plans/2026-03-30-governed-flywheel-implementation-backlog.md`

## Usage

This file turns the backlog into GitHub-ready issues. Each issue includes:

- title
- labels
- dependencies
- scope
- definition of done

Create these as separate GitHub issues or import them into your preferred planning system.

## Epic 1: Foundation

### Issue 1

**Title**
`feat(flywheel): add canonical models for decision events, dataset snapshots, candidates, runs, and evidence`

**Labels**
- `area:agent-bus`
- `area:data-flywheel`
- `type:feature`
- `priority:high`

**Depends on**
- none

**Scope**
- Add `packages/enhanced_agent_bus/data_flywheel/models.py`
- Re-export new types from `packages/enhanced_agent_bus/data_flywheel/__init__.py`
- Add tests for required `tenant_id` and `constitutional_hash` invariants

**Definition of done**
- Canonical models exist for `WorkloadKey`, `DecisionEvent`, `FeedbackEvent`,
  `DatasetSnapshot`, `CandidateArtifact`, `EvaluationRun`, and `EvidenceBundle`
- All persisted event-like models require `tenant_id`
- All models require `constitutional_hash`
- Unit tests pass for valid and invalid payloads

### Issue 2

**Title**
`feat(self-evolution): implement the missing operator control plane package used by the gateway`

**Labels**
- `area:gateway`
- `area:self-evolution`
- `type:feature`
- `priority:critical`

**Depends on**
- none

**Scope**
- Add `src/core/self_evolution/`
- Implement `src/core/self_evolution/research/operator_control.py`
- Add tests for pause, resume, stop, and snapshot behavior

**Definition of done**
- Gateway imports resolve without fallback stubs
- Control plane supports pause, resume, stop, and snapshot
- Snapshot includes `paused`, `stop_requested`, `status`, `updated_by`, and `reason`
- Route-level tests and package tests pass

### Issue 3

**Title**
`refactor(flywheel): update flywheel config for ACGS runtime storage and replay contracts`

**Labels**
- `area:agent-bus`
- `area:config`
- `type:refactor`
- `priority:high`

**Depends on**
- Issue 1

**Scope**
- Update `packages/enhanced_agent_bus/data_flywheel/config.py`
- Remove blueprint-biased assumptions from the required path
- Add object-storage and replay settings aligned to the ADR

**Definition of done**
- Config treats Elastic/Mongo as optional adapter integrations
- Config supports S3-compatible artifact configuration
- Replay and retention settings are explicit
- Existing coverage tests are updated and pass

## Epic 2: Observation and persistence

### Issue 4

**Title**
`feat(flywheel): normalize workload identity and ingest governed decision telemetry`

**Labels**
- `area:agent-bus`
- `area:gateway`
- `area:data-flywheel`
- `type:feature`
- `priority:high`

**Depends on**
- Issue 1
- Issue 2

**Scope**
- Add `workload_registry.py` and `ingest.py`
- Update gateway feedback route and message processor emission points
- Require validator metadata for governed actions entering the flywheel path

**Definition of done**
- Stable `workload_key` generation exists
- Flywheel ingestion works for gateway and bus events
- Missing tenant or validator metadata is rejected
- Tests cover malformed workload keys and tenant isolation

### Issue 5

**Title**
`feat(persistence): add durable postgres storage for flywheel metadata and evidence bundles`

**Labels**
- `area:persistence`
- `area:data-flywheel`
- `type:feature`
- `priority:high`

**Depends on**
- Issue 1
- Issue 4

**Scope**
- Extend `packages/enhanced_agent_bus/persistence/`
- Add repository methods and schema support for:
  - `flywheel_decision_events`
  - `flywheel_dataset_snapshots`
  - `flywheel_candidates`
  - `flywheel_evaluation_runs`
  - `flywheel_evidence_bundles`

**Definition of done**
- Repository CRUD exists for the new flywheel metadata records
- Table/index definitions follow the ADR storage contract
- Tests verify create, query, and tenant-scoped retrieval

### Issue 6

**Title**
`feat(saga): add flywheel run-state orchestration on top of existing saga persistence`

**Labels**
- `area:saga`
- `area:data-flywheel`
- `type:feature`
- `priority:high`

**Depends on**
- Issue 2
- Issue 5

**Scope**
- Extend saga persistence models and repository usage for flywheel runs
- Reuse `saga_states`, `saga_checkpoints`, and `saga_locks`
- Standardize `saga_name = 'flywheel_run'`

**Definition of done**
- Flywheel runs can start, checkpoint, pause, resume, and stop
- State and immutable evidence remain separated
- Resume-after-restart semantics are covered by tests

### Issue 7

**Title**
`feat(admin-api): expose flywheel evidence and run inspection routes`

**Labels**
- `area:gateway`
- `area:self-evolution`
- `type:feature`
- `priority:high`

**Depends on**
- Issue 2
- Issue 5
- Issue 6

**Scope**
- Add `src/core/self_evolution/api.py`
- Add `src/core/self_evolution/evidence_store.py`
- Mount admin routes in the gateway

**Definition of done**
- Admin users can list evidence bundles and inspect individual records
- API returns validator records, dataset snapshot IDs, and rollback plans
- Unauthorized access is rejected in tests

## Epic 3: Replay and recommendations

### Issue 8

**Title**
`feat(flywheel): build redacted dataset snapshots for tenant-local replay`

**Labels**
- `area:data-flywheel`
- `area:security`
- `type:feature`
- `priority:high`

**Depends on**
- Issue 4
- Issue 5

**Scope**
- Add `redaction.py` and `dataset_builder.py`
- Add replay-oriented metadata in persistence
- Enforce fail-closed export behavior

**Definition of done**
- Dataset snapshots are grouped by `tenant_id` and `workload_key`
- Redaction is mandatory before export
- Cross-tenant joins are blocked
- Snapshot metadata includes record counts and time windows

### Issue 9

**Title**
`feat(flywheel): generate bounded governance candidates from replayable evidence`

**Labels**
- `area:data-flywheel`
- `area:adaptive-governance`
- `type:feature`
- `priority:medium`

**Depends on**
- Issue 8

**Scope**
- Add `candidate_generator.py`
- Support candidates for thresholds, routing, prompts, evaluator weights, and context strategies

**Definition of done**
- Candidate generation is deterministic for a fixed replay slice
- Candidate records include parent champion version and intended workload scope
- Per-tenant or per-workload disable flags are supported

### Issue 10

**Title**
`feat(flywheel): implement offline replay evaluator and immutable evidence artifacts`

**Labels**
- `area:data-flywheel`
- `area:persistence`
- `type:feature`
- `priority:high`

**Depends on**
- Issue 8
- Issue 9

**Scope**
- Add `evaluator.py`, `metrics.py`, and `artifacts.py`
- Write `flywheel_evaluation_runs` and `flywheel_evidence_bundles`
- Persist S3-compatible artifact manifests

**Definition of done**
- Offline replay scores compliance, latency, intervention rate, and regressions
- Evidence bundles include dataset snapshot, summary metrics, validator records, and rollback plan
- Artifact manifests match the ADR contract and are immutable after creation

### Issue 11

**Title**
`feat(admin-api): add recommendation-only flywheel run creation and candidate listing routes`

**Labels**
- `area:gateway`
- `type:feature`
- `priority:medium`

**Depends on**
- Issue 7
- Issue 10

**Scope**
- Add `routes/flywheel_admin.py`
- Support create/list replay runs and inspect recommendation-only candidates

**Definition of done**
- Admins can create replay runs
- Admins can inspect recommendation summaries and linked evidence IDs
- No promote action is enabled in this issue

## Epic 4: Promotion and canary

### Issue 12

**Title**
`feat(deliberation): require approval chains for flywheel promotions`

**Labels**
- `area:deliberation`
- `area:data-flywheel`
- `type:feature`
- `priority:high`

**Depends on**
- Issue 10

**Scope**
- Integrate flywheel promotions with HITL and multi-approver flows
- Enforce proposer/validator/executor separation

**Definition of done**
- Self-validation is blocked
- High-impact candidates require HITL approval
- Approval-chain evidence is written to the evidence bundle

### Issue 13

**Title**
`feat(ab-testing): add shadow and canary routing for flywheel candidates with automatic rollback`

**Labels**
- `area:adaptive-governance`
- `area:ab-testing`
- `area:data-flywheel`
- `type:feature`
- `priority:high`

**Depends on**
- Issue 10
- Issue 12

**Scope**
- Extend `ab_testing.py` and `governance_engine.py`
- Add candidate-linked routing metadata and rollback triggers

**Definition of done**
- Shadow and canary modes both exist
- Every served decision can be linked to a candidate and evidence bundle
- Automatic rollback triggers on regression thresholds
- Tests cover champion/candidate metrics and rollback activation

### Issue 14

**Title**
`feat(operator-control): add run-aware pause, resume, and stop for active flywheel runs`

**Labels**
- `area:self-evolution`
- `area:gateway`
- `type:feature`
- `priority:medium`

**Depends on**
- Issue 6
- Issue 13

**Scope**
- Expand evolution control routes to operate on specific flywheel runs
- Synchronize control state with saga persistence

**Definition of done**
- Operators can control specific run IDs
- Control changes appear in API status and saga state
- Safe-boundary pause behavior is tested

## Epic 5: Admin UI

### Issue 15

**Title**
`feat(ui): add flywheel admin dashboard for runs, evidence, and operator actions`

**Labels**
- `area:frontend`
- `area:data-flywheel`
- `type:feature`
- `priority:medium`

**Depends on**
- Issue 11
- Issue 14

**Scope**
- Add admin run list view and typed API client
- Support pause, resume, and stop actions from the UI

**Definition of done**
- UI lists runs and recent evidence bundles
- Authorized operators can trigger run controls
- UI tests cover loading, success, and authorization failure

### Issue 16

**Title**
`feat(ui): add candidate comparison and evidence inspection views`

**Labels**
- `area:frontend`
- `area:data-flywheel`
- `type:feature`
- `priority:medium`

**Depends on**
- Issue 15
- Issue 13

**Scope**
- Add run detail page and comparison components
- Display compliance, latency, and rollback metadata

**Definition of done**
- Champion vs candidate comparison is visible
- Evidence view shows validator records, approval chain, and rollback plan
- UI tests cover detail rendering and error states

## Epic 6: Hardening

### Issue 17

**Title**
`feat(flywheel): add immutable artifact manifests and retention metadata for evidence bundles`

**Labels**
- `area:data-flywheel`
- `area:security`
- `type:feature`
- `priority:medium`

**Depends on**
- Issue 10

**Scope**
- Add retention class and legal-hold metadata to artifact manifests
- Enforce write-once artifact semantics

**Definition of done**
- Artifact manifests include `sha256`, `byte_size`, `retention_class`, and `legal_hold`
- Promoted or rejected evidence bundles do not point to mutable content
- Tests verify integrity and missing-artifact handling

### Issue 18

**Title**
`feat(flywheel): add optional external trainer adapters behind strict governance gates`

**Labels**
- `area:data-flywheel`
- `type:feature`
- `priority:low`

**Depends on**
- Issue 10
- Issue 12
- Issue 17

**Scope**
- Add trainer adapter interface for future prompt/model tuning integrations
- Keep adapters disabled by default

**Definition of done**
- External training is opt-in only
- Unredacted data cannot reach trainer adapters
- Promotion paths still require replay, validation, approval, and evidence generation

## Suggested Milestones

### Milestone A: Observation complete
- Issue 1
- Issue 2
- Issue 3
- Issue 4
- Issue 5
- Issue 6
- Issue 7

### Milestone B: Replay complete
- Issue 8
- Issue 9
- Issue 10
- Issue 11

### Milestone C: Promotion complete
- Issue 12
- Issue 13
- Issue 14

### Milestone D: Operator UX complete
- Issue 15
- Issue 16

### Milestone E: Hardening complete
- Issue 17
- Issue 18
