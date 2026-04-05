# Subnet Concept: Technical Accuracy Notes

Cross-reference between subnet concept claims and ACGS-2 codebase reality.
Reviewed March 2026 against commit history up to `1097e429`.

---

## What the Concept Document Gets Right

### Escalation / Human-in-the-Loop Architecture (GREEN)

The strongest technical foundation. Fully implemented in `enhanced_agent_bus/deliberation_layer/`:

| Component | File | What It Does |
|-----------|------|--------------|
| Impact scoring | `impact_scorer.py` | 7-vector governance risk scoring (0.0--1.0) |
| Adaptive routing | `adaptive_router.py` | Three-tier routing: LOW/MEDIUM/HIGH |
| Deliberation queue | `deliberation_queue.py` | `DeliberationTask` dataclass with human fields |
| HITL manager | `hitl_manager.py` | Reviewer notification via Slack/Teams |
| Override tracking | `impact_scorer.py` | `spec_to_artifact_score = 1 - override_rate` |
| Workflow orchestration | `deliberation_workflow.py` | Full lifecycle with compensation/rollback |

The three-tier model:
- **LOW** (< 0.3): Fully automated, sub-millisecond
- **MEDIUM** (0.3--0.8): Auto-remediation + 15-minute human override window
- **HIGH** (>= 0.8): Blocks until human approval

### Z3 Formal Verification (GREEN)

`Z3PolicyVerifier` at `enhanced_agent_bus/verification_layer/z3_policy_verifier.py`:
- Full Z3 SMT solver integration with constraint generation
- Time-bounded verification with heuristic fallback
- Also available via `acl_adapters/z3_adapter.py`

### Compliance Frameworks (GREEN)

Nine pre-built frameworks in `acgs-lite/src/acgs_lite/compliance/`:
- `nist_ai_rmf.py`, `iso_42001.py`, `oecd_ai.py`, `gdpr.py`, `hipaa.py`
- `nyc_ll144.py`, `soc2_ai.py`, `us_fair_lending.py`
- Plus `eu_ai_act/` module with article-level coverage (Articles 12, 13, 14)

Report generation: `report.py` (551 lines) produces PDF/Markdown with cross-framework
gap analysis.

### Custom Constitutions (GREEN)

`ConstitutionBuilder` at `acgs-lite/src/acgs_lite/constitution/templates.py`:
- Fluent API for programmatic constitution building
- YAML-based constitution format
- Template extension and rule composition

### Sub-Millisecond Latency (GREEN)

Benchmarked at 560ns P50 on Rust/PyO3 hot path. Python fallback ~5--15us.
Note: this is **rule-matching latency**, not full end-to-end compliance assessment.

---

## What the Concept Document Gets Wrong

### "97% Accuracy" (RED -- Misframed)

**Claim**: "97% accuracy" with a "3% failure rate."

**Reality**: The 97/3 split (from `DEVPOST_SUBMISSION.md`) refers to **escalation rate by
design**, not accuracy:

> "97% of decisions are verified in under a millisecond. 3% are escalated to humans."

Actual benchmark results (`autoresearch/results.tsv`, 847 scenarios):
- Compliance rate: **100%** (1.000000)
- False negative rate: **0%**
- The system does not "fail" on 3% -- it **escalates** 3% by design

**Fix applied in revised doc**: Reframed as escalation rate, not failure rate.

### Failure Mode Percentages (RED -- Fabricated)

**Claim**: Constitutional Conflicts (41%), Context Misinterpretation (27%), Stakeholder
Irreconcilability (19%), Edge Case Ambiguity (13%).

**Reality**: These categories and percentages **do not exist anywhere in the codebase**.
No enum, no analysis, no research paper, no benchmark result contains them.

**Fix applied in revised doc**: Categories presented as a working taxonomy for escalation
types. Percentages removed. Quantifying their frequency flagged as an open research
question.

### "Transformer-Based Contextual Interpretation Engine" (RED -- Does Not Exist)

**Claim**: One of three reasoning engines is a "transformer-based interpretation" engine.

**Reality**: No transformer-based reasoning engine exists. The codebase uses:
- Keyword-based semantic scoring (`minicpm_semantic.py`)
- LLM wrappers (`deliberation_layer/llm_assistant.py`)
- Neither is a distinct "contextual interpretation engine"

**Fix applied in revised doc**: Replaced "three reasoning engines" with accurate
description of the verification pipeline components.

### "Blockchain-Anchored" Anything (RED -- Does Not Exist)

**Claim**: Compliance certificates are "blockchain-anchored." Decisions are "recorded
on-chain."

**Reality**: Zero blockchain integration exists in the codebase.
- `ComplianceCertificate` uses local HMAC-SHA256 signing
- `CertificateAuthority` maintains an in-memory chain, not distributed ledger
- `AuditLog` uses local SHA-256 hash chaining

**Fix applied in revised doc**: Reframed on-chain recording as a capability the Bittensor
subnet would enable (true -- that's the point of deploying on Bittensor), not something
that exists today.

### Constitutional Hash Scope (RED -- Overstated)

**Claim**: Hash ensures "integrity and traceability of all governance decisions."

**Reality**: Hash `608508a9bd224290` covers **only the rule set**:
```
{rule.id}:{rule.text}:{rule.severity}:{rule.hardcoded}:{rule.keywords}
```
It is static -- changes only when rules change, not per-decision. Individual audit log
entries attach the hash but it does not commit to decision content.

**Fix applied in revised doc**: Described accurately as rule-set integrity hash with audit
entries recording validation outcomes.

---

## What the Concept Document Overstates

### "Real-Time Compliance Scores" (YELLOW)

`GovernanceMetrics` provides operational event counts (allow/deny rates, escalation
frequency). `MultiFrameworkAssessor` performs one-shot assessment. Neither is continuous
real-time scoring.

**Fix applied in revised doc**: Described as "operational governance metrics" rather than
"real-time compliance scores."

### Multi-Perspective Synthesis Engine (YELLOW)

`polis_engine.py` and `democratic_governance.py` exist but implement Polis-style
deliberation/voting -- a consensus mechanism, not a synthesis engine combining outputs from
other reasoning engines.

**Fix applied in revised doc**: Described as "Polis-style democratic deliberation" rather
than a synthesis pipeline.

### MACI Model (YELLOW)

Two incompatible implementations coexist:
- `acgs-lite/maci.py`: 3 roles (Proposer, Validator, Executor) + Observer
- `enhanced_agent_bus/maci/enforcer.py`: 7 roles (Executive, Legislative, Judicial,
  Monitor, Auditor, Controller, Implementer)

No mapping between them. The 3-role model is what the subnet concept references.

**Fix applied in revised doc**: References MACI without asserting a unified model. Added
an open question about mapping MACI roles to Bittensor's architecture.

---

## Codebase Components Most Relevant to Subnet Implementation

These are the modules that would form the subnet's core:

| Component | Path | Subnet Role |
|-----------|------|-------------|
| Constitution loader | `acgs-lite/src/acgs_lite/constitution/` | Define governance rules |
| Governance engine | `acgs-lite/src/acgs_lite/engine/core.py` | Automated validation |
| Z3 verifier | `enhanced_agent_bus/verification_layer/z3_policy_verifier.py` | Formal policy checking |
| Adaptive router | `enhanced_agent_bus/deliberation_layer/adaptive_router.py` | Escalation detection |
| Deliberation queue | `enhanced_agent_bus/deliberation_layer/deliberation_queue.py` | Task packaging for miners |
| HITL manager | `enhanced_agent_bus/deliberation_layer/hitl_manager.py` | Miner notification dispatch |
| Impact scorer | `enhanced_agent_bus/deliberation_layer/impact_scorer.py` | 7-vector risk scoring |
| Audit log | `acgs-lite/src/acgs_lite/audit.py` | Decision recording |
| Report generator | `acgs-lite/src/acgs_lite/report.py` | Compliance reports |
| Compliance frameworks | `acgs-lite/src/acgs_lite/compliance/` | Regulatory mapping |
| Certificate authority | `acgs-lite/src/acgs_lite/constitution/certificate.py` | Compliance attestation |
| MACI enforcer | `enhanced_agent_bus/maci/enforcer.py` | Role separation |
| Polis engine | `enhanced_agent_bus/governance/polis_engine.py` | Democratic deliberation |

---

## What Needs to Be Built for the Subnet

Features referenced in the concept doc that do not yet exist:

1. **Bittensor integration layer** -- miner/validator protocol, task broadcast, response
   collection, TAO reward distribution
2. **On-chain audit recording** -- extend `AuditLog` to write to Bittensor's chain
3. **Deliberative authenticity detection** -- validator logic to distinguish human
   reasoning from AI-generated responses
4. **Miner qualification tiers** -- complexity-based task routing to qualified miners
5. **Precedent feedback loop** -- mechanism to incorporate miner judgments into future
   automated decision-making
6. **Per-decision hash commitment** -- extend constitutional hash to cover individual
   governance decisions, not just the rule set
7. **MACI role mapping** -- map Proposer/Validator/Executor onto Bittensor
   miner/validator architecture
