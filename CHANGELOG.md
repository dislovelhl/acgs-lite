# Changelog

All notable changes to acgs-lite will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.9.0] - 2026-04-22

### Added

- **ARC-Kit bridge** (`acgs_lite.arckit`): parse architecture diagrams, generate and export
  constitution bundles, emit CLI commands, and map to compliance frameworks — full pipeline from
  project structure to governed rules.
- **Governance memory** (`constitution.governance_memory`): unified retrieval layer over rules and
  precedents; MCP `validate_action` tool now returns matched rules and precedents in the response.
- **Policy linter** (`constitution.policy_linter`): static quality analysis of YAML constitution
  files with structured findings and a CI-friendly exit code.
- **`GovernanceStream`**, **`PolicyStorage`**, and DI-scoped service interfaces for framework
  integration (AFFiNE-style architecture patterns).
- **Batch audit writes**: `AuditLog.record_atomic_many()` writes multiple entries atomically to
  durable backends, reducing round-trips for bulk governance events.
- 21 previously internal governance symbols exported from the public API.

### Changed

- PyPI development-status classifier changed from `5 - Production/Stable` to `4 - Beta`; package
  description rewritten for accuracy.
- README: added "Safety Defaults" section and "Component Stability" table.
- Rust fast path enabled for `strict=False` validation mode (+374% allow-ops throughput).

### Fixed

- **Telegram webhook** (`integrations.telegram_webhook`): handler changed from `async def` to
  `def` so FastAPI runs it in a thread pool and the event loop is not blocked by the synchronous
  `validate()` call.
- **MCP server strict-mode safety** (`integrations.mcp_server`): `engine.strict` is now restored
  inside a `try/finally` block at all three call sites so an exception during `validate()` cannot
  leave strict mode permanently disabled.
- `engine_getter` pattern in `create_telegram_webhook_router` prevents stale engine closure after
  `_rebuild_engine` replaces the module-level engine.
- CDP report generation: `fpdf2` API call updated (`ln=True` → `new_x`/`new_y`) for fpdf2 ≥ 2.8.
- PQC module now catches `SystemExit` and `RuntimeError` from broken oqs/liboqs installations
  instead of propagating them.
- `__init__.py` duplicate-import warnings (F811) removed.
- `AuditLog.record()` backend write serialized under state lock (thread-safety regression fix).
- `record_atomic` is now truly atomic for durable backends.

## [2.8.1] - 2026-04-16

### Changed (fail-closed hardening, non-breaking)

- **Streaming validator is now fail-closed on engine exception.** `StreamingValidator._validate_window` previously swallowed any engine exception and returned `passed=True, should_halt=False` — a silent fail-open that defeats constitutional guarantees when the engine is unstable. The default is now `passed=False, should_halt=True` with an `ERROR`-level log line. A new `fail_open_on_error: bool = False` constructor flag restores the legacy behavior for callers that genuinely need it. Existing test coverage was migrated to the explicit opt-in, and new tests pin the fail-closed default.
- **`StreamingValidator` now emits a `UserWarning` when `blocking_severities` is unset.** The empty-set default means no severity level halts the stream; this is a silent safety gap. Pass `blocking_severities={"critical"}` (or higher) to silence the warning. The default will change to `{"critical"}` in 3.0.
- **`GovernedAgent` emits a `DeprecationWarning` when `maci_role` is set but `enforce_maci=False`.** This is the most common misconfiguration surfaced by the v2.8 gap analysis — MACI role separation looks enforced but is advisory. The `enforce_maci` default will flip to `True` in 3.0. Opt in now with `enforce_maci=True` plus `governance_action=...` on every run.

### Added

- **Opt-in quarantine wiring in `InterventionEngine`.** New constructor parameter `quarantine: GovernanceQuarantine | None = None`. When supplied, the `ESCALATE` action submits the offending CDP record to quarantine (with `quarantine_id` surfaced on the outcome metadata) instead of only flagging `requires_review`. The previously orphan `GovernanceQuarantine` module is now reachable from the standard intervention pipeline without any API break — default `None` preserves v2.8.0 behavior.

### Fixed

- **Observable error handling in `GovernedAgent._emit_cdp`.** Three blanket `except Exception: pass` blocks (runtime compliance check, intervention handler, outer CDP emission) are replaced with logged `ERROR` entries including exception type and traceback. Fail-open semantics are preserved for CDP (the governed call never fails from CDP trouble), but failures are now diagnosable instead of silent. The inner `server`-backend import fallback is now logged at `DEBUG`.
- **Thread-safety for `AuditLog.record()`.** `AuditLog._entries` and `AuditLog._chain_hashes` are now protected by a `threading.Lock` during read-modify-write (chain hash computation, append, trim-on-overflow). The backend write is deliberately released outside the lock to avoid serializing all recorders on disk I/O. Eliminates the race where concurrent recorders could corrupt the chain hash.
- **Thread-safety for `InterventionEngine` throttle and cool-off state.** `_handle_throttle` and `_handle_cool_off` now take a `threading.Lock` around dict read-modify-write; `is_cooled_off` takes the lock for the read. Eliminates lost-update and torn-read bugs under concurrent evaluation.

### Deprecation notices

- `StreamingValidator(blocking_severities=None)` — default will change in 3.0.
- `GovernedAgent(maci_role=<role>, enforce_maci=False)` — default will flip in 3.0.

## [2.8.0] - 2026-04-15

### Added

- **Phase A — Real eval integration**: `ConstitutionLifecycle.run_evaluation()` now executes actual `EvalScenario` objects against a `GovernanceEngine` built from the bundle's constitution. Pass rate is recorded in `bundle.eval_summary`. Vacuous-pass bypass (empty/None scenarios) raises `LifecycleError`. Self-approval guard added to `approve()`.
- **Phase B — SQLite persistent BundleStore**: New `SQLiteBundleStore` survives process restarts. WAL journal mode, `BEGIN EXCLUSIVE` transactions for multi-step writes, and a partial unique index enforce one active bundle per tenant at the database level. Raw `sqlite3.OperationalError` is wrapped as `LifecycleError` with context.
- **Phase C — FastAPI lifecycle router**: Thirteen REST endpoints under `/constitution/lifecycle/` expose the full saga lifecycle (10 `POST` mutation endpoints + 3 `GET` read endpoints), including `POST /{id}/reject` for VALIDATOR-role rejection. When configured, all lifecycle endpoints require `X-API-Key` authentication. Pydantic request models provide OpenAPI schema. Active-bundle response includes `engine_binding_active: bool` to surface the Phase C/E gap explicitly.
- **Phase E — BundleAwareGovernanceEngine**: `BundleAwareGovernanceEngine(store).for_active_bundle(tenant_id)` returns a `GovernanceEngine` built from the tenant's active bundle constitution. Engine cache is keyed by `(tenant_id, bundle_hash)` with `threading.Lock`. Host applications must call `invalidate(tenant_id)` after lifecycle changes that should refresh the bound engine.
- **Agno integration adapter**: New `acgs_lite.integrations.agno` adapter for the Agno agent framework (optional `[agno]` extra).
- **`[server]` extra**: `fastapi` + `uvicorn` now installable as `pip install acgs-lite[server]` for the lifecycle HTTP router.
- **Lifecycle quickstart example**: `examples/lifecycle_quickstart.py` demonstrates the full `create_draft → run_evaluation → activate → validate()` flow end-to-end.
- **Lifecycle HTTP API docs**: `docs/api/lifecycle.md` documents all thirteen endpoints with request/response shapes, error codes, and auth requirements.
- **Audit trail parity in `withdraw()`**: `withdraw()` now passes `reason` to `status_history`, matching the audit record written by `reject()`. Both ops now leave a full operator-reason trail.

## [2.7.2] - 2026-04-09

### Fixed
- **Standalone package test compatibility**: Fixed four test files that used monorepo-relative
  `parents[3]` path calculations, updated to `parents[1]` (repo root). Added `skipif` guards
  for tests that require `autoresearch/` data not present in the standalone package
  (`test_autoresearch_scenario_corpus.py`, `test_real_use_case_datasets.py`,
  `test_rule_metrics.py`, `test_provider_capability_manifest.py`).
- **Editable install path**: Updated `.pth` file to point to `src/` in the standalone repo
  rather than the old monorepo location.

## [2.7.1] - 2026-04-09

### Added
- **Constitutional swarm mesh settlement durability**: `SQLiteSettlementStore` provides a
  persistent SQLite-backed settlement store alongside the existing `JSONLSettlementStore`.
  Mesh proofs now survive process restarts. Settlement backends implement a pluggable
  `SettlementStore` protocol; swap adapters at instantiation time.
- **Provider capabilities manifest and session observability**: `provider_capabilities.py`
  ships a `provider_capabilities_manifest.json` with validated model IDs and capability
  flags for all major providers. `observe_session.py` command enables live observation
  logging with structured JSONL output.
- **acgs-lite hardening**: circuit breaker, fail_closed, governed, scoring, and all
  integration adapters (openai, anthropic, langchain, litellm, autogen, pydantic_ai,
  google_genai, haystack) received audit and exception logging improvements.

### Fixed
- **JWT verification error no longer leaks exception details**: `auth.py` error handler
  now logs `type(e).__name__` only, not the full exception string, preventing token
  content or key material from appearing in logs.
- **GovernanceEngine `strict` flag leak**: `openai.py` integration wraps the temporary
  `strict=False` output validation in `try/finally`, guaranteeing the flag is always
  restored even if `validate()` raises. Concurrent callers can no longer observe a
  permanently-disabled strict mode.

### Changed
- **JWT algorithm normalization unified** across `enhanced_agent_bus`, `collaboration`,
  and `enterprise_sso`: all JWT decode paths now use `resolve_jwt_algorithm()` from
  `src.core.shared.security.jwt_algorithms`, enforcing a canonical allowlist of
  `{RS256, RS384, RS512, ES256, ES384, EdDSA, HS256}`.
- **CapabilityPassport tier routing hardened**: T030-T032 integration tests cover
  override, tamper fail-closed, and no-passport fallthrough scenarios.

## [2.7.0] - 2026-04-06

### Added
- **`ViolationAction` enum** (`src/acgs_lite/constitution/rule.py`): Replaces the
  undocumented `workflow_action: str` hint-field with a proper `str, Enum` type.
  Values: `warn`, `block` (default), `block_and_notify`, `require_human_review`,
  `escalate_to_senior`, `halt_and_alert`.  Old string values are still accepted via
  Pydantic coercion; empty string `""` coerces to `BLOCK`.
- **Enforced dispatch in `GovernanceEngine.validate()`**: the engine now routes
  violations by `workflow_action` instead of purely by severity:
  - `WARN` — non-blocking; violation goes to `result.warnings`, not `result.violations`.
  - `BLOCK / BLOCK_AND_NOTIFY / REQUIRE_HUMAN_REVIEW / ESCALATE` — blocks when `strict=True`,
    recorded when `strict=False` (always in `result.violations`).
  - `HALT` — always raises `ConstitutionalViolationError`, ignores `strict=False`.
- **`ValidationResult.warnings`** field (was a severity-derived property): now a first-class
  `list[Violation]` field populated by the engine with WARN-action violations.
- **`ValidationResult.action_taken`**: new `ViolationAction | None` field recording which
  enforcement action was applied (`HALT`, `BLOCK`, `WARN`, or `None` for allow).
- **`ConstitutionalViolationError.enforcement_action`**: new `ViolationAction` attribute
  (default `BLOCK`; set to `HALT` for circuit-breaker raises).
- **`ViolationAction` exported** from `acgs_lite` and `acgs` top-level packages.

### Changed
- `Rule.workflow_action` default changed from `""` to `ViolationAction.BLOCK`.
  MEDIUM/LOW advisory rules should now set `workflow_action=ViolationAction.WARN` explicitly.
- CRITICAL rules with `workflow_action=WARN` skip the hot-path early-exit; they are
  collected and dispatched non-blockingly like any other WARN violation.
- `serialization.py` always emits `workflow_action` in YAML/bundle output (was omitted
  when empty).
- `conflict_resolution.py` / `constitution.py`: conflict detection no longer guards on
  `workflow_action != ""` (now meaningless since the field always has a value).
- `dependency_analysis._KNOWN_WORKFLOW_ACTIONS`: added `halt_and_alert`.

### Fixed
- `ruff` config changed from `exclude` to `extend-exclude` so default dotfile
  exclusions (`.git`, `.venv`, `.codex-home`, etc.) are preserved.
- CI `ruff format --check` failure on `examples/mcp_agent_client.py` (trailing
  whitespace + lines > 100 chars); file auto-formatted.
- Test assertion in `test_coverage_engine_extra.py` for PAT-MED
  (`MEDIUM` severity / `WARN` action): corrected `result.violations` →
  `result.warnings`.

### Tests
- 32 new tests in `tests/test_workflow_action.py` covering `ViolationAction` enum
  coercion, WARN dispatch, HALT circuit-breaker, `action_taken` field, and
  backward-compatible string values.
- **Total: 4,687 passing, 156 skipped** (suite-wide)

## [2.6.0] - 2026-04-05

### Added
- **Leanstral Formal Verification**: `LeanstralVerifier` generates Lean 4 proof certificates
  via Mistral, producing `ProofCertificate` with `.to_audit_dict()` for audit trail attachment.
  Requires `mistralai` extra. 32 tests.
- **Engine correctness**: `_validate_rust_no_context` and `_validate_rust_metadata_context`
  now raise `ConstitutionalViolationError` for `_RUST_DENY` blocking violations (HIGH severity
  in strict mode), closing a gap where Rust dispatch could silently pass HIGH violations.
- **74 new constitutional_swarm tests**: Deep coverage for DAG immutability, MACI enforcement,
  ArtifactStore integrity, CapabilityRegistry routing, concurrency safety, and compiler edge cases.
- **Documentation refresh**: New guides — 2026 compliance landscape, MCP integration, OWASP LLM
  Top 10 mapping, supervisor model patterns, testing governance, use-case catalogue.
- **Stability classifier**: Promoted from Beta → Production/Stable.

### Changed
- `pyproject.toml` description: clearer one-line summary of capabilities.
- Keywords expanded: added `llm-safety`, `agentic-firewall`, `formal-verification`,
  `z3`, `lean4`, `hipaa`, `gdpr`, `nist-ai-rmf`, `ai-act`, `responsible-ai`.
- README: full rewrite — comprehensive feature tour, integration examples,
  compliance table, performance benchmarks, CLI reference, formal verification examples.

### Fixed
- `deploy-clinicalguard.yml`: `_parse_skill` now correctly routes explicit-but-unknown
  skill prefixes to the helpful-error path instead of falling through to `validate_clinical_action`.
- CI: `deploy` steps gated on `env.FLY_API_TOKEN` presence; no more parse errors from
  invalid `secrets` context in job-level `if` conditions.
- `examples/mcp_agent_client.py`: pass `StdioServerParameters` object to `stdio_client`
  instead of a plain dict (mcp SDK no longer accepts dict for server params).

### Deferred to post-v2.6.0
- mypy strict errors in `integrations/` adapters (pre-existing, `ignore_errors = true`)
- bandit security warnings in example scripts (pre-existing)
- LaTeX paper PDF build in release workflow (requires full TeX Live; non-blocking)

## [2026.1.0] - 2026-04-05

### Added
- **2026 Governance Frameworks**: Native support for EU AI Act, Colorado SB 205, and Texas TRAIGA.
- **Agentic Firewall**: New high-performance deterministic engine for runtime action interception.
- **MCP Governance Hub**: Full Model Context Protocol server integration for centralized safety.
- **Verification Kernels**: Support for Z3 SMT formal verification and Lean 4 proof certificates.
- **Governance Circuit Breaker**: Automated halting of "rogue" agents based on violation thresholds.
- **Expanded Documentation**: New guides for 2026 regulatory compliance, OWASP Top 10 for agents, and advanced safety patterns.

### Changed
- **Package Name**: Standardized on `acgs-lite` for the core engine.
- **Architecture**: Refactored to a Zero-Trust architecture with mandatory MACI role separation.
- **Audit Backend**: Optimized `JSONLAuditBackend` with cryptographic chaining (SHA-256).
- **Integrations**: Updated Anthropic, OpenAI, and LangChain adapters for 2026 model release lines.

## [2.5.2] - 2026-04-05

### Added
- Open-source distribution scaffolding: MkDocs documentation site, CONTRIBUTING.md,
  SECURITY.md, CODE_OF_CONDUCT.md, GitHub Actions CI/CD, issue and PR templates
- Apache-2.0 license with Commons Clause

### Fixed
- Updated all package URLs to individual GitHub repositories
- Pinned Node 22 and uv 0.10.9 in eval-rules and GitLab CI

## [2.5.1] - 2026-04-04

### Added
- `to_decision_record()` for cross-layer governance evaluation
- Autonoma E2E scenario definitions and QA test tracking

### Fixed
- CI test failures in tenant context blocking, OIDC mocking, and audit chain validation

## [2.5.0] - 2026-04-03

### Added
- Self-evaluation architecture (Phases 0-3): decision schema, LLM judge, shadow cascade
- Constrained decoding engine (`acgs_lite.constrained_decoding`)
- Multi-framework compliance assessor covering 9 regulatory frameworks (125 items)
- EU AI Act one-shot assessment CLI command
- CrewAI integration adapter
- A2A (Agent-to-Agent) integration
- PDF report generation (`acgs-lite[pdf]`)
- OpenTelemetry export (`acgs otel`)
- Policy lifecycle management (`acgs lifecycle`)
- Governance denial explanation (`acgs refusal`)

### Changed
- Upgraded MACI enforcer with risk-level-based escalation paths
- Improved constitutional validation performance with memoization

## [2.4.0] - 2026-03-15

### Added
- GitLab CI/CD integration with merge request governance bot
- Google GenAI integration adapter
- LlamaIndex integration adapter
- AutoGen integration adapter
- Cloud Run deployment support
- Hackathon starter examples

### Changed
- Expanded compliance coverage to HIPAA + AI, GDPR Art. 22, ECOA/FCRA, NYC LL 144

## [2.3.0] - 2026-02-20

### Added
- MCP Server integration (`acgs-lite[mcp]`)
- LiteLLM integration adapter
- ASGI/FastAPI governance middleware
- Batch validation support
- Constitutional merge and diff helpers

### Changed
- Improved audit trail with SHA-256 chain verification

## [2.2.0] - 2026-01-15

### Added
- LangChain integration (`GovernanceRunnable`)
- Constitution templates (`general`, `gitlab`)
- `ConstitutionBuilder` fluent API
- CLI: `acgs init`, `acgs lint`, `acgs test`

## [2.1.0] - 2025-12-01

### Added
- OpenAI integration adapter
- Anthropic integration adapter
- YAML constitution loading
- Severity levels (CRITICAL, HIGH, MEDIUM, LOW)

## [2.0.0] - 2025-10-15

### Added
- Initial public release
- `GovernedAgent` wrapper with constitutional validation
- `GovernanceEngine` with deterministic rule matching
- MACI role separation enforcement
- Tamper-evident audit trail
- CLI tool (`acgs` / `acgs-lite`)
- Keyword-based and regex rule matching

[2.5.2]: https://github.com/dislovelhl/acgs-lite/compare/v2.5.1...v2.5.2
[2.5.1]: https://github.com/dislovelhl/acgs-lite/compare/v2.5.0...v2.5.1
[2.5.0]: https://github.com/dislovelhl/acgs-lite/compare/v2.4.0...v2.5.0
[2.4.0]: https://github.com/dislovelhl/acgs-lite/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/dislovelhl/acgs-lite/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/dislovelhl/acgs-lite/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/dislovelhl/acgs-lite/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/dislovelhl/acgs-lite/releases/tag/v2.0.0
