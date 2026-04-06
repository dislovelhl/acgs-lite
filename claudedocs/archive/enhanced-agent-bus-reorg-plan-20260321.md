# Enhanced Agent Bus Reorg Plan

Date: 2026-03-21

## Objective

Reduce `packages/enhanced_agent_bus/` from a platform super-package into a smaller execution
kernel with explicit dependencies on adjacent packages.

This plan treats the current package as four mixed concerns:

1. Message execution core
2. Deliberation and HITL orchestration
3. Governance control plane
4. Protocol and integration surfaces

The target state is a repository with clearer package ownership, a smaller runtime trust
boundary, and fewer "optional import" branches inside the message execution path.

## Target Package Layout

### 1. `packages/acgs-bus-core`

Purpose: execution-plane kernel for governed message handling.

Keep here:

- `bus/`
- `message_processor.py`
- `batch_processor.py`
- `batch_models.py`
- `models.py`
- `validators.py`
- `interfaces.py`
- `pipeline/`
- `middlewares/`
- `api/` for runtime-only routes
- `maci/`
- `opa_client/`
- `persistence/`
- `saga_persistence/`
- `context_memory/`
- `runtime/`
- `exceptions/`
- `config.py`
- `governance_constants.py`

Rules:

- Own the critical execution path.
- No authoring, copilot, UI, or model-training concerns.
- Only depend outward on stable interfaces.

### 2. `packages/acgs-deliberation`

Purpose: high-impact review, consensus, HITL, and impact-routing workflows.

Move here:

- `deliberation_layer/`
- `impact_scorer_infra/`
- `agent_health/` if it remains tied to approval/review lifecycle

Rules:

- Own voting, queueing, timeouts, review escalation, and impact scoring.
- Expose one narrow interface back to `acgs-bus-core`:
  - `score(message, context) -> impact result`
  - `route(review request) -> review outcome`

### 3. `packages/acgs-governance-control-plane`

Purpose: policy authoring, constitutional amendments, attestation, and compliance publication.

Move here:

- `constitutional/`
- `governance/`
- `policy/`
- `policies/`
- `policy_copilot/`
- `attestation/`
- `compliance_layer/`
- `verification/`
- `verification_layer/`
- `snapshot/`
- `prov/`

Rules:

- Own policy lifecycle and publication.
- Publish immutable policy snapshots consumed by `acgs-bus-core`.
- No direct runtime message dispatch responsibility.

### 4. `packages/acgs-mcp-runtime`

Purpose: MCP client/server/protocol runtime.

Move here:

- `mcp/`
- `mcp_integration/`
- `mcp_server/`

Rules:

- Keep protocol and transport churn away from the bus core.
- Expose typed adapters consumed by core or other packages.

### 5. `packages/acgs-agent-runtime`

Purpose: LLM adapters, agent orchestration, and assistant-facing runtime helpers.

Move here:

- `llm_adapters/`
- `ai_assistant/`
- `agents/`
- `langgraph_orchestration/`
- `meta_orchestrator/`
- `orchestration/`
- `swarm_intelligence/`
- `adaptive_governance/`

Rules:

- Own model/provider integration and orchestration logic.
- Do not sit inside the execution trust boundary for every message.

### 6. `packages/acgs-platform-shared`

Purpose: shared operational primitives used by multiple packages.

Move here only if reused by at least two packages:

- `observability/`
- `circuit_breaker/`
- `monitoring/`
- `contracts/`
- selected `components/`

Rules:

- No business logic.
- Only cross-cutting infrastructure and types.

## What Stays in `enhanced_agent_bus` During Transition

During transition, keep `packages/enhanced_agent_bus/` as the compatibility shell.

It should gradually become:

- import shims
- deprecated facades
- a thin composition layer wiring the new packages together

It should stop being the primary home for new implementation code.

## First-Batch Moves

First batch should optimize for high cohesion and low breakage.

### Batch 1A: Extract deliberation

Create `packages/acgs-deliberation/` and move:

- `packages/enhanced_agent_bus/deliberation_layer/`
- `packages/enhanced_agent_bus/impact_scorer_infra/`

Why first:

- Already has strong internal cohesion.
- Already behaves like a subsystem with its own queue, scoring, voting, and workflow logic.
- Core bus can depend on a narrow deliberation interface without deep rewiring.

### Batch 1B: Extract MCP runtime

Create `packages/acgs-mcp-runtime/` and move:

- `packages/enhanced_agent_bus/mcp/`
- `packages/enhanced_agent_bus/mcp_integration/`
- `packages/enhanced_agent_bus/mcp_server/`

Why second:

- Protocol/server code changes faster than the execution kernel.
- Current package mixes client and server concerns into one runtime bundle.

### Batch 1C: Freeze bus-core boundary

After 1A and 1B, declare the core-owned surface:

- `message_processor.py`
- `bus/`
- `pipeline/`
- `middlewares/`
- `maci/`
- `opa_client/`
- `persistence/`
- `saga_persistence/`
- `context_memory/`
- runtime-only `api/`

At this point, any new directory added outside this list should be challenged by default.

## Detailed Path Mapping

### Keep in bus-core

| Current path | Target package | Notes |
| --- | --- | --- |
| `packages/enhanced_agent_bus/message_processor.py` | `packages/acgs-bus-core/` | Core ingress engine |
| `packages/enhanced_agent_bus/bus/` | `packages/acgs-bus-core/` | Handler dispatch and lifecycle |
| `packages/enhanced_agent_bus/pipeline/` | `packages/acgs-bus-core/` | Execution pipeline contract |
| `packages/enhanced_agent_bus/middlewares/` | `packages/acgs-bus-core/` | Canonical middleware path |
| `packages/enhanced_agent_bus/maci/` | `packages/acgs-bus-core/` | Runtime separation of powers |
| `packages/enhanced_agent_bus/opa_client/` | `packages/acgs-bus-core/` | Runtime policy evaluation |
| `packages/enhanced_agent_bus/persistence/` | `packages/acgs-bus-core/` | Workflow persistence |
| `packages/enhanced_agent_bus/saga_persistence/` | `packages/acgs-bus-core/` | Saga persistence |
| `packages/enhanced_agent_bus/context_memory/` | `packages/acgs-bus-core/` | Runtime context only |
| `packages/enhanced_agent_bus/api/` | `packages/acgs-bus-core/` | Runtime HTTP API only |

### Move to deliberation

| Current path | Target package | Notes |
| --- | --- | --- |
| `packages/enhanced_agent_bus/deliberation_layer/` | `packages/acgs-deliberation/` | Full subsystem move |
| `packages/enhanced_agent_bus/impact_scorer_infra/` | `packages/acgs-deliberation/` | Impact scoring backend |

### Move to MCP runtime

| Current path | Target package | Notes |
| --- | --- | --- |
| `packages/enhanced_agent_bus/mcp/` | `packages/acgs-mcp-runtime/` | MCP client/runtime |
| `packages/enhanced_agent_bus/mcp_integration/` | `packages/acgs-mcp-runtime/` | Integration glue |
| `packages/enhanced_agent_bus/mcp_server/` | `packages/acgs-mcp-runtime/` | Server and tools |

### Move to governance control plane

| Current path | Target package | Notes |
| --- | --- | --- |
| `packages/enhanced_agent_bus/constitutional/` | `packages/acgs-governance-control-plane/` | Amendment and storage workflows |
| `packages/enhanced_agent_bus/governance/` | `packages/acgs-governance-control-plane/` | Governance-specific services |
| `packages/enhanced_agent_bus/policy/` | `packages/acgs-governance-control-plane/` | Policy domain logic |
| `packages/enhanced_agent_bus/policies/` | `packages/acgs-governance-control-plane/` | Policy assets and bundles |
| `packages/enhanced_agent_bus/policy_copilot/` | `packages/acgs-governance-control-plane/` | Authoring copilot |
| `packages/enhanced_agent_bus/attestation/` | `packages/acgs-governance-control-plane/` | Attestation and evidence |
| `packages/enhanced_agent_bus/compliance_layer/` | `packages/acgs-governance-control-plane/` | Compliance mapping |
| `packages/enhanced_agent_bus/verification/` | `packages/acgs-governance-control-plane/` | Verification workflows |
| `packages/enhanced_agent_bus/verification_layer/` | `packages/acgs-governance-control-plane/` | Verification adapters |
| `packages/enhanced_agent_bus/snapshot/` | `packages/acgs-governance-control-plane/` | Governance snapshots |
| `packages/enhanced_agent_bus/prov/` | `packages/acgs-governance-control-plane/` | Provenance/evidence |

### Move to agent runtime

| Current path | Target package | Notes |
| --- | --- | --- |
| `packages/enhanced_agent_bus/llm_adapters/` | `packages/acgs-agent-runtime/` | Provider adapters |
| `packages/enhanced_agent_bus/ai_assistant/` | `packages/acgs-agent-runtime/` | Assistant logic |
| `packages/enhanced_agent_bus/agents/` | `packages/acgs-agent-runtime/` | Agent abstractions |
| `packages/enhanced_agent_bus/langgraph_orchestration/` | `packages/acgs-agent-runtime/` | Graph orchestration |
| `packages/enhanced_agent_bus/meta_orchestrator/` | `packages/acgs-agent-runtime/` | Higher-order orchestration |
| `packages/enhanced_agent_bus/orchestration/` | `packages/acgs-agent-runtime/` | Runtime orchestration |
| `packages/enhanced_agent_bus/swarm_intelligence/` | `packages/acgs-agent-runtime/` | Swarm logic |
| `packages/enhanced_agent_bus/adaptive_governance/` | `packages/acgs-agent-runtime/` | Runtime adaptation |

## Interfaces to Freeze Before Moving Code

These contracts should be made explicit before any directory move:

### Bus to deliberation

- `ImpactScorerProtocol`
- `AdaptiveRouterProtocol`
- `DeliberationQueueProtocol`
- one top-level `DeliberationService` facade

### Bus to policy

- `PolicyDecision`
- `PolicySnapshotRef`
- `PolicyEvaluationClient`

### Bus to MCP

- `ToolInvocationRequest`
- `ToolInvocationResult`
- `MCPTransportConfig`

If these interfaces are not frozen first, directory moves will just move coupling around.

## Compatibility Strategy

Use a three-stage compatibility approach.

### Stage 1

- Create new packages.
- Re-export old imports from `enhanced_agent_bus`.
- Keep tests green with shims.

### Stage 2

- Update internal imports package by package.
- Add deprecation warnings for old import paths.

### Stage 3

- Remove implementation from legacy locations.
- Keep only compatibility wrappers for one release cycle.

## Risks

### Risk 1: Import churn without real decoupling

Mitigation:

- Freeze interfaces first.
- Move tests with the implementation they validate.

### Risk 2: Core message processor still depends on too many optional packages

Mitigation:

- Ban new optional feature imports inside `message_processor.py`.
- Route optional behavior through explicit adapters.

### Risk 3: API route sprawl keeps leaking control-plane features back into bus-core

Mitigation:

- Split runtime API routes from product/control-plane routes.
- Runtime API remains in bus-core.
- Authoring/admin APIs move outward.

## Immediate Next Actions

1. Create package skeletons for `acgs-bus-core`, `acgs-deliberation`, and `acgs-mcp-runtime`.
2. Move `deliberation_layer/` and its tests first.
3. Introduce `enhanced_agent_bus.deliberation` compatibility re-exports.
4. Move `mcp/`, `mcp_integration/`, and `mcp_server/` second.
5. Only after those succeed, start extracting constitutional/policy authoring concerns.

## Non-Goals

- No full package rename in one step.
- No attempt to perfect every subdomain before first extraction.
- No simultaneous rewrite of runtime behavior and repository layout.

The first success criterion is narrower:

`enhanced_agent_bus` should stop growing as the default destination for unrelated new features.
