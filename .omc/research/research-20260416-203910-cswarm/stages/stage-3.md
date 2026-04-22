# Stage 3: Test Coverage, Lint Debt & Quality Signals

**Tier:** MEDIUM | **Model:** sonnet | **Status:** complete

## [FINDING:TEST_SUITE_OVERVIEW]

- **40 test files, 1,018 test functions** (README says 1,019 — off by one).
- **1 strict xfail:** `test_manifold_degeneration.py::test_birkhoff_uniformity_collapse` (Birkhoff Uniformity Collapse proof, also marked `@pytest.mark.research`).
- **Top 5 files:** `test_dag_coordinator_deep.py` (83), `test_mesh.py` (75), `test_evolutionary_systems.py` (68), `test_constitutional_swarm.py` (54), `test_arweave_audit_log.py` (46).
- **Async:** 40 `@pytest.mark.asyncio` decorators + `asyncio_mode="auto"` config.
- **Markers:** only `asyncio`, `slow` (4), `parametrize` (3), `xfail` (1), `research` (1) have usage. `integration`, `contract`, `bittensor`, `benchmark`, `e2e` are **registered but unused** → CI marker-based exclusions are mostly no-ops.
- **No Hypothesis / property-based tests.**

[CONFIDENCE:HIGH]

## [FINDING:COVERAGE_REPORT_SYNTHESIS]

From `test-coverage-report.md`. **No numeric % reported** — qualitative gap analysis only.

**HIGH priority gaps:**
1. **Remote vote transport failure paths** — only success paths covered. Missing: malformed JSON, wrong `voter_id`/key-mismatch, `request_vote()` timeout, `collect_remote_votes()` routing failures, `RemoteVoteServer` unavailable (websockets missing).

**MEDIUM priority gaps:**
2. Registration mode transitions — local-signer vs remote-peer split (`mesh.py:330`) partial; lacks key-replacement/cleanup tests.
3. Compiler/swarm collision guard — deterministic ID stability tested; no regression for `TaskDAG.add_node()` duplicate raising `ValueError`.
4. Integration tests skew local-signer — remote-peer end-to-end path not exercised.

Well-covered: `settlement_store` JSONL/SQLite round-trips, corruption, pending reconciliation.

[CONFIDENCE:HIGH for gaps list; MEDIUM for claim of "well-covered" (no coverage %)]

## [FINDING:LINT_DEBT]

- **`ruff check src/` → All checks passed! (0 violations).** The CLAUDE.md note about "53 pre-existing errors in `latent_dna.py` — suppress RUF002/RUF003" is stale — already resolved.
- **Architectural debt (not ruff):** `mesh.py` at 71KB / ~1,670 lines is doing 9+ jobs (registration, vote auth, quorum/finality, proof construction, settlement persistence, remote vote orchestration, reputation, manifold integration, serialization, utility math). Style report recommends split into `mesh/core.py`, `mesh/persistence.py`, `mesh/remote.py`, `mesh/proof.py`.
- `__init__.py` over-exports stable primitives alongside transport runtime classes in a single flat namespace.
- `remote_vote_transport.py` conflates JSON codecs, WebSocket client/server, in-process peer runtime in one file.

[CONFIDENCE:HIGH]

## [FINDING:SECURITY_AUDIT_SYNTHESIS]

`security-audit-report.md` findings (last-audited state, **remediation claimed in `SYSTEMIC_IMPROVEMENT.md` but audit was not re-run**):

- **HIGH — Remote vote transport unauthenticated/plaintext** (`remote_vote_transport.py:114-230`, `mesh.py:850-875`): Client uses `ws://` with no TLS or request auth. Response signature protects vote decision, but MITM can alter content seen by remote peer before signing. SYSTEMIC_IMPROVEMENT.md claims "non-local WebSocket transport now requires TLS" — partial mitigation, unverified.
- **MEDIUM — Settlement persistence not replay-complete** (`mesh.py:1320-1407`): `_deserialize_assignment()` recreates missing `content` as `""`, weakens auditability. Not explicitly claimed fixed.
- **MEDIUM — Pending settlement reconciliation not fail-closed** (`mesh.py:284-290`): constructor calls `_load_settlements()` + `retry_pending_settlements()` but ignored reconciliation failure count. **Claimed fixed** in SYSTEMIC_IMPROVEMENT.md.

Residual: `JSONLSettlementStore` single-writer, O(n) duplicate check; docs understate networked trust boundary.

[CONFIDENCE:MEDIUM] — remediation status unverified without re-running the audit.

## [FINDING:CI_POSTURE]

**`.github/workflows/ci.yml` — 6 jobs:**
- `test` (matrix Py3.11+3.12): ruff + pytest excl. slow/benchmark/e2e/research/bittensor
- `test-research` (Py3.11): pytest excl. slow/benchmark/e2e (includes `research`)
- `package`: wheel+sdist build + twine check + import smoke test
- `test-extras-bittensor`: import-only, no behavior tests
- `test-extras-transport`: import-only, no behavior tests

**`publish.yml`:** Release-gated PyPI publish via `pypa/gh-action-pypi-publish@v1.12.3` with OIDC trusted publishing.

**⚠️ Possible bug:** `test` and `test-research` use `actions/checkout@v6` and `actions/setup-python@v6` — these versions may not exist (current stable is v4). The `test-extras-*` jobs use `@v4`/`@v5`. **CI may fail to check out code on primary jobs.** [CONFIDENCE:MEDIUM — verify against current GitHub Actions release history; could be valid if releases rolled forward since my knowledge cutoff.]

**Gaps:** No `--cov-fail-under`, no mypy/typecheck step, no integration/e2e job, extras jobs verify import only.

[CONFIDENCE:HIGH for jobs; MEDIUM for @v6 issue]

## [FINDING:OVERALL_QUALITY_VERDICT]

**Strengths:**
- Zero ruff violations.
- 1,018 tests is substantial.
- Core happy paths well-covered.
- Phase-2 security hardening completed (Ed25519 signatures, local-signer vs remote-peer split, TLS for non-local transport per `SYSTEMIC_IMPROVEMENT.md`).
- Publish uses OIDC (no stored PyPI token).
- Extras correctly isolated.

**Weaknesses requiring attention:**
1. **CI actions version bug** (@v6) — primary jobs may fail.
2. **Unverified security remediation** — HIGH finding claimed fixed but audit not re-run.
3. **Failure-path coverage gaps** — remote vote transport, registration transitions, collision guard all lack tests.
4. **No coverage enforcement in CI.**
5. **`mesh.py` architectural debt** — 71KB monolith.
6. **Delivery hygiene** — `__pycache__` tracked, `SYSTEMIC_IMPROVEMENT.md` as root artifact, README still partially describes local-only model.

[CONFIDENCE:HIGH]

[STAGE_COMPLETE:3]
