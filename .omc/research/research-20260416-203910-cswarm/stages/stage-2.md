# Stage 2: Architecture of the 5 Governance Patterns

**Tier:** MEDIUM | **Model:** sonnet | **Status:** complete

## [FINDING:PATTERN_A_DNA] — Agent DNA (embedded constitutional co-processor)

`AgentDNA` is a frozen dataclass wrapping `acgs_lite.GovernanceEngine` (Rust engine). Per-agent, immutable `Constitution` reference. Three layers:

1. **Scorer** (opt-in, ~1 ms): `ConstitutionalImpactScorer`
2. **Rule engine** (443 ns): the Rust keyword/rule match — this is where the "443 ns" headline comes from
3. **Z3** (opt-in, ~50–500 ms): only when `risk_score >= Z3_RISK_THRESHOLD`

Fail behavior: `strict=True` is default → raises `ConstitutionalViolationError`. `strict=False` returns `DNAValidationResult` with violations.

`.govern(fn)` decorator validates input AND output (`validate_output=True` default). Output extraction handles `str`, `dict`, `list`, custom `__str__`.

Kill switch: `.disable()` (EU AI Act Art. 14(3)) — all calls raise `DNADisabledError`.

**File:** `src/constitutional_swarm/dna.py` lines 38–320

[CONFIDENCE:HIGH]

## [FINDING:PATTERN_B_STIGMERGIC_SWARM] — DAG-compiled orchestrator-free

Two classes: `DAGCompiler` (`compiler.py`) + `SwarmExecutor` / `TaskDAG` (`swarm.py`).

**`DAGCompiler.compile(GoalSpec)`** — compile-time invariants:
- Non-empty domain names
- No duplicate step titles
- All dependencies must exist
- Step domains must be in declared domain list
- No cycles (DFS detection)
- Deterministic node IDs: `sha256(title)[:16]`

**`TaskDAG`** is immutable — all mutations return new instances. The DAG structure IS the coordination; no orchestrator message-passing.

**`SwarmExecutor.available_tasks(agent_id)`** — capability/domain match, sorted by priority desc. Claiming is atomic under `threading.Lock`.

**MACI submit guard (swarm.py:280–283):** `if node.claimed_by is not None and artifact.agent_id != node.claimed_by: raise PermissionError`

**Node state machine:** `BLOCKED → READY → CLAIMED → COMPLETED`

[CONFIDENCE:HIGH]

## [FINDING:PATTERN_C_CONSTITUTIONAL_MESH] — Byzantine-tolerant peer validation

`ConstitutionalMesh` (`mesh.py`, 71KB). Three-step flow:

1. **DNA pre-check** (`request_validation`): mesh-shared `AgentDNA` validates content first (443 ns). Fails fast with `ConstitutionalViolationError`.
2. **MACI peer selection:** producer unconditionally excluded (`mesh.py:536`). Adaptive scaling: `risk >= 0.8` → all peers; `>= 0.5` → +1. Quorum enforced.
3. **Ed25519-signed votes:** verified on `submit_vote`. Late votes after quorum → `AssignmentSettledError`.

**`MeshProof`** is a Merkle-style chain: `sha256(assignment_id + content_hash + constitutional_hash + vote_hashes + accepted)`. `.verify()` recomputes.

Peer-validator DNA uses `strict=False` (mesh.py:754) — correct, since peers vote, not abort.

**MACI separation:** producer = Proposer, peers = Validators, mesh quorum = Executor authority.

**Remote peers:** Ed25519 request signature verified before validating content. `ws://` allowed on localhost only; non-local requires TLS.

**Kill switch:** `.halt()` / `.resume()` → `MeshHaltedError` during halt.

**Settlement:** `JSONLSettlementStore`, `SQLiteSettlementStore`. Pending settlement reconciliation failure at startup raises `SettlementPersistenceError` (fail-closed).

[CONFIDENCE:HIGH]

## [FINDING:PATTERN_D_MANIFOLD_CONSTRAINED_TRUST] — Two implementations

**`GovernanceManifold`** (`manifold.py`) — Birkhoff polytope via Sinkhorn-Knopp. **Marked "Research use only"** in module docstring — suffers Birkhoff Uniformity Collapse (Perron-Frobenius drives repeated compositions → J = (1/N)·11ᵀ, destroying specialization by cycle ~10).

**`SpectralSphereManifold`** (`spectral_sphere.py`) — production replacement. Projection: `H_proj = H * min(1, r / sigma_max(H))`. Power iteration on MᵀM (O(n²·k)). Allows negative entries (explicit distrust). Optional `residual_alpha=0.1` → >80% variance retention across 100+ cycles vs ~0% for Birkhoff.

`ConstitutionalMesh` integrates both via `manifold_type="birkhoff"|"spectral"` flag; `shadow_spectral=True` runs spectral in parallel for A/B.

[CONFIDENCE:HIGH]

## [FINDING:PATTERN_E_EVOLUTION_LOG] — SQL-trigger-enforced metric invariants

`EvolutionLog` (`evolution_log.py`) — append-only SQLite with 5 invariants enforced entirely at DB layer:

1. **Strict monotonicity:** `value(N) > value(N-1)` — no plateaus, no regressions
2. **Strict acceleration:** `delta(N) > delta(N-1)` — improvement rate must grow
3. **Contiguous history:** epoch N requires N-1
4. **Uniqueness:** `(epoch, metric)` PRIMARY KEY
5. **Minimum evidence:** ≥2 epochs for monotonicity, ≥3 for acceleration

`STRICT` table + `BEFORE INSERT`/`UPDATE`/`DELETE` triggers. Derived delta/accel live in a SQL view — never stored. Python maps `RAISE(ABORT, ...)` strings to typed exceptions.

[CONFIDENCE:HIGH]

## [FINDING:MACI_AND_FAIL_CLOSED]

**MACI enforcement** at 3 independent layers:
1. `AgentDNA`: `MACIEnforcer.check_maci(action_type)` → `MACIViolationError`
2. Mesh peer exclusion: `mesh.py:536`
3. `SwarmExecutor.submit` guard: `swarm.py:280–283`

**Fail-closed defaults:**
- `AgentDNA(strict=True)` raises on violations
- Mesh refuses to serve if pending settlements can't be reconciled at startup
- `bittensor/axon_server.py:80` — broad `except Exception` commented "must fail closed without raising"
- `DNADisabledError` raised (not silently passed) when disabled

**Constitutional hash `608508a9bd224290`** — not hardcoded in this package. Flows from `Constitution.hash` through `PeerAssignment`, `ValidationVote`, `MeshProof`, `WorkReceipt`. Cross-checked on every remote vote request.

**Cross-pattern dependencies:**
- Pattern C (Mesh) → Pattern A (DNA)
- Pattern C (Mesh) optionally → Pattern D (Manifold) via `use_manifold` flag
- Pattern B (Swarm) is independent at the code level
- Pattern E (Evolution Log) is fully standalone
- All patterns → `acgs-lite` for primitives

[CONFIDENCE:HIGH]

[STAGE_COMPLETE:2]
