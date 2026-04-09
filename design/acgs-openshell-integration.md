# ACGS + OpenShell + OpenClaw Integration

## Purpose

This document defines a practical integration pattern for running OpenClaw inside OpenShell while
delegating governance decisions, MACI separation-of-powers, compliance verdicts, and durable audit
logging to ACGS.

The target deployment model is:

- OpenClaw handles channels, sessions, and agent loops.
- OpenShell enforces sandbox, egress, filesystem, process, and inference boundaries.
- ACGS acts as the governance control plane and audit spine.

## Architecture

### Logical Overview

```mermaid
flowchart LR
    U[User / External Channel] --> OC[OpenClaw<br/>Session / Skills / Agent Loop]

    OC -->|Action Intent / Tool Request| OS[OpenShell Sandbox]
    OS -->|Governance RPC| ACGS[ACGS Governance API]

    ACGS --> CV[Constitutional Validation]
    ACGS --> MACI[MACI Role Enforcement]
    ACGS --> DELIB[Deliberation / HITL / Voting]
    ACGS --> COMP[Compliance Verdict]
    ACGS --> AUDIT[Audit Trail]

    ACGS --> PERSIST[Postgres / Redis / OPA / Shared Memory]

    OS -->|Allowed external calls| EXT[External APIs / SaaS]
    OS -->|Managed inference| LLM[LLM Providers / Local Models]

    ACGS -->|Decision: allow / deny / escalate| OC
```

### Boundary Model

```mermaid
flowchart TD
    A[User Intent] --> B[OpenClaw]
    B --> C[ACGS Decision Boundary]
    C -->|allow| D[OpenShell Enforcement Boundary]
    C -->|deny| X[Blocked]
    C -->|escalate| H[Human / Validator Review]
    H -->|approved| D
    H -->|rejected| X
    D --> E[External World]
```

### High-Risk Action Flow

```mermaid
sequenceDiagram
    participant User
    participant OC as OpenClaw
    participant OS as OpenShell
    participant AG as ACGS
    participant VH as Validator/Human
    participant EXT as External API

    User->>OC: Request action
    OC->>AG: POST /governance/evaluate-action
    AG-->>OC: decision=escalate

    OC->>VH: Submit for approval
    VH->>AG: Approve action
    AG-->>OC: decision=allow + decision_id

    OC->>OS: Execute action in sandbox
    OS->>EXT: Perform bounded request
    EXT-->>OS: Result
    OS-->>OC: Execution result

    OC->>AG: POST /governance/record-outcome
    AG-->>OC: Audit recorded
```

## Design Principles

- OpenClaw proposes actions but does not self-authorize high-risk execution.
- OpenShell enforces hard runtime boundaries but does not interpret business governance semantics.
- ACGS makes governance decisions but does not directly own external side effects.
- High-risk actions require both a governance decision and an execution boundary.
- Proposer, validator, and executor identities must remain distinct for governed actions.

## Role Mapping

| Role | Runtime Mapping | Responsibility |
| ---- | --------------- | -------------- |
| Proposer | OpenClaw primary agent | Draft action intent |
| Validator | Human reviewer or validator agent | Approve or reject |
| Executor | OpenShell sandbox worker | Execute approved action |

### MACI Rules

- The proposer must not approve its own high-risk action.
- The validator should not execute the same high-risk action.
- The executor should consume a bounded approval artifact rather than broad governance authority.

## Integration Contract

### Action Envelope

All governed actions should be normalized into a stable envelope before they reach ACGS.

Required fields:

- `request_id`
- `session_id`
- `actor`
- `resource`
- `action_type`
- `operation`
- `risk_level`
- `payload_hash`
- `requires_network`
- `requires_secret`

This avoids coupling governance rules to individual OpenClaw skills.

### Governance Decision Outcomes

ACGS returns one of:

- `allow`
- `deny`
- `escalate`
- `require_separate_executor`

### OpenShell Policy Intent

OpenShell should apply deny-by-default outbound controls and explicitly allow:

- the ACGS governance endpoint
- approved model providers
- approved SaaS targets required by the action

Example intent:

```yaml
network:
  default: deny
  allow:
    - host: acgs.internal.example.com
      methods: [GET, POST]
    - host: api.github.com
      methods: [GET, POST]
filesystem:
  deny_write:
    - /host
    - /secrets
process:
  deny_privilege_escalation: true
inference:
  route_managed: true
```

## Minimal API Surface

Recommended first-pass endpoints:

- `POST /governance/evaluate-action`
- `POST /governance/submit-for-approval`
- `POST /governance/review-approval`
- `POST /governance/record-outcome`

These cover:

- decisioning
- approval handoff
- validator review
- outcome recording

## Audit Requirements

Every governed action should leave an audit trail with:

- request ID
- decision ID
- session ID
- sandbox ID
- proposer / validator / executor IDs
- action type
- resource URI
- payload hash
- compliance verdict
- decision reason codes
- execution outcome
- external references

## Rollout Plan

### Phase 0: Observe Only

- OpenClaw calls ACGS for high-risk actions.
- ACGS responds, but execution is not yet blocked.
- Collect false positives, latency, and decision coverage.

### Phase 1: Soft Gate

- Human approval becomes required for a small set of write actions.
- OpenShell still allows only the minimal approved egress set.

### Phase 2: Hard Gate

- No high-risk action runs without an ACGS decision.
- Denials are enforced by both the governance layer and runtime boundary.

### Phase 3: Full MACI

- Proposer / validator / executor are fully separated.
- Shared memory writes and external mutations all require governed flow.

## MVP Scope

Recommended first governed action classes:

- `http.write`
- `filesystem.write`
- `github.write`
- `memory.shared_write`

This is enough to validate:

- action normalization
- governance RPC
- approval flow
- runtime enforcement
- durable audit closure

## Code Skeleton

The initial Python skeleton for this integration lives in:

- `src/acgs_lite/integrations/openshell_governance.py`

It provides:

- Pydantic request/response models
- a FastAPI router factory
- a lightweight app factory
- placeholder decision logic suitable for a PoC

