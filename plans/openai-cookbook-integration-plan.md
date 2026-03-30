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

## Work Items

### Priority 1: Constitutional Rule Eval Harness

**Objective:** Build a labeled eval dataset and precision/recall/F1 scoring for the
ACGS constitutional rule engine, integrated with the `autoresearch/` benchmark harness.

**What it does:** For each rule in the constitution, create test cases with expected
firing behavior. Run the engine. Measure TP/FP/FN/TN per rule and per category.
Produce a regression gate: `make eval-rules` fails if any metric drops.

**Files affected:**
- `autoresearch/eval_rules.py` (new) — eval runner
- `autoresearch/eval_data/rule_test_data.jsonl` (new) — labeled dataset
- `autoresearch/eval_data/` (new directory) — eval artifacts
- `packages/acgs-lite/tests/test_eval_harness.py` (new) — pytest integration
- `Makefile` — add `eval-rules` target

**Approach:**
1. Extract the existing `autoresearch/scenarios/` corpus and add expected rule-firing
   labels (which rule IDs should fire for each scenario).
2. Build a `RuleEval` class that runs `GovernanceEngine.validate()` on each labeled
   input and computes precision/recall/F1 per rule.
3. Output: JSON metrics file + markdown summary table.
4. CI integration: `make eval-rules` runs as part of `make test`.

**Why this matters:** The autoresearch harness currently measures `composite_score`,
`compliance_rate`, and latency — but has no standard ML metrics per rule. A rule change
that improves speed but introduces 3 new false positives is invisible today. This eval
harness makes it visible.

**Estimated effort:** human ~3 days / CC ~45 min

### Priority 2: `openai-guardrails` Integration Adapter

**Objective:** Create `acgs_lite.integrations.openai_guardrails` that wraps
`GuardrailsOpenAI` with ACGS constitutional governance on top.

**What it does:** Users get deterministic rule checks (µs) + LLM-based semantic
checks (ms) + MACI enforcement + tamper-evident audit in one client.

**Files affected:**
- `packages/acgs-lite/src/acgs_lite/integrations/openai_guardrails.py` (new)
- `packages/acgs-lite/tests/test_openai_guardrails_integration.py` (new)
- `packages/acgs-lite/pyproject.toml` — add `openai-guardrails` optional extra

**Approach:**
1. Wrap `GuardrailsOpenAI` the same way `GovernedOpenAI` wraps `OpenAI`:
   validate input against constitution before the guardrails client processes it,
   validate output after.
2. Merge audit trails: ACGS audit entries + guardrails trigger events in one log.
3. Preserve `GovernedOpenAI` as the standalone (no-guardrails-lib) path.
4. Optional dependency: `pip install acgs[openai-guardrails]`.

**Why this matters:** Positions ACGS as the superset, not a competitor. Users who
adopt `openai-guardrails` (as the cookbook recommends) get ACGS governance for free
on top. Users who don't want the OpenAI dependency keep using `GovernedOpenAI`.

**Estimated effort:** human ~2 days / CC ~30 min

### Priority 3: Red-Team CI Pipeline

**Objective:** Add adversarial testing targeting the ACGS governance engine,
running automatically on policy/rule changes.

**What it does:** Generates hundreds of adversarial inputs designed to bypass
keyword/pattern matching through paraphrasing, encoding, and indirection.
Tests them against `GovernedAgent` and reports bypass rates.

**Files affected:**
- `.github/workflows/redteam.yml` (new) — CI pipeline
- `tests/redteam/` (new directory) — red team config and target scripts
- `tests/redteam/target.py` (new) — bridges Promptfoo to GovernedAgent
- `tests/redteam/promptfooconfig.yaml` (new) — red team configuration
- `docs/security/red-teaming.md` (new) — documentation

**Approach:**
1. Install Promptfoo. Create a target script that runs adversarial inputs
   through `GovernedAgent` with the default constitution.
2. Configure plugins: `prompt-injection`, `system-prompt-override`, `policy`,
   `off-topic`, encoding strategies (`base64`, `leetspeak`, `rot13`).
3. CI trigger: on changes to `packages/acgs-lite/src/acgs_lite/constitution/`,
   `autoresearch/constitution.yaml`, or `packages/acgs-lite/src/acgs_lite/engine/`.
4. Report: artifact upload with pass/fail rates per vulnerability category.

**Why this matters:** The constitutional engine's keyword+pattern matching is
inherently bypassable through paraphrasing. "Deploy without safety review" is
caught; "put into production skipping the safety check" may not be. Red-teaming
finds these gaps systematically instead of waiting for production incidents.

**Estimated effort:** human ~1 week / CC ~1 hour

### Priority 4: ZDR Observability Mode

**Objective:** Add Zero Data Retention tracing mode to the enhanced agent bus
observability subsystem.

**What it does:** Provides a trace processor that never sends data to external
systems. Traces stay within the deployment boundary. Supports HIPAA, financial
services, and government deployments.

**Files affected:**
- `packages/enhanced_agent_bus/observability/zdr.py` (new)
- `packages/enhanced_agent_bus/observability/__init__.py` — register ZDR mode
- `packages/enhanced_agent_bus/tests/test_zdr_observability.py` (new)
- `docs/deployment/zdr-mode.md` (new) — compliance documentation

**Approach:**
1. Create a `ZDRTraceProcessor` that writes structured traces to local
   storage (file, internal DB, or memory ring buffer) — never to external APIs.
2. PII redaction before storage (using the existing ACGS rule engine for detection).
3. Configurable retention policies (auto-purge after N hours/days).
4. Configuration: `ACGS_ZDR_MODE=true` environment variable.

**Why this matters:** Real compliance need called out explicitly in the cookbook.
Financial services and healthcare deployments need observability without data
leaving the trust boundary. Without this, organizations default to "disable
tracing entirely," losing all observability.

**Estimated effort:** human ~3 days / CC ~45 min

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

1. **Rule eval harness:** `make eval-rules` runs in <30s, produces per-rule
   precision/recall/F1 metrics, and fails CI on any metric regression.
2. **Guardrails adapter:** `GovernedGuardrailsOpenAI` passes the same test suite
   as `GovernedOpenAI` plus guardrails-specific trigger tests.
3. **Red-team CI:** Promptfoo runs on policy changes, reports bypass rates,
   and blocks merge if critical bypasses are found.
4. **ZDR mode:** Traces are written only to local storage. No data leaves
   the process. Configurable retention. Tests verify no external network calls.

## Dependencies

- `openai-guardrails` PyPI package (Priority 2 only)
- `promptfoo` npm package + Node.js 20+ (Priority 3 only)
- No new dependencies for Priorities 1 and 4

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| `openai-guardrails` API instability | Pin version. Optional dependency. Adapter wraps, doesn't inherit. |
| Promptfoo requires Node.js in CI | Already available in most CI environments. Document as optional. |
| Red-team false positives blocking CI | Separate "advisory" and "blocking" severity levels. Only critical bypasses block merge. |
| ZDR mode performance impact | Ring buffer for recent traces, async file writes. Benchmark to verify <5% overhead. |
