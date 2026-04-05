# Subnet Concept: Q&A Responses

Detailed responses to stakeholder questions on the subnet concept document, incorporating
feedback from both initial codebase analysis and stakeholder review.

*March 2026. Cross-references `06-subnet-concept.md` and `06-subnet-concept-technical-notes.md`.*

---

## Table of Contents

1. [7-Vector Governance Scoring](#1-7-vector-governance-scoring)
2. [Failure Mode Percentages](#2-failure-mode-percentages)
3. [Blockchain-Anchored: Concrete Design](#3-blockchain-anchored-concrete-design)
4. [Constitutional Hash Scope](#4-constitutional-hash-scope)
5. [Multi-Perspective Synthesis Engine](#5-multi-perspective-synthesis-engine)
6. [MACI Role Model: Mapping to Bittensor Parties](#6-maci-role-model-mapping-to-bittensor-parties)

---

## 1. 7-Vector Governance Scoring

There are **two scoring systems** that operate at different layers. Both use a 7-vector
weighted model, but they serve different purposes.

### Layer 1: Subnet Opportunity Scoring (Miner/Validator Economics)

This scoring system evaluates **subnet-level opportunity** — how attractive the subnet is
for miners and how well governance is functioning at the network layer. It extends the
current 4-input `compute_opportunity_score()` to a 7-vector model:

| # | Vector | Input | Weight |
|---|--------|-------|--------|
| V1 | **Emission yield** | `emission_rate / miner_count` | 0.25 |
| V2 | **Hardware accessibility** | `_ACCESSIBILITY` multiplier | 0.15 |
| V3 | **Competition saturation** | `avg_miner_score` → competition adjustment | 0.15 |
| V4 | **Constitutional compliance** | % of miner outputs passing governance rules | 0.20 |
| V5 | **Validator consensus** | Standard deviation of validator scores (lower = better) | 0.10 |
| V6 | **Trend momentum** | 7-day change magnitude + direction | 0.10 |
| V7 | **Stake depth** | Total stake relative to network average | 0.05 |

**Formula**:

```
score = Σ(weight_i × normalized_vector_i) × 100
```

Each vector is normalized to `[0, 1]` before weighting.

**Hard gate**: The constitutional compliance vector (V4) acts as a non-negotiable gate.
If V4 falls below a threshold (e.g., 0.60), the overall score caps at 40 regardless of
how strong the other vectors are. This makes governance compliance non-negotiable — a
subnet with high emissions but poor constitutional compliance cannot score well.

### Layer 2: Per-Decision Governance Scoring (ACGS-2 Engine)

This scoring system evaluates **individual governance decisions** as they flow through the
ACGS-2 engine. It determines whether a decision can be resolved automatically or must be
escalated to human miners.

| # | Dimension | Weight | What It Measures |
|---|-----------|--------|------------------|
| 1 | **Safety** | 20% | Physical and operational harm risk |
| 2 | **Security** | 20% | Unauthorized access, breaches, exploits |
| 3 | **Privacy** | 15% | PII exposure, consent violations, GDPR |
| 4 | **Fairness** | 15% | Algorithmic bias, discriminatory outcomes |
| 5 | **Reliability** | 10% | Uptime, data integrity, fault tolerance |
| 6 | **Transparency** | 10% | Explainability, audit trail, disclosure |
| 7 | **Efficiency** | 10% | Resource utilization, latency, cost |

#### How Per-Decision Scoring Works

1. **Text extraction** — content, action descriptions, reasoning text, and tool names
   are extracted from the incoming message context.

2. **Per-dimension scoring** — for each of the 7 governance domains, two signals are
   combined:
   - **Semantic similarity** (80% weight when MiniCPM model is available): the message
     embedding is compared via cosine similarity to pre-computed domain centroid
     embeddings. Each domain has 6 reference texts that define what "high impact" looks
     like (e.g., "Unauthorized access attempt detected" for security).
   - **Keyword boost** (20% weight): high-impact indicator keywords per domain trigger a
     score boost (e.g., "breach", "exploit", "vulnerability" for security).

3. **Aggregate score** = weighted sum of all 7 dimension scores.

4. **Routing decision** based on aggregate:

| Tier | Impact Score | Handling | Share |
|------|-------------|----------|-------|
| **LOW** | < 0.3 | Fully automated, sub-millisecond | ~97% |
| **MEDIUM** | 0.3 – 0.8 | Auto-remediation + 15-min human override window | ~2% |
| **HIGH** | ≥ 0.8 | Blocks until human approval | ~1% |

When the MiniCPM embedding model is not available, the system falls back to keyword-only
scoring at lower confidence (0.6 vs 0.95).

#### Secondary Scoring Formula

The main `ImpactScorer` class also applies a secondary formula with five weighted factors:

| Factor | Weight | What It Measures |
|--------|--------|------------------|
| Semantic | 60% | Keyword and content analysis |
| Permission | 10% | Tool risk level (execute, transfer, delete) |
| Volume | 5% | Agent request frequency (anomaly detection) |
| Context | 20% | Transaction amount, payload analysis |
| Drift | 5% | Behavioral deviation from historical average |

A 6th dimension — **DTMC trajectory risk** — uses a Discrete-Time Markov Chain model to
detect anomalous agent behavior patterns over time. Applied additively, opt-in (weight
defaults to 0.0).

### How the Two Layers Connect

The per-decision scoring (Layer 2) feeds into the subnet opportunity scoring (Layer 1):

- Layer 2 produces the **constitutional compliance rate** (V4 in Layer 1): the percentage
  of miner outputs that pass governance rules.
- Layer 2 produces the **escalation rate**: the percentage routed to MEDIUM/HIGH tiers,
  which becomes the workload for human reviewer miners.
- Layer 1 uses these as inputs to assess overall subnet health and economic opportunity.

### Codebase References

| Component | File |
|-----------|------|
| 7-vector model definition | `packages/enhanced_agent_bus/impact_scorer_infra/models.py` → `ImpactVector` |
| MiniCPM semantic scorer | `packages/enhanced_agent_bus/impact_scorer_infra/algorithms/minicpm_semantic.py` |
| Domain reference texts | Same file → `DOMAIN_REFERENCE_TEXTS` |
| Aggregate weights | Same file → `weights` dict in `score()` method |
| Main impact scorer facade | `packages/enhanced_agent_bus/deliberation_layer/impact_scorer.py` |
| Scoring constants | `packages/enhanced_agent_bus/governance_constants.py` |
| Adaptive router | `packages/enhanced_agent_bus/deliberation_layer/adaptive_router.py` |

---

## 2. Failure Mode Percentages

### Decision Outcome Categories

Accurate percentages require instrumentation — you cannot estimate these reliably from
static analysis. The categories to track are:

| Decision Outcome | Meaning | Expected % |
|-----------------|---------|------------|
| **Auto-resolved** | Decision made confidently by automated engine | ~85% |
| **Low-confidence escalation** | Score within ambiguity band (e.g., 45–55) | ~10% |
| **Constitutional violation (hard reject)** | Blocked outright, no human needed | ~4% |
| **Infrastructure failure** | Timeout, missing data, service unavailable | ~1% |
| **Human escalation (miners)** | The 3% requiring human deliberation | ~3% |

**Key distinction**: The 3% that miners see is only the low-confidence escalations — not
the hard rejects. Hard rejects are handled automatically (the constitution clearly
prohibits the action). Miners only receive cases where the automated system genuinely
cannot decide.

### What Miners See on Escalation

To prepare miners for the 3% escalation workload, each escalated case should surface:

1. **Why the automated system couldn't decide** — which vector was ambiguous, what the
   competing scores were, and what pushed the case into the ambiguity band.

2. **Historical precedent** — similar past cases and how they were resolved. As the
   subnet accumulates decisions, this becomes increasingly useful.

3. **Stake at risk** — how much TAO is affected by this decision. Higher-stakes cases
   may warrant more careful deliberation and could carry higher emissions.

### Implementation: Decision Outcome Tracking

To get real percentages, add a `decision_outcome` enum to each governance event log and
aggregate over rolling 7-day windows:

```python
class DecisionOutcome(str, Enum):
    AUTO_PASS = "auto_pass"           # Confident automated approval
    AUTO_REJECT = "auto_reject"       # Constitutional violation, hard reject
    ESCALATED = "escalated"           # Sent to human miners
    INFRA_ERROR = "infra_error"       # Timeout, missing data, service failure
```

Aggregation produces a rolling dashboard:

```
Week of 2026-03-24:
  auto_pass:    84.7%  (↑0.3% vs prior week)
  auto_reject:   4.1%  (↓0.2%)
  escalated:     3.2%  (→ stable)
  infra_error:   0.8%  (↓0.1%)
  low_conf:      7.2%  (auto-resolved after re-scoring)
```

### Recommended Framing for Miners

> "The automated engine handles ~97% of governance decisions. Of the remaining ~3%
> escalated to miners, each case includes the specific governance vector that was
> ambiguous, relevant historical precedent, and the TAO at stake. Your job is to resolve
> the cases the machine genuinely can't — and your past resolutions make the machine
> smarter over time."

---

## 3. Blockchain-Anchored: Concrete Design

There are three distinct blockchain uses, and the technology choice differs per use.

### A. Anchoring the Constitutional Hash (Cheapest, Highest Value)

**What**: Write the constitutional hash + block height to Bittensor's own chain via an
extrinsic.

**Why**: No ZKP needed — the hash is public by design. It's a version identifier for the
rule set. Changing the constitution creates a new hash, creating an auditable version
history on-chain.

**How**: A simple extrinsic call per constitution version change. Minimal gas cost,
maximum auditability. Any party can re-hash the constitution document and compare it to
the on-chain record.

**Current state**: The hash `608508a9bd224290` exists in the codebase as a static
fingerprint. Extending it to on-chain anchoring is straightforward.

### B. Anchoring Individual Governance Decisions (Where ZKP Matters)

**What**: Prove that a specific miner output was evaluated under a specific constitution
version and passed — without revealing the output content.

**Why**: A miner's output may be sensitive. Clients need compliance proof without
exposing proprietary data. A ZK-SNARK proves the statement "this output was evaluated
under constitution v3 and passed" without revealing the output itself.

**Technology options**:

| Library | Tradeoff |
|---------|----------|
| **Noir** (Aztec) | Easiest to implement, Rust-based, good for structured proofs |
| **circom/snarkjs** | Most mature ecosystem, JavaScript tooling |
| **RISC Zero** | General computation proofs, most flexible but heaviest |

**Recommended**: Start with Noir for its simplicity and Rust compatibility with the
existing ACGS-2 codebase.

### C. Storage of Audit Logs (Where Arweave/Filecoin Fits)

**What**: Append-only governance decision logs stored permanently on decentralized
storage.

**Why**: Full audit trails are too large for on-chain storage but too important for
centralized storage. Arweave provides permanent, cheap per-byte storage. Logs are
retrievable by constitutional hash as the key.

**How**: Batch audit log entries, compute a merkle root, anchor the root on Bittensor's
chain, store the full log on Arweave. Auditors can verify the merkle root matches the
on-chain anchor and the log content matches the root.

### NMC (Nil Message Compute) — Deferred

NMC is relevant for the synthesis engine (see §5) — computing aggregate statistics over
miner outputs without any single party seeing the raw data. It's more complex to
implement and best deferred until the basic ZKP anchoring is working.

### Privacy Layer Summary

| Layer | Technology | What It Protects | Priority |
|-------|-----------|-----------------|----------|
| Constitution versioning | Bittensor extrinsic | Nothing (public by design) | **Phase 1** |
| Audit log storage | Arweave + merkle anchoring | Log permanence, not content | **Phase 2** |
| Decision compliance proofs | ZK-SNARKs (Noir) | Output content + client identity | **Phase 3** |
| Multi-party synthesis | NMC | Raw miner outputs during aggregation | **Phase 4** |

### Recommended Implementation Order

```
Phase 1: Constitutional hash anchoring on Bittensor chain
    ↓
Phase 2: Decision audit logs on Arweave with merkle root anchoring
    ↓
Phase 3: ZKP for individual decision compliance proofs (Noir)
    ↓
Phase 4: NMC for multi-party synthesis (deferred)
```

### Competitive Differentiator

This layered approach enables: **"Provably compliant without revealing what you're
complying about."** No existing AI governance product offers this. The combination of
constitutional governance + blockchain immutability + zero-knowledge privacy is novel and
directly addresses enterprise adoption blockers in regulated industries.

---

## 4. Constitutional Hash Scope

### What the Hash Is

The constitutional hash (`608508a9bd224290`) is a SHA-256 fingerprint of the current
rule set, computed from:

```
{rule.id}:{rule.text}:{rule.severity}:{rule.hardcoded}:{rule.keywords}
```

Any rule change produces a new hash.

### Three Functions of the Hash

| Function | Description |
|----------|------------|
| **Version identifier** | Uniquely identifies which constitution is in effect |
| **On-chain anchor** | Publishing to Bittensor's chain creates a timestamped, public record of which constitution governed decisions in a given block range |
| **Auditability proof** | An auditor can re-hash the constitution document and compare it to the on-chain record — no central authority needed |

### What Is and Isn't on the Public Ledger

| On the public ledger | NOT on the public ledger (by default) |
|---------------------|--------------------------------------|
| Constitutional hash per version | Individual governance decisions |
| Block range each version was active | Content of miner outputs |
| Version change history | Client-specific decision data |
| | Deliberation reasoning text |

Individual governance decisions and miner output content can be anchored selectively
using ZKP proofs (see §3-B above) — proving compliance without revealing content.

### Current State vs. Target

| Capability | Current | Target (on Bittensor) |
|-----------|---------|----------------------|
| Rule-set hash | ✅ Exists (`608508a9bd224290`) | Anchor to chain per version |
| Per-decision hash | ❌ Does not exist | Extend hash to cover individual decisions |
| On-chain anchoring | ❌ Local only | Bittensor extrinsic per version change |
| Public verifiability | ❌ Local audit entries | Any party can verify via chain lookup |
| Version history | ❌ Implicit in codebase | Explicit on-chain timeline |

---

## 5. Multi-Perspective Synthesis Engine (Zero-Retraining Architecture)

### Design Constraint: No Model Retraining

The synthesis engine must improve governance accuracy **without retraining any ML model**.
Retraining introduces GPU dependency, opacity, catastrophic forgetting risk, and training
instability — all of which contradict the subnet's design principles:

- Miners are humans providing judgment, not GPUs running training jobs
- Every governance decision must be explainable and auditable
- The system must be deterministic and reproducible for compliance purposes
- No single training run should be able to silently shift governance behavior

**The system learns by accumulating structured precedent, not by updating model weights.**

### Architecture: Precedent-Based Governance

```
Miner output → automated 7-vector score → ambiguous (3%) → human miner decision
                                                                    ↓
                                              structured precedent record stored
                                                (miner decision + validator grade
                                                 + SN owner criteria + reasoning)
                                                                    ↓
                                              precedent index updated (retrieval, not training)
                                                                    ↓
                                              future ambiguous cases retrieve similar precedent
                                              → auto-resolve if match confidence is high enough
```

No fine-tuning. No gradient descent. No model weights changed. The system gets smarter
by remembering what humans decided in similar situations and applying those decisions to
future cases.

### Three Mechanisms (All Zero-Retraining)

#### Mechanism 1: Precedent Retrieval (Case Law Database)

Each resolved escalation becomes a **precedent record** stored in an indexed database:

```
PrecedentRecord:
  case_id:            "ESC-2026-04-0271"
  constitutional_hash: "608508a9bd224290"
  input_vector:        [0.42, 0.71, 0.38, 0.65, 0.22, 0.55, 0.18]  # 7-vector scores
  ambiguous_vectors:   ["security", "fairness"]                      # which vectors conflicted
  miner_decision:      "allow_with_conditions"
  miner_reasoning:     "Security risk is mitigated by existing rate limiting..."
  validator_grade:     0.91
  sn_owner_criteria:   {"security_weight": 0.20, "fairness_weight": 0.15}
  outcome_category:    "constitutional_conflict"
  resolution_date:     "2026-04-15T14:32:00Z"
```

When a new ambiguous case arrives, the system retrieves the **k most similar precedent
records** by 7-vector cosine similarity. If precedent match confidence exceeds a
threshold (e.g., 0.85), the system auto-resolves using the precedent — no miner needed.

This is **retrieval, not retraining**. The embedding model that computes similarity is
frozen. Only the precedent database grows.

#### Mechanism 2: Threshold Adjustment (Bayesian Weight Updating)

The 7-vector scoring weights and escalation thresholds are adjusted using simple
Bayesian updating — not neural network training:

```
Prior:    security_weight = 0.20 (from constitution definition)
Evidence: 47 escalated healthcare cases where security was the ambiguous vector
          → 41 resolved as "security concern was valid" (87%)
          → 6 resolved as "security concern was overblown" (13%)

Posterior: security_weight for healthcare domain = 0.23 (+0.03)
```

This is a **statistical update to a lookup table**, not model retraining. The update is:
- Deterministic — same inputs always produce same output
- Reversible — any weight change can be rolled back to its prior
- Transparent — "security weight increased because 87% of healthcare escalations
  confirmed the security concern was valid"
- Bounded — weights cannot shift more than ±X% per update cycle

#### Mechanism 3: Constitutional Rule Codification

When a precedent pattern reaches sufficient consensus (e.g., 50+ similar cases with
90%+ validator agreement), it is **codified as a new constitutional rule** — not learned
implicitly by a model:

```yaml
# Auto-generated rule from precedent cluster ESC-HEALTH-SEC-*
- id: HEALTH-SEC-047
  text: "Healthcare data access requests with both security and fairness
         vectors above 0.60 require explicit consent verification"
  severity: high
  source: precedent_codification
  precedent_cluster: ESC-HEALTH-SEC
  case_count: 53
  validator_agreement: 0.94
  effective_date: 2026-06-01
  constitutional_hash: <new hash after rule addition>
```

This is **rule writing, not model training**. The new rule is:
- Explicit — written in plain language, auditable
- Versioned — produces a new constitutional hash
- Governed — requires Governor (SN Owner) approval before activation
- Reversible — can be revoked if it produces bad outcomes

### Why "Multi-Perspective" Is Critical

Each precedent record must include **all three party perspectives**:

| Party | What They Contribute | Why It Matters |
|-------|---------------------|---------------|
| **Validator** | Quality grade + constitutional compliance score | Objective quality signal |
| **SN Owner** | Criteria weights + rubric definition | What "good" means in context |
| **Miner** | Decision + written rationale | Human judgment and reasoning |

A single-perspective precedent (e.g., just the miner's decision) would bias future
retrievals toward one viewpoint. With all three labels, the retrieval engine can match
on cases where validator consensus and SN owner criteria diverge — which is exactly the
hard 3% case where simple scoring fails.

### How the 3% Shrinks Over Time (Without Retraining)

```
Month 1:  3.0% escalation rate  |  0 precedent records
Month 3:  2.7% escalation rate  |  ~500 precedent records → some auto-resolve via retrieval
Month 6:  2.1% escalation rate  |  ~2,000 records + 12 codified rules
Month 12: 1.4% escalation rate  |  ~8,000 records + 40 codified rules
Month 24: 0.8% escalation rate  |  ~25,000 records + 100+ codified rules
```

The system doesn't retrain — it **remembers and codifies**. The automated 97% grows
toward 99%+ as precedent accumulates, but the remaining cases are genuinely novel (no
similar precedent exists) and still require human judgment.

### What Exists Today

| Component | File | Status |
|-----------|------|--------|
| Polis engine | `governance/polis_engine.py` | ✅ Exists — Polis-style consensus/voting |
| Democratic governance | `governance/democratic_governance.py` | ✅ Exists — wraps Polis with amendment workflows |
| Spec-to-Artifact score | `deliberation_layer/impact_scorer.py` | ✅ Exists — tracks override rate |
| DTMC trajectory scorer | `adaptive_governance/dtmc_learner.py` | ✅ Exists — behavioral pattern detection |
| Precedent record storage | — | ❌ Needs to be built |
| Precedent retrieval index | — | ❌ Needs to be built |
| Bayesian threshold updater | — | ❌ Needs to be built |
| Rule codification pipeline | — | ❌ Needs to be built |
| Multi-party label schema | — | ❌ Needs to be built |

### Safeguards

| Safeguard | Mechanism |
|-----------|-----------|
| **Quorum requirement** | A single miner judgment never becomes precedent alone |
| **Validator consensus** | Precedent retrieval requires validator agreement ≥ threshold |
| **Constitutional compatibility** | Codified rules cannot contradict hard-coded constitutional rules |
| **Rollback capability** | Any precedent or codified rule can be reverted by Governor |
| **Weight drift bounds** | Bayesian weight updates capped at ±X% per cycle |
| **Transparency** | Every precedent match and weight change is logged with source cases |
| **Frozen embeddings** | Similarity model is never retrained — only the index grows |
| **Governor approval gate** | Rule codification requires SN Owner sign-off before activation |

### Compounding Value (Without Retraining)

- **Early miners** set foundational precedent → their work has outsized long-term value
- **Escalation rate decreases** as precedent accumulates → system handles more automatically
- **Codified rules** make the constitution richer and more nuanced over time
- **Precedent corpus** becomes a data product → Revenue Stream 3 (Governance Intelligence)
- **All of this is auditable** — every improvement traces to specific human decisions,
  not opaque model weight changes

---

## 6. MACI Role Model: Mapping to Bittensor Parties

### The 7-Role Decomposition for the Subnet

The current ACGS codebase has two MACI models: a 3-role model (Proposer, Validator,
Executor) in `acgs-lite` and a 7-role model (Executive, Legislative, Judicial, Monitor,
Auditor, Controller, Implementer) in `enhanced_agent_bus`. For the subnet, the 7 roles
are reframed to map directly onto Bittensor's three parties:

| MACI Role | Bittensor Party | Responsibility |
|-----------|----------------|----------------|
| **Proposer** | Miner | Submits work output for evaluation |
| **Quality Validator** | Validator | Scores output quality against SN owner's rubric |
| **Constitutional Validator** | Validator | Independently checks governance rule compliance (separate from quality) |
| **Governor** | SN Owner | Defines the rubric, weights, and constitutional rules |
| **Executor** | SN Owner | Triggers reward emission based on validated scores |
| **Auditor** | Validator | Spot-checks historical decisions for drift or gaming |
| **Human Reviewer** | Miner (escalation pool) | Resolves the 3% ambiguous cases |

### Critical Separations

#### Quality Validator ≠ Constitutional Validator

These must be **different validators** (or the same validator running independent
pipelines with no shared state). This is the ACGS core invariant: **agents never validate
their own output.**

- The Quality Validator asks: "Is this output good work?"
- The Constitutional Validator asks: "Does this output comply with governance rules?"

These are independent questions. A high-quality output could still violate constitutional
rules. A constitutionally compliant output could still be low-quality work. Separating
them prevents a single validation pipeline from having unchecked authority.

#### Governor ≠ Executor

The SN Owner role is deliberately split:

- The **Governor** defines rules — what the constitution says, what the rubric weights
  are, what the scoring criteria mean.
- The **Executor** triggers emissions — but only after independent validation confirms
  compliance.

The Executor is **gated, not autonomous**. It cannot distribute rewards without both
Quality Validator and Constitutional Validator approval. This prevents the SN Owner from
unilaterally rewarding favored miners.

#### Human Reviewer = Specialized Miner Pool

Human Reviewer miners form a **dedicated pool** — higher-stake participants who opt in to
escalation duties in exchange for additional emissions on resolved cases. This creates a
tiered miner structure:

| Miner Tier | Work Type | Emission Source |
|-----------|-----------|----------------|
| **Standard miners** | Submit regular work outputs | Standard emission based on quality scores |
| **Human Reviewer miners** | Resolve the 3% ambiguous cases | Additional emission per resolved escalation |

Human Reviewers could be selected based on:
- Stake level (higher stake = more skin in the game)
- Historical resolution quality (validator grades on past escalation work)
- Domain expertise (if the subnet implements topic-based routing)

### How It Maps to the Existing Codebase

| Subnet Role | acgs-lite Role | enhanced_agent_bus Role |
|-------------|---------------|------------------------|
| Proposer | `MACIRole.PROPOSER` | `MACIRole.EXECUTIVE` (scoped to submission) |
| Quality Validator | `MACIRole.VALIDATOR` | `MACIRole.JUDICIAL` |
| Constitutional Validator | `MACIRole.VALIDATOR` | `MACIRole.AUDITOR` |
| Governor | — (SN Owner, external) | `MACIRole.LEGISLATIVE` + `MACIRole.CONTROLLER` |
| Executor | `MACIRole.EXECUTOR` | `MACIRole.EXECUTIVE` (scoped to emission) |
| Auditor | `MACIRole.VALIDATOR` (audit subset) | `MACIRole.MONITOR` |
| Human Reviewer | `MACIRole.EXECUTOR` (deliberation) | `MACIRole.IMPLEMENTER` |

### Domain Scoping (Already Supported)

The codebase includes `DomainScopedRole` and `DomainRoleRegistry` classes that support
partitioning roles by governance domain:

| Domain Scope | Active Roles | Purpose |
|-------------|-------------|---------|
| `subnet-governance` | Governor, Constitutional Validator | Rule definition and compliance |
| `output-quality` | Quality Validator, Proposer | Work quality assessment |
| `emission-control` | Executor, Auditor | Reward distribution and oversight |
| `escalation` | Human Reviewer, Constitutional Validator | 3% ambiguous case resolution |

Cross-domain isolation prevents lateral movement: a Quality Validator cannot influence
constitutional compliance checks, and a Governor cannot bypass the Executor gate.

### The Golden Rule in Practice

```
Miner (Proposer) submits work
    → Quality Validator scores quality (cannot also check compliance)
    → Constitutional Validator checks compliance (cannot also score quality)
    → Both pass? → Executor triggers emission (cannot validate)
    → Ambiguous? → Human Reviewer resolves (cannot also validate the resolution)
    → Auditor spot-checks historical decisions (independent of all above)
```

No single party controls more than one step. No agent validates its own output.

---

## 7. constitutional_swarm: Existing Primitives for Subnet Implementation

The `constitutional_swarm` package (`packages/constitutional_swarm/`) already implements core
primitives that map directly to the Bittensor subnet architecture. See
`08-subnet-implementation-roadmap.md` for the full 5-phase build plan.

### Component Mapping

| constitutional_swarm | Subnet Role | Ready? |
|---------------------|-------------|--------|
| `AgentDNA` (443ns local validator) | Miner constitutional pre-check | ✅ Ready |
| `ConstitutionalMesh` (peer validation + Merkle proofs) | Validator grading mechanism | ✅ Ready |
| `GovernanceManifold` (Sinkhorn-Knopp trust projection) | TAO emission weight calculation | ✅ Ready |
| `SwarmExecutor` + `ArtifactStore` | Miner task self-selection | ✅ Ready |
| `CapabilityRegistry` (O(1) routing) | Miner qualification tiers | ✅ Ready |
| `DAGCompiler` + `GoalSpec` | SN Owner task packaging | ✅ Ready |
| `MeshProof` (cryptographic Merkle chain) | On-chain proof anchoring | ✅ Ready for bridge |
| `bittensor/synapses.py` (protocol types) | Miner/validator message format | ✅ Scaffolded |
| `bittensor/protocol.py` (EscalationType enum) | Failure mode data collection | ✅ Scaffolded |

### How Each Question Is Addressed

| Question | constitutional_swarm Answer |
|----------|---------------------------|
| 1. 7-vector scoring | `AgentDNA.validate()` embeds scoring at agent level; mesh peers re-validate |
| 2. Failure mode % | `EscalationType` enum + `SubnetMetrics.escalation_distribution()` generates data |
| 3. Blockchain + ZKP | `MeshProof` Merkle chain ready for on-chain anchoring; ZKP/NMC in Phase 2 |
| 4. Constitutional hash | `AgentDNA.hash` + `MeshProof.constitutional_hash` verifiable at every layer |
| 5. Learning from data | `ArtifactStore` captures judgments; precedent loop → `DTMCLearner` (Phase 3) |
| 6. MACI role mapping | `AgentDNA(maci_role=EXECUTOR)` for miners; mesh excludes producers (MACI) |

### Mathematical Guarantees (GovernanceManifold)

Three proven properties (see `packages/constitutional_swarm/paper/constitutional_swarm_paper.md`):

1. **Bounded Influence** (Theorem 1): spectral norm ≤ 1 — no miner monopolizes TAO emissions
2. **Compositional Closure** (Theorem 2): multi-round validation remains stable
3. **Conservation** (Theorem 3): trust/TAO neither created nor destroyed

---

## Summary of Action Items

| # | Topic | Status | Next Step |
|---|-------|--------|-----------|
| 1 | 7-vector subnet scoring | 🔧 Extend `compute_opportunity_score()` to 7 inputs | Add V4-V7 vectors, implement V4 hard gate |
| 1b | 7-vector per-decision scoring | ✅ Fully implemented in ACGS-2 | Document for miners |
| 2 | Failure mode tracking | ✅ `EscalationType` enum scaffolded | Subnet generates empirical distribution |
| 3a | Constitutional hash anchoring | ⚠️ `MeshProof` ready | Chain bridge via `ChainAnchor` (Phase 2) |
| 3b | Audit log storage | ❌ Not implemented | Merkle root batch anchoring (Phase 2) |
| 3c | ZKP decision proofs | ❌ Not implemented | Privacy-preserving compliance certificates (Phase 2) |
| 3d | NMC for synthesis | ❌ Not implemented | Anti-collusion multi-miner deliberation (Phase 2) |
| 4 | Constitutional hash scope | ⚠️ Rule-set only | Per-decision hashes + on-chain anchoring |
| 5 | Multi-perspective synthesis (zero-retraining) | ⚠️ Polis engine exists, precedent system does not | Build precedent store + retrieval index + Bayesian thresholds + rule codification pipeline |
| 6 | MACI role mapping | ✅ Mapped | 7-role → 3-party in `08-subnet-implementation-roadmap.md` |
| 7 | constitutional_swarm | ✅ Primitives ready | Protocol bridge (Phase 1) |

---

## Codebase Reference Index

| Topic | Primary File(s) |
|-------|----------------|
| **constitutional_swarm** | |
| Agent DNA | `packages/constitutional_swarm/src/constitutional_swarm/dna.py` |
| Constitutional mesh | `packages/constitutional_swarm/src/constitutional_swarm/mesh.py` |
| Governance manifold | `packages/constitutional_swarm/src/constitutional_swarm/manifold.py` |
| Swarm executor | `packages/constitutional_swarm/src/constitutional_swarm/swarm.py` |
| DAG compiler | `packages/constitutional_swarm/src/constitutional_swarm/compiler.py` |
| Capability registry | `packages/constitutional_swarm/src/constitutional_swarm/capability.py` |
| Artifact store | `packages/constitutional_swarm/src/constitutional_swarm/artifact.py` |
| Bittensor synapses | `packages/constitutional_swarm/src/constitutional_swarm/bittensor/synapses.py` |
| Bittensor protocol | `packages/constitutional_swarm/src/constitutional_swarm/bittensor/protocol.py` |
| Research paper | `packages/constitutional_swarm/paper/constitutional_swarm_paper.md` |
| Implementation roadmap | `docs/strategy/08-subnet-implementation-roadmap.md` |
| **ACGS-2 core** | |
| 7-vector model | `packages/enhanced_agent_bus/impact_scorer_infra/models.py` |
| MiniCPM semantic scorer | `packages/enhanced_agent_bus/impact_scorer_infra/algorithms/minicpm_semantic.py` |
| Impact scorer facade | `packages/enhanced_agent_bus/deliberation_layer/impact_scorer.py` |
| Governance constants | `packages/enhanced_agent_bus/governance_constants.py` |
| Adaptive router | `packages/enhanced_agent_bus/deliberation_layer/adaptive_router.py` |
| MACI 3-role model | `packages/acgs-lite/src/acgs_lite/maci.py` |
| MACI 7-role model | `packages/enhanced_agent_bus/maci/models.py` |
| MACI enforcer (7-role) | `packages/enhanced_agent_bus/maci/enforcer.py` |
| Domain-scoped roles | `packages/acgs-lite/src/acgs_lite/maci.py` → `DomainScopedRole` |
| Polis deliberation | `packages/enhanced_agent_bus/governance/polis_engine.py` |
| Democratic governance | `packages/enhanced_agent_bus/governance/democratic_governance.py` |
| DTMC trajectory learner | `packages/enhanced_agent_bus/adaptive_governance/dtmc_learner.py` |
| Audit log | `packages/acgs-lite/src/acgs_lite/audit.py` |
| Compliance frameworks | `packages/acgs-lite/src/acgs_lite/compliance/` |
| Constitutional hash | `src/core/shared/constants.py` |
| **Strategy docs** | |
| Subnet concept | `docs/strategy/06-subnet-concept.md` |
| Technical accuracy | `docs/strategy/06-subnet-concept-technical-notes.md` |
| Q&A responses | `docs/strategy/07-subnet-concept-qa-responses.md` (this file) |
| Implementation roadmap | `docs/strategy/08-subnet-implementation-roadmap.md` |
