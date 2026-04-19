# Research Report: constitutional_swarm Package

**Session ID:** research-20260416-203910-cswarm
**Date:** 2026-04-16
**Status:** complete
**Target:** `/home/martin/Downloads/ACGS/packages/constitutional_swarm`

## Executive Summary

`constitutional-swarm` (v0.2.0, AGPL-3.0, Py3.11+, 16.3 KLOC across 47 modules) ships **five composable governance patterns** for multi-agent systems, with deep-but-correctly-layered coupling to `acgs-lite`. The core governance path — Agent DNA (443ns validation) + Stigmergic Swarm (DAG-compiled task execution) + Constitutional Mesh (Ed25519-signed Byzantine peer voting) + Manifold-Constrained Trust (production `SpectralSphereManifold`) + Evolution Log (SQL-trigger-enforced metric invariants) — is coherent, well-tested (1,018 test functions, 0 lint violations, MACI separation enforced at 3 layers), and fail-closed by default. The package also carries a **research track (MCFS stack)** that is architecturally isolated: `latent_dna`, `swarm_ode`, `merkle_crdt`, and `gossip_protocol` are opt-in via the `[research]`/`[transport]` extras and are not called from the production mesh path. `spectral_sphere` is the sole MCFS-lineage module that is integrated into production code.

**The primary risks are not in the core governance code — they're in the research/claims layer and the CI pipeline.** The repo contains two papers whose claims partly refute each other (the older whitepaper's Birkhoff/Sinkhorn solution is named as a failure mode in the newer ICLR submission), some fabricated-looking arXiv cites, paper metrics that are not reproducible from the shipped code (`torchdiffeq.dopri5` ≠ custom RK4; "2,656% topological capacity" has no test backing), and a CI workflow that uses `actions/checkout@v6` / `actions/setup-python@v6` on primary jobs while extras jobs use `@v4`/`@v5` — likely to break CI. A HIGH-severity security finding (unauthenticated `ws://` transport) was partially remediated per `SYSTEMIC_IMPROVEMENT.md` but the audit was never re-run to confirm.

**Net: production governance surface is defensible; the research/publication surface and CI are where work is needed before a credible external release.**

## Methodology

### Research Stages

| Stage | Focus | Tier | Status |
|---|---|---|---|
| 1 | Package structure & public API inventory | LOW (haiku) | complete |
| 2 | Architecture of the 5 governance patterns | MEDIUM (sonnet) | complete |
| 3 | Test coverage, lint debt & quality signals | MEDIUM (sonnet) | complete |
| 4 | Research novelty: MCFS, latent DNA, paper claims | HIGH (opus) | complete |
| 5 | Integration surface: acgs-lite, transport, ecosystem | MEDIUM (sonnet) | complete |
| V | Cross-validation | sonnet | complete (3 corrections applied) |

### Approach

Decomposed the open-ended "research this package" goal into 5 parallel investigations by axis (structure, architecture, quality, novelty, integration). Ran them concurrently to cover breadth, then ran a verification pass to resolve inter-stage inconsistencies with shell commands against the live repo.

## Key Findings

### Finding 1: Five governance patterns are well-separated and defensible

**Confidence:** HIGH

| Pattern | Core Module | LOC | Role |
|---|---|---|---|
| A. Agent DNA | `dna.py` | 416 | Per-agent constitutional co-processor, 3-layer (scorer → rule engine → Z3), 443ns Rust engine |
| B. Stigmergic Swarm | `swarm.py`+`compiler.py` | ~700 | Immutable `TaskDAG`, orchestrator-free capability/domain matching |
| C. Constitutional Mesh | `mesh.py` | 1,797 | Byzantine-tolerant peer validation, Merkle-style `MeshProof`, Ed25519 votes, adaptive quorum |
| D. Governance Manifold | `manifold.py`+`spectral_sphere.py` | ~550 | Birkhoff polytope (research-only) + SpectralSphere (production, integrated in mesh) |
| E. Evolution Log | `evolution_log.py` | 530 | Append-only SQLite with invariants enforced via triggers (monotonicity, acceleration, uniqueness) |

**MACI separation-of-powers enforced at 3 independent layers:**
1. `AgentDNA.MACIEnforcer.check_maci(action_type)` → `MACIViolationError`
2. Mesh peer exclusion: `mesh.py:536` unconditionally excludes producer from peer pool
3. `SwarmExecutor.submit` guard: `swarm.py:280–283` only claiming agent can submit

**Fail-closed defaults throughout:** `strict=True` on `AgentDNA`, `SettlementPersistenceError` on startup if reconciliation incomplete, `MeshHaltedError` during kill-switch, explicit comment at `bittensor/axon_server.py:80` ("must fail closed without raising").

Constitutional hash `608508a9bd224290` is not hardcoded — it flows from `Constitution.hash` through `PeerAssignment`, `ValidationVote`, `MeshProof`, `WorkReceipt`, and is cross-checked on every remote vote request.

### Finding 2: `spectral_sphere` is production — `latent_dna`, `swarm_ode`, `merkle_crdt`, `gossip_protocol` are research-only

**Confidence:** HIGH (verified in cross-validation)

The "MCFS research stack" is NOT a single uniform block. `mesh.py:52` imports `spectral_sphere` unconditionally at module top-level, and `ConstitutionalMesh` instantiates `SpectralSphereManifold` directly via `manifold_type="spectral"` and optionally `shadow_spectral=True` for A/B testing. Spectral-Sphere is **production**, not research-only.

The other four research-stack modules (`latent_dna`, `swarm_ode`, `merkle_crdt`, `gossip_protocol`) are gated behind `[research]`/`[transport]` extras, require torch (or websockets), are not re-exported from `__init__.py`, and have zero production callsites outside tests and `swe_bench/agent.py`. They are legitimately optional.

### Finding 3: The research/claims layer has credibility issues

**Confidence:** HIGH

Three categories of issue:

**a) Self-refuting papers in the same repo.** `paper/constitutional_swarm_paper.md` (older) sells the Birkhoff/Sinkhorn `GovernanceManifold` as the solution. `papers/iclr2027/` formally names that exact mechanism **"Birkhoff Uniformity Collapse (BUC)"** as a failure mode and replaces it with `SpectralSphereManifold`. The module docstring at `manifold.py:132–142` deprecates the older paper's centerpiece: "Research use only."

**b) Novelty is narrower than the marketing suggests.**
- **Genuinely novel (narrow):** explicit framing of BUC as a named failure mode for iterated Sinkhorn in multi-agent trust; Lemma 8 (§3.4 of ICLR paper) DP sensitivity `Δ = 2(1-α)r` via α·I cancellation.
- **Standard techniques rebranded:** "Governance Manifold" = Xie et al. mHC 2025; "SpectralSphere" = sHC; "BODES" = activation steering + orthogonal projection (credited to Zou et al. RepE 2023 in-code, not in paper abstract); "443ns" = Aho-Corasick throughput against a ~10-byte string with a pre-compiled automaton.
- **Paper-only, not in code:** ICLR experiments claim `torchdiffeq.dopri5` (rtol=1e-3, atol=1e-6) — repo ships a custom hand-rolled `projected_rk4_step`, never imports torchdiffeq. "2,656% topological capacity" appears only in LaTeX (abstract.tex, conclusion.tex, figures/variance_comparison.tex) — no test computes reachable-set volume. The abstract itself admits "high topological capacity does not itself guarantee amplification of the correct specialization" — unusually honest self-limitation that undercuts the headline.

**c) Citation red flags.**
- NDSS 2027 companion paper cites `mcfs_iclr2027` 5× as if it were published third-party literature (self-citation).
- `spectral_sphere.py:19` cites sHC as `arXiv:2603.20896`. This ID is *temporally plausible* (March 2026 is in the past as of 2026-04-16) but unverified. Referenced mHC cite `2512.24880` is likewise temporally plausible but unverified.
- The "1,021 tests / 1,019 pass / 2 xfail" test-suite boast doubles as paper metric when those xfails include the flagship BUC "collapse proof" (a test deliberately designed to fail as its research result).
- 443ns copied into 14+ files as the dominant marketing datum.

### Finding 4: Test suite is substantial but has specific failure-path gaps

**Confidence:** HIGH

- **40 test files, 1,018 test functions** (README claim of 1,019 is off by one)
- **0 ruff violations** in `src/` — lint is fully clean
- **1 strict xfail** — `test_manifold_degeneration.py::test_birkhoff_uniformity_collapse` (BUC proof, intentional)
- **Unused markers** — `integration`, `contract`, `bittensor`, `benchmark`, `e2e` are registered but have zero uses. CI's marker-based exclusions are mostly no-ops.
- **No Hypothesis / property-based tests.**

**Coverage gaps (from `test-coverage-report.md`, no numeric %):**
- HIGH: remote vote transport failure paths (malformed JSON, key mismatch, timeouts, websockets missing) — only success paths tested.
- MEDIUM: registration-mode transitions (local-signer ↔ remote-peer), collision-guard regression, remote-peer end-to-end integration.
- Well-covered: settlement store round-trips, corruption handling, pending reconciliation.

### Finding 5: Integration surface is clean; coupling is one-directional with guards

**Confidence:** HIGH

- **acgs-lite coupling:** `>=2.7.2`, 14 distinct imports across 8 files. Deep sub-module paths (`acgs_lite.scoring.*`, `acgs_lite.z3_verify.*`, `acgs_lite.constitution.*` in `governance_coordinator.py`) increase break surface — any acgs-lite refactor without major version bump breaks constitutional_swarm.
- **Transport:** websockets lazy-imported inside function bodies. `RemoteVoteClient` enforces TLS for non-localhost. `LocalRemotePeer.handle_vote_request()` runs 4 signature/identity/hash checks before signing. **Replay gap:** no nonce/timestamp in `RemoteVoteRequest`/`RemoteVoteResponse` — `assignment_id` provides per-request uniqueness but no explicit replay window.
- **Research extras:** torch required at module-body top of `latent_dna.py` and `swarm_ode.py` — fail-fast ImportError. `__init__.py` correctly does not re-export these names.
- **Reverse coupling:** 3 ACGS consumers — `acgs-lite/integrations/workflow.py` (clean `try/except ImportError` with `WORKFLOW_AVAILABLE` flag), `enhanced_agent_bus/governance_core.py` (dynamic `importlib.import_module`, enforced by `test_import_boundaries.py`), `acgs-deliberation/tests/test_import_boundaries.py` (explicit must-NOT-import). No circular deps.
- **External surface:** no HTTP/MCP endpoints, no CLI entry points. Only network surface is WebSocket transport.

### Finding 6: CI has a likely-breaking version bug; security remediation unverified

**Confidence:** HIGH (for observed inconsistency); MEDIUM (for break severity)

**CI bug:** `ci.yml` primary jobs (`test`, `test-research`) use `actions/checkout@v6` and `actions/setup-python@v6` while extras jobs use `@v4`/`@v5`. The inconsistency is a code smell regardless; if `@v6` is not a released version on either action, the primary gates will fail to check out code. Extras jobs verify import only, not behavior.

**Security:** `security-audit-report.md` has 1 HIGH + 2 MEDIUM findings:
- **HIGH** — unauthenticated `ws://` transport (`remote_vote_transport.py`). `SYSTEMIC_IMPROVEMENT.md` claims TLS is now required for non-local transport — this matches Stage 5's finding that `RemoteVoteClient` enforces TLS for non-localhost. Likely fixed but audit not re-run to confirm.
- **MEDIUM** — settlement persistence not replay-complete (missing `content` restored as `""`). No explicit remediation claim.
- **MEDIUM** — pending settlement reconciliation not fail-closed. Claimed fixed in `SYSTEMIC_IMPROVEMENT.md` — matches Stage 2's observation that `SettlementPersistenceError` is raised at mesh startup if reconciliation fails. Likely fixed.

**Publish pipeline uses OIDC trusted publishing** (no stored PyPI token) — good.

## Cross-Validation Results

See [findings/verified/cross-validation.md](findings/verified/cross-validation.md). 7 items checked, 3 corrections applied (test file count, SpectralSphere classification, arXiv date framing). No other inter-stage conflicts.

## Limitations

- **Coverage %** — `test-coverage-report.md` provides qualitative gap analysis only; no `pytest-cov --cov-fail-under` baseline exists.
- **Security remediation** — based on `SYSTEMIC_IMPROVEMENT.md` prose + Stage 2/5 code observations. Re-running the original audit would confirm.
- **arXiv IDs** — `2603.20896` (sHC) and `2512.24880` (mHC) are temporally plausible as of 2026-04-16 but **not verified against arXiv.org.** They could be real or fabricated.
- **`@v6` actions** — not verified against GitHub Actions release registry.
- **No tests were executed** — all findings are from static reading + `ruff check --quiet`. A test run could surface flaky/broken tests not visible here.
- **`bittensor/` subpackage (62% of LOC)** was not deeply analyzed beyond counting and spot-checking — its internal correctness is out of scope.

## Recommendations

**Before external release or paper submission:**

1. **Fix CI actions versions.** Either pin all jobs to a known-good version (`@v4` for checkout, `@v5` for setup-python) or verify `@v6` is released. Current inconsistency will likely break primary jobs.
2. **Re-run the security audit.** Regenerate `security-audit-report.md` against current code so the HIGH finding status is documented, not just claimed in a separate `SYSTEMIC_IMPROVEMENT.md`.
3. **Add nonce/timestamp to `RemoteVoteRequest`.** Close the replay window — `assignment_id` alone is insufficient for a captured-response replay scenario.
4. **Reconcile the two paper tracks.** Either update `paper/constitutional_swarm_paper.md` to reflect the BUC finding and SpectralSphere replacement, or delete it. Currently the repo publishes a thesis and its refutation.
5. **Verify every arXiv cite in the papers** against `arxiv.org`. Flag fabricated/placeholder IDs before submission.
6. **Remove or re-contextualize paper claims that have no code backing.** Either implement `torchdiffeq.dopri5` (replacing custom RK4), or update the experiments section to match the shipped integrator. The `2,656% topological capacity` number needs either a test or a removal.

**Medium-term maintenance:**

7. **Split `mesh.py`** (1,797 lines, 9+ responsibilities) per the style report recommendation: `mesh/core.py`, `mesh/persistence.py`, `mesh/remote.py`, `mesh/proof.py`.
8. **Add failure-path tests for remote vote transport** (per `test-coverage-report.md` HIGH-priority gap).
9. **Add `--cov-fail-under` threshold** in CI so coverage regressions are visible.
10. **Populate `examples/`** with at least one runnable demo per public pattern. The current state (one YAML file) is insufficient for developer onboarding given the 5-pattern architecture advertised in the README.
11. **Evaluate tightness of `acgs-lite` deep-import coupling.** 4 of 8 importing files use internal sub-module paths. Consider re-exporting needed symbols from `acgs_lite` top level, or adding a compatibility shim layer in constitutional_swarm.

## Appendix

### Raw Findings

- [stages/stage-1.md](stages/stage-1.md) — Structure & API
- [stages/stage-2.md](stages/stage-2.md) — Architecture
- [stages/stage-3.md](stages/stage-3.md) — Quality
- [stages/stage-4.md](stages/stage-4.md) — Novelty
- [stages/stage-5.md](stages/stage-5.md) — Integration
- [findings/verified/cross-validation.md](findings/verified/cross-validation.md) — Cross-check

### Session State

- [state.json](state.json)

### Key Paths Referenced

- `/home/martin/Downloads/ACGS/packages/constitutional_swarm/src/constitutional_swarm/{dna,swarm,compiler,mesh,manifold,spectral_sphere,evolution_log}.py`
- `/home/martin/Downloads/ACGS/packages/constitutional_swarm/paper/constitutional_swarm_paper.md`
- `/home/martin/Downloads/ACGS/packages/constitutional_swarm/papers/iclr2027/sections/`
- `/home/martin/Downloads/ACGS/packages/constitutional_swarm/.github/workflows/ci.yml`
- `/home/martin/Downloads/ACGS/packages/constitutional_swarm/SYSTEMIC_IMPROVEMENT.md`
- `/home/martin/Downloads/ACGS/packages/constitutional_swarm/test-coverage-report.md`
- `/home/martin/Downloads/ACGS/packages/constitutional_swarm/security-audit-report.md`
- `/home/martin/Downloads/ACGS/packages/constitutional_swarm/style-improvement-report.md`

[PROMISE:RESEARCH_COMPLETE]
