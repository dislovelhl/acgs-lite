# ACGS Landing Page Copy

**Date:** 2026-03-27
**Status:** Draft for implementation
**Target:** `packages/propriety-ai` homepage and supporting pages

---

## Hero Section

### Headline
**AI agents can take actions. They need a constitution.**

### Subheadline
ACGS is the constitutional governance layer for agentic systems. Enforce machine-readable rules
before execution, prevent self-validation by architecture, and produce audit-ready evidence for
regulated AI workflows.

### Supporting text
Guardrails filter outputs. GRC tracks policies. Agent frameworks orchestrate flow.
**ACGS governs actions.**

### CTAs
- Primary: **Get Started**
- Secondary: **Run the EU AI Act Check**

### Code snippet
```bash
pip install acgs-lite
```

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")  # Governed.
```

---

## Problem Section

### Heading
AI infrastructure got good at helping agents act. It is still weak at constraining them.

### Body
Prompts are not governance. Dashboards are not runtime control. Post-hoc review is not prevention.

Once agents can approve, deny, deploy, escalate, or call tools, the real questions change:
- Who proposed the action?
- Who validated it?
- Which rules were active?
- Can you prove governance happened after the fact?

Most teams still cannot answer those questions cleanly.

---

## Solution Section

### Heading
Govern actions inside the runtime

### Body
ACGS embeds governance directly into agent execution. Before an agent can act, ACGS can evaluate
constitutional rules, enforce role boundaries, and record what happened against a specific
governance state.

### Three pillars

**Constitutional Rules**  
Machine-readable governance policies with versioned rule state, templates, and composable
constitutions.

**Structural Separation**  
Proposer, validator, executor, and observer roles stay distinct so the same agent does not approve
its own high-risk action.

**Audit Evidence**  
Every decision is tied to rule state and written into a tamper-evident audit trail for compliance,
security, and post-incident review.

---

## Proof Strip

- Machine-readable constitutional rules
- Structural anti-self-validation
- Tamper-evident audit trail
- Compliance-oriented outputs
- Developer-first integration

---

## Why ACGS Is Different

### Heading
The missing layer in the AI stack

### Body
- **Governance platforms** organize oversight and compliance workflows
- **Guardrails tools** filter prompts and outputs
- **Policy engines** evaluate general policy-as-code
- **Agent frameworks** orchestrate execution

ACGS adds the missing layer: governance inside execution.

---

## Use Cases

### Heading
Where ACGS fits first

- Merge request governance for AI-generated code
- High-risk internal copilots
- Regulated decision-support systems
- Tool-using agents in healthcare, finance, and compliance-heavy environments

---

## How It Works

### Heading
Define rules. Wrap the agent. Govern every action.

**1. Define your constitution**
```yaml
rules:
  - id: SAFE-001
    text: Agent must not provide financial advice
    severity: critical
    keywords: [invest, buy stocks, financial advice]
```

**2. Wrap your agent**
```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
```

**3. Evaluate actions inline**
```text
Action: "Approve the deployment"
Decision: REQUIRE_VALIDATOR_REVIEW
Rule state: hash-bound
Audit: chain-verified
```

---

## Compliance Section

### Heading
Built for regulated environments

### Body
ACGS maps governance outputs to major frameworks including the EU AI Act, NIST AI RMF,
ISO/IEC 42001, SOC 2 + AI, HIPAA + AI, GDPR Article 22, ECOA/FCRA, NYC LL 144, and OECD AI.

The goal is not to replace your governance program. The goal is to give it enforceable runtime
controls and evidence your security, legal, and compliance teams can use.

### CTA
**Run the EU AI Act Check**

---

## Integrations Section

### Heading
Fits into the stack you already use

- Anthropic (`acgs-lite[anthropic]`)
- OpenAI (`acgs-lite[openai]`)
- LangChain (`acgs-lite[langchain]`)
- LiteLLM (`acgs-lite[litellm]`)
- Google GenAI (`acgs-lite[google]`)
- LlamaIndex (`acgs-lite[llamaindex]`)
- AutoGen (`acgs-lite[autogen]`)
- CrewAI (`acgs-lite[crewai]`)
- MCP (`acgs-lite[mcp]`)
- A2A (`acgs-lite[a2a]`)
- GitLab CI/CD

---

## Footer CTA

### Heading
If your agents can act in the world, they need more than prompts.

### Body
They need governance at runtime.

### CTA
**Get Started** — `pip install acgs-lite`
