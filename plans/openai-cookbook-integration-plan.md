<!-- /autoplan restore point: /home/martin/.gstack/projects/martin668-acgs-clean/main-autoplan-restore-20260330-145813.md -->
# ACGS × OpenAI Agentic Governance Cookbook — Integration Plan

**Branch:** main (pre-feature-branch)
**Date:** 2026-03-29
**Source:** https://developers.openai.com/cookbook/examples/partners/agentic_governance_guide/agentic_governance_cookbook
**Constitutional Hash:** 608508a9bd224290

---

## Context

OpenAI published a partner cookbook titled "Building Governed AI Agents: A Practical Guide to
Agentic Scaffolding." It demonstrates governance patterns using `openai-agents` SDK,
`openai-guardrails` library, tracing, eval harnesses, threshold tuning, and red-teaming
via Promptfoo. The cookbook builds a Private Equity firm AI assistant as a worked example.

This plan identifies what ACGS should adopt, integrate, or explicitly reject from
the cookbook, based on deep analysis of both systems.

## Premises

1. **ACGS is infrastructure, the cookbook is a recipe.** ACGS provides the governance
   kernel (deterministic rules, MACI, audit, compliance). The cookbook shows how to
   glue OpenAI's SDK products together. These are complementary layers, not competitors.

2. **LLM-as-judge and deterministic governance serve different purposes.** The cookbook's
   guardrails use LLM calls (~200ms, ~$0.001/check) for semantic classification (jailbreak,
   off-topic). ACGS's engine uses Aho-Corasick + Rust (~1µs, free after init) for structural
   rule matching. Both are needed; neither replaces the other.

3. **ACGS's per-rule eval gap is the highest-leverage improvement.** The `autoresearch/`
   harness has 809 labeled scenarios with decision-level FP/FN tracking. The gap is
   **per-rule granularity** — which specific rules fired and whether they should have —
   not correctness testing per se. Standard ML metrics (precision/recall/F1) per rule
   would make rule changes evidence-based.

4. **Red-teaming is a genuine gap.** ACGS has no adversarial testing pipeline. The
   keyword/pattern engine is inherently bypassable through paraphrasing. Promptfoo CI
   integration would expose these blind spots.

5. **ACGS already does policy-as-package better than the cookbook.** `pip install acgs`
   with `GovernedOpenAI(constitution=c)` is structurally identical to the cookbook's
   `pip install git+<policy-repo>` pattern, but with tamper-evident audit, MACI, and
   15+ compliance frameworks.

6. **Vendor lock-in to OpenAI's SDK is unacceptable.** ACGS supports OpenAI, Anthropic,
   Google GenAI, xAI, LangChain, LlamaIndex, AutoGen, and A2A. Any integration must
   preserve this vendor neutrality.

## Strategic Position

ACGS as the **governance kernel** — the deterministic, auditable, compliance-proven base
layer that works with any provider's probabilistic guardrails on top:

```
┌─────────────────────────────────────────┐
│  Application Layer                       │
│  (openai-agents, LangChain, AutoGen...) │
├─────────────────────────────────────────┤
│  LLM Guardrails (optional, probabilistic)│
│  openai-guardrails, custom classifiers   │
├─────────────────────────────────────────┤
│  ACGS Governance Kernel (deterministic)  │
│  Constitutional engine, MACI, audit      │
│  Compliance mapping (15+ frameworks)     │
├─────────────────────────────────────────┤
│  LLM Providers                           │
│  OpenAI, Anthropic, Google, xAI...       │
└─────────────────────────────────────────┘
```

---

## Approved Work Item

### Per-Rule Eval Harness (Priority 1, eval-first)

**Objective:** Add per-rule precision/recall/F1 metrics and scenario-level outcome
metrics to the ACGS governance engine, extending the existing `GovernanceTestSuite`.

**What it does:** For each of the 18 active constitutional rules, measure how
accurately the engine fires (or doesn't fire) against 809 labeled scenarios.
Primary CI gate: scenario-level decision accuracy. Diagnostic: per-rule P/R/F1
for rule authors.

**Files affected:**
- `autoresearch/eval_rules.py` (new) — loads scenarios + sidecar annotations, runs suite, outputs metrics
- `autoresearch/eval_data/rule_annotations.yaml` (new) — per-scenario rule labels joined by content hash
- `packages/acgs-lite/src/acgs_lite/constitution/test_suite.py` — extend with `compute_rule_metrics()`
- `packages/acgs-lite/tests/test_rule_metrics.py` (new) — unit tests for metrics math
- `Makefile` — add `eval-rules` target (standalone, NOT in `make test`)

**Key implementation constraints:**
1. **strict=False required** — engine raises on first CRITICAL rule in strict mode,
   losing bundled violations. Eval must capture ALL rules that fire.
2. **Sidecar annotations** — do NOT modify frozen `autoresearch/scenarios/`. Use
   `autoresearch/eval_data/rule_annotations.yaml` joined by SHA256 content hash.
3. **Reuse GovernanceTestSuite** — don't reinvent. Extend `TestReport` with
   `compute_rule_metrics()` and `scenario_outcome_metrics()`.
4. **Canonicalize rule IDs** — uppercase before comparison (CLI uses lowercase,
   engine uses uppercase).
5. **Label validation** — fail fast if annotation references rule IDs not in
   the active constitution.

**Output:** `eval_results/rule_metrics.json` (machine-readable) + `eval_results/summary.md` (human-readable).

**Estimated effort:** human ~2 days / CC ~30 min

## Deferred Work Items (see TODOS.md)

| Item | Why Deferred | Depends On |
|------|-------------|------------|
| Generic semantic-guardrail adapter | Needs provider-agnostic design (Codex: OpenAI-specific contradicts Premise 6) | Eval harness results |
| Red-team CI pipeline | Narrow scope covers only paraphrase; needs multi-turn/tool-call/memory abuse design | Eval harness identifying weakest rules |
| ZDR observability mode | One egress constraint ≠ compliance story; needs encryption/access/deletion/tenant design | Enterprise customer demand |
| Reference app / demo | Go-to-market question, not engineering question | Strategic decision |

---

## Explicitly Not Building

| Item | Reason |
|------|--------|
| Threshold tuning feedback loops | ACGS rules are deterministic. No confidence thresholds to tune. If LLM-based guardrails are added via Priority 2 adapter, tuning lives in `openai-guardrails`, not ACGS. |
| `openai-agents` SDK deep integration | The agent bus has its own orchestration. Tight coupling to one vendor's SDK violates Premise 6. |
| Cookbook-style demo app | ACGS's docs should show the kernel story, not replicate the PE firm demo. Different audience. |
| Promptfoo as a production guardrail | Promptfoo is a test tool, not a runtime guardrail. Use for CI, not in the hot path. |

---

## Success Criteria

1. **`make eval-rules`** runs in <30s, produces per-rule precision/recall/F1 + scenario-level accuracy.
2. **Label validation** catches stale rule IDs and case mismatches before eval runs.
3. **Regression detection** via `GovernanceTestSuite.assert_no_regressions()` flags any metric drop.
4. **12 tests** pass (unit math, validation, integration, edge cases).

## Dependencies

- No new external dependencies. Uses existing `acgs_lite` + `autoresearch/` infrastructure.

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Annotation effort for 809 scenarios | Auto-generate initial labels by running engine with strict=False, then hand-verify outliers |
| Scenario content hash collisions | SHA256 on (action + sorted context) — collision probability negligible |
| GovernanceTestSuite API changes | Pin to existing interface, extend via new methods only |

---

## /autoplan CEO Review Findings

### Approach Selected: C (Eval-First)
Ship only Priority 1 (per-rule eval harness). Use its results to inform subsequent work.
Priorities 2-4 deferred to TODOS.md with redesign notes.

### Corrected Premise
Premise 3 overstated — 809 labeled scenarios already exist with decision-level FP/FN.
The real gap is per-rule granularity.

### NOT in scope (this plan)
- Priority 2 (openai-guardrails adapter) — deferred; needs redesign as generic semantic-guardrail adapter per Codex feedback
- Priority 3 (red-team CI) — deferred; narrow scope covers only paraphrase bypass, not multi-turn/tool-call/memory abuse
- Priority 4 (ZDR observability) — deferred; one egress constraint ≠ compliance story, needs encryption/access/deletion/tenant-isolation design
- Cookbook-style demo app — deferred; go-to-market question, not engineering question
- Customer wedge/ICP definition — deferred; upstream strategy work

### What already exists
- `autoresearch/benchmark.py` — 809 scenarios, decision-level FP/FN, composite_score
- `autoresearch/scenarios/` — 6 JSON files with action/expected/context labels
- `packages/acgs-lite/src/acgs_lite/engine/core.py` — `validate()` returns `ValidationResult` with `violations: list[Violation]` (per-rule data already available)
- `GovernedOpenAI` — drop-in OpenAI wrapper (pattern to mirror for any future adapter)
- 15 integration adapters — vendor-neutral pattern established

### Dream State Delta
This plan (eval harness only) advances us from "correctness at decision level" to
"correctness at rule level." The 12-month ideal is automated eval regression in every
PR with per-rule tracking over time. This plan delivers the foundation.

### Error & Rescue Registry

| METHOD/CODEPATH | WHAT CAN GO WRONG | RESCUED? | USER SEES |
|---|---|---|---|
| load_scenarios() | Missing file | Y | Clear error message |
| load_scenarios() | Malformed JSON | Y | Warning + skip file |
| evaluate_per_rule() | Rule ID in labels not in constitution | **N ← GAP** | KeyError crash |
| compute_metrics() | Zero samples for a rule | **N ← GAP** | ZeroDivisionError |

### Failure Modes Registry

| CODEPATH | FAILURE MODE | RESCUED? | TEST? | USER SEES | LOGGED? |
|---|---|---|---|---|---|
| label_validation | Stale rule IDs after constitution change | N | N | Crash | N |
| compute_metrics | All-negative rule (0 positive samples) | N | N | NaN/Inf | N |
| scenario_loading | Duplicate scenario IDs | N | N | Silent double-count | N |

**2 CRITICAL GAPS** (rescue + test needed for stale rule IDs and zero-division).

### Codex CEO Findings (verbatim summary)
1. No customer wedge — technology comparison, not market strategy
2. Priority 2 contradicts Premise 6 — named OpenAI adapter = vendor lock
3. Per-rule metrics wrong truth metric — internal calibration, not outcome
4. Red-team too narrow — misses multi-turn, tool-call, memory abuse
5. ZDR overstated — one egress constraint ≠ compliance
6. Demo app dismissed too quickly — reference apps drive devtool adoption

### Cross-Phase Themes
None yet (CEO only). Will assess after Eng review.

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Principle | Rationale | Rejected |
|---|-------|----------|-----------|-----------|----------|
| 1 | CEO | Mode: SELECTIVE EXPANSION | P3 pragmatic | Feature enhancement on existing system, not greenfield | EXPANSION, HOLD, REDUCTION |
| 2 | CEO | Approach C (eval-first) | P3 pragmatic | Eval data drives all other decisions | Approach A (extend only), B (all 4 at once) |
| 3 | CEO | Correct Premise 3 | P5 explicit | 809 scenarios already exist; gap is per-rule, not correctness | Original wording |
| 4 | CEO | Defer Priorities 2-4 | P2 boil lakes | P1 is the lake; P2-4 are separate lakes needing their own eval data | Ship all 4 together |
| 5 | CEO | Accept Codex: generic adapter | P4 DRY | OpenAI-specific adapter contradicts vendor neutrality premise | Named openai-guardrails adapter |
| 6 | CEO | Both per-rule + scenario metrics | P1 completeness | Per-rule for rule authors + scenario-level for operators | Per-rule only (TASTE) |
| 7 | CEO | Defer demo app question | P6 action | Go-to-market question outside this plan's scope | Build demo now (TASTE) |
| 8 | CEO | Note multi-turn abuse gap | P2 boil lakes | Promptfoo on engine is lake; runtime abuse testing is ocean | Expand red-team scope |
| 9 | CEO-S2 | Fix KeyError gap | P1 completeness | Label validation must check rule IDs exist in constitution | Leave unhandled |
| 10 | CEO-S2 | Fix ZeroDivision gap | P1 completeness | Guard zero-sample rules with explicit handling | Leave unhandled |
| 11 | CEO-S4 | Add label validation step | P1 completeness | Fail fast when scenario labels reference removed rules | Silent mismatch |
| 12 | CEO-S5 | Extract shared load_scenarios | P4 DRY | Don't duplicate scenario loading between benchmark.py and eval_rules.py | Copy-paste |
| 13 | CEO-S6 | All 4 test types needed | P1 completeness | Unit (math), unit (validation), integration, edge cases | Skip edge cases |
| 14 | CEO-S8 | JSON + markdown output | P5 explicit | Machine-readable for CI + human-readable for PRs | JSON only |
| 15 | ENG | Use GovernanceTestSuite not new JSONL | P4 DRY | test_suite.py already has GovernanceTestCase with expected_rules_triggered/not_triggered | New parallel schema |
| 16 | ENG | Must run strict=False | P1 completeness | strict=True raises on first CRITICAL, losing bundled violations | Default strict mode |
| 17 | ENG | Sidecar annotation file | P5 explicit | Respects frozen autoresearch contract, doesn't modify scenarios/ | Modify frozen corpus |
| 18 | ENG | Separate CI target | P3 pragmatic | Keep dev loop fast; eval is diagnostic, not gating every test run | Fold into make test |
| 19 | ENG | Content hash as join key | P1 completeness | Scenarios have no IDs; need deterministic join to sidecar annotations | Assume ordered match |
| 20 | ENG | Clean up plan scope | P5 explicit | Remove P2-P4 active details; future implementer will misread scope | Keep all 4 visible |
| 21 | ENG | Canonicalize rule IDs uppercase | P1 completeness | CLI uses lowercase, engine uses uppercase; silent mis-scoring risk | Trust input casing |

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | CLEAR (via /autoplan) | 4 proposed, 0 accepted, 4 deferred |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (via /autoplan) | 6 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | SKIPPED (no UI scope) | — |

**VERDICT:** CEO + ENG CLEARED — ready to implement (Priority 1 only, eval-first approach).

## Eng Review Findings

### Architecture
Reuse `GovernanceTestSuite` (410 LOC, already has rule-level assertions).
Add `compute_rule_metrics()` to `TestReport`. New `eval_rules.py` joins frozen
scenarios with sidecar annotations by content hash.

### Critical Codex Finding: strict=False Required
`GovernanceEngine.validate()` raises `ConstitutionalViolationError` on first CRITICAL
rule when `strict=True`. This collapses multi-rule scenarios into a single exception,
losing the full fired-rule set. The eval harness MUST run with `strict=False` to capture
all violations.

### Key Discovery: GovernanceTestSuite Already Exists
`packages/acgs-lite/src/acgs_lite/constitution/test_suite.py` provides:
- `GovernanceTestCase` with `expected_rules_triggered` + `expected_rules_not_triggered`
- `TestReport` with pass/fail/error/skip, coverage %, regressions
- `GovernanceTestSuite.run()` that captures triggered rules
- `assert_no_regressions()` — baseline comparison
- 410 lines of existing, tested infrastructure

**The plan's JSONL format is unnecessary.** Use YAML fixtures loaded into GovernanceTestSuite.

### Frozen Benchmark Contract
`autoresearch/program.md` says scenarios/ and benchmark.py are read-only.
Solution: sidecar `autoresearch/eval_data/rule_annotations.yaml` joined to
frozen scenarios by SHA256 content hash of (action + context).

### Revised File List (Priority 1 only)
- `autoresearch/eval_rules.py` (new) — loads scenarios + annotations, runs suite, outputs metrics
- `autoresearch/eval_data/rule_annotations.yaml` (new) — per-scenario rule labels
- `packages/acgs-lite/src/acgs_lite/constitution/test_suite.py` — extend with `compute_rule_metrics()`
- `packages/acgs-lite/tests/test_rule_metrics.py` (new) — unit tests for metrics math
- `Makefile` — add `eval-rules` target (standalone, NOT in `make test`)

### Eng Completion Summary
```
+====================================================================+
|            ENG REVIEW — COMPLETION SUMMARY                          |
+====================================================================+
| Scope Challenge    | P1 only (eval-first). Reuse GovernanceTestSuite|
| Architecture       | 1 critical (strict=False), 1 high (reuse suite)|
| Errors             | 2 gaps (KeyError, ZeroDivision) — both fixable |
| Security           | 0 issues (dev tool, no new attack surface)      |
| Data/Edge Cases    | 3 edge cases mapped (empty, zero-positive, hash)|
| Code Quality       | 1 DRY issue (shared scenario loading)           |
| Tests              | 12 tests planned across 4 types                 |
| Performance        | 0 issues (same engine, same scenarios)           |
| Observability      | JSON + markdown output for CI and humans         |
| Deployment         | Feature branch → PR → merge                     |
| Long-term          | Reversibility 5/5. Foundation for eval-driven gov|
+--------------------------------------------------------------------+
| Codex eng findings | 6 (1 critical, 2 high, 3 medium)                |
| Critical gaps      | 0 (all addressed in decisions)                  |
| Test plan          | Written to ~/.gstack/projects/                  |
+====================================================================+
```
