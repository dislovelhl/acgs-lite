# Subnet Implementation Roadmap

## constitutional_swarm as Bittensor Subnet Runtime

This document maps existing `constitutional_swarm` primitives to the Bittensor subnet
architecture and defines the implementation phases needed to go from prototype to live subnet.

*March 2026. Cross-references `06-subnet-concept.md`, `07-subnet-concept-qa-responses.md`,
and `packages/constitutional_swarm/`.*

---

## Existing Primitives → Bittensor Mapping

### Component-Level Mapping

| constitutional_swarm Module | Bittensor Role | How It Maps |
|-----------------------------|---------------|-------------|
| `AgentDNA` | Miner local validator | Every miner embeds constitutional DNA; validates own output before submission (443ns) |
| `SwarmExecutor` + `ArtifactStore` | Task distribution | Miners self-select escalated cases by capability; no central assignment bottleneck |
| `DAGCompiler` + `GoalSpec` | SN Owner task packaging | Escalated governance cases compiled into structured task DAGs |
| `ConstitutionalMesh` | Validator grading | Peer validation with MACI exclusion, quorum voting, Merkle proofs |
| `MeshProof` | On-chain attestation | Cryptographic proof chain ready for Bittensor chain anchoring |
| `GovernanceManifold` | TAO emission weighting | Sinkhorn-Knopp projected trust → emission distribution weights |
| `CapabilityRegistry` | Miner qualification tiers | Domain-scoped capabilities route complex cases to qualified miners |
| `Artifact` (content-addressed) | Decision record | SHA-256 integrity verification, constitutional hash attached |

### MACI Role Mapping (3-Role × 7-Role × Bittensor)

```
Bittensor Party    3-Role MACI    7-Role MACI (internal)    constitutional_swarm
─────────────────────────────────────────────────────────────────────────────────
SN Owner           Proposer       Executive + Legislative    DAGCompiler + GoalSpec
                                  + Controller               CapabilityRegistry config

Miner              Executor       Implementer + Executive    AgentDNA (EXECUTOR role)
                                  (scoped)                   SwarmExecutor.claim() + submit()

Validator          Validator      Judicial + Auditor         ConstitutionalMesh.validate_and_vote()
                                  + Monitor                  GovernanceManifold trust updates
```

Golden rule preserved at every layer:
- `ConstitutionalMesh.request_validation()` excludes producer from peers (line 312)
- `SwarmExecutor.submit()` verifies submitter == claimant (line 269)
- `AgentDNA` enforces MACI role via embedded `MACIEnforcer` (line 82-83)

---

## Phase 1: Protocol Bridge (Weeks 1-4)

### Goal: Connect constitutional_swarm to Bittensor's miner/validator protocol

#### 1.1 Bittensor Synapse Adapters

Create synapse types for the three message flows:

```python
# packages/constitutional_swarm/src/constitutional_swarm/bittensor/synapses.py

class DeliberationSynapse(bt.Synapse):
    """SN Owner → Miner: escalated governance case."""
    task_dag: str          # Serialized TaskDAG
    constitution_hash: str # Must match miner's AgentDNA.hash
    deadline_seconds: int
    domain: str
    required_capabilities: list[str]

class JudgmentSynapse(bt.Synapse):
    """Miner → Validator: deliberation result."""
    task_id: str
    judgment: str          # Miner's governance decision
    reasoning: str         # Written justification
    artifact_hash: str     # SHA-256 of the Artifact
    dna_validation: dict   # DNAValidationResult from local pre-check
    constitutional_hash: str

class ValidationSynapse(bt.Synapse):
    """Validator → SN Owner: grading result with proof."""
    assignment_id: str
    mesh_result: dict      # Serialized MeshResult
    mesh_proof: dict       # Serialized MeshProof (Merkle chain)
    trust_update: dict     # GovernanceManifold delta
```

#### 1.2 Miner Runtime

```python
# packages/constitutional_swarm/src/constitutional_swarm/bittensor/miner.py

class ConstitutionalMiner:
    def __init__(self, constitution_path: str, capabilities: list[str]):
        self.dna = AgentDNA.from_yaml(constitution_path, maci_role=MACIRole.EXECUTOR)
        self.registry = CapabilityRegistry()
        self.registry.register(self.uid, [
            Capability(name=cap, domain=cap) for cap in capabilities
        ])

    async def forward(self, synapse: DeliberationSynapse) -> JudgmentSynapse:
        # 1. Verify constitution hash matches
        assert synapse.constitution_hash == self.dna.hash

        # 2. Deserialize task DAG
        dag = TaskDAG.from_dict(synapse.task_dag)

        # 3. Check capability match
        executor = SwarmExecutor(self.registry, ArtifactStore())
        executor.load_dag(dag)
        tasks = executor.available_tasks(self.uid)

        # 4. Execute deliberation (human-in-the-loop or AI-assisted)
        judgment, reasoning = await self.deliberate(tasks[0])

        # 5. DNA pre-validation (443ns)
        result = self.dna.validate(judgment)

        # 6. Package and return
        artifact = Artifact(
            artifact_id=uuid.uuid4().hex[:12],
            task_id=tasks[0].node_id,
            agent_id=self.uid,
            content_type="governance_judgment",
            content=judgment,
            constitutional_hash=self.dna.hash,
        )
        return JudgmentSynapse(
            task_id=tasks[0].node_id,
            judgment=judgment,
            reasoning=reasoning,
            artifact_hash=artifact.content_hash,
            dna_validation=asdict(result),
            constitutional_hash=self.dna.hash,
        )
```

#### 1.3 Validator Runtime

```python
# packages/constitutional_swarm/src/constitutional_swarm/bittensor/validator.py

class ConstitutionalValidator:
    def __init__(self, constitution_path: str, num_validators: int = 3):
        constitution = Constitution.from_yaml(constitution_path)
        self.mesh = ConstitutionalMesh(
            constitution,
            peers_per_validation=num_validators,
            quorum=num_validators // 2 + 1,
            use_manifold=True,
        )

    async def forward(self, synapse: JudgmentSynapse) -> ValidationSynapse:
        # 1. Register miner as mesh participant
        self.mesh.register_agent(synapse.miner_uid, domain=synapse.domain)

        # 2. Full mesh validation (DNA check + peer votes + Merkle proof)
        result = self.mesh.full_validation(
            producer_id=synapse.miner_uid,
            content=synapse.judgment,
            artifact_id=synapse.artifact_hash,
        )

        # 3. Return grading with cryptographic proof
        return ValidationSynapse(
            assignment_id=result.assignment_id,
            mesh_result=asdict(result),
            mesh_proof=asdict(result.proof) if result.proof else {},
            trust_update=self.mesh.manifold_summary() or {},
        )

    def set_weights(self) -> dict[int, float]:
        """Convert manifold trust matrix to TAO emission weights."""
        matrix = self.mesh.trust_matrix
        if matrix is None:
            return {}
        # Each miner's weight = their column sum in the trust matrix
        # (how much trust they receive from all validators)
        n = len(matrix)
        weights = {}
        for j in range(n):
            weights[j] = sum(matrix[i][j] for i in range(n))
        return weights
```

#### 1.4 Deliverables

| Deliverable | File | Status |
|------------|------|--------|
| Synapse definitions | `bittensor/synapses.py` | ✅ Complete |
| Miner runtime | `bittensor/miner.py` | ✅ Complete |
| Validator runtime | `bittensor/validator.py` | ✅ Complete |
| SN Owner orchestrator | `bittensor/subnet_owner.py` | ✅ Complete |
| Constitution distribution | `bittensor/constitution_sync.py` | ✅ Complete |
| Governance Coordinator | `bittensor/governance_coordinator.py` | ✅ Complete |
| Integration tests | `tests/test_bittensor_e2e.py` | ✅ Complete |
| Full-stack integration | `tests/test_full_stack_integration.py` | ✅ Complete |

---

## Phase 2: On-Chain Anchoring + Privacy (Weeks 5-8)

### Goal: Anchor governance proofs to Bittensor chain with privacy preservation

#### 2.1 Merkle Proof Anchoring

`MeshProof` already produces cryptographic proofs (content_hash + vote_hashes + root_hash).
Extend to batch-anchor on Bittensor:

```python
class ChainAnchor:
    """Batch-anchor MeshProofs to Bittensor chain."""

    def __init__(self, batch_size: int = 100):
        self.pending_proofs: list[MeshProof] = []
        self.batch_size = batch_size

    def add_proof(self, proof: MeshProof) -> None:
        self.pending_proofs.append(proof)
        if len(self.pending_proofs) >= self.batch_size:
            self.flush()

    def flush(self) -> str:
        """Compute batch Merkle root and submit to chain."""
        proof_hashes = [p.root_hash for p in self.pending_proofs]
        batch_root = compute_batch_merkle_root(proof_hashes)
        # Submit batch_root to Bittensor chain via extrinsic
        # Store mapping: batch_root → individual proof hashes
        self.pending_proofs = []
        return batch_root
```

#### 2.2 ZKP Compliance Certificates

Privacy-preserving compliance attestation:

```
Enterprise AI System
    │
    │ "Prove we passed EU AI Act Art. 14 checks"
    │
    ▼
ZKP Certificate Generator
    │
    │ Inputs: constitutional_hash, pass/fail counts, time range
    │ Output: ZKP proof that compliance_rate >= threshold
    │ Reveals: NOTHING about actual decisions or data
    │
    ▼
On-Chain ZKP Certificate
    │
    │ Anyone can verify: "This enterprise was ≥99.7% compliant in Q1"
    │ Nobody can see: What decisions were made, what data was processed
    │
    ▼
Regulator / Auditor
```

#### 2.3 NMC for Multi-Miner Deliberation

When multiple miners contribute to a single governance case:

```
Miner A ─┐
Miner B ──┤── NMC Protocol ──→ Consensus Judgment
Miner C ─┘
          │
          │ No miner sees other miners' reasoning
          │ Validators verify collective quality
          │ Prevents gaming / Sybil copying
```

#### 2.4 Selective On-Chain / Off-Chain Split

| On-Chain (Small, Immutable) | Off-Chain (Large, Private) |
|-----------------------------|---------------------------|
| Constitutional hash per version | Full audit log entries |
| `MeshProof.root_hash` per batch | Deliberation reasoning text |
| ZKP compliance certificates | Message embeddings |
| Miner judgment attestation proofs | Client-specific decision data |
| `GovernanceManifold` snapshots | Raw 7-vector scoring data |

---

## Phase 3: Precedent Feedback Loop (Weeks 9-12)

### Goal: Miner judgments improve automated governance over time

#### 3.1 Precedent Capture

```python
class PrecedentStore:
    """Store validated miner judgments as constitutional precedent."""

    def record_precedent(
        self,
        judgment: Artifact,
        mesh_result: MeshResult,
        escalation_type: EscalationType,
    ) -> Precedent:
        """Record a precedent only if:
        1. MeshResult.accepted == True (quorum approved)
        2. MeshResult.votes_for >= quorum_for_precedent (higher bar)
        3. Constitutional compatibility verified via DNA
        """
        ...
```

#### 3.2 Feedback Integration with DTMCLearner

```
Miner judgment (validated) ──→ PrecedentStore
    │
    ├── Pattern extraction (which reasoning correlates with approval)
    ├── Threshold adjustment (update 7-vector scoring weights)
    ├── DTMCLearner training (incorporate into trajectory model)
    └── Constitutional evolution (codify as new rule when consensus sufficient)
```

#### 3.3 Safeguards

| Safeguard | Mechanism |
|-----------|-----------|
| Quorum requirement | Single miner judgment never becomes precedent alone |
| Validator consensus | Precedent requires ≥ 2/3 validator agreement on quality |
| Constitutional compatibility | `AgentDNA.validate()` checks precedent doesn't contradict hard-coded rules |
| Rollback capability | Precedent can be reverted if harmful effects detected |
| Confidence gating | Only incorporate precedent above confidence threshold |

---

## Phase 4: Authenticity Detection + Anti-Gaming (Weeks 13-16)

### Goal: Ensure miner responses reflect genuine human reasoning

#### 4.1 Deliberative Authenticity Scoring

Validators assess five quality dimensions:

| Dimension | Weight | What It Detects |
|-----------|--------|-----------------|
| Reasoning depth | 25% | Superficial vs. substantive analysis |
| Stakeholder coverage | 20% | Does the judgment consider all affected parties? |
| Constitutional consistency | 20% | Alignment with the broader constitutional framework |
| Deliberative authenticity | 20% | Human reasoning vs. AI-generated response |
| Precedent compatibility | 15% | Consistency with established precedent corpus |

#### 4.2 Anti-Gaming via GovernanceManifold

The manifold provides mathematical anti-gaming guarantees:

- **Trust explosion prevention**: Spectral norm ≤ 1 — no miner accumulates disproportionate influence
- **Conservation**: Total trust is constant — gaming one miner up means another goes down
- **Compositional stability**: Gaming across multiple rounds doesn't compound

Combined with NMC (miners can't see each other's reasoning), the system is resistant to:
- Sybil attacks (multiple fake miners copying same answer)
- Collusion (miners coordinating responses)
- Quality degradation (free-riding on others' work)

---

## Phase 5: Miner Qualification Tiers (Weeks 17-20)

### Goal: Route complex cases to qualified miners

#### 5.1 Tier Structure

| Tier | Qualification | Task Complexity | TAO Multiplier |
|------|--------------|-----------------|----------------|
| **Apprentice** | New miner, < 10 validated judgments | LOW complexity only | 1.0x |
| **Journeyman** | ≥ 10 validated, reputation ≥ 1.2 | LOW + MEDIUM | 1.5x |
| **Master** | ≥ 50 validated, reputation ≥ 1.5, domain specialist | All tiers | 2.5x |
| **Elder** | ≥ 200 validated, precedent-setting judgments | Constitutional amendments | 4.0x |

#### 5.2 Implementation via CapabilityRegistry

```python
# Miner registers with tier-appropriate capabilities
registry.register("miner-01", [
    Capability(name="governance-judgment", domain="finance",
               tags=("tier:master", "specialization:regulatory")),
])

# SN Owner compiles task with tier requirement
spec = GoalSpec(
    goal="Resolve privacy vs. transparency conflict in financial reporting",
    domains=["finance", "privacy"],
    steps=[{
        "title": "Analyze constitutional conflict",
        "domain": "finance",
        "required_capabilities": ["tier:master", "finance"],
    }],
)
```

---

## Economic Model Integration

### TAO Emission Formula

```
emission_weight(miner_i) = f(
    manifold_trust[i],          # GovernanceManifold projected column sum
    reputation[i],              # ConstitutionalMesh reputation score
    tier_multiplier[i],         # Qualification tier bonus
    precedent_contribution[i],  # Number of precedent-setting judgments
    authenticity_score[i],      # Average deliberative authenticity rating
)
```

### Revenue Streams Enabled

| Stream | constitutional_swarm Component | Status |
|--------|-------------------------------|--------|
| 1. AI-Compliant Compute | `AgentDNA` + `AdaptiveRouter` | Ready (Phase 1) |
| 2. Governance Certification | `MeshProof` + ZKP certificates | Phase 2 |
| 3. Governance Intelligence | `PrecedentStore` + anonymized corpus | Phase 3 |

---

## Phase 6: TurboQuant KV Cache Compression (Cross-Cutting)

### Background

Google's TurboQuant (ICLR 2026, arXiv:2504.19874) compresses LLM KV caches to 3-4 bits
with zero accuracy loss: 6x memory reduction, 8x attention speedup on H100. Training-free,
architecture-agnostic, two-stage pipeline: PolarQuant (random rotation + polar coordinate
quantization) + QJL (1-bit Johnson-Lindenstrauss residual correction).

### Integration Points in ACGS

| Component | How TurboQuant Helps | Impact |
|-----------|---------------------|--------|
| **MiniCPM Semantic Scorer** | Compress domain reference embeddings (42 vectors × 7 domains) and message embeddings in the KV cache | 6x less VRAM for semantic scoring, more nodes can run it |
| **Miner LLM Inference** | Miners using AI-assisted deliberation get 6x longer context on same hardware | Lower miner participation barrier, better judgments on complex cases |
| **Validator Attention** | Mesh peers validating long governance cases can hold 6x more context | More thorough validation without hardware upgrades |
| **GovernanceKVCache** | Domain-aware compressed embedding cache with constitutional hash tagging, LRU eviction, fidelity monitoring | Production-ready caching layer for 7-vector scoring |

### Implementation Status

| Component | Status | File |
|-----------|--------|------|
| Pure Python reference compressor | ✅ Implemented | `enhanced_agent_bus/impact_scorer_infra/turboquant_cache.py` |
| Lloyd-Max optimal codebooks (2/3/4 bit) | ✅ Implemented | Same file |
| PolarQuant random rotation | ✅ Implemented | Same file (Gram-Schmidt QR) |
| QJL residual projection | ✅ Implemented (encode side) | Same file |
| GovernanceKVCache | ✅ Implemented | Same file |
| Fidelity monitoring | ✅ Implemented | Cosine sim + Spearman rank checks |
| Triton kernel acceleration | ⚠️ Optional, via `pip install turboquant` | Falls back to pure Python |
| vLLM integration | ❌ Not yet | Depends on vllm-project/vllm#38280 landing |

### Performance (Pure Python Baseline vs Triton Target)

| Metric | Pure Python (current) | Triton (target via `turboquant` pkg) |
|--------|----------------------|--------------------------------------|
| 4-bit cosine fidelity | >0.93 | >0.99 (paper benchmark) |
| 3-bit cosine fidelity | >0.65 | >0.95 (paper benchmark) |
| Compression ratio (4-bit) | ~4x | ~4x |
| Compression ratio (3-bit) | ~5x | ~6x |
| Attention speedup | N/A (Python) | 8x on H100 |

### Integration with `pip install turboquant`

The `back2matching/turboquant` package provides a drop-in HuggingFace-compatible
KV cache compression. For ACGS integration:

```python
# Option A: Use our GovernanceKVCache with pure Python compressor
from enhanced_agent_bus.impact_scorer_infra.turboquant_cache import (
    GovernanceKVCache, TurboQuantConfig,
)
cache = GovernanceKVCache(TurboQuantConfig(bits=4))
cache.put("msg-embed", embedding, domain="security")

# Option B: Use turboquant package directly for LLM inference
# pip install turboquant
from turboquant import TurboQuantCache
kv_cache = TurboQuantCache(bits=4)
output = model.generate(input_ids, past_key_values=kv_cache)
```

---

## Implementation Priority

| Phase | Weeks | Dependencies | Enables |
|-------|-------|-------------|---------|
| 1. Protocol Bridge | 1-4 | None | Live subnet with basic miner/validator flow |
| 2. On-Chain + Privacy | 5-8 | Phase 1 | Revenue Stream 2 (certification) |
| 3. Precedent Loop | 9-12 | Phase 2 | Revenue Stream 3 (intelligence), decreasing escalation rate |
| 4. Authenticity | 13-16 | Phase 3 | Anti-gaming, Sybil resistance |
| 5. Qualification | 17-20 | Phase 4 | Complex case routing, TAO multipliers |
| 6. TurboQuant | Cross-cutting | None (pure Python ready) | 6x memory reduction, lower miner/validator hardware bar |

---

## Codebase Reference

| Topic | File |
|-------|------|
| **constitutional_swarm** | |
| Agent DNA | `packages/constitutional_swarm/src/constitutional_swarm/dna.py` |
| Swarm executor | `packages/constitutional_swarm/src/constitutional_swarm/swarm.py` |
| Constitutional mesh | `packages/constitutional_swarm/src/constitutional_swarm/mesh.py` |
| Governance manifold | `packages/constitutional_swarm/src/constitutional_swarm/manifold.py` |
| DAG compiler | `packages/constitutional_swarm/src/constitutional_swarm/compiler.py` |
| Capability registry | `packages/constitutional_swarm/src/constitutional_swarm/capability.py` |
| Artifact store | `packages/constitutional_swarm/src/constitutional_swarm/artifact.py` |
| Bittensor miner runtime | `packages/constitutional_swarm/src/constitutional_swarm/bittensor/miner.py` |
| Bittensor validator runtime | `packages/constitutional_swarm/src/constitutional_swarm/bittensor/validator.py` |
| Bittensor SN Owner | `packages/constitutional_swarm/src/constitutional_swarm/bittensor/subnet_owner.py` |
| Governance Coordinator | `packages/constitutional_swarm/src/constitutional_swarm/bittensor/governance_coordinator.py` |
| Precedent Cascade | `packages/constitutional_swarm/src/constitutional_swarm/bittensor/cascade.py` |
| Island Evolution | `packages/constitutional_swarm/src/constitutional_swarm/bittensor/island_evolution.py` |
| MAP-Elites Grid | `packages/constitutional_swarm/src/constitutional_swarm/bittensor/map_elites.py` |
| Research paper | `packages/constitutional_swarm/paper/constitutional_swarm_paper.md` |
| **acgs-lite governance pipeline** | |
| Claim lifecycle | `packages/acgs-lite/src/acgs_lite/constitution/claim_lifecycle.py` |
| Validator selection | `packages/acgs-lite/src/acgs_lite/constitution/validator_selection.py` |
| Spot-check auditor | `packages/acgs-lite/src/acgs_lite/constitution/spot_check.py` |
| Trust scoring (domain-scoped) | `packages/acgs-lite/src/acgs_lite/constitution/trust_score.py` |
| **ACGS-2 core** | |
| TurboQuant KV cache | `packages/enhanced_agent_bus/impact_scorer_infra/turboquant_cache.py` |
| MiniCPM semantic scorer | `packages/enhanced_agent_bus/impact_scorer_infra/algorithms/minicpm_semantic.py` |
| Impact scorer service | `packages/enhanced_agent_bus/impact_scorer_infra/service.py` |
| Deliberation queue | `packages/enhanced_agent_bus/deliberation_layer/deliberation_queue.py` |
| Adaptive router | `packages/enhanced_agent_bus/deliberation_layer/adaptive_router.py` |
| Impact scorer | `packages/enhanced_agent_bus/deliberation_layer/impact_scorer.py` |
| MACI 3-role model | `packages/acgs-lite/src/acgs_lite/maci.py` |
| MACI 7-role model | `packages/enhanced_agent_bus/maci/models.py` |
| Trust scoring | `packages/acgs-lite/src/acgs_lite/constitution/trust_score.py` |
| DTMC learner | `packages/enhanced_agent_bus/adaptive_governance/dtmc_learner.py` |
| **External** | |
| TurboQuant paper | arXiv:2504.19874 (ICLR 2026) |
| turboquant PyPI package | `pip install turboquant` (back2matching/turboquant) |
| vLLM integration PR | vllm-project/vllm#38280 |

---

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|---------------|-----------|-----------|----------|
| 1 | CEO | Mode: SELECTIVE EXPANSION | Mechanical | P6 action | Feature enhancement on existing code | SCOPE EXPANSION |
| 2 | CEO | Approach: Testnet-first (user chose) | User gate | N/A | User selected from 4 options | Full 6-phase, SDK+subnet, Phase 1 only |
| 3 | CEO-S1 | bt.Synapse adapter task needed | Mechanical | P5 explicit | Mock dataclasses ≠ real protocol | N/A |
| 4 | CEO-S2 | 3 error gaps acceptable for testnet | Mechanical | P3 pragmatic | Handler timeout, DAG fail, no miners | N/A |
| 5 | CEO-S3 | Defer authenticity detection | Mechanical | P6 action | Both voices: unsolved research problem | Build Phase 4 now |
| 6 | CEO-S6 | bt SDK integration tests are Phase 1.5 | Mechanical | P3 pragmatic | Can't test without real bittensor | N/A |
| 7 | CEO-S8 | Add structlog to bittensor layer | Mechanical | P1 complete | Observability is non-negotiable | Skip logging |
| 8 | CEO-S9 | Testnet deploy scripts are blockers | Mechanical | P1 complete | Can't deploy without scripts | N/A |
| 9 | ENG | Scope: commit existing code + testnet prep | Mechanical | P6 action | 14 new files, all untracked | N/A |
| 10 | ENG | Constitution rollout needs grace window | Taste | P5 explicit | Split-brain risk on version bump | Hard reject on mismatch |
| 11 | ENG | Auto-registration is a security hole | Mechanical | P5 explicit | Any entity can spoof miner_uid | N/A |
| 12 | ENG | Manifold rebuild discarding trust is HIGH | Taste | P1 complete | Defeats purpose of trust accumulation | Accept current behavior |

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | ISSUES_OPEN (via /autoplan) | 4 critical gaps, mode: SELECTIVE_EXPANSION, reframed to testnet-first |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | -- | -- |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | ISSUES_OPEN (via /autoplan) | 20 findings (5 HIGH), 5 critical test gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | SKIPPED | No UI scope |

- **CEO VOICES:** Codex (9 strategic findings) + Claude subagent (10 findings, 1 CRITICAL). Consensus: 6/6 confirmed.
- **ENG VOICES:** Codex (9 findings, 5 HIGH) + Claude subagent (20 findings, 5 HIGH). Consensus: 6/6 confirmed.
- **CROSS-PHASE THEMES:** Authentication/identity gap, precedent poisoning risk, document/decision scope mismatch.
- **UNRESOLVED:** 0 decisions unresolved. 2 taste choices accepted (dual-hash grace window, manifold preservation).
- **VERDICT:** CEO + ENG reviewed. Testnet-first reframe approved. Action items: commit untracked files, add 5 critical tests, fix auto-registration security hole, create testnet deploy scripts. Run `/ship` when ready.
