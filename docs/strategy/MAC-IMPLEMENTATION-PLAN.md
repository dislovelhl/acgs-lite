# MAC-Driven Constitution Roadmap: Concrete Implementation Plan

*April 2026*

## Goal

Turn the MAC roadmap into an executable implementation plan centered on three product surfaces:

1. **`workflow_action` as real runtime dispatch**
2. **amendment diffs and constitutional lineage**
3. **constitution-eval as a pre-deployment quality gate**

This plan assumes the current state of `acgs-lite` already includes:
- `ViolationAction` enum in `constitution/rule.py`
- engine-side dispatch split between blocking, warning, and halt behaviors in `engine/core.py`
- amendment application helpers in `constitution/merging.py`
- test coverage for enum/dispatch behavior in `tests/test_workflow_action.py`

That means the right move is not greenfield design. It is to finish the missing product loop.

---

## Current state snapshot

### What already exists

#### `workflow_action`
- `Rule.workflow_action` is typed as `ViolationAction`
- supported values already include:
  - `warn`
  - `block`
  - `block_and_notify`
  - `require_human_review`
  - `escalate_to_senior`
  - `halt_and_alert`
- `GovernanceEngine` already groups violations into:
  - halt
  - blocking
  - warning
- strict mode already raises on blocking variants
- non-strict mode already records block outcomes without raising

#### Amendments
- `apply_amendments()` already supports:
  - `modify_rule`
  - `modify_severity`
  - `modify_workflow`
  - `add_rule`
  - `remove_rule`
- constitution changelog support already exists in the object model

#### Tests
- `tests/test_workflow_action.py` already covers enum values and dispatch behavior
- governance-quality tests already exercise workflow changes in changelog/history paths

### What is still missing

#### `workflow_action`
Today, several actions collapse to generic blocking behavior.

Specifically:
- `block_and_notify`
- `require_human_review`
- `escalate_to_senior`

all behave like "block" from the engine’s point of view, with limited differentiation beyond the rule value.

#### Amendments
There is amendment application, but not yet a first-class **diff / compare / review** surface for humans.

#### Constitution-eval
There is no obvious first-class offline evaluation harness that scores a constitution or amendment set against a named scenario corpus before deployment.

---

## Workstream 1: Finish `workflow_action` as real runtime dispatch

## Objective

Move `workflow_action` from "typed hint with partial engine semantics" to "operationally distinct enforcement path with structured outputs."

## Desired end state

When a rule fires, the system should produce a distinct, inspectable runtime outcome:

- `warn` → allow, record warning
- `block` → deny, record violation
- `block_and_notify` → deny + emit notification event
- `require_human_review` → deny/defer + create review artifact
- `escalate_to_senior` → deny/defer + create escalation artifact
- `halt_and_alert` → halt agent + create critical incident artifact

## Proposed implementation

### Phase 1A: introduce explicit enforcement outcome model

**Add file**
- `packages/acgs-lite/src/acgs_lite/engine/enforcement.py`

**Add types**
- `EnforcementOutcome`
- `NotificationEvent`
- `ReviewRequest`
- `EscalationRequest`
- `IncidentAlert`

Suggested shape:

```python
@dataclass(slots=True)
class EnforcementOutcome:
    action: ViolationAction
    blocking: bool
    should_notify: bool = False
    should_queue_review: bool = False
    should_escalate: bool = False
    should_halt: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
```

**Why**
Right now the engine mostly returns `ValidationResult` plus exceptions. That is enough for enforcement, but not enough for downstream workflow systems.

### Phase 1B: normalize action mapping in one place

**Update**
- `packages/acgs-lite/src/acgs_lite/engine/core.py`

**Change**
Replace implicit grouping logic with a helper that resolves each fired violation into an `EnforcementOutcome`.

Example:
- `_resolve_enforcement_outcome(violation) -> EnforcementOutcome`
- `_dispatch_enforcement_outcomes(outcomes)`

This keeps the engine readable and makes later integrations easier.

### Phase 1C: expose distinct artifacts in `ValidationResult`

**Update**
- `packages/acgs-lite/src/acgs_lite/engine/models.py`

**Add fields**
- `notifications: list[dict[str, Any]] = []`
- `review_requests: list[dict[str, Any]] = []`
- `escalations: list[dict[str, Any]] = []`
- `incident_alerts: list[dict[str, Any]] = []`

**Why**
Today `action_taken` exists, which is useful, but it is too shallow to drive real workflows.

### Phase 1D: audit-log differentiation

**Update**
- `packages/acgs-lite/src/acgs_lite/engine/core.py`
- `packages/acgs-lite/src/acgs_lite/audit.py`

**Add metadata recording**
For each enforcement path, record:
- `workflow_action`
- `enforcement_path`
- `notification_emitted`
- `review_request_id`
- `escalation_target`
- `incident_level`

### Phase 1E: tests

**Add / extend tests**
- `tests/test_workflow_action.py`
- new file: `tests/test_enforcement_outcomes.py`

**Test cases**
- `block_and_notify` produces notification artifact
- `require_human_review` produces review artifact and blocks
- `escalate_to_senior` produces escalation artifact and blocks
- `halt_and_alert` produces incident artifact and raises
- mixed warnings + escalation preserve both advisory and blocking records

## Deliverable definition of done

- each `ViolationAction` maps to a distinct runtime artifact path
- audit log captures the exact enforcement path taken
- downstream consumers can inspect the difference between block/review/escalate/notify
- tests cover all action paths

---

## Workstream 2: Build amendment diffs and constitutional lineage

## Objective

Make constitutions reviewable as governed artifacts, not just mutable blobs.

## Desired end state

A reviewer should be able to answer:
- what changed,
- why it changed,
- which rules were added/removed/modified,
- whether severity or workflow semantics changed,
- and what constitutional hash / amendment chain resulted.

## Proposed implementation

### Phase 2A: add first-class diff model

**Add file**
- `packages/acgs-lite/src/acgs_lite/constitution/diffing.py`

**Add types**
- `RuleDiff`
- `ConstitutionDiff`

Suggested outputs:
- `added_rules`
- `removed_rules`
- `modified_rules`
- field-level changes for:
  - `text`
  - `severity`
  - `workflow_action`
  - `keywords`
  - `patterns`
  - `condition`
  - `deprecated`
  - `valid_from/valid_until`

### Phase 2B: implement compare API on Constitution

**Update**
- `packages/acgs-lite/src/acgs_lite/constitution/constitution.py`

**Add methods**
- `compare(self, other) -> ConstitutionDiff`
- `diff_summary(self, other) -> dict[str, Any]`

**Why**
The API should make review easy enough that product surfaces, CLIs, dashboards, and reports can all consume the same canonical diff.

### Phase 2C: connect amendment application to diff artifacts

**Update**
- `packages/acgs-lite/src/acgs_lite/constitution/merging.py`

After `apply_amendments()`, generate and optionally attach:
- pre-hash
- post-hash
- diff summary
- amendment bundle metadata

Suggested optional return path:
- new helper `apply_amendments_with_report()`

### Phase 2D: CLI / report surfacing

**Update or add**
- CLI command path under `src/acgs_lite/commands/`

Suggested commands:
- `acgs diff before.yaml after.yaml`
- `acgs amendments review amendments.yaml constitution.yaml`
- `acgs constitution show-hash constitution.yaml`

### Phase 2E: tests

**Add tests**
- new file: `tests/test_constitution_diff.py`

**Test cases**
- add rule diff
- remove rule diff
- modify text
- modify severity
- modify workflow_action
- keyword/pattern diff normalization
- pre/post hash reporting

## Deliverable definition of done

- constitutions can be compared directly in code
- amendment bundles produce reviewable diff output
- workflow-action changes are visible as first-class diffs
- hash lineage is visible before deployment

---

## Workstream 3: Build constitution-eval as a pre-deployment gate

## Objective

Give ACGS a repeatable offline harness for evaluating constitutions and amendments against a scenario corpus before activation.

## Desired end state

Before a constitution or amendment ships, the team can run something like:

```bash
acgs eval constitution.yaml scenarios.yaml
```

and get:
- pass/fail summary
- regressions vs baseline
- per-rule precision-ish signals
- warning/block/review/escalation distributions
- suggested areas needing review

## Proposed implementation

### Phase 3A: define scenario schema

**Add file**
- `packages/acgs-lite/src/acgs_lite/evals/schema.py`

Scenario fields should include:
- `id`
- `input_action`
- `context`
- `expected_valid`
- `expected_action_taken`
- `expected_rule_ids`
- optional `expected_warnings`
- optional `expected_review/escalation/incident flags`
- tags like `eu_ai_act`, `tool_calling`, `pii`, `human_oversight`

### Phase 3B: build eval runner

**Add file**
- `packages/acgs-lite/src/acgs_lite/evals/runner.py`

Runner responsibilities:
- load constitution
- load scenario suite
- execute each scenario through `GovernanceEngine`
- capture actual vs expected
- compute aggregate metrics

### Phase 3C: baseline and regression support

**Add file**
- `packages/acgs-lite/src/acgs_lite/evals/report.py`

Support:
- compare candidate constitution to baseline constitution
- regression report by scenario ID
- changed action distributions
- changed matched rule IDs

### Phase 3D: CLI surface

**Add commands**
- `acgs eval run constitution.yaml scenarios.yaml`
- `acgs eval compare baseline.yaml candidate.yaml scenarios.yaml`
- `acgs eval report results.json`

### Phase 3E: seed corpora

**Add directory**
- `packages/acgs-lite/evals/fixtures/`

Initial suites:
- `workflow_action.yaml`
- `tool_governance.yaml`
- `eu_ai_act.yaml`
- `pii_and_privacy.yaml`
- `human_oversight.yaml`

These should be intentionally small first, but high-signal.

### Phase 3F: tests

**Add tests**
- `tests/test_constitution_eval.py`

**Test cases**
- schema validation
- expected block/warn/halt outcomes
- baseline vs candidate regression detection
- report rendering sanity

## Deliverable definition of done

- a constitution can be evaluated offline against a named suite
- candidate constitutions can be compared to a baseline
- release decisions can depend on eval output
- workflow-action changes are visible in regression reports

---

## Recommended delivery sequence

## Sprint 1
1. enforcement outcome model
2. distinct runtime artifact support for `workflow_action`
3. tests for action-path differentiation

## Sprint 2
1. constitution diff model
2. compare API
3. amendment review report generation

## Sprint 3
1. eval schema and runner
2. baseline/candidate compare
3. first seeded scenario suites

## Sprint 4
1. CLI polish
2. audit/report integration
3. docs and examples

---

## Concrete file targets

### Likely touched existing files
- `packages/acgs-lite/src/acgs_lite/engine/core.py`
- `packages/acgs-lite/src/acgs_lite/engine/models.py`
- `packages/acgs-lite/src/acgs_lite/constitution/constitution.py`
- `packages/acgs-lite/src/acgs_lite/constitution/merging.py`
- `packages/acgs-lite/src/acgs_lite/server.py`
- `packages/acgs-lite/src/acgs_lite/commands/`

### Likely new files
- `packages/acgs-lite/src/acgs_lite/engine/enforcement.py`
- `packages/acgs-lite/src/acgs_lite/constitution/diffing.py`
- `packages/acgs-lite/src/acgs_lite/evals/schema.py`
- `packages/acgs-lite/src/acgs_lite/evals/runner.py`
- `packages/acgs-lite/src/acgs_lite/evals/report.py`
- `packages/acgs-lite/tests/test_enforcement_outcomes.py`
- `packages/acgs-lite/tests/test_constitution_diff.py`
- `packages/acgs-lite/tests/test_constitution_eval.py`

---

## Success metrics

### For `workflow_action`
- every `ViolationAction` produces a distinct observable path
- audit logs record path-specific metadata
- no action type is silently collapsed into generic block semantics

### For amendment diffs
- reviewers can inspect amendment impact without reading raw YAML by hand
- workflow changes are clearly surfaced
- pre/post constitutional hashes are visible in reports

### For constitution-eval
- new constitutions can be regression-tested before deployment
- candidate amendment bundles can be rejected automatically on scenario regressions
- eval reports become launch / release artifacts

---

## Bottom line

The next highest-leverage ACGS move is not more broad research. It is to complete the operating loop around constitutions:

- **enforce them distinctly** with real `workflow_action` semantics,
- **change them legibly** with amendment diffs and lineage,
- and **test them before activation** with constitution-eval.

That turns ACGS from a promising governance runtime into a much more complete constitutional governance system.
