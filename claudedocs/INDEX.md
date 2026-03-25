# ACGS-2 Project Index

> Generated: 2026-03-20 | Branch: `main` | Constitutional Hash: `608508a9bd224290`

## Overview

ACGS (Advanced Constitutional Governance System) — constitutional governance infrastructure for AI agents. Three domains: a standalone governance library, a platform engine with 80+ subsystems, and shared core services.

---

## Repository Structure

```
acgs-clean/
├── packages/
│   ├── acgs-lite/              # Standalone governance library (v0.2.0)
│   └── enhanced_agent_bus/     # Platform engine (80+ subsystems)
├── src/core/
│   ├── services/api_gateway/   # FastAPI REST API (port 8080)
│   └── shared/                 # Types, errors, security, auth, config (188 files)
├── tests/                      # Root-level test infrastructure
├── scripts/                    # Build/deploy scripts
├── autoresearch/               # Governance quality experiments
├── sdk/                        # SDK artifacts
├── runtime/                    # Runtime execution
├── tools/                      # Developer tooling
├── .github/workflows/          # CI/CD (lint, test-quick, test-full)
├── pyproject.toml              # Root workspace (uv, Python 3.11+)
├── Makefile                    # make test, lint, format, bench
├── ecosystem.config.cjs        # PM2 definitions for checked-in local services
├── docker-compose.yml          # Redis, OPA, agent-bus, api-gateway
├── conftest.py                 # Root pytest config (auto-sets ACGS2_SERVICE_SECRET)
└── CLAUDE.md                   # AI agent instructions
```

---

## Package 1: acgs-lite

**Path:** `packages/acgs-lite/` | **Tests:** 460+ across 16 files | **Rust P50:** 560ns

### Public API

```python
from acgs_lite import Constitution, GovernedAgent, GovernanceEngine
from acgs_lite import MACIRole, MACIEnforcer, AuditLog
from acgs_lite import ConstitutionalViolationError, set_license
```

### Module Map

| Module | Files | Purpose |
|--------|-------|---------|
| `constitution/` | 89 | Core rules, ABAC, analytics, versioning, 77 lazy-loaded modules |
| `engine/` | 4 | GovernanceEngine, batch validation, Rust fallback |
| `compliance/` | 11 | GDPR, HIPAA, ISO 42001, NIST, NYC LL144, OECD, SOC2, US Fair Lending |
| `eu_ai_act/` | 6 | Article 12, risk classification, human oversight, 125-item checklist |
| `integrations/` | 14 | OpenAI, Anthropic, LangChain, LlamaIndex, AutoGen, CrewAI, GitLab, MCP |
| `maci.py` | 1 | MACI role enforcement (1,201 lines) |
| `governed.py` | 1 | GovernedAgent & GovernedCallable wrappers |
| `matcher.py` | 1 | Rule matching engine |
| `middleware.py` | 1 | Governance middleware stack |
| `audit.py` | 1 | Tamper-evident audit trail |
| `licensing.py` | 1 | License tiers & activation |
| `rust/` | 8 .rs | PyO3 native extension (optional, 100-1000x speedup) |

### Key Features
- Constitutional rule validation (560ns P50 with Rust)
- MACI enforcement (Proposer/Validator/Executor separation)
- 9 regulatory compliance frameworks
- 11 LLM framework integrations
- Policy simulation, fuzzing, semantic search
- GitLab webhook governance

---

## Package 2: enhanced_agent_bus

**Path:** `packages/enhanced_agent_bus/` | **Tests:** 3,534 across 387 files | **Subsystems:** 60+

### Subsystem Architecture (by Layer)

#### Layer 0-1: Constitutional Governance
| Subsystem | Files | Purpose |
|-----------|-------|---------|
| `constitutional/` | 18 | Self-evolving constitutions, amendments, rollback, HITL, OPA |
| `adaptive_governance/` | 8 | ML-based governance: DTMC learner, impact scoring, amendments |
| `governance/` | 5 | CCAI democratic framework, Polis-style deliberation |
| `maci/` | 8 | Maker-Approver-Checker-Inspector role enforcement |
| `compliance_layer/` | 9 | NIST RMF, SOC 2, EU AI Act compliance |

#### Layer 2: Deliberation & Safety
| Subsystem | Files | Purpose |
|-----------|-------|---------|
| `deliberation_layer/` | 26 | Event-driven voting, Redis pub/sub, ONNX impact scoring |
| `guardrails/` | 13 | OWASP safety: sandbox execution, input sanitization, audit |
| `circuit_breaker/` | 11 | Resilience patterns, Prometheus metrics, fallback |

#### Layer 3: Agent Health & Verification
| Subsystem | Files | Purpose |
|-----------|-------|---------|
| `agent_health/` | 8 | Anomaly detection, autonomous healing, governed recovery |
| `verification_layer/` | 9 | Constitutional & policy verification |
| `verification/` | 6 | Generic validators |

#### Layer 4: Context & Memory
| Subsystem | Files | Purpose |
|-----------|-------|---------|
| `context_memory/` | 8 | Mamba-2 hybrid processor (4M+ tokens), constitutional cache |
| `batch_processor_infra/` | 7 | Batch queuing & concurrency |
| `persistence/` | 7 | Durable workflows, replay engine, saga compensation |
| `saga_persistence/` | 6 | Distributed saga state (Redis/PostgreSQL) |

#### Layer 5: Observability
| Subsystem | Files | Purpose |
|-----------|-------|---------|
| `observability/` | 7 | OpenTelemetry, Prometheus, structured logging |
| `profiling/` | 3 | Performance analysis |

#### Orchestration & Coordination
| Subsystem | Files | Purpose |
|-----------|-------|---------|
| `orchestration/` | 3 | Hierarchical & market-based orchestration |
| `langgraph_orchestration/` | 10 | LangGraph agent workflows |
| `meta_orchestrator/` | 6 | Cross-subsystem orchestration |
| `coordinators/` | 8 | Task distribution & sync |

#### LLM & External Integration
| Subsystem | Files | Purpose |
|-----------|-------|---------|
| `llm_adapters/` | 14 | Multi-provider LLM (OpenAI, Anthropic, Bedrock, HuggingFace) |
| `ai_assistant/` | 9 | NLU, dialog management, governance-integrated AI |
| `mcp_server/` | 4 | Model Context Protocol server |
| `mcp_integration/` | 6 | MCP client integration |

#### Enterprise
| Subsystem | Files | Purpose |
|-----------|-------|---------|
| `enterprise_sso/` | 16 | SAML 2.0/OIDC, MACI role mapping, tenant-aware sessions |
| `multi_tenancy/` | 12 | PostgreSQL RLS, quota management |
| `acl_adapters/` | 5 | Fine-grained authorization |

#### Data & ML
| Subsystem | Files | Purpose |
|-----------|-------|---------|
| `online_learning_infra/` | 10 | Online learning pipeline |
| `ab_testing_infra/` | 5 | Experimentation framework |
| `data_flywheel/` | 2 | Continuous feedback loops |

#### Specialized
| Subsystem | Files | Purpose |
|-----------|-------|---------|
| `collaboration/` | 7 | Real-time multi-user (presence, cursor sync, OT) |
| `swarm_intelligence/` | 8 | Swarm-based multi-agent coordination |
| `chaos/` | 4 | Chaos engineering framework |
| `cognitive/` | 4 | Cognitive modeling & reasoning |
| `policy_copilot/` | 3 | AI-assisted policy creation |

#### Cross-Cutting
| Subsystem | Files | Purpose |
|-----------|-------|---------|
| `bus/` | 8 | Core EnhancedAgentBus (messaging, batch, governance) |
| `api/` | 11 | FastAPI REST API (port 8000) |
| `middlewares/` | 9 | Session, security, MACI enforcement |
| `exceptions/` | 8 | Unified exception hierarchy |
| `validators/` | 4 | MACI & constitutional hash validators |

---

## Shared Core: src/core/

**Path:** `src/core/` | **Files:** 234

### src/core/shared/ (188 files)

| Module | Files | Purpose |
|--------|-------|---------|
| `security/` | 62 | JWT, OIDC, SAML, PQC, rate limiting, GDPR/CCPA, secret rotation |
| `auth/` | 15 | OIDC handler, SAML assertions, WorkOS, provisioning |
| `config/` | 15 | Settings, profiles, tenant-aware config, env overrides |
| `cache/` | 9 | L1 in-memory + Redis, cache warming, workflow state |
| `event_schemas/` | 7 | Agent messages, audit, circuit breaker, validation events |
| `errors/` | 6 | Custom exceptions, context poisoning, retry, circuit breaker |
| `types/` | 5 | Agent, governance, JSON, protocol types |
| `policy/` | 5 | Policy models, YAML generation, verification |
| `database/` | 4 | SQLAlchemy async, N+1 detection |
| `metrics/` | 4 | Prometheus registry, rate-of-change scaling |
| `acgs_logging/` | 3 | structlog setup, audit logger |
| `resilience/` | 2 | Retry with exponential backoff |

### src/core/services/api_gateway/ (46 files)

**Port:** 8080 | **Routes prefix:** `/api/v1/`

| Route Group | Endpoints |
|-------------|-----------|
| Health | `/health`, `/health/live`, `/health/ready` |
| Auth | OIDC, SAML, WorkOS login/logout/callbacks |
| Admin | SSO config, WorkOS setup, autonomy tier management |
| Governance | Decision explanation (FR-12), data subject rights, compliance |
| Self-Evolution | Bounded experiments, operator control (pause/resume/stop) |
| PQC Phase 5 | Post-quantum only mode activation |
| x402 | Pay-per-call governance (pricing, validate, health) |
| Catch-all | `/{path:path}` reverse proxy to agent-bus (port 8000) |

**Rate Limits:** Auth=10/min, SSO=5/min, Health=6000/min, Default=1000/min

---

## Services (PM2)

The checked-in `ecosystem.config.cjs` currently starts only the services with real launchers in
this repo snapshot.

| Service | Port | Purpose |
|---------|------|---------|
| agent-bus | 8000 | Core bus: MACI, constitutional validation |
| api-gateway | 8080 | Auth, rate limiting, routing |

---

## Testing

| Suite | Command | Tests |
|-------|---------|-------|
| Full | `make test` | ~3,820 |
| Quick | `make test-quick` | excludes `@slow` |
| acgs-lite | `make test-lite` | 286 |
| agent-bus | `make test-bus` | 3,534 |
| API gateway | `make test-gw` | ~46 |

**Markers:** `unit`, `integration`, `slow`, `constitutional`, `benchmark`, `governance`, `security`, `maci`, `chaos`, `pqc`, `e2e`, `compliance`

**Required flag:** `--import-mode=importlib`

---

## Architecture Invariants

1. **MACI Separation of Powers** — Agents NEVER validate their own output (Proposer → Validator → Executor)
2. **Constitutional Hash** — `608508a9bd224290` embedded in all validation paths
3. **Import Paths** — Use `enhanced_agent_bus.*` directly (never `src.core.enhanced_agent_bus.*`)
4. **Canonical Paths** — `middlewares/` (plural), `context_memory/`, `persistence/`
5. **Async-First** — `async def` for all I/O operations
6. **structlog Only** — Never `print()` in production
7. **Pydantic Boundaries** — Pydantic models at all API boundaries

---

## Recent History

```
c3b421f exp03: add tests for 5 high-miss modules (+366 tests)
7adb04d exp02: add tests for 5 more zero-coverage modules (+293 tests)
35871c4 refactor: improve project foundation — CI, pre-commit, decompose large files
7e1e5bf exp01: add tests for 5 zero-coverage modules (+393 tests)
fa8021d fix: resolve final 23 test failures — full suite now green (20,676 pass)
8f5b33b feat: add dev-agent governance infrastructure
```

---

## Cross-References

- [CLAUDE.md](/CLAUDE.md) — AI agent instructions (root)
- [packages/acgs-lite/CLAUDE.md](/packages/acgs-lite/CLAUDE.md) — acgs-lite specifics
- [packages/enhanced_agent_bus/CLAUDE.md](/packages/enhanced_agent_bus/CLAUDE.md) — agent-bus specifics
- [claudedocs/research_acgs_codebase_deep_dive_20260318.md](/claudedocs/research_acgs_codebase_deep_dive_20260318.md) — Deep dive research
- [claudedocs/design_enhanced_agent_bus_decomposition_20260318.md](/claudedocs/design_enhanced_agent_bus_decomposition_20260318.md) — Bus decomposition design
