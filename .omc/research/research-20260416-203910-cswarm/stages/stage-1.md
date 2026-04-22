# Stage 1: Package Structure & Public API Inventory

**Tier:** LOW | **Model:** haiku | **Status:** complete

## [FINDING:DIRECTORY_TREE]

Root: `/home/martin/Downloads/ACGS/packages/constitutional_swarm/src/constitutional_swarm/`

**Top-level (19 main modules):**
- `__init__.py` — main package entry
- Core patterns: `dna.py`, `swarm.py`, `compiler.py`, `mesh.py`, `manifold.py`, `spectral_sphere.py`, `evolution_log.py`
- Supporting: `artifact.py`, `bench.py`, `capability.py`, `contract.py`, `execution.py`, `gossip_protocol.py`, `merkle_crdt.py`, `remote_vote_transport.py`, `settlement_store.py`
- Research: `latent_dna.py`, `swarm_ode.py`

**Subpackages:**
- `bittensor/` — 24 modules (mining, validation, emissions, chain anchoring, MAP-Elites, island evolution, NMC consensus, Arweave audit log, etc.)
- `swe_bench/` — 4 modules (agent, harness, swarm_coordinator)

**Tests:** 41 test files under `tests/`

[CONFIDENCE:HIGH]

## [FINDING:PUBLIC_API_EXPORTS]

`__init__.py` exports **62 symbols** including:

- **Core classes:** `AgentDNA`, `constitutional_dna`, `SwarmExecutor`, `TaskDAG`, `TaskNode`, `DAGCompiler`, `GoalSpec`, `ConstitutionalMesh`, `MeshProof`, `MeshResult`, `ValidationVote`, `PeerAssignment`, `GovernanceManifold`, `sinkhorn_knopp`, `ManifoldProjectionResult`, `EvolutionLog`, `DashboardRow`
- **Infrastructure:** `Artifact`, `ArtifactStore`, `Capability`, `CapabilityRegistry`, `TaskContract`, `ContractStatus`, `WorkReceipt`, `ExecutionStatus`, `RemoteVoteClient`, `RemoteVoteServer`, `RemoteVoteRequest`, `RemoteVoteResponse`, `LocalRemotePeer`, `SettlementStore`, `JSONLSettlementStore`, `SQLiteSettlementStore`, `SettlementRecord`, `SwarmBenchmark`, `BenchmarkResult`
- **Exceptions (15):** `DNADisabledError`, `EvolutionViolationError`, `MissingPriorEpochError`, `NonIncreasingValueError`, `DecelerationBlockedError`, `MutationBlockedError`, `RegressionRecord`, `DecelerationRecord`, `GapRecord`, `MeshHaltedError`, `AssignmentSettledError`, `InvalidVoteSignatureError`, `DuplicateSettlementError`, `SettlementPersistenceError`, `DuplicateRecordError`

**Not re-exported at top level:** `LatentDNAWrapper`, `SpectralSphereManifold`, `swarm_ode.*`, `TrustDecayField`, `MerkleCRDT` — research modules are opt-in by import path.

[CONFIDENCE:HIGH]

## [FINDING:MODULE_LOC_DISTRIBUTION]

**Total source LOC: 16,351 across 47 Python modules.**

| Module | LOC | Purpose |
|---|---|---|
| `mesh.py` | 1,797 | Constitutional mesh (peer validation, voting, settlement) |
| `bittensor/arweave_audit_log.py` | 641 | Arweave audit log |
| `bittensor/nmc_protocol.py` | 633 | NMC consensus |
| `latent_dna.py` | 563 | MCFS: latent DNA steering |
| `bittensor/rule_codifier.py` | 562 | Blockchain rule codification |
| `gossip_protocol.py` | 535 | Peer gossip discovery |
| `evolution_log.py` | 530 | SQLite append-only metric log |
| `bittensor/tier_manager.py` | 529 | Agent tier/reputation |
| `bittensor/governance_coordinator.py` | 521 | Multi-subnet governance |
| `bittensor/compliance_certificate.py` | 495 | Compliance proofs |
| `dna.py` | 416 | Agent DNA validator |

**Distribution:** Mesh ~11%, Bittensor subpackage ~62%, Core patterns ~27%.

[CONFIDENCE:HIGH]

## [FINDING:TEST_INVENTORY]

41 test files. Top test files: `test_dag_coordinator_deep.py` (83), `test_mesh.py` (75), `test_evolutionary_systems.py` (68), `test_constitutional_swarm.py` (54), `test_arweave_audit_log.py` (46).

**Markers:** `slow` (800+ agent scale), `integration`, `contract`, `research` (empirical research proofs, excluded from release gating).

[CONFIDENCE:HIGH]

## [FINDING:CLI_ENTRY_POINTS]

**No `[project.scripts]`.** CLI surface is `scripts/testnet_deploy.py` (bittensor-only) + library import.

[CONFIDENCE:HIGH]

## [FINDING:DOCUMENTATION_STRUCTURE]

| Path | Files |
|---|---|
| `docs/` | `maci_dp_protocol.md` |
| `paper/` | `constitutional_swarm_paper.md` (18KB), `README.md` |
| `papers/` | `iclr2027/`, `ndss2027/` (LaTeX submissions) |
| `examples/` | `constitution.yaml` only |
| Root | `README.md` (~16KB), `CHANGELOG.md`, `CLAUDE.md`, `SECURITY.md` |

[CONFIDENCE:HIGH]

## [FINDING:GIT_STATUS]

- Current branch: `feat/week3-constitution-lifecycle` (parent repo integration)
- Latest commit: `c2e1626` — "fix: add DuplicateRecordError for duplicate (epoch, metric) writes"
- Package version: 0.2.0 (AGPL-3.0-or-later, Python 3.11+)
- Submodule: commits made from inside the package dir per CLAUDE.md rule

[CONFIDENCE:HIGH]

[STAGE_COMPLETE:1]
