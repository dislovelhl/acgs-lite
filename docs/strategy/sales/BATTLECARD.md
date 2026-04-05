# ACGS Sales Battlecard

**Last updated:** 2026-03-27
**Audience:** founder, design partners, early enterprise conversations

---

## 30-Second Pitch

> "ACGS is the constitutional governance layer for AI agents. It governs actions inside the
> runtime, keeps proposer and validator roles separate, and leaves behind audit-ready evidence tied
> to rule state. Guardrails filter outputs. ACGS governs actions."

---

## Elevator Pitches by Audience

### To a Developer

> "`pip install acgs-lite`. Wrap your agent in five lines. ACGS evaluates machine-readable
> governance rules before actions execute, keeps validation structurally separate, and records what
> happened in an audit trail your team can inspect."

### To a CTO / VP Engineering

> "Your systems are moving from answers to actions. ACGS gives you a runtime governance layer for
> those actions: machine-readable rules, separated proposer and validator roles, and evidence your
> security and compliance teams can review."

### To a CISO / DPO

> "ACGS helps turn governance from policy documents into enforceable runtime controls and reviewable
> evidence. It gives teams auditable records, explicit approval boundaries, and outputs mapped to
> major compliance expectations."

### To an Investor

> "The market has orchestration, observability, and safety controls, but it still lacks a runtime
> governance plane for agentic systems. ACGS is building that missing layer."

---

## Objection Handling

### Technical

| Objection | Response |
|-----------|----------|
| "We already use OPA / Rego" | OPA is excellent for general policy-as-code. ACGS is the AI-native governance layer for agentic systems. Keep OPA for infrastructure policy and use ACGS for governed agent actions. |
| "We already use Guardrails AI" | Guardrails AI focuses on validators, IO controls, and output reliability. ACGS focuses on governance process: who can act, who can validate, and what evidence is left behind. Different layers. |
| "We don't need the latency story" | The point of the hot path is not only speed. It is making governance cheap enough that teams do not disable it when systems move into production paths. |
| "Rule-based systems are too simple" | For regulatory and institutional controls, determinism and traceability are advantages. ACGS is not trying to replace model intelligence. It is trying to govern it. |

### Trust

| Objection | Response |
|-----------|----------|
| "Small company, no track record" | The product can be inspected directly, integrated locally, and evaluated as infrastructure. The adoption motion is developer-first rather than all-or-nothing platform replacement. |
| "AGPL is a blocker" | The commercial path needs to be handled clearly up front. Internal evaluation is easy; production deployment questions should route immediately into the commercial conversation. |
| "What if you disappear?" | Buyers keep the code, the logs, and the deployment surface. The control plane is designed to reduce dependency risk, not increase it. |

### Competitive

| Objection | Response |
|-----------|----------|
| "We already have a governance platform" | Governance platforms organize oversight and workflow. ACGS is the runtime enforcement layer underneath that program. |
| "We already have AI security tools" | Security products stop attacks and unsafe content. ACGS governs approved action paths and leaves behind reviewable evidence. |
| "We already use LangGraph" | Good. LangGraph orchestrates the flow. ACGS governs what the graph is allowed to do. |

---

## Competitive Positioning

### vs Guardrails AI

| Dimension | ACGS | Guardrails AI |
|-----------|------|---------------|
| Focus | Runtime governance | LLM output quality |
| Output | Governed action + evidence | Validated/corrected output |
| Role separation | Structural | None |
| Positioning | Governance layer | Validation layer |

**Key line:** "Guardrails AI helps validate outputs. ACGS governs actions."

### vs OPA

| Dimension | ACGS | OPA |
|-----------|------|-----|
| Focus | AI agent governance | General policy |
| Core entity | Agent action | Generic policy decision |
| Framing | Constitutional layer | Policy engine |
| Positioning | Agent governance | Infrastructure policy |

**Key line:** "OPA governs infrastructure policy. ACGS governs agent actions."

### vs LangGraph

| Dimension | ACGS | LangGraph |
|-----------|------|-----------|
| Focus | Runtime governance | Orchestration |
| Primary job | Decide if an action may proceed | Coordinate workflow and state |
| Relationship | Complementary | Complementary |

**Key line:** "LangGraph orchestrates flow. ACGS governs actions."

---

## Qualification Signals

### Strong

- Team has agents or copilots that can take actions
- Buyer cares about reviewability, approval boundaries, or audit evidence
- Regulated or risk-sensitive environment
- Existing stack already includes orchestration or guardrails, but not governance

### Weak

- Pure experimentation with no real workflows
- Interest only in prompt filtering
- Buyer wants only a compliance dashboard

---

## Design Partner Pitch

> "We're looking for a small set of design partners building serious agentic systems in regulated
> or risk-sensitive environments. You get direct founder access and priority feature input. We get
> rapid feedback on what runtime governance actually needs to look like in production."
