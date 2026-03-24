# ACGS Codebase Deep Dive Research Report

**Date:** 2026-03-18
**Branch:** skill-evolve/skill-create-v2
**Depth:** Exhaustive (4 parallel research agents)
**Confidence:** HIGH (direct source code analysis)

---

## Executive Summary

ACGS (Advanced Constitutional Governance System) is a **339K-line Python/Rust/TypeScript monorepo** implementing constitutional governance infrastructure for AI agents. The system enforces a **MACI (Montesquieu-Inspired) separation of powers** (Proposer/Validator/Executor) with a cryptographic constitutional hash (`cdd01ef066bc6cf2`) embedded across all validation paths.

**Key Metrics:**
| Metric | Value |
|--------|-------|
| Total Python LoC | ~339,000 |
| Test count | ~3,820 |
| Packages | 5 (acgs-lite, enhanced-agent-bus, api-gateway, propriety-ai, SDK) |
| Rust extension | PyO3, P50 = 560ns validation |
| Compliance frameworks | 9 implemented |
| LLM integrations | 14 adapters |
| Extension modules | 15 optional |
| API routes | 30+ endpoints |

**Overall Assessment:** Production-quality governance engine with strong security fundamentals, but architectural debt in the enhanced-agent-bus package (237K lines in one package) and 2 critical security findings that need immediate attention.

---

## 1. Package Architecture

### 1.1 acgs-lite (49K LoC) — The Public API

**Entry Points:**
```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")
```

**Structure:**
- `Constitution` class (constitution.py, 4,120 lines) — Pydantic model with 6 factory methods: `from_yaml()`, `from_yaml_str()`, `from_rules()`, `default()`, `from_template()`, `from_rules_with_metadata()`
- `GovernedAgent` (governed.py, 246 lines) — Wraps any agent with pre/post validation + audit trail
- `ValidationEngine` (engine/core.py, 1,579 lines) — Three-tier matching: Aho-Corasick → Keyword Index → Bloom Filter
- `MACI` (maci.py, 1,201 lines) — Four roles: Proposer, Validator, Executor, Observer with action-risk routing

**Rust Backend (6 modules):**
- `validator.rs` — Aho-Corasick automaton for O(N) keyword scanning + anchor-dispatch to regex
- `severity.rs`, `verbs.rs`, `result.rs`, `context.rs`, `hash.rs`
- Performance: 560ns P50 validation (100-1000x faster than Python fallback)

**80+ Submodules via Lazy Registry:**
The `constitution/__init__.py` uses `__getattr__` with a `_LAZY_REGISTRY` mapping 80+ symbols across 5 domains (core, lifecycle, enforcement, monitoring, analysis). Symbols are imported on first access only.

**Compliance Frameworks (9):**
ISO 42001, NIST AI RMF, SOC 2, GDPR, HIPAA, EU AI Act, OECD AI, NYC LL 144, US Fair Lending. Each implements a `ComplianceFramework` protocol with checklist items and gap analysis.

**Integration Adapters (14):**
GitLab (868 LoC), Anthropic (444), MCP Server (278), Cloud Run (269), A2A (261), LlamaIndex (243), Google GenAI (225), AutoGen (223), LiteLLM (201), LangChain (189), Cloud Logging (187), OpenAI, plus others.

### 1.2 enhanced-agent-bus (237K LoC) — The Platform Engine

**Core Bus** (`bus/core.py`):
- Redis-backed message passing with multi-tenant isolation
- Composable DI: RegistryManager, GovernanceValidator, MessageRouter, MessageProcessor
- Rate limiting via SlidingWindowRateLimiter
- Circuit breaker integration
- MACI strict mode enforcement (default: True)

**MACI Enforcer** (`maci/enforcer.py`):
- Trias Politica enforcement preventing Godel bypass attacks
- `validate_action()` checks: agent registration → role permissions → self-validation prevention → cross-role constraints
- Exception types: MACIRoleNotAssignedError, MACIRoleViolationError, MACISelfValidationError, MACICrossRoleValidationError

**Governance Middleware** (`middlewares/batch/governance.py`, 1,040 lines):
The actual enforcement point. Four-stage pipeline:
1. `_execute_maci_validation()` — Check role permissions
2. `_execute_tenant_validation()` — Verify tenant isolation
3. `_execute_impact_validation()` — Score governance risk (thresholds: 0.3/0.5/0.7/0.9)
4. `_execute_constitutional_validation()` — Verify invariant compliance

Request-scoped caching: `(tenant_id, agent_id, action_type, content_type) → bool`

**Constitutional Subsystem** (`constitutional/`):
- InvariantClassifier — stateless path-based classification, fail-closed on empty manifest
- ProposalInvariantValidator — prevents HARD/META invariant modifications
- RuntimeMutationGuard — prevents runtime mutations of MACI registry, constitutional hash
- RollbackEngine — refoundation protocol for constitutional changes

**Adaptive Governance** (`adaptive_governance/governance_engine.py`, 1,273 lines):
ML-based self-evolution with:
- ImpactScorer (ML risk prediction)
- AdaptiveThresholds (dynamic adjustment)
- DriftDetector (distribution shift monitoring)
- OnlineLearningPipeline (River ML continuous learning)
- AmendmentRecommender
- DTMCLearner (Discrete-time Markov chain)

**15 Extension Modules** (`_ext_*.py`):
MCP, persistence, PQC, circuit breaker, context memory, cognitive architecture, LangGraph, cache warming, chaos engineering, performance profiling, context optimization, decision store, explanation service, response quality, circuit breaker clients. All use try/except with `_AVAILABLE` flags.

**77 Subsystem Directories** organized across: governance, communication, infrastructure, learning, agents, external integrations, security, observability, data models.

### 1.3 API Gateway (53K LoC)

**Entry Point:** `src/core/services/api_gateway/main.py` (1,110 lines), FastAPI on port 8080

**Middleware Stack** (ordered):
1. GZipMiddleware (1KB threshold)
2. APIVersioningMiddleware
3. DeprecationNoticeMiddleware
4. RateLimitMiddleware (Redis-backed)
5. SessionMiddleware (SAML/OAuth state)
6. PQCOnlyModeMiddleware
7. AutonomyTierEnforcementMiddleware
8. UsageMeteringMiddleware
9. Security headers

**Authentication:**
- JWT: RS256, RS384, RS512, ES256, ES384, EdDSA, HS256
- `UserClaims` model binds `constitutional_hash` to every token
- SSO: OIDC + SAML + WorkOS

**Rate Limiting Hierarchy:**
- Auth: 10 req/min
- SSO login: 5 req/min
- Policies: 100 req/min
- Validation: 5,000 req/min
- Default: 1,000 req/min

**Routes (30+):**
Health, feedback, SSO, governance, autonomy tiers, decisions, data subject rights, compliance, audit, evolution control, PQC admin, billing, x402 payment governance, plus catch-all proxy to agent-bus.

### 1.4 Frontend — propriety-ai

React 19 + Vite + TypeScript + Tailwind + Radix UI + Framer Motion + React Three Fiber.
Pages: Home, Dashboard, Assessment, Pricing, About, Compliance, Privacy.

### 1.5 TypeScript SDK

`ACGSClient` class with sub-APIs: `governance`, `audit`, `health`, `policies`.
Type-safe with Zod validation, fetch-based HTTP client with timeout/retry.

---

## 2. Security Findings

### CRITICAL

**C-1. MACI Non-Strict Mode Bypass** (`maci/enforcer.py:112-122`)
When `strict_mode=False`, unregistered agent_ids bypass ALL MACI checks — `validate_action()` returns `is_valid=True`. Completely undermines separation of powers. An attacker can use a fabricated agent_id.

**C-2. Service Auth Environment Variable Mismatch** (`shared/security/service_auth.py:35-40`)
Checks `ACGS2_ENV` but application uses `ENVIRONMENT`. If `ENVIRONMENT=production` but `ACGS2_ENV` unset → hardcoded dev secret `"dev-service-secret-32-bytes-minimum-length"` used in production.

### HIGH

**H-1.** JWT token revocation module exists but not integrated into auth flow — revoked tokens valid until expiry
**H-2.** Feedback endpoint stores raw IP addresses in Redis with 90-day TTL (GDPR PII)
**H-3.** Catch-all proxy uses header blocklist instead of allowlist — internal headers can be injected
**H-4.** OIDC pending states stored in unbounded memory dict — DoS via login flow flooding

### MEDIUM

**M-1.** Redis defaults to non-TLS, production only warns
**M-2.** Subprocess Dafny path not validated (potential binary injection)
**M-3.** License HMAC has public default secret
**M-4.** Exception chains may propagate internal details
**M-5.** Constitutional hash is static, not cryptographically verified at startup

### Positive Security Patterns
- JWT validates issuer, audience, constitutional hash, JTI, expiration
- CORS blocks wildcard origins in production
- CSP, HSTS, X-Frame-Options DENY, X-Content-Type-Options
- Production guards enforce JWT secret >= 32 chars
- Proxy has path traversal protection with regex allowlist
- No unsafe deserialization found
- No real secrets committed
- MACI properly prevents self-validation in strict mode
- Pydantic validation on all API models

---

## 3. Code Quality Analysis

### File Size Violations (>800 lines, project style guide)

**acgs-lite (6 files):**
- `constitution.py` — 4,120 lines (monolithic domain model)
- `engine/core.py` — 1,579 lines
- `metrics.py` — 1,428 lines
- `maci.py` — 1,201 lines
- `amendments.py` — 802 lines
- `gap_analyzer.py` — 767 lines

**enhanced-agent-bus (19+ files over 1,000 lines):**
- `routes/tenants.py` — 1,437 lines
- `deliberation_layer/impact_scorer.py` — 1,412 lines
- `deliberation_layer/integration.py` — 1,299 lines
- `adaptive_governance/governance_engine.py` — 1,273 lines
- `response_quality.py` — 1,238 lines
- `constitutional/rollback_engine.py` — 1,215 lines
- `bundle_registry.py` — 1,177 lines
- `enterprise_sso/saga_orchestration.py` — 1,157 lines
- `message_processor.py` — 1,156 lines
- Plus 10 more files between 1,000-1,100 lines

### Coverage Threshold

`fail_under = 30` in pyproject.toml — far too low for a governance-critical system.

### mypy Exclusion

The entire enhanced-agent-bus package (237K lines, the largest package) is excluded from mypy static type checking.

### Test Distribution

| Package | Test Files | Source Files | Ratio |
|---------|-----------|-------------|-------|
| enhanced-agent-bus | 543 | 714 | 0.76 |
| api-gateway | 52 | ~100 | 0.52 |
| acgs-lite | 16 | ~187 | 0.09 |

acgs-lite test file ratio is notably low.

### Positive Quality Patterns
- Immutability: Frozen dataclasses, NamedTuples, Pydantic `frozen=True`
- Structured logging: `get_logger()` used in 414+ files, no `print()`
- Factory + lazy imports pattern
- Protocol/runtime_checkable for interfaces
- Custom error types with clear semantics
- Request-scoped caching in hot paths
- Audit chain integrity (hash-chained entries)

---

## 4. Architectural Observations

### Strengths

1. **MACI Separation of Powers** — Genuine innovation. Three-role enforcement at middleware level prevents agents from validating their own output. Constitutional hash binding in JWT tokens ensures governance is cryptographically tied to every operation.

2. **acgs-lite API Design** — Clean two-entry-point public API (Constitution + GovernedAgent). Lazy-loading of 80+ submodules. Rust backend for hot paths. Well-factored.

3. **Multi-Tier Validation** — Aho-Corasick → Keyword Index → Bloom Filter → Regex provides excellent performance/accuracy tradeoff.

4. **Compliance Breadth** — 9 regulatory frameworks, 14 LLM integrations, 15 extension modules. Serious enterprise coverage.

5. **Test Infrastructure** — 3,820 tests, 12 markers, Hypothesis property testing, singleton reset fixtures, test reordering for isolation.

### Weaknesses

1. **enhanced-agent-bus is a Monolith** — 237K lines, 77 directories, 714 files in one Python package. Mixes SSO, deliberation, LLM adapters, messaging, billing concepts. Needs domain-driven decomposition.

2. **No Formal Requirements Document** — For a system that provides constitutional governance to AI, having no SRS/PRD is a significant gap. Key semantics (constitutional hash derivation, update protocol, failure modes) are undocumented.

3. **Thin Container/Deployment Infrastructure** — The repo has local `docker-compose.yml` and PM2 support, but the checked-in PM2 config now covers only two launchable local services (`agent-bus-8000` and `api-gateway-8080`). This is still insufficient for the stated commercialization goal.

4. **Extension Module Fragility** — 15 `_ext_*.py` modules all use try/except with stub fallbacks. No runtime capability manifest. Different deployments silently have different feature sets.

5. **Static Constitutional Hash** — `cdd01ef066bc6cf2` appears in 200+ files but its derivation from actual rules is not verified at startup. A tampered deployment could bypass governance.

---

## 5. Key Design Patterns

| Pattern | Where | Assessment |
|---------|-------|------------|
| MACI Separation of Powers | maci/enforcer.py, middlewares/batch/governance.py | Core innovation, well-implemented in strict mode |
| Constitutional Hash Binding | JWT claims, API headers, health metrics | Good concept, needs startup verification |
| Lazy Registry Loading | constitution/__init__.py (80+ symbols) | Excellent for import performance |
| Aho-Corasick + Regex | engine/core.py, rust/validator.rs | Optimal for pattern matching workload |
| Fail-Closed Defaults | Throughout security paths | Correct posture for governance system |
| Request-Scoped Caching | governance.py (MACI decisions) | Good performance optimization |
| Saga Persistence | enterprise_sso/saga_orchestration.py | Correct for long-running workflows |
| Adaptive Thresholds | adaptive_governance/ | Novel ML-based governance evolution |
| Hash-Chained Audit | audit.py, audit_trail.py | Tamper-evident audit trail |

---

## 6. Dependency Analysis

### Python Dependencies (pyproject.toml)
**Core:** FastAPI, httpx, Pydantic, Redis, structlog, prometheus-client, PyJWT, orjson, cachetools, pybreaker, slowapi, msgpack, PyYAML, psutil, jsonschema, click
**Test:** pytest, pytest-cov, pytest-xdist, pytest-asyncio, pytest-timeout, pytest-mock, pytest-benchmark, fakeredis, hypothesis, respx, aiosqlite
**Optional:** numpy/scikit-learn/pandas (ML), liboqs-python/cryptography (PQC), asyncpg/sqlalchemy (Postgres)

### Cross-Package Imports
enhanced-agent-bus → src.core.shared (types, redis, metrics, security, utilities)
api-gateway → enhanced-agent-bus (proxied), src.core.shared

### External Service Dependencies
- Redis (rate limiting, caching, PQC flags, feedback storage)
- PostgreSQL/SQLite (tier assignments)
- OPA (policy evaluation)
- HITL service (autonomy tier enforcement, port 8002)
- Stripe (billing)
- WorkOS (SSO)
- EVM/x402 (payment governance)

---

## 7. Recommendations

### Immediate (P0)
1. Fix MACI non-strict bypass (C-1) — unregistered agents must always be denied
2. Fix service auth env var mismatch (C-2)
3. Integrate token revocation into auth flow (H-1)
4. Raise coverage threshold from 30% to 60%+

### Short-Term (P1)
5. Switch proxy header filtering to allowlist (H-3)
6. Hash/anonymize IP in feedback storage (H-2)
7. Add TTL + max_size to OIDC pending states (H-4)
8. Add startup constitutional hash verification (M-5)
9. Create runtime capability manifest for _ext_* modules

### Medium-Term (P2)
10. Begin enhanced-agent-bus decomposition (SSO, deliberation, LLM adapters as separate packages)
11. Create Dockerfiles and docker-compose
12. Enable mypy for enhanced-agent-bus (gradual)
13. Write formal requirements for MACI invariants

### Long-Term (P3)
14. Kubernetes deployment manifests
15. Replace _ext_* try/except with plugin registry
16. BDD executable specifications for governance invariants
17. Unified observability specification (metrics catalog, alert rules)

---

## Sources

All findings based on direct source code analysis of:
- `/home/martin/Documents/acgs-clean/packages/acgs-lite/` (187 files)
- `/home/martin/Documents/acgs-clean/packages/enhanced_agent_bus/` (714+ files)
- `/home/martin/Documents/acgs-clean/src/core/` (100+ files)
- `/home/martin/Documents/acgs-clean/propriety-ai/` (frontend)
- `/home/martin/Documents/acgs-clean/sdk/typescript/` (SDK)
- `/home/martin/Documents/acgs-clean/pyproject.toml` (root config)
