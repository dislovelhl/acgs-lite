# Stage 5: Integration Surface — acgs-lite, Transport, Examples, Ecosystem

**Tier:** MEDIUM | **Model:** sonnet | **Status:** complete

## [FINDING:ACGS_LITE_COUPLING]

Pin: `acgs-lite>=2.7.2`. **14 distinct imports across 8 source files.**

**Deep and non-optional coupling:**
- `dna.py:20-29` imports `Constitution`, `Rule`, `Severity`, `GovernanceEngine`, `ConstitutionalViolationError`, `MACIRole`, plus deep sub-module paths: `acgs_lite.scoring.ConstitutionalImpactScorer`, `acgs_lite.z3_verify.{Z3_RISK_THRESHOLD, Z3ConstraintVerifier, Z3VerifyResult}`. All top-level unconditional imports.
- `bittensor/governance_coordinator.py:60-75` imports **4 constitution lifecycle sub-modules**: `claim_lifecycle`, `spot_check`, `trust_score`, `validator_selection` (internal paths added in week-3 lifecycle feature).
- `remote_vote_transport.py` imports `Constitution` and constructs `AgentDNA(constitution=...)` — tight coupling to constructor signature.

**Risk:** 4 of 8 importing files use internal sub-module paths (not just public `acgs_lite.*`). Any refactor in acgs-lite without major version bump = breaking change for constitutional_swarm.

[CONFIDENCE:HIGH]

## [FINDING:TRANSPORT_LAYER]

`[transport]` extra (`websockets>=12.0`) → `gossip_protocol.py` + `remote_vote_transport.py`.

**Lazy imports correctly implemented** — `import websockets` inside function bodies (`start()`, `send_batch()`, `request_vote()`), raises clear `ImportError` with install instructions if missing. No top-level `import websockets` anywhere.

**What gets gossipped:** `DAGNode` batches — Merkle-CRDT append-only DAG content. Fields: `cid` (SHA-256), `agent_id`, `payload`, `payload_type`, `parent_cids`, `bodes_passed`, `constitutional_hash`. Task output and artifact data, NOT raw constitutional rules.

**Remote vote transport:** Ed25519-signed vote decisions. `RemoteVoteClient` **enforces TLS for non-localhost** (`ssl_context` required unless host is `127.0.0.1`/`localhost`/`::1`).

**`LocalRemotePeer.handle_vote_request()` performs 4 verification checks** before signing:
1. Voter identity match
2. Public key match
3. Ed25519 request signature (`ConstitutionalMesh.verify_remote_vote_request()`)
4. SHA-256 content hash match

**⚠️ Replay resistance gap:** NO nonce or timestamp field in `RemoteVoteRequest` or `RemoteVoteResponse`. `assignment_id` provides per-request uniqueness, but no explicit replay window or sequence counter. A captured valid response could in principle be replayed for the same `assignment_id`.

[CONFIDENCE:HIGH]

## [FINDING:RESEARCH_EXTRA]

`[research]` extra (`torch>=2.0, transformers>=4.40`) → `latent_dna.py` + `swarm_ode.py`.

**Pattern: top-level `try: import torch except ImportError: raise ImportError(...)`.** This is NOT lazy import — `import torch` is at module body top. Fails fast at module import if torch missing.

**Correct usage pattern:** callers must never import these modules unconditionally. `__init__.py` correctly does NOT re-export `LatentDNAWrapper`, `swarm_ode.*`, `TrustDecayField` — research modules are opt-in by import path.

`transformers` is handled lazily via `importlib.util.find_spec("transformers")` — asymmetric with torch (torch required for module; transformers optional within it).

[CONFIDENCE:HIGH]

## [FINDING:EXAMPLES_DIRECTORY]

**Exactly ONE file: `examples/constitution.yaml`.**

- 0 Python example scripts.
- 0 `if __name__ == "__main__":` entry points.
- 0 demonstration of any of the 5 patterns (CRDT gossip, mesh voting, DAG compilation, bittensor subnet, latent DNA steering).

constitution.yaml itself is well-formed: declares canonical hash `608508a9bd224290`, 4 principles (safety, transparency, proportionality, pluralism), 3 domains, governance params (quorum 0.6, min_validators 3, max_deliberation_rounds 5).

**Gap:** examples dir is essentially empty for developer onboarding relative to the package's documented 5-pattern architecture. `scripts/testnet_deploy.py` (bittensor-only) is the only runnable artifact.

[CONFIDENCE:HIGH]

## [FINDING:EXTERNAL_INTEGRATION_POINTS]

**No HTTP/MCP endpoints.** No FastAPI/aiohttp/MCP server scaffolding in `src/`. No `[project.scripts]` or `[project.entry-points]` in pyproject.toml.

**Bittensor extra:** correct dual-base pattern — `synapse_adapter.py:31-38`: `try: import bittensor as bt; _SynapseBase = bt.Synapse; HAS_BITTENSOR = True; except ImportError: _SynapseBase = BaseModel; HAS_BITTENSOR = False`. Clean ABC/Protocol fallback.

**⚠️ Inconsistency:** `bittensor/governance_coordinator.py:60-75` imports 4 `acgs_lite.constitution.*` sub-modules as **unconditional top-level imports** — despite bittensor being optional. Installing constitutional_swarm without `[bittensor]` extra does NOT isolate this file from acgs-lite's lifecycle sub-modules.

[CONFIDENCE:HIGH]

## [FINDING:REVERSE_COUPLING]

**3 ACGS repo consumers:**

1. **`acgs-lite`** — `src/acgs_lite/integrations/workflow.py:44-60`: guarded `try/except ImportError` with `WORKFLOW_AVAILABLE = False` fallback. Clean optional integration. Tested in `test_workflow_compiler.py` + `test_mcp_server.py` with skip guards.

2. **`enhanced_agent_bus`** — `governance_core.py:37`: dynamic `importlib.import_module("constitutional_swarm")`. **`test_import_boundaries.py` explicitly asserts** constitutional_swarm does NOT appear in static imports — the dynamic-only pattern is intentional and enforced.

3. **`acgs-deliberation`** — `tests/test_import_boundaries.py:8`: explicit exclusion assertion (must NOT import).

**Dependency direction:** `constitutional_swarm` → `acgs-lite` (core). `acgs-lite` / `enhanced_agent_bus` → `constitutional_swarm` (optional, lazy). **No circular imports.** No dashboard/demo/frontend consumers.

[CONFIDENCE:HIGH]

[STAGE_COMPLETE:5]
