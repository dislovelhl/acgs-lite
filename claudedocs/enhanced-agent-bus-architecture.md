# Enhanced Agent Bus — Architecture Reference

**Package**: `enhanced_agent_bus` (`packages/enhanced_agent_bus/`)
**Entry point**: `enhanced_agent_bus.api.app:app`
**Port**: 8000
**Version**: 2.0.0
**Constitutional hash**: `cdd01ef066bc6cf2`
**Test suite**: 3,534 tests (`python -m pytest packages/enhanced_agent_bus/tests/ -v --import-mode=importlib`)
**Performance targets**: P99 < 0.103 ms | throughput > 5,066 RPS | memory < 5 MB / 1,000 messages

---

## Table of Contents

1. [Overview](#1-overview)
2. [Governance Pipeline](#2-governance-pipeline)
3. [Subsystem Reference](#3-subsystem-reference)
4. [MACI Enforcement](#4-maci-enforcement)
5. [Constitutional Amendment Flow](#5-constitutional-amendment-flow)
6. [Deliberation Layer](#6-deliberation-layer)
7. [Agent Health and Healing](#7-agent-health-and-healing)
8. [Observability](#8-observability)
9. [Persistence and Saga](#9-persistence-and-saga)
10. [Enterprise Features](#10-enterprise-features)
11. [Extension Points](#11-extension-points)
12. [Configuration Reference](#12-configuration-reference)

---

## 1. Overview

The Enhanced Agent Bus is the platform engine for ACGS-2 (Advanced Constitutional Governance System). It provides constitutional governance infrastructure for multi-agent systems: every message that flows through the bus is subject to constitutional validation, MACI role enforcement, and OPA policy evaluation before it reaches a handler.

The bus is not a simple message broker. It enforces a separation of powers between agents, prevents self-validation (Gödel bypass), runs deliberative consensus on high-impact decisions, and provides durable execution with saga compensation. All of this runs inside a FastAPI service with multi-tenant isolation, structured logging, and full OpenTelemetry instrumentation.

**Import convention**: Always use `from enhanced_agent_bus.*`. The `src.core.enhanced_agent_bus.*` path is a legacy alias maintained for backward compatibility only; do not use it in new code.

```python
from enhanced_agent_bus.models import Priority
from enhanced_agent_bus.agent_bus import EnhancedAgentBus
from enhanced_agent_bus.maci.enforcer import MACIRole
```

**Key design decisions**:
- Fail-closed by default: `policy_fail_closed=True`, `maci_strict_mode=True`
- MACI enabled by default since a 2025-12 audit finding classified self-validation as a critical security violation
- All extension modules (`_ext_*.py`) follow a try/except pattern; missing optional dependencies degrade gracefully, never crash import

---

## 2. Governance Pipeline

### 2.1 End-to-End Message Flow

```
HTTP POST /messages
        │
        ▼
┌───────────────────────────────┐
│  API Layer (FastAPI, port 8000) │
│  - Correlation-ID middleware    │
│  - Tenant context extraction    │
│  - Security headers             │
│  - Rate limiting (slowapi)      │
│  - Session extraction           │
└────────────────┬──────────────┘
                 │  AgentMessage (validated Pydantic model)
                 ▼
┌───────────────────────────────┐
│  MessageProcessor              │
│  (.message_processor.py, 47KB) │
│  - Constitutional hash verify  │
│  - Schema version check        │
│  - PQC signature verify (opt.) │
│  - Risk level classification   │
└────────────────┬──────────────┘
                 │
                 ▼
┌───────────────────────────────┐
│  Batch Middleware Pipeline     │
│  (middlewares/batch/)          │
│  1. BatchValidationMiddleware  │
│  2. BatchTenantIsolationMiddlw │
│  3. BatchDeduplicationMiddlw   │
│  4. BatchGovernanceMiddleware  │  ◄── MACI enforcement lives here
│  5. BatchConcurrencyMiddleware │
│  6. BatchProcessingMiddleware  │
│  7. BatchAutoTuneMiddleware    │
│  8. BatchMetricsMiddleware     │
└────────────────┬──────────────┘
                 │
       ┌─────────┴──────────┐
       │ Impact score < 0.5  │  Impact score >= 0.5
       ▼                     ▼
  Direct route       Deliberation Layer
       │             (voting, consensus,
       │              Redis pub/sub)
       └────────┬────────────┘
                │
                ▼
┌───────────────────────────────┐
│  OPA Policy Evaluation         │
│  (opa_client/, cb_opa_client)  │
│  - Policy resolution           │
│  - Circuit breaker guard       │
└────────────────┬──────────────┘
                 │ ALLOW / DENY
                 ▼
┌───────────────────────────────┐
│  Handler Execution             │
│  (bus/core.py EnhancedAgentBus)│
│  - Registered handler dispatch │
│  - Capability routing          │
│  - Kafka publish (optional)    │
└────────────────┬──────────────┘
                 │
                 ▼
┌───────────────────────────────┐
│  Audit & Observability         │
│  - SIEM event emission         │
│  - OTel span close             │
│  - Prometheus counter update   │
│  - Structured JSON log entry   │
└───────────────────────────────┘
```

### 2.2 Critical Path Invariants

Every message passing through the pipeline must satisfy all of the following, or be rejected before handler execution:

| Check | Where enforced | Failure mode |
|---|---|---|
| Constitutional hash matches `cdd01ef066bc6cf2` | `MessageProcessor` | `ConstitutionalHashMismatchError` |
| Schema version is supported | `SchemaRegistry` | `MessageValidationError` |
| MACI role permits the requested action | `BatchGovernanceMiddleware` | `MACIRoleViolationError` |
| Agent is not validating its own output | `MACIEnforcer` | `MACISelfValidationError` |
| OPA policy returns ALLOW | `PolicyResolver` | `PolicyEvaluationError` |
| Payload ≤ 10 MB (configurable) | `MessageProcessor` | `MessageValidationError` |
| Tenant context present and valid | `TenantMiddleware` | HTTP 401 |
| Rate limit not exceeded | `slowapi` limiter | HTTP 429 |

---

## 3. Subsystem Reference

### 3.1 `bus/` — Core Bus

**Purpose**: The `EnhancedAgentBus` singleton. Manages agent registration, message dispatch, routing, and lifecycle.

**Key classes**:

| Class | Module | Role |
|---|---|---|
| `EnhancedAgentBus` | `bus/core.py` | Central coordinator; start/stop lifecycle |
| `MessageHandler` | `bus/messaging.py` | Per-message-type handler registration |
| `MessageValidator` | `bus/validation.py` | Constitutional hash + schema validation |
| `GovernanceIntegration` | `bus/governance.py` | Wires MACI enforcer and OPA resolver |
| `BatchProcessor` | `bus/batch.py` | Async batch ingestion |
| `BusMetrics` | `bus/metrics.py` | Internal throughput + latency gauges |
| `get_agent_bus()` | `bus/singleton.py` | Module-level singleton accessor |

**Usage**:

```python
from enhanced_agent_bus.agent_bus import EnhancedAgentBus, get_agent_bus

bus = get_agent_bus()
await bus.start()

@bus.handler(MessageType.GOVERNANCE_PROPOSAL)
async def handle_proposal(msg: AgentMessage) -> None:
    ...

await bus.stop()
```

**Note**: `agent_bus.py` at the package root is a backward-compatibility shim that re-exports everything from `bus/`.

### 3.2 `api/` — FastAPI Application

**Purpose**: HTTP interface to the bus. Exposes REST endpoints for message submission, health, metrics, and constitutional amendment review.

**Sub-modules**:

| Module | Responsibility |
|---|---|
| `api/app.py` | `create_app()` factory, lifespan, circuit breaker setup |
| `api/config.py` | API-level constants (rate limits, timeouts, sizes) |
| `api/middleware.py` | Correlation-ID, CORS, security headers, API versioning, tenant context |
| `api/rate_limiting.py` | `slowapi`-based rate limiting; `check_batch_rate_limit()` |
| `api/routes/messages.py` | `POST /messages`, `POST /batch` |
| `api/routes/health.py` | `GET /health`, latency tracker |
| `api/routes/_tenant_auth.py` | Tenant ID extraction from JWT / header |

**Rate limit defaults** (overridable via env):
- Single message: 60 req/min per remote address
- Batch: configurable multiplier via `BATCH_RATE_LIMIT_BASE`
- Cache warming: separate budget via `CACHE_WARMING_RATE_LIMIT`

### 3.3 `models/` — Data Models

Models are split across focused modules. Import from `enhanced_agent_bus.models` for backward compatibility, or directly from the source module.

| Module | Contents |
|---|---|
| `enums.py` | `Priority`, `MessageType`, `MessageStatus`, `ValidationStatus`, `RiskLevel`, `TaskType`, `AutonomyTier` |
| `core_models.py` | `AgentMessage`, `RoutingContext`, `PQCMetadata`, `DecisionLog` |
| `batch_models.py` | `BatchRequest`, `BatchRequestItem`, `BatchResponse`, `BatchResponseStats` |
| `session_models.py` | `SessionContext`, `SessionGovernanceConfig` |
| `agent_models.py` | `SwarmAgent` |
| `schema_evolution.py` | `SchemaRegistry`, `SchemaMigrator`, versioned schema constants |

**`AgentMessage` key fields**:

```python
@dataclass
class AgentMessage:
    message_id: str         # UUID
    sender_id: str          # Registrant agent ID
    recipient_id: str       # Target agent or broadcast topic
    message_type: MessageType
    priority: Priority      # CRITICAL / HIGH / MEDIUM / LOW
    payload: dict
    constitutional_hash: str  # Must equal cdd01ef066bc6cf2
    tenant_id: str | None
    session_id: str | None
    risk_level: RiskLevel   # Set by MessageProcessor after scoring
    pqc_metadata: PQCMetadata | None
```

**Schema evolution**: The `SchemaRegistry` supports three pinned schema versions (`V1`, `V1_1`, `V1_2`) with backward-compatible migration. Use `CompatibilityChecker` before deserializing messages from external producers.

### 3.4 `policy_resolver.py` — Policy Resolution

**Purpose**: Translates a message + routing context into an OPA policy decision (ALLOW/DENY) using a configurable strategy.

**Key classes**:

| Class | Description |
|---|---|
| `PolicyResolver` | Orchestrates resolution across multiple policy sources |
| `PolicyResolutionResult` | Final decision with explanation and matched rules |
| `DynamicPolicyValidationStrategy` | Fetches live rules from OPA at `OPA_URL` |
| `StaticHashValidationStrategy` | Validates against the static constitutional hash only |
| `RustValidationStrategy` | Delegates to Rust extension (10-50x faster, optional) |
| `CompositeValidationStrategy` | Chains multiple strategies; first DENY wins |

**Configuration**:

```python
config = BusConfiguration(
    use_dynamic_policy=True,   # Enable OPA queries (default: False)
    policy_fail_closed=True,   # DENY if OPA is unreachable (default: True)
)
```

### 3.5 `registry.py` — Agent Registry and Routing

**Purpose**: Tracks registered agents (capabilities, roles, health state) and routes incoming messages to appropriate handlers.

| Class | Description |
|---|---|
| `InMemoryAgentRegistry` | Default; thread-safe dict-backed registry |
| `RedisAgentRegistry` | Distributed registry for multi-instance deployments |
| `CapabilityBasedRouter` | Routes by declared `AgentCapability` set |
| `DirectMessageRouter` | Routes by explicit `recipient_id` |

### 3.6 `middlewares/` — Request Middleware

The middleware package has two tiers:

**API-level** (`middlewares/`):
- `SessionExtractionMiddleware`: Extracts `session_id` / `tenant_id` from headers (`X-Session-ID`, `X-Tenant-ID`)
- `SecurityMiddleware` / `AIGuardrailsConfig`: AI-specific input guardrails (lazy-loaded to avoid circular imports)

**Batch pipeline** (`middlewares/batch/`): Eight composable stages applied sequentially to every batch. See Section 4 for the governance stage in detail.

### 3.7 `runtime_security.py` — Runtime Security Scanner

**Purpose**: Scans message payloads and LLM-generated content for secrets, malicious patterns, and policy violations at runtime.

**Key classes**:

| Class | Description |
|---|---|
| `RuntimeSecurityScanner` | Async scanner; call `scan_content(content)` |
| `SecurityScanResult` | Verdict + list of `SecurityEvent` findings |
| `SecurityEvent` | Single finding: type, severity, matched text |
| `SecurityEventType` | `SECRET_EXPOSURE`, `PROMPT_INJECTION`, `UNSAFE_URL`, etc. |
| `SecuritySeverity` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |

```python
from enhanced_agent_bus import scan_content, SecuritySeverity

result = await scan_content(payload_text)
if result.highest_severity == SecuritySeverity.CRITICAL:
    raise RuntimeError("Critical security finding — message rejected")
```

### 3.8 `siem_integration.py` — SIEM

**Purpose**: Emits structured security events to external SIEM systems (Splunk, QRadar, Elastic, generic CEF/LEEF).

```python
from enhanced_agent_bus import initialize_siem, log_security_event, SIEMFormat

await initialize_siem(SIEMConfig(format=SIEMFormat.SPLUNK, endpoint="https://..."))
await log_security_event(event_type="MACI_VIOLATION", severity="HIGH", details={...})
```

### 3.9 `circuit_breaker/` — Service Circuit Breakers

**Purpose**: Per-dependency circuit breakers (OPA, Redis, Kafka) with configurable thresholds, fallback strategies, and health endpoints.

**Key classes**:

| Class | Description |
|---|---|
| `ServiceCircuitBreaker` | Single dependency circuit breaker |
| `ServiceCircuitBreakerRegistry` | Global registry; get via `get_circuit_breaker_registry()` |
| `ServiceCircuitConfig` | Per-service threshold tuning |
| `CircuitState` | `CLOSED`, `OPEN`, `HALF_OPEN` |
| `FallbackStrategy` | `REJECT`, `CACHED_RESPONSE`, `DEGRADED_MODE` |

**CB configurations** for known services are pre-registered in `SERVICE_CIRCUIT_CONFIGS`. The health router (`create_circuit_health_router()`) mounts a `/circuit-breakers` endpoint showing all circuit states.

### 3.10 `llm_adapters/` — LLM Provider Adapters

**Purpose**: Model-agnostic LLM integration with constitutional compliance validation, cost optimization, and failover.

**Providers**: OpenAI, Anthropic, AWS Bedrock, Azure OpenAI, Hugging Face, OpenClaw (custom). Each adapter is imported conditionally; missing provider SDK results in `None`, not an import error.

**Key classes**:

| Class | Description |
|---|---|
| `LLMAdapterRegistry` | Registry of active adapters with circuit breakers |
| `LLMFailoverOrchestrator` | Health-score-based failover across providers |
| `CostOptimizer` | Token budget management, anomaly detection |
| `CapabilityRegistry` | Maps `CapabilityRequirement` to best available provider |
| `FallbackChain` | Ordered provider list with per-level retry config |

```python
from enhanced_agent_bus.llm_adapters import LLMAdapterRegistry, OpenAIAdapterConfig

registry = LLMAdapterRegistry()
registry.register("openai", OpenAIAdapterConfig(api_key=os.environ["OPENAI_API_KEY"]))
response = await registry.complete("openai", request)
```

### 3.11 `context_memory/` — Conversation Memory

**Purpose**: Sliding-window and summarization-based context memory for multi-turn agent conversations. Backed by Redis (optional) with in-memory fallback.

### 3.12 `durable_execution.py` — Durable Execution

**Purpose**: Deterministic replay of long-running agent workflows with checkpoint-based recovery.

### 3.13 `session_context.py` — Session Context

**Purpose**: Per-request `SessionContext` carrying tenant ID, session ID, governance config, and request-scoped state. Stored in `SessionContextStore` (Redis-backed); resolved per request via `SessionContextManager`.

---

## 4. MACI Enforcement

### 4.1 Concept

MACI (Multi-Agent Constitutional Intelligence) enforces separation of powers across the agent system, directly analogous to Trias Politica (executive / legislative / judicial). The fundamental rule is: **agents never validate their own output**. Violating this rule constitutes a Gödel bypass attack — an agent that self-validates can ratify any decision regardless of its correctness.

### 4.2 Role Model

| Role | Permitted actions | Cannot |
|---|---|---|
| `EXECUTIVE` | PROPOSE, SYNTHESIZE, QUERY | VALIDATE |
| `LEGISLATIVE` | EXTRACT_RULES, SYNTHESIZE, QUERY | PROPOSE, VALIDATE |
| `JUDICIAL` | VALIDATE, AUDIT, QUERY, EMERGENCY_COOLDOWN | PROPOSE, SYNTHESIZE |
| `AUDITOR` | AUDIT, QUERY | PROPOSE, SYNTHESIZE, VALIDATE production |
| `MONITOR` | MONITOR_ACTIVITY, QUERY | Mutate state |
| `CONTROLLER` | ENFORCE_CONTROL, QUERY | Propose, validate |
| `IMPLEMENTER` | SYNTHESIZE, QUERY | Validate own output |

**Role hierarchy** (higher number = higher authority):

```
JUDICIAL (100) > AUDITOR (90) > LEGISLATIVE (80) > EXECUTIVE (70)
> MONITOR (60) > CONTROLLER (50) > IMPLEMENTER (40)
```

**Validation constraints** (who can validate whom):

| Validator role | May validate |
|---|---|
| JUDICIAL | EXECUTIVE, LEGISLATIVE, IMPLEMENTER |
| AUDITOR | MONITOR, CONTROLLER, IMPLEMENTER |

### 4.3 Enforcement Location

MACI is enforced at `middlewares/batch/governance.py → BatchGovernanceMiddleware`, not in any metrics module. This is intentional: governance enforcement runs as a pipeline stage on every batch, ensuring no message bypasses it through an alternative code path.

**Key classes**:

| Class | Module | Description |
|---|---|---|
| `MACIEnforcer` | `maci/enforcer.py` | Core enforcement engine |
| `MACIRoleRegistry` | `maci/registry.py` | Agent → role mapping |
| `BatchGovernanceMiddleware` | `middlewares/batch/governance.py` | Pipeline integration |
| `MACIValidationStrategy` | `maci/strategy.py` | Pluggable strategy for custom enforcement |

### 4.4 Initialization and Configuration

```python
from enhanced_agent_bus.maci import MACIEnforcer, MACIRoleRegistry, MACIRole
from enhanced_agent_bus.maci import create_maci_enforcement_middleware

# Register agents
registry = MACIRoleRegistry()
registry.register_agent("proposer-001", MACIRole.EXECUTIVE)
registry.register_agent("validator-001", MACIRole.JUDICIAL)

# Wire into enforcer (strict_mode=True is the secure default)
enforcer = MACIEnforcer(registry=registry, strict_mode=True)

# Or use the factory to produce a middleware-compatible wrapper
middleware = create_maci_enforcement_middleware(registry=registry)
```

### 4.5 Self-Validation Detection

`MACIEnforcer` checks `sender_id == validator_id` on every VALIDATE action. When detected:
1. `MACISelfValidationError` is raised (always, regardless of `strict_mode`)
2. A CRITICAL security event is emitted to the structured logger
3. If SIEM is configured, a `MACI_SELF_VALIDATION` event is published

### 4.6 Cross-Role Validation Check

Before a VALIDATE action proceeds, the enforcer verifies that the validator's role appears in `VALIDATION_CONSTRAINTS[validator_role]` as a role permitted to validate the proposer's role. Violations raise `MACICrossRoleValidationError`.

### 4.7 Impact Thresholds

`BatchGovernanceMiddleware` scores each batch against four thresholds:

| Threshold | Constant | Action |
|---|---|---|
| Low | 0.3 | Standard pipeline |
| Medium | 0.5 | Additional logging |
| High | 0.7 | HITL escalation candidate |
| Critical | 0.9 | Mandatory deliberation |

### 4.8 Configuration via `BusConfiguration`

```python
config = BusConfiguration(
    enable_maci=True,          # Default: True. Set False only for testing.
    maci_strict_mode=True,     # Default: True. Fail-closed on MACI violations.
    require_independent_validator=True,   # Require cross-agent validation gate
    independent_validator_threshold=0.8,  # Minimum required validation score
)
```

Environment variable: `MACI_STRICT_MODE=true` (read by `BusConfiguration.from_environment()`).

---

## 5. Constitutional Amendment Flow

The `constitutional/` subpackage implements self-evolving constitutional governance: amendments are proposed, reviewed by humans and validators, diffed against the current constitution, tested for degradation, and activated or rolled back atomically.

### 5.1 Lifecycle

```
AmendmentProposalEngine.propose()
        │
        ▼
AmendmentProposal (status=DRAFT)
        │
        ▼
ConstitutionalHITLIntegration  ← HITLApprovalRequest → humans review
        │  approval/rejection
        ▼
ConstitutionalDiffEngine.diff()  ← produces SemanticDiff, PrincipleChange list
        │
        ▼
DegradationDetector.analyze()    ← statistical significance test on governance metrics
        │  no degradation detected
        ▼
OPAPolicyUpdater.push()          ← PolicyUpdateRequest → OPA live reload
        │
        ▼
activate_amendment()             ← ActivationSagaActivities runs atomically
        │  failure at any step
        ▼
rollback_amendment()             ← RollbackSagaActivities compensates
```

### 5.2 Key Classes

| Class | Module | Description |
|---|---|---|
| `AmendmentProposalEngine` | `proposal_engine.py` | Accepts `ProposalRequest`, validates against current constitution |
| `AmendmentProposal` | `amendment_model.py` | Proposal state machine: `DRAFT → UNDER_REVIEW → APPROVED → ACTIVE / REJECTED / ROLLED_BACK` |
| `ConstitutionalDiffEngine` | `diff_engine.py` | Semantic diff between constitutional versions |
| `DegradationDetector` | `degradation_detector.py` | Statistical regression tests (t-test, Mann-Whitney) on governance KPIs |
| `GovernanceMetricsCollector` | `metrics_collector.py` | Collects before/after metrics snapshots for comparison |
| `OPAPolicyUpdater` | `opa_updater.py` | Pushes Rego policies to live OPA instance |
| `ConstitutionalHITLIntegration` | `hitl_integration.py` | Multi-approver human-in-the-loop workflow |
| `VersionHistoryService` | `version_history.py` | Queryable audit trail of all constitutional versions |
| `ConstitutionalStorageService` | `storage.py` | Persists versions and proposals |
| `RollbackEngine` | `rollback_engine.py` | Saga-based compensation; triggers on DegradationDetector alert |

### 5.3 Review REST API

The `constitutional.review_api.router` FastAPI router mounts endpoints for amendment management:

- `GET /amendments` — list with status filter
- `GET /amendments/{id}` — detail view including diff
- `POST /amendments/{id}/approve` — JUDICIAL agent or human operator
- `POST /amendments/{id}/reject` — with mandatory rejection reason

### 5.4 Degradation Detection

`DegradationDetector` uses configurable `DegradationThresholds` and `StatisticalTest` (t-test or Mann-Whitney U) over a `TimeWindow` to detect whether a proposed amendment would degrade governance KPIs. Significance levels are configurable (`SignificanceLevel`). Severity classes (`DegradationSeverity`) map to automatic vs. human-escalated rollback decisions.

---

## 6. Deliberation Layer

### 6.1 Overview

High-impact messages (impact score ≥ configurable threshold) pass through the deliberation layer before handler execution. The layer implements multi-stakeholder weighted voting with event-driven vote collection via Redis pub/sub. Target: 100+ concurrent sessions, > 6,000 RPS.

### 6.2 Components

| Class | Description |
|---|---|
| `DeliberationQueue` / `RedisDeliberationQueue` | Queues tasks for deliberation; Redis backend for distributed deployments |
| `VotingService` | Manages `Election` lifecycle from open → closed → result |
| `VotingStrategy` | `SIMPLE_MAJORITY`, `SUPERMAJORITY`, `UNANIMITY`, `WEIGHTED` |
| `EventDrivenVoteCollector` | Subscribes to Redis pub/sub channels; receives `VoteEvent` in real time |
| `RedisVotingSystem` | High-level facade: open election, submit vote, query result |
| `ImpactScorer` | ML-powered (ONNX/PyTorch with numpy fallback) impact scoring |
| `GraphRAGContextEnricher` | Enriches deliberation context with graph-RAG retrieved governance precedents |
| `multi_approver` | Multi-approver workflow requiring N-of-M signatures |

### 6.3 Impact Scorer

`ImpactScorer` is lazy-loaded (requires numpy). Install the `[ml]` extra to enable it:

```
pip install enhanced-agent-bus[ml]
```

Without numpy, messages still route correctly — the impact score defaults to 0.0 (low impact), bypassing deliberation.

### 6.4 Redis Integration

```python
from enhanced_agent_bus.deliberation_layer import get_redis_voting_system, VotingStrategy

voting = await get_redis_voting_system(redis_url="redis://localhost:6379/0")
election_id = await voting.open_election(topic="amendment-007", strategy=VotingStrategy.SUPERMAJORITY)
await voting.cast_vote(election_id, voter_id="judicial-001", vote=True, weight=1.5)
result = await voting.close_election(election_id)
```

Vote events flow over the pub/sub channel `deliberation:votes:{election_id}`. The `EventDrivenVoteCollector` processes them asynchronously, enabling sub-second consensus on large stakeholder sets.

### 6.5 Configuration

| Field | Default | Description |
|---|---|---|
| `REDIS_URL` env var | `redis://localhost:6379/0` | Redis connection for voting |
| Quorum timeout | Configurable per `VotingService` | Time before election auto-closes |
| Weighted voting | Per-agent weight in registry | Overrides simple majority |

---

## 7. Agent Health and Healing

### 7.1 Overview

The `agent_health/` subpackage provides per-agent health tracking, anomaly detection, and autonomous healing actions governed by the agent's declared autonomy tier. It does not take any action outside its permitted tier without HITL approval.

### 7.2 Health State Machine

```
HEALTHY → DEGRADED → UNHEALTHY → QUARANTINED
    ▲         │            │
    └─────────┘            └─ HITL_REQUIRED
         (recovery)
```

### 7.3 Autonomy Tiers

Healing actions are gated by the agent's `AutonomyTier`:

| Tier | Permitted healing actions |
|---|---|
| `SUPERVISED` | Log only; all actions require human approval |
| `SEMI_AUTONOMOUS` | Reroute, soft restart; escalate quarantine to HITL |
| `AUTONOMOUS` | Restart, reroute, ramp-down; log quarantine without escalation |
| `FULLY_AUTONOMOUS` | All actions including quarantine without human approval |

### 7.4 Key Classes

| Class | Description |
|---|---|
| `AgentHealthMonitor` | Central monitor; polls metrics, transitions states, triggers healing |
| `AgentHealthStore` | Time-series health record storage per agent |
| `AgentHealthRecord` | Snapshot: error rate, latency percentiles, queue depth, consecutive failures |
| `AgentHealthThresholds` | Per-metric trigger thresholds (configurable per agent) |
| `HealingAction` | Proposed action: type, justification, rollback plan |
| `HealingActionType` | `RESTART`, `REROUTE`, `QUARANTINE`, `RAMP_DOWN`, `ESCALATE_HITL` |
| `HealingTrigger` | What caused the transition |
| `HealingOverride` | Manual override record (operator-injected) |
| `AgentBusGateway` | Issues bus-level commands (restart, suspend) on behalf of the monitor |
| `GracefulRestarter` | Drains in-flight messages before restart |
| `emit_health_metrics` | Publishes `AgentHealthRecord` fields to the Prometheus metrics collector |

### 7.5 Usage

```python
from enhanced_agent_bus.agent_health import AgentHealthMonitor, AgentHealthThresholds, AutonomyTier

monitor = AgentHealthMonitor(
    agent_id="proposer-001",
    thresholds=AgentHealthThresholds(error_rate_threshold=0.05, p99_latency_ms=200),
    autonomy_tier=AutonomyTier.SEMI_AUTONOMOUS,
)
await monitor.start()
# Monitor runs a background loop; call monitor.record_outcome(success, latency_ms) per message
```

---

## 8. Observability

### 8.1 Stack

The `observability/` subpackage provides three layers of telemetry, unified under the `SPEC_ACGS2_ENHANCED.md` specification:

| Layer | Standard | Module |
|---|---|---|
| Tracing | OpenTelemetry (OTEL) | `telemetry.py` |
| Metrics | Prometheus | `prometheus_metrics.py` |
| Logging | Structured JSON | `structured_logging.py` |

### 8.2 OpenTelemetry

```python
from enhanced_agent_bus.observability import configure_telemetry, get_tracer, get_meter

configure_telemetry(service_name="agent-bus", otlp_endpoint="http://collector:4317")
tracer = get_tracer("enhanced_agent_bus")
meter = get_meter("enhanced_agent_bus")
```

`OTEL_AVAILABLE` is `True` only when `opentelemetry-sdk` is installed. When absent, `get_tracer()` returns a no-op tracer.

### 8.3 Prometheus Metrics

`MetricsCollector` (singleton via `get_metrics_collector()`) exposes counters and histograms for all governance pipeline stages. `create_metrics_endpoint()` mounts `/metrics` on the FastAPI app.

**Named capacity-planning metrics** (record via dedicated helpers):

| Helper | Metric |
|---|---|
| `record_maci_enforcement_latency(ms)` | Histogram: MACI check duration |
| `record_opa_policy_evaluation(ms, decision)` | Histogram + counter by decision |
| `record_constitutional_validation(ms, result)` | Histogram by validation result |
| `record_deliberation_layer_duration(ms)` | Histogram: full deliberation round-trip |
| `record_z3_solver_latency(ms)` | Histogram: formal verification solver |
| `record_cache_miss(layer, reason)` | Counter by cache layer and miss reason |
| `record_batch_processing_overhead(ms)` | Histogram: batch pipeline overhead |
| `record_adaptive_threshold_decision(result)` | Counter: auto-tuner decisions |

**Alert rules**: `generate_prometheus_alert_rules()` outputs ready-to-load Prometheus alert YAML. Three severity buckets are predefined: `CRITICAL_ALERTS`, `HIGH_ALERTS`, `WARNING_ALERTS`.

### 8.4 Structured Logging

All log output uses `StructuredLogger` (backed by `structlog`). Never use `print()` in production code.

```python
from enhanced_agent_bus.observability import get_structured_logger

logger = get_structured_logger(__name__)
logger.info("message_processed", message_id=msg.message_id, latency_ms=12.4)
```

`redact_sensitive_data()` and `redact_dict()` strip credential fields before log emission. Trace context (span ID, trace ID) is injected automatically when OTel is active.

### 8.5 Decorators

```python
from enhanced_agent_bus.observability import traced, timed, metered

@traced("my_operation")
@timed("my_operation_duration")
@metered("my_operation_count")
async def my_handler(msg: AgentMessage) -> None:
    ...
```

### 8.6 Timeout Budget

`TimeoutBudgetManager` allocates per-layer timeout slices from a total request budget. `LayerTimeoutBudget` tracks remaining budget. Exceeding the budget raises `LayerTimeoutError`, which the pipeline translates into a 408 response.

---

## 9. Persistence and Saga

Two separate packages handle durable state. They have zero cross-domain imports.

### 9.1 `persistence/` — Workflow Execution

**Domain**: Workflow instance lifecycle. Use this when you need to model multi-step agent workflows with deterministic replay.

| Class | Description |
|---|---|
| `DurableWorkflowExecutor` | Runs `WorkflowInstance` steps; checkpoints state after each step |
| `ReplayEngine` | Replays workflow from any `WorkflowEvent` checkpoint |
| `WorkflowInstance` | Workflow run state: ID, status, current step, history |
| `WorkflowStep` | Single step: type, status, input/output, compensation function |
| `WorkflowCompensation` | Compensation record for rollback |
| `InMemoryWorkflowRepository` | Default; test-friendly |
| `PostgresWorkflowRepository` | Production; requires `asyncpg` |

**Step types** (`StepType`): `GOVERNANCE_VALIDATION`, `POLICY_EVALUATION`, `AMENDMENT_REVIEW`, `AGENT_ACTION`, `HUMAN_REVIEW`, `COMPENSATION`

**Status transitions** (`WorkflowStatus`): `PENDING → RUNNING → COMPLETED / FAILED / COMPENSATING → COMPENSATED`

### 9.2 `saga_persistence/` — Distributed Saga State

**Domain**: Distributed saga coordination. Use this when multiple services must coordinate with compensation on partial failure.

| Class | Description |
|---|---|
| `PersistedSagaState` | Complete saga state for persistence |
| `SagaCheckpoint` | Point-in-time saga snapshot |
| `CompensationEntry` | Ordered compensation action for rollback |
| `SagaStateRepository` | Abstract interface |
| `RedisSagaStateRepository` | Redis hash storage; TTL-based expiry |
| `PostgresSagaStateRepository` | JSONB storage; optimistic locking via `version` field |
| `create_saga_repository()` | Factory; reads `SAGA_BACKEND` env var (`redis` / `postgres`) |

**Saga states** (`SagaState`): `PENDING → RUNNING → COMPLETED / FAILED / COMPENSATING → COMPENSATED`

**Distributed locking**: The Redis repository uses `SETNX`-based locks (`saga:lock:{saga_id}`) with configurable `DEFAULT_LOCK_TIMEOUT_SECONDS` (default: 30 s) to prevent concurrent modification.

**Multi-tenant isolation**: `PersistedSagaState.tenant_id` is indexed in both backends. All queries are scoped by tenant.

```python
from enhanced_agent_bus.saga_persistence import create_saga_repository, SagaBackend

repo = await create_saga_repository(SagaBackend.REDIS, redis_url="redis://localhost:6379/0")
saga = PersistedSagaState(saga_name="constitutional_amendment", tenant_id="tenant-abc")
await repo.save(saga)
```

### 9.3 `durable_execution.py`

Long-running agent execution with retry, deterministic replay, and OTel instrumentation. Distinct from `persistence/` in that it focuses on single-agent execution traces, not multi-service sagas.

---

## 10. Enterprise Features

### 10.1 Multi-Tenancy (`multi_tenancy/`)

**Phase 10 Task 1**. Provides request-scoped tenant isolation using PostgreSQL Row-Level Security.

**Architecture**:
- `TenantContext`: asyncio context var holding the current `Tenant` for the request scope
- `TenantMiddleware`: extracts tenant from JWT or `X-Tenant-ID` header; calls `set_current_tenant()`
- `RLSPolicyManager`: creates and manages `CREATE POLICY` statements on the database
- `TenantAwareRepository`: wraps SQLAlchemy sessions; sets `SET LOCAL app.current_tenant_id` for every query
- `TenantManager`: lifecycle (create, suspend, quota enforcement, event publishing)
- `TenantQuota`: per-tenant resource limits (message rate, storage, agent count)

**System tenant**: `SYSTEM_TENANT_ID` is a reserved tenant for internal governance operations. `is_system_tenant()` and `system_tenant_session()` are provided for administrative contexts that bypass per-tenant RLS.

**RLS setup**:

```python
from enhanced_agent_bus.multi_tenancy import create_tenant_rls_policies, enable_rls_for_table

await enable_rls_for_table(engine, "agent_messages")
await create_tenant_rls_policies(engine, "agent_messages", tenant_id_column="tenant_id")
```

### 10.2 Enterprise SSO (`enterprise_sso/`)

**Phase 10 Task 2**. SAML 2.0 and OIDC integration with automatic MACI role mapping from IdP groups.

**Key classes**:

| Class | Description |
|---|---|
| `EnterpriseSSOService` | Top-level SSO service; handles authentication flows |
| `TenantSSOConfigManager` | Per-tenant IdP config (SAML metadata URL, OIDC discovery) |
| `SAML2Handler` / `OIDCHandler` | Protocol-specific authentication |
| `ProtocolHandlerFactory` | Selects handler by `SSOProtocolType` |
| `RoleMappingService` | Maps IdP group claims to `MACIRole` values |
| `SSOAuthenticationMiddleware` | FastAPI middleware; populates `SSOSessionContext` |
| `SessionGovernanceClient` | SDK for session lifecycle in SSO context |

**Role mapping**:

```python
from enhanced_agent_bus.enterprise_sso import RoleMappingService, RoleMappingRule

service = RoleMappingService()
service.add_rule(RoleMappingRule(
    idp_group="governance-reviewers",
    maci_role=MACIRole.JUDICIAL,
    tenant_id="tenant-prod",
))
```

**Kafka streaming**: `GovernanceEventProducer` / `GovernanceEventConsumer` in `kafka_streaming.py` publish SSO and governance events to Kafka topics with configurable `DeliveryGuarantee` (`AT_LEAST_ONCE`, `EXACTLY_ONCE`) and `SchemaRegistry` integration.

**Constitutional gap analysis**: `ConstitutionalPolicyScanner` scans SSO configurations for missing constitutional coverage. `GapTracker` and `RemediationEngine` provide automated remediation suggestions.

**Migration tooling**: `ShadowModeExecutor` runs legacy policy decisions in parallel with new constitutional decisions for validation before cutover. `TrafficRouter` gradually shifts traffic using `TrafficConfig`.

---

## 11. Extension Points

### 11.1 `_ext_*.py` Pattern

Optional capabilities are loaded via 15 `_ext_*.py` modules at the package root. Each module:
1. Attempts the import inside `try/except ImportError`
2. Falls back to stub objects if the dependency is absent
3. Exports an `_EXT_ALL` list that is spread into the package `__all__`

This pattern means the package always imports successfully regardless of optional dependencies. Feature availability is signaled via boolean flags.

| Module | Flag | Contents |
|---|---|---|
| `_ext_circuit_breaker.py` | `SERVICE_CIRCUIT_BREAKER_AVAILABLE` | `ServiceCircuitBreaker`, `ServiceCircuitBreakerRegistry` |
| `_ext_circuit_breaker_clients.py` | — | CB-wrapped Redis, OPA, Kafka clients |
| `_ext_pqc.py` | `PQC_VALIDATORS_AVAILABLE` | `validate_constitutional_hash_pqc`, `PQCConfig` |
| `_ext_cache_warming.py` | — | Cache pre-warming utilities |
| `_ext_chaos.py` | — | Chaos engineering faults for testing |
| `_ext_cognitive.py` | — | Cognitive load modeling for agent decisions |
| `_ext_context_memory.py` | — | Redis-backed conversation memory |
| `_ext_context_optimization.py` | — | Context window optimization (Phase 4) |
| `_ext_decision_store.py` | — | Decision audit store |
| `_ext_explanation_service.py` | — | Decision explanation generation |
| `_ext_langgraph.py` | — | LangGraph graph orchestration |
| `_ext_mcp.py` | — | Model Context Protocol server integration |
| `_ext_performance.py` | `PERF_*` | Performance profiling, memory profiler |
| `_ext_persistence.py` | — | Saga persistence wrappers |
| `_ext_response_quality.py` | — | Response quality scoring (Phase 5) |

### 11.2 Adding a New Backend

1. Create a new directory under `packages/enhanced_agent_bus/` for the backend.
2. Implement the relevant ABC: `SagaStateRepository` for saga backends, `BaseLLMAdapter` for LLM backends, `TenantRepository` for tenant storage.
3. Declare optional deps in `pyproject.toml` under `[project.optional-dependencies]`.
4. Create `_ext_yourbackend.py` with try/except import and `_EXT_ALL`.
5. Add the star-import and `_EXT_ALL` spread to `__init__.py`.

**Do not** add optional dependency packages to `[project.dependencies]` (the core requirements). Keep the core importable without any optional deps installed.

### 11.3 Adding a New LLM Provider

```python
# packages/enhanced_agent_bus/llm_adapters/myprovider_adapter.py
from .base import BaseLLMAdapter, LLMRequest, LLMResponse

class MyProviderAdapter(BaseLLMAdapter):
    async def complete(self, request: LLMRequest) -> LLMResponse:
        ...
    async def health_check(self) -> HealthCheckResult:
        ...
```

Then add a guarded import in `llm_adapters/__init__.py`:

```python
try:
    from .myprovider_adapter import MyProviderAdapter
except ImportError:
    MyProviderAdapter = None
```

Register in `LLMAdapterRegistry` at startup. The `CapabilityRegistry` and `LLMFailoverOrchestrator` will automatically include the new provider in routing decisions.

### 11.4 Rust Extension

A Rust/PyO3 extension (`rust/`) provides a 10–50x validation speedup. Build and install with:

```bash
cd packages/enhanced_agent_bus/rust
maturin develop --release
```

Once installed, `RustValidationStrategy` is automatically preferred over `StaticHashValidationStrategy`. The `USE_RUST` feature flag reflects availability. See `rust/AGENTS.md` for CI build instructions and platform-specific notes.

---

## 12. Configuration Reference

### 12.1 `BusConfiguration` Fields

All fields have safe defaults. Override via `BusConfiguration(field=value)` or `BusConfiguration.from_environment()`.

| Field | Type | Default | Description |
|---|---|---|---|
| `redis_url` | `str` | `redis://localhost:6379` | Redis connection string |
| `kafka_bootstrap_servers` | `str` | `localhost:9092` | Kafka broker list |
| `audit_service_url` | `str` | `http://localhost:8001` | Audit event sink |
| `use_dynamic_policy` | `bool` | `False` | Enable OPA policy queries |
| `policy_fail_closed` | `bool` | `True` | DENY if OPA unreachable |
| `use_kafka` | `bool` | `False` | Publish messages to Kafka |
| `use_redis_registry` | `bool` | `False` | Use Redis-backed agent registry |
| `use_rust` | `bool` | `True` | Use Rust validation extension if available |
| `enable_metering` | `bool` | `True` | Enable token/request metering |
| `enable_maci` | `bool` | `True` | Enable MACI enforcement |
| `maci_strict_mode` | `bool` | `True` | Fail-closed on MACI violations |
| `enable_pqc` | `bool` | `False` | Enable post-quantum cryptography |
| `pqc_mode` | `str` | `classical_only` | `classical_only`, `hybrid`, `pqc_only` |
| `pqc_key_algorithm` | `str` | `dilithium3` | `dilithium2`, `dilithium3`, `dilithium5` |
| `enable_session_governance` | `bool` | `False` | Per-session governance config override |
| `session_context_ttl` | `int` | `3600` | Session context TTL (seconds) |
| `require_independent_validator` | `bool` | `False` | Require cross-agent validation gate |
| `independent_validator_threshold` | `float` | `0.8` | Minimum validation score |
| `enable_dtmc` | `bool` | `False` | DTMC trajectory risk scoring |
| `dtmc_intervention_threshold` | `float` | `0.8` | P(unsafe) threshold for HITL escalation |
| `opal_enabled` | `bool` | `True` | Enable OPAL live policy distribution |
| `opal_server_url` | `str` | `http://opal-server:7002` | OPAL server endpoint |
| `max_queue_size` | `int` | `10_000` | Back-pressure queue limit |
| `max_message_size_bytes` | `int` | `1_048_576` | Per-message size cap (1 MiB) |
| `queue_full_behavior` | `str` | `reject` | `reject` (HTTP 429) or `drop_oldest` |
| `constitutional_hash` | `str` | `cdd01ef066bc6cf2` | Must match embedded hash |

### 12.2 Environment Variables (PM2 / Runtime)

These are the variables set by `ecosystem.config.cjs` and read by `BusConfiguration.from_environment()`.

| Variable | Required | Example | Description |
|---|---|---|---|
| `CONSTITUTIONAL_HASH` | Yes | `cdd01ef066bc6cf2` | Constitutional hash; must match package constant |
| `MACI_STRICT_MODE` | Yes | `true` | Fail-closed MACI enforcement |
| `OPA_URL` | Yes | `http://localhost:8181` | OPA policy engine endpoint |
| `REDIS_URL` | Yes | `redis://localhost:6379/0` | Redis connection |
| `ENVIRONMENT` | Yes | `development` / `production` | Runtime mode |
| `LOG_LEVEL` | No | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `PYTHONPATH` | Yes | `/repo:/repo/src` | Must include project root and `src/` |
| `PYTHONUNBUFFERED` | Yes | `1` | Unbuffered stdout for PM2 log capture |
| `KAFKA_BOOTSTRAP` | No | `localhost:19092` | Kafka brokers (only if `USE_KAFKA=true`) |
| `USE_DYNAMIC_POLICY` | No | `false` | Enable OPA policy queries |
| `POLICY_FAIL_CLOSED` | No | `true` | OPA unreachable → DENY |
| `USE_KAFKA` | No | `false` | Publish messages to Kafka |
| `AUDIT_SERVICE_URL` | No | `http://localhost:8001` | Audit event sink URL |
| `SAGA_BACKEND` | No | `redis` / `postgres` | Saga state storage backend |
| `OPAL_SERVER_URL` | No | `http://opal-server:7002` | OPAL live policy distribution |
| `OPAL_CLIENT_TOKEN` | No | — | OPAL authentication token |
| `PM2_UVICORN_WORKERS` | No | `2` | Uvicorn worker count (production) |
| `JWT_SECRET` | No (gateway) | — | JWT signing secret for API gateway |

### 12.3 `api/config.py` Constants

These constants are not environment-configurable by default; change them by subclassing `BusConfiguration` or overriding at startup.

| Constant | Value | Description |
|---|---|---|
| `API_VERSION` | `v2` | URL prefix |
| `DEFAULT_API_PORT` | `8000` | uvicorn bind port |
| `DEFAULT_WORKERS` | `1` | uvicorn worker count |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | Per-IP rate limit |
| `BATCH_RATE_LIMIT_BASE` | `10` | Batch endpoint rate limit (lower because batches are expensive) |
| `MAX_ITEM_CONTENT_SIZE` | `1 MB` | Per-batch-item content cap |
| `CIRCUIT_BREAKER_FAIL_MAX` | `5` | Failures before CB opens |
| `CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS` | `60` | CB reset timeout |

### 12.4 Deployment

The agent bus is managed by PM2 via `ecosystem.config.cjs`:

```bash
# Start agent bus
pm2 start ecosystem.config.cjs --only agent-bus-8000

# Production (2 uvicorn workers)
pm2 start ecosystem.config.cjs --only agent-bus-8000 --env production

# Tail logs
pm2 logs agent-bus-8000

# Health check
curl http://localhost:8000/health
```

**PYTHONPATH** must include both the project root and `src/` for cross-package imports (`src.core.shared.*`). The PM2 config constructs this automatically as `[PROJECT_ROOT, PROJECT_ROOT/src].join(":")`.

**Docker**: A `Dockerfile` is present at the package root for containerized deployments. A `Dockerfile.demo` and `Dockerfile.dev` provide lighter images for demos and local development.

---

*Document generated from source inspection of `packages/enhanced_agent_bus/` at constitutional hash `cdd01ef066bc6cf2`. Update this document whenever a new subsystem is added or a public API contract changes.*
