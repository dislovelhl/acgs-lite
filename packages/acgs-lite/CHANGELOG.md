# Changelog

All notable changes to acgs-lite will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
