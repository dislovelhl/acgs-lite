# Changelog

All notable changes to acgs-lite will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
