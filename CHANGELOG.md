# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] — 2026-03-21

### 🚀 First stable release

ACGS-Lite 1.0.0 is the first stable, production-ready release of constitutional governance
infrastructure for AI agents. Five lines of code. Nine regulatory frameworks. Zero false negatives.

---

### Added

#### Core
- `GovernedAgent` wrapper — drop-in constitutional governance for any LLM agent
- `Constitution.from_yaml()` / `Constitution.from_template()` — declarative rule authoring
- MACI (Multi-Agent Constitutional Infrastructure) enforcement — separation of powers at the agent boundary
- SHA-256-chained tamper-evident audit log — every decision verifiable in sequence
- HITL (Human-in-the-loop) escalation with configurable SLA metadata
- 125-item EU AI Act conformity checklist, auto-generated from audit log
- Nine regulatory framework mappings: EU AI Act, NIST RMF, ISO 42001, HIPAA, GDPR, SOC 2, Colorado AI Act, Singapore PDPA, Australia AI Ethics Framework

#### Integrations (11)
- `acgs-lite[openai]` — governed drop-in for `OpenAI()` client
- `acgs-lite[anthropic]` — governed Claude client
- `acgs-lite[langchain]` — LangChain chain and agent governance wrapper
- `acgs-lite[litellm]` — multi-provider governance via LiteLLM
- `acgs-lite[google]` — governed Gemini / Google GenAI client
- `acgs-lite[llamaindex]` — query engine governance for LlamaIndex
- `acgs-lite[autogen]` — multi-agent governance for AutoGen
- `acgs-lite[crewai]` — crew task governance for CrewAI
- `acgs-lite[mcp]` — Model Context Protocol server (5 tools: validate_action, get_constitution, get_audit_log, check_compliance, governance_stats)
- `acgs-lite[a2a]` — Google Agent-to-Agent (A2A) protocol support
- `acgs-lite[xai]` — xAI / Grok integration

#### GitLab Integration
- `GitLabGovernanceBot` — webhook handler for MR governance
- `GitLabWebhookHandler` — inline diff comments on constitutional violations
- CI/CD pipeline governance gate (`.gitlab-ci.yml` stage)
- MACI enforcement: MR author cannot approve their own MR when AI agents are involved

#### x402 Pay-Per-Call API
- `/x402/validate` — per-action constitutional validation ($0.01/call)
- `/x402/scan` — constitutional scan without decision ($0.03/call)
- `/x402/governance` — full governance suite endpoints
- `/x402/marketplace` — premium governance endpoints with cross-sell funnel
- `x402_revenue.jsonl` — local revenue audit log
- Cloudflare Worker governance proxy (`workers/governance-proxy/`)

#### Enhanced Agent Bus (packages/enhanced_agent_bus)
- MACI enforcement layer
- LLM adapter matrix: OpenAI, Azure OpenAI, OpenClaw, xAI
- Context memory submodule
- OPA client integration
- Observability and middleware layers
- Workflow routes API
- Enterprise SSO saga orchestration
- Postgres persistence repository

#### Constitutional Swarm (packages/constitutional_swarm)
- New package: swarm-level constitutional governance across agent collectives

#### MHC (packages/mhc)
- Replaces and consolidates omalhc package
- Mesh orchestration with constitutional constraints
- Swarm management

#### Infrastructure
- `cloudbuild.yaml` — Google Cloud Build pipeline
- `ecosystem.config.cjs` — PM2 process management for all services
- `workspace.dsl` — Structurizr architecture diagrams
- `constitutional-sentinel-demo/` — live demo harness
- Cloudflare Worker WASM validator

#### Autoresearch
- 244–248 experiment log with ceiling detection
- Automated benchmark harness across 532 governance scenarios

### Changed
- Constitution refactored: 32 methods extracted into 7 focused modules
- `Constitution.from_template()` — template data fully extracted and parameterized
- `merging_advanced.py` consolidated into `merging.py`
- Enhanced Agent Bus API restructured with explicit route modules
- `AGENTS.md` and `CLAUDE.md` updated across all packages with current architecture

### Removed
- `packages/omalhc/` — consolidated into `packages/mhc/`
- `src/acgs_lite/` — stale duplicate removed (53 files)
- Unused imports from `constitution.py`, LLM adapters, and coverage tests
- Rust build artifacts from git tracking

### Fixed
- 9 ruff E501 line-length violations in refactored modules
- PyO3 Rust fallback path coverage (71%)
- Torch mocking stability in batch25e coverage tests
- Azure OpenAI adapter typing and docstrings
- Intent classifier test isolation

---

## [0.2.0] — 2026-03-01

Initial beta release. Core Constitution engine, MACI enforcement, audit logging, and GitLab integration.
