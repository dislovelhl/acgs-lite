# Build Brief for Pi / Codex

## Goal

Implement the next concrete ACGS constitutional-governance loop in `packages/acgs-lite` across three workstreams:

1. real `workflow_action` runtime dispatch artifacts,
2. amendment diffs and constitutional lineage,
3. constitution-eval as an offline pre-deployment gate.

This is not a greenfield design task. The codebase already contains partial support for all three areas. The job is to finish and connect the loop cleanly.

---

## Important constraints

- Work only in `/home/martin/Documents/acgs-clean`
- Focus on the smallest surface that completes the feature cleanly
- Preserve existing public APIs unless there is a strong reason to extend them
- Add tests with each logical change
- Do not modify unrelated files
- Do not change `CLAUDE.md` or `AGENTS.md`
- Commit after each logical milestone
- Do not force-push or rewrite history

---

## Relevant existing code to inspect first

### Workflow actions
- `packages/acgs-lite/src/acgs_lite/constitution/rule.py`
- `packages/acgs-lite/src/acgs_lite/engine/core.py`
- `packages/acgs-lite/src/acgs_lite/engine/models.py`
- `packages/acgs-lite/tests/test_workflow_action.py`

### Amendments / merging
- `packages/acgs-lite/src/acgs_lite/constitution/merging.py`
- `packages/acgs-lite/src/acgs_lite/constitution/constitution.py`
- `packages/acgs-lite/tests/test_governance_quality.py`
- `packages/acgs-lite/tests/test_coverage_batch3a.py`

### Evaluation surface
- existing tests and fixtures under `packages/acgs-lite/tests/`
- any CLI command modules under `packages/acgs-lite/src/acgs_lite/commands/`

---

## Workstream 1: Real `workflow_action` dispatch

### Problem
`ViolationAction` exists and engine dispatch partially exists, but several actions still collapse into generic block semantics.

### Deliverable
Each action should create a distinct runtime outcome:
- `warn`
- `block`
- `block_and_notify`
- `require_human_review`
- `escalate_to_senior`
- `halt_and_alert`

### Tasks

#### 1. Add explicit enforcement outcome types
Create a new module:
- `packages/acgs-lite/src/acgs_lite/engine/enforcement.py`

Add focused dataclasses or typed models for things like:
- `EnforcementOutcome`
- `NotificationEvent`
- `ReviewRequest`
- `EscalationRequest`
- `IncidentAlert`

Keep them small and serialization-friendly.

#### 2. Refactor engine action resolution
In `engine/core.py`:
- centralize action mapping instead of scattering behavior
- resolve each matched violation into an explicit enforcement outcome
- keep existing strict/non-strict semantics intact

#### 3. Extend validation result surface
In `engine/models.py`, add fields for distinct artifacts, for example:
- notifications
- review_requests
- escalations
- incident_alerts

Do not bloat the object unnecessarily. Keep defaults empty and backward-compatible.

#### 4. Record path-specific audit metadata
Make sure audit output distinguishes:
- workflow action chosen
- whether notification fired
- whether human review was queued
- whether escalation happened
- whether halt/incident path triggered

#### 5. Add tests
Add or extend tests to verify:
- `block_and_notify` creates a notification artifact
- `require_human_review` creates a review artifact and blocks/defer-fails correctly
- `escalate_to_senior` creates escalation artifact and blocks/defer-fails correctly
- `halt_and_alert` creates incident artifact and raises correctly
- mixed warn + block cases remain correct

### Suggested commit
`feat(acgs-lite): add real workflow_action enforcement artifacts`

---

## Workstream 2: Amendment diffs and constitutional lineage

### Problem
Amendments can be applied, but there is no first-class human review surface for what changed.

### Deliverable
A reviewer should be able to compare constitutions and see:
- added rules
- removed rules
- modified rules
- field-level changes
- pre/post constitutional hashes
- amendment summary

### Tasks

#### 1. Add diffing module
Create:
- `packages/acgs-lite/src/acgs_lite/constitution/diffing.py`

Implement:
- `RuleDiff`
- `ConstitutionDiff`
- compare helpers for rule-level and constitution-level changes

Field-level diffs should include at least:
- text
- severity
- workflow_action
- keywords
- patterns
- condition
- deprecated
- valid_from
- valid_until

#### 2. Add compare API to Constitution
In `constitution.py`, add methods like:
- `compare(self, other)`
- `diff_summary(self, other)`

Keep the return values structured, stable, and easy for CLI/report consumers.

#### 3. Add amendment-report helper
In `merging.py`, add a helper such as:
- `apply_amendments_with_report()`

It should return both the updated constitution and a review artifact containing:
- pre-hash
- post-hash
- diff summary
- amendment metadata

#### 4. Add tests
Add a new test file for constitution diffs.
Cover:
- add rule
- remove rule
- modify rule text
- modify severity
- modify workflow_action
- pre/post hash visibility

### Suggested commit
`feat(acgs-lite): add constitution diff and amendment review reporting`

---

## Workstream 3: Constitution-eval offline gate

### Problem
There is no obvious first-class offline harness for validating a constitution or amendment bundle against a scenario corpus before deployment.

### Deliverable
A baseline-vs-candidate constitution evaluation workflow with structured reports.

### Tasks

#### 1. Add eval schema
Create:
- `packages/acgs-lite/src/acgs_lite/evals/schema.py`

Scenario schema should include:
- id
- input_action
- context
- expected_valid
- expected_action_taken
- expected_rule_ids
- optional expected warning/review/escalation/incident indicators
- tags

#### 2. Add eval runner
Create:
- `packages/acgs-lite/src/acgs_lite/evals/runner.py`

Runner should:
- load constitution
- load scenario suite
- run scenarios through `GovernanceEngine`
- compare actual vs expected
- emit structured results

#### 3. Add reporting / regression compare
Create:
- `packages/acgs-lite/src/acgs_lite/evals/report.py`

Support:
- baseline vs candidate comparison
- scenario regressions
- changed matched-rule sets
- changed action distributions

#### 4. Add minimal CLI surface
If CLI structure already exists, add commands that fit the current style, roughly:
- `acgs eval run constitution.yaml scenarios.yaml`
- `acgs eval compare baseline.yaml candidate.yaml scenarios.yaml`

Do not overbuild the CLI. Keep it minimal and usable.

#### 5. Seed small high-signal fixtures
Add small initial suites, likely under a new eval fixtures directory, covering:
- workflow actions
- tool governance
- privacy/PII
- EU AI Act / human oversight style cases

#### 6. Add tests
Add tests for:
- schema validation
- expected outcome matching
- baseline/candidate regression detection
- report structure sanity

### Suggested commit
`feat(acgs-lite): add constitution eval runner and regression reports`

---

## Delivery order

### Milestone 1
Real `workflow_action` artifact support + tests

### Milestone 2
Constitution diff / amendment report support + tests

### Milestone 3
Constitution-eval schema, runner, compare reports + tests

### Milestone 4
CLI polish and docs/examples if needed

---

## Definition of done

### Workflow actions
- no non-trivial action silently collapses to generic block behavior
- runtime result exposes distinct artifact paths
- audit data reflects the exact enforcement path

### Amendment diffs
- constitutions can be compared programmatically
- amendment application can emit a reviewable diff artifact
- workflow_action changes are clearly visible

### Constitution-eval
- candidate constitutions can be regression-tested offline
- baseline vs candidate reports identify changed outcomes
- scenario fixtures exist for at least the highest-signal governance cases

---

## Final instruction

Be pragmatic. Prefer the smallest clean implementation that completes the operating loop, rather than a broad framework. The high-value outcome is that constitutions become:
- distinctly enforced,
- legibly changed,
- and testable before activation.
