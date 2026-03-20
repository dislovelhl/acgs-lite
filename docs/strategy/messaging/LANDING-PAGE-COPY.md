# Propriety.ai Landing Page Copy

**Date:** 2026-03-19
**Status:** Draft for implementation
**Target:** propriety-ai/src/pages/Home.tsx and components

---

## Hero Section

### Headline
**HTTPS for AI**

### Subheadline
Constitutional governance for your AI systems. Cryptographic proof that every decision is compliant.

### Supporting text
560 nanoseconds of overhead. 9 regulatory frameworks. 5 lines of code. EU AI Act enforcement begins August 2, 2026.

### CTAs
- Primary: **Get Started Free** (-> pip install instructions / signup)
- Secondary: **View Pricing** (-> /pricing)

### Code snippet (hero visual)
```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")  # Governed.
```

---

## Problem Section

### Heading
The most powerful decision-making engines in history. No brakes.

### Body
$203 billion invested in AI in 2025. Less than 1% in governance infrastructure.

A single mother applies for a mortgage. 742 credit score. 12 years of stable employment. The AI rejects her in 340 milliseconds. No human review. No appeal. No audit trail.

The EU AI Act takes full enforcement August 2026. Fines up to 7% of global annual revenue. Most companies have zero governance infrastructure.

### Stat bar
| 340ms | 7% | $0 |
|-------|-----|-----|
| Time for AI to deny a mortgage | Maximum fine under EU AI Act | What most companies spend on AI governance |

---

## Solution Section

### Heading
Governance that runs faster than a cache hit

### Body
ACGS validates every AI action against constitutional rules in 560 nanoseconds. No exceptions. No performance excuse to turn it off.

### Three pillars

**Constitutional Engine**
Define governance rules in YAML. Keywords, regex patterns, severity levels. Context-aware matching that doesn't false-flag constructive actions. Tamper-proof constitutional hash.

**MACI Separation of Powers**
Agents never validate their own output. Proposer, Validator, Executor — enforced at the middleware level. The same separation of powers we built for human institutions, now for AI.

**Compliance Proof**
Every validation produces an auditable receipt. Cryptographic chain verification. Nine regulatory frameworks mapped to 125 compliance checklist items. Your auditor gets evidence, not promises.

---

## Metrics Bar

| 560ns | 9 | 125 | 2.8M | 3,820 |
|-------|---|-----|------|-------|
| P50 validation latency | Regulatory frameworks | Compliance items (72 auto) | Validations/sec (Rust) | Automated tests |

---

## Framework Coverage Section

### Heading
Nine regulatory frameworks. One tool.

### Grid

| Framework | Jurisdiction | Enforcement | ACGS Coverage |
|-----------|-------------|-------------|---------------|
| EU AI Act | EU (27 states) | Aug 2026, 7% fine | Articles 12, 13, 14 |
| GDPR | EU | Active, 4% fine | Articles 22, 35, 40 |
| NIST AI RMF | US (federal) | Procurement gate | GOVERN/MAP/MEASURE/MANAGE |
| ISO 42001 | International | Certification | AI Management System |
| SOC 2 + AI | International | Enterprise gate | Trust Service Criteria |
| HIPAA + AI | US (healthcare) | Active, $1.5M/violation | PHI protection |
| ECOA/FCRA | US (finance) | Active, unlimited damages | Fair lending |
| NYC LL 144 | New York City | Active, $1,500/day | Employment automation |
| OECD AI | 46 countries | Baseline standard | AI Principles |

---

## How It Works Section

### Heading
Three steps. Five minutes. Full governance.

### Steps

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

**3. Every action is governed**
```
Action: "Should I invest in crypto?"
Decision: DENY (SAFE-001)
Latency: 487ns
Audit: chain-verified, hash cdd01ef066bc6cf2
```

---

## Integration Section

### Heading
Works with everything you already use

### Grid (logos + pip install extras)
- OpenAI (`acgs-lite[openai]`)
- Anthropic (`acgs-lite[anthropic]`)
- LangChain (`acgs-lite[langchain]`)
- LiteLLM (`acgs-lite[litellm]`)
- Google GenAI (`acgs-lite[google]`)
- LlamaIndex (`acgs-lite[llamaindex]`)
- AutoGen (`acgs-lite[autogen]`)
- CrewAI (`acgs-lite[crewai]`)
- MCP (`acgs-lite[mcp]`)
- A2A (`acgs-lite[a2a]`)
- GitLab CI/CD (pipeline stage)

---

## EU AI Act Countdown Section

### Heading
**[X] days until EU AI Act enforcement**

### Body
High-risk AI provisions take effect August 2, 2026. Fines up to 7% of global annual revenue or EUR 35 million — whichever is higher.

### CTA
**Take the free assessment** — see where you stand against Article 12, 13, and 14 requirements.

---

## Pricing Preview Section

### Heading
Start free. Scale with compliance needs.

| Community | Pro | Team | Enterprise |
|-----------|-----|------|------------|
| **Free** | **$299/mo** | **$999/mo** | **Custom** |
| Full governance engine | + Compliance reports | + All 9 frameworks | + Everything |
| Local audit trail | + Cloud audit sync | + SSO/SAML | + On-premise |
| MACI separation | + 3 frameworks | + Change workflows | + Dedicated engineer |
| Community support | + Email support | + Priority support | + 1h SLA |
| [Install] | [Start Free Trial] | [Start Free Trial] | [Contact Sales] |

---

## Social Proof Section (when available)

### Pre-launch (use metrics)
- "3,820 automated tests"
- "847 benchmark scenarios"
- "118 optimization experiments"
- "Open source under AGPL-3.0"

### Post-launch (use logos + quotes)
- Design partner logos
- Quote from partner champion
- PyPI download count
- GitHub star count

---

## Footer CTA

### Heading
Your AI makes decisions. Can you prove they're governed?

### CTA
**Get Started Free** — `pip install acgs-lite`

### Secondary links
- Documentation
- GitHub
- Pricing
- EU AI Act Guide
- AGPL FAQ
